# Phase 13 retest (iteration 20): F1 stock hold/release, F2 client_ip, F3 headers, F4 email allowlist, F5 send-hour gate, F6 7-day higher reference
import asyncio
import time
import uuid
from datetime import timedelta

import httpx
from bson import ObjectId

from tests.test_phase03_vendors import BASE, _ENV, admin_client, mongo
from tests.test_phase06_cart import live
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w  # noqa: F401

_FLAGS = mongo.platform_settings.find_one({"key": "marketing.flags"})
SECRET = open("/app/backend/.env").read().split("WEBHOOK_CRON_SECRET=")[1].split("\n")[0].strip('"')
BODY = {"abandoned_cart_enabled": False, "first_delay_min": 60, "second_delay_min": 1440, "max_per_7_days": 2}
TAG = uuid.uuid4().hex[:6]
RL_EMAIL = f"qa20{TAG}@example.com"


def teardown_module():
    ids = S.get("buyers", [])
    for c in ("wishlist_alerts", "wishlist_digests", "wishlists", "notifications"):
        mongo[c].delete_many({"user_id": {"$in": ids}})
    mongo.rate_limits.delete_many({"key": {"$regex": f"qa20{TAG}"}})
    mongo.cron_runs.delete_many({"run_id": {"$regex": f"^t20-{TAG}"}})
    mongo.platform_settings.delete_many({"key": "marketing.flags"})
    if _FLAGS:
        mongo.platform_settings.insert_one(_FLAGS)


def inv(vid):
    d = mongo.inventory.find_one({"variant_id": ObjectId(vid)})
    return d["quantity_on_hand"], d.get("quantity_reserved", 0)


def checkout(c, oid_):
    return c.post(f"/payments/orders/{oid_}/checkout", json={"origin_url": _ENV["FRONTEND_URL"]})


def expired(p):
    return {"id": p["provider_session_id"], "object": "checkout.session", "status": "expired", "payment_status": "unpaid", "metadata": {"payment_id": str(p["_id"])}}


# F1: hold on session create, reuse does not double-hold, cancel/expired release exactly once, paid keeps the hold
def test_01_stock_hold_and_release(w):  # noqa: F811
    _, vid = live(w["a"], w["adm"], f"TEST20 Hold {TAG}", 1500, 1)
    assert inv(vid) == (1, 0)
    b1, b2, b3 = buyer(), buyer(), buyer()
    o1, o2, o3 = draft(b1, [(vid, 1)]), draft(b2, [(vid, 1)]), draft(b3, [(vid, 1)])
    p1 = start_pay(b1, o1["id"])
    assert p1.get("stock_reserved") is True and inv(vid) == (1, 1)
    r = checkout(b1, o1["id"])  # reuse the open session
    assert r.status_code == 200 and r.json()["reused"] is True and inv(vid) == (1, 1)
    r = checkout(b2, o2["id"])
    assert r.status_code == 409, r.text
    print("second buyer while held:", r.json()["error"]["code"])
    # cancel releases once
    assert b1.post(f"/payments/orders/{o1['id']}/cancel").status_code == 200
    assert inv(vid) == (1, 0)
    assert b1.post(f"/payments/orders/{o1['id']}/cancel").status_code == 200
    assert inv(vid) == (1, 0)
    assert mongo.payments.find_one({"_id": p1["_id"]})["stock_reserved"] is False
    # buyer 2 can now take it; expired webhook releases once (replayed twice)
    p2 = start_pay(b2, o2["id"])
    assert inv(vid) == (1, 1)
    for _ in range(2):
        assert send("checkout.session.expired", expired(p2)).status_code == 200
    time.sleep(1)
    assert inv(vid) == (1, 0)
    assert mongo.payments.find_one({"_id": p2["_id"]})["status"] == "cancelled"
    # buyer 3 pays: hold kept, mark_paid does not reserve a second time
    p3 = start_pay(b3, o3["id"])
    assert send("checkout.session.completed", completed(p3, real_pi(p3["amount_minor"]).id)).status_code == 200
    time.sleep(2)
    assert mongo.orders.find_one({"_id": p3["order_id"]})["status"] == "paid"
    assert inv(vid) == (1, 1)
    # a late expired event for the paid session must not release
    send("checkout.session.expired", expired(p3))
    time.sleep(1)
    assert inv(vid) == (1, 1)


# F2: rate-limit key uses the real client IP, not the LB and not a spoofed leftmost XFF entry
def test_02_client_ip_from_trusted_hop():
    my_ip = httpx.get("https://ifconfig.me/ip", timeout=20).text.strip()
    g = httpx.Client(base_url=BASE, timeout=30)
    g.post("/auth/login", json={"email": RL_EMAIL, "password": "WrongPass12345"}, headers={"X-Forwarded-For": "6.6.6.6"})
    g.post("/auth/forgot-password", json={"email": f"x{RL_EMAIL}"}, headers={"X-Forwarded-For": "7.7.7.7, 8.8.8.8"})
    keys = [d["key"] for d in mongo.rate_limits.find({"key": {"$regex": f"qa20{TAG}"}})]
    print("my egress ip:", my_ip, "keys:", keys)
    assert keys and all("34.160.159.238" not in k and "6.6.6.6" not in k for k in keys)
    assert any(f"login:{my_ip}:" in k for k in keys), keys
    recent = mongo.rate_limits.find_one({"key": {"$regex": "^forgot:"}}, sort=[("_id", -1)])
    print("latest forgot key:", recent and recent["key"])
    assert recent and "7.7.7.7" not in recent["key"] and "8.8.8.8" not in recent["key"]


# F3: security headers on API responses
def test_03_security_headers():
    for path in ("/health", "/catalog/products/does-not-exist-qa20"):
        h = httpx.get(f"{BASE}{path}", timeout=30).headers
        assert h.get("strict-transport-security", "").startswith("max-age=31536000")
        assert h.get("x-frame-options") == "DENY"
        assert h.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert h.get("x-content-type-options") == "nosniff"


# F4: email allowlist outside production (in-process unit check)
def test_04_email_allowlist():
    from afrovending.core import email as mail
    from afrovending.core.config import settings
    assert settings.app_env != "production"
    ok = mail._allowed_outside_production
    assert ok("delivered+x@resend.dev") and ok("a@example.com") and ok("b@example.org") and ok(settings.admin_email.upper())
    assert not ok("real.customer@gmail.com") and not ok(["a@example.com", "real@yahoo.com"])
    assert not ok("x@notexample.com") and not ok("x@example.com.evil.io")
    sent = asyncio.run(mail.try_send(to="real.customer@gmail.com", subject="TEST", html="<p>x</p>"))
    assert sent is True  # suppressed, reported as handled


def _cron(force: bool):
    rid = f"t20-{TAG}-{uuid.uuid4().hex[:6]}"
    h = {"Authorization": f"Bearer {SECRET}", "X-Webhook-Id": rid}
    if force:
        h["X-Force-Run"] = "1"
    r = httpx.post(f"{BASE}/cron/wishlist-alerts", headers=h, timeout=30)
    assert r.status_code == 202, r.text
    for _ in range(20):
        time.sleep(0.5)
        d = mongo.cron_runs.find_one({"run_id": rid})
        if d and d["status"] != "queued":
            return d
    return mongo.cron_runs.find_one({"run_id": rid})


# F5 + F6: send-hour gate and 7-day hold for a higher reference price
def test_05_send_hour_gate_and_higher_ref(w):  # noqa: F811
    from afrovending.core.wishlist_alerts import ET
    from datetime import datetime, timezone
    sup = admin_client()
    assert sup.put("/admin/marketing/flags", json={**BODY, "wishlist_alerts_enabled": True, "wishlist_threshold_bps": 500}).status_code == 200
    hour = datetime.now(timezone.utc).astimezone(ET).hour
    d = _cron(False)
    print("unforced cron result:", d.get("status"), d.get("result"), "ET hour:", hour)
    if hour != 9:
        assert d["result"] == {"skipped": "not_send_hour"}
    c = buyer()
    uid = S["buyers"][-1]
    pid = mongo.product_variants.find_one({"_id": ObjectId(w["scarf"][1])})["product_id"]
    slug = mongo.products.find_one({"_id": pid})["slug"]
    assert c.put(f"/wishlist/{slug}").status_code == 200
    cur = mongo.wishlists.find_one({"user_id": uid})["ref_price_minor"]
    low = cur - 300
    mongo.wishlists.update_one({"user_id": uid}, {"$set": {"ref_price_minor": low}})
    assert _cron(True)["status"] == "done"
    r = mongo.wishlists.find_one({"user_id": uid})
    assert r["ref_price_minor"] == low and r["higher_price_minor"] == cur and r["higher_since"]
    assert _cron(True)["status"] == "done"
    assert mongo.wishlists.find_one({"user_id": uid})["ref_price_minor"] == low  # still < 7 days
    mongo.wishlists.update_one({"user_id": uid}, {"$set": {"higher_since": r["higher_since"] - timedelta(days=8)}})
    assert _cron(True)["status"] == "done"
    r = mongo.wishlists.find_one({"user_id": uid})
    assert r["ref_price_minor"] == cur and r.get("higher_since") is None
    assert sup.put("/admin/marketing/flags", json={**BODY, "wishlist_alerts_enabled": False}).status_code == 200
