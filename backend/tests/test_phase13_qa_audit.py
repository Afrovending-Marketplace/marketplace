# Phase 13 QA audit: authz/isolation, injection, CSRF, uploads, rate limits, cron secret, headers, oversell of last unit
import io
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
from bson import ObjectId

from tests.test_phase03_vendors import BASE, PNG, _ENV, mongo
from tests.test_phase06_cart import live
from tests.test_phase07_payments import (S, _p6_cleanup, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w)  # noqa: F401
from tests import test_phase10_admin as p10

TICKETS: list = []


def teardown_module():
    mongo.support_tickets.delete_many({"_id": {"$in": TICKETS}})
    ids = S.get("buyers", [])
    mongo.files.delete_many({"owner_user_id": {"$in": ids}})
    mongo.notifications.delete_many({"user_id": {"$in": ids}})
    mongo.rate_limits.delete_many({"key": {"$regex": "^(login|forgot):.*qa13"}})
    p10.teardown_module()


# --- security headers / request id / health
def test_01_headers_request_id_health():
    r = httpx.get(f"{BASE}/health", timeout=30)
    assert r.status_code == 200 and r.json()["database"] == "ok"
    assert r.headers.get("x-content-type-options") == "nosniff" and r.headers.get("x-request-id")
    e = httpx.get(f"{BASE}/catalog/products/does-not-exist-qa13", timeout=30)
    assert e.status_code == 404 and e.json()["error"]["request_id"]
    missing = [h for h in ("strict-transport-security", "x-frame-options", "referrer-policy") if h not in r.headers]
    open("/tmp/qa13_headers.txt", "w").write(repr(missing))


# --- CSRF origin guard
def test_02_foreign_origin_rejected_with_cookie():
    c = buyer()
    r = c.patch("/account/profile", json={"name": "TEST_hacked"}, headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    r = c.post("/cart/items", json={"variant_id": str(ObjectId()), "quantity": 1}, headers={"Origin": "null"})
    assert r.status_code == 403
    ok = c.get("/auth/me", headers={"Origin": "https://evil.example.com"})
    assert ok.status_code == 200  # GET is not state-changing


# --- Mongo operator injection
def test_03_operator_injection():
    g = httpx.Client(base_url=BASE, timeout=30)
    r = g.post("/auth/login", json={"email": {"$ne": None}, "password": {"$ne": None}})
    assert r.status_code == 422
    r = g.post("/auth/forgot-password", json={"email": {"$gt": ""}})
    assert r.status_code == 422
    for q in ("/catalog/search?q[$ne]=x", "/catalog/products?category[$ne]=x", "/catalog/search?q=%7B%22%24ne%22%3Anull%7D", "/catalog/products/%7B%24ne%7D"):
        assert g.get(q).status_code in (200, 404, 422), q


# --- customer isolation + XSS stored raw (React escapes on render)
def test_04_customer_isolation_tickets_notifications_wishlist():
    a, b = buyer(), buyer()
    t = a.post("/support/tickets", json={"category": "other", "subject": "<script>alert(1)</script> help", "body": "<img src=x onerror=alert(1)> please help"})
    assert t.status_code == 201, t.text
    tid = t.json().get("id") or t.json()["ticket"]["id"]
    TICKETS.append(ObjectId(tid))
    assert b.get(f"/support/tickets/{tid}").status_code == 404
    assert b.post(f"/support/tickets/{tid}/replies", json={"body": "intrude"}).status_code == 404
    assert all(x["id"] != tid for x in (b.get("/support/tickets").json().get("tickets") or b.get("/support/tickets").json().get("items") or []))
    n = mongo.notifications.insert_one({"user_id": S["buyers"][-2], "category": "support", "title": "TEST", "body": "x", "read_at": None, "created_at": mongo.users.find_one()["created_at"]}).inserted_id
    assert b.post(f"/notifications/{n}/read").status_code in (404, 403)
    assert mongo.notifications.find_one({"_id": n})["read_at"] is None
    assert b.get("/support/tickets/{\"$ne\":null}").status_code in (404, 422)


# --- vendor cross-isolation
def test_05_vendor_cross_isolation(w):  # noqa: F811
    pid_a = mongo.product_variants.find_one({"_id": ObjectId(w["scarf"][1])})["product_id"]
    b = w["b"]
    assert b.get(f"/vendor/products/{pid_a}").status_code in (403, 404)
    full = {"title": "TEST stolen", "description": "Made by hand with care and tradition.", "category_slug": "fashion", "sku": "STOLEN1", "price_minor": 1}
    assert b.patch(f"/vendor/products/{pid_a}", json=full).status_code in (403, 404)
    assert b.post(f"/vendor/inventory/{w['scarf'][1]}/adjust", json={"delta": 50, "reason": "restock", "note": "x"}).status_code in (403, 404, 422)
    assert b.delete(f"/vendor/products/{pid_a}").status_code in (403, 404)
    assert mongo.products.find_one({"_id": pid_a})["title"].startswith("TEST7 Scarf")
    any_vo = mongo.vendor_orders.find_one({"vendor_id": {"$ne": S["vendor_ids"][1]}})
    if any_vo:
        assert b.get(f"/vendor/orders/{any_vo['_id']}/messages").status_code in (403, 404)
        assert b.post(f"/vendor/orders/{any_vo['_id']}/status", json={"status": "processing"}).status_code in (403, 404, 422)
    c = buyer()
    assert c.get("/vendor/dashboard").status_code == 403
    assert c.get("/vendor/payments/statements").status_code == 403
    assert c.get("/admin/users").status_code == 403


# --- uploads
def test_06_uploads_type_size_private():
    c = buyer()
    f = lambda name, data, ct, purpose: c.post("/files", data={"purpose": purpose}, files={"file": (name, io.BytesIO(data), ct)})
    assert f("x.svg", b"<svg onload=alert(1)>", "image/svg+xml", "logo").status_code == 422
    assert f("x.html", b"<script>alert(1)</script>", "text/html", "logo").status_code == 422
    assert f("big.png", PNG + b"0" * 2_100_000, "image/png", "logo").status_code == 422
    assert f("x.png", PNG, "image/png", "nope").status_code == 422
    doc = f("doc.pdf", b"%PDF-1.4 test", "application/pdf", "verification_doc")
    assert doc.status_code == 201 and doc.json()["url"] is None
    assert httpx.get(f"{BASE}/files/{doc.json()['id']}", timeout=30).status_code == 404
    rp = f("r.png", PNG, "image/png", "review_photo")
    assert rp.status_code == 201
    assert httpx.get(f"{BASE}/reviews/photos/{rp.json()['id']}", timeout=30).status_code == 404  # never approved
    spoof = f("evil.png", b"<html><script>alert(1)</script></html>", "image/png", "logo")
    open("/tmp/qa13_spoof.txt", "w").write(str(spoof.status_code))


# --- rate limiting / lockout
def test_07_login_lockout():
    g = httpx.Client(base_url=BASE, timeout=30)
    email = f"qa13_{uuid.uuid4().hex[:6]}@example.com"
    codes = [g.post("/auth/login", json={"email": email, "password": "WrongPass12345"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[-1] == 429, codes
    mongo.rate_limits.delete_many({"key": {"$regex": email}})


# --- cron secrets
def test_08_cron_requires_secret():
    for path in ("/cron/wishlist-alerts", "/cron/abandoned-carts", "/cron/payout-release"):
        assert httpx.post(f"{BASE}{path}", timeout=30).status_code == 401
        assert httpx.post(f"{BASE}{path}", headers={"Authorization": "Bearer wrong", "X-Webhook-Id": "qa13"}, timeout=30).status_code == 401


# --- granular admin permissions
def test_09_admin_role_permissions():
    sup, _ = p10.admin_with("support_admin")
    con, _ = p10.admin_with("content_admin")
    fin, _ = p10.admin_with("finance_admin")
    assert sup.get("/admin/payments/payments").status_code == 403
    assert sup.put("/admin/marketing/flags", json={"wishlist_alerts_enabled": True}).status_code == 403
    assert con.get("/admin/payments/payments").status_code == 403
    assert con.get("/admin/audit-logs").status_code == 403
    assert fin.put("/admin/marketing/flags", json={"wishlist_alerts_enabled": True}).status_code == 403
    assert fin.post("/admin/team/invites", json={"email": "qa13@example.com", "role": "super_admin"}).status_code == 403
    assert fin.get("/admin/payments/payments").status_code == 200
    assert sup.get("/admin/support/tickets").status_code == 200


# --- overselling: two shoppers pay for the last unit
def test_10_last_unit_concurrent_checkout(w):  # noqa: F811
    pid, vid = live(w["a"], w["adm"], f"TEST7 LastUnit {uuid.uuid4().hex[:5]}", 2000, 1)
    b1, b2 = buyer(), buyer()
    o1, o2 = draft(b1, [(vid, 1)]), draft(b2, [(vid, 1)])
    with ThreadPoolExecutor(2) as ex:
        r = list(ex.map(lambda x: x[0].post(f"/payments/orders/{x[1]['id']}/checkout", json={"origin_url": _ENV["FRONTEND_URL"]}), [(b1, o1), (b2, o2)]))
    codes = [x.status_code for x in r]
    print("concurrent stripe-session codes:", codes)
    pays = [mongo.payments.find_one({"_id": ObjectId(x.json()["payment_id"])}) for x in r if x.status_code == 200]
    for p in pays:
        send("checkout.session.completed", completed(p, real_pi(p["amount_minor"]).id))
    time.sleep(2)
    inv = mongo.inventory.find_one({"variant_id": ObjectId(vid)})
    vos = list(mongo.vendor_orders.find({"payment_id": {"$in": [p["_id"] for p in pays]}}))
    paid = [mongo.orders.find_one({"_id": p["order_id"]})["status"] for p in pays]
    print("order statuses:", paid, "inventory:", inv["quantity_on_hand"], inv["quantity_reserved"], "stock_issue:", [v.get("stock_issue") for v in vos])
    assert inv["quantity_reserved"] <= inv["quantity_on_hand"]
    S["oversell"] = {"codes": codes, "paid": paid, "inv": [inv["quantity_on_hand"], inv["quantity_reserved"]], "stock_issue": [v.get("stock_issue") for v in vos]}
    open("/tmp/qa13_oversell.txt", "w").write(repr(S["oversell"]))
    assert paid.count("paid") <= 1, "OVERSOLD: two shoppers charged for the last unit"
