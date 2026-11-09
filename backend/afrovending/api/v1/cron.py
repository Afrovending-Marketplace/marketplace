import hmac
import json
import logging
import os
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Header, Request
from pymongo.errors import DuplicateKeyError

from afrovending.core.catalog import send_low_stock_digests
from afrovending.core.payments import release_all
from afrovending.core.fulfillment import escalate_overdue, handling_alerts
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow

router = APIRouter(prefix="/cron", tags=["cron"])
SECRET = os.environ["WEBHOOK_CRON_SECRET"]
log = logging.getLogger("afrovending.cron")


async def _run(run_id: str, job, schedule: str = "") -> None:
    from afrovending.core import ops
    try:
        result = await job()
        await db.cron_runs.update_one({"run_id": run_id}, {"$set": {"status": "done", "result": result, "finished_at": utcnow()}})
        await ops.job_heartbeat(schedule, True)
    except Exception as exc:
        log.exception("cron job failed run_id=%s", run_id)
        await db.cron_runs.update_one({"run_id": run_id}, {"$set": {"status": "failed", "finished_at": utcnow()}})
        await ops.job_heartbeat(schedule, False)
        await ops.record_exception("background_jobs", exc, severity="error", path=f"cron {schedule}")


async def ops_tick() -> dict:
    """Every 15 min: health check + abandoned carts; hourly jobs run in their usual quarter-hour slot."""
    from afrovending.core import ops
    from afrovending.core import marketing as mk
    from afrovending.core.wishlist_alerts import run_wishlist_alerts
    quarter = utcnow().minute // 15
    jobs = [("health", ops.health_tick), ("abandoned-carts", mk.run_abandoned_carts)]
    jobs += {0: [("wishlist-alerts", run_wishlist_alerts)], 1: [("fulfillment-escalations", escalate_overdue)], 3: [("handling-alerts", handling_alerts)]}.get(quarter, [])
    out = {}
    for name, fn in jobs:
        try:
            await fn()
            out[name] = "ok"
            await ops.job_heartbeat(name, True)
        except Exception as exc:
            log.exception("ops-tick job failed: %s", name)
            out[name] = "failed"
            await ops.job_heartbeat(name, False)
            await ops.record_exception("background_jobs", exc, path=f"cron {name}")
    return out


@router.post("/ops-tick", status_code=202)
async def ops_tick_job(request: Request, background: BackgroundTasks, authorization: str = Header(default="")):
    return await _accept(request, background, authorization, "ops-tick", ops_tick)


@router.post("/low-stock-digest", status_code=202)
async def low_stock_digest(request: Request, background: BackgroundTasks, authorization: str = Header(default="")):
    return await _accept(request, background, authorization, "low-stock-digest", send_low_stock_digests)


@router.post("/payout-release", status_code=202)
async def payout_release(request: Request, background: BackgroundTasks, authorization: str = Header(default="")):
    return await _accept(request, background, authorization, "payout-release", release_all)


@router.post("/fulfillment-escalations", status_code=202)
async def fulfillment_escalations(request: Request, background: BackgroundTasks, authorization: str = Header(default="")):
    return await _accept(request, background, authorization, "fulfillment-escalations", escalate_overdue)


@router.post("/handling-alerts", status_code=202)
async def handling_alerts_job(request: Request, background: BackgroundTasks, authorization: str = Header(default="")):
    return await _accept(request, background, authorization, "handling-alerts", handling_alerts)


async def _accept(request: Request, background: BackgroundTasks, authorization: str, schedule: str, job):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    scheme, _, token = authorization.partition(" ")
    if scheme != "Bearer" or not hmac.compare_digest(token.encode(), SECRET.encode()):
        raise APIError(401, "unauthorized", "Unauthorized.")
    raw = await request.body()
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        raise APIError(400, "bad_request", "Invalid JSON body.")
    if not isinstance(body, dict):
        raise APIError(400, "bad_request", "Invalid webhook envelope.")
    run_id = request.headers.get("X-Webhook-Id") or body.get("run_id")
    if not run_id:
        raise APIError(400, "bad_request", "Missing run id.")
    now = utcnow()
    try:
        await db.cron_runs.insert_one({"run_id": str(run_id)[:100], "schedule": schedule, "status": "queued",
                                       "created_at": now, "expires_at": now + timedelta(days=30)})
    except DuplicateKeyError:
        return {"status": "duplicate"}
    background.add_task(_run, str(run_id)[:100], job, schedule)
    return {"status": "accepted"}
