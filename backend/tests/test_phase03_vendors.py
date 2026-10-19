import io
import os
import uuid

import httpx
import pytest
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient

_ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
BASE = os.environ.get("API_BASE_URL", _ENV["FRONTEND_URL"]) + "/api/v1"
ADMIN = {"email": _ENV["ADMIN_EMAIL"], "password": _ENV["ADMIN_PASSWORD"]}
mongo = MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    mongo.rate_limits.delete_many({})
    yield
    ids = [u["_id"] for u in mongo.users.find({"email": {"$in": CREATED}})]  # only this worker's users (xdist-safe)
    vendor_ids = [v["_id"] for v in mongo.vendors.find({"owner_user_id": {"$in": ids}})]
    mongo.vendor_stores.delete_many({"vendor_id": {"$in": vendor_ids}})
    mongo.vendors.delete_many({"_id": {"$in": vendor_ids}})
    for coll, field in (("vendor_applications", "user_id"), ("vendor_policy_acceptances", "user_id"), ("files", "owner_user_id"),
                        ("sessions", "user_id"), ("auth_tokens", "user_id")):
        mongo[coll].delete_many({field: {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    CREATED.clear()


CREATED: list = []


def verified_client():
    c = httpx.Client(base_url=BASE, timeout=60)
    mongo.rate_limits.delete_many({"key": {"$regex": "^register:"}})
    email = f"delivered+v{uuid.uuid4().hex[:8]}@resend.dev"
    r = c.post("/auth/register", json={"name": "TEST_Vendor", "email": email, "password": "TestPass12345"})
    assert r.status_code == 201, r.text
    CREATED.append(email)
    mongo.users.update_one({"email": email}, {"$set": {"email_verified_at": mongo.users.find_one({"email": email})["created_at"], "status": "active"}})
    return c


def application(slug):
    return {"business_name": "TEST Biz", "contact_email": "biz@example.com", "country": "us", "city": "Boston",
            "categories": ["fashion"], "description": "We make handcrafted textiles and accessories for everyone.", "desired_slug": slug}


def admin_client():
    c = httpx.Client(base_url=BASE, timeout=60)
    assert c.post("/auth/login", json=ADMIN).status_code == 200
    return c


def submit(c, slug):
    assert c.put("/vendor/application", json=application(slug)).status_code == 200
    policy = c.get("/vendor/policy").json()["version"]
    assert c.post("/vendor/application/submit", json={"accept_policy": False, "policy_version": policy}).status_code == 422
    r = c.post("/vendor/application/submit", json={"accept_policy": True, "policy_version": policy})
    assert r.status_code == 200
    return r.json()["application"]


def test_full_onboarding_and_store_publish():
    slug = f"test-{uuid.uuid4().hex[:6]}"
    c, adm = verified_client(), admin_client()
    app = submit(c, slug)
    assert app["status"] == "submitted" and app["policy_version"]
    assert mongo.vendor_policy_acceptances.find_one({"application_id": ObjectId(app["id"])})["accepted_at"]
    # applicant cannot publish before approval
    assert c.post("/vendor/store/publish").status_code == 403
    assert c.put("/vendor/application", json=application(slug)).status_code == 409
    r = adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "approve"})
    assert r.status_code == 200 and r.json()["application"]["status"] == "approved"
    assert "vendor" in c.get("/auth/me").json()["user"]["roles"]
    assert httpx.get(f"{BASE}/stores/{slug}").status_code == 404  # draft not public
    assert c.post("/vendor/store/publish").json()["store"]["status"] == "published"
    assert httpx.get(f"{BASE}/stores/{slug}").json()["display_name"] == "TEST Biz"
    vendor = mongo.vendors.find_one({"slug": slug})
    assert adm.post(f"/admin/vendors/{vendor['_id']}/suspend", json={"reason": "TEST policy check"}).status_code == 200
    assert httpx.get(f"{BASE}/stores/{slug}").status_code == 404
    assert c.post("/vendor/store/publish").status_code == 403
    assert adm.post(f"/admin/vendors/{vendor['_id']}/reactivate", json={"reason": "TEST resolved"}).status_code == 200
    assert c.post("/vendor/store/publish").status_code == 200


def test_request_info_reject_and_slug_uniqueness():
    slug = f"test-{uuid.uuid4().hex[:6]}"
    a, b, adm = verified_client(), verified_client(), admin_client()
    app = submit(a, slug)
    assert b.put("/vendor/application", json=application(slug)).status_code == 409
    assert adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "reject"}).status_code == 422
    r = adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "request_info", "note": "Please add ID", "require_documents": True})
    assert r.json()["application"]["status"] == "changes_requested"
    policy = a.get("/vendor/policy").json()["version"]
    assert a.post("/vendor/application/submit", json={"accept_policy": True, "policy_version": policy}).status_code == 422
    doc = a.post("/files", data={"purpose": "verification_doc"}, files={"file": ("id.png", io.BytesIO(PNG), "image/png")})
    assert doc.status_code == 201 and doc.json()["url"] is None
    doc_id = doc.json()["id"]
    assert a.post("/vendor/application/submit", json={"accept_policy": True, "policy_version": policy}).status_code == 200
    # documents: not public, not for other users or the owner via admin route; admin can download
    assert httpx.get(f"{BASE}/files/{doc_id}").status_code == 404
    assert a.get(f"/admin/vendor-documents/{doc_id}").status_code == 403
    assert b.get(f"/admin/vendor-documents/{doc_id}").status_code == 403
    assert adm.get(f"/admin/vendor-documents/{doc_id}").status_code == 200
    r = adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "reject", "note": "TEST not eligible"})
    assert r.json()["application"]["status"] == "rejected"


def test_vendors_isolated_and_non_admin_blocked():
    a, b = verified_client(), verified_client()
    assert a.get("/vendor/store").status_code == 403
    assert a.get("/admin/vendor-applications").status_code == 403
    submit(a, f"test-{uuid.uuid4().hex[:6]}")
    assert b.get("/vendor/application").json()["application"] is None
    logo = a.post("/files", data={"purpose": "logo"}, files={"file": ("l.png", io.BytesIO(PNG), "image/png")}).json()
    bad = {**application(f"test-{uuid.uuid4().hex[:6]}"), "logo_file_id": logo["id"]}
    assert b.put("/vendor/application", json=bad).status_code == 422  # cannot use another user's file
