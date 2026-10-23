import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta

import httpx
import pytest
import stripe

from tests.test_phase03_vendors import _ENV, mongo
from tests.test_phase06_cart import START, account, admin_client, live, vendor
from tests.test_phase06_cart import cleanup as _p6_cleanup  # noqa: F401  (removes TEST6_ users/vendors/products/orders)

stripe.api_key = _ENV["STRIPE_SECRET_KEY"]
HOOK = _ENV["FRONTEND_URL"] + "/api/stripe/webhook"
TAG = uuid.uuid4().hex[:6].upper()
S = {}


@pytest.fixture(scope="module", autouse=True)
def cleanup7():
    yield
    buyers = S.get("buyers", [])
    pays = [p["_id"] for p in mongo.payments.find({"customer_id": {"$in": buyers}})]
    vos = [v["_id"] for v in mongo.vendor_orders.find({"customer_id": {"$in": buyers}})]
    mongo.commission_ledger.delete_many({"$or": [{"payment_id": {"$in": pays}}, {"vendor_order_id": {"$in": vos}}]})
    for coll, field in (("payouts", "vendor_order_id"), ("order_items", "vendor_order_id"), ("shipments", "vendor_order_id"),
                        ("order_requests", "vendor_order_id"), ("order_events", "vendor_order_id"), ("notification_log", "vendor_order_id")):
        mongo[coll].delete_many({field: {"$in": vos}})
    mongo.pickup_slots.delete_many({"vendor_id": {"$in": S.get("vendor_ids", [])}})
    for coll in ("refunds", "disputes"):
        mongo[coll].delete_many({"payment_id": {"$in": pays}})
    mongo.vendor_orders.delete_many({"_id": {"$in": vos}})
    mongo.payments.delete_many({"_id": {"$in": pays}})
    mongo.connected_accounts.delete_many({"vendor_id": {"$in": S.get("vendor_ids", [])}})
    mongo.webhook_events.delete_many({"event_id": {"$regex": f"^evt_t7{TAG}"}})
    mongo.commission_rules.delete_many({"note": {"$regex": "^TEST7"}})
    mongo.audit_logs.delete_many({"created_at": {"$gte": START}, "action": {"$regex": "^(payment|admin.refund|admin.payout|admin.dispute|admin.commission|vendor.payout|vendor.dispute)"}})
    mongo.shipping_methods.delete_many({"name": {"$regex": f"^TEST7 {TAG}"}})
    mongo.tax_rates.delete_many({"label": {"$regex": "^TEST7"}})


def send(event_type: str, obj: dict, secret: str = _ENV["STRIPE_WEBHOOK_SECRET"], event_id: str | None = None, **extra) -> httpx.Response:
    payload = json.dumps({"id": event_id or f"evt_t7{TAG}{uuid.uuid4().hex[:10]}", "object": "event", "type": event_type, "data": {"object": obj}, **extra})
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
    return httpx.post(HOOK, content=payload, headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"}, timeout=90)


def real_pi(amount: int):
    return stripe.PaymentIntent.create(amount=amount, currency="usd", payment_method="pm_card_visa", confirm=True,
                                       automatic_payment_methods={"enabled": True, "allow_redirects": "never"})


def draft(c, items: list[tuple[str, int]]) -> dict:
    for vid, q in items:
        assert c.post("/cart/items", json={"variant_id": vid, "quantity": q}).status_code == 200
    addr = c.post("/account/addresses", json={"full_name": "TEST Buyer", "line1": "1 Main St", "city": "Boston", "country": "ZY"}).json()
    c.put("/cart/address", json={"address_id": addr.get("id") or addr["address"]["id"]})
    r = c.post("/checkout/start", headers={"Idempotency-Key": f"t7-{uuid.uuid4().hex}"})
    assert r.status_code == 200, r.text
    return r.json()["order"]


def start_pay(c, order_id: str) -> dict:
    r = c.post(f"/payments/orders/{order_id}/checkout", json={"origin_url": _ENV["FRONTEND_URL"]})
    assert r.status_code == 200, r.text
    assert r.json()["checkout_url"].startswith("https://checkout.stripe.com")
    return mongo.payments.find_one({"_id": __import__("bson").ObjectId(r.json()["payment_id"])})


def completed(p: dict, pi_id: str, amount: int | None = None) -> dict:
    return {"id": p["provider_session_id"], "object": "checkout.session", "payment_status": "paid", "status": "complete", "payment_intent": pi_id,
            "amount_total": p["amount_minor"] if amount is None else amount, "currency": "usd", "metadata": {"payment_id": str(p["_id"])}}


def buyer():
    c, email = account()
    S.setdefault("buyers", []).append(mongo.users.find_one({"email": email})["_id"])
    return c


@pytest.fixture(scope="module")
def w():
    adm = admin_client()
    a, slug_a = vendor(adm)
    b, slug_b = vendor(adm)
    S["vendor_ids"] = [mongo.vendor_stores.find_one({"slug": s})["vendor_id"] for s in (slug_a, slug_b)]
    adm.post("/admin/commerce/shipping-methods", json={"name": f"TEST7 {TAG} Flat", "amount_minor": 500})
    adm.post("/admin/commerce/tax-rates", json={"country": "ZY", "rate_bps": 625, "label": "TEST7 tax"})
    assert adm.post("/admin/payments/commission-rules", json={"scope": "category", "target": "fashion", "rate_bps": 1500, "note": "TEST7 cat"}).status_code == 201
    assert adm.post("/admin/payments/commission-rules", json={"scope": "vendor", "target": slug_b, "rate_bps": 1200, "note": "TEST7 vendor"}).status_code == 201
    assert a.post("/admin/payments/commission-rules", json={"scope": "default", "rate_bps": 0}).status_code == 403
    return {"adm": adm, "a": a, "b": b, "slug_a": slug_a, "slug_b": slug_b,
            "scarf": live(a, adm, f"TEST7 Scarf {TAG}", 4500, 5), "shea": live(b, adm, f"TEST7 Shea {TAG}", 1500, 10)}


def test_01_multi_vendor_payment_success_commission_fee_and_duplicates(w):
    c = buyer()
    order = draft(c, [(w["scarf"][1], 2), (w["shea"][1], 3)])
    assert c.post(f"/payments/orders/{order['id']}/checkout", json={"origin_url": "https://evil.example"}).status_code == 422
    p = start_pay(c, order["id"])
    plan = {g["vendor_slug"]: g for g in p["plan"]}
    assert plan[w["slug_a"]]["charged_minor"] == 9000 + 500 + 563 and plan[w["slug_b"]]["charged_minor"] == 4500 + 500 + 281
    assert p["amount_minor"] == 15344
    assert plan[w["slug_a"]]["commission_minor"] == 1350 and plan[w["slug_a"]]["lines"][0]["commission_source"] == "category"
    assert plan[w["slug_b"]]["commission_minor"] == 540 and plan[w["slug_b"]]["lines"][0]["commission_source"] == "vendor"
    again = c.post(f"/payments/orders/{order['id']}/checkout", json={"origin_url": _ENV["FRONTEND_URL"]}).json()
    assert again["reused"] is True and mongo.payments.count_documents({"order_id": p["order_id"]}) == 1
    assert c.get(f"/payments/orders/{order['id']}").json()["order"]["status"] == "pending_payment"  # redirect alone never marks paid
    assert send("checkout.session.completed", completed(p, "pi_x"), secret="whsec_wrong").status_code == 400
    pi = real_pi(15344)
    eid = f"evt_t7{TAG}paid"
    assert send("checkout.session.completed", completed(p, pi.id), event_id=eid).json()["status"] == "ok"
    assert send("checkout.session.completed", completed(p, pi.id), event_id=eid).json()["status"] == "duplicate"
    assert send("checkout.session.completed", completed(p, pi.id)).json()["status"] == "ok"  # new event id, same payment: no double-processing
    o = c.get(f"/payments/orders/{order['id']}").json()["order"]
    assert o["status"] == "paid" and o["payment"]["status"] == "succeeded" and len(o["vendor_orders"]) == 2
    for _ in range(15):  # Stripe attaches the balance transaction (actual fee) asynchronously
        if w["adm"].post(f"/admin/payments/payments/{p['_id']}/sync-fee").json()["fee_recorded"]:
            break
        time.sleep(2)
    pay = mongo.payments.find_one({"_id": p["_id"]})
    assert pay["fee_minor"] and pay["fee_minor"] > 0
    vos = list(mongo.vendor_orders.find({"payment_id": p["_id"]}))
    assert sum(v["fee_minor"] for v in vos) == pay["fee_minor"]
    assert mongo.commission_ledger.count_documents({"payment_id": p["_id"], "type": "gross_sale"}) == 2
    items = list(mongo.order_items.find({"order_id": p["order_id"]}))
    assert {i["commission_bps"] for i in items} == {1500, 1200}
    inv = mongo.inventory.find_one({"variant_id": __import__("bson").ObjectId(w["scarf"][1])})
    assert inv["quantity_on_hand"] == 5 and inv["quantity_reserved"] == 2  # reserved at payment, deducted at shipment
    assert c.post(f"/payments/orders/{order['id']}/checkout", json={"origin_url": _ENV["FRONTEND_URL"]}).status_code == 409
    rec = w["adm"].get("/admin/payments/reconciliation").json()
    assert not [i for i in rec["issues"] if i.get("payment_id") == str(p["_id"])]
    S.update(c=c, order=order, payment=p, pi=pi.id)


def test_02_amount_mismatch_and_isolation(w):
    c = buyer()
    order = draft(c, [(w["shea"][1], 1)])
    p = start_pay(c, order["id"])
    send("checkout.session.completed", completed(p, real_pi(100).id, amount=100))
    assert mongo.payments.find_one({"_id": p["_id"]})["status"] == "needs_review"
    assert mongo.orders.find_one({"_id": p["order_id"]})["status"] == "pending_payment"
    assert c.get(f"/payments/orders/{S['order']['id']}").status_code == 404
    assert w["a"].get("/admin/payments/payments").status_code == 403
    assert c.get("/vendor/payments/summary").status_code == 403


def test_03_cancel_and_failed_payment(w):
    c = buyer()
    order = draft(c, [(w["shea"][1], 1)])
    p1 = start_pay(c, order["id"])
    o = c.post(f"/payments/orders/{order['id']}/cancel").json()["order"]
    assert o["status"] == "draft" and mongo.payments.find_one({"_id": p1["_id"]})["status"] == "cancelled"
    p2 = start_pay(c, order["id"])
    assert p2["_id"] != p1["_id"] and p2["idempotency_key"].endswith(":2")
    send("checkout.session.async_payment_failed", {"id": p2["provider_session_id"], "object": "checkout.session"})
    assert mongo.payments.find_one({"_id": p2["_id"]})["status"] == "failed"
    assert mongo.orders.find_one({"_id": p2["order_id"]})["status"] == "draft"


def test_04_partial_refund_one_vendor(w):
    adm, p = w["adm"], S["payment"]
    va = mongo.vendor_orders.find_one({"payment_id": p["_id"], "vendor_slug": w["slug_a"]})
    vb = mongo.vendor_orders.find_one({"payment_id": p["_id"], "vendor_slug": w["slug_b"]})
    b_before = sum(e["amount_minor"] for e in mongo.commission_ledger.find({"vendor_order_id": vb["_id"], "account": "vendor"}))
    item = mongo.order_items.find_one({"vendor_order_id": va["_id"]})
    key = {"Idempotency-Key": f"rf-{uuid.uuid4().hex}"}
    body = {"lines": [{"order_item_id": str(item["_id"]), "quantity": 1}], "reason": "TEST damaged"}
    assert w["a"].post(f"/admin/payments/vendor-orders/{va['_id']}/refunds", json=body, headers=key).status_code == 403
    r = adm.post(f"/admin/payments/vendor-orders/{va['_id']}/refunds", json=body, headers=key).json()["refund"]
    assert r["amount_minor"] == 4500 + 281 and r["commission_returned_minor"] == 675 and r["vendor_debit_minor"] == 4500 - 675
    assert r["status"] == "succeeded"
    assert adm.post(f"/admin/payments/vendor-orders/{va['_id']}/refunds", json=body, headers=key).json()["replayed"] is True
    over = {"lines": [{"order_item_id": str(item["_id"]), "quantity": 2}], "reason": "TEST too many"}
    assert adm.post(f"/admin/payments/vendor-orders/{va['_id']}/refunds", json=over, headers={"Idempotency-Key": f"rf-{uuid.uuid4().hex}"}).status_code == 422
    assert sum(e["amount_minor"] for e in mongo.commission_ledger.find({"vendor_order_id": vb["_id"], "account": "vendor"})) == b_before
    assert mongo.orders.find_one({"_id": p["order_id"]})["status"] == "partially_refunded"
    assert stripe.PaymentIntent.retrieve(S["pi"], expand=["latest_charge"]).latest_charge.amount_refunded == 4781


def test_05_dispute_attributed_to_one_vendor(w):
    adm, p = w["adm"], S["payment"]
    dp = {"id": f"dp_t7{TAG}", "object": "dispute", "payment_intent": S["pi"], "amount": 5281, "currency": "usd", "status": "needs_response",
          "reason": "product_not_received", "evidence_details": {"due_by": int(time.time()) + 86400 * 7}}
    send("charge.dispute.created", dp)
    send("charge.dispute.created", dp)
    d = mongo.disputes.find_one({"provider_dispute_id": dp["id"]})
    assert d and mongo.disputes.count_documents({"provider_dispute_id": dp["id"]}) == 1
    vos = {v["vendor_slug"]: v for v in mongo.vendor_orders.find({"payment_id": p["_id"]})}
    assert all(any(h["active"] for h in v["holds"]) for v in vos.values())
    summary = w["b"].get("/vendor/payments/summary").json()
    assert summary["disputes"][0]["status"] == "needs_response"
    assert w["b"].post(f"/vendor/payments/disputes/{d['_id']}/evidence", json={"text": "TEST tracking 1Z999 delivered"}).status_code == 200
    vb, va = vos[w["slug_b"]], vos[w["slug_a"]]
    r = adm.post(f"/admin/payments/disputes/{d['_id']}/attribute", json={"attributions": [
        {"vendor_order_id": str(vb["_id"]), "amount_minor": 5281, "vendor_liable": True}, {"vendor_order_id": str(va["_id"]), "amount_minor": 0, "vendor_liable": False}]})
    assert r.status_code == 200
    assert not any(h["active"] for h in mongo.vendor_orders.find_one({"_id": va["_id"]})["holds"])
    a_before = sum(e["amount_minor"] for e in mongo.commission_ledger.find({"vendor_order_id": va["_id"], "account": "vendor"}))
    send("charge.dispute.closed", {**dp, "status": "lost", "balance_transactions": [{"fee": 1500}]})
    debit = sum(e["amount_minor"] for e in mongo.commission_ledger.find({"vendor_order_id": vb["_id"], "account": "vendor", "type": {"$in": ["dispute_debit", "dispute_fee", "commission_reversal"]}}))
    assert debit == -5281 - 1500 + 540
    assert sum(e["amount_minor"] for e in mongo.commission_ledger.find({"vendor_order_id": va["_id"], "account": "vendor"})) == a_before
    send("charge.dispute.closed", {**dp, "status": "lost", "balance_transactions": [{"fee": 1500}]})
    assert mongo.commission_ledger.count_documents({"vendor_order_id": vb["_id"], "type": "dispute_debit"}) == 1
    assert w["b"].get("/vendor/payments/summary").json()["balances"]["owed_minor"] > 0


def test_06_payout_release_idempotent(w):
    adm, p = w["adm"], S["payment"]
    va = mongo.vendor_orders.find_one({"payment_id": p["_id"], "vendor_slug": w["slug_a"]})
    mongo.vendor_orders.update_one({"_id": va["_id"]}, {"$set": {"eligible_at": va["created_at"] - timedelta(days=1)}})
    vid = str(va["vendor_id"])
    assert adm.post("/admin/payments/payouts/release", json={"vendor_id": vid}).json()["skipped"]
    on = w["a"].post("/vendor/payments/onboarding", json={"country": "US"}).json()
    assert on["mode"] in ("simulated", "stripe")
    assert w["a"].post("/vendor/payments/onboarding", json={"country": "NG"}).status_code == 422
    if on["mode"] == "simulated":
        assert w["a"].post("/vendor/payments/onboarding/simulate-complete").status_code == 200
    balance = sum(e["amount_minor"] for e in mongo.commission_ledger.find({"vendor_order_id": va["_id"], "account": "vendor"}))
    assert balance == 9000 + 500 - 1350 - va["fee_minor"] - (4500 - 675)
    r = adm.post("/admin/payments/payouts/release", json={"vendor_id": vid}).json()
    assert r["released"] == 1 and r["amount_minor"] == balance
    assert adm.post("/admin/payments/payouts/release", json={"vendor_id": vid}).json()["released"] == 0
    assert mongo.payouts.count_documents({"vendor_order_id": va["_id"]}) == 1
    s = w["a"].get("/vendor/payments/summary").json()
    assert s["balances"]["transferred_minor"] == balance and s["vendor_orders"][0]["earning_status"] == "transferred"
    payout = mongo.payouts.find_one({"vendor_order_id": va["_id"]})
    assert adm.post(f"/admin/payments/payouts/{payout['_id']}/simulate-paid").status_code == 200
    assert w["a"].get("/vendor/payments/summary").json()["balances"]["paid_minor"] == balance
    rec = adm.get("/admin/payments/reconciliation").json()
    assert not [i for i in rec["issues"] if i.get("payment_id") == str(p["_id"])]


def test_07_saved_for_later(w):
    c = buyer()
    c.post("/cart/items", json={"variant_id": w["shea"][1], "quantity": 2})
    cart = c.post(f"/cart/items/{w['shea'][1]}/save-for-later").json()
    assert cart["item_count"] == 0 and cart["saved"][0]["quantity"] == 2 and cart["saved"][0]["status"] == "ok"
    cart = c.post(f"/cart/saved/{w['shea'][1]}/move-to-cart").json()
    assert cart["item_count"] == 2 and cart["saved"] == []
    c.post(f"/cart/items/{w['shea'][1]}/save-for-later")
    assert c.delete(f"/cart/saved/{w['shea'][1]}").json()["saved"] == []
    assert c.delete(f"/cart/saved/{w['shea'][1]}").status_code == 404
