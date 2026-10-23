"""Vendor reporting. Every figure is derived from persisted ledger, refund, order and inventory records. Reporting time zone: US Eastern."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from afrovending.core.catalog import available
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.ledger import TAX, VENDOR, vendor_summary
from afrovending.core.models import utcnow

ET = ZoneInfo("America/New_York")
OPEN = ("pending", "accepted", "processing", "partially_shipped", "ready_for_pickup")
FEE_TYPES, COMM_TYPES = ("processing_fee_allocation", "fee_return"), ("commission", "commission_reversal")
DISPUTE_TYPES = ("dispute_debit", "dispute_fee", "dispute_recovery", "dispute_reinstated", "dispute_withdrawal", "liability_recovery")


def et_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Inclusive ET calendar dates -> [UTC start, UTC exclusive next-midnight end). DST handled by zoneinfo."""
    return (datetime.combine(start, time(0), ET).astimezone(timezone.utc),
            datetime.combine(end + timedelta(days=1), time(0), ET).astimezone(timezone.utc))


def et_month(period: str) -> tuple[datetime, datetime]:
    s = datetime.strptime(period, "%Y-%m").date()
    nxt = date(s.year + (s.month == 12), s.month % 12 + 1, 1)
    return et_bounds(s, nxt - timedelta(days=1))


def parse_range(frm: str | None, to: str | None) -> tuple[date, date]:
    today = utcnow().astimezone(ET).date()
    try:
        end = date.fromisoformat(to) if to else today
        start = date.fromisoformat(frm) if frm else end - timedelta(days=29)
    except ValueError:
        raise APIError(422, "validation_error", "Dates must look like 2026-10-31.") from None
    if start > end:
        raise APIError(422, "validation_error", "The start date must be on or before the end date.")
    if (end - start).days > 366:
        raise APIError(422, "validation_error", "Reports can cover at most 366 days.")
    return start, end


def et_day(d: datetime) -> str:
    return d.astimezone(ET).date().isoformat()


async def entries(vendor_id, start: date, end: date) -> list[dict]:
    a, b = et_bounds(start, end)
    return await db.commission_ledger.find({"vendor_id": vendor_id, "account": {"$in": [VENDOR, TAX]}, "created_at": {"$gte": a, "$lt": b}}).sort("created_at", 1).to_list(50000)


async def sales(vendor_id, start: date, end: date) -> dict:
    """Net item sales = paid merchandise (gross_sale) minus the merchandise part of confirmed refunds. Shipping and tax kept separate."""
    rows = await entries(vendor_id, start, end)
    refund_ids = {e["entry_key"].split(":")[1] for e in rows if e["type"] == "refund" and e["account"] == VENDOR}
    from bson import ObjectId
    refunds = {str(r["_id"]): r for r in await db.refunds.find({"_id": {"$in": [ObjectId(i) for i in refund_ids if ObjectId.is_valid(i)]}}).to_list(5000)}
    t = defaultdict(int)
    days = defaultdict(lambda: {"net_item_sales_minor": 0, "orders": 0})
    for e in rows:
        amt, typ, day = e["amount_minor"], e["type"], et_day(e["created_at"])
        if e["account"] == TAX:
            t["tax_collected_minor" if typ == "tax_collected" else "tax_refunded_minor"] += amt
            continue
        if typ == "gross_sale":
            t["gross_item_sales_minor"] += amt
            days[day]["net_item_sales_minor"] += amt
        elif typ == "shipping":
            t["shipping_charged_minor"] += amt
        elif typ == "refund":
            r = refunds.get(e["entry_key"].split(":")[1]) or {}
            items, ship = r.get("items_minor", -amt), r.get("shipping_minor", 0)
            t["item_refunds_minor"] -= items
            t["shipping_refunds_minor"] -= ship
            t["refunds_minor"] += amt
            days[day]["net_item_sales_minor"] -= items
        elif typ in COMM_TYPES:
            t["commission_minor"] += amt
        elif typ in FEE_TYPES:
            t["processing_fees_minor"] += amt
        elif typ in DISPUTE_TYPES:
            t["dispute_adjustments_minor"] += amt
        elif typ in ("transfer", "transfer_reversal"):
            t["transferred_minor"] += -amt
            continue
        if typ not in ("transfer", "transfer_reversal"):
            t["vendor_earnings_minor"] += amt
    t["net_item_sales_minor"] = t["gross_item_sales_minor"] + t["item_refunds_minor"]
    a, b = et_bounds(start, end)
    async for vo in db.vendor_orders.find({"vendor_id": vendor_id, "created_at": {"$gte": a, "$lt": b}}, {"created_at": 1, "status": 1}):
        days[et_day(vo["created_at"])]["orders"] += 1
        t["orders"] += 1
        t["cancelled_orders"] += vo["status"] == "cancelled"
    series, d = [], start
    while d <= end:
        series.append({"date": d.isoformat(), **days.get(d.isoformat(), {"net_item_sales_minor": 0, "orders": 0})})
        d += timedelta(days=1)
    keys = ("net_item_sales_minor", "gross_item_sales_minor", "item_refunds_minor", "shipping_charged_minor", "shipping_refunds_minor", "tax_collected_minor",
            "tax_refunded_minor", "commission_minor", "processing_fees_minor", "refunds_minor", "dispute_adjustments_minor", "vendor_earnings_minor",
            "transferred_minor", "orders", "cancelled_orders")
    t["average_order_minor"] = t["net_item_sales_minor"] // (t["orders"] - t["cancelled_orders"]) if t["orders"] - t["cancelled_orders"] > 0 else 0
    return {"from": start.isoformat(), "to": end.isoformat(), "timezone": "America/New_York (US Eastern)",
            "totals": {k: t[k] for k in keys} | {"average_order_minor": t["average_order_minor"]}, "series": series}


async def top_products(vendor_id, start: date, end: date, limit: int = 10) -> list[dict]:
    a, b = et_bounds(start, end)
    vo_ids = [v["_id"] async for v in db.vendor_orders.find({"vendor_id": vendor_id, "created_at": {"$gte": a, "$lt": b}}, {"_id": 1})]
    out = defaultdict(lambda: {"title": "", "units": 0, "refunded_units": 0, "net_item_sales_minor": 0})
    async for i in db.order_items.find({"vendor_id": vendor_id, "vendor_order_id": {"$in": vo_ids}}):
        p = out[str(i["product_id"])]
        p["title"] = i["title"]
        p["units"] += i["quantity"] - i.get("cancelled_qty", 0)
        p["refunded_units"] += i.get("refunded_qty", 0)
        p["net_item_sales_minor"] += i["line_total_minor"] - i.get("refunded_minor", 0)
    return sorted(({"product_id": k, **v} for k, v in out.items()), key=lambda r: -r["net_item_sales_minor"])[:limit]


async def inventory(vendor_id) -> dict:
    prods = {p["_id"]: p async for p in db.products.find({"vendor_id": vendor_id, "status": {"$ne": "deleted"}})}
    counts = defaultdict(int)
    for p in prods.values():
        counts[p["status"]] += 1
    stock = {s["variant_id"]: s async for s in db.inventory.find({"vendor_id": vendor_id})}
    low, out, units = [], [], 0
    async for v in db.product_variants.find({"product_id": {"$in": list(prods)}, "status": "active"}):
        p, s = prods[v["product_id"]], stock.get(v["_id"])
        n = available(s) if s else 0
        units += n
        row = {"product_id": str(p["_id"]), "title": p["title"], "variant": v.get("label", ""), "sku": v.get("sku", ""), "available": n,
               "reserved": (s or {}).get("quantity_reserved", 0), "threshold": p.get("low_stock_threshold", 5), "product_status": p["status"]}
        if n == 0:
            out.append(row)
        elif n <= row["threshold"]:
            low.append(row)
    return {"products_by_status": dict(counts), "products_total": len(prods), "units_available": units,
            "low_stock": sorted(low, key=lambda r: r["available"]), "out_of_stock": out}


async def operations(vendor_id) -> dict:
    now = utcnow()
    counts = {s: await db.vendor_orders.count_documents({"vendor_id": vendor_id, "status": s}) for s in OPEN}
    overdue = await db.vendor_orders.count_documents({"vendor_id": vendor_id, "status": {"$in": ["accepted", "processing", "partially_shipped"]},
                                                       "handling.deadline_at": {"$lt": now}})
    stale = await db.vendor_orders.count_documents({"vendor_id": vendor_id, "status": "pending", "created_at": {"$lt": now - timedelta(hours=24)}})
    reqs = await db.order_requests.find({"vendor_id": vendor_id, "status": "requested"}, {"due_at": 1, "type": 1}).to_list(500)
    newest = await db.vendor_orders.find({"vendor_id": vendor_id, "status": {"$in": list(OPEN)}}).sort("created_at", 1).to_list(8)
    return {"open_orders": counts, "overdue_orders": overdue, "pending_over_24h": stale, "open_requests": len(reqs),
            "requests_overdue": sum(1 for r in reqs if r["due_at"] < now),
            "queue": [{"id": str(v["_id"]), "order_number": v["order_number"], "status": v["status"], "fulfillment_type": v.get("fulfillment_type", "ship"),
                       "created_at": v["created_at"].isoformat(), "charged_minor": v["charged_minor"],
                       "deadline_at": ((v.get("handling") or {}).get("deadline_at") or now).isoformat() if v.get("handling") else None} for v in newest]}


async def payouts(vendor_id, limit: int = 20) -> dict:
    rows = await db.payouts.find({"vendor_id": vendor_id}).sort("created_at", -1).to_list(limit)
    vos = {v["_id"]: v["order_number"] async for v in db.vendor_orders.find({"_id": {"$in": [p["vendor_order_id"] for p in rows]}}, {"order_number": 1})}
    return {"balances": await vendor_summary(vendor_id),
            "history": [{"id": str(p["_id"]), "order_number": vos.get(p["vendor_order_id"], ""), "amount_minor": p["amount_minor"], "status": p["status"],
                         "transfer_ref": p.get("stripe_transfer_id") or "", "created_at": p["created_at"].isoformat(),
                         "updated_at": (p.get("updated_at") or p["created_at"]).isoformat()} for p in rows]}


def alerts(vendor: dict, store: dict, inv: dict, ops: dict, pay: dict, account: dict | None) -> list[dict]:
    a = []
    add = lambda level, code, text, link: a.append({"level": level, "code": code, "text": text, "link": link})  # noqa: E731
    if vendor.get("status") != "active":
        add("error", "vendor_suspended", "Your vendor account is not active. Contact info@afrovending.com.", "/vendor")
    if store.get("status") != "published":
        add("warning", "store_unpublished", "Your store is not published, so customers can't see it.", "/vendor")
    if ops["overdue_orders"]:
        add("error", "orders_overdue", f"{ops['overdue_orders']} order(s) passed their handling deadline.", "/vendor/orders")
    if ops["requests_overdue"]:
        add("error", "requests_overdue", f"{ops['requests_overdue']} cancellation/return request(s) passed the 48-hour response time.", "/vendor/orders")
    elif ops["open_requests"]:
        add("warning", "requests_open", f"{ops['open_requests']} cancellation/return request(s) need your decision.", "/vendor/orders")
    if ops["pending_over_24h"]:
        add("warning", "orders_waiting", f"{ops['pending_over_24h']} new order(s) have waited more than 24 hours for acceptance.", "/vendor/orders")
    if inv["out_of_stock"]:
        add("warning", "out_of_stock", f"{len(inv['out_of_stock'])} variant(s) are out of stock.", "/vendor/products")
    if inv["low_stock"]:
        add("info", "low_stock", f"{len(inv['low_stock'])} variant(s) are at or below their low-stock level.", "/vendor/products")
    if pay["balances"]["held_minor"]:
        add("warning", "earnings_held", "Some earnings are on hold (refund, dispute or review).", "/vendor/earnings")
    if pay["balances"]["owed_minor"]:
        add("error", "balance_owed", "You have a negative balance that will be recovered from future earnings.", "/vendor/earnings")
    if not account or not account.get("transfers_enabled"):
        add("info", "payout_account", "Finish payout account setup so earnings can be transferred.", "/vendor/earnings")
    return a
