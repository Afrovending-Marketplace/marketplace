# Phase 00 public-URL API regression: health, platform, schema, error envelope, request-id
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", os.environ.get("API_BASE_URL", "http://localhost:8001")).rstrip("/")


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# Health + request id
class TestHealth:
    def test_health_ok(self, s):
        r = s.get(f"{BASE_URL}/api/v1/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok" and d["database"] == "ok"
        assert d["phase"] in (0, "0", "00")
        assert r.headers.get("X-Request-ID")

    def test_request_id_echo(self, s):
        rid = "TEST-req-12345678"
        r = s.get(f"{BASE_URL}/api/v1/health", headers={"X-Request-ID": rid})
        assert r.headers.get("X-Request-ID") == rid

    def test_invalid_request_id_replaced(self, s):
        r = s.get(f"{BASE_URL}/api/v1/health", headers={"X-Request-ID": "bad id!"})
        assert r.headers.get("X-Request-ID") != "bad id!"
        assert len(r.headers.get("X-Request-ID")) >= 8

    def test_api_root(self, s):
        r = s.get(f"{BASE_URL}/api")
        assert r.status_code == 200 and "v1" in r.json()["versions"]


# Platform public settings
class TestPlatform:
    def test_public_only(self, s):
        r = s.get(f"{BASE_URL}/api/v1/platform")
        assert r.status_code == 200
        st = r.json()["settings"]
        assert "marketplace.tagline" in st
        val = st["marketplace.tagline"]
        assert "From Culture to Commerce" in (val if isinstance(val, str) else str(val))
        assert "commission.default_rate_bps" not in st
        assert "commission.default_rate_bps" not in r.text


# Schema contract
class TestSchema:
    def test_schema(self, s):
        r = s.get(f"{BASE_URL}/api/v1/system/schema")
        assert r.status_code == 200
        d = r.json()
        names = {e["name"] for e in d["entities"]}
        assert len(d["entities"]) >= 29
        for n in ["Users", "Vendors", "Products", "Orders", "CommissionLedger", "AuditLogs", "PlatformSettings"]:
            assert n in names
        assert len(d["roles"]) == 8
        assert any(m["version"] == "0001" for m in d["migrations"])
        assert "\"_id\"" not in r.text


# Error envelope
class TestErrors:
    def _env(self, r, code):
        e = r.json()["error"]
        assert e["code"] == code
        assert isinstance(e["message"], str)
        assert "details" in e
        assert e["request_id"] == r.headers.get("X-Request-ID")

    def test_404(self, s):
        r = s.get(f"{BASE_URL}/api/v1/nope")
        assert r.status_code == 404
        self._env(r, "not_found")

    def test_405(self, s):
        r = s.post(f"{BASE_URL}/api/v1/health")
        assert r.status_code == 405
        self._env(r, "method_not_allowed")
