# Phase 14 clean launch: legacy URL redirects (related pages only), removed migration endpoints, SEO files, backup/restore drill
import json
import subprocess

import httpx

from tests.test_phase03_vendors import BASE


def resolve(path):
    return httpx.get(f"{BASE}/redirects/resolve", params={"path": path}, timeout=15)


def test_01_related_redirects():
    assert resolve("/terms-and-conditions").json()["to"] == "/terms"
    assert resolve("/return-policy").json()["to"] == "/returns-policy"
    assert resolve("/category/hair-care/").json()["to"] == "/categories/beauty-hair-care"
    assert resolve("/product-tag/palm-oil").json()["to"] == "/search?q=palm oil"


def test_02_unrelated_pages_not_redirected_to_home():
    for p in ("/drop-off-warehouse", "/flash-sales", "/product/dar-chill-pepper", "/store/old-shop", "/category/fitness-gear"):
        assert resolve(p).status_code == 404, p


def test_03_migration_endpoints_removed():
    assert httpx.post(f"{BASE}/auth/activation/request", json={"email": "x@example.com"}).status_code in (404, 405)
    assert httpx.get(f"{BASE}/admin/migration/report").status_code == 404


def test_04_seo_files():
    r = httpx.get(BASE.split("/api/")[0] + "/robots.txt", timeout=15)
    assert r.status_code == 200 and "Sitemap: https://afrovending.com/api/v1/seo/sitemap.xml" in r.text and "Disallow: /admin" in r.text
    s = httpx.get(f"{BASE}/seo/sitemap.xml", timeout=15)
    assert s.status_code == 200 and "<urlset" in s.text and "/categories/fashion<" in s.text and "?category=" not in s.text


def test_05_backup_restore_drill():
    r = subprocess.run(["bash", "-c", "./scripts/backup_db.sh | tail -1 && ./scripts/restore_verify.sh $(ls -t /app/backups/*.archive.gz | head -1) | tail -1"],
                       cwd="/app/backend", capture_output=True, text=True, timeout=250)
    assert r.returncode == 0 and json.loads(r.stdout.strip().splitlines()[-1])["restore_check"] == "PASS", r.stdout + r.stderr
