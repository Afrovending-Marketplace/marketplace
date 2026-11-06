"""Verified-purchase product reviews, per-vendor-order seller ratings, one vendor response per review, abuse reports and admin moderation."""
import hashlib
from datetime import timedelta
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from afrovending.core import moderation as mod
from afrovending.core import rate_limit
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.notify import notify
from afrovending.core.permissions import MOD_RULES, REVIEWS_MOD, require_perm

router = APIRouter(tags=["reviews"])
Kind = Literal["product", "seller"]
COLL = {"product": "reviews", "seller": "seller_ratings"}
PUBLIC = "published"


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str = Field(default="", max_length=120)
    comment: str = Field(default="", max_length=3000)
    photo_file_ids: list[str] = Field(default_factory=list, max_length=3)


class ResponseIn(BaseModel):
    body: str = Field(min_length=2, max_length=2000)


class ReportIn(BaseModel):
    part: Literal["review", "response"] = "review"
    reason: Literal["spam", "abuse", "contact_info", "off_topic", "fake", "other"]
    details: str = Field(default="", max_length=500)


class DecisionIn(BaseModel):
    part: Literal["review", "response"] = "review"
    action: Literal["approve", "reject", "remove"]
    reason: str = Field(min_length=5, max_length=500)


class RulesIn(BaseModel):
    approved_domains: list[str] = Field(max_length=50)
    payment_terms: list[str] = Field(max_length=200)
    payment_domains: list[str] = Field(max_length=100)
    threat_terms: list[str] = Field(max_length=200)
    abuse_terms: list[str] = Field(max_length=300)
    spam_terms: list[str] = Field(max_length=200)


def _oid(v: str) -> ObjectId:
    if not ObjectId.is_valid(v):
        raise APIError(404, "not_found", "Not found.")
    return ObjectId(v)


def _display_name(u: User) -> str:
    parts = (u.name or "Customer").split()
    return parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "")


async def _received_item_ids(vo: dict) -> set:
    """Items the buyer actually has: whole vendor order delivered/collected, or the item sits in a shipment marked delivered."""
    items = await db.order_items.find({"vendor_order_id": vo["_id"]}).to_list(100)
    if vo["status"] == "delivered":
        return {i["_id"] for i in items if i.get("shipped_qty", 0) > 0}
    if vo.get("fulfillment_type") == "pickup":
        return set()
    ships = await db.shipments.find({"vendor_order_id": vo["_id"], "status": "delivered"}).to_list(50)
    return {ln["order_item_id"] for s in ships for ln in s.get("lines", [])}


def _photos(d: dict, everything: bool = False) -> list:
    return [{"id": str(p["file_id"]), "url": f"/api/v1/reviews/photos/{p['file_id']}", **({"status": p["status"]} if everything else {})}
            for p in d.get("photos", []) if everything or p["status"] == "approved"]


async def _photo_list(ids: list[str], user: User, existing: dict | None) -> list:
    """Buyer's own uploads only; already-reviewed photos keep their status, new ones wait for an admin."""
    prior = {p["file_id"]: p for p in (existing or {}).get("photos", [])}
    out = []
    for fid in dict.fromkeys(ids):
        if not ObjectId.is_valid(fid):
            raise APIError(422, "validation_error", "Unknown photo.")
        f = await db.files.find_one({"_id": ObjectId(fid), "owner_user_id": ObjectId(user.id), "purpose": "review_photo", "is_deleted": False})
        if not f:
            raise APIError(422, "validation_error", "Upload each photo before attaching it.")
        out.append(prior.get(f["_id"]) or {"file_id": f["_id"], "status": "pending", "added_at": utcnow()})
    return out


def _pub_review(d: dict, kind: str) -> dict:
    resp = d.get("response")
    return {"id": str(d["_id"]), "kind": kind, "rating": d["rating"], "title": d.get("title", ""), "comment": d.get("comment", ""), "photos": _photos(d),
            "author": d["author_name"], "verified_purchase": True, "created_at": d["created_at"], "updated_at": d["updated_at"], "edited": d.get("edited", False),
            "product_title": d.get("product_title"), "vendor_name": d.get("vendor_name"),
            "response": {"body": resp["body"], "updated_at": resp["updated_at"]} if resp and resp.get("status") == PUBLIC else None}


def _own_review(d: dict, kind: str) -> dict:
    resp = d.get("response")
    return {**_pub_review(d, kind), "status": d["status"], "moderation_note": d.get("moderation_note"), "flags": d.get("flags", []), "photos": _photos(d, True),
            "response": {"body": resp["body"], "updated_at": resp["updated_at"]} if resp and resp.get("status") == PUBLIC else None}


async def _summary(coll: str, q: dict) -> dict:
    rows = await db[coll].aggregate([{"$match": {**q, "status": PUBLIC}}, {"$group": {"_id": "$rating", "n": {"$sum": 1}}}]).to_list(10)
    dist = {str(s): 0 for s in range(5, 0, -1)}
    for r in rows:
        dist[str(r["_id"])] = r["n"]
    total = sum(dist.values())
    return {"total": total, "average": round(sum(int(k) * v for k, v in dist.items()) / total, 2) if total else None, "distribution": dist}


async def _suspicious(coll: str, user: User, comment: str, vendor_id) -> list[str]:
    flags = []
    since = utcnow() - timedelta(hours=1)
    if await db.reviews.count_documents({"customer_id": ObjectId(user.id), "updated_at": {"$gte": since}}) + \
            await db.seller_ratings.count_documents({"customer_id": ObjectId(user.id), "updated_at": {"$gte": since}}) >= 8:
        flags.append("burst")
    if len(comment) >= 20:
        h = hashlib.sha256(" ".join(comment.lower().split()).encode()).hexdigest()
        same = await db[coll].count_documents({"comment_hash": h, "vendor_id": vendor_id, "created_at": {"$gte": utcnow() - timedelta(days=7)}})
        if same >= 2:
            flags.append("duplicate_text")
    return flags


async def _write(kind: str, key: dict, base: dict, body: ReviewIn, request: Request, user: User) -> dict:
    """Create or edit (never duplicates). Clean content publishes at once; suspicious content waits. Rating value never affects moderation."""
    await rate_limit.hit(f"review:{user.id}", 20, 3600, message="You're submitting reviews very quickly. Please wait a little and try again.")
    coll = COLL[kind]
    title, comment = mod.sanitize(body.title, 120), mod.sanitize(body.comment, 3000)
    r = await mod.rules()
    s = mod.scan(f"{title}\n{comment}", r)
    flags = sorted(set(s["flags"]) | set(await _suspicious(coll, user, comment, base["vendor_id"])))
    status = "pending_moderation" if flags else PUBLIC
    now = utcnow()
    existing = await db[coll].find_one(key)
    photos = await _photo_list(body.photo_file_ids, user, existing) if kind == "product" else []
    h = hashlib.sha256(" ".join(comment.lower().split()).encode()).hexdigest() if len(comment) >= 20 else None
    fields = {"rating": body.rating, "title": title, "comment": comment, "comment_hash": h, "status": status, "flags": flags, "updated_at": now, "photos": photos}
    if existing:
        if existing["status"] == "removed":
            raise APIError(409, "invalid_state", "This review was removed for a policy violation and can't be edited. Contact support to appeal.")
        await db[coll].update_one({"_id": existing["_id"]}, {"$set": {**fields, "edited": True, "moderation_note": None},
                                                             "$push": {"history": {"at": now, "by": ObjectId(user.id), "change": "edited", "status": status}}})
        rid, action = existing["_id"], "edited"
    else:
        doc = {**key, **base, **fields, "customer_id": ObjectId(user.id), "author_name": _display_name(user), "verified_purchase": True,
               "created_at": now, "history": [{"at": now, "by": ObjectId(user.id), "change": "created", "status": status}]}
        try:
            rid = (await db[coll].insert_one(doc)).inserted_id
        except DuplicateKeyError:
            raise APIError(409, "conflict", "You've already reviewed this. Edit your existing review instead.")
        action = "created"
    await audit(f"review.{kind}_{action}", coll, request=request, actor=user, entity_id=str(rid), status=status, flags=flags)
    if status != PUBLIC:
        await notify(user.id, "reviews", "Your review is being checked",
                     "Thanks for your review. Our team is checking it against the AfroVending review policy before it goes live. "
                     "Low ratings and honest criticism are always allowed.", "/account/reviews")
    return _own_review(await db[coll].find_one({"_id": rid}), kind)


@router.get("/orders/{order_id}/review-status")
async def order_review_status(order_id: str, user: User = Depends(get_current_user)):
    vos = await db.vendor_orders.find({"order_id": _oid(order_id), "customer_id": ObjectId(user.id)}).to_list(50)
    out = {}
    for vo in vos:
        got = await _received_item_ids(vo)
        items = await db.order_items.find({"vendor_order_id": vo["_id"]}).to_list(100)
        reviews = {r["order_item_id"]: r for r in await db.reviews.find({"vendor_order_id": vo["_id"]}).to_list(100)}
        seller = await db.seller_ratings.find_one({"vendor_order_id": vo["_id"]})
        out[str(vo["_id"])] = {"seller_eligible": vo["status"] == "delivered", "seller_rating": _own_review(seller, "seller") if seller else None,
                               "items": {str(i["_id"]): {"eligible": i["_id"] in got, "review": _own_review(reviews[i["_id"]], "product") if i["_id"] in reviews else None}
                                         for i in items}}
    return {"vendor_orders": out}


@router.put("/reviews/items/{order_item_id}")
async def review_item(order_item_id: str, body: ReviewIn, request: Request, user: User = Depends(get_current_user)):
    it = await db.order_items.find_one({"_id": _oid(order_item_id)})
    vo = await db.vendor_orders.find_one({"_id": it["vendor_order_id"], "customer_id": ObjectId(user.id)}) if it else None
    if not vo:
        raise APIError(404, "not_found", "We couldn't find that item in your orders.")
    if it["_id"] not in await _received_item_ids(vo):
        raise APIError(403, "not_eligible", "You can review this item once it has been delivered or collected.")
    product = await db.products.find_one({"_id": it["product_id"]}, {"slug": 1, "title": 1})
    base = {"product_id": it["product_id"], "product_slug": (product or {}).get("slug"), "product_title": it["title"], "vendor_id": vo["vendor_id"],
            "vendor_name": vo.get("vendor_name"), "vendor_order_id": vo["_id"], "order_id": vo["order_id"], "order_number": vo["order_number"]}
    return {"review": await _write("product", {"order_item_id": it["_id"]}, base, body, request, user)}


@router.put("/reviews/sellers/{vendor_order_id}")
async def review_seller(vendor_order_id: str, body: ReviewIn, request: Request, user: User = Depends(get_current_user)):
    vo = await db.vendor_orders.find_one({"_id": _oid(vendor_order_id), "customer_id": ObjectId(user.id)})
    if not vo:
        raise APIError(404, "not_found", "We couldn't find that order.")
    if vo["status"] != "delivered":
        raise APIError(403, "not_eligible", "You can rate this seller once this part of your order has been delivered or collected.")
    base = {"vendor_id": vo["vendor_id"], "vendor_name": vo.get("vendor_name"), "order_id": vo["order_id"], "order_number": vo["order_number"]}
    return {"review": await _write("seller", {"vendor_order_id": vo["_id"]}, base, body, request, user)}


@router.get("/reviews/mine")
async def my_reviews(user: User = Depends(get_current_user)):
    q = {"customer_id": ObjectId(user.id)}
    return {"product": [_own_review(d, "product") for d in await db.reviews.find(q).sort("updated_at", -1).to_list(200)],
            "seller": [_own_review(d, "seller") for d in await db.seller_ratings.find(q).sort("updated_at", -1).to_list(200)]}


@router.get("/products/{slug}/reviews")
async def product_reviews(slug: str):
    p = await db.products.find_one({"slug": slug.lower(), "status": "active"}, {"_id": 1})
    if not p:
        return {"summary": await _summary("reviews", {"_id": None}), "reviews": []}
    q = {"product_id": p["_id"]}
    docs = await db.reviews.find({**q, "status": PUBLIC}).sort("created_at", -1).to_list(100)
    return {"summary": await _summary("reviews", q), "reviews": [_pub_review(d, "product") for d in docs]}


@router.get("/stores/{slug}/seller-ratings")
async def seller_ratings(slug: str):
    store = await db.vendor_stores.find_one({"slug": slug.lower(), "status": "published"}, {"vendor_id": 1})
    if not store:
        return {"summary": await _summary("seller_ratings", {"_id": None}), "reviews": []}
    q = {"vendor_id": store["vendor_id"]}
    docs = await db.seller_ratings.find({**q, "status": PUBLIC}).sort("created_at", -1).to_list(100)
    return {"summary": await _summary("seller_ratings", q), "reviews": [_pub_review(d, "seller") for d in docs]}


async def vendor_summary(vendor_id) -> dict:
    """Used by the vendor dashboard: published reviews only; product and seller scores stay separate."""
    q = {"vendor_id": vendor_id}
    recent = await db.reviews.find({**q, "status": PUBLIC}).sort("created_at", -1).to_list(5)
    return {**await _summary("reviews", q), "seller": await _summary("seller_ratings", q), "available": True,
            "recent": [_pub_review(d, "product") for d in recent]}


async def _vendor(user: User) -> dict:
    from afrovending.api.v1.vendors import my_vendor
    return await my_vendor(user)


@router.get("/vendor/reviews")
async def vendor_reviews(user: User = Depends(get_current_user)):
    v = await _vendor(user)
    q = {"vendor_id": v["_id"], "status": PUBLIC}

    def row(d, kind):
        resp = d.get("response")
        return {**_pub_review(d, kind), "my_response": {"body": resp["body"], "status": resp["status"]} if resp else None}
    return {"product": [row(d, "product") for d in await db.reviews.find(q).sort("created_at", -1).to_list(300)],
            "seller": [row(d, "seller") for d in await db.seller_ratings.find(q).sort("created_at", -1).to_list(300)],
            "summary": await vendor_summary(v["_id"])}


@router.put("/vendor/reviews/{kind}/{review_id}/response")
async def vendor_respond(kind: Kind, review_id: str, body: ResponseIn, request: Request, user: User = Depends(get_current_user)):
    v = await _vendor(user)
    coll = COLL[kind]
    d = await db[coll].find_one({"_id": _oid(review_id), "vendor_id": v["_id"], "status": PUBLIC})
    if not d:
        raise APIError(404, "not_found", "Review not found.")
    if (d.get("response") or {}).get("status") == "removed":
        raise APIError(409, "invalid_state", "Your response was removed for a policy violation and can't be edited.")
    await rate_limit.hit(f"review-response:{user.id}", 30, 3600)
    text = mod.sanitize(body.body, 2000)
    s = mod.scan(text, await mod.rules())
    status = "pending_moderation" if s["flags"] else PUBLIC
    now = utcnow()
    first = not d.get("response")
    resp = {"body": text, "status": status, "flags": s["flags"], "author_id": ObjectId(user.id), "created_at": (d.get("response") or {}).get("created_at", now), "updated_at": now}
    await db[coll].update_one({"_id": d["_id"]}, {"$set": {"response": resp},
                                                  "$push": {"history": {"at": now, "by": ObjectId(user.id), "change": "vendor response " + ("created" if first else "edited"), "status": status}}})
    await audit(f"review.response_{'created' if first else 'edited'}", coll, request=request, actor=user, entity_id=review_id, status=status, flags=s["flags"])
    if status == PUBLIC:
        await _response_published(d)
    return {"response": {"body": text, "status": status, "flags": s["flags"]}}


async def _response_published(d: dict) -> None:
    await notify(d["customer_id"], "reviews", f"{d.get('vendor_name') or 'The seller'} responded to your review",
                 "The seller posted a public response to your review. Open your reviews to read it.", "/account/reviews")


@router.post("/reviews/{kind}/{review_id}/report", status_code=201)
async def report(kind: Kind, review_id: str, body: ReportIn, request: Request, user: User = Depends(get_current_user)):
    d = await db[COLL[kind]].find_one({"_id": _oid(review_id), "status": PUBLIC})
    if not d or (body.part == "response" and (d.get("response") or {}).get("status") != PUBLIC):
        raise APIError(404, "not_found", "Review not found.")
    await rate_limit.hit(f"review-report:{user.id}", 15, 3600)
    try:
        await db.review_reports.insert_one({"target_kind": kind, "target_id": d["_id"], "part": body.part, "reporter_id": ObjectId(user.id),
                                            "reporter_role": "vendor" if "vendor" in user.roles else "customer", "reason": body.reason,
                                            "details": mod.sanitize(body.details, 500), "status": "open", "created_at": utcnow()})
    except DuplicateKeyError:
        raise APIError(409, "conflict", "You've already reported this.")
    await audit("review.reported", COLL[kind], request=request, actor=user, entity_id=review_id, reason=body.reason, part=body.part)
    return {"ok": True}


def _admin_row(d: dict, kind: str, reports: list) -> dict:
    resp = d.get("response")
    return {**_pub_review(d, kind), "status": d["status"], "flags": d.get("flags", []), "order_number": d.get("order_number"), "photos": _photos(d, True),
            "moderation_note": d.get("moderation_note"), "history": [{**h, "by": str(h["by"]) if h.get("by") else None} for h in d.get("history", [])],
            "response": {"body": resp["body"], "status": resp["status"], "flags": resp.get("flags", [])} if resp else None,
            "reports": [{"part": r["part"], "reason": r["reason"], "details": r["details"], "reporter_role": r["reporter_role"], "status": r["status"],
                         "created_at": r["created_at"]} for r in reports]}


@router.get("/admin/reviews")
async def admin_reviews(kind: Kind = "product", status: Optional[Literal["published", "pending_moderation", "rejected", "removed"]] = None,
                        queue: Literal["all", "needs_action"] = "needs_action", _: User = Depends(require_perm(REVIEWS_MOD))):
    coll = COLL[kind]
    reported = await db.review_reports.distinct("target_id", {"target_kind": kind, "status": "open"})
    if queue == "needs_action" and not status:
        q = {"$or": [{"status": "pending_moderation"}, {"response.status": "pending_moderation"}, {"photos.status": "pending"}, {"_id": {"$in": reported}}]}
    else:
        q = {"status": status} if status else {}
    docs = await db[coll].find(q).sort("updated_at", -1).to_list(300)
    reps = await db.review_reports.find({"target_kind": kind, "target_id": {"$in": [d["_id"] for d in docs]}}).to_list(1000)
    return {"data": [_admin_row(d, kind, [r for r in reps if r["target_id"] == d["_id"]]) for d in docs]}


@router.get("/admin/reviews/summary")
async def admin_summary(_: User = Depends(require_perm(REVIEWS_MOD))):
    async def counts(coll):
        return {s: await db[coll].count_documents({"status": s}) for s in ("published", "pending_moderation", "rejected", "removed")}
    return {"product": {**await _summary("reviews", {}), "by_status": await counts("reviews")},
            "seller": {**await _summary("seller_ratings", {}), "by_status": await counts("seller_ratings")},
            "pending_responses": await db.reviews.count_documents({"response.status": "pending_moderation"}) + await db.seller_ratings.count_documents({"response.status": "pending_moderation"}),
            "open_reports": await db.review_reports.count_documents({"status": "open"}),
            "flagged_messages": await db.order_messages.count_documents({"review_status": "open"})}


@router.post("/admin/reviews/{kind}/{review_id}/decision")
async def decide(kind: Kind, review_id: str, body: DecisionIn, request: Request, admin: User = Depends(require_perm(REVIEWS_MOD))):
    coll = COLL[kind]
    d = await db[coll].find_one({"_id": _oid(review_id)})
    if not d or (body.part == "response" and not d.get("response")):
        raise APIError(404, "not_found", "Review not found.")
    new = {"approve": PUBLIC, "reject": "rejected", "remove": "removed"}[body.action]
    reason, now = mod.sanitize(body.reason, 500), utcnow()
    field = "status" if body.part == "review" else "response.status"
    sets = {field: new, "updated_at": now}
    if body.part == "review":
        sets["moderation_note"] = reason if new != PUBLIC else None
    await db[coll].update_one({"_id": d["_id"]}, {"$set": sets, "$push": {"history": {"at": now, "by": ObjectId(admin.id), "change": f"{body.part} {body.action}",
                                                                                       "status": new, "reason": reason}}})
    await db.review_reports.update_many({"target_id": d["_id"], "part": body.part, "status": "open"},
                                        {"$set": {"status": "resolved", "resolution": body.action, "resolved_by": ObjectId(admin.id), "resolved_at": now}})
    await audit(f"review.moderated_{body.action}", coll, request=request, actor=admin, entity_id=review_id, part=body.part, reason=reason)
    if body.part == "review" and new in ("rejected", "removed"):
        await notify(d["customer_id"], "reviews", "Update on your review",
                     f"Your review couldn't be published under the AfroVending review policy. Reason: {reason}. "
                     + ("You can edit it and resubmit, or reply via Help & support to appeal." if new == "rejected" else "To appeal, open a ticket in Help & support."),
                     "/account/reviews")
    elif body.part == "review" and new == PUBLIC and d["status"] == "pending_moderation":
        await notify(d["customer_id"], "reviews", "Your review is live", "Thanks — your review passed our checks and is now published.", "/account/reviews")
    elif body.part == "response" and new == PUBLIC and d["response"]["status"] != PUBLIC:
        await _response_published(d)
    elif body.part == "response" and new in ("rejected", "removed"):
        v = await db.vendors.find_one({"_id": d["vendor_id"]})
        if v:
            await notify(v["owner_user_id"], "reviews", "Update on your review response",
                         f"Your public response couldn't be shown under the AfroVending review policy. Reason: {reason}. "
                         + ("You can edit it and resubmit." if new == "rejected" else "To appeal, contact AfroVending support."), "/vendor/reviews")
    return {"ok": True, "status": new}


class PhotoDecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=3, max_length=300)


@router.post("/admin/reviews/product/{review_id}/photos/{file_id}")
async def decide_photo(review_id: str, file_id: str, body: PhotoDecisionIn, request: Request, admin: User = Depends(require_perm(REVIEWS_MOD))):
    st = "approved" if body.action == "approve" else "rejected"
    res = await db.reviews.update_one({"_id": _oid(review_id), "photos.file_id": _oid(file_id)},
                                      {"$set": {"photos.$.status": st, "photos.$.decided_at": utcnow(), "photos.$.decided_by": ObjectId(admin.id)}})
    if not res.matched_count:
        raise APIError(404, "not_found", "Photo not found.")
    await audit(f"review.photo_{st}", "reviews", request=request, actor=admin, entity_id=review_id, file_id=file_id, reason=mod.sanitize(body.reason, 300))
    if st == "rejected":
        d = await db.reviews.find_one({"_id": _oid(review_id)})
        await notify(d["customer_id"], "reviews", "A review photo wasn't approved", f"One of your review photos couldn't be shown. Reason: {body.reason[:200]}.", "/account/reviews")
    return {"ok": True, "status": st}


@router.get("/reviews/photos/{file_id}")
async def review_photo(file_id: str):
    """Only photos an admin approved, on a published review, are served publicly."""
    from afrovending.api.v1.files import stream_private
    fid = _oid(file_id)
    if not await db.reviews.find_one({"status": PUBLIC, "photos": {"$elemMatch": {"file_id": fid, "status": "approved"}}}, {"_id": 1}):
        raise APIError(404, "not_found", "Photo not found.")
    doc = await db.files.find_one({"_id": fid, "is_deleted": False})
    if not doc:
        raise APIError(404, "not_found", "Photo not found.")
    r = await stream_private(doc)
    r.headers["Content-Disposition"] = "inline"
    r.headers["Cache-Control"] = "public, max-age=3600"
    return r


@router.get("/admin/reviews/photos/{file_id}")
async def admin_review_photo(file_id: str, _: User = Depends(require_perm(REVIEWS_MOD))):
    from afrovending.api.v1.files import stream_private
    doc = await db.files.find_one({"_id": _oid(file_id), "purpose": "review_photo", "is_deleted": False})
    if not doc:
        raise APIError(404, "not_found", "Photo not found.")
    r = await stream_private(doc)
    r.headers["Content-Disposition"] = "inline"
    return r


@router.get("/admin/moderation/rules")
async def get_rules(_: User = Depends(require_perm(MOD_RULES))):
    return await mod.rules()


@router.put("/admin/moderation/rules")
async def put_rules(body: RulesIn, request: Request, admin: User = Depends(require_perm(MOD_RULES))):
    clean = {k: sorted({mod.sanitize(x, 80).lower() for x in v if x.strip()}) for k, v in body.model_dump().items()}
    if "afrovending.com" not in clean["approved_domains"]:
        clean["approved_domains"].append("afrovending.com")
    saved = await mod.save_rules(clean, ObjectId(admin.id))
    await audit("moderation.rules_updated", "platform_settings", request=request, actor=admin, entity_id=mod.RULES_KEY)
    return saved
