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
from .ir_incidents import (
    _parse_occurred_at,
    generate_incident_number,
    send_ir_notifications_task,
)

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
    description: str = Field(..., min_length=10, max_length=10_000)
    occurred_at: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=255)
    involved_parties: Optional[str] = Field(None, max_length=2_000)
    contact_info: Optional[str] = Field(None, max_length=255)
    # Honeypot — must be empty
    company_name: Optional[str] = Field(None, max_length=255)


def _derive_title(description: str, limit: int = 80) -> str:
    """Pull a title from the first line/sentence of the description."""
    text = description.strip()
    # First non-empty line
    for line in text.splitlines():
        line = line.strip()
        if line:
            text = line
            break
    # Cut at first sentence-ending punctuation if it's reasonably short
    for sep in (". ", "! ", "? "):
        idx = text.find(sep)
        if 0 < idx <= limit:
            return text[: idx + 1].strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


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

    # Re-validate trimmed length — Pydantic min_length runs pre-strip.
    description_trimmed = body.description.strip()
    if len(description_trimmed) < 10:
        raise HTTPException(status_code=422, detail="Description must be at least 10 characters")
    title_derived = _derive_title(description_trimmed)

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

    # User types occurred_at as free text ("yesterday at 3pm", "May 1 4pm").
    # _parse_occurred_at falls back to NOW() on parse failure.
    occurred_at = (
        _parse_occurred_at(body.occurred_at) if body.occurred_at else now_naive
    )

    extra_category_data: dict = {}
    if body.involved_parties and body.involved_parties.strip():
        extra_category_data["involved_parties"] = body.involved_parties.strip()
    if body.contact_info and body.contact_info.strip():
        extra_category_data["contact_info"] = body.contact_info.strip()

    location_clean = body.location.strip() if body.location else None
    if not location_clean:
        location_clean = None

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
                    occurred_at, location, reported_by_name, category_data,
                    company_id, created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id, incident_number, title, status
                """,
                incident_number,
                title_derived,
                description_trimmed,
                "other",
                "medium",
                occurred_at,
                location_clean,
                "Anonymous",
                json.dumps(extra_category_data),
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
                occurred_at=occurred_at,
            )
        except Exception as e:
            logger.warning(f"[Anon Report] Failed to send notifications: {e}")

    return {"submitted": True}
