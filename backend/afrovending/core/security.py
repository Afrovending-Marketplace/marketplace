import hashlib
import re
import secrets
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Request, Response

from afrovending.core.config import settings
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow

JWT_ALGORITHM = "HS256"
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=7)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def password_problem(password: str, strong: bool = False) -> str | None:
    if len(password) > 128:
        return "Password must be at most 128 characters."
    if strong:
        ok = len(password) >= 14 and all(re.search(p, password) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
        return None if ok else "Admin passwords need 14+ characters with upper, lower, number and symbol."
    if len(password) < 10 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must be at least 10 characters and include a letter and a number."
    return None


def require_valid_password(password: str, strong: bool = False) -> None:
    problem = password_problem(password, strong)
    if problem:
        raise APIError(422, "validation_error", problem, [{"field": "password", "message": problem}])


def create_token(user_id: str, sid: str, kind: str, ttl: timedelta) -> str:
    payload = {"sub": user_id, "sid": sid, "type": kind, "exp": utcnow() + ttl, "iat": utcnow()}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str, kind: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise APIError(401, "token_expired", "Your session has expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise APIError(401, "unauthorized", "Invalid session.")
    if payload.get("type") != kind:
        raise APIError(401, "unauthorized", "Invalid session.")
    return payload


def new_opaque_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def set_auth_cookies(response: Response, access: str, refresh: str | None = None) -> None:
    opts = {"httponly": True, "secure": True, "samesite": "none", "path": "/"}
    response.set_cookie("access_token", access, max_age=int(ACCESS_TTL.total_seconds()), **opts)
    if refresh:
        response.set_cookie("refresh_token", refresh, max_age=int(REFRESH_TTL.total_seconds()), **opts)


def clear_auth_cookies(response: Response) -> None:
    for name in ("access_token", "refresh_token"):
        response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="none")
