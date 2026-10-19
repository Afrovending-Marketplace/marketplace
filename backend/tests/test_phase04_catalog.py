import io
import uuid

import httpx
import pytest
from PIL import Image

from tests.test_phase03_vendors import BASE, admin_client, mongo, submit

PREFIX = "TEST4_"  # own prefix so other modules' cleanups (TEST_) never race with this module under xdist


@pytest.fixture(scope="module", autouse=True)
def catalog_cleanup():
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
    mongo.categories.delete_many({"name": {"$regex": "^TEST "}})


def verified_client():
    c = httpx.Client(base_url=BASE, timeout=90)
    mongo.rate_limits.delete_many({"key": {"$regex": "^(register|login):"}})
    email = f"delivered+p4{uuid.uuid4().hex[:8]}@resend.dev"
    r = c.post("/auth/register", json={"name": f"{PREFIX}Vendor", "email": email, "password": "TestPass12345"})
    assert r.status_code == 201, r.text
    u = mongo.users.find_one({"email": email})
    mongo.users.update_one({"_id": u["_id"]}, {"$set": {"email_verified_at": u["created_at"], "status": "active"}})
    return c


def jpeg(w=2400, h=1800):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def vendor():
    slug = f"test-{uuid.uuid4().hex[:6]}"
    c, adm = verified_client(), admin_client()
    app = submit(c, slug)
    assert adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "approve"}).status_code == 200
    assert c.post("/vendor/store/publish").status_code == 200
    return c, adm, slug


def product_body(sku, **kw):
    return {"title": "TEST Kente Scarf", "description": "Handwoven kente scarf made in Bonwire, Ghana.", "category_slug": "fashion",
            "tags": ["Kente", "scarf"], "sku": sku, "price_minor": 4500, "currency": "USD", **kw}


def test_create_validate_variants_images_and_moderation():
    c, adm, slug = vendor()
    sku = f"T{uuid.uuid4().hex[:6]}".upper()
    assert c.post("/vendor/products", json=product_body(sku, price_minor=0)).status_code == 422
    assert c.post("/vendor/products", json=product_body(sku, category_slug="nope")).status_code == 422
    assert c.post("/vendor/products", json=product_body(sku, currency="XYZ")).status_code == 422
    r = c.post("/vendor/products", json=product_body(sku, variants=[{"sku": sku, "price_minor": 4500, "initial_stock": 3}]))
    assert r.status_code == 201, r.text
    pid = r.json()["product"]["id"]
    assert r.json()["product"]["status"] == "draft" and r.json()["variants"][0]["quantity_on_hand"] == 3
    assert c.post(f"/vendor/products/{pid}/submit").status_code == 422  # no image yet
    body = {"option_names": ["Size", "Color"], "variants": [
        {"sku": f"{sku}-S-RED", "options": {"Size": "S", "Color": "Red"}, "price_minor": 4500, "initial_stock": 10},
        {"sku": f"{sku}-M-RED", "options": {"Size": "M", "Color": "Red"}, "price_minor": 5000, "initial_stock": 2}]}
    dup = {**body, "variants": [body["variants"][0], {**body["variants"][1], "options": {"Size": "S", "Color": "Red"}}]}
    assert c.put(f"/vendor/products/{pid}/variants", json=dup).status_code == 422
    r = c.put(f"/vendor/products/{pid}/variants", json=body)
    assert r.status_code == 200, r.text
    active = [v for v in r.json()["variants"] if v["status"] == "active"]
    assert len(active) == 2 and r.json()["product"]["price_max_minor"] == 5000
    assert c.post(f"/vendor/products/{pid}/images", files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 422
    assert c.post(f"/vendor/products/{pid}/images", files={"file": ("fake.jpg", b"notanimage", "image/jpeg")}).status_code == 422
    r = c.post(f"/vendor/products/{pid}/images", files={"file": ("big.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 201, r.text
    img = r.json()["images"][0]
    assert max(img["width"], img["height"]) == 2400 and img["size"] > 0
    served = httpx.get(BASE.replace("/api/v1", "") + img["url"])
    assert served.status_code == 200 and Image.open(io.BytesIO(served.content)).size[0] <= 1600
    assert c.post(f"/vendor/products/{pid}/submit").json()["product"]["status"] == "pending_review"
    assert httpx.get(f"{BASE}/catalog/products", params={"vendor": slug}).json()["total"] == 0
    assert adm.post(f"/admin/products/{pid}/moderate", json={"decision": "reject", "note": ""}).status_code == 422
    assert adm.post(f"/admin/products/{pid}/moderate", json={"decision": "approve"}).json()["product"]["status"] == "active"
    listing = httpx.get(f"{BASE}/catalog/products", params={"vendor": slug}).json()
    assert listing["total"] == 1 and len(listing["data"][0]["variants"]) == 2
    pslug = listing["data"][0]["slug"]
    assert httpx.get(f"{BASE}/catalog/products/{pslug}").json()["vendor_slug"] == slug
    # price-only change keeps it live; content change requeues review
    body["variants"][0]["price_minor"] = 4700
    for v, cur in zip(body["variants"], active):
        v["id"] = cur["id"]
    assert c.put(f"/vendor/products/{pid}/variants", json=body).json()["product"]["status"] == "active"
    detail = c.get(f"/vendor/products/{pid}").json()["product"]
    fields = {k: detail[k] for k in ("title", "description", "category_slug", "tags", "sku", "price_minor", "currency", "option_names", "low_stock_threshold")}
    r = c.patch(f"/vendor/products/{pid}", json={**fields, "title": "TEST Kente Scarf v2"})
    assert r.json()["requeued_for_review"] is True and r.json()["product"]["status"] == "pending_review"
    assert httpx.get(f"{BASE}/catalog/products/{pslug}").status_code == 404
    # ever-active products can only be archived
    assert c.delete(f"/vendor/products/{pid}").status_code == 409
    assert c.post(f"/vendor/products/{pid}/archive").json()["product"]["status"] == "archived"
    assert c.patch(f"/vendor/products/{pid}", json=fields).status_code == 409
    # suspension hides products and blocks writes
    v = mongo.vendors.find_one({"slug": slug})
    adm.post(f"/admin/products/{pid}/moderate", json={"decision": "approve"})
    assert c.post(f"/vendor/products/{pid}/unarchive").status_code == 200
    assert adm.post(f"/admin/vendors/{v['_id']}/suspend", json={"reason": "TEST check"}).status_code == 200
    assert c.post("/vendor/products", json=product_body(sku + "Z")).status_code == 403


def test_inventory_adjustments_and_history():
    c, _, _ = vendor()
    sku = f"I{uuid.uuid4().hex[:6]}".upper()
    r = c.post("/vendor/products", json=product_body(sku, low_stock_threshold=5, variants=[{"sku": sku, "price_minor": 1000, "initial_stock": 8}]))
    pid, vid = r.json()["product"]["id"], r.json()["variants"][0]["id"]
    assert c.post(f"/vendor/inventory/{vid}/adjust", json={"quantity": -20, "reason": "damaged"}).status_code == 422
    assert c.post(f"/vendor/inventory/{vid}/adjust", json={"quantity": 2, "reason": "initial"}).status_code == 422
    r = c.post(f"/vendor/inventory/{vid}/adjust", json={"quantity": -4, "reason": "damaged", "note": "TEST water"})
    assert r.json()["quantity_on_hand"] == 4 and r.json()["low_stock"] is True
    assert c.post(f"/vendor/inventory/{vid}/adjust", json={"mode": "set", "quantity": 12, "reason": "correction"}).json()["quantity_on_hand"] == 12
    hist = c.get(f"/vendor/products/{pid}/stock-history").json()["data"]
    assert [(h["delta"], h["before"], h["after"]) for h in hist] == [(8, 4, 12), (-4, 8, 4), (8, 0, 8)]
    assert c.delete(f"/vendor/products/{pid}").json()["status"] == "deleted"
    assert mongo.stock_adjustments.count_documents({"product_id": __import__("bson").ObjectId(pid)}) == 3


def test_cross_vendor_isolation_and_permissions():
    a, adm, _ = vendor()
    b, _, _ = vendor()
    sku = f"X{uuid.uuid4().hex[:6]}".upper()
    r = a.post("/vendor/products", json=product_body(sku, variants=[{"sku": sku, "price_minor": 1000, "initial_stock": 1}]))
    pid, vid = r.json()["product"]["id"], r.json()["variants"][0]["id"]
    assert b.get(f"/vendor/products/{pid}").status_code == 404
    assert b.patch(f"/vendor/products/{pid}", json=product_body("ZZ1")).status_code == 404
    assert b.post(f"/vendor/products/{pid}/archive").status_code == 404
    assert b.delete(f"/vendor/products/{pid}").status_code == 404
    assert b.post(f"/vendor/inventory/{vid}/adjust", json={"quantity": 5, "reason": "restock"}).status_code == 404
    assert b.post(f"/vendor/products/{pid}/images", files={"file": ("a.jpg", jpeg(100, 100), "image/jpeg")}).status_code == 404
    assert all(p["id"] != pid for p in b.get("/vendor/products").json()["data"])
    assert b.post("/vendor/products", json=product_body("ZZ2", variants=[{"sku": sku, "price_minor": 100}])).status_code == 409
    customer = verified_client()
    assert customer.get("/vendor/products").status_code in (403, 404)
    assert customer.get("/admin/products").status_code == 403
    assert b.post(f"/admin/products/{pid}/moderate", json={"decision": "approve"}).status_code == 403
    assert httpx.get(f"{BASE}/admin/categories").status_code == 401


def test_csv_import_preview_errors_and_commit():
    c, _, _ = vendor()
    h = uuid.uuid4().hex[:5]
    csv_text = ("handle,title,description,category,tags,option1_name,option1_value,sku,price,stock\n"
                f"t-dress-{h},TEST Dress,A lovely ankara dress for every day.,fashion,ankara,Size,S,TD{h}-S,80.00,4\n"
                f"t-dress-{h},,,,,Size,M,TD{h}-M,80.00,2\n"
                f"t-bad-{h},TEST Bad,Bad row,unknowncat,,,,TB{h},-3,x\n"
                f"t-dup-{h},TEST Dup,Duplicate sku product.,beauty,,,,TD{h}-S,10.00,1\n")
    assert c.post("/vendor/products/import/preview", files={"file": ("p.csv", b"title\nx", "text/csv")}).status_code == 422
    r = c.post("/vendor/products/import/preview", files={"file": ("p.csv", csv_text.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["valid_count"] == 1 and p["invalid_count"] == 2
    fields = {(e["row"], e["field"]) for e in p["errors"]}
    assert (4, "price") in fields and (4, "category") in fields and (5, "sku") in fields
    r = c.post(f"/vendor/products/import/{p['batch_id']}/commit")
    assert len(r.json()["created"]) == 1
    assert c.post(f"/vendor/products/import/{p['batch_id']}/commit").status_code == 404
    rows = c.get("/vendor/products").json()["data"]
    dress = next(x for x in rows if x["title"] == "TEST Dress")
    assert dress["status"] == "draft" and dress["variant_count"] == 2 and dress["stock_total"] == 6
    assert "afrovending" in c.get("/vendor/products/import/template").headers["content-disposition"]


def test_admin_category_management():
    adm = admin_client()
    name = f"TEST Cat {uuid.uuid4().hex[:4]}"
    r = adm.post("/admin/categories", json={"name": name, "parent_slug": "fashion"})
    assert r.status_code == 201, r.text
    cid, cslug = r.json()["id"], r.json()["slug"]
    assert adm.post("/admin/categories", json={"name": name, "parent_slug": "fashion"}).status_code == 409
    tree = httpx.get(f"{BASE}/catalog/categories").json()["data"]
    assert any(k["slug"] == cslug for c in tree if c["slug"] == "fashion" for k in c["children"])
    assert adm.patch(f"/admin/categories/{cid}", json={"name": name, "status": "hidden"}).json()["status"] == "hidden"
    tree = httpx.get(f"{BASE}/catalog/categories").json()["data"]
    assert not any(k["slug"] == cslug for c in tree for k in c["children"])
    assert adm.delete(f"/admin/categories/{cid}").status_code == 200
    fashion = next(c for c in adm.get("/admin/categories").json()["data"] if c["slug"] == "fashion")
    assert adm.delete(f"/admin/categories/{fashion['id']}").status_code == 409
