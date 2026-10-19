from typing import Literal, Optional

from fastapi import APIRouter

from afrovending.core.catalog import file_url, public_products, visible_vendor_ids
from afrovending.core.db import db
from afrovending.core.errors import APIError

router = APIRouter(prefix="/catalog", tags=["catalog"])
SORTS = {"featured": [("approved_at", -1)], "newest": [("created_at", -1)],
         "price-asc": [("price_min_minor", 1)], "price-desc": [("price_min_minor", -1)]}


def _cat(c: dict, counts: dict, children: list) -> dict:
    kids = [k for k in children if k["parent_id"] == c["_id"]]
    return {"id": str(c["_id"]), "slug": c["slug"], "name": c["name"], "blurb": c.get("blurb", ""), "image": c.get("image"),
            "sort_order": c.get("sort_order", 0), "product_count": counts.get(c["slug"], 0) + sum(counts.get(k["slug"], 0) for k in kids),
            "subcategories": [k["name"] for k in kids],
            "children": [{"id": str(k["_id"]), "slug": k["slug"], "name": k["name"], "product_count": counts.get(k["slug"], 0)} for k in kids]}


async def category_tree() -> list:
    cats = await db.categories.find({"status": "active"}).sort([("sort_order", 1), ("name", 1)]).to_list(1000)
    pipeline = [{"$match": {"status": "active", "vendor_id": {"$in": await visible_vendor_ids()}}}, {"$group": {"_id": "$category_slug", "n": {"$sum": 1}}}]
    counts = {r["_id"]: r["n"] async for r in db.products.aggregate(pipeline)}
    top, children = [c for c in cats if not c.get("parent_id")], [c for c in cats if c.get("parent_id")]
    return [_cat(c, counts, children) for c in top]


@router.get("/categories")
async def categories():
    return {"data": await category_tree()}


@router.get("/products")
async def products(category: Optional[str] = None, vendor: Optional[str] = None, q: Optional[str] = None,
                   sort: Literal["featured", "newest", "price-asc", "price-desc"] = "featured", page: int = 1, limit: int = 24,
                   min_price: Optional[int] = None, max_price: Optional[int] = None):
    page, limit = max(1, page), min(max(1, limit), 60)
    vendor_ids = await visible_vendor_ids()
    query: dict = {"status": "active", "vendor_id": {"$in": vendor_ids}}
    if category:
        cat = await db.categories.find_one({"slug": category.lower(), "status": "active"})
        if not cat:
            raise APIError(404, "not_found", "Category not found.")
        kids = [k["slug"] async for k in db.categories.find({"parent_id": cat["_id"], "status": "active"}, {"slug": 1})]
        query["category_slug"] = {"$in": [cat["slug"], *kids]}
    if vendor:
        store = await db.vendor_stores.find_one({"slug": vendor.lower(), "status": "published"})
        query["vendor_id"] = store["vendor_id"] if store and store["vendor_id"] in vendor_ids else None
    if q and q.strip():
        query["$text"] = {"$search": q.strip()[:100]}
    if min_price is not None or max_price is not None:
        query["price_min_minor"] = {k: v for k, v in (("$gte", min_price), ("$lte", max_price)) if v is not None}
    total = await db.products.count_documents(query)
    docs = await db.products.find(query).sort(SORTS[sort] + [("_id", -1)]).skip((page - 1) * limit).limit(limit).to_list(limit)
    return {"data": await public_products(docs), "page": page, "limit": limit, "total": total}


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
