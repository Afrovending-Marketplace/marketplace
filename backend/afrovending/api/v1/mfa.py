import pyotp
from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from afrovending.core import rate_limit
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.permissions import is_admin, perms_of

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])


class CodeIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


async def _check(user_id: str, secret: str, code: str) -> None:
    key = f"mfa:{user_id}"
    if await rate_limit.count(key) >= 5:
        raise APIError(429, "rate_limited", "Too many incorrect codes. Try again in 15 minutes.")
    totp = pyotp.TOTP(secret)
    doc = await db.users.find_one({"_id": ObjectId(user_id)}, {"mfa_last_step": 1})
    step = next((s for s in (totp.timecode(utcnow()) + d for d in (0, -1, 1)) if hmac_ok(totp, code, s)), None)
    if step is None or step <= (doc or {}).get("mfa_last_step", -1):
        await rate_limit.hit(key, 5, 900, raise_over=False)
        raise APIError(422, "invalid_code", "That code is incorrect or already used.")
    await rate_limit.reset(key)
    await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"mfa_last_step": step}})


def hmac_ok(totp: pyotp.TOTP, code: str, step: int) -> bool:
    import hmac
    return hmac.compare_digest(totp.generate_otp(step), code)


async def _mark_session(request: Request) -> None:
    await db.sessions.update_one({"_id": ObjectId(request.state.session_id)}, {"$set": {"mfa_verified": True, "mfa_verified_at": utcnow()}})


@router.get("")
async def status(request: Request, user: User = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user.id)}, {"mfa_enabled_at": 1})
    return {"required": is_admin(user), "enrolled": bool(doc.get("mfa_enabled_at")), "verified": request.state.mfa_verified,
            "permissions": sorted(perms_of(user.roles))}


@router.post("/setup")
async def setup(user: User = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user.id)}, {"mfa_enabled_at": 1})
    if doc.get("mfa_enabled_at"):
        raise APIError(409, "conflict", "Two-step sign-in is already set up.")
    secret = pyotp.random_base32()
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {"mfa_pending_secret": secret}})
    return {"secret": secret, "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="AfroVending")}


@router.post("/enable")
async def enable(body: CodeIn, request: Request, user: User = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user.id)}, {"mfa_pending_secret": 1, "mfa_enabled_at": 1})
    if doc.get("mfa_enabled_at") or not doc.get("mfa_pending_secret"):
        raise APIError(409, "conflict", "Start setup first.")
    await _check(user.id, doc["mfa_pending_secret"], body.code)
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {"mfa_secret": doc["mfa_pending_secret"], "mfa_enabled_at": utcnow()},
                                                            "$unset": {"mfa_pending_secret": ""}})
    await _mark_session(request)
    await audit("auth.mfa_enabled", "users", request=request, actor=user, entity_id=user.id)
    return {"enrolled": True, "verified": True}


@router.post("/verify")
async def verify(body: CodeIn, request: Request, user: User = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user.id)}, {"mfa_secret": 1})
    if not doc.get("mfa_secret"):
        raise APIError(409, "mfa_not_enrolled", "Set up two-step sign-in first.")
    await _check(user.id, doc["mfa_secret"], body.code)
    await _mark_session(request)
    await audit("auth.mfa_verified", "users", request=request, actor=user, entity_id=user.id)
    return {"verified": True}
