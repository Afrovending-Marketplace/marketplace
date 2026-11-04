import csv
import io
from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from afrovending.core import reports
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.permissions import (AUDIT, CONTENT, CUST_EXPORT, DASH, FIN_EXPORT, FIN_MANAGE, FIN_VIEW, OPS_EXPORT, SETTINGS, TICKETS,
                                          perms_of, require_perm)

router = APIRouter(tags=["admin-ops"])
DATE = r"^\d{4}-\d{2}-\d{2}$"
APPROVALS_KEY = "admin.approvals"


class BannerIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(default="", max_length=400)
    cta_label: str = Field(default="", max_length=40)
    cta_url: str = Field(default="", max_length=300, pattern=r"^(|/|/[^/\\\s][^\s]*|https://[^\s]+)$")
    placement: Literal["home_hero", "home_strip"] = "home_strip"
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    status: Literal["active", "inactive"] = "active"
    sort: int = Field(default=0, ge=0, le=1000)


class FeaturedIn(BaseModel):
    product_ids: list[str] = Field(default_factory=list, max_length=24)
    vendor_ids: list[str] = Field(default_factory=list, max_length=12)


class ApprovalCfgIn(BaseModel):
    refund_threshold_minor: int = Field(ge=0, le=100_000_000)


def _b(d: dict) -> dict:
    return {"id": str(d["_id"]), **{k: d.get(k) for k in BannerIn.model_fields}}


@router.get("/content/homepage")
async def homepage():
    now = utcnow()
    banners = await db.content_banners.find({"status": "active", "$and": [{"$or": [{"starts_at": None}, {"starts_at": {"$lte": now}}]},
                                                                            {"$or": [{"ends_at": None}, {"ends_at": {"$gt": now}}]}]}).sort("sort", 1).to_list(20)
    f = (await db.platform_settings.find_one({"key": "homepage.featured"}) or {}).get("value", {})
    pids, vids = [ObjectId(i) for i in f.get("product_ids", [])], [ObjectId(i) for i in f.get("vendor_ids", [])]
    prods = {p["_id"]: p async for p in db.products.find({"_id": {"$in": pids}, "status": "published"}, {"title": 1, "slug": 1})}
    stores = {s["vendor_id"]: s async for s in db.vendor_stores.find({"vendor_id": {"$in": vids}, "status": "published"}, {"display_name": 1, "slug": 1, "tagline": 1, "vendor_id": 1})}
    active = {v["_id"] async for v in db.vendors.find({"_id": {"$in": list(stores)}, "status": "active"}, {"_id": 1})}
    return {"banners": [_b(b) for b in banners],
            "featured_products": [{"id": str(i), "title": prods[i]["title"], "slug": prods[i]["slug"]} for i in pids if i in prods],
            "featured_vendors": [{"id": str(i), "name": stores[i]["display_name"], "slug": stores[i]["slug"], "tagline": stores[i].get("tagline", "")}
                                 for i in vids if i in stores and i in active]}


@router.get("/admin/content")
async def content_list(_: User = Depends(require_perm(CONTENT))):
    f = (await db.platform_settings.find_one({"key": "homepage.featured"}) or {}).get("value", {"product_ids": [], "vendor_ids": []})
    return {"banners": [_b(b) for b in await db.content_banners.find({}).sort("sort", 1).to_list(200)], "featured": f}


@router.post("/admin/content/banners", status_code=201)
async def banner_create(body: BannerIn, request: Request, admin: User = Depends(require_perm(CONTENT))):
    if body.starts_at and body.ends_at and body.ends_at <= body.starts_at:
        raise APIError(422, "validation_error", "The end time must be after the start time.")
    doc = {**body.model_dump(), "created_by": ObjectId(admin.id), "created_at": utcnow(), "updated_at": utcnow()}
    doc["_id"] = (await db.content_banners.insert_one(doc)).inserted_id
    await audit("content.banner_created", "content_banners", request=request, actor=admin, entity_id=str(doc["_id"]), title=body.title)
    return _b(doc)


@router.put("/admin/content/banners/{banner_id}")
async def banner_update(banner_id: str, body: BannerIn, request: Request, admin: User = Depends(require_perm(CONTENT))):
    if not ObjectId.is_valid(banner_id):
        raise APIError(404, "not_found", "Banner not found.")
    r = await db.content_banners.update_one({"_id": ObjectId(banner_id)}, {"$set": {**body.model_dump(), "updated_at": utcnow()}})
    if not r.matched_count:
        raise APIError(404, "not_found", "Banner not found.")
    await audit("content.banner_updated", "content_banners", request=request, actor=admin, entity_id=banner_id)
    return _b(await db.content_banners.find_one({"_id": ObjectId(banner_id)}))


@router.delete("/admin/content/banners/{banner_id}")
async def banner_delete(banner_id: str, request: Request, admin: User = Depends(require_perm(CONTENT))):
    if not ObjectId.is_valid(banner_id):
        raise APIError(404, "not_found", "Banner not found.")
    if not (await db.content_banners.delete_one({"_id": ObjectId(banner_id)})).deleted_count:
        raise APIError(404, "not_found", "Banner not found.")
    await audit("content.banner_deleted", "content_banners", request=request, actor=admin, entity_id=banner_id)
    return {"status": "deleted"}


@router.put("/admin/content/featured")
async def featured(body: FeaturedIn, request: Request, admin: User = Depends(require_perm(CONTENT))):
    pids = [ObjectId(i) for i in dict.fromkeys(body.product_ids) if ObjectId.is_valid(i)]
    vids = [ObjectId(i) for i in dict.fromkeys(body.vendor_ids) if ObjectId.is_valid(i)]
    if await db.products.count_documents({"_id": {"$in": pids}, "status": "published"}) != len(pids):
        raise APIError(422, "validation_error", "Only published products can be featured.")
    if await db.vendors.count_documents({"_id": {"$in": vids}, "status": "active"}) != len(vids):
        raise APIError(422, "validation_error", "Only active vendors can be featured.")
    value = {"product_ids": [str(i) for i in pids], "vendor_ids": [str(i) for i in vids]}
    await db.platform_settings.update_one({"key": "homepage.featured"}, {"$set": {"value": value, "updated_at": utcnow()}}, upsert=True)
    await audit("content.featured_updated", "platform_settings", request=request, actor=admin, **value)
    return value


@router.get("/admin/overview")
async def overview(admin: User = Depends(require_perm(DASH))):
    perms = perms_of(admin.roles)
    out = {"permissions": sorted(perms), "roles": [r for r in admin.roles if r.endswith("_admin")]}
    if perms & {"vendors.manage", "catalog.moderate", "orders.view", "customers.view"}:
        out["operations"] = {
            "customers": await db.users.count_documents({"roles": "customer"}),
            "vendors_active": await db.vendors.count_documents({"status": "active"}),
            "vendors_suspended": await db.vendors.count_documents({"status": "suspended"}),
            "applications_pending": await db.vendor_applications.count_documents({"status": {"$in": ["submitted", "under_review"]}}),
            "products_pending_review": await db.products.count_documents({"status": "pending_review"}),
            "orders_open": await db.vendor_orders.count_documents({"status": {"$in": list(reports.OPEN)}}),
            "orders_overdue": await db.vendor_orders.count_documents({"status": {"$in": ["accepted", "processing", "partially_shipped"]}, "handling.deadline_at": {"$lt": utcnow()}}),
            "requests_open": await db.order_requests.count_documents({"status": "requested"})}
    if TICKETS in perms:
        out["tickets"] = {q: await db.support_tickets.count_documents({"queue": q, "status": {"$nin": ["resolved", "closed"]}}) for q in ("support", "marketplace", "finance")}
    if FIN_VIEW in perms:
        start, end = reports.parse_range(None, None)
        a, b = reports.et_bounds(start, end)
        led = await db.commission_ledger.aggregate([{"$match": {"created_at": {"$gte": a, "$lt": b}, "account": "platform"}},
                                                    {"$group": {"_id": "$type", "s": {"$sum": "$amount_minor"}}}]).to_list(50)
        pays = await db.payments.aggregate([{"$match": {"status": {"$in": ["succeeded", "partially_refunded", "refunded"]}, "created_at": {"$gte": a, "$lt": b}}},
                                            {"$group": {"_id": None, "s": {"$sum": "$amount_minor"}, "n": {"$sum": 1}}}]).to_list(1)
        out["finance"] = {"period": f"{start} to {end} (US Eastern)", "gross_payments_minor": pays[0]["s"] if pays else 0, "payments": pays[0]["n"] if pays else 0,
                          "platform_ledger_by_type": {x["_id"]: x["s"] for x in led},
                          "refunds_pending": await db.refunds.count_documents({"status": "pending"}),
                          "disputes_open": await db.disputes.count_documents({"status": {"$nin": ["won", "lost", "closed"]}}),
                          "approvals_pending": await db.admin_approvals.count_documents({"status": "pending"})}
    if AUDIT in perms:
        out["recent_audit"] = [{"action": d["action"], "actor_role": d.get("actor_role"), "created_at": d["created_at"]}
                               for d in await db.audit_logs.find({}, {"action": 1, "actor_role": 1, "created_at": 1}).sort("created_at", -1).to_list(10)]
    return out


EXPORT_PERM = {"orders": FIN_EXPORT, "ledger": FIN_EXPORT, "payouts": FIN_EXPORT, "refunds": FIN_EXPORT, "vendors": OPS_EXPORT, "tickets": TICKETS, "customers": CUST_EXPORT}


@router.get("/admin/exports/{kind}.csv")
async def export(kind: Literal["orders", "ledger", "payouts", "refunds", "vendors", "tickets", "customers"], request: Request,
                 from_: Optional[str] = Query(default=None, alias="from", pattern=DATE), to: Optional[str] = Query(default=None, pattern=DATE),
                 admin: User = Depends(require_perm(DASH))):
    if EXPORT_PERM[kind] not in perms_of(admin.roles):
        raise APIError(403, "forbidden", "You do not have permission to export this report.")
    start, end = reports.parse_range(from_, to)
    a, b = reports.et_bounds(start, end)
    rng = {"created_at": {"$gte": a, "$lt": b}}
    et = lambda d: d.astimezone(reports.ET).strftime("%Y-%m-%d %H:%M") if d else ""  # noqa: E731
    usd = lambda m: f"{(m or 0) / 100:.2f}"  # noqa: E731
    specs = {
        "orders": ("vendor_orders", ["date_et", "order", "vendor", "status", "items_usd", "shipping_usd", "tax_usd", "charged_usd", "refunded_usd"],
                   lambda d: [et(d["created_at"]), d["order_number"], d.get("vendor_name", ""), d["status"], usd(d.get("items_net_minor")), usd(d.get("shipping_minor")),
                              usd(d.get("tax_minor")), usd(d.get("charged_minor")), usd(d.get("refunded_minor"))]),
        "ledger": ("commission_ledger", ["date_et", "entry_key", "account", "type", "amount_usd", "vendor_id", "order_id"],
                   lambda d: [et(d["created_at"]), d["entry_key"], d["account"], d["type"], usd(d["amount_minor"]), str(d.get("vendor_id") or ""), str(d.get("order_id") or "")]),
        "payouts": ("payouts", ["date_et", "order", "vendor_id", "amount_usd", "status", "transfer_ref"],
                    lambda d: [et(d["created_at"]), d.get("order_number", ""), str(d["vendor_id"]), usd(d["amount_minor"]), d["status"], d.get("stripe_transfer_id") or ""]),
        "refunds": ("refunds", ["date_et", "refund_id", "vendor_order_id", "amount_usd", "status", "reason"],
                    lambda d: [et(d["created_at"]), str(d["_id"]), str(d.get("vendor_order_id") or ""), usd(d.get("amount_minor")), d.get("status"), d.get("reason", "")]),
        "vendors": ("vendors", ["created_et", "vendor_id", "name", "status", "plan"], lambda d: [et(d.get("created_at")), str(d["_id"]), d.get("name", ""), d["status"], d.get("plan") or "starter"]),
        "tickets": ("support_tickets", ["created_et", "reference", "category", "status", "priority", "queue", "assigned"],
                    lambda d: [et(d["created_at"]), d["reference"], d["category"], d["status"], d["priority"], d["queue"], d.get("assigned_name") or ""]),
        "customers": ("users", ["created_et", "user_id", "name", "email", "status"], lambda d: [et(d.get("created_at")), str(d["_id"]), d.get("name", ""), d["email"], d["status"]]),
    }
    coll, header, row = specs[kind]
    q = {**rng, **({"roles": "customer"} if kind == "customers" else {})}
    docs = await db[coll].find(q).sort("created_at", 1).to_list(50001)
    if len(docs) > 50000:
        raise APIError(422, "range_too_large", "Too many rows. Choose a shorter date range.")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(row(d) for d in docs)
    await audit("admin.export", kind, request=request, actor=admin, rows=len(docs), range=f"{start}..{end}")
    return Response(buf.getvalue().encode(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="afrovending-{kind}-{start}_{end}.csv"'})


async def approval_cfg() -> dict:
    return {"refund_threshold_minor": 50000, **((await db.platform_settings.find_one({"key": APPROVALS_KEY}) or {}).get("value") or {})}


@router.get("/admin/approvals")
async def approvals(admin: User = Depends(require_perm(FIN_VIEW, FIN_MANAGE))):
    docs = await db.admin_approvals.find({}).sort("created_at", -1).to_list(200)
    return {"config": await approval_cfg(), "data": [{"id": str(d["_id"]), "action": d["action"], "amount_minor": d["amount_minor"], "status": d["status"],
                                                      "requested_by": d["requested_by_name"], "reason": d["payload"].get("reason", ""), "created_at": d["created_at"],
                                                      "decided_by": d.get("decided_by_name"), "result_id": d.get("result_id")} for d in docs]}


@router.put("/admin/approvals/config")
async def set_approval_cfg(body: ApprovalCfgIn, request: Request, admin: User = Depends(require_perm(SETTINGS))):
    await db.platform_settings.update_one({"key": APPROVALS_KEY}, {"$set": {"value": body.model_dump(), "updated_at": utcnow()}}, upsert=True)
    await audit("admin.approval_threshold_changed", "platform_settings", request=request, actor=admin, **body.model_dump())
    return body.model_dump()


class DecideIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=300)


@router.post("/admin/approvals/{approval_id}/decide")
async def decide(approval_id: str, body: DecideIn, request: Request, admin: User = Depends(require_perm(FIN_MANAGE))):
    from afrovending.core import payments as pay
    ap = await db.admin_approvals.find_one({"_id": ObjectId(approval_id), "status": "pending"}) if ObjectId.is_valid(approval_id) else None
    if not ap:
        raise APIError(404, "not_found", "Approval not found or already decided.")
    if str(ap["requested_by"]) == admin.id:
        raise APIError(403, "forbidden", "A different finance administrator must approve this request.")
    claimed = await db.admin_approvals.find_one_and_update({"_id": ap["_id"], "status": "pending"}, {"$set": {"status": "processing" if body.decision == "approve" else "rejected",
                                                                                                         "decided_by": ObjectId(admin.id), "decided_by_name": admin.name, "decided_at": utcnow(), "note": body.note}})
    if not claimed:
        raise APIError(409, "conflict", "Someone else just decided this request.")
    result = None
    if body.decision == "approve":
        p = ap["payload"]
        vo = await db.vendor_orders.find_one({"_id": ObjectId(p["vo_id"])})
        try:
            doc = await pay.create_refund(vo, [(ObjectId(i), q) for i, q in p["lines"]], include_shipping=p["include_shipping"], reason=p["reason"],
                                          key=p["key"], actor_id=str(ap["requested_by"]))
        except Exception as exc:
            await db.admin_approvals.update_one({"_id": ap["_id"]}, {"$set": {"status": "failed", "error": str(exc)[:300]}})
            await audit("admin.approval_failed", "admin_approvals", request=request, actor=admin, entity_id=approval_id)
            raise
        result = str(doc["_id"])
        await db.admin_approvals.update_one({"_id": ap["_id"]}, {"$set": {"status": "approved", "result_id": result}})
    await audit(f"admin.approval_{body.decision}d", "admin_approvals", request=request, actor=admin, entity_id=approval_id, amount=ap["amount_minor"], result=result)
    return {"status": "approved" if result else "rejected", "refund_id": result}
