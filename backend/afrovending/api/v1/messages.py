"""Customer–vendor messages tied to one vendor order. Contact details and outside links are masked for recipients; originals are visible only to moderators."""
import hashlib
from datetime import timedelta
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from afrovending.core import moderation as mod
from afrovending.core import rate_limit
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.notify import notify
from afrovending.core.permissions import MSG_REVIEW, require_perm

router = APIRouter(tags=["messages"])
NOTICE = "Some contact details or links were hidden under AfroVending's marketplace communication policy. Please keep conversations and payments on AfroVending."
HELD = "This message is being reviewed by AfroVending before delivery."


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ReviewIn(BaseModel):
    action: Literal["dismiss", "confirm", "hide"]
    note: str = Field(min_length=3, max_length=300)


def _oid(v: str) -> ObjectId:
    if not ObjectId.is_valid(v):
        raise APIError(404, "not_found", "Order not found.")
    return ObjectId(v)


def _view(m: dict, me: str) -> dict:
    mine = m["sender_role"] == me
    hidden = m.get("hidden") or (m.get("held") and m.get("review_status") == "open")
    body = m["body_display"] if mine or not hidden else HELD
    if m.get("hidden") and mine:
        body = "This message was removed by AfroVending for breaking the marketplace communication policy."
    return {"id": str(m["_id"]), "sender_role": m["sender_role"], "sender_name": m["sender_name"], "body": body, "created_at": m["created_at"],
            "mine": mine, "notice": NOTICE if mine and m.get("flags") else None, "held": bool(hidden)}


async def _thread(vo: dict, me: str) -> dict:
    msgs = await db.order_messages.find({"vendor_order_id": vo["_id"]}).sort("created_at", 1).to_list(500)
    await db.order_messages.update_many({"vendor_order_id": vo["_id"], "sender_role": {"$ne": me}, f"read_by_{me}": {"$ne": True}}, {"$set": {f"read_by_{me}": True}})
    return {"vendor_order_id": str(vo["_id"]), "order_number": vo["order_number"], "messages": [_view(m, me) for m in msgs],
            "policy": "Messages are for this order only. Phone numbers, email addresses, outside links and payment requests are hidden automatically."}


async def _post(vo: dict, me: str, user: User, body: MessageIn, request: Request, sender_name: str) -> dict:
    await rate_limit.hit(f"msg:{user.id}:{vo['_id']}", 20, 3600, message="You're sending messages very quickly. Please wait a little and try again.")
    await rate_limit.hit(f"msg-day:{user.id}", 150, 86400, message="Daily message limit reached. Please try again tomorrow.")
    text = mod.sanitize(body.body, 2000)
    if not text:
        raise APIError(422, "validation_error", "Write a message first.")
    h = hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()
    if await db.order_messages.find_one({"sender_id": ObjectId(user.id), "body_hash": h, "created_at": {"$gte": utcnow() - timedelta(minutes=10)}}):
        raise APIError(429, "rate_limited", "You just sent this same message. Please don't repeat it.")
    s = mod.scan(text, await mod.rules())
    m = {"vendor_order_id": vo["_id"], "order_id": vo["order_id"], "vendor_id": vo["vendor_id"], "customer_id": vo["customer_id"], "sender_role": me,
         "sender_id": ObjectId(user.id), "sender_name": sender_name, "body_original": text, "body_display": s["masked"], "body_hash": h, "flags": s["flags"],
         "held": s["high"], "hidden": False, "review_status": "open" if s["flags"] else "none", "created_at": utcnow()}
    m["_id"] = (await db.order_messages.insert_one(m)).inserted_id
    if s["flags"]:
        await audit("message.flagged", "order_messages", request=request, actor=user, entity_id=str(m["_id"]), flags=s["flags"], held=s["high"])
    if not s["high"]:
        await _notify_recipient(vo, me)
    return _view(m, me)


async def _notify_recipient(vo: dict, sender_role: str) -> None:
    """No message content in notifications or email previews — recipients open the order to read."""
    if sender_role == "customer":
        v = await db.vendors.find_one({"_id": vo["vendor_id"]})
        if v:
            await notify(v["owner_user_id"], "messages", f"New customer message · {vo['order_number']}", "A customer sent you a message about this order.", "/vendor/orders")
    else:
        await notify(vo["customer_id"], "messages", f"New message from {vo.get('vendor_name') or 'the seller'}",
                     f"You have a new message about order {vo['order_number']}.", f"/account/orders/{vo['order_id']}")


async def _customer_vo(order_id: str, vo_id: str, user: User) -> dict:
    vo = await db.vendor_orders.find_one({"_id": _oid(vo_id), "order_id": _oid(order_id), "customer_id": ObjectId(user.id)})
    if not vo:
        raise APIError(404, "not_found", "Order not found.")
    return vo


async def _vendor_vo(vo_id: str, user: User) -> dict:
    from afrovending.api.v1.vendors import my_vendor
    v = await my_vendor(user)
    vo = await db.vendor_orders.find_one({"_id": _oid(vo_id), "vendor_id": v["_id"]})
    if not vo:
        raise APIError(404, "not_found", "Order not found.")
    return vo


@router.get("/orders/{order_id}/vendor-orders/{vo_id}/messages")
async def customer_thread(order_id: str, vo_id: str, user: User = Depends(get_current_user)):
    return await _thread(await _customer_vo(order_id, vo_id, user), "customer")


@router.post("/orders/{order_id}/vendor-orders/{vo_id}/messages", status_code=201)
async def customer_send(order_id: str, vo_id: str, body: MessageIn, request: Request, user: User = Depends(get_current_user)):
    vo = await _customer_vo(order_id, vo_id, user)
    first = (user.name or "Customer").split()[0]
    return {"message": await _post(vo, "customer", user, body, request, first)}


@router.get("/vendor/orders/{vo_id}/messages")
async def vendor_thread(vo_id: str, user: User = Depends(get_current_user)):
    return await _thread(await _vendor_vo(vo_id, user), "vendor")


@router.post("/vendor/orders/{vo_id}/messages", status_code=201)
async def vendor_send(vo_id: str, body: MessageIn, request: Request, user: User = Depends(get_current_user)):
    vo = await _vendor_vo(vo_id, user)
    return {"message": await _post(vo, "vendor", user, body, request, vo.get("vendor_name") or "Seller")}


@router.get("/vendor/messages/unread")
async def vendor_unread(user: User = Depends(get_current_user)):
    from afrovending.api.v1.vendors import my_vendor
    v = await my_vendor(user)
    rows = await db.order_messages.aggregate([{"$match": {"vendor_id": v["_id"], "sender_role": "customer", "read_by_vendor": {"$ne": True}}},
                                              {"$group": {"_id": "$vendor_order_id", "n": {"$sum": 1}}}]).to_list(500)
    return {"by_vendor_order": {str(r["_id"]): r["n"] for r in rows}}


@router.get("/admin/messages/flagged")
async def flagged(status: Literal["open", "dismissed", "confirmed", "hidden", "all"] = "open", _: User = Depends(require_perm(MSG_REVIEW))):
    q = {"review_status": {"$ne": "none"}} if status == "all" else {"review_status": status}
    docs = await db.order_messages.find(q).sort("created_at", -1).to_list(300)
    vos = {v["_id"]: v for v in await db.vendor_orders.find({"_id": {"$in": list({d["vendor_order_id"] for d in docs})}}, {"order_number": 1, "vendor_name": 1}).to_list(300)}
    return {"data": [{"id": str(d["_id"]), "order_number": vos.get(d["vendor_order_id"], {}).get("order_number"), "vendor_name": vos.get(d["vendor_order_id"], {}).get("vendor_name"),
                      "sender_role": d["sender_role"], "sender_name": d["sender_name"], "original": d["body_original"], "shown": d["body_display"],
                      "flags": d["flags"], "held": d["held"], "hidden": d.get("hidden", False), "review_status": d["review_status"], "created_at": d["created_at"],
                      "review_note": d.get("review_note")} for d in docs]}


@router.post("/admin/messages/{message_id}/review")
async def review_message(message_id: str, body: ReviewIn, request: Request, admin: User = Depends(require_perm(MSG_REVIEW))):
    """dismiss = false positive (held messages are delivered, masked); confirm = violation noted, stays masked; hide = removed for the recipient."""
    m = await db.order_messages.find_one({"_id": _oid(message_id), "review_status": {"$ne": "none"}})
    if not m:
        raise APIError(404, "not_found", "Message not found.")
    status = {"dismiss": "dismissed", "confirm": "confirmed", "hide": "hidden"}[body.action]
    await db.order_messages.update_one({"_id": m["_id"]}, {"$set": {"review_status": status, "hidden": body.action == "hide", "held": False if body.action != "hide" else m["held"],
                                                                   "review_note": mod.sanitize(body.note, 300), "reviewed_by": ObjectId(admin.id), "reviewed_at": utcnow()}})
    await audit(f"message.review_{body.action}", "order_messages", request=request, actor=admin, entity_id=message_id, note=body.note[:300])
    if m["held"] and body.action != "hide":
        await _notify_recipient(await db.vendor_orders.find_one({"_id": m["vendor_order_id"]}), m["sender_role"])
    return {"ok": True, "review_status": status}
