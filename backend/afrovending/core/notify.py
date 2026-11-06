"""One entry point for user notifications: in-app record + optional branded email, honouring each user's preferences."""
import logging

from bson import ObjectId

from afrovending.core import email as mail
from afrovending.core.db import db
from afrovending.core.models import utcnow

logger = logging.getLogger("afrovending.notify")
CATEGORIES = {"orders": "Order updates", "messages": "Order messages", "reviews": "Reviews and vendor responses",
              "support": "Support tickets", "vendor": "Vendor account and applications"}
TEST_DOMAINS = ("example.com", "example.org", "example.net", "test.afrovending.dev")


def prefs_of(user: dict) -> dict:
    saved = user.get("notification_prefs") or {}
    return {c: {"email": bool(saved.get(c, {}).get("email", True)), "in_app": bool(saved.get(c, {}).get("in_app", True))} for c in CATEGORIES}


def is_test_address(addr: str) -> bool:
    dom = addr.lower().rsplit("@", 1)[-1]
    return any(dom == d or dom.endswith("." + d) for d in TEST_DOMAINS)


async def notify(user_id, category: str, headline: str, text: str, path: str, *, email: bool = True,
                 email_content: tuple[str, str] | None = None, in_app: bool = True) -> bool:
    """Returns True when nothing failed (email skipped by preference/test address counts as success)."""
    u = await db.users.find_one({"_id": ObjectId(user_id) if isinstance(user_id, str) else user_id})
    if not u:
        return True
    p = prefs_of(u)[category]
    status = "not_requested"
    if email and not p["email"]:
        status = "disabled_by_preference"
    elif email and is_test_address(u["email"]):
        status = "suppressed_test_address"
    elif email:
        subject, html = email_content or mail.payment_notice_email(u.get("first_name") or u.get("name") or "there", headline, text, path)
        status = "sent" if await mail.try_send(to=u["email"], subject=subject, html=html) else "failed"
    if in_app and p["in_app"]:
        await db.notifications.insert_one({"user_id": u["_id"], "category": category, "title": headline[:140], "body": text[:600], "link": path,
                                           "status": "unread", "email_status": status, "created_at": utcnow()})
    if status == "failed":
        logger.warning("notification email failed (category=%s)", category)
    return status != "failed"
