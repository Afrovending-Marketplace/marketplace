import re
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field

from afrovending.api.v1.files import file_out
from afrovending.core import email as mail
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.security import client_ip

router = APIRouter(tags=["vendors"])
VENDOR_POLICY_VERSION = "vendor-agreement-draft-2026-10-17"
CATEGORIES = {"fashion", "beauty", "food-groceries", "home-living", "arts-crafts", "jewelry", "electronics", "books", "cultural-products"}
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,48}[a-z0-9])$")
RESERVED = {"admin", "api", "account", "vendor", "vendors", "store", "stores", "shop", "afrovending", "support", "help", "login"}
EDITABLE = {"draft", "changes_requested"}


def _clean(v):
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def ser(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    return {("id" if k == "_id" else k): _clean(v) for k, v in doc.items()}


class ApplicationIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=120)
    contact_email: EmailStr
    contact_phone: str = Field(default="", max_length=30)
    country: str = Field(min_length=2, max_length=2)
    region: str = Field(default="", max_length=100)
    city: str = Field(min_length=1, max_length=100)
    categories: list[str] = Field(min_length=1, max_length=9)
    description: str = Field(min_length=30, max_length=3000)
    desired_slug: str = Field(min_length=3, max_length=50)
    logo_file_id: Optional[str] = None
    banner_file_id: Optional[str] = None


class SubmitIn(BaseModel):
    accept_policy: bool
    policy_version: str


class StoreIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    tagline: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=3000)
    slug: str = Field(min_length=3, max_length=50)
    logo_file_id: Optional[str] = None
    banner_file_id: Optional[str] = None


async def check_slug(slug: str, user_id: str) -> str:
    slug = slug.strip().lower()
    if not SLUG_RE.match(slug) or slug in RESERVED:
        raise APIError(422, "validation_error", "Store URL must be 3–50 lowercase letters, numbers or hyphens.", [{"field": "slug", "message": "Invalid store URL."}])
    taken = await db.vendor_stores.find_one({"slug": slug, "owner_user_id": {"$ne": ObjectId(user_id)}}) or \
        await db.vendor_applications.find_one({"desired_slug": slug, "user_id": {"$ne": ObjectId(user_id)}, "status": {"$nin": ["rejected", "withdrawn"]}})
    if taken:
        raise APIError(409, "conflict", "That store URL is already taken.", [{"field": "slug", "message": "Already taken."}])
    return slug


async def own_file(file_id: Optional[str], user_id: str, purpose: str) -> Optional[ObjectId]:
    if not file_id:
        return None
    if not ObjectId.is_valid(file_id) or not await db.files.find_one({"_id": ObjectId(file_id), "owner_user_id": ObjectId(user_id), "purpose": purpose, "is_deleted": False}):
        raise APIError(422, "validation_error", f"Invalid {purpose} file.")
    return ObjectId(file_id)


async def my_application(user: User) -> Optional[dict]:
    return await db.vendor_applications.find_one({"user_id": ObjectId(user.id)}, sort=[("created_at", -1)])


async def my_vendor(user: User) -> dict:
    vendor = await db.vendors.find_one({"owner_user_id": ObjectId(user.id)})
    if not vendor or "vendor" not in user.roles:
        raise APIError(403, "forbidden", "Only approved vendors can do this.")
    return vendor


@router.get("/vendor/policy")
async def vendor_policy():
    return {"version": VENDOR_POLICY_VERSION, "url": "/vendor-agreement", "status": "draft_pending_legal_review"}


@router.get("/vendor/application")
async def get_application(user: User = Depends(get_current_user)):
    app = await my_application(user)
    docs = await db.files.find({"owner_user_id": ObjectId(user.id), "purpose": "verification_doc", "is_deleted": False}).to_list(20) if app else []
    return {"application": ser(app), "documents": [file_out(d) for d in docs], "policy_version": VENDOR_POLICY_VERSION}


@router.put("/vendor/application")
async def save_application(body: ApplicationIn, request: Request, user: User = Depends(get_current_user)):
    if not user.email_verified_at:
        raise APIError(403, "email_unverified", "Verify your email address before applying to sell.")
    if set(body.categories) - CATEGORIES:
        raise APIError(422, "validation_error", "Unknown category.")
    app = await my_application(user)
    if app and app["status"] in ("rejected", "withdrawn"):
        app = None  # start a fresh application; the old one stays for the record
    if app and app["status"] not in EDITABLE:
        raise APIError(409, "conflict", f"Your application is {app['status'].replace('_', ' ')} and can't be edited.")
    data = {**body.model_dump(), "country": body.country.upper(), "desired_slug": await check_slug(body.desired_slug, user.id),
            "logo_file_id": await own_file(body.logo_file_id, user.id, "logo"),
            "banner_file_id": await own_file(body.banner_file_id, user.id, "banner"), "updated_at": utcnow()}
    if app:
        await db.vendor_applications.update_one({"_id": app["_id"]}, {"$set": data})
    else:
        await db.vendor_applications.insert_one({**data, "user_id": ObjectId(user.id), "status": "draft", "verification_status": "not_required",
                                                 "admin_note": "", "history": [], "created_at": utcnow()})
    await audit("vendor.application_saved", "vendor_applications", request=request, actor=user)
    return {"application": ser(await my_application(user))}


@router.post("/vendor/application/submit")
async def submit_application(body: SubmitIn, request: Request, user: User = Depends(get_current_user)):
    app = await my_application(user)
    if not app or app["status"] not in EDITABLE:
        raise APIError(409, "conflict", "There is no draft application to submit.")
    if not body.accept_policy or body.policy_version != VENDOR_POLICY_VERSION:
        raise APIError(422, "validation_error", "You must accept the current Vendor Agreement.")
    if app.get("verification_status") == "requested" and not await db.files.find_one({"owner_user_id": ObjectId(user.id), "purpose": "verification_doc", "is_deleted": False}):
        raise APIError(422, "validation_error", "Please upload the requested verification document first.")
    now = utcnow()
    await db.vendor_policy_acceptances.insert_one({"user_id": ObjectId(user.id), "policy": "vendor_agreement", "version": VENDOR_POLICY_VERSION,
                                                   "accepted_at": now, "ip": client_ip(request), "application_id": app["_id"]})
    await db.files.update_many({"owner_user_id": ObjectId(user.id), "purpose": "verification_doc", "application_id": None}, {"$set": {"application_id": app["_id"]}})
    verification = "pending" if app.get("verification_status") == "requested" else app.get("verification_status", "not_required")
    await db.vendor_applications.update_one({"_id": app["_id"]}, {
        "$set": {"status": "submitted", "submitted_at": now, "policy_version": VENDOR_POLICY_VERSION, "policy_accepted_at": now, "verification_status": verification},
        "$push": {"history": {"status": "submitted", "note": "", "at": now, "by": ObjectId(user.id)}}})
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$addToSet": {"roles": "vendor_applicant"}})
    await audit("vendor.application_submitted", "vendor_applications", request=request, actor=user, entity_id=str(app["_id"]), policy_version=VENDOR_POLICY_VERSION)
    subject, html = mail.vendor_notice_email(user.name, "We received your vendor application", "Our team will review it and email you with a decision.")
    await mail.try_send(to=user.email, subject=subject, html=html)
    return {"application": ser(await my_application(user))}


@router.get("/vendor/store")
async def get_store(user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    return {"vendor": ser(vendor), "store": ser(await db.vendor_stores.find_one({"vendor_id": vendor["_id"]}))}


@router.patch("/vendor/store")
async def update_store(body: StoreIn, request: Request, user: User = Depends(get_current_user)):
    vendor = await my_vendor(user)
    if vendor["status"] != "active":
        raise APIError(403, "vendor_suspended", "Your vendor account is suspended. Store changes are disabled.")
    data = {**body.model_dump(), "slug": await check_slug(body.slug, user.id), "logo_file_id": await own_file(body.logo_file_id, user.id, "logo"),
            "banner_file_id": await own_file(body.banner_file_id, user.id, "banner"), "updated_at": utcnow()}
    await db.vendor_stores.update_one({"vendor_id": vendor["_id"]}, {"$set": data})
    await db.vendors.update_one({"_id": vendor["_id"]}, {"$set": {"slug": data["slug"], "name": data["display_name"], "updated_at": utcnow()}})
    await db.vendor_applications.update_one({"_id": vendor["application_id"]}, {"$set": {"desired_slug": data["slug"]}})
    await audit("vendor.store_updated", "vendor_stores", request=request, actor=user, entity_id=str(vendor["_id"]))
    return {"store": ser(await db.vendor_stores.find_one({"vendor_id": vendor["_id"]}))}


@router.post("/vendor/store/{action}")
async def publish_store(action: str, request: Request, user: User = Depends(get_current_user)):
    if action not in ("publish", "unpublish"):
        raise APIError(404, "not_found", "Not found.")
    vendor = await my_vendor(user)
    if action == "publish" and vendor["status"] != "active":
        raise APIError(403, "vendor_suspended", "Only active, approved vendors can publish a store.")
    status = "published" if action == "publish" else "draft"
    await db.vendor_stores.update_one({"vendor_id": vendor["_id"]}, {"$set": {"status": status, "updated_at": utcnow()}})
    await audit(f"vendor.store_{action}ed", "vendor_stores", request=request, actor=user, entity_id=str(vendor["_id"]))
    return {"store": ser(await db.vendor_stores.find_one({"vendor_id": vendor["_id"]}))}


@router.get("/stores")
async def list_stores():
    stores = await db.vendor_stores.find({"status": "published"}).sort("display_name", 1).to_list(200)
    return {"data": [_public_store(s) for s in stores]}


@router.get("/stores/{slug}")
async def public_store(slug: str):
    store = await db.vendor_stores.find_one({"slug": slug.lower(), "status": "published"})
    if not store or not await db.vendors.find_one({"_id": store["vendor_id"], "status": "active"}):
        raise APIError(404, "not_found", "Store not found.")
    return _public_store(store)


def _public_store(s: dict) -> dict:
    url = lambda fid: f"/api/v1/files/{fid}" if fid else None  # noqa: E731
    return {"slug": s["slug"], "display_name": s["display_name"], "tagline": s.get("tagline", ""), "description": s.get("description", ""),
            "location": s.get("location", ""), "categories": s.get("categories", []), "logo_url": url(s.get("logo_file_id")), "banner_url": url(s.get("banner_file_id"))}
