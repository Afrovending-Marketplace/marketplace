"""Live-order gate. Production (or any live-key/live-mode environment) refuses new orders until every payment-readiness item is
Verified and the Super Admin activates orders with a fresh MFA code. The emergency stop pauses new orders everywhere, immediately."""
from afrovending.core.config import settings
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.stripe_client import MODE, is_live_key

KEY = "orders.live"
PAYMENT_ITEMS = [  # key, label
    ("pay_stripe_live", "Stripe account claimed and live payment processing configured"),
    ("pay_connect", "Stripe Connect enabled and vendor onboarding operational"),
    ("pay_payouts_real", "Vendor transfers and payouts verified with real (not simulated) connected accounts"),
    ("pay_auth_capture", "Payment authorization and capture tested"),
    ("pay_refunds", "Refunds, partial refunds, chargebacks and reversals tested"),
    ("pay_fees", "Commission and Stripe processing fee calculations verified"),
    ("pay_ledger", "Multi-vendor checkout and financial ledger reconciliation tested"),
    ("pay_webhooks", "Stripe webhook signatures, retries and idempotency verified"),
    ("pay_inventory", "Inventory reservation and overselling protections verified"),
    ("super_admin_mfa", "Super Admin MFA enabled"),
]
PAYMENT_KEYS = [k for k, _ in PAYMENT_ITEMS]


def live_environment() -> bool:
    return settings.is_production or is_live_key() or MODE != "test"


async def state() -> dict:
    return ((await db.platform_settings.find_one({"key": KEY})) or {}).get("value") or {"enabled": False, "paused": False}


async def blockers() -> list[str]:
    docs = {d["key"]: d.get("status") async for d in db.launch_checklist.find({"key": {"$in": PAYMENT_KEYS}})}
    return [label for k, label in PAYMENT_ITEMS if docs.get(k) != "verified"]


async def accepting() -> tuple[bool, str]:
    s = await state()
    if s.get("paused"):
        return False, "New orders are paused right now. You can keep browsing and saving items to your wishlist."
    if not live_environment():
        return True, ""
    if not s.get("enabled") or await blockers():
        return False, "AfroVending isn't taking orders yet. You can browse and save items to your wishlist — checkout opens soon."
    return True, ""


async def assert_accepting() -> None:
    ok, msg = await accepting()
    if not ok:
        raise APIError(503, "orders_closed", msg)
