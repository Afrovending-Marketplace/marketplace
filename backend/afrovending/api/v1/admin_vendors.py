from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from afrovending.api.v1.files import file_out, stream_private
from afrovending.api.v1.vendors import ser
from afrovending.core import email as mail
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.permissions import VENDORS, require_perm
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow

router = APIRouter(prefix="/admin", tags=["admin-vendors"])
REVIEWER = require_perm(VENDORS)
REVIEWABLE = {"submitted", "under_review"}


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "request_info"]
    note: str = Field(default="", max_length=2000)
    require_documents: bool = False


class StatusIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


def _oid(v: str) -> ObjectId:
    if not ObjectId.is_valid(v):
        raise APIError(404, "not_found", "Not found.")
    return ObjectId(v)


@router.get("/vendor-applications")
async def list_applications(status: str | None = None, _: User = Depends(REVIEWER)):
    q = {"status": status} if status else {"status": {"$ne": "draft"}}
    apps = await db.vendor_applications.find(q).sort("submitted_at", -1).to_list(200)
    return {"data": [ser(a) for a in apps]}


@router.get("/vendor-applications/{app_id}")
async def get_application(app_id: str, _: User = Depends(REVIEWER)):
    app = await db.vendor_applications.find_one({"_id": _oid(app_id)})
    if not app:
        raise APIError(404, "not_found", "Application not found.")
    docs = await db.files.find({"owner_user_id": app["user_id"], "purpose": "verification_doc", "is_deleted": False}).to_list(20)
    acceptance = await db.vendor_policy_acceptances.find_one({"application_id": app["_id"]}, {"_id": 0, "ip": 0}, sort=[("accepted_at", -1)])
    return {"application": ser(app), "documents": [file_out(d) for d in docs], "policy_acceptance": ser(acceptance)}


@router.post("/vendor-applications/{app_id}/decision")
async def decide(app_id: str, body: DecisionIn, request: Request, admin: User = Depends(REVIEWER)):
    app = await db.vendor_applications.find_one_and_update({"_id": _oid(app_id), "status": {"$in": list(REVIEWABLE)}}, {"$set": {"status": "deciding"}})
    if not app:
        raise APIError(409, "conflict", "Only submitted applications can be reviewed.")
    if body.decision != "approve" and len(body.note.strip()) < 5:
        await db.vendor_applications.update_one({"_id": app["_id"]}, {"$set": {"status": app["status"]}})
        raise APIError(422, "validation_error", "Add a note for the applicant.")
    now = utcnow()
    status = {"approve": "approved", "reject": "rejected", "request_info": "changes_requested"}[body.decision]
    sets = {"status": status, "admin_note": body.note, "reviewed_by": ObjectId(admin.id), "reviewed_at": now}
    if body.decision == "request_info" and body.require_documents:
        sets["verification_status"] = "requested"
    if body.decision == "approve":
        sets["verification_status"] = "verified" if app.get("verification_status") == "pending" else app.get("verification_status", "not_required")
        vendor_id = (await db.vendors.insert_one({"owner_user_id": app["user_id"], "application_id": app["_id"], "slug": app["desired_slug"],
                                                  "name": app["business_name"], "status": "active", "approved_at": now, "created_at": now, "updated_at": now})).inserted_id
        location = ", ".join(x.strip() for x in (app["city"], app.get("region", ""), app["country"]) if x and x.strip())
        await db.vendor_stores.insert_one({"vendor_id": vendor_id, "owner_user_id": app["user_id"], "slug": app["desired_slug"], "display_name": app["business_name"],
                                           "tagline": "", "description": app["description"], "location": location, "categories": app["categories"],
                                           "logo_file_id": app.get("logo_file_id"), "banner_file_id": app.get("banner_file_id"), "status": "draft",
                                           "created_at": now, "updated_at": now})
        await db.users.update_one({"_id": app["user_id"]}, {"$addToSet": {"roles": "vendor"}})
        await db.users.update_one({"_id": app["user_id"]}, {"$pull": {"roles": "vendor_applicant"}})
    await db.vendor_applications.update_one({"_id": app["_id"]}, {"$set": sets, "$push": {"history": {"status": status, "note": body.note, "at": now, "by": ObjectId(admin.id)}}})
    await audit(f"admin.vendor_application_{status}", "vendor_applications", request=request, actor=admin, entity_id=app_id)
    owner = await db.users.find_one({"_id": app["user_id"]})
    headline = {"approved": "Your vendor application is approved", "rejected": "Update on your vendor application",
                "changes_requested": "More information needed for your vendor application"}[status]
    text = {"approved": "Welcome to AfroVending! Your store is ready to set up and publish from your vendor dashboard.",
            "rejected": f"We're unable to approve your application at this time. {body.note}",
            "changes_requested": f"Please update your application: {body.note}"}[status]
    subject, html = mail.vendor_notice_email(owner["name"], headline, text)
    sent = await mail.try_send(to=owner["email"], subject=subject, html=html)
    return {"application": ser(await db.vendor_applications.find_one({"_id": app["_id"]})), "notification_sent": sent}


@router.get("/vendor-documents/{file_id}")
async def download_document(file_id: str, request: Request, admin: User = Depends(REVIEWER)):
    doc = await db.files.find_one({"_id": _oid(file_id), "purpose": "verification_doc", "is_deleted": False})
    if not doc:
        raise APIError(404, "not_found", "Document not found.")
    await audit("admin.vendor_document_viewed", "files", request=request, actor=admin, entity_id=file_id)
    return await stream_private(doc)


@router.delete("/vendor-documents/{file_id}")
async def delete_document(file_id: str, request: Request, admin: User = Depends(REVIEWER)):
    res = await db.files.update_one({"_id": _oid(file_id), "purpose": "verification_doc"}, {"$set": {"is_deleted": True, "deleted_at": utcnow()}})
    if not res.matched_count:
        raise APIError(404, "not_found", "Document not found.")
    await audit("admin.vendor_document_deleted", "files", request=request, actor=admin, entity_id=file_id)
    return {"status": "deleted"}


@router.get("/vendors")
async def list_vendors(_: User = Depends(REVIEWER)):
    return {"data": [ser(v) for v in await db.vendors.find({}).sort("created_at", -1).to_list(500)]}


@router.post("/vendors/{vendor_id}/{action}")
async def set_vendor_status(vendor_id: str, action: str, body: StatusIn, request: Request, admin: User = Depends(REVIEWER)):
    if action not in ("suspend", "reactivate"):
        raise APIError(404, "not_found", "Not found.")
    status = "suspended" if action == "suspend" else "active"
    vendor = await db.vendors.find_one_and_update({"_id": _oid(vendor_id)}, {"$set": {"status": status, "status_reason": body.reason, "updated_at": utcnow()}}, return_document=True)
    if not vendor:
        raise APIError(404, "not_found", "Vendor not found.")
    if status == "suspended":
        await db.vendor_stores.update_many({"vendor_id": vendor["_id"], "status": "published"}, {"$set": {"status": "paused"}})
    await audit(f"admin.vendor_{status}", "vendors", request=request, actor=admin, entity_id=vendor_id, reason=body.reason)
    owner = await db.users.find_one({"_id": vendor["owner_user_id"]})
    msg = f"Your vendor account was suspended: {body.reason}" if status == "suspended" else "Your vendor account was reactivated. You can publish your store again."
    subject, html = mail.vendor_notice_email(owner["name"], "Vendor account status update", msg)
    await mail.try_send(to=owner["email"], subject=subject, html=html)
    return {"vendor": ser(vendor)}
