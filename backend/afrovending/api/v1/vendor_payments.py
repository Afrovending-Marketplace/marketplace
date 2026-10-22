import secrets

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

import stripe
from afrovending.api.v1.vendors import my_vendor, ser
from afrovending.core import ledger
from afrovending.core.audit import audit
from afrovending.core.catalog import oid
from afrovending.core.config import settings
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.stripe_client import MODE, call, get_config, guard

router = APIRouter(prefix="/vendor/payments", tags=["vendor-payments"])
BREAKDOWN = ("order_number", "status", "earning_status", "items_minor", "discount_minor", "items_net_minor", "shipping_minor", "tax_minor", "charged_minor",
             "commission_minor", "fee_minor", "refunded_minor", "items_refunded_minor", "shipping_refunded_minor", "commission_refunded_minor",
             "eligible_at", "transferred_at", "created_at")


class OnboardIn(BaseModel):
    country: str = Field(min_length=2, max_length=2)


class EvidenceIn(BaseModel):
    text: str = Field(min_length=10, max_length=4000)


def _acct(a):
    if not a:
        return None
    return {k: a.get(k) for k in ("simulated", "country", "currency", "details_submitted", "transfers_enabled", "payouts_enabled")} | {"id": str(a["_id"])}


async def _create_real(vendor: dict, country: str, email: str):
    try:
        return await call(stripe.Account.create, type="express", country=country, email=email, metadata={"vendor_id": str(vendor["_id"])},
                          capabilities={"transfers": {"requested": True}}, idempotency_key=f"acct:{vendor['_id']}")
    except APIError as e:
        if "Connect" in e.message or "connect" in e.message:
            return None
        raise


@router.post("/onboarding")
async def onboarding(body: OnboardIn, request: Request, user: User = Depends(get_current_user)):
    """Express onboarding when Stripe Connect is available; otherwise a clearly-labelled simulated sandbox account."""
    await guard()
    vendor = await my_vendor(user)
    if vendor["status"] != "active":
        raise APIError(403, "forbidden", "Your vendor account isn't active.")
    country = body.country.upper()
    if country not in (await get_config())["allowed_countries"]:
        raise APIError(422, "unsupported_country", "Payouts are available to US-based vendors only for now.")
    acct = await db.connected_accounts.find_one({"vendor_id": vendor["_id"]})
    if not acct:
        real = await _create_real(vendor, country, user.email)
        acct = {"vendor_id": vendor["_id"], "owner_user_id": ObjectId(user.id), "country": country, "currency": "USD", "simulated": real is None,
                "stripe_account_id": real["id"] if real else f"acct_sim_{secrets.token_hex(8)}", "details_submitted": False,
                "transfers_enabled": False, "payouts_enabled": False, "created_at": utcnow(), "updated_at": utcnow()}
        acct["_id"] = (await db.connected_accounts.insert_one(acct)).inserted_id
        await audit("vendor.payout_account_created", "connected_accounts", request=request, actor=user, entity_id=str(acct["_id"]), simulated=acct["simulated"])
    if acct["simulated"]:
        return {"mode": "simulated", "account": _acct(acct)}
    link = await call(stripe.AccountLink.create, account=acct["stripe_account_id"], type="account_onboarding",
                      refresh_url=f"{settings.frontend_url}/vendor/earnings?onboarding=refresh", return_url=f"{settings.frontend_url}/vendor/earnings?onboarding=done")
    return {"mode": "stripe", "url": link["url"], "account": _acct(acct)}


@router.post("/onboarding/simulate-complete")
async def simulate_complete(request: Request, user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    if MODE != "test":
        raise APIError(403, "forbidden", "Simulation is only available in test mode.")
    acct = await db.connected_accounts.find_one_and_update({"vendor_id": vendor["_id"], "simulated": True}, {"$set": {
        "details_submitted": True, "transfers_enabled": True, "payouts_enabled": True, "updated_at": utcnow()}})
    if not acct:
        raise APIError(404, "not_found", "No simulated payout account.")
    await audit("vendor.payout_account_simulated_verified", "connected_accounts", request=request, actor=user, entity_id=str(acct["_id"]))
    return {"account": _acct(await db.connected_accounts.find_one({"_id": acct["_id"]}))}


@router.post("/onboarding/refresh")
async def refresh_account(user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    acct = await db.connected_accounts.find_one({"vendor_id": vendor["_id"]})
    if acct and not acct["simulated"]:
        a = await call(stripe.Account.retrieve, acct["stripe_account_id"])
        await db.connected_accounts.update_one({"_id": acct["_id"]}, {"$set": {
            "transfers_enabled": (a.get("capabilities") or {}).get("transfers") == "active", "payouts_enabled": a.get("payouts_enabled", False),
            "details_submitted": a.get("details_submitted", False), "updated_at": utcnow()}})
    return {"account": _acct(await db.connected_accounts.find_one({"vendor_id": vendor["_id"]}))}


@router.get("/summary")
async def summary(user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    vid = vendor["_id"]
    bal = await ledger.vo_balances(vid)
    vos = await db.vendor_orders.find({"vendor_id": vid}).sort("created_at", -1).to_list(200)
    payouts = await db.payouts.find({"vendor_id": vid}).sort("created_at", -1).to_list(200)
    disputes = await db.disputes.find({"payment_id": {"$in": list({v["payment_id"] for v in vos})}}).to_list(100)
    cfg = await get_config()
    earned = {}
    async for e in db.commission_ledger.find({"account": "vendor", "vendor_id": vid, "type": {"$nin": ["transfer", "transfer_reversal", "liability_recovery"]}}):
        earned[e["vendor_order_id"]] = earned.get(e["vendor_order_id"], 0) + e["amount_minor"]
    return {"account": _acct(await db.connected_accounts.find_one({"vendor_id": vid})), "balances": await ledger.vendor_summary(vid),
            "hold_days": cfg["hold_days"], "mode": MODE,
            "vendor_orders": [{"id": str(v["_id"]), **ser({k: v.get(k) for k in BREAKDOWN}), "net_minor": bal.get(v["_id"], 0),
                               "earned_net_minor": earned.get(v["_id"], 0),
                               "on_hold": any(h["active"] for h in v.get("holds", [])),
                               "holds": [{"type": h["type"], "reason": h["reason"]} for h in v.get("holds", []) if h["active"]]} for v in vos],
            "payouts": [{"id": str(p["_id"]), "order_number": p["order_number"], "amount_minor": p["amount_minor"], "status": p["status"],
                         "simulated": p["simulated"], "created_at": p["created_at"].isoformat()} for p in payouts],
            "disputes": [{"id": str(d["_id"]), "amount_minor": d["amount_minor"], "status": d["status"], "reason": d.get("reason"),
                          "evidence_due_by": d.get("evidence_due_by"), "my_evidence": [e["text"] for e in d["vendor_evidence"] if e["vendor_id"] == vid]}
                         for d in disputes]}


@router.get("/ledger")
async def my_ledger(user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    docs = await db.commission_ledger.find({"account": "vendor", "vendor_id": vendor["_id"]}).sort("created_at", -1).to_list(500)
    return {"data": [{"type": d["type"], "amount_minor": d["amount_minor"], "vendor_order_id": str(d["vendor_order_id"]) if d.get("vendor_order_id") else None,
                      "created_at": d["created_at"].isoformat()} for d in docs]}


@router.post("/disputes/{dispute_id}/evidence")
async def submit_evidence(dispute_id: str, body: EvidenceIn, request: Request, user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    d = await db.disputes.find_one({"_id": oid(dispute_id)})
    if not d or not await db.vendor_orders.find_one({"payment_id": d["payment_id"], "vendor_id": vendor["_id"]}):
        raise APIError(404, "not_found", "Dispute not found.")
    if d["status"] in ("won", "lost"):
        raise APIError(409, "conflict", "This dispute is closed.")
    await db.disputes.update_one({"_id": d["_id"]}, {"$push": {"vendor_evidence": {"vendor_id": vendor["_id"], "text": body.text, "at": utcnow()}}})
    await audit("vendor.dispute_evidence", "disputes", request=request, actor=user, entity_id=dispute_id)
    return {"ok": True}
