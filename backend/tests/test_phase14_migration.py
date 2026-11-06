# Phase 14: legacy import, activation, redirects, wishlist display, backups
import json
import os
import subprocess
import uuid
from datetime import timedelta

import httpx
from bson import ObjectId
from pymongo import MongoClient

from afrovending.core.models import utcnow
from afrovending.core.security import hash_token
from afrovending.legacy.importer import run
from tests.test_phase03_vendors import BASE, admin_client, mongo

SAMPLE = "/app/migration/sample_export"
TDB = f"{mongo.name}_t14_import"
client = MongoClient(os.environ.get("MONGO_URL") or open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip('"'))
MADE = []


def teardown_module():
    client.drop_database(TDB)
    mongo.users.delete_many({"_id": {"$in": MADE}})
    mongo.auth_tokens.delete_many({"user_id": {"$in": MADE}})
    mongo.sessions.delete_many({"user_id": {"$in": MADE}})
    mongo.legacy_redirects.delete_many({"source": "t14"})


def test_01_dry_run_writes_nothing_and_reports_errors():
    rep = run(SAMPLE, TDB, dry=True, client=client)
    assert TDB not in client.list_database_names() or client[TDB].users.count_documents({}) == 0
    msgs = " ".join(e["message"] for e in rep["errors"])
    assert "Unknown or skipped vendor V9" in msgs and "Unknown category C9" in msgs and "Duplicate order number" in msgs and "SKU 'bad sku!'" in msgs
    types = {r["type"] for r in rep["reconciliation"]}
    assert {"duplicate_email", "invalid_email"} <= types
    assert rep["activation_readiness"]["accounts"] == 4 and rep["activation_readiness"]["emails_sent"] == 0


def test_02_import_counts_ownership_prices_idempotent():
    rep = run(SAMPLE, TDB, client=client)
    db = client[TDB]
    assert rep["verification"] == {"products_without_vendor": 0, "variants_without_inventory": 0, "products_owner_mismatch": 0, "price_mismatch": 0,
                                   "images_pending": 1, "admin_roles_on_migrated_accounts": 0, "migrated_accounts_with_password": 0}
    assert db.users.count_documents({}) == 4 and db.products.count_documents({}) == 3 and db.legacy_orders.count_documents({}) == 2
    u = db.users.find_one({"email": "test.ada.legacy@example.com"})
    assert u["password_hash"] is None and u["marketing_opt_in"] is False and u["migration"]["activation_required"] is True and u["roles"] == ["customer"]
    owner = db.users.find_one({"email": "test.vendor.legacy@example.com"})
    assert set(owner["roles"]) == {"customer", "vendor"}
    pepper = db.products.find_one({"slug": "dar-cameron-pepper"})
    assert pepper["status"] == "draft" and pepper["price_min_minor"] == 799 and pepper["price_max_minor"] == 1349 and pepper["owner_user_id"] == owner["_id"]
    assert db.inventory.find_one({"variant_id": db.product_variants.find_one({"sku": "TEST-LEG-PEPPER-L"})["_id"]})["quantity_on_hand"] == 0
    o = db.legacy_orders.find_one({"order_number": "LEG-1001"})
    assert o["total_minor"] == 3348 and o["read_only"] and len(o["items"]) == 2 and o["user_id"] == u["_id"]
    assert db.payments.count_documents({}) == 0 and db.ledger_entries.count_documents({}) == 0 and db.orders.count_documents({}) == 0
    assert db.legacy_redirects.find_one({"from_path": "/product/dar-cameron-pepper"})["to_path"] == "/products/dar-cameron-pepper"
    again = run(SAMPLE, TDB, client=client)
    changed = {k: v for k, v in again["entities"].items() if v.get("created") or v.get("updated")}
    assert changed == {}, changed


def test_03_refuses_live_db_without_flag():
    r = subprocess.run(["python", "-m", "afrovending.legacy.importer", "--source", SAMPLE, "--target-db", mongo.name], cwd="/app/backend", capture_output=True, text=True)
    assert r.returncode != 0 and "Refusing" in (r.stderr + r.stdout)


def _migrated_user():
    uid = mongo.users.insert_one({"email": f"t14-{uuid.uuid4().hex[:8]}@example.com", "name": "TEST14 Migrated", "roles": ["customer"], "status": "active",
                                  "password_hash": None, "auth_providers": [], "email_verified_at": None, "created_at": utcnow(), "updated_at": utcnow(),
                                  "migration": {"source": "legacy_afrovending", "legacy_ids": {}, "activation_required": True}}).inserted_id
    MADE.append(uid)
    return uid


def _token(uid, hours=24):
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    mongo.auth_tokens.insert_one({"user_id": uid, "purpose": "activate_account", "token_hash": hash_token(raw), "created_at": utcnow(),
                                  "expires_at": utcnow() + timedelta(hours=hours), "used_at": None})
    return raw


def test_04_activation_flow():
    uid = _migrated_user()
    email = mongo.users.find_one({"_id": uid})["email"]
    c = httpx.Client(base_url=BASE, timeout=30)
    assert c.post("/auth/login", json={"email": email, "password": "Whatever123"}).status_code == 401
    a = c.post("/auth/activation/request", json={"email": email}).json()
    b = c.post("/auth/activation/request", json={"email": "nobody-t14@example.com"}).json()
    assert a == b  # no account enumeration
    assert mongo.auth_tokens.count_documents({"user_id": uid, "purpose": "activate_account"}) == 1
    assert c.post("/auth/activation/complete", json={"token": _token(uid, hours=-1), "password": "NewPassw0rd!x"}).status_code == 400  # expired
    raw = _token(uid)
    assert c.post("/auth/activation/complete", json={"token": raw, "password": "short"}).status_code == 422
    raw = _token(uid)
    assert mongo.auth_tokens.count_documents({"user_id": uid, "purpose": "activate_account", "used_at": None}) >= 1
    r = c.post("/auth/activation/complete", json={"token": raw, "password": "NewPassw0rd!x"})
    assert r.status_code == 200, r.text
    assert c.post("/auth/activation/complete", json={"token": raw, "password": "NewPassw0rd!x"}).status_code == 400  # reuse
    u = mongo.users.find_one({"_id": uid})
    assert u["password_hash"] and not u["migration"]["activation_required"] and u["email_verified_at"] and "admin" not in " ".join(u["roles"])
    assert c.post("/auth/login", json={"email": email, "password": "NewPassw0rd!x"}).status_code == 200


def test_05_bulk_activation_needs_approval_and_super_admin():
    sup = admin_client()
    assert sup.put("/admin/migration/activation-approval", json={"approved": False}).status_code == 200
    assert sup.post("/admin/migration/activation-batch", json={"batch_size": 1}).status_code == 409
    assert sup.put("/admin/migration/activation-approval", json={"approved": True, "confirm": "yes"}).status_code == 422
    rep = sup.get("/admin/migration/report").json()
    assert rep["approval"]["approved"] is False and "activation_pending" in rep
    assert httpx.get(f"{BASE}/admin/migration/report").status_code == 401


def test_06_redirect_resolve():
    mongo.legacy_redirects.insert_one({"from_path": "/product/t14-old", "to_path": "/products/t14-new", "status": 301, "source": "t14"})
    assert httpx.get(f"{BASE}/redirects/resolve", params={"path": "/product/t14-old/"}).json()["to"] == "/products/t14-new"
    assert httpx.get(f"{BASE}/redirects/resolve", params={"path": "/product-tag/palm-oil"}).json()["to"] == "/search?q=palm oil"
    assert httpx.get(f"{BASE}/redirects/resolve", params={"path": "/nope-t14"}).status_code == 404


def test_07_backup_restore_drill():
    r = subprocess.run(["bash", "-c", "./scripts/backup_db.sh | tail -1 && ./scripts/restore_verify.sh $(ls -t /app/backups/*.archive.gz | head -1) | tail -1"],
                       cwd="/app/backend", capture_output=True, text=True, timeout=250)
    assert r.returncode == 0 and json.loads(r.stdout.strip().splitlines()[-1])["restore_check"] == "PASS", r.stdout + r.stderr
    assert ObjectId  # keep import used
