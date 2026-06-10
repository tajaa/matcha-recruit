"""Contact form route - no authentication required."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

from ...database import get_connection
from ..services.email import get_email_service
from ..services.redis_cache import check_rate_limit, client_ip


logger = logging.getLogger(__name__)

router = APIRouter()


async def _persist_submission(body: "ContactFormRequest", ip: str, kind: str, email_sent: bool) -> bool:
    """Store the submission so a lead is never lost if the email send fails.

    Best-effort: a DB hiccup (or the table not yet existing on an un-migrated
    env) must not break the form — the email path still runs independently.
    Returns True if a row was written.
    """
    try:
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO contact_submissions
                    (kind, company_name, contact_name, email, description,
                     preferred_date, preferred_time, ip, email_sent)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                kind, body.company_name, body.contact_name, str(body.email),
                body.description, body.preferred_date, body.preferred_time, ip, email_sent,
            )
        return True
    except Exception:
        logger.exception("contact_submissions insert failed (continuing; email path unaffected)")
        return False


class ContactFormRequest(BaseModel):
    """Contact form submission."""
    company_name: str = Field(..., max_length=200)
    contact_name: str = Field(..., max_length=200)
    email: EmailStr
    description: str = Field(..., max_length=4000)
    preferred_date: str | None = Field(default=None, max_length=50)
    preferred_time: str | None = Field(default=None, max_length=50)
    website: Optional[str] = Field(default=None)  # honeypot


class ContactFormResponse(BaseModel):
    """Response after submitting contact form."""
    success: bool
    message: str


@router.post("", response_model=ContactFormResponse)
async def submit_contact_form(body: ContactFormRequest, request: Request):
    """Submit a contact form inquiry.

    Lead is persisted first (best-effort) so it survives an email failure; the
    email notification is then sent best-effort on top. We only fail the request
    if BOTH the store and the email fail — i.e. we genuinely captured nothing.
    """
    if body.website:
        raise HTTPException(status_code=400, detail="Invalid submission")

    ip = client_ip(request)
    await check_rate_limit(ip, "contact", 5, 3600)

    kind = "consultation" if (body.preferred_date or body.preferred_time) else "contact"

    # 1) Best-effort email notification.
    email_service = get_email_service()
    email_sent = False
    if email_service.is_configured():
        try:
            email_sent = await email_service.send_contact_form_email(
                sender_name=body.contact_name,
                sender_email=body.email,
                company_name=body.company_name,
                message=body.description,
                preferred_date=body.preferred_date,
                preferred_time=body.preferred_time,
            )
        except Exception:
            logger.exception("contact form email send raised")
    else:
        logger.warning(
            "[Contact] email backend not configured: %s - %s <%s>",
            body.company_name, body.contact_name, body.email,
        )

    # 2) Persist the lead regardless of email outcome.
    persisted = await _persist_submission(body, ip, kind, email_sent)

    # 3) Succeed if we captured the lead either way; only fail if we got nothing.
    if not (email_sent or persisted):
        raise HTTPException(
            status_code=500,
            detail="Failed to send message. Please try again later.",
        )

    return ContactFormResponse(
        success=True,
        message="Thank you for your interest. We'll be in touch shortly."
    )
