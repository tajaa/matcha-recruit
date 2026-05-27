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

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from ...database import get_connection
from app.matcha.models.ir_incident import Witness
from .ir_incidents import (
    _location_label,
    _parse_occurred_at,
    create_incident_core,
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


class LocationReportRequest(BaseModel):
    """Payload for the attributed per-location magic-link form (/intake/{token}).

    Note: there is intentionally no `location` field — the location is derived
    from the token server-side, so a public caller can't pick an arbitrary one.
    """
    description: str = Field(..., min_length=10, max_length=10_000)
    reported_by_name: str = Field(..., min_length=1, max_length=255)
    occurred_at: Optional[str] = Field(None, max_length=255)
    witnesses: list[str] = Field(default_factory=list, max_length=50)
    corrective_actions: Optional[str] = Field(None, max_length=10_000)
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


# ---------------------------------------------------------------------------
# Location magic links — /intake/{token}
#
# Unlike the anonymous /report link, these are per-location, attributed
# (reporter name required), and produce a full-quality incident with a real
# location_id, witnesses, and AI categorization (via create_incident_core).
# Single-use: the token is burned on first submit.
# ---------------------------------------------------------------------------

@router.get("/intake/{token}")
async def validate_location_intake_token(token: str):
    """Validate a per-location magic link so the form can show its locked location."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT rl.used_at, rl.location_id, rl.company_id,
                   c.name AS company_name, c.enabled_features
            FROM ir_report_links rl
            JOIN companies c ON c.id = rl.company_id
            WHERE rl.token = $1
            """,
            token.lower(),
        )
    if not row:
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    features = row["enabled_features"]
    if isinstance(features, str):
        features = json.loads(features)
    if not (features or {}).get("incidents", False):
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    if row["used_at"] is not None:
        raise HTTPException(status_code=410, detail="This reporting link has already been used")

    # Read the location under the tenant so business_locations RLS is satisfied
    # even once the app stops connecting as a superuser (rl + companies are
    # RLS-free; business_locations is tenant-scoped on app.current_tenant_id).
    loc = None
    if row["location_id"]:
        async with get_connection(tenant_id=str(row["company_id"])) as lconn:
            loc = await lconn.fetchrow(
                "SELECT name, city, state FROM business_locations WHERE id = $1",
                row["location_id"],
            )
    return {
        "valid": True,
        "company_name": row["company_name"],
        "location": {
            "id": str(row["location_id"]) if row["location_id"] else None,
            "name": loc["name"] if loc else None,
            "label": _location_label(
                loc["name"] if loc else None,
                loc["city"] if loc else None,
                loc["state"] if loc else None,
            ),
        },
    }


@router.post("/intake/{token}")
async def submit_location_report(
    token: str,
    body: LocationReportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Submit an attributed incident via a per-location magic link.

    Mirrors the authenticated create: location_id is derived from the token
    (never trusted from the client), witnesses + reporter name are recorded,
    and AI auto-classify / policy-map / notifications fire — so the incident is
    indistinguishable in quality from a logged-in submission.
    """
    # Honeypot — bots fill this hidden field; silently accept so as not to tip them off.
    if body.company_name:
        return {"submitted": True}

    description_trimmed = body.description.strip()
    if len(description_trimmed) < 10:
        raise HTTPException(status_code=422, detail="Description must be at least 10 characters")
    reporter = body.reported_by_name.strip()
    if not reporter:
        raise HTTPException(status_code=422, detail="Your name is required")

    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many reports. Please try again later.")

    # 1. Resolve token -> company + location_id (rl + companies are RLS-free).
    #    The location row itself is read under the tenant inside the txn below.
    async with get_connection() as conn:
        link = await conn.fetchrow(
            """
            SELECT rl.location_id, rl.used_at,
                   c.id AS company_id, c.enabled_features
            FROM ir_report_links rl
            JOIN companies c ON c.id = rl.company_id
            WHERE rl.token = $1
            """,
            token.lower(),
        )
    if not link:
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    features = link["enabled_features"]
    if isinstance(features, str):
        features = json.loads(features)
    if not (features or {}).get("incidents", False):
        raise HTTPException(status_code=404, detail="Invalid reporting link")

    company_id = str(link["company_id"])
    location_id = str(link["location_id"]) if link["location_id"] else None

    witnesses = [
        Witness(name=n.strip()[:255], contact=None)
        for n in (body.witnesses or [])
        if n and n.strip()
    ][:50]

    # 2. Tenant-scoped atomic write — ir_incidents has RLS, so the tenant must
    #    be set on the connection. Re-check used_at under FOR UPDATE so a
    #    double-submit can't mint two incidents off one single-use link.
    async with get_connection(tenant_id=company_id) as conn:
        async with conn.transaction():
            link_row = await conn.fetchrow(
                "SELECT used_at FROM ir_report_links WHERE token = $1 FOR UPDATE",
                token.lower(),
            )
            if not link_row:
                raise HTTPException(status_code=404, detail="Invalid reporting link")
            if link_row["used_at"] is not None:
                raise HTTPException(status_code=410, detail="This reporting link has already been used")

            # Location label + active-state, read under the tenant (RLS-safe).
            # A link for a since-deactivated location is rejected (parity with
            # the authed create, which requires is_active=true).
            loc = None
            if location_id:
                loc = await conn.fetchrow(
                    "SELECT name, city, state, is_active FROM business_locations WHERE id = $1",
                    location_id,
                )
            if loc is not None and not loc["is_active"]:
                raise HTTPException(
                    status_code=410,
                    detail="This location is no longer active. Contact your HR team for a new link.",
                )
            location_label = _location_label(
                loc["name"] if loc else None,
                loc["city"] if loc else None,
                loc["state"] if loc else None,
            )

            response_row, bg_tasks = await create_incident_core(
                conn,
                company_id=company_id,
                description=description_trimmed,
                occurred_at=body.occurred_at,
                reported_by_name=reporter,
                location=location_label,
                location_id=location_id,
                witnesses=witnesses,
                corrective_actions=(body.corrective_actions or None),
                created_by=None,
                actor_user_id=None,
                actor_email=None,
                actor_ip=client_ip,
                current_user=None,
            )

            await conn.execute(
                "UPDATE ir_report_links SET used_at = NOW() WHERE token = $1",
                token.lower(),
            )

    # Schedule notifications + AI auto-classify + policy-map after the commit.
    for fn, args, kwargs in bg_tasks:
        background_tasks.add_task(fn, *args, **kwargs)

    logger.info(
        "[Location Intake] Created incident %s for company %s",
        response_row.get("incident_number"), company_id,
    )
    return {"submitted": True}
