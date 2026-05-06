"""Contact form route - no authentication required."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

from ..services.email import get_email_service
from ..services.redis_cache import check_rate_limit, client_ip


router = APIRouter()


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
    """Submit a contact form inquiry."""
    if body.website:
        raise HTTPException(status_code=400, detail="Invalid submission")

    ip = client_ip(request)
    await check_rate_limit(ip, "contact", 5, 3600)

    email_service = get_email_service()

    if not email_service.is_configured():
        print(f"[Contact] Form submitted (email not configured): {body.company_name} - {body.contact_name} <{body.email}>")
        return ContactFormResponse(
            success=True,
            message="Thank you for your interest. We'll be in touch shortly."
        )

    success = await email_service.send_contact_form_email(
        sender_name=body.contact_name,
        sender_email=body.email,
        company_name=body.company_name,
        message=body.description,
        preferred_date=body.preferred_date,
        preferred_time=body.preferred_time,
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to send message. Please try again later."
        )

    return ContactFormResponse(
        success=True,
        message="Thank you for your interest. We'll be in touch shortly."
    )
