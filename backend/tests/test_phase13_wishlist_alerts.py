# Phase 13: wishlist daily summary (price drop >= 5%, back in stock), consent, dedupe, DST-safe day key
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from bson import ObjectId

from afrovending.core.wishlist_alerts import ET, drop_bps
from tests.test_phase03_vendors import BASE, admin_client, mongo
from tests.test_phase07_payments import S, _p6_cleanup, account, buyer, cleanup7, w  # noqa: F401

_FLAGS = mongo.platform_settings.find_one({"key": "marketing.flags"})
SECRET = open("/app/backend/.env").read().split("WEBHOOK_CRON_SECRET=")[1].split("\n")[0].strip('"')
BODY = {"abandoned_cart_enabled": False, "first_delay_min": 60, "second_delay_min": 1440, "max_per_7_days": 2}


def teardown_module():
    ids = S.get("buyers", [])
    for c in ("wishlist_alerts", "wishlist_digests", "wishlists", "notifications"):
        mongo[c].delete_many({"user_id": {"$in": ids}})
    mongo.platform_settings.delete_many({"key": "marketing.flags"})
    if _FLAGS:
        mongo.platform_settings.insert_one(_FLAGS)


def run():
    r = httpx.post(f"{BASE}/cron/wishlist-alerts", headers={"Authorization": f"Bearer {SECRET}", "X-Webhook-Id": f"t13-{uuid.uuid4().hex}", "X-Force-Run": "1"}, timeout=30)
    assert r.status_code == 202
    time.sleep(4)


def test_01_math_and_dst():
    assert drop_bps(10000, 9500) == Decimal("500.00") and drop_bps(10000, 9501) < 500 and drop_bps(1999, 1899) >= 500
    assert datetime(2026, 3, 9, 2, 30, tzinfo=timezone.utc).astimezone(ET).date().isoformat() == "2026-03-08"  # 9:30 PM EDT, day before
    assert datetime(2026, 11, 2, 4, 30, tzinfo=timezone.utc).astimezone(ET).date().isoformat() == "2026-11-01"  # 11:30 PM EST


def test_02_price_drop_restock_consent_dedupe(w):  # noqa: F811
    sup = admin_client()
    assert sup.put("/admin/marketing/flags", json={**BODY, "wishlist_alerts_enabled": True, "wishlist_threshold_bps": 500}).status_code == 200
    yes, no = buyer(), buyer()
    uy, un = S["buyers"][-2], S["buyers"][-1]
    assert yes.put("/account/marketing", json={"marketing_opt_in": True}).status_code == 200
    pid = mongo.product_variants.find_one({"_id": ObjectId(w["scarf"][1])})["product_id"]
    slug = mongo.products.find_one({"_id": pid})["slug"]
    for c in (yes, no):
        assert c.put(f"/wishlist/{slug}").status_code == 200
    ref = mongo.wishlists.find_one({"user_id": uy})["ref_price_minor"]
    assert ref
    # 4% drop: no alert; then 6% drop vs reference: alert
    mongo.wishlists.update_many({"user_id": {"$in": [uy, un]}}, {"$set": {"ref_price_minor": int(ref / Decimal("0.96")) - 1}})
    run()
    assert mongo.wishlist_alerts.count_documents({"user_id": uy}) == 0
    mongo.wishlists.update_many({"user_id": {"$in": [uy, un]}}, {"$set": {"ref_price_minor": int(ref / Decimal("0.94")) + 1}})
    run()
    a = list(mongo.wishlist_alerts.find({"user_id": uy}))
    assert len(a) == 1 and a[0]["kind"] == "price_drop" and a[0]["new_minor"] == ref
    assert mongo.wishlist_digests.count_documents({"user_id": uy}) == 1
    assert mongo.wishlist_alerts.count_documents({"user_id": un}) == 0  # not opted in
    run()
    assert mongo.wishlist_alerts.count_documents({"user_id": uy}) == 1  # same price change never re-alerted
    # restock on same day: recorded but no second email that day
    mongo.wishlists.update_one({"user_id": uy}, {"$set": {"ref_in_stock": False}})
    run()
    assert mongo.wishlist_alerts.count_documents({"user_id": uy, "kind": "back_in_stock"}) == 1
    assert mongo.wishlist_digests.count_documents({"user_id": uy}) == 1
    # opt-out of price drops respected
    assert yes.put("/account/marketing", json={"marketing_opt_in": True, "wishlist_price_drop": False}).status_code == 200
    mongo.wishlists.update_one({"user_id": uy}, {"$set": {"ref_price_minor": ref * 2}})
    run()
    assert mongo.wishlist_alerts.count_documents({"user_id": uy, "kind": "price_drop"}) == 1
    assert sup.put("/admin/marketing/flags", json={**BODY, "wishlist_alerts_enabled": False}).status_code == 200
