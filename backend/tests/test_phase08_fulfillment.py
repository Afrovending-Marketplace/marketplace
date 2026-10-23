import csv
import io
import time
import uuid
from datetime import datetime

import httpx
from bson import ObjectId

from tests.test_phase03_vendors import _ENV, mongo
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w  # noqa: F401

K = lambda: {"Idempotency-Key": f"t8-{uuid.uuid4().hex}"}  # noqa: E731


def paid(c, items) -> tuple[str, dict]:
    order = draft(c, items)
    p = start_pay(c, order["id"])
    send("checkout.session.completed", completed(p, real_pi(p["amount_minor"]).id))
    return order["id"], {v["vendor_slug"]: v for v in c.get(f"/orders/{order['id']}/detail").json()["vendor_orders"]}


def inv(vid):
    return mongo.inventory.find_one({"variant_id": ObjectId(vid)})


def test_01_multi_vendor_cancel_ship_partial_deliver(w):  # noqa: F811
    c = buyer()
    S["c8"] = c
    oid_, vos = paid(c, [(w["scarf"][1], 2), (w["shea"][1], 3)])
    S["o8"] = oid_
    va, vb = vos[w["slug_a"]], vos[w["slug_b"]]
    assert va["status"] == "pending" and va["shipping_address"]["city"] == "Boston"
    assert inv(w["shea"][1])["quantity_reserved"] == 3
    r = c.post(f"/orders/{oid_}/vendor-orders/{vb['id']}/cancel", json={"reason": "Changed mind"}, headers=K()).json()
    assert r["result"] == "cancelled" and r["vendor_order"]["refunds"][0]["status"] == "succeeded"
    assert c.post(f"/orders/{oid_}/vendor-orders/{vb['id']}/cancel", json={"reason": "again"}, headers=K()).json()["result"] == "cancelled"
    assert mongo.refunds.count_documents({"vendor_order_id": ObjectId(vb["id"])}) == 1
    assert inv(w["shea"][1])["quantity_reserved"] == 0 and inv(w["shea"][1])["quantity_on_hand"] == 10
    assert w["b"].post(f"/vendor/orders/{vb['id']}/status", json={"to": "accepted"}).status_code == 409
    a = w["a"]
    assert w["b"].post(f"/vendor/orders/{va['id']}/status", json={"to": "accepted"}).status_code == 404
    assert a.post(f"/vendor/orders/{va['id']}/status", json={"to": "accepted"}).status_code == 200
    assert a.post(f"/vendor/orders/{va['id']}/status", json={"to": "delivered"}).status_code == 409
    req = c.post(f"/orders/{oid_}/vendor-orders/{va['id']}/cancel", json={"reason": "Too slow"}, headers=K()).json()
    assert req["result"] == "requested"
    item = va["items"][0]["id"]
    s1 = a.post(f"/vendor/orders/{va['id']}/shipments", json={"lines": [{"order_item_id": item, "quantity": 1}], "carrier": "ups", "tracking_number": "1Z999AA10123456784"})
    assert s1.status_code == 201 and "ups.com" in s1.json()["shipment"]["tracking_url"]
    assert inv(w["scarf"][1])["quantity_on_hand"] == 4 and inv(w["scarf"][1])["quantity_reserved"] == 1
    q = a.get("/vendor/orders?status=partially_shipped").json()
    rid = q["data"][0]["requests"][0]["id"]
    assert a.post(f"/vendor/requests/{rid}/decide", json={"decision": "approve"}).status_code == 409
    assert a.post(f"/vendor/requests/{rid}/decide", json={"decision": "reject", "note": "Already shipping"}).status_code == 200
    assert a.post(f"/vendor/orders/{va['id']}/shipments", json={"lines": [{"order_item_id": item, "quantity": 2}], "carrier": "usps", "tracking_number": "9400100000000000000000"}).status_code == 422
    s2 = a.post(f"/vendor/orders/{va['id']}/shipments", json={"lines": [{"order_item_id": item, "quantity": 1}], "carrier": "usps", "tracking_number": "9400100000000000000000"}).json()
    for s in (s1.json()["shipment"], s2["shipment"]):
        assert a.post(f"/vendor/shipments/{s['id']}/status", json={"status": "delivered"}).status_code == 200
    d = c.get(f"/orders/{oid_}/detail").json()["vendor_orders"]
    va = next(v for v in d if v["vendor_slug"] == w["slug_a"])
    assert va["status"] == "delivered" and len(va["shipments"]) == 2
    assert inv(w["scarf"][1])["quantity_on_hand"] == 3 and inv(w["scarf"][1])["quantity_reserved"] == 0
    types = [e["type"] for e in va["events"]]
    assert "status_partially_shipped" in types and "status_delivered" in types and "cancel_rejected" in types
    S["va8"] = va


def test_02_return_rma_refund_restock_and_admin_override(w):  # noqa: F811
    c, a, va, oid_ = S["c8"], w["a"], S["va8"], S["o8"]
    item = va["items"][0]["id"]
    assert c.post(f"/orders/{oid_}/vendor-orders/{va['id']}/returns", json={"lines": [{"order_item_id": item, "quantity": 3}], "reason": "Wrong size"}).status_code == 422
    r = c.post(f"/orders/{oid_}/vendor-orders/{va['id']}/returns", json={"lines": [{"order_item_id": item, "quantity": 1}], "reason": "Wrong size"})
    assert r.status_code == 201
    rid = r.json()["request"]["id"]
    vo = mongo.vendor_orders.find_one({"_id": ObjectId(va["id"])})
    assert any(h["active"] and h["ref"] == rid for h in vo["holds"])
    ok = a.post(f"/vendor/requests/{rid}/decide", json={"decision": "approve"}).json()["request"]
    assert ok["rma_number"].startswith("RMA-")
    done = a.post(f"/vendor/requests/{rid}/receive", json={"restock": True}).json()["request"]
    assert done["status"] == "refunded"
    ref = mongo.refunds.find_one({"_id": ObjectId(done["refund_id"])})
    assert ref["status"] == "succeeded" and ref["amount_minor"] == 4500 + 281 and ref["commission_returned_minor"] == 675
    assert inv(w["scarf"][1])["quantity_on_hand"] == 4
    assert not any(h["active"] and h["ref"] == rid for h in mongo.vendor_orders.find_one({"_id": vo["_id"]})["holds"])
    r2 = c.post(f"/orders/{oid_}/vendor-orders/{va['id']}/returns", json={"lines": [{"order_item_id": item, "quantity": 1}], "reason": "Faded"}).json()["request"]
    mongo.order_requests.update_one({"_id": ObjectId(r2["id"])}, {"$set": {"due_at": datetime(2020, 1, 1)}})
    cron = httpx.post(_ENV["FRONTEND_URL"] + "/api/v1/cron/fulfillment-escalations", headers={"Authorization": f"Bearer {_ENV['WEBHOOK_CRON_SECRET']}",
                                                                                            "X-Webhook-Id": f"test-t8-{uuid.uuid4().hex}"}, json={}, timeout=60)
    assert cron.status_code == 202
    for _ in range(10):
        if mongo.order_requests.find_one({"_id": ObjectId(r2["id"])})["escalated"]:
            break
        time.sleep(1)
    assert mongo.order_requests.find_one({"_id": ObjectId(r2["id"])})["escalated"]
    adm = w["adm"]
    assert adm.post(f"/admin/fulfillment/requests/{r2['id']}/decide", json={"decision": "reject", "note": ""}).status_code == 422
    assert adm.post(f"/admin/fulfillment/requests/{r2['id']}/decide", json={"decision": "reject", "note": "Outside policy: worn item"}).status_code == 200
    assert a.post(f"/vendor/requests/{r2['id']}/decide", json={"decision": "approve"}).status_code == 409
    hist = mongo.order_requests.find_one({"_id": ObjectId(r2["id"])})["history"]
    assert [h["role"] for h in hist] == ["customer", "admin"]
    assert w["a"].get("/admin/fulfillment/requests").status_code == 403


def test_03_vendor_shipping_methods_and_pickup_rules(w):  # noqa: F811
    m = w["a"].post("/vendor/shipping-methods", json={"name": "TEST8 Pickup", "type": "pickup", "amount_minor": 0, "pickup_address": "12 Market St, Boston"})
    assert m.status_code == 201
    assert w["b"].put(f"/vendor/shipping-methods/{m.json()['id']}", json={"name": "Hijack", "amount_minor": 1}).status_code == 404
    assert w["a"].post("/vendor/shipping-methods", json={"name": "TEST8 Bad", "type": "pickup", "amount_minor": 0}).status_code == 422
    assert w["a"].post(f"/vendor/orders/{S['va8']['id']}/status", json={"to": "ready_for_pickup"}).status_code == 409
    mongo.shipping_methods.delete_many({"name": {"$regex": "^TEST8"}})


def test_04_statements_pdf_csv_permissions(w):  # noqa: F811
    a = w["a"]
    periods = a.get("/vendor/payments/statements").json()["data"]
    assert periods and periods[0]["statement_id"].startswith("AVS-")
    p = periods[0]["period"]
    pdf = a.get(f"/vendor/payments/statements/{p}.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    rows = list(csv.reader(io.StringIO(a.get(f"/vendor/payments/statements/{p}.csv").text)))
    entries = [r for r in rows[2:] if r[0] != "TOTAL"]
    totals = {r[1]: r[3] for r in rows if r[0] == "TOTAL"}
    vid = mongo.vendor_stores.find_one({"slug": w["slug_a"]})["vendor_id"]
    ledger_sum = sum(e["amount_minor"] for e in mongo.commission_ledger.find({"account": "vendor", "vendor_id": vid, "type": {"$nin": ["transfer", "transfer_reversal"]}}))
    assert round(float(totals["Net marketplace earnings"]) * 100) == ledger_sum
    assert round(sum(float(r[3]) for r in entries if r[1] not in ("transfer", "transfer_reversal")) * 100) == ledger_sum
    assert a.get(f"/vendor/payments/statements/{p}.csv").text == a.get(f"/vendor/payments/statements/{p}.csv").text
    assert mongo.statements.count_documents({"statement_id": periods[0]["statement_id"]}) == 1
    assert a.get(f"/admin/payments/statements/{vid}/{p}.csv").status_code == 403
    assert w["adm"].get(f"/admin/payments/statements/{vid}/{p}.pdf").status_code == 200
    assert a.get("/vendor/payments/statements/2026-13.csv").status_code == 422
    mongo.statements.delete_many({"vendor_id": {"$in": S["vendor_ids"]}})


def test_05_business_days():
    from datetime import timezone
    from afrovending.core.business_days import add_business_days
    fri = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
    assert add_business_days(fri, 3, set()) == datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
    assert add_business_days(fri, 3, {"2026-10-26"}) == datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)
    sat = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)
    assert add_business_days(sat, 1, set()) == datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
    assert add_business_days(fri, 0, set()) == fri


def run_cron(name: str) -> None:
    rid = f"test-t8-{uuid.uuid4().hex}"
    r = httpx.post(_ENV["FRONTEND_URL"] + f"/api/v1/cron/{name}", headers={"Authorization": f"Bearer {_ENV['WEBHOOK_CRON_SECRET']}", "X-Webhook-Id": rid},
                   json={}, timeout=60)
    assert r.status_code == 202
    for _ in range(20):
        if (mongo.cron_runs.find_one({"run_id": rid}) or {}).get("status") == "done":
            return
        time.sleep(0.5)
    raise AssertionError("cron did not finish")


def logs(vo_id, kind):
    docs = list(mongo.notification_log.find({"vendor_order_id": ObjectId(vo_id), "kind": kind}))
    assert all(d["status"] in ("sent", "failed") and d["attempts"] <= 5 for d in docs)
    return len(docs)


def test_06_handling_deadline_snapshot_alerts_extension(w):  # noqa: F811
    from datetime import timedelta, timezone
    from afrovending.core.business_days import add_business_days
    c, a, adm = S["c8"], w["a"], w["adm"]
    oid_, vos = paid(c, [(w["scarf"][1], 1)])
    va = vos[w["slug_a"]]
    assert va["handling"] is None and va["shipping_method"]["handling_days"] == 3
    a.post(f"/vendor/orders/{va['id']}/status", json={"to": "accepted"})
    vo = mongo.vendor_orders.find_one({"_id": ObjectId(va["id"])})
    h = vo["handling"]
    assert h["days"] == 3 and h["kind"] == "ship"
    assert h["deadline_at"].replace(tzinfo=timezone.utc) == add_business_days(h["started_at"].replace(tzinfo=timezone.utc), 3, set())
    cfg = adm.get("/admin/fulfillment/config").json()
    assert adm.put("/admin/fulfillment/config", json={**cfg, "default_handling_days": 20, "max_handling_days": 5}).status_code == 422
    assert adm.put("/admin/fulfillment/config", json={**cfg, "default_handling_days": 5}).status_code == 200
    assert mongo.vendor_orders.find_one({"_id": vo["_id"]})["handling"]["deadline_at"] == h["deadline_at"]
    assert a.post("/vendor/shipping-methods", json={"name": "TEST8 Slow", "amount_minor": 100, "handling_days": 40}).status_code == 422
    m = a.post("/vendor/shipping-methods", json={"name": "TEST8 Std", "amount_minor": 100}).json()
    assert m["handling_days"] == 5
    adm.put("/admin/fulfillment/config", json=cfg)
    now = datetime.now(timezone.utc)
    mongo.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"handling.deadline_at": now + timedelta(hours=2)}})
    run_cron("handling-alerts")
    run_cron("handling-alerts")
    assert logs(va["id"], "reminder") == 1 and logs(va["id"], "overdue_customer") == 0
    mongo.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"handling.deadline_at": now - timedelta(hours=1)}})
    run_cron("handling-alerts")
    run_cron("handling-alerts")
    assert logs(va["id"], "overdue_customer") == 1 and logs(va["id"], "overdue_vendor") == 1 and logs(va["id"], "overdue_admin") == 0
    assert mongo.vendor_orders.find_one({"_id": vo["_id"]})["handling"]["overdue"] is True
    assert any(o["id"] == va["id"] for o in adm.get("/admin/fulfillment/overdue").json()["data"])
    mongo.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"handling.deadline_at": now - timedelta(hours=49)}})
    run_cron("handling-alerts")
    run_cron("handling-alerts")
    assert logs(va["id"], "overdue_admin") == 1
    assert a.post(f"/admin/fulfillment/vendor-orders/{va['id']}/extend", json={"business_days": 2, "reason": "Supplier delay"}).status_code == 403
    assert adm.post(f"/admin/fulfillment/vendor-orders/{va['id']}/extend", json={"business_days": 2, "reason": "x"}).status_code == 422
    ext = adm.post(f"/admin/fulfillment/vendor-orders/{va['id']}/extend", json={"business_days": 5, "reason": "Supplier delay documented"})
    assert ext.status_code == 200
    h2 = mongo.vendor_orders.find_one({"_id": vo["_id"]})["handling"]
    assert h2["overdue"] is False and len(h2["extensions"]) == 1 and h2["extensions"][0]["reason"] == "Supplier delay documented"
    assert h2["original_deadline_at"] == h["deadline_at"]
    item = va["items"][0]["id"]
    s = a.post(f"/vendor/orders/{va['id']}/shipments", json={"lines": [{"order_item_id": item, "quantity": 1}], "carrier": "usps", "tracking_number": "9400111111111111111111"}).json()["shipment"]
    mongo.vendor_orders.update_one({"_id": vo["_id"]}, {"$set": {"handling.deadline_at": now - timedelta(hours=100)}})
    before = mongo.notification_log.count_documents({"vendor_order_id": vo["_id"]})
    run_cron("handling-alerts")
    assert mongo.notification_log.count_documents({"vendor_order_id": vo["_id"]}) == before
    assert not any(o["id"] == va["id"] for o in adm.get("/admin/fulfillment/overdue").json()["data"])
    S["slip"] = (va["id"], s["id"])
    mongo.shipping_methods.delete_many({"name": {"$regex": "^TEST8"}})


def test_07_packing_slips(w):  # noqa: F811
    vo_id, ship_id = S["slip"]
    a, b = w["a"], w["b"]
    r = a.get(f"/vendor/orders/{vo_id}/packing-slip")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and r.headers["content-type"] == "application/pdf"
    assert a.get(f"/vendor/orders/{vo_id}/packing-slip", params={"shipment_id": ship_id}).status_code == 200
    assert b.get(f"/vendor/orders/{vo_id}/packing-slip").status_code == 404
    assert S["c8"].get(f"/vendor/orders/{vo_id}/packing-slip").status_code in (403, 404)
    other = mongo.shipments.find_one({"vendor_id": {"$ne": mongo.vendor_orders.find_one({"_id": ObjectId(vo_id)})["vendor_id"]}})
    if other:
        assert a.get(f"/vendor/orders/{vo_id}/packing-slip", params={"shipment_id": str(other["_id"])}).status_code == 404
    from afrovending.core.packing_slip import build_slip
    from reportlab import rl_config
    rl_config.pageCompression = 0
    vo = mongo.vendor_orders.find_one({"_id": ObjectId(vo_id)})
    items = list(mongo.order_items.find({"vendor_order_id": vo["_id"]}))
    text = build_slip(vo, [(i, i["quantity"]) for i in items], None)
    assert vo["order_number"].encode() in text and items[0]["sku"].encode() in text
    assert b"$" not in text and b"info@afrovending.com" in text
