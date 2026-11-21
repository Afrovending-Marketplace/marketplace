"""Policy Management: public published policies, user acceptance, and the admin draft → legal review → approval → publication workflow."""
from datetime import date, datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from afrovending.core import policies as pol
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.permissions import POLICY_EDIT, require_perm

router = APIRouter(tags=["policies"])
EDITOR = require_perm(POLICY_EDIT)


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, ObjectId) else v


def _v(d: dict, body: bool = True) -> dict:
    out = {k: _iso(v) for k, v in d.items() if k not in ("_id", "body", "history")}
    out["id"] = str(d["_id"])
    out["history"] = [{k: _iso(v) for k, v in h.items()} for h in d.get("history", [])]
    if body:
        out["body"] = d.get("body", "")
    return out


def _slug(slug: str) -> str:
    if slug not in pol.META:
        raise APIError(404, "not_found", "Policy not found.")
    return slug


def _super(admin: User):
    if "super_admin" not in admin.roles:
        raise APIError(403, "forbidden", "Only the Super Admin can do this.")


async def _version(vid: str) -> dict:
    d = await db.policy_versions.find_one({"_id": ObjectId(vid)}) if ObjectId.is_valid(vid) else None
    if not d:
        raise APIError(404, "not_found", "Version not found.")
    return d


async def _move(d: dict, frm: tuple, to: str, admin: User, request: Request, note: str = "", extra: dict | None = None):
    now = utcnow()
    r = await db.policy_versions.update_one({"_id": d["_id"], "status": {"$in": list(frm)}},
                                           {"$set": {"status": to, "updated_at": now, **(extra or {})},
                                            "$push": {"history": {"status": to, "by": admin.email, "at": now, "note": note}}})
    if not r.modified_count:
        raise APIError(409, "conflict", f"This version is {d['status'].replace('_', ' ')}; that action isn't allowed.")
    await audit(f"policy.{to}", "policy_versions", request=request, actor=admin, entity_id=str(d["_id"]), slug=d["slug"], version=d["version"], note=note)


# ---------- public ----------
@router.get("/policies")
async def list_public():
    out = []
    for slug, m in pol.META.items():
        cur = await pol.published(slug)
        out.append({**m, "published": {"version": cur["version"], "effective_date": cur.get("effective_date"), "published_at": _iso(cur.get("published_at"))} if cur else None})
    return {"data": out}


@router.get("/policies/{slug}")
async def get_public(slug: str):
    m = pol.META[_slug(slug)]
    cur = await pol.published(slug)
    if not cur:
        return {**m, "status": "finalising"}
    return {**m, "status": "published", "version": cur["version"], "effective_date": cur.get("effective_date"), "published_at": _iso(cur.get("published_at")),
            "change_summary": cur.get("change_summary", ""), "body": cur["body"], "changes": await _changes(slug)}


async def _changes(slug: str) -> list[dict]:
    """Public change log: every version that has been published (current or since archived)."""
    docs = await db.policy_versions.find({"slug": slug, "published_at": {"$ne": None}}, {"body": 0, "history": 0, "legal_review": 0}).sort("version", -1).to_list(100)
    return [{"version": d["version"], "effective_date": d.get("effective_date"), "published_at": _iso(d["published_at"]),
             "change_summary": d.get("change_summary", ""), "material": d.get("classification") == "material", "current": d["status"] == "published"} for d in docs]


# ---------- account acceptance ----------
@router.get("/account/policy-status")
async def my_status(user: User = Depends(get_current_user)):
    return {"pending": await pol.pending_for(user.id, pol.slugs_for(user.roles))}


class AcceptIn(BaseModel):
    version_ids: list[str] = Field(min_length=1, max_length=7)
    accept: bool


@router.post("/account/policy-acceptances")
async def accept(body: AcceptIn, request: Request, user: User = Depends(get_current_user)):
    if body.accept is not True:
        raise APIError(422, "validation_error", "Tick the box to confirm you accept.")
    pend = await pol.pending_for(user.id, pol.slugs_for(user.roles))
    wanted = {p["version_id"]: p["slug"] for p in pend}
    if not pend or set(body.version_ids) != set(wanted):
        raise APIError(409, "conflict", "The policies to accept have changed. Please reload and review them again.")
    rows = await pol.record(user.id, list(wanted.values()), "reacceptance", request)
    await audit("policy.accepted", "policy_acceptances", request=request, actor=user, versions=[f"{r['slug']}-v{r['version']}" for r in rows])
    return {"pending": await pol.pending_for(user.id, pol.slugs_for(user.roles))}


# ---------- admin ----------
@router.get("/admin/policies")
async def admin_list(admin: User = Depends(EDITOR)):
    out = []
    for slug, m in pol.META.items():
        cur = await pol.published(slug)
        open_v = await db.policy_versions.find_one({"slug": slug, "status": {"$in": ["draft", "pending_review", "approved"]}}, sort=[("version", -1)])
        out.append({**m, "published": _v(cur, False) if cur else None, "open": _v(open_v, False) if open_v else None,
                    "versions": await db.policy_versions.count_documents({"slug": slug}),
                    "acceptances": await db.policy_acceptances.count_documents({"slug": slug})})
    return {"data": out, "is_super_admin": "super_admin" in admin.roles}


@router.get("/admin/policies/{slug}/versions")
async def admin_versions(slug: str, _: User = Depends(EDITOR)):
    docs = await db.policy_versions.find({"slug": _slug(slug)}).sort("version", -1).to_list(200)
    return {"data": [_v(d, False) for d in docs]}


@router.get("/admin/policies/versions/{vid}")
async def admin_version(vid: str, _: User = Depends(EDITOR)):
    d = await _version(vid)
    accepted = await db.policy_acceptances.count_documents({"version_id": d["_id"]})
    return {**_v(d), "acceptance_count": accepted}


class DraftIn(BaseModel):
    body: str = Field(default="", max_length=200_000)
    change_summary: str = Field(default="", max_length=2000)
    effective_date: Optional[date] = None


@router.post("/admin/policies/{slug}/versions", status_code=201)
async def new_draft(slug: str, body: DraftIn, request: Request, admin: User = Depends(EDITOR)):
    _slug(slug)
    if await db.policy_versions.find_one({"slug": slug, "status": {"$in": ["draft", "pending_review", "approved"]}}):
        raise APIError(409, "conflict", "This policy already has an open version. Finish or archive it first.")
    last = await db.policy_versions.find_one({"slug": slug}, sort=[("version", -1)])
    now = utcnow()
    doc = {"slug": slug, "version": (last["version"] + 1) if last else 1, "status": "draft", "body": body.body or (last or {}).get("body", ""),
           "change_summary": body.change_summary, "effective_date": body.effective_date.isoformat() if body.effective_date else None,
           "created_by": admin.email, "created_at": now, "updated_at": now, "published_at": None, "requires_reacceptance": False,
           "history": [{"status": "draft", "by": admin.email, "at": now, "note": f"Created from v{last['version']}" if last else "Created"}]}
    doc["_id"] = (await db.policy_versions.insert_one(doc)).inserted_id
    await audit("policy.draft_created", "policy_versions", request=request, actor=admin, entity_id=str(doc["_id"]), slug=slug, version=doc["version"])
    return _v(doc)


@router.put("/admin/policies/versions/{vid}")
async def edit_draft(vid: str, body: DraftIn, request: Request, admin: User = Depends(EDITOR)):
    d = await _version(vid)
    sets = {"body": body.body, "change_summary": body.change_summary, "effective_date": body.effective_date.isoformat() if body.effective_date else None,
            "updated_at": utcnow(), "updated_by": admin.email}
    r = await db.policy_versions.update_one({"_id": d["_id"], "status": "draft"}, {"$set": sets})
    if not r.modified_count:
        raise APIError(409, "version_locked", "Only drafts can be edited. Create a new draft to make changes.")
    await audit("policy.draft_edited", "policy_versions", request=request, actor=admin, entity_id=vid, slug=d["slug"], version=d["version"])
    return _v(await _version(vid))


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=2000)


@router.post("/admin/policies/versions/{vid}/submit")
async def submit(vid: str, body: NoteIn, request: Request, admin: User = Depends(EDITOR)):
    d = await _version(vid)
    if len(d.get("body", "").strip()) < 200:
        raise APIError(422, "validation_error", "The policy text is too short to submit.")
    await _move(d, ("draft",), "pending_review", admin, request, body.note or "Submitted for legal review")
    return _v(await _version(vid))


@router.post("/admin/policies/versions/{vid}/request-changes")
async def request_changes(vid: str, body: NoteIn, request: Request, admin: User = Depends(EDITOR)):
    _super(admin)
    if len(body.note.strip()) < 5:
        raise APIError(422, "validation_error", "Describe the changes needed.")
    await _move(await _version(vid), ("pending_review",), "draft", admin, request, body.note)
    return _v(await _version(vid))


class ApproveIn(BaseModel):
    legal_review_confirmed: bool
    reviewer_name: str = Field(min_length=2, max_length=200)
    reviewer_firm: str = Field(default="", max_length=200)
    review_date: date
    review_notes: str = Field(default="", max_length=2000)
    classification: Literal["material", "non_material"]
    change_summary: str = Field(min_length=5, max_length=2000)
    effective_date: date


@router.post("/admin/policies/versions/{vid}/approve")
async def approve(vid: str, body: ApproveIn, request: Request, admin: User = Depends(EDITOR)):
    _super(admin)
    if body.legal_review_confirmed is not True:
        raise APIError(422, "legal_review_required", "Confirm that an external legal review has actually been completed.")
    if body.review_date > date.today():
        raise APIError(422, "validation_error", "The legal review date can't be in the future.")
    pre = await _version(vid)
    open_n = await db.legal_change_requests.count_documents({"policy_slug": pre["slug"], "status": {"$in": ["open", "in_progress"]}})
    if open_n:
        raise APIError(409, "attorney_changes_open", f"{open_n} attorney-requested change(s) for this policy are still open. Resolve them first.")
    d = await _version(vid)
    first = not await db.policy_versions.find_one({"slug": d["slug"], "published_at": {"$ne": None}})
    needs = pol.META[d["slug"]]["acceptance"] is not None and (first or body.classification == "material")
    review = {"confirmed": True, "reviewer_name": body.reviewer_name, "reviewer_firm": body.reviewer_firm, "review_date": body.review_date.isoformat(),
              "notes": body.review_notes, "recorded_by": admin.email, "recorded_at": utcnow()}
    await _move(d, ("pending_review",), "approved", admin, request, f"Legal review by {body.reviewer_name} on {body.review_date}",
                {"legal_review": review, "classification": body.classification, "requires_reacceptance": needs, "change_summary": body.change_summary,
                 "effective_date": body.effective_date.isoformat(), "approved_by": admin.email, "approved_at": utcnow()})
    return _v(await _version(vid))


class ConfirmIn(BaseModel):
    confirm: str = Field(default="", max_length=20)
    reason: str = Field(default="", max_length=500)


@router.post("/admin/policies/versions/{vid}/publish")
async def publish(vid: str, body: ConfirmIn, request: Request, admin: User = Depends(EDITOR)):
    _super(admin)
    if body.confirm != "PUBLISH":
        raise APIError(422, "validation_error", "Type PUBLISH to confirm.")
    d = await _version(vid)
    if d["status"] != "approved" or not (d.get("legal_review") or {}).get("confirmed"):
        raise APIError(409, "conflict", "Only legally approved versions can be published.")
    prev = await pol.published(d["slug"])
    if prev:
        await _move(prev, ("published",), "archived", admin, request, f"Replaced by v{d['version']}", {"archived_at": utcnow()})
    try:
        await _move(d, ("approved",), "published", admin, request, body.reason or "Published", {"published_at": utcnow(), "published_by": admin.email})
    except Exception:
        if prev:
            await db.policy_versions.update_one({"_id": prev["_id"]}, {"$set": {"status": "published"}, "$unset": {"archived_at": ""}})
        raise
    return _v(await _version(vid))


@router.post("/admin/policies/versions/{vid}/archive")
async def archive(vid: str, body: ConfirmIn, request: Request, admin: User = Depends(EDITOR)):
    _super(admin)
    if len(body.reason.strip()) < 5:
        raise APIError(422, "validation_error", "Give a reason for archiving.")
    d = await _version(vid)
    await _move(d, ("draft", "pending_review", "approved", "published"), "archived", admin, request, body.reason, {"archived_at": utcnow()})
    return _v(await _version(vid))


@router.get("/admin/policies/{slug}/acceptances")
async def acceptances(slug: str, _: User = Depends(EDITOR)):
    _slug(slug)
    by_v = await db.policy_acceptances.aggregate([{"$match": {"slug": slug}}, {"$group": {"_id": "$version", "n": {"$sum": 1}}}, {"$sort": {"_id": -1}}]).to_list(100)
    recent = await db.policy_acceptances.find({"slug": slug}).sort("accepted_at", -1).limit(25).to_list(25)
    users = {u["_id"]: u["email"] async for u in db.users.find({"_id": {"$in": [r["user_id"] for r in recent]}}, {"email": 1})}
    return {"by_version": [{"version": b["_id"], "count": b["n"]} for b in by_v],
            "recent": [{"email": users.get(r["user_id"], "deleted user"), "version": r["version"], "context": r["context"], "accepted_at": _iso(r["accepted_at"])} for r in recent]}


# ---------- attorney review pack (admin-only files, stored in the database) ----------
MIME = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "pdf": "application/pdf"}


def _pack_out(d: dict) -> dict:
    recs = [{k: _iso(v) for k, v in r.items() if k != "storage_path"} for r in d.get("attorney_records", [])]
    return {"id": str(d["_id"]), "pack_number": d.get("pack_number", 1), "created_by": d["created_by"], "created_at": _iso(d["created_at"]), "sizes": d["sizes"],
            "policy_versions": d["policy_versions"], "external_sharing_approved": d.get("external_sharing_approved", False),
            "sharing_approved_by": d.get("sharing_approved_by"), "sharing_approved_at": _iso(d.get("sharing_approved_at")), "downloads": d.get("downloads", 0),
            "attorney_records": recs}


def _render(data: dict) -> dict:
    import tempfile
    from pathlib import Path
    from afrovending.core import review_pack as rp
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for fmt, fn in (("docx", rp.build_docx), ("pdf", rp.build_pdf)):
            p = Path(tmp) / f"pack.{fmt}"
            fn(data, p)
            out[fmt] = p.read_bytes()
    return out


@router.post("/admin/policies/review-pack", status_code=201)
async def make_pack(request: Request, admin: User = Depends(EDITOR)):
    from bson import Binary
    from afrovending.core import review_pack as rp
    data = await rp.gather()
    files = await run_in_threadpool(_render, data)
    doc = {"created_by": admin.email, "created_at": utcnow(), "files": {k: Binary(v) for k, v in files.items()}, "sizes": {k: len(v) for k, v in files.items()},
           "policy_versions": [{"slug": p["slug"], "version": p["version"], "status": p["status"]} for p in data["policies"]],
           "external_sharing_approved": False, "downloads": 0, "pack_number": ((await db.review_packs.find_one({}, {"pack_number": 1}, sort=[("pack_number", -1)])) or {}).get("pack_number", 0) + 1, "attorney_records": []}
    doc["_id"] = (await db.review_packs.insert_one(doc)).inserted_id
    await audit("policy.review_pack_generated", "review_packs", request=request, actor=admin, entity_id=str(doc["_id"]))
    return _pack_out(doc)


@router.get("/admin/policies/review-pack")
async def list_packs(_: User = Depends(EDITOR)):
    docs = await db.review_packs.find({}, {"files": 0}).sort("created_at", -1).limit(10).to_list(10)
    return {"data": [_pack_out(d) for d in docs]}


@router.get("/admin/policies/review-pack/{pid}/download")
async def download_pack(pid: str, request: Request, format: Literal["docx", "pdf"] = "docx", admin: User = Depends(EDITOR)):
    d = await db.review_packs.find_one({"_id": ObjectId(pid)}) if ObjectId.is_valid(pid) else None
    if not d:
        raise APIError(404, "not_found", "Review pack not found.")
    if not d.get("external_sharing_approved"):
        raise APIError(403, "sharing_not_approved", "The Super Admin must approve this pack for external sharing before it can be downloaded.")
    await db.review_packs.update_one({"_id": d["_id"]}, {"$inc": {"downloads": 1}})
    await audit("policy.review_pack_downloaded", "review_packs", request=request, actor=admin, entity_id=pid, format=format, pack_number=d.get("pack_number", 1))
    from zoneinfo import ZoneInfo
    local = d["created_at"].replace(tzinfo=d["created_at"].tzinfo or ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))
    name = f"AfroVending-Legal-Policy-Review-Pack-CONFIDENTIAL-{local:%Y-%m-%d}.{format}"
    return Response(content=bytes(d["files"][format]), media_type=MIME[format],
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


class ShareIn(BaseModel):
    confirm: bool = False
    acknowledge_not_legal_approval: bool = False


@router.post("/admin/policies/review-pack/{pid}/approve-sharing")
async def approve_sharing(pid: str, body: ShareIn, request: Request, admin: User = Depends(EDITOR)):
    _super(admin)
    if not (body.confirm and body.acknowledge_not_legal_approval):
        raise APIError(422, "validation_error", "Confirm the approval and acknowledge that sharing approval is not legal approval.")
    d = await db.review_packs.find_one({"_id": ObjectId(pid)}, {"files": 0}) if ObjectId.is_valid(pid) else None
    if not d:
        raise APIError(404, "not_found", "Review pack not found.")
    if d.get("external_sharing_approved"):
        return {"ok": True, "already_approved": True}
    r = await db.review_packs.update_one({"_id": d["_id"], "external_sharing_approved": {"$ne": True}},
                                         {"$set": {"external_sharing_approved": True, "sharing_approved_by": admin.email, "sharing_approved_at": utcnow()}})
    if not r.modified_count:
        return {"ok": True, "already_approved": True}
    await audit("policy.review_pack_sharing_approved", "review_packs", request=request, actor=admin, entity_id=pid, pack_number=d.get("pack_number", 1),
                policy_versions=[f"{p['slug']}-v{p['version']}" for p in d["policy_versions"]])
    return {"ok": True}


ATTORNEY_TYPES = {"application/pdf": "pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}


@router.post("/admin/policies/review-pack/{pid}/attorney-review", status_code=201)
async def attorney_review(pid: str, request: Request, reviewer_name: str = Form(..., min_length=2, max_length=200), reviewer_firm: str = Form("", max_length=200),
                          received_on: date = Form(...), comments: str = Form("", max_length=10000), recommendations: str = Form("", max_length=10000),
                          requested_changes: str = Form("", max_length=10000), file: Optional[UploadFile] = File(None), admin: User = Depends(EDITOR)):
    """Records attorney feedback (optionally with the reviewed document). Never changes policy status; publication has its own approval."""
    import uuid
    from afrovending.core.storage import APP_PREFIX, put_object
    _super(admin)
    d = await db.review_packs.find_one({"_id": ObjectId(pid)}, {"files": 0}) if ObjectId.is_valid(pid) else None
    if not d:
        raise APIError(404, "not_found", "Review pack not found.")
    if received_on > date.today():
        raise APIError(422, "validation_error", "The received date can't be in the future.")
    rec = {"id": str(ObjectId()), "reviewer_name": reviewer_name, "reviewer_firm": reviewer_firm, "received_on": received_on.isoformat(), "comments": comments,
           "recommendations": recommendations, "requested_changes": requested_changes, "recorded_by": admin.email, "recorded_at": utcnow(), "filename": None, "size": None}
    if file is not None and file.filename:
        if file.content_type not in ATTORNEY_TYPES:
            raise APIError(422, "validation_error", "Upload a PDF or Word (.docx) file.")
        data = await file.read()
        if not data or len(data) > 15_000_000:
            raise APIError(422, "validation_error", "File must be under 15 MB.")
        if not data.startswith(b"%PDF" if ATTORNEY_TYPES[file.content_type] == "pdf" else b"PK"):
            raise APIError(422, "validation_error", "The file content doesn't match a PDF or Word document.")
        path = f"{APP_PREFIX}/private/legal-review/{pid}/{uuid.uuid4()}.{ATTORNEY_TYPES[file.content_type]}"
        try:
            res = await run_in_threadpool(put_object, path, data, file.content_type)
        except Exception:
            raise APIError(503, "storage_unavailable", "File storage is unavailable. Please try again.")
        rec.update(filename=(file.filename or "attorney-review")[:200], size=len(data), content_type=file.content_type, storage_path=res["path"])
    await db.review_packs.update_one({"_id": d["_id"]}, {"$push": {"attorney_records": rec}})
    await audit("policy.attorney_review_recorded", "review_packs", request=request, actor=admin, entity_id=pid, record_id=rec["id"], reviewer=reviewer_name,
                has_file=bool(rec["filename"]))
    return _pack_out(await db.review_packs.find_one({"_id": d["_id"]}, {"files": 0}))


@router.get("/admin/policies/review-pack/{pid}/attorney-review/{rid}/file")
async def attorney_file(pid: str, rid: str, request: Request, admin: User = Depends(EDITOR)):
    from afrovending.core.storage import get_object
    d = await db.review_packs.find_one({"_id": ObjectId(pid)}, {"files": 0}) if ObjectId.is_valid(pid) else None
    rec = next((r for r in (d or {}).get("attorney_records", []) if r["id"] == rid and r.get("storage_path")), None)
    if not rec:
        raise APIError(404, "not_found", "File not found.")
    data, _ = await run_in_threadpool(get_object, rec["storage_path"])
    await audit("policy.attorney_review_downloaded", "review_packs", request=request, actor=admin, entity_id=pid, record_id=rid)
    return Response(content=data, media_type=rec["content_type"], headers={"Content-Disposition": f'attachment; filename="{rec["filename"]}"', "Cache-Control": "no-store"})


# ---------- attorney feedback tracker ----------
CHANGE_STATUSES = ("open", "in_progress", "done", "wont_do")


def _chg(d: dict) -> dict:
    return {**{k: _iso(v) for k, v in d.items() if k not in ("_id", "history")}, "id": str(d["_id"]),
            "history": [{k: _iso(v) for k, v in h.items()} for h in d.get("history", [])]}


class ChangeItem(BaseModel):
    policy_slug: str
    clause: str = Field(default="", max_length=100)
    description: str = Field(min_length=5, max_length=2000)


class ChangesIn(BaseModel):
    items: list[ChangeItem] = Field(min_length=1, max_length=50)


@router.post("/admin/policies/review-pack/{pid}/attorney-review/{rid}/changes", status_code=201)
async def create_changes(pid: str, rid: str, body: ChangesIn, request: Request, admin: User = Depends(EDITOR)):
    """Turn attorney-requested changes into tracked items, each linked to the policy version it affects."""
    _super(admin)
    d = await db.review_packs.find_one({"_id": ObjectId(pid)}, {"files": 0}) if ObjectId.is_valid(pid) else None
    rec = next((r for r in (d or {}).get("attorney_records", []) if r["id"] == rid), None)
    if not rec:
        raise APIError(404, "not_found", "Attorney record not found.")
    now, docs = utcnow(), []
    for it in body.items:
        _slug(it.policy_slug)
        v = await db.policy_versions.find_one({"slug": it.policy_slug, "status": {"$in": ["draft", "pending_review", "approved"]}}, sort=[("version", -1)]) \
            or await db.policy_versions.find_one({"slug": it.policy_slug}, sort=[("version", -1)])
        docs.append({"policy_slug": it.policy_slug, "policy_title": pol.META[it.policy_slug]["title"], "version_id": v["_id"], "version": v["version"],
                     "clause": it.clause, "description": it.description, "status": "open", "pack_id": d["_id"], "pack_number": d.get("pack_number", 1),
                     "attorney_record_id": rid, "reviewer_name": rec["reviewer_name"], "created_by": admin.email, "created_at": now, "updated_at": now,
                     "history": [{"status": "open", "by": admin.email, "at": now, "note": "Created from attorney feedback"}]})
    res = await db.legal_change_requests.insert_many(docs)
    await audit("policy.attorney_changes_created", "legal_change_requests", request=request, actor=admin, entity_id=pid, record_id=rid, count=len(docs))
    return {"data": [_chg({**x, "_id": i}) for x, i in zip(docs, res.inserted_ids)]}


@router.get("/admin/policies/changes")
async def list_changes(slug: Optional[str] = None, status: Optional[str] = None, _: User = Depends(EDITOR)):
    q = {**({"policy_slug": _slug(slug)} if slug else {}), **({"status": status} if status in CHANGE_STATUSES else {})}
    docs = await db.legal_change_requests.find(q).sort([("status", 1), ("created_at", 1)]).to_list(500)
    counts = {s: await db.legal_change_requests.count_documents({**({"policy_slug": slug} if slug else {}), "status": s}) for s in CHANGE_STATUSES}
    return {"data": [_chg(x) for x in docs], "counts": counts}


class ChangeStatusIn(BaseModel):
    status: Literal["open", "in_progress", "done", "wont_do"]
    note: str = Field(default="", max_length=2000)


@router.put("/admin/policies/changes/{cid}")
async def update_change(cid: str, body: ChangeStatusIn, request: Request, admin: User = Depends(EDITOR)):
    d = await db.legal_change_requests.find_one({"_id": ObjectId(cid)}) if ObjectId.is_valid(cid) else None
    if not d:
        raise APIError(404, "not_found", "Change request not found.")
    if body.status in ("wont_do", "open") and d["status"] != body.status:
        _super(admin)
    if body.status in ("done", "wont_do") and len(body.note.strip()) < 5:
        raise APIError(422, "validation_error", "Explain how the change was handled (at least 5 characters).")
    now = utcnow()
    await db.legal_change_requests.update_one({"_id": d["_id"]}, {"$set": {"status": body.status, "updated_at": now, "resolution_note": body.note or d.get("resolution_note", "")},
                                                                  "$push": {"history": {"status": body.status, "by": admin.email, "at": now, "note": body.note}}})
    await audit(f"policy.attorney_change_{body.status}", "legal_change_requests", request=request, actor=admin, entity_id=cid, slug=d["policy_slug"], note=body.note)
    return _chg(await db.legal_change_requests.find_one({"_id": d["_id"]}))

