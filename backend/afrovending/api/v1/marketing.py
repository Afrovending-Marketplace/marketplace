"""Phase 12 marketing & monetization APIs: analytics, consent/unsubscribe, wishlists, referrals, campaigns, vendor coupons,
subscription framework and sponsored-listing infrastructure (paid features locked off)."""
import os
from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError

from afrovending.core import ledger, rate_limit, reports
from afrovending.core import marketing as mk
from afrovending.core.audit import audit
from afrovending.core.config import settings
from afrovending.core.db import db
from afrovending.core.deps import get_current_user, get_optional_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.permissions import ANALYTICS, CONTENT, FIN_VIEW, SETTINGS, require_perm
from afrovending.core.security import client_ip

router = APIRouter(tags=["marketing"])
PLAN_FEATURES = {"starter": ["Up to 50 live products", "Standard storefront", "Order messaging"],
                 "growth": ["Up to 500 live products", "Store coupons", "Sales analytics"],
                 "premium": ["Unlimited products", "Store coupons", "Sales analytics", "Priority support"]}


def _oid(v: str) -> ObjectId:
    if not ObjectId.is_valid(v):
        raise APIError(404, "not_found", "Not found.")
    return ObjectId(v)


def _iso(d):
    return d.isoformat() if isinstance(d, datetime) else d


# ---------- public config, analytics ingest, consent ----------
@router.get("/marketing/config")
async def public_config():
    f = await mk.flags()
    ga = os.environ.get("GA4_MEASUREMENT_ID", "").strip()
    return {"ga4_measurement_id": ga if ga and f.get("ga4_enabled") else None, "privacy_url": "/privacy",
            "sponsored_listings_enabled": False, "referral_rewards_enabled": False}


class EventIn(BaseModel):
    type: Literal["page_view", "product_view", "search", "add_to_cart", "begin_checkout", "referral_visit"]
    event_id: str = Field(min_length=8, max_length=100)
    path: str = Field(default="", max_length=300)
    product_slug: str = Field(default="", max_length=200)
    query: str = Field(default="", max_length=120)
    referral_code: str = Field(default="", max_length=20)


class EventsIn(BaseModel):
    anon_id: str = Field(min_length=8, max_length=64)
    events: list[EventIn] = Field(min_length=1, max_length=20)


@router.post("/analytics/events", status_code=202)
async def ingest(body: EventsIn, request: Request, user: Optional[User] = Depends(get_optional_user)):
    """Only sent by the browser after the visitor accepts analytics cookies. Purchases are recorded server-side only."""
    await rate_limit.hit(f"analytics:{client_ip(request)}", 300, 600)
    stored = 0
    for e in body.events:
        pid = vid = None
        if e.product_slug:
            p = await db.products.find_one({"slug": e.product_slug.lower()}, {"vendor_id": 1})
            pid, vid = (p["_id"], p["vendor_id"]) if p else (None, None)
        code = e.referral_code.strip().upper() if e.type == "referral_visit" else ""
        if e.type == "referral_visit" and not await db.users.find_one({"referral_code": code}, {"_id": 1}):
            continue
        eid = f"{e.type}:{body.anon_id}:{code}:{utcnow():%Y%m%d}" if code else f"{e.type}:{e.event_id}"
        stored += await mk.track(e.type, eid, anon_id=body.anon_id, user_id=ObjectId(user.id) if user else None, path=e.path,
                                 product_id=pid, vendor_id=vid, query=e.query.strip().lower(), referral_code=code)
    return {"stored": stored}


class ConsentIn(BaseModel):
    marketing_opt_in: bool
    wishlist_price_drop: Optional[bool] = None
    wishlist_back_in_stock: Optional[bool] = None


@router.get("/account/marketing")
async def my_consent(user: User = Depends(get_current_user)):
    u = await db.users.find_one({"_id": ObjectId(user.id)})
    wa = u.get("wishlist_alerts") or {}
    return {"marketing_opt_in": bool(u.get("marketing_opt_in")), "consent_at": _iso(u.get("marketing_consent_at")),
            "withdrawn_at": _iso(u.get("marketing_withdrawn_at")), "wishlist_price_drop": wa.get("price_drop", True), "wishlist_back_in_stock": wa.get("back_in_stock", True)}


@router.put("/account/marketing")
async def put_consent(body: ConsentIn, request: Request, user: User = Depends(get_current_user)):
    await mk.set_consent(ObjectId(user.id), body.marketing_opt_in, "account_settings")
    for k, f in (("wishlist_price_drop", "price_drop"), ("wishlist_back_in_stock", "back_in_stock")):
        if getattr(body, k) is not None:
            await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {f"wishlist_alerts.{f}": getattr(body, k)}})
    await audit("marketing.consent_" + ("given" if body.marketing_opt_in else "withdrawn"), "users", request=request, actor=user, entity_id=user.id)
    return {"marketing_opt_in": body.marketing_opt_in}


class UnsubIn(BaseModel):
    token: str = Field(min_length=10, max_length=120)


@router.post("/marketing/unsubscribe")
async def unsubscribe(body: UnsubIn, request: Request):
    await rate_limit.hit(f"unsub:{client_ip(request)}", 30, 600)
    uid = mk.verify_unsubscribe(body.token)
    if not uid:
        raise APIError(422, "invalid_token", "This unsubscribe link isn't valid.")
    await mk.set_consent(uid, False, "unsubscribe_link")
    await audit("marketing.unsubscribed", "users", request=request, entity_id=str(uid))
    return {"ok": True}


@router.post("/marketing/cart-click")
async def cart_click(body: UnsubIn):
    await db.cart_reminders.update_one({"token": body.token, "clicked_at": None}, {"$set": {"clicked_at": utcnow()}})
    return {"ok": True}


# ---------- wishlists ----------
@router.get("/wishlist")
async def wishlist(user: User = Depends(get_current_user)):
    from afrovending.core.catalog import public_products
    rows = await db.wishlists.find({"user_id": ObjectId(user.id)}).sort("created_at", -1).to_list(300)
    docs = await db.products.find({"_id": {"$in": [r["product_id"] for r in rows]}, "status": "active"}).to_list(300)
    order = {r["product_id"]: i for i, r in enumerate(rows)}
    docs.sort(key=lambda d: order[d["_id"]])
    return {"data": await public_products(docs) if docs else [], "slugs": [d["slug"] for d in docs]}


@router.put("/wishlist/{slug}")
async def wish_add(slug: str, user: User = Depends(get_current_user)):
    p = await db.products.find_one({"slug": slug.lower(), "status": "active"}, {"_id": 1})
    if not p:
        raise APIError(404, "not_found", "Product not found.")
    await rate_limit.hit(f"wish:{user.id}", 120, 3600)
    if await db.wishlists.count_documents({"user_id": ObjectId(user.id)}) >= 300:
        raise APIError(409, "limit", "Your wishlist is full (300 items).")
    await db.wishlists.update_one({"user_id": ObjectId(user.id), "product_id": p["_id"]}, {"$setOnInsert": {"created_at": utcnow(), **await _ref(p["_id"])}}, upsert=True)
    return {"ok": True}


async def _ref(pid) -> dict:
    from afrovending.core.catalog import public_products
    from afrovending.core.wishlist_alerts import snapshot
    pub = await public_products([await db.products.find_one({"_id": pid})])
    price, stock = snapshot(pub[0]) if pub else (None, None)
    return {"ref_price_minor": price, "ref_in_stock": stock}


@router.delete("/wishlist/{slug}")
async def wish_remove(slug: str, user: User = Depends(get_current_user)):
    p = await db.products.find_one({"slug": slug.lower()}, {"_id": 1})
    if p:
        await db.wishlists.delete_one({"user_id": ObjectId(user.id), "product_id": p["_id"]})
    return {"ok": True}


# ---------- referrals ----------
@router.get("/referrals/me")
async def my_referrals(user: User = Depends(get_current_user)):
    uid = ObjectId(user.id)
    code = await mk.ensure_code(uid)
    rows = await db.referrals.find({"referrer_id": uid}).sort("signed_up_at", -1).to_list(500)
    return {"code": code, "link": f"{settings.frontend_url}/?ref={code}", "rewards_enabled": False,
            "visits": await db.analytics_events.count_documents({"type": "referral_visit", "referral_code": code}),
            "signups": len(rows), "first_orders": sum(r["status"] == "converted" for r in rows),
            "activity": [{"label": f"Friend {len(rows) - i}", "status": r["status"], "signed_up_at": _iso(r["signed_up_at"]),
                          "converted_at": _iso(r.get("converted_at"))} for i, r in enumerate(rows)]}


# ---------- campaigns ----------
class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    headline: str = Field(min_length=2, max_length=120)
    subtext: str = Field(default="", max_length=240)
    cta_label: str = Field(default="Shop now", max_length=30)
    cta_url: str = Field(default="/shop", max_length=300, pattern=r"^(/|/[^/\\\s][^\s]*|https://[^\s]+)$")
    coupon_code: str = Field(default="", max_length=30)
    product_slugs: list[str] = Field(default_factory=list, max_length=12)
    placement: Literal["homepage_hero", "homepage_strip"] = "homepage_strip"
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    status: Literal["draft", "active", "paused"] = "draft"

    @field_validator("coupon_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


def _camp(d: dict) -> dict:
    return {"id": str(d["_id"]), **{k: _iso(d.get(k)) for k in ("name", "headline", "subtext", "cta_label", "cta_url", "coupon_code", "product_slugs",
                                                             "placement", "starts_at", "ends_at", "status")}}


@router.get("/campaigns/active")
async def active_campaigns():
    now = utcnow()
    q = {"status": "active", "$and": [{"$or": [{"starts_at": None}, {"starts_at": {"$lte": now}}]}, {"$or": [{"ends_at": None}, {"ends_at": {"$gt": now}}]}]}
    return {"data": [_camp(d) for d in await db.campaigns.find(q).sort("starts_at", -1).to_list(10)]}


@router.get("/admin/campaigns")
async def list_campaigns(_: User = Depends(require_perm(CONTENT))):
    return {"data": [_camp(d) for d in await db.campaigns.find({}).sort("created_at", -1).to_list(200)]}


async def _check_campaign(b: CampaignIn) -> dict:
    if b.starts_at and b.ends_at and b.starts_at >= b.ends_at:
        raise APIError(422, "validation_error", "End date must be after start date.")
    if b.coupon_code and not await db.coupons.find_one({"code": b.coupon_code, "funded_by": "marketplace", "status": "active"}):
        raise APIError(422, "validation_error", "Link an active marketplace coupon.")
    return b.model_dump()


@router.post("/admin/campaigns", status_code=201)
async def create_campaign(body: CampaignIn, request: Request, admin: User = Depends(require_perm(CONTENT))):
    doc = {**await _check_campaign(body), "created_at": utcnow(), "created_by": ObjectId(admin.id)}
    doc["_id"] = (await db.campaigns.insert_one(doc)).inserted_id
    await audit("content.campaign_created", "campaigns", request=request, actor=admin, entity_id=str(doc["_id"]))
    return _camp(doc)


@router.put("/admin/campaigns/{cid}")
async def update_campaign(cid: str, body: CampaignIn, request: Request, admin: User = Depends(require_perm(CONTENT))):
    res = await db.campaigns.update_one({"_id": _oid(cid)}, {"$set": {**await _check_campaign(body), "updated_at": utcnow()}})
    if not res.matched_count:
        raise APIError(404, "not_found", "Campaign not found.")
    await audit("content.campaign_updated", "campaigns", request=request, actor=admin, entity_id=cid, status=body.status)
    return _camp(await db.campaigns.find_one({"_id": _oid(cid)}))


# ---------- vendor coupons (vendor-funded) ----------
class VendorCouponIn(BaseModel):
    code: str = Field(min_length=3, max_length=30)
    type: Literal["percent", "fixed"]
    value: int = Field(ge=1, le=100_000_000)
    min_subtotal_minor: int = Field(default=0, ge=0)
    max_redemptions: Optional[int] = Field(default=None, ge=1)
    max_discount_minor: Optional[int] = Field(default=None, ge=1)
    per_customer_limit: Optional[int] = Field(default=None, ge=1, le=100)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    status: Literal["draft", "active", "paused"] = "active"

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.replace("-", "").isalnum():
            raise ValueError("Use letters, numbers and dashes only.")
        return v


async def _vendor(user: User) -> dict:
    from afrovending.api.v1.vendors import my_vendor
    return await my_vendor(user)


def _coupon_out(c: dict) -> dict:
    return {"id": str(c["_id"]), **{k: _iso(c.get(k)) for k in ("code", "type", "value", "min_subtotal_minor", "max_redemptions", "max_discount_minor",
                                                              "per_customer_limit", "starts_at", "ends_at", "status", "funded_by")},
            "redemptions": c.get("redemptions", 0), "spent_minor": c.get("spent_minor", 0)}


def _validate_coupon(b) -> None:
    if b.type == "percent" and b.value > 10_000:
        raise APIError(422, "validation_error", "Percent coupons are in basis points (max 10000 = 100%).")
    if b.starts_at and b.ends_at and b.starts_at >= b.ends_at:
        raise APIError(422, "validation_error", "End date must be after start date.")


@router.get("/vendor/coupons")
async def vendor_coupons(user: User = Depends(get_current_user)):
    v = await _vendor(user)
    return {"data": [_coupon_out(c) for c in await db.coupons.find({"vendor_id": v["_id"], "funded_by": "vendor"}).sort("created_at", -1).to_list(200)]}


@router.post("/vendor/coupons", status_code=201)
async def vendor_coupon_create(body: VendorCouponIn, request: Request, user: User = Depends(get_current_user)):
    v = await _vendor(user)
    _validate_coupon(body)
    await rate_limit.hit(f"vcoupon:{v['_id']}", 30, 86400)
    doc = {**body.model_dump(), "vendor_id": v["_id"], "funded_by": "vendor", "first_order_only": False, "budget_minor": None,
           "redemptions": 0, "spent_minor": 0, "created_at": utcnow(), "updated_at": utcnow(), "created_by": ObjectId(user.id)}
    try:
        doc["_id"] = (await db.coupons.insert_one(doc)).inserted_id
    except DuplicateKeyError:
        raise APIError(409, "conflict", "That coupon code is already taken.")
    await audit("coupon.created", "coupons", request=request, actor=user, entity_id=str(doc["_id"]), funded_by="vendor")
    return _coupon_out(doc)


@router.put("/vendor/coupons/{coupon_id}")
async def vendor_coupon_update(coupon_id: str, body: VendorCouponIn, request: Request, user: User = Depends(get_current_user)):
    v = await _vendor(user)
    _validate_coupon(body)
    c = await db.coupons.find_one({"_id": _oid(coupon_id), "vendor_id": v["_id"], "funded_by": "vendor"})
    if not c:
        raise APIError(404, "not_found", "Coupon not found.")
    if body.code != c["code"] and c.get("redemptions"):
        raise APIError(409, "conflict", "A coupon that has been used can't change its code.")
    try:
        await db.coupons.update_one({"_id": c["_id"]}, {"$set": {**body.model_dump(), "updated_at": utcnow()}})
    except DuplicateKeyError:
        raise APIError(409, "conflict", "That coupon code is already taken.")
    await audit("coupon.updated" if body.status != "paused" else "coupon.paused", "coupons", request=request, actor=user, entity_id=coupon_id)
    return _coupon_out(await db.coupons.find_one({"_id": c["_id"]}))


@router.get("/admin/coupons/report")
async def coupon_report(_: User = Depends(require_perm(FIN_VIEW))):
    rows = await db.coupon_redemptions.aggregate([{"$group": {"_id": "$coupon_id", "code": {"$first": "$code"}, "orders": {"$sum": 1},
                                                              "platform_funded_minor": {"$sum": "$platform_funded_minor"},
                                                              "vendor_funded_minor": {"$sum": "$vendor_funded_minor"}}}]).to_list(500)
    promo = await db.commission_ledger.aggregate([{"$match": {"type": {"$in": ["promo_expense", "promo_expense_reversal"]}}},
                                               {"$group": {"_id": "$type", "total": {"$sum": "$amount_minor"}}}]).to_list(5)
    return {"coupons": [{**{k: v for k, v in r.items() if k != "_id"}, "coupon_id": str(r["_id"])} for r in rows],
            "promotional_expense_minor": -sum(p["total"] for p in promo)}


# ---------- subscriptions (framework; paid billing locked) ----------
@router.get("/plans")
async def plans():
    f = await mk.flags()
    return {"paid_billing_enabled": f["paid_subscriptions_enabled"],
            "plans": [{"key": k, **v, "features": PLAN_FEATURES[k]} for k, v in ledger.PLANS.items()]}


class PlanRequestIn(BaseModel):
    plan: Literal["starter", "growth", "premium"]


@router.get("/vendor/subscription")
async def vendor_subscription(user: User = Depends(get_current_user)):
    v = await _vendor(user)
    req = await db.subscription_requests.find_one({"vendor_id": v["_id"], "status": "pending_billing_approval"})
    return {"plan": v.get("plan") or "starter", "features": PLAN_FEATURES[v.get("plan") or "starter"], "paid_billing_enabled": False,
            "pending_request": {"plan": req["plan"], "requested_at": _iso(req["created_at"])} if req else None}


@router.post("/vendor/subscription/request", status_code=201)
async def request_plan(body: PlanRequestIn, request: Request, user: User = Depends(get_current_user)):
    """Paid plans can't be bought yet: the request is recorded for the owner, nothing is charged and the plan doesn't change."""
    v = await _vendor(user)
    if body.plan == (v.get("plan") or "starter"):
        raise APIError(409, "conflict", "You're already on this plan.")
    await db.subscription_requests.update_one({"vendor_id": v["_id"], "status": "pending_billing_approval"},
                                              {"$set": {"plan": body.plan, "requested_by": ObjectId(user.id), "created_at": utcnow()}}, upsert=True)
    await audit("vendor.plan_requested", "subscription_requests", request=request, actor=user, entity_id=str(v["_id"]), plan=body.plan)
    return {"status": "pending_billing_approval", "message": "Paid plans aren't available to buy yet. We've noted your interest and nothing has been charged."}


# ---------- sponsored listings (infrastructure; disabled) ----------
class SponsoredIn(BaseModel):
    product_slug: str = Field(min_length=1, max_length=200)
    placement: Literal["search", "category", "homepage"] = "search"
    keywords: list[str] = Field(default_factory=list, max_length=20)
    status: Literal["inactive", "active"] = "inactive"


@router.get("/sponsored")
async def sponsored(q: str = Query(default="", max_length=120), placement: str = "search"):
    """Kept separate from organic results and always labelled 'Sponsored'. Returns nothing while the feature is locked off."""
    f = await mk.flags()
    return {"enabled": f["sponsored_listings_enabled"], "label": "Sponsored", "items": []}


@router.get("/admin/sponsored")
async def list_sponsored(_: User = Depends(require_perm(SETTINGS))):
    docs = await db.sponsored_listings.find({}).sort("created_at", -1).to_list(200)
    return {"enabled": False, "data": [{"id": str(d["_id"]), "product_slug": d["product_slug"], "placement": d["placement"], "status": d["status"]} for d in docs]}


@router.post("/admin/sponsored", status_code=201)
async def create_sponsored(body: SponsoredIn, request: Request, admin: User = Depends(require_perm(SETTINGS))):
    if body.status == "active" or not (await mk.flags())["sponsored_listings_enabled"] and body.status != "inactive":
        raise APIError(409, "feature_locked", "Sponsored listings stay switched off until pricing and billing rules are approved.")
    p = await db.products.find_one({"slug": body.product_slug.lower()}, {"_id": 1, "vendor_id": 1})
    if not p:
        raise APIError(422, "validation_error", "Unknown product.")
    doc = {**body.model_dump(), "product_id": p["_id"], "vendor_id": p["vendor_id"], "created_at": utcnow(), "created_by": ObjectId(admin.id)}
    doc["_id"] = (await db.sponsored_listings.insert_one(doc)).inserted_id
    await audit("marketing.sponsored_created", "sponsored_listings", request=request, actor=admin, entity_id=str(doc["_id"]))
    return {"id": str(doc["_id"]), "status": "inactive"}


# ---------- flags ----------
class FlagsIn(BaseModel):
    abandoned_cart_enabled: bool
    first_delay_min: int = Field(ge=15, le=1440)
    second_delay_min: int = Field(ge=60, le=10080)
    max_per_7_days: int = Field(ge=1, le=4)
    ga4_enabled: bool = False
    analytics_retention_days: int = Field(default=400, ge=30, le=730)
    paid_subscriptions_enabled: bool = False
    sponsored_listings_enabled: bool = False
    referral_rewards_enabled: bool = False
    wishlist_alerts_enabled: bool = False
    wishlist_threshold_bps: int = Field(default=500, ge=100, le=9000)
    wishlist_max_items: int = Field(default=10, ge=1, le=30)


@router.get("/admin/marketing/flags")
async def get_flags(_: User = Depends(require_perm(SETTINGS))):
    return {**await mk.flags(), "ga4_configured": bool(os.environ.get("GA4_MEASUREMENT_ID", "").strip()), "locked": list(mk.LOCKED_OFF)}


@router.put("/admin/marketing/flags")
async def put_flags(body: FlagsIn, request: Request, admin: User = Depends(require_perm(SETTINGS))):
    if body.paid_subscriptions_enabled or body.sponsored_listings_enabled or body.referral_rewards_enabled:
        raise APIError(409, "feature_locked", "Paid subscriptions, sponsored listings and referral rewards stay off until the owner approves pricing and billing rules.")
    if body.second_delay_min <= body.first_delay_min:
        raise APIError(422, "validation_error", "The second reminder must come after the first.")
    cur = await mk.flags()
    value = {**{k: cur[k] for k in ("referral_rewards",)}, "ga4_enabled": body.ga4_enabled, "analytics_retention_days": body.analytics_retention_days,
             "abandoned_cart": {"enabled": body.abandoned_cart_enabled, "first_delay_min": body.first_delay_min, "second_delay_min": body.second_delay_min,
                                "max_per_7_days": body.max_per_7_days},
             "wishlist_alerts": {"enabled": body.wishlist_alerts_enabled, "threshold_bps": body.wishlist_threshold_bps, "max_items": body.wishlist_max_items,
                                 "send_hour_et": 9}}
    out = await mk.save_flags(value, ObjectId(admin.id))
    await audit("marketing.flags_updated", "platform_settings", request=request, actor=admin, entity_id=mk.FLAGS_KEY, abandoned_cart=body.abandoned_cart_enabled)
    return out


# ---------- reporting ----------
async def _counts(match: dict) -> dict:
    rows = await db.analytics_events.aggregate([{"$match": match}, {"$group": {"_id": "$type", "n": {"$sum": 1}}}]).to_list(20)
    return {r["_id"]: r["n"] for r in rows}


@router.get("/admin/analytics")
async def admin_analytics(frm: Optional[str] = Query(default=None, alias="from"), to: Optional[str] = None, _: User = Depends(require_perm(ANALYTICS))):
    s, e = reports.parse_range(frm, to)
    lo, hi = reports.et_bounds(s, e)
    m = {"created_at": {"$gte": lo, "$lt": hi}}
    c = await _counts(m)
    visitors = len(await db.analytics_events.distinct("anon_id", {**m, "type": "page_view"}))
    paid = await db.payments.find({"status": "succeeded", "paid_at": {"$gte": lo, "$lt": hi}}, {"amount_minor": 1, "order_id": 1}).to_list(20000)
    top = await db.analytics_events.aggregate([{"$match": {**m, "type": "product_view", "product_id": {"$ne": None}}}, {"$group": {"_id": "$product_id", "n": {"$sum": 1}}},
                                              {"$sort": {"n": -1}}, {"$limit": 10}]).to_list(10)
    titles = {p["_id"]: p for p in await db.products.find({"_id": {"$in": [t["_id"] for t in top]}}, {"title": 1, "slug": 1}).to_list(10)}
    searches = await db.analytics_events.aggregate([{"$match": {**m, "type": "search", "query": {"$ne": ""}}}, {"$group": {"_id": "$query", "n": {"$sum": 1}}},
                                                   {"$sort": {"n": -1}}, {"$limit": 10}]).to_list(10)
    refs = await db.referrals.find({"converted_at": {"$gte": lo, "$lt": hi}}).to_list(5000)
    begin = c.get("begin_checkout", 0)
    return {"range": {"from": s.isoformat(), "to": e.isoformat(), "timezone": "America/New_York (US Eastern Time)"},
            "events": {k: c.get(k, 0) for k in mk.CLIENT_EVENTS}, "visitors": visitors,
            "purchases": len(paid), "revenue_minor": sum(p["amount_minor"] for p in paid),
            "checkout_conversion": round(len(paid) / begin, 4) if begin else None,
            "visitor_conversion": round(len(paid) / visitors, 4) if visitors else None,
            "top_products": [{"title": titles.get(t["_id"], {}).get("title"), "slug": titles.get(t["_id"], {}).get("slug"), "views": t["n"]} for t in top],
            "top_searches": [{"query": t["_id"], "count": t["n"]} for t in searches],
            "referral_sales_minor": sum(r["first_order_value_minor"] for r in refs), "referral_first_orders": len(refs),
            "source_note": "Purchases and revenue come from confirmed payments; other events only from visitors who accepted analytics cookies."}


@router.get("/admin/referrals")
async def admin_referrals(_: User = Depends(require_perm(ANALYTICS))):
    signups = await db.referrals.count_documents({})
    conv = await db.referrals.find({"status": "converted"}, {"first_order_value_minor": 1}).to_list(20000)
    visits = await db.analytics_events.count_documents({"type": "referral_visit"})
    return {"visits": visits, "signups": signups, "first_orders": len(conv), "sales_minor": sum(r["first_order_value_minor"] for r in conv),
            "visit_to_signup": round(signups / visits, 4) if visits else None, "signup_to_order": round(len(conv) / signups, 4) if signups else None,
            "rewards_enabled": False}


@router.get("/admin/cart-reminders/stats")
async def reminder_stats(_: User = Depends(require_perm(ANALYTICS))):
    sent = await db.cart_reminders.find({"status": "sent"}, {"cart_id": 1, "clicked_at": 1}).to_list(20000)
    carts = {c["_id"] for c in await db.carts.find({"_id": {"$in": [s["cart_id"] for s in sent]}, "status": "converted"}, {"_id": 1}).to_list(20000)}
    return {"enabled": (await mk.flags())["abandoned_cart"]["enabled"], "sent": len(sent), "clicked": sum(1 for s in sent if s.get("clicked_at")),
            "recovered_carts": len(carts), "cancelled": await db.cart_reminders.count_documents({"status": "cancelled"}),
            "failed": await db.cart_reminders.count_documents({"status": "failed"})}


@router.get("/vendor/analytics")
async def vendor_analytics(frm: Optional[str] = Query(default=None, alias="from"), to: Optional[str] = None, user: User = Depends(get_current_user)):
    v = await _vendor(user)
    s, e = reports.parse_range(frm, to)
    lo, hi = reports.et_bounds(s, e)
    c = await _counts({"vendor_id": v["_id"], "created_at": {"$gte": lo, "$lt": hi}})
    vos = await db.vendor_orders.find({"vendor_id": v["_id"], "created_at": {"$gte": lo, "$lt": hi}}, {"items_net_minor": 1}).to_list(20000)
    views = c.get("product_view", 0)
    return {"range": {"from": s.isoformat(), "to": e.isoformat(), "timezone": "America/New_York (US Eastern Time)"},
            "product_views": views, "add_to_cart": c.get("add_to_cart", 0), "orders": len(vos), "net_item_sales_minor": sum(x["items_net_minor"] for x in vos),
            "view_to_order": round(len(vos) / views, 4) if views else None}


# ---------- cron ----------
@router.post("/cron/abandoned-carts", status_code=202)
async def cron_abandoned(request: Request, background: BackgroundTasks, authorization: str = Header(default="")):
    from afrovending.api.v1.cron import _accept
    return await _accept(request, background, authorization, "abandoned-carts", mk.run_abandoned_carts)


@router.post("/cron/wishlist-alerts", status_code=202)
async def cron_wishlist(request: Request, background: BackgroundTasks, authorization: str = Header(default="")):
    from afrovending.api.v1.cron import _accept
    from afrovending.core.wishlist_alerts import run_wishlist_alerts
    return await _accept(request, background, authorization, "wishlist-alerts", run_wishlist_alerts)
