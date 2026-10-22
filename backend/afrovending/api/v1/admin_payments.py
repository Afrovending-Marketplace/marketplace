from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from afrovending.api.v1.vendors import ser
from afrovending.core import ledger
from afrovending.core import payments as pay
from afrovending.core.audit import audit
from afrovending.core.catalog import oid
from afrovending.core.db import db
from afrovending.core.deps import require_roles
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.roles import Role
from afrovending.core.stripe_client import MODE, get_config, guard

router = APIRouter(prefix="/admin/payments", tags=["admin-payments"])
READ = require_roles(Role.MARKETPLACE_ADMIN, Role.SUPER_ADMIN)
FINANCE = require_roles(Role.SUPER_ADMIN)


class ConfigIn(BaseModel):
    hold_days: int = Field(ge=0, le=90)


class RuleIn(BaseModel):
    scope: Literal["default", "category", "vendor"]
    target: Optional[str] = Field(default=None, max_length=80, description="category slug or vendor store slug")
    rate_bps: int
    note: str = Field(default="", max_length=200)


class RefundLine(BaseModel):
    order_item_id: str
    quantity: int = Field(ge=1, le=100)


class RefundIn(BaseModel):
    lines: list[RefundLine] = Field(default_factory=list, max_length=50)
    include_shipping: bool = False
    reason: str = Field(min_length=3, max_length=300)


class HoldIn(BaseModel):
    type: Literal["refund", "fraud", "admin", "dispute"] = "admin"
    reason: str = Field(min_length=3, max_length=300)


class Attribution(BaseModel):
    vendor_order_id: str
    amount_minor: int = Field(ge=0)
    vendor_liable: bool = True


class AttributeIn(BaseModel):
    attributions: list[Attribution] = Field(max_length=50)
    note: str = Field(default="", max_length=300)


class ReleaseIn(BaseModel):
    vendor_id: Optional[str] = None


@router.get("/config")
async def get_cfg(_: User = Depends(READ)):
    return {**await get_config(), "mode": MODE}


@router.put("/config")
async def put_cfg(body: ConfigIn, request: Request, admin: User = Depends(FINANCE)):
    before = await get_config()
    await db.platform_settings.update_one({"key": "payments.config"}, {"$set": {"value.hold_days": body.hold_days, "updated_at": utcnow()}}, upsert=True)
    await audit("admin.payments_config_updated", "platform_settings", request=request, actor=admin, before=before["hold_days"], after=body.hold_days)
    return {**await get_config(), "mode": MODE}


async def _target(scope: str, target: Optional[str]):
    if scope == "default":
        return None, "Marketplace default"
    if scope == "category":
        c = await db.categories.find_one({"slug": target})
        if not c:
            raise APIError(422, "validation_error", "Unknown category.")
        return c["_id"], c["name"]
    s = await db.vendor_stores.find_one({"slug": target})
    if not s:
        raise APIError(422, "validation_error", "Unknown vendor store.")
    return s["vendor_id"], s["display_name"]


@router.get("/commission-rules")
async def rules(_: User = Depends(READ)):
    docs = await db.commission_rules.find({}).sort("created_at", -1).to_list(500)
    return {"data": [ser(d) for d in docs]}


@router.post("/commission-rules", status_code=201)
async def set_rule(body: RuleIn, request: Request, admin: User = Depends(FINANCE)):
    """Rules are versioned: a change supersedes the previous rule; historical order items keep their recorded rate."""
    if not 0 <= body.rate_bps <= 5000:
        raise APIError(422, "validation_error", "Rate must be between 0% and 50%.")
    sid, label = await _target(body.scope, body.target)
    now = utcnow()
    prev = await db.commission_rules.find_one_and_update({"scope": body.scope, "scope_id": sid, "status": "active"},
                                                         {"$set": {"status": "superseded", "superseded_at": now}})
    doc = {"scope": body.scope, "scope_id": sid, "label": label, "rate_bps": body.rate_bps, "note": body.note, "status": "active",
           "created_by": ObjectId(admin.id), "created_at": now}
    doc["_id"] = (await db.commission_rules.insert_one(doc)).inserted_id
    await audit("admin.commission_rule_set", "commission_rules", request=request, actor=admin, entity_id=str(doc["_id"]), scope=body.scope,
                target=label, before=prev["rate_bps"] if prev else None, after=body.rate_bps)
    return ser(doc)


@router.delete("/commission-rules/{rule_id}")
async def end_rule(rule_id: str, request: Request, admin: User = Depends(FINANCE)):
    r = await db.commission_rules.find_one({"_id": oid(rule_id), "status": "active"})
    if not r:
        raise APIError(404, "not_found", "Rule not found.")
    if r["scope"] == "default":
        raise APIError(409, "conflict", "The marketplace default can be changed but not removed.")
    await db.commission_rules.update_one({"_id": r["_id"]}, {"$set": {"status": "ended", "superseded_at": utcnow()}})
    await audit("admin.commission_rule_ended", "commission_rules", request=request, actor=admin, entity_id=rule_id, rate=r["rate_bps"])
    return {"ok": True}


@router.get("/payments")
async def list_payments(_: User = Depends(READ)):
    docs = await db.payments.find({}, {"plan": 0, "checkout_url": 0}).sort("created_at", -1).to_list(200)
    return {"data": [ser(d) for d in docs]}


@router.post("/payments/{payment_id}/sync-fee")
async def sync_fee(payment_id: str, _: User = Depends(FINANCE)):
    p = await db.payments.find_one({"_id": oid(payment_id), "status": "succeeded"})
    if not p:
        raise APIError(404, "not_found", "Payment not found.")
    return {"fee_recorded": await pay.finalize_fee(p)}


@router.get("/vendor-orders")
async def list_vendor_orders(_: User = Depends(READ)):
    vos = await db.vendor_orders.find({}).sort("created_at", -1).to_list(300)
    items = await db.order_items.find({"vendor_order_id": {"$in": [v["_id"] for v in vos]}}).to_list(3000)
    out = []
    for v in vos:
        d = ser(v)
        d["items"] = [ser(i) for i in items if i["vendor_order_id"] == v["_id"]]
        out.append(d)
    return {"data": out}


@router.post("/vendor-orders/{vo_id}/refunds", status_code=201)
async def refund(vo_id: str, body: RefundIn, request: Request, idempotency_key: str = Header(default="", alias="Idempotency-Key"),
                 admin: User = Depends(FINANCE)):
    await guard()
    if not 8 <= len(idempotency_key) <= 100:
        raise APIError(422, "validation_error", "Missing Idempotency-Key header.")
    prior = await db.refunds.find_one({"idempotency_key": idempotency_key})
    if prior:
        return {"refund": ser(prior), "replayed": True}
    vo = await db.vendor_orders.find_one({"_id": oid(vo_id)})
    if not vo:
        raise APIError(404, "not_found", "Vendor order not found.")
    doc = await pay.create_refund(vo, [(oid(rl.order_item_id), rl.quantity) for rl in body.lines], include_shipping=body.include_shipping,
                                  reason=body.reason, key=idempotency_key, actor_id=admin.id)
    await audit("admin.refund_requested", "refunds", request=request, actor=admin, entity_id=str(doc["_id"]), amount=doc["amount_minor"], reason=body.reason)
    return {"refund": ser(doc), "replayed": False}


@router.get("/refunds")
async def list_refunds(_: User = Depends(READ)):
    return {"data": [ser(d) for d in await db.refunds.find({}).sort("created_at", -1).to_list(300)]}


@router.post("/vendor-orders/{vo_id}/holds", status_code=201)
async def add_hold(vo_id: str, body: HoldIn, request: Request, admin: User = Depends(FINANCE)):
    h = ledger.hold(body.reason, body.type, by=admin.id)
    res = await db.vendor_orders.update_one({"_id": oid(vo_id), "earning_status": {"$in": ["pending", "releasing"]}}, {"$push": {"holds": h}})
    if not res.modified_count:
        raise APIError(409, "conflict", "Holds can only be placed before earnings are transferred.")
    await audit("admin.payout_hold_added", "vendor_orders", request=request, actor=admin, entity_id=vo_id, type=body.type, reason=body.reason)
    return {"hold": {k: v for k, v in h.items() if k != "created_at"}}


@router.post("/vendor-orders/{vo_id}/holds/{hold_id}/release")
async def release_hold(vo_id: str, hold_id: str, request: Request, admin: User = Depends(FINANCE)):
    res = await db.vendor_orders.update_one({"_id": oid(vo_id), "holds": {"$elemMatch": {"id": hold_id, "active": True}}},
                                            {"$set": {"holds.$.active": False, "holds.$.released_at": utcnow(), "holds.$.released_by": admin.id}})
    if not res.modified_count:
        raise APIError(404, "not_found", "Active hold not found.")
    await audit("admin.payout_hold_released", "vendor_orders", request=request, actor=admin, entity_id=vo_id, hold=hold_id)
    return {"ok": True}


@router.get("/disputes")
async def list_disputes(_: User = Depends(READ)):
    return {"data": [ser(d) for d in await db.disputes.find({}).sort("created_at", -1).to_list(200)]}


@router.post("/disputes/{dispute_id}/attribute")
async def attribute(dispute_id: str, body: AttributeIn, request: Request, admin: User = Depends(FINANCE)):
    d = await db.disputes.find_one({"_id": oid(dispute_id)})
    if not d:
        raise APIError(404, "not_found", "Dispute not found.")
    if d.get("applied"):
        raise APIError(409, "conflict", "This dispute's financial adjustments are already recorded.")
    out = []
    for a in body.attributions:
        vo = await db.vendor_orders.find_one({"_id": oid(a.vendor_order_id), "payment_id": d["payment_id"]})
        if not vo:
            raise APIError(422, "validation_error", "That vendor order isn't part of the disputed payment.")
        if a.amount_minor > vo["charged_minor"] - vo["refunded_minor"]:
            raise APIError(422, "validation_error", f"Amount for {vo['vendor_name']} exceeds that vendor order.")
        out.append({"vendor_order_id": vo["_id"], "vendor_id": vo["vendor_id"], "amount_minor": a.amount_minor, "vendor_liable": a.vendor_liable})
    if sum(a["amount_minor"] for a in out) > d["amount_minor"]:
        raise APIError(422, "validation_error", "Attributed amounts exceed the disputed amount.")
    await db.disputes.update_one({"_id": d["_id"]}, {"$set": {"attributions": out, "attributed": True, "attribution_note": body.note,
                                                              "attributed_by": ObjectId(admin.id), "updated_at": utcnow()}})
    liable = {a["vendor_order_id"] for a in out if a["vendor_liable"] and a["amount_minor"]}
    await db.vendor_orders.update_many({"payment_id": d["payment_id"], "_id": {"$nin": list(liable)}},
                                       {"$set": {"holds.$[h].active": False, "holds.$[h].released_at": utcnow()}},
                                       array_filters=[{"h.ref": str(d["_id"]), "h.type": "dispute"}])
    await audit("admin.dispute_attributed", "disputes", request=request, actor=admin, entity_id=dispute_id, liable=len(liable))
    await pay.settle_dispute(await db.disputes.find_one({"_id": d["_id"]}))
    return {"dispute": ser(await db.disputes.find_one({"_id": d["_id"]}))}


@router.post("/payouts/release")
async def release(body: ReleaseIn, request: Request, admin: User = Depends(FINANCE)):
    await guard()
    result = await pay.release_vendor(oid(body.vendor_id), admin.id) if body.vendor_id else await pay.release_all()
    await audit("admin.payouts_release_run", "payouts", request=request, actor=admin, result=str(result)[:500])
    return result


@router.get("/payouts")
async def list_payouts(_: User = Depends(READ)):
    return {"data": [ser(d) for d in await db.payouts.find({}).sort("created_at", -1).to_list(300)]}


@router.post("/payouts/{payout_id}/simulate-paid")
async def simulate_paid(payout_id: str, request: Request, admin: User = Depends(FINANCE)):
    if MODE != "test":
        raise APIError(403, "forbidden", "Simulation is only available in test mode.")
    p = await db.payouts.find_one_and_update({"_id": oid(payout_id), "simulated": True, "status": "transferred"},
                                             {"$set": {"status": "paid", "bank_payout_id": f"po_sim_{payout_id}", "updated_at": utcnow()}})
    if not p:
        raise APIError(404, "not_found", "Simulated transfer not found.")
    await db.vendor_orders.update_one({"_id": p["vendor_order_id"]}, {"$set": {"earning_status": "paid"}})
    await audit("admin.payout_simulated_paid", "payouts", request=request, actor=admin, entity_id=payout_id)
    return {"ok": True}


@router.get("/ledger")
async def ledger_entries(vendor_id: Optional[str] = None, _: User = Depends(READ)):
    q = {"vendor_id": oid(vendor_id)} if vendor_id else {}
    return {"data": [ser(d) for d in await db.commission_ledger.find(q).sort("created_at", -1).to_list(500)]}


@router.get("/reconciliation")
async def reconciliation(_: User = Depends(READ)):
    """Checks ledger vs payments, fee allocation, refunds and transfers; totals by entry type and account."""
    totals = {f"{d['_id']['account']}.{d['_id']['type']}": d["sum"] async for d in db.commission_ledger.aggregate(
        [{"$group": {"_id": {"account": "$account", "type": "$type"}, "sum": {"$sum": "$amount_minor"}}}])}
    issues = []
    for p in await db.payments.find({"status": {"$in": ["succeeded", "needs_review"]}}).to_list(1000):
        if p["status"] == "needs_review":
            issues.append({"payment_id": str(p["_id"]), "issue": p.get("review_reason", "needs review")})
            continue
        rows = {d["_id"]: d["sum"] async for d in db.commission_ledger.aggregate([
            {"$match": {"payment_id": p["_id"], "type": {"$in": ["gross_sale", "shipping", "tax_collected"]}}},
            {"$group": {"_id": "$type", "sum": {"$sum": "$amount_minor"}}}])}
        if sum(rows.values()) != p["amount_minor"]:
            issues.append({"payment_id": str(p["_id"]), "issue": f"ledger sales {sum(rows.values())} ≠ charged {p['amount_minor']}"})
        if p.get("fee_minor") is None:
            issues.append({"payment_id": str(p["_id"]), "issue": "processing fee not yet reported by Stripe"})
        else:
            alloc = sum([-e["amount_minor"] async for e in db.commission_ledger.find({"payment_id": p["_id"], "account": "vendor", "type": "processing_fee_allocation"})])
            if alloc != p["fee_minor"]:
                issues.append({"payment_id": str(p["_id"]), "issue": f"fee allocations {alloc} ≠ Stripe fee {p['fee_minor']}"})
    refunds = sum(r["amount_minor"] for r in await db.refunds.find({"status": "succeeded"}).to_list(5000))
    ledger_refunds = -(totals.get("vendor.refund", 0) + totals.get("tax.refund", 0))
    if refunds != ledger_refunds:
        issues.append({"issue": f"refunds {refunds} ≠ ledger refunds {ledger_refunds}"})
    transfers = sum(p["amount_minor"] for p in await db.payouts.find({}).to_list(5000))
    if transfers != -totals.get("vendor.transfer", 0):
        issues.append({"issue": f"payout records {transfers} ≠ ledger transfers {-totals.get('vendor.transfer', 0)}"})
    vendor_balance = sum(v for k, v in totals.items() if k.startswith("vendor."))
    pays = await db.payments.find({"status": "succeeded"}).to_list(5000)
    return {"totals": totals, "summary": {
        "gross_charged_minor": sum(p["amount_minor"] for p in pays), "processing_fees_minor": sum(p.get("fee_minor") or 0 for p in pays),
        "commission_net_minor": totals.get("platform.commission", 0) + totals.get("platform.commission_reversal", 0),
        "refunds_minor": refunds, "transfers_minor": transfers, "tax_held_minor": totals.get("tax.tax_collected", 0) + totals.get("tax.refund", 0),
        "vendor_balances_held_minor": vendor_balance, "open_disputes": await db.disputes.count_documents({"status": {"$nin": ["won", "lost"]}}),
        "webhook_failures": await db.webhook_events.count_documents({"status": "failed"})}, "issues": issues, "ok": not issues}
