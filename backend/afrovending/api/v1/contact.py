from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field

from afrovending.core import email as mail
from afrovending.core import rate_limit
from afrovending.core.config import settings
from afrovending.core.db import db
from afrovending.core.errors import APIError
from afrovending.core.models import utcnow
from afrovending.core.security import client_ip

router = APIRouter(tags=["contact"])


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    subject: str = Field(min_length=1, max_length=150)
    message: str = Field(min_length=10, max_length=5000)


@router.post("/contact", status_code=201)
async def contact(body: ContactIn, request: Request):
    await rate_limit.hit(f"contact:{client_ip(request)}", 5, 3600)
    subject, html = mail.contact_inbox_email(body.name, body.email, body.subject, body.message)
    sent = await mail.try_send(to=settings.contact_inbox, subject=subject, html=html)
    await db.contact_messages.insert_one({**body.model_dump(), "status": "sent" if sent else "failed",
                                          "request_id": request.state.request_id, "created_at": utcnow()})
    if not sent:
        raise APIError(503, "email_unavailable", f"We couldn't deliver your message right now. Please email {settings.contact_inbox} directly.")
    return {"status": "sent"}
