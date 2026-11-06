# Phase 13 iteration 21: Cloudflare-aware client_ip + login lockout, start_payment stock release on Stripe failure / amount mismatch
import asyncio
import uuid

import httpx
import stripe
from bson import ObjectId
from starlette.requests import Request

from tests.test_phase03_vendors import BASE, _ENV, mongo
from tests.test_phase06_cart import live
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, draft, start_pay, w  # noqa: F401

TAG = uuid.uuid4().hex[:6]
CF = "104.22.64.41"
LB = "34.160.159.238"


def teardown_module():
    mongo.rate_limits.delete_many({"key": {"$regex": f"qa21{TAG}"}})


def _req(xff: str, cf: str | None = None) -> Request:
    h = [(b"x-forwarded-for", xff.encode())]
    if cf:
        h.append((b"cf-connecting-ip", cf.encode()))
    return Request({"type": "http", "headers": h, "client": ("10.0.0.1", 1), "method": "GET", "path": "/"})


def inv(vid):
    d = mongo.inventory.find_one({"variant_id": ObjectId(vid)})
    return d["quantity_on_hand"], d.get("quantity_reserved", 0)


# client_ip unit cases (TRUSTED_PROXY_HOPS default 2)
def test_01_client_ip_unit():
    from afrovending.core.security import client_ip
    assert client_ip(_req(f"203.0.113.5, {CF}, {LB}", "203.0.113.5")) == "203.0.113.5"
    assert client_ip(_req(f"203.0.113.5, {CF}, {LB}")) == "203.0.113.5"  # no CF header -> entry left of CF hop
    assert client_ip(_req(f"6.6.6.6, 203.0.113.5, {CF}, {LB}")) == "203.0.113.5"  # spoofed leftmost ignored
    assert client_ip(_req(f"6.6.6.6, 198.51.100.7, {LB}", "9.9.9.9")) == "198.51.100.7"  # CF header ignored when hop not Cloudflare
    assert client_ip(_req(f"{LB}")) == LB
    print("bare CF hop, no header:", client_ip(_req(f"{CF}, {LB}")))


# Live: 6 bad logins from this client -> 429; spoofed CF-Connecting-IP / XFF does not reset the counter
def test_02_live_login_lockout():
    email = f"qa21{TAG}@example.com"
    c = httpx.Client(base_url=BASE, timeout=30)
    codes = []
    for i in range(7):
        hdr = {"X-Forwarded-For": f"8.8.8.{i}"} if i >= 3 else {}  # client-sent CF-Connecting-IP is rejected by Cloudflare (403 error 1000)
        codes.append(c.post("/auth/login", json={"email": email, "password": "WrongPass12345"}, headers=hdr).status_code)
    keys = [d["key"] for d in mongo.rate_limits.find({"key": {"$regex": f"^login:.*qa21{TAG}"}})]
    print("codes:", codes, "keys:", keys)
    assert codes[:5] == [401] * 5 and codes[5] == 429 and codes[6] == 429, codes
    assert len(keys) == 1 and "9.9.9." not in keys[0] and "8.8.8." not in keys[0] and LB not in keys[0]
    # same client, other email: not locked
    assert c.post("/auth/login", json={"email": f"qa21{TAG}b@example.com", "password": "WrongPass12345"}).status_code == 401


# In-process: client A locked out; client B (different CF-Connecting-IP behind a CF hop) is unaffected
def test_03_other_client_unaffected():
    import server
    email = f"qa21{TAG}c@example.com"

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="https://t") as c:
            def h(ip):
                return {"X-Forwarded-For": f"{ip}, {CF}, {LB}", "CF-Connecting-IP": ip}
            a = [(await c.post("/api/v1/auth/login", json={"email": email, "password": "Wrong12345678"}, headers=h("203.0.113.5"))).status_code for _ in range(6)]
            b = (await c.post("/api/v1/auth/login", json={"email": email, "password": "Wrong12345678"}, headers=h("203.0.113.9"))).status_code
            return a, b
    a, b = asyncio.run(run())
    print("client A:", a, "client B:", b)
    assert a[-1] == 429 and b == 401


# In-process: Session.create raises -> 502, stock released, payment failed, retry works; amount mismatch -> 500, stock released
def test_04_start_payment_failure_paths(w, monkeypatch):  # noqa: F811
    import server
    from afrovending.core.db import client as motor_client
    _, vid = live(w["a"], w["adm"], f"TEST21 Fail {TAG}", 1500, 1)
    b = buyer()
    o = draft(b, [(vid, 1)])
    b2 = buyer()
    o2 = draft(b2, [(vid, 1)])
    tok = b.cookies.get("access_token")
    body = {"origin_url": _ENV["FRONTEND_URL"]}
    real_create = stripe.checkout.Session.create

    def boom(*a, **k):
        raise stripe.error.APIConnectionError("TEST21 network down")

    def mismatch(*a, **k):
        s = real_create(*a, **k)
        s["amount_total"] = s["amount_total"] + 1
        return s

    async def run():
        motor_client.get_io_loop = asyncio.get_running_loop  # bind motor to this loop
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="https://t", cookies={"access_token": tok}) as c:
            url = f"/api/v1/payments/orders/{o['id']}/checkout"
            monkeypatch.setattr(stripe.checkout.Session, "create", boom)
            r1 = await c.post(url, json=body)
            st1 = inv(vid)
            monkeypatch.setattr(stripe.checkout.Session, "create", mismatch)
            c.cookies.set("access_token", b2.cookies.get("access_token"))
            r2 = await c.post(f"/api/v1/payments/orders/{o2['id']}/checkout", json=body)
            st2 = inv(vid)
            return r1, st1, r2, st2
    r1, st1, r2, st2 = asyncio.run(run())
    print("create raises:", r1.status_code, r1.text[:150], st1, "| mismatch:", r2.status_code, r2.text[:150], st2)
    pays = list(mongo.payments.find({"order_id": {"$in": [ObjectId(o["id"]), ObjectId(o2["id"])]}}).sort("_id", 1))
    print([(p["status"], p.get("failure"), p.get("stock_reserved")) for p in pays])
    assert r1.status_code == 502 and st1 == (1, 0)
    assert r2.status_code == 500 and r2.json()["error"]["code"] == "amount_mismatch" and st2 == (1, 0)
    assert [p.get("failure") for p in pays] == ["session_create_failed", "amount_mismatch"]
    assert all(p["status"] == "failed" and p["stock_reserved"] is False for p in pays)
    monkeypatch.undo()
    # live retry not stuck in payment_in_progress
    r = b.post(f"/payments/orders/{o['id']}/checkout", json=body)
    print("live retry after session_create_failed:", r.status_code, r.text[:160])
    assert r.status_code == 200, "retry stuck: payment_attempts not bumped on failure -> same idempotency_key -> DuplicateKeyError -> 409"
    assert inv(vid) == (1, 1)
    assert b2.post(f"/payments/orders/{o2['id']}/checkout", json=body).status_code == 409  # last unit held by buyer 1
    assert b.post(f"/payments/orders/{o['id']}/cancel").status_code == 200 and inv(vid) == (1, 0)
    p = start_pay(b2, o2["id"])
    assert p["stock_reserved"] is True and inv(vid) == (1, 1)
    assert b2.post(f"/payments/orders/{o2['id']}/cancel").status_code == 200
