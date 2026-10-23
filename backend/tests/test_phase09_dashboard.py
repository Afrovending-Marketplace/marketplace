import csv
import io
import uuid
from datetime import date, datetime, timezone

from bson import ObjectId

from afrovending.core.reports import et_bounds, et_month
from tests.test_phase03_vendors import mongo
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w  # noqa: F401
from tests.test_phase08_fulfillment import K, paid

ET_TODAY = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).date().isoformat()


def vid_of(slug):
    return mongo.vendor_stores.find_one({"slug": slug})["vendor_id"]


def ledger_truth(vendor_id, a, b):
    """Independent recomputation straight from Mongo, used to check the dashboard."""
    es = list(mongo.commission_ledger.find({"vendor_id": vendor_id, "account": "vendor", "created_at": {"$gte": a, "$lt": b}}))
    gross = sum(e["amount_minor"] for e in es if e["type"] == "gross_sale")
    ref_ids = [ObjectId(e["entry_key"].split(":")[1]) for e in es if e["type"] == "refund"]
    items_ref = sum(r["items_minor"] for r in mongo.refunds.find({"_id": {"$in": ref_ids}}))
    return {"gross": gross, "net": gross - items_ref, "refunds": sum(e["amount_minor"] for e in es if e["type"] == "refund"),
            "commission": sum(e["amount_minor"] for e in es if e["type"] in ("commission", "commission_reversal")),
            "fees": sum(e["amount_minor"] for e in es if e["type"] in ("processing_fee_allocation", "fee_return")),
            "shipping": sum(e["amount_minor"] for e in es if e["type"] == "shipping"),
            "earnings": sum(e["amount_minor"] for e in es if e["type"] not in ("transfer", "transfer_reversal")), "count": len(es)}


def test_01_et_boundaries_dst_and_months():
    utc = timezone.utc
    assert et_bounds(date(2026, 3, 8), date(2026, 3, 8)) == (datetime(2026, 3, 8, 5, tzinfo=utc), datetime(2026, 3, 9, 4, tzinfo=utc))  # 23-hour day
    assert et_bounds(date(2026, 11, 1), date(2026, 11, 1)) == (datetime(2026, 11, 1, 4, tzinfo=utc), datetime(2026, 11, 2, 5, tzinfo=utc))  # 25-hour day
    assert et_month("2026-12") == (datetime(2026, 12, 1, 5, tzinfo=utc), datetime(2027, 1, 1, 5, tzinfo=utc))
    assert et_month("2026-07") == (datetime(2026, 7, 1, 4, tzinfo=utc), datetime(2026, 8, 1, 4, tzinfo=utc))


def test_02_ownership_and_validation(w):  # noqa: F811
    c = buyer()
    S["c9"] = c
    assert c.get("/vendor/dashboard").status_code == 403
    assert c.get("/vendor/reports/orders.csv").status_code == 403
    assert w["a"].get("/vendor/dashboard", params={"from": "2026-10-10", "to": "2026-10-01"}).status_code == 422
    assert w["a"].get("/vendor/dashboard", params={"from": "2024-01-01", "to": "2026-01-01"}).status_code == 422
    assert w["a"].get("/vendor/dashboard", params={"from": "bad"}).status_code == 422
    assert w["a"].put(f"/admin/vendors/{vid_of(w['slug_a'])}/plan", json={"plan": "premium"}).status_code == 403


def test_03_totals_reconcile_with_orders_refunds_and_ledger(w):  # noqa: F811
    c, a, b = S["c9"], w["a"], w["b"]
    oid_, vos = paid(c, [(w["scarf"][1], 2), (w["shea"][1], 3)])
    va, vb = vos[w["slug_a"]], vos[w["slug_b"]]
    assert c.post(f"/orders/{oid_}/vendor-orders/{vb['id']}/cancel", json={"reason": "Changed mind"}, headers=K()).json()["result"] == "cancelled"
    a.post(f"/vendor/orders/{va['id']}/status", json={"to": "accepted"})
    item = va["items"][0]["id"]
    a.post(f"/vendor/orders/{va['id']}/shipments", json={"lines": [{"order_item_id": item, "quantity": 2}], "carrier": "usps", "tracking_number": "9400333333333333333333"})
    d = a.get("/vendor/dashboard", params={"from": ET_TODAY, "to": ET_TODAY}).json()
    A, B = vid_of(w["slug_a"]), vid_of(w["slug_b"])
    bounds = et_bounds(date.fromisoformat(ET_TODAY), date.fromisoformat(ET_TODAY))
    ta, t = ledger_truth(A, *bounds), d["sales"]["totals"]
    assert t["net_item_sales_minor"] == ta["net"] and t["gross_item_sales_minor"] == ta["gross"] and t["commission_minor"] == ta["commission"]
    assert t["processing_fees_minor"] == ta["fees"] and t["shipping_charged_minor"] == ta["shipping"] and t["vendor_earnings_minor"] == ta["earnings"]
    vo_a = mongo.vendor_orders.find_one({"_id": ObjectId(va["id"])})
    assert ta["gross"] >= vo_a["items_net_minor"] and sum(x["net_item_sales_minor"] for x in d["sales"]["series"]) == t["net_item_sales_minor"]
    assert t["orders"] == mongo.vendor_orders.count_documents({"vendor_id": A, "created_at": {"$gte": bounds[0], "$lt": bounds[1]}})
    db_ = b.get("/vendor/dashboard", params={"from": ET_TODAY, "to": ET_TODAY}).json()
    tb = ledger_truth(B, *bounds)
    assert db_["sales"]["totals"]["net_item_sales_minor"] == tb["net"] and db_["sales"]["totals"]["refunds_minor"] == tb["refunds"] < 0
    vo_b = mongo.vendor_orders.find_one({"_id": ObjectId(vb["id"])})
    assert tb["gross"] - tb["net"] >= vo_b["items_net_minor"]  # full cancellation refunded all of B's merchandise
    assert va["id"] not in {q["id"] for q in db_["operations"]["queue"]} and db_["sales"]["totals"]["cancelled_orders"] >= 1
    assert d["reviews"]["total"] == 0 and d["reviews"]["average"] is None
    assert d["inventory"]["products_total"] == mongo.products.count_documents({"vendor_id": A, "status": {"$ne": "deleted"}})
    rows = list(csv.reader(io.StringIO(a.get("/vendor/reports/summary.csv", params={"from": ET_TODAY, "to": ET_TODAY}).text)))
    assert dict(rows[1:])["net_item_sales"] == f"{t['net_item_sales_minor'] / 100:.2f}"
    tx = list(csv.reader(io.StringIO(a.get("/vendor/reports/transactions.csv", params={"from": ET_TODAY, "to": ET_TODAY}).text)))
    assert len(tx) - 1 == ta["count"] + mongo.commission_ledger.count_documents({"vendor_id": A, "account": "tax", "created_at": {"$gte": bounds[0], "$lt": bounds[1]}})
    a_keys = {e["entry_key"] for e in mongo.commission_ledger.find({"vendor_id": A}, {"entry_key": 1})}
    assert all(r[6] in a_keys for r in tx[1:])
    orders = list(csv.DictReader(io.StringIO(a.get("/vendor/reports/orders.csv", params={"from": ET_TODAY, "to": ET_TODAY}).text)))
    row = next(r for r in orders if r["order"] == va["order_number"])
    assert row["status"] == "shipped" and float(row["items_usd"]) * 100 == vo_a["items_net_minor"]
    assert len(orders) == t["orders"] and all(r["status"] != "cancelled" or r["order"] != va["order_number"] for r in orders)
    S["vo9"] = (va, vb)


def test_04_date_range_excludes_other_days(w):  # noqa: F811
    B = vid_of(w["slug_b"])
    tag = uuid.uuid4().hex[:8]
    for k, at in (("before", datetime(2026, 3, 8, 4, 59, tzinfo=timezone.utc)), ("inside", datetime(2026, 3, 8, 5, 0, tzinfo=timezone.utc)),
                  ("late", datetime(2026, 3, 9, 3, 59, tzinfo=timezone.utc)), ("after", datetime(2026, 3, 9, 4, 0, tzinfo=timezone.utc))):
        mongo.commission_ledger.insert_one({"entry_key": f"t9:{tag}:{k}", "account": "vendor", "type": "gross_sale", "amount_minor": 1000, "currency": "USD",
                                            "vendor_id": B, "vendor_order_id": None, "order_id": None, "payment_id": None, "meta": {"test": True}, "created_at": at})
    try:
        t = w["b"].get("/vendor/dashboard", params={"from": "2026-03-08", "to": "2026-03-08"}).json()["sales"]
        assert t["totals"]["gross_item_sales_minor"] == 2000 and t["series"] == [{"date": "2026-03-08", "net_item_sales_minor": 2000, "orders": 0}]
        assert w["b"].get("/vendor/dashboard", params={"from": "2026-03-07", "to": "2026-03-09"}).json()["sales"]["totals"]["gross_item_sales_minor"] == 4000
        assert w["a"].get("/vendor/dashboard", params={"from": "2026-03-08", "to": "2026-03-08"}).json()["sales"]["totals"]["gross_item_sales_minor"] == 0
    finally:
        mongo.commission_ledger.delete_many({"entry_key": {"$regex": f"^t9:{tag}:"}})


def test_05_plan_commission_applies_to_new_orders_only(w):  # noqa: F811
    adm, B = w["adm"], vid_of(w["slug_b"])
    has_override = mongo.commission_rules.find_one({"scope": "vendor", "scope_id": B, "status": "active"})
    va, vb = S["vo9"]
    before = mongo.order_items.find_one({"vendor_order_id": ObjectId(vb["id"])})
    r = adm.put(f"/admin/vendors/{B}/plan", json={"plan": "growth", "reason": "TEST upgrade"})
    assert r.status_code == 200 and r.json()["plan"]["rate_bps"] == 700
    try:
        _, vos = paid(S["c9"], [(w["shea"][1], 1)])
        it = mongo.order_items.find_one({"vendor_order_id": ObjectId(vos[w["slug_b"]]["id"])})
        if not has_override and not it.get("commission_source") == "category":
            assert it["commission_bps"] == 700 and it["commission_source"] == "plan:growth"
        assert mongo.order_items.find_one({"_id": before["_id"]})["commission_bps"] == before["commission_bps"]
        plan = w["b"].get("/vendor/dashboard").json()["plan"]
        assert plan["name"] == "Growth" and plan["monthly_fee_minor"] == 2499
    finally:
        mongo.vendors.update_one({"_id": B}, {"$unset": {"plan": ""}})
