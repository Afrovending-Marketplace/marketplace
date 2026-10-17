from bson import ObjectId
from fastapi import Request, Response

from afrovending.core.db import db
from afrovending.core.models import User, utcnow
from afrovending.core.security import ACCESS_TTL, REFRESH_TTL, client_ip, create_token, set_auth_cookies


async def start_session(response: Response, user: User, request: Request) -> None:
    now = utcnow()
    res = await db.sessions.insert_one({
        "user_id": ObjectId(user.id), "status": "active", "created_at": now, "last_used_at": now,
        "expires_at": now + REFRESH_TTL, "ip": client_ip(request), "user_agent": request.headers.get("user-agent", "")[:200],
    })
    sid = str(res.inserted_id)
    set_auth_cookies(response, create_token(user.id, sid, "access", ACCESS_TTL), create_token(user.id, sid, "refresh", REFRESH_TTL))


async def revoke_session(sid: str) -> None:
    await db.sessions.update_one({"_id": ObjectId(sid)}, {"$set": {"status": "revoked", "revoked_at": utcnow()}})


async def revoke_all_sessions(user_id: str, except_sid: str | None = None) -> None:
    query = {"user_id": ObjectId(user_id), "status": "active"}
    if except_sid:
        query["_id"] = {"$ne": ObjectId(except_sid)}
    await db.sessions.update_many(query, {"$set": {"status": "revoked", "revoked_at": utcnow()}})


async def issue_token(user_id: str, purpose: str, ttl, token_hash: str) -> None:
    await db.auth_tokens.update_many({"user_id": ObjectId(user_id), "purpose": purpose, "used_at": None},
                                     {"$set": {"used_at": utcnow(), "superseded": True}})
    await db.auth_tokens.insert_one({"user_id": ObjectId(user_id), "purpose": purpose, "token_hash": token_hash,
                                     "created_at": utcnow(), "expires_at": utcnow() + ttl, "used_at": None})


async def consume_token(purpose: str, token_hash: str) -> dict | None:
    return await db.auth_tokens.find_one_and_update(
        {"purpose": purpose, "token_hash": token_hash, "used_at": None, "expires_at": {"$gt": utcnow()}},
        {"$set": {"used_at": utcnow()}},
    )
