# T1 iter26: Pre-launch Founding Vendors rule + public /founding-vendors list + DNS-failure/backup regression
import asyncio
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId

from afrovending.core import founding
from tests.test_phase03_vendors import BASE, admin_client, mongo

SAVED = {}
VENDORS, USERS = [], []
H = uuid.uuid4().hex[:6]


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
    for coll in ("sessions", "auth_tokens", "notifications"):
        mongo[coll].delete_many({"user_id": {"$in": USERS}})
    mongo.users.delete_many({"_id": {"$in": USERS}})


def _vendor(tag, email, approved_at, status="active", store_status="published", override=None):
    now = datetime.now(timezone.utc)
    uid = mongo.users.insert_one({"email": email, "name": f"TEST_T1 {tag}", "roles": ["customer", "vendor"], "status": "active", "password_hash": None,
                                  "created_at": now, "updated_at": now}).inserted_id
    USERS.append(uid)
    slug = f"t1fp-{tag}-{H}"
    doc = {"owner_user_id": uid, "slug": slug, "name": f"TEST_T1 {slug}", "status": status, "approved_at": approved_at, "created_at": now, "updated_at": now}
    if override is not None:
        doc["founding_override"] = {"value": override, "reason": "TEST override", "by": "t1", "at": now}
    vid = mongo.vendors.insert_one(doc).inserted_id
    VENDORS.append(vid)
    mongo.vendor_stores.insert_one({"vendor_id": vid, "owner_user_id": uid, "slug": slug, "display_name": f"TEST_T1 {slug}", "tagline": "", "description": "",
                                    "location": "", "categories": [], "status": store_status, "created_at": now, "updated_at": now})
    return slug


def _public():
    r = httpx.get(f"{BASE}/founding-vendors", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d["data"], list)
    return {e["slug"]: e for e in d["data"]}


def _store(slug):
    return httpx.get(f"{BASE}/stores/{slug}", timeout=30)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
S = {}


# --- No launch recorded: every approved active non-test vendor qualifies ---
def test_01_no_launch_prelaunch_rule():
    mongo.platform_settings.delete_one({"key": founding.LAUNCH_KEY})
    S["ok"] = _vendor("ok", f"realok-{H}@afvt1.dev", NOW - timedelta(days=3))
    S["exnet"] = _vendor("exnet", f"a-{H}@example.net", NOW - timedelta(days=3))
    S["excom"] = _vendor("excom", f"a-{H}@example.com", NOW - timedelta(days=3))
    S["testcom"] = _vendor("testcom", f"a-{H}@test.com", NOW - timedelta(days=3))
    S["testpre"] = _vendor("testpre", f"testvendor{H}@afvt1.dev", NOW - timedelta(days=3))
    S["qapre"] = _vendor("qapre", f"qa{H}@afvt1.dev", NOW - timedelta(days=3))
    S["susp"] = _vendor("susp", f"susp-{H}@afvt1.dev", NOW - timedelta(days=3), status="suspended")
    S["term"] = _vendor("term", f"term-{H}@afvt1.dev", NOW - timedelta(days=3), status="terminated")
    S["ovf"] = _vendor("ovf", f"ovf-{H}@afvt1.dev", NOW - timedelta(days=3), override=False)
    S["draft"] = _vendor("draft", f"draft-{H}@afvt1.dev", NOW - timedelta(days=3), store_status="draft")
    S["noappr"] = _vendor("noappr", f"noappr-{H}@afvt1.dev", None)
    pub = _public()
    assert S["ok"] in pub and pub[S["ok"]]["founding_vendor"] is True
    for k in ("exnet", "excom", "testcom", "testpre", "qapre", "susp", "term", "ovf", "draft", "noappr"):
        assert S[k] not in pub, k
    assert all(e["founding_vendor"] is True for e in pub.values())
    # no internal fields leaked
    e = pub[S["ok"]]
    for leak in ("vendor_id", "owner_user_id", "_id", "email"):
        assert leak not in e, leak
    assert _store(S["ok"]).json()["founding_vendor"] is True
    assert _store(S["excom"]).json()["founding_vendor"] is False
    assert _store(S["ovf"]).json()["founding_vendor"] is False
    assert _store(S["susp"]).status_code == 404 and _store(S["term"]).status_code == 404
    sf = {v["slug"]: v for v in httpx.get(f"{BASE}/catalog/storefront", timeout=30).json()["vendors"]}
    assert sf[S["ok"]]["founding_vendor"] is True
    assert sf[S["qapre"]]["founding_vendor"] is False
    assert S["susp"] not in sf and S["term"] not in sf
    rows = {r["slug"]: r for r in admin_client().get("/admin/founding-vendors").json()["vendors"]}
    assert rows[S["ok"]]["eligible"] is True and "pre-launch" in rows[S["ok"]]["reason"]


# --- Launch recorded 40 days ago: pre-launch + within 30d included, >= launch+30d excluded ---
def test_02_launch_window_rule():
    launch = NOW - timedelta(days=40)
    mongo.platform_settings.update_one({"key": founding.LAUNCH_KEY}, {"$set": {"value": {"launched_at": launch, "recorded_by": "t1"}}}, upsert=True)
    S["pre"] = _vendor("pre", f"pre-{H}@afvt1.dev", launch - timedelta(days=5))
    S["at"] = _vendor("at", f"at-{H}@afvt1.dev", launch)
    S["in"] = _vendor("in", f"in-{H}@afvt1.dev", launch + timedelta(days=29, hours=23))
    S["edge"] = _vendor("edge", f"edge-{H}@afvt1.dev", launch + timedelta(days=30))
    S["late"] = _vendor("late", f"late-{H}@afvt1.dev", launch + timedelta(days=35))
    S["lategrant"] = _vendor("lategrant", f"lg-{H}@afvt1.dev", launch + timedelta(days=35), override=True)
    S["pretest"] = _vendor("pretest", f"x-{H}@example.org", launch - timedelta(days=5))
    pub = _public()
    for k in ("pre", "at", "in", "lategrant"):
        assert S[k] in pub, k
        assert _store(S[k]).json()["founding_vendor"] is True, k
    for k in ("edge", "late", "pretest"):
        assert S[k] not in pub, k
        assert _store(S[k]).json()["founding_vendor"] is False, k
    sf = {v["slug"]: v for v in httpx.get(f"{BASE}/catalog/storefront", timeout=30).json()["vendors"]}
    assert sf[S["pre"]]["founding_vendor"] is True and sf[S["edge"]]["founding_vendor"] is False
    d = admin_client().get("/admin/founding-vendors").json()
    assert d["launched_at"] and d["window_ends_at"]
    rows = {r["slug"]: r for r in d["vendors"]}
    assert rows[S["pre"]]["eligible"] and "pre-launch" in rows[S["pre"]]["reason"]
    assert rows[S["ok"]]["eligible"] is False  # approved NOW-3d > launch+30d
    assert rows[S["in"]]["eligible"] and "30 days" in rows[S["in"]]["reason"]
    assert rows[S["late"]]["eligible"] is False and "window" in rows[S["late"]]["reason"]
    assert rows[S["lategrant"]]["eligible"] and "admin" in rows[S["lategrant"]]["reason"].lower()


# --- Public endpoint needs no auth and is in sitemap ---
def test_03_public_no_auth_and_sitemap():
    r = httpx.get(f"{BASE}/founding-vendors", timeout=30)
    assert r.status_code == 200 and "data" in r.json()
    root = BASE.rsplit("/api/v1", 1)[0]
    sm = None
    for u in (f"{BASE}/seo/sitemap.xml",):
        x = httpx.get(u, timeout=30)
        if x.status_code == 200 and "<urlset" in x.text:
            sm = x.text
            break
    assert sm and "/founding-vendors" in sm


# --- Regression: DNS check never 500 even when lookup fails ---
def test_04_dns_lookup_failure_returns_blocked():
    from afrovending.api.v1 import launch as L

    class Boom:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise httpx.ConnectError("dns down")

    class BadJson(Boom):
        async def get(self, *a, **k):
            return httpx.Response(200, text="<html>not json</html>")

    orig = L.httpx.AsyncClient
    try:
        for cls in (Boom, BadJson):
            L.httpx.AsyncClient = cls
            status, ev = asyncio.run(L._check("dns"))
            assert status == "blocked" and "lookup failed" in ev, (cls, ev)
    finally:
        L.httpx.AsyncClient = orig
    r = admin_client().post("/admin/launch/checklist/dns/check")
    assert r.status_code == 200 and r.json()["status"] in ("blocked", "verified")


# --- Regression: backup_rollback passes after backup + restore drill ---
def test_05_backup_rollback_after_scripts():
    sd = os.path.join(os.path.dirname(__file__), "..", "scripts")
    b = subprocess.run(["bash", os.path.join(sd, "backup_db.sh")], capture_output=True, text=True, timeout=120)
    assert b.returncode == 0, b.stderr
    import json
    arch = json.loads(b.stdout.strip().splitlines()[-1])["backup"]
    rv = subprocess.run(["bash", os.path.join(sd, "restore_verify.sh"), arch], capture_output=True, text=True, timeout=120)
    assert rv.returncode == 0, rv.stdout + rv.stderr
    r = admin_client().post("/admin/launch/checklist/backup_rollback/check")
    assert r.status_code == 200 and r.json()["status"] == "verified", r.text
    assert mongo.platform_settings.find_one({"key": "payments.config"}) == SAVED["pay"]
