"""Managed legal policies: versioned drafts, Super Admin legal approval and publication, and user acceptance records."""
from bson import ObjectId

from afrovending.core.config import settings
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow

POLICIES = [  # slug, title, public path, who must accept it
    ("terms", "Terms of Service", "/terms", "customer"),
    ("privacy", "Privacy Policy", "/privacy", "customer"),
    ("vendor_agreement", "Vendor Agreement", "/vendor-agreement", "vendor"),
    ("shipping", "Shipping & Delivery Policy", "/shipping-policy", None),
    ("returns", "Returns & Refunds Policy", "/returns-policy", None),
    ("cookies", "Cookie Policy", "/cookie-policy", None),
    ("prohibited", "Prohibited Products Policy", "/prohibited-products", "vendor"),
]
META = {s: {"slug": s, "title": t, "path": p, "acceptance": a} for s, t, p, a in POLICIES}
CUSTOMER = ["terms", "privacy"]
VENDOR = ["vendor_agreement", "prohibited"]
REQUIRED = {"registration": CUSTOMER, "vendor": VENDOR, "checkout": ["terms", "privacy", "shipping", "returns"], "personal_info": ["privacy"]}
STATUSES = ("draft", "pending_review", "approved", "published", "archived")


async def published(slug: str):
    return await db.policy_versions.find_one({"slug": slug, "status": "published"})


async def missing(group: str) -> list[str]:
    out = []
    for slug in REQUIRED[group]:
        if not await published(slug):
            out.append(META[slug]["title"])
    return out


async def gate(group: str) -> None:
    """In production, activities needing legal disclosures stay closed until the required policies are approved and published."""
    if not settings.is_production:
        return
    gone = await missing(group)
    if gone:
        raise APIError(503, "policies_unavailable", f"This isn't available yet: {', '.join(gone)} must be published first.")


async def required_version(slug: str):
    """Highest published-at-some-point version that requires (re)acceptance; the first publication always does."""
    doc = await db.policy_versions.find_one({"slug": slug, "published_at": {"$ne": None}, "requires_reacceptance": True}, sort=[("version", -1)])
    return doc["version"] if doc else None


async def pending_for(user_id, slugs: list[str]) -> list[dict]:
    out = []
    for slug in slugs:
        need = await required_version(slug)
        if need is None:
            continue
        last = await db.policy_acceptances.find_one({"user_id": ObjectId(str(user_id)), "slug": slug}, sort=[("version", -1)])
        if last and last["version"] >= need:
            continue
        cur = await published(slug)
        if cur:
            out.append({"slug": slug, "title": META[slug]["title"], "path": META[slug]["path"], "version": cur["version"], "version_id": str(cur["_id"]),
                        "change_summary": cur.get("change_summary", ""), "effective_date": cur.get("effective_date")})
    return out


def slugs_for(roles: list[str]) -> list[str]:
    return CUSTOMER + (VENDOR if "vendor" in roles else [])


async def record(user_id, slugs: list[str], context: str, request=None) -> list[dict]:
    from afrovending.core.security import client_ip
    rows = []
    for slug in slugs:
        cur = await published(slug)
        if not cur:
            continue
        rows.append({"user_id": ObjectId(str(user_id)), "slug": slug, "version": cur["version"], "version_id": cur["_id"], "title": META[slug]["title"],
                     "effective_date": cur.get("effective_date"), "context": context, "accepted_at": utcnow(),
                     "ip": client_ip(request) if request else None, "user_agent": request.headers.get("user-agent", "")[:200] if request else None})
    if rows:
        await db.policy_acceptances.insert_many(rows)
    return rows


async def assert_accepted(user_id, slugs: list[str], who: str = "you") -> None:
    pend = await pending_for(user_id, slugs)
    if pend:
        names = ", ".join(f"{p['title']} (v{p['version']})" for p in pend)
        msg = f"Please review and accept the updated {names} to continue." if who == "you" else f"This seller can't take new orders right now ({who})."
        raise APIError(409, "policy_acceptance_required", msg, [{"field": p["slug"], "message": p["title"]} for p in pend])


async def label(slugs: list[str]) -> str:
    parts = []
    for s in slugs:
        cur = await published(s)
        parts.append(f"{s}-v{cur['version']}" if cur else f"{s}-unpublished")
    return "+".join(parts)



async def assert_vendors_ready(vendor_ids) -> None:
    """Vendors with an outstanding material Vendor Agreement / Prohibited Products acceptance can't take new orders."""
    for v in await db.vendors.find({"_id": {"$in": list(vendor_ids)}}, {"owner_user_id": 1, "name": 1}).to_list(200):
        if await pending_for(v["owner_user_id"], VENDOR):
            raise APIError(409, "vendor_unavailable", f"{v.get('name', 'A seller')} can't take new orders right now. Remove their items to continue.")


async def checkout_ready(user_id, vendor_ids) -> None:
    await gate("checkout")
    await assert_accepted(user_id, CUSTOMER)
    await assert_vendors_ready(vendor_ids)
