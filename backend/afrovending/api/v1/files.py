import uuid

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from afrovending.core import rate_limit
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.storage import APP_PREFIX, get_object, put_object

router = APIRouter(tags=["files"])
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
DOC_TYPES = {**IMAGE_TYPES, "application/pdf": "pdf"}
PUBLIC_PURPOSES = {"logo", "banner", "product_main", "product_thumb"}
LIMITS = {"logo": 2_000_000, "banner": 5_000_000, "verification_doc": 10_000_000}


def file_out(doc: dict) -> dict:
    return {"id": str(doc["_id"]), "purpose": doc["purpose"], "filename": doc["original_filename"],
            "content_type": doc["content_type"], "size": doc["size"], "created_at": doc["created_at"],
            "url": f"/api/v1/files/{doc['_id']}" if doc["purpose"] in PUBLIC_PURPOSES else None}


@router.post("/files", status_code=201)
async def upload(request: Request, purpose: str = Form(...), file: UploadFile = File(...), user: User = Depends(get_current_user)):
    if purpose not in LIMITS:
        raise APIError(422, "validation_error", "Unknown file purpose.")
    await rate_limit.hit(f"upload:{user.id}", 30, 3600)
    if await db.vendors.find_one({"owner_user_id": ObjectId(user.id), "status": "suspended"}):
        raise APIError(403, "vendor_suspended", "Uploads are disabled while your vendor account is suspended.")
    allowed = DOC_TYPES if purpose == "verification_doc" else IMAGE_TYPES
    if file.content_type not in allowed:
        raise APIError(422, "validation_error", "Unsupported file type. Use JPG, PNG, WEBP" + (" or PDF." if purpose == "verification_doc" else "."))
    data = await file.read()
    if not data or len(data) > LIMITS[purpose]:
        raise APIError(422, "validation_error", f"File must be under {LIMITS[purpose] // 1_000_000} MB.")
    folder = "private/vendor-docs" if purpose == "verification_doc" else "public/vendor-media"
    path = f"{APP_PREFIX}/{folder}/{user.id}/{uuid.uuid4()}.{allowed[file.content_type]}"
    try:
        result = await run_in_threadpool(put_object, path, data, file.content_type)
    except Exception:
        raise APIError(503, "storage_unavailable", "File storage is unavailable. Please try again.")
    doc = {"owner_user_id": ObjectId(user.id), "purpose": purpose, "storage_path": result["path"], "original_filename": (file.filename or "file")[:200],
           "content_type": file.content_type, "size": len(data), "is_private": purpose not in PUBLIC_PURPOSES, "is_deleted": False,
           "application_id": None, "created_at": utcnow()}
    doc["_id"] = (await db.files.insert_one(doc)).inserted_id
    await audit("file.uploaded", "files", request=request, actor=user, entity_id=str(doc["_id"]), purpose=purpose)
    return file_out(doc)


@router.get("/files/{file_id}")
async def public_file(file_id: str):
    if not ObjectId.is_valid(file_id):
        raise APIError(404, "not_found", "File not found.")
    doc = await db.files.find_one({"_id": ObjectId(file_id), "is_deleted": False, "is_private": False})
    if not doc:
        raise APIError(404, "not_found", "File not found.")
    data, _ = await run_in_threadpool(get_object, doc["storage_path"])
    return Response(content=data, media_type=doc["content_type"], headers={"Cache-Control": "public, max-age=86400"})


async def stream_private(doc: dict) -> Response:
    data, _ = await run_in_threadpool(get_object, doc["storage_path"])
    return Response(content=data, media_type=doc["content_type"],
                    headers={"Content-Disposition": f'attachment; filename="{doc["original_filename"]}"', "Cache-Control": "no-store"})
