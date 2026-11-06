"""Marketing & monetization core: feature flags, first-party analytics, referral attribution, consent, abandoned-cart reminders."""
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from html import escape

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from afrovending.core import email as mail
from afrovending.core.audit import audit
from afrovending.core.config import settings
from afrovending.core.db import db
from afrovending.core.models import utcnow

log = logging.getLogger("afrovending.marketing")
FLAGS_KEY = "marketing.flags"
# Paid vendor subscriptions, sponsored listings and referral rewards are locked off in code until pricing/billing rules are approved by the owner.
LOCKED_OFF = ("paid_subscriptions_enabled", "sponsored_listings_enabled", "referral_rewards_enabled")
DEFAULT_FLAGS = {"paid_subscriptions_enabled": False, "sponsored_listings_enabled": False, "referral_rewards_enabled": False,
                 "abandoned_cart": {"enabled": False, "first_delay_min": 60, "second_delay_min": 1440, "max_per_7_days": 2},
                 "referral_rewards": {"referrer_reward_minor": None, "friend_reward_minor": None, "trigger": "first_paid_order"},
                 "analytics_retention_days": 400}
CLIENT_EVENTS = ("page_view", "product_view", "search", "add_to_cart", "begin_checkout")


async def flags() -> dict:
    doc = await db.platform_settings.find_one({"key": FLAGS_KEY})
    saved = (doc or {}).get("value") or {}
    out = {**DEFAULT_FLAGS, **saved, "abandoned_cart": {**DEFAULT_FLAGS["abandoned_cart"], **saved.get("abandoned_cart", {})}}
    for k in LOCKED_OFF:
        out[k] = False
    return out


async def save_flags(value: dict, actor_id) -> dict:
    await db.platform_settings.update_one({"key": FLAGS_KEY}, {"$set": {"value": value, "updated_at": utcnow(), "updated_by": actor_id},
                                                                "$setOnInsert": {"key": FLAGS_KEY, "created_at": utcnow()}}, upsert=True)
    return await flags()


async def track(type_: str, event_id: str, *, anon_id: str = "", user_id=None, path: str = "", product_id=None, vendor_id=None,
                query: str = "", value_minor: int = 0, order_id=None, referral_code: str = "") -> bool:
    """Idempotent by event_id. No names, emails, phones or addresses are ever stored here."""
    try:
        await db.analytics_events.insert_one({"type": type_, "event_id": event_id[:120], "anon_id": anon_id[:64], "user_id": user_id, "path": path[:300],
                                              "product_id": product_id, "vendor_id": vendor_id, "query": query[:120], "value_minor": value_minor,
                                              "order_id": order_id, "referral_code": referral_code[:20] or None, "created_at": utcnow()})
        return True
    except DuplicateKeyError:
        return False


def referral_code() -> str:
    return "AV" + secrets.token_hex(4).upper()


async def ensure_code(user_id) -> str:
    u = await db.users.find_one({"_id": user_id}, {"referral_code": 1})
    if u and u.get("referral_code"):
        return u["referral_code"]
    for _ in range(5):
        code = referral_code()
        try:
            await db.users.update_one({"_id": user_id, "referral_code": {"$exists": False}}, {"$set": {"referral_code": code}})
            break
        except DuplicateKeyError:
            continue
    return (await db.users.find_one({"_id": user_id}, {"referral_code": 1}))["referral_code"]


async def attribute_signup(new_user_id, code: str, email: str) -> None:
    """First-touch-at-signup policy: the code presented at registration wins; one referrer per customer, never yourself."""
    code = (code or "").strip().upper()[:20]
    if not code:
        return
    ref = await db.users.find_one({"referral_code": code}, {"_id": 1, "email": 1})
    if not ref or ref["_id"] == new_user_id or ref["email"].split("@")[-1] == email.split("@")[-1] and ref["email"].split("@")[0].split("+")[0] == email.split("@")[0].split("+")[0]:
        await audit("referral.rejected", "referrals", entity_id=str(new_user_id), reason="self_or_unknown")
        return
    try:
        await db.referrals.insert_one({"referrer_id": ref["_id"], "referred_id": new_user_id, "code": code, "status": "signed_up",
                                       "signed_up_at": utcnow(), "first_order_id": None, "first_order_value_minor": 0, "reward_status": "not_applicable"})
    except DuplicateKeyError:
        pass


async def on_paid(order: dict, payment: dict) -> None:
    """Server-side purchase event (once per order), referral first-order conversion (once per referred customer), stop cart reminders."""
    await track("purchase", f"purchase:{order['_id']}", user_id=order["customer_id"], value_minor=payment["amount_minor"], order_id=order["_id"])
    await db.referrals.update_one({"referred_id": order["customer_id"], "status": "signed_up", "first_order_id": None},
                                  {"$set": {"status": "converted", "first_order_id": order["_id"], "first_order_value_minor": payment["amount_minor"],
                                            "converted_at": utcnow()}})
    await db.cart_reminders.update_many({"cart_id": order.get("cart_id"), "status": "scheduled"}, {"$set": {"status": "cancelled", "cancel_reason": "checkout"}})


def unsubscribe_token(user_id) -> str:
    sig = hmac.new(settings.jwt_secret.encode(), f"unsub:{user_id}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{user_id}.{sig}"


def verify_unsubscribe(token: str):
    uid, _, sig = (token or "").partition(".")
    if not ObjectId.is_valid(uid) or not hmac.compare_digest(unsubscribe_token(uid), token):
        return None
    return ObjectId(uid)


async def set_consent(user_id, opted_in: bool, source: str) -> None:
    now = utcnow()
    await db.users.update_one({"_id": user_id}, {"$set": {"marketing_opt_in": opted_in, "marketing_consent_at" if opted_in else "marketing_withdrawn_at": now},
                                                 "$push": {"consent_log": {"$each": [{"marketing": opted_in, "source": source, "at": now}], "$slice": -50}}})
    if not opted_in:
        await db.cart_reminders.update_many({"user_id": user_id, "status": "scheduled"}, {"$set": {"status": "cancelled", "cancel_reason": "unsubscribed"}})


def _cart_html(name: str, lines: list[dict], link: str, unsub: str, step: int) -> tuple[str, str]:
    rows = "".join(f"<li>{escape(li['title'])} × {li['quantity']}</li>" for li in lines[:8])
    head = "You left something in your cart" if step == 1 else "Your cart is still waiting"
    body = (f"<p>Hi {escape(name)},</p><p>These items are still in your AfroVending cart:</p><ul>{rows}</ul>" + mail._button(link, "Return to your cart") +
            f'<p style="font-size:12px;color:#777">You get this because you opted in to AfroVending marketing emails. '
            f'<a href="{escape(unsub)}">Unsubscribe</a> at any time.</p>')
    return head, mail._layout(head, body)


async def run_abandoned_carts() -> dict:
    """Idempotent: one reminder document per (cart, abandonment version, step), claimed atomically before sending."""
    cfg = (await flags())["abandoned_cart"]
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    now, sent = utcnow(), 0
    oldest = now - timedelta(days=7)
    carts = await db.carts.find({"status": "active", "user_id": {"$ne": None}, "items.0": {"$exists": True},
                                 "updated_at": {"$lte": now - timedelta(minutes=cfg["first_delay_min"]), "$gte": oldest}}).to_list(500)
    for cart in carts:
        u = await db.users.find_one({"_id": cart["user_id"]})
        if not u or not u.get("marketing_opt_in") or u.get("status") != "active":
            continue
        idle = now - cart["updated_at"].replace(tzinfo=now.tzinfo)
        step = 2 if idle >= timedelta(minutes=cfg["second_delay_min"]) else 1
        version = cart["updated_at"].isoformat()
        if step == 2 and not await db.cart_reminders.find_one({"cart_id": cart["_id"], "version": version, "step": 1, "status": "sent"}):
            step = 1
        if await db.cart_reminders.count_documents({"user_id": u["_id"], "status": "sent", "sent_at": {"$gte": now - timedelta(days=7)}}) >= cfg["max_per_7_days"]:
            continue
        try:
            rid = (await db.cart_reminders.insert_one({"cart_id": cart["_id"], "user_id": u["_id"], "version": version, "step": step, "status": "sending",
                                                       "token": secrets.token_urlsafe(16), "created_at": now})).inserted_id
        except DuplicateKeyError:
            continue
        rem = await db.cart_reminders.find_one({"_id": rid})
        lines = await _lines(cart)
        link = f"{settings.frontend_url}/cart?utm_source=email&utm_campaign=abandoned_cart&r={rem['token']}"
        unsub = f"{settings.frontend_url}/unsubscribe?token={unsubscribe_token(u['_id'])}"
        subject, html = _cart_html(u.get("name") or "there", lines, link, unsub, step)
        ok = await mail.try_send(to=u["email"], subject=subject, html=html)
        await db.cart_reminders.update_one({"_id": rid}, {"$set": {"status": "sent" if ok else "failed", "sent_at": utcnow()}})
        sent += ok
    return {"sent": sent, "checked": len(carts)}


async def _lines(cart: dict) -> list[dict]:
    out = []
    for it in cart.get("items", []):
        v = await db.product_variants.find_one({"_id": it.get("variant_id")}, {"product_id": 1})
        p = await db.products.find_one({"_id": v["product_id"]}, {"title": 1}) if v else None
        if p:
            out.append({"title": p["title"], "quantity": it["quantity"]})
    return out
