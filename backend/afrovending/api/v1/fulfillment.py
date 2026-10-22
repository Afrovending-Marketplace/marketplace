from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from afrovending.api.v1.vendors import my_vendor, ser
from afrovending.core import fulfillment as ff
from afrovending.core import ledger
from afrovending.core.catalog import adjust_stock, oid
from afrovending.core.db import db
from afrovending.core.deps import get_current_user, require_roles
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.payments import create_refund
from afrovending.core.roles import Role

router = APIRouter(tags=["fulfillment"])
ADMIN = require_roles(Role.MARKETPLACE_ADMIN, Role.SUPER_ADMIN)
OPEN_REQ = ("requested", "approved")


class Line(BaseModel):
    order_item_id: str
    quantity: int = Field(ge=1, le=100)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ReturnIn(ReasonIn):
    lines: list[Line] = Field(min_length=1, max_length=50)


class StatusIn(BaseModel):
    to: Literal["accepted", "processing", "ready_for_pickup", "delivered"]
    note: str = Field(default="", max_length=300)


class ShipmentIn(BaseModel):
    lines: list[Line] = Field(min_length=1, max_length=50)
    carrier: Literal["usps", "ups", "fedex", "dhl", "other"]
    tracking_number: str = Field(min_length=4, max_length=60, pattern=r"^[A-Za-z0-9 -]+$")


class ShipStatusIn(BaseModel):
    status: Literal["in_transit", "out_for_delivery", "delivered", "exception"]
    note: str = Field(default="", max_length=300)


class DecideIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=500)


class ReceiveIn(BaseModel):
    restock: bool = True


class MethodIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    type: Literal["ship", "pickup"] = "ship"
    amount_minor: int = Field(ge=0, le=1_000_000)
    eta: str = Field(default="", max_length=80)
    free_over_minor: Optional[int] = Field(default=None, ge=0)
    pickup_address: str = Field(default="", max_length=200)
    status: Literal["active", "inactive"] = "active"


class ReturnsFlagIn(BaseModel):
    returns_accepted: bool


class ConfigIn(BaseModel):
    return_window_days: int = Field(ge=0, le=365)
    response_hours: int = Field(ge=1, le=720)
    escalate_to_admin: bool = True


async def _detail(vo: dict, customer: bool) -> dict:
    items = await db.order_items.find({"vendor_order_id": vo["_id"]}).to_list(100)
    ships = await db.shipments.find({"vendor_order_id": vo["_id"]}).sort("created_at", 1).to_list(50)
    reqs = await db.order_requests.find({"vendor_order_id": vo["_id"]}).sort("created_at", -1).to_list(50)
    refunds = await db.refunds.find({"vendor_order_id": vo["_id"]}).to_list(50)
    q = {"vendor_order_id": vo["_id"], **({"customer_visible": True} if customer else {})}
    events = await db.order_events.find(q).sort("at", 1).to_list(200)
    keys = ("order_number", "vendor_name", "vendor_slug", "status", "fulfillment_type", "shipping_method", "shipping_address", "items_net_minor",
            "shipping_minor", "tax_minor", "charged_minor", "refunded_minor", "created_at", "delivered_at", "cancelled_at", "order_id")
    return {"id": str(vo["_id"]), **ser({k: vo.get(k) for k in keys}),
            "items": [ser({k: i.get(k) for k in ("_id", "title", "label", "sku", "quantity", "unit_price_minor", "line_total_minor", "shipped_qty",
                                                  "cancelled_qty", "returned_qty", "refunded_qty", "product_id")}) for i in items],
            "shipments": [ser({k: s.get(k) for k in ("_id", "carrier_name", "tracking_number", "tracking_url", "status", "lines", "created_at")}) for s in ships],
            "requests": [ser({k: r.get(k) for k in ("_id", "type", "status", "reason", "lines", "rma_number", "due_at", "escalated", "history", "created_at")}) for r in reqs],
            "refunds": [{"amount_minor": r["amount_minor"], "status": r["status"], "created_at": r["created_at"].isoformat()} for r in refunds],
            "events": [{"type": e["type"], "message": e["message"], "role": e["actor_role"], "at": e["at"].isoformat()} for e in events]}


async def _customer_vo(order_id: str, vo_id: str, user: User) -> dict:
    vo = await db.vendor_orders.find_one({"_id": oid(vo_id), "order_id": oid(order_id), "customer_id": ObjectId(user.id)})
    if not vo:
        raise APIError(404, "not_found", "Order not found.")
    return vo


@router.get("/orders/{order_id}/detail")
async def order_detail(order_id: str, user: User = Depends(get_current_user)):
    order = await db.orders.find_one({"_id": oid(order_id), "customer_id": ObjectId(user.id)})
    if not order:
        raise APIError(404, "not_found", "Order not found.")
    vos = await db.vendor_orders.find({"order_id": order["_id"]}).to_list(50)
    cfg = await ff.get_config()
    return {"order": {"id": order_id, "order_number": order["order_number"], "status": order["status"], "totals": order["totals"],
                      "shipping_address": order["shipping_address"], "paid_at": order.get("paid_at")},
            "vendor_orders": [await _detail(v, True) for v in vos], "return_window_days": cfg["return_window_days"]}


@router.post("/orders/{order_id}/vendor-orders/{vo_id}/cancel")
async def customer_cancel(order_id: str, vo_id: str, body: ReasonIn, idempotency_key: str = Header(default="", alias="Idempotency-Key"),
                          user: User = Depends(get_current_user)):
    if not 8 <= len(idempotency_key) <= 100:
        raise APIError(422, "validation_error", "Missing Idempotency-Key header.")
    vo = await _customer_vo(order_id, vo_id, user)
    if vo["status"] == "cancelled":
        return {"result": "cancelled", "vendor_order": await _detail(vo, True)}
    # Atomic claim: wins only if the vendor hasn't accepted yet (accept uses the same status guard).
    claimed = await db.vendor_orders.find_one_and_update({"_id": vo["_id"], "status": "pending"}, {"$set": {"status": "cancelling"}})
    if claimed:
        claimed["status"] = "cancelling"
        try:
            await ff.cancel_vendor_order(claimed, "customer", user.id, body.reason, f"cancel:{vo['_id']}")
        except Exception:
            await db.vendor_orders.update_one({"_id": vo["_id"], "status": "cancelling"}, {"$set": {"status": "pending"}})
            raise
        return {"result": "cancelled", "vendor_order": await _detail(await db.vendor_orders.find_one({"_id": vo["_id"]}), True)}
    vo = await db.vendor_orders.find_one({"_id": vo["_id"]})
    if vo["status"] not in ("accepted", "processing"):
        raise APIError(409, "not_cancellable", "This order has already shipped or can't be cancelled. You can request a return after delivery.")
    if await db.order_requests.find_one({"vendor_order_id": vo["_id"], "type": "cancel", "status": {"$in": list(OPEN_REQ)}}):
        raise APIError(409, "conflict", "A cancellation request is already open for these items.")
    await ff.new_request(vo, "cancel", [], body.reason, ObjectId(user.id))
    await ff.event(vo, "cancel_requested", f"Customer asked to cancel: {body.reason}", "customer", user.id)
    await ff.notify_vendor(vo["vendor_id"], "Cancellation request", f"The customer asked to cancel order {vo['order_number']}. Respond within the deadline.")
    return {"result": "requested", "vendor_order": await _detail(vo, True)}


@router.post("/orders/{order_id}/vendor-orders/{vo_id}/returns", status_code=201)
async def request_return(order_id: str, vo_id: str, body: ReturnIn, user: User = Depends(get_current_user)):
    vo = await _customer_vo(order_id, vo_id, user)
    cfg = await ff.get_config()
    if vo["status"] != "delivered" or not vo.get("delivered_at"):
        raise APIError(409, "not_returnable", "Returns can be requested after delivery.")
    if (utcnow() - vo["delivered_at"].replace(tzinfo=utcnow().tzinfo)).days > cfg["return_window_days"]:
        raise APIError(409, "return_window_closed", f"The {cfg['return_window_days']}-day return window has closed.")
    pending = {}
    async for r in db.order_requests.find({"vendor_order_id": vo["_id"], "type": "return", "status": {"$in": list(OPEN_REQ)}}):
        for ln in r["lines"]:
            pending[ln["order_item_id"]] = pending.get(ln["order_item_id"], 0) + ln["quantity"]
    lines = []
    for ln in body.lines:
        it = await db.order_items.find_one({"_id": oid(ln.order_item_id), "vendor_order_id": vo["_id"]})
        if not it:
            raise APIError(422, "validation_error", "That item isn't part of this order.")
        product = await db.products.find_one({"_id": it["product_id"]})
        if product and product.get("returns_accepted") is False:
            raise APIError(422, "not_returnable", f"“{it['title']}” is marked as non-returnable.")
        left = it["shipped_qty"] - it["returned_qty"] - pending.get(it["_id"], 0)
        if ln.quantity > left:
            raise APIError(422, "validation_error", f"Only {left} of “{it['title']}” can be returned.")
        lines.append({"order_item_id": it["_id"], "quantity": ln.quantity, "title": it["title"]})
    req = await ff.new_request(vo, "return", lines, body.reason, ObjectId(user.id))
    await db.vendor_orders.update_one({"_id": vo["_id"], "earning_status": {"$in": ["pending", "releasing"]}},
                                      {"$push": {"holds": ledger.hold("Return requested", "refund", ref=str(req["_id"]))}})
    await ff.event(vo, "return_requested", f"Return requested: {body.reason}", "customer", user.id)
    await ff.notify_vendor(vo["vendor_id"], "Return request", f"A return was requested on order {vo['order_number']}. Respond within the deadline.")
    return {"request": ser(req)}


async def _own_vo(vo_id: str, user: User) -> tuple[dict, dict]:
    vendor = await my_vendor(user)
    vo = await db.vendor_orders.find_one({"_id": oid(vo_id), "vendor_id": vendor["_id"]})
    if not vo:
        raise APIError(404, "not_found", "Order not found.")
    return vendor, vo


@router.get("/vendor/orders")
async def vendor_queue(status: Optional[str] = None, user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    q = {"vendor_id": vendor["_id"], **({"status": status} if status else {})}
    vos = await db.vendor_orders.find(q).sort("created_at", -1).to_list(200)
    counts = {d["_id"]: d["n"] async for d in db.vendor_orders.aggregate([{"$match": {"vendor_id": vendor["_id"]}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    return {"data": [await _detail(v, False) for v in vos], "counts": counts}


@router.post("/vendor/orders/{vo_id}/status")
async def vendor_status(vo_id: str, body: StatusIn, user: User = Depends(get_current_user)):
    _, vo = await _own_vo(vo_id, user)
    if body.to == "ready_for_pickup" and vo["fulfillment_type"] != "pickup":
        raise APIError(409, "invalid_transition", "Only local pickup orders can be marked ready for pickup.")
    if body.to == "delivered" and vo["status"] != "ready_for_pickup":
        raise APIError(409, "invalid_transition", "Shipped orders are delivered via shipment tracking updates.")
    if body.to in ("ready_for_pickup", "delivered"):
        for it in await db.order_items.find({"vendor_order_id": vo["_id"]}).to_list(100):
            left = it["quantity"] - it["shipped_qty"] - it["cancelled_qty"]
            if left > 0 and body.to == "ready_for_pickup":
                await ff.fulfil(it["variant_id"], left, vo["order_number"])
                await db.order_items.update_one({"_id": it["_id"]}, {"$inc": {"shipped_qty": left}})
    vo = await ff.transition(vo, body.to, "vendor", user.id, body.note)
    msgs = {"accepted": "was accepted by", "processing": "is being prepared by", "ready_for_pickup": "is ready for pickup from", "delivered": "was picked up from"}
    await ff.notify_user(vo["customer_id"], "Order update", f"Your order {vo['order_number']} {msgs[body.to]} {vo['vendor_name']}.", f"/account/orders/{vo['order_id']}")
    return {"vendor_order": await _detail(vo, False)}


@router.post("/vendor/orders/{vo_id}/shipments", status_code=201)
async def create_shipment(vo_id: str, body: ShipmentIn, user: User = Depends(get_current_user)):
    _, vo = await _own_vo(vo_id, user)
    if vo["status"] not in ("accepted", "processing", "partially_shipped"):
        raise APIError(409, "invalid_transition", "Accept the order before shipping it.")
    items = {i["_id"]: i for i in await db.order_items.find({"vendor_order_id": vo["_id"]}).to_list(100)}
    lines = []
    for ln in body.lines:
        it = items.get(oid(ln.order_item_id))
        if not it or ln.quantity > it["quantity"] - it["shipped_qty"] - it["cancelled_qty"]:
            raise APIError(422, "validation_error", "Ship quantity is more than what's left to ship.")
        lines.append((it, ln.quantity))
    if await db.vendor_orders.find_one_and_update({"_id": vo["_id"], "status": vo["status"], "shipping_lock": {"$ne": True}}, {"$set": {"shipping_lock": True}}) is None:
        raise APIError(409, "conflict", "This order changed at the same time. Refresh and try again.")
    try:
        for it, q in lines:
            await ff.fulfil(it["variant_id"], q, vo["order_number"])
            await db.order_items.update_one({"_id": it["_id"]}, {"$inc": {"shipped_qty": q}})
            it["shipped_qty"] += q
        label = await ff.LABELS.create_label(carrier=body.carrier, tracking_number=body.tracking_number.strip())
        doc = {"vendor_order_id": vo["_id"], "order_id": vo["order_id"], "vendor_id": vo["vendor_id"], "carrier": body.carrier, **label,
               "tracking_number": body.tracking_number.strip(), "status": "label_created", "lines": [{"order_item_id": i["_id"], "quantity": q} for i, q in lines],
               "events": [{"status": "label_created", "at": utcnow()}], "created_at": utcnow()}
        doc["_id"] = (await db.shipments.insert_one(doc)).inserted_id
        done = all(i["shipped_qty"] + i["cancelled_qty"] >= i["quantity"] for i in items.values())
    finally:
        await db.vendor_orders.update_one({"_id": vo["_id"]}, {"$unset": {"shipping_lock": ""}})
    vo = await ff.transition(vo, "shipped" if done else "partially_shipped", "vendor", user.id,
                             f"{'Shipped' if done else 'Partly shipped'} via {label['carrier_name']} · tracking {doc['tracking_number']}")
    await ff.notify_user(vo["customer_id"], "Your order shipped", f"{vo['vendor_name']} shipped items from order {vo['order_number']} via {label['carrier_name']}"
                         f" (tracking {doc['tracking_number']}).", f"/account/orders/{vo['order_id']}")
    return {"shipment": ser(doc)}


@router.post("/vendor/shipments/{shipment_id}/status")
async def shipment_status(shipment_id: str, body: ShipStatusIn, user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    s = await db.shipments.find_one_and_update({"_id": oid(shipment_id), "vendor_id": vendor["_id"], "status": {"$ne": "delivered"}},
                                               {"$set": {"status": body.status}, "$push": {"events": {"status": body.status, "note": body.note, "at": utcnow()}}})
    if not s:
        raise APIError(404, "not_found", "Shipment not found or already delivered.")
    vo = await db.vendor_orders.find_one({"_id": s["vendor_order_id"]})
    await ff.event(vo, "shipment_" + body.status, f"Shipment {s['tracking_number']}: {body.status.replace('_', ' ')}", "vendor", user.id)
    await ff.notify_user(vo["customer_id"], "Shipment update", f"Shipment {s['tracking_number']} for order {vo['order_number']} is now "
                         f"{body.status.replace('_', ' ')}.", f"/account/orders/{vo['order_id']}")
    if body.status == "delivered" and vo["status"] == "shipped" and not await db.shipments.find_one({"vendor_order_id": vo["_id"], "status": {"$ne": "delivered"}}):
        await ff.transition(vo, "delivered", "vendor", user.id, "All shipments delivered")
    return {"ok": True}


async def _decide(req: dict, decision: str, role: str, actor_id, note: str) -> dict:
    vo = await db.vendor_orders.find_one({"_id": req["vendor_order_id"]})
    final = req["status"] == "approved" and decision == "reject" and role == "admin"
    if req["status"] != "requested" and not final:
        raise APIError(409, "conflict", "This request was already decided.")
    if decision == "reject":
        req = await ff.move_request(req, ("requested", "approved"), "rejected", role, actor_id, note)
        await db.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"holds.$[h].active": False}}, array_filters=[{"h.ref": str(req["_id"])}])
    elif req["type"] == "cancel":
        if vo["status"] not in ("accepted", "processing"):
            raise APIError(409, "not_cancellable", "The order already shipped; it can no longer be cancelled.")
        req = await ff.move_request(req, ("requested",), "approved", role, actor_id, note)
        await ff.cancel_vendor_order(vo, role, actor_id, f"Cancellation approved: {req['reason']}", f"cancel:{vo['_id']}")
    else:
        req = await ff.move_request(req, ("requested",), "approved", role, actor_id, note, rma_number=ff.rma())
    if not req:
        raise APIError(409, "conflict", "This request changed at the same time. Refresh and try again.")
    word = "approved" if decision == "approve" else "rejected"
    await ff.event(vo, f"{req['type']}_{word}", f"{req['type'].title()} request {word} by {role}{': ' + note if note else ''}"
                   + (f" · RMA {req['rma_number']}" if req.get("rma_number") else ""), role, actor_id)
    await ff.notify_user(vo["customer_id"], f"{req['type'].title()} request {word}", f"Your {req['type']} request for order {vo['order_number']} was {word}."
                         + (f" Return authorisation: {req['rma_number']}." if req.get("rma_number") else ""), f"/account/orders/{vo['order_id']}")
    if role == "admin":
        await ff.notify_vendor(vo["vendor_id"], "Request decided by AfroVending", f"An administrator {word} the {req['type']} request on {vo['order_number']}: {note}")
    return req


async def _receive(req: dict, restock: bool, role: str, actor_id) -> dict:
    vo = await db.vendor_orders.find_one({"_id": req["vendor_order_id"]})
    req = await ff.move_request(req, ("approved",), "received", role, actor_id, "Return received" + (" and restocked" if restock else ""))
    if not req:
        raise APIError(409, "conflict", "Only approved returns can be received.")
    for ln in req["lines"]:
        it = await db.order_items.find_one_and_update({"_id": ln["order_item_id"]}, {"$inc": {"returned_qty": ln["quantity"]}})
        if restock:
            inv = await db.inventory.find_one({"variant_id": it["variant_id"]})
            product = await db.products.find_one({"_id": it["product_id"]})
            await adjust_stock(inv=inv, product=product, actor_id=actor_id, delta=ln["quantity"], reason="return", note=req["rma_number"] or "")
    refund = await create_refund(vo, [(ln["order_item_id"], ln["quantity"]) for ln in req["lines"]], include_shipping=False,
                                 reason=f"Return {req['rma_number']}", key=f"return:{req['_id']}", actor_id=actor_id)
    req = await ff.move_request(req, ("received",), "refunded", "system", None, f"Refund {refund['status']}", refund_id=refund["_id"])
    await db.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"holds.$[h].active": False}}, array_filters=[{"h.ref": str(req["_id"])}])
    await ff.event(vo, "return_refunded", f"Return {req['rma_number']} received; refund of ${refund['amount_minor'] / 100:.2f} "
                   f"{'confirmed' if refund['status'] == 'succeeded' else 'pending with Stripe'}", role, actor_id)
    await ff.notify_user(vo["customer_id"], "Return refunded", f"We received your return {req['rma_number']}. A refund of ${refund['amount_minor'] / 100:.2f} "
                         "was sent to Stripe; your bank may take 5–10 business days.", f"/account/orders/{vo['order_id']}")
    return req


async def _vendor_req(req_id: str, user: User) -> dict:
    vendor = await my_vendor(user)
    req = await db.order_requests.find_one({"_id": oid(req_id), "vendor_id": vendor["_id"]})
    if not req:
        raise APIError(404, "not_found", "Request not found.")
    return req


@router.post("/vendor/requests/{req_id}/decide")
async def vendor_decide(req_id: str, body: DecideIn, user: User = Depends(get_current_user)):
    return {"request": ser(await _decide(await _vendor_req(req_id, user), body.decision, "vendor", user.id, body.note))}


@router.post("/vendor/requests/{req_id}/receive")
async def vendor_receive(req_id: str, body: ReceiveIn, user: User = Depends(get_current_user)):
    return {"request": ser(await _receive(await _vendor_req(req_id, user), body.restock, "vendor", user.id))}


@router.get("/vendor/shipping-methods")
async def my_methods(user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    return {"data": [ser(d) for d in await db.shipping_methods.find({"vendor_id": vendor["_id"]}).to_list(50)]}


@router.post("/vendor/shipping-methods", status_code=201)
async def add_method(body: MethodIn, user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    if body.type == "pickup" and len(body.pickup_address) < 5:
        raise APIError(422, "validation_error", "Add the pickup address customers should come to.")
    doc = {**body.model_dump(), "vendor_id": vendor["_id"], "created_by": ObjectId(user.id), "created_at": utcnow(), "updated_at": utcnow()}
    doc["_id"] = (await db.shipping_methods.insert_one(doc)).inserted_id
    return ser(doc)


@router.put("/vendor/shipping-methods/{method_id}")
async def edit_method(method_id: str, body: MethodIn, user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    res = await db.shipping_methods.find_one_and_update({"_id": oid(method_id), "vendor_id": vendor["_id"]}, {"$set": {**body.model_dump(), "updated_at": utcnow()}})
    if not res:
        raise APIError(404, "not_found", "Shipping option not found.")
    return ser(await db.shipping_methods.find_one({"_id": res["_id"]}))


@router.put("/vendor/products/{product_id}/returns")
async def returns_flag(product_id: str, body: ReturnsFlagIn, user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    res = await db.products.update_one({"_id": oid(product_id), "vendor_id": vendor["_id"]}, {"$set": {"returns_accepted": body.returns_accepted}})
    if not res.matched_count:
        raise APIError(404, "not_found", "Product not found.")
    return {"ok": True}


@router.get("/admin/fulfillment/requests")
async def admin_requests(_: User = Depends(ADMIN)):
    docs = await db.order_requests.find({}).sort([("escalated", -1), ("created_at", -1)]).to_list(300)
    return {"data": [ser(d) for d in docs]}


@router.post("/admin/fulfillment/requests/{req_id}/decide")
async def admin_decide(req_id: str, body: DecideIn, admin: User = Depends(ADMIN)):
    if len(body.note.strip()) < 3:
        raise APIError(422, "validation_error", "Give a reason for the override.")
    req = await db.order_requests.find_one({"_id": oid(req_id)})
    if not req:
        raise APIError(404, "not_found", "Request not found.")
    return {"request": ser(await _decide(req, body.decision, "admin", admin.id, body.note))}


@router.post("/admin/fulfillment/requests/{req_id}/receive")
async def admin_receive(req_id: str, body: ReceiveIn, admin: User = Depends(ADMIN)):
    req = await db.order_requests.find_one({"_id": oid(req_id)})
    if not req:
        raise APIError(404, "not_found", "Request not found.")
    return {"request": ser(await _receive(req, body.restock, "admin", admin.id))}


@router.get("/admin/fulfillment/config")
async def get_cfg(_: User = Depends(ADMIN)):
    return await ff.get_config()


@router.put("/admin/fulfillment/config")
async def put_cfg(body: ConfigIn, request: Request, admin: User = Depends(ADMIN)):
    from afrovending.core.audit import audit
    await db.platform_settings.update_one({"key": "fulfillment.config"}, {"$set": {"value": body.model_dump(), "updated_at": utcnow()}}, upsert=True)
    await audit("admin.fulfillment_config_updated", "platform_settings", request=request, actor=admin, **body.model_dump())
    return await ff.get_config()
