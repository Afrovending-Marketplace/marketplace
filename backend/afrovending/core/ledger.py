from collections import defaultdict
from typing import Optional

from pymongo.errors import DuplicateKeyError

from afrovending.core.db import db
from afrovending.core.models import utcnow
from afrovending.core.pricing import _allocate, _bps

# account: vendor (vendor earnings held by platform) | platform (AfroVending revenue/costs) | tax (tax collected, held for remittance)
VENDOR, PLATFORM, TAX = "vendor", "platform", "tax"


async def post(entry_key: str, *, account: str, type: str, amount_minor: int, currency: str = "USD", vendor_id=None,
               vendor_order_id=None, order_id=None, payment_id=None, **meta) -> bool:
    """Append-only, idempotent ledger write. Returns False if the entry already existed."""
    doc = {"entry_key": entry_key, "account": account, "type": type, "amount_minor": int(amount_minor), "currency": currency,
           "vendor_id": vendor_id, "vendor_order_id": vendor_order_id, "order_id": order_id, "payment_id": payment_id,
           "meta": meta, "created_at": utcnow()}
    try:
        await db.commission_ledger.insert_one(doc)
        return True
    except DuplicateKeyError:
        return False


async def active_rules() -> dict:
    return {(r["scope"], str(r.get("scope_id"))): r async for r in db.commission_rules.find({"status": "active"})}


# Subscription plans: (monthly fee in cents, commission in basis points). Billing of plan fees is not part of Phase 09.
PLANS = {"starter": {"name": "Starter", "monthly_fee_minor": 0, "rate_bps": 1000},
         "growth": {"name": "Growth", "monthly_fee_minor": 2499, "rate_bps": 700},
         "premium": {"name": "Premium", "monthly_fee_minor": 4999, "rate_bps": 500}}


def rate_for(rules: dict, vendor_id, category_id, plan: Optional[str] = None) -> tuple[int, str]:
    """Priority: approved vendor override → category rule → vendor's subscription plan → marketplace default."""
    for scope, sid in (("vendor", vendor_id), ("category", category_id)):
        r = rules.get((scope, str(sid)))
        if r:
            return r["rate_bps"], scope
    if plan in PLANS:
        return PLANS[plan]["rate_bps"], f"plan:{plan}"
    r = rules.get(("default", "None"))
    return (r["rate_bps"], "default") if r else (0, "none")


def commission(eligible_minor: int, rate_bps: int) -> int:
    return _bps(eligible_minor, rate_bps)


def allocate_fee(fee_minor: int, vendor_orders: list[dict]) -> list[tuple[dict, int]]:
    """Largest remainder on charged totals; ties → larger amount, then vendor id. Shares always sum to the actual fee."""
    ordered = sorted(vendor_orders, key=lambda v: (-v["charged_minor"], str(v["vendor_id"])))
    return list(zip(ordered, _allocate(fee_minor, [v["charged_minor"] for v in ordered])))


def split(total: int, weights: list[int]) -> list[int]:
    return _allocate(total, weights)


async def vo_balances(vendor_id) -> dict:
    out = defaultdict(int)
    async for e in db.commission_ledger.find({"account": VENDOR, "vendor_id": vendor_id}, {"vendor_order_id": 1, "amount_minor": 1}):
        out[e["vendor_order_id"]] += e["amount_minor"]
    return out


async def vendor_summary(vendor_id) -> dict:
    """Pending / eligible / held (before transfer), transferred / paid (after transfer), owed (negative balances)."""
    bal = await vo_balances(vendor_id)
    now = utcnow()
    buckets = {"pending_minor": 0, "eligible_minor": 0, "held_minor": 0, "transferred_minor": 0, "paid_minor": 0, "owed_minor": 0}
    async for vo in db.vendor_orders.find({"vendor_id": vendor_id}):
        b = bal.get(vo["_id"], 0)
        st = vo.get("earning_status")
        if st in ("pending", "releasing"):
            if any(h["active"] for h in vo.get("holds", [])):
                buckets["held_minor"] += max(b, 0)
            elif vo.get("eligible_at") and vo["eligible_at"].replace(tzinfo=now.tzinfo) <= now:
                buckets["eligible_minor"] += max(b, 0)
            else:
                buckets["pending_minor"] += max(b, 0)
        if b < 0:
            buckets["owed_minor"] += -b
    async for p in db.payouts.find({"vendor_id": vendor_id, "status": {"$in": ["transferred", "paid"]}}):
        buckets["paid_minor" if p["status"] == "paid" else "transferred_minor"] += p["amount_minor"]
    return buckets


def eligible_now(vo: dict, now=None) -> bool:
    now = now or utcnow()
    return (vo.get("earning_status") == "pending" and vo.get("fee_allocated") and not any(h["active"] for h in vo.get("holds", []))
            and vo.get("eligible_at") is not None and vo["eligible_at"].replace(tzinfo=now.tzinfo) <= now)


def hold(reason: str, kind: str, by: Optional[str] = None, ref: Optional[str] = None) -> dict:
    import secrets
    return {"id": secrets.token_hex(6), "type": kind, "reason": reason[:300], "ref": ref, "active": True, "created_by": by, "created_at": utcnow()}
