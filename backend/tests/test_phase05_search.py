import time
import uuid
from datetime import timedelta

import httpx
import pytest
from bson import ObjectId

from tests.test_phase03_vendors import BASE, admin_client, mongo, submit
from tests.test_phase04_catalog import jpeg

PREFIX = "TEST5_"
CRON_SECRET = __import__("dotenv").dotenv_values(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", ".env"))["WEBHOOK_CRON_SECRET"]
TAG = uuid.uuid4().hex[:6]


@pytest.fixture(scope="module", autouse=True)
def search_cleanup():
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
    mongo.search_queries.delete_many({"query": "[redacted]"})
    mongo.cron_runs.delete_many({"run_id": {"$regex": "^test-"}})


def client():
    c = httpx.Client(base_url=BASE, timeout=90)
    mongo.rate_limits.delete_many({"key": {"$regex": "^(register|login):"}})
    email = f"delivered+p5{uuid.uuid4().hex[:8]}@resend.dev"
    assert c.post("/auth/register", json={"name": f"{PREFIX}Vendor", "email": email, "password": "TestPass12345"}).status_code == 201
    u = mongo.users.find_one({"email": email})
    mongo.users.update_one({"_id": u["_id"]}, {"$set": {"email_verified_at": u["created_at"], "status": "active"}})
    return c


def vendor():
    slug = f"test5-{uuid.uuid4().hex[:6]}"
    c, adm = client(), admin_client()
    app = submit(c, slug)
    assert adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "approve"}).status_code == 200
    assert c.post("/vendor/store/publish").status_code == 200
    return c, adm, slug


def live(c, adm, title, category, price, stock, tags=(), desc="Handmade by artisans with care and tradition."):
    sku = f"S{uuid.uuid4().hex[:7]}".upper()
    r = c.post("/vendor/products", json={"title": title, "description": desc, "category_slug": category, "tags": list(tags), "sku": sku,
                                         "price_minor": price, "variants": [{"sku": sku, "price_minor": price, "initial_stock": stock}]})
    pid = r.json()["product"]["id"]
    assert c.post(f"/vendor/products/{pid}/images", files={"file": ("a.jpg", jpeg(60, 60), "image/jpeg")}).status_code == 201
    assert c.post(f"/vendor/products/{pid}/submit").status_code == 200
    assert adm.post(f"/admin/products/{pid}/moderate", json={"decision": "approve"}).status_code == 200
    return pid


@pytest.fixture(scope="module")
def catalog():
    a, adm, slug_a = vendor()
    b, _, slug_b = vendor()
    ids = {
        "scarf": live(a, adm, f"Kente {TAG} Scarf", "fashion", 4500, 5, ["kente", TAG]),
        "dress": live(a, adm, f"Ankara {TAG} Wrap Dress", "fashion-dresses", 9000, 0, [TAG, "ankara"], desc=f"Bold kente-inspired print dress {TAG}."),
        "shea": live(b, adm, f"Raw Shea {TAG} Butter", "beauty", 1500, 20, [TAG, "skincare"]),
        "basket": live(b, adm, f"Bolga {TAG} Market Basket", "home-living", 6000, 3, [TAG, "woven"]),
    }
    draft = a.post("/vendor/products", json={"title": f"Hidden Draft {TAG}", "description": "Not approved yet, must never show.", "category_slug": "fashion",
                                            "sku": f"H{uuid.uuid4().hex[:7]}".upper(), "price_minor": 100}).json()["product"]["id"]
    return {"a": a, "b": b, "adm": adm, "slug_a": slug_a, "slug_b": slug_b, "ids": ids, "draft": draft}


def s(**params):
    r = httpx.get(f"{BASE}/catalog/search", params=params, headers={"DNT": "1"}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def titles(res):
    return [p["title"] for p in res["data"]]


def test_full_text_relevance_partial_and_exclusions(catalog):
    res = s(q=f"kente {TAG}")
    assert res["mode"] == "text" and res["sort"] == "relevance"
    assert titles(res)[0] == f"Kente {TAG} Scarf"  # title match outranks description-only match
    assert f"Ankara {TAG} Wrap Dress" in titles(res)
    assert all("Hidden Draft" not in t for t in titles(s(q=TAG, limit=50)))
    part = s(q=f"bolg {TAG[:4]}")
    assert part["mode"] == "partial" and titles(part) == [f"Bolga {TAG} Market Basket"]
    assert s(q=f"zzqx{TAG}")["total"] == 0
    assert s(q="   ")["mode"] == "browse"


def test_filter_combinations_and_facets(catalog):
    assert set(titles(s(q=TAG, category="fashion"))) == {f"Kente {TAG} Scarf", f"Ankara {TAG} Wrap Dress"}  # includes subcategory
    assert titles(s(q=TAG, category="fashion-dresses")) == [f"Ankara {TAG} Wrap Dress"]
    assert titles(s(q=TAG, category="fashion", in_stock="true")) == [f"Kente {TAG} Scarf"]
    assert set(titles(s(q=TAG, min="20", max="60"))) == {f"Kente {TAG} Scarf", f"Bolga {TAG} Market Basket"}
    assert titles(s(q=TAG, vendor=catalog["slug_b"], max="20")) == [f"Raw Shea {TAG} Butter"]
    both = s(q=TAG, vendor=f"{catalog['slug_a']},{catalog['slug_b']}", in_stock="true", sort="price-asc")
    assert titles(both) == [f"Raw Shea {TAG} Butter", f"Kente {TAG} Scarf", f"Bolga {TAG} Market Basket"]
    assert titles(s(q=TAG, sort="price-desc"))[0] == f"Ankara {TAG} Wrap Dress"
    f = s(q=TAG)["facets"]
    assert f["in_stock"] == 3 and f["price"] == {"min": 1500, "max": 9000}
    assert {v["slug"]: v["count"] for v in f["vendors"]} == {catalog["slug_a"]: 2, catalog["slug_b"]: 2}
    fashion = next(c for c in f["categories"] if c["slug"] == "fashion")
    assert fashion["product_count"] == 2 and any(k["slug"] == "fashion-dresses" and k["product_count"] == 1 for k in fashion["children"])
    assert httpx.get(f"{BASE}/catalog/search", params={"min": "50", "max": "10"}).status_code == 422
    assert httpx.get(f"{BASE}/catalog/search", params={"min": "abc"}).status_code == 422
    assert httpx.get(f"{BASE}/catalog/search", params={"category": "nope"}).status_code == 404
    assert httpx.get(f"{BASE}/catalog/search", params={"sort": "random"}).status_code == 422


def test_pagination_and_visibility_rules(catalog):
    p1, p2, p3 = s(q=TAG, limit=2, page=1, sort="price-asc"), s(q=TAG, limit=2, page=2, sort="price-asc"), s(q=TAG, limit=2, page=3, sort="price-asc")
    assert p1["total"] == 4 and p1["has_more"] and not p2["has_more"] and p3["data"] == []
    assert len(set(titles(p1)) | set(titles(p2))) == 4
    # stock change updates availability filter
    dress = catalog["a"].get(f"/vendor/products/{catalog['ids']['dress']}").json()["variants"][0]["id"]
    assert catalog["a"].post(f"/vendor/inventory/{dress}/adjust", json={"quantity": 2, "reason": "restock"}).status_code == 200
    assert f"Ankara {TAG} Wrap Dress" in titles(s(q=TAG, in_stock="true"))
    # suspended vendor's products disappear from search and suggestions
    vid = mongo.vendors.find_one({"slug": catalog["slug_b"]})["_id"]
    assert catalog["adm"].post(f"/admin/vendors/{vid}/suspend", json={"reason": "TEST search check"}).status_code == 200
    assert s(q=TAG)["total"] == 2
    assert httpx.get(f"{BASE}/catalog/suggest", params={"q": "raw shea"}).json()["products"] == []
    assert catalog["adm"].post(f"/admin/vendors/{vid}/reactivate", json={"reason": "TEST done"}).status_code == 200
    assert catalog["b"].post("/vendor/store/publish").status_code == 200
    assert s(q=TAG)["total"] == 4


def test_suggestions(catalog):
    r = httpx.get(f"{BASE}/catalog/suggest", params={"q": "bolga"}).json()
    assert any(p["title"] == f"Bolga {TAG} Market Basket" for p in r["products"])
    assert "skincare" in httpx.get(f"{BASE}/catalog/suggest", params={"q": "skinc"}).json()["keywords"]
    assert any(c["slug"] == "beauty" for c in httpx.get(f"{BASE}/catalog/suggest", params={"q": "beau"}).json()["categories"])
    assert httpx.get(f"{BASE}/catalog/suggest", params={"q": "k"}).json()["products"] == []
    assert all("Hidden" not in p["title"] for p in httpx.get(f"{BASE}/catalog/suggest", params={"q": "hidden"}).json()["products"])


def test_search_analytics_privacy(catalog):
    before = mongo.search_queries.count_documents({})
    s(q=f"dnt {TAG}")  # DNT header -> not logged
    assert mongo.search_queries.count_documents({}) == before
    for _ in range(2):
        httpx.get(f"{BASE}/catalog/search", params={"q": f"  KENTE   {TAG} "})
    httpx.get(f"{BASE}/catalog/search", params={"q": f"nothing{TAG}"})
    httpx.get(f"{BASE}/catalog/search", params={"q": "jane.doe@example.com"})
    httpx.get(f"{BASE}/catalog/search", params={"q": f"kente {TAG}", "page": 2})  # later pages not logged
    doc = mongo.search_queries.find_one({"query": f"kente {TAG}"})
    assert doc and set(doc) <= {"_id", "query", "result_count", "mode", "filters", "day", "created_at", "expires_at"}
    assert doc["expires_at"] - doc["created_at"] == timedelta(days=180)
    assert mongo.search_queries.count_documents({"query": f"kente {TAG}"}) == 2
    assert not mongo.search_queries.find_one({"query": {"$regex": "example.com"}})
    rep = catalog["adm"].get("/admin/search-analytics", params={"days": 7}).json()
    assert any(q["query"] == f"kente {TAG}" and q["count"] == 2 for q in rep["top_queries"])
    assert all(q["query"] != f"nothing{TAG}" for q in rep["zero_result_queries"])  # single searches hidden (k=2)
    assert rep["privacy"]["min_count"] == 2
    assert catalog["a"].get("/admin/search-analytics").status_code == 403
    assert httpx.get(f"{BASE}/admin/search-analytics").status_code == 401


def test_performance_at_catalog_scale(catalog):
    vendor_id = mongo.vendors.find_one({"slug": catalog["slug_a"]})["_id"]
    owner = mongo.vendors.find_one({"_id": vendor_id})["owner_user_id"]
    cat = mongo.categories.find_one({"slug": "books"})
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    docs = [{"vendor_id": vendor_id, "owner_user_id": owner, "slug": f"perf-{TAG}-{i}", "title": f"Perf {TAG} Book {i} history novel",
             "description": "Bulk generated performance record.", "category_slug": "books", "category_id": cat["_id"], "tags": ["perf", TAG],
             "sku": f"PERF{TAG}{i}".upper(), "price_minor": 500 + i, "price_min_minor": 500 + i, "price_max_minor": 500 + i, "currency": "USD",
             "status": "active", "in_stock": i % 2 == 0, "option_names": [], "approved_at": now, "created_at": now, "updated_at": now} for i in range(1500)]
    mongo.products.insert_many(docs)
    plan = mongo.products.find({"$text": {"$search": "history"}, "status": "active"}).explain()
    assert "TEXT" in str(plan["queryPlanner"]["winningPlan"])
    times = []
    for params in ({"q": f"history {TAG}"}, {"category": "books", "in_stock": "true", "sort": "price-asc"}, {"q": "novel", "min": "6", "max": "15", "page": 3}):
        t = time.perf_counter()
        res = s(**params, limit=24)
        times.append(time.perf_counter() - t)
        assert res["total"] > 0 and len(res["data"]) <= 24
    assert max(times) < 2.0, times
    mongo.products.delete_many({"slug": {"$regex": f"^perf-{TAG}-"}})


def test_low_stock_preference_and_digest_cron(catalog):
    a = catalog["a"]
    assert a.put("/vendor/preferences", json={"low_stock_alerts": "daily"}).status_code == 422
    assert a.put("/vendor/preferences", json={"low_stock_alerts": "weekly"}).json()["low_stock_alerts"] == "weekly"
    assert a.get("/vendor/products").json()["low_stock_alerts"] == "weekly"
    url = f"{BASE}/cron/low-stock-digest"
    assert httpx.post(url).status_code == 401
    assert httpx.post(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
    auth = {"Authorization": f"Bearer {CRON_SECRET}"}
    assert httpx.post(url, headers=auth, content=b"[1]").status_code == 400
    run = f"test-{uuid.uuid4().hex[:8]}"
    r = httpx.post(url, headers={**auth, "X-Webhook-Id": run}, json={"event": "schedule.triggered", "run_id": run, "data": None})
    assert r.status_code == 202 and r.json()["status"] == "accepted"
    assert httpx.post(url, headers={**auth, "X-Webhook-Id": run}).json()["status"] == "duplicate"
    for _ in range(30):
        doc = mongo.cron_runs.find_one({"run_id": run})
        if doc["status"] != "queued":
            break
        time.sleep(1)
    assert doc["status"] == "done", doc
    assert doc["result"]["sent"] + doc["result"]["failed"] >= 1  # vendor A has low-stock items and chose weekly
    assert a.put("/vendor/preferences", json={"low_stock_alerts": "instant"}).status_code == 200
    assert ObjectId.is_valid(catalog["draft"])
