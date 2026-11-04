import logging

from afrovending.core.config import settings
from afrovending.core.models import User, utcnow
from afrovending.core.roles import Role
from afrovending.core.security import hash_password, password_problem

logger = logging.getLogger("afrovending.seed")


async def seed_admin(db) -> None:
    """Preview/test convenience only. Runs only when ALLOW_ENV_ADMIN_SEED=true AND no super admin exists yet.
    Never changes an existing account's password or roles. Production uses `python -m afrovending.scripts.bootstrap_admin`."""
    import os
    if os.environ.get("ALLOW_ENV_ADMIN_SEED", "").lower() != "true":
        return
    if await db.users.find_one({"email": settings.admin_email}) or await db.users.find_one({"roles": Role.SUPER_ADMIN.value, "status": "active"}):
        return
    problem = password_problem(settings.admin_password, strong=True)
    if problem:
        raise RuntimeError(f"ADMIN_PASSWORD rejected: {problem}")
    admin = User(email=settings.admin_email, name="AfroVending Admin", password_hash=hash_password(settings.admin_password),
                 roles=[Role.SUPER_ADMIN.value], status="active", email_verified_at=utcnow(),
                 auth_providers=[{"provider": "password", "linked_at": utcnow()}])
    await db.users.insert_one(admin.to_mongo())
    logger.info("Seeded preview super admin account (MFA enrollment required on first admin use)")
