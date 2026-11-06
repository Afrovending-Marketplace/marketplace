# Phase 11: verified-purchase reviews, seller ratings, vendor responses, moderation, order messaging privacy, notifications
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from tests.test_phase03_vendors import mongo
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, completed, draft, real_pi, send, start_pay, w  # noqa: F401
from tests.test_phase08_fulfillment import HOURS, _pickup_order, paid
from tests.test_phase10_admin import MADE, admin_with, teardown_module as _p10_teardown  # noqa: F401

T = {}


def teardown_module():
    buyers = S.get("buyers", [])
    vids = S.get("vendor_ids", [])
    for coll in ("reviews", "seller_ratings"):
        ids = [d["_id"] for d in mongo[coll].find({"customer_id": {"$in": buyers}})]
        mongo.review_reports.delete_many({"target_id": {"$in": ids}})
        mongo.audit_logs.delete_many({"entity_id": {"$in": ids + [str(i) for i in ids]}})
        mongo[coll].delete_many({"_id": {"$in": ids}})
    msgs = [m["_id"] for m in mongo.order_messages.find({"vendor_id": {"$in": vids}})]
    mongo.audit_logs.delete_many({"entity_id": {"$in": msgs + [str(i) for i in msgs]}})
    mongo.audit_logs.delete_many({"action": "account.notification_prefs_updated", "actor_id": {"$in": buyers}})
    mongo.order_messages.delete_many({"_id": {"$in": msgs}})
    owners = [v["owner_user_id"] for v in mongo.vendors.find({"_id": {"$in": vids}})]
    mongo.notifications.delete_many({"user_id": {"$in": buyers + owners}})
    mongo.platform_settings.delete_many({"key": "moderation.rules"})
    mongo.rate_limits.delete_many({"key": {"$regex": "^(review|msg)"}})
    _p10_teardown()


def _deliver_all(a, vo):
    for it in vo["items"]:
        left = it["quantity"] - it["shipped_qty"] - it["cancelled_qty"]
        if left:
            s = a.post(f"/vendor/orders/{vo['id']}/shipments", json={"lines": [{"order_item_id": it["id"], "quantity": left}], "carrier": "usps",
                                                                     "tracking_number": "9400100000000000000011"}).json()["shipment"]
            assert a.post(f"/vendor/shipments/{s['id']}/status", json={"status": "delivered"}).status_code == 200


def test_01_eligibility_partial_multi_vendor_duplicates(w):  # noqa: F811
    c, other = buyer(), buyer()
    T["c"] = c
    oid_, vos = paid(c, [(w["scarf"][1], 2), (w["shea"][1], 1)])
    va, vb = vos[w["slug_a"]], vos[w["slug_b"]]
    T.update(oid=oid_, va=va, vb=vb)
    scarf, shea = va["items"][0]["id"], vb["items"][0]["id"]
    good = {"rating": 5, "title": "Beautiful", "comment": "Lovely colours and well made."}
    assert c.put(f"/reviews/items/{scarf}", json=good).status_code == 403  # not received yet
    a = w["a"]
    assert a.post(f"/vendor/orders/{va['id']}/status", json={"to": "accepted"}).status_code == 200
    s = a.post(f"/vendor/orders/{va['id']}/shipments", json={"lines": [{"order_item_id": scarf, "quantity": 1}], "carrier": "ups", "tracking_number": "1Z999AA10123456700"}).json()["shipment"]
    assert c.put(f"/reviews/items/{scarf}", json=good).status_code == 403  # shipped but not delivered
    assert a.post(f"/vendor/shipments/{s['id']}/status", json={"status": "delivered"}).status_code == 200
    r = c.put(f"/reviews/items/{scarf}", json=good)
    assert r.status_code == 200 and r.json()["review"]["status"] == "published" and r.json()["review"]["verified_purchase"]
    T["rid"] = r.json()["review"]["id"]
    assert c.put(f"/reviews/sellers/{va['id']}", json=good).status_code == 403  # vendor order only partly delivered
    r2 = c.put(f"/reviews/items/{scarf}", json={**good, "rating": 4})
    assert r2.json()["review"]["id"] == T["rid"] and r2.json()["review"]["edited"] and mongo.reviews.count_documents({"order_item_id": ObjectId(scarf)}) == 1
    assert other.put(f"/reviews/items/{scarf}", json=good).status_code == 404
    assert a.put(f"/reviews/items/{scarf}", json=good).status_code == 404
    assert c.put(f"/reviews/items/{shea}", json=good).status_code == 403  # vendor B not delivered
    doc = mongo.reviews.find_one({"_id": ObjectId(T["rid"])})
    try:
        mongo.reviews.insert_one({k: v for k, v in doc.items() if k != "_id"})
        raise AssertionError("duplicate review allowed")
    except DuplicateKeyError:
        pass
    _deliver_all(a, c.get(f"/orders/{oid_}/detail").json()["vendor_orders"][[v["vendor_slug"] for v in c.get(f"/orders/{oid_}/detail").json()["vendor_orders"]].index(w["slug_a"])])
    neg = c.put(f"/reviews/sellers/{va['id']}", json={"rating": 1, "title": "Disappointing", "comment": "Terrible packaging and the seller was slow to ship."})
    assert neg.status_code == 200 and neg.json()["review"]["status"] == "published"  # negative reviews publish
    assert c.put(f"/reviews/sellers/{va['id']}", json={"rating": 2, "comment": "Slightly better after support."}).json()["review"]["id"] == neg.json()["review"]["id"]
    assert mongo.seller_ratings.count_documents({"vendor_order_id": ObjectId(va["id"])}) == 1
    st = c.get(f"/orders/{oid_}/review-status").json()["vendor_orders"]
    assert st[va["id"]]["seller_eligible"] and not st[vb["id"]]["seller_eligible"] and st[va["id"]]["items"][scarf]["review"]["rating"] == 4
    slug = mongo.products.find_one({"_id": ObjectId(va["items"][0]["product_id"])})["slug"]
    pr = c.get(f"/products/{slug}/reviews").json()
    assert pr["summary"]["total"] == 1 and pr["summary"]["average"] == 4 and pr["reviews"][0]["verified_purchase"]
    sr = c.get(f"/stores/{w['slug_a']}/seller-ratings").json()["summary"]
    assert sr["total"] == 1 and sr["average"] == 2
    assert c.get(f"/stores/{w['slug_b']}/seller-ratings").json()["summary"] == {"total": 0, "average": None, "distribution": {str(n): 0 for n in range(5, 0, -1)}}
    dash = a.get("/vendor/dashboard").json()["reviews"]
    assert dash["total"] == 1 and dash["average"] == 4 and dash["seller"]["average"] == 2


def test_02_pickup_collection_enables_review(w):  # noqa: F811
    a, c = w["a"], T["c"]
    m = a.post("/vendor/shipping-methods", json={"name": "TEST11 Pickup", "type": "pickup", "amount_minor": 0, "pickup_address": "1 Pickup Rd", "pickup_hours": HOURS}).json()
    _, vo = _pickup_order(c, w, m["id"])
    it = vo["items"][0]["id"]
    assert a.post(f"/vendor/orders/{vo['id']}/status", json={"to": "accepted"}).status_code == 200
    assert a.post(f"/vendor/orders/{vo['id']}/status", json={"to": "ready_for_pickup"}).status_code == 200
    assert c.put(f"/reviews/items/{it}", json={"rating": 3}).status_code == 403  # ready but not collected
    assert a.post(f"/vendor/orders/{vo['id']}/status", json={"to": "delivered"}).status_code == 200
    assert c.put(f"/reviews/items/{it}", json={"rating": 3}).json()["review"]["status"] == "published"
    assert c.put(f"/reviews/sellers/{vo['id']}", json={"rating": 5}).status_code == 200
    T["pickup_vo"] = vo


def test_03_moderation_flags_permissions_and_appeal(w):  # noqa: F811
    c = buyer()
    oid_, vos = paid(c, [(w["shea"][1], 1)])
    vb = vos[w["slug_b"]]
    assert w["b"].post(f"/vendor/orders/{vb['id']}/status", json={"to": "accepted"}).status_code == 200
    _deliver_all(w["b"], vb)
    it = vb["items"][0]["id"]
    r = c.put(f"/reviews/items/{it}", json={"rating": 5, "comment": "Great! Buy cheaper at www.my-cheap-shea.com or call 617-555-0199"}).json()["review"]
    assert r["status"] == "pending_moderation" and {"link", "phone"} <= set(r["flags"])
    slug = mongo.products.find_one({"_id": ObjectId(vb["items"][0]["product_id"])})["slug"]
    assert all(x["id"] != r["id"] for x in c.get(f"/products/{slug}/reviews").json()["reviews"])
    uid = mongo.users.find_one({"_id": S["buyers"][-1]})["_id"]
    assert mongo.notifications.find_one({"user_id": uid, "title": "Your review is being checked"})
    abuse = c.put(f"/reviews/sellers/{vb['id']}", json={"rating": 1, "comment": "You i d i o t, I will find you"}).json()["review"]
    assert abuse["status"] == "pending_moderation" and {"abuse", "threat"} <= set(abuse["flags"])
    sup, _ = admin_with("support_admin")
    mkt, _ = admin_with("marketplace_admin")
    content, _ = admin_with("content_admin")
    assert sup.get("/admin/reviews").status_code == 403 and content.get("/admin/reviews").status_code == 403
    q = mkt.get("/admin/reviews").json()["data"]
    assert any(x["id"] == r["id"] for x in q)
    assert mkt.post(f"/admin/reviews/product/{r['id']}/decision", json={"action": "reject", "reason": ""}).status_code == 422
    assert mkt.post(f"/admin/reviews/product/{r['id']}/decision", json={"action": "reject", "reason": "Contains outside links and a phone number"}).status_code == 200
    assert mongo.notifications.find_one({"user_id": uid, "title": "Update on your review"})
    fixed = c.put(f"/reviews/items/{it}", json={"rating": 5, "comment": "Great shea butter, very rich."}).json()["review"]
    assert fixed["status"] == "published"
    assert mkt.post(f"/admin/reviews/seller/{abuse['id']}/decision", json={"action": "remove", "reason": "Threatening language toward the seller"}).status_code == 200
    assert c.put(f"/reviews/sellers/{vb['id']}", json={"rating": 1, "comment": "ok"}).status_code == 409
    assert mongo.audit_logs.count_documents({"action": {"$regex": "^review.moderated"}, "entity_id": {"$in": [ObjectId(r["id"]), ObjectId(abuse["id"])]}}) == 2
    T.update(mkt=mkt, sup=sup, content=content)


def test_04_vendor_responses_reports(w):  # noqa: F811
    a, b, c = w["a"], w["b"], T["c"]
    rid = T["rid"]
    assert b.put(f"/vendor/reviews/product/{rid}/response", json={"body": "Thanks!"}).status_code == 404
    r = a.put(f"/vendor/reviews/product/{rid}/response", json={"body": "Thank you for shopping with us!"})
    assert r.status_code == 200 and r.json()["response"]["status"] == "published"
    assert a.put(f"/vendor/reviews/product/{rid}/response", json={"body": "Thank you so much for shopping with us!"}).status_code == 200
    doc = mongo.reviews.find_one({"_id": ObjectId(rid)})
    assert doc["response"]["body"].startswith("Thank you so much") and doc["rating"] == 4  # one response, rating untouched
    assert mongo.notifications.count_documents({"user_id": doc["customer_id"], "category": "reviews", "title": {"$regex": "responded"}}) >= 1
    held = a.put(f"/vendor/reviews/product/{rid}/response", json={"body": "Email me at seller.joe@gmail.com for a refund"}).json()["response"]
    assert held["status"] == "pending_moderation"
    slug = doc["product_slug"]
    assert next(x for x in c.get(f"/products/{slug}/reviews").json()["reviews"] if x["id"] == rid)["response"] is None
    assert a.post(f"/reviews/product/{rid}/report", json={"reason": "fake"}).status_code == 201
    assert a.post(f"/reviews/product/{rid}/report", json={"reason": "fake"}).status_code == 409
    row = next(x for x in T["mkt"].get("/admin/reviews").json()["data"] if x["id"] == rid)
    assert row["reports"][0]["reporter_role"] == "vendor" and row["response"]["status"] == "pending_moderation"
    assert T["mkt"].post(f"/admin/reviews/product/{rid}/decision", json={"part": "response", "action": "approve", "reason": "Reviewed: ok to show"}).status_code == 200


def test_05_order_messages_privacy(w):  # noqa: F811
    a, b, c = w["a"], w["b"], T["c"]
    oid_, va = T["oid"], T["va"]
    path = f"/orders/{oid_}/vendor-orders/{va['id']}/messages"
    m = c.post(path, json={"body": "Call me 617 555 0199 or j.doe (at) gmail (dot) com"}).json()["message"]
    assert "[contact details hidden]" in m["body"] and m["notice"]
    ok = c.post(path, json={"body": "Please leave it at the back door, gate code 4521. Order AV-123456-ABCDEF."}).json()["message"]
    assert ok["notice"] is None and "4521" in ok["body"]
    pay = c.post(path, json={"body": "Can I pay you on paypal.me/joe instead?"}).json()["message"]
    assert pay["notice"]
    site = c.post(path, json={"body": "FAQ is at https://www.afrovending.com/faq"}).json()["message"]
    assert site["notice"] is None and "afrovending.com/faq" in site["body"]
    assert c.post(path, json={"body": "FAQ is at https://www.afrovending.com/faq"}).status_code == 429
    vt = a.get(f"/vendor/orders/{va['id']}/messages").json()["messages"]
    bodies = [x["body"] for x in vt]
    assert not any("617" in x or "gmail" in x or "paypal" in x for x in bodies)
    assert "This message is being reviewed by AfroVending before delivery." in bodies
    assert b.get(f"/vendor/orders/{va['id']}/messages").status_code == 404
    assert buyer().get(path).status_code == 404
    reply = a.post(f"/vendor/orders/{va['id']}/messages", json={"body": "Will do! Text me at five five five one two three four five six seven"}).json()["message"]
    assert "[contact details hidden]" in reply["body"]
    assert T["content"].get("/admin/messages/flagged").status_code == 403
    flagged = T["sup"].get("/admin/messages/flagged").json()["data"]
    held = next(x for x in flagged if "paypal" in x["original"])
    assert held["held"] and "617 555 0199" in next(x for x in flagged if "617" in x["original"])["original"]
    assert T["sup"].post(f"/admin/messages/{held['id']}/review", json={"action": "dismiss", "note": "Customer question only"}).status_code == 200
    assert "[payment details hidden]" in [x for x in a.get(f"/vendor/orders/{va['id']}/messages").json()["messages"] if x["id"] == held["id"]][0]["body"]
    vendor_owner = mongo.vendors.find_one({"_id": mongo.vendor_orders.find_one({"_id": ObjectId(va["id"])})["vendor_id"]})["owner_user_id"]
    n = mongo.notifications.find_one({"user_id": vendor_owner, "category": "messages"})
    assert n and "617" not in n["body"] and "gmail" not in n["body"]
    assert mongo.audit_logs.find_one({"action": "message.review_dismiss", "entity_id": {"$in": [held["id"], ObjectId(held["id"])]}})


def test_06_notifications_center_and_preferences(w):  # noqa: F811
    c, other = T["c"], buyer()
    d = c.get("/notifications").json()
    assert d["unread"] >= 1 and any(n["category"] == "orders" for n in d["data"])
    assert other.post(f"/notifications/{d['data'][0]['id']}/read").status_code == 404
    assert c.post(f"/notifications/{d['data'][0]['id']}/read").status_code == 200
    p = c.get("/notifications/preferences").json()["preferences"]
    p["messages"]["email"] = False
    assert c.put("/notifications/preferences", json=p).status_code == 200
    va = T["va"]
    w["a"].post(f"/vendor/orders/{va['id']}/messages", json={"body": "Your parcel is on the way."})
    uid = mongo.vendor_orders.find_one({"_id": ObjectId(va["id"])})["customer_id"]
    last = mongo.notifications.find_one({"user_id": uid, "category": "messages"}, sort=[("created_at", -1)])
    assert last["email_status"] == "disabled_by_preference"
    assert c.post("/notifications/read-all").status_code == 200 and c.get("/notifications/unread-count").json()["unread"] == 0


def test_07_rules_config_and_rate_limits(w):  # noqa: F811
    mkt, sup = T["mkt"], T["sup"]
    rules = mkt.get("/admin/moderation/rules").json()
    assert sup.put("/admin/moderation/rules", json=rules).status_code == 403
    assert sorted(mkt.put("/admin/moderation/rules", json={**rules, "approved_domains": ["partner-example.org"]}).json()["approved_domains"]) == ["afrovending.com", "partner-example.org"]
    va = T["va"]
    m = T["c"].post(f"/orders/{T['oid']}/vendor-orders/{va['id']}/messages", json={"body": "See partner-example.org/guide"}).json()["message"]
    assert m["notice"] is None
    codes = [T["c"].post(f"/orders/{T['oid']}/vendor-orders/{va['id']}/messages", json={"body": f"question number {i}"}).status_code for i in range(25)]
    assert 429 in codes
