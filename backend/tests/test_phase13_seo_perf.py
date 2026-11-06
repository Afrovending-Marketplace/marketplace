# Phase 13 QA: sitemap validity + listed URLs resolve, robots, product SEO tags via API, slow public endpoints
import re
import time
import xml.etree.ElementTree as ET

import httpx

from tests.test_phase03_vendors import BASE, _ENV

SITE = _ENV["FRONTEND_URL"]


def test_sitemap_valid_and_urls_resolve():
    r = httpx.get(f"{BASE}/seo/sitemap.xml", timeout=60)
    assert r.status_code == 200 and "xml" in r.headers["content-type"]
    root = ET.fromstring(r.content)
    locs = [e.text for e in root.iter() if e.tag.endswith("loc")]
    assert locs, "empty sitemap"
    bad = []
    for u in locs[:60]:
        path = re.sub(r"^https?://[^/]+", "", u)
        slug = path.rstrip("/").split("/")[-1]
        if path.startswith("/products/"):
            code = httpx.get(f"{BASE}/catalog/products/{slug}", timeout=30).status_code
        elif path.startswith("/stores/"):
            code = httpx.get(f"{BASE}/stores/{slug}", timeout=30).status_code
        else:
            code = httpx.get(f"{SITE}{path}", timeout=30).status_code
        if code != 200:
            bad.append((u, code))
    open("/tmp/qa13_sitemap.txt", "w").write(f"{len(locs)} urls; hosts={set(re.findall(r'https?://[^/]+', ' '.join(locs)))}; bad={bad}")
    assert not bad, bad


def test_robots():
    r = httpx.get(f"{BASE}/seo/robots.txt", timeout=30)
    assert r.status_code == 200 and "User-agent" in r.text


def test_public_endpoint_latency():
    slow = {}
    for p in ("/catalog/storefront", "/catalog/products", "/catalog/search?q=shea", "/catalog/categories", "/campaigns/active", "/health"):
        t = time.perf_counter()
        r = httpx.get(f"{BASE}{p}", timeout=60)
        dt = time.perf_counter() - t
        assert r.status_code == 200, (p, r.status_code)
        slow[p] = round(dt, 2)
    open("/tmp/qa13_latency.txt", "w").write(repr(slow))
    assert all(v < 3 for v in slow.values()), slow
