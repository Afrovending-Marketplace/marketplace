# ruff: noqa: F811
# Iteration 34 (T1): Attorney Feedback Tracker — create change items from an attorney record (RBAC, validation, version link, audit),
# list with per-status counts, status updates (content_admin vs super_admin rules, notes, history, audit),
# approval blocked (409 attorney_changes_open) while items are open, launch checklist policy_ detail, pack #1 untouched.
# Run serially: pytest tests/test_phase17_t1_feedback_tracker.py -n 0
import os
import subprocess
from datetime import date

import pytest
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from tests.test_phase03_vendors import _ENV, admin_client, mongo  # noqa: E402
from tests.test_phase06_cart import PREFIX, account  # noqa: E402,F401
from tests.test_phase10_admin import MADE as ADMINS_MADE, admin_with  # noqa: E402

PACK1 = ObjectId("6af273a06c693e2488c1ac51")
DUMP = "/tmp/polbak_t34"
S = {"packs": [], "changes": [], "cust_emails": []}
BEFORE = sorted((d["slug"], d["version"], d["status"], len(d.get("history", [])), d["body"]) for d in mongo.policy_versions.find())
PACK1_BEFORE = mongo.review_packs.find_one({"_id": PACK1}, {"files": 0})


def setup_module():
    subprocess.run(["mongodump", f"--uri={_ENV['MONGO_URL']}", f"--db={_ENV['DB_NAME']}", "--collection=policy_versions", f"--out={DUMP}"], check=True,
                   capture_output=True)


def teardown_module():
    mongo.legal_change_requests.delete_many({"_id": {"$in": S["changes"]}})
    mongo.legal_change_requests.delete_many({"pack_id": {"$in": S["packs"]}})
    mongo.review_packs.delete_many({"_id": {"$in": S["packs"]}})
    mongo.policy_versions.delete_many({})
    subprocess.run(["mongorestore", f"--uri={_ENV['MONGO_URL']}", f"--nsInclude={_ENV['DB_NAME']}.policy_versions", DUMP], check=True, capture_output=True)
    mongo.launch_checklist.delete_many({"key": {"$regex": "^(policy_|legal_review_pack)"}})
    ids = [u["_id"] for u in mongo.users.find({"email": {"$in": ADMINS_MADE}})]
    for coll in ("sessions", "auth_tokens", "notifications"):
        mongo[coll].delete_many({"user_id": {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    mongo.admin_invites.delete_many({"email": {"$in": ADMINS_MADE}})
    tu = [u["_id"] for u in mongo.users.find({"email": {"$in": S["cust_emails"]}})]
    for coll in ("sessions", "auth_tokens", "notifications"):
        mongo[coll].delete_many({"user_id": {"$in": tu}})
    mongo.users.delete_many({"_id": {"$in": tu}})


@pytest.fixture(scope="module")
def sup():
    return admin_client()


@pytest.fixture(scope="module")
def content():
    return admin_with("content_admin")[0]


@pytest.fixture(scope="module")
def cust():
    c, email = account()
    S["cust_emails"].append(email)
    return c


def base(pid, rid):
    return f"/admin/policies/review-pack/{pid}/attorney-review/{rid}/changes"


def test_01_setup_test_pack(sup):
    r = sup.post("/admin/policies/review-pack", timeout=180)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    S["packs"].append(ObjectId(pid))
    S["pid"], S["pno"] = pid, r.json()["pack_number"]
    assert sup.post(f"/admin/policies/review-pack/{pid}/approve-sharing", json={"confirm": True, "acknowledge_not_legal_approval": True}).status_code == 200
    r = sup.post(f"/admin/policies/review-pack/{pid}/attorney-review",
                 data={"reviewer_name": "TEST Counsel", "reviewer_firm": "TEST LLP", "received_on": date.today().isoformat(),
                       "requested_changes": "Clarify governing law\nAdd cookie consent wording\nTighten refund window"})
    assert r.status_code == 201, r.text
    S["rid"] = r.json()["attorney_records"][-1]["id"]


def test_02_create_rbac_validation(sup, content, cust):
    pid, rid = S["pid"], S["rid"]
    ok = {"items": [{"policy_slug": "terms", "clause": "§12", "description": "Clarify governing law"}]}
    assert content.post(base(pid, rid), json=ok).status_code == 403
    assert cust.post(base(pid, rid), json=ok).status_code == 403
    r = sup.post(base(pid, "0" * 24), json=ok)
    assert r.status_code == 404, r.text
    assert sup.post(base("0" * 24, rid), json=ok).status_code == 404
    r = sup.post(base(pid, rid), json={"items": [{"policy_slug": "nope", "description": "Clarify governing law"}]})
    assert r.status_code == 404, r.text
    # mixed valid + invalid slug must not insert anything
    n0 = mongo.legal_change_requests.count_documents({"pack_id": ObjectId(pid)})
    r = sup.post(base(pid, rid), json={"items": [ok["items"][0], {"policy_slug": "bogus", "description": "abcdef"}]})
    assert r.status_code == 404 and mongo.legal_change_requests.count_documents({"pack_id": ObjectId(pid)}) == n0
    assert sup.post(base(pid, rid), json={"items": [{"policy_slug": "terms", "description": "abcd"}]}).status_code == 422
    assert sup.post(base(pid, rid), json={"items": []}).status_code == 422


def test_03_create_items(sup):
    pid, rid = S["pid"], S["rid"]
    body = {"items": [{"policy_slug": "terms", "clause": "§12", "description": "Clarify governing law"},
                      {"policy_slug": "terms", "clause": "§3", "description": "Define marketplace role"},
                      {"policy_slug": "cookies", "clause": "", "description": "Add cookie consent wording"}]}
    r = sup.post(base(pid, rid), json=body)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert len(data) == 3
    S["changes"] += [ObjectId(x["id"]) for x in data]
    S["terms_ids"] = [x["id"] for x in data[:2]]
    S["cookie_id"] = data[2]["id"]
    tv = mongo.policy_versions.find_one({"slug": "terms", "status": "pending_review"})
    x = data[0]
    assert x["status"] == "open" and x["version_id"] == str(tv["_id"]) and x["version"] == tv["version"]
    assert x["pack_number"] == S["pno"] and x["reviewer_name"] == "TEST Counsel" and x["policy_slug"] == "terms" and x["clause"] == "§12"
    assert len(x["history"]) == 1 and x["history"][0]["status"] == "open"
    assert "_id" not in x
    assert mongo.audit_logs.find_one({"action": "policy.attorney_changes_created", "entity_id": {"$in": [pid, ObjectId(pid)]}})


def test_04_list_counts(sup, content, cust):
    r = sup.get("/admin/policies/changes", params={"slug": "terms"})
    assert r.status_code == 200, r.text
    j = r.json()
    ids = {x["id"] for x in j["data"]}
    assert set(S["terms_ids"]) <= ids and S["cookie_id"] not in ids
    assert set(j["counts"]) == {"open", "in_progress", "done", "wont_do"} and j["counts"]["open"] >= 2
    assert content.get("/admin/policies/changes").status_code == 200
    assert cust.get("/admin/policies/changes").status_code == 403
    assert sup.get("/admin/policies/changes", params={"slug": "nope"}).status_code == 404


def test_05_update_rules(sup, content):
    a, b = S["terms_ids"]
    u = lambda c, i, **kw: c.put(f"/admin/policies/changes/{i}", json=kw)  # noqa: E731
    r = u(content, a, status="in_progress")
    assert r.status_code == 200 and r.json()["status"] == "in_progress", r.text
    assert u(content, a, status="done").status_code == 422
    assert u(content, a, status="done", note="abc").status_code == 422
    assert u(content, a, status="wont_do", note="Not needed").status_code == 403
    r = u(content, a, status="done", note="Updated clause 12 text")
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["resolution_note"] == "Updated clause 12 text"
    assert u(content, a, status="open").status_code == 403  # reopen super only
    r = u(sup, a, status="open", note="Reopened")
    assert r.status_code == 200 and r.json()["status"] == "open"
    assert len(r.json()["history"]) == 4
    assert u(sup, b, status="wont_do").status_code == 422
    r = u(sup, b, status="wont_do", note="Out of scope for v1")
    assert r.status_code == 200 and r.json()["status"] == "wont_do"
    assert sup.put(f"/admin/policies/changes/{'0' * 24}", json={"status": "in_progress"}).status_code == 404
    assert sup.put(f"/admin/policies/changes/{a}", json={"status": "bogus"}).status_code == 422
    for act in ("policy.attorney_change_in_progress", "policy.attorney_change_done", "policy.attorney_change_open", "policy.attorney_change_wont_do"):
        assert mongo.audit_logs.find_one({"action": act, "entity_id": {"$in": [a, b, ObjectId(a), ObjectId(b)]}}), act


def test_06_content_admin_cannot_reopen_via_in_progress(sup, content):
    """wont_do -> in_progress is not an allowed transition (reopen is Super Admin only)."""
    b = S["terms_ids"][1]
    r = content.put(f"/admin/policies/changes/{b}", json={"status": "in_progress"})
    assert r.status_code == 409, r.text
    r = content.put(f"/admin/policies/changes/{b}", json={"status": "open"})
    assert r.status_code == 403, r.text


def approve_body():
    t = date.today().isoformat()
    return {"legal_review_confirmed": True, "reviewer_name": "TEST Counsel", "reviewer_firm": "TEST LLP", "review_date": t, "review_notes": "TEST",
            "classification": "material", "change_summary": "TEST first version", "effective_date": t}


def test_07_launch_detail(sup):
    r = sup.post("/admin/launch/checklist/policy_terms/check")
    assert r.status_code == 200, r.text
    item = lambda j, k: next(i for i in j["items"] if i["key"] == k) if "items" in j else j  # noqa: E731
    assert "1 attorney-requested change(s) open" in item(r.json(), "policy_terms")["evidence"], r.json()
    r = sup.post("/admin/launch/checklist/policy_privacy/check")
    assert "attorney-requested" not in item(r.json(), "policy_privacy")["evidence"]
    r = sup.post("/admin/launch/checklist/policy_cookies/check")
    assert "1 attorney-requested change(s) open" in item(r.json(), "policy_cookies")["evidence"]


def test_08_approve_blocked_then_allowed(sup):
    a = S["terms_ids"][0]
    vid = str(mongo.policy_versions.find_one({"slug": "terms", "status": "pending_review"})["_id"])
    r = sup.post(f"/admin/policies/versions/{vid}/approve", json=approve_body())
    assert r.status_code == 409 and r.json()["error"]["code"] == "attorney_changes_open", r.text
    assert sup.put(f"/admin/policies/changes/{a}", json={"status": "in_progress"}).status_code == 200
    r = sup.post(f"/admin/policies/versions/{vid}/approve", json=approve_body())
    assert r.status_code == 409, r.text
    assert sup.put(f"/admin/policies/changes/{a}", json={"status": "done", "note": "Resolved in v1"}).status_code == 200
    r = sup.post(f"/admin/policies/versions/{vid}/approve", json=approve_body())
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    # cookies still blocked
    cv = str(mongo.policy_versions.find_one({"slug": "cookies", "status": "pending_review"})["_id"])
    r = sup.post(f"/admin/policies/versions/{cv}/approve", json=approve_body())
    assert r.status_code == 409


def test_09_pack1_untouched_and_downloads(sup):
    p = mongo.review_packs.find_one({"_id": PACK1}, {"files": 0})
    assert p["external_sharing_approved"] is True and p.get("attorney_records", []) == PACK1_BEFORE.get("attorney_records", [])
    assert mongo.legal_change_requests.count_documents({"pack_id": PACK1}) == 0
    for fmt, magic in (("docx", b"PK"), ("pdf", b"%PDF")):
        r = sup.get(f"/admin/policies/review-pack/{PACK1}/download", params={"format": fmt})
        assert r.status_code == 200 and r.content[:len(magic)] == magic, (fmt, r.status_code)


def test_99_restore_check():
    teardown_module()
    after = sorted((d["slug"], d["version"], d["status"], len(d.get("history", [])), d["body"]) for d in mongo.policy_versions.find())
    assert after == BEFORE
    assert mongo.legal_change_requests.count_documents({"_id": {"$in": S["changes"]}}) == 0
