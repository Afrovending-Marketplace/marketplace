# Phase 12 T1 extended checks: SEO share pages, campaigns/coupons validation, sponsored lock, wishlist, referrals, unsubscribe, permissions.
# Requires seeded UI data: python -m tests.seed_phase11_ui seed (state in /tmp/seed11ui.json)
import json
import uuid

import httpx
import pytest

from tests.test_phase03_vendors import BASE, admin_client, mongo
from tests.test_phase10_admin import MADE, admin_with, teardown_module as _p10_teardown  # noqa: F401

ST = json.load(open("/tmp/seed11ui.json"))
T = {"codes": [], "camps": [], "users": []}
_FLAGS = mongo.platform_settings.find_one({"key": "marketing.flags"})


def teardown_module():
    cids = [c["_id"] for c in mongo.coupons.find({"code": {"$in": T["codes"]}})]
    mongo.coupons.delete_many({"_id": {"$in": cids}})
    mongo.campaigns.delete_many({"_id": {"$in": T["camps"]}})
    mongo.audit_logs.delete_many({"entity_id": {"$in": [str(c) for c in cids + T["camps"]]}})
    for uid in T["users"]:
        mongo.referrals.delete_many({"$or": [{"referred_id": uid}, {"referrer_id": uid}]})
        mongo.wishlists.delete_many({"user_id": uid})
        mongo.sessions.delete_many({"user_id": uid})
        mongo.audit_logs.delete_many({"$or": [{"actor_id": uid}, {"entity_id": str(uid)}]})
        mongo.users.delete_one({"_id": uid})
    if not _FLAGS:
        mongo.platform_settings.delete_many({"key": "marketing.flags"})
    _p10_teardown()


def _login(email, pw=ST["pw"]):
    c = httpx.Client(base_url=BASE, timeout=60)
    mongo.rate_limits.delete_many({"key": {"$regex": "^login"}})
    r = c.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="module")
def buyer():
    return _login(ST["buyer"])


@pytest.fixture(scope="module")
def vendor():
    return _login(ST["vendor_a"])


# SEO share pages
def test_share_product_and_store_and_sitemap():
    h = httpx.get(f"{BASE}/seo/share/products/{ST['product_slug']}").text
    assert 'property="og:title"' in h and 'rel="canonical"' in h and '"@type": "Product"' in h
    assert '"price": "45.00"' in h, h[:1500]
    s = httpx.get(f"{BASE}/seo/share/stores/{ST['slug_a']}").text
    assert 'property="og:title"' in s and '"@type": "Store"' in s and f"/store/{ST['slug_a']}" in s
    sm = httpx.get(f"{BASE}/seo/sitemap.xml").text
    assert f"/products/{ST['product_slug']}</loc>" in sm and f"/store/{ST['slug_a']}</loc>" in sm
    nf = httpx.get(f"{BASE}/seo/share/products/does-not-exist-xyz")
    assert nf.status_code == 200 and '"@type"' not in nf.text


# Wishlist
def test_wishlist_add_remove_unknown(buyer):
    assert buyer.put("/wishlist/does-not-exist-xyz").status_code == 404
    assert buyer.put("/wishlist/kente-wrap-dress").status_code in (200, 404)  # static dev slug
    assert buyer.put(f"/wishlist/{ST['product_slug']}").status_code == 200
    d = buyer.get("/wishlist").json()
    assert ST["product_slug"] in d["slugs"] and d["data"][0]["title"]
    assert buyer.delete(f"/wishlist/{ST['product_slug']}").status_code == 200
    assert ST["product_slug"] not in buyer.get("/wishlist").json()["slugs"]
    assert httpx.get(f"{BASE}/wishlist").status_code == 401


# Vendor coupons validation and duplicate codes
def test_vendor_coupon_validation(vendor):
    code = f"T12X{uuid.uuid4().hex[:5].upper()}"
    T["codes"].append(code)
    assert vendor.post("/vendor/coupons", json={"code": code, "type": "percent", "value": 20000}).status_code == 422
    assert vendor.post("/vendor/coupons", json={"code": "bad code!", "type": "fixed", "value": 100}).status_code == 422
    r = vendor.post("/vendor/coupons", json={"code": code.lower(), "type": "fixed", "value": 300})
    assert r.status_code == 201 and r.json()["code"] == code and r.json()["funded_by"] == "vendor"
    assert vendor.post("/vendor/coupons", json={"code": code, "type": "fixed", "value": 300}).status_code == 409
    assert any(c["code"] == code for c in vendor.get("/vendor/coupons").json()["data"])
    upd = vendor.put(f"/vendor/coupons/{r.json()['id']}", json={"code": code, "type": "fixed", "value": 400, "status": "paused"})
    assert upd.status_code == 200 and upd.json()["status"] == "paused" and upd.json()["value"] == 400
    assert vendor.put("/vendor/coupons/notanid", json={"code": code, "type": "fixed", "value": 1}).status_code == 404


def test_customer_cannot_use_vendor_coupon_api(buyer):
    assert buyer.get("/vendor/coupons").status_code in (403, 404)


# Campaigns validation, update, public listing
def test_campaign_validation_and_lifecycle():
    content, _ = admin_with("content_admin")
    base = {"name": "TEST12T1 Camp", "headline": "Harmattan sale", "cta_url": "/shop"}
    assert content.post("/admin/campaigns", json={**base, "coupon_code": "NOPE-NOT-REAL"}).status_code == 422
    assert content.post("/admin/campaigns", json={**base, "starts_at": "2026-02-01T00:00:00Z", "ends_at": "2026-01-01T00:00:00Z"}).status_code == 422
    assert content.post("/admin/campaigns", json={**base, "cta_url": "javascript:alert(1)"}).status_code == 422
    r = content.post("/admin/campaigns", json=base)
    assert r.status_code == 201 and r.json()["status"] == "draft"
    from bson import ObjectId
    T["camps"].append(ObjectId(r.json()["id"]))
    pub = httpx.get(f"{BASE}/campaigns/active").json()["data"]
    assert not any(x["id"] == r.json()["id"] for x in pub)  # draft hidden
    u = content.put(f"/admin/campaigns/{r.json()['id']}", json={**base, "status": "active"})
    assert u.status_code == 200 and u.json()["status"] == "active"
    assert any(x["id"] == r.json()["id"] for x in httpx.get(f"{BASE}/campaigns/active").json()["data"])
    content.put(f"/admin/campaigns/{r.json()['id']}", json={**base, "status": "paused"})
    assert content.put("/admin/campaigns/000000000000000000000000", json=base).status_code == 404


# Sponsored & flags locks
def test_sponsored_and_flags_locked():
    sup = admin_client()
    assert sup.post("/admin/sponsored", json={"product_slug": ST["product_slug"], "status": "active"}).status_code == 409
    body = {"abandoned_cart_enabled": False, "first_delay_min": 60, "second_delay_min": 1440, "max_per_7_days": 2}
    assert sup.put("/admin/marketing/flags", json={**body, "referral_rewards_enabled": True}).status_code == 409
    assert sup.put("/admin/marketing/flags", json={**body, "second_delay_min": 60}).status_code == 422
    f = sup.get("/admin/marketing/flags").json()
    assert f["abandoned_cart"]["enabled"] is False and f["sponsored_listings_enabled"] is False
    cfg = httpx.get(f"{BASE}/marketing/config").json()
    assert cfg["sponsored_listings_enabled"] is False


# Admin reporting endpoints & permissions
def test_admin_reports_permissions():
    sup = admin_client()
    a = sup.get("/admin/analytics", params={"from": "2026-01-01", "to": "2026-01-31"})
    assert a.status_code == 200 and a.json()["range"]["from"].startswith("2026-01-01")
    assert sup.get("/admin/referrals").status_code == 200
    st = sup.get("/admin/cart-reminders/stats").json()
    assert st["enabled"] is False
    rep = sup.get("/admin/coupons/report")
    assert rep.status_code == 200 and "promotional_expense_minor" in rep.json()
    support, _ = admin_with("support_admin")
    assert support.get("/admin/analytics").status_code == 403
    assert support.get("/admin/referrals").status_code == 403
    assert httpx.get(f"{BASE}/admin/analytics").status_code == 401


# Referrals: unknown code, PII, self-referral via same email base
def test_referral_unknown_code_and_link(buyer):
    me = buyer.get("/referrals/me").json()
    assert me["code"].startswith("AV") and f"?ref={me['code']}" in me["link"]
    email = f"t12t1_{uuid.uuid4().hex[:6]}@example.com"
    r = httpx.post(f"{BASE}/auth/register", json={"name": "TEST T1 ref", "email": email, "password": "Str0ng!Passw0rd#", "referral_code": "AVNOTREAL"})
    assert r.status_code == 201, r.text
    uid = mongo.users.find_one({"email": email})["_id"]
    T["users"].append(uid)
    assert mongo.referrals.count_documents({"referred_id": uid}) == 0
    assert mongo.users.find_one({"_id": uid}).get("marketing_opt_in") in (False, None)
    # invalid ref visit is not stored
    s = httpx.post(f"{BASE}/analytics/events", json={"anon_id": f"t12t1{uuid.uuid4().hex[:8]}", "events": [{"type": "referral_visit", "event_id": f"r{uuid.uuid4().hex}", "referral_code": "AVNOTREAL"}]})
    assert s.json()["stored"] == 0


# Unsubscribe tokens
def test_unsubscribe_tampered():
    from afrovending.core.marketing import unsubscribe_token
    uid = mongo.users.find_one({"email": ST["buyer"]})["_id"]
    tok = unsubscribe_token(uid)
    assert httpx.post(f"{BASE}/marketing/unsubscribe", json={"token": tok[:-2] + "00"}).status_code == 422
    assert httpx.post(f"{BASE}/marketing/unsubscribe", json={"token": ""}).status_code == 422


# Plans / subscription
def test_vendor_plan_request_keeps_plan(vendor):
    before = vendor.get("/vendor/subscription").json()["plan"]
    r = vendor.post("/vendor/subscription/request", json={"plan": "growth"})
    assert r.status_code == 201
    after = vendor.get("/vendor/subscription").json()
    assert after["plan"] == before and after["pending_request"]["plan"] == "growth"
    assert vendor.post("/vendor/subscription/request", json={"plan": before}).status_code == 409
    vid = mongo.vendors.find_one({"slug": ST["slug_a"]}) or {}
    mongo.subscription_requests.delete_many({"requested_by": mongo.users.find_one({"email": ST["vendor_a"]})["_id"]})
    assert vid is not None
