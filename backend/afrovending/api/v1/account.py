from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from afrovending.core import email as mail
from afrovending.core import rate_limit
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import Address, PrivacyRequest, User, utcnow
from afrovending.core.security import clear_auth_cookies, verify_password
from afrovending.core.sessions import revoke_all_sessions

router = APIRouter(prefix="/account", tags=["account"])
MAX_ADDRESSES = 10


class ProfileIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)


class AddressIn(BaseModel):
    label: str = Field(default="", max_length=40)
    full_name: str = Field(min_length=1, max_length=100)
    line1: str = Field(min_length=1, max_length=200)
    line2: str = Field(default="", max_length=200)
    city: str = Field(min_length=1, max_length=100)
    region: str = Field(default="", max_length=100)
    postal_code: str = Field(default="", max_length=20)
    country: str = Field(min_length=2, max_length=2)
    phone: str = Field(default="", max_length=30)
    is_default: bool = False


class DeactivateIn(BaseModel):
    password: str
    reason: str = Field(default="", max_length=500)


class PrivacyIn(BaseModel):
    request_type: Literal["data_export", "data_deletion", "data_correction"]
    details: str = Field(default="", max_length=1000)


def _oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise APIError(404, "not_found", "Not found.")
    return ObjectId(value)


@router.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    return {"user": user.public()}


@router.patch("/profile")
async def update_profile(body: ProfileIn, request: Request, user: User = Depends(get_current_user)):
    changes = {k: v.strip() for k, v in body.model_dump(exclude_none=True).items()}
    if changes:
        doc = await db.users.find_one_and_update({"_id": ObjectId(user.id)}, {"$set": {**changes, "updated_at": utcnow()}},
                                                 return_document=True)
        user = User.from_mongo(doc)
        await audit("account.profile_updated", "users", request=request, actor=user, entity_id=user.id, fields=list(changes))
    return {"user": user.public()}


async def _clear_default(user_id: str) -> None:
    await db.addresses.update_many({"user_id": ObjectId(user_id)}, {"$set": {"is_default": False}})


@router.get("/addresses")
async def list_addresses(user: User = Depends(get_current_user)):
    docs = await db.addresses.find({"user_id": ObjectId(user.id)}).sort([("is_default", -1), ("created_at", 1)]).to_list(MAX_ADDRESSES)
    return {"data": [Address.from_mongo(d).model_dump() for d in docs]}


@router.post("/addresses", status_code=201)
async def create_address(body: AddressIn, user: User = Depends(get_current_user)):
    existing = await db.addresses.count_documents({"user_id": ObjectId(user.id)})
    if existing >= MAX_ADDRESSES:
        raise APIError(409, "conflict", f"You can save up to {MAX_ADDRESSES} addresses.")
    data = body.model_dump()
    data["country"] = data["country"].upper()
    if data["is_default"] or existing == 0:
        await _clear_default(user.id)
        data["is_default"] = True
    addr = Address(user_id=user.id, **data)
    addr.id = str((await db.addresses.insert_one(addr.to_mongo())).inserted_id)
    return addr.model_dump()


@router.patch("/addresses/{address_id}")
async def update_address(address_id: str, body: AddressIn, user: User = Depends(get_current_user)):
    query = {"_id": _oid(address_id), "user_id": ObjectId(user.id)}
    if not await db.addresses.find_one(query):
        raise APIError(404, "not_found", "Address not found.")
    data = body.model_dump()
    data["country"] = data["country"].upper()
    if data["is_default"]:
        await _clear_default(user.id)
    else:
        data.pop("is_default")
    doc = await db.addresses.find_one_and_update(query, {"$set": {**data, "updated_at": utcnow()}}, return_document=True)
    return Address.from_mongo(doc).model_dump()


@router.delete("/addresses/{address_id}")
async def delete_address(address_id: str, user: User = Depends(get_current_user)):
    doc = await db.addresses.find_one_and_delete({"_id": _oid(address_id), "user_id": ObjectId(user.id)})
    if not doc:
        raise APIError(404, "not_found", "Address not found.")
    if doc.get("is_default"):
        await db.addresses.find_one_and_update({"user_id": ObjectId(user.id)}, {"$set": {"is_default": True}}, sort=[("created_at", 1)])
    return {"status": "deleted"}


@router.post("/deactivate")
async def deactivate(body: DeactivateIn, request: Request, response: Response, user: User = Depends(get_current_user)):
    await rate_limit.hit(f"deactivate:{user.id}", 5, 900)
    if any(r.endswith("admin") for r in user.roles):
        raise APIError(403, "forbidden", "Administrator accounts must be deactivated by a super administrator.")
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise APIError(400, "invalid_credentials", "Your password is incorrect.")
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {"status": "deactivated", "deactivated_at": utcnow(), "updated_at": utcnow()}})
    await revoke_all_sessions(user.id)
    clear_auth_cookies(response)
    await audit("account.deactivated", "users", request=request, actor=user, entity_id=user.id, reason=body.reason)
    subject, html = mail.security_notice_email(user.name, "Your AfroVending account was deactivated and all devices were signed out.")
    await mail.try_send(to=user.email, subject=subject, html=html)
    return {"status": "deactivated"}


@router.get("/privacy-requests")
async def list_privacy_requests(user: User = Depends(get_current_user)):
    docs = await db.privacy_requests.find({"user_id": ObjectId(user.id)}).sort("created_at", -1).to_list(50)
    return {"data": [PrivacyRequest.from_mongo(d).model_dump() for d in docs]}


@router.post("/privacy-requests", status_code=201)
async def create_privacy_request(body: PrivacyIn, request: Request, user: User = Depends(get_current_user)):
    await rate_limit.hit(f"privacy:{user.id}", 5, 86400)
    if await db.privacy_requests.find_one({"user_id": ObjectId(user.id), "request_type": body.request_type,
                                           "status": {"$in": ["submitted", "in_review"]}}):
        raise APIError(409, "conflict", "You already have an open request of this type.")
    req = PrivacyRequest(user_id=user.id, **body.model_dump())
    req.id = str((await db.privacy_requests.insert_one(req.to_mongo())).inserted_id)
    await audit("account.privacy_request_created", "privacy_requests", request=request, actor=user, entity_id=req.id, type=body.request_type)
    return req.model_dump()
