"""Resend delivery webhooks (Svix-signed). Updates email_deliveries by provider message id."""
import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, Request

from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow

router = APIRouter(prefix="/webhooks", tags=["email-webhooks"])
STATUS = {"email.delivered": "delivered", "email.bounced": "bounced", "email.complained": "complained",
          "email.delivery_delayed": "delayed", "email.failed": "failed", "email.sent": "sent"}


def _verify(secret: str, msg_id: str, ts: str, body: bytes, header: str) -> bool:
    try:
        if not (msg_id and header) or abs(time.time() - int(ts)) > 300:
            return False
        key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    except (ValueError, TypeError):
        return False
    expected = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, part.split(",", 1)[-1]) for part in header.split())


@router.post("/resend")
async def resend_webhook(request: Request):
    secret = (os.environ.get("RESEND_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise APIError(503, "not_configured", "Email webhook is not configured.")
    body = await request.body()
    h = request.headers
    if not _verify(secret, h.get("svix-id", ""), h.get("svix-timestamp", "0"), body, h.get("svix-signature", "")):
        raise APIError(401, "invalid_signature", "Invalid webhook signature.")
    try:
        evt = json.loads(body)
    except ValueError:
        raise APIError(400, "invalid_payload", "Webhook body is not JSON.")
    status = STATUS.get(evt.get("type", ""))
    email_id = (evt.get("data") or {}).get("email_id")
    if status and email_id:
        await db.email_deliveries.update_one({"provider_id": email_id}, {"$set": {"status": status, "updated_at": utcnow()},
                                                                         "$push": {"events": {"type": evt["type"], "at": utcnow()}}})
        if status in ("bounced", "complained", "failed"):
            from afrovending.core.ops import record_error
            await record_error("email", f"delivery_{status}", f"Resend reported {status} for message {email_id}", severity="warning")
    return {"ok": True}
