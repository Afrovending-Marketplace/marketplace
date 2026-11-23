# ruff: noqa: F811
# Iteration 36 (T1): DigitalOcean / Emergent clean-up changes - Resend email log (no key configured), sender mapping,
# admin email deliveries API, Resend webhook (503 + Svix _verify unit tests), upload magic-byte checks, launch items.
import base64
import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from bson import ObjectId
from dotenv import dotenv_values

from tests.test_phase03_vendors import BASE, admin_client, mongo

_ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
for k, v in _ENV.items():
    os.environ.setdefault(k, v or "")
os.environ.pop("RESEND_API_KEY", None)

START = datetime.now(timezone.utc).replace(tzinfo=None)
TAG = uuid.uuid4().hex[:6]
MADE = {"users": [], "files": [], "deliveries": [], "contact": []}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64


def teardown_module():
    users = [ObjectId(u) for u in MADE["users"]]
    for coll in ("sessions", "auth_tokens", "notifications", "policy_acceptances"):
        mongo[coll].delete_many({"user_id": {"$in": users}})
    mongo.users.delete_many({"_id": {"$in": users}})
    mongo.files.delete_many({"_id": {"$in": [ObjectId(f) for f in MADE["files"]]}})
    mongo.email_deliveries.delete_many({"_id": {"$in": MADE["deliveries"]}})
    mongo.contact_messages.delete_many({"_id": {"$in": MADE["contact"]}})


def _deliveries(prefix):
    docs = list(mongo.email_deliveries.find({"to_masked": f"{prefix}***@resend.dev", "created_at": {"$gte": START}}))
    MADE["deliveries"] += [d["_id"] for d in docs if d["_id"] not in MADE["deliveries"]]
    return docs


@pytest.fixture(scope="module")
def buyer():
    mongo.rate_limits.delete_many({"key": {"$regex": "^(register|login|forgot)"}})
    prefix = "q" + uuid.uuid4().hex[:1]
    email = f"{prefix}{uuid.uuid4().hex[:8]}@resend.dev"
    c = httpx.Client(base_url=BASE, timeout=90)
    r = c.post("/auth/register", json={"name": f"TEST_T36 {TAG}", "email": email, "password": "TestPass12345", "accept_policies": True})
    assert r.status_code == 201, r.text
    u = mongo.users.find_one({"email": email})
    MADE["users"].append(str(u["_id"]))
    return {"c": c, "email": email, "prefix": prefix}


# Registration writes a delivery record (security category): sent with a Resend key, failed without one
def test_01_register_logs_failed_delivery(buyer):
    time.sleep(1)
    docs = [d for d in _deliveries(buyer["prefix"]) if d["subject"].startswith("Verify your")]
    assert docs, "no email_deliveries record for verification email"
    d = docs[0]
    assert (d["status"] == "sent" and d["provider_id"]) or (d["status"] == "failed" and d["error"] == "RESEND_API_KEY not configured")
    assert d["category"] == "security" and d["attempts"] >= 1 and d["to_masked"].endswith("***@resend.dev")
    assert buyer["email"] not in str(d)


# Forgot password still returns success and logs 'Reset your AfroVending password' as security
def test_02_forgot_password_logs(buyer):
    r = httpx.post(f"{BASE}/auth/forgot-password", json={"email": buyer["email"]}, timeout=60)
    assert r.status_code in (200, 202), r.text
    time.sleep(1)
    docs = [d for d in _deliveries(buyer["prefix"]) if d["subject"] == "Reset your AfroVending password"]
    assert docs and docs[0]["status"] in ("sent", "failed") and docs[0]["category"] == "security"


# Contact form to info@ (not allowlisted outside production) is suppressed and still succeeds
def test_03_contact_form():
    mongo.rate_limits.delete_many({"key": {"$regex": "^contact:"}})
    em = f"TEST_t36{TAG}@example.com"
    r = httpx.post(f"{BASE}/contact", json={"name": "TEST_T36", "email": em, "subject": "TEST_ hello", "message": "Testing contact form please ignore"}, timeout=60)
    MADE["contact"] += [d["_id"] for d in mongo.contact_messages.find({"email": em})]
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "sent"


# sender_for mapping + allowlist suppression + from address
def test_04_sender_for_and_allowlist():
    from afrovending.core import email as mail
    assert mail.sender_for("[AfroVending alert] error spike") == "alerts"
    assert mail.sender_for("Reset your AfroVending password") == "security"
    assert mail.sender_for("Verify your AfroVending email") == "security"
    assert mail.sender_for("AfroVending: Vendor application approved") == "vendors"
    assert mail.sender_for("AfroVending receipt for order AV-1") == "orders"
    assert mail.sender_for("AfroVending: Order AV-1 is ready for pickup") == "orders"
    assert mail.sender_for("Welcome to the newsletter") == "notifications"
    assert mail._allowed_outside_production("x@resend.dev") and mail._allowed_outside_production("y@example.com")
    assert not mail._allowed_outside_production("someone@gmail.com")
    assert not mail._allowed_outside_production("info@afrovending.com")
    os.environ["EMAIL_SENDER_OVERRIDE"] = ""
    assert mail._from_address("orders") == f"{os.environ['EMAIL_FROM_NAME']} <orders@{mail.EMAIL_DOMAIN}>"


# Admin email deliveries API + filters + RBAC
def test_05_admin_emails(buyer):
    a = admin_client()
    r = a.get("/admin/ops/emails")
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j) >= {"data", "sending_enabled", "provider_configured"}
    assert isinstance(j["provider_configured"], bool) and isinstance(j["sending_enabled"], bool)
    assert all("idempotency_key" not in d and "_id" not in d and "id" in d for d in j["data"])
    f = a.get("/admin/ops/emails", params={"status": "failed"}).json()["data"]
    assert f and all(d["status"] == "failed" for d in f)
    assert a.get("/admin/ops/emails", params={"status": "bogus"}).status_code == 422
    assert httpx.get(f"{BASE}/admin/ops/emails", timeout=30).status_code == 401
    assert buyer["c"].get("/admin/ops/emails").status_code in (401, 403)


# Resend webhook: 503 while secret unset
def test_06_webhook_unconfigured():
    r = httpx.post(f"{BASE}/webhooks/resend", content=b'{"type":"email.delivered"}', timeout=30)
    assert r.status_code == 503, r.text


# Svix signature verification unit test
def test_07_verify_unit():
    from afrovending.api.v1.email_webhooks import _verify
    raw = os.urandom(24)
    secret = "whsec_" + base64.b64encode(raw).decode()
    body, mid, ts = b'{"type":"email.delivered","data":{"email_id":"x"}}', "msg_1", str(int(time.time()))
    sig = base64.b64encode(hmac.new(raw, f"{mid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    assert _verify(secret, mid, ts, body, f"v1,{sig}")
    assert _verify(secret, mid, ts, body, f"v1,bad v1,{sig}")
    assert not _verify(secret, mid, ts, body, "v1,AAAA")
    assert not _verify(secret, mid, ts, body + b" ", f"v1,{sig}")
    old = str(int(time.time()) - 600)
    sig_old = base64.b64encode(hmac.new(raw, f"{mid}.{old}.".encode() + body, hashlib.sha256).digest()).decode()
    assert not _verify(secret, mid, old, body, f"v1,{sig_old}")
    assert not _verify(secret, "", ts, body, f"v1,{sig}")


# Upload magic-byte checks
@pytest.mark.parametrize("purpose,name,ctype,data", [
    ("logo", "a.png", "image/png", b"hello this is text"),
    ("logo", "a.png", "image/png", b"MZ\x90\x00" + b"\x00" * 60),
    ("logo", "a.jpg", "image/jpeg", PNG),
    ("verification_doc", "a.pdf", "application/pdf", b"MZ\x90\x00"),
    ("logo", "a.webp", "image/webp", b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 20),
])
def test_08_upload_mismatch_rejected(buyer, purpose, name, ctype, data):
    mongo.rate_limits.delete_many({"key": {"$regex": "^upload:"}})
    r = buyer["c"].post("/files", data={"purpose": purpose}, files={"file": (name, data, ctype)})
    assert r.status_code == 422, r.text
    assert "File content does not match its type." in r.text


@pytest.mark.parametrize("purpose,name,ctype,data", [
    ("logo", "TEST_a.png", "image/png", PNG),
    ("logo", "TEST_a.jpg", "image/jpeg", JPG),
    ("logo", "TEST_a.webp", "image/webp", WEBP),
    ("verification_doc", "TEST_a.pdf", "application/pdf", PDF),
])
def test_09_upload_valid_accepted(buyer, purpose, name, ctype, data):
    mongo.rate_limits.delete_many({"key": {"$regex": "^upload:"}})
    r = buyer["c"].post("/files", data={"purpose": purpose}, files={"file": (name, data, ctype)})
    assert r.status_code == 201, r.text
    j = r.json()
    MADE["files"].append(j["id"])
    pub = httpx.get(f"{BASE}/files/{j['id']}", timeout=60)
    if purpose == "verification_doc":
        assert j["url"] is None and pub.status_code == 404
    else:
        assert pub.status_code == 200 and pub.content == data


# Launch checklist new manual items
def test_10_launch_items():
    a = admin_client()
    r = a.get("/admin/launch/checklist")
    assert r.status_code == 200, r.text
    keys = {i.get("key") for i in (r.json().get("items") or r.json().get("data") or [])}
    assert {"email_sending", "do_hosting", "storage_review"} <= keys, keys
