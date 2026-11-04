"""One-time Super Admin bootstrap. Usage (server shell only):
    python -m afrovending.scripts.bootstrap_admin --email owner@example.com --name "Owner"
Refuses to run if any active Super Admin exists, and never elevates or overwrites an existing account.
Recovery (all Super Admins lost): set BOOTSTRAP_RECOVERY_CODE in the server environment and pass --recovery-code with the same value."""
import argparse
import asyncio
import getpass
import hmac
import os
import sys

from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.models import User, utcnow
from afrovending.core.roles import Role
from afrovending.core.security import hash_password, password_problem


async def main(email: str, name: str, recovery: str | None) -> int:
    email = email.strip().lower()
    if await db.users.find_one({"roles": Role.SUPER_ADMIN.value, "status": "active"}):
        expected = os.environ.get("BOOTSTRAP_RECOVERY_CODE", "")
        if not (recovery and expected and len(expected) >= 24 and hmac.compare_digest(recovery, expected)):
            print("A Super Admin already exists. Bootstrap is disabled.", file=sys.stderr)
            return 1
    if await db.users.find_one({"email": email}):
        print("An account with this email already exists; bootstrap never elevates existing accounts. Use an in-app invite.", file=sys.stderr)
        return 1
    pw = getpass.getpass("New Super Admin password: ")
    if pw != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1
    problem = password_problem(pw, strong=True)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    u = User(email=email, name=name, password_hash=hash_password(pw), roles=[Role.SUPER_ADMIN.value], status="active",
             email_verified_at=utcnow(), auth_providers=[{"provider": "password", "linked_at": utcnow()}])
    uid = str((await db.users.insert_one(u.to_mongo())).inserted_id)
    await audit("admin.bootstrap", "users", entity_id=uid, recovery=bool(recovery))
    print("Super Admin created. Sign in, then enroll your authenticator app when prompted.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="AfroVending Owner")
    p.add_argument("--recovery-code")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.email, a.name, a.recovery_code)))
