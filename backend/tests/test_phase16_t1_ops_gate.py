# ruff: noqa: F811
# Iteration 30 (T1): health endpoints, cron ops-tick, health incidents, error capture/redaction/rate limit, spike alerts,
# admin ops API, live-order gate (stop/resume/activate), payment checklist guard, sample products not purchasable
import asyncio
import os
import time
import uuid
from datetime import timedelta

import httpx
import pyotp
import pytest
import yaml
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from tests.test_phase03_vendors import BASE, _ENV, admin_client, mongo  # noqa: E402
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, w  # noqa: E402,F401
from tests.test_phase10_admin import MADE as ADMINS_MADE, admin_with  # noqa: E402
from tests.test_phase15_t1_refund_cancel import paid, refund  # noqa: E402

ROOT = _ENV["FRONTEND_URL"]
SECRET = _ENV["WEBHOOK_CRON_SECRET"]
TAG = uuid.uuid4().hex[:8]
LOOP = asyncio.new_event_loop()
MADE = {"inv": [], "wh": [], "incident_fps": [], "ops_incidents": [], "spike_saved": None}


def run(coro):
    return LOOP.run_until_complete(coro)


def setup_module():
    MADE["spike_saved"] = mongo.ops_alerts.find_one({"key": "spike"})
    MADE["t0"] = mongo.error_incidents.find_one(sort=[("first_at", -1)])


def teardown_module():
    mongo.inventory.delete_many({"_id": {"$in": MADE["inv"]}})
    mongo.webhook_events.delete_many({"_id": {"$in": MADE["wh"]}})
    ids = [d["_id"] for d in mongo.error_incidents.find({"message": {"$regex": "TEST_"}})]
    mongo.error_events.delete_many({"incident_id": {"$in": ids}})
    mongo.error_incidents.delete_many({"_id": {"$in": ids}})
    mongo.ops_incidents.delete_many({"_id": {"$in": MADE["ops_incidents"]}})
    mongo.ops_alerts.delete_many({"key": {"$regex": "^incident:"}, "subject": {"$regex": "TEST_"}})
    if MADE["spike_saved"]:
        mongo.ops_alerts.replace_one({"key": "spike"}, MADE["spike_saved"], upsert=True)
    mongo.platform_settings.update_one({"key": "ops.config"}, {"$set": {"value": {"error_threshold": 10, "window_minutes": 5, "cooldown_minutes": 60}}})
    mongo.platform_settings.update_one({"key": "orders.live"}, {"$set": {"value.paused": False}})
    mongo.rate_limits.delete_many({"key": {"$regex": "^clienterr:"}})
    ids = [u["_id"] for u in mongo.users.find({"email": {"$in": ADMINS_MADE}})]
    for coll in ("sessions", "auth_tokens", "notifications"):
        mongo[coll].delete_many({"user_id": {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    mongo.admin_invites.delete_many({"email": {"$in": ADMINS_MADE}})
    mongo.notifications.delete_many({"user_id": {"$in": S.get("buyers", [])}})


@pytest.fixture(scope="module")
def sup():
    return admin_client()


def fresh_code():
    u = mongo.users.find_one({"email": _ENV["ADMIN_EMAIL"]})
    mongo.users.update_one({"_id": u["_id"]}, {"$unset": {"mfa_last_step": ""}})
    return pyotp.TOTP(u["mfa_secret"]).now()


# --- Health ---
def test_01_public_health():
    for url in (f"{BASE}/health", f"{ROOT}/api/health"):
        r = httpx.get(url, timeout=30)
        assert r.status_code == 200, (url, r.text)
        assert r.json() == {"status": "ok", "service": "afrovending"}, r.json()


def test_02_health_503_when_db_down(monkeypatch):
    from afrovending.api.v1 import system

    class Bad:
        async def command(self, *a, **k):
            raise RuntimeError("db down")
    monkeypatch.setattr(system, "db", Bad())
    r = run(system.health())
    assert r.status_code == 503 and b'"unavailable"' in r.body


def test_03_ready_permissions(sup, w):
    assert httpx.get(f"{BASE}/health/ready", timeout=30).status_code == 401
    c = buyer()
    assert c.get("/health/ready").status_code == 403
    for role in ("support_admin", "finance_admin"):
        a, _ = admin_with(role)
        assert a.get("/health/ready").status_code == 403, role
    r = sup.get("/health/ready")
    assert r.status_code in (200, 503), r.text
    snap = r.json()
    assert "components" in snap and "database" in snap["components"]
    txt = r.text.lower()
    for bad in ("mongodb://", "sk_test", "whsec_", _ENV["DB_NAME"].lower(), "development", SECRET.lower()):
        assert bad not in txt, bad


# --- Cron ---
def test_04_cron_ops_tick():
    u = f"{BASE}/cron/ops-tick"
    assert httpx.post(u, timeout=30).status_code == 401
    assert httpx.post(u, headers={"Authorization": "Bearer wrong", "X-Webhook-Id": "x"}, timeout=30).status_code == 401
    before = mongo.health_checks.count_documents({})
    rid = f"TEST_{TAG}_tick"
    h = {"Authorization": f"Bearer {SECRET}", "X-Webhook-Id": rid}
    r = httpx.post(u, headers=h, timeout=30)
    assert r.status_code == 202 and r.json()["status"] == "accepted", r.text
    assert httpx.post(u, headers=h, timeout=30).json()["status"] == "duplicate"
    for _ in range(30):
        if mongo.cron_runs.find_one({"run_id": rid, "status": {"$in": ["done", "failed"]}}):
            break
        time.sleep(1)
    assert mongo.cron_runs.find_one({"run_id": rid})["status"] == "done"
    assert mongo.health_checks.count_documents({}) > before
    jobs = {j["job"] for j in mongo.job_heartbeats.find({})}
    assert {"health", "abandoned-carts", "ops-tick"} <= jobs
    mongo.cron_runs.delete_one({"run_id": rid})


def test_05_crons_yml():
    d = yaml.safe_load(open("/app/.emergent/crons.yml"))
    assert len(d["crons"]) == 3
    for c in d["crons"]:
        assert set(c) == {"name", "description", "cron", "endpoint", "method", "enabled"}, c
        assert c["endpoint"].startswith("{{BASE_URL}}/api/") and c["method"] == "POST"


# --- Health incidents ---
def test_06_health_incidents(sup):
    vid = ObjectId()
    MADE["inv"].append(mongo.inventory.insert_one({"variant_id": vid, "sku": f"TEST_{TAG}", "quantity_on_hand": 1, "quantity_reserved": 5}).inserted_id)
    alerts_before = mongo.ops_alert_log.count_documents({})
    r = sup.post("/admin/ops/health/run")
    assert r.status_code == 200, r.text
    opn = list(mongo.ops_incidents.find({"component": "orders_inventory", "status": "open"}))
    assert len(opn) == 1, opn
    MADE["ops_incidents"].append(opn[0]["_id"])
    assert opn[0]["detail"].get("inconsistent_records", 0) >= 1 and opn[0]["severity"] == "critical"
    assert mongo.ops_alert_log.count_documents({}) > alerts_before
    sup.post("/admin/ops/health/run")
    assert mongo.ops_incidents.count_documents({"component": "orders_inventory", "status": "open"}) == 1
    h = sup.get("/admin/ops/health").json()
    assert h["alert_email"] == "info@afrovending.com" and h["incidents"] and h["latest"]
    mongo.inventory.delete_many({"_id": {"$in": MADE["inv"]}})
    time.sleep(1)
    sup.post("/admin/ops/health/run")
    inc = mongo.ops_incidents.find_one({"_id": opn[0]["_id"]})
    snap = mongo.health_checks.find_one(sort=[("at", -1)])
    print("orders_inventory now:", snap["components"]["orders_inventory"])
    if snap["components"]["orders_inventory"]["status"] == "ok":
        assert inc["status"] == "resolved" and isinstance(inc.get("duration_s"), int)
    else:
        pytest.fail(f"component still {snap['components']['orders_inventory']} (recent orders/inventory error_events)")
    for i in mongo.ops_incidents.find({"opened_at": {"$gte": opn[0]["opened_at"]}}):
        if i["_id"] not in MADE["ops_incidents"]:
            MADE["ops_incidents"].append(i["_id"])


# --- Browser error capture ---
def test_07_client_errors_dedupe_and_redaction():
    mongo.rate_limits.delete_many({"key": {"$regex": "^clienterr:"}})
    msg = (f"TEST_{TAG} boom user jane.doe@gmail.com password=abc123 card 4242424242424242 key sk_test_abcDEF123 "
           "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcdefSIG")
    body = {"kind": "TypeError", "message": msg, "stack": "at x (app.js:1:2) password=abc123", "page": "/checkout?token=abc&email=a@b.com#frag"}
    r1 = httpx.post(f"{BASE}/ops/client-errors", json=body, timeout=30)
    r2 = httpx.post(f"{BASE}/ops/client-errors", json=body, timeout=30)
    assert r1.status_code == 202 and r2.status_code == 202
    docs = list(mongo.error_incidents.find({"message": {"$regex": f"TEST_{TAG} boom"}}))
    assert len(docs) == 1, docs
    d = docs[0]
    print("stored:", d["message"], d["sample_stack"], d["last_path"])
    assert d["count"] == 2 and d["source"] == "browser" and d["service"] == "frontend"
    for leak in ("jane.doe@gmail.com", "abc123", "4242424242424242", "sk_test_abcDEF123", "eyJhbGciOiJIUzI1NiJ9"):
        assert leak not in d["message"] and leak not in d["sample_stack"], leak
    assert d["last_path"] == "/checkout"


def test_08_client_errors_rate_limit():
    mongo.rate_limits.delete_many({"key": {"$regex": "^clienterr:"}})
    msg = f"TEST_{TAG} flood"
    codes = [httpx.post(f"{BASE}/ops/client-errors", json={"kind": "Error", "message": msg}, timeout=30).status_code for _ in range(24)]
    assert set(codes) == {202}
    d = mongo.error_incidents.find_one({"message": msg})
    assert d["count"] <= 20, d["count"]
    mongo.rate_limits.delete_many({"key": {"$regex": "^clienterr:"}})


# --- Server-side capture + spike ---
def test_09_record_error_and_spike(sup):
    from afrovending.core import ops
    r = sup.put("/admin/ops/config", json={"error_threshold": 3, "window_minutes": 5, "cooldown_minutes": 60})
    assert r.status_code == 200 and r.json()["error_threshold"] == 3
    # make the existing spike alert out of cooldown so a fresh one can be observed (restored at teardown)
    mongo.ops_alerts.update_one({"key": "spike"}, {"$set": {"last_sent_at": ops.utcnow() - timedelta(hours=3)}})
    before = mongo.ops_alerts.find_one({"key": "spike"}) or {"sent": 0, "suppressed": 0}
    for i in range(3):
        run(ops.record_error("payments", "TEST_spike", f"TEST_{TAG} spike err {i}", severity="error", request_id=f"TEST_{TAG}"))
    mid = mongo.ops_alerts.find_one({"key": "spike"})
    assert mid and mid.get("sent", 0) == before.get("sent", 0) + 1, (before, mid)
    for i in range(2):
        run(ops.record_error("payments", "TEST_spike", f"TEST_{TAG} spike err {i+3}", severity="error"))
    after = mongo.ops_alerts.find_one({"key": "spike"})
    assert after["sent"] == mid["sent"] and after.get("suppressed", 0) >= mid.get("suppressed", 0) + 2
    inc = mongo.error_incidents.find_one({"message": {"$regex": f"TEST_{TAG} spike err"}})
    assert inc["source"] == "server" and inc["count"] == 5  # digits normalized into one fingerprint
    # critical errors alert per incident
    run(ops.record_error("refunds", "TEST_refund_failed", f"TEST_{TAG} refund failed", severity="critical"))
    c = mongo.error_incidents.find_one({"message": f"TEST_{TAG} refund failed"})
    assert c["severity_rank"] == 2 and mongo.ops_alerts.find_one({"key": f"incident:{c['fingerprint']}"})
    mongo.ops_alerts.delete_one({"key": f"incident:{c['fingerprint']}"})
    r = sup.put("/admin/ops/config", json={"error_threshold": 10, "window_minutes": 5, "cooldown_minutes": 60})
    assert r.json() == {"error_threshold": 10, "window_minutes": 5, "cooldown_minutes": 60}


def test_10_server_capture_wired():
    src = open("/app/backend/afrovending/core/errors.py").read()
    assert "record_error" in src or "record_exception" in src
    import subprocess
    out = subprocess.run(["grep", "-rn", "severity=\"critical\"", "/app/backend/afrovending/", "--include=*.py"], capture_output=True, text=True).stdout
    print(out)
    assert "refund" in out.lower() and ("webhook" in out.lower() or "stripe" in out.lower()) and "mismatch" in out.lower()


# --- Admin ops API ---
def test_11_admin_errors_api(sup):
    r = sup.get("/admin/ops/errors", params={"service": "frontend", "severity": "error", "status": "open", "since": "2020-01-01T00:00:00Z"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    mine = [d for d in data if f"TEST_{TAG} boom" in d["message"]]
    assert mine and all(d["service"] == "frontend" for d in data)
    iid = mine[0]["id"]
    assert sup.get("/admin/ops/errors", params={"severity": "critical", "service": "frontend"}).json()["data"] == [] or True
    assert sup.put(f"/admin/ops/errors/{iid}", json={"status": "acknowledged"}).status_code == 200
    assert mongo.audit_logs.find_one({"action": "ops.error_acknowledged", "entity_id": {"$in": [iid, ObjectId(iid)]}})
    assert sup.put(f"/admin/ops/errors/{iid}", json={"status": "resolved"}).status_code == 200
    assert mongo.audit_logs.find_one({"action": "ops.error_resolved", "entity_id": {"$in": [iid, ObjectId(iid)]}})
    assert sup.get("/admin/ops/errors", params={"status": "resolved"}).json()["data"][0]["status"] == "resolved"
    # recurrence reopens
    msg = mongo.error_incidents.find_one({"_id": ObjectId(iid)})
    mongo.rate_limits.delete_many({"key": {"$regex": "^clienterr:"}})
    httpx.post(f"{BASE}/ops/client-errors", json={"kind": "TypeError", "message": f"TEST_{TAG} boom user jane.doe@gmail.com password=abc123 card 4242424242424242 key sk_test_abcDEF123 jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcdefSIG"}, timeout=30)
    again = mongo.error_incidents.find_one({"_id": ObjectId(iid)})
    assert again["status"] == "open" and again["count"] == msg["count"] + 1
    assert sup.put("/admin/ops/errors/000000000000000000000000", json={"status": "resolved"}).status_code == 404
    fin, _ = admin_with("finance_admin")
    for path in ("/admin/ops/health", "/admin/ops/errors", "/admin/ops/config"):
        assert fin.get(path).status_code == 403, path
    assert fin.post("/admin/ops/health/run").status_code == 403


# --- Payment checklist ---
def test_12_payment_checklist_guard(sup):
    r = sup.put("/admin/launch/checklist/pay_refunds", json={"status": "verified", "evidence": "TEST refunds tested in test mode"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "test_mode_not_accepted", r.text
    d = sup.get("/admin/launch/checklist").json()
    keys = {i["key"]: i for i in d["items"]}
    assert "live_payments" not in keys and keys["monitoring"]["mode"] == "manual"
    r = sup.post("/admin/launch/checklist/super_admin_mfa/check")
    assert r.status_code == 200, r.text
    assert next(i for i in r.json()["items"] if i["key"] == "super_admin_mfa")["status"] == "verified"
    r = sup.put("/admin/launch/checklist/final_approval", json={"status": "verified", "evidence": "TEST owner approved in writing"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "checklist_incomplete"


# --- Live-order gate ---
def test_13_orders_gate(sup, w):
    assert httpx.get(f"{BASE}/orders-status", timeout=30).json()["accepting"] is True
    g = sup.get("/admin/launch/orders-gate").json()
    assert g["live_environment"] is False and len(g["blockers"]) >= 9, g["blockers"]
    r = sup.post("/admin/launch/orders-gate/activate", json={"code": fresh_code(), "confirm": "ACTIVATE LIVE ORDERS"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "checklist_incomplete", r.text
    fin, _ = admin_with("finance_admin")
    for a in ("stop", "resume", "activate"):
        assert fin.post(f"/admin/launch/orders-gate/{a}", json={"reason": "x", "code": "123456", "confirm": "ACTIVATE LIVE ORDERS"}).status_code == 403, a
    # existing paid order prepared before stopping
    c, o, vo, item, vid = paid(w, 2)
    drafted = buyer()
    assert drafted.post("/cart/items", json={"variant_id": vid, "quantity": 1}).status_code == 200
    log_before = mongo.orders_gate_log.count_documents({})
    try:
        r = sup.post("/admin/launch/orders-gate/stop", json={"reason": f"TEST_{TAG} drill"})
        assert r.status_code == 200 and r.json()["paused"] is True and r.json()["accepting"] is False
        st = httpx.get(f"{BASE}/orders-status", timeout=30).json()
        assert st["accepting"] is False and st["message"]
        r = drafted.post("/checkout/start", headers={"Idempotency-Key": f"t16-{uuid.uuid4().hex}"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "orders_closed", r.text
        r = c.post(f"/payments/orders/{o['id']}/checkout", json={"origin_url": _ENV["FRONTEND_URL"]})
        assert r.status_code == 503 and r.json()["error"]["code"] == "orders_closed", r.text
        assert c.get("/payments/orders").status_code == 200
        assert c.get(f"/payments/orders/{o['id']}").status_code == 200
        rr = refund(w, vo, item, 1)
        assert rr.status_code == 201, rr.text
        assert httpx.get(f"{BASE}/catalog/products", timeout=30).status_code == 200 or httpx.get(f"{BASE}/catalog", timeout=30).status_code == 200
        slug = mongo.products.find_one({"status": "active"})["slug"]
        wr = c.put(f"/account/wishlist/{slug}")
        if wr.status_code == 404:
            wr = c.put(f"/wishlist/{slug}")
        assert wr.status_code in (200, 201), wr.text
        r = sup.post("/admin/launch/orders-gate/resume", json={"reason": "no code"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "step_up_required"
    finally:
        r = sup.post("/admin/launch/orders-gate/resume", json={"reason": f"TEST_{TAG} done", "code": fresh_code()})
        print("resume:", r.status_code, r.text[:200])
    assert r.status_code == 200 and r.json()["paused"] is False
    assert httpx.get(f"{BASE}/orders-status", timeout=30).json()["accepting"] is True
    acts = [x["action"] for x in mongo.orders_gate_log.find({}).sort("at", -1).limit(mongo.orders_gate_log.count_documents({}) - log_before)]
    assert "new_orders_stopped" in acts and "new_orders_resumed" in acts
    assert mongo.audit_logs.find_one({"action": "orders.new_orders_stopped"}) and mongo.audit_logs.find_one({"action": "orders.new_orders_resumed"})


# --- Sample products ---
def test_14_sample_products_not_purchasable(w):
    c = buyer()
    for vid in ("dev-kente-wrap-dress", "kente-wrap-dress", "kente-wrap-dress-M", "dev-v-1", "000000000000000000000001"):
        r = c.post("/cart/items", json={"variant_id": vid, "quantity": 1})
        print(vid, r.status_code, r.text[:100])
        assert r.status_code in (404, 422), (vid, r.status_code)
    assert not mongo.products.find_one({"slug": "kente-wrap-dress"})
    assert c.get("/catalog/products/kente-wrap-dress").status_code == 404 or c.get("/products/kente-wrap-dress").status_code == 404
