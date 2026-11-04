import os
import uuid

import httpx
import pytest
from pymongo import MongoClient

from dotenv import dotenv_values

_ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
# Secure cookies require HTTPS, so default to the public preview URL.
BASE = os.environ.get("API_BASE_URL", _ENV["FRONTEND_URL"]) + "/api/v1"
ADMIN = {"email": "afrovending.online@gmail.com", "password": os.environ.get("ADMIN_PASSWORD", "r6A4E28e1ijx0ZQYf7fmYZj1!Av9")}
mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]


def _email():
    return f"delivered+test{uuid.uuid4().hex[:8]}@resend.dev"


def _client():
    return httpx.Client(base_url=BASE, timeout=30)


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    ids = [u["_id"] for u in mongo.users.find({"name": {"$regex": "^TEST2_"}})]
    for coll in ("addresses", "sessions", "auth_tokens", "privacy_requests"):
        mongo[coll].delete_many({"user_id": {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    mongo.rate_limits.delete_many({"key": {"$regex": "resend.dev"}})


def _register(c, email=None, password="TestPass12345"):
    mongo.rate_limits.delete_many({"key": {"$regex": "^register:"}})
    r = c.post("/auth/register", json={"name": "TEST2_User", "email": email or _email(), "password": password})
    assert r.status_code == 201, r.text
    return r.json()


class TestAuthFlow:
    def test_register_sets_cookies_and_sends_verification(self):
        with _client() as c:
            body = _register(c)
            assert isinstance(body["verification_email_sent"], bool)
            assert body["user"]["roles"] == ["customer"] and not body["user"]["email_verified"]
            assert c.get("/auth/me").status_code == 200
            assert mongo.users.find_one({"email": body["user"]["email"]})["password_hash"].startswith("$2b$")

    def test_duplicate_and_weak_password_rejected(self):
        with _client() as c:
            email = _email()
            _register(c, email)
            assert c.post("/auth/register", json={"name": "TEST2_x", "email": email, "password": "TestPass12345"}).status_code == 409
            assert c.post("/auth/register", json={"name": "TEST2_x", "email": _email(), "password": "short"}).status_code == 422

    def test_logout_revokes_session(self):
        with _client() as c:
            _register(c)
            access = c.cookies.get("access_token")
            c.post("/auth/logout")
            r = httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {access}"})
            assert r.status_code == 401

    def test_expired_token_rejected(self):
        import jwt
        from datetime import datetime, timedelta, timezone
        secret = os.environ.get("JWT_SECRET") or open(os.path.join(os.path.dirname(__file__), "..", ".env")).read().split('JWT_SECRET="')[1].split('"')[0]
        token = jwt.encode({"sub": "0" * 24, "sid": "0" * 24, "type": "access", "exp": datetime.now(timezone.utc) - timedelta(seconds=5)}, secret, "HS256")
        r = httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"

    def test_login_lockout_after_5_failures(self):
        with _client() as c:
            email = _email()
            _register(c, email)
            codes = [c.post("/auth/login", json={"email": email, "password": "WrongPass999"}).status_code for _ in range(6)]
            assert codes[:5] == [401] * 5 and codes[5] == 429

    def test_password_reset_flow(self):
        with _client() as c:
            email = _email()
            uid = _register(c, email)["user"]["id"]
            assert c.post("/auth/forgot-password", json={"email": email}).status_code == 200
            from bson import ObjectId
            assert mongo.auth_tokens.find_one({"user_id": ObjectId(uid), "purpose": "reset_password", "used_at": None})
            assert c.post("/auth/reset-password", json={"token": "x" * 20, "password": "NewPass12345"}).status_code == 400

    def test_verify_email_with_db_token(self):
        import secrets, hashlib
        from bson import ObjectId
        from datetime import datetime, timedelta, timezone
        with _client() as c:
            uid = _register(c)["user"]["id"]
            raw = secrets.token_urlsafe(32)
            mongo.auth_tokens.insert_one({"user_id": ObjectId(uid), "purpose": "verify_email", "token_hash": hashlib.sha256(raw.encode()).hexdigest(),
                                          "expires_at": datetime.now(timezone.utc) + timedelta(hours=1), "used_at": None})
            assert c.post("/auth/verify-email", json={"token": raw}).status_code == 200
            assert c.get("/auth/me").json()["user"]["email_verified"] is True
            assert c.post("/auth/verify-email", json={"token": raw}).status_code == 400


class TestAuthorization:
    def test_customer_blocked_from_admin(self):
        with _client() as c:
            _register(c)
            assert c.get("/admin/users").status_code == 403
            assert c.post("/admin/staff", json={"name": "TEST2_x", "email": _email(), "password": "Aa1!aaaaaaaaaaaa", "role": "super_admin"}).status_code == 403

    def test_anonymous_blocked(self):
        assert httpx.get(f"{BASE}/account/addresses").status_code == 401

    def test_admin_access(self):
        with _client() as c:
            mongo.rate_limits.delete_many({"key": {"$regex": "afrovending.online"}})
            assert c.post("/auth/login", json=ADMIN).status_code == 200
            r = c.get("/admin/users")
            assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required"  # Phase 10: admin tools need TOTP first
        from tests.test_phase03_vendors import admin_client
        c = admin_client()
        assert c.get("/admin/users").status_code == 200
        assert c.get("/admin/audit-logs").status_code == 200

    def test_addresses_are_owner_scoped(self):
        addr = {"full_name": "TEST2_A", "line1": "1 Main St", "city": "Boston", "country": "us"}
        with _client() as a, _client() as b:
            _register(a)
            _register(b)
            created = a.post("/account/addresses", json=addr).json()
            assert created["is_default"] is True and created["country"] == "US"
            assert b.delete(f"/account/addresses/{created['id']}").status_code == 404
            assert len(b.get("/account/addresses").json()["data"]) == 0

    def test_deactivate_blocks_login(self):
        with _client() as c:
            email = _email()
            _register(c, email)
            assert c.post("/account/deactivate", json={"password": "TestPass12345"}).status_code == 200
            assert c.post("/auth/login", json={"email": email, "password": "TestPass12345"}).status_code == 403

    def test_foreign_origin_rejected(self):
        r = httpx.post(f"{BASE}/auth/login", json=ADMIN, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403
