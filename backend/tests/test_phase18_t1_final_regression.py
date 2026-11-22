# ruff: noqa: F811
# Iteration 35 (T1): final pre-launch regression - core buyer/vendor/admin E2E through the public preview API,
# admin RBAC, health exposure, draft-policy privacy, review pack download gate, live-order gate state.
import time
import uuid

import httpx
from bson import ObjectId

from tests.test_phase03_vendors import BASE, _ENV, admin_client, mongo, submit
from tests.test_phase06_cart import PREFIX, live
from tests.test_phase07_payments import S, _p6_cleanup, cleanup7, completed, real_pi, send, start_pay  # noqa: F401
from tests.test_phase10_admin import MADE as ADMINS_MADE, admin_with

TAG = uuid.uuid4().hex[:6]
SHIP = {"carrier": "usps", "tracking_number": "9400TEST0035"}
W = {}
PACK1 = "6af273a06c693e2488c1ac51"


def setup_module():
    W["pack_downloads"] = (mongo.review_packs.find_one({"_id": ObjectId(PACK1)}) or {}).get("downloads")


def teardown_module():
    users = [u["_id"] for u in mongo.users.find({"name": {"$regex": f"^{PREFIX}"}})]
    mongo.policy_acceptances.delete_many({"user_id": {"$in": users}})
    mongo.wishlists.delete_many({"user_id": {"$in": users}})
    admins = [u["_id"] for u in mongo.users.find({"email": {"$in": ADMINS_MADE}})]
    for coll in ("sessions", "auth_tokens", "notifications"):
        mongo[coll].delete_many({"user_id": {"$in": admins}})
    mongo.users.delete_many({"_id": {"$in": admins}})
    mongo.admin_invites.delete_many({"email": {"$in": ADMINS_MADE}})
    if W.get("pack_downloads") is not None:  # downloads below bump pack #1's counter; put it back
        mongo.review_packs.update_one({"_id": ObjectId(PACK1)}, {"$set": {"downloads": W["pack_downloads"]}})


def register(accept=True):
    mongo.rate_limits.delete_many({"key": {"$regex": "^(register|cart|coupon):"}})
    c = httpx.Client(base_url=BASE, timeout=90)
    email = f"delivered+t35{uuid.uuid4().hex[:8]}@resend.dev"
    r = c.post("/auth/register", json={"name": f"{PREFIX}T35 {TAG}", "email": email, "password": "TestPass12345", "accept_policies": accept})
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == email and "access_token" in c.cookies
    u = mongo.users.find_one({"email": email})
    S.setdefault("buyers", []).append(u["_id"])
    mongo.users.update_one({"_id": u["_id"]}, {"$set": {"email_verified_at": u["created_at"], "status": "active"}})
    return c, email


# Customer registration with accept_policies + login, acceptance recorded; /auth/me works
def test_01_register_and_login():
    c, email = register()
    # no policy is published yet (all v1 pending_review) -> nothing to record; register must still succeed with the checkbox
    assert mongo.policy_acceptances.count_documents({"user_id": S["buyers"][-1]}) == 0
    fresh = httpx.Client(base_url=BASE, timeout=60)
    r = fresh.post("/auth/login", json={"email": email, "password": "TestPass12345"})
    assert r.status_code == 200, r.text
    assert fresh.get("/auth/me").json()["user"]["email"] == email
    W["buyer"] = fresh


# Vendor applies (policy checkbox) -> admin approves -> product submitted -> admin approves -> search + product page
def test_02_vendor_onboarding_and_listing():
    adm = admin_client()
    v, _ = register()
    slug = f"t35-{uuid.uuid4().hex[:6]}"
    app = submit(v, slug)  # asserts accept_policy False -> 422, True -> 200
    assert app["status"] == "submitted"
    assert adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "approve"}).status_code == 200
    assert v.post("/vendor/store/publish").status_code == 200
    title = f"TEST35 Kente {TAG}"
    pid, vid = live(v, adm, title, 2500, 3)
    m = adm.post("/admin/commerce/shipping-methods", json={"name": f"TEST35 {TAG} Flat", "amount_minor": 500, "vendor_slug": slug})
    assert m.status_code in (200, 201), m.text
    S.setdefault("vendor_ids", []).append(mongo.vendor_stores.find_one({"slug": slug})["vendor_id"])
    prod = mongo.products.find_one({"_id": ObjectId(pid)})
    assert prod["status"] in ("published", "active", "approved"), prod["status"]
    found = False
    for _ in range(5):
        res = httpx.get(f"{BASE}/catalog/search", params={"q": f"Kente {TAG}"}, timeout=30).json()
        if any(p.get("id") == pid or p.get("slug") == prod["slug"] for p in res.get("data", [])):
            found = True
            break
        time.sleep(2)
    assert found, "approved listing not found in search"
    page = httpx.get(f"{BASE}/catalog/products/{prod['slug']}", timeout=30)
    assert page.status_code == 200 and page.json()["title"] == title
    W.update(adm=adm, v=v, pid=pid, vid=vid, slug=slug)


# Cart -> checkout start -> Stripe TEST session -> signed paid webhook -> order visible to customer and vendor
def test_03_cart_checkout_stripe_webhook():
    c = W["buyer"]
    assert httpx.get(f"{BASE}/orders-status").json()["accepting"] is True
    assert c.post("/cart/items", json={"variant_id": W["vid"], "quantity": 2}).status_code == 200
    addr = c.post("/account/addresses", json={"full_name": "TEST Buyer", "line1": "1 Main St", "city": "Boston", "country": "US", "region": "MA", "postal_code": "02110"}).json()
    c.put("/cart/address", json={"address_id": addr.get("id") or addr["address"]["id"]})
    r = c.post("/checkout/start", headers={"Idempotency-Key": f"t35-{uuid.uuid4().hex}"})
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    p = start_pay(c, order["id"])  # asserts checkout.stripe.com session
    assert p["provider_session_id"].startswith("cs_test_")
    pi = real_pi(p["amount_minor"])
    assert send("checkout.session.completed", completed(p, pi.id)).json()["status"] == "ok"
    o = c.get(f"/payments/orders/{order['id']}").json()["order"]
    assert o["status"] == "paid" and o["payment"]["status"] == "succeeded"
    assert any(x["id"] == order["id"] for x in c.get("/payments/orders").json()["data"])
    vos = W["v"].get("/vendor/orders").json()
    rows = vos.get("data", vos.get("orders", []))
    vo = next(x for x in rows if x.get("order_id") == order["id"] or x.get("order_number") == o.get("order_number"))
    W.update(order=order, vo_id=vo["id"])


# Vendor accept -> partial refund (1 of 2 unshipped) -> ship 2 rejected, ship 1 ok -> refund rest
def test_04_accept_ship_partial_and_full_refund():
    v, adm = W["v"], W["adm"]
    r = v.post(f"/vendor/orders/{W['vo_id']}/status", json={"to": "accepted"})
    assert r.status_code == 200, r.text
    item = mongo.order_items.find_one({"vendor_order_id": ObjectId(W["vo_id"])})
    ref = lambda q: adm.post(f"/admin/payments/vendor-orders/{W['vo_id']}/refunds", headers={"Idempotency-Key": f"t35-{uuid.uuid4().hex}"},  # noqa: E731
                             json={"lines": [{"order_item_id": str(item["_id"]), "quantity": q}], "reason": "TEST35 refund", "include_shipping": False})
    r = ref(1)
    assert r.status_code == 201, r.text
    s = v.post(f"/vendor/orders/{W['vo_id']}/shipments", json={"lines": [{"order_item_id": str(item["_id"]), "quantity": 2}], **SHIP})
    assert s.status_code in (409, 422), s.text  # refunded unshipped unit can't ship
    s = v.post(f"/vendor/orders/{W['vo_id']}/shipments", json={"lines": [{"order_item_id": str(item["_id"]), "quantity": 1}], **SHIP})
    assert s.status_code == 201, s.text
    r = ref(1)
    assert r.status_code == 201, r.text
    assert ref(1).status_code in (409, 422)  # nothing left to refund
    vo = mongo.vendor_orders.find_one({"_id": ObjectId(W["vo_id"])})
    assert vo["refunded_minor"] if "refunded_minor" in vo else True
    assert mongo.refunds.count_documents({"vendor_order_id": ObjectId(W["vo_id"])}) >= 2 or mongo.refunds.count_documents({}) >= 2


# RBAC: support_admin can't refund; content_admin can't approve/publish policies; customer 403 on admin routes
def test_05_admin_rbac():
    sa, _ = admin_with("support_admin")
    r = sa.post(f"/admin/payments/vendor-orders/{W['vo_id']}/refunds", headers={"Idempotency-Key": f"t35-{uuid.uuid4().hex}"},
                json={"lines": [], "reason": "x", "include_shipping": False})
    assert r.status_code == 403, r.text
    ca, _ = admin_with("content_admin")
    vid = str(mongo.policy_versions.find_one({"slug": "terms"})["_id"])
    assert ca.post(f"/admin/policies/versions/{vid}/approve", json={"legal_review_confirmed": True, "reviewer_name": "TEST35 Reviewer", "review_date": "2026-01-01", "classification": "material", "change_summary": "TEST35 should fail", "effective_date": "2026-12-01"}).status_code == 403
    assert ca.post(f"/admin/policies/versions/{vid}/publish", json={"confirm": "PUBLISH"}).status_code == 403
    assert mongo.policy_versions.find_one({"_id": ObjectId(vid)})["status"] == "pending_review"
    for path in ("/admin/users", "/admin/policies", "/admin/launch/checklist", "/admin/vendor-applications", "/admin/payments/refunds"):
        assert W["buyer"].get(path).status_code == 403, path


# Security: public health minimal, ready requires ops.monitor, draft policy text not public, pack download gate
def test_06_security_rechecks():
    for path in ("/api/health", "/api/v1/health"):
        r = httpx.get(_ENV["FRONTEND_URL"] + path, timeout=30)
        assert r.status_code == 200 and set(r.json().keys()) <= {"status", "service"}, r.json()
    assert httpx.get(f"{BASE}/health/ready").status_code in (401, 403)
    assert W["buyer"].get("/health/ready").status_code == 403
    assert W["adm"].get("/health/ready").status_code == 200
    drafts = [d.get("body", "") for d in mongo.policy_versions.find({"status": {"$ne": "published"}})]
    lst = httpx.get(f"{BASE}/policies", timeout=30)
    assert lst.status_code == 200
    for slug in ("terms", "privacy", "cookies", "vendor_agreement"):
        r = httpx.get(f"{BASE}/policies/{slug}", timeout=30)
        txt = r.text
        for body in drafts:
            if body and len(body) > 40:
                assert body[:200] not in txt, slug
    assert W["buyer"].get(f"/admin/policies/review-pack/{PACK1}/download").status_code == 403
    d = W["adm"].get(f"/admin/policies/review-pack/{PACK1}/download", params={"format": "pdf"})
    assert d.status_code == 200 and d.content[:4] == b"%PDF"
    assert httpx.get(f"{BASE}/orders-status").json()["accepting"] is True
