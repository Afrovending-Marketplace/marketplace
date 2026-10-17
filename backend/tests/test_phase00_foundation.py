import os

import httpx
import pytest

from afrovending.core.roles import Role
from afrovending.schema.entities import ENTITIES, ENTITIES_BY_COLLECTION

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001")

REQUIRED_ENTITIES = {
    "Users", "Roles", "Vendors", "VendorApplications", "VendorVerification", "VendorStores", "Categories",
    "Products", "ProductVariants", "ProductImages", "Inventory", "Carts", "CartItems", "Orders", "OrderItems",
    "VendorOrders", "Payments", "Refunds", "CommissionLedger", "Payouts", "ShippingMethods", "Shipments",
    "Returns", "Coupons", "Reviews", "Notifications", "SupportTickets", "AuditLogs", "PlatformSettings",
}


class TestEntityRegistry:
    def test_all_required_entities_defined(self):
        assert REQUIRED_ENTITIES <= {e.name for e in ENTITIES}

    def test_collections_unique(self):
        assert len(ENTITIES_BY_COLLECTION) == len(ENTITIES)

    def test_relations_reference_known_collections(self):
        for e in ENTITIES:
            for rel in e.relations:
                assert rel.split("->")[1].strip() in ENTITIES_BY_COLLECTION, f"{e.name}: {rel}"

    def test_index_names_unique_per_entity_and_phase_range(self):
        for e in ENTITIES:
            names = [i.name for i in e.indexes]
            assert len(names) == len(set(names)), e.name
            assert 0 <= e.phase <= 14

    def test_all_roles_present(self):
        assert {r.value for r in Role} == {
            "guest", "customer", "vendor_applicant", "vendor", "vendor_team_member",
            "support_admin", "marketplace_admin", "super_admin",
        }


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        yield c


class TestSystemApi:
    def test_health(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok" and body["database"] == "ok" and body["phase"] >= 0
        assert r.headers.get("x-request-id")

    def test_request_id_echoed(self, client):
        r = client.get("/api/v1/health", headers={"X-Request-ID": "test-req-12345"})
        assert r.headers["x-request-id"] == "test-req-12345"

    def test_platform_public_settings_only(self, client):
        settings = client.get("/api/v1/platform").json()["settings"]
        assert settings["marketplace.tagline"] == "From Culture to Commerce"
        assert "commission.default_rate_bps" not in settings

    def test_schema_contract_and_migration(self, client):
        body = client.get("/api/v1/system/schema").json()
        assert {e["name"] for e in body["entities"]} >= REQUIRED_ENTITIES
        assert any(m["version"] == "0001" for m in body["migrations"])

    def test_not_found_error_envelope(self, client):
        r = client.get("/api/v1/does-not-exist")
        assert r.status_code == 404
        err = r.json()["error"]
        assert err["code"] == "not_found" and err["request_id"]

    def test_method_not_allowed_envelope(self, client):
        r = client.post("/api/v1/health")
        assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"
