"""Policy Management: public published policies, user acceptance, and the admin draft → legal review → approval → publication workflow."""
from datetime import date, datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
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
            "change_summary": cur.get("change_summary", ""), "body": cur["body"]}


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
    return {"id": str(d["_id"]), "created_by": d["created_by"], "created_at": _iso(d["created_at"]), "sizes": d["sizes"],
            "policy_versions": d["policy_versions"], "external_sharing_approved": d.get("external_sharing_approved", False),
            "sharing_approved_by": d.get("sharing_approved_by"), "sharing_approved_at": _iso(d.get("sharing_approved_at")), "downloads": d.get("downloads", 0)}


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
           "external_sharing_approved": False, "downloads": 0}
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
    await db.review_packs.update_one({"_id": d["_id"]}, {"$inc": {"downloads": 1}})
    await audit("policy.review_pack_downloaded", "review_packs", request=request, actor=admin, entity_id=pid, format=format)
    name = f"AfroVending-Legal-Policy-Review-Pack-CONFIDENTIAL-{d['created_at']:%Y-%m-%d}.{format}"
    return Response(content=bytes(d["files"][format]), media_type=MIME[format],
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.post("/admin/policies/review-pack/{pid}/approve-sharing")
async def approve_sharing(pid: str, request: Request, admin: User = Depends(EDITOR)):
    _super(admin)
    r = await db.review_packs.update_one({"_id": ObjectId(pid)} if ObjectId.is_valid(pid) else {"_id": None},
                                         {"$set": {"external_sharing_approved": True, "sharing_approved_by": admin.email, "sharing_approved_at": utcnow()}})
    if not r.matched_count:
        raise APIError(404, "not_found", "Review pack not found.")
    await audit("policy.review_pack_sharing_approved", "review_packs", request=request, actor=admin, entity_id=pid)
    return {"ok": True}

