# Phase 05 extended: facet scoping by category, visibility of pending/rejected/unpublished, query edge cases, analytics privacy (Sec-GPC, purge perms)
import uuid

import httpx
import pytest

from tests.test_phase03_vendors import BASE, admin_client, mongo, submit
from tests.test_phase04_catalog import jpeg

PREFIX = "TEST5X_"
TAG = "x" + uuid.uuid4().hex[:6]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    users = [u["_id"] for u in mongo.users.find({"name": {"$regex": f"^{PREFIX}"}})]
    vendors = [v["_id"] for v in mongo.vendors.find({"owner_user_id": {"$in": users}})]
    for coll in ("products", "product_variants", "product_images", "inventory", "stock_adjustments", "product_imports", "vendor_stores"):
        mongo[coll].delete_many({"vendor_id": {"$in": vendors}})
    mongo.vendors.delete_many({"_id": {"$in": vendors}})
    for coll, field in (("vendor_applications", "user_id"), ("vendor_policy_acceptances", "user_id"), ("files", "owner_user_id"),
                        ("sessions", "user_id"), ("auth_tokens", "user_id")):
        mongo[coll].delete_many({field: {"$in": users}})
    mongo.users.delete_many({"_id": {"$in": users}})
    mongo.search_queries.delete_many({"query": {"$regex": TAG}})


def vendor():
    c = httpx.Client(base_url=BASE, timeout=90)
    mongo.rate_limits.delete_many({"key": {"$regex": "^register:"}})
    email = f"delivered+p5x{uuid.uuid4().hex[:8]}@resend.dev"
    assert c.post("/auth/register", json={"name": f"{PREFIX}Vendor", "email": email, "password": "TestPass12345"}).status_code == 201
    u = mongo.users.find_one({"email": email})
    mongo.users.update_one({"_id": u["_id"]}, {"$set": {"email_verified_at": u["created_at"], "status": "active"}})
    slug = f"test5x-{uuid.uuid4().hex[:6]}"
    adm = admin_client()
    app = submit(c, slug)
    assert adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "approve"}).status_code == 200
    assert c.post("/vendor/store/publish").status_code == 200
    return c, adm, slug


def product(c, adm, title, category, price, stock, decision="approve"):
    sku = f"X{uuid.uuid4().hex[:7]}".upper()
    r = c.post("/vendor/products", json={"title": title, "description": f"Handmade item {TAG} with care.", "category_slug": category, "tags": [TAG],
                                         "sku": sku, "price_minor": price, "variants": [{"sku": sku, "price_minor": price, "initial_stock": stock}]})
    pid = r.json()["product"]["id"]
    assert c.post(f"/vendor/products/{pid}/images", files={"file": ("a.jpg", jpeg(60, 60), "image/jpeg")}).status_code == 201
    if decision is None:
        return pid
    assert c.post(f"/vendor/products/{pid}/submit").status_code == 200
    if decision == "pending":
        return pid
    body = {"decision": decision} if decision == "approve" else {"decision": "reject", "note": "TEST rejected for search check"}
    assert adm.post(f"/admin/products/{pid}/moderate", json=body).status_code == 200, body
    return pid


@pytest.fixture(scope="module")
def cat():
    a, adm, sa = vendor()
    b, _, sb = vendor()
    product(a, adm, f"Kente {TAG} Shawl", "fashion", 4000, 4)
    product(a, adm, f"Ankara {TAG} Gown", "fashion-dresses", 12000, 0)
    product(b, adm, f"Cocoa {TAG} Body Butter", "beauty", 2000, 10)
    product(b, adm, f"Pending {TAG} Thing", "beauty", 2500, 10, decision="pending")
    product(b, adm, f"Rejected {TAG} Thing", "beauty", 2500, 10, decision="reject")
    product(b, adm, f"Draft {TAG} Thing", "beauty", 2500, 10, decision=None)
    return {"a": a, "b": b, "adm": adm, "sa": sa, "sb": sb}


def s(**p):
    r = httpx.get(f"{BASE}/catalog/search", params=p, headers={"DNT": "1"}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def test_facets_scoped_to_category(cat):
    f = s(q=TAG, category="beauty")["facets"]
    assert {v["slug"]: v["count"] for v in f["vendors"]} == {cat["sb"]: 1}
    assert f["price"] == {"min": 2000, "max": 2000} and f["in_stock"] == 1
    assert {c["slug"] for c in f["categories"]} >= {"fashion", "beauty"}  # category facet not scoped (switchable)
    f2 = s(q=TAG, category="fashion")["facets"]
    assert {v["slug"]: v["count"] for v in f2["vendors"]} == {cat["sa"]: 2}
    assert f2["price"] == {"min": 4000, "max": 12000} and f2["in_stock"] == 1
    browse = s(category="fashion-dresses", vendor=cat["sa"])
    assert [p["title"] for p in browse["data"]] == [f"Ankara {TAG} Gown"]


def test_pending_rejected_draft_never_visible(cat):
    res = s(q=TAG, limit=50)
    t = [p["title"] for p in res["data"]]
    assert res["total"] == 3 and not any(w in x for x in t for w in ("Pending", "Rejected", "Draft"))
    for w in ("pending", "rejected", "draft"):
        sug = httpx.get(f"{BASE}/catalog/suggest", params={"q": f"{w} {TAG}"}).json()
        assert sug["products"] == []
    # facets ignore hidden products too
    assert s(q=TAG, category="beauty")["facets"]["price"]["max"] == 2000


def test_unpublished_store_hidden_everywhere(cat):
    assert cat["b"].post("/vendor/store/unpublish").status_code == 200
    try:
        res = s(q=TAG, limit=50)
        assert res["total"] == 2 and all(v["slug"] != cat["sb"] for v in res["facets"]["vendors"])
        assert s(q=TAG, vendor=cat["sb"])["total"] == 0
        assert httpx.get(f"{BASE}/catalog/suggest", params={"q": "cocoa"}).json()["products"] == [] or \
            all(TAG not in p["title"] for p in httpx.get(f"{BASE}/catalog/suggest", params={"q": "cocoa"}).json()["products"])
    finally:
        assert cat["b"].post("/vendor/store/publish").status_code == 200
    assert s(q=TAG)["total"] == 3


def test_query_edge_cases(cat):
    assert s(q=f'"kente {TAG}"')["total"] >= 1  # phrase
    for q in ("(.*", "[[", "$where", "a" * 150, "<script>"):
        r = httpx.get(f"{BASE}/catalog/search", params={"q": q}, headers={"DNT": "1"})
        assert r.status_code == 200, (q, r.text)
    assert s(q=TAG, vendor="does-not-exist")["total"] == 0
    assert httpx.get(f"{BASE}/catalog/search", params={"limit": 500}).status_code == 422
    assert httpx.get(f"{BASE}/catalog/search", params={"min": "-1"}).status_code == 422
    assert s(q=TAG, min="40", max="40")["total"] == 1  # inclusive bounds
    assert s(q=TAG, sort="newest")["sort"] == "newest"
    assert s(sort="relevance")["sort"] == "featured"  # relevance without q falls back


def test_analytics_sec_gpc_and_purge_permissions(cat):
    before = mongo.search_queries.count_documents({})
    httpx.get(f"{BASE}/catalog/search", params={"q": f"gpc {TAG}", "log": "true"}, headers={"Sec-GPC": "1"})
    assert mongo.search_queries.count_documents({}) == before
    assert cat["a"].delete("/admin/search-analytics").status_code == 403
    assert httpx.delete(f"{BASE}/admin/search-analytics").status_code == 401
    rep = cat["adm"].get("/admin/search-analytics", params={"days": 9999}).json()
    assert rep["days"] == 180
