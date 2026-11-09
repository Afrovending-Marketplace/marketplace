# Iteration 28 (T1): refund of unshipped units cancels them, releases stock once, closes fully refunded vendor orders; cancel_vendor_order no double count
import uuid

from bson import ObjectId

from tests.test_phase03_vendors import mongo
from tests.test_phase06_cart import live
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w  # noqa: F401

TAG = uuid.uuid4().hex[:6]
SHIP = {"carrier": "usps", "tracking_number": "9400TEST0028"}


def teardown_module():
    mongo.notifications.delete_many({"user_id": {"$in": S.get("buyers", [])}})


def inv(vid):
    d = mongo.inventory.find_one({"variant_id": ObjectId(vid)})
    return d["quantity_on_hand"], d.get("quantity_reserved", 0)


def paid(w, qty, stock=10):
    pid, vid = live(w["a"], w["adm"], f"TEST7 RC {TAG} {uuid.uuid4().hex[:4]}", 2000, stock)
    c = buyer()
    o = draft(c, [(vid, qty)])
    p = start_pay(c, o["id"])
    pi = real_pi(p["amount_minor"])
    assert send("checkout.session.completed", completed(p, pi.id)).status_code == 200
    vo = mongo.vendor_orders.find_one({"order_id": ObjectId(o["id"])})
    item = mongo.order_items.find_one({"vendor_order_id": vo["_id"]})
    assert vo["status"] == "pending" and inv(vid) == (stock, qty)
    return c, o, vo, item, vid


def refund(w, vo, item, qty, ship=False):
    return w["adm"].post(f"/admin/payments/vendor-orders/{vo['_id']}/refunds", headers={"Idempotency-Key": f"t1-{uuid.uuid4().hex}"},
                         json={"lines": [{"order_item_id": str(item["_id"]), "quantity": qty}], "reason": "TEST refund", "include_shipping": ship})


def ship(w, vo, item, qty):
    return w["a"].post(f"/vendor/orders/{vo['_id']}/shipments", json={"lines": [{"order_item_id": str(item["_id"]), "quantity": qty}], **SHIP})


def it(item):
    return mongo.order_items.find_one({"_id": item["_id"]})


def vo_(vo):
    return mongo.vendor_orders.find_one({"_id": vo["_id"]})


# Full refund of unshipped order -> cancelled, event, stock released once, accept/ship rejected, replay idempotent
def test_01_full_refund_unshipped_cancels(w):
    c, o, vo, item, vid = paid(w, 2)
    r = refund(w, vo, item, 2, ship=True)
    assert r.status_code == 201, r.text
    assert it(item)["cancelled_qty"] == 2 and it(item)["refunded_qty"] == 2
    assert inv(vid) == (10, 0)
    v = vo_(vo)
    assert v["status"] == "cancelled", v["status"]
    assert mongo.order_events.count_documents({"vendor_order_id": vo["_id"], "type": "cancelled"}) + \
        mongo.order_events.count_documents({"vendor_order_id": vo["_id"], "kind": "cancelled"}) + \
        mongo.order_events.count_documents({"vendor_order_id": vo["_id"], "to": "cancelled"}) >= 1, list(mongo.order_events.find({"vendor_order_id": vo["_id"]}))
    acc = w["a"].post(f"/vendor/orders/{vo['_id']}/status", json={"to": "accepted"})
    s = ship(w, vo, item, 1)
    print("accept:", acc.status_code, acc.text[:120], "ship:", s.status_code, s.text[:120])
    assert acc.status_code in (409, 422) and s.status_code in (409, 422)
    # over-refund rejected, stock untouched
    again = refund(w, vo, item, 1)
    print("refund again:", again.status_code, again.text[:150])
    assert again.status_code >= 400
    assert inv(vid) == (10, 0) and it(item)["cancelled_qty"] == 2
    # customer cancel on an already cancelled order is a no-op
    cc = c.post(f"/orders/{o['id']}/vendor-orders/{vo['_id']}/cancel", json={"reason": "TEST cancel"}, headers={"Idempotency-Key": f"t1-{uuid.uuid4().hex}"})
    print("customer cancel after close:", cc.status_code, cc.text[:150])
    assert inv(vid) == (10, 0) and it(item)["cancelled_qty"] == 2
    detail = w["a"].get(f"/vendor/orders/{vo['_id']}").json()
    print("vendor detail status:", detail.get("vendor_order", {}).get("status"))
    S["rc_cancelled_vo"] = str(vo["_id"])


# Partial refund of 1 of 2 unshipped -> 1 left shippable; ship 2 -> 422; ship 1 OK; refund of shipped unit doesn't touch cancelled_qty
def test_02_partial_refund_then_ship(w):
    c, o, vo, item, vid = paid(w, 2)
    assert refund(w, vo, item, 1).status_code == 201
    assert it(item)["cancelled_qty"] == 1 and inv(vid) == (10, 1)
    assert vo_(vo)["status"] == "pending"
    assert w["a"].post(f"/vendor/orders/{vo['_id']}/status", json={"to": "accepted"}).status_code == 200
    s2 = ship(w, vo, item, 2)
    assert s2.status_code == 422 and "left to ship" in s2.text, s2.text
    s1 = ship(w, vo, item, 1)
    assert s1.status_code == 201, s1.text
    assert inv(vid) == (9, 0)
    assert ship(w, vo, item, 1).status_code in (409, 422)
    v = vo_(vo)
    print("status after shipping the remaining unit:", v["status"])
    assert v["status"] != "cancelled"
    r = refund(w, vo, item, 1, ship=True)
    assert r.status_code == 201, r.text
    assert it(item)["cancelled_qty"] == 1 and it(item)["refunded_qty"] == 2 and inv(vid) == (9, 0)
    assert vo_(vo)["status"] != "cancelled"


# Partial refund then customer cancel (cancel_vendor_order): cancelled_qty == quantity, stock released exactly qty
def test_03_partial_refund_then_customer_cancel(w):
    c, o, vo, item, vid = paid(w, 3)
    assert refund(w, vo, item, 1).status_code == 201
    assert it(item)["cancelled_qty"] == 1 and inv(vid) == (10, 2)
    cc = c.post(f"/orders/{o['id']}/vendor-orders/{vo['_id']}/cancel", json={"reason": "TEST changed mind"}, headers={"Idempotency-Key": f"t1-{uuid.uuid4().hex}"})
    print("customer cancel:", cc.status_code, cc.text[:200])
    assert cc.status_code == 200
    i = it(item)
    print("after cancel: cancelled", i["cancelled_qty"], "refunded", i["refunded_qty"], "inv", inv(vid))
    assert i["cancelled_qty"] == 3 and i["refunded_qty"] == 3 and inv(vid) == (10, 0)
    assert vo_(vo)["status"] == "cancelled"
    assert sum(r["amount_minor"] for r in mongo.refunds.find({"vendor_order_id": vo["_id"], "status": "succeeded"})) == vo_(vo)["charged_minor"]


# Plain customer cancel (no prior refund): refund + cancel without double counting
def test_04_customer_cancel_only(w):
    c, o, vo, item, vid = paid(w, 2)
    cc = c.post(f"/orders/{o['id']}/vendor-orders/{vo['_id']}/cancel", json={"reason": "TEST cancel"}, headers={"Idempotency-Key": f"t1-{uuid.uuid4().hex}"})
    assert cc.status_code == 200, cc.text
    i = it(item)
    assert i["cancelled_qty"] == 2 and i["refunded_qty"] == 2 and inv(vid) == (10, 0)
    assert vo_(vo)["status"] == "cancelled"
    assert mongo.refunds.count_documents({"vendor_order_id": vo["_id"]}) == 1


# Partially shipped (ship 1 of 2) then refund 1: observational - which unit does it hit?
def test_05_partially_shipped_refund_observe(w):
    c, o, vo, item, vid = paid(w, 2)
    assert w["a"].post(f"/vendor/orders/{vo['_id']}/status", json={"to": "accepted"}).status_code == 200
    assert ship(w, vo, item, 1).status_code == 201
    assert refund(w, vo, item, 1).status_code == 201
    i = it(item)
    s = ship(w, vo, item, 1)
    print("partially shipped + refund 1: cancelled_qty", i["cancelled_qty"], "inv", inv(vid), "ship remaining:", s.status_code, s.text[:120],
          "vo status", vo_(vo)["status"])
    assert i["cancelled_qty"] == 0 and s.status_code == 201  # refunding a shipped unit never cancels the unshipped one
