"""Contact form route - no authentication required."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from ..services.email import get_email_service


router = APIRouter()


class ContactFormRequest(BaseModel):
    """Contact form submission."""
    company_name: str
    contact_name: str
    email: EmailStr
    description: str


class ContactFormResponse(BaseModel):
    """Response after submitting contact form."""
    success: bool
    message: str


@router.post("", response_model=ContactFormResponse)
async def submit_contact_form(request: ContactFormRequest):
    """Submit a contact form inquiry."""
    email_service = get_email_service()

    if not email_service.is_configured():
        # Log the submission even if email isn't configured
        print(f"[Contact] Form submitted (email not configured): {request.company_name} - {request.contact_name} <{request.email}>")
        return ContactFormResponse(
            success=True,
            message="Thank you for your interest. We'll be in touch shortly."
        )

    success = await email_service.send_contact_form_email(
        sender_name=request.contact_name,
        sender_email=request.email,
        company_name=request.company_name,
        message=request.description,
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
