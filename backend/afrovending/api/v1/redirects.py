"""Clean launch: old afrovending.com URLs -> closest related new page (301). Unrelated old pages fall through to 404, never the homepage."""
import re

from fastapi import APIRouter

from afrovending.core.errors import APIError

router = APIRouter(tags=["redirects"])

_C = "/categories/"
LEGACY_REDIRECTS = {
    "/about-us": "/about", "/contact-us": "/contact", "/faqs": "/faq", "/privacy-policy": "/privacy", "/terms-and-conditions": "/terms",
    "/return-policy": "/returns-policy", "/support-topics": "/faq", "/become-a-vendor": "/sell", "/stores": "/vendors", "/category": "/categories",
    "/checkout": "/cart", "/fashion-products": _C + "fashion", "/species-products": _C + "food-groceries-spices", "/other-fees": "/sell",
    "/category/accessories": _C + "fashion-accessories", "/category/african-art-craft": _C + "arts-crafts", "/category/african-beauty-personal-care": _C + "beauty",
    "/category/african-fashion": _C + "fashion", "/category/african-home-living": _C + "home-living", "/category/african-instruments": _C + "cultural-products-instruments",
    "/category/african-jewelry": _C + "jewelry", "/category/african-textiles": _C + "home-living-textiles", "/category/bedding-linens": _C + "home-living-textiles",
    "/category/beverages": _C + "food-groceries", "/category/body-care": _C + "beauty-body", "/category/cereal": _C + "food-groceries-grains--flours",
    "/category/cosmetics": _C + "beauty", "/category/cultural-artifacts": _C + "cultural-products", "/category/festivals-accessories": _C + "cultural-products-ceremonial",
    "/category/footwear": _C + "fashion", "/category/fragrances": _C + "beauty-fragrance", "/category/fresh-produce-dry-goods": _C + "food-groceries",
    "/category/furniture": _C + "home-living", "/category/grains-and-flour": _C + "food-groceries-grains--flours", "/category/hair-care": _C + "beauty-hair-care",
    "/category/handmade-art": _C + "arts-crafts", "/category/home-decor": _C + "home-living-wall-decor", "/category/household-accessories": _C + "home-living",
    "/category/kitchenware": _C + "home-living", "/category/ladies-wear": _C + "fashion", "/category/mens-wear": _C + "fashion",
    "/category/natural-skincare-healing": _C + "beauty-skin-care", "/category/sauces-pastes": _C + "food-groceries", "/category/skincare-products": _C + "beauty-skin-care",
    "/category/traditional-performance-items": _C + "cultural-products-ceremonial",
}


@router.get("/redirects/resolve")
async def resolve(path: str):
    path = "/" + path.split("?")[0].strip("/")[:300]
    if path in LEGACY_REDIRECTS:
        return {"to": LEGACY_REDIRECTS[path], "status": 301}
    m = re.fullmatch(r"/product-tag/([a-z0-9-]{1,60})", path)
    if m:
        return {"to": f"/search?q={m.group(1).replace('-', ' ')}", "status": 301}
    raise APIError(404, "not_found", "No redirect for this path.")
