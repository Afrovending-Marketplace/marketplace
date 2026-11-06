"""Phase 14: legacy URL redirects (public) and migrated-account activation controls (Super Admin, approval-gated)."""
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.permissions import SETTINGS, require_perm

router = APIRouter(tags=["migration"])
APPROVAL_KEY = "migration.activation"
CONFIRM = "SEND ACTIVATION EMAILS"
SUPER = require_perm(SETTINGS)
MIGRATED = {"migration.source": "legacy_afrovending"}


@router.get("/redirects/resolve")
async def resolve(path: str):
    path = "/" + path.split("?")[0].strip("/")[:300]
    from afrovending.legacy.importer import STATIC_REDIRECTS
    if path in STATIC_REDIRECTS:
        return {"to": STATIC_REDIRECTS[path], "status": 301}
    hit = await db.legacy_redirects.find_one({"from_path": path})
    if hit:
        return {"to": hit["to_path"], "status": hit.get("status", 301)}
    m = re.fullmatch(r"/product-tag/([a-z0-9-]{1,60})", path)
    if m:
        return {"to": f"/search?q={m.group(1).replace('-', ' ')}", "status": 301}
    raise APIError(404, "not_found", "No redirect for this path.")


@router.get("/admin/migration/report")
async def report(admin: User = Depends(SUPER)):
    base = {**MIGRATED}
    total = await db.users.count_documents(base)
    appr = await db.platform_settings.find_one({"key": APPROVAL_KEY})
    last = await db.migration_runs.find_one({"kind": "legacy_import"}, sort=[("_id", -1)], projection={"_id": 0, "entities": 1, "finished_at": 1, "mode": 1})
    return {
        "accounts": total,
        "customers_only": await db.users.count_documents({**base, "roles": {"$ne": "vendor"}}),
        "vendors": await db.users.count_documents({**base, "roles": "vendor"}),
        "activation_pending": await db.users.count_documents({**base, "migration.activation_required": True}),
        "activation_emails_sent": await db.users.count_documents({**base, "migration.activation_sent_at": {"$ne": None}}),
        "activated": await db.users.count_documents({**base, "migration.activated_at": {"$ne": None}}),
        "linked_existing_accounts": await db.users.count_documents({"migration_link.source": "legacy_afrovending"}),
        "legacy_orders": await db.legacy_orders.count_documents({}),
        "redirects": await db.legacy_redirects.count_documents({}),
        "images_pending": await db.legacy_image_queue.count_documents({"status": {"$ne": "done"}}),
        "approval": (appr or {}).get("value", {"approved": False}),
        "last_import": last,
    }


class ApprovalIn(BaseModel):
    approved: bool
    confirm: str = Field(default="", max_length=40)


@router.put("/admin/migration/activation-approval")
async def set_approval(body: ApprovalIn, request: Request, admin: User = Depends(SUPER)):
    if body.approved and body.confirm != CONFIRM:
        raise APIError(422, "validation_error", f"Type “{CONFIRM}” to confirm the owner approved sending activation emails.")
    value = {"approved": body.approved, "by": admin.email, "at": utcnow()}
    await db.platform_settings.update_one({"key": APPROVAL_KEY}, {"$set": {"value": value, "updated_at": utcnow()}}, upsert=True)
    await audit("admin.migration_activation_approval", "platform_settings", request=request, actor=admin, approved=body.approved)
    return {"approval": value}


class BatchIn(BaseModel):
    batch_size: int = Field(default=50, ge=1, le=200)


@router.post("/admin/migration/activation-batch")
async def activation_batch(body: BatchIn, request: Request, admin: User = Depends(SUPER)):
    from afrovending.api.v1.auth import _needs_activation, send_activation
    appr = await db.platform_settings.find_one({"key": APPROVAL_KEY})
    if not (appr or {}).get("value", {}).get("approved"):
        raise APIError(409, "not_approved", "Activation emails are not approved yet. The owner must approve sending first.")
    sent = failed = 0
    q = {**MIGRATED, "migration.activation_required": True, "migration.activation_sent_at": None, "status": "active",
         "$or": [{"migration.activation_claim": None}, {"migration.activation_claim": {"$lt": utcnow().timestamp() - 900}}]}
    for _ in range(body.batch_size):
        now = utcnow()
        doc = await db.users.find_one_and_update(q, {"$set": {"migration.activation_claim": now.timestamp()}})
        if not doc:
            break
        if not _needs_activation(doc):
            continue
        ok = await send_activation(doc)
        upd = {"migration.activation_sent_at": now} if ok else {}
        await db.users.update_one({"_id": doc["_id"]}, {"$set": {**upd, "migration.activation_claim": None if ok else now.timestamp() + 3600},
                                                       "$inc": {"migration.activation_attempts": 1}})
        await db.migration_activation_log.insert_one({"user_id": doc["_id"], "ok": ok, "at": now, "by": admin.email})
        sent, failed = sent + ok, failed + (not ok)
    remaining = await db.users.count_documents({**MIGRATED, "migration.activation_required": True, "migration.activation_sent_at": None})
    await audit("admin.migration_activation_batch", "users", request=request, actor=admin, sent=sent, failed=failed, remaining=remaining)
    return {"sent": sent, "failed": failed, "remaining": remaining}
