import hashlib
import json
from typing import Optional

from bson import ObjectId

from afrovending.core.catalog import available, file_url, visible_vendor_ids
from afrovending.core.db import db
from afrovending.core.models import utcnow

MAX_QTY_PER_LINE = 20
MAX_LINES = 50
TBC_METHOD = {"id": "to_be_confirmed", "name": "Standard shipping", "amount_minor": None,
              "eta": "Rate confirmed before payment", "free_over_minor": None}


def _bps(amount: int, bps: int) -> int:
    return (amount * bps + 5_000) // 10_000  # round half up


def _allocate(total: int, weights: list[int]) -> list[int]:
    """Split `total` across weights (largest remainder) so per-vendor discounts add up exactly."""
    s = sum(weights)
    if not s or not total:
        return [0] * len(weights)
    raw = [total * w / s for w in weights]
    out = [int(r) for r in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[: total - sum(out)]:
        out[i] += 1
    return out


async def shipping_methods(vendor_id) -> list[dict]:
    from afrovending.core.fulfillment import get_config
    default = (await get_config())["default_handling_days"]
    docs = await db.shipping_methods.find({"status": "active", "vendor_id": {"$in": [None, vendor_id]}}).sort("amount_minor", 1).to_list(20)
    methods = [{"id": str(d["_id"]), "name": d["name"], "amount_minor": d["amount_minor"], "eta": d.get("eta", ""),
                "free_over_minor": d.get("free_over_minor"), "type": d.get("type", "ship"), "pickup_address": d.get("pickup_address", ""),
                "handling_days": default if d.get("handling_days") is None else d["handling_days"], "pickup_hours": d.get("pickup_hours"), "slot_minutes": d.get("slot_minutes"), "slot_capacity": d.get("slot_capacity")} for d in docs]
    return methods or [{**TBC_METHOD, "handling_days": default}]


async def check_coupon(code: str, groups: list[dict], user_id=None) -> tuple[Optional[dict], str]:
    c = await db.coupons.find_one({"code": code.strip().upper()})
    now = utcnow()
    if not c or c["status"] != "active":
        return None, "This coupon code isn't valid."
    if (c.get("starts_at") and c["starts_at"].replace(tzinfo=now.tzinfo) > now) or (c.get("ends_at") and c["ends_at"].replace(tzinfo=now.tzinfo) < now):
        return None, "This coupon isn't active right now."
    if c.get("max_redemptions") and c.get("redemptions", 0) >= c["max_redemptions"]:
        return None, "This coupon has reached its usage limit."
    eligible = [g for g in groups if not c.get("vendor_id") or g["vendor_id"] == str(c["vendor_id"])]
    base = sum(g["subtotal_minor"] for g in eligible)
    if not eligible or not base:
        return None, "This coupon doesn't apply to the items in your cart."
    if base < c.get("min_subtotal_minor", 0):
        return None, f"Spend at least ${c['min_subtotal_minor'] / 100:.2f} on eligible items to use this coupon."
    if c.get("budget_minor") is not None and c.get("spent_minor", 0) >= c["budget_minor"]:
        return None, "This promotion has ended."
    if (c.get("per_customer_limit") or c.get("first_order_only")) and not user_id:
        return None, "Sign in to use this coupon."
    if c.get("per_customer_limit") and await db.coupon_redemptions.count_documents({"coupon_id": c["_id"], "customer_id": user_id}) >= c["per_customer_limit"]:
        return None, "You've already used this coupon."
    if c.get("first_order_only") and await db.orders.find_one({"customer_id": user_id, "payment_status": "paid"}, {"_id": 1}):
        return None, "This coupon is for first orders only."
    return c, ""


async def tax_rate(address: Optional[dict]) -> Optional[dict]:
    if not address:
        return None
    country, region = address.get("country", "").strip().upper(), address.get("region", "").strip().upper()
    return (await db.tax_rates.find_one({"status": "active", "country": country, "region": region})
            or await db.tax_rates.find_one({"status": "active", "country": country, "region": ""}))


async def evaluate(cart: dict, address: Optional[dict] = None) -> dict:
    """Server-side source of truth for every amount in cart and checkout. Browser-sent prices are never used."""
    items = cart.get("items", [])
    vids = [i["variant_id"] for i in items]
    variants = {v["_id"]: v for v in await db.product_variants.find({"_id": {"$in": vids}}).to_list(MAX_LINES)}
    pids = list({v["product_id"] for v in variants.values()})
    products = {p["_id"]: p for p in await db.products.find({"_id": {"$in": pids}}).to_list(MAX_LINES)}
    stock = {s["variant_id"]: s for s in await db.inventory.find({"variant_id": {"$in": vids}}).to_list(MAX_LINES)}
    thumbs = {}
    async for i in db.product_images.find({"product_id": {"$in": pids}, "sort_order": 0}):
        thumbs[i["product_id"]] = file_url(i["thumb_file_id"])
    visible = set(await visible_vendor_ids())
    stores = {s["vendor_id"]: s async for s in db.vendor_stores.find({"vendor_id": {"$in": [p["vendor_id"] for p in products.values()]}})}
    groups: dict = {}
    for it in items:
        v = variants.get(it["variant_id"])
        p = products.get(v["product_id"]) if v else None
        status, avail = "ok", 0
        if not v or not p or p["status"] != "active" or v["status"] != "active" or p["vendor_id"] not in visible:
            status = "unavailable"
        else:
            avail = available(stock.get(v["_id"]))
            status = "out_of_stock" if avail <= 0 else "insufficient_stock" if it["quantity"] > avail else "ok"
        price = v["price_minor"] if v else it["added_price_minor"]
        line = {"variant_id": str(it["variant_id"]), "product_id": str(p["_id"]) if p else None, "quantity": it["quantity"],
                "title": p["title"] if p else it.get("title", "Item"), "label": v["label"] if v else "", "sku": v["sku"] if v else "",
                "slug": p["slug"] if p else None, "image": thumbs.get(p["_id"]) if p else None, "status": status,
                "available": avail if status == "insufficient_stock" else None, "unit_price_minor": price,
                "previous_price_minor": it["added_price_minor"] if price != it["added_price_minor"] else None,
                "line_total_minor": price * it["quantity"] if status == "ok" else 0, "currency": p["currency"] if p else "USD"}
        key = p["vendor_id"] if p else None
        store = stores.get(key, {})
        g = groups.setdefault(key, {"vendor_id": str(key) if key else None, "vendor_name": store.get("display_name", "Unavailable items"),
                                    "vendor_slug": store.get("slug"), "items": [], "subtotal_minor": 0})
        g["items"].append(line)
        g["subtotal_minor"] += line["line_total_minor"]
    group_list = list(groups.values())
    for g in group_list:
        g["shipping_methods"] = await shipping_methods(ObjectId(g["vendor_id"])) if g["vendor_id"] else []
        chosen = (cart.get("shipping_selections") or {}).get(g["vendor_id"] or "")
        method = next((m for m in g["shipping_methods"] if m["id"] == chosen), None)
        if not method and len(g["shipping_methods"]) == 1:
            method = g["shipping_methods"][0]
        g["shipping_method_id"] = method["id"] if method else None
        amount = method["amount_minor"] if method else None
        if method and method.get("free_over_minor") is not None and g["subtotal_minor"] >= method["free_over_minor"]:
            amount = 0
        g["shipping_minor"] = amount
        g["shipping_status"] = "not_selected" if not method else "to_be_confirmed" if amount is None else "estimated"
    sellable = [g for g in group_list if g["vendor_id"] and g["subtotal_minor"]]
    discount, coupon_out = 0, None
    if cart.get("coupon_code"):
        coupon, error = await check_coupon(cart["coupon_code"], sellable, cart.get("user_id"))
        funded = None
        if coupon:
            funded = coupon.get("funded_by") or ("vendor" if coupon.get("vendor_id") else "marketplace")
            eligible = [g for g in sellable if not coupon.get("vendor_id") or g["vendor_id"] == str(coupon["vendor_id"])]
            base = sum(g["subtotal_minor"] for g in eligible)
            discount = min(base, _bps(base, coupon["value"]) if coupon["type"] == "percent" else coupon["value"])
            if coupon.get("max_discount_minor"):
                discount = min(discount, coupon["max_discount_minor"])
            if coupon.get("budget_minor") is not None:
                discount = min(discount, max(0, coupon["budget_minor"] - coupon.get("spent_minor", 0)))
            for g, share in zip(eligible, _allocate(discount, [g["subtotal_minor"] for g in eligible])):
                g["discount_minor"] = share
                g["platform_discount_minor"] = share if funded == "marketplace" else 0
        coupon_out = {"code": cart["coupon_code"], "applied": bool(coupon), "message": error or "Coupon applied.", "discount_minor": discount, "funded_by": funded}
    rate = await tax_rate(address)
    for g in group_list:
        g.setdefault("discount_minor", 0)
        g.setdefault("platform_discount_minor", 0)
        g["tax_estimate_minor"] = _bps(g["subtotal_minor"] - g["discount_minor"], rate["rate_bps"]) if rate and g["subtotal_minor"] else None
    subtotal = sum(g["subtotal_minor"] for g in sellable)
    ship_values = [g["shipping_minor"] for g in sellable]
    shipping = sum(ship_values) if sellable and all(s is not None for s in ship_values) else None
    known = sum(s for s in ship_values if s is not None)
    not_selected = any(g["shipping_status"] == "not_selected" for g in sellable)
    tax = sum(g["tax_estimate_minor"] for g in sellable) if rate and sellable else None
    lines = [line for g in group_list for line in g["items"]]
    blocking = []
    if not lines:
        blocking.append("Your cart is empty.")
    if any(line["status"] != "ok" for line in lines):
        blocking.append("Remove unavailable items or lower quantities to what's in stock.")
    if any(line["previous_price_minor"] is not None for line in lines):
        blocking.append("Some prices changed since you added them. Review and accept the new prices.")
    return {"groups": group_list, "item_count": sum(line["quantity"] for line in lines if line["status"] == "ok"), "coupon": coupon_out,
            "totals": {"currency": "USD", "subtotal_minor": subtotal, "discount_minor": discount, "shipping_minor": shipping,
                       "shipping_known_minor": known if shipping is None else None,
                       "shipping_status": "estimated" if shipping is not None else "not_selected" if not_selected else "to_be_confirmed",
                       "tax_estimate_minor": tax, "tax_status": "estimated" if tax is not None else "not_calculated",
                       "tax_rate_label": rate.get("label") if rate else None,
                       "estimated_total_minor": subtotal - discount + (shipping if shipping is not None else known) + (tax or 0), "final": False},
            "blocking": blocking}


def cart_fingerprint(cart: dict, evaluation: dict) -> str:
    data = {"lines": sorted((str(i["variant_id"]), i["quantity"]) for i in cart.get("items", [])),
            "prices": sorted((line["variant_id"], line["unit_price_minor"]) for g in evaluation["groups"] for line in g["items"]),
            "address": str(cart.get("address_id")), "shipping": cart.get("shipping_selections") or {}, "coupon": cart.get("coupon_code"),
            "total": evaluation["totals"]["estimated_total_minor"]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
