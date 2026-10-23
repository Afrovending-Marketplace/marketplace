import csv
import hashlib
import io
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from afrovending.api.v1.vendors import my_vendor
from afrovending.core import ledger
from afrovending.core.catalog import oid
from afrovending.core.db import db
from afrovending.core.deps import get_current_user, require_roles
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.reports import ET, et_month
from afrovending.core.roles import Role

router = APIRouter(tags=["statements"])
ADMIN = require_roles(Role.MARKETPLACE_ADMIN, Role.SUPER_ADMIN)
GROUPS = {"Gross item sales": ("gross_sale",), "Shipping collected": ("shipping",), "Refunds": ("refund",),
          "Commission": ("commission", "commission_reversal"), "Card processing fees": ("processing_fee_allocation", "fee_return"),
          "Chargebacks": ("dispute_debit", "dispute_fee"), "Adjustments": ("liability_recovery",),
          "Transfers to Stripe account": ("transfer", "transfer_reversal")}


def _period(period: str) -> tuple[datetime, datetime]:
    """US Eastern calendar month, converted to UTC (same reporting time zone as the vendor dashboard)."""
    try:
        return et_month(period)
    except ValueError:
        raise APIError(422, "validation_error", "Period must look like 2026-10.") from None


async def build(vendor: dict, period: str) -> dict:
    """Built only from append-only ledger entries dated in the period; later corrections appear in later statements."""
    start, end = _period(period)
    entries = await db.commission_ledger.find({"account": "vendor", "vendor_id": vendor["_id"], "created_at": {"$gte": start, "$lt": end}}).sort("created_at", 1).to_list(20000)
    vos = {v["_id"]: v for v in await db.vendor_orders.find({"_id": {"$in": list({e["vendor_order_id"] for e in entries})}}).to_list(5000)}
    payouts = {p["vendor_order_id"]: p for p in await db.payouts.find({"vendor_id": vendor["_id"]}).to_list(5000)}
    totals = {k: sum(e["amount_minor"] for e in entries if e["type"] in t) for k, t in GROUPS.items()}
    net = sum(v for k, v in totals.items() if not k.startswith("Transfers"))
    rates = await db.order_items.aggregate([{"$match": {"vendor_id": vendor["_id"], "vendor_order_id": {"$in": list(vos)}}},
                                            {"$group": {"_id": {"bps": "$commission_bps", "source": "$commission_source"}}}]).to_list(20)
    rows = [{"date": e["created_at"].astimezone(ET).strftime("%Y-%m-%d %H:%M ET"), "type": e["type"], "order": vos.get(e["vendor_order_id"], {}).get("order_number", ""),
             "amount_minor": e["amount_minor"], "currency": e["currency"], "entry_key": e["entry_key"],
             "stripe_ref": (payouts.get(e["vendor_order_id"]) or {}).get("stripe_transfer_id", "") if e["type"] == "transfer" else ""} for e in entries]
    digest = hashlib.sha256("|".join(r["entry_key"] for r in rows).encode()).hexdigest()[:16]
    sid = f"AVS-{str(vendor['_id'])[-6:].upper()}-{period.replace('-', '')}"
    prev = await db.statements.find_one({"statement_id": sid})
    if not prev:
        await db.statements.insert_one({"statement_id": sid, "vendor_id": vendor["_id"], "period": period, "digest": digest, "totals": totals,
                                        "generated_at": utcnow(), "versions": 1})
    elif prev["digest"] != digest:
        await db.statements.update_one({"_id": prev["_id"]}, {"$set": {"digest": digest, "totals": totals}, "$inc": {"versions": 1}})
    store = await db.vendor_stores.find_one({"vendor_id": vendor["_id"]}) or {}
    return {"statement_id": sid, "period": period, "vendor_name": store.get("display_name", vendor["name"]), "vendor_id": str(vendor["_id"]),
            "totals": totals, "net_earnings_minor": net, "rows": rows, "digest": digest,
            "rates": [f"{r['_id']['bps'] / 100:g}% ({r['_id']['source']})" for r in rates],
            "balances": await ledger.vendor_summary(vendor["_id"]), "generated_at": utcnow().strftime("%Y-%m-%d %H:%M UTC")}


def _money(m: int) -> str:
    return f"{'-' if m < 0 else ''}${abs(m) / 100:,.2f}"


def to_csv(s: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["statement_id", s["statement_id"], "period", s["period"], "vendor", s["vendor_name"]])
    w.writerow(["date", "entry_type", "order_number", "amount", "currency", "entry_key", "stripe_reference"])
    for r in s["rows"]:
        w.writerow([r["date"], r["type"], r["order"], f"{r['amount_minor'] / 100:.2f}", r["currency"], r["entry_key"], r["stripe_ref"]])
    for k, v in s["totals"].items():
        w.writerow(["TOTAL", k, "", f"{v / 100:.2f}", "USD"])
    w.writerow(["TOTAL", "Net marketplace earnings", "", f"{s['net_earnings_minor'] / 100:.2f}", "USD"])
    return buf.getvalue().encode()


def to_pdf(s: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=f"AfroVending statement {s['statement_id']}", leftMargin=40, rightMargin=40, topMargin=36)
    st = getSampleStyleSheet()
    red = colors.HexColor("#D40000")
    head = Table([[Paragraph("<font color='white' size=16><b>AFROVENDING</b></font><br/><font color='white' size=8>AfroVending Online Marketplace LLC · "
                             "From Culture to Commerce</font>", st["Normal"])]], colWidths=[532])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E2A38")), ("LINEBELOW", (0, 0), (-1, -1), 3, red), ("PADDING", (0, 0), (-1, -1), 10)]))
    summary = [["Item", "Amount"]] + [[k, _money(v)] for k, v in s["totals"].items() if not k.startswith("Transfers")] + [["Net marketplace earnings", _money(s["net_earnings_minor"])]]
    b = s["balances"]
    status = [["Pending", "Eligible", "On hold", "Transferred", "Paid to bank", "Owed"],
              [_money(b[k]) for k in ("pending_minor", "eligible_minor", "held_minor", "transferred_minor", "paid_minor", "owed_minor")]]
    detail = [["Date", "Type", "Order", "Amount", "Stripe ref"]] + [[r["date"], r["type"], r["order"], _money(r["amount_minor"]), r["stripe_ref"]] for r in s["rows"]]
    grid = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E6DFD3")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FAF7F2")), ("FONTSIZE", (0, 0), (-1, -1), 8)]
    parts = [head, Spacer(1, 12), Paragraph(f"<b>Vendor payout statement {s['statement_id']}</b>", st["Heading2"]),
             Paragraph(f"Vendor: {s['vendor_name']} · Period: {s['period']} · Generated {s['generated_at']} · Currency USD · Test mode data", st["Normal"]),
             Paragraph(f"Commission rates applied: {', '.join(s['rates']) or '—'}. Subscription plan: none (no subscription charges; this statement covers "
                       "marketplace earnings only).", st["Normal"]), Spacer(1, 8)]
    for title, data, widths in (("Summary", summary, [380, 152]), ("Earnings status (as of generation)", status, [88] * 6),
                                ("Transactions", detail, [90, 140, 110, 80, 112])):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle(grid))
        parts += [Paragraph(f"<b>{title}</b>", st["Heading4"]), t, Spacer(1, 8)]
    parts.append(Paragraph("Built from AfroVending's append-only ledger. Corrections appear as separate entries in the period they are recorded. "
                           "A transfer to your Stripe account is separate from Stripe's bank payout.", st["Italic"]))
    doc.build(parts)
    return buf.getvalue()


def _file(s: dict, fmt: str) -> Response:
    if fmt == "csv":
        return Response(to_csv(s), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{s["statement_id"]}.csv"'})
    if fmt == "pdf":
        return Response(to_pdf(s), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{s["statement_id"]}.pdf"'})
    raise APIError(404, "not_found", "Use .pdf or .csv")


async def _months(vendor_id) -> list[str]:
    docs = await db.commission_ledger.aggregate([{"$match": {"account": "vendor", "vendor_id": vendor_id}},
                                                 {"$group": {"_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at", "timezone": "America/New_York"}}}}]).to_list(240)
    return sorted((d["_id"] for d in docs), reverse=True)


@router.get("/vendor/payments/statements")
async def my_statements(user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    return {"data": [{"period": p, "statement_id": f"AVS-{str(vendor['_id'])[-6:].upper()}-{p.replace('-', '')}"} for p in await _months(vendor["_id"])]}


@router.get("/vendor/payments/statements/{period}.{fmt}")
async def my_statement(period: str, fmt: str, user: User = Depends(get_current_user)):
    return _file(await build(await my_vendor(user), period), fmt)


@router.get("/admin/payments/statements")
async def all_statements(_: User = Depends(ADMIN)):
    out = []
    for vid in await db.commission_ledger.distinct("vendor_id", {"account": "vendor"}):
        store = await db.vendor_stores.find_one({"vendor_id": vid}) or {}
        out += [{"vendor_id": str(vid), "vendor_name": store.get("display_name", ""), "vendor_slug": store.get("slug"), "period": p,
                 "statement_id": f"AVS-{str(vid)[-6:].upper()}-{p.replace('-', '')}"} for p in await _months(vid)]
    return {"data": out}


@router.get("/admin/payments/statements/{vendor_id}/{period}.{fmt}")
async def admin_statement(vendor_id: str, period: str, fmt: str, _: User = Depends(ADMIN)):
    vendor = await db.vendors.find_one({"_id": oid(vendor_id)})
    if not vendor:
        raise APIError(404, "not_found", "Vendor not found.")
    return _file(await build(vendor, period), fmt)


__all__ = ["router", "build", "ObjectId"]
