"""Shared helpers for IR Incidents submodules.

Cross-cutting utilities used by more than one submodule. Promoted out of
the original flat `ir_incidents.py` during the package split.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import HTTPException, Request, UploadFile

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id
from app.matcha.models.ir.incident import IRIncidentResponse, Witness
from app.core.services.osha_privacy import (  # noqa: F401  (re-export: copilot.py)
    PRIVACY_CASE_REASONS,
    PRIVACY_CASE_REASON_LABELS,
)

# Re-exports (refactor round 2, stage 3) — the real implementations now live
# in services/ir/*; kept here so every existing `from ._shared import ...`
# inside this package (crud.py, copilot.py, osha.py, people.py,
# investigation_interviews.py) and the package's own __init__.py re-export
# keep working unchanged.
from app.matcha.services.ir.ir_incident_create import create_incident_core  # noqa: F401
from app.matcha.services.ir.ir_notifications import (  # noqa: F401
    send_ir_notifications_task,
    send_ir_info_request_notification_task,
)
from app.matcha.services.ir.ir_osha_cases import (  # noqa: F401
    next_case_step,
    ensure_osha_case_rows,
    fetch_osha_case_rows,
    fetch_osha_case_rows_for,
    _persist_osha_emergency_alert,
)
from app.matcha.services.ir.ir_people_index import (  # noqa: F401
    IR_PERSON_ROLES,
    IR_INCIDENT_BODY_ROLES,
    _gather_incident_people,
    _sync_incident_people,
    _upsert_ir_person,
    _link_incident_person,
    _normalize_person_name,
)


logger = logging.getLogger(__name__)

# Card builders + their constants live in services/ir/ir_cards.py (moved there
# refactor round 2, stage 3). Re-exported here so existing
# `from ._shared import build_osha_...` / `OSHA_INJURY_...` imports — and the
# DB-backed dispatchers below (next_case_step, _persist_osha_emergency_alert)
# that build these cards — keep working unchanged. `_cards.py` (the former
# re-export shim, only ever imported from here) was deleted — this package's
# own `from ._cards import build_osha_...` never existed, so nothing else
# needed updating.
from app.matcha.services.ir.ir_cards import (  # noqa: E402,F401
    OSHA_INJURY_TYPES,
    OSHA_INJURY_TYPE_LABELS,
    OSHA_EMERGENCY_ALERT_CARD_ID,
    OSHA_EMERGENCY_HOTLINE,
    OSHA_REPORTING_WINDOW,
    build_osha_emergency_alert_card,
    build_osha_recordable_query_card,
    build_osha_days_type_query_card,
    build_osha_days_count_card,
    build_osha_injury_type_query_card,
    build_privacy_case_query_card,
    ROOT_CAUSE_INTERVIEW_STEPS,
    ROOT_CAUSE_PROMPTS,
    ROOT_CAUSE_PLAINTEXT_LABELS,
    build_log_root_cause_query_card,
    build_root_cause_text_card,
    build_root_cause_logged_ack_card,
    compose_root_cause_text,
    build_osha_close_confirmation_card,
    build_treatment_query_card,
    build_request_documents_card,
    build_investigation_notes_card,
    build_osha_clean_description_card,
    build_assign_training_card,
)


# Valid analysis types — used by ai_analysis.clear_analysis_cache signature.
ANALYSIS_TYPES = Literal[
    "categorization", "severity", "root_cause", "recommendations",
    "similar", "consistency", "company_consistency", "policy_mapping",
]



# Moved to services/ir/ir_incident_parsing.py (pure, no DB/routes) — aliased
# here so every existing `from ._shared import _detect_osha_reportable_keywords`
# inside this package keeps working.
from app.matcha.services.ir.ir_incident_parsing import (  # noqa: F401,E402
    _detect_osha_reportable_keywords,
)


def _build_public_link(request: Request, token: str, segment: str) -> str:
    """Build a public token URL under the given path ``segment``.

    Honors the X-Forwarded-Proto / Host pair set by nginx so links work
    behind the prod proxy as well as in local dev. Falls back to the
    request's own scheme/host if those headers aren't present.
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}/{segment}/{token}"


# Voice dictation upload validation — shared by the authed endpoint (voice.py)
# and the public token forms (inbound_email.py) so both enforce the same
# WAV-only contract. The RIFF/WAVE magic-byte check matters most for the
# unauthenticated callers (a forged content-type header could otherwise reach
# the expensive Gemini call), but there's no reason to make the authed path
# any looser, so both share this one implementation.
_ALLOWED_AUDIO_MIME = {"audio/wav", "audio/x-wav", "audio/wave"}
_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # ~13 min of 16kHz mono 16-bit WAV


async def _read_audio_or_400(file: UploadFile) -> bytes:
    """Validate the upload content-type/size/structure and return the bytes.

    content_type is client-controlled, so it is a hint, not a guarantee — the
    RIFF/WAVE magic-byte check is the real gate before spending a Gemini call.
    """
    if (file.content_type or "").lower() not in _ALLOWED_AUDIO_MIME:
        raise HTTPException(status_code=400, detail="Unsupported audio format — expected WAV.")
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    if len(audio) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large (max 25MB).")
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise HTTPException(status_code=400, detail="Unsupported audio format — expected WAV.")
    return audio


# ---------------------------------------------------------------------------
# Document upload validation — shared by the authed upload (documents.py) and
# the public per-location magic-link intake (inbound_email.py).
# ---------------------------------------------------------------------------

# Max IR document size on the authenticated path. Matches the voice-intake
# guard; keeps a single large upload from being buffered whole into memory
# unbounded.
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024

# Tighter caps for the *unauthenticated* magic-link intake. The authed path is
# bounded by a login; this one is bounded only by a token that may have leaked,
# so a submit can't spend 5 × 25MB of backend memory and S3 on one request.
MAX_INTAKE_FILES = 5
MAX_INTAKE_FILE_BYTES = 10 * 1024 * 1024
MAX_INTAKE_TOTAL_BYTES = 25 * 1024 * 1024

# Server-derived MIME per allowed extension. We do NOT trust the client-supplied
# content_type for storage: a .png uploaded as text/html would be a stored-XSS
# vector if the object is ever served inline. The stored/served type is derived
# from the validated extension here.
_EXT_MIME = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".csv": "text/csv",
    ".json": "application/json",
}

# Extensions that map to ir_incident_documents.document_type = 'photo'. The
# intake form has no type picker, so the type is derived from the extension.
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif"}


def validate_upload_name(filename: Optional[str]) -> tuple[str, str, str]:
    """Validate an upload's filename and derive its stored name/ext/MIME.

    Returns (safe_name, ext, mime). Raises 400 on a disallowed extension.

    The client filename is attacker-controlled: it can contain path separators
    or be absent entirely, so it is reduced to a bare basename before anything
    else touches it. The MIME comes from the validated extension, never from
    the client-supplied content_type.
    """
    raw_name = filename or ""
    safe_name = os.path.basename(raw_name.replace("\\", "/")).strip() or "upload"
    _, ext = os.path.splitext(safe_name)
    ext = ext.lower()
    if ext not in _EXT_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {sorted(_EXT_MIME)}",
        )
    return safe_name, ext, _EXT_MIME[ext]


def document_type_for_ext(ext: str) -> str:
    """Map a validated extension onto the ir_incident_documents type CHECK."""
    return "photo" if ext in _IMAGE_EXTS else "other"


# Lifted to services/_shared/uploads.py so matcha_work's handbook upload can bound
# its read too, without importing another route package. Aliased here so this
# package's `from ._shared import read_upload_capped` callers are unchanged.
from app.matcha.services._shared.uploads import read_upload_capped  # noqa: F401,E402


def _info_request_effective_status(row) -> str:
    """pending | submitted | expired | revoked for an ir_info_requests row.

    Expiry is derived at read time (mirrors ir_report_links' _link_status),
    not stored — shared by the admin-side list/serialize (info_requests.py)
    and the public-form usability gate (inbound_email.py) so the two never
    drift on what counts as "still usable".
    """
    if row["status"] in ("submitted", "revoked"):
        return row["status"]
    expires_at = row["expires_at"]
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        return "expired"
    return "pending"


def _sse(event: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


# Moved to services/ir/ir_incident_parsing.py (pure, no DB/routes) — aliased
# here so every existing `from ._shared import generate_incident_number` inside
# this package keeps working.
from app.matcha.services.ir.ir_incident_parsing import (  # noqa: F401,E402
    generate_incident_number,
)


async def log_audit(
    conn,
    incident_id: Optional[str],
    # Nullable: system-triggered actions (e.g. the Copilot auto-resume after an
    # anonymous respondent submits an info request) have no authenticated user.
    # ir_audit_log.user_id is a nullable FK, so NULL is a valid trail entry.
    user_id: Optional[str],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Log an action to the audit trail."""
    from app.core.services.audit_log import insert_audit_log

    await insert_audit_log(
        conn,
        table="ir_audit_log",
        id_column="incident_id",
        id_value=incident_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )


async def _resolve_employee_refs(
    conn,
    refs: Optional[list[str]],
    company_id: Optional[str],
) -> Optional[list[str]]:
    """Convert a mixed list of employee UUIDs and HR-internal UIDs to UUIDs.

    IR-only customers identify involved employees by badge / employee
    number rather than UUID. The form accepts either; persistence
    expects UUIDs (asyncpg array binding for the existing UUID[] column).
    UIDs are resolved per-company via employees.external_uid; unresolved
    references are dropped silently with a warning so a typo doesn't
    block the whole incident submission.
    """
    if not refs:
        return None
    out: list[str] = []
    pending_uids: list[str] = []
    for ref in refs:
        if not ref:
            continue
        try:
            UUID(str(ref))
            out.append(str(ref))
        except (ValueError, TypeError):
            pending_uids.append(str(ref).strip())
    if pending_uids and company_id:
        try:
            rows = await conn.fetch(
                """
                SELECT id::text AS id, external_uid
                FROM employees
                WHERE org_id = $1 AND external_uid = ANY($2::text[])
                """,
                company_id, pending_uids,
            )
            found = {r["external_uid"]: r["id"] for r in rows}
            for uid in pending_uids:
                if uid in found:
                    out.append(found[uid])
                else:
                    logger.warning("[IR] unresolved employee UID %s for company %s", uid, company_id)
        except Exception:
            logger.exception("[IR] employee UID resolution failed for company %s", company_id)
    return out or None


async def _hydrate_involved_employees(
    conn, company_id: Optional[str], ids,
) -> list[dict]:
    """Resolve involved_employee_ids (UUIDs) → roster employee detail.

    Returns [{id, first_name, last_name, job_title, department,
    employment_status}] ordered by name, scoped to the company's roster.
    Best-effort: an empty/unreachable roster yields []. Mirrors the
    name-resolution pattern in analytics.risk_insights.
    """
    if not company_id or not ids:
        return []
    uuids = [str(x) for x in ids if x]
    if not uuids:
        return []
    try:
        rows = await conn.fetch(
            """
            SELECT id, first_name, last_name, job_title, department, employment_status
            FROM employees
            WHERE org_id = $1 AND id = ANY($2::uuid[])
            ORDER BY last_name, first_name
            """,
            company_id, uuids,
        )
    except Exception as e:
        # Roster may be empty/unavailable for the tenant — don't fail the read.
        logger.info("[IR] involved-employee hydration skipped: %s", e)
        return []
    return [
        {
            "id": r["id"],
            "first_name": r["first_name"],
            "last_name": r["last_name"],
            "job_title": r["job_title"],
            "department": r["department"],
            "employment_status": r["employment_status"],
        }
        for r in rows
    ]


def _company_filter(param_idx: int) -> str:
    """Build a company_id filter clause for SQL queries."""
    return f"i.company_id = ${param_idx}"


# Both now live in services/_shared/time.py so services can reach them without
# importing this package (which runs the whole IR router __init__). Aliased to the
# private names this package's modules already import.
from app.matcha.services._shared.time import (  # noqa: F401,E402
    to_naive_utc as _to_naive_utc,
    utc_now_naive as _utc_now_naive,
)


# Moved to services/ir/ir_incident_parsing.py (pure, no DB/routes) — aliased
# here so every existing `from ._shared import _parse_occurred_at` inside this
# package and `from app.matcha.routes.ir_incidents import _parse_occurred_at`
# from inbound_email.py keep working.
from app.matcha.services.ir.ir_incident_parsing import (  # noqa: F401,E402
    _parse_occurred_at,
)


def _privacy_signal_overlay(signals: Optional[dict]) -> dict:
    """Build the category_data overlay of POSITIVE OSHA privacy signals from the
    AI extraction.

    Only includes keys worth setting — true flags, a real infectious agent, a
    non-empty injury_type / body_parts. It deliberately omits false/"none"
    defaults so the merge never writes a value that would block a later human
    override (and never falsely masks a case the AI didn't actually flag).
    """
    s = signals or {}
    overlay: dict = {}

    it = s.get("injury_type")
    if isinstance(it, str) and it.strip():
        overlay["injury_type"] = it.strip().lower()

    bps = s.get("body_parts")
    if isinstance(bps, list):
        cleaned = [str(b).strip().lower() for b in bps if str(b).strip()]
        if cleaned:
            overlay["body_parts"] = cleaned

    if s.get("intimate_injury") is True:
        overlay["intimate_injury"] = True
    if s.get("from_sexual_assault") is True:
        overlay["from_sexual_assault"] = True
    if s.get("contaminated_sharps") is True:
        overlay["contaminated_sharps"] = True

    agent = s.get("infectious_agent")
    if isinstance(agent, str) and agent.strip().lower() in ("hiv", "hepatitis", "tuberculosis", "other"):
        overlay["infectious_agent"] = agent.strip().lower()

    return overlay


async def _auto_classify_incident_task(
    incident_id: str,
    *,
    user_passed_type: bool,
    user_passed_severity: bool,
):
    """Best-effort AI auto-categorization triggered after IR submit.

    Runs categorize + severity in the background. Updates the row only
    when the corresponding field was inserted with the system default
    (so an explicit API caller passing `incident_type='safety'` is never
    overridden). Caches both analyses to ir_incident_analysis so the
    detail-view panels open without re-calling Gemini.

    Any failure is logged and swallowed — never re-raised.
    """
    try:
        from app.matcha.services.ir.ir_analysis import get_ir_analyzer, IRAnalysisError
    except Exception:  # pragma: no cover - import problems shouldn't crash submit
        logger.exception("[IR] Unable to import IRAnalyzer for auto-classify")
        return

    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, description, location, reported_by_name,
                       incident_type, severity, category_data
                FROM ir_incidents WHERE id = $1
                """,
                incident_id,
            )
        if not row:
            return

        analyzer = get_ir_analyzer()

        new_type: Optional[str] = None
        try:
            cat = await analyzer.categorize_incident(
                title=row["title"] or "",
                description=row["description"] or "",
                location=row["location"],
                reported_by=row["reported_by_name"],
            )
            async with get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                    VALUES ($1, 'categorization', $2)
                    """,
                    incident_id,
                    json.dumps(cat),
                )
                if not user_passed_type and cat.get("suggested_type"):
                    new_type = cat["suggested_type"]
                    await conn.execute(
                        "UPDATE ir_incidents SET incident_type = $1, updated_at = NOW() WHERE id = $2 AND incident_type = 'other'",
                        new_type,
                        incident_id,
                    )
        except IRAnalysisError as e:
            logger.warning(f"[IR] auto-categorize failed for {incident_id}: {e}")

        try:
            sev = await analyzer.assess_severity(
                title=row["title"] or "",
                description=row["description"] or "",
                incident_type=new_type or row["incident_type"] or "other",
                location=row["location"],
                category_data=_safe_json_loads(row["category_data"]) if row.get("category_data") else None,
            )
            async with get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                    VALUES ($1, 'severity', $2)
                    """,
                    incident_id,
                    json.dumps(sev),
                )
                if not user_passed_severity and sev.get("suggested_severity"):
                    await conn.execute(
                        "UPDATE ir_incidents SET severity = $1, updated_at = NOW() WHERE id = $2 AND severity = 'medium'",
                        sev["suggested_severity"],
                        incident_id,
                    )
        except IRAnalysisError as e:
            logger.warning(f"[IR] auto-severity failed for {incident_id}: {e}")

        # OSHA Privacy Case "data organization" — extract the structured signals
        # (intimate injury, sexual assault, infectious pathogen, contaminated
        # sharps + clinical injury_type / body_parts) so the deterministic
        # privacy-case rule can mask names with no one hand-typing them. Merged
        # into category_data WITHOUT clobbering existing keys (jsonb `||` with
        # existing on the right wins), so a human/Copilot entry always beats the
        # AI and only positive signals are written.
        try:
            signals = await analyzer.extract_privacy_signals(
                title=row["title"] or "",
                description=row["description"] or "",
            )
            overlay = _privacy_signal_overlay(signals)
            if overlay:
                async with get_connection() as conn:
                    await conn.execute(
                        """
                        UPDATE ir_incidents
                        SET category_data = $2::jsonb || COALESCE(category_data, '{}'::jsonb),
                            updated_at = NOW()
                        WHERE id = $1
                        """,
                        incident_id,
                        json.dumps(overlay),
                    )
        except IRAnalysisError as e:
            logger.warning(f"[IR] privacy-signal extraction failed for {incident_id}: {e}")
        except Exception:
            logger.exception(f"[IR] privacy-signal extraction crashed for {incident_id}")

        # NOTE: the OSHA Description (Column F) name-cleanse is NOT run here.
        # It moved to the recordable workflow — only incidents marked OSHA
        # recordable reach the 300 log, so the cleanse is generated then and
        # shown to the human for approval/edit before it prints
        # (build_osha_clean_description_card + copilot._emit_osha_description_review).

    except Exception:
        logger.exception(f"[IR] auto-classify task crashed for {incident_id}")


async def _get_incident_with_company_check(conn, incident_id: UUID, current_user, columns: str = "*"):
    """Fetch an incident row after verifying company ownership. Raises 404 if not found."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = "company_id = $2"
    row = await conn.fetchrow(
        f"SELECT {columns} FROM ir_incidents WHERE id = $1 AND {company_clause}",
        str(incident_id),
        company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    return row


# Lives in services/_shared/jsonio.py so services can reach it without importing
# this package. Aliased to the private name this package's modules already import.
from app.matcha.services._shared.jsonio import (  # noqa: F401,E402
    safe_json_loads as _safe_json_loads,
)


def parse_witnesses(witnesses_json) -> list[Witness]:
    """Parse witnesses from JSONB."""
    if not witnesses_json:
        return []
    try:
        if isinstance(witnesses_json, str):
            witnesses_json = json.loads(witnesses_json)
        return [Witness(**w) for w in witnesses_json]
    except (json.JSONDecodeError, TypeError, ValueError, KeyError) as e:
        logger.warning(f"Failed to parse witnesses: {e}")
        return []



def _location_label(name: Optional[str], city: Optional[str], state: Optional[str]) -> str:
    """Human-readable location label, mirroring the frontend `locationLabel`.

    "Name — City, ST", falling back to whichever parts exist. Used for the
    free-text `ir_incidents.location` mirror and the public intake header.
    """
    name = (name or "").strip()
    place = ", ".join(p for p in (city, state) if p)
    if name and place:
        return f"{name} — {place}"
    return name or place or "Location"


def row_to_response(row, document_count: int = 0) -> IRIncidentResponse:
    """Convert a database row to IRIncidentResponse."""
    return IRIncidentResponse(
        id=row["id"],
        incident_number=row["incident_number"],
        title=row["title"],
        description=row["description"],
        incident_type=row["incident_type"],
        severity=row["severity"],
        status=row["status"],
        occurred_at=row["occurred_at"],
        location=row["location"],
        reported_by_name=row["reported_by_name"],
        reported_by_email=row["reported_by_email"],
        reported_at=row["reported_at"],
        assigned_to=row["assigned_to"],
        witnesses=parse_witnesses(row.get("witnesses")),
        category_data=_safe_json_loads(row.get("category_data"), {}),
        root_cause=row["root_cause"],
        corrective_actions=row["corrective_actions"],
        involved_employee_ids=row.get("involved_employee_ids") or [],
        involved_people=row.get("involved_people") or [],
        involved_employees=row.get("involved_employees") or [],
        er_case_id=row.get("er_case_id"),
        document_count=document_count,
        company_id=row.get("company_id"),
        location_id=row.get("location_id"),
        company_name=row.get("company_name"),
        location_name=row.get("location_name"),
        location_city=row.get("location_city"),
        location_state=row.get("location_state"),
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        resolved_at=row["resolved_at"],
        osha_recordable=row.get("osha_recordable"),
        wc_claim_type=row.get("wc_claim_type"),
        post_termination=row.get("post_termination"),
        return_to_work_date=row.get("return_to_work_date"),
    )
