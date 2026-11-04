from datetime import timedelta
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field

from afrovending.core import email as mail
from afrovending.core import rate_limit
from afrovending.core.audit import audit
from afrovending.core.config import settings
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.permissions import ADMIN_ROLE_VALUES, ADMINS, require_perm
from afrovending.core.security import client_ip, decode_token, hash_password, hash_token, new_opaque_token, require_valid_password, verify_password
from afrovending.core.sessions import revoke_all_sessions

router = APIRouter(tags=["admin-team"])
SUPER = require_perm(ADMINS)
AdminRole = Literal["super_admin", "marketplace_admin", "finance_admin", "support_admin", "content_admin"]
INVITE_TTL = timedelta(hours=72)


class InviteIn(BaseModel):
    email: EmailStr
    role: AdminRole


class RoleIn(BaseModel):
    role: AdminRole
    password: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=300)


class ConfirmIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=300)


class AcceptIn(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    name: Optional[str] = Field(default=None, max_length=100)
    password: Optional[str] = Field(default=None, max_length=200)


async def _reverify(actor: User, password: str) -> None:
    doc = await db.users.find_one({"_id": ObjectId(actor.id)})
    if not doc.get("password_hash") or not verify_password(password, doc["password_hash"]):
        raise APIError(403, "reauth_failed", "Your password is incorrect.")


async def _target(user_id: str, actor: User) -> dict:
    if user_id == actor.id:
        raise APIError(403, "forbidden", "You can't change your own admin access.")
    doc = await db.users.find_one({"_id": ObjectId(user_id)}) if ObjectId.is_valid(user_id) else None
    if not doc or not ADMIN_ROLE_VALUES & set(doc.get("roles", [])):
        raise APIError(404, "not_found", "Administrator not found.")
    return doc


async def _guard_last_super(doc: dict, keeps_super: bool) -> None:
    if "super_admin" in doc.get("roles", []) and not keeps_super:
        others = await db.users.count_documents({"_id": {"$ne": doc["_id"]}, "roles": "super_admin", "status": "active"})
        if others == 0:
            raise APIError(409, "last_super_admin", "You can't remove or demote the last active Super Admin.")


def _row(d: dict) -> dict:
    return {"id": str(d["_id"]), "email": d["email"], "name": d.get("name", ""), "roles": [r for r in d.get("roles", []) if r in ADMIN_ROLE_VALUES],
            "status": d["status"], "mfa_enrolled": bool(d.get("mfa_enabled_at")), "last_login_at": d.get("last_login_at")}


@router.get("/admin/team")
async def team(_: User = Depends(SUPER)):
    admins = await db.users.find({"roles": {"$in": list(ADMIN_ROLE_VALUES)}}).sort("created_at", 1).to_list(500)
    invites = await db.admin_invites.find({"status": "pending", "expires_at": {"$gt": utcnow()}}).sort("created_at", -1).to_list(200)
    return {"admins": [_row(a) for a in admins],
            "invites": [{"id": str(i["_id"]), "email": i["email"], "role": i["role"], "expires_at": i["expires_at"], "created_at": i["created_at"]} for i in invites]}


@router.post("/admin/team/invites", status_code=201)
async def invite(body: InviteIn, request: Request, admin: User = Depends(SUPER)):
    await rate_limit.hit(f"admin-invite:{admin.id}", 20, 3600)
    email = body.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing and body.role in existing.get("roles", []):
        raise APIError(409, "conflict", "This person already has that role.")
    await db.admin_invites.update_many({"email": email, "status": "pending"}, {"$set": {"status": "revoked", "revoked_at": utcnow()}})
    raw, hashed = new_opaque_token()
    doc = {"email": email, "role": body.role, "token_hash": hashed, "status": "pending", "invited_by": ObjectId(admin.id),
           "expires_at": utcnow() + INVITE_TTL, "created_at": utcnow()}
    doc["_id"] = (await db.admin_invites.insert_one(doc)).inserted_id
    link = f"{settings.frontend_url}/admin/invite?token={raw}"
    subject, html = mail.payment_notice_email(email, "You're invited to AfroVending admin",
                                              f"{admin.name} invited you to join AfroVending as {body.role.replace('_', ' ')}. The link works once and expires in 72 hours. "
                                              "You'll set up two-step sign-in before you can use admin tools.", "/admin/invite?token=" + raw)
    sent = await mail.try_send(to=email, subject=subject, html=html)
    await audit("admin.invite_created", "admin_invites", request=request, actor=admin, entity_id=str(doc["_id"]), email=email, role=body.role)
    out = {"id": str(doc["_id"]), "email": email, "role": body.role, "expires_at": doc["expires_at"], "email_sent": sent}
    if not sent:
        out["invite_link"] = link  # shown once to the inviting Super Admin only, never logged
    return out


@router.delete("/admin/team/invites/{invite_id}")
async def revoke_invite(invite_id: str, request: Request, admin: User = Depends(SUPER)):
    if not ObjectId.is_valid(invite_id):
        raise APIError(404, "not_found", "Invite not found.")
    r = await db.admin_invites.update_one({"_id": ObjectId(invite_id), "status": "pending"}, {"$set": {"status": "revoked", "revoked_at": utcnow()}})
    if not r.modified_count:
        raise APIError(404, "not_found", "Invite not found.")
    await audit("admin.invite_revoked", "admin_invites", request=request, actor=admin, entity_id=invite_id)
    return {"status": "revoked"}


@router.post("/auth/admin-invite/accept")
async def accept(body: AcceptIn, request: Request):
    await rate_limit.hit(f"invite-accept:{client_ip(request)}", 10, 900)
    inv = await db.admin_invites.find_one({"token_hash": hash_token(body.token), "status": "pending", "expires_at": {"$gt": utcnow()}})
    if not inv:
        raise APIError(410, "invite_invalid", "This invite link is invalid, used or expired. Ask a Super Admin for a new one.")
    user = await db.users.find_one({"email": inv["email"]})
    if user:
        try:
            current = await get_current_user(request)
        except APIError:
            current = None
        if not current or current.email != inv["email"]:
            raise APIError(401, "sign_in_required", f"Sign in as {inv['email']} first, then open this link again.")
    else:
        if not body.name or not body.password:
            raise APIError(422, "validation_error", "Enter your name and a password.")
        require_valid_password(body.password, strong=True)
        user = {"email": inv["email"], "name": body.name.strip(), "password_hash": hash_password(body.password), "roles": [], "status": "active",
                "email_verified_at": utcnow(), "auth_providers": [{"provider": "password", "linked_at": utcnow()}], "created_at": utcnow(), "updated_at": utcnow()}
        user["_id"] = (await db.users.insert_one(user)).inserted_id
    claimed = await db.admin_invites.find_one_and_update({"_id": inv["_id"], "status": "pending"}, {"$set": {"status": "accepted", "accepted_at": utcnow(),
                                                                                                         "user_id": user["_id"]}})
    if not claimed:
        raise APIError(410, "invite_invalid", "This invite was already used.")
    await db.users.update_one({"_id": user["_id"]}, {"$addToSet": {"roles": inv["role"]}, "$set": {"updated_at": utcnow()}})
    await revoke_all_sessions(str(user["_id"]))
    await audit("admin.invite_accepted", "users", request=request, entity_id=str(user["_id"]), role=inv["role"])
    return {"status": "accepted", "email": inv["email"], "role": inv["role"], "next": "Sign in and set up two-step sign-in."}


@router.put("/admin/team/{user_id}/role")
async def change_role(user_id: str, body: RoleIn, request: Request, admin: User = Depends(SUPER)):
    await _reverify(admin, body.password)
    doc = await _target(user_id, admin)
    await _guard_last_super(doc, body.role == "super_admin")
    roles = [r for r in doc["roles"] if r not in ADMIN_ROLE_VALUES] + [body.role]
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {"roles": roles, "updated_at": utcnow()}})
    await revoke_all_sessions(user_id)
    await audit("admin.role_changed", "users", request=request, actor=admin, entity_id=user_id, before=_row(doc)["roles"], after=[body.role], reason=body.reason)
    return {"admin": _row({**doc, "roles": roles})}


async def _access(user_id: str, body: ConfirmIn, request: Request, admin: User, action: str) -> dict:
    await _reverify(admin, body.password)
    doc = await _target(user_id, admin)
    if action != "reactivate":
        await _guard_last_super(doc, False)
    update = {"revoke": {"$set": {"roles": [r for r in doc["roles"] if r not in ADMIN_ROLE_VALUES]}},
              "suspend": {"$set": {"status": "suspended", "status_reason": body.reason}},
              "reactivate": {"$set": {"status": "active", "status_reason": None}}}[action]
    update["$set"]["updated_at"] = utcnow()
    await db.users.update_one({"_id": doc["_id"]}, update)
    await revoke_all_sessions(user_id)
    await audit(f"admin.access_{action}", "users", request=request, actor=admin, entity_id=user_id, reason=body.reason, roles=_row(doc)["roles"])
    return {"admin": _row(await db.users.find_one({"_id": doc["_id"]}) or doc)}


@router.post("/admin/team/{user_id}/revoke")
async def revoke(user_id: str, body: ConfirmIn, request: Request, admin: User = Depends(SUPER)):
    return await _access(user_id, body, request, admin, "revoke")


@router.post("/admin/team/{user_id}/suspend")
async def suspend(user_id: str, body: ConfirmIn, request: Request, admin: User = Depends(SUPER)):
    return await _access(user_id, body, request, admin, "suspend")


@router.post("/admin/team/{user_id}/reactivate")
async def reactivate(user_id: str, body: ConfirmIn, request: Request, admin: User = Depends(SUPER)):
    return await _access(user_id, body, request, admin, "reactivate")


__all__ = ["router", "decode_token"]
