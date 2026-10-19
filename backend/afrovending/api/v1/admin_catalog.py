from datetime import timedelta
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from afrovending.api.v1.catalog import MIN_REPORT_COUNT, SEARCH_RETENTION_DAYS
from afrovending.api.v1.products import _summary, product_detail
from afrovending.api.v1.vendors import ser
from afrovending.core import email as mail
from afrovending.core.audit import audit
from afrovending.core.catalog import load_parts, oid, slugify
from afrovending.core.db import db
from afrovending.core.deps import require_roles
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.roles import Role

router = APIRouter(prefix="/admin", tags=["admin-catalog"])
MODERATOR = require_roles(Role.MARKETPLACE_ADMIN, Role.SUPER_ADMIN)
LIVE = ["active", "pending_review"]


class ModerateIn(BaseModel):
    decision: Literal["approve", "reject", "take_down"]
    note: str = Field(default="", max_length=2000)


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    slug: Optional[str] = Field(default=None, max_length=60)
    parent_slug: Optional[str] = None
    blurb: str = Field(default="", max_length=300)
    sort_order: int = Field(default=100, ge=0, le=10_000)


class CategoryUpdateIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    blurb: str = Field(default="", max_length=300)
    sort_order: int = Field(default=100, ge=0, le=10_000)
    status: Literal["active", "hidden"] = "active"


@router.get("/products")
async def list_products(status: str = "pending_review", _: User = Depends(MODERATOR)):
    q = {} if status == "all" else {"status": status}
    docs = await db.products.find(q).sort("submitted_at", 1 if status == "pending_review" else -1).to_list(500)
    variants, images, stock = await load_parts([d["_id"] for d in docs])
    names = {s["vendor_id"]: s["display_name"] async for s in db.vendor_stores.find({"vendor_id": {"$in": list({d["vendor_id"] for d in docs})}})}
    counts = {r["_id"]: r["n"] async for r in db.products.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    rows = [{**_summary(d, variants.get(d["_id"], []), images.get(d["_id"], []), stock), "vendor_name": names.get(d["vendor_id"], "")} for d in docs]
    return {"data": rows, "counts": counts}


@router.get("/products/{product_id}")
async def get_product(product_id: str, _: User = Depends(MODERATOR)):
    product = await db.products.find_one({"_id": oid(product_id)})
    if not product:
        raise APIError(404, "not_found", "Product not found.")
    store = await db.vendor_stores.find_one({"vendor_id": product["vendor_id"]}) or {}
    return {**await product_detail(product), "vendor_name": store.get("display_name", ""), "vendor_slug": store.get("slug")}


@router.post("/products/{product_id}/moderate")
async def moderate(product_id: str, body: ModerateIn, request: Request, admin: User = Depends(MODERATOR)):
    source = "active" if body.decision == "take_down" else "pending_review"
    status = {"approve": "active", "reject": "rejected", "take_down": "rejected"}[body.decision]
    if body.decision != "approve" and len(body.note.strip()) < 5:
        raise APIError(422, "validation_error", "Add a note so the vendor knows what to fix.")
    now = utcnow()
    sets = {"status": status, "moderation_note": body.note, "reviewed_by": ObjectId(admin.id), "reviewed_at": now, "updated_at": now}
    if status == "active":
        sets.update(ever_active=True, approved_at=now)
    product = await db.products.find_one_and_update({"_id": oid(product_id), "status": source},
                                                    {"$set": sets, "$push": {"history": {"status": status, "note": body.note, "at": now, "by": ObjectId(admin.id)}}})
    if not product:
        raise APIError(409, "conflict", "This product is not in a state that allows that decision.")
    await audit(f"admin.product_{body.decision}", "products", request=request, actor=admin, entity_id=product_id, note=body.note)
    owner = await db.users.find_one({"_id": product["owner_user_id"]})
    text = {"approve": f"{product['title']} is approved and now live on your store.",
            "reject": f"{product['title']} needs changes before it can go live: {body.note}",
            "take_down": f"{product['title']} was removed from the storefront: {body.note}"}[body.decision]
    subject, html = mail.vendor_notice_email(owner["name"], "Product review update", text)
    sent = await mail.try_send(to=owner["email"], subject=subject, html=html)
    return {**await product_detail(await db.products.find_one({"_id": product["_id"]})), "notification_sent": sent}


async def _category_out(c: dict) -> dict:
    return {**ser(c), "product_count": await db.products.count_documents({"category_slug": c["slug"], "status": {"$ne": "archived"}})}


@router.get("/categories")
async def list_categories(_: User = Depends(MODERATOR)):
    cats = await db.categories.find({}).sort([("sort_order", 1), ("name", 1)]).to_list(1000)
    return {"data": [await _category_out(c) for c in cats]}


@router.post("/categories", status_code=201)
async def create_category(body: CategoryIn, request: Request, admin: User = Depends(MODERATOR)):
    parent = None
    if body.parent_slug:
        parent = await db.categories.find_one({"slug": body.parent_slug, "parent_id": None})
        if not parent:
            raise APIError(422, "validation_error", "Parent must be a top-level category.")
    slug = slugify(body.slug or (f"{parent['slug']}-{body.name}" if parent else body.name))[:60]
    if len(slug) < 2 or await db.categories.find_one({"slug": slug}):
        raise APIError(409, "conflict", "A category with that URL already exists.", [{"field": "slug", "message": "Already taken."}])
    now = utcnow()
    doc = {"slug": slug, "name": body.name.strip(), "blurb": body.blurb, "sort_order": body.sort_order, "parent_id": parent["_id"] if parent else None,
           "image": None, "status": "active", "created_at": now, "updated_at": now}
    doc["_id"] = (await db.categories.insert_one(doc)).inserted_id
    await audit("admin.category_created", "categories", request=request, actor=admin, entity_id=str(doc["_id"]), slug=slug)
    return await _category_out(doc)


@router.patch("/categories/{category_id}")
async def update_category(category_id: str, body: CategoryUpdateIn, request: Request, admin: User = Depends(MODERATOR)):
    cat = await db.categories.find_one({"_id": oid(category_id)})
    if not cat:
        raise APIError(404, "not_found", "Category not found.")
    if body.status == "hidden" and cat["status"] != "hidden":
        slugs = [cat["slug"], *[k["slug"] async for k in db.categories.find({"parent_id": cat["_id"]}, {"slug": 1})]]
        if await db.products.count_documents({"category_slug": {"$in": slugs}, "status": {"$in": LIVE}}):
            raise APIError(409, "conflict", "This category has live or pending products. Move or archive them before hiding it.")
    await db.categories.update_one({"_id": cat["_id"]}, {"$set": {**body.model_dump(), "updated_at": utcnow()}})
    await audit("admin.category_updated", "categories", request=request, actor=admin, entity_id=category_id, status=body.status)
    return await _category_out(await db.categories.find_one({"_id": cat["_id"]}))


@router.delete("/categories/{category_id}")
async def delete_category(category_id: str, request: Request, admin: User = Depends(MODERATOR)):
    cat = await db.categories.find_one({"_id": oid(category_id)})
    if not cat:
        raise APIError(404, "not_found", "Category not found.")
    if await db.categories.find_one({"parent_id": cat["_id"]}) or await db.products.find_one({"category_slug": cat["slug"]}):
        raise APIError(409, "delete_blocked", "Only empty categories without subcategories can be deleted. Hide it instead.")
    await db.categories.delete_one({"_id": cat["_id"]})
    await audit("admin.category_deleted", "categories", request=request, actor=admin, entity_id=category_id, slug=cat["slug"])
    return {"status": "deleted"}


async def _top(match: dict, limit: int = 20) -> tuple[list, int]:
    rows = await db.search_queries.aggregate([{"$match": match}, {"$group": {"_id": "$query", "n": {"$sum": 1}, "avg": {"$avg": "$result_count"}}},
                                               {"$sort": {"n": -1, "_id": 1}}]).to_list(5000)
    shown = [{"query": r["_id"], "count": r["n"], "avg_results": round(r["avg"], 1)} for r in rows if r["n"] >= MIN_REPORT_COUNT and r["_id"] != "[redacted]"]
    return shown[:limit], len(rows) - len(shown)


@router.get("/search-analytics")
async def search_analytics(days: int = 30, _: User = Depends(MODERATOR)):
    days = min(max(days, 1), SEARCH_RETENTION_DAYS)
    match = {"created_at": {"$gte": utcnow() - timedelta(days=days)}}
    total = await db.search_queries.count_documents(match)
    zero = await db.search_queries.count_documents({**match, "result_count": 0})
    top, hidden = await _top(match)
    zero_top, _ = await _top({**match, "result_count": 0})
    daily = await db.search_queries.aggregate([{"$match": match}, {"$group": {"_id": "$day", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]).to_list(200)
    return {"days": days, "total_searches": total, "zero_result_searches": zero, "zero_result_rate": round(zero / total, 3) if total else 0,
            "top_queries": top, "zero_result_queries": zero_top, "hidden_rare_queries": hidden, "daily": [{"day": d["_id"], "count": d["n"]} for d in daily],
            "privacy": {"min_count": MIN_REPORT_COUNT, "retention_days": SEARCH_RETENTION_DAYS,
                        "stored": "Normalized search text, result count, filter names and time. No account, session, IP address or device. Emails and phone numbers are redacted; Do-Not-Track / Global Privacy Control is honoured."}}


@router.delete("/search-analytics")
async def purge_search_analytics(request: Request, admin: User = Depends(MODERATOR)):
    n = (await db.search_queries.delete_many({})).deleted_count
    await audit("admin.search_analytics_purged", "search_queries", request=request, actor=admin, deleted=n)
    return {"deleted": n}
