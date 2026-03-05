"""Public anonymous incident reporting endpoint.

Accepts submissions from an unauthenticated form gated by a company-specific
token. Rate-limited per IP and protected by a honeypot field.
"""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...database import get_connection
from .ir_incidents import generate_incident_number, send_ir_notifications_task

logger = logging.getLogger(__name__)

router = APIRouter(tags=["anonymous-reporting"])

# ---------------------------------------------------------------------------
# Rate limiting: max 5 submissions per IP per hour
# ---------------------------------------------------------------------------
_RATE_LIMIT = 5
_RATE_WINDOW = 3600  # seconds
_ip_submissions: dict[str, list[float]] = defaultdict(list)


def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    window_start = now - _RATE_WINDOW
    # Prune old entries
    _ip_submissions[ip] = [t for t in _ip_submissions[ip] if t > window_start]
    if len(_ip_submissions[ip]) >= _RATE_LIMIT:
        return True
    _ip_submissions[ip].append(now)
    return False


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class AnonymousReportRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=10, max_length=10_000)
    # Honeypot — must be empty
    company_name: Optional[str] = Field(None, max_length=255)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/report/{token}")
async def validate_report_token(token: str):
    """Check that a token is valid so the form can show an error early."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT report_token_used_at FROM companies
            WHERE report_email_token = $1
              AND COALESCE((enabled_features->>'incidents')::boolean, false) = true
            """,
            token.lower(),
        )
    if not row:
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    if row["report_token_used_at"] is not None:
        raise HTTPException(status_code=410, detail="This reporting link has already been used")
    return {"valid": True}


@router.post("/report/{token}")
async def submit_anonymous_report(token: str, body: AnonymousReportRequest, request: Request):
    """Submit an anonymous incident report."""
    # Honeypot check — bots fill this hidden field
    if body.company_name:
        # Silently accept to not tip off the bot
        return {"submitted": True}

    # Rate limit
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many reports. Please try again later.")

    # Look up company, insert incident, and mark token used atomically.
    # The connection must carry the tenant_id so that the INSERT into
    # ir_incidents passes the RLS policy.  We resolve the company_id from
    # the token first, then open a tenant-scoped connection for the write.
    incident_number = generate_incident_number()
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Quick lookup to resolve company_id (companies table has no RLS)
    async with get_connection() as conn:
        company_id_row = await conn.fetchval(
            "SELECT id FROM companies WHERE report_email_token = $1",
            token.lower(),
        )
    if not company_id_row:
        raise HTTPException(status_code=404, detail="Invalid reporting link")

    company_id = str(company_id_row)

    # 2. Tenant-scoped connection for the atomic write
    async with get_connection(tenant_id=company_id) as conn:
        async with conn.transaction():
            company = await conn.fetchrow(
                """SELECT id, name, enabled_features, report_token_used_at
                   FROM companies WHERE report_email_token = $1 FOR UPDATE""",
                token.lower(),
            )

            if not company:
                raise HTTPException(status_code=404, detail="Invalid reporting link")

            if company["report_token_used_at"] is not None:
                raise HTTPException(status_code=410, detail="This reporting link has already been used")

            # Check incidents feature — deny when NULL or missing
            features = company.get("enabled_features")
            if isinstance(features, str):
                features = json.loads(features)
            if not (features or {}).get("incidents", False):
                raise HTTPException(status_code=404, detail="Invalid reporting link")

            row = await conn.fetchrow(
                """
                INSERT INTO ir_incidents (
                    incident_number, title, description, incident_type, severity,
                    occurred_at, reported_by_name, company_id, created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id, incident_number, title, status
                """,
                incident_number,
                body.title.strip(),
                body.description.strip(),
                "other",
                "medium",
                now_naive,
                "Anonymous",
                company_id,
                None,
            )

            await conn.execute(
                "UPDATE companies SET report_token_used_at = NOW() WHERE report_email_token = $1",
                token.lower(),
            )

    if row:
        logger.info(f"[Anon Report] Created incident {row['incident_number']} for company {company_id}")
        try:
            await send_ir_notifications_task(
                company_id=company_id,
                incident_id=str(row["id"]),
                incident_number=row["incident_number"],
                incident_title=row["title"],
                event_type="created",
                current_status=row["status"],
                changed_by_email=None,
                previous_status=None,
                occurred_at=now_naive,
            )
        except Exception as e:
            logger.warning(f"[Anon Report] Failed to send notifications: {e}")

    return {"submitted": True}
