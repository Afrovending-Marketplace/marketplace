import logging
from datetime import timedelta

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

import stripe
from afrovending.api.v1.vendors import ser
from afrovending.core import ledger
from afrovending.core import payments as pay
from afrovending.core.audit import audit
from afrovending.core.catalog import available, oid
from afrovending.core.config import settings
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.fulfillment import release, reserve
from afrovending.core.models import User, utcnow
from afrovending.core.stripe_client import WEBHOOK_SECRET, call, guard

router = APIRouter(prefix="/payments", tags=["payments"])
webhook_router = APIRouter(tags=["stripe-webhook"])
log = logging.getLogger("afrovending.payments")
SESSION_MINUTES = 30


class CheckoutIn(BaseModel):
    origin_url: str = Field(max_length=200)


async def _own_order(order_id: str, user: User) -> dict:
    order = await db.orders.find_one({"_id": oid(order_id), "customer_id": ObjectId(user.id)})
    if not order:
        raise APIError(404, "not_found", "Order not found.")
    return order


async def build_plan(order: dict) -> list[dict]:
    """Re-check every draft line against live data and freeze commission per item. Prices are never taken from the browser."""
    rules = await ledger.active_rules()
    plan = []
    for g in order["vendor_groups"]:
        vendor = await db.vendors.find_one({"_id": ObjectId(g["vendor_id"])})
        if not vendor or vendor["status"] != "active":
            raise APIError(409, "checkout_changed", f"{g['vendor_name']} can't take orders right now. Return to your cart.")
        if g["shipping_minor"] is None:
            raise APIError(409, "shipping_unconfirmed", f"Shipping for {g['vendor_name']} isn't confirmed yet, so payment can't be taken. Contact us or choose another option.")
        weights = [line["line_total_minor"] for line in g["items"]]
        pdisc = g.get("platform_discount_minor", 0)
        vdisc = g["discount_minor"] - pdisc
        discounts, pshares = ledger.split(vdisc, weights), ledger.split(pdisc, weights)
        lines = []
        for line, disc, pshare in zip(g["items"], discounts, pshares):
            v = await db.product_variants.find_one({"_id": ObjectId(line["variant_id"]), "status": "active"})
            p = await db.products.find_one({"_id": ObjectId(line["product_id"]), "status": "active", "vendor_id": vendor["_id"]})
            if not v or not p or v["price_minor"] != line["unit_price_minor"]:
                raise APIError(409, "checkout_changed", f"“{line['title']}” changed since your draft. Return to your cart to review it.")
            if available(await db.inventory.find_one({"variant_id": v["_id"]})) < line["quantity"]:
                raise APIError(409, "checkout_changed", f"“{line['title']}” no longer has enough stock. Return to your cart.")
            eligible = line["line_total_minor"] - disc
            bps, source = ledger.rate_for(rules, vendor["_id"], p.get("category_id"), vendor.get("plan"))
            lines.append({**line, "discount_minor": disc, "platform_discount_minor": pshare, "eligible_minor": eligible, "commission_bps": bps, "commission_source": source,
                          "commission_minor": ledger.commission(eligible, bps)})
        items_net = g["subtotal_minor"] - vdisc
        tax = g["tax_estimate_minor"] or 0
        plan.append({"vendor_id": g["vendor_id"], "vendor_name": g["vendor_name"], "vendor_slug": g["vendor_slug"], "items_minor": g["subtotal_minor"],
                     "discount_minor": vdisc, "platform_discount_minor": pdisc, "items_net_minor": items_net, "shipping_minor": g["shipping_minor"], "tax_minor": tax,
                     "charged_minor": items_net - pdisc + g["shipping_minor"] + tax, "commission_minor": sum(x["commission_minor"] for x in lines), "lines": lines})
    return plan


def _origin(url: str) -> str:
    url = url.rstrip("/")
    if url not in settings.cors_origins:
        raise APIError(422, "validation_error", "Unknown site origin.")
    return url


@router.post("/orders/{order_id}/checkout")
async def start_payment(order_id: str, body: CheckoutIn, request: Request, user: User = Depends(get_current_user)):
    await guard()
    order = await _own_order(order_id, user)
    origin = _origin(body.origin_url)
    if order["status"] in ("paid", "partially_refunded", "refunded"):
        raise APIError(409, "already_paid", "This order is already paid.")
    if order["status"] not in ("draft", "pending_payment") or order["expires_at"].replace(tzinfo=utcnow().tzinfo) < utcnow():
        raise APIError(409, "draft_expired", "This order draft has expired. Return to your cart to start again.")
    open_pay = await db.payments.find_one({"order_id": order["_id"], "status": {"$in": list(pay.OPEN)}})
    if open_pay:
        if open_pay.get("checkout_url") and open_pay["session_expires_at"].replace(tzinfo=utcnow().tzinfo) > utcnow() + timedelta(minutes=2):
            session = await call(stripe.checkout.Session.retrieve, open_pay["provider_session_id"])
            if session["status"] == "open":
                return {"checkout_url": open_pay["checkout_url"], "payment_id": str(open_pay["_id"]), "reused": True}
            if session["payment_status"] == "paid":
                await pay.mark_paid(open_pay, session["payment_intent"], session["amount_total"], session["currency"], "status_check")
                raise APIError(409, "already_paid", "This order is already paid.")
        if not open_pay.get("checkout_url"):
            raise APIError(409, "payment_in_progress", "Payment is being prepared. Try again in a moment.")
        await _close_session(open_pay, "cancelled")
    plan = await build_plan(order)
    amount = sum(g["charged_minor"] for g in plan)
    attempt = order.get("payment_attempts", 0) + 1
    key = f"pay:{order['_id']}:{attempt}"
    now = utcnow()
    doc = {"order_id": order["_id"], "customer_id": order["customer_id"], "order_number": order["order_number"], "provider": "stripe",
           "mode": "test", "amount_minor": amount, "currency": "USD", "plan": plan, "status": "requires_payment", "idempotency_key": key,
           "fee_minor": None, "created_at": now, "updated_at": now}
    try:
        doc["_id"] = (await db.payments.insert_one(doc)).inserted_id
    except DuplicateKeyError:
        raise APIError(409, "payment_in_progress", "Payment is being prepared. Try again in a moment.")
    held = []
    for g in plan:
        for line in g["lines"]:
            if not await reserve(ObjectId(line["variant_id"]), line["quantity"]):
                for vid_, q in held:
                    await release(vid_, q)
                await db.payments.update_one({"_id": doc["_id"]}, {"$set": {"status": "failed", "failure": "out_of_stock", "updated_at": utcnow()}})
                raise APIError(409, "out_of_stock", f"Sorry, “{line.get('title', 'an item')}” just sold out. Please update your cart.")
            held.append((ObjectId(line["variant_id"]), line["quantity"]))
    await db.payments.update_one({"_id": doc["_id"]}, {"$set": {"stock_reserved": True}})
    meta = {"order_id": str(order["_id"]), "payment_id": str(doc["_id"]), "order_number": order["order_number"]}
    try:
        session = await call(
            stripe.checkout.Session.create, mode="payment", customer_email=user.email, client_reference_id=str(order["_id"]), metadata=meta,
            line_items=[{"quantity": 1, "price_data": {"currency": "usd", "unit_amount": g["charged_minor"], "product_data": {
                "name": f"{g['vendor_name']} — {sum(x['quantity'] for x in g['lines'])} item(s)",
                "description": f"Items ${g['items_net_minor'] / 100:.2f} · shipping ${g['shipping_minor'] / 100:.2f} · tax ${g['tax_minor'] / 100:.2f}"}}}
                for g in plan],
            payment_intent_data={"transfer_group": order["order_number"], "metadata": meta},
            success_url=f"{origin}/checkout/payment/{order['_id']}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/checkout/payment/{order['_id']}?cancelled=1",
            expires_at=int((now + timedelta(minutes=SESSION_MINUTES)).timestamp()), idempotency_key=key)
    except APIError:
        await db.payments.update_one({"_id": doc["_id"]}, {"$set": {"status": "failed", "failure": "session_create_failed", "updated_at": utcnow()}})
        await release_payment_stock(doc["_id"])
        raise
    if session["amount_total"] != amount:
        await call(stripe.checkout.Session.expire, session["id"])
        await db.payments.update_one({"_id": doc["_id"]}, {"$set": {"status": "failed", "failure": "amount_mismatch", "updated_at": utcnow()}})
        await release_payment_stock(doc["_id"])
        raise APIError(500, "amount_mismatch", "Payment amount check failed. Nothing was charged.")
    await db.payments.update_one({"_id": doc["_id"]}, {"$set": {"provider_session_id": session["id"], "checkout_url": session["url"],
                                                                 "session_expires_at": now + timedelta(minutes=SESSION_MINUTES)}})
    await db.orders.update_one({"_id": order["_id"]}, {"$set": {"status": "pending_payment", "payment_status": "requires_payment",
                                                                "payment_attempts": attempt, "updated_at": now}})
    await audit("payment.session_created", "payments", request=request, actor=user, entity_id=str(doc["_id"]), amount=amount)
    return {"checkout_url": session["url"], "payment_id": str(doc["_id"]), "reused": False}


async def _close_session(payment: dict, status: str) -> None:
    if payment.get("provider_session_id"):
        try:
            await call(stripe.checkout.Session.expire, payment["provider_session_id"])
        except APIError:
            pass
    res = await db.payments.update_one({"_id": payment["_id"], "status": {"$in": list(pay.OPEN)}}, {"$set": {"status": status, "updated_at": utcnow()}})
    if res.modified_count:
        await db.orders.update_one({"_id": payment["order_id"], "status": "pending_payment"}, {"$set": {"status": "draft", "payment_status": status}})
        await release_payment_stock(payment["_id"])


async def release_payment_stock(payment_id) -> None:
    """Give back stock held for an unpaid checkout exactly once (atomic flag flip)."""
    p = await db.payments.find_one_and_update({"_id": payment_id, "stock_reserved": True, "status": {"$nin": ["succeeded"]}}, {"$set": {"stock_reserved": False}})
    if p:
        for g in p["plan"]:
            for line in g["lines"]:
                await release(ObjectId(line["variant_id"]), line["quantity"])


async def _refresh(order: dict) -> None:
    """Server-side re-check with Stripe (never trust the redirect)."""
    p = await db.payments.find_one({"order_id": order["_id"], "status": {"$in": list(pay.OPEN)}, "provider_session_id": {"$exists": True}})
    if not p:
        return
    s = await call(stripe.checkout.Session.retrieve, p["provider_session_id"])
    if s["payment_status"] == "paid":
        await pay.mark_paid(p, s["payment_intent"], s["amount_total"], s["currency"], "status_check")
    elif s["status"] == "expired":
        await _close_session(p, "cancelled")


def _receipt(order: dict, payment: dict | None, vos: list, items: list, refunds: list) -> dict:
    out = ser({k: v for k, v in order.items() if k not in ("cart_fingerprint", "idempotency_key")})
    out["payment"] = {"status": payment["status"], "amount_minor": payment["amount_minor"], "currency": payment["currency"], "mode": payment["mode"],
                      "paid_at": payment.get("paid_at").isoformat() if payment.get("paid_at") else None} if payment else None
    out["vendor_orders"] = [{"id": str(v["_id"]), "vendor_name": v["vendor_name"], "vendor_slug": v["vendor_slug"], "status": v["status"],
                             **{k: v[k] for k in ("items_net_minor", "shipping_minor", "tax_minor", "charged_minor", "refunded_minor", "discount_minor")},
                             "items": [{k: i[k] for k in ("title", "label", "quantity", "unit_price_minor", "line_total_minor", "refunded_qty")}
                                       for i in items if i["vendor_order_id"] == v["_id"]]} for v in vos]
    out["refunds"] = [{"id": str(r["_id"]), "amount_minor": r["amount_minor"], "status": r["status"], "vendor_order_id": str(r["vendor_order_id"]),
                       "created_at": r["created_at"].isoformat()} for r in refunds]
    return out


@router.get("/orders/{order_id}")
async def payment_status(order_id: str, user: User = Depends(get_current_user)):
    order = await _own_order(order_id, user)
    if order["status"] == "pending_payment":
        await _refresh(order)
        order = await _own_order(order_id, user)
    payment = await db.payments.find_one({"order_id": order["_id"]}, sort=[("created_at", -1)])
    if order.get("payment_id"):
        payment = await db.payments.find_one({"_id": order["payment_id"]})
    vos = await db.vendor_orders.find({"order_id": order["_id"]}).to_list(50)
    items = await db.order_items.find({"order_id": order["_id"]}).to_list(500)
    refunds = await db.refunds.find({"order_id": order["_id"]}).to_list(100)
    return {"order": _receipt(order, payment, vos, items, refunds)}


@router.post("/orders/{order_id}/cancel")
async def cancel_payment(order_id: str, request: Request, user: User = Depends(get_current_user)):
    order = await _own_order(order_id, user)
    await _refresh(order)
    p = await db.payments.find_one({"order_id": order["_id"], "status": {"$in": list(pay.OPEN)}})
    if p:
        await _close_session(p, "cancelled")
        await audit("payment.cancelled", "payments", request=request, actor=user, entity_id=str(p["_id"]))
    return await payment_status(order_id, user)


@router.get("/orders")
async def my_orders(user: User = Depends(get_current_user)):
    docs = await db.orders.find({"customer_id": ObjectId(user.id), "status": {"$in": ["pending_payment", "paid", "partially_refunded", "refunded"]}},
                                {"order_number": 1, "status": 1, "totals": 1, "paid_at": 1, "created_at": 1}).sort("created_at", -1).to_list(100)
    return {"data": [ser(d) for d in docs]}


async def _handle(event) -> None:
    t, obj = event["type"], event["data"]["object"]
    if t in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        p = await db.payments.find_one({"provider_session_id": obj["id"]})
        if p and obj.get("metadata", {}).get("payment_id") == str(p["_id"]) and obj["payment_status"] == "paid":
            await pay.mark_paid(p, obj["payment_intent"], obj["amount_total"], obj["currency"], "webhook")
    elif t in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        p = await db.payments.find_one({"provider_session_id": obj["id"]})
        if p:
            await _close_session(p, "cancelled" if t.endswith("expired") else "failed")
    elif t == "payment_intent.payment_failed":
        await db.payments.update_one({"_id": oid(obj.get("metadata", {}).get("payment_id", "0" * 24)), "status": "requires_payment"},
                                     {"$set": {"last_failure": (obj.get("last_payment_error") or {}).get("message", "Payment failed")[:200]}})
    elif t in ("refund.created", "refund.updated", "charge.refund.updated"):
        r = await db.refunds.find_one({"provider_refund_id": obj["id"]})
        if r and obj["status"] == "succeeded":
            await pay.apply_refund(r)
        elif r and obj["status"] in ("failed", "canceled"):
            await db.refunds.update_one({"_id": r["_id"], "status": {"$in": ["processing", "pending"]}}, {"$set": {"status": "failed"}})
    elif t == "charge.dispute.created":
        await pay.dispute_opened(obj)
    elif t == "charge.dispute.updated":
        await db.disputes.update_one({"provider_dispute_id": obj["id"]}, {"$set": {"status": obj["status"], "updated_at": utcnow()}})
    elif t == "charge.dispute.closed":
        await pay.dispute_closed(obj)
    elif t == "charge.succeeded" or t == "charge.updated":
        p = await db.payments.find_one({"provider_payment_id": obj.get("payment_intent")})
        if p:
            await pay.finalize_fee(p)
    elif t == "account.updated":
        await db.connected_accounts.update_one({"stripe_account_id": obj["id"], "simulated": False}, {"$set": {
            "transfers_enabled": (obj.get("capabilities") or {}).get("transfers") == "active", "payouts_enabled": obj.get("payouts_enabled", False),
            "details_submitted": obj.get("details_submitted", False), "updated_at": utcnow()}})
    elif t in ("payout.paid", "payout.failed") and event.get("account"):
        status = "paid" if t == "payout.paid" else "transferred"
        await db.payouts.update_many({"destination": event["account"], "status": "transferred", "simulated": False},
                                     {"$set": {"status": status, "bank_payout_id": obj["id"], "updated_at": utcnow()}})
        if status == "paid":
            ids = [p["vendor_order_id"] async for p in db.payouts.find({"bank_payout_id": obj["id"]})]
            await db.vendor_orders.update_many({"_id": {"$in": ids}}, {"$set": {"earning_status": "paid"}})


@webhook_router.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature", ""), WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise APIError(400, "invalid_signature", "Invalid signature.")
    try:
        await db.webhook_events.insert_one({"event_id": event["id"], "type": event["type"], "status": "processing", "received_at": utcnow()})
    except DuplicateKeyError:
        prior = await db.webhook_events.find_one({"event_id": event["id"]})
        if prior["status"] != "failed":
            return {"status": "duplicate"}
        await db.webhook_events.update_one({"event_id": event["id"]}, {"$set": {"status": "processing"}})
    try:
        await _handle(event)
    except Exception:
        log.exception("webhook failed id=%s type=%s", event["id"], event["type"])
        await db.webhook_events.update_one({"event_id": event["id"]}, {"$set": {"status": "failed"}})
        raise APIError(500, "webhook_failed", "Processing failed; Stripe will retry.")
    await db.webhook_events.update_one({"event_id": event["id"]}, {"$set": {"status": "processed", "processed_at": utcnow()}})
    return {"status": "ok"}
