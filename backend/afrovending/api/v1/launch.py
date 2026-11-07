"""Launch Readiness Checklist (Super Admin) and Founding Vendor review. Recording statuses never changes DNS, payments, emails or launch state."""
import glob
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import httpx
from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from afrovending.core import founding
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.permissions import ADMIN_ROLE_VALUES, DASH, FIN_MANAGE, SETTINGS, perms_of, require_perm

router = APIRouter(prefix="/admin", tags=["launch"])
ADMIN = require_perm(DASH)
STATUSES = ("not_started", "in_progress", "verified", "blocked")
ITEMS = [  # key, label, mode, who may edit
    ("dns", "DNS and domain: afrovending.com and www resolve", "auto", SETTINGS),
    ("ssl", "SSL: both hosts serve AfroVending over valid HTTPS", "auto", SETTINGS),
    ("stripe_test", "Stripe test payments working (test mode)", "auto", FIN_MANAGE),
    ("live_payments", "Live payment readiness: Connect enabled, live keys and approval recorded", "manual", FIN_MANAGE),
    ("admin_mfa", "Every active administrator has MFA enrolled", "auto", SETTINGS),
    ("email_domain", "Resend sending domain verified (SPF, DKIM, DMARC)", "manual", SETTINGS),
    ("phase13_audit", "Phase 13 audit cleared and launch blockers resolved", "manual", SETTINGS),
    ("marketplace_testing", "Buyer, vendor and admin end-to-end testing passed", "manual", SETTINGS),
    ("backup_rollback", "Verified backup and restore drill within 7 days, rollback plan ready", "auto", SETTINGS),
    ("final_approval", "Final launch approval (Super Admin)", "final", SETTINGS),
]
BY_KEY = {k: (label, mode, perm) for k, label, mode, perm in ITEMS}
LAUNCH_CONFIRM = "RECORD PUBLIC LAUNCH"


def _iso(d):
    return d.isoformat() if isinstance(d, datetime) else d


def _can(user: User, key: str) -> bool:
    p = perms_of(user.roles)
    return SETTINGS in p or (BY_KEY[key][2] == FIN_MANAGE and FIN_MANAGE in p)


def _viewer(user: User):
    if not ({SETTINGS, FIN_MANAGE} & perms_of(user.roles)):
        raise APIError(403, "forbidden", "Only the Super Admin and Finance Admins can view the launch checklist.")


async def _items() -> list[dict]:
    docs = {d["key"]: d async for d in db.launch_checklist.find({})}
    out = []
    for k, label, mode, perm in ITEMS:
        d = docs.get(k, {})
        out.append({"key": k, "label": label, "mode": mode, "editable_by": "finance_or_super" if perm == FIN_MANAGE else "super_admin",
                    "status": d.get("status", "not_started"), "evidence": d.get("evidence", ""), "note": d.get("note", ""),
                    "updated_by": d.get("updated_by"), "updated_at": _iso(d.get("updated_at")), "verified_by": d.get("verified_by"), "verified_at": _iso(d.get("verified_at")),
                    "history": [{**h, "at": _iso(h.get("at"))} for h in d.get("history", [])[-5:]]})
    return out


async def _set(key: str, status: str, evidence: str, note: str, actor: User, request: Request, source: str):
    now = utcnow()
    upd = {"key": key, "status": status, "evidence": evidence[:2000], "note": note[:500], "updated_by": actor.email, "updated_at": now, "source": source}
    upd.update({"verified_by": actor.email, "verified_at": now} if status == "verified" else {"verified_by": None, "verified_at": None})
    await db.launch_checklist.update_one({"key": key}, {"$set": upd, "$push": {"history": {"$each": [{"status": status, "by": actor.email, "at": now, "source": source,
                                                                                                    "evidence": evidence[:300]}], "$slice": -50}}}, upsert=True)
    await audit("launch.checklist_updated", "launch_checklist", request=request, actor=actor, entity_id=key, status=status, source=source)
    if key != "final_approval" and status != "verified":
        fin = await db.launch_checklist.find_one({"key": "final_approval"})
        if fin and fin.get("status") == "verified":
            await _set("final_approval", "in_progress", fin.get("evidence", ""), f"Reopened: '{key}' is no longer verified.", actor, request, "system")


@router.get("/launch/checklist")
async def checklist(admin: User = Depends(ADMIN)):
    _viewer(admin)
    items = await _items()
    launch = ((await db.platform_settings.find_one({"key": founding.LAUNCH_KEY})) or {}).get("value")
    return {"items": items, "verified": sum(i["status"] == "verified" for i in items), "total": len(items),
            "public_launch": {k: _iso(v) for k, v in launch.items()} if launch else None,
            "can_edit": [i["key"] for i in items if _can(admin, i["key"])], "is_super_admin": "super_admin" in admin.roles,
            "safety": "Completing items never changes DNS, enables live payments, sends emails or launches the marketplace."}


class ItemIn(BaseModel):
    status: Literal["not_started", "in_progress", "verified", "blocked"]
    evidence: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=500)


@router.put("/launch/checklist/{key}")
async def update_item(key: str, body: ItemIn, request: Request, admin: User = Depends(ADMIN)):
    if key not in BY_KEY:
        raise APIError(404, "not_found", "Unknown checklist item.")
    if not _can(admin, key):
        raise APIError(403, "forbidden", "You can't update this checklist item.")
    mode = BY_KEY[key][1]
    if body.status == "verified":
        if mode == "auto":
            raise APIError(422, "auto_only", "This item is verified by the automatic check. Use “Run check”.")
        if len(body.evidence.strip()) < 10:
            raise APIError(422, "validation_error", "Add supporting evidence (at least 10 characters) before marking this verified.")
        if mode == "final":
            if "super_admin" not in admin.roles:
                raise APIError(403, "forbidden", "Only the Super Admin can give final launch approval.")
            pending = [i["label"] for i in await _items() if i["key"] != key and i["status"] != "verified"]
            if pending:
                raise APIError(409, "checklist_incomplete", f"{len(pending)} item(s) still need verification first.")
    await _set(key, body.status, body.evidence, body.note, admin, request, "manual")
    return {"items": await _items()}


async def _check(key: str) -> tuple[str, str]:
    if key == "dns":
        out = []
        async with httpx.AsyncClient(timeout=10) as c:
            for h in ("afrovending.com", "www.afrovending.com"):
                d = (await c.get("https://dns.google/resolve", params={"name": h, "type": "A"})).json()
                ans = [a["data"] for a in d.get("Answer", [])]
                out.append((h, d.get("Status"), ans))
        ok = all(s == 0 and a for _, s, a in out)
        return ("verified" if ok else "blocked"), "; ".join(f"{h}: status {s}, answers {a or 'none'}" for h, s, a in out)
    if key == "ssl":
        notes, ok = [], True
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            for url in ("https://afrovending.com/api/v1/health", "https://www.afrovending.com/api/v1/health"):
                try:
                    r = await c.get(url)
                    good = r.status_code == 200 and str(r.json().get("service", "")).startswith("AfroVending")
                    notes.append(f"{url}: HTTP {r.status_code}{' (AfroVending)' if good else ' (not this app)'}")
                    ok &= good
                except Exception as e:
                    notes.append(f"{url}: {type(e).__name__}")
                    ok = False
        return ("verified" if ok else "blocked"), "; ".join(notes)
    if key == "stripe_test":
        import stripe

        from afrovending.core.stripe_client import MODE, call, is_live_key
        if is_live_key() or MODE != "test":
            return "blocked", "A live key or non-test mode is configured in this environment."
        try:
            await call(stripe.Balance.retrieve)
        except APIError as e:
            return "blocked", f"Stripe test API error: {e.message}"
        paid = await db.payments.count_documents({"status": "paid"})
        return "verified", f"Stripe test API reachable (test mode). Paid test payments on record: {paid}."
    if key == "admin_mfa":
        admins = await db.users.find({"roles": {"$in": list(ADMIN_ROLE_VALUES)}, "status": "active"}, {"email": 1, "mfa_enabled_at": 1}).to_list(500)
        missing = [a["email"] for a in admins if not a.get("mfa_enabled_at")]
        if not admins:
            return "blocked", "No active administrators found."
        return ("verified", f"All {len(admins)} active administrators enrolled.") if not missing else ("blocked", f"{len(missing)} of {len(admins)} not enrolled: {', '.join(missing[:10])}")
    if key == "backup_rollback":
        files = sorted(glob.glob(os.path.join(os.environ.get("BACKUP_DIR", "/app/backups"), "*.archive.gz.restore.json")), key=os.path.getmtime, reverse=True)
        if not files:
            return "not_started", "No restore drill result found. Run scripts/backup_db.sh then scripts/restore_verify.sh."
        res = json.load(open(files[0]))
        age = datetime.now(timezone.utc) - datetime.fromisoformat(res["checked_at"])
        ok = res.get("restore_check") == "PASS" and age < timedelta(days=7)
        return ("verified" if ok else "blocked"), f"{os.path.basename(files[0])}: {res.get('restore_check')}, {res.get('documents')} documents, {age.days} day(s) old. Rollback plan: docs/PHASE14_MIGRATION_PLAN.md §6."
    raise APIError(422, "manual_only", "This item needs documented manual verification.")


@router.post("/launch/checklist/{key}/check")
async def run_check(key: str, request: Request, admin: User = Depends(ADMIN)):
    if key not in BY_KEY or BY_KEY[key][1] != "auto":
        raise APIError(422, "manual_only", "This item needs documented manual verification.")
    if not _can(admin, key):
        raise APIError(403, "forbidden", "You can't update this checklist item.")
    status, evidence = await _check(key)
    await _set(key, status, f"[automatic check] {evidence}", "", admin, request, "auto")
    return {"status": status, "evidence": evidence, "items": await _items()}


class LaunchIn(BaseModel):
    confirm: str = Field(max_length=40)
    launched_at: Optional[datetime] = None
    reason: str = Field(default="", max_length=300)


@router.post("/launch/public-launch")
async def record_launch(body: LaunchIn, request: Request, admin: User = Depends(require_perm(SETTINGS))):
    """Records the officially approved public launch timestamp (used for Founding Vendor eligibility). Triggers nothing else."""
    if body.confirm != LAUNCH_CONFIRM:
        raise APIError(422, "validation_error", f"Type “{LAUNCH_CONFIRM}” to confirm.")
    fin = await db.launch_checklist.find_one({"key": "final_approval"})
    if not fin or fin.get("status") != "verified":
        raise APIError(409, "not_approved", "Final launch approval must be verified before recording the public launch.")
    existing = await db.platform_settings.find_one({"key": founding.LAUNCH_KEY})
    if existing and len(body.reason.strip()) < 5:
        raise APIError(409, "already_recorded", "The launch is already recorded. Give a reason to correct it.")
    at = body.launched_at or utcnow()
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    if at > utcnow() + timedelta(minutes=5):
        raise APIError(422, "validation_error", "The launch time can't be in the future.")
    value = {"launched_at": at, "recorded_by": admin.email, "recorded_at": utcnow(), "reason": body.reason}
    await db.platform_settings.update_one({"key": founding.LAUNCH_KEY}, {"$set": {"value": value, "updated_at": utcnow()}}, upsert=True)
    await audit("launch.public_launch_recorded", "platform_settings", request=request, actor=admin, launched_at=at.isoformat(), correction=bool(existing))
    return {"public_launch": {k: _iso(v) for k, v in value.items()}}


@router.get("/founding-vendors")
async def founding_review(admin: User = Depends(require_perm(SETTINGS))):
    launched = await founding.launch_at()
    vendors = await db.vendors.find({}, {"name": 1, "slug": 1, "status": 1, "approved_at": 1, "founding_override": 1, "owner_user_id": 1}).sort("approved_at", 1).to_list(1000)
    emails = {u["_id"]: u["email"] async for u in db.users.find({"_id": {"$in": [v["owner_user_id"] for v in vendors]}}, {"email": 1})}
    rows = []
    for v in vendors:
        ok, reason = founding.eligibility(v, launched, emails.get(v["owner_user_id"], ""))
        ov = v.get("founding_override")
        rows.append({"vendor_id": str(v["_id"]), "name": v["name"], "slug": v["slug"], "status": v["status"], "approved_at": _iso(v.get("approved_at")),
                     "eligible": ok, "reason": reason, "override": {**ov, "at": _iso(ov.get("at"))} if ov else None})
    window_end = launched + timedelta(days=founding.FOUNDING_DAYS) if launched else None
    return {"launched_at": _iso(launched), "window_ends_at": _iso(window_end), "vendors": rows}


class OverrideIn(BaseModel):
    value: Optional[bool] = None
    reason: str = Field(min_length=5, max_length=300)


@router.put("/founding-vendors/{vendor_id}")
async def founding_override(vendor_id: str, body: OverrideIn, request: Request, admin: User = Depends(require_perm(SETTINGS))):
    if not ObjectId.is_valid(vendor_id):
        raise APIError(404, "not_found", "Vendor not found.")
    ov = None if body.value is None else {"value": body.value, "reason": body.reason, "by": admin.email, "at": utcnow()}
    r = await db.vendors.update_one({"_id": ObjectId(vendor_id)}, {"$set": {"founding_override": ov}})
    if not r.matched_count:
        raise APIError(404, "not_found", "Vendor not found.")
    await audit("vendor.founding_override", "vendors", request=request, actor=admin, entity_id=vendor_id, value=body.value, reason=body.reason)
    return {"ok": True}
