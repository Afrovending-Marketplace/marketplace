"""Emergent managed email (Resend). Bodies come only from the server-side templates below."""
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

EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ["EMERGENT_EMAIL_KEY"]
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")

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


async def send_email(*, to: str, subject: str, html: str) -> str | None:
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    if EMAIL_REPLY_TO:
        payload["contact_email"] = EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{EMAIL_BASE_URL}/api/v1/email/send", headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        try:
            code = e.response.json().get("code", "")
        except ValueError:
            code = ""
        if code in ("insufficient_credits", "integration_disabled", "daily_limit_reached"):
            logger.warning(f"Email paused: {code} ({e.response.status_code}): {e.response.json().get('message', '')}")
            raise HTTPException(status_code=503, detail="Email is temporarily unavailable")
        logger.error(f"Email send failed: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=502, detail="Failed to send email")
    except Exception as e:
        logger.error(f"Email send error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email")


async def try_send(**kwargs) -> bool:
    try:
        await send_email(**kwargs)
        return True
    except HTTPException:
        return False


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


def contact_inbox_email(name: str, email: str, subject: str, message: str) -> tuple[str, str]:
    body = (f"<p><strong>From:</strong> {escape(name)} &lt;{escape(email)}&gt;</p><p><strong>Subject:</strong> {escape(subject)}</p>"
            f"<p style=\"white-space:pre-wrap;background:#F3EDE4;padding:16px;border-radius:8px\">{escape(message)}</p>"
            "<p style=\"font-size:13px;color:#6E675F\">Submitted via the AfroVending contact form. Reply directly to the sender's address above.</p>")
    return "New AfroVending contact form inquiry", _layout("Contact form inquiry", body)
