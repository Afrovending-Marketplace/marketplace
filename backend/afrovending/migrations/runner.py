import json
import logging

from afrovending.core.config import BACKEND_DIR
from afrovending.core.models import AuditLog, PlatformSetting, utcnow
from afrovending.core.roles import ROLE_DESCRIPTIONS
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


async def m0002_phase02_identity(db) -> None:
    await ensure_indexes(db, phase=2)
    for role, description in ROLE_DESCRIPTIONS.items():
        await db.roles.update_one({"key": role.value}, {"$setOnInsert": {"key": role.value, "description": description,
                                                                          "created_at": utcnow()}}, upsert=True)


async def m0003_phase03_vendors(db) -> None:
    await ensure_indexes(db, phase=3)


async def m0006_phase06_cart(db) -> None:
    await ensure_indexes(db, phase=6)


async def m0007_phase07_payments(db) -> None:
    await ensure_indexes(db, phase=7)
    if not await db.commission_rules.find_one({"scope": "default", "status": "active"}):
        await db.commission_rules.insert_one({"scope": "default", "scope_id": None, "label": "Marketplace default", "rate_bps": 1000,
                                              "note": "Initial 10% approved by owner", "status": "active", "created_by": None, "created_at": utcnow()})


async def m0008_phase08_fulfillment(db) -> None:
    await ensure_indexes(db, phase=8)


async def m0009_handling_times(db) -> None:
    await ensure_indexes(db, phase=8)


async def m0010_pickup_slots(db) -> None:
    await ensure_indexes(db, phase=8)


async def m0005_phase05_search(db) -> None:
    for idx in await db.products.list_indexes().to_list(50):
        if "textIndexVersion" in idx and "weights" in idx and idx["weights"].get("title") != 10:
            await db.products.drop_index(idx["name"])
    await ensure_indexes(db, phase=5)
    from afrovending.core.catalog import refresh_stock_flag
    async for p in db.products.find({"in_stock": {"$exists": False}}, {"_id": 1}):
        await refresh_stock_flag(p["_id"])


async def m0004_phase04_catalog(db) -> None:
    await ensure_indexes(db, phase=4)
    fixtures = json.loads((BACKEND_DIR / "fixtures" / "categories.json").read_text())
    for i, item in enumerate(fixtures):
        now = utcnow()
        base = {"blurb": item["blurb"], "image": item["image"], "status": "active", "created_at": now, "updated_at": now}
        await db.categories.update_one({"slug": item["slug"]}, {"$setOnInsert": {**base, "slug": item["slug"], "name": item["name"],
                                                                             "parent_id": None, "sort_order": i * 10}}, upsert=True)
        parent = await db.categories.find_one({"slug": item["slug"]})
        for j, name in enumerate(item["children"]):
            slug = item["slug"] + "-" + "".join(c if c.isalnum() else "-" for c in name.lower()).replace("--", "-").strip("-")
            await db.categories.update_one({"slug": slug}, {"$setOnInsert": {**base, "slug": slug, "name": name, "blurb": "", "image": None,
                                                                          "parent_id": parent["_id"], "sort_order": j * 10}}, upsert=True)


MIGRATIONS = (
    ("0001", "phase00_foundation", m0001_phase00_foundation),
    ("0002", "phase02_identity", m0002_phase02_identity),
    ("0003", "phase03_vendor_onboarding", m0003_phase03_vendors),
    ("0004", "phase04_catalog_inventory", m0004_phase04_catalog),
    ("0005", "phase05_search_discovery", m0005_phase05_search),
    ("0006", "phase06_cart_checkout", m0006_phase06_cart),
    ("0007", "phase07_payments", m0007_phase07_payments),
    ("0008", "phase08_fulfillment", m0008_phase08_fulfillment),
    ("0009", "handling_times", m0009_handling_times),
    ("0010", "pickup_slots", m0010_pickup_slots),
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
