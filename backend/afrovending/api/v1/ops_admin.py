"""Super Admin production monitoring: health, downtime incidents, error incidents and alert settings."""
from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from afrovending.core import ops
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.permissions import OPS, require_perm

router = APIRouter(prefix="/admin/ops", tags=["ops"])
OPS_ADMIN = require_perm(OPS)


def _out(d: dict) -> dict:
    return {**{k: (v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, ObjectId) else v) for k, v in d.items() if k not in ("_id", "expires_at")}, "id": str(d["_id"])}


@router.get("/health")
async def health(_: User = Depends(OPS_ADMIN)):
    last = await db.health_checks.find_one({}, sort=[("at", -1)])
    incidents = await db.ops_incidents.find({}).sort("opened_at", -1).limit(20).to_list(20)
    alerts = await db.ops_alert_log.find({}).sort("at", -1).limit(10).to_list(10)
    jobs = await db.job_heartbeats.find({}).to_list(50)
    return {"latest": _out(last) if last else None, "incidents": [_out(i) for i in incidents], "alerts": [_out(a) for a in alerts],
            "jobs": [_out(j) for j in jobs], "alert_email": ops.ALERT_EMAIL}


@router.post("/health/run")
async def run_now(request: Request, admin: User = Depends(OPS_ADMIN)):
    res = await ops.health_tick()
    await audit("ops.health_check_run", "health_checks", request=request, actor=admin, status=res["status"])
    return res


@router.get("/errors")
async def errors(service: Optional[str] = None, severity: Optional[Literal["critical", "error", "warning"]] = None,
                 status: Optional[Literal["open", "acknowledged", "resolved"]] = None, since: Optional[datetime] = None, until: Optional[datetime] = None,
                 limit: int = Query(50, ge=1, le=200), _: User = Depends(OPS_ADMIN)):
    q: dict = {}
    if service:
        q["service"] = service
    if severity:
        q["severity_rank"] = ops.SEVERITIES[::-1].index(severity)
    if status:
        q["status"] = status
    if since or until:
        q["last_at"] = {**({"$gte": since} if since else {}), **({"$lte": until} if until else {})}
    docs = await db.error_incidents.find(q).sort("last_at", -1).limit(limit).to_list(limit)
    services = await db.error_incidents.distinct("service")
    return {"data": [{**_out(d), "severity": ops.SEVERITIES[::-1][d.get("severity_rank", 1)]} for d in docs], "services": sorted(services)}


class StatusIn(BaseModel):
    status: Literal["acknowledged", "resolved", "open"]
    note: str = Field(default="", max_length=300)


@router.put("/errors/{incident_id}")
async def set_status(incident_id: str, body: StatusIn, request: Request, admin: User = Depends(OPS_ADMIN)):
    if not ObjectId.is_valid(incident_id):
        raise APIError(404, "not_found", "Incident not found.")
    now = utcnow()
    r = await db.error_incidents.update_one({"_id": ObjectId(incident_id)}, {"$set": {"status": body.status, f"{body.status}_at": now, f"{body.status}_by": admin.email},
                                                                        "$push": {"history": {"status": body.status, "by": admin.email, "at": now, "note": body.note}}})
    if not r.matched_count:
        raise APIError(404, "not_found", "Incident not found.")
    await audit(f"ops.error_{body.status}", "error_incidents", request=request, actor=admin, entity_id=incident_id, note=body.note)
    return {"ok": True}


@router.get("/emails")
async def email_deliveries(status: Optional[Literal["failed", "bounced", "complained", "delayed", "sent", "delivered"]] = None,
                           limit: int = Query(50, ge=1, le=200), _: User = Depends(OPS_ADMIN)):
    from afrovending.core import email as mail
    q = {"status": status} if status else {}
    docs = await db.email_deliveries.find(q, {"events": 0, "idempotency_key": 0}).sort("updated_at", -1).limit(limit).to_list(limit)
    return {"data": [_out(d) for d in docs], "sending_enabled": mail.sending_enabled(), "provider_configured": bool(mail._key())}


class ConfigIn(BaseModel):
    error_threshold: int = Field(ge=1, le=1000)
    window_minutes: int = Field(ge=1, le=60)
    cooldown_minutes: int = Field(ge=5, le=1440)


@router.get("/config")
async def get_config(_: User = Depends(OPS_ADMIN)):
    return await ops.get_config()


@router.put("/config")
async def put_config(body: ConfigIn, request: Request, admin: User = Depends(OPS_ADMIN)):
    await db.platform_settings.update_one({"key": ops.CONFIG_KEY}, {"$set": {"value": body.model_dump(), "updated_at": utcnow()}}, upsert=True)
    await audit("ops.config_updated", "platform_settings", request=request, actor=admin, **body.model_dump())
    return await ops.get_config()
