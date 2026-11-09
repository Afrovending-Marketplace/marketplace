from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from afrovending.core import ops, orders_gate, rate_limit
from afrovending.core.permissions import OPS, require_perm
from afrovending.core.security import client_ip

from afrovending.core.config import APP_VERSION, CURRENT_PHASE, settings
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import PlatformSetting
from afrovending.core.roles import ROLE_DESCRIPTIONS
from afrovending.schema.entities import ENTITIES, entity_contract

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    """Public availability probe for uptime monitors. Reveals nothing beyond up/down."""
    try:
        await db.command("ping")
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "service": "afrovending"})
    return {"status": "ok", "service": "afrovending"}


@router.get("/health/ready")
async def ready(_: object = Depends(require_perm(OPS))):
    snap = await ops.run_checks()
    return JSONResponse(status_code=200 if snap["status"] != "down" else 503, content=snap)


@router.get("/orders-status")
async def orders_status():
    ok, msg = await orders_gate.accepting()
    return {"accepting": ok, "message": msg}


class ClientErrorIn(BaseModel):
    kind: str = Field(default="Error", max_length=80)
    message: str = Field(default="", max_length=1000)
    stack: str = Field(default="", max_length=4000)
    page: str = Field(default="", max_length=300)


@router.post("/ops/client-errors", status_code=202)
async def client_error(body: ClientErrorIn, request: Request):
    """Browser error reports. Rate limited per address; query strings and form values are never stored."""
    n = await rate_limit.hit(f"clienterr:{client_ip(request)}", 20, 300, raise_over=False)
    if n <= 20:
        await ops.record_error("frontend", body.kind, body.message, stack=body.stack, source="browser", path=body.page.split("?")[0].split("#")[0],
                               browser=request.headers.get("user-agent", ""), request_id=getattr(request.state, "request_id", None))
    return {"status": "accepted"}


@router.get("/platform")
async def platform():
    docs = await db.platform_settings.find({"is_public": True}).to_list(200)
    return {"settings": {s.key: s.value for s in map(PlatformSetting.from_mongo, docs)}}


@router.get("/system/schema")
async def schema_contract():
    if settings.is_production:
        raise APIError(404, "not_found", "Not Found")
    migrations = await db.schema_migrations.find({}, {"_id": 0}).sort("version", 1).to_list(500)
    return {
        "version": APP_VERSION,
        "current_phase": CURRENT_PHASE,
        "roles": [{"key": r.value, "description": d} for r, d in ROLE_DESCRIPTIONS.items()],
        "entities": [entity_contract(e) for e in ENTITIES],
        "migrations": [{**m, "applied_at": m["applied_at"].isoformat()} for m in migrations],
    }
