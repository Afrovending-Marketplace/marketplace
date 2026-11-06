"""Search-engine and social-preview support: XML sitemap, robots.txt and crawler-friendly share pages with Open Graph + JSON-LD."""
import json
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from afrovending.core.catalog import public_products, visible_vendor_ids
from afrovending.core.config import settings
from afrovending.core.db import db

router = APIRouter(prefix="/seo", tags=["seo"])
STATIC_PATHS = ["/", "/shop", "/vendors", "/about", "/contact", "/sell", "/privacy", "/terms"]


@router.get("/sitemap.xml")
async def sitemap():
    base = settings.frontend_url
    vids = await visible_vendor_ids()
    urls = [(f"{base}{p}", None) for p in STATIC_PATHS]
    for p in await db.products.find({"status": "active", "vendor_id": {"$in": vids}}, {"slug": 1, "updated_at": 1}).to_list(50000):
        urls.append((f"{base}/products/{p['slug']}", p.get("updated_at")))
    for s in await db.vendor_stores.find({"vendor_id": {"$in": vids}, "status": "published"}, {"slug": 1, "updated_at": 1}).to_list(5000):
        urls.append((f"{base}/store/{s['slug']}", s.get("updated_at")))
    for c in await db.categories.find({"status": "active"}, {"slug": 1}).to_list(2000):
        urls.append((f"{base}/shop?category={c['slug']}", None))
    body = "".join(f"<url><loc>{escape(u)}</loc>{f'<lastmod>{d:%Y-%m-%d}</lastmod>' if d else ''}</url>" for u, d in urls)
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + body + "</urlset>",
                    media_type="application/xml")


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    prod = settings.app_env == "production"
    rules = ("Disallow: /account\nDisallow: /admin\nDisallow: /vendor\nDisallow: /checkout\nDisallow: /cart\nDisallow: /api/\nAllow: /api/v1/seo/\n"
             if prod else "Disallow: /\n")
    return f"User-agent: *\n{rules}Sitemap: {settings.frontend_url}/api/v1/seo/sitemap.xml\n"


def _page(title: str, desc: str, url: str, image: str | None, ld: dict, kind: str = "website") -> HTMLResponse:
    img = f'<meta property="og:image" content="{escape(image)}"><meta name="twitter:image" content="{escape(image)}">' if image else ""
    ld_json = json.dumps(ld).replace("</", "<\\/")
    html = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>'
            f'<meta name="description" content="{escape(desc)}"><link rel="canonical" href="{escape(url)}">'
            f'<meta property="og:type" content="{kind}"><meta property="og:site_name" content="AfroVending"><meta property="og:title" content="{escape(title)}">'
            f'<meta property="og:description" content="{escape(desc)}"><meta property="og:url" content="{escape(url)}">{img}'
            f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{escape(title)}">'
            f'<script type="application/ld+json">{ld_json}</script>'
            f'<meta http-equiv="refresh" content="0;url={escape(url)}"></head><body><a href="{escape(url)}">{escape(title)}</a></body></html>')
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=600"})


def product_ld(p: dict, url: str) -> dict:
    price = p.get("price_minor") or (p.get("variants") or [{}])[0].get("price_minor")
    ld = {"@context": "https://schema.org", "@type": "Product", "name": p["title"], "description": (p.get("description") or "")[:500], "url": url,
          "image": [i for i in [p.get("image")] if i], "brand": {"@type": "Brand", "name": p.get("vendor_name") or "AfroVending"},
          "offers": {"@type": "Offer", "priceCurrency": "USD", "price": f"{(price or 0) / 100:.2f}", "url": url,
                     "availability": "https://schema.org/InStock" if p.get("in_stock", True) else "https://schema.org/OutOfStock",
                     "seller": {"@type": "Organization", "name": p.get("vendor_name") or "AfroVending"}}}
    return ld


@router.get("/share/products/{slug}")
async def share_product(slug: str):
    doc = await db.products.find_one({"slug": slug.lower(), "status": "active", "vendor_id": {"$in": await visible_vendor_ids()}})
    url = f"{settings.frontend_url}/products/{slug}"
    if not doc:
        return _page("AfroVending", "African fashion, beauty, food and crafts from independent sellers.", settings.frontend_url, None, {})
    p = (await public_products([doc]))[0]
    img = p.get("image") if isinstance(p.get("image"), str) else None
    full = f"{settings.frontend_url}{img}" if img and img.startswith("/") else img
    return _page(f"{p['title']} | AfroVending", (p.get("description") or p["title"])[:200], url, full, product_ld({**p, "image": full}, url), "product")


@router.get("/share/stores/{slug}")
async def share_store(slug: str):
    s = await db.vendor_stores.find_one({"slug": slug.lower(), "status": "published"})
    url = f"{settings.frontend_url}/store/{slug}"
    if not s or s["vendor_id"] not in await visible_vendor_ids():
        return _page("AfroVending", "African fashion, beauty, food and crafts from independent sellers.", settings.frontend_url, None, {})
    logo = f"{settings.frontend_url}/api/v1/files/{s['logo_file_id']}" if s.get("logo_file_id") else None
    ld = {"@context": "https://schema.org", "@type": "Store", "name": s["display_name"], "url": url, "description": (s.get("description") or "")[:500],
          **({"logo": logo, "image": logo} if logo else {})}
    return _page(f"{s['display_name']} | AfroVending", (s.get("tagline") or s.get("description") or s["display_name"])[:200], url, logo, ld)
