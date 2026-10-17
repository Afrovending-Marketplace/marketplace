from typing import Optional

from fastapi import Request

from afrovending.core.db import db
from afrovending.core.models import AuditLog


async def audit(action: str, entity_type: str, *, request: Optional[Request] = None, actor=None,
                entity_id: Optional[str] = None, **metadata) -> None:
    log = AuditLog(
        actor_id=getattr(actor, "id", None),
        actor_role=(actor.roles[0] if actor and actor.roles else "anonymous"),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=getattr(request.state, "request_id", None) if request else None,
        metadata=metadata,
    )
    await db.audit_logs.insert_one(log.to_mongo())
