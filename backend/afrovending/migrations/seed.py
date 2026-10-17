import logging

from afrovending.core.config import settings
from afrovending.core.models import User, utcnow
from afrovending.core.roles import Role
from afrovending.core.security import hash_password, password_problem, verify_password

logger = logging.getLogger("afrovending.seed")


async def seed_admin(db) -> None:
    problem = password_problem(settings.admin_password, strong=True)
    if problem:
        raise RuntimeError(f"ADMIN_PASSWORD rejected: {problem}")
    existing = await db.users.find_one({"email": settings.admin_email})
    if existing is None:
        admin = User(email=settings.admin_email, name="AfroVending Admin", password_hash=hash_password(settings.admin_password),
                     roles=[Role.SUPER_ADMIN.value], status="active", email_verified_at=utcnow(),
                     auth_providers=[{"provider": "password", "linked_at": utcnow()}])
        await db.users.insert_one(admin.to_mongo())
        logger.info("Seeded super admin account")
        return
    updates = {}
    if not existing.get("password_hash") or not verify_password(settings.admin_password, existing["password_hash"]):
        updates["password_hash"] = hash_password(settings.admin_password)
    if Role.SUPER_ADMIN.value not in existing.get("roles", []):
        updates["roles"] = [*existing.get("roles", []), Role.SUPER_ADMIN.value]
    if updates:
        await db.users.update_one({"_id": existing["_id"]}, {"$set": {**updates, "updated_at": utcnow()}})
