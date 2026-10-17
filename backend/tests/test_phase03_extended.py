# Phase 03 vendor onboarding - extended edge cases (re-apply, slug sync, doc access, files, store states)
import uuid

import httpx
from bson import ObjectId

from tests.test_phase03_vendors import BASE, PNG, admin_client, application, cleanup, mongo, submit, verified_client  # noqa: F401


def _approve(adm, app_id):
    return adm.post(f"/admin/vendor-applications/{app_id}/decision", json={"decision": "approve"})


# Unverified user cannot save an application
def test_unverified_user_cannot_apply():
    c = httpx.Client(base_url=BASE, timeout=60)
    mongo.rate_limits.delete_many({"key": {"$regex": "^register:"}})
    email = f"delivered+u{uuid.uuid4().hex[:8]}@resend.dev"
    assert c.post("/auth/register", json={"name": "TEST_Unv", "email": email, "password": "TestPass12345"}).status_code == 201
    r = c.put("/vendor/application", json=application(f"test-{uuid.uuid4().hex[:6]}"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_unverified" if "error" in r.json() else r.status_code == 403


# Validation: reserved slug, bad category, short description, unknown file
def test_application_validation():
    c = verified_client()
    assert c.put("/vendor/application", json=application("admin")).status_code == 422
    assert c.put("/vendor/application", json={**application("test-ok-1"), "categories": ["weapons"]}).status_code == 422
    assert c.put("/vendor/application", json={**application("test-ok-1"), "description": "short"}).status_code == 422
    assert c.put("/vendor/application", json={**application("test-ok-1"), "logo_file_id": str(ObjectId())}).status_code == 422
    assert c.put("/vendor/application", json=application("Bad Slug!")).status_code == 422
    # submit without draft
    c2 = verified_client()
    assert c2.post("/vendor/application/submit", json={"accept_policy": True, "policy_version": "x"}).status_code == 409


# Double approve must not create a second vendor
def test_double_approve_conflict():
    c, adm = verified_client(), admin_client()
    app = submit(c, f"test-{uuid.uuid4().hex[:6]}")
    assert _approve(adm, app["id"]).status_code == 200
    assert _approve(adm, app["id"]).status_code == 409
    assert mongo.vendors.count_documents({"application_id": ObjectId(app["id"])}) == 1


# File upload: wrong type rejected, verification doc not publicly readable, non-admin cannot download
def test_files_privacy():
    c = verified_client()
    r = c.post("/files", data={"purpose": "logo"}, files={"file": ("a.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 422
    r = c.post("/files", data={"purpose": "logo"}, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 201 and r.json()["url"]
    assert httpx.get(f"{BASE}/files/{r.json()['id']}").status_code == 200
    d = c.post("/files", data={"purpose": "verification_doc"}, files={"file": ("id.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert d.status_code == 201 and d.json()["url"] is None
    doc_id = d.json()["id"]
    assert httpx.get(f"{BASE}/files/{doc_id}").status_code == 404
    assert c.get(f"/admin/vendor-documents/{doc_id}").status_code == 403
    assert httpx.get(f"{BASE}/admin/vendor-documents/{doc_id}").status_code == 401
    adm = admin_client()
    r = adm.get(f"/admin/vendor-documents/{doc_id}")
    assert r.status_code == 200 and "attachment" in r.headers.get("content-disposition", "")


# Changing store slug: old URL 404, new URL works, admin vendors list reflects new slug
def test_store_slug_change_syncs():
    slug = f"test-{uuid.uuid4().hex[:6]}"
    c, adm = verified_client(), admin_client()
    app = submit(c, slug)
    assert _approve(adm, app["id"]).status_code == 200
    new = slug + "-n"
    r = c.patch("/vendor/store", json={"display_name": "TEST New", "tagline": "t", "description": "d", "slug": new})
    assert r.status_code == 200 and r.json()["store"]["slug"] == new
    c.post("/vendor/store/publish")
    assert httpx.get(f"{BASE}/stores/{new}").status_code == 200
    assert httpx.get(f"{BASE}/stores/{slug}").status_code == 404
    v = [x for x in adm.get("/admin/vendors").json()["data"] if x["application_id"] == app["id"]][0]
    assert v["slug"] == new, f"admin vendor list still shows old slug {v['slug']}"


# Reactivated vendor: store paused -> publish again; suspended vendor cannot edit
def test_suspend_reactivate_store_state():
    slug = f"test-{uuid.uuid4().hex[:6]}"
    c, adm = verified_client(), admin_client()
    app = submit(c, slug)
    _approve(adm, app["id"])
    c.post("/vendor/store/publish")
    vid = mongo.vendors.find_one({"application_id": ObjectId(app["id"])})["_id"]
    assert adm.post(f"/admin/vendors/{vid}/suspend", json={"reason": "x"}).status_code == 422  # reason too short
    assert adm.post(f"/admin/vendors/{vid}/suspend", json={"reason": "TEST reason"}).status_code == 200
    assert c.get("/vendor/store").json()["store"]["status"] == "paused"
    assert c.patch("/vendor/store", json={"display_name": "TEST X", "slug": slug}).status_code == 403
    assert slug not in [s["slug"] for s in httpx.get(f"{BASE}/stores").json()["data"]]
    assert adm.post(f"/admin/vendors/{vid}/reactivate", json={"reason": "TEST ok"}).status_code == 200
    assert c.post("/vendor/store/publish").json()["store"]["status"] == "published"
    assert httpx.get(f"{BASE}/stores/{slug}").status_code == 200


# Rejected applicant should be able to re-apply (business expectation check)
def test_rejected_can_reapply():
    c, adm = verified_client(), admin_client()
    app = submit(c, f"test-{uuid.uuid4().hex[:6]}")
    assert adm.post(f"/admin/vendor-applications/{app['id']}/decision", json={"decision": "reject", "note": "TEST not a fit"}).status_code == 200
    r = c.put("/vendor/application", json=application(f"test-{uuid.uuid4().hex[:6]}"))
    assert r.status_code == 200, f"rejected applicant cannot re-apply: {r.status_code} {r.text}"
