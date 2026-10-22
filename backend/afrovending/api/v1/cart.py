import hashlib
import secrets
from datetime import timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from afrovending.core import rate_limit
from afrovending.core.catalog import available, oid, visible_vendor_ids
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.pricing import MAX_LINES, MAX_QTY_PER_LINE, evaluate

router = APIRouter(prefix="/cart", tags=["cart"])
GUEST_DAYS = 30


class AddIn(BaseModel):
    variant_id: str
    quantity: int = Field(default=1, ge=1, le=MAX_QTY_PER_LINE)


class QtyIn(BaseModel):
    quantity: int = Field(ge=0, le=MAX_QTY_PER_LINE)


class CouponIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)


class ShippingIn(BaseModel):
    vendor_id: str
    method_id: str = Field(max_length=40)


class AddressIn(BaseModel):
    address_id: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def optional_user(request: Request) -> Optional[User]:
    try:
        return await get_current_user(request)
    except APIError:
        return None


async def _new_cart(user: Optional[User]) -> tuple[dict, Optional[str]]:
    now, token = utcnow(), None
    doc = {"status": "active", "items": [], "coupon_code": None, "shipping_selections": {}, "address_id": None, "created_at": now, "updated_at": now}
    if user:
        doc["user_id"] = ObjectId(user.id)
    else:
        token = secrets.token_urlsafe(32)
        doc.update(token_hash=_hash(token), expires_at=now + timedelta(days=GUEST_DAYS))
    doc["_id"] = (await db.carts.insert_one(doc)).inserted_id
    return doc, token


async def resolve(request: Request, create: bool = False) -> tuple[Optional[dict], Optional[User], Optional[str]]:
    user = await optional_user(request)
    if user:
        cart = await db.carts.find_one({"user_id": ObjectId(user.id), "status": "active"})
    else:
        token = request.headers.get("X-Cart-Token", "")
        cart = await db.carts.find_one({"token_hash": _hash(token), "status": "active"}) if 20 <= len(token) <= 100 else None
    if cart or not create:
        return cart, user, None
    cart, token = await _new_cart(user)
    return cart, user, token


async def address_for(cart: dict, user: Optional[User]) -> Optional[dict]:
    if not user or not cart.get("address_id"):
        return None
    return await db.addresses.find_one({"_id": cart["address_id"], "user_id": ObjectId(user.id)})


async def view(cart: Optional[dict], user: Optional[User], token: Optional[str] = None) -> dict:
    if not cart:
        return {"id": None, "groups": [], "item_count": 0, "coupon": None, "blocking": ["Your cart is empty."], "address_id": None,
                "totals": {"currency": "USD", "subtotal_minor": 0, "discount_minor": 0, "shipping_minor": None, "shipping_status": "to_be_confirmed",
                           "tax_estimate_minor": None, "tax_status": "not_calculated", "tax_rate_label": None, "estimated_total_minor": 0, "final": False}}
    out = await evaluate(cart, await address_for(cart, user))
    return {"id": str(cart["_id"]), "address_id": str(cart["address_id"]) if cart.get("address_id") and user else None,
            **out, **({"cart_token": token} if token else {})}


async def _save(cart: dict, **sets) -> None:
    extra = {"expires_at": utcnow() + timedelta(days=GUEST_DAYS)} if cart.get("token_hash") else {}
    await db.carts.update_one({"_id": cart["_id"]}, {"$set": {**sets, **extra, "updated_at": utcnow()}})


async def _purchasable(variant_id: str, wanted: int) -> dict:
    v = await db.product_variants.find_one({"_id": oid(variant_id), "status": "active"})
    p = await db.products.find_one({"_id": v["product_id"], "status": "active"}) if v else None
    if not p or p["vendor_id"] not in await visible_vendor_ids():
        raise APIError(404, "not_found", "This item isn't available.")
    left = available(await db.inventory.find_one({"variant_id": v["_id"]}))
    if left <= 0:
        raise APIError(409, "out_of_stock", "This item is out of stock.")
    if wanted > left:
        raise APIError(409, "insufficient_stock", f"Only {left} left in stock.", [{"field": "quantity", "message": f"Max {left}."}])
    return {"variant": v, "product": p}


@router.get("")
async def get_cart(request: Request):
    cart, user, _ = await resolve(request)
    return await view(cart, user)


@router.post("/items")
async def add_item(body: AddIn, request: Request):
    await rate_limit.hit(f"cart:{request.client.host if request.client else 'x'}", 120, 60)
    cart, user, token = await resolve(request, create=True)
    items = cart["items"]
    line = next((i for i in items if str(i["variant_id"]) == body.variant_id), None)
    qty = min(MAX_QTY_PER_LINE, (line["quantity"] if line else 0) + body.quantity)
    found = await _purchasable(body.variant_id, qty)
    if line:
        line["quantity"] = qty
    else:
        if len(items) >= MAX_LINES:
            raise APIError(422, "validation_error", f"A cart can hold up to {MAX_LINES} different items.")
        items.append({"variant_id": found["variant"]["_id"], "product_id": found["product"]["_id"], "vendor_id": found["product"]["vendor_id"],
                      "quantity": qty, "added_price_minor": found["variant"]["price_minor"], "title": found["product"]["title"], "added_at": utcnow()})
    await _save(cart, items=items)
    return await view(await db.carts.find_one({"_id": cart["_id"]}), user, token)


@router.patch("/items/{variant_id}")
async def set_quantity(variant_id: str, body: QtyIn, request: Request):
    cart, user, _ = await resolve(request)
    line = next((i for i in (cart or {}).get("items", []) if str(i["variant_id"]) == variant_id), None)
    if not line:
        raise APIError(404, "not_found", "That item isn't in your cart.")
    if body.quantity == 0:
        cart["items"].remove(line)
    else:
        if body.quantity > line["quantity"]:
            await _purchasable(variant_id, body.quantity)
        line["quantity"] = body.quantity
    await _save(cart, items=cart["items"])
    return await view(await db.carts.find_one({"_id": cart["_id"]}), user)


@router.delete("/items/{variant_id}")
async def remove_item(variant_id: str, request: Request):
    return await set_quantity(variant_id, QtyIn(quantity=0), request)


@router.post("/accept-prices")
async def accept_prices(request: Request):
    cart, user, _ = await resolve(request)
    if not cart:
        raise APIError(404, "not_found", "Your cart is empty.")
    prices = {v["_id"]: v["price_minor"] async for v in db.product_variants.find({"_id": {"$in": [i["variant_id"] for i in cart["items"]]}})}
    for i in cart["items"]:
        i["added_price_minor"] = prices.get(i["variant_id"], i["added_price_minor"])
    await _save(cart, items=cart["items"])
    return await view(await db.carts.find_one({"_id": cart["_id"]}), user)


@router.put("/coupon")
async def apply_coupon(body: CouponIn, request: Request):
    cart, user, _ = await resolve(request)
    if not cart or not cart["items"]:
        raise APIError(409, "conflict", "Add items before applying a coupon.")
    await rate_limit.hit(f"coupon:{request.client.host if request.client else 'x'}", 20, 600)
    await _save(cart, coupon_code=body.code.strip().upper())
    out = await view(await db.carts.find_one({"_id": cart["_id"]}), user)
    if not out["coupon"]["applied"]:
        await _save(cart, coupon_code=None)
        raise APIError(422, "invalid_coupon", out["coupon"]["message"], [{"field": "code", "message": out["coupon"]["message"]}])
    return out


@router.delete("/coupon")
async def remove_coupon(request: Request):
    cart, user, _ = await resolve(request)
    if cart:
        await _save(cart, coupon_code=None)
    return await view(await db.carts.find_one({"_id": cart["_id"]}) if cart else None, user)


@router.put("/shipping")
async def choose_shipping(body: ShippingIn, request: Request):
    cart, user, _ = await resolve(request)
    out = await view(cart, user)
    group = next((g for g in out["groups"] if g["vendor_id"] == body.vendor_id), None)
    if not group or body.method_id not in {m["id"] for m in group["shipping_methods"]}:
        raise APIError(422, "validation_error", "Choose a shipping option offered for these items.")
    await _save(cart, **{f"shipping_selections.{body.vendor_id}": body.method_id})
    return await view(await db.carts.find_one({"_id": cart["_id"]}), user)


@router.put("/address")
async def choose_address(body: AddressIn, request: Request):
    user = await get_current_user(request)
    cart, _, _ = await resolve(request)
    if not cart:
        raise APIError(404, "not_found", "Your cart is empty.")
    if not await db.addresses.find_one({"_id": oid(body.address_id), "user_id": ObjectId(user.id)}):
        raise APIError(404, "not_found", "Address not found.")
    await _save(cart, address_id=ObjectId(body.address_id))
    return await view(await db.carts.find_one({"_id": cart["_id"]}), user)


@router.post("/merge")
async def merge(request: Request, x_cart_token: str = Header(default="")):
    """Move a guest cart into the signed-in customer's cart. Requires the guest token; the guest cart is consumed."""
    user = await get_current_user(request)
    guest = await db.carts.find_one_and_update({"token_hash": _hash(x_cart_token), "status": "active"} if x_cart_token else {"_id": None},
                                               {"$set": {"status": "merged", "merged_into_user": ObjectId(user.id), "updated_at": utcnow()}})
    cart = await db.carts.find_one({"user_id": ObjectId(user.id), "status": "active"}) or (await _new_cart(user))[0]
    if guest:
        items = cart["items"]
        for g in guest["items"]:
            line = next((i for i in items if i["variant_id"] == g["variant_id"]), None)
            if line:
                line["quantity"] = min(MAX_QTY_PER_LINE, line["quantity"] + g["quantity"])
            elif len(items) < MAX_LINES:
                items.append(g)
        await _save(cart, items=items, coupon_code=cart.get("coupon_code") or guest.get("coupon_code"))
    return {**await view(await db.carts.find_one({"_id": cart["_id"]}), user), "merged": bool(guest)}
