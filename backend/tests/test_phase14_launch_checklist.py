# Launch readiness checklist + Founding Vendor badge
import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from afrovending.core import founding
from tests.test_phase03_vendors import BASE, admin_client, mongo
from tests.test_phase10_admin import MADE as ADMINS_MADE, admin_with

SAVED = {}
VENDORS, USERS = [], []


def setup_module():
    SAVED["launch"] = mongo.platform_settings.find_one({"key": founding.LAUNCH_KEY})
    SAVED["items"] = list(mongo.launch_checklist.find({}))


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


def test_01_checklist_access_and_rules():
    sup = admin_client()
    d = sup.get("/admin/launch/checklist").json()
    assert d["total"] == 10 and "never changes DNS" in d["safety"] and d["is_super_admin"]
    fin, _ = admin_with("finance_admin")
    f = fin.get("/admin/launch/checklist").json()
    assert set(f["can_edit"]) == {"stripe_test", "live_payments"} and not f["is_super_admin"]
    assert fin.put("/admin/launch/checklist/phase13_audit", json={"status": "verified", "evidence": "x" * 20}).status_code == 403
    assert fin.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "x" * 20}).status_code == 403
    assert fin.put("/admin/launch/checklist/live_payments", json={"status": "blocked", "evidence": "Connect not enabled yet"}).status_code == 200
    mk, _ = admin_with("marketplace_admin")
    assert mk.get("/admin/launch/checklist").status_code == 403
    assert httpx.get(f"{BASE}/admin/launch/checklist").status_code == 401
    assert sup.put("/admin/launch/checklist/email_domain", json={"status": "verified", "evidence": "short"}).status_code == 422
    assert sup.put("/admin/launch/checklist/dns", json={"status": "verified", "evidence": "trust me, it resolves"}).json()["error"]["code"] == "auto_only"
    r = sup.put("/admin/launch/checklist/email_domain", json={"status": "verified", "evidence": "Resend dashboard: afrovending.com verified (TEST)"})
    item = next(i for i in r.json()["items"] if i["key"] == "email_domain")
    assert item["status"] == "verified" and item["verified_by"] and item["verified_at"] and item["history"]
    assert sup.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "Owner approved in writing"}).json()["error"]["code"] == "checklist_incomplete"
    assert mongo.audit_logs.find_one({"action": "launch.checklist_updated", "entity_id": "email_domain"}) or mongo.audit_log.find_one({"action": "launch.checklist_updated"})


def test_02_automatic_checks():
    sup = admin_client()
    r = sup.post("/admin/launch/checklist/admin_mfa/check").json()
    assert r["status"] in ("verified", "blocked") and "administrator" in r["evidence"]
    dns = sup.post("/admin/launch/checklist/dns/check").json()
    assert dns["status"] == "blocked"  # afrovending.com does not resolve today
    assert sup.post("/admin/launch/checklist/email_domain/check").status_code == 422
    subprocess.run(["bash", "-c", "./scripts/backup_db.sh >/dev/null && ./scripts/restore_verify.sh $(ls -t /app/backups/*.archive.gz | head -1) >/dev/null"], cwd="/app/backend", check=True, timeout=250)
    b = sup.post("/admin/launch/checklist/backup_rollback/check").json()
    assert b["status"] == "verified" and "PASS" in b["evidence"]
    assert mongo.payments.count_documents({"livemode": True}) == 0


def test_03_final_approval_reopens_and_launch_record_gate():
    sup = admin_client()
    for k in ("dns", "ssl", "stripe_test", "live_payments", "admin_mfa", "email_domain", "phase13_audit", "marketplace_testing", "backup_rollback"):
        mongo.launch_checklist.update_one({"key": k}, {"$set": {"key": k, "status": "verified"}}, upsert=True)
    assert sup.post("/admin/launch/public-launch", json={"confirm": "RECORD PUBLIC LAUNCH"}).json()["error"]["code"] == "not_approved"
    assert sup.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "TEST owner approval reference"}).status_code == 200
    assert sup.post("/admin/launch/public-launch", json={"confirm": "nope"}).status_code == 422
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert sup.post("/admin/launch/public-launch", json={"confirm": "RECORD PUBLIC LAUNCH", "launched_at": future}).status_code == 422
    sup.put("/admin/launch/checklist/ssl", json={"status": "blocked", "evidence": "cert expired (TEST)"})
    fin = mongo.launch_checklist.find_one({"key": "final_approval"})
    assert fin["status"] == "in_progress" and "Reopened" in fin["note"]
    assert mongo.platform_settings.find_one({"key": "payments.config", "value.live_payments_enabled": True}) is None


def _vendor(email, approved_at, status="active", publish=True):
    uid = mongo.users.insert_one({"email": email, "name": "Founding T14", "roles": ["customer", "vendor"], "status": "active", "password_hash": None,
                                  "created_at": approved_at, "updated_at": approved_at}).inserted_id
    USERS.append(uid)
    slug = f"fv-{uuid.uuid4().hex[:8]}"
    vid = mongo.vendors.insert_one({"owner_user_id": uid, "slug": slug, "name": f"FV {slug}", "status": status, "approved_at": approved_at,
                                    "created_at": approved_at, "updated_at": approved_at}).inserted_id
    VENDORS.append(vid)
    if publish:
        mongo.vendor_stores.insert_one({"vendor_id": vid, "owner_user_id": uid, "slug": slug, "display_name": f"FV {slug}", "tagline": "", "description": "",
                                        "location": "", "categories": [], "status": "published", "created_at": approved_at, "updated_at": approved_at})
    return slug, str(vid)


def test_04_founding_eligibility_from_launch_timestamp():
    launch = datetime.now(timezone.utc) - timedelta(days=40)
    mongo.platform_settings.update_one({"key": founding.LAUNCH_KEY}, {"$set": {"value": {"launched_at": launch, "recorded_by": "t14"}}}, upsert=True)
    h = uuid.uuid4().hex[:6]
    inside, _ = _vendor(f"inside-{h}@afvfounders.dev", launch + timedelta(days=29, hours=23))
    edge, _ = _vendor(f"edge-{h}@afvfounders.dev", launch + timedelta(days=30))
    before, _ = _vendor(f"before-{h}@afvfounders.dev", launch - timedelta(days=1))
    susp, _ = _vendor(f"susp-{h}@afvfounders.dev", launch + timedelta(days=3), status="suspended")
    test_acct, _ = _vendor(f"t-{h}@example.com", launch + timedelta(days=3))
    store = lambda s: httpx.get(f"{BASE}/stores/{s}").json()  # noqa: E731
    assert store(inside)["founding_vendor"] is True  # retained after the window ended 10 days ago
    assert store(edge)["founding_vendor"] is False and store(before)["founding_vendor"] is False and store(test_acct)["founding_vendor"] is False
    assert httpx.get(f"{BASE}/stores/{susp}").status_code == 404
    sf = {v["slug"]: v["founding_vendor"] for v in httpx.get(f"{BASE}/catalog/storefront").json()["vendors"]}
    assert sf[inside] is True and sf[edge] is False
    rows = {r["slug"]: r for r in admin_client().get("/admin/founding-vendors").json()["vendors"]}
    assert rows[susp]["eligible"] is False and "not active" in rows[susp]["reason"] and rows[test_acct]["reason"] == "Test account."


def test_05_admin_corrections_audited_and_super_only():
    sup = admin_client()
    h = uuid.uuid4().hex[:6]
    launch = mongo.platform_settings.find_one({"key": founding.LAUNCH_KEY})["value"]["launched_at"]
    slug, vid = _vendor(f"fix-{h}@afvfounders.dev", launch - timedelta(days=5))
    assert sup.put(f"/admin/founding-vendors/{vid}", json={"value": True, "reason": "x"}).status_code == 422
    assert sup.put(f"/admin/founding-vendors/{vid}", json={"value": True, "reason": "Approval delayed by admin backlog"}).status_code == 200
    assert httpx.get(f"{BASE}/stores/{slug}").json()["founding_vendor"] is True
    assert sup.put(f"/admin/founding-vendors/{vid}", json={"value": False, "reason": "Policy violation (TEST)"}).status_code == 200
    assert httpx.get(f"{BASE}/stores/{slug}").json()["founding_vendor"] is False
    fin, _ = admin_with("finance_admin")
    assert fin.get("/admin/founding-vendors").status_code == 403
    assert fin.put(f"/admin/founding-vendors/{vid}", json={"value": True, "reason": "self-serve grant"}).status_code == 403
    v = mongo.vendors.find_one({"_id": __import__("bson").ObjectId(vid)})
    assert v["founding_override"]["by"] and "commission_rate" not in v
