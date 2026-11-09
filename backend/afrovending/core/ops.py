"""Production monitoring: sanitized error incidents, health checks, downtime incidents and deduplicated alerts. Sentry can be added later behind record_error()."""
import hashlib
import logging
import os
import re
import traceback
from datetime import timedelta

from afrovending.core.db import db
from afrovending.core.models import utcnow

log = logging.getLogger("afrovending.ops")
ALERT_EMAIL = os.environ["ALERT_EMAIL"]
RETENTION_DAYS = 30
CONFIG_KEY = "ops.config"
DEFAULT_CONFIG = {"error_threshold": 10, "window_minutes": 5, "cooldown_minutes": 60}
SEVERITIES = ("critical", "error", "warning")
# Expected cadence of each scheduled job; a job is "delayed" when its last success is older than the allowance.
JOB_ALLOWANCE = {"ops-tick": timedelta(minutes=45), "payout-release": timedelta(hours=26), "low-stock-digest": timedelta(days=8)}

_REDACT = [
    (re.compile(r"\b(sk|pk|rk)_(live|test)_[A-Za-z0-9]+"), "[stripe-key]"),
    (re.compile(r"\bwhsec_[A-Za-z0-9]+"), "[webhook-secret]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"), "[token]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*"), "Bearer [token]"),
    (re.compile(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|authorization|cookie|cvc|cvv)(\"?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,&}]+)"), r"\1\2[redacted]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[number]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
]


def sanitize(text, limit: int = 4000) -> str:
    out = str(text or "")
    for pat, rep in _REDACT:
        out = pat.sub(rep, out)
    return out[:limit]


def service_for(path: str) -> str:
    for prefix, name in (("/api/stripe/webhook", "stripe_webhook"), ("/api/v1/payments", "payments"), ("/api/v1/checkout", "checkout"),
                         ("/api/v1/admin/payments", "refunds"), ("/api/v1/fulfillment", "orders"), ("/api/v1/cart", "checkout"),
                         ("/api/v1/auth", "auth"), ("/api/v1/cron", "background_jobs")):
        if path.startswith(prefix):
            return name
    return "api"


async def get_config() -> dict:
    doc = await db.platform_settings.find_one({"key": CONFIG_KEY})
    return {**DEFAULT_CONFIG, **((doc or {}).get("value") or {})}


async def record_error(service: str, kind: str, message: str = "", *, severity: str = "error", stack: str = "", source: str = "server",
                       request_id: str | None = None, path: str = "", browser: str = "") -> None:
    """Never raises: monitoring must not break the request that failed."""
    try:
        severity = severity if severity in SEVERITIES else "error"
        msg = sanitize(message, 500)
        norm = re.sub(r"[0-9a-f]{24}|\d+", "#", msg)[:200]
        fp = hashlib.sha1(f"{source}|{service}|{kind}|{norm}".encode()).hexdigest()
        now = utcnow()
        inc = await db.error_incidents.find_one_and_update(
            {"fingerprint": fp},
            {"$inc": {"count": 1}, "$set": {"last_at": now, "message": msg, "sample_stack": sanitize(stack), "last_request_id": request_id, "last_path": sanitize(path, 200)},
             "$max": {"severity_rank": SEVERITIES[::-1].index(severity)},
             "$setOnInsert": {"fingerprint": fp, "service": service, "kind": kind[:120], "source": source, "first_at": now, "status": "open", "history": []}},
            upsert=True, return_document=True)
        if inc.get("status") == "resolved":
            await db.error_incidents.update_one({"_id": inc["_id"]}, {"$set": {"status": "open"}, "$push": {"history": {"status": "open", "by": "system", "at": now, "note": "Recurred after resolution"}}})
        await db.error_events.insert_one({"incident_id": inc["_id"], "service": service, "severity": severity, "source": source, "at": now,
                                          "request_id": request_id, "path": sanitize(path, 200), "browser": sanitize(browser, 200),
                                          "expires_at": now + timedelta(days=RETENTION_DAYS)})
        log.error("ops.error service=%s kind=%s severity=%s request_id=%s", service, kind, severity, request_id)
        if severity == "critical":
            await _alert(f"incident:{fp}", f"Critical: {service} — {kind}", f"{msg or kind} (occurrences: {inc.get('count', 1)}). Request ID: {request_id or 'n/a'}.")
        if source == "server":
            await _spike_check()
    except Exception:
        log.exception("record_error failed")


def record_exception(service: str, exc: BaseException, **kw):
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:]
    return record_error(service, type(exc).__name__, str(exc), stack=stack, **kw)


async def _spike_check() -> None:
    cfg = await get_config()
    since = utcnow() - timedelta(minutes=cfg["window_minutes"])
    n = await db.error_events.count_documents({"source": "server", "at": {"$gte": since}})
    if n >= cfg["error_threshold"]:
        await _alert("spike", f"Server errors: {n} in {cfg['window_minutes']} minutes",
                     f"{n} server errors in the last {cfg['window_minutes']} minutes (threshold {cfg['error_threshold']}). See Admin → Operations.")


async def _alert(key: str, subject: str, text: str) -> bool:
    """One alert per key per cooldown window. Returns True when an alert was sent (or suppressed outside production)."""
    from afrovending.core.email import payment_notice_email, try_send
    cfg = await get_config()
    now = utcnow()
    res = await db.ops_alerts.update_one({"key": key, "$or": [{"last_sent_at": {"$lt": now - timedelta(minutes=cfg["cooldown_minutes"])}}, {"last_sent_at": None}]},
                                         {"$set": {"last_sent_at": now, "subject": subject}, "$inc": {"sent": 1}})
    if not res.modified_count:
        try:
            await db.ops_alerts.insert_one({"key": key, "last_sent_at": now, "subject": subject, "sent": 1, "suppressed": 0})
        except Exception:
            await db.ops_alerts.update_one({"key": key}, {"$inc": {"suppressed": 1}})
            return False
    s, html = payment_notice_email("AfroVending operations", subject, text, "/admin/ops")
    ok = await try_send(to=ALERT_EMAIL, subject=f"[AfroVending alert] {subject}", html=html)
    await db.ops_alert_log.insert_one({"key": key, "subject": subject, "to": ALERT_EMAIL, "delivered": ok, "at": now, "expires_at": now + timedelta(days=RETENTION_DAYS)})
    return True


async def job_heartbeat(job: str, ok: bool) -> None:
    await db.job_heartbeats.update_one({"job": job}, {"$set": {"last_status": "ok" if ok else "failed", "last_run_at": utcnow(), **({"last_ok_at": utcnow()} if ok else {})}}, upsert=True)


async def run_checks() -> dict:
    """Health snapshot. Contains counts and statuses only; never configuration values or credentials."""
    now = utcnow()
    comps = {}
    try:
        await db.command("ping")
        comps["database"] = {"status": "ok"}
    except Exception:
        return {"status": "down", "components": {"database": {"status": "down", "detail": "Database unreachable"}}, "checked_at": now.isoformat()}
    comps["api"] = {"status": "ok"}
    stale = []
    async for h in db.job_heartbeats.find({}):
        allow = JOB_ALLOWANCE.get(h["job"])
        last = h.get("last_ok_at")
        if allow and last and last.replace(tzinfo=now.tzinfo) < now - allow:
            stale.append(h["job"])
    failed_jobs = await db.cron_runs.count_documents({"status": "failed", "created_at": {"$gte": now - timedelta(hours=24)}})
    comps["background_jobs"] = {"status": "degraded" if stale or failed_jobs else "ok", "failed_24h": failed_jobs, "delayed": stale}
    wh_failed = await db.webhook_events.count_documents({"status": "failed"})
    wh_stuck = await db.webhook_events.count_documents({"status": "processing", "received_at": {"$lt": now - timedelta(minutes=10)}})
    comps["stripe_webhooks"] = {"status": "degraded" if wh_failed or wh_stuck else "ok", "failed": wh_failed, "stuck": wh_stuck}
    since = now - timedelta(hours=1)
    for name, svc in (("checkout_payments", ["checkout", "payments"]), ("email", ["email"]), ("orders_inventory", ["orders", "inventory"]), ("refunds", ["refunds"])):
        n = await db.error_events.count_documents({"service": {"$in": svc}, "at": {"$gte": since}})
        comps[name] = {"status": "degraded" if n else "ok", "errors_1h": n}
    bad_inv = await db.inventory.count_documents({"$or": [{"quantity_on_hand": {"$lt": 0}}, {"quantity_reserved": {"$lt": 0}},
                                                          {"$expr": {"$gt": [{"$ifNull": ["$quantity_reserved", 0]}, "$quantity_on_hand"]}}]})
    if bad_inv:
        comps["orders_inventory"] = {**comps["orders_inventory"], "status": "down", "inconsistent_records": bad_inv}
    worst = "down" if any(c["status"] == "down" for c in comps.values()) else "degraded" if any(c["status"] == "degraded" for c in comps.values()) else "ok"
    return {"status": worst, "components": comps, "checked_at": now.isoformat()}


async def health_tick() -> dict:
    """Run checks, open/close one downtime incident per component, alert once on open and once on recovery."""
    snap = await run_checks()
    now = utcnow()
    await db.health_checks.insert_one({**snap, "at": now, "expires_at": now + timedelta(days=RETENTION_DAYS)})
    for name, c in snap["components"].items():
        open_inc = await db.ops_incidents.find_one({"component": name, "status": "open"})
        if c["status"] != "ok" and not open_inc:
            sev = "critical" if c["status"] == "down" or name in ("checkout_payments", "stripe_webhooks", "orders_inventory") else "error"
            await db.ops_incidents.insert_one({"component": name, "status": "open", "severity": sev, "opened_at": now, "detail": {k: v for k, v in c.items() if k != "status"}})
            await _alert(f"health:{name}:{now.isoformat()}", f"{name.replace('_', ' ').title()} is {c['status']}", f"Health check found {name} {c['status']}: {c}.")
        elif c["status"] == "ok" and open_inc:
            dur = int((now - open_inc["opened_at"].replace(tzinfo=now.tzinfo)).total_seconds())
            await db.ops_incidents.update_one({"_id": open_inc["_id"]}, {"$set": {"status": "resolved", "resolved_at": now, "duration_s": dur}})
            await _alert(f"recovery:{open_inc['_id']}", f"Recovered: {name.replace('_', ' ')}", f"{name} returned to normal after {dur // 60} minute(s).")
    return {"status": snap["status"]}
