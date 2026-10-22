from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from afrovending.api.v1.vendors import ser
from afrovending.core.audit import audit
from afrovending.core.catalog import oid
from afrovending.core.db import db
from afrovending.core.deps import require_roles
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.roles import Role

router = APIRouter(prefix="/admin/commerce", tags=["admin-commerce"])
ADMIN = require_roles(Role.MARKETPLACE_ADMIN, Role.SUPER_ADMIN)
Status = Literal["active", "inactive"]


class ShippingIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    amount_minor: int = Field(ge=0, le=1_000_000)
    eta: str = Field(default="", max_length=80)
    free_over_minor: Optional[int] = Field(default=None, ge=0)
    vendor_slug: Optional[str] = None
    status: Status = "active"


class CouponIn(BaseModel):
    code: str = Field(min_length=3, max_length=30)
    type: Literal["percent", "fixed"]
    value: int = Field(ge=1, le=100_000_000, description="percent: basis points (1000 = 10%); fixed: cents")
    min_subtotal_minor: int = Field(default=0, ge=0)
    max_redemptions: Optional[int] = Field(default=None, ge=1)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    vendor_slug: Optional[str] = None
    status: Literal["draft", "active", "paused", "expired"] = "active"

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.replace("-", "").isalnum():
            raise ValueError("Use letters, numbers and dashes only.")
        return v


class TaxIn(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    region: str = Field(default="", max_length=10)
    rate_bps: int = Field(ge=0, le=5000)
    label: str = Field(min_length=2, max_length=60)
    status: Status = "active"


async def _vendor_id(slug: Optional[str]):
    if not slug:
        return None
    store = await db.vendor_stores.find_one({"slug": slug})
    if not store:
        raise APIError(422, "validation_error", "Unknown vendor store.")
    return store["vendor_id"]


def _crud(path: str, coll: str, model, prepare, unique=None):
    @router.get(f"/{path}", name=f"list_{coll}")
    async def list_all(_: User = Depends(ADMIN)):
        return {"data": [ser(d) for d in await db[coll].find({}).sort("created_at", -1).to_list(500)]}

    @router.post(f"/{path}", status_code=201, name=f"create_{coll}")
    async def create(body: model, request: Request, admin: User = Depends(ADMIN)):
        doc = await prepare(body)
        if unique and await db[coll].find_one({k: doc[k] for k in unique}):
            raise APIError(409, "conflict", "That already exists.")
        doc.update(created_at=utcnow(), updated_at=utcnow(), created_by=ObjectId(admin.id))
        doc["_id"] = (await db[coll].insert_one(doc)).inserted_id
        await audit(f"admin.{coll}_created", coll, request=request, actor=admin, entity_id=str(doc["_id"]))
        return ser(doc)

    @router.put(f"/{path}/{{item_id}}", name=f"update_{coll}")
    async def update(item_id: str, body: model, request: Request, admin: User = Depends(ADMIN)):
        doc = await prepare(body)
        res = await db[coll].find_one_and_update({"_id": oid(item_id)}, {"$set": {**doc, "updated_at": utcnow()}})
        if not res:
            raise APIError(404, "not_found", "Not found.")
        await audit(f"admin.{coll}_updated", coll, request=request, actor=admin, entity_id=item_id)
        return ser(await db[coll].find_one({"_id": res["_id"]}))


async def _ship(b: ShippingIn) -> dict:
    return {**b.model_dump(exclude={"vendor_slug"}), "vendor_id": await _vendor_id(b.vendor_slug)}


async def _coupon(b: CouponIn) -> dict:
    if b.type == "percent" and b.value > 10_000:
        raise APIError(422, "validation_error", "Percent coupons are in basis points (max 10000 = 100%).")
    if b.starts_at and b.ends_at and b.starts_at >= b.ends_at:
        raise APIError(422, "validation_error", "End date must be after start date.")
    return {**b.model_dump(exclude={"vendor_slug"}), "vendor_id": await _vendor_id(b.vendor_slug)}


async def _tax(b: TaxIn) -> dict:
    return {**b.model_dump(), "country": b.country.upper(), "region": b.region.strip().upper()}


_crud("shipping-methods", "shipping_methods", ShippingIn, _ship)
_crud("coupons", "coupons", CouponIn, _coupon, unique=("code",))
_crud("tax-rates", "tax_rates", TaxIn, _tax, unique=("country", "region"))
