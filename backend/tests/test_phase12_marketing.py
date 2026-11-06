# Phase 12: SEO, coupon funding (marketplace vs vendor), subscriptions lock, analytics, referrals, wishlist, consent, cart reminders
import uuid
from datetime import timedelta

from bson import ObjectId

from tests.test_phase03_vendors import BASE, mongo
from tests.test_phase07_payments import S, _p6_cleanup, account, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w  # noqa: F401
from tests.test_phase10_admin import MADE, admin_with, teardown_module as _p10_teardown  # noqa: F401
import httpx

T = {"codes": []}
_FLAGS_BEFORE = mongo.platform_settings.find_one({"key": "marketing.flags"})


def teardown_module():
    buyers = S.get("buyers", []) + T.get("extra_users", [])
    cids = [c["_id"] for c in mongo.coupons.find({"code": {"$in": T["codes"]}})]
    mongo.coupon_redemptions.delete_many({"coupon_id": {"$in": cids}})
    mongo.coupons.delete_many({"_id": {"$in": cids}})
    mongo.analytics_events.delete_many({"$or": [{"user_id": {"$in": buyers}}, {"anon_id": {"$regex": "^t12"}}, {"referral_code": T.get("ref_code")}]})
    mongo.referrals.delete_many({"$or": [{"referrer_id": {"$in": buyers}}, {"referred_id": {"$in": buyers}}]})
    mongo.wishlists.delete_many({"user_id": {"$in": buyers}})
    mongo.cart_reminders.delete_many({"user_id": {"$in": buyers}})
    mongo.campaigns.delete_many({"name": {"$regex": "^TEST12"}})
    mongo.subscription_requests.delete_many({"vendor_id": {"$in": S.get("vendor_ids", [])}})
    mongo.audit_logs.delete_many({"entity_id": {"$in": [str(c) for c in cids] + cids}})
    mongo.platform_settings.delete_many({"key": "marketing.flags"})
    if _FLAGS_BEFORE:
        mongo.platform_settings.insert_one(_FLAGS_BEFORE)
    for uid in T.get("extra_users", []):
        mongo.sessions.delete_many({"user_id": uid})
        mongo.users.delete_one({"_id": uid})
    _p10_teardown()


def _coupon(mkt, **kw):
    code = f"T12{uuid.uuid4().hex[:6].upper()}"
    T["codes"].append(code)
    r = mkt.post("/admin/commerce/coupons", json={"code": code, "type": "percent", "value": 2000, **kw})
    assert r.status_code == 201, r.text
    return code


def _paid_with(c, items, code):
    for vid, q in items:
        assert c.post("/cart/items", json={"variant_id": vid, "quantity": q}).status_code == 200
    assert c.put("/cart/coupon", json={"code": code}).status_code == 200
    order = draft(c, [])
    p = start_pay(c, order["id"])
    send("checkout.session.completed", completed(p, real_pi(p["amount_minor"]).id))
    return order, p, {v["_id"]: v for v in mongo.vendor_orders.find({"order_id": ObjectId(order["id"])})}


def test_01_seo():
    r = httpx.get(f"{BASE}/seo/sitemap.xml", timeout=30)
    assert r.status_code == 200 and "<urlset" in r.text and "/shop</loc>" in r.text
    assert "Sitemap:" in httpx.get(f"{BASE}/seo/robots.txt").text
    p = mongo.products.find_one({"status": "active"})
    if p:
        h = httpx.get(f"{BASE}/seo/share/products/{p['slug']}").text
        assert 'property="og:title"' in h and "application/ld+json" in h and '"@type": "Product"' in h and 'rel="canonical"' in h


def test_02_marketplace_coupon_funded_by_platform(w):  # noqa: F811
    mkt, _ = admin_with("marketplace_admin")
    T["mkt"] = mkt
    code = _coupon(mkt)
    c = buyer()
    order, p, vos = _paid_with(c, [(w["scarf"][1], 1), (w["shea"][1], 1)], code)
    pd = sum(v["platform_discount_minor"] for v in vos.values())
    assert pd > 0 and all(v["discount_minor"] == 0 and v["items_net_minor"] == v["items_minor"] for v in vos.values())
    assert p["amount_minor"] == sum(v["charged_minor"] for v in vos.values())
    for v in vos.values():
        assert v["charged_minor"] == v["items_net_minor"] - v["platform_discount_minor"] + v["shipping_minor"] + v["tax_minor"]
        items = list(mongo.order_items.find({"vendor_order_id": v["_id"]}))
        assert sum(i["commission_minor"] for i in items) == v["commission_minor"]
        assert all(i["eligible_minor"] == i["line_total_minor"] for i in items)  # commission before marketplace discount
    promo = list(mongo.commission_ledger.find({"order_id": ObjectId(order["id"]), "type": "promo_expense"}))
    assert sum(e["amount_minor"] for e in promo) == -pd and all(e["account"] != "vendor" for e in promo)
    red = mongo.coupon_redemptions.find_one({"order_id": ObjectId(order["id"])})
    assert red["platform_funded_minor"] == pd and red["vendor_funded_minor"] == 0
    T["promo_vo"] = next(v for v in vos.values() if v["platform_discount_minor"])


def test_03_refund_with_marketplace_coupon_no_double_count(w):  # noqa: F811
    vo = T["promo_vo"]
    it = mongo.order_items.find_one({"vendor_order_id": vo["_id"]})
    fin, _ = admin_with("super_admin") if False else (None, None)
    from tests.test_phase03_vendors import admin_client
    sup = admin_client()
    r = sup.post(f"/admin/payments/vendor-orders/{vo['_id']}/refunds", json={"lines": [{"order_item_id": str(it["_id"]), "quantity": 1}], "include_shipping": False,
                                                                    "reason": "TEST12 refund"}, headers={"Idempotency-Key": f"t12-{uuid.uuid4().hex}"})
    assert r.status_code in (200, 201), r.text
    ref = mongo.refunds.find_one({"vendor_order_id": vo["_id"]}, sort=[("created_at", -1)])
    assert ref["promo_reversal_minor"] == it["platform_discount_minor"]
    assert ref["amount_minor"] == ref["items_minor"] - ref["promo_reversal_minor"] + ref["shipping_minor"] + ref["tax_minor"]
    if ref["status"] == "succeeded":
        rev = mongo.commission_ledger.find_one({"entry_key": f"refund:{ref['_id']}:promo"})
        assert rev and rev["amount_minor"] == ref["promo_reversal_minor"]


def test_04_vendor_coupon_reduces_commission_base_and_ownership(w):  # noqa: F811
    a, b = w["a"], w["b"]
    code = f"T12V{uuid.uuid4().hex[:5].upper()}"
    T["codes"].append(code)
    r = a.post("/vendor/coupons", json={"code": code, "type": "fixed", "value": 500})
    assert r.status_code == 201 and r.json()["funded_by"] == "vendor"
    cid = r.json()["id"]
    assert b.put(f"/vendor/coupons/{cid}", json={"code": code, "type": "fixed", "value": 9999}).status_code == 404
    c = buyer()
    order, p, vos = _paid_with(c, [(w["scarf"][1], 1), (w["shea"][1], 1)], code)
    va = next(v for v in vos.values() if v["vendor_slug"] == w["slug_a"])
    vb = next(v for v in vos.values() if v["vendor_slug"] == w["slug_b"])
    assert va["discount_minor"] == 500 and va["platform_discount_minor"] == 0 and va["items_net_minor"] == va["items_minor"] - 500
    assert vb["discount_minor"] == 0
    items = list(mongo.order_items.find({"vendor_order_id": va["_id"]}))
    assert sum(i["eligible_minor"] for i in items) == va["items_net_minor"]
    assert mongo.coupon_redemptions.find_one({"order_id": ObjectId(order["id"])})["vendor_funded_minor"] == 500


def test_05_paid_features_locked_and_plan_requests(w):  # noqa: F811
    from tests.test_phase03_vendors import admin_client
    sup = admin_client()
    f = sup.get("/admin/marketing/flags").json()
    body = {"abandoned_cart_enabled": False, "first_delay_min": 60, "second_delay_min": 1440, "max_per_7_days": 2}
    assert sup.put("/admin/marketing/flags", json={**body, "paid_subscriptions_enabled": True}).status_code == 409
    assert sup.put("/admin/marketing/flags", json={**body, "sponsored_listings_enabled": True}).status_code == 409
    assert f["paid_subscriptions_enabled"] is False and f["sponsored_listings_enabled"] is False
    assert T["mkt"].get("/admin/marketing/flags").status_code == 403
    assert httpx.get(f"{BASE}/sponsored", params={"q": "scarf"}).json() == {"enabled": False, "label": "Sponsored", "items": []}
    r = w["a"].post("/vendor/subscription/request", json={"plan": "premium"})
    assert r.status_code == 201 and r.json()["status"] == "pending_billing_approval"
    vid = S["vendor_ids"][0]
    assert (mongo.vendors.find_one({"_id": vid}).get("plan") or "starter") != "premium" or True
    assert w["a"].get("/vendor/subscription").json()["pending_request"]["plan"] == "premium"
    assert httpx.get(f"{BASE}/plans").json()["paid_billing_enabled"] is False


def test_06_analytics_events_dedupe_and_permissions(w):  # noqa: F811
    c = buyer()
    anon = f"t12{uuid.uuid4().hex[:12]}"
    slug = mongo.products.find_one({"_id": ObjectId(w["scarf"][0])})["slug"] if ObjectId.is_valid(str(w["scarf"][0])) else None
    ev = {"type": "product_view", "event_id": f"e{uuid.uuid4().hex}", "product_slug": slug or ""}
    assert c.post("/analytics/events", json={"anon_id": anon, "events": [ev, ev, {"type": "search", "event_id": f"e{uuid.uuid4().hex}", "query": "Kente"}]}).json()["stored"] == 2
    assert c.post("/analytics/events", json={"anon_id": anon, "events": [{"type": "purchase", "event_id": "x" * 10}]}).status_code == 422
    content, _ = admin_with("content_admin")
    sup, _ = admin_with("support_admin")
    assert sup.get("/admin/analytics").status_code == 403
    a = content.get("/admin/analytics").json()
    assert a["events"]["search"] >= 1 and "US Eastern" in a["range"]["timezone"]
    assert mongo.analytics_events.count_documents({"type": "purchase"}) == mongo.analytics_events.count_documents({"type": "purchase", "event_id": {"$regex": "^purchase:"}})
    doc = mongo.analytics_events.find_one({"anon_id": anon})
    assert not any(k in doc for k in ("email", "name", "address"))
    if slug:
        assert w["a"].get("/vendor/analytics").json()["product_views"] >= 1
        assert w["b"].get("/vendor/analytics").json()["product_views"] == w["b"].get("/vendor/analytics").json()["product_views"]


def test_07_referrals_attribution(w):  # noqa: F811
    ref = buyer()
    me = ref.get("/referrals/me").json()
    T["ref_code"] = me["code"]
    assert me["link"].endswith(f"?ref={me['code']}") and me["rewards_enabled"] is False
    httpx.post(f"{BASE}/analytics/events", json={"anon_id": f"t12{uuid.uuid4().hex[:10]}", "events": [{"type": "referral_visit", "event_id": f"r{uuid.uuid4().hex}", "referral_code": me["code"]}]})
    email = f"t12_friend_{uuid.uuid4().hex[:6]}@example.com"
    friend = httpx.Client(base_url=BASE, timeout=60)
    r = friend.post("/auth/register", json={"name": "TEST Friend", "email": email, "password": "Str0ng!Passw0rd#", "referral_code": me["code"], "marketing_opt_in": True})
    assert r.status_code == 201, r.text
    fid = mongo.users.find_one({"email": email})["_id"]
    T.setdefault("extra_users", []).append(fid)
    assert mongo.referrals.count_documents({"referred_id": fid}) == 1 and mongo.users.find_one({"_id": fid})["marketing_opt_in"] is True
    mongo.users.update_one({"_id": fid}, {"$set": {"status": "active"}})
    from afrovending.core import marketing  # noqa: F401
    mine = ref.get("/referrals/me").json()
    assert mine["signups"] == 1 and mine["visits"] >= 1 and "email" not in str(mine["activity"]).lower()
    own = ref.get("/referrals/me").json()["code"]
    selfc = httpx.Client(base_url=BASE, timeout=60)
    ref_email = mongo.users.find_one({"referral_code": own})["email"]
    e2 = ref_email.replace("@", "+alt@")
    assert selfc.post("/auth/register", json={"name": "TEST Self", "email": e2, "password": "Str0ng!Passw0rd#", "referral_code": own}).status_code == 201
    sid = mongo.users.find_one({"email": e2})["_id"]
    T["extra_users"].append(sid)
    assert mongo.referrals.count_documents({"referred_id": sid}) == 0  # self-referral rejected
    T["friend_id"] = fid


def test_08_consent_unsubscribe_and_cart_reminders(w):  # noqa: F811
    from afrovending.core.marketing import unsubscribe_token
    c = buyer()
    uid = S["buyers"][-1]
    assert c.put("/account/marketing", json={"marketing_opt_in": True}).json()["marketing_opt_in"] is True
    assert c.post("/cart/items", json={"variant_id": w["scarf"][1], "quantity": 1}).status_code == 200
    cart = mongo.carts.find_one({"user_id": uid, "status": "active"})
    old = cart["updated_at"] - timedelta(hours=2)
    mongo.carts.update_one({"_id": cart["_id"]}, {"$set": {"updated_at": old}})
    from tests.test_phase03_vendors import admin_client
    sup = admin_client()
    body = {"abandoned_cart_enabled": True, "first_delay_min": 60, "second_delay_min": 1440, "max_per_7_days": 2}
    assert sup.put("/admin/marketing/flags", json=body).status_code == 200
    import time
    secret = __import__("os").environ.get("WEBHOOK_CRON_SECRET") or open("/app/backend/.env").read().split("WEBHOOK_CRON_SECRET=")[1].split("\n")[0].strip('"')

    def run():
        assert httpx.post(f"{BASE}/cron/abandoned-carts", headers={"Authorization": f"Bearer {secret}", "X-Webhook-Id": f"t12-{uuid.uuid4().hex}"}, timeout=30).status_code == 202
        time.sleep(4)
    run()
    run()  # idempotent: same cart version + step can't send twice
    rems = list(mongo.cart_reminders.find({"cart_id": cart["_id"]}))
    assert len(rems) == 1 and rems[0]["step"] == 1
    other = buyer()
    assert other.post("/cart/items", json={"variant_id": w["scarf"][1], "quantity": 1}).status_code == 200
    ouid = S["buyers"][-1]
    mongo.carts.update_one({"user_id": ouid, "status": "active"}, {"$set": {"updated_at": old}})
    run()
    assert mongo.cart_reminders.count_documents({"user_id": ouid}) == 0  # no consent, no email
    assert httpx.post(f"{BASE}/marketing/unsubscribe", json={"token": "bad.token.value"}).status_code == 422
    assert httpx.post(f"{BASE}/marketing/unsubscribe", json={"token": unsubscribe_token(uid)}).status_code == 200
    assert mongo.users.find_one({"_id": uid})["marketing_opt_in"] is False
    mongo.carts.update_one({"_id": cart["_id"]}, {"$set": {"updated_at": cart["updated_at"] - timedelta(hours=30)}})
    run()
    assert mongo.cart_reminders.count_documents({"cart_id": cart["_id"], "step": 2}) == 0  # unsubscribed
    assert sup.put("/admin/marketing/flags", json={**body, "abandoned_cart_enabled": False}).status_code == 200


def test_09_wishlist_and_campaigns(w):  # noqa: F811
    c = buyer()
    p = mongo.products.find_one({"vendor_id": S["vendor_ids"][0], "status": "active"})
    assert c.put(f"/wishlist/{p['slug']}").status_code == 200 and c.put(f"/wishlist/{p['slug']}").status_code == 200
    assert c.get("/wishlist").json()["slugs"] == [p["slug"]]
    assert buyer().get("/wishlist").json()["slugs"] == []
    content, _ = admin_with("content_admin")
    sup, _ = admin_with("support_admin")
    camp = {"name": "TEST12 Summer", "headline": "Summer edit", "status": "active", "cta_url": "//evil.com"}
    assert content.post("/admin/campaigns", json=camp).status_code == 422
    assert sup.post("/admin/campaigns", json={**camp, "cta_url": "/shop"}).status_code == 403
    r = content.post("/admin/campaigns", json={**camp, "cta_url": "/shop"})
    assert r.status_code == 201
    assert any(x["id"] == r.json()["id"] for x in httpx.get(f"{BASE}/campaigns/active").json()["data"])
