from bson import ObjectId
from fastapi import Depends, Request

from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import User
from afrovending.core.roles import Role
from afrovending.core.security import decode_token

INACTIVE = {"suspended", "deactivated"}


async def get_current_user(request: Request) -> User:
    token = request.cookies.get("access_token")
    auth = request.headers.get("authorization", "")
    if not token and auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise APIError(401, "unauthorized", "Please sign in to continue.")
    payload = decode_token(token, "access")
    session = await db.sessions.find_one({"_id": ObjectId(payload["sid"]), "status": "active"})
    if not session:
        raise APIError(401, "unauthorized", "Your session has ended. Please sign in again.")
    doc = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not doc or doc["status"] in INACTIVE:
        raise APIError(401, "unauthorized", "Please sign in to continue.")
    request.state.session_id = payload["sid"]
    request.state.mfa_verified = bool(session.get("mfa_verified"))
    return User.from_mongo(doc)


async def get_optional_user(request: Request):
    if not request.cookies.get("access_token") and not request.headers.get("authorization", "").startswith("Bearer "):
        return None
    try:
        return await get_current_user(request)
    except APIError:
        return None


def require_roles(*roles: Role):
    allowed = {r.value for r in roles}

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if not allowed & set(user.roles):
            raise APIError(403, "forbidden", "You do not have permission to perform this action.")
        return user

    return _dep
