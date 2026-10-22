import secrets
from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from afrovending.core import email as mail
from afrovending.core.audit import audit
from afrovending.core.business_days import add_business_days
from afrovending.core.catalog import refresh_stock_flag
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow

DEFAULT_CONFIG = {"return_window_days": 14, "response_hours": 48, "escalate_to_admin": True,
                  "default_handling_days": 3, "min_handling_days": 1, "max_handling_days": 10, "non_business_days": [],
                  "reminder_hours_before": 24, "admin_escalation_hours": 48, "vendor_reminder": True,
                  "customer_overdue_email": True, "vendor_overdue_email": True, "escalate_overdue_to_admin": True}
HANDLING_ACTIVE = ("accepted", "processing")
TRANSITIONS = {
    "pending": {"accepted", "cancelled"},
    "accepted": {"processing", "partially_shipped", "shipped", "ready_for_pickup", "cancelled"},
    "processing": {"partially_shipped", "shipped", "ready_for_pickup", "cancelled"},
    "partially_shipped": {"partially_shipped", "shipped", "cancelled"},
    "shipped": {"delivered"},
    "ready_for_pickup": {"delivered"},
    "delivered": set(), "cancelled": set(),
}
CARRIERS = {"usps": ("USPS", "https://tools.usps.com/go/TrackConfirmAction?tLabels={}"),
            "ups": ("UPS", "https://www.ups.com/track?tracknum={}"),
            "fedex": ("FedEx", "https://www.fedex.com/fedextrack/?trknbr={}"),
            "dhl": ("DHL", "https://www.dhl.com/us-en/home/tracking.html?tracking-id={}"),
            "other": ("Other carrier", None)}
SHIPMENT_STATES = ("label_created", "in_transit", "out_for_delivery", "delivered", "exception")


class ManualLabelProvider:
    """Label abstraction. Manual = vendor buys postage elsewhere and enters tracking. Paid carrier APIs plug in here once approved."""
    name = "manual"

    async def create_label(self, *, carrier: str, tracking_number: str, **_) -> dict:
        label, url = CARRIERS.get(carrier, CARRIERS["other"])
        return {"provider": self.name, "carrier_name": label, "tracking_url": url.format(tracking_number) if url else None, "label_url": None}


LABELS = ManualLabelProvider()


async def get_config() -> dict:
    doc = await db.platform_settings.find_one({"key": "fulfillment.config"})
    return {**DEFAULT_CONFIG, **((doc or {}).get("value") or {})}


async def event(vo: dict, type: str, message: str, role: str, actor_id=None, customer_visible: bool = True, **meta) -> None:
    await db.order_events.insert_one({"order_id": vo["order_id"], "vendor_order_id": vo["_id"], "vendor_id": vo["vendor_id"], "type": type,
                                      "message": message, "actor_role": role, "actor_id": ObjectId(actor_id) if actor_id else None,
                                      "customer_visible": customer_visible, "meta": meta, "at": utcnow()})
    await audit(f"order.{type}", "vendor_orders", entity_id=str(vo["_id"]), role=role, message=message[:200])


async def notify_user(user_id, headline: str, text: str, path: str) -> None:
    u = await db.users.find_one({"_id": user_id})
    if u:
        subject, html = mail.payment_notice_email(u.get("first_name") or u.get("name") or "there", headline, text, path)
        await mail.try_send(to=u["email"], subject=subject, html=html)


async def notify_vendor(vendor_id, headline: str, text: str) -> None:
    v = await db.vendors.find_one({"_id": vendor_id})
    if v:
        await notify_user(v["owner_user_id"], headline, text, "/vendor/orders")


async def transition(vo: dict, to: str, role: str, actor_id=None, note: str = "", **sets) -> dict:
    """Atomic, validated status change: only succeeds if the order is still in the status we read."""
    if to not in TRANSITIONS.get(vo["status"], set()):
        raise APIError(409, "invalid_transition", f"An order that is {vo['status'].replace('_', ' ')} can't become {to.replace('_', ' ')}.")
    now = utcnow()
    updated = await db.vendor_orders.find_one_and_update({"_id": vo["_id"], "status": vo["status"]},
                                                         {"$set": {"status": to, f"{to}_at": now, "updated_at": now, **sets}},
                                                         return_document=ReturnDocument.AFTER)
    if not updated:
        raise APIError(409, "conflict", "This order changed at the same time. Refresh and try again.")
    await event(updated, f"status_{to}", note or f"Order {to.replace('_', ' ')}", role, actor_id)
    return updated


async def reserve(variant_id, qty: int) -> bool:
    res = await db.inventory.find_one_and_update(
        {"variant_id": variant_id, "$expr": {"$gte": [{"$subtract": ["$quantity_on_hand", {"$ifNull": ["$quantity_reserved", 0]}]}, qty]}},
        {"$inc": {"quantity_reserved": qty}, "$set": {"updated_at": utcnow()}})
    return bool(res)


async def release(variant_id, qty: int) -> None:
    inv = await db.inventory.find_one_and_update({"variant_id": variant_id, "quantity_reserved": {"$gte": qty}},
                                                 {"$inc": {"quantity_reserved": -qty}, "$set": {"updated_at": utcnow()}})
    if inv:
        await refresh_stock_flag(inv["product_id"])


async def fulfil(variant_id, qty: int, note: str) -> None:
    """Shipped units leave stock: on-hand and reserved both drop, with an append-only adjustment record."""
    inv = await db.inventory.find_one_and_update({"variant_id": variant_id, "quantity_reserved": {"$gte": qty}, "quantity_on_hand": {"$gte": qty}},
                                                 {"$inc": {"quantity_reserved": -qty, "quantity_on_hand": -qty}, "$set": {"updated_at": utcnow()}})
    if not inv:
        raise APIError(409, "stock_conflict", "Reserved stock for this item is missing. Contact AfroVending support.")
    await db.stock_adjustments.insert_one({"variant_id": variant_id, "product_id": inv["product_id"], "vendor_id": inv["vendor_id"], "delta": -qty,
                                           "before": inv["quantity_on_hand"], "after": inv["quantity_on_hand"] - qty, "reason": "fulfilled",
                                           "note": note, "actor_id": None, "created_at": utcnow()})
    await refresh_stock_flag(inv["product_id"])


async def cancel_vendor_order(vo: dict, role: str, actor_id, reason: str, key: str) -> dict:
    """Refund everything not yet shipped (incl. shipping), release reservations, mark cancelled. Idempotent by key."""
    from afrovending.core.payments import create_refund
    items = await db.order_items.find({"vendor_order_id": vo["_id"]}).to_list(100)
    lines = [(it["_id"], it["quantity"] - it["refunded_qty"]) for it in items if it["quantity"] - it["refunded_qty"] > 0]
    refund = await create_refund(vo, lines, include_shipping=True, reason=reason, key=key, actor_id=actor_id) if lines else None
    for it in items:
        left = it["quantity"] - it.get("shipped_qty", 0) - it.get("cancelled_qty", 0)
        if left > 0:
            await db.order_items.update_one({"_id": it["_id"]}, {"$inc": {"cancelled_qty": left}})
            await release(it["variant_id"], left)
    if vo["status"] != "cancelled":
        vo = await db.vendor_orders.find_one_and_update({"_id": vo["_id"], "status": {"$ne": "cancelled"}},
                                                        {"$set": {"status": "cancelled", "cancelled_at": utcnow(), "cancel_reason": reason}},
                                                        return_document=ReturnDocument.AFTER) or vo
        await event(vo, "cancelled", f"Cancelled: {reason}. Refund {'pending confirmation from Stripe' if refund else 'not needed'}.", role, actor_id)
        await notify_user(vo["customer_id"], "Order cancelled", f"Your items from {vo['vendor_name']} on order {vo['order_number']} were cancelled. "
                          "Your refund is being processed by Stripe; banks usually take 5–10 business days to show it.", f"/account/orders/{vo['order_id']}")
        await notify_vendor(vo["vendor_id"], "Order cancelled", f"Order {vo['order_number']} was cancelled ({reason}). Reserved stock was released.")
    return {"vendor_order": vo, "refund": refund}


def rma() -> str:
    return f"RMA-{secrets.token_hex(4).upper()}"


async def new_request(vo: dict, type: str, lines: list, reason: str, customer_id) -> dict:
    cfg = await get_config()
    now = utcnow()
    doc = {"type": type, "order_id": vo["order_id"], "vendor_order_id": vo["_id"], "vendor_id": vo["vendor_id"], "customer_id": customer_id,
           "order_number": vo["order_number"], "vendor_name": vo["vendor_name"], "lines": lines, "reason": reason, "status": "requested",
           "due_at": now + timedelta(hours=cfg["response_hours"]), "escalated": False, "rma_number": None, "refund_id": None,
           "history": [{"status": "requested", "role": "customer", "note": reason, "at": now}], "created_at": now, "updated_at": now}
    doc["_id"] = (await db.order_requests.insert_one(doc)).inserted_id
    return doc


async def move_request(req: dict, frm: tuple, to: str, role: str, actor_id, note: str, **sets) -> Optional[dict]:
    now = utcnow()
    return await db.order_requests.find_one_and_update(
        {"_id": req["_id"], "status": {"$in": list(frm)}},
        {"$set": {"status": to, "updated_at": now, **sets}, "$push": {"history": {"status": to, "role": role, "by": str(actor_id) if actor_id else None,
                                                                                    "note": note, "at": now}}}, return_document=ReturnDocument.AFTER)


def handling_snapshot(vo: dict, cfg: dict, now: datetime) -> dict:
    """Frozen on acceptance so later setting changes never move an existing order's deadline."""
    days = (vo.get("shipping_method") or {}).get("handling_days")
    days = int(cfg["default_handling_days"] if days is None else days)
    deadline = add_business_days(now, days, set(cfg["non_business_days"]))
    return {"days": days, "kind": "pickup" if vo.get("fulfillment_type") == "pickup" else "ship", "started_at": now,
            "deadline_at": deadline, "original_deadline_at": deadline, "non_business_days": list(cfg["non_business_days"]),
            "overdue": False, "extensions": []}


async def _once(key: str, vo: dict, kind: str) -> bool:
    try:
        await db.notification_log.insert_one({"key": key, "kind": kind, "vendor_order_id": vo["_id"], "vendor_id": vo["vendor_id"], "sent_at": utcnow()})
        return True
    except DuplicateKeyError:
        return False


def _day(d: datetime) -> str:
    return d.strftime("%a %b %d, %Y")


async def notify_admins(headline: str, text: str, path: str) -> None:
    async for admin in db.users.find({"roles": {"$in": ["marketplace_admin", "super_admin"]}, "status": "active"}):
        await notify_user(admin["_id"], headline, text, path)


async def handling_alerts() -> dict:
    """Hourly. Every email is guarded by a unique notification_log key tied to the current deadline, so it sends once."""
    cfg = await get_config()
    now = utcnow()
    out = {"reminders": 0, "overdue": 0, "escalations": 0}
    async for vo in db.vendor_orders.find({"status": {"$in": list(HANDLING_ACTIVE)}, "handling.deadline_at": {"$ne": None}}):
        h = vo["handling"]
        dl, pickup, vid = h["deadline_at"], h["kind"] == "pickup", str(vo["_id"])
        tag, task = dl.isoformat(), ("get it ready for pickup" if h["kind"] == "pickup" else "ship it")
        if now < dl:
            if cfg["vendor_reminder"] and dl - now <= timedelta(hours=cfg["reminder_hours_before"]) and await _once(f"{vid}:reminder:{tag}", vo, "reminder"):
                await notify_vendor(vo["vendor_id"], "Handling deadline approaching",
                                    f"Order {vo['order_number']} must be {'ready for pickup' if pickup else 'shipped'} by {_day(dl)}. Please {task} or update its status.")
                out["reminders"] += 1
            continue
        if not h.get("overdue"):
            await db.vendor_orders.update_one({"_id": vo["_id"], "handling.deadline_at": dl}, {"$set": {"handling.overdue": True, "handling.overdue_since": now}})
            await event(vo, "handling_overdue", "Pickup preparation is taking longer than expected" if pickup else "Shipping is taking longer than expected", "system")
            out["overdue"] += 1
        status = vo["status"].replace("_", " ")
        if cfg["customer_overdue_email"] and await _once(f"{vid}:overdue_customer:{tag}", vo, "overdue_customer"):
            if pickup:
                text = (f"We're sorry — your pickup order {vo['order_number']} from {vo['vendor_name']} isn't ready yet. It was expected to be ready by "
                        f"{_day(dl)}. Current status: {status}. We've asked the seller to prepare it right away; we'll email you when it's ready to collect.")
            else:
                text = (f"We're sorry — {vo['vendor_name']} hasn't shipped your items from order {vo['order_number']} yet. They were expected to ship by "
                        f"{_day(dl)}. Current status: {status}. We've asked the seller to ship right away or send you an update. You can track the order here.")
            await notify_user(vo["customer_id"], "Pickup delayed" if pickup else "Your order is delayed", text, f"/account/orders/{vo['order_id']}")
        if cfg["vendor_overdue_email"] and await _once(f"{vid}:overdue_vendor:{tag}", vo, "overdue_vendor"):
            await notify_vendor(vo["vendor_id"], "Order overdue", f"Order {vo['order_number']} passed its handling deadline ({_day(dl)}). The customer has been told. "
                                f"Please {task} now or update the order status.")
        if cfg["escalate_overdue_to_admin"] and now - dl >= timedelta(hours=cfg["admin_escalation_hours"]) \
                and await _once(f"{vid}:overdue_admin:{tag}", vo, "overdue_admin"):
            await notify_admins("Overdue order escalation", f"Order {vo['order_number']} from {vo['vendor_name']} has been overdue for more than "
                                f"{cfg['admin_escalation_hours']} hours ({'pickup preparation' if pickup else 'shipment'}).", "/admin/fulfillment")
            out["escalations"] += 1
    return out


async def escalate_overdue() -> dict:
    cfg = await get_config()
    if not cfg["escalate_to_admin"]:
        return {"escalated": 0}
    n = 0
    async for r in db.order_requests.find({"status": "requested", "escalated": False, "due_at": {"$lt": utcnow()}}):
        await db.order_requests.update_one({"_id": r["_id"]}, {"$set": {"escalated": True, "escalated_at": utcnow()}})
        n += 1
    if n:
        await notify_admins("Requests need attention", f"{n} cancellation/return request(s) passed the vendor response deadline.", "/admin/fulfillment")
    return {"escalated": n}
