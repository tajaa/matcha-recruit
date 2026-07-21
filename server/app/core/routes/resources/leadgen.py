"""leadgen routes (L9 split)."""
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



@router.post("/waitlist/lite", response_model=LiteWaitlistResponse)
async def join_lite_waitlist(body: LiteWaitlistRequest, request: Request):
    """Public Matcha Lite waitlist capture. Writes to lead_captures and
    fires a best-effort sales notification email."""
    if body.website:
        raise HTTPException(status_code=400, detail="Invalid submission")

    ip = client_ip(request)
    await check_rate_limit(ip, "waitlist_lite", 5, 3600)

    import re as _re
    email = body.email.strip().lower()
    if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    note_blob = body.note or ""
    if body.company_name:
        note_blob = f"company: {body.company_name}\n" + note_blob
    if body.headcount:
        note_blob = f"headcount: {body.headcount}\n" + note_blob

    async with get_connection() as conn:
        # De-dupe: don't insert a second row for the same email + slug
        # within 24h. Avoids spamming sales on accidental double-submits
        # while still allowing repeated interest later.
        existing = await conn.fetchval(
            """
            SELECT 1 FROM lead_captures
            WHERE email = $1
              AND asset_slug = 'matcha_lite_waitlist'
              AND created_at > NOW() - INTERVAL '24 hours'
            LIMIT 1
            """,
            email,
        )
        if not existing:
            await conn.execute(
                """
                INSERT INTO lead_captures (email, name, asset_slug, source)
                VALUES ($1, $2, 'matcha_lite_waitlist', $3)
                """,
                email,
                body.name,
                note_blob[:100] if note_blob else "matcha_lite_landing",
            )

    try:
        from app.core.services.email import get_email_service
        email_svc = get_email_service()
        if not email_svc.is_configured():
            return LiteWaitlistResponse(ok=True)

        # Confirmation to the user — only on the first signup in 24h to
        # avoid double-sending on accidental re-submits.
        if not existing:
            display_name = body.name.strip() if body.name else None
            greeting = f"Hi {_html.escape(display_name)}," if display_name else "Hi there,"
            user_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
    body {{ margin: 0; padding: 0; background: #f1f5f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1f2937; }}
    .container {{ max-width: 600px; margin: 0 auto; padding: 0; }}
    .header {{ background: linear-gradient(135deg, #16a34a 0%, #22c55e 55%, #4ade80 100%); padding: 40px 32px 36px; text-align: center; }}
    .logo {{ color: #ffffff; font-size: 26px; font-weight: 800; letter-spacing: 4px; }}
    .pill {{ display: inline-block; margin-top: 10px; background: rgba(255,255,255,0.18); color: #ffffff; font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; padding: 5px 12px; border-radius: 999px; }}
    .body {{ background: #ffffff; padding: 36px 32px 28px; }}
    h1 {{ font-size: 22px; margin: 0 0 18px; color: #14532d; }}
    p {{ margin: 0 0 16px; font-size: 15px; }}
    .card {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #22c55e; border-radius: 10px; padding: 16px 18px; margin: 22px 0; }}
    .card p {{ margin: 0; font-size: 14px; color: #166534; }}
    .resources {{ background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 12px; padding: 22px; margin: 24px 0; }}
    .resources h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 1.5px; color: #6b7280; margin: 0 0 14px; }}
    .res-item {{ margin: 0 0 12px; font-size: 14px; }}
    .res-item strong {{ color: #14532d; }}
    .btn {{ display: inline-block; background: #16a34a; color: #ffffff !important; padding: 13px 30px; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 15px; }}
    .footer {{ text-align: center; padding: 24px 32px 32px; color: #9ca3af; font-size: 12px; background: #ffffff; border-top: 1px solid #f1f5f0; }}
    a {{ color: #16a34a; }}
</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
            <div class="pill">Lite&nbsp;·&nbsp;Waitlist</div>
        </div>
        <div class="body">
            <h1>You're on the list&nbsp;🍵</h1>
            <p>{greeting}</p>
            <p>You're officially on the <strong>Matcha Lite</strong> waitlist. You'll get exactly one email from us — the moment Lite opens up.</p>
            <div class="card">
                <p><strong>No noise.</strong> No newsletter, no drip campaign, no "just checking in." Just that one ping when your spot is ready.</p>
            </div>
            <div class="resources">
                <h2>While you wait</h2>
                <div class="res-item">📖 <strong>HR Glossary</strong> — plain-English definitions for the acronym soup.</div>
                <div class="res-item">✍️ <strong>The Blog</strong> — practical HR &amp; compliance reads, no fluff.</div>
                <p style="text-align: center; margin: 18px 0 4px;">
                    <a href="https://hey-matcha.com/resources" class="btn">Explore the resource hub →</a>
                </p>
            </div>
            <p style="color: #6b7280; font-size: 14px;">Talk soon,<br>— The Matcha team</p>
        </div>
        <div class="footer">
            <p style="margin: 0;">Sent via Matcha Recruit · You're receiving this because you joined the Matcha Lite waitlist.</p>
        </div>
    </div>
</body>
</html>
            """
            user_text = (
                f"{'Hi ' + display_name + ',' if display_name else 'Hi there,'}\n\n"
                "You're on the Matcha Lite waitlist. We'll email you the moment Lite opens up.\n\n"
                "In the meantime: https://hey-matcha.com/resources\n\n"
                "— The Matcha team"
            )
            await email_svc.send_email(
                to_email=email,
                to_name=display_name,
                subject="You're on the Matcha Lite waitlist",
                html_content=user_html,
                text_content=user_text,
            )

        # Sales notification — fire on every submit, even repeat ones,
        # so sales sees re-engagement signals.
        sales_email = os.getenv("SALES_INQUIRY_EMAIL")
        if sales_email:
            safe_email = _html.escape(email)
            safe_name = _html.escape(body.name or "(no name)")
            safe_company = _html.escape(body.company_name or "(none)")
            safe_headcount = _html.escape(str(body.headcount) if body.headcount else "(none)")
            safe_note = _html.escape(body.note or "(none)")
            repeat_marker = " (repeat within 24h)" if existing else ""
            sales_html = (
                f"<h3>Matcha Lite waitlist signup{repeat_marker}</h3>"
                f"<p><strong>Email:</strong> {safe_email}</p>"
                f"<p><strong>Name:</strong> {safe_name}</p>"
                f"<p><strong>Company:</strong> {safe_company}</p>"
                f"<p><strong>Headcount:</strong> {safe_headcount}</p>"
                "<p><strong>Note:</strong></p>"
                f"<pre>{safe_note}</pre>"
            )
            await email_svc.send_email(
                to_email=sales_email,
                to_name="Matcha Sales",
                subject=f"New Matcha Lite waitlist signup{repeat_marker}",
                html_content=sales_html,
            )
    except Exception as exc:
        logger.warning("Lite waitlist email failed: %s", exc)

    return LiteWaitlistResponse(ok=True)




@router.post("/qualify", response_model=QualifyResponse)
async def submit_qualification(body: QualifyRequest, request: Request):
    """Public landing-page qualification wizard.

    Writes a lead_captures row with the structured answers in `details`
    and fires a best-effort sales notification. Work emails only.
    """
    if body.website:
        raise HTTPException(status_code=400, detail="Invalid submission")

    ip = client_ip(request)
    await check_rate_limit(ip, "qualify", 5, 3600)

    import re as _re
    email = body.email.strip().lower()
    if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    domain = email.rsplit("@", 1)[1]
    if domain in FREE_EMAIL_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail="Please use your work email address.",
        )

    if body.headcount_range not in HEADCOUNT_RANGES:
        raise HTTPException(status_code=400, detail="Invalid headcount range")
    if body.location_range not in LOCATION_RANGES:
        raise HTTPException(status_code=400, detail="Invalid location range")
    needs = [n for n in body.primary_needs if n in PRIMARY_NEEDS]

    details = {
        "headcount_range": body.headcount_range,
        "location_range": body.location_range,
        "primary_needs": needs,
        "company_name": body.company_name,
    }

    async with get_connection() as conn:
        # De-dupe on email + slug within 24h, same as the Lite waitlist —
        # a double-submit shouldn't page sales twice.
        existing = await conn.fetchval(
            """
            SELECT 1 FROM lead_captures
            WHERE email = $1
              AND asset_slug = 'landing_qualification'
              AND created_at > NOW() - INTERVAL '24 hours'
            LIMIT 1
            """,
            email,
        )
        if not existing:
            await conn.execute(
                """
                INSERT INTO lead_captures (email, name, asset_slug, source, ip_address, details)
                VALUES ($1, $2, 'landing_qualification', 'home_wizard', $3, $4::jsonb)
                """,
                email,
                body.name,
                ip,
                _json.dumps(details),
            )

    if existing:
        return QualifyResponse(ok=True)

    try:
        from app.core.services.email import get_email_service
        sales_email = os.getenv("SALES_INQUIRY_EMAIL")
        email_svc = get_email_service()
        if sales_email and email_svc.is_configured():
            safe_email = _html.escape(email)
            safe_name = _html.escape(body.name or "(no name)")
            safe_company = _html.escape(body.company_name or "(not given)")
            safe_headcount = _html.escape(body.headcount_range)
            safe_locations = _html.escape(body.location_range)
            safe_needs = _html.escape(", ".join(needs) or "(none selected)")
            await email_svc.send_email(
                to_email=sales_email,
                to_name="Matcha Sales",
                subject=f"New qualified lead: {body.company_name or email}",
                html_content=(
                    "<h2>Landing qualification wizard</h2>"
                    f"<p><strong>Contact:</strong> {safe_name} &lt;{safe_email}&gt;</p>"
                    f"<p><strong>Company:</strong> {safe_company}</p>"
                    f"<p><strong>Employees:</strong> {safe_headcount}</p>"
                    f"<p><strong>Locations:</strong> {safe_locations}</p>"
                    f"<p><strong>Needs:</strong> {safe_needs}</p>"
                ),
            )
    except Exception as exc:
        logger.warning("Qualification lead email failed: %s", exc)

    return QualifyResponse(ok=True)




@router.post("/audit")
async def submit_audit(
    body: AuditSubmitRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Compliance-audit submission. Emails the gap report to the signed-in user.

    Findings are computed client-side from a static rule set (frontend owns
    the quiz logic). This endpoint emails the user an HTML summary.
    """
    # Best-effort email — don't fail the request if delivery breaks.
    try:
        from app.core.services.email import get_email_service
        html = _render_audit_email(body)
        await get_email_service().send_email(
            to_email=current_user.email,
            to_name=None,
            subject="Your HR Compliance Gap Report",
            html_content=html,
        )
        delivered = True
    except Exception:
        logger.exception("Failed to send audit email to %s", current_user.email)
        delivered = False

    logger.info(
        "Audit submission: user=%s findings=%d score=%s state=%s",
        current_user.email,
        len(body.findings),
        body.score,
        body.state_slug,
    )

    return {"ok": True, "delivered": delivered}
