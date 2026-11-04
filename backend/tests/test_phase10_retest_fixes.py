# Phase 10 retest (iteration 16): banner cta_url hardening, invalid ObjectId handling, cumulative refund threshold
import uuid

from bson import ObjectId

from tests.test_phase03_vendors import mongo, admin_client
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w  # noqa: F401
from tests.test_phase08_fulfillment import paid
from tests.test_phase10_admin import MADE, admin_with, teardown_module as _p10_teardown  # noqa: F401

APPROVALS, BANNERS = [], []


def teardown_module():
    mongo.admin_approvals.delete_many({"_id": {"$in": [ObjectId(i) for i in APPROVALS]}})
    mongo.content_banners.delete_many({"_id": {"$in": [ObjectId(i) for i in BANNERS]}})
    mongo.platform_settings.delete_many({"key": "admin.approvals"})
    _p10_teardown()


# Banner CTA URL validation
def test_01_banner_cta_url():
    cc, _ = admin_with("content_admin")
    rejected_ok, accepted_ok = [], []
    for bad in ("//evil.com", "/\\evil.com", "javascript:alert(1)", "JavaScript:alert(1)", "http://x.com", "data:text/html,x", " //evil.com"):
        r = cc.post("/admin/content/banners", json={"title": "TEST bad", "cta_url": bad})
        if r.status_code == 201:
            BANNERS.append(r.json()["id"])
            accepted_ok.append(bad)
        else:
            assert r.status_code == 422, (bad, r.status_code, r.text)
            print("rejected", bad, r.json())
    for good in ("/shop", "https://x.com", "", "/"):
        r = cc.post("/admin/content/banners", json={"title": "TEST good", "cta_url": good, "status": "inactive"})
        assert r.status_code == 201, (good, r.text)
        BANNERS.append(r.json()["id"])
        assert r.json()["cta_url"] == good
        rejected_ok.append(good)
    assert not accepted_ok, f"unsafe accepted: {accepted_ok}"
    # update with bad url also rejected
    bid = BANNERS[-1]
    assert cc.put(f"/admin/content/banners/{bid}", json={"title": "TEST good", "cta_url": "//evil.com"}).status_code == 422


# Invalid ObjectId inputs -> 404/422 not 500
def test_02_invalid_object_ids():
    sup = admin_client()
    res = {
        "DELETE invite": sup.delete("/admin/team/invites/notanid").status_code,
        "PUT banner": sup.put("/admin/content/banners/notanid", json={"title": "TEST x", "cta_url": "/shop"}).status_code,
        "PATCH banner": sup.patch("/admin/content/banners/notanid", json={"title": "TEST x"}).status_code,
        "DELETE banner": sup.delete("/admin/content/banners/notanid").status_code,
        "GET tickets assigned_to": sup.get("/admin/support/tickets", params={"assigned_to": "notanid"}).status_code,
        "GET tickets assigned_to none": sup.get("/admin/support/tickets", params={"assigned_to": "none"}).status_code,
        "PATCH ticket bad": sup.patch("/admin/support/tickets/notanid", json={"status": "open"}).status_code,
        "decide bad": sup.post("/admin/approvals/notanid/decide", json={"decision": "approve"}).status_code,
        "refund bad vo": sup.post("/admin/payments/vendor-orders/notanid/refunds", json={"lines": [], "include_shipping": True, "reason": "x"},
                                  headers={"Idempotency-Key": f"t16-{uuid.uuid4().hex}"}).status_code,
        "team user bad": sup.patch("/admin/team/notanid", json={"role": "content_admin"}).status_code,
    }
    print(res)
    assert all(v != 500 and v < 500 for v in res.values()), res
    assert res["DELETE invite"] == 404 and res["DELETE banner"] == 404 and res["PUT banner"] == 404
    assert res["GET tickets assigned_to"] in (404, 422) and res["GET tickets assigned_to none"] == 200


# Cumulative refund threshold
def test_03_cumulative_refund_threshold(w):  # noqa: F811
    sup = admin_client()
    c = buyer()
    _, vos = paid(c, [(w["scarf"][1], 2)])
    vo = mongo.vendor_orders.find_one({"customer_id": S["buyers"][-1], "vendor_slug": w["slug_a"]}, sort=[("_id", -1)])
    item = mongo.order_items.find_one({"vendor_order_id": vo["_id"]})
    unit = item["line_total_minor"] // item["quantity"]
    print("unit", unit, "qty", item["quantity"])
    assert item["quantity"] == 2
    # threshold between 1 unit and 2 units
    assert sup.put("/admin/approvals/config", json={"refund_threshold_minor": unit + unit // 2}).status_code == 200
    f1, _ = admin_with("finance_admin")
    body = {"lines": [{"order_item_id": str(item["_id"]), "quantity": 1}], "reason": "TEST cumulative"}
    r1 = f1.post(f"/admin/payments/vendor-orders/{vo['_id']}/refunds", json=body, headers={"Idempotency-Key": f"t16-{uuid.uuid4().hex}"})
    assert r1.status_code in (200, 201), r1.text
    assert "refund" in r1.json()
    r2 = f1.post(f"/admin/payments/vendor-orders/{vo['_id']}/refunds", json=body, headers={"Idempotency-Key": f"t16-{uuid.uuid4().hex}"})
    print("second", r2.status_code, r2.text[:300])
    assert r2.status_code == 202, r2.text
    APPROVALS.append(r2.json()["approval_id"])
    assert r2.json()["status"] == "pending_approval"
    assert mongo.refunds.count_documents({"vendor_order_id": vo["_id"]}) == 1
