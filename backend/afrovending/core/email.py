"""Transactional email via AfroVending's own Resend account. Bodies come only from the server-side templates below."""
import asyncio
import hashlib
import ipaddress
import logging
import os
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from afrovending.core.config import settings

logger = logging.getLogger("afrovending.email")

RESEND_URL = "https://api.resend.com/emails"
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")
EMAIL_DOMAIN = os.environ.get("EMAIL_DOMAIN", "afrovending.com")
SENDERS = {"orders": "orders", "vendors": "vendors", "security": "security", "notifications": "notifications", "alerts": "alerts"}
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _key() -> str:
    return (os.environ.get("RESEND_API_KEY") or "").strip()


def sending_enabled() -> bool:
    return os.environ.get("EMAIL_SENDING_ENABLED", "false").lower() == "true"


def sender_for(subject: str) -> str:
    s = subject.lower()
    if "[afrovending alert]" in s:
        return "alerts"
    if any(w in s for w in ("verify", "password", "security", "sign-in", "mfa", "invite", "admin")):
        return "security"
    if any(w in s for w in ("vendor", "low-stock", "payout", "statement", "application")):
        return "vendors"
    if any(w in s for w in ("order", "receipt", "pickup", "refund", "ship", "deliver", "cancel")):
        return "orders"
    return "notifications"


def _from_address(category: str) -> str:
    override = (os.environ.get("EMAIL_SENDER_OVERRIDE") or "").strip()
    return f"{EMAIL_FROM_NAME} <{override or SENDERS[category] + '@' + EMAIL_DOMAIN}>"

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan(); scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)")


def _mask(addr: str) -> str:
    user, _, dom = addr.partition("@")
    return f"{user[:2]}***@{dom}"


async def _post(payload: dict, idem: str) -> httpx.Response:
    headers = {"Authorization": f"Bearer {_key()}", "Idempotency-Key": idem}
    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(3):
            resp = await client.post(RESEND_URL, headers=headers, json=payload)
            if resp.status_code not in _RETRY_STATUS or attempt == 2:
                return resp
            await asyncio.sleep(2 ** attempt)
    return resp


async def send_email(*, to: str, subject: str, html: str, category: str | None = None) -> str | None:
    from afrovending.core.db import db
    from afrovending.core.models import utcnow
    _assert_safe_email(subject, html)
    category = category or sender_for(subject)
    idem = hashlib.sha256(f"{to}|{subject}|{html}|{utcnow().date()}".encode()).hexdigest()
    if await db.email_deliveries.find_one({"idempotency_key": idem, "status": {"$in": ["sent", "delivered"]}}):
        return None
    base = {"idempotency_key": idem, "to_masked": _mask(to), "subject": subject[:200], "category": category, "updated_at": utcnow()}
    if not _key():
        await db.email_deliveries.update_one({"idempotency_key": idem}, {"$set": {**base, "status": "failed", "error": "RESEND_API_KEY not configured"},
                                                                       "$setOnInsert": {"created_at": utcnow()}, "$inc": {"attempts": 1}}, upsert=True)
        err = HTTPException(status_code=503, detail="Email provider is not configured")
        err.upstream = "not_configured"
        raise err
    payload = {"from": _from_address(category), "to": [to], "subject": subject, "html": html}
    if EMAIL_REPLY_TO:
        payload["reply_to"] = EMAIL_REPLY_TO
    try:
        resp = await _post(payload, idem)
    except httpx.HTTPError as e:
        resp, net_err = None, type(e).__name__
    ok = resp is not None and resp.status_code < 300
    try:
        provider_id = resp.json().get("id") if ok else None
    except ValueError:
        provider_id = None
    error = None if ok else (f"provider HTTP {resp.status_code}" if resp is not None else f"network error {net_err}")
    await db.email_deliveries.update_one({"idempotency_key": idem}, {"$set": {**base, "status": "sent" if ok else "failed", "provider_id": provider_id, "error": error},
                                                                   "$setOnInsert": {"created_at": utcnow()}, "$inc": {"attempts": 1}}, upsert=True)
    if ok:
        return provider_id
    logger.error("Email send failed: %s", error)
    err = HTTPException(status_code=502, detail=f"Failed to send email ({error})")
    err.upstream = resp.status_code if resp is not None else "network"
    raise err


async def try_send(**kwargs) -> bool:
    if not sending_enabled():
        logger.info("email suppressed: EMAIL_SENDING_ENABLED is not true")
        return True
    if not _allowed_outside_production(kwargs.get("to", "")):
        logger.info("email suppressed outside production (recipient not on test allowlist)")
        return True
    try:
        await send_email(**kwargs)
        return True
    except HTTPException as e:
        from afrovending.core.ops import record_error
        if "[AfroVending alert]" not in kwargs.get("subject", ""):
            await record_error("email", f"send_failed_{getattr(e, 'upstream', e.status_code)}", str(e.detail), severity="warning")
        return False


def _allowed_outside_production(to) -> bool:
    """Preview/staging never emails real customers: only test domains, the owner/admin address and EMAIL_TEST_ALLOWLIST entries."""
    import os
    if settings.app_env == "production":
        return True
    allow = {"example.com", "example.org", "resend.dev"} | {x.strip().lower() for x in os.environ.get("EMAIL_TEST_ALLOWLIST", "").split(",") if x.strip()}
    admin = (getattr(settings, "admin_email", "") or "").lower()
    for addr in ([to] if isinstance(to, str) else list(to or [])):
        a = addr.lower()
        if a != admin and a not in allow and a.rsplit("@", 1)[-1] not in allow:
            return False
    return True


def _layout(title: str, body: str) -> str:
    return (
        '<table role="presentation" width="100%" style="background:#FAF7F2;padding:24px 0"><tr><td align="center">'
        '<table role="presentation" width="560" style="max-width:560px;background:#ffffff;border:1px solid #E6DFD3;border-radius:12px;font-family:Arial,sans-serif;color:#1A1613">'
        '<tr><td style="background:#1E2A38;padding:18px 28px;border-radius:12px 12px 0 0">'
        f'<img src="{settings.frontend_url}/brand/logo-mark-white.png" alt="AfroVending" width="40" height="40" style="vertical-align:middle;border:0">'
        '<span style="font-family:Impact,Arial Narrow,sans-serif;font-size:24px;letter-spacing:1px;color:#ffffff;vertical-align:middle;margin-left:10px">AFROVENDING</span></td></tr>'
        '<tr><td style="height:4px;background:#D40000"></td></tr>'
        f'<tr><td style="padding:28px"><h1 style="font-family:Georgia,serif;font-size:22px;margin:0 0 16px">{escape(title)}</h1>{body}</td></tr>'
        f'<tr><td style="padding:16px 28px 24px;font-size:12px;color:#6E675F;border-top:1px solid #E6DFD3">Sent by {escape(EMAIL_FROM_NAME)} '
        '(AfroVending Online Marketplace LLC). From Culture to Commerce. We never ask for your password or card details by email.</td></tr>'
        '</table></td></tr></table>'
    )


def _button(url: str, label: str) -> str:
    return (f'<p style="margin:24px 0"><a href="{escape(url)}" style="background:#B24B25;color:#ffffff;padding:12px 22px;'
            f'border-radius:999px;text-decoration:none;font-weight:bold">{escape(label)}</a></p>')


def verification_email(name: str, raw_token: str) -> tuple[str, str]:
    url = f"{settings.frontend_url}/verify-email?token={raw_token}"
    body = (f"<p>Hi {escape(name)},</p><p>Welcome to AfroVending. Please confirm this email address to activate your account.</p>"
            f"{_button(url, 'Verify my email')}<p style=\"font-size:13px;color:#6E675F\">This link expires in 24 hours. If you didn't create an account, you can ignore this email.</p>")
    return "Verify your AfroVending email", _layout("Confirm your email", body)


def reset_email(name: str, raw_token: str) -> tuple[str, str]:
    url = f"{settings.frontend_url}/reset-password?token={raw_token}"
    body = (f"<p>Hi {escape(name)},</p><p>We received a request to reset your AfroVending password.</p>"
            f"{_button(url, 'Choose a new password')}<p style=\"font-size:13px;color:#6E675F\">This link expires in 1 hour and can be used once. If you didn't ask for this, no action is needed.</p>")
    return "Reset your AfroVending password", _layout("Password reset", body)


def security_notice_email(name: str, event: str) -> tuple[str, str]:
    body = (f"<p>Hi {escape(name)},</p><p>{escape(event)}</p><p>If this wasn't you, reset your password right away from the sign-in page "
            f"and contact us at <a href=\"mailto:{escape(settings.contact_inbox)}\">{escape(settings.contact_inbox)}</a>.</p>")
    return "AfroVending account security notice", _layout("Security notice", body)


def vendor_notice_email(name: str, headline: str, text: str) -> tuple[str, str]:
    url = f"{settings.frontend_url}/vendor/apply"
    body = f"<p>Hi {escape(name)},</p><p>{escape(text)}</p>{_button(url, 'View my vendor status')}"
    return f"AfroVending: {headline}", _layout(headline, body)


def low_stock_digest_email(name: str, items: list[dict]) -> tuple[str, str]:
    rows = "".join(f"<tr><td style=\"padding:6px 0;border-bottom:1px solid #E6DFD3\">{escape(i['title'])} ({escape(i['label'])})"
                   f"<br><span style=\"font-size:12px;color:#6E675F\">{escape(i['sku'])}</span></td>"
                   f"<td align=\"right\" style=\"padding:6px 0;border-bottom:1px solid #E6DFD3;font-weight:bold\">{i['available']} left</td></tr>"
                   for i in items[:50])
    more = f"<p style=\"font-size:13px;color:#6E675F\">…and {len(items) - 50} more.</p>" if len(items) > 50 else ""
    body = (f"<p>Hi {escape(name)},</p><p>Here is your weekly summary of {len(items)} low-stock item{'s' if len(items) != 1 else ''}.</p>"
            f"<table role=\"presentation\" width=\"100%\" style=\"font-size:14px\">{rows}</table>{more}"
            f"{_button(settings.frontend_url + '/vendor/products', 'Restock in my dashboard')}"
            "<p style=\"font-size:13px;color:#6E675F\">You chose weekly low-stock summaries. Change this on your Products page.</p>")
    return "AfroVending: weekly low-stock summary", _layout("Weekly low-stock summary", body)


def contact_inbox_email(name: str, email: str, subject: str, message: str) -> tuple[str, str]:
    body = (f"<p><strong>From:</strong> {escape(name)} &lt;{escape(email)}&gt;</p><p><strong>Subject:</strong> {escape(subject)}</p>"
            f"<p style=\"white-space:pre-wrap;background:#F3EDE4;padding:16px;border-radius:8px\">{escape(message)}</p>"
            "<p style=\"font-size:13px;color:#6E675F\">Submitted via the AfroVending contact form. Reply directly to the sender's address above.</p>")
    return "New AfroVending contact form inquiry", _layout("Contact form inquiry", body)



def payment_notice_email(name: str, headline: str, text: str, path: str) -> tuple[str, str]:
    body = f"<p>Hi {escape(name)},</p><p>{escape(text)}</p>{_button(settings.frontend_url + path, 'View details')}"
    return f"AfroVending: {headline}", _layout(headline, body)


def pickup_ready_email(name: str, vo: dict, hours: list[str], exceptions: list[str], tz: str, path: str,
                       stage: str = "ready", booking: str = "") -> tuple[str, str]:
    m = vo.get("shipping_method") or {}
    hrs = "".join(f"<li>{escape(x)}</li>" for x in hours) or "<li>Contact the seller for opening hours.</li>"
    exc = f"<p><b>Upcoming closures / special hours</b></p><ul>{''.join(f'<li>{escape(x)}</li>' for x in exceptions)}</ul>" if exceptions else ""
    ins = f"<p><b>Pickup instructions</b><br/>{escape((m.get('pickup_hours') or {}).get('instructions', ''))}</p>" if (m.get("pickup_hours") or {}).get("instructions") else ""
    num, ven = escape(vo["order_number"]), escape(vo["vendor_name"])
    intro = {"ready": f"Good news — your order <b>{num}</b> from <b>{ven}</b> is ready to collect. You can choose a pickup time on your order page.",
             "reminder": f"A friendly reminder — your order <b>{num}</b> from <b>{ven}</b> is still waiting for you. Please collect it soon.",
             "final": f"Final reminder — your order <b>{num}</b> from <b>{ven}</b> has been waiting for a week. We've let the seller know. "
                      "If you can't collect it, please contact the seller or reply to this email."}[stage]
    slot = f"<p><b>Your booked pickup time</b><br/>{escape(booking)}</p>" if booking else ""
    body = (f"<p>Hi {escape(name)},</p><p>{intro}</p>{slot}"
            f"<p><b>Pickup address</b><br/>{escape(m.get('pickup_address') or 'See your order page')}</p>"
            f"<p><b>Opening hours</b>{f' ({escape(tz)})' if tz else ''}</p><ul>{hrs}</ul>{exc}{ins}"
            f"<p>Please bring your order number.</p>{_button(settings.frontend_url + path, 'Book or view pickup time' if not booking else 'View order')}")
    subject = {"ready": f"Order {vo['order_number']} is ready for pickup", "reminder": f"Reminder: order {vo['order_number']} is waiting for pickup",
               "final": f"Final reminder: collect order {vo['order_number']}"}[stage]
    return f"AfroVending: {subject}", _layout({"ready": "Ready for pickup", "reminder": "Waiting for you", "final": "Please collect your order"}[stage], body)


def receipt_email(name: str, order: dict, payment: dict) -> tuple[str, str]:
    rows = "".join(f"<tr><td style=\"padding:6px 0;border-bottom:1px solid #E6DFD3\">Sold by {escape(g['vendor_name'])}</td>"
                   f"<td align=\"right\" style=\"padding:6px 0;border-bottom:1px solid #E6DFD3\">${g['charged_minor'] / 100:.2f}</td></tr>"
                   for g in payment["plan"])
    body = (f"<p>Hi {escape(name)},</p><p>Thank you for your order <b>{escape(order['order_number'])}</b>. Your payment of "
            f"<b>${payment['amount_minor'] / 100:.2f} USD</b> was received (test mode).</p><table width=\"100%\" style=\"font-size:14px\">{rows}</table>"
            f"{_button(settings.frontend_url + '/account/orders/' + str(order['_id']), 'View receipt')}")
    return f"AfroVending receipt for order {order['order_number']}", _layout("Payment received", body)
