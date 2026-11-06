# Phase 14 T1 extended: admin migration guards (MFA, confirm text, approval gate), activation edge cases, redirect resolve normalisation
import uuid
from datetime import timedelta

import httpx

from afrovending.core.models import utcnow
from afrovending.core.security import hash_token
from tests.test_phase03_vendors import ADMIN, BASE, admin_client, mongo
from tests.test_phase06_cart import account

MADE = []


def teardown_module():
    mongo.users.delete_many({"_id": {"$in": MADE}})
    for c in ("auth_tokens", "sessions", "carts", "notifications"):
        mongo[c].delete_many({"user_id": {"$in": MADE}})
    mongo.legacy_redirects.delete_many({"source": "t14x"})


def setup_function():
    mongo.rate_limits.delete_many({"key": {"$regex": "^activate"}})  # per-IP activation limits (10/h) are shared by all test runs


def _approval():
    return (mongo.platform_settings.find_one({"key": "migration.activation"}) or {}).get("value", {}).get("approved", False)


# --- admin migration endpoints ---
def test_report_requires_mfa_and_super_admin():
    c = httpx.Client(base_url=BASE, timeout=30)
    assert c.post("/auth/login", json=ADMIN).status_code == 200
    r = c.get("/admin/migration/report")  # signed in, MFA not verified
    assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required", r.text
    cust, email = account()
    MADE.append(mongo.users.find_one({"email": email})["_id"])
    assert cust.get("/admin/migration/report").status_code == 403
    assert cust.post("/admin/migration/activation-batch", json={"batch_size": 1}).status_code == 403
    assert cust.put("/admin/migration/activation-approval", json={"approved": False}).status_code == 403
    sup = admin_client()
    rep = sup.get("/admin/migration/report").json()
    for k in ("accounts", "activation_pending", "activation_emails_sent", "activated", "legacy_orders", "redirects", "approval"):
        assert k in rep, k
    assert "_id" not in str(rep.get("last_import") or {})


def test_approval_confirm_text_and_batch_409():
    assert _approval() is False
    sup = admin_client()
    for bad in ("", "send activation emails", "SEND ACTIVATION EMAIL", " SEND ACTIVATION EMAILS"):
        r = sup.put("/admin/migration/activation-approval", json={"approved": True, "confirm": bad})
        assert r.status_code == 422, (bad, r.status_code)
    assert _approval() is False
    r = sup.post("/admin/migration/activation-batch", json={"batch_size": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_approved"
    assert sup.post("/admin/migration/activation-batch", json={"batch_size": 0}).status_code == 422
    assert sup.post("/admin/migration/activation-batch", json={"batch_size": 201}).status_code == 422
    assert _approval() is False


# --- activation edge cases ---
def _migrated(**kw):
    uid = mongo.users.insert_one({"email": f"t14x-{uuid.uuid4().hex[:8]}@example.com", "name": "TEST14X", "roles": ["customer"], "status": "active",
                                  "password_hash": None, "auth_providers": [], "email_verified_at": None, "created_at": utcnow(), "updated_at": utcnow(),
                                  "migration": {"source": "legacy_afrovending", "legacy_ids": {}, "activation_required": True}, **kw}).inserted_id
    MADE.append(uid)
    return uid


def _tok(uid, purpose="activate_account"):
    raw = uuid.uuid4().hex * 2
    mongo.auth_tokens.insert_one({"user_id": uid, "purpose": purpose, "token_hash": hash_token(raw), "created_at": utcnow(),
                                  "expires_at": utcnow() + timedelta(hours=24), "used_at": None})
    return raw


def test_reset_token_cannot_activate_and_raw_token_not_stored():
    uid = _migrated()
    raw = _tok(uid, purpose="reset_password")
    r = httpx.post(f"{BASE}/auth/activation/complete", json={"token": raw, "password": "NewPassw0rd!x"})
    assert r.status_code == 400
    assert mongo.users.find_one({"_id": uid})["password_hash"] is None


def test_request_for_normal_or_suspended_account_issues_no_token():
    cust, email = account()
    u = mongo.users.find_one({"email": email})
    MADE.append(u["_id"])
    sus = _migrated(status="suspended")
    se = mongo.users.find_one({"_id": sus})["email"]
    a = httpx.post(f"{BASE}/auth/activation/request", json={"email": email}).json()
    b = httpx.post(f"{BASE}/auth/activation/request", json={"email": se}).json()
    assert a == b
    assert mongo.auth_tokens.count_documents({"user_id": {"$in": [u["_id"], sus]}, "purpose": "activate_account"}) == 0
    raw = _tok(sus)
    r = httpx.post(f"{BASE}/auth/activation/complete", json={"token": raw, "password": "NewPassw0rd!x"})
    print("suspended activation:", r.status_code, r.text[:200], mongo.users.find_one({"_id": sus})["status"])
    assert r.status_code == 400 and mongo.users.find_one({"_id": sus})["status"] == "suspended"
    assert mongo.users.find_one({"_id": sus})["password_hash"] is None
    assert httpx.post(f"{BASE}/auth/activation/complete", json={"token": "short", "password": "NewPassw0rd!x"}).status_code == 400


def test_new_request_supersedes_old_token():
    uid = _migrated()
    email = mongo.users.find_one({"_id": uid})["email"]
    old = _tok(uid)
    assert httpx.post(f"{BASE}/auth/activation/request", json={"email": email.upper()}).status_code == 200
    r = httpx.post(f"{BASE}/auth/activation/complete", json={"token": old, "password": "NewPassw0rd!x"})
    assert r.status_code == 400, "older activation token should be superseded by a new request"


def test_redirect_resolve_normalisation():
    mongo.legacy_redirects.insert_one({"from_path": "/product/t14x-old", "to_path": "/shop", "status": 301, "source": "t14x"})
    for p in ("/product/t14x-old", "product/t14x-old", "/product/t14x-old/", "/product/t14x-old?ref=1"):
        r = httpx.get(f"{BASE}/redirects/resolve", params={"path": p})
        assert r.status_code == 200 and r.json()["to"] == "/shop", p
    assert httpx.get(f"{BASE}/redirects/resolve", params={"path": "/product-tag/Palm_Oil"}).status_code == 404
    assert httpx.get(f"{BASE}/redirects/resolve", params={"path": "/about-us"}).status_code in (200, 404)
