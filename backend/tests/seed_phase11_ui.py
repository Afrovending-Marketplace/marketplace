# Seed / cleanup helper for Phase 11 trust UI E2E (TEST11UI_ data, cleaned by tracked ids). Usage: python -m tests.seed_phase11_ui seed|cleanup
import json
import sys

from bson import ObjectId

from tests.seed_phase08_ui import PW, account, live, vendor
from tests.test_phase03_vendors import admin_client, mongo
from tests.test_phase07_payments import completed, draft, real_pi, send, start_pay

STATE = "/tmp/seed11ui.json"


def seed():
    adm = admin_client()
    sm = adm.post("/admin/commerce/shipping-methods", json={"name": "TEST11UI Flat", "amount_minor": 500})
    a, ea, sa = vendor(adm, "VendA")
    c, buyer = account("Buyer")
    pa = live(a, adm, "TEST11UI Kente Scarf", 4500, 5)
    order = draft(c, [(pa["vid"], 1)])
    p = start_pay(c, order["id"])
    print("webhook", send("checkout.session.completed", completed(p, real_pi(p["amount_minor"]).id)).status_code)
    d = c.get(f"/orders/{order['id']}/detail").json()
    vo = d["vendor_orders"][0]
    assert a.post(f"/vendor/orders/{vo['id']}/status", json={"to": "accepted"}).status_code == 200
    it = vo["items"][0]
    s = a.post(f"/vendor/orders/{vo['id']}/shipments", json={"lines": [{"order_item_id": it["id"], "quantity": it["quantity"]}], "carrier": "usps",
                                                           "tracking_number": "9400100000000000000011"}).json()["shipment"]
    assert a.post(f"/vendor/shipments/{s['id']}/status", json={"status": "delivered"}).status_code == 200
    product = mongo.products.find_one({"_id": ObjectId(pa["pid"])})
    st = {"vendor_a": ea, "slug_a": sa, "buyer": buyer, "pw": PW, "pa": pa, "product_slug": product["slug"], "order_id": order["id"],
          "vo_id": vo["id"], "vo_number": vo.get("order_number"), "item_id": it["id"], "item_sku": it.get("sku"),
          "shipping_method_id": (sm.json().get("id") or (sm.json().get("method") or {}).get("id")) if sm.status_code in (200, 201) else None,
          "user_emails": [ea, buyer]}
    json.dump(st, open(STATE, "w"), indent=1)
    print(json.dumps(st, indent=1))


def cleanup():
    st = json.load(open(STATE))
    users = [u["_id"] for u in mongo.users.find({"email": {"$in": st["user_emails"]}})]
    vendors = [v["_id"] for v in mongo.vendors.find({"owner_user_id": {"$in": users}})]
    pays = [p["_id"] for p in mongo.payments.find({"customer_id": {"$in": users}})]
    vos = [v["_id"] for v in mongo.vendor_orders.find({"$or": [{"customer_id": {"$in": users}}, {"vendor_id": {"$in": vendors}}]})]
    for coll in ("reviews", "seller_ratings"):
        ids = [d["_id"] for d in mongo[coll].find({"customer_id": {"$in": users}})]
        mongo.review_reports.delete_many({"target_id": {"$in": ids}})
        mongo.audit_logs.delete_many({"entity_id": {"$in": ids + [str(i) for i in ids]}})
        mongo[coll].delete_many({"_id": {"$in": ids}})
    msgs = [m["_id"] for m in mongo.order_messages.find({"vendor_order_id": {"$in": vos}})]
    mongo.audit_logs.delete_many({"entity_id": {"$in": msgs + [str(i) for i in msgs]}})
    mongo.order_messages.delete_many({"_id": {"$in": msgs}})
    mongo.notifications.delete_many({"user_id": {"$in": users}})
    mongo.audit_logs.delete_many({"actor_id": {"$in": users + [str(u) for u in users]}})
    mongo.commission_ledger.delete_many({"$or": [{"payment_id": {"$in": pays}}, {"vendor_order_id": {"$in": vos}}, {"vendor_id": {"$in": vendors}}]})
    for coll in ("payouts", "order_items", "shipments", "order_requests", "order_events"):
        mongo[coll].delete_many({"vendor_order_id": {"$in": vos}})
    for coll in ("refunds", "disputes"):
        mongo[coll].delete_many({"payment_id": {"$in": pays}})
    mongo.vendor_orders.delete_many({"_id": {"$in": vos}})
    mongo.payments.delete_many({"_id": {"$in": pays}})
    for coll in ("connected_accounts", "payouts", "statements", "shipping_methods", "products", "product_variants", "product_images", "inventory",
                 "stock_adjustments", "vendor_stores"):
        mongo[coll].delete_many({"vendor_id": {"$in": vendors}})
    mongo.carts.delete_many({"items.vendor_id": {"$in": vendors}})
    mongo.vendors.delete_many({"_id": {"$in": vendors}})
    for coll, field in (("vendor_applications", "user_id"), ("vendor_policy_acceptances", "user_id"), ("files", "owner_user_id"),
                        ("sessions", "user_id"), ("auth_tokens", "user_id"), ("addresses", "user_id"), ("carts", "user_id"),
                        ("orders", "customer_id"), ("carts", "merged_into_user")):
        mongo[coll].delete_many({field: {"$in": users}})
    mongo.users.delete_many({"_id": {"$in": users}})
    if st.get("shipping_method_id"):
        mongo.shipping_methods.delete_one({"_id": ObjectId(st["shipping_method_id"])})
    else:
        mongo.shipping_methods.delete_many({"name": "TEST11UI Flat"})
    print("cleaned users", len(users), "vendors", len(vendors), "vos", len(vos), "msgs", len(msgs))


if __name__ == "__main__":
    {"seed": seed, "cleanup": cleanup}[sys.argv[1]]()
