import os

import stripe
from starlette.concurrency import run_in_threadpool

from afrovending.core.db import db
from afrovending.core.errors import APIError

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]
MODE = os.environ["STRIPE_MODE"]

DEFAULT_CONFIG = {"hold_days": 7, "tax_held_by": "platform", "allowed_countries": ["US"], "currencies": ["USD"],
                  "live_payments_enabled": False}


def is_live_key() -> bool:
    return stripe.api_key.startswith(("sk_live", "rk_live"))


async def get_config() -> dict:
    doc = await db.platform_settings.find_one({"key": "payments.config"})
    return {**DEFAULT_CONFIG, **((doc or {}).get("value") or {})}


async def guard() -> None:
    """Live payments stay disabled until an administrator explicitly approves them."""
    if (is_live_key() or MODE != "test") and not (await get_config())["live_payments_enabled"]:
        raise APIError(503, "payments_disabled", "Live payments are not enabled.")


async def call(fn, *args, **kwargs):
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except stripe.error.StripeError as e:
        raise APIError(502, "payment_provider_error", e.user_message or "The payment provider returned an error. Try again.")
