# Phase 10 extended (T1): refund second-approval, invite revoke, MFA gating, support order-linking, content admin, regressions
import uuid

import httpx
from bson import ObjectId

from tests.test_phase03_vendors import ADMIN, BASE, mongo, verified_client, admin_client
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w  # noqa: F401
from tests.test_phase08_fulfillment import paid
from tests.test_phase10_admin import MADE, admin_with, teardown_module as _p10_teardown  # noqa: F401

APPROVALS = []
BANNERS = []
TICKETS = []


def teardown_module():
    mongo.admin_approvals.delete_many({"_id": {"$in": [ObjectId(i) for i in APPROVALS]}})
    mongo.content_banners.delete_many({"_id": {"$in": [ObjectId(i) for i in BANNERS]}})
    mongo.support_tickets.delete_many({"_id": {"$in": [ObjectId(i) for i in TICKETS]}})
    mongo.platform_settings.delete_many({"key": "admin.approvals"})  # none existed before this run
    _p10_teardown()


# MFA gating: super admin without TOTP step cannot use admin tools
def test_01_mfa_gate_and_staff_410():
    c = httpx.Client(base_url=BASE, timeout=60)
    assert c.post("/auth/login", json=ADMIN).status_code == 200
    r = c.get("/admin/overview")
    assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required"
    st = c.get("/auth/mfa").json()
    assert st["required"] is True and st["enrolled"] is True and st["verified"] is False
    assert c.post("/auth/mfa/verify", json={"code": "12345"}).status_code == 422
    sup = admin_client()
    assert sup.post("/admin/staff", json={"name": "x", "email": "y@example.com", "password": "Str0ng!Passw0rd#1", "role": "super_admin"}).status_code == 410
    for path in ("/admin/payments/ledger", "/admin/payments/ledger/abc"):
        assert sup.put(path, json={"amount_minor": 1}).status_code in (404, 405)
        assert sup.delete(path).status_code in (404, 405)


# Invite create/list/revoke; revoked token rejected
def test_02_invite_revoke():
    sup = admin_client()
    mongo.rate_limits.delete_many({"key": {"$regex": "^(invite-accept|admin-invite|mfa|login)"}})
    email = f"test10_rev_{uuid.uuid4().hex[:6]}@example.com"
    MADE.append(email)
    inv = sup.post("/admin/team/invites", json={"email": email, "role": "content_admin"})
    assert inv.status_code == 201
    iid = inv.json()["id"]
    assert any(i["id"] == iid for i in sup.get("/admin/team").json()["invites"])
    stored = mongo.admin_invites.find_one({"_id": ObjectId(iid)})
    assert "token" not in stored and len(stored["token_hash"]) >= 32
    from afrovending.core.security import new_opaque_token
    raw, h = new_opaque_token()
    mongo.admin_invites.update_one({"_id": ObjectId(iid)}, {"$set": {"token_hash": h}})
    assert sup.delete(f"/admin/team/invites/{iid}").status_code == 200
    assert not any(i["id"] == iid for i in sup.get("/admin/team").json()["invites"])
    assert httpx.post(f"{BASE}/auth/admin-invite/accept", json={"token": raw, "name": "x", "password": "Str0ng!Passw0rd#1"}).status_code == 410
    assert sup.delete(f"/admin/team/invites/{iid}").status_code == 404
    bad = sup.post("/admin/team/invites", json={"email": email, "role": "god_admin"})
    assert bad.status_code == 422


# Refund above threshold needs a second finance admin
def test_03_refund_second_approval(w):
    sup = admin_client()
    assert sup.put("/admin/approvals/config", json={"refund_threshold_minor": 1000}).status_code == 200
    c = buyer()
    _, vos = paid(c, [(w["scarf"][1], 1)])
    va = vos[w["slug_a"]]
    vo = mongo.vendor_orders.find_one({"order_number": va["order_number"]}) if va.get("order_number") else None
    vo = vo or mongo.vendor_orders.find_one({"customer_id": S["buyers"][-1], "vendor_slug": w["slug_a"]})
    item = mongo.order_items.find_one({"vendor_order_id": vo["_id"]})
    f1, _ = admin_with("finance_admin")
    f2, _ = admin_with("finance_admin")
    supp, _ = admin_with("support_admin")
    body = {"lines": [{"order_item_id": str(item["_id"]), "quantity": 1}], "reason": "TEST approval"}
    key = {"Idempotency-Key": f"t10-{uuid.uuid4().hex}"}
    assert supp.post(f"/admin/payments/vendor-orders/{vo['_id']}/refunds", json=body, headers=key).status_code == 403
    r = f1.post(f"/admin/payments/vendor-orders/{vo['_id']}/refunds", json=body, headers=key)
    assert r.status_code == 202, r.text
    d = r.json()
    APPROVALS.append(d["approval_id"])
    assert d["status"] == "pending_approval" and d["amount_minor"] >= 4500
    assert f1.post(f"/admin/payments/vendor-orders/{vo['_id']}/refunds", json=body, headers=key).status_code == 409
    assert mongo.refunds.count_documents({"vendor_order_id": vo["_id"]}) == 0
    assert f1.post(f"/admin/approvals/{d['approval_id']}/decide", json={"decision": "approve"}).status_code == 403
    assert supp.post(f"/admin/approvals/{d['approval_id']}/decide", json={"decision": "approve"}).status_code == 403
    assert any(a["id"] == d["approval_id"] and a["status"] == "pending" for a in f2.get("/admin/approvals").json()["data"])
    ok = f2.post(f"/admin/approvals/{d['approval_id']}/decide", json={"decision": "approve", "note": "TEST ok"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved" and ok.json()["refund_id"]
    assert mongo.refunds.count_documents({"vendor_order_id": vo["_id"]}) == 1
    assert f2.post(f"/admin/approvals/{d['approval_id']}/decide", json={"decision": "approve"}).status_code == 404
    # rejection path
    key2 = {"Idempotency-Key": f"t10-{uuid.uuid4().hex}"}
    shipping_only = {"lines": [], "include_shipping": True, "reason": "TEST reject"}
    r2 = f1.post(f"/admin/payments/vendor-orders/{vo['_id']}/refunds", json=shipping_only, headers=key2)
    print("shipping-only refund", r2.status_code, r2.text[:200])
    if r2.status_code == 202:
        APPROVALS.append(r2.json()["approval_id"])
        rj = f2.post(f"/admin/approvals/{r2.json()['approval_id']}/decide", json={"decision": "reject"})
        assert rj.status_code == 200 and rj.json()["status"] == "rejected"


# Support ticket linked to own order; other customer's order number rejected
def test_04_ticket_with_own_order(w):
    c = buyer()
    oid, _ = paid(c, [(w["shea"][1], 1)])
    num = mongo.orders.find_one({"_id": ObjectId(oid)})["order_number"]
    other = verified_client()
    assert other.post("/support/tickets", json={"category": "delivery", "subject": "Not mine", "body": "Trying another order number", "order_number": num}).status_code == 422
    t = c.post("/support/tickets", json={"category": "delivery", "subject": "TEST late", "body": "Where is my parcel please", "order_number": num})
    assert t.status_code == 201, t.text
    TICKETS.append(t.json()["id"])
    assert t.json()["order_number"] == num and t.json()["queue"] == "support"
    assert "customer_email" not in t.json() and "history" not in t.json()
    assert other.get(f"/support/tickets/{t.json()['id']}").status_code == 404
    assert other.post(f"/support/tickets/{t.json()['id']}/replies", json={"body": "hi"}).status_code == 404
    assert c.post("/support/tickets", json={"category": "bogus", "subject": "xxxx", "body": "xxxxxxxxxxxx"}).status_code == 422
    sup = admin_client()
    assert sup.patch(f"/admin/support/tickets/{t.json()['id']}", json={"status": "closed"}).status_code == 200
    assert c.post(f"/support/tickets/{t.json()['id']}/replies", json={"body": "again"}).status_code == 409


# Content admin: hide banner removes it from homepage; content admin blocked elsewhere
def test_05_content_hide_and_scope():
    cc, _ = admin_with("content_admin")
    b = cc.post("/admin/content/banners", json={"title": "TEST T1 hide", "cta_url": "https://example.com/x", "placement": "home_strip"})
    assert b.status_code == 201
    bid = b.json()["id"]
    BANNERS.append(bid)
    accepted = []
    for bad in ("javascript:alert(1)", "http://insecure.example", "data:text/html,x", "//evil.com", "/\\evil.com"):
        r = cc.post("/admin/content/banners", json={"title": "Bad", "cta_url": bad})
        if r.status_code == 201:
            BANNERS.append(r.json()["id"])
            accepted.append(bad)
    assert any(x["id"] == bid for x in httpx.get(f"{BASE}/content/homepage").json()["banners"])
    assert cc.put(f"/admin/content/banners/{bid}", json={"title": "TEST T1 hide", "cta_url": "https://example.com/x", "status": "inactive"}).status_code == 200
    assert not any(x["id"] == bid for x in httpx.get(f"{BASE}/content/homepage").json()["banners"])
    for path in ("/admin/vendors", "/admin/payments/payments", "/admin/support/tickets", "/admin/users", "/admin/team", "/admin/approvals"):
        assert cc.get(path).status_code == 403, path
    for kind in ("orders", "ledger", "tickets", "customers", "vendors"):
        assert cc.get(f"/admin/exports/{kind}.csv").status_code == 403, kind
    assert cc.delete(f"/admin/content/banners/{bid}").status_code == 200
    assert not accepted, f"unsafe CTA URLs accepted: {accepted}"
