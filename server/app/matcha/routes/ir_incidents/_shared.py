"""Shared helpers for IR Incidents submodules.

Cross-cutting utilities used by more than one submodule. Promoted out of
the original flat `ir_incidents.py` during the package split.
"""
import asyncio
import json
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import HTTPException

from app.core.services.email import get_email_service
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id
from app.matcha.models.ir_incident import IRIncidentResponse, Witness


logger = logging.getLogger(__name__)


# Valid analysis types — used by ai_analysis.clear_analysis_cache signature.
ANALYSIS_TYPES = Literal[
    "categorization", "severity", "root_cause", "recommendations",
    "similar", "consistency", "company_consistency", "policy_mapping",
]


# OSHA 300 form M-column injury/illness type values. Stashed in
# ir_incidents.osha_form_301_data->>'injury_type' so 300A aggregation
# can group on them without an Alembic migration.
OSHA_INJURY_TYPES = {
    "injury", "skin_disorder", "respiratory",
    "poisoning", "hearing_loss", "other_illness",
}

OSHA_INJURY_TYPE_LABELS = {
    "injury": "Standard Injury",
    "skin_disorder": "Skin Disorder",
    "respiratory": "Respiratory Condition",
    "poisoning": "Poisoning",
    "hearing_loss": "Hearing Loss",
    "other_illness": "All Other",
}


# Severe keywords that mandate an immediate OSHA reportable-event call
# (8 hours for fatality, 24 hours for amputation / lost eye / in-patient
# hospitalization — 29 CFR 1904.39). Detection runs on incident creation
# against the title+description; a hit flips severity to critical and
# pushes the emergency alert card into the Copilot transcript.
_OSHA_REPORTABLE_KEYWORD_RE = re.compile(
    r"\b("
    r"fatalit(?:y|ies)"
    r"|passed\s+away"
    r"|(?:was|were)\s+killed"
    r"|(?:was|were|has)\s+died"
    r"|amputat(?:e|ed|ion|ing)"
    r"|lost\s+(?:an?\s+|his\s+|her\s+|their\s+)?eye"
    r"|hospitali[sz]ed"
    r"|hospitali[sz]ation"
    r"|in-?patient\s+admission"
    r")\b",
    re.IGNORECASE,
)


def _detect_osha_reportable_keywords(text: Optional[str]) -> bool:
    """True if text mentions a 29 CFR 1904.39 reportable-event term.

    False on None / empty / no match. Boundary-anchored so false-friends
    like "studied" or "skilled" don't match (no overlap with the pattern
    anyway, but the word boundary keeps it safe against future additions).
    """
    if not text:
        return False
    return bool(_OSHA_REPORTABLE_KEYWORD_RE.search(text))


def _sse(event: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


def generate_incident_number() -> str:
    """Generate a unique incident number."""
    now = datetime.now(timezone.utc)
    random_suffix = secrets.token_hex(2).upper()
    return f"IR-{now.year}-{now.month:02d}-{random_suffix}"


async def log_audit(
    conn,
    incident_id: Optional[str],
    user_id: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Log an action to the audit trail."""
    await conn.execute(
        """
        INSERT INTO ir_audit_log (incident_id, user_id, action, entity_type, entity_id, details, ip_address)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        incident_id,
        user_id,
        action,
        entity_type,
        entity_id,
        json.dumps(details) if details else None,
        ip_address,
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


# ===========================================
# IR People — lightweight per-person identity (matcha-lite, no roster)
# ===========================================
#
# People named in incidents get a stable id WITHOUT a managed employee
# roster: identity is the typed name, normalized for dedup. This is
# distinct from `involved_employee_ids` (which targets the real
# `employees` table). Name-based identity trades exactness for zero
# upkeep — two genuinely-different "John Smith"s collapse to one row; the
# `verified` flag exists so a future manual-merge/confirm step can split
# or promote them. The create form's type-ahead nudges consistent
# spelling so the dedup actually catches repeats.

IR_PERSON_ROLES = ("reporter", "involved", "witness", "interviewee")

# Roles owned by the incident create/update body. Interviewee rows are
# managed separately by the investigation-interview endpoints, so a
# re-sync from incident edit must NOT delete them.
IR_INCIDENT_BODY_ROLES = ("reporter", "involved", "witness")

_WS_RE = re.compile(r"\s+")


def _normalize_person_name(name: Optional[str]) -> str:
    """Casefold + collapse whitespace for dedup matching. '' if blank."""
    if not name:
        return ""
    return _WS_RE.sub(" ", str(name).strip()).casefold()


def _gather_incident_people(
    *,
    reported_by_name: Optional[str] = None,
    reported_by_email: Optional[str] = None,
    witnesses=None,
    category_data: Optional[dict] = None,
) -> list[tuple[str, Optional[str], str]]:
    """Extract (display_name, email, role) tuples from an incident's people
    fields. Roles: reporter, witness (witnesses JSONB), involved
    (category_data injured_person + parties_involved). Blank names dropped.
    """
    out: list[tuple[str, Optional[str], str]] = []

    if reported_by_name and reported_by_name.strip().lower() not in ("", "anonymous", "unknown"):
        out.append((reported_by_name.strip(), (reported_by_email or None), "reporter"))

    for w in (witnesses or []):
        name = getattr(w, "name", None) if not isinstance(w, dict) else w.get("name")
        contact = getattr(w, "contact", None) if not isinstance(w, dict) else w.get("contact")
        if name and name.strip():
            out.append((name.strip(), (contact or None), "witness"))

    cd = category_data or {}
    injured = cd.get("injured_person")
    if injured and str(injured).strip():
        out.append((str(injured).strip(), None, "involved"))
    for party in (cd.get("parties_involved") or []):
        pname = party.get("name") if isinstance(party, dict) else None
        if pname and str(pname).strip():
            out.append((str(pname).strip(), None, "involved"))

    return out


async def _upsert_ir_person(
    conn, company_id: str, name: str, email: Optional[str] = None,
) -> Optional[str]:
    """Insert-or-touch an ir_people row by normalized name. Returns id."""
    norm = _normalize_person_name(name)
    if not norm or not company_id:
        return None
    row = await conn.fetchrow(
        """
        INSERT INTO ir_people (company_id, display_name, normalized_name, email)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (company_id, normalized_name)
        DO UPDATE SET last_seen = NOW(),
                      email = COALESCE(ir_people.email, EXCLUDED.email)
        RETURNING id::text AS id
        """,
        company_id, name.strip(), norm, (email or None),
    )
    return row["id"] if row else None


async def _link_incident_person(
    conn, company_id: str, incident_id: str, name: str,
    email: Optional[str], role: str,
) -> None:
    """Upsert a person and attach them to an incident in a given role."""
    person_id = await _upsert_ir_person(conn, company_id, name, email)
    if not person_id:
        return
    await conn.execute(
        """
        INSERT INTO ir_incident_people (incident_id, person_id, role)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING
        """,
        incident_id, person_id, role,
    )


async def _sync_incident_people(
    conn, company_id: Optional[str], incident_id: str,
    entries: list[tuple[str, Optional[str], str]],
    managed_roles: tuple[str, ...] = IR_INCIDENT_BODY_ROLES,
) -> None:
    """Re-sync an incident's people rows for the managed roles.

    Delete-and-reinsert scoped to ``managed_roles`` so interviewee links
    (owned by the interview endpoints) survive an incident edit. Best-effort
    by contract — callers wrap this and swallow failures so identity tracking
    never blocks incident submission.
    """
    if not company_id:
        return
    await conn.execute(
        "DELETE FROM ir_incident_people WHERE incident_id = $1 AND role = ANY($2::text[])",
        incident_id, list(managed_roles),
    )
    for name, email, role in entries:
        if role in managed_roles:
            await _link_incident_person(conn, company_id, incident_id, name, email, role)


def _company_filter(param_idx: int) -> str:
    """Build a company_id filter clause for SQL queries."""
    return f"i.company_id = ${param_idx}"


def _to_naive_utc(value: datetime) -> datetime:
    """Normalize datetimes to naive UTC for TIMESTAMP (without timezone) columns."""
    if value.tzinfo:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _utc_now_naive() -> datetime:
    """Return current UTC time as naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_occurred_at(value) -> datetime:
    """Coerce IR submit `occurred_at` to a naive UTC datetime.

    Accepts a real datetime (from rich clients / admin tooling) or a free
    text string from the slim submit form ("yesterday at 3pm", "May 1 4pm").
    Falls back to NOW() on parse failure rather than 400'ing — incident
    capture should never block on a date typo.
    """
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return _utc_now_naive()
        try:
            from dateutil import parser as _date_parser
            parsed = _date_parser.parse(text, fuzzy=True)
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except (ValueError, OverflowError, TypeError):
            return _utc_now_naive()
    return _utc_now_naive()


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
        from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError
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

    except Exception:
        logger.exception(f"[IR] auto-classify task crashed for {incident_id}")


async def _get_company_admin_contacts(company_id: str) -> tuple[str, list[dict[str, str]]]:
    """Return company display name and company-admin/client email recipients."""
    async with get_connection() as conn:
        company_name = await conn.fetchval(
            "SELECT name FROM companies WHERE id = $1",
            company_id,
        ) or "Your company"

        rows = await conn.fetch(
            """
            SELECT DISTINCT
                u.email,
                COALESCE(NULLIF(c.name, ''), split_part(u.email, '@', 1)) AS name
            FROM clients c
            JOIN users u ON u.id = c.user_id
            WHERE c.company_id = $1
              AND u.is_active = true
              AND u.email IS NOT NULL
            ORDER BY u.email
            """,
            company_id,
        )

    contacts = [
        {"email": row["email"], "name": row["name"] or row["email"]}
        for row in rows
    ]
    return company_name, contacts


async def send_ir_notifications_task(
    *,
    company_id: str,
    incident_id: str,
    incident_number: str,
    incident_title: str,
    event_type: str,
    current_status: str,
    changed_by_email: Optional[str] = None,
    previous_status: Optional[str] = None,
    location_name: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
):
    """Send IR lifecycle notifications to company admins in the background."""
    email_service = get_email_service()
    if not email_service.is_configured():
        logger.info("[IR] Email service not configured - skipping IR notifications")
        return

    company_name, contacts = await _get_company_admin_contacts(company_id)
    if not contacts:
        logger.info(f"[IR] No admin/client contacts found for company {company_id}")
        return

    tasks = [
        email_service.send_ir_incident_notification_email(
            to_email=contact["email"],
            to_name=contact.get("name"),
            company_name=company_name,
            incident_id=incident_id,
            incident_number=incident_number,
            incident_title=incident_title,
            event_type=event_type,
            current_status=current_status,
            changed_by_email=changed_by_email,
            previous_status=previous_status,
            location_name=location_name,
            occurred_at=occurred_at,
        )
        for contact in contacts
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    sent_count = 0
    for contact, result in zip(contacts, results):
        if isinstance(result, Exception):
            logger.warning(f"[IR] Failed to notify {contact['email']}: {result}")
            continue
        if result:
            sent_count += 1

    if sent_count:
        logger.info(f"[IR] Sent {sent_count}/{len(contacts)} IR notification email(s)")
    else:
        logger.warning("[IR] IR notifications attempted but no emails were sent successfully")


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


def _safe_json_loads(value, default=None):
    """Safely parse JSON from a database value."""
    if value is None:
        return default if default is not None else {}
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return default if default is not None else {}


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


# ===========================================
# OSHA emergency alert helpers
# ===========================================

OSHA_EMERGENCY_ALERT_CARD_ID = "osha_emergency_alert"
OSHA_EMERGENCY_HOTLINE = "1-800-321-6742"
OSHA_REPORTING_WINDOW = "8 to 24 hours"


def build_osha_emergency_alert_card() -> dict:
    """Build the static emergency alert card payload (29 CFR 1904.39).

    Same shape every emit so the frontend can render it with a fixed
    component. ``content`` is the title (used as message_type='card'
    content column); the full card sits under ``metadata.card`` per the
    transcript convention.
    """
    return {
        "id": OSHA_EMERGENCY_ALERT_CARD_ID,
        "title": "⚠️ CRITICAL: OSHA Reporting Required",
        "recommendation": (
            "Based on the severity of this incident, you may be legally "
            "required to report this directly to OSHA within "
            f"{OSHA_REPORTING_WINDOW}."
        ),
        "rationale": (
            "29 CFR 1904.39 mandates calling OSHA within 8 hours for any "
            "work-related fatality and within 24 hours for any in-patient "
            "hospitalization, amputation, or loss of an eye."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "osha_emergency_alert",
            "label": "I've reported it",
            "phone": OSHA_EMERGENCY_HOTLINE,
            "deadline": OSHA_REPORTING_WINDOW,
        },
    }


def build_osha_recordable_query_card() -> dict:
    """Yes/No: does the incident qualify as an OSHA recordable event?"""
    return {
        "id": "osha_recordable_query",
        "title": "OSHA Recordable Event",
        "recommendation": "Does this qualify as an OSHA recordable event?",
        "rationale": (
            "Treatment beyond on-site first aid generally makes an injury "
            "OSHA recordable (29 CFR 1904.7). Confirm so we can populate "
            "the OSHA 300/300A logs."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "osha_recordable_query",
            "choices": [
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        },
    }


def build_osha_days_type_query_card() -> dict:
    """Days Away / Job Restriction / Neither — drives osha_classification."""
    return {
        "id": "osha_days_type_query",
        "title": "OSHA Case Classification",
        "recommendation": (
            "Did this result in days away from work or a temporary job restriction?"
        ),
        "rationale": (
            "Drives column J/K/L on OSHA Form 300 (case classification). "
            "Pick Neither for medical-treatment-only cases."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "osha_days_type_query",
            "choices": [
                {"label": "Days Away", "value": "days_away"},
                {"label": "Job Restriction", "value": "restricted_duty"},
                {"label": "Neither", "value": "neither"},
            ],
        },
    }


def build_osha_days_count_card(*, target_field: str, pending_classification: str) -> dict:
    """Numeric input: how many days away / restricted?"""
    label_word = "away from work" if target_field == "days_away_from_work" else "on job restriction"
    return {
        "id": f"osha_days_count__{pending_classification}",
        "title": f"Days {label_word.title()}",
        "recommendation": f"How many days {label_word}?",
        "rationale": "Enter the total days (1-365). This populates the OSHA 300 day-count columns.",
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "numeric_input",
            "label": "Save",
            "target_field": target_field,
            "pending_classification": pending_classification,
            "input_label": "Days",
            "input_min": 1,
            "input_max": 365,
        },
    }


def build_osha_injury_type_query_card() -> dict:
    """6-button picker — OSHA 300 M-column injury/illness type."""
    return {
        "id": "osha_injury_type_query",
        "title": "Injury / Illness Type",
        "recommendation": "How would you classify this injury?",
        "rationale": (
            "Drives the M-columns on OSHA Form 300A (Injury / Skin Disorder / "
            "Respiratory / Poisoning / Hearing Loss / All Other Illnesses)."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "osha_injury_type_query",
            "choices": [
                {"label": OSHA_INJURY_TYPE_LABELS[k], "value": k}
                for k in ("injury", "skin_disorder", "respiratory", "poisoning", "hearing_loss", "other_illness")
            ],
        },
    }


# ===========================================
# Root-cause interview chain (replaces AI-driven run_analysis root_cause)
# ===========================================
#
# The orchestrator used to recommend `run_analysis root_cause`, but the
# analyzer only sees the initial title+description and produces generic
# guesses (or stale failures). Per customer feedback, the Copilot now
# captures root cause via a structured 3-question interview: Hazard /
# Why / Prevention. Answers persist verbatim — no AI synthesis.

ROOT_CAUSE_INTERVIEW_STEPS: tuple[str, ...] = ("hazard", "why", "prevention")

ROOT_CAUSE_PROMPTS = {
    "hazard": "What was the hazard?",
    "why": "Why did it happen?",
    "prevention": "How can we prevent it?",
}

ROOT_CAUSE_PLAINTEXT_LABELS = {
    "hazard": "Hazard",
    "why": "Why it happened",
    "prevention": "Prevention",
}


def build_log_root_cause_query_card() -> dict:
    """Yes/No: kick off the root-cause interview chain."""
    return {
        "id": "log_root_cause_query",
        "title": "Log Root Cause",
        "recommendation": "Would you like to log the root cause?",
        "rationale": (
            "Capture the hazard, why it happened, and how to prevent it in "
            "your own words. We save the answers verbatim — no AI guesses."
        ),
        "priority": "medium",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "log_root_cause_query",
            "choices": [
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        },
    }


def build_root_cause_text_card(*, step: str) -> dict:
    """One text_input card per interview step. ``step`` must be in
    ROOT_CAUSE_INTERVIEW_STEPS — the dispatcher reads it from action.target_field
    to know which JSONB key to write and which step is next."""
    if step not in ROOT_CAUSE_INTERVIEW_STEPS:
        raise ValueError(f"Unknown root-cause step: {step}")
    prompt = ROOT_CAUSE_PROMPTS[step]
    return {
        "id": f"root_cause_interview__{step}",
        "title": f"Root cause — {ROOT_CAUSE_PLAINTEXT_LABELS[step]}",
        "recommendation": prompt,
        "rationale": (
            "Type your answer in your own words. Saved exactly as written."
        ),
        "priority": "medium",
        "blockers": [],
        "action": {
            "type": "text_input",
            "label": "Save",
            "target_field": step,
            "prompt_text": prompt,
            "input_label": "Answer",
            "input_rows": 3,
        },
    }


def build_root_cause_logged_ack_card() -> dict:
    """Final 'Root cause logged' ack — informational, no further action."""
    return {
        "id": "root_cause_logged",
        "title": "Root cause logged",
        "recommendation": "Saved your hazard / why / prevention answers.",
        "rationale": (
            "The combined entry is now on the incident and feeds the OSHA 301 "
            "form, broker reports, and the AI Analysis tab."
        ),
        "priority": "low",
        "blockers": [],
        "action": {
            "type": "request_info",
            "label": "Got it",
        },
    }


def compose_root_cause_text(interview: dict) -> str:
    """Render the three interview answers into the plain-text format we
    write to ir_incidents.root_cause TEXT. Missing steps surface as empty
    blocks rather than silently dropping — keeps the schema consistent.
    """
    parts: list[str] = []
    for step in ROOT_CAUSE_INTERVIEW_STEPS:
        answer = (interview or {}).get(step) or ""
        label = ROOT_CAUSE_PLAINTEXT_LABELS[step]
        parts.append(f"{label}: {answer.strip()}")
    return "\n\n".join(parts)


def build_osha_close_confirmation_card() -> dict:
    """Final close card after the OSHA chain completes."""
    return {
        "id": "osha_close_confirmation",
        "title": "Close incident",
        "recommendation": "OSHA capture complete. Close this incident?",
        "rationale": "All OSHA 300 fields recorded. You can close the incident now.",
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "close_incident",
            "label": "Close incident",
        },
    }


# ===========================================
# Injury assessment + document capture (deterministic flow engine)
# ===========================================

def build_treatment_query_card() -> dict:
    """Yes/No: was treatment provided beyond basic on-site first aid?

    The injury-assessment gate. A "yes" makes the injury OSHA-recordable
    (29 CFR 1904.7) and kicks off the recordable chain. Handled by
    ``_handle_quick_reply`` under quick_reply_kind 'treatment_query', which
    writes category_data.treatment_beyond_first_aid.
    """
    return {
        "id": "treatment_query",
        "title": "Injury Assessment",
        "recommendation": "Was any treatment provided beyond basic on-site first aid?",
        "rationale": (
            "Treatment beyond first aid — stitches, prescription medication, "
            "work restrictions, or similar — generally makes an injury OSHA "
            "recordable (29 CFR 1904.7)."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "quick_reply",
            "label": "Choose one",
            "quick_reply_kind": "treatment_query",
            "choices": [
                {"label": "Yes — beyond first aid", "value": "yes"},
                {"label": "No — first aid only", "value": "no"},
            ],
        },
    }


def build_request_documents_card() -> dict:
    """Prompt the user to attach supporting documents to the incident.

    Handled by the ``request_documents`` action in accept_copilot_card, which
    re-checks the ir_incident_documents count and marks
    category_data.documents_prompted so the flow advances whether the user
    uploads or explicitly skips. The frontend opens the Documents upload zone.
    """
    return {
        "id": "request_documents",
        "title": "Attach supporting documents",
        "recommendation": (
            "Upload any photos, witness statements, medical or first-aid "
            "records, or incident forms related to this report."
        ),
        "rationale": (
            "Documentation strengthens the record for OSHA, insurance, and "
            "legal defense. Attach what you have — or skip if there's nothing "
            "to add."
        ),
        "priority": "medium",
        "blockers": [],
        "action": {
            "type": "request_documents",
            "label": "Open upload",
        },
    }


async def _persist_osha_emergency_alert(conn, incident_id: str, current_user) -> None:
    """Flip severity to critical, mark the alert active in category_data,
    and persist the emergency card to the Copilot transcript.

    Idempotent: a second call on the same incident skips re-persisting the
    card if one already exists (e.g. background classifier re-triggered).
    """
    await conn.execute(
        """
        UPDATE ir_incidents
        SET severity = 'critical',
            category_data = jsonb_set(
                COALESCE(category_data, '{}'::jsonb),
                '{osha_emergency_alert_active}',
                'true'::jsonb,
                true
            )
        WHERE id = $1
        """,
        incident_id,
    )

    existing = await conn.fetchval(
        """
        SELECT 1 FROM ir_incident_ai_messages
        WHERE incident_id = $1
          AND message_type = 'card'
          AND metadata->'card'->>'id' = $2
        LIMIT 1
        """,
        incident_id,
        OSHA_EMERGENCY_ALERT_CARD_ID,
    )
    if existing:
        return

    # Inline assistant directive — must precede the card insert so
    # _extract_current_cards in copilot.py treats the alert as part of
    # the current round (it walks messages and only includes assistant
    # cards after the most recent assistant text marker). Without this
    # text the panel sees a transcript with no active round and renders
    # the alert card with no guidance copy above it — looks inert.
    user_id_str = (
        str(current_user.id) if current_user and getattr(current_user, "id", None) else None
    )
    directive_text = (
        "Severity flipped to critical because the report describes a "
        "potential OSHA reportable event (29 CFR 1904.39). Acknowledge "
        "the alert below with your reporting notes, then we'll capture "
        "the OSHA recordable details for the 300 log."
    )
    directive_metadata = {
        "open_questions": [],
        "model": "osha_emergency_inline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await conn.execute(
        """
        INSERT INTO ir_incident_ai_messages
          (incident_id, role, message_type, content, metadata, created_by)
        VALUES ($1, 'assistant', 'text', $2, $3::jsonb, $4)
        """,
        incident_id,
        directive_text,
        json.dumps(directive_metadata),
        user_id_str,
    )

    card = build_osha_emergency_alert_card()
    metadata = {"card": card, "accepted": False}
    await conn.execute(
        """
        INSERT INTO ir_incident_ai_messages
          (incident_id, role, message_type, content, metadata, created_by)
        VALUES ($1, 'assistant', 'card', $2, $3::jsonb, $4)
        """,
        incident_id,
        card["title"],
        json.dumps(metadata),
        user_id_str,
    )


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


async def create_incident_core(
    conn,
    *,
    company_id: Optional[str],
    description: Optional[str],
    occurred_at,
    reported_by_name: str,
    title: Optional[str] = None,
    incident_type: Optional[str] = None,
    severity: Optional[str] = None,
    location: Optional[str] = None,
    location_id: Optional[str] = None,
    reported_by_email: Optional[str] = None,
    witnesses: Optional[list] = None,
    category_data: Optional[dict] = None,
    involved_employee_ids: Optional[list[str]] = None,
    corrective_actions: Optional[str] = None,
    created_by: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    actor_ip: Optional[str] = None,
    current_user=None,
) -> tuple[dict, list]:
    """Insert an incident + run the shared post-insert mechanics.

    Shared by the authenticated create route (`crud.create_incident`) and the
    public location magic-link intake (`inbound_email.submit_location_report`)
    so both paths produce identical-quality incidents: real `location_id`,
    witnesses, the per-person identity index, OSHA emergency detection, and the
    same AI auto-classify + policy-map + notification background jobs.

    The CALLER owns the connection and its tenant scoping — the authed path uses
    `get_connection()`; the public token path uses
    `get_connection(tenant_id=company_id)` so the INSERT clears RLS — as well as
    transaction boundaries. This function never opens its own connection.

    Returns `(response_row, bg_tasks)` where `response_row` is a dict augmented
    with company/location names (ready for `row_to_response`) and `bg_tasks` is a
    list of `(fn, args, kwargs)` tuples the caller schedules on its own
    `BackgroundTasks` (or awaits). Deferring them lets the caller commit the
    transaction first and keeps this function connection-agnostic.
    """
    witnesses = witnesses or []
    incident_number = generate_incident_number()
    occurred_at_dt = _parse_occurred_at(occurred_at)

    # Track whether the caller explicitly set type/severity so the background
    # classifier knows whether to override the system defaults.
    user_passed_type = incident_type is not None
    user_passed_severity = severity is not None and severity != "medium"
    effective_type = incident_type or "other"
    effective_severity = severity or "medium"

    # Title derives from the description's first line when not supplied (the
    # slim + public forms drop the Title field entirely).
    raw_title = (title or "").strip()
    if not raw_title:
        body = (description or "Incident").strip()
        first_line = body.splitlines()[0] if body else "Incident"
        raw_title = first_line[:80].strip() or "Incident"
    effective_title = raw_title

    row = await conn.fetchrow(
        """
        INSERT INTO ir_incidents (
            incident_number, title, description, incident_type, severity,
            occurred_at, location, reported_by_name, reported_by_email,
            witnesses, category_data, involved_employee_ids,
            company_id, location_id, created_by, corrective_actions
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        RETURNING *
        """,
        incident_number,
        effective_title,
        description,
        effective_type,
        effective_severity,
        occurred_at_dt,
        location,
        reported_by_name,
        reported_by_email,
        json.dumps([w.model_dump() if hasattr(w, "model_dump") else w for w in witnesses]),
        json.dumps(category_data or {}),
        involved_employee_ids,
        company_id,
        (str(location_id) if location_id else None),
        created_by,
        (corrective_actions or None),
    )

    # Resolve company / location names for the response payload.
    company_name = None
    location_name = None
    location_city = None
    location_state = None
    if company_id:
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
        if company:
            company_name = company["name"]
    if row.get("location_id"):
        loc = await conn.fetchrow(
            "SELECT name, city, state FROM business_locations WHERE id = $1",
            row["location_id"],
        )
        if loc:
            location_name = loc["name"]
            location_city = loc["city"]
            location_state = loc["state"]

    # Audit — only when there's an actor (public intake has no user).
    if actor_user_id:
        await log_audit(
            conn,
            str(row["id"]),
            actor_user_id,
            "incident_created",
            "incident",
            str(row["id"]),
            {"title": effective_title, "type": effective_type},
            actor_ip,
        )

    # Per-person identity index (best-effort; never blocks submit).
    if company_id:
        try:
            people = _gather_incident_people(
                reported_by_name=row.get("reported_by_name"),
                reported_by_email=row.get("reported_by_email"),
                witnesses=witnesses,
                category_data=category_data,
            )
            await _sync_incident_people(conn, str(company_id), str(row["id"]), people)
        except Exception:
            logger.exception("[IR] people sync failed for incident %s", row.get("id"))

    # OSHA reportable-event (29 CFR 1904.39) emergency detection — flips
    # severity to critical and drops the alert card into the Copilot transcript.
    if _detect_osha_reportable_keywords(f"{effective_title}\n{description or ''}"):
        await _persist_osha_emergency_alert(conn, str(row["id"]), current_user)
        row = await conn.fetchrow("SELECT * FROM ir_incidents WHERE id = $1", row["id"])

    response_row = dict(row)
    response_row["company_name"] = company_name
    response_row["location_name"] = location_name
    response_row["location_city"] = location_city
    response_row["location_state"] = location_state

    # Post-commit background work — assembled here, scheduled by the caller.
    bg_tasks: list = []
    if company_id:
        bg_tasks.append((
            send_ir_notifications_task,
            (),
            dict(
                company_id=str(company_id),
                incident_id=str(row["id"]),
                incident_number=row["incident_number"],
                incident_title=row["title"],
                event_type="created",
                current_status=row["status"],
                changed_by_email=actor_email,
                previous_status=None,
                location_name=location_name or row.get("location"),
                occurred_at=row.get("occurred_at"),
            ),
        ))
        bg_tasks.append((
            _auto_classify_incident_task,
            (str(row["id"]),),
            dict(user_passed_type=user_passed_type, user_passed_severity=user_passed_severity),
        ))
        # Lazy import: ai_analysis imports from _shared, so a module-level import
        # here would be circular (same pattern crud.create_incident used).
        from .ai_analysis import _auto_map_policy_violations
        bg_tasks.append((
            _auto_map_policy_violations,
            (str(row["id"]), str(company_id)),
            {},
        ))

    return response_row, bg_tasks


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
    )
