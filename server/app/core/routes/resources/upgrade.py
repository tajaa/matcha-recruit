"""upgrade routes (L9 split)."""
import html as _html
import json as _json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.models.auth import CurrentUser
from app.core.dependencies import get_optional_user
from app.matcha.dependencies import require_client, get_client_company_id
from app.core.services.redis_cache import check_rate_limit, client_ip

from app.core.routes.resources._shared import *  # noqa: F401,F403  (router objects + shared models/consts)
logger = logging.getLogger(__name__)



@router.post("/upgrade/inquiry", response_model=UpgradeInquiryResponse)
async def submit_upgrade_inquiry(
    body: UpgradeInquiryRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Record an in-app upgrade inquiry from a Cap-tier user.

    Cap (ir_only_self_serve / resources_free) doesn't have a self-serve
    Stripe path to the full Matcha Platform — it's contract-billed. This
    endpoint captures the click + optional message so sales can follow
    up, and fires a notification email if the email service is configured.
    """
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # users has no `name` column — pull it from clients via the require_client
        # tenant's user→client link. Same pattern as stripe_webhook.py:170.
        user_row = await conn.fetchrow(
            """
            SELECT u.email, c.name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            WHERE u.id = $1
            LIMIT 1
            """,
            current_user.id,
        )
        company_row = None
        if company_id is not None:
            company_row = await conn.fetchrow(
                "SELECT name, signup_source FROM companies WHERE id = $1",
                company_id,
            )

        email = user_row["email"] if user_row else None
        user_name = (user_row["name"] if user_row else None) or None
        company_name = company_row["name"] if company_row else None
        signup_source = company_row["signup_source"] if company_row else None

        if not email:
            raise HTTPException(status_code=400, detail="No email on file for this user")

        await conn.execute(
            """
            INSERT INTO lead_captures (email, name, asset_slug, source)
            VALUES ($1, $2, 'upgrade_inquiry_to_matcha_platform', $3)
            """,
            email,
            user_name,
            body.source,
        )

    # Best-effort sales notification email — escape user-controlled content
    try:
        from app.core.services.email import get_email_service
        sales_email = os.getenv("SALES_INQUIRY_EMAIL")
        email_svc = get_email_service()
        if sales_email and email_svc.is_configured():
            safe_email = _html.escape(email)
            safe_user_name = _html.escape(user_name or "(no name)")
            safe_company = _html.escape(company_name or "unknown")
            safe_signup_source = _html.escape(signup_source or "unknown tier")
            safe_source = _html.escape(body.source)
            safe_message = _html.escape(body.message or "(none)")
            html_body = (
                f"<h3>Matcha Platform upgrade inquiry</h3>"
                f"<p><strong>From:</strong> {safe_user_name} &lt;{safe_email}&gt;</p>"
                f"<p><strong>Company:</strong> {safe_company} ({safe_signup_source})</p>"
                f"<p><strong>Source:</strong> {safe_source}</p>"
                f"<p><strong>Message:</strong></p>"
                f"<pre>{safe_message}</pre>"
            )
            await email_svc.send_email(
                to_email=sales_email,
                to_name="Matcha Sales",
                subject="Upgrade inquiry from a Matcha tenant",
                html_content=html_body,
            )
    except Exception as exc:
        logger.warning("Sales inquiry email failed: %s", exc)

    return UpgradeInquiryResponse(ok=True)




@router.post("/upgrade/lite/request", response_model=UpgradeInquiryResponse)
async def request_lite_upgrade(
    body: LiteUpgradeRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Record a Matcha Lite access request from a resources_free user.

    Writes a lead_captures row and emails the admin with a direct link
    to the company in the admin panel for manual activation.
    """
    from app.config import get_settings

    try:
        company_id = await get_client_company_id(current_user)

        async with get_connection() as conn:
            # users has no `name` column — pull it from clients (require_client
            # gates this route, so the link is always present for real callers).
            user_row = await conn.fetchrow(
                """
                SELECT u.email, c.name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                WHERE u.id = $1
                LIMIT 1
                """,
                current_user.id,
            )
            company_name: Optional[str] = None
            if company_id is not None:
                company_row = await conn.fetchrow(
                    "SELECT name FROM companies WHERE id = $1",
                    company_id,
                )
                company_name = company_row["name"] if company_row else None

            email = user_row["email"] if user_row else None
            user_name = (user_row["name"] if user_row else None) or None

            if not email:
                raise HTTPException(status_code=400, detail="No email on file for this user")

            await conn.execute(
                """
                INSERT INTO lead_captures (email, name, asset_slug, source)
                VALUES ($1, $2, 'upgrade_request_to_matcha_lite', 'free_to_lite_request')
                """,
                email,
                user_name,
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("request_lite_upgrade failed for user=%s: %s", current_user.id, exc)
        raise HTTPException(status_code=500, detail="Failed to submit upgrade request") from exc

    try:
        from app.core.services.email import get_email_service
        sales_email = os.getenv("SALES_INQUIRY_EMAIL")
        email_svc = get_email_service()
        if sales_email and email_svc.is_configured():
            base_url = get_settings().app_base_url.rstrip("/")
            safe_company = _html.escape(company_name or "unknown")
            safe_user = _html.escape(user_name or "(no name)")
            safe_email_str = _html.escape(email)
            headcount_str = str(body.headcount) if body.headcount else "not specified"
            admin_link = f"{base_url}/admin/companies/{company_id}" if company_id else f"{base_url}/admin/customers"
            html_content = (
                f"<h3>Matcha Lite access request</h3>"
                f"<p><strong>Company:</strong> {safe_company}</p>"
                f"<p><strong>Contact:</strong> {safe_user} &lt;{safe_email_str}&gt;</p>"
                f"<p><strong>Headcount:</strong> {headcount_str}</p>"
                f"<p><a href='{admin_link}'>Review in admin panel →</a></p>"
            )
            await email_svc.send_email(
                to_email=sales_email,
                to_name="Matcha Admin",
                subject=f"Lite access request: {company_name or email}",
                html_content=html_content,
            )
    except Exception as exc:
        logger.warning("Lite upgrade request email failed: %s", exc)

    return UpgradeInquiryResponse(ok=True)
