"""Expert advice — Matcha Lite users submit HR questions, founder responds manually.

Stores submission in `lead_captures` (asset_slug='expert_advice') and fires
a notification email to SALES_INQUIRY_EMAIL so the founder can reply
directly. No SLA UI yet; tracked via response email thread.
"""

import html as _html
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...database import get_connection
from ..models.auth import CurrentUser
from ..services.redis_cache import check_rate_limit, client_ip
from ...matcha.dependencies import require_client, get_client_company_id


logger = logging.getLogger(__name__)
router = APIRouter()


class ExpertAdviceRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10, max_length=4000)
    preferred_contact: str = Field("email", pattern="^(email|phone)$")
    phone: Optional[str] = Field(default=None, max_length=50)
    website: Optional[str] = Field(default=None)  # honeypot


class ExpertAdviceResponse(BaseModel):
    ok: bool
    message: str


@router.post("/request", response_model=ExpertAdviceResponse)
async def submit_expert_advice(
    body: ExpertAdviceRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_client),
):
    """Submit an HR advice request. Auth-gated to client users (Matcha Lite + above)."""
    if body.website:
        raise HTTPException(status_code=400, detail="Invalid submission")

    await check_rate_limit(client_ip(request), "expert_advice", 5, 3600)

    if body.preferred_contact == "phone" and not body.phone:
        raise HTTPException(status_code=400, detail="Phone number required for phone callback")

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        user_row = await conn.fetchrow(
            """
            SELECT u.email, c.name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            WHERE u.id = $1
            """,
            current_user.id,
        )
        company_row = None
        if company_id is not None:
            company_row = await conn.fetchrow(
                "SELECT name, signup_source FROM companies WHERE id = $1",
                company_id,
            )

        if not user_row or not user_row["email"]:
            raise HTTPException(status_code=400, detail="No email on file")

        user_email = user_row["email"]
        user_name = user_row["name"] or None
        company_name = company_row["name"] if company_row else None
        signup_source = company_row["signup_source"] if company_row else None

        note = f"topic: {body.topic}\ncontact: {body.preferred_contact}"
        if body.phone:
            note += f"\nphone: {body.phone}"
        note += f"\n\n{body.description}"

        await conn.execute(
            """
            INSERT INTO lead_captures (email, name, asset_slug, source)
            VALUES ($1, $2, 'expert_advice', $3)
            """,
            user_email,
            user_name,
            note[:500],
        )

    try:
        from ..services.email import get_email_service
        notify_email = os.getenv("SALES_INQUIRY_EMAIL") or "finitemaths@proton.me"
        email_svc = get_email_service()
        if email_svc.is_configured():
            safe_email = _html.escape(user_email)
            safe_user_name = _html.escape(user_name or "(no name)")
            safe_company = _html.escape(company_name or "unknown")
            safe_signup_source = _html.escape(signup_source or "unknown tier")
            safe_topic = _html.escape(body.topic)
            safe_description = _html.escape(body.description)
            safe_contact = _html.escape(body.preferred_contact)
            safe_phone = _html.escape(body.phone or "(none)")
            html_body = (
                f"<h3>Live HR advice request</h3>"
                f"<p><strong>From:</strong> {safe_user_name} &lt;{safe_email}&gt;</p>"
                f"<p><strong>Company:</strong> {safe_company} ({safe_signup_source})</p>"
                f"<p><strong>Preferred contact:</strong> {safe_contact}"
                f" (phone: {safe_phone})</p>"
                f"<p><strong>Topic:</strong> {safe_topic}</p>"
                f"<p><strong>Question:</strong></p>"
                f"<pre style='white-space:pre-wrap;font-family:inherit;'>{safe_description}</pre>"
                f"<hr><p style='color:#666;font-size:12px;'>"
                f"Reply directly to {safe_email} to answer the user.</p>"
            )
            await email_svc.send_email(
                to_email=notify_email,
                to_name="Matcha Founder",
                subject=f"[Advice] {body.topic[:80]}",
                html_content=html_body,
                extra_headers={"Reply-To": user_email},
            )
    except Exception as exc:
        logger.warning("Expert advice notification email failed: %s", exc)

    return ExpertAdviceResponse(
        ok=True,
        message=(
            "Got it. Aaron will respond personally within 1 business day"
            f"{' via phone' if body.preferred_contact == 'phone' else ' by email'}."
        ),
    )
