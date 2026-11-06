import re
import secrets
from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from afrovending.core import rate_limit
from afrovending.core.audit import audit
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow
from afrovending.core.permissions import TICKETS, perms_of, require_perm

router = APIRouter(tags=["support"])
STAFF = require_perm(TICKETS)
Category = Literal["order_issue", "delivery", "refund", "payment", "product", "account", "other"]
Status = Literal["open", "in_progress", "waiting_for_customer", "resolved", "closed"]
Priority = Literal["low", "normal", "high", "urgent"]
Queue = Literal["support", "marketplace", "finance"]
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(s: str) -> str:
    return _CTRL.sub("", s).strip()


class TicketIn(BaseModel):
    category: Category
    subject: str = Field(min_length=4, max_length=140)
    body: str = Field(min_length=10, max_length=5000)
    order_number: Optional[str] = Field(default=None, max_length=40)


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class StaffReplyIn(ReplyIn):
    internal: bool = False


class PatchIn(BaseModel):
    status: Optional[Status] = None
    priority: Optional[Priority] = None
    queue: Optional[Queue] = None
    assigned_to: Optional[str] = Field(default=None, max_length=40)
    note: str = Field(default="", max_length=300)


def _out(t: dict, staff: bool) -> dict:
    msgs = [m for m in t["messages"] if staff or not m.get("internal")]
    return {"id": str(t["_id"]), "reference": t["reference"], "category": t["category"], "subject": t["subject"], "status": t["status"],
            "priority": t["priority"], "queue": t["queue"], "order_number": t.get("order_number"), "created_at": t["created_at"], "updated_at": t["updated_at"],
            "assigned_to": str(t["assigned_to"]) if t.get("assigned_to") else None, "assigned_name": t.get("assigned_name"),
            "messages": [{"author": m["name"], "role": m["role"], "body": m["body"], "at": m["at"], "internal": m.get("internal", False)} for m in msgs],
            **({"customer_email": t.get("customer_email"), "history": [{**h, "by": str(h["by"]) if h.get("by") else None} for h in t.get("history", [])]} if staff else {})}


async def _notify(user_id, headline: str, text: str, path: str) -> None:
    from afrovending.core.notify import notify
    await notify(user_id, "support", headline, text, path)


async def _mine(ticket_id: str, user: User) -> dict:
    t = await db.support_tickets.find_one({"_id": ObjectId(ticket_id), "customer_id": ObjectId(user.id)}) if ObjectId.is_valid(ticket_id) else None
    if not t:
        raise APIError(404, "not_found", "Ticket not found.")
    return t


@router.post("/support/tickets", status_code=201)
async def create(body: TicketIn, request: Request, user: User = Depends(get_current_user)):
    await rate_limit.hit(f"ticket:{user.id}", 10, 3600)
    order = None
    if body.order_number:
        order = await db.orders.find_one({"order_number": body.order_number.strip(), "customer_id": ObjectId(user.id)})
        if not order:
            raise APIError(422, "validation_error", "We couldn't find that order on your account.")
    now = utcnow()
    queue = "finance" if body.category in ("refund", "payment") else "support"
    t = {"reference": f"AVT-{secrets.token_hex(3).upper()}", "customer_id": ObjectId(user.id), "customer_email": user.email, "category": body.category,
         "subject": clean(body.subject), "status": "open", "priority": "normal", "queue": queue, "order_id": order["_id"] if order else None,
         "order_number": order["order_number"] if order else None, "assigned_to": None,
         "messages": [{"author_id": ObjectId(user.id), "role": "customer", "name": user.name, "body": clean(body.body), "at": now}],
         "history": [{"at": now, "by": ObjectId(user.id), "change": "created"}], "created_at": now, "updated_at": now}
    t["_id"] = (await db.support_tickets.insert_one(t)).inserted_id
    await _notify(t["customer_id"], "We've received your request", f"Your ticket {t['reference']} (\u201c{t['subject']}\u201d) is open. We'll reply by email.",
                  f"/account/support/{t['_id']}")
    await audit("support.ticket_created", "support_tickets", request=request, actor=user, entity_id=str(t["_id"]), category=body.category)
    return _out(t, False)


@router.get("/support/tickets")
async def my_tickets(user: User = Depends(get_current_user)):
    docs = await db.support_tickets.find({"customer_id": ObjectId(user.id)}).sort("updated_at", -1).to_list(200)
    return {"data": [_out(t, False) for t in docs]}


@router.get("/support/tickets/{ticket_id}")
async def my_ticket(ticket_id: str, user: User = Depends(get_current_user)):
    return _out(await _mine(ticket_id, user), False)


@router.post("/support/tickets/{ticket_id}/replies")
async def customer_reply(ticket_id: str, body: ReplyIn, user: User = Depends(get_current_user)):
    t = await _mine(ticket_id, user)
    if t["status"] == "closed":
        raise APIError(409, "invalid_state", "This ticket is closed. Please open a new one.")
    now = utcnow()
    status = "open" if t["status"] in ("waiting_for_customer", "resolved") else t["status"]
    await db.support_tickets.update_one({"_id": t["_id"]}, {"$push": {"messages": {"author_id": ObjectId(user.id), "role": "customer", "name": user.name,
                                                                                    "body": clean(body.body), "at": now},
                                                                       "history": {"at": now, "by": ObjectId(user.id), "change": f"customer replied; status {status}"}},
                                                             "$set": {"status": status, "updated_at": now}})
    return _out(await db.support_tickets.find_one({"_id": t["_id"]}), False)


@router.get("/admin/support/tickets")
async def staff_list(status: Optional[Status] = None, category: Optional[Category] = None, priority: Optional[Priority] = None,
                     queue: Optional[Queue] = None, assigned_to: Optional[str] = None,
                     created_from: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                     created_to: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"), _: User = Depends(STAFF)):
    from afrovending.core.reports import et_bounds
    q = {k: v for k, v in (("status", status), ("category", category), ("priority", priority), ("queue", queue)) if v}
    if assigned_to:
        if assigned_to != "none" and not ObjectId.is_valid(assigned_to):
            raise APIError(422, "validation_error", "Unknown administrator.")
        q["assigned_to"] = None if assigned_to == "none" else ObjectId(assigned_to)
    if created_from or created_to:
        a, _b = et_bounds(datetime.fromisoformat(created_from or "2000-01-01").date(), datetime.fromisoformat(created_to or "2100-01-01").date())
        q["created_at"] = {"$gte": a, "$lt": _b}
    docs = await db.support_tickets.find(q).sort([("updated_at", -1)]).to_list(500)
    return {"data": [_out(t, True) for t in docs]}


async def _staff_ticket(ticket_id: str) -> dict:
    t = await db.support_tickets.find_one({"_id": ObjectId(ticket_id)}) if ObjectId.is_valid(ticket_id) else None
    if not t:
        raise APIError(404, "not_found", "Ticket not found.")
    return t


@router.get("/admin/support/tickets/{ticket_id}")
async def staff_get(ticket_id: str, _: User = Depends(STAFF)):
    return _out(await _staff_ticket(ticket_id), True)


@router.post("/admin/support/tickets/{ticket_id}/replies")
async def staff_reply(ticket_id: str, body: StaffReplyIn, request: Request, admin: User = Depends(STAFF)):
    t = await _staff_ticket(ticket_id)
    now = utcnow()
    sets = {"updated_at": now}
    if not body.internal and t["status"] in ("open", "in_progress"):
        sets["status"] = "waiting_for_customer"
    await db.support_tickets.update_one({"_id": t["_id"]}, {"$push": {"messages": {"author_id": ObjectId(admin.id), "role": "staff", "name": f"{admin.name} (AfroVending)",
                                                                                    "body": clean(body.body), "at": now, "internal": body.internal},
                                                                       "history": {"at": now, "by": ObjectId(admin.id), "change": "internal note" if body.internal else "staff replied"}},
                                                             "$set": sets})
    if not body.internal:
        await _notify(t["customer_id"], f"New reply on {t['reference']}", f"AfroVending support replied to \u201c{t['subject']}\u201d. Open the ticket to read and respond.",
                      f"/account/support/{t['_id']}")
    await audit("support.ticket_replied", "support_tickets", request=request, actor=admin, entity_id=ticket_id, internal=body.internal)
    return _out(await db.support_tickets.find_one({"_id": t["_id"]}), True)


@router.patch("/admin/support/tickets/{ticket_id}")
async def staff_patch(ticket_id: str, body: PatchIn, request: Request, admin: User = Depends(STAFF)):
    """Status changes never trigger refunds, cancellations or transfers \u2014 those stay in their own permissioned workflows."""
    t = await _staff_ticket(ticket_id)
    sets, changes = {"updated_at": utcnow()}, []
    for k in ("status", "priority", "queue"):
        v = getattr(body, k)
        if v and v != t[k]:
            sets[k] = v
            changes.append(f"{k}: {t[k]} \u2192 {v}")
    if body.assigned_to is not None:
        if body.assigned_to == "":
            sets["assigned_to"], sets["assigned_name"] = None, None
            changes.append("unassigned")
        else:
            u = await db.users.find_one({"_id": ObjectId(body.assigned_to), "status": "active"}) if ObjectId.is_valid(body.assigned_to) else None
            if not u or TICKETS not in perms_of(u.get("roles", [])):
                raise APIError(422, "validation_error", "Tickets can only be assigned to an active admin who handles tickets.")
            sets["assigned_to"], sets["assigned_name"] = u["_id"], u.get("name")
            changes.append(f"assigned to {u.get('name')}")
    if not changes:
        return _out(t, True)
    await db.support_tickets.update_one({"_id": t["_id"]}, {"$set": sets, "$push": {"history": {"at": utcnow(), "by": ObjectId(admin.id), "change": "; ".join(changes),
                                                                                                  "note": clean(body.note)}}})
    if "status" in sets and sets["status"] in ("resolved", "closed", "waiting_for_customer"):
        await _notify(t["customer_id"], f"Ticket {t['reference']} updated", f"Your ticket is now {sets['status'].replace('_', ' ')}.", f"/account/support/{t['_id']}")
    await audit("support.ticket_updated", "support_tickets", request=request, actor=admin, entity_id=ticket_id, changes=changes, escalated="queue" in sets)
    return _out(await db.support_tickets.find_one({"_id": t["_id"]}), True)
