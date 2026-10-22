import logging
from datetime import timedelta

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import stripe
from afrovending.core import email as mail
from afrovending.core import ledger
from afrovending.core.audit import audit
from afrovending.core.catalog import adjust_stock
from afrovending.core.db import db
from afrovending.core.ledger import PLATFORM, TAX, VENDOR
from afrovending.core.models import utcnow
from afrovending.core.stripe_client import call, get_config

log = logging.getLogger("afrovending.payments")
OPEN = ("requires_payment", "processing")


async def _notify_vendor(vendor_id, headline: str, text: str) -> None:
    vendor = await db.vendors.find_one({"_id": vendor_id})
    owner = await db.users.find_one({"_id": vendor["owner_user_id"]}) if vendor else None
    if owner:
        subject, html = mail.payment_notice_email(owner.get("first_name") or vendor["name"], headline, text, "/vendor/earnings")
        await mail.try_send(to=owner["email"], subject=subject, html=html)


async def mark_paid(payment: dict, pi_id: str, amount_total: int, currency: str, source: str) -> bool:
    """Single entry point for confirmed payments (verified webhook or server-side Stripe re-check). Idempotent."""
    if amount_total != payment["amount_minor"] or currency.upper() != payment["currency"]:
        await db.payments.update_one({"_id": payment["_id"]}, {"$set": {"status": "needs_review", "review_reason": "amount_mismatch"}})
        await audit("payment.amount_mismatch", "payments", entity_id=str(payment["_id"]), expected=payment["amount_minor"], got=amount_total)
        return False
    now = utcnow()
    claimed = await db.payments.find_one_and_update(
        {"_id": payment["_id"], "status": {"$in": [*OPEN, "cancelled", "failed"]}},
        {"$set": {"status": "succeeded", "provider_payment_id": pi_id, "paid_at": now, "confirmed_by": source, "updated_at": now}},
        return_document=ReturnDocument.AFTER)
    if not claimed:
        return False
    order = await db.orders.find_one_and_update({"_id": payment["order_id"], "status": {"$nin": ["paid", "partially_refunded", "refunded"]}},
                                                {"$set": {"status": "paid", "payment_status": "paid", "payment_id": payment["_id"], "paid_at": now,
                                                          "amounts_final": True, "updated_at": now}}, return_document=ReturnDocument.AFTER)
    if not order:
        await db.payments.update_one({"_id": payment["_id"]}, {"$set": {"status": "needs_review", "review_reason": "duplicate_payment"}})
        await audit("payment.duplicate_detected", "payments", entity_id=str(payment["_id"]), order_id=str(payment["order_id"]))
        return False
    cfg = await get_config()
    for g in payment["plan"]:
        vid = ObjectId(g["vendor_id"])
        vo = {"order_id": order["_id"], "order_number": order["order_number"], "vendor_id": vid, "customer_id": order["customer_id"],
              "payment_id": payment["_id"], "vendor_name": g["vendor_name"], "vendor_slug": g["vendor_slug"], "currency": payment["currency"],
              **{k: g[k] for k in ("items_minor", "discount_minor", "items_net_minor", "shipping_minor", "tax_minor", "charged_minor", "commission_minor")},
              "fee_minor": None, "fee_allocated": False, "refunded_minor": 0, "items_refunded_minor": 0, "shipping_refunded_minor": 0,
              "tax_refunded_minor": 0, "commission_refunded_minor": 0, "status": "pending", "earning_status": "pending",
              "eligible_at": now + timedelta(days=cfg["hold_days"]), "holds": [], "created_at": now, "updated_at": now}
        try:
            vo["_id"] = (await db.vendor_orders.insert_one(vo)).inserted_id
        except DuplicateKeyError:
            vo = await db.vendor_orders.find_one({"order_id": order["_id"], "vendor_id": vid})
        for line in g["lines"]:
            await db.order_items.update_one({"vendor_order_id": vo["_id"], "variant_id": ObjectId(line["variant_id"])}, {"$setOnInsert": {
                "order_id": order["_id"], "vendor_id": vid, "customer_id": order["customer_id"], "product_id": ObjectId(line["product_id"]),
                **{k: line[k] for k in ("title", "label", "sku", "quantity", "unit_price_minor", "line_total_minor", "discount_minor", "eligible_minor",
                                        "commission_bps", "commission_source", "commission_minor")},
                "refunded_qty": 0, "refunded_minor": 0, "commission_refunded_minor": 0, "created_at": now}}, upsert=True)
        k, ids = f"pay:{payment['_id']}:{vo['_id']}", dict(vendor_id=vid, vendor_order_id=vo["_id"], order_id=order["_id"], payment_id=payment["_id"])
        await ledger.post(f"{k}:sale", account=VENDOR, type="gross_sale", amount_minor=g["items_net_minor"], **ids)
        if g["shipping_minor"]:
            await ledger.post(f"{k}:ship", account=VENDOR, type="shipping", amount_minor=g["shipping_minor"], **ids)
        if g["tax_minor"]:
            await ledger.post(f"{k}:tax", account=TAX, type="tax_collected", amount_minor=g["tax_minor"], **ids)
        await ledger.post(f"{k}:comm", account=VENDOR, type="commission", amount_minor=-g["commission_minor"], **ids)
        await ledger.post(f"{k}:comm_rev", account=PLATFORM, type="commission", amount_minor=g["commission_minor"], **ids)
        for line in g["lines"]:
            inv = await db.inventory.find_one({"variant_id": ObjectId(line["variant_id"])})
            product = await db.products.find_one({"_id": ObjectId(line["product_id"])})
            try:
                await adjust_stock(inv=inv, product=product, actor_id=None, delta=-line["quantity"], reason="sale", note=order["order_number"])
            except Exception:
                await db.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"stock_issue": True}})
        await _notify_vendor(vid, "New paid order", f"Order {order['order_number']} was paid: {g['items_net_minor'] / 100:.2f} USD in items. "
                                                     f"Earnings become eligible for payout after {cfg['hold_days']} days.")
    if order.get("coupon_code"):
        await db.coupons.update_one({"code": order["coupon_code"]}, {"$inc": {"redemptions": 1}})
    await db.carts.update_one({"_id": order.get("cart_id"), "status": "active"}, {"$set": {"status": "converted", "updated_at": now}})
    await finalize_fee(claimed)
    await audit("payment.succeeded", "payments", entity_id=str(payment["_id"]), order_id=str(order["_id"]), amount=amount_total, source=source)
    customer = await db.users.find_one({"_id": order["customer_id"]})
    if customer:
        subject, html = mail.receipt_email(customer.get("first_name") or "there", order, payment)
        await mail.try_send(to=customer["email"], subject=subject, html=html)
    return True


async def finalize_fee(payment: dict) -> bool:
    """Read the actual Stripe processing fee and allocate it across the vendor orders of this payment."""
    if payment.get("fee_minor") is not None or payment.get("status") != "succeeded":
        return payment.get("fee_minor") is not None
    pi = await call(stripe.PaymentIntent.retrieve, payment["provider_payment_id"], expand=["latest_charge.balance_transaction"])
    charge = pi.get("latest_charge")
    bt = charge.get("balance_transaction") if charge else None
    if not bt:
        return False
    fee = int(bt["fee"])
    res = await db.payments.update_one({"_id": payment["_id"], "fee_minor": None}, {"$set": {"fee_minor": fee, "charge_id": charge["id"],
                                                                                                 "balance_transaction_id": bt["id"]}})
    if not res.modified_count:
        return True
    vos = await db.vendor_orders.find({"payment_id": payment["_id"]}).to_list(100)
    await ledger.post(f"fee:{payment['_id']}", account=PLATFORM, type="processing_fee", amount_minor=-fee, order_id=payment["order_id"],
                      payment_id=payment["_id"], balance_transaction=bt["id"])
    for vo, share in ledger.allocate_fee(fee, vos):
        ids = dict(vendor_id=vo["vendor_id"], vendor_order_id=vo["_id"], order_id=vo["order_id"], payment_id=payment["_id"])
        await ledger.post(f"fee:{payment['_id']}:{vo['_id']}", account=VENDOR, type="processing_fee_allocation", amount_minor=-share, **ids)
        await ledger.post(f"fee:{payment['_id']}:{vo['_id']}:recovery", account=PLATFORM, type="processing_fee_allocation", amount_minor=share, **ids)
        await db.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"fee_minor": share, "fee_allocated": True}})
    return True


async def apply_refund(refund: dict) -> bool:
    """Record a succeeded refund exactly once: vendor debit, commission returned, tax reduced."""
    done = await db.refunds.find_one_and_update({"_id": refund["_id"], "status": {"$in": ["processing", "pending"]}},
                                                {"$set": {"status": "succeeded", "succeeded_at": utcnow()}})
    if not done:
        return False
    vo = await db.vendor_orders.find_one({"_id": refund["vendor_order_id"]})
    k = f"refund:{refund['_id']}"
    ids = dict(vendor_id=vo["vendor_id"], vendor_order_id=vo["_id"], order_id=vo["order_id"], payment_id=vo["payment_id"])
    await ledger.post(f"{k}:vendor", account=VENDOR, type="refund", amount_minor=-(refund["items_minor"] + refund["shipping_minor"]), **ids)
    if refund["tax_minor"]:
        await ledger.post(f"{k}:tax", account=TAX, type="refund", amount_minor=-refund["tax_minor"], **ids)
    if refund["commission_returned_minor"]:
        await ledger.post(f"{k}:comm", account=VENDOR, type="commission_reversal", amount_minor=refund["commission_returned_minor"], **ids)
        await ledger.post(f"{k}:comm_plat", account=PLATFORM, type="commission_reversal", amount_minor=-refund["commission_returned_minor"], **ids)
    for line in refund["lines"]:
        await db.order_items.update_one({"_id": line["order_item_id"]}, {"$inc": {"refunded_qty": line["quantity"], "refunded_minor": line["amount_minor"],
                                                                                 "commission_refunded_minor": line["commission_minor"]}})
    vo = await db.vendor_orders.find_one_and_update({"_id": vo["_id"]}, {"$inc": {
        "refunded_minor": refund["amount_minor"], "items_refunded_minor": refund["items_minor"], "shipping_refunded_minor": refund["shipping_minor"],
        "tax_refunded_minor": refund["tax_minor"], "commission_refunded_minor": refund["commission_returned_minor"]}}, return_document=ReturnDocument.AFTER)
    if vo["earning_status"] in ("transferred", "paid"):
        await _reverse_transfer(vo, refund["items_minor"] + refund["shipping_minor"] - refund["commission_returned_minor"], k)
    vos = await db.vendor_orders.find({"order_id": vo["order_id"]}).to_list(100)
    full = all(v["refunded_minor"] >= v["charged_minor"] for v in vos)
    await db.orders.update_one({"_id": vo["order_id"]}, {"$set": {"status": "refunded" if full else "partially_refunded", "updated_at": utcnow()}})
    await _notify_vendor(vo["vendor_id"], "Refund issued", f"A refund of {refund['amount_minor'] / 100:.2f} USD was issued on order {vo['order_number']}.")
    await audit("payment.refund_succeeded", "refunds", entity_id=str(refund["_id"]), amount=refund["amount_minor"])
    return True


async def _reverse_transfer(vo: dict, debit: int, key: str) -> None:
    """After transfer: pull the vendor share back via transfer reversal when possible; otherwise it stays as an owed balance."""
    payout = await db.payouts.find_one({"vendor_order_id": vo["_id"], "status": {"$in": ["transferred", "paid"]}})
    if not payout or payout.get("simulated") or debit <= 0:
        return
    amount = min(debit, payout["amount_minor"] - payout.get("reversed_minor", 0))
    if amount <= 0:
        return
    try:
        rev = await call(stripe.Transfer.create_reversal, payout["stripe_transfer_id"], amount=amount, idempotency_key=f"{key}:reversal")
    except Exception:
        log.warning("transfer reversal failed vo=%s; amount stays owed", vo["_id"])
        return
    await db.payouts.update_one({"_id": payout["_id"]}, {"$inc": {"reversed_minor": amount}})
    await ledger.post(f"{key}:reversal", account=VENDOR, type="transfer_reversal", amount_minor=amount, vendor_id=vo["vendor_id"],
                      vendor_order_id=vo["_id"], order_id=vo["order_id"], payment_id=vo["payment_id"], stripe_reversal_id=rev["id"])


async def dispute_opened(d: dict) -> None:
    payment = await db.payments.find_one({"provider_payment_id": d.get("payment_intent")})
    if not payment:
        return
    now = utcnow()
    doc = {"provider_dispute_id": d["id"], "payment_id": payment["_id"], "order_id": payment["order_id"], "amount_minor": d["amount"],
           "currency": d["currency"].upper(), "reason": d.get("reason"), "status": d["status"], "evidence_due_by": (d.get("evidence_details") or {}).get("due_by"),
           "attributions": [], "vendor_evidence": [], "applied": False, "created_at": now, "updated_at": now}
    try:
        doc["_id"] = (await db.disputes.insert_one(doc)).inserted_id
    except DuplicateKeyError:
        await db.disputes.update_one({"provider_dispute_id": d["id"]}, {"$set": {"status": d["status"], "updated_at": now}})
        return
    await ledger.post(f"dispute:{doc['_id']}:withdrawal", account=PLATFORM, type="dispute_withdrawal", amount_minor=-d["amount"],
                      order_id=payment["order_id"], payment_id=payment["_id"])
    vos = await db.vendor_orders.find({"payment_id": payment["_id"]}).to_list(100)
    for vo in vos:
        if vo["earning_status"] in ("pending", "releasing"):
            await db.vendor_orders.update_one({"_id": vo["_id"]}, {"$push": {"holds": ledger.hold("Customer dispute opened", "dispute", ref=str(doc["_id"]))}})
        await _notify_vendor(vo["vendor_id"], "Payment disputed", f"The customer disputed the payment for order {vo['order_number']}. Earnings are on hold. "
                                                                  "Submit evidence from your earnings page before the deadline.")
    await audit("payment.dispute_opened", "disputes", entity_id=str(doc["_id"]), amount=d["amount"])


async def dispute_closed(d: dict) -> None:
    fee = sum(-int(bt["fee"]) for bt in d.get("balance_transactions") or [] if bt.get("fee"))
    res = await db.disputes.find_one_and_update({"provider_dispute_id": d["id"]}, {"$set": {"status": d["status"], "closed_at": utcnow(),
                                                                                           "dispute_fee_minor": abs(fee), "updated_at": utcnow()}},
                                                return_document=ReturnDocument.AFTER)
    if res:
        await settle_dispute(res)


async def settle_dispute(dispute: dict) -> None:
    """Won → release holds. Lost → debit only the admin-attributed vendors; unattributed amount stays with the platform."""
    if dispute["status"] == "won":
        await _release_dispute_holds(dispute)
        await ledger.post(f"dispute:{dispute['_id']}:reinstated", account=PLATFORM, type="dispute_reinstated", amount_minor=dispute["amount_minor"],
                          order_id=dispute["order_id"], payment_id=dispute["payment_id"])
        return
    if dispute["status"] != "lost" or not dispute.get("attributed") or dispute.get("applied"):
        return
    if not (await db.disputes.update_one({"_id": dispute["_id"], "applied": False}, {"$set": {"applied": True}})).modified_count:
        return
    liable = [a for a in dispute["attributions"] if a["vendor_liable"] and a["amount_minor"] > 0]
    fees = ledger.split(dispute.get("dispute_fee_minor", 0), [a["amount_minor"] for a in liable])
    k = f"dispute:{dispute['_id']}"
    for a, fee in zip(liable, fees):
        vo = await db.vendor_orders.find_one({"_id": a["vendor_order_id"]})
        ids = dict(vendor_id=vo["vendor_id"], vendor_order_id=vo["_id"], order_id=vo["order_id"], payment_id=vo["payment_id"])
        comm = vo["commission_minor"] * a["amount_minor"] // max(vo["charged_minor"], 1)
        await ledger.post(f"{k}:{vo['_id']}:debit", account=VENDOR, type="dispute_debit", amount_minor=-a["amount_minor"], **ids)
        await ledger.post(f"{k}:{vo['_id']}:recovery", account=PLATFORM, type="dispute_recovery", amount_minor=a["amount_minor"], **ids)
        if comm:
            await ledger.post(f"{k}:{vo['_id']}:comm", account=VENDOR, type="commission_reversal", amount_minor=comm, **ids)
            await ledger.post(f"{k}:{vo['_id']}:comm_plat", account=PLATFORM, type="commission_reversal", amount_minor=-comm, **ids)
        if fee:
            await ledger.post(f"{k}:{vo['_id']}:fee", account=VENDOR, type="dispute_fee", amount_minor=-fee, **ids)
            await ledger.post(f"{k}:{vo['_id']}:fee_plat", account=PLATFORM, type="dispute_fee", amount_minor=fee, **ids)
        if vo["earning_status"] in ("transferred", "paid"):
            await _reverse_transfer(vo, a["amount_minor"] + fee - comm, f"{k}:{vo['_id']}")
        await _notify_vendor(vo["vendor_id"], "Dispute lost", f"The dispute on order {vo['order_number']} was lost. "
                                                              f"{(a['amount_minor'] + fee - comm) / 100:.2f} USD was deducted from your earnings.")
    if dispute.get("dispute_fee_minor"):
        await ledger.post(f"{k}:fee_platform", account=PLATFORM, type="dispute_fee", amount_minor=-dispute["dispute_fee_minor"],
                          order_id=dispute["order_id"], payment_id=dispute["payment_id"])
    await _release_dispute_holds(dispute)
    await audit("payment.dispute_settled", "disputes", entity_id=str(dispute["_id"]), liable=len(liable))


async def _release_dispute_holds(dispute: dict) -> None:
    await db.vendor_orders.update_many({"payment_id": dispute["payment_id"]},
                                       {"$set": {"holds.$[h].active": False, "holds.$[h].released_at": utcnow()}},
                                       array_filters=[{"h.ref": str(dispute["_id"]), "h.type": "dispute"}])


async def account_eligible(vendor_id) -> tuple[bool, str, dict | None]:
    vendor = await db.vendors.find_one({"_id": vendor_id})
    acct = await db.connected_accounts.find_one({"vendor_id": vendor_id})
    cfg = await get_config()
    if not vendor or vendor["status"] != "active":
        return False, "Vendor isn't active.", acct
    if not acct:
        return False, "Vendor hasn't set up payouts.", acct
    if acct["country"] not in cfg["allowed_countries"]:
        return False, "Vendor country isn't supported yet.", acct
    if not (acct.get("transfers_enabled") and acct.get("payouts_enabled")):
        return False, "Vendor's payout account isn't fully verified.", acct
    return True, "", acct


async def release_vendor(vendor_id, actor_id=None) -> dict:
    """Release eligible earnings: one idempotent transfer per vendor order, net of any owed balance."""
    pids = await db.vendor_orders.distinct("payment_id", {"vendor_id": vendor_id, "fee_allocated": False})
    for p in await db.payments.find({"_id": {"$in": pids}, "status": "succeeded", "fee_minor": None}).to_list(100):
        try:
            await finalize_fee(p)
        except Exception:
            log.warning("fee finalize failed payment=%s", p["_id"])
    ok, why, acct = await account_eligible(vendor_id)
    if not ok:
        return {"vendor_id": str(vendor_id), "released": 0, "skipped": why}
    now = utcnow()
    bal = await ledger.vo_balances(vendor_id)
    owed = {vid: -b for vid, b in bal.items() if b < 0}
    released, total = 0, 0
    async for vo in db.vendor_orders.find({"vendor_id": vendor_id, "earning_status": "pending"}).sort("eligible_at", 1):
        if not ledger.eligible_now(vo, now):
            continue
        vo = await db.vendor_orders.find_one_and_update({"_id": vo["_id"], "earning_status": "pending"}, {"$set": {"earning_status": "releasing"}})
        if not vo:
            continue
        payment = await db.payments.find_one({"_id": vo["payment_id"]})
        amount = bal.get(vo["_id"], 0)
        ids = dict(vendor_id=vendor_id, vendor_order_id=vo["_id"], order_id=vo["order_id"], payment_id=vo["payment_id"])
        for liable_vo in list(owed):
            take = min(amount, owed[liable_vo])
            if take <= 0:
                break
            await ledger.post(f"recover:{liable_vo}:{vo['_id']}", account=VENDOR, type="liability_recovery", amount_minor=-take, **ids)
            await ledger.post(f"recover:{liable_vo}:{vo['_id']}:credit", account=VENDOR, type="liability_recovery", amount_minor=take,
                              vendor_id=vendor_id, vendor_order_id=liable_vo)
            owed[liable_vo] -= take
            amount -= take
            if not owed[liable_vo]:
                owed.pop(liable_vo)
        key = f"transfer:{vo['_id']}:1"
        payout = {"vendor_id": vendor_id, "vendor_order_id": vo["_id"], "order_number": vo["order_number"], "amount_minor": amount,
                  "currency": vo["currency"], "idempotency_key": key, "simulated": acct["simulated"], "destination": acct["stripe_account_id"],
                  "status": "transferred", "reversed_minor": 0, "created_by": actor_id, "created_at": now, "updated_at": now}
        if amount > 0:
            if not acct["simulated"]:
                try:
                    tr = await call(stripe.Transfer.create, amount=amount, currency=vo["currency"].lower(), destination=acct["stripe_account_id"],
                                    transfer_group=vo["order_number"], source_transaction=payment.get("charge_id"),
                                    metadata={"vendor_order_id": str(vo["_id"])}, idempotency_key=key)
                except Exception as e:
                    await db.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"earning_status": "pending", "last_release_error": str(e)[:200]}})
                    continue
                payout["stripe_transfer_id"] = tr["id"]
            else:
                payout["stripe_transfer_id"] = f"tr_sim_{vo['_id']}"
            try:
                await db.payouts.insert_one(payout)
            except DuplicateKeyError:
                pass
            await ledger.post(key, account=VENDOR, type="transfer", amount_minor=-amount, simulated=acct["simulated"], **ids)
        await db.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"earning_status": "transferred", "transferred_at": now}})
        released += 1
        total += max(amount, 0)
    if released:
        await audit("payout.released", "payouts", entity_id=str(vendor_id), count=released, amount=total, actor=None)
        await _notify_vendor(vendor_id, "Earnings transferred", f"{total / 100:.2f} USD was transferred to your payout account. "
                                                                "Your bank deposit follows Stripe's payout schedule.")
    return {"vendor_id": str(vendor_id), "released": released, "amount_minor": total}


async def release_all() -> dict:
    results = []
    for p in await db.payments.find({"status": "succeeded", "fee_minor": None}).to_list(200):
        try:
            await finalize_fee(p)
        except Exception:
            log.warning("fee finalize failed payment=%s", p["_id"])
    for vid in await db.vendor_orders.distinct("vendor_id", {"earning_status": "pending"}):
        results.append(await release_vendor(vid))
    return {"vendors": results}
