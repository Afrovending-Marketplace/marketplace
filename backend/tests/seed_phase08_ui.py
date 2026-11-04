# Seed / cleanup helper for Phase 08 fulfillment frontend E2E (TEST8UI_ data). Usage: python -m tests.seed_phase08_ui seed|cleanup
import json
import sys
import uuid

import httpx
from bson import ObjectId  # noqa: F401

from tests.test_phase03_vendors import BASE, admin_client, mongo, submit
from tests.test_phase04_catalog import jpeg
from tests.test_phase07_payments import completed, draft, real_pi, send, start_pay

STATE = "/tmp/seed8ui.json"
PW = "TestPass12345"


def account(tag):
    c = httpx.Client(base_url=BASE, timeout=90)
    mongo.rate_limits.delete_many({"key": {"$regex": "^(register|cart|coupon|login|checkout):"}})
    email = f"delivered+t8ui{tag.lower()}{uuid.uuid4().hex[:6]}@resend.dev"
    r = c.post("/auth/register", json={"name": f"TEST8UI_{tag}", "email": email, "password": PW})
    assert r.status_code == 201, r.text
    u = mongo.users.find_one({"email": email})
    mongo.users.update_one({"_id": u["_id"]}, {"$set": {"email_verified_at": u["created_at"], "status": "active"}})
    return c, email


def vendor(adm, tag):
    c, email = account(tag)
    slug = f"test8ui-{uuid.uuid4().hex[:6]}"
    app = submit(c, slug)
    assert adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "approve"}).status_code == 200
    assert c.post("/vendor/store/publish").status_code == 200
    return c, email, slug


def live(c, adm, title, price, stock):
    sku = f"U{uuid.uuid4().hex[:7]}".upper()
    r = c.post("/vendor/products", json={"title": title, "description": "Made by hand with care and tradition.", "category_slug": "fashion",
                                         "sku": sku, "price_minor": price, "variants": [{"sku": sku, "price_minor": price, "initial_stock": stock}]})
    assert r.status_code in (200, 201), r.text
    pid, vid = r.json()["product"]["id"], r.json()["variants"][0]["id"]
    c.post(f"/vendor/products/{pid}/images", files={"file": ("a.jpg", jpeg(40, 40), "image/jpeg")})
    c.post(f"/vendor/products/{pid}/submit")
    assert adm.post(f"/admin/products/{pid}/moderate", json={"decision": "approve"}).status_code == 200
    return {"pid": pid, "vid": vid, "sku": sku}


def seed():
    adm = admin_client()
    print(adm.post("/admin/commerce/shipping-methods", json={"name": "TEST8UI Flat", "amount_minor": 500}).status_code)
    a, ea, sa = vendor(adm, "VendA")
    b, eb, sb = vendor(adm, "VendB")
    c, buyer = account("Buyer")
    pa, pb = live(a, adm, "TEST8UI Kente Scarf", 4500, 5), live(b, adm, "TEST8UI Shea Butter", 1500, 10)
    order = draft(c, [(pa["vid"], 2), (pb["vid"], 3)])
    p = start_pay(c, order["id"])
    print("webhook", send("checkout.session.completed", completed(p, real_pi(p["amount_minor"]).id)).status_code)
    d = c.get(f"/orders/{order['id']}/detail").json()
    st = {"vendor_a": ea, "vendor_b": eb, "slug_a": sa, "slug_b": sb, "buyer": buyer, "pw": PW, "pa": pa, "pb": pb,
          "order_id": order["id"], "order_number": d["order"]["order_number"],
          "vos": {v["vendor_slug"]: {"id": v["id"], "status": v["status"], "number": v.get("order_number")} for v in d["vendor_orders"]}}
    json.dump(st, open(STATE, "w"), indent=1)
    print(json.dumps(st, indent=1))


def cleanup():
    users = [u["_id"] for u in mongo.users.find({"name": {"$regex": "^TEST8UI_"}})]
    vendors = [v["_id"] for v in mongo.vendors.find({"owner_user_id": {"$in": users}})]
    pays = [p["_id"] for p in mongo.payments.find({"customer_id": {"$in": users}})]
    vos = [v["_id"] for v in mongo.vendor_orders.find({"$or": [{"customer_id": {"$in": users}}, {"vendor_id": {"$in": vendors}}]})]
    mongo.commission_ledger.delete_many({"$or": [{"payment_id": {"$in": pays}}, {"vendor_order_id": {"$in": vos}}, {"vendor_id": {"$in": vendors}}]})
    for coll in ("payouts", "order_items", "shipments", "order_requests", "order_events"):
        mongo[coll].delete_many({"vendor_order_id": {"$in": vos}})
    for coll in ("refunds", "disputes"):
        mongo[coll].delete_many({"payment_id": {"$in": pays}})
    mongo.vendor_orders.delete_many({"_id": {"$in": vos}})
    mongo.payments.delete_many({"_id": {"$in": pays}})
    for coll in ("connected_accounts", "payouts", "statements", "shipping_methods"):
        mongo[coll].delete_many({"vendor_id": {"$in": vendors}})
    for coll in ("products", "product_variants", "product_images", "inventory", "stock_adjustments", "vendor_stores"):
        mongo[coll].delete_many({"vendor_id": {"$in": vendors}})
    mongo.carts.delete_many({"items.vendor_id": {"$in": vendors}})
    mongo.vendors.delete_many({"_id": {"$in": vendors}})
    for coll, field in (("vendor_applications", "user_id"), ("vendor_policy_acceptances", "user_id"), ("files", "owner_user_id"),
                        ("sessions", "user_id"), ("auth_tokens", "user_id"), ("addresses", "user_id"), ("carts", "user_id"),
                        ("orders", "customer_id"), ("carts", "merged_into_user")):
        mongo[coll].delete_many({field: {"$in": users}})
    mongo.users.delete_many({"_id": {"$in": users}})
    mongo.shipping_methods.delete_many({"name": {"$regex": "^TEST8UI"}})
    mongo.webhook_events.delete_many({"event_id": {"$regex": "^evt_t7"}})
    print("cleaned users", len(users), "vendors", len(vendors), "payments", len(pays), "vos", len(vos))


if __name__ == "__main__":
    {"seed": seed, "cleanup": cleanup}[sys.argv[1]]()
