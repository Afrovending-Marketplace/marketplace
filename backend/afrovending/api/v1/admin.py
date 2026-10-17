from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, EmailStr, Field

from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import require_roles
from afrovending.core.errors import APIError
from afrovending.core.models import PrivacyRequest, User, utcnow
from afrovending.core.roles import Role
from afrovending.core.security import hash_password, require_valid_password

router = APIRouter(prefix="/admin", tags=["admin"])
ANY_ADMIN = require_roles(Role.SUPPORT_ADMIN, Role.MARKETPLACE_ADMIN, Role.SUPER_ADMIN)
PRIVACY_ADMIN = require_roles(Role.MARKETPLACE_ADMIN, Role.SUPER_ADMIN)
SUPER = require_roles(Role.SUPER_ADMIN)


class StaffIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str
    role: Literal["support_admin", "marketplace_admin", "super_admin"]


class PrivacyUpdateIn(BaseModel):
    status: Literal["in_review", "completed", "rejected"]
    resolution_note: str = Field(default="", max_length=1000)


def _page(page: int, size: int):
    return (page - 1) * size, size


@router.get("/users")
async def list_users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), _: User = Depends(ANY_ADMIN)):
    skip, limit = _page(page, page_size)
    docs = await db.users.find({}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.users.count_documents({})
    return {"data": [User.from_mongo(d).public() for d in docs], "meta": {"page": page, "page_size": page_size, "total": total}}


@router.post("/staff", status_code=201)
async def create_staff(body: StaffIn, request: Request, admin: User = Depends(SUPER)):
    require_valid_password(body.password, strong=True)
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise APIError(409, "conflict", "An account with this email already exists.")
    staff = User(email=email, name=body.name, password_hash=hash_password(body.password), roles=[body.role], status="active",
                 email_verified_at=utcnow(), auth_providers=[{"provider": "password", "linked_at": utcnow()}])
    staff.id = str((await db.users.insert_one(staff.to_mongo())).inserted_id)
    await audit("admin.staff_created", "users", request=request, actor=admin, entity_id=staff.id, role=body.role)
    return {"user": staff.public()}


@router.get("/privacy-requests")
async def list_privacy(status: str | None = None, _: User = Depends(PRIVACY_ADMIN)):
    docs = await db.privacy_requests.find({"status": status} if status else {}).sort("created_at", -1).to_list(200)
    return {"data": [PrivacyRequest.from_mongo(d).model_dump() for d in docs]}


@router.patch("/privacy-requests/{request_id}")
async def update_privacy(request_id: str, body: PrivacyUpdateIn, request: Request, admin: User = Depends(PRIVACY_ADMIN)):
    if not ObjectId.is_valid(request_id):
        raise APIError(404, "not_found", "Request not found.")
    doc = await db.privacy_requests.find_one_and_update({"_id": ObjectId(request_id)},
                                                        {"$set": {**body.model_dump(), "updated_at": utcnow()}}, return_document=True)
    if not doc:
        raise APIError(404, "not_found", "Request not found.")
    await audit("admin.privacy_request_updated", "privacy_requests", request=request, actor=admin, entity_id=request_id, status=body.status)
    return PrivacyRequest.from_mongo(doc).model_dump()


@router.get("/audit-logs")
async def audit_logs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), _: User = Depends(SUPER)):
    skip, limit = _page(page, page_size)
    docs = await db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    for d in docs:
        for k in ("actor_id", "entity_id"):
            d[k] = str(d[k]) if d.get(k) else None
    return {"data": docs, "meta": {"page": page, "page_size": page_size, "total": await db.audit_logs.count_documents({})}}
