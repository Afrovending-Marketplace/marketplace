import uuid
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from afrovending.api.v1.vendors import my_vendor, ser
from afrovending.core import rate_limit
from afrovending.core.audit import audit
from afrovending.core.catalog import (CURRENCIES, MAX_IMAGES, MAX_OPTIONS, MAX_VARIANTS, REVIEW_FIELDS, SKU_RE, STOCK_REASONS,
                                      active_category, adjust_stock, available, file_url, load_parts, oid, refresh_stock_flag,
                                      unique_product_slug)
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.images import optimize
from afrovending.core.models import User, utcnow
from afrovending.core.storage import APP_PREFIX, put_object

router = APIRouter(prefix="/vendor", tags=["vendor-products"])
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10_000_000


class VariantIn(BaseModel):
    id: Optional[str] = None
    sku: str = Field(min_length=2, max_length=64)
    options: dict[str, str] = Field(default_factory=dict)
    price_minor: int = Field(ge=1, le=100_000_000)
    initial_stock: int = Field(default=0, ge=0, le=1_000_000)
    is_active: bool = True

    @field_validator("sku")
    @classmethod
    def _sku(cls, v: str) -> str:
        v = v.strip().upper()
        if not SKU_RE.match(v):
            raise ValueError("SKU may use letters, numbers, dots, dashes and underscores (2–64).")
        return v


class ProductIn(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    description: str = Field(default="", max_length=5000)
    category_slug: str = Field(min_length=2, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=15)
    sku: str = Field(min_length=2, max_length=64)
    price_minor: int = Field(ge=1, le=100_000_000)
    currency: str = "USD"
    option_names: list[str] = Field(default_factory=list, max_length=MAX_OPTIONS)
    low_stock_threshold: int = Field(default=5, ge=0, le=10_000)

    _sku = field_validator("sku")(VariantIn._sku.__func__)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        out = []
        for t in v:
            t = t.strip().lower()[:30]
            if t and t not in out:
                out.append(t)
        return out

    @field_validator("option_names")
    @classmethod
    def _opts(cls, v: list[str]) -> list[str]:
        v = [o.strip()[:30] for o in v if o.strip()]
        if len({o.lower() for o in v}) != len(v):
            raise ValueError("Option names must be different (e.g. Size, Color, Material).")
        return v

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str) -> str:
        if v.upper() not in CURRENCIES:
            raise ValueError(f"Supported currency: {', '.join(CURRENCIES)}.")
        return v.upper()


class ProductCreateIn(ProductIn):
    variants: list[VariantIn] = Field(default_factory=list, max_length=MAX_VARIANTS)


class VariantsIn(BaseModel):
    variants: list[VariantIn] = Field(min_length=1, max_length=MAX_VARIANTS)
    option_names: Optional[list[str]] = Field(default=None, max_length=MAX_OPTIONS)

    _opts = field_validator("option_names")(lambda cls, v: v if v is None else ProductIn._opts.__func__(cls, v))


class AdjustIn(BaseModel):
    mode: Literal["delta", "set"] = "delta"
    quantity: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str
    note: str = Field(default="", max_length=500)


class PreferencesIn(BaseModel):
    low_stock_alerts: Literal["instant", "weekly"]


class OrderIn(BaseModel):
    image_ids: list[str] = Field(max_length=MAX_IMAGES)


async def writable_vendor(user: User = Depends(get_current_user)) -> dict:
    vendor = await my_vendor(user)
    if vendor["status"] != "active":
        raise APIError(403, "vendor_suspended", "Your vendor account is suspended. Catalog changes are disabled.")
    return vendor


async def reader_vendor(user: User = Depends(get_current_user)) -> dict:
    return await my_vendor(user)


async def own_product(product_id: str, vendor: dict) -> dict:
    docs = await db.products.find({"_id": oid(product_id), "vendor_id": vendor["_id"]}).to_list(1)
    if docs:
        return docs[0]
    raise APIError(404, "not_found", "Product not found.")


def check_variants(option_names: list[str], variants: list[VariantIn]) -> None:
    names = set(option_names)
    combos, skus = set(), set()
    for i, v in enumerate(variants):
        opts = {k.strip(): str(x).strip() for k, x in v.options.items()}
        if set(opts) != names or any(not x or len(x) > 40 for x in opts.values()):
            msg = f"Set a value for {', '.join(option_names)}." if names else "Products without options have a single variant."
            raise APIError(422, "validation_error", msg, [{"field": f"variants.{i}.options", "message": msg}])
        v.options = {k: opts[k] for k in option_names}
        combo = tuple(x.lower() for x in v.options.values())
        if combo in combos:
            raise APIError(422, "validation_error", "Two variants have the same options.", [{"field": f"variants.{i}.options", "message": "Duplicate option combination."}])
        if v.sku in skus:
            raise APIError(422, "validation_error", f"SKU {v.sku} is used twice.", [{"field": f"variants.{i}.sku", "message": "Duplicate SKU."}])
        combos.add(combo)
        skus.add(v.sku)
    if not names and len(variants) > 1:
        raise APIError(422, "validation_error", "Add an option (e.g. Size) to offer more than one variant.")


async def check_skus_free(skus: list[str], product_id: Optional[ObjectId]) -> None:
    taken = await db.product_variants.find_one({"sku": {"$in": skus}, "product_id": {"$ne": product_id}}, {"sku": 1})
    if taken:
        raise APIError(409, "conflict", f"SKU {taken['sku']} is already in use.", [{"field": "sku", "message": "SKU already in use."}])


async def save_variants(product: dict, variants: list[VariantIn], actor_id: str, reason: str = "initial") -> bool:
    """Upsert variants; removed ones become inactive so their SKU and stock history are kept. Returns True if structure changed."""
    check_variants(product.get("option_names", []), variants)
    await check_skus_free([v.sku for v in variants], product["_id"])
    existing = await db.product_variants.find({"product_id": product["_id"]}).to_list(500)
    by_id, by_sku = {str(v["_id"]): v for v in existing}, {v["sku"]: v for v in existing}
    before = {(v["sku"], v["label"]) for v in existing if v["status"] == "active"}
    keep, now = set(), utcnow()
    for i, v in enumerate(variants):
        label = " / ".join(v.options.values()) or "Default"
        data = {"sku": v.sku, "options": v.options, "label": label, "price_minor": v.price_minor,
                "status": "active" if v.is_active else "inactive", "sort_order": i, "updated_at": now}
        match = by_id.get(v.id or "") or by_sku.get(v.sku)
        if match:
            if match["sku"] != v.sku and v.sku in by_sku:
                raise APIError(409, "conflict", f"SKU {v.sku} belongs to another variant of this product.")
            await db.product_variants.update_one({"_id": match["_id"]}, {"$set": data})
            keep.add(match["_id"])
            continue
        vid = (await db.product_variants.insert_one({**data, "product_id": product["_id"], "vendor_id": product["vendor_id"], "created_at": now})).inserted_id
        inv = {"variant_id": vid, "product_id": product["_id"], "vendor_id": product["vendor_id"], "quantity_on_hand": 0, "quantity_reserved": 0, "updated_at": now}
        inv["_id"] = (await db.inventory.insert_one(inv)).inserted_id
        if v.initial_stock:
            await adjust_stock(inv=inv, product=product, actor_id=actor_id, delta=v.initial_stock, reason=reason, note="Opening stock")
        keep.add(vid)
    await db.product_variants.update_many({"product_id": product["_id"], "_id": {"$nin": list(keep)}}, {"$set": {"status": "inactive", "updated_at": now}})
    active = await db.product_variants.find({"product_id": product["_id"], "status": "active"}, {"price_minor": 1, "sku": 1, "label": 1}).to_list(500)
    if not active:
        raise APIError(422, "validation_error", "Keep at least one active variant.")
    prices = [v["price_minor"] for v in active]
    await db.products.update_one({"_id": product["_id"]}, {"$set": {"price_min_minor": min(prices), "price_max_minor": max(prices), "updated_at": now}})
    await refresh_stock_flag(product["_id"])
    return before != {(v["sku"], v["label"]) for v in active}


async def create_product(vendor: dict, user_id: str, body: ProductCreateIn, reason: str = "initial") -> dict:
    cat = await active_category(body.category_slug)
    variants = body.variants or [VariantIn(sku=body.sku, price_minor=body.price_minor)]
    check_variants(body.option_names, variants)
    await check_skus_free([v.sku for v in variants], None)
    if await db.products.find_one({"vendor_id": vendor["_id"], "sku": body.sku}, {"_id": 1}):
        raise APIError(409, "conflict", f"You already have a product with SKU {body.sku}.", [{"field": "sku", "message": "SKU already in use."}])
    now = utcnow()
    doc = {**body.model_dump(exclude={"variants"}), "category_slug": cat["slug"], "category_id": cat["_id"], "vendor_id": vendor["_id"],
           "owner_user_id": ObjectId(user_id), "slug": await unique_product_slug(body.title), "status": "draft", "ever_active": False,
           "moderation_note": "", "history": [{"status": "draft", "note": "Created", "at": now, "by": ObjectId(user_id)}],
           "price_min_minor": body.price_minor, "price_max_minor": body.price_minor, "created_at": now, "updated_at": now}
    doc["_id"] = (await db.products.insert_one(doc)).inserted_id
    try:
        await save_variants(doc, variants, user_id, reason)
    except APIError:
        await db.products.delete_one({"_id": doc["_id"]})
        await db.product_variants.delete_many({"product_id": doc["_id"]})
        await db.inventory.delete_many({"product_id": doc["_id"]})
        raise
    return doc


async def product_detail(product: dict) -> dict:
    variants, images, stock = await load_parts([product["_id"]])
    threshold = product.get("low_stock_threshold", 5)
    vs = [{**ser(v), "quantity_on_hand": stock.get(v["_id"], {}).get("quantity_on_hand", 0), "available": available(stock.get(v["_id"])),
           "low_stock": v["status"] == "active" and available(stock.get(v["_id"])) <= threshold} for v in variants.get(product["_id"], [])]
    imgs = [{"id": str(i["_id"]), "url": file_url(i["file_id"]), "thumb_url": file_url(i["thumb_file_id"]), "alt": i.get("alt", ""),
             "width": i.get("width"), "height": i.get("height"), "size": i.get("size")} for i in images.get(product["_id"], [])]
    return {"product": ser(product), "variants": vs, "images": imgs}


def _summary(p: dict, variants: list, images: list, stock: dict) -> dict:
    active = [v for v in variants if v["status"] == "active"]
    low = [v["label"] for v in active if available(stock.get(v["_id"])) <= p.get("low_stock_threshold", 5)]
    return {"id": str(p["_id"]), "title": p["title"], "slug": p["slug"], "sku": p["sku"], "status": p["status"], "currency": p["currency"],
            "category_slug": p["category_slug"], "price_min_minor": p.get("price_min_minor"), "price_max_minor": p.get("price_max_minor"),
            "stock_total": sum(available(stock.get(v["_id"])) for v in active), "variant_count": len(active), "low_stock_variants": low,
            "thumb_url": file_url(images[0]["thumb_file_id"]) if images else None, "moderation_note": p.get("moderation_note", ""),
            "updated_at": p["updated_at"]}


async def _log(action: str, request: Request, user: User, product: dict, **meta) -> None:
    await audit(action, "products", request=request, actor=user, entity_id=str(product["_id"]), **meta)


async def _set_status(product: dict, status: str, user_id, note: str = "", **extra) -> None:
    await db.products.update_one({"_id": product["_id"]}, {"$set": {"status": status, "updated_at": utcnow(), **extra},
                                                           "$push": {"history": {"status": status, "note": note, "at": utcnow(), "by": ObjectId(user_id)}}})


async def _requeue_if_live(product: dict, user: User, why: str) -> bool:
    if product["status"] == "active":
        await _set_status(product, "pending_review", user.id, why, submitted_at=utcnow())
        return True
    return False


def _editable(product: dict) -> None:
    if product["status"] == "archived":
        raise APIError(409, "conflict", "Restore this product from the archive before editing it.")


@router.get("/products")
async def list_products(status: Optional[str] = None, vendor: dict = Depends(reader_vendor)):
    q = {"vendor_id": vendor["_id"], **({"status": status} if status else {})}
    docs = await db.products.find(q).sort("updated_at", -1).to_list(1000)
    variants, images, stock = await load_parts([d["_id"] for d in docs])
    counts = {r["_id"]: r["n"] async for r in db.products.aggregate([{"$match": {"vendor_id": vendor["_id"]}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    rows = [_summary(d, variants.get(d["_id"], []), images.get(d["_id"], []), stock) for d in docs]
    low = [r for r in rows if r["low_stock_variants"] and r["status"] != "archived"]
    return {"data": rows, "counts": counts, "low_stock": low, "vendor_status": vendor["status"],
            "low_stock_alerts": vendor.get("low_stock_alerts", "instant")}


@router.put("/preferences")
async def set_preferences(body: PreferencesIn, request: Request, user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    await db.vendors.update_one({"_id": vendor["_id"]}, {"$set": {"low_stock_alerts": body.low_stock_alerts, "updated_at": utcnow()}})
    await audit("vendor.preferences_updated", "vendors", request=request, actor=user, entity_id=str(vendor["_id"]), low_stock_alerts=body.low_stock_alerts)
    return {"low_stock_alerts": body.low_stock_alerts}


@router.post("/products", status_code=201)
async def new_product(body: ProductCreateIn, request: Request, user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    doc = await create_product(vendor, user.id, body)
    await _log("product.created", request, user, doc)
    return await product_detail(await db.products.find_one({"_id": doc["_id"]}))


@router.get("/products/{product_id}")
async def get_product(product_id: str, vendor: dict = Depends(reader_vendor)):
    return await product_detail(await own_product(product_id, vendor))


@router.patch("/products/{product_id}")
async def update_product(product_id: str, body: ProductIn, request: Request, user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    product = await own_product(product_id, vendor)
    _editable(product)
    cat = await active_category(body.category_slug)
    data = {**body.model_dump(), "category_slug": cat["slug"], "category_id": cat["_id"]}
    if data["sku"] != product["sku"] and await db.products.find_one({"vendor_id": vendor["_id"], "sku": data["sku"], "_id": {"$ne": product["_id"]}}):
        raise APIError(409, "conflict", f"You already have a product with SKU {data['sku']}.", [{"field": "sku", "message": "SKU already in use."}])
    if data["option_names"] != product.get("option_names", []) and await db.product_variants.count_documents({"product_id": product["_id"], "status": "active"}) > 1:
        raise APIError(409, "conflict", "Remove extra variants before changing option names.")
    changed = [f for f in REVIEW_FIELDS if data[f] != product.get(f)]
    if data["title"] != product["title"]:
        data["slug"] = await unique_product_slug(data["title"], product["_id"])
    await db.products.update_one({"_id": product["_id"]}, {"$set": {**data, "updated_at": utcnow()}})
    if data["option_names"] != product.get("option_names", []):
        await db.product_variants.update_many({"product_id": product["_id"], "status": "active"}, {"$set": {"options": {}, "label": "Default"}})
    active = await db.product_variants.find({"product_id": product["_id"], "status": "active"}, {"_id": 1}).to_list(2)
    if not data["option_names"] and len(active) == 1 and data["price_minor"] != product["price_minor"]:
        await db.product_variants.update_one({"_id": active[0]["_id"]}, {"$set": {"price_minor": data["price_minor"]}})
        await db.products.update_one({"_id": product["_id"]}, {"$set": {"price_min_minor": data["price_minor"], "price_max_minor": data["price_minor"]}})
    requeued = changed and await _requeue_if_live(product, user, "Edited: " + ", ".join(changed))
    await _log("product.updated", request, user, product, fields=changed)
    return {**await product_detail(await db.products.find_one({"_id": product["_id"]})), "requeued_for_review": bool(requeued)}


@router.put("/products/{product_id}/variants")
async def put_variants(product_id: str, body: VariantsIn, request: Request, user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    product = await own_product(product_id, vendor)
    _editable(product)
    renamed = body.option_names is not None and body.option_names != product.get("option_names", [])
    if renamed:
        product["option_names"] = body.option_names
        await db.products.update_one({"_id": product["_id"]}, {"$set": {"option_names": body.option_names, "updated_at": utcnow()}})
    structural = await save_variants(product, body.variants, user.id) or renamed
    requeued = structural and await _requeue_if_live(product, user, "Variants changed")
    await _log("product.variants_updated", request, user, product, count=len(body.variants))
    return {**await product_detail(await db.products.find_one({"_id": product["_id"]})), "requeued_for_review": bool(requeued)}


@router.post("/products/{product_id}/images", status_code=201)
async def add_image(product_id: str, request: Request, file: UploadFile = File(...), alt: str = Form(default=""), user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    product = await own_product(product_id, vendor)
    _editable(product)
    await rate_limit.hit(f"product-image:{user.id}", 120, 3600)
    if await db.product_images.count_documents({"product_id": product["_id"]}) >= MAX_IMAGES:
        raise APIError(422, "validation_error", f"A product can have up to {MAX_IMAGES} images.")
    if file.content_type not in IMAGE_TYPES:
        raise APIError(422, "validation_error", "Unsupported file type. Use JPG, PNG or WEBP.")
    data = await file.read()
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise APIError(422, "validation_error", "Image must be under 10 MB.")
    try:
        result = await run_in_threadpool(optimize, data)
    except ValueError as e:
        raise APIError(422, "validation_error", str(e))
    now, ids = utcnow(), {}
    for kind in ("main", "thumb"):
        path = f"{APP_PREFIX}/public/product-media/{vendor['_id']}/{uuid.uuid4()}-{kind}.webp"
        try:
            stored = await run_in_threadpool(put_object, path, result[kind], "image/webp")
        except Exception:
            raise APIError(503, "storage_unavailable", "File storage is unavailable. Please try again.")
        ids[kind] = (await db.files.insert_one({"owner_user_id": ObjectId(user.id), "purpose": f"product_{kind}", "storage_path": stored["path"],
                                                "original_filename": (file.filename or "image")[:200], "content_type": "image/webp", "size": len(result[kind]),
                                                "is_private": False, "is_deleted": False, "application_id": None, "created_at": now})).inserted_id
    order = await db.product_images.count_documents({"product_id": product["_id"]})
    await db.product_images.insert_one({"product_id": product["_id"], "vendor_id": vendor["_id"], "file_id": ids["main"], "thumb_file_id": ids["thumb"],
                                        "alt": alt[:200] or product["title"], "sort_order": order, "width": result["width"], "height": result["height"],
                                        "original_size": len(data), "size": len(result["main"]), "created_at": now})
    await _requeue_if_live(product, user, "Images changed")
    await _log("product.image_added", request, user, product, original_bytes=len(data), optimized_bytes=len(result["main"]))
    return await product_detail(await db.products.find_one({"_id": product["_id"]}))


@router.delete("/products/{product_id}/images/{image_id}")
async def delete_image(product_id: str, image_id: str, request: Request, user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    product = await own_product(product_id, vendor)
    _editable(product)
    img = await db.product_images.find_one_and_delete({"_id": oid(image_id), "product_id": product["_id"]})
    if not img:
        raise APIError(404, "not_found", "Image not found.")
    await db.files.update_many({"_id": {"$in": [img["file_id"], img["thumb_file_id"]]}}, {"$set": {"is_deleted": True, "deleted_at": utcnow()}})
    remaining = await db.product_images.find({"product_id": product["_id"]}).sort("sort_order", 1).to_list(MAX_IMAGES)
    for i, r in enumerate(remaining):
        await db.product_images.update_one({"_id": r["_id"]}, {"$set": {"sort_order": i}})
    if product["status"] == "active" and not remaining:
        await _set_status(product, "draft", user.id, "Last image removed")
    await _log("product.image_deleted", request, user, product)
    return await product_detail(await db.products.find_one({"_id": product["_id"]}))


@router.put("/products/{product_id}/images/order")
async def order_images(product_id: str, body: OrderIn, request: Request, user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    product = await own_product(product_id, vendor)
    _editable(product)
    current = {str(i["_id"]) for i in await db.product_images.find({"product_id": product["_id"]}, {"_id": 1}).to_list(MAX_IMAGES)}
    if set(body.image_ids) != current or len(body.image_ids) != len(current):
        raise APIError(422, "validation_error", "Send every image of this product exactly once.")
    for i, iid in enumerate(body.image_ids):
        await db.product_images.update_one({"_id": ObjectId(iid)}, {"$set": {"sort_order": i}})
    await _log("product.images_reordered", request, user, product)
    return await product_detail(product)


@router.post("/products/{product_id}/{action}")
async def product_action(product_id: str, action: str, request: Request, user: User = Depends(get_current_user)):
    if action not in ("submit", "archive", "unarchive"):
        raise APIError(404, "not_found", "Not found.")
    vendor = await writable_vendor(user)
    product = await own_product(product_id, vendor)
    if action == "submit":
        if product["status"] not in ("draft", "rejected"):
            raise APIError(409, "conflict", "Only draft or rejected products can be submitted for review.")
        problems = []
        if len(product.get("description", "").strip()) < 20:
            problems.append({"field": "description", "message": "Add a description of at least 20 characters."})
        if not await db.product_images.count_documents({"product_id": product["_id"]}):
            problems.append({"field": "images", "message": "Add at least one product image."})
        if not await db.product_variants.count_documents({"product_id": product["_id"], "status": "active"}):
            problems.append({"field": "variants", "message": "Add at least one active variant."})
        if problems:
            raise APIError(422, "validation_error", "This product isn't ready for review.", problems)
        await _set_status(product, "pending_review", user.id, "Submitted for review", submitted_at=utcnow())
    elif action == "archive":
        if product["status"] == "archived":
            raise APIError(409, "conflict", "This product is already archived.")
        await _set_status(product, "archived", user.id, "Archived by vendor", archived_from=product["status"])
    else:
        if product["status"] != "archived":
            raise APIError(409, "conflict", "Only archived products can be restored.")
        await _set_status(product, "draft", user.id, "Restored from archive")
    await _log(f"product.{action}", request, user, product)
    return await product_detail(await db.products.find_one({"_id": product["_id"]}))


@router.delete("/products/{product_id}")
async def delete_product(product_id: str, request: Request, user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    product = await own_product(product_id, vendor)
    if product.get("ever_active") or product["status"] not in ("draft", "rejected", "archived"):
        raise APIError(409, "delete_blocked", "Products that have been live can't be deleted. Archive it instead to keep its history.")
    images = await db.product_images.find({"product_id": product["_id"]}).to_list(MAX_IMAGES)
    file_ids = [x for i in images for x in (i["file_id"], i["thumb_file_id"])]
    await db.files.update_many({"_id": {"$in": file_ids}}, {"$set": {"is_deleted": True, "deleted_at": utcnow()}})
    for coll in ("product_images", "inventory", "product_variants"):
        await db[coll].delete_many({"product_id": product["_id"]})
    await db.products.delete_one({"_id": product["_id"]})
    await _log("product.deleted", request, user, product, title=product["title"], sku=product["sku"])
    return {"status": "deleted"}


@router.post("/inventory/{variant_id}/adjust")
async def adjust(variant_id: str, body: AdjustIn, request: Request, user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    if body.reason not in STOCK_REASONS:
        raise APIError(422, "validation_error", f"Reason must be one of: {', '.join(sorted(STOCK_REASONS))}.")
    if body.mode == "set" and body.quantity < 0:
        raise APIError(422, "validation_error", "Stock can't be negative.")
    inv = await db.inventory.find_one({"variant_id": oid(variant_id), "vendor_id": vendor["_id"]})
    if not inv:
        raise APIError(404, "not_found", "Variant not found.")
    product = await db.products.find_one({"_id": inv["product_id"]})
    _editable(product)
    kwargs = {"set_to": body.quantity} if body.mode == "set" else {"delta": body.quantity}
    updated = await adjust_stock(inv=inv, product=product, actor_id=user.id, reason=body.reason, note=body.note, **kwargs)
    await audit("inventory.adjusted", "inventory", request=request, actor=user, entity_id=variant_id,
                before=inv["quantity_on_hand"], after=updated["quantity_on_hand"], reason=body.reason)
    return {"variant_id": variant_id, "quantity_on_hand": updated["quantity_on_hand"], "available": available(updated),
            "low_stock": available(updated) <= product.get("low_stock_threshold", 5)}


@router.get("/products/{product_id}/stock-history")
async def stock_history(product_id: str, vendor: dict = Depends(reader_vendor)):
    product = await own_product(product_id, vendor)
    labels = {v["_id"]: v["label"] async for v in db.product_variants.find({"product_id": product["_id"]}, {"label": 1})}
    rows = await db.stock_adjustments.find({"product_id": product["_id"]}).sort("created_at", -1).to_list(200)
    return {"data": [{**ser(r), "variant_label": labels.get(r["variant_id"], "")} for r in rows]}
