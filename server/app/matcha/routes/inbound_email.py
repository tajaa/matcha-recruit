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

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

from ...database import get_connection
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.matcha.models.ir_incident import Witness
from app.matcha.services.ir_voice_parser import parse_voice_incident
from .ir_incidents import (
    _location_label,
    _parse_occurred_at,
    _safe_json_loads,
    _info_request_effective_status,
    create_incident_core,
    generate_incident_number,
    send_ir_notifications_task,
    send_ir_info_request_notification_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["anonymous-reporting"])

# Voice dictation on the public intake forms. Mirrors the authed endpoint
# (ir_incidents/voice.py) — same WAV-only contract + size cap. The Gemini parse is
# auth-agnostic; these public handlers resolve the company from the link token
# instead of a JWT, and honor the same ir_voice_intake admin-toggle.
_ALLOWED_AUDIO_MIME = {"audio/wav", "audio/x-wav", "audio/wave"}
_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # ~13 min of 16kHz mono 16-bit WAV


def _features_dict(raw) -> dict:
    """Coerce the companies.enabled_features column (JSONB → dict, or text)."""
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw or {}


async def _read_audio_or_400(file: UploadFile) -> bytes:
    """Validate the upload content-type/size/structure and return the bytes.

    Stricter than the authed voice.py because the caller is unauthenticated: we
    verify the RIFF/WAVE magic bytes so a 25MB blob with a forged content-type
    header can't reach the (expensive) Gemini call. content_type is
    client-controlled, so it is a hint, not a guarantee.
    """
    if (file.content_type or "").lower() not in _ALLOWED_AUDIO_MIME:
        raise HTTPException(status_code=400, detail="Unsupported audio format — expected WAV.")
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    if len(audio) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large (max 25MB).")
    # Cheap structural gate before spending a Gemini multimodal call.
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise HTTPException(status_code=400, detail="Unsupported audio format — expected WAV.")
    return audio


async def _voice_parse_budget(ip: str, token: str, company_id: str) -> None:
    """Per-link + per-company budget on top of the per-IP limits.

    The per-IP cap (applied separately, before the DB lookup) is defeated by IP
    rotation, so a single leaked public link could otherwise drive unlimited
    Gemini spend. These two caps bound abuse of one link, and total spend across
    all of a company's links, regardless of how many IPs the attacker rotates."""
    await check_rate_limit(token, "ir_voice_parse_link", 15, 3600)
    await check_rate_limit(company_id, "ir_voice_parse_co", 120, 3600)

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
            SELECT report_token_used_at, enabled_features FROM companies
            WHERE report_email_token = $1
              AND COALESCE((enabled_features->>'incidents')::boolean, false) = true
            """,
            token,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    if row["report_token_used_at"] is not None:
        raise HTTPException(status_code=410, detail="This reporting link has already been used")
    voice_enabled = bool(_features_dict(row["enabled_features"]).get("ir_voice_intake", False))
    return {"valid": True, "voice_enabled": voice_enabled}


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
            token,
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
                token,
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
                token,
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


@router.post("/report/{token}/voice/parse")
async def parse_report_voice(token: str, request: Request, file: UploadFile = File(...)):
    """Public voice-dictation parse for the anonymous /report form.

    No JWT — the company is resolved from the token, exactly like GET/POST
    /report/{token}. Parsing is pre-submit, so it does NOT consult/burn the
    single-use token; only POST /report/{token} burns it. Returns the same
    prefill shape as the authed endpoint (never creates an incident).
    """
    # Expensive Gemini multimodal call — throttle per IP before reading the upload.
    ip = client_ip(request)
    await check_rate_limit(ip, "ir_voice_parse_public_burst", 5, 60)
    await check_rate_limit(ip, "ir_voice_parse_public", 40, 3600)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, report_token_used_at, enabled_features FROM companies WHERE report_email_token = $1",
            token,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    features = _features_dict(row["enabled_features"])
    if not features.get("incidents", False):
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    # Single-use link: once the report is filed the link is dead — so is its voice
    # parse. Closes the post-burn "free Gemini proxy" window on a leaked link.
    if row["report_token_used_at"] is not None:
        raise HTTPException(status_code=410, detail="This reporting link has already been used")
    if not features.get("ir_voice_intake", False):
        raise HTTPException(status_code=403, detail="Voice dictation is not enabled.")

    await _voice_parse_budget(ip, token, str(row["id"]))
    audio = await _read_audio_or_400(file)
    # Anonymous form has no structured location picker — no options to pin to.
    return await parse_voice_incident(audio, (file.content_type or "audio/wav").lower(),
                                      location_options=[])


# ---------------------------------------------------------------------------
# Location magic links — /intake/{token}
#
# Unlike the anonymous /report link, these are per-location, attributed
# (reporter name required), and produce a full-quality incident with a real
# location_id, witnesses, and AI categorization (via create_incident_core).
# Single-use: the token is burned on first submit.
# ---------------------------------------------------------------------------

def _check_link_usable(row) -> None:
    """Raise 410 if a per-location link is revoked, expired, or over its
    max-use cap. Reusable links pass; the only blockers are these three.
    ``row`` must expose is_active, expires_at, max_uses, use_count."""
    if not row["is_active"]:
        raise HTTPException(
            status_code=410,
            detail="This reporting link has been revoked. Contact your HR team for a new link.",
        )
    expires_at = row["expires_at"]
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=410,
            detail="This reporting link has expired. Contact your HR team for a new link.",
        )
    max_uses = row["max_uses"]
    if max_uses is not None and (row["use_count"] or 0) >= max_uses:
        raise HTTPException(
            status_code=410,
            detail="This reporting link has reached its usage limit. Contact your HR team for a new link.",
        )


@router.get("/intake/{token}")
async def validate_location_intake_token(token: str):
    """Validate a per-location magic link so the form can show its locked location."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT rl.location_id, rl.company_id,
                   rl.is_active, rl.expires_at, rl.max_uses, rl.use_count,
                   c.name AS company_name, c.enabled_features
            FROM ir_report_links rl
            JOIN companies c ON c.id = rl.company_id
            WHERE rl.token = $1
            """,
            token,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    features = row["enabled_features"]
    if isinstance(features, str):
        features = json.loads(features)
    if not (features or {}).get("incidents", False):
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    _check_link_usable(row)

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
    voice_enabled = bool(_features_dict(features).get("ir_voice_intake", False))
    return {
        "valid": True,
        "company_name": row["company_name"],
        "voice_enabled": voice_enabled,
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
            SELECT rl.location_id,
                   c.id AS company_id, c.enabled_features
            FROM ir_report_links rl
            JOIN companies c ON c.id = rl.company_id
            WHERE rl.token = $1
            """,
            token,
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
    #    be set on the connection. Re-check usability under FOR UPDATE so a
    #    burst of concurrent submits can't overshoot a max_uses cap (the link is
    #    reusable, so the lock guards the ceiling, not single-use).
    async with get_connection(tenant_id=company_id) as conn:
        async with conn.transaction():
            link_row = await conn.fetchrow(
                """
                SELECT is_active, expires_at, max_uses, use_count
                FROM ir_report_links WHERE token = $1 FOR UPDATE
                """,
                token,
            )
            if not link_row:
                raise HTTPException(status_code=404, detail="Invalid reporting link")
            _check_link_usable(link_row)

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

            # Reusable: bump the counter + last-used stamp instead of burning it.
            await conn.execute(
                "UPDATE ir_report_links SET use_count = use_count + 1, used_at = NOW() WHERE token = $1",
                token,
            )

    # Schedule notifications + AI auto-classify + policy-map after the commit.
    for fn, args, kwargs in bg_tasks:
        background_tasks.add_task(fn, *args, **kwargs)

    logger.info(
        "[Location Intake] Created incident %s for company %s",
        response_row.get("incident_number"), company_id,
    )
    return {"submitted": True}


@router.post("/intake/{token}/voice/parse")
async def parse_location_intake_voice(token: str, request: Request, file: UploadFile = File(...)):
    """Public voice-dictation parse for the per-location /intake form.

    No JWT — company + usability resolved from the token like GET/POST
    /intake/{token}. Parsing does NOT increment use_count (parse ≠ submit).
    The location is locked by the token, so no options are passed (voice must
    not override it). Returns the same prefill shape as the authed endpoint.
    """
    ip = client_ip(request)
    await check_rate_limit(ip, "ir_voice_parse_public_burst", 5, 60)
    await check_rate_limit(ip, "ir_voice_parse_public", 40, 3600)

    async with get_connection() as conn:
        link = await conn.fetchrow(
            """
            SELECT rl.is_active, rl.expires_at, rl.max_uses, rl.use_count,
                   c.id AS company_id, c.enabled_features
            FROM ir_report_links rl
            JOIN companies c ON c.id = rl.company_id
            WHERE rl.token = $1
            """,
            token,
        )
    if not link:
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    features = _features_dict(link["enabled_features"])
    if not features.get("incidents", False):
        raise HTTPException(status_code=404, detail="Invalid reporting link")
    _check_link_usable(link)
    if not features.get("ir_voice_intake", False):
        raise HTTPException(status_code=403, detail="Voice dictation is not enabled.")

    await _voice_parse_budget(ip, token, str(link["company_id"]))
    audio = await _read_audio_or_400(file)
    return await parse_voice_incident(audio, (file.content_type or "audio/wav").lower(),
                                      location_options=[])


# ---------------------------------------------------------------------------
# IR Copilot "Request More Info" — /request-info/{token}
#
# Single-use, 14-day-expiry link scoped to one incident. Unlike /report and
# /intake this never creates an incident — it attaches an outside party's
# answers to an EXISTING one, created via the admin-side info_requests.py
# router. Answers land in the Copilot transcript as a system event; they are
# never auto-written into ir_incidents columns (admin reviews and applies
# them by hand).
# ---------------------------------------------------------------------------

class InfoRequestAnswers(BaseModel):
    answers: list[str] = Field(..., min_length=1, max_length=20)
    # The responder's self-typed name — their attestation signature (the
    # submit-time disclaimer stands in for a signed paper form). Distinct from
    # the admin-addressed ``recipient_name``.
    respondent_name: str = Field(..., min_length=1, max_length=255)
    # Honeypot — must be empty. Deliberately not a plausible field name
    # (e.g. "company_name"/"email") so browser autofill/password managers
    # don't populate it for a real respondent.
    internal_ref: Optional[str] = Field(None, max_length=255)

    @field_validator("answers")
    @classmethod
    def _answers_not_blank(cls, v: list[str]) -> list[str]:
        if any(not a.strip() for a in v):
            raise ValueError("Answers cannot be blank")
        if any(len(a) > 4000 for a in v):
            raise ValueError("Answers must be 4000 characters or fewer")
        return v

    @field_validator("respondent_name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


_INFO_REQUEST_USABLE_MESSAGES = {
    "revoked": "This link has been revoked. Contact the sender for a new one.",
    "submitted": "This link has already been used.",
    "expired": "This link has expired. Contact the sender for a new one.",
}


def _check_info_request_usable(row) -> None:
    """Raise 410 if an info-request link is submitted, revoked, or expired."""
    status = _info_request_effective_status(row)
    if status != "pending":
        raise HTTPException(status_code=410, detail=_INFO_REQUEST_USABLE_MESSAGES[status])


@router.get("/request-info/{token}")
async def validate_info_request_token(token: str):
    """Validate an info-request link and return the incident-safe context."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT ir.incident_id, ir.company_id, ir.status, ir.expires_at, ir.questions,
                   c.name AS company_name, c.enabled_features
            FROM ir_info_requests ir
            JOIN companies c ON c.id = ir.company_id
            WHERE ir.token = $1
            """,
            token,
        )
    if not row or not _features_dict(row["enabled_features"]).get("incidents", False):
        raise HTTPException(status_code=404, detail="Invalid link")
    _check_info_request_usable(row)

    # Read the incident under the tenant so ir_incidents RLS is satisfied
    # even once the app stops connecting as a superuser (ir_info_requests +
    # companies are RLS-free, mirroring the /intake pattern above).
    async with get_connection(tenant_id=str(row["company_id"])) as conn:
        incident = await conn.fetchrow(
            "SELECT incident_number FROM ir_incidents WHERE id = $1", row["incident_id"],
        )

    questions = _safe_json_loads(row["questions"], [])
    return {
        "valid": True,
        "company_name": row["company_name"],
        "incident_number": incident["incident_number"] if incident else None,
        "questions": [q.get("text") for q in questions],
    }


@router.post("/request-info/{token}")
async def submit_info_request(
    token: str, body: InfoRequestAnswers, request: Request, background_tasks: BackgroundTasks,
):
    """Submit answers to an info-request link. Single-use — burns the token."""
    # Honeypot — bots fill this hidden field; silently accept so as not to tip them off.
    if body.internal_ref:
        return {"submitted": True}

    # Proxy-aware IP (nginx sits in front in prod) + a bucket key distinct
    # from /report and /intake so the three public forms don't share one
    # 5-per-hour quota.
    ip = client_ip(request)
    if _is_rate_limited(f"info:{ip}"):
        raise HTTPException(status_code=429, detail="Too many submissions. Please try again later.")

    # 1. Resolve token -> company_id (ir_info_requests has no RLS).
    async with get_connection() as conn:
        pre = await conn.fetchrow(
            """
            SELECT ir.company_id, c.enabled_features
            FROM ir_info_requests ir
            JOIN companies c ON c.id = ir.company_id
            WHERE ir.token = $1
            """,
            token,
        )
    if not pre or not _features_dict(pre["enabled_features"]).get("incidents", False):
        raise HTTPException(status_code=404, detail="Invalid link")
    company_id = str(pre["company_id"])

    # 2. Tenant-scoped, transaction-wrapped re-check + write — same structure
    #    as /report/{token}'s single-use burn (FOR UPDATE + write in one txn,
    #    not a bare FOR UPDATE statement that would release its lock early).
    async with get_connection(tenant_id=company_id) as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM ir_info_requests WHERE token = $1 FOR UPDATE", token,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Invalid link")
            _check_info_request_usable(row)

            questions = _safe_json_loads(row["questions"], [])
            if len(body.answers) != len(questions):
                raise HTTPException(status_code=422, detail="Answer count doesn't match question count")

            responses = [
                {"question": q.get("text"), "answer": a.strip()}
                for q, a in zip(questions, body.answers)
            ]

            respondent_name = body.respondent_name  # validator-stripped, non-blank

            await conn.execute(
                """
                UPDATE ir_info_requests
                SET responses = $1::jsonb, respondent_name = $2,
                    status = 'submitted', submitted_at = NOW()
                WHERE token = $3
                """,
                json.dumps(responses),
                respondent_name,
                token,
            )

            incident = await conn.fetchrow(
                "SELECT incident_number FROM ir_incidents WHERE id = $1", row["incident_id"],
            )

            # No log_audit here — there is no user_id for an unauthenticated
            # submitter, matching /report/{token} and /intake/{token}.
            from app.matcha.services.ir_ai_orchestrator import append_message
            await append_message(
                conn,
                incident_id=row["incident_id"],
                role="system",
                message_type="event",
                content=f"{respondent_name} submitted the requested information.",
                metadata={
                    "info_request_id": str(row["id"]),
                    "responses": responses,
                    "respondent_name": respondent_name,
                    "addressed_to": row["recipient_name"],
                },
            )

    logger.info(
        "[Info Request] %s submitted answers for incident %s",
        respondent_name, row["incident_id"],
    )
    # Backgrounded: the respondent doesn't wait on an admin-notification email.
    background_tasks.add_task(
        send_ir_info_request_notification_task,
        company_id=company_id,
        incident_id=str(row["incident_id"]),
        incident_number=incident["incident_number"] if incident else "",
        respondent_name=respondent_name,
    )

    return {"submitted": True}
