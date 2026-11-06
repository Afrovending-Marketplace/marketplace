import secrets
from datetime import timedelta

from bson import ObjectId
from fastapi import APIRouter, Depends, Header, Request
from pymongo.errors import DuplicateKeyError

from afrovending.api.v1.cart import address_for, resolve
from afrovending.api.v1.vendors import ser
from afrovending.core.audit import audit
from afrovending.core.catalog import oid
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.pricing import cart_fingerprint, evaluate

router = APIRouter(prefix="/checkout", tags=["checkout"])
DRAFT_HOURS = 24
ADDRESS_FIELDS = ("label", "full_name", "line1", "line2", "city", "region", "postal_code", "country", "phone")


def _public(order: dict) -> dict:
    out = ser(order)
    out.pop("cart_fingerprint", None)
    return out


@router.post("/start")
async def start(request: Request, idempotency_key: str = Header(default="", alias="Idempotency-Key"), user: User = Depends(get_current_user)):
    """Create (or replay) a draft order from the server-evaluated cart. No payment is taken."""
    if not 8 <= len(idempotency_key) <= 100:
        raise APIError(422, "validation_error", "Missing Idempotency-Key header.")
    uid = ObjectId(user.id)
    existing = await db.orders.find_one({"customer_id": uid, "idempotency_key": idempotency_key})
    cart, _, _ = await resolve(request)
    if not cart:
        if existing:
            return {"order": _public(existing), "replayed": True}
        raise APIError(409, "cart_empty", "Your cart is empty.")
    address = await address_for(cart, user)
    ev = await evaluate(cart, address)
    fingerprint = cart_fingerprint(cart, ev)
    if existing:
        if existing["cart_fingerprint"] != fingerprint:
            raise APIError(409, "idempotency_conflict", "This checkout was already started with a different cart. Refresh and try again.")
        return {"order": _public(existing), "replayed": True}
    problems = list(ev["blocking"])
    if not address:
        problems.append("Choose a delivery address.")
    sellable = [g for g in ev["groups"] if g["vendor_id"] and g["subtotal_minor"]]
    if any(not g["shipping_method_id"] for g in sellable):
        problems.append("Choose a shipping option for each vendor.")
    if problems:
        raise APIError(409, "checkout_blocked", problems[0], [{"field": "cart", "message": p} for p in problems])
    now = utcnow()
    order = {"order_number": f"AV-{now:%y%m%d}-{secrets.token_hex(3).upper()}", "customer_id": uid, "cart_id": cart["_id"],
             "status": "draft", "payment_status": "not_started", "idempotency_key": idempotency_key, "cart_fingerprint": fingerprint,
             "currency": "USD", "shipping_address": {k: address.get(k, "") for k in ADDRESS_FIELDS},
             "vendor_groups": [{**{k: g[k] for k in ("vendor_id", "vendor_name", "vendor_slug", "subtotal_minor", "discount_minor", "platform_discount_minor",
                                                      "shipping_minor", "shipping_status", "tax_estimate_minor")},
                                "shipping_method": next(m for m in g["shipping_methods"] if m["id"] == g["shipping_method_id"]),
                                "items": [{k: line[k] for k in ("variant_id", "product_id", "title", "label", "sku", "quantity", "unit_price_minor", "line_total_minor")}
                                          for line in g["items"]]} for g in sellable],
             "coupon_code": ev["coupon"]["code"] if ev["coupon"] and ev["coupon"]["applied"] else None, "totals": ev["totals"],
             "amounts_final": False, "expires_at": now + timedelta(hours=DRAFT_HOURS), "created_at": now, "updated_at": now}
    try:
        order["_id"] = (await db.orders.insert_one(order)).inserted_id
    except DuplicateKeyError:
        return {"order": _public(await db.orders.find_one({"customer_id": uid, "idempotency_key": idempotency_key})), "replayed": True}
    await db.orders.update_many({"customer_id": uid, "status": "draft", "_id": {"$ne": order["_id"]}}, {"$set": {"status": "abandoned", "updated_at": now}})
    await audit("checkout.draft_created", "orders", request=request, actor=user, entity_id=str(order["_id"]), total=ev["totals"]["estimated_total_minor"])
    return {"order": _public(order), "replayed": False}


@router.get("/orders/{order_id}")
async def get_draft(order_id: str, user: User = Depends(get_current_user)):
    order = await db.orders.find_one({"_id": oid(order_id), "customer_id": ObjectId(user.id)})
    if not order:
        raise APIError(404, "not_found", "Order not found.")
    if order["status"] == "draft" and order["expires_at"].replace(tzinfo=utcnow().tzinfo) < utcnow():
        await db.orders.update_one({"_id": order["_id"]}, {"$set": {"status": "expired"}})
        order["status"] = "expired"
    return {"order": _public(order)}
