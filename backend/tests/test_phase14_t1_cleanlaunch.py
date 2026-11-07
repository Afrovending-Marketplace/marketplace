# Phase 14 clean launch (T1 iteration 24): legacy redirect map, 404 for unrelated paths, removed migration surface, SEO sitemap/robots
import os
import xml.etree.ElementTree as ET

import httpx
import pytest

ROOT = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
ROOT = ROOT.rstrip("/")
BASE = f"{ROOT}/api/v1"


def resolve(path):
    return httpx.get(f"{BASE}/redirects/resolve", params={"path": path}, timeout=15)


# Legacy redirects -> related pages
@pytest.mark.parametrize("old,new", [
    ("/terms-and-conditions", "/terms"), ("/return-policy", "/returns-policy"), ("/support-topics", "/faq"),
    ("/fashion-products", "/categories/fashion"), ("/category/hair-care", "/categories/beauty-hair-care"),
    ("/product-tag/palm-oil", "/search?q=palm oil"), ("/terms-and-conditions/", "/terms"), ("/return-policy?x=1", "/returns-policy"),
])
def test_related_redirects(old, new):
    r = resolve(old)
    assert r.status_code == 200, r.text
    assert r.json() == {"to": new, "status": 301}


# Unrelated old pages must 404, never home
@pytest.mark.parametrize("old", ["/drop-off-warehouse", "/flash-sales", "/species-products", "/other-fees", "/product/anything",
                                 "/store/anything", "/category/fitness-gear", "/", "/product-tag/", "/product-tag/UPPER"])
def test_unrelated_404(old):
    r = resolve(old)
    assert r.status_code == 404, (old, r.text)
    assert r.json().get("to") != "/"


# Every redirect target is a real route / active category
def test_all_redirect_targets_valid():
    from afrovending.api.v1.redirects import LEGACY_REDIRECTS
    sm = httpx.get(f"{BASE}/seo/sitemap.xml", timeout=15).text
    for old, to in LEGACY_REDIRECTS.items():
        assert to != "/", old
        if to.startswith("/categories/"):
            assert f"/categories/{to.split('/')[-1]}<" in sm, (old, to)


# Removed migration/activation surface
def test_activation_removed():
    for p in ("/auth/activation/request", "/auth/activation/complete"):
        r = httpx.post(f"{BASE}{p}", json={"email": "x@example.com", "token": "a" * 64, "password": "TestPass12345"}, timeout=15)
        assert r.status_code in (404, 405), (p, r.status_code)


@pytest.mark.parametrize("p", ["/admin/migration/report", "/admin/migration/batches", "/admin/migration/status", "/admin/migration/approve"])
def test_admin_migration_removed(p):
    assert httpx.get(f"{BASE}{p}", timeout=15).status_code == 404


# SEO files
def test_robots():
    r = httpx.get(f"{ROOT}/robots.txt", timeout=15)
    assert r.status_code == 200
    for s in ("Sitemap: https://afrovending.com/api/v1/seo/sitemap.xml", "Disallow: /admin", "Disallow: /account", "Disallow: /vendor"):
        assert s in r.text, s


def test_sitemap_valid_xml():
    r = httpx.get(f"{BASE}/seo/sitemap.xml", timeout=15)
    assert r.status_code == 200 and "xml" in r.headers["content-type"]
    root = ET.fromstring(r.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text for e in root.findall("s:url/s:loc", ns)]
    assert len(locs) >= 8
    cat_locs = [u for u in locs if "/categories/" in u]
    assert len(cat_locs) == 43, len(cat_locs)
    assert not any("?category=" in u for u in locs)
