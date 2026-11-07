import uuid
from datetime import timedelta

import httpx
import pyotp
from bson import ObjectId

from afrovending.core.models import utcnow
from tests.test_phase03_vendors import ADMIN, BASE, admin_client, mongo, verified_client

MADE = []


def admin_with(role):
    """Creates a TEST admin via a real invite accepted by a new account, then enrolls TOTP."""
    sup = admin_client()
    mongo.rate_limits.delete_many({"key": {"$regex": "^(invite-accept|admin-invite|mfa|login)"}})
    email = f"test10_{role}_{uuid.uuid4().hex[:6]}@example.com"
    r = sup.post("/admin/team/invites", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    MADE.append(email)
    raw = r.json().get("invite_link", "").split("token=")[-1]
    if not raw:  # email sent: issue a known token for the test by replacing the stored hash
        from afrovending.core.security import new_opaque_token
        raw, h = new_opaque_token()
        mongo.admin_invites.update_one({"_id": ObjectId(r.json()["id"])}, {"$set": {"token_hash": h}})
    c = httpx.Client(base_url=BASE, timeout=60)
    assert c.post("/auth/admin-invite/accept", json={"token": raw, "name": f"TEST {role}", "password": "Str0ng!Passw0rd#1"}).status_code == 200
    assert c.post("/auth/admin-invite/accept", json={"token": raw, "name": "x", "password": "Str0ng!Passw0rd#1"}).status_code in (410, 429)
    assert c.post("/auth/login", json={"email": email, "password": "Str0ng!Passw0rd#1"}).status_code == 200
    assert c.get("/admin/overview").json()["error"]["code"] == "mfa_required"
    secret = c.post("/auth/mfa/setup").json()["secret"]
    assert c.post("/auth/mfa/enable", json={"code": "000000"}).status_code == 422
    assert c.post("/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    return c, str(mongo.users.find_one({"email": email})["_id"])


def test_01_permission_matrix():
    clients = {r: admin_with(r) for r in ("marketplace_admin", "finance_admin", "support_admin", "content_admin")}
    sup = admin_client()
    cust = verified_client()
    matrix = [  # (method, path, json, allowed roles)
        ("get", "/admin/team", None, {"super"}),
        ("get", "/admin/audit-logs", None, {"super"}),
        ("post", "/admin/payments/commission-rules", {"scope": "default", "rate_bps": 1000}, {"super"}),
        ("get", "/admin/payments/payments", None, {"super", "marketplace_admin", "finance_admin"}),
        ("get", "/admin/payments/refunds", None, {"super", "marketplace_admin", "finance_admin"}),
        ("get", "/admin/vendor-applications", None, {"super", "marketplace_admin"}),
        ("get", "/admin/support/tickets", None, {"super", "marketplace_admin", "finance_admin", "support_admin"}),
        ("get", "/admin/content", None, {"super", "content_admin"}),
        ("get", "/admin/users", None, {"super", "marketplace_admin", "support_admin"}),
        ("get", "/admin/exports/ledger.csv", None, {"super", "finance_admin"}),
        ("get", "/admin/exports/customers.csv", None, {"super"}),
        ("get", "/admin/exports/vendors.csv", None, {"super", "marketplace_admin"}),
        ("get", "/admin/overview", None, {"super", "marketplace_admin", "finance_admin", "support_admin", "content_admin"}),
    ]
    for method, path, body, allowed in matrix:
        for name, c in [("super", sup), *[(r, cl) for r, (cl, _) in clients.items()], ("customer", cust)]:
            r = getattr(c, method)(path, **({"json": body} if body is not None else {}))
            if name in allowed:
                assert r.status_code < 400 or r.status_code == 422, (name, path, r.status_code, r.text[:200])
            else:
                assert r.status_code == 403, (name, path, r.status_code)
    ov = clients["content_admin"][0].get("/admin/overview").json()
    assert "finance" not in ov and "operations" not in ov and "tickets" not in ov
    assert "finance" in clients["finance_admin"][0].get("/admin/overview").json()
    assert mongo.commission_ledger.count_documents({}) >= 0  # no ledger edit endpoints exist
    for path in ("/admin/payments/ledger/x", "/admin/ledger/x"):
        assert sup.patch(path, json={"amount_minor": 1}).status_code in (404, 405)


def test_02_team_safeguards_and_session_revocation():
    sup = admin_client()
    me = str(mongo.users.find_one({"email": ADMIN["email"]})["_id"])
    assert sup.put(f"/admin/team/{me}/role", json={"role": "support_admin", "password": ADMIN["password"]}).status_code == 403  # no self-change
    c, uid = admin_with("support_admin")
    assert c.post("/admin/team/invites", json={"email": "x@example.com", "role": "super_admin"}).status_code == 403  # no self-promotion path
    assert sup.put(f"/admin/team/{uid}/role", json={"role": "finance_admin", "password": "wrong"}).status_code == 403
    assert sup.put(f"/admin/team/{uid}/role", json={"role": "finance_admin", "password": ADMIN["password"]}).status_code == 200
    assert c.get("/admin/overview").status_code == 401  # sessions revoked on role change
    assert sup.post(f"/admin/team/{uid}/revoke", json={"password": ADMIN["password"], "reason": "TEST offboard"}).status_code == 200
    assert "finance_admin" not in mongo.users.find_one({"_id": ObjectId(uid)})["roles"]
    others = list(mongo.users.find({"roles": "super_admin", "status": "active", "email": {"$ne": ADMIN["email"]}}))
    if not others:
        s2, sid2 = admin_with("super_admin")
        mongo.users.update_one({"_id": ObjectId(sid2)}, {"$set": {"status": "suspended"}})
        assert s2.post(f"/admin/team/{me}/revoke", json={"password": "Str0ng!Passw0rd#1", "reason": "TEST"}).status_code in (401, 409)
    inv = sup.post("/admin/team/invites", json={"email": f"test10_exp_{uuid.uuid4().hex[:5]}@example.com", "role": "content_admin"}).json()
    MADE.append(inv["email"])
    from afrovending.core.security import new_opaque_token
    raw, h = new_opaque_token()
    mongo.admin_invites.update_one({"_id": ObjectId(inv["id"])}, {"$set": {"token_hash": h, "expires_at": utcnow() - timedelta(minutes=1)}})
    assert httpx.post(f"{BASE}/auth/admin-invite/accept", json={"token": raw, "name": "x", "password": "Str0ng!Passw0rd#1"}).status_code == 410
    assert sup.post("/admin/staff", json={"name": "x", "email": "y@example.com", "password": "Str0ng!Passw0rd#1", "role": "super_admin"}).status_code == 410


def test_03_tickets_ownership_assignment_no_financial_side_effects():
    c, other = verified_client(), verified_client()
    assert c.post("/support/tickets", json={"category": "delivery", "subject": "Where is it", "body": "My parcel has not arrived yet.", "order_number": "AV-NOPE"}).status_code == 422
    t = c.post("/support/tickets", json={"category": "refund", "subject": "Refund please", "body": "<script>x</script> item broken\x07"}).json()
    assert t["reference"].startswith("AVT-") and t["queue"] == "finance" and "\x07" not in t["messages"][0]["body"]
    assert other.get(f"/support/tickets/{t['id']}").status_code == 404
    sc, sup_id = admin_with("support_admin")
    cc, content_id = admin_with("content_admin")
    assert sc.patch(f"/admin/support/tickets/{t['id']}", json={"assigned_to": content_id}).status_code == 422
    r = sc.patch(f"/admin/support/tickets/{t['id']}", json={"assigned_to": sup_id, "priority": "high", "status": "in_progress", "queue": "finance"})
    assert r.status_code == 200 and r.json()["priority"] == "high"
    assert sc.post(f"/admin/support/tickets/{t['id']}/replies", json={"body": "Checking now", "internal": False}).json()["status"] == "waiting_for_customer"
    sc.post(f"/admin/support/tickets/{t['id']}/replies", json={"body": "internal only", "internal": True})
    mine = c.get(f"/support/tickets/{t['id']}").json()
    assert all("internal only" != m["body"] for m in mine["messages"])
    assert c.post(f"/support/tickets/{t['id']}/replies", json={"body": "Thanks"}).json()["status"] == "open"
    before = mongo.refunds.count_documents({})
    sc.patch(f"/admin/support/tickets/{t['id']}", json={"status": "resolved"})
    assert mongo.refunds.count_documents({}) == before
    assert len(sc.get("/admin/support/tickets", params={"priority": "high", "queue": "finance"}).json()["data"]) >= 1
    assert cc.get("/admin/support/tickets").status_code == 403
    assert mongo.audit_logs.count_documents({"entity_id": {"$in": [t["id"], ObjectId(t["id"])]}, "action": "support.ticket_updated"}) >= 2
    mongo.support_tickets.delete_many({"_id": ObjectId(t["id"])})


def test_04_content_banners_and_featured():
    cc, _ = admin_with("content_admin")
    b = cc.post("/admin/content/banners", json={"title": "TEST Sale", "cta_url": "/search", "placement": "home_hero"}).json()
    assert cc.post("/admin/content/banners", json={"title": "Bad", "cta_url": "javascript:alert(1)"}).status_code == 422
    assert any(x["id"] == b["id"] for x in httpx.get(f"{BASE}/content/homepage").json()["banners"])
    assert cc.put("/admin/content/featured", json={"product_ids": [str(ObjectId())]}).status_code == 422
    assert cc.delete(f"/admin/content/banners/{b['id']}").status_code == 200


def teardown_module():
    from tests.test_phase03_vendors import CREATED  # users made via imported verified_client() (phase03's own cleanup fixture does not run here)
    ids = [u["_id"] for u in mongo.users.find({"email": {"$in": MADE + CREATED}})]
    for coll, f in (("sessions", "user_id"), ("support_tickets", "customer_id"), ("notifications", "user_id"), ("auth_tokens", "user_id")):
        mongo[coll].delete_many({f: {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    mongo.admin_invites.delete_many({"email": {"$in": MADE}})
    mongo.content_banners.delete_many({"title": {"$regex": "^TEST"}})
