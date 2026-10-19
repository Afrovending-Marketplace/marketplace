import hmac
import json
import logging
import os
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Header, Request
from pymongo.errors import DuplicateKeyError

from afrovending.core.catalog import send_low_stock_digests
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow

router = APIRouter(prefix="/cron", tags=["cron"])
SECRET = os.environ["WEBHOOK_CRON_SECRET"]
log = logging.getLogger("afrovending.cron")


async def _run_digest(run_id: str) -> None:
    try:
        result = await send_low_stock_digests()
        await db.cron_runs.update_one({"run_id": run_id}, {"$set": {"status": "done", "result": result, "finished_at": utcnow()}})
    except Exception:
        log.exception("low-stock digest failed run_id=%s", run_id)
        await db.cron_runs.update_one({"run_id": run_id}, {"$set": {"status": "failed", "finished_at": utcnow()}})


@router.post("/low-stock-digest", status_code=202)
async def low_stock_digest(request: Request, background: BackgroundTasks, authorization: str = Header(default="")):
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
        await db.cron_runs.insert_one({"run_id": str(run_id)[:100], "schedule": "low-stock-digest", "status": "queued",
                                       "created_at": now, "expires_at": now + timedelta(days=30)})
    except DuplicateKeyError:
        return {"status": "duplicate"}
    background.add_task(_run_digest, str(run_id)[:100])
    return {"status": "accepted"}
