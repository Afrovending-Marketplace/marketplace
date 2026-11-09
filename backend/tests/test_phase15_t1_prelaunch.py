# ruff: noqa: F811

# Iteration 27 pre-launch verification (T1): F1 concurrent last-unit race, F2 public lockout, admin access, tenant isolation, refund ledger immutability
import concurrent.futures
import uuid

import httpx
from bson import ObjectId

from tests.test_phase03_vendors import BASE, _ENV, mongo
from tests.test_phase06_cart import live
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w  # noqa: F401

TAG = uuid.uuid4().hex[:6]


def teardown_module():
    mongo.rate_limits.delete_many({"key": {"$regex": f"t1p15{TAG}"}})
    ids = S.get("buyers", [])
    mongo.notifications.delete_many({"user_id": {"$in": ids}})


def inv(vid):
    d = mongo.inventory.find_one({"variant_id": ObjectId(vid)})
    return d["quantity_on_hand"], d.get("quantity_reserved", 0)


def co(c, oid_):
    return c.post(f"/payments/orders/{oid_}/checkout", json={"origin_url": _ENV["FRONTEND_URL"]})


# F1: two buyers race for the last unit at the same time -> exactly one session, the other 409; cancel releases once; loser can retry
def test_01_concurrent_last_unit(w):
    pid, vid = live(w["a"], w["adm"], f"TEST7 Last {TAG}", 2000, 1)
    b1, b2 = buyer(), buyer()
    o1, o2 = draft(b1, [(vid, 1)]), draft(b2, [(vid, 1)])
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        rs = list(ex.map(lambda t: co(*t), [(b1, o1["id"]), (b2, o2["id"])]))
    codes = sorted(r.status_code for r in rs)
    print("race codes:", codes, [r.text[:120] for r in rs])
    assert codes == [200, 409]
    assert [r.json()["error"]["code"] for r in rs if r.status_code == 409][0] in ("out_of_stock", "checkout_changed")
    assert inv(vid) == (1, 1)
    winner = (b1, o1) if rs[0].status_code == 200 else (b2, o2)
    loser = (b2, o2) if winner[0] is b1 else (b1, o1)
    # cancel twice + late expired webhook -> released exactly once
    assert winner[0].post(f"/payments/orders/{winner[1]['id']}/cancel").status_code == 200
    assert winner[0].post(f"/payments/orders/{winner[1]['id']}/cancel").status_code == 200
    p = mongo.payments.find_one({"order_id": ObjectId(winner[1]["id"]), "provider_session_id": {"$exists": True}})
    send("checkout.session.expired", {"id": p["provider_session_id"], "object": "checkout.session", "status": "expired", "payment_status": "unpaid",
                                      "metadata": {"payment_id": str(p["_id"])}})
    assert inv(vid) == (1, 0), inv(vid)
    # loser retries and now gets the unit
    r = co(*[loser[0], loser[1]["id"]])
    print("loser retry:", r.status_code, r.text[:120])
    assert r.status_code == 200
    assert inv(vid) == (1, 1)
    loser[0].post(f"/payments/orders/{loser[1]['id']}/cancel")
    assert inv(vid) == (1, 0)


# F2: live public URL lockout per client+email; spoofed forwarding headers do not escape the bucket; other email not locked
def test_02_public_lockout_and_spoof():
    email = f"t1p15{TAG}@example.com"
    c = httpx.Client(base_url=BASE, timeout=30)
    codes = [c.post("/auth/login", json={"email": email, "password": "WrongPass12345"}).status_code for _ in range(6)]
    print("bad logins:", codes)
    assert codes[:5] == [401] * 5 and codes[5] == 429
    spoof = [c.post("/auth/login", json={"email": email, "password": "WrongPass12345"}, headers=h).status_code
             for h in ({"X-Forwarded-For": "9.9.9.9"}, {"CF-Connecting-IP": "9.9.9.8"}, {"X-Real-IP": "9.9.9.7"})]
    print("spoofed header codes:", spoof)
    assert all(x in (429, 403) for x in spoof)  # 403 = Cloudflare error 1000 for a client-sent CF-Connecting-IP (never reaches the app)
    other = c.post("/auth/login", json={"email": f"x{email}", "password": "WrongPass12345"}).status_code
    assert other == 401


# Customer / vendor cannot reach /api/v1/admin/*
def test_03_non_admin_blocked(w):
    paths = ["/admin/users", "/admin/audit-logs", "/admin/payments/config", "/admin/payments/refunds", "/admin/payments/ledger",
             "/admin/vendor-applications", "/admin/fulfillment/config", "/admin/payments/payouts"]
    cust = buyer()
    for who, c in (("customer", cust), ("vendor", w["a"])):
        codes = {p: c.get(p).status_code for p in paths}
        print(who, codes)
        assert all(v in (401, 403) for v in codes.values()), codes
    anon = httpx.Client(base_url=BASE, timeout=30)
    assert all(anon.get(p).status_code == 401 for p in paths)


# Tenant isolation: vendor B cannot read/edit vendor A products, inventory or vendor orders
def test_04_tenant_isolation(w):
    pid, vid = w["scarf"]
    b = w["b"]
    assert b.get(f"/vendor/products/{pid}").status_code in (403, 404)
    assert b.patch(f"/vendor/products/{pid}", json={"title": "hijack", "description": "Made by hand with care and tradition.", "category_slug": "fashion", "sku": "HIJACK1", "price_minor": 100}).status_code in (403, 404)
    assert b.post(f"/vendor/products/{pid}/archive").status_code in (403, 404)
    assert b.post(f"/vendor/inventory/{vid}/adjust", json={"delta": 5, "reason": "TEST"}).status_code in (403, 404, 422)
    assert b.get(f"/vendor/products/{pid}/stock-history").status_code in (403, 404)
    mine = [x["id"] for x in b.get("/vendor/products").json().get("data", [])]
    assert pid not in mine
    # paid order for A only, B must not see it
    c = buyer()
    o = draft(c, [(vid, 1)])
    p = start_pay(c, o["id"])
    pi = real_pi(p["amount_minor"])
    assert send("checkout.session.completed", completed(p, pi.id)).status_code == 200
    vo = mongo.vendor_orders.find_one({"order_id": ObjectId(o["id"])})
    b_orders = b.get("/vendor/orders").json()
    assert str(vo["_id"]) not in str(b_orders)
    assert b.post(f"/vendor/orders/{vo['_id']}/status", json={"to": "accepted"}).status_code in (403, 404)
    assert b.get(f"/vendor/orders/{vo['_id']}/packing-slip").status_code in (403, 404)
    assert str(vo["_id"]) in str(w["a"].get("/vendor/orders").json())
    # another customer cannot read the order
    assert buyer().get(f"/payments/orders/{o['id']}").status_code in (403, 404)
    S["iso_vo"], S["iso_order"] = vo["_id"], o["id"]


# Refunds: full refund on a vendor order appends ledger rows (existing rows untouched), reverses commission, order -> refunded
def test_05_full_refund_ledger_append_only(w):
    vo = mongo.vendor_orders.find_one({"_id": S["iso_vo"]})
    before = {str(e["_id"]): e for e in mongo.commission_ledger.find({"vendor_order_id": vo["_id"]})}
    item = mongo.order_items.find_one({"vendor_order_id": vo["_id"]})
    oh_before = inv(w["scarf"][1])
    body = {"lines": [{"order_item_id": str(item["_id"]), "quantity": 1}], "reason": "TEST full", "include_shipping": True}
    r = w["adm"].post(f"/admin/payments/vendor-orders/{vo['_id']}/refunds", json=body, headers={"Idempotency-Key": f"t1-{uuid.uuid4().hex}"})
    print("refund:", r.status_code, r.text[:300])
    assert r.status_code == 201
    after = {str(e["_id"]): e for e in mongo.commission_ledger.find({"vendor_order_id": vo["_id"]})}
    for k, e in before.items():
        assert after[k] == e, "existing ledger row was modified"
    new = [e for k, e in after.items() if k not in before]
    print("new ledger rows:", [(e["account"], e["type"], e["amount_minor"]) for e in new])
    assert new and any(e["account"] == "platform" and e["amount_minor"] < 0 for e in new)
    vo2 = mongo.vendor_orders.find_one({"_id": vo["_id"]})
    assert vo2["commission_refunded_minor"] == vo["commission_minor"]
    print("order status:", mongo.orders.find_one({"_id": ObjectId(S["iso_order"])})["status"], "inv before/after", oh_before, inv(w["scarf"][1]))


# Refund before shipment: does the fully refunded vendor order stay fulfillable, and is the held stock released? (observational, iteration 27)
def test_06_refunded_unshipped_order_state(w):
    vo = mongo.vendor_orders.find_one({"_id": S["iso_vo"]})
    item = mongo.order_items.find_one({"vendor_order_id": vo["_id"]})
    print("vo status after full refund:", vo["status"], "refunded_qty", item["refunded_qty"], "inv", inv(w["scarf"][1]))
    a = w["a"]
    acc = a.post(f"/vendor/orders/{vo['_id']}/status", json={"to": "accepted"})
    ship = a.post(f"/vendor/orders/{vo['_id']}/shipments", json={"lines": [{"order_item_id": str(item["_id"]), "quantity": 1}], "carrier": "usps",
                                                                 "tracking_number": "9400TEST0001"})
    print("accept after refund:", acc.status_code, "ship after refund:", ship.status_code, ship.text[:160], "inv", inv(w["scarf"][1]))
    assert ship.status_code in (409, 422), "a fully refunded, unshipped item can still be shipped"
