from fastapi import APIRouter

from afrovending.core.config import APP_NAME, APP_VERSION, CURRENT_PHASE, settings
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import PlatformSetting, utcnow
from afrovending.core.roles import ROLE_DESCRIPTIONS
from afrovending.schema.entities import ENTITIES, entity_contract

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    try:
        await db.command("ping")
        database = "ok"
    except Exception:
        database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "service": APP_NAME,
        "version": APP_VERSION,
        "environment": settings.app_env,
        "phase": CURRENT_PHASE,
        "time": utcnow().isoformat(),
    }


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
