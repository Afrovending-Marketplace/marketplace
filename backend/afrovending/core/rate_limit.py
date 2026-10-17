from datetime import timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow

DEFAULT_MSG = "Too many attempts. Please wait a few minutes and try again."


async def count(key: str) -> int:
    doc = await db.rate_limits.find_one({"key": key, "expires_at": {"$gt": utcnow()}})
    return doc["count"] if doc else 0


async def hit(key: str, limit: int, window_s: int, raise_over: bool = True, message: str = DEFAULT_MSG) -> int:
    now = utcnow()
    doc = await db.rate_limits.find_one_and_update(
        {"key": key, "expires_at": {"$gt": now}}, {"$inc": {"count": 1}}, return_document=ReturnDocument.AFTER
    )
    if doc:
        n = doc["count"]
    else:
        fresh = {"count": 1, "expires_at": now + timedelta(seconds=window_s)}
        try:
            await db.rate_limits.insert_one({"key": key, **fresh})
        except DuplicateKeyError:
            await db.rate_limits.update_one({"key": key}, {"$set": fresh})
        n = 1
    if raise_over and n > limit:
        raise APIError(429, "rate_limited", message)
    return n


async def reset(key: str) -> None:
    await db.rate_limits.delete_one({"key": key})
