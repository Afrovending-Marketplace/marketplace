"""Founding Vendor badge: approved within 30 days after the recorded public launch, active, not a test account. Cosmetic only (no fee/ranking effect)."""
from datetime import timedelta

from afrovending.core.db import db

FOUNDING_DAYS = 30
LAUNCH_KEY = "launch.public"
TEST_DOMAINS = ("example.com", "example.org", "example.net", "test.com", "afrovending.test")


def _naive(d):
    return d.replace(tzinfo=None) if d and d.tzinfo else d


async def launch_at():
    return _naive(((await db.platform_settings.find_one({"key": LAUNCH_KEY})) or {}).get("value", {}).get("launched_at"))


def is_test_email(email: str) -> bool:
    e = (email or "").lower()
    return e.split("@")[-1] in TEST_DOMAINS or e.startswith(("test", "qa"))


def eligibility(v: dict, launched, owner_email: str) -> tuple[bool, str]:
    ov = v.get("founding_override") or {}
    if v.get("status") != "active":
        return False, "Vendor is not active (suspended or terminated)."
    if ov.get("value") is False:
        return False, f"Removed by admin: {ov.get('reason', '')}"
    if is_test_email(owner_email):
        return False, "Test account."
    if ov.get("value") is True:
        return True, f"Granted by admin correction: {ov.get('reason', '')}"
    if not launched:
        return False, "Public launch date not recorded yet."
    approved = _naive(v.get("approved_at"))
    if approved and launched <= approved < launched + timedelta(days=FOUNDING_DAYS):
        return True, "Approved within 30 days of public launch."
    return False, "Approved outside the founding window."


async def founding_ids(vendor_ids: list) -> set:
    if not vendor_ids:
        return set()
    launched = await launch_at()
    vendors = await db.vendors.find({"_id": {"$in": vendor_ids}}, {"status": 1, "approved_at": 1, "founding_override": 1, "owner_user_id": 1}).to_list(len(vendor_ids))
    emails = {u["_id"]: u["email"] async for u in db.users.find({"_id": {"$in": [v["owner_user_id"] for v in vendors]}}, {"email": 1})}
    return {v["_id"] for v in vendors if eligibility(v, launched, emails.get(v["owner_user_id"], ""))[0]}
