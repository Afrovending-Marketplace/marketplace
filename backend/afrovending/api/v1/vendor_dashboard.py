import csv
import io
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel

from afrovending.api.v1.vendors import my_vendor
from afrovending.core import ledger, reports
from afrovending.core.audit import audit
from afrovending.core.catalog import oid
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.permissions import COMMISSION, require_perm
from afrovending.core.errors import APIError
from afrovending.core.models import User

router = APIRouter(tags=["vendor-dashboard"])
ADMIN = require_perm(COMMISSION)
DATE = r"^\d{4}-\d{2}-\d{2}$"


def _plan(vendor: dict, default_bps: int | None = None) -> dict:
    key = vendor.get("plan")
    if not key and default_bps is not None:
        return {"key": "starter", **ledger.PLANS["starter"], "rate_bps": default_bps, "note": "marketplace default rate"}
    key = key or "starter"
    return {"key": key, **ledger.PLANS[key]}


async def _reviews(vendor_id) -> dict:
    """Customer reviews arrive in Phase 11; until then the summary reports zero reviews and no average (never a fabricated rating)."""
    return {"total": 0, "average": None, "distribution": {str(n): 0 for n in range(5, 0, -1)}, "recent": [], "available": False}


@router.get("/vendor/dashboard")
async def dashboard(from_: Optional[str] = Query(default=None, alias="from", pattern=DATE), to: Optional[str] = Query(default=None, pattern=DATE),
                    user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    start, end = reports.parse_range(from_, to)
    vid = vendor["_id"]
    store = await db.vendor_stores.find_one({"vendor_id": vid}) or {}
    inv, ops, pay = await reports.inventory(vid), await reports.operations(vid), await reports.payouts(vid)
    account = await db.connected_accounts.find_one({"vendor_id": vid})
    rules = await ledger.active_rules()
    override = rules.get(("vendor", str(vid)))
    default = rules.get(("default", "None"))
    return {"vendor": {"id": str(vid), "name": vendor["name"], "status": vendor["status"]},
            "store": {"display_name": store.get("display_name", vendor["name"]), "slug": store.get("slug"), "status": store.get("status", "draft")},
            "plan": _plan(vendor, default["rate_bps"] if default else None) | {"override_bps": override["rate_bps"] if override else None},
            "sales": await reports.sales(vid, start, end), "top_products": await reports.top_products(vid, start, end),
            "inventory": inv, "operations": ops, "payouts": pay, "reviews": await _reviews(vid),
            "alerts": reports.alerts(vendor, store, inv, ops, pay, account)}


def _csv(header: list[str], rows: list[list], name: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response(buf.getvalue().encode(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _usd(m: int) -> str:
    return f"{m / 100:.2f}"


@router.get("/vendor/reports/{kind}.csv")
async def export(kind: Literal["summary", "transactions", "orders", "products"], from_: Optional[str] = Query(default=None, alias="from", pattern=DATE),
                 to: Optional[str] = Query(default=None, pattern=DATE), user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    start, end = reports.parse_range(from_, to)
    vid, tag = vendor["_id"], f"{start}_{end}"
    if kind == "summary":
        s = await reports.sales(vid, start, end)
        rows = [[k.removesuffix("_minor"), _usd(v) if k.endswith("_minor") else v] for k, v in s["totals"].items()]
        rows += [["daily_" + d["date"], _usd(d["net_item_sales_minor"])] for d in s["series"]]
        return _csv(["metric (USD unless count) — US Eastern time " + tag, "value"], rows, f"afrovending-summary-{tag}.csv")
    if kind == "transactions":
        es = await reports.entries(vid, start, end)
        vos = {v["_id"]: v["order_number"] async for v in db.vendor_orders.find({"_id": {"$in": list({e["vendor_order_id"] for e in es})}}, {"order_number": 1})}
        rows = [[e["created_at"].astimezone(reports.ET).strftime("%Y-%m-%d %H:%M:%S"), vos.get(e["vendor_order_id"], ""), e["account"], e["type"],
                 _usd(e["amount_minor"]), e["currency"], e["entry_key"]] for e in es]
        return _csv(["date_et", "order", "account", "type", "amount_usd", "currency", "ledger_entry"], rows, f"afrovending-transactions-{tag}.csv")
    a, b = reports.et_bounds(start, end)
    vos = await db.vendor_orders.find({"vendor_id": vid, "created_at": {"$gte": a, "$lt": b}}).sort("created_at", 1).to_list(20001)
    if len(vos) > 20000:
        raise APIError(422, "range_too_large", "This date range has too many orders. Choose a shorter range.")
    if kind == "orders":
        per = {}
        async for e in db.commission_ledger.find({"account": "vendor", "vendor_order_id": {"$in": [v["_id"] for v in vos]}}):
            p = per.setdefault(e["vendor_order_id"], {"comm": 0, "fee": 0, "earn": 0})
            p["comm"] += e["amount_minor"] if e["type"] in reports.COMM_TYPES else 0
            p["fee"] += e["amount_minor"] if e["type"] in reports.FEE_TYPES else 0
            p["earn"] += e["amount_minor"] if e["type"] not in ("transfer", "transfer_reversal") else 0
        z = {"comm": 0, "fee": 0, "earn": 0}
        rows = [[v["created_at"].astimezone(reports.ET).strftime("%Y-%m-%d %H:%M"), v["order_number"], v["status"], v.get("fulfillment_type", "ship"),
                 _usd(v["items_net_minor"]), _usd(v["shipping_minor"]), _usd(v["tax_minor"]), _usd(v["charged_minor"]), _usd(v.get("refunded_minor", 0)),
                 _usd(per.get(v["_id"], z)["comm"]), _usd(per.get(v["_id"], z)["fee"]), _usd(per.get(v["_id"], z)["earn"]), v.get("earning_status", "")] for v in vos]
        return _csv(["date_et", "order", "status", "fulfillment", "items_usd", "shipping_usd", "tax_usd", "charged_usd", "refunded_usd",
                     "commission_usd", "processing_fee_usd", "vendor_earnings_usd", "earning_status"], rows, f"afrovending-orders-{tag}.csv")
    top = await reports.top_products(vid, start, end, limit=10000)
    return _csv(["product (orders placed in range)", "units_sold", "units_refunded_after_sale", "net_item_sales_usd"],
                [[p["title"], p["units"], p["refunded_units"], _usd(p["net_item_sales_minor"])] for p in top], f"afrovending-products-{tag}.csv")


class PlanIn(BaseModel):
    plan: Literal["starter", "growth", "premium"]
    reason: str = ""


@router.put("/admin/vendors/{vendor_id}/plan")
async def set_plan(vendor_id: str, body: PlanIn, admin: User = Depends(ADMIN)):
    """Applies to orders paid after the change; historical commission entries are never rewritten."""
    vendor = await db.vendors.find_one_and_update({"_id": oid(vendor_id)}, {"$set": {"plan": body.plan}})
    if not vendor:
        raise APIError(404, "not_found", "Vendor not found.")
    await audit("vendor.plan_changed", "vendor", actor=admin, entity_id=vendor_id, before=vendor.get("plan") or "starter", after=body.plan, reason=body.reason)
    return {"vendor_id": vendor_id, "plan": _plan({**vendor, "plan": body.plan})}
