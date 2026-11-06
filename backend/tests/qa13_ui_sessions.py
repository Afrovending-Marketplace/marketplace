# Phase 13 QA helper: creates TEST sessions (customer, vendor, super admin) for UI checks; run with "cleanup" to remove them
import json
import sys

from tests.test_phase03_vendors import admin_client, mongo
from tests.test_phase06_cart import account, vendor

OUT = "/tmp/qa13_sessions.json"


def cookies(c):
    return [{"name": k, "value": v} for k, v in c.cookies.items()]


if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    d = json.load(open(OUT))
    ids = [mongo.users.find_one({"email": e})["_id"] for e in d["emails"] if mongo.users.find_one({"email": e})]
    vids = [v["_id"] for v in mongo.vendors.find({"owner_user_id": {"$in": ids}})]
    for coll in ("products", "product_variants", "product_images", "inventory", "stock_adjustments", "vendor_stores"):
        mongo[coll].delete_many({"vendor_id": {"$in": vids}})
    mongo.vendors.delete_many({"_id": {"$in": vids}})
    for coll, f in (("vendor_applications", "user_id"), ("vendor_policy_acceptances", "user_id"), ("files", "owner_user_id"), ("sessions", "user_id"),
                    ("auth_tokens", "user_id"), ("addresses", "user_id"), ("carts", "user_id"), ("wishlists", "user_id"), ("notifications", "user_id")):
        mongo[coll].delete_many({f: {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    print("cleaned", len(ids))
else:
    adm = admin_client()
    cust, ce = account()
    assert cust.put("/account/marketing", json={"marketing_opt_in": True}).status_code == 200
    ven, slug = vendor(adm)
    from tests.test_phase06_cart import live
    pid, vid = live(ven, adm, "TEST QA13 Kente Scarf", 4500, 3)
    assert cust.put(f"/wishlist/{mongo.products.find_one({'_id': __import__('bson').ObjectId(pid)})['slug']}").status_code == 200
    assert cust.post("/cart/items", json={"variant_id": vid, "quantity": 1}).status_code == 200
    ve = mongo.users.find_one({"_id": mongo.vendors.find_one({"_id": mongo.vendor_stores.find_one({"slug": slug})["vendor_id"]})["owner_user_id"]})["email"]
    json.dump({"emails": [ce, ve], "customer": cookies(cust), "vendor": cookies(ven), "admin": cookies(adm)}, open(OUT, "w"))
    print("ok", ce, ve)
