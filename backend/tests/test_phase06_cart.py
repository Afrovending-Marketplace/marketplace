import concurrent.futures
import uuid

import httpx
import pytest

from tests.test_phase03_vendors import BASE, admin_client, mongo, submit
from tests.test_phase04_catalog import jpeg

PREFIX = "TEST6_"
TAG = uuid.uuid4().hex[:6].upper()
START = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    users = [u["_id"] for u in mongo.users.find({"name": {"$regex": f"^{PREFIX}"}})]
    vendors = [v["_id"] for v in mongo.vendors.find({"owner_user_id": {"$in": users}})]
    for coll in ("products", "product_variants", "product_images", "inventory", "stock_adjustments", "vendor_stores"):
        mongo[coll].delete_many({"vendor_id": {"$in": vendors}})
    mongo.vendors.delete_many({"_id": {"$in": vendors}})
    for coll, field in (("vendor_applications", "user_id"), ("vendor_policy_acceptances", "user_id"), ("files", "owner_user_id"),
                        ("sessions", "user_id"), ("auth_tokens", "user_id"), ("addresses", "user_id"), ("carts", "user_id"),
                        ("orders", "customer_id"), ("carts", "merged_into_user")):
        mongo[coll].delete_many({field: {"$in": users}})
    mongo.carts.delete_many({"items.vendor_id": {"$in": vendors}})
    mongo.carts.delete_many({"token_hash": {"$exists": True}, "created_at": {"$gte": START}})
    mongo.users.delete_many({"_id": {"$in": users}})
    for coll in ("shipping_methods", "coupons", "tax_rates"):
        mongo[coll].delete_many({"$or": [{"name": {"$regex": "^TEST"}}, {"code": {"$regex": TAG}}, {"label": {"$regex": "^TEST"}}]})


def account():
    c = httpx.Client(base_url=BASE, timeout=90)
    mongo.rate_limits.delete_many({"key": {"$regex": "^(register|cart|coupon):"}})
    email = f"delivered+p6{uuid.uuid4().hex[:8]}@resend.dev"
    assert c.post("/auth/register", json={"name": f"{PREFIX}User", "email": email, "password": "TestPass12345"}).status_code == 201
    u = mongo.users.find_one({"email": email})
    mongo.users.update_one({"_id": u["_id"]}, {"$set": {"email_verified_at": u["created_at"], "status": "active"}})
    return c, email


def vendor(adm):
    c, _ = account()
    slug = f"test6-{uuid.uuid4().hex[:6]}"
    app = submit(c, slug)
    assert adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "approve"}).status_code == 200
    assert c.post("/vendor/store/publish").status_code == 200
    return c, slug


def live(c, adm, title, price, stock):
    sku = f"C{uuid.uuid4().hex[:7]}".upper()
    r = c.post("/vendor/products", json={"title": title, "description": "Made by hand with care and tradition.", "category_slug": "fashion",
                                         "sku": sku, "price_minor": price, "variants": [{"sku": sku, "price_minor": price, "initial_stock": stock}]})
    pid, vid = r.json()["product"]["id"], r.json()["variants"][0]["id"]
    c.post(f"/vendor/products/{pid}/images", files={"file": ("a.jpg", jpeg(40, 40), "image/jpeg")})
    c.post(f"/vendor/products/{pid}/submit")
    assert adm.post(f"/admin/products/{pid}/moderate", json={"decision": "approve"}).status_code == 200
    return pid, vid


@pytest.fixture(scope="module")
def world():
    adm = admin_client()
    a, slug_a = vendor(adm)
    b, slug_b = vendor(adm)
    return {"adm": adm, "a": a, "b": b, "slug_a": slug_a, "slug_b": slug_b,
            "scarf": live(a, adm, f"TEST Scarf {TAG}", 4500, 5), "dress": live(a, adm, f"TEST Dress {TAG}", 9000, 2),
            "shea": live(b, adm, f"TEST Shea {TAG}", 1500, 10)}


def guest():
    return httpx.Client(base_url=BASE, timeout=90)


def test_guest_cart_add_update_remove_and_stock_rules(world):
    g = guest()
    r = g.post("/cart/items", json={"variant_id": world["scarf"][1], "quantity": 2, "price_minor": 1})
    assert r.status_code == 200, r.text
    token = r.json()["cart_token"]
    h = {"X-Cart-Token": token}
    assert r.json()["totals"]["subtotal_minor"] == 9000  # browser price ignored
    assert g.get("/cart").json()["item_count"] == 0  # no token -> no cart
    assert g.post("/cart/items", json={"variant_id": world["scarf"][1], "quantity": 4}, headers=h).status_code == 409  # 6 > 5 in stock
    assert g.patch(f"/cart/items/{world['scarf'][1]}", json={"quantity": 5}, headers=h).json()["item_count"] == 5
    assert g.patch(f"/cart/items/{world['scarf'][1]}", json={"quantity": 6}, headers=h).status_code == 409
    assert g.post("/cart/items", json={"variant_id": "0" * 24}, headers=h).status_code == 404
    assert g.post("/cart/items", json={"variant_id": world["shea"][1], "quantity": 21}, headers=h).status_code == 422
    assert g.delete(f"/cart/items/{world['scarf'][1]}", headers=h).json()["item_count"] == 0
    assert g.get("/cart", headers={"X-Cart-Token": "x" * 40}).json()["id"] is None


def test_mixed_vendor_grouping_totals_shipping_tax_coupon(world):
    c, _ = account()
    c.post("/cart/items", json={"variant_id": world["scarf"][1], "quantity": 2})
    c.post("/cart/items", json={"variant_id": world["dress"][1], "quantity": 1})
    cart = c.post("/cart/items", json={"variant_id": world["shea"][1], "quantity": 3}).json()
    groups = {g["vendor_slug"]: g for g in cart["groups"]}
    assert groups[world["slug_a"]]["subtotal_minor"] == 18000 and groups[world["slug_b"]]["subtotal_minor"] == 4500
    t = cart["totals"]
    assert t["subtotal_minor"] == 22500 and t["shipping_minor"] is None and t["shipping_status"] == "to_be_confirmed"
    assert t["tax_estimate_minor"] is None and t["tax_status"] == "not_calculated" and t["final"] is False
    assert groups[world["slug_a"]]["shipping_methods"][0]["id"] == "to_be_confirmed"
    adm = world["adm"]
    m = adm.post("/admin/commerce/shipping-methods", json={"name": f"TEST Flat {TAG}", "amount_minor": 700, "vendor_slug": world["slug_a"], "free_over_minor": 50000}).json()
    tx = adm.post("/admin/commerce/tax-rates", json={"country": "ZZ", "region": "", "rate_bps": 625, "label": "TEST estimated tax"}).json()
    assert adm.post("/admin/commerce/tax-rates", json={"country": "ZZ", "rate_bps": 1, "label": "TEST dup"}).status_code == 409
    assert world["a"].get("/admin/commerce/coupons").status_code == 403
    addr = c.post("/account/addresses", json={"full_name": "TEST Buyer", "line1": "1 Main St", "city": "Boston", "country": "ZZ"}).json()
    aid = addr.get("id") or addr["address"]["id"]
    cart = c.put("/cart/address", json={"address_id": aid}).json()
    groups = {g["vendor_slug"]: g for g in cart["groups"]}
    assert groups[world["slug_a"]]["shipping_method_id"] == m["id"] and groups[world["slug_a"]]["shipping_minor"] == 700
    assert cart["totals"]["shipping_minor"] is None  # vendor B still "to be confirmed"
    assert cart["totals"]["tax_estimate_minor"] == 22500 * 625 // 10000 and cart["totals"]["tax_status"] == "estimated"
    assert c.post("/cart/coupon", json={}).status_code == 405
    assert c.put("/cart/coupon", json={"code": "NOPE"}).status_code == 422
    adm.post("/admin/commerce/coupons", json={"code": f"BIG{TAG}", "type": "fixed", "value": 1000, "min_subtotal_minor": 999999})
    assert c.put("/cart/coupon", json={"code": f"BIG{TAG}"}).status_code == 422
    adm.post("/admin/commerce/coupons", json={"code": f"TEN{TAG}", "type": "percent", "value": 1000})
    cart = c.put("/cart/coupon", json={"code": f"ten{TAG.lower()}"}).json()
    assert cart["totals"]["discount_minor"] == 2250
    assert sum(g["discount_minor"] for g in cart["groups"]) == 2250
    assert cart["totals"]["estimated_total_minor"] == 22500 - 2250 + 0 + (18000 - 1800) * 625 // 10000 + (4500 - 450) * 625 // 10000
    adm.put(f"/admin/commerce/tax-rates/{tx['id']}", json={"country": "ZZ", "rate_bps": 625, "label": "TEST estimated tax", "status": "inactive"})


def test_price_change_unavailable_and_checkout_blocking(world):
    c, _ = account()
    c.post("/cart/items", json={"variant_id": world["shea"][1], "quantity": 1})
    b = world["b"]
    body = {"variants": [{"id": world["shea"][1], "sku": b.get(f"/vendor/products/{world['shea'][0]}").json()["variants"][0]["sku"], "price_minor": 1800}]}
    assert b.put(f"/vendor/products/{world['shea'][0]}/variants", json=body).status_code == 200
    cart = c.get("/cart").json()
    line = cart["groups"][0]["items"][0]
    assert line["previous_price_minor"] == 1500 and line["unit_price_minor"] == 1800 and cart["totals"]["subtotal_minor"] == 1800
    assert any("prices changed" in x for x in cart["blocking"])
    assert c.post("/checkout/start", headers={"Idempotency-Key": f"k-{uuid.uuid4()}"}).status_code == 409
    cart = c.post("/cart/accept-prices").json()
    assert cart["groups"][0]["items"][0]["previous_price_minor"] is None and not cart["blocking"]
    assert b.post(f"/vendor/products/{world['shea'][0]}/archive").status_code == 200
    cart = c.get("/cart").json()
    assert cart["groups"][0]["items"][0]["status"] == "unavailable" and cart["totals"]["subtotal_minor"] == 0
    assert c.post("/checkout/start", headers={"Idempotency-Key": f"k-{uuid.uuid4()}"}).status_code == 409
    b.post(f"/vendor/products/{world['shea'][0]}/unarchive")
    b.post(f"/vendor/products/{world['shea'][0]}/submit")
    world["adm"].post(f"/admin/products/{world['shea'][0]}/moderate", json={"decision": "approve"})
    vid = world["dress"][1]
    c.post("/cart/items", json={"variant_id": vid, "quantity": 2})
    world["a"].post(f"/vendor/inventory/{vid}/adjust", json={"quantity": -1, "reason": "damaged"})
    line = next(x for g in c.get("/cart").json()["groups"] for x in g["items"] if x["variant_id"] == vid)
    assert line["status"] == "insufficient_stock" and line["available"] == 1
    world["a"].post(f"/vendor/inventory/{vid}/adjust", json={"quantity": 1, "reason": "returned"})


def test_guest_merge_after_login(world):
    c, email = account()
    c.post("/cart/items", json={"variant_id": world["scarf"][1], "quantity": 1})
    g = guest()
    token = g.post("/cart/items", json={"variant_id": world["scarf"][1], "quantity": 2}).json()["cart_token"]
    g.post("/cart/items", json={"variant_id": world["shea"][1], "quantity": 1}, headers={"X-Cart-Token": token})
    other, _ = account()
    assert other.post("/cart/merge", headers={"X-Cart-Token": "wrong" * 8}).json()["merged"] is False
    assert g.post("/auth/login", json={"email": email, "password": "TestPass12345"}).status_code == 200
    r = g.post("/cart/merge", headers={"X-Cart-Token": token}).json()
    assert r["merged"] is True and r["item_count"] == 4
    assert g.post("/cart/merge", headers={"X-Cart-Token": token}).json()["merged"] is False  # one-time
    assert guest().get("/cart", headers={"X-Cart-Token": token}).json()["id"] is None
    assert httpx.post(f"{BASE}/cart/merge", headers={"X-Cart-Token": token}).status_code == 401


def test_idempotent_checkout_draft_orders(world):
    c, _ = account()
    assert guest().post("/checkout/start", headers={"Idempotency-Key": "abcdefgh12"}).status_code == 401
    c.post("/cart/items", json={"variant_id": world["scarf"][1], "quantity": 1})
    cart = c.post("/cart/items", json={"variant_id": world["shea"][1], "quantity": 2}).json()
    assert c.post("/checkout/start").status_code == 422
    assert c.post("/checkout/start", headers={"Idempotency-Key": "abcdefgh01"}).status_code == 409  # no address yet
    addr = c.post("/account/addresses", json={"full_name": "TEST Buyer", "line1": "2 Elm St", "city": "Accra", "country": "GH"}).json()
    cart = c.put("/cart/address", json={"address_id": addr.get("id") or addr["address"]["id"]}).json()
    key = f"k-{uuid.uuid4()}"
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: httpx.post(f"{BASE}/checkout/start", headers={"Idempotency-Key": key}, cookies=c.cookies, timeout=60), range(4)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    ids = {r.json()["order"]["id"] for r in results}
    assert len(ids) == 1 and mongo.orders.count_documents({"idempotency_key": key}) == 1
    order = results[0].json()["order"]
    assert order["status"] == "draft" and order["amounts_final"] is False and "cart_fingerprint" not in order
    assert order["totals"]["subtotal_minor"] == cart["totals"]["subtotal_minor"] == 4500 + 2 * 1800  # shea repriced earlier in module
    assert {g["vendor_slug"] for g in order["vendor_groups"]} == {world["slug_a"], world["slug_b"]}
    assert c.post("/checkout/start", headers={"Idempotency-Key": key}).json()["replayed"] is True
    c.patch(f"/cart/items/{world['shea'][1]}", json={"quantity": 1})
    assert c.post("/checkout/start", headers={"Idempotency-Key": key}).status_code == 409
    new = c.post("/checkout/start", headers={"Idempotency-Key": f"k-{uuid.uuid4()}"}).json()["order"]
    assert new["id"] != order["id"] and c.get(f"/checkout/orders/{order['id']}").json()["order"]["status"] == "abandoned"
    other, _ = account()
    assert other.get(f"/checkout/orders/{new['id']}").status_code == 404
