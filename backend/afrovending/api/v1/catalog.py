import re
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Query, Request

from afrovending.core.catalog import file_url, public_products, visible_vendor_ids
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow

router = APIRouter(prefix="/catalog", tags=["catalog"])
SortKey = Literal["relevance", "featured", "newest", "price-asc", "price-desc"]
SORTS = {"featured": [("approved_at", -1)], "newest": [("created_at", -1)],
         "price-asc": [("price_min_minor", 1)], "price-desc": [("price_max_minor", -1)]}
SEARCH_RETENTION_DAYS = 180
MIN_REPORT_COUNT = 2
MAX_LIMIT = 120
_REDACT = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}|\d[\d\s().+-]{5,}\d", re.I)
_WORD = re.compile(r"[\w'-]+", re.U)


def normalize_query(q: str) -> str:
    q = " ".join(q.lower().split())[:80]
    return "[redacted]" if _REDACT.search(q) else q


def _words(q: str) -> list[str]:
    return [w for w in _WORD.findall(q.lower()) if len(w) > 1][:8]


def _partial_match(words: list[str]) -> dict:
    """Prefix match on every word (used when full-text finds nothing, e.g. 'kent' or 'bask')."""
    clauses = []
    for w in words:
        rx = {"$regex": rf"(^|[^a-z0-9]){re.escape(w)}", "$options": "i"}
        clauses.append({"$or": [{"title": rx}, {"tags": rx}, {"category_slug": rx}, {"description": rx}]})
    return {"$and": clauses} if clauses else {}


def _cat(c: dict, counts: dict, children: list) -> dict:
    kids = [k for k in children if k["parent_id"] == c["_id"]]
    return {"id": str(c["_id"]), "slug": c["slug"], "name": c["name"], "blurb": c.get("blurb", ""), "image": c.get("image"),
            "sort_order": c.get("sort_order", 0), "product_count": counts.get(c["slug"], 0) + sum(counts.get(k["slug"], 0) for k in kids),
            "subcategories": [k["name"] for k in kids],
            "children": [{"id": str(k["_id"]), "slug": k["slug"], "name": k["name"], "product_count": counts.get(k["slug"], 0)} for k in kids]}


async def category_tree(counts: Optional[dict] = None) -> list:
    cats = await db.categories.find({"status": "active"}).sort([("sort_order", 1), ("name", 1)]).to_list(1000)
    if counts is None:
        pipeline = [{"$match": {"status": "active", "vendor_id": {"$in": await visible_vendor_ids()}}}, {"$group": {"_id": "$category_slug", "n": {"$sum": 1}}}]
        counts = {r["_id"]: r["n"] async for r in db.products.aggregate(pipeline)}
    top, children = [c for c in cats if not c.get("parent_id")], [c for c in cats if c.get("parent_id")]
    return [_cat(c, counts, children) for c in top]


async def _facets(match: dict, scoped: dict) -> dict:
    """Category counts ignore the category filter (so users can switch); vendor/price/stock counts are scoped to it."""
    pipeline = [{"$match": match}, {"$facet": {
        "categories": [{"$group": {"_id": "$category_slug", "n": {"$sum": 1}}}],
        "vendors": [{"$match": scoped}, {"$group": {"_id": "$vendor_id", "n": {"$sum": 1}}}],
        "price": [{"$match": scoped}, {"$group": {"_id": None, "min": {"$min": "$price_min_minor"}, "max": {"$max": "$price_max_minor"}}}],
        "in_stock": [{"$match": {**scoped, "in_stock": True}}, {"$count": "n"}]}}]
    f = (await db.products.aggregate(pipeline).to_list(1))[0]
    counts = {r["_id"]: r["n"] for r in f["categories"]}
    stores = {s["vendor_id"]: s async for s in db.vendor_stores.find({"vendor_id": {"$in": [r["_id"] for r in f["vendors"]]}})}
    vendors = sorted([{"slug": stores[r["_id"]]["slug"], "name": stores[r["_id"]]["display_name"], "count": r["n"]} for r in f["vendors"] if r["_id"] in stores],
                     key=lambda v: (-v["count"], v["name"]))
    price = f["price"][0] if f["price"] else {"min": None, "max": None}
    return {"categories": [c for c in await category_tree(counts) if c["product_count"]], "vendors": vendors,
            "price": {"min": price["min"], "max": price["max"]}, "in_stock": f["in_stock"][0]["n"] if f["in_stock"] else 0}


async def run_search(*, q: str = "", category: Optional[str] = None, vendors: Optional[list] = None, min_price: Optional[int] = None,
                     max_price: Optional[int] = None, in_stock: bool = False, sort: str = "relevance", page: int = 1, limit: int = 24,
                     with_facets: bool = True) -> dict:
    page, limit = max(1, page), min(max(1, limit), MAX_LIMIT)
    base: dict = {"status": "active", "vendor_id": {"$in": await visible_vendor_ids()}}
    q = (q or "").strip()[:100]
    mode, text = "browse", {}
    if q:
        text = {"$text": {"$search": q}}
        mode = "text"
        if not await db.products.count_documents({**base, **text}, limit=1):
            text, mode = _partial_match(_words(q)), "partial"
            if not text:
                text = {"_id": None}
    filters: dict = {}
    if category:
        cat = await db.categories.find_one({"slug": category.lower(), "status": "active"})
        if not cat:
            raise APIError(404, "not_found", "Category not found.")
        kids = [k["slug"] async for k in db.categories.find({"parent_id": cat["_id"], "status": "active"}, {"slug": 1})]
        filters["category_slug"] = {"$in": [cat["slug"], *kids]}
    if vendors:
        ids = [s["vendor_id"] async for s in db.vendor_stores.find({"slug": {"$in": [v.lower() for v in vendors[:20]]}, "status": "published"}, {"vendor_id": 1})]
        allowed = set(base["vendor_id"]["$in"])
        filters["vendor_id"] = {"$in": [i for i in ids if i in allowed]}
    if min_price is not None or max_price is not None:
        filters["price_min_minor"] = {k: v for k, v in (("$gte", min_price), ("$lte", max_price)) if v is not None}
    if in_stock:
        filters["in_stock"] = True
    query = {**base, **text, **filters}
    if sort == "relevance" and mode != "text":
        sort = "featured"
    order = [("score", {"$meta": "textScore"}), ("approved_at", -1)] if sort == "relevance" else SORTS[sort]
    projection = {"score": {"$meta": "textScore"}} if mode == "text" else None
    total = await db.products.count_documents(query)
    docs = await db.products.find(query, projection).sort(order + [("_id", -1)]).skip((page - 1) * limit).limit(limit).to_list(limit)
    out = {"data": await public_products(docs), "page": page, "limit": limit, "total": total, "has_more": page * limit < total,
           "mode": mode, "sort": sort, "query": q}
    if with_facets:
        out["facets"] = await _facets({**base, **text}, {k: v for k, v in filters.items() if k == "category_slug"})
    return out


async def log_search(request: Request, q: str, total: int, mode: str, filters: list[str]) -> None:
    """Privacy: normalized text, result count and filter names only - no user, session, IP or user agent."""
    if request.headers.get("DNT") == "1" or request.headers.get("Sec-GPC") == "1":
        return
    now = utcnow()
    await db.search_queries.insert_one({"query": normalize_query(q), "result_count": total, "mode": mode, "filters": sorted(filters),
                                        "day": now.strftime("%Y-%m-%d"), "created_at": now, "expires_at": now + timedelta(days=SEARCH_RETENTION_DAYS)})


def _price(v: Optional[str]) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        n = round(float(v) * 100)
    except ValueError:
        raise APIError(422, "validation_error", "Price filters must be numbers.")
    if n < 0:
        raise APIError(422, "validation_error", "Price filters can't be negative.")
    return n


@router.get("/categories")
async def categories():
    return {"data": await category_tree()}


@router.get("/search")
async def search(request: Request, q: str = Query(default="", max_length=200), category: Optional[str] = None, vendor: Optional[str] = None,
                 min: Optional[str] = None, max: Optional[str] = None, in_stock: bool = False, sort: SortKey = "relevance",
                 page: int = Query(default=1, ge=1, le=500), limit: int = Query(default=24, ge=1, le=MAX_LIMIT), log: bool = False):
    lo, hi = _price(min), _price(max)
    if lo is not None and hi is not None and lo > hi:
        raise APIError(422, "validation_error", "Minimum price is higher than maximum price.")
    vendors = [v for v in (vendor or "").split(",") if v.strip()]
    result = await run_search(q=q, category=category, vendors=vendors, min_price=lo, max_price=hi, in_stock=in_stock, sort=sort, page=page, limit=limit)
    if log and result["query"] and page == 1:
        used = [k for k, v in (("category", category), ("vendor", vendors), ("price", lo is not None or hi is not None), ("in_stock", in_stock)) if v]
        await log_search(request, result["query"], result["total"], result["mode"], used)
    return result


@router.get("/suggest")
async def suggest(q: str = Query(default="", max_length=60)):
    q = q.strip()
    if len(q) < 2:
        return {"query": q, "products": [], "keywords": [], "categories": [], "vendors": []}
    rx = {"$regex": rf"(^|[^a-z0-9]){re.escape(q)}", "$options": "i"}
    vendor_ids = await visible_vendor_ids()
    live = {"status": "active", "vendor_id": {"$in": vendor_ids}}
    docs = await db.products.find({**live, "title": rx}, {"title": 1, "slug": 1, "price_min_minor": 1, "currency": 1}).sort("approved_at", -1).limit(5).to_list(5)
    tags = await db.products.aggregate([{"$match": {**live, "tags": rx}}, {"$unwind": "$tags"}, {"$match": {"tags": rx}},
                                        {"$group": {"_id": "$tags", "n": {"$sum": 1}}}, {"$sort": {"n": -1, "_id": 1}}, {"$limit": 5}]).to_list(5)
    cats = await db.categories.find({"status": "active", "name": rx}, {"slug": 1, "name": 1}).limit(4).to_list(4)
    stores = await db.vendor_stores.find({"status": "published", "vendor_id": {"$in": vendor_ids}, "display_name": rx}, {"slug": 1, "display_name": 1}).limit(3).to_list(3)
    return {"query": q,
            "products": [{"title": d["title"], "slug": d["slug"], "price_minor": d.get("price_min_minor"), "currency": d.get("currency", "USD")} for d in docs],
            "keywords": [t["_id"] for t in tags], "categories": [{"slug": c["slug"], "name": c["name"]} for c in cats],
            "vendors": [{"slug": s["slug"], "name": s["display_name"]} for s in stores]}


@router.get("/products")
async def products(category: Optional[str] = None, vendor: Optional[str] = None, q: Optional[str] = None,
                   sort: SortKey = "featured", page: int = Query(default=1, ge=1), limit: int = Query(default=24, ge=1, le=60),
                   min_price: Optional[int] = None, max_price: Optional[int] = None):
    vendors = [v for v in (vendor or "").split(",") if v.strip()]
    return await run_search(q=q or "", category=category, vendors=vendors, min_price=min_price, max_price=max_price,
                            sort=sort, page=page, limit=limit, with_facets=False)


@router.get("/products/{slug}")
async def product(slug: str):
    doc = await db.products.find_one({"slug": slug.lower(), "status": "active", "vendor_id": {"$in": await visible_vendor_ids()}})
    if not doc:
        raise APIError(404, "not_found", "Product not found.")
    return (await public_products([doc]))[0]


@router.get("/storefront")
async def storefront():
    """Snapshot used by the storefront shell: categories, live products and published vendors."""
    vendor_ids = await visible_vendor_ids()
    docs = await db.products.find({"status": "active", "vendor_id": {"$in": vendor_ids}}).sort("approved_at", -1).to_list(500)
    stores = await db.vendor_stores.find({"vendor_id": {"$in": vendor_ids}}).sort("display_name", 1).to_list(500)
    vendors = [{"slug": s["slug"], "name": s["display_name"], "location": s.get("location", ""), "logo": file_url(s.get("logo_file_id")),
                "banner": file_url(s.get("banner_file_id")), "categories": s.get("categories", []), "tagline": s.get("tagline", ""),
                "story": s.get("description", ""), "verified": True, "is_dev_data": False} for s in stores]
    return {"categories": await category_tree(), "products": await public_products(docs), "vendors": vendors}
