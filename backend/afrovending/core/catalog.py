import re
from typing import Optional

from bson import ObjectId
from pymongo import ReturnDocument

from afrovending.core import email as mail
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow

CURRENCIES = ("USD",)
SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,63}$")
MAX_OPTIONS = 3
MAX_VARIANTS = 100
MAX_IMAGES = 8
STOCK_REASONS = {"restock", "correction", "damaged", "lost", "returned"}
REVIEW_FIELDS = ("title", "description", "category_slug", "tags", "option_names")


def file_url(fid) -> Optional[str]:
    return f"/api/v1/files/{fid}" if fid else None


def slugify(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def oid(v: str) -> ObjectId:
    if not ObjectId.is_valid(v):
        raise APIError(404, "not_found", "Not found.")
    return ObjectId(v)


async def unique_product_slug(title: str, exclude_id: Optional[ObjectId] = None) -> str:
    base = slugify(title)[:60].strip("-") or "product"
    slug, n = base, 2
    while await db.products.find_one({"slug": slug, "_id": {"$ne": exclude_id}}, {"_id": 1}):
        slug, n = f"{base}-{n}", n + 1
    return slug


async def active_category(slug_or_name: str) -> dict:
    key = (slug_or_name or "").strip()
    cat = await db.categories.find_one({"status": "active", "$or": [{"slug": key.lower()}, {"name": {"$regex": f"^{re.escape(key)}$", "$options": "i"}}]})
    if not cat:
        raise APIError(422, "validation_error", "Choose a valid category.", [{"field": "category_slug", "message": "Unknown category."}])
    return cat


async def visible_vendor_ids() -> list:
    active = [v["_id"] async for v in db.vendors.find({"status": "active"}, {"_id": 1})]
    return [s["vendor_id"] async for s in db.vendor_stores.find({"status": "published", "vendor_id": {"$in": active}}, {"vendor_id": 1})]


async def load_parts(product_ids: list) -> tuple[dict, dict, dict]:
    variants, images, stock = {}, {}, {}
    async for v in db.product_variants.find({"product_id": {"$in": product_ids}}).sort("sort_order", 1):
        variants.setdefault(v["product_id"], []).append(v)
    async for i in db.product_images.find({"product_id": {"$in": product_ids}}).sort("sort_order", 1):
        images.setdefault(i["product_id"], []).append(i)
    async for s in db.inventory.find({"product_id": {"$in": product_ids}}):
        stock[s["variant_id"]] = s
    return variants, images, stock


def available(inv: Optional[dict]) -> int:
    return max(0, (inv or {}).get("quantity_on_hand", 0) - (inv or {}).get("quantity_reserved", 0))


async def public_products(docs: list) -> list:
    """Storefront shape shared by every public catalog endpoint."""
    if not docs:
        return []
    variants, images, stock = await load_parts([d["_id"] for d in docs])
    stores = {s["vendor_id"]: s async for s in db.vendor_stores.find({"vendor_id": {"$in": list({d["vendor_id"] for d in docs})}})}
    out = []
    for d in docs:
        store = stores.get(d["vendor_id"], {})
        vs = [v for v in variants.get(d["_id"], []) if v["status"] == "active"]
        threshold = d.get("low_stock_threshold", 5)
        pv = [{"id": str(v["_id"]), "sku": v["sku"], "label": v["label"], "options": v.get("options", {}), "price_minor": v["price_minor"],
               "in_stock": available(stock.get(v["_id"])) > 0, "low_stock": 0 < available(stock.get(v["_id"])) <= threshold} for v in vs]
        imgs = images.get(d["_id"], [])
        out.append({"id": str(d["_id"]), "slug": d["slug"], "title": d["title"], "description": d.get("description", ""),
                    "category_slug": d["category_slug"], "tags": d.get("tags", []), "details": d.get("tags", []),
                    "vendor_slug": store.get("slug"), "vendor_name": store.get("display_name"), "currency": d["currency"],
                    "price_minor": d.get("price_min_minor", d["price_minor"]), "price_max_minor": d.get("price_max_minor", d["price_minor"]),
                    "images": [file_url(i["file_id"]) for i in imgs], "thumbnails": [file_url(i["thumb_file_id"]) for i in imgs],
                    "option_names": d.get("option_names", []), "variants": pv, "in_stock": any(v["in_stock"] for v in pv),
                    "is_featured": False, "is_dev_data": False, "created_at": d["created_at"].isoformat()})
    return out


async def adjust_stock(*, inv: dict, product: dict, actor_id, delta: Optional[int] = None, set_to: Optional[int] = None,
                       reason: str, note: str = "") -> dict:
    """Optimistic-concurrency stock change with an append-only adjustment record."""
    before = inv["quantity_on_hand"]
    delta = (set_to - before) if set_to is not None else delta
    if not delta:
        return inv
    after = before + delta
    if after < 0:
        raise APIError(422, "validation_error", "Stock can't go below zero.")
    if after - inv.get("quantity_reserved", 0) < 0:
        raise APIError(422, "validation_error", "Stock can't go below the quantity already reserved.")
    updated = await db.inventory.find_one_and_update({"_id": inv["_id"], "quantity_on_hand": before},
                                                     {"$inc": {"quantity_on_hand": delta}, "$set": {"updated_at": utcnow()}},
                                                     return_document=ReturnDocument.AFTER)
    if not updated:
        raise APIError(409, "conflict", "Stock changed at the same time. Refresh and try again.")
    await db.stock_adjustments.insert_one({"variant_id": inv["variant_id"], "product_id": inv["product_id"], "vendor_id": inv["vendor_id"],
                                           "delta": delta, "before": before, "after": after, "reason": reason, "note": note[:500],
                                           "actor_id": ObjectId(actor_id) if actor_id else None, "created_at": utcnow()})
    threshold = product.get("low_stock_threshold", 5)
    if before > threshold >= after and reason not in ("initial", "import"):
        await notify_low_stock(product, inv, after)
    return updated


async def notify_low_stock(product: dict, inv: dict, qty: int) -> None:
    owner = await db.users.find_one({"_id": product["owner_user_id"]})
    variant = await db.product_variants.find_one({"_id": inv["variant_id"]})
    if owner and variant:
        subject, html = mail.vendor_notice_email(owner["name"], "Low stock alert",
                                                 f"{product['title']} ({variant['label']}) is down to {qty} in stock. Restock from your vendor dashboard.")
        await mail.try_send(to=owner["email"], subject=subject, html=html)
