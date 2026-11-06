from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.notify import CATEGORIES, prefs_of

router = APIRouter(tags=["notifications"])


class Channel(BaseModel):
    email: bool = True
    in_app: bool = True


class PrefsIn(BaseModel):
    orders: Channel
    messages: Channel
    reviews: Channel
    support: Channel
    vendor: Channel


def _out(n: dict) -> dict:
    return {"id": str(n["_id"]), "category": n["category"], "title": n["title"], "body": n["body"], "link": n["link"], "read": n["status"] == "read",
            "created_at": n["created_at"]}


@router.get("/notifications")
async def list_notifications(user: User = Depends(get_current_user)):
    q = {"user_id": ObjectId(user.id)}
    docs = await db.notifications.find(q).sort("created_at", -1).to_list(100)
    return {"data": [_out(n) for n in docs], "unread": await db.notifications.count_documents({**q, "status": "unread"})}


@router.get("/notifications/unread-count")
async def unread_count(user: User = Depends(get_current_user)):
    return {"unread": await db.notifications.count_documents({"user_id": ObjectId(user.id), "status": "unread"})}


@router.post("/notifications/{notification_id}/read")
async def mark_read(notification_id: str, user: User = Depends(get_current_user)):
    res = await db.notifications.update_one({"_id": ObjectId(notification_id), "user_id": ObjectId(user.id)} if ObjectId.is_valid(notification_id) else {"_id": None},
                                            {"$set": {"status": "read", "read_at": utcnow()}})
    if not res.matched_count:
        raise APIError(404, "not_found", "Notification not found.")
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all(user: User = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": ObjectId(user.id), "status": "unread"}, {"$set": {"status": "read", "read_at": utcnow()}})
    return {"ok": True}


@router.get("/notifications/preferences")
async def get_prefs(user: User = Depends(get_current_user)):
    u = await db.users.find_one({"_id": ObjectId(user.id)})
    return {"preferences": prefs_of(u), "labels": CATEGORIES,
            "always_sent": "Security, sign-in and payment receipt emails are always sent."}


@router.put("/notifications/preferences")
async def put_prefs(body: PrefsIn, request: Request, user: User = Depends(get_current_user)):
    prefs = body.model_dump()
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {"notification_prefs": prefs, "updated_at": utcnow()}})
    await audit("account.notification_prefs_updated", "users", request=request, actor=user, entity_id=user.id)
    return {"preferences": prefs}
