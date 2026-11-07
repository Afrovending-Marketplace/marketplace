from datetime import timedelta

from bson import ObjectId
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field

from afrovending.core import email as mail
from afrovending.core import rate_limit
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import INACTIVE, get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.security import (ACCESS_TTL, client_ip, clear_auth_cookies, create_token, decode_token, hash_password,
                                       hash_token, new_opaque_token, require_valid_password, set_auth_cookies, verify_password)
from afrovending.core.sessions import consume_token, issue_token, revoke_all_sessions, revoke_session, start_session

router = APIRouter(prefix="/auth", tags=["auth"])
LOGIN_LIMIT, LOGIN_WINDOW = 5, 15 * 60
ACCOUNT_LOGIN_LIMIT = 20


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str
    marketing_opt_in: bool = False
    referral_code: str = Field(default="", max_length=20)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class ResetIn(TokenIn):
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


async def _send_verification(user: User) -> bool:
    raw, hashed = new_opaque_token()
    await issue_token(user.id, "verify_email", timedelta(hours=24), hashed)
    subject, html = mail.verification_email(user.name, raw)
    return await mail.try_send(to=user.email, subject=subject, html=html)


@router.post("/register", status_code=201)
async def register(body: RegisterIn, request: Request, response: Response):
    await rate_limit.hit(f"register:{client_ip(request)}", 10, 3600)
    require_valid_password(body.password)
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise APIError(409, "conflict", "An account with this email already exists. Try signing in.")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password),
                auth_providers=[{"provider": "password", "linked_at": utcnow()}])
    user.id = str((await db.users.insert_one(user.to_mongo())).inserted_id)
    from afrovending.core import marketing as mk
    if body.marketing_opt_in:
        await mk.set_consent(ObjectId(user.id), True, "registration")
    await mk.attribute_signup(ObjectId(user.id), body.referral_code, email)
    sent = await _send_verification(user)
    await start_session(response, user, request)
    await audit("auth.register", "users", request=request, actor=user, entity_id=user.id, verification_email_sent=sent)
    return {"user": user.public(), "verification_email_sent": sent}


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.lower()
    key = f"login:{client_ip(request)}:{email}"
    account_key = f"login-account:{email}"
    if await rate_limit.count(key) >= LOGIN_LIMIT or await rate_limit.count(account_key) >= ACCOUNT_LOGIN_LIMIT:
        raise APIError(429, "rate_limited", "Too many failed sign-in attempts. Try again in 15 minutes.")
    doc = await db.users.find_one({"email": email})
    if not doc or not doc.get("password_hash") or not verify_password(body.password, doc["password_hash"]):
        await rate_limit.hit(key, LOGIN_LIMIT, LOGIN_WINDOW, raise_over=False)
        await rate_limit.hit(account_key, ACCOUNT_LOGIN_LIMIT, LOGIN_WINDOW, raise_over=False)
        await audit("auth.login_failed", "users", request=request, entity_id=str(doc["_id"]) if doc else None, email=email)
        raise APIError(401, "invalid_credentials", "Incorrect email or password.")
    user = User.from_mongo(doc)
    if user.status in INACTIVE:
        raise APIError(403, "account_inactive", "This account is deactivated. Contact support to restore it.")
    await rate_limit.reset(key)
    await rate_limit.reset(account_key)
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {"last_login_at": utcnow()}})
    await start_session(response, user, request)
    await audit("auth.login", "users", request=request, actor=user, entity_id=user.id)
    return {"user": user.public()}


@router.post("/logout")
async def logout(request: Request, response: Response):
    for name, kind in (("access_token", "access"), ("refresh_token", "refresh")):
        token = request.cookies.get(name)
        if token:
            try:
                await revoke_session(decode_token(token, kind)["sid"])
                break
            except APIError:
                continue
    clear_auth_cookies(response)
    return {"status": "signed_out"}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise APIError(401, "unauthorized", "Please sign in to continue.")
    payload = decode_token(token, "refresh")
    session = await db.sessions.find_one({"_id": ObjectId(payload["sid"]), "status": "active", "expires_at": {"$gt": utcnow()}})
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not session or not user or user["status"] in INACTIVE:
        clear_auth_cookies(response)
        raise APIError(401, "unauthorized", "Your session has ended. Please sign in again.")
    await db.sessions.update_one({"_id": session["_id"]}, {"$set": {"last_used_at": utcnow()}})
    set_auth_cookies(response, create_token(payload["sub"], payload["sid"], "access", ACCESS_TTL))
    return {"user": User.from_mongo(user).public()}


@router.get("/me")
async def me(request: Request, user: User = Depends(get_current_user)):
    from afrovending.core.permissions import is_admin, perms_of
    return {"user": {**user.public(), "permissions": sorted(perms_of(user.roles)), "is_admin": is_admin(user), "mfa_verified": request.state.mfa_verified}}


@router.post("/verify-email")
async def verify_email(body: TokenIn, request: Request):
    await rate_limit.hit(f"verify:{client_ip(request)}", 20, 3600)
    tok = await consume_token("verify_email", hash_token(body.token))
    if not tok:
        raise APIError(400, "invalid_token", "This verification link is invalid or has expired.")
    await db.users.update_one({"_id": tok["user_id"], "status": "pending_verification"}, {"$set": {"status": "active"}})
    await db.users.update_one({"_id": tok["user_id"]}, {"$set": {"email_verified_at": utcnow(), "updated_at": utcnow()}})
    await audit("auth.email_verified", "users", request=request, entity_id=str(tok["user_id"]))
    return {"status": "verified"}


@router.post("/resend-verification")
async def resend_verification(request: Request, user: User = Depends(get_current_user)):
    if user.email_verified_at:
        return {"status": "already_verified"}
    await rate_limit.hit(f"resend:{user.id}", 3, 3600)
    sent = await _send_verification(user)
    if not sent:
        raise APIError(503, "email_unavailable", "We couldn't send the email right now. Please try again later.")
    return {"status": "sent"}


@router.post("/forgot-password")
async def forgot_password(body: EmailIn, request: Request):
    email = body.email.lower()
    await rate_limit.hit(f"forgot:{client_ip(request)}", 10, 3600)
    if await rate_limit.hit(f"forgot:{email}", 3, 3600, raise_over=False) <= 3:
        doc = await db.users.find_one({"email": email})
        if doc and doc.get("password_hash") and doc["status"] not in INACTIVE:
            user = User.from_mongo(doc)
            raw, hashed = new_opaque_token()
            await issue_token(user.id, "reset_password", timedelta(hours=1), hashed)
            subject, html = mail.reset_email(user.name, raw)
            await mail.try_send(to=user.email, subject=subject, html=html)
            await audit("auth.password_reset_requested", "users", request=request, entity_id=user.id)
    return {"status": "ok", "message": "If an account exists for that email, a reset link is on its way."}


@router.post("/reset-password")
async def reset_password(body: ResetIn, request: Request, response: Response):
    await rate_limit.hit(f"reset:{client_ip(request)}", 10, 3600)
    require_valid_password(body.password)
    tok = await consume_token("reset_password", hash_token(body.token))
    if not tok:
        raise APIError(400, "invalid_token", "This reset link is invalid or has expired. Request a new one.")
    doc = await db.users.find_one_and_update({"_id": tok["user_id"]},
                                             {"$set": {"password_hash": hash_password(body.password), "updated_at": utcnow()}})
    await revoke_all_sessions(str(tok["user_id"]))
    clear_auth_cookies(response)
    await audit("auth.password_reset", "users", request=request, entity_id=str(tok["user_id"]))
    subject, html = mail.security_notice_email(doc["name"], "Your AfroVending password was just reset and all devices were signed out.")
    await mail.try_send(to=doc["email"], subject=subject, html=html)
    return {"status": "password_reset"}


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(get_current_user)):
    await rate_limit.hit(f"change-pw:{user.id}", 5, 900)
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise APIError(400, "invalid_credentials", "Your current password is incorrect.")
    require_valid_password(body.new_password, strong=any(r.endswith("admin") for r in user.roles))
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {"password_hash": hash_password(body.new_password), "updated_at": utcnow()}})
    await revoke_all_sessions(user.id, except_sid=request.state.session_id)
    await audit("auth.password_changed", "users", request=request, actor=user, entity_id=user.id)
    subject, html = mail.security_notice_email(user.name, "Your AfroVending password was changed. Other devices were signed out.")
    await mail.try_send(to=user.email, subject=subject, html=html)
    return {"status": "password_changed"}
