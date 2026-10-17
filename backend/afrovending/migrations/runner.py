import json
import logging

from afrovending.core.config import BACKEND_DIR
from afrovending.core.models import AuditLog, PlatformSetting, utcnow
from afrovending.schema.entities import active_entities

logger = logging.getLogger("afrovending.migrations")


async def ensure_indexes(db, phase: int) -> None:
    for entity in active_entities(phase):
        for idx in entity.indexes:
            await db[entity.collection].create_index(list(idx.keys), name=idx.name, unique=idx.unique, **idx.options)


async def m0001_phase00_foundation(db) -> None:
    await ensure_indexes(db, phase=0)
    fixtures = json.loads((BACKEND_DIR / "fixtures" / "platform_settings.json").read_text())
    for item in fixtures:
        setting = PlatformSetting(**item).to_mongo()
        await db.platform_settings.update_one({"key": setting["key"]}, {"$setOnInsert": setting}, upsert=True)


MIGRATIONS = (
    ("0001", "phase00_foundation", m0001_phase00_foundation),
)


async def run_migrations(db) -> None:
    await db.schema_migrations.create_index("version", name="version_1", unique=True)
    applied = {d["version"] async for d in db.schema_migrations.find({}, {"version": 1})}
    for version, name, fn in MIGRATIONS:
        if version in applied:
            continue
        logger.info("Applying migration %s_%s", version, name)
        await fn(db)
        await db.schema_migrations.insert_one({"version": version, "name": name, "applied_at": utcnow()})
        await db.audit_logs.insert_one(
            AuditLog(action="schema.migration_applied", entity_type="schema_migrations", entity_id=version,
                     metadata={"name": name}).to_mongo()
        )
