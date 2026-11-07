# T1 extended: Launch checklist (permissions, auto/manual rules, final approval, public launch record) + Founding badge edge cases
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId

from afrovending.core import founding
from tests.test_phase03_vendors import BASE, admin_client, mongo
from tests.test_phase10_admin import MADE as ADMINS_MADE, admin_with

SAVED = {}
VENDORS, USERS = [], []
AUTO = ("dns", "ssl", "stripe_test", "admin_mfa", "backup_rollback")
NON_FINAL = ("dns", "ssl", "stripe_test", "live_payments", "admin_mfa", "email_domain", "phase13_audit", "marketplace_testing", "backup_rollback")


def setup_module():
    SAVED["launch"] = mongo.platform_settings.find_one({"key": founding.LAUNCH_KEY})
    SAVED["items"] = list(mongo.launch_checklist.find({}))
    SAVED["pay"] = mongo.platform_settings.find_one({"key": "payments.config"})


def teardown_module():
    mongo.launch_checklist.delete_many({})
    if SAVED["items"]:
        mongo.launch_checklist.insert_many(SAVED["items"])
    mongo.platform_settings.delete_one({"key": founding.LAUNCH_KEY})
    if SAVED["launch"]:
        mongo.platform_settings.insert_one(SAVED["launch"])
    mongo.vendor_stores.delete_many({"vendor_id": {"$in": VENDORS}})
    mongo.vendors.delete_many({"_id": {"$in": VENDORS}})
    ids = USERS + [u["_id"] for u in mongo.users.find({"email": {"$in": ADMINS_MADE}})]
    for coll in ("sessions", "auth_tokens", "notifications"):
        mongo[coll].delete_many({"user_id": {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    mongo.admin_invites.delete_many({"email": {"$in": ADMINS_MADE}})


# --- Checklist access ---
def test_01_access_matrix():
    sup = admin_client()
    d = sup.get("/admin/launch/checklist").json()
    assert d["total"] == 10 and len(d["items"]) == 10 and d["is_super_admin"] is True
    assert [i["key"] for i in d["items"]][-1] == "final_approval"
    assert set(d["can_edit"]) == {i["key"] for i in d["items"]}
    assert all(i["status"] in ("not_started", "in_progress", "verified", "blocked") for i in d["items"])
    fin, _ = admin_with("finance_admin")
    f = fin.get("/admin/launch/checklist").json()
    assert sorted(f["can_edit"]) == ["live_payments", "stripe_test"] and f["is_super_admin"] is False
    assert fin.post("/admin/launch/checklist/dns/check").status_code == 403
    assert fin.post("/admin/launch/public-launch", json={"confirm": "RECORD PUBLIC LAUNCH"}).status_code == 403
    assert fin.get("/admin/founding-vendors").status_code == 403
    mk, _ = admin_with("marketplace_admin")
    r = mk.get("/admin/launch/checklist")
    assert r.status_code == 403
    assert mk.put("/admin/launch/checklist/email_domain", json={"status": "in_progress"}).status_code == 403
    assert mk.get("/admin/founding-vendors").status_code == 403
    assert httpx.get(f"{BASE}/admin/launch/checklist").status_code == 401
    assert httpx.post(f"{BASE}/admin/launch/public-launch", json={"confirm": "RECORD PUBLIC LAUNCH"}).status_code == 401
    assert httpx.get(f"{BASE}/admin/founding-vendors").status_code == 401


# --- Manual / auto rules ---
def test_02_manual_auto_rules():
    sup = admin_client()
    for k in AUTO:
        r = sup.put(f"/admin/launch/checklist/{k}", json={"status": "verified", "evidence": "manual evidence long enough"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "auto_only", k
    for k in ("live_payments", "email_domain", "phase13_audit", "marketplace_testing", "final_approval"):
        r = sup.post(f"/admin/launch/checklist/{k}/check")
        assert r.status_code == 422 and r.json()["error"]["code"] == "manual_only", k
    assert sup.post("/admin/launch/checklist/bogus/check").status_code == 422
    assert sup.put("/admin/launch/checklist/bogus", json={"status": "verified", "evidence": "x" * 20}).status_code == 404
    assert sup.put("/admin/launch/checklist/email_domain", json={"status": "verified", "evidence": "123456789"}).status_code == 422
    assert sup.put("/admin/launch/checklist/email_domain", json={"status": "verified", "evidence": "          x         "}).status_code == 422
    assert sup.put("/admin/launch/checklist/email_domain", json={"status": "bogus"}).status_code == 422
    # non-verified statuses need no evidence; auto items can be blocked manually
    assert sup.put("/admin/launch/checklist/ssl", json={"status": "in_progress"}).status_code == 200
    r = sup.put("/admin/launch/checklist/phase13_audit", json={"status": "verified", "evidence": "1234567890"})
    assert r.status_code == 200
    it = next(i for i in r.json()["items"] if i["key"] == "phase13_audit")
    assert it["status"] == "verified" and it["verified_by"] and it["updated_at"] and it["evidence"] == "1234567890"
    # moving away from verified clears verified_by
    r = sup.put("/admin/launch/checklist/phase13_audit", json={"status": "blocked", "evidence": "regression found"})
    it = next(i for i in r.json()["items"] if i["key"] == "phase13_audit")
    assert it["status"] == "blocked" and it["verified_by"] is None and len(it["history"]) >= 2


def test_03_dns_check_blocked_and_safety():
    sup = admin_client()
    r = sup.post("/admin/launch/checklist/dns/check")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "blocked" and "afrovending.com" in d["evidence"]
    item = next(i for i in d["items"] if i["key"] == "dns")
    assert item["evidence"].startswith("[automatic check]")
    s = sup.post("/admin/launch/checklist/stripe_test/check").json()
    assert s["status"] in ("verified", "blocked")
    ssl = sup.post("/admin/launch/checklist/ssl/check").json()
    assert ssl["status"] == "blocked"
    assert mongo.platform_settings.find_one({"key": "payments.config"}) == SAVED["pay"]


# --- Final approval + reopen ---
def test_04_final_approval_gate_and_reopen():
    sup = admin_client()
    fin, _ = admin_with("finance_admin")
    r = sup.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "Owner approved in writing"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "checklist_incomplete"
    for k in NON_FINAL:
        mongo.launch_checklist.update_one({"key": k}, {"$set": {"key": k, "status": "verified"}}, upsert=True)
    assert fin.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "Owner approved in writing"}).status_code == 403
    assert sup.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "short"}).status_code == 422
    r = sup.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "TEST owner approval reference"})
    assert r.status_code == 200
    d = sup.get("/admin/launch/checklist").json()
    assert d["verified"] == 10
    # finance admin reopens by changing live_payments
    assert fin.put("/admin/launch/checklist/live_payments", json={"status": "in_progress", "evidence": "keys rotated"}).status_code == 200
    f = next(i for i in sup.get("/admin/launch/checklist").json()["items"] if i["key"] == "final_approval")
    assert f["status"] == "in_progress" and "Reopened" in f["note"] and "live_payments" in f["note"]
    # auto check returning blocked also reopens
    mongo.launch_checklist.update_one({"key": "live_payments"}, {"$set": {"status": "verified"}})
    assert sup.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "TEST owner approval reference"}).status_code == 200
    sup.post("/admin/launch/checklist/dns/check")
    f = mongo.launch_checklist.find_one({"key": "final_approval"})
    assert f["status"] == "in_progress" and "dns" in f["note"]


# --- Public launch record ---
def test_05_public_launch_record():
    sup = admin_client()
    pay_before = mongo.platform_settings.find_one({"key": "payments.config"})
    r = sup.post("/admin/launch/public-launch", json={"confirm": "RECORD PUBLIC LAUNCH"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_approved"
    mongo.launch_checklist.update_one({"key": "dns"}, {"$set": {"status": "verified"}})
    assert sup.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "TEST owner approval reference"}).status_code == 200
    assert sup.post("/admin/launch/public-launch", json={"confirm": "record public launch"}).status_code == 422
    fut = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert sup.post("/admin/launch/public-launch", json={"confirm": "RECORD PUBLIC LAUNCH", "launched_at": fut}).status_code == 422
    past = (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0)
    r = sup.post("/admin/launch/public-launch", json={"confirm": "RECORD PUBLIC LAUNCH", "launched_at": past.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["public_launch"]["recorded_by"]
    r2 = sup.post("/admin/launch/public-launch", json={"confirm": "RECORD PUBLIC LAUNCH"})
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "already_recorded"
    r3 = sup.post("/admin/launch/public-launch", json={"confirm": "RECORD PUBLIC LAUNCH", "launched_at": past.isoformat(), "reason": "TEST correction"})
    assert r3.status_code == 200
    d = sup.get("/admin/launch/checklist").json()
    assert d["public_launch"] and d["public_launch"]["reason"] == "TEST correction"
    assert mongo.platform_settings.find_one({"key": "payments.config"}) == pay_before
    assert mongo.audit_logs.find_one({"action": "launch.public_launch_recorded"}) is not None


def _vendor(email, approved_at, status="active"):
    uid = mongo.users.insert_one({"email": email, "name": "TEST_T1 Founding", "roles": ["customer", "vendor"], "status": "active", "password_hash": None,
                                  "created_at": approved_at, "updated_at": approved_at}).inserted_id
    USERS.append(uid)
    slug = f"t1fv-{uuid.uuid4().hex[:8]}"
    vid = mongo.vendors.insert_one({"owner_user_id": uid, "slug": slug, "name": f"TEST_T1 {slug}", "status": status, "approved_at": approved_at,
                                    "created_at": approved_at, "updated_at": approved_at}).inserted_id
    VENDORS.append(vid)
    mongo.vendor_stores.insert_one({"vendor_id": vid, "owner_user_id": uid, "slug": slug, "display_name": f"TEST_T1 {slug}", "tagline": "", "description": "",
                                    "location": "", "categories": [], "status": "published", "created_at": approved_at, "updated_at": approved_at})
    return slug, str(vid)


# --- Founding badge ---
def test_06_founding_edges_and_overrides():
    launch = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=10)
    mongo.platform_settings.update_one({"key": founding.LAUNCH_KEY}, {"$set": {"value": {"launched_at": launch, "recorded_by": "t1"}}}, upsert=True)
    h = uuid.uuid4().hex[:6]
    at_launch, _ = _vendor(f"start-{h}@afvt1.dev", launch)
    qa_acct, _ = _vendor(f"qa-{h}@afvt1.dev", launch + timedelta(days=1))
    test_acct, _ = _vendor(f"tester{h}@afvt1.dev", launch + timedelta(days=1))
    ex_org, _ = _vendor(f"real-{h}@example.org", launch + timedelta(days=1))
    term, term_id = _vendor(f"term-{h}@afvt1.dev", launch + timedelta(days=1), status="terminated")
    store = lambda s: httpx.get(f"{BASE}/stores/{s}")  # noqa: E731
    assert store(at_launch).json()["founding_vendor"] is True
    for s in (qa_acct, test_acct, ex_org):
        assert store(s).json()["founding_vendor"] is False, s
    assert store(term).status_code == 404
    sf = {v["slug"]: v for v in httpx.get(f"{BASE}/catalog/storefront").json()["vendors"]}
    assert sf[at_launch]["founding_vendor"] is True and term not in sf
    assert all(isinstance(v["founding_vendor"], bool) for v in sf.values())
    sup = admin_client()
    # Override cannot grant a test account or a terminated vendor
    slug_vid = {r["slug"]: r for r in sup.get("/admin/founding-vendors").json()["vendors"]}
    qa_vid = slug_vid[qa_acct]["vendor_id"]
    assert sup.put(f"/admin/founding-vendors/{qa_vid}", json={"value": True, "reason": "TEST grant attempt"}).status_code == 200
    assert store(qa_acct).json()["founding_vendor"] is False
    assert sup.put(f"/admin/founding-vendors/{term_id}", json={"value": True, "reason": "TEST grant attempt"}).status_code == 200
    rows = {r["slug"]: r for r in sup.get("/admin/founding-vendors").json()["vendors"]}
    assert rows[term]["eligible"] is False and rows[term]["override"]["value"] is True
    # clear override (null) and audit
    vid = slug_vid[at_launch]["vendor_id"]
    assert sup.put(f"/admin/founding-vendors/{vid}", json={"value": False, "reason": "TEST remove"}).status_code == 200
    assert store(at_launch).json()["founding_vendor"] is False
    assert sup.put(f"/admin/founding-vendors/{vid}", json={"value": None, "reason": "TEST clear"}).status_code == 200
    assert store(at_launch).json()["founding_vendor"] is True
    assert mongo.vendors.find_one({"_id": ObjectId(vid)})["founding_override"] is None
    assert mongo.audit_logs.count_documents({"action": "vendor.founding_override", "entity_id": {"$in": [vid, ObjectId(vid)]}}) >= 2
    assert sup.put("/admin/founding-vendors/notanid", json={"value": True, "reason": "TEST xxxxx"}).status_code == 404
    assert sup.put(f"/admin/founding-vendors/{ObjectId()}", json={"value": True, "reason": "TEST xxxxx"}).status_code == 404
    assert sup.put(f"/admin/founding-vendors/{vid}", json={"value": True, "reason": "abcd"}).status_code == 422
    # no launch recorded -> nobody is founding
    mongo.platform_settings.delete_one({"key": founding.LAUNCH_KEY})
    assert store(at_launch).json()["founding_vendor"] is False
    d = sup.get("/admin/founding-vendors").json()
    assert d["launched_at"] is None and d["window_ends_at"] is None
