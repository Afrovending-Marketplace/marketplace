# Phase 02 extended regression: cookies, CORS, lockout bypass, addresses, privacy, profile, contact validation
import os
import uuid

import httpx
import pytest
from dotenv import dotenv_values
from pymongo import MongoClient

_BENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
_FENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env"))
SITE = _FENV["REACT_APP_BACKEND_URL"].rstrip("/")
BASE = SITE + "/api/v1"
mongo = MongoClient(_BENV["MONGO_URL"])[_BENV["DB_NAME"]]
PW = "TestPass12345"


def _email():
    return f"delivered+ext{uuid.uuid4().hex[:8]}@resend.dev"


def _client(**kw):
    return httpx.Client(base_url=BASE, timeout=30, **kw)


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    mongo.rate_limits.delete_many({})
    yield
    ids = [u["_id"] for u in mongo.users.find({"name": {"$regex": "^TEST_"}})]
    for coll in ("addresses", "sessions", "auth_tokens", "privacy_requests"):
        mongo[coll].delete_many({"user_id": {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    mongo.rate_limits.delete_many({})


def _register(c, email=None):
    mongo.rate_limits.delete_many({"key": {"$regex": "^register:"}})
    r = c.post("/auth/register", json={"name": "TEST_Ext", "email": email or _email(), "password": PW})
    assert r.status_code == 201, r.text
    return r


class TestCookiesAndHashing:
    def test_cookie_flags_and_bcrypt(self):
        with _client() as c:
            email = _email()
            r = _register(c, email)
            sc = r.headers.get_list("set-cookie")
            joined = " | ".join(sc).lower()
            assert "access_token=" in joined and "refresh_token=" in joined
            for ck in sc:
                low = ck.lower()
                assert "httponly" in low and "secure" in low and "samesite=none" in low
            doc = mongo.users.find_one({"email": email})
            assert doc["password_hash"].startswith("$2b$")
            assert doc["status"] == "pending_verification"
            assert "password_hash" not in r.json()["user"]
            assert "_id" not in r.json()["user"]

    def test_cors_credentials_explicit_origin(self):
        r = httpx.options(BASE + "/auth/login", headers={"Origin": SITE, "Access-Control-Request-Method": "POST"}, timeout=30)
        assert r.headers.get("access-control-allow-origin") == SITE
        assert r.headers.get("access-control-allow-credentials") == "true"


class TestLockout:
    def test_lockout_cannot_be_bypassed_with_x_forwarded_for(self):
        with _client() as c:
            email = _email()
            _register(c, email)
        with _client() as c:
            for i in range(5):
                c.post("/auth/login", json={"email": email, "password": "wrongpass123"})
            assert c.post("/auth/login", json={"email": email, "password": "wrongpass123"}).status_code == 429
            spoof = c.post("/auth/login", json={"email": email, "password": PW}, headers={"X-Forwarded-For": "1.2.3.4"})
            # Expected: still 429. If 200, lockout is bypassable via spoofed XFF header.
            assert spoof.status_code == 429, f"lockout bypassed with spoofed X-Forwarded-For: {spoof.status_code}"


class TestAccount:
    def test_refresh_after_logout_rejected(self):
        with _client() as c:
            _register(c)
            refresh = c.cookies.get("refresh_token")
            assert c.post("/auth/logout").status_code == 200
        with _client() as c2:
            c2.cookies.set("refresh_token", refresh, domain=httpx.URL(SITE).host)
            assert c2.post("/auth/refresh").status_code == 401

    def test_profile_update_persists(self):
        with _client() as c:
            _register(c)
            r = c.patch("/account/profile", json={"name": "TEST_Renamed", "phone": "+1 555 0100"})
            assert r.status_code == 200
            me = c.get("/auth/me").json()["user"]
            assert me["name"] == "TEST_Renamed" and me["phone"] == "+1 555 0100"
            assert c.patch("/account/profile", json={"name": ""}).status_code == 422

    def test_change_password_wrong_current(self):
        with _client() as c:
            _register(c)
            r = c.post("/auth/change-password", json={"current_password": "nopenope123", "new_password": "NewPass123456"})
            assert r.status_code == 400

    def test_address_default_switch_edit_delete(self):
        with _client() as c:
            _register(c)
            base = {"full_name": "TEST A", "line1": "1 Main", "city": "Boston", "country": "us"}
            a1 = c.post("/account/addresses", json=base).json()
            assert a1["is_default"] is True and a1["country"] == "US"
            a2 = c.post("/account/addresses", json={**base, "line1": "2 Main"}).json()
            assert a2["is_default"] is False
            r = c.patch(f"/account/addresses/{a2['id']}", json={**base, "line1": "2 Main", "is_default": True})
            assert r.status_code == 200 and r.json()["is_default"] is True
            lst = c.get("/account/addresses").json()["data"]
            assert [a["is_default"] for a in lst].count(True) == 1 and lst[0]["id"] == a2["id"]
            # edit a1 without is_default keeps it non-default
            r = c.patch(f"/account/addresses/{a1['id']}", json={**base, "city": "Cambridge"})
            assert r.json()["city"] == "Cambridge" and r.json()["is_default"] is False
            # delete default -> remaining promoted
            assert c.delete(f"/account/addresses/{a2['id']}").status_code == 200
            lst = c.get("/account/addresses").json()["data"]
            assert len(lst) == 1 and lst[0]["is_default"] is True
            assert c.delete("/account/addresses/notanid").status_code == 404
            assert c.post("/account/addresses", json={**base, "country": "USA"}).status_code == 422

    def test_privacy_duplicate_conflict(self):
        with _client() as c:
            _register(c)
            r = c.post("/account/privacy-requests", json={"request_type": "data_export"})
            assert r.status_code == 201 and r.json()["status"] == "submitted"
            assert c.post("/account/privacy-requests", json={"request_type": "data_export"}).status_code == 409
            assert c.post("/account/privacy-requests", json={"request_type": "bogus"}).status_code == 422
            assert len(c.get("/account/privacy-requests").json()["data"]) == 1

    def test_deactivate_wrong_password(self):
        with _client() as c:
            _register(c)
            assert c.post("/account/deactivate", json={"password": "wrongwrong1"}).status_code == 400
            assert c.get("/auth/me").status_code == 200


class TestContactValidation:
    def test_contact_invalid_payload_422(self):
        r = httpx.post(BASE + "/contact", json={"name": "", "email": "bad", "subject": "", "message": "short"}, timeout=30)
        assert r.status_code == 422
