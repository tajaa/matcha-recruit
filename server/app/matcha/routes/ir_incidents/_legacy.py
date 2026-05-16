"""IR (Incident Report) API Routes.

Incident Report management for HR departments:
- Incidents CRUD
- Document upload
- AI analysis (categorization, severity, root cause, recommendations)
- Analytics dashboard
"""

import csv
import io
import json
import logging
import secrets
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request, Query, BackgroundTasks
from fastapi.responses import StreamingResponse

from app.database import get_connection
from app.core.dependencies import require_admin
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.config import get_settings
from app.core.services.storage import get_storage
from app.core.services.email import get_email_service
from app.matcha.models.ir_incident import (
    IRCopilotAcceptRequest,
    IRCopilotCard,
    IRCopilotMessage,
    IRCopilotStreamRequest,
    IRCopilotTranscript,
    IRIncidentCreate,
    IRIncidentUpdate,
    IRIncidentResponse,
    IRIncidentListResponse,
    IRDocumentResponse,
    IRDocumentUploadResponse,
    CategorizationAnalysis,
    SeverityAnalysis,
    RootCauseAnalysis,
    RecommendationsAnalysis,
    PrecedentMatch,
    PrecedentAnalysis,
    ActionProbability,
    ConsistencyGuidance,
    ConsistencyAnalytics,
    PolicyMappingAnalysis,
    AnalyticsSummary,
    TrendsAnalysis,
    TrendDataPoint,
    LocationAnalysis,
    LocationHotspot,
    RiskMatrixCell,
    RiskMatrixRow,
    RiskMatrixResponse,
    RiskTheme,
    RiskInsightsResponse,
    IRAuditLogEntry,
    IRAuditLogResponse,
    Witness,
    OshaRecordabilityUpdate,
    Osha300LogEntry,
    Osha300ASummary,
)
from app.matcha.models.interview import (
    InvestigationInterviewCreate,
    InvestigationInterviewResponse,
    InvestigationInterviewStart,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Valid analysis types
ANALYSIS_TYPES = Literal["categorization", "severity", "root_cause", "recommendations", "similar", "consistency", "company_consistency", "policy_mapping"]


def _sse(event: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


# ===========================================
# Helper Functions
# ===========================================

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


# ===========================================
# Incidents CRUD
# ===========================================

@router.post("", response_model=IRIncidentResponse)
async def create_incident(
    incident: IRIncidentCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin_or_client),
):
    """Create a new incident report."""
    incident_number = generate_incident_number()
    scoped_company_id = await get_client_company_id(current_user)
    if current_user.role == "admin":
        effective_company_id = (
            str(incident.company_id)
            if incident.company_id
            else (str(scoped_company_id) if scoped_company_id else None)
        )
    else:
        # Clients are always scoped to their own company.
        effective_company_id = str(scoped_company_id) if scoped_company_id else None

    # The slim submit form sends free-text dates ("yesterday at 3pm"); the
    # rich admin path still sends ISO datetimes. Helper handles both and
    # falls back to NOW() on parse failure.
    occurred_at = _parse_occurred_at(incident.occurred_at)

    # Track whether the caller explicitly set type/severity so the
    # background classifier knows whether to override.
    user_passed_type = incident.incident_type is not None
    user_passed_severity = (
        incident.severity is not None and incident.severity != "medium"
    )

    effective_type = incident.incident_type or "other"
    effective_severity = incident.severity or "medium"

    # Title derives from the description if the caller didn't provide one
    # (the slim form drops the Title field entirely).
    raw_title = (incident.title or "").strip()
    if not raw_title:
        body = (incident.description or "Incident").strip()
        # First line, capped at 80 chars, falls back to "Incident" for empty.
        first_line = body.splitlines()[0] if body else "Incident"
        raw_title = first_line[:80].strip() or "Incident"
    effective_title = raw_title

    # Client-submitted incidents must be tied to one of the company's
    # business_locations. Admins are allowed to create cross-tenant or
    # legacy-style incidents without a location_id (e.g. backfills).
    if current_user.role != "admin":
        if not incident.location_id:
            raise HTTPException(
                status_code=400,
                detail="A location is required. Add one in Settings → Locations.",
            )
        if not effective_company_id:
            raise HTTPException(status_code=400, detail="No company associated with this account")

    async with get_connection() as conn:
        if incident.location_id and effective_company_id:
            owns_location = await conn.fetchval(
                """
                SELECT 1 FROM business_locations
                 WHERE id = $1 AND company_id = $2 AND is_active = true
                """,
                str(incident.location_id),
                effective_company_id,
            )
            if not owns_location:
                raise HTTPException(
                    status_code=400,
                    detail="Selected location does not belong to your company",
                )

        resolved_employee_ids = await _resolve_employee_refs(
            conn, incident.involved_employee_ids, effective_company_id
        )
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
            incident.description,
            effective_type,
            effective_severity,
            occurred_at,
            incident.location,
            incident.reported_by_name,
            incident.reported_by_email,
            json.dumps([w.model_dump() for w in incident.witnesses]),
            json.dumps(incident.category_data or {}),
            resolved_employee_ids,
            effective_company_id,
            str(incident.location_id) if incident.location_id else None,
            str(current_user.id),
            (incident.corrective_actions or None),
        )

        # Fetch company/location names for response
        company_name = None
        location_name = None
        location_city = None
        location_state = None

        if row.get("company_id"):
            company = await conn.fetchrow(
                "SELECT name FROM companies WHERE id = $1",
                row["company_id"],
            )
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

        # Log audit
        await log_audit(
            conn,
            str(row["id"]),
            str(current_user.id),
            "incident_created",
            "incident",
            str(row["id"]),
            {"title": effective_title, "type": effective_type},
            request.client.host if request.client else None,
        )

        # Build response with context
        response_row = dict(row)
        response_row["company_name"] = company_name
        response_row["location_name"] = location_name
        response_row["location_city"] = location_city
        response_row["location_state"] = location_state

        effective_company_id = row.get("company_id") or scoped_company_id
        if effective_company_id:
            background_tasks.add_task(
                send_ir_notifications_task,
                company_id=str(effective_company_id),
                incident_id=str(row["id"]),
                incident_number=row["incident_number"],
                incident_title=row["title"],
                event_type="created",
                current_status=row["status"],
                changed_by_email=current_user.email,
                previous_status=None,
                location_name=location_name or row.get("location"),
                occurred_at=row.get("occurred_at"),
            )
            # Auto-classify incident_type + severity from the description.
            # Best-effort; the task swallows any failure so submit never blocks.
            background_tasks.add_task(
                _auto_classify_incident_task,
                str(row["id"]),
                user_passed_type=user_passed_type,
                user_passed_severity=user_passed_severity,
            )
            from .ai_analysis import _auto_map_policy_violations
            background_tasks.add_task(
                _auto_map_policy_violations,
                str(row["id"]),
                str(effective_company_id),
            )

        return row_to_response(response_row, 0)


@router.get("", response_model=IRIncidentListResponse)
async def list_incidents(
    status: Optional[str] = None,
    incident_type: Optional[str] = None,
    severity: Optional[str] = None,
    location: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_admin_or_client),
):
    """List incidents with filters."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return IRIncidentListResponse(incidents=[], total=0)
    async with get_connection() as conn:
        # Build dynamic query — always scope by company
        conditions = [_company_filter(1)]
        params = [company_id]
        param_idx = 2

        if status:
            conditions.append(f"i.status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if incident_type:
            conditions.append(f"i.incident_type = ${param_idx}")
            params.append(incident_type)
            param_idx += 1

        if severity:
            conditions.append(f"i.severity = ${param_idx}")
            params.append(severity)
            param_idx += 1

        if location:
            conditions.append(f"i.location ILIKE ${param_idx}")
            params.append(f"%{location}%")
            param_idx += 1

        if from_date:
            conditions.append(f"i.occurred_at >= ${param_idx}")
            params.append(_to_naive_utc(from_date))
            param_idx += 1

        if to_date:
            conditions.append(f"i.occurred_at <= ${param_idx}")
            params.append(_to_naive_utc(to_date))
            param_idx += 1

        if search:
            conditions.append(f"(i.title ILIKE ${param_idx} OR i.description ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        # Get total count
        count_query = f"SELECT COUNT(*) FROM ir_incidents i{where_clause}"
        total = await conn.fetchval(count_query, *params)

        # Get incidents with document count and company/location context
        query = f"""
            SELECT i.*, COUNT(d.id) as document_count,
                   c.name as company_name,
                   bl.name as location_name,
                   bl.city as location_city,
                   bl.state as location_state
            FROM ir_incidents i
            LEFT JOIN ir_incident_documents d ON i.id = d.incident_id
            LEFT JOIN companies c ON i.company_id = c.id
            LEFT JOIN business_locations bl ON i.location_id = bl.id
            {where_clause}
            GROUP BY i.id, c.name, bl.name, bl.city, bl.state
            ORDER BY i.occurred_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

        return IRIncidentListResponse(
            incidents=[row_to_response(row, row["document_count"]) for row in rows],
            total=total,
        )


# ===========================================
# Export — CSV / PDF report
# ===========================================

EXPORT_ROW_LIMIT = 5000


@router.get("/export")
async def export_incidents(
    format: Literal["csv", "pdf"] = Query("csv"),
    status: Optional[str] = None,
    incident_type: Optional[str] = None,
    severity: Optional[str] = None,
    location_id: Optional[UUID] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    current_user=Depends(require_admin_or_client),
):
    """Export filtered incidents as CSV or PDF.

    Filters mirror /ir/incidents (status, incident_type, severity,
    location_id, from_date, to_date). Hard-capped at EXPORT_ROW_LIMIT rows
    to keep response sizes sane.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company scope")

    async with get_connection() as conn:
        conditions = [_company_filter(1)]
        params: list = [company_id]
        idx = 2

        if status:
            conditions.append(f"i.status = ${idx}")
            params.append(status); idx += 1
        if incident_type:
            conditions.append(f"i.incident_type = ${idx}")
            params.append(incident_type); idx += 1
        if severity:
            conditions.append(f"i.severity = ${idx}")
            params.append(severity); idx += 1
        if location_id:
            conditions.append(f"i.location_id = ${idx}")
            params.append(location_id); idx += 1
        if from_date:
            conditions.append(f"i.occurred_at >= ${idx}")
            params.append(_to_naive_utc(from_date)); idx += 1
        if to_date:
            conditions.append(f"i.occurred_at <= ${idx}")
            params.append(_to_naive_utc(to_date)); idx += 1

        where_clause = " WHERE " + " AND ".join(conditions)

        rows = await conn.fetch(
            f"""
            SELECT i.incident_number, i.title, i.description, i.incident_type,
                   i.severity, i.status, i.location, i.occurred_at, i.created_at,
                   i.osha_recordable, i.reported_by_name,
                   bl.name AS location_name, bl.city AS location_city, bl.state AS location_state
            FROM ir_incidents i
            LEFT JOIN business_locations bl ON bl.id = i.location_id
            {where_clause}
            ORDER BY i.occurred_at DESC NULLS LAST
            LIMIT {EXPORT_ROW_LIMIT}
            """,
            *params,
        )

    def _loc(r) -> str:
        if r["location_name"]:
            place = ", ".join([p for p in (r["location_city"], r["location_state"]) if p])
            return f"{r['location_name']}{f' — {place}' if place else ''}"
        return r["location"] or "—"

    def _fmt(d) -> str:
        return d.strftime("%Y-%m-%d %H:%M") if d else ""

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename_base = f"incidents-{timestamp}"

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Incident #", "Title", "Type", "Severity", "Status",
            "Location", "Reported By", "Occurred At", "Created At",
            "OSHA Recordable", "Description",
        ])
        for r in rows:
            writer.writerow([
                r["incident_number"] or "",
                r["title"] or "",
                r["incident_type"] or "",
                r["severity"] or "",
                r["status"] or "",
                _loc(r),
                r["reported_by_name"] or "",
                _fmt(r["occurred_at"]),
                _fmt(r["created_at"]),
                "yes" if r["osha_recordable"] else "no",
                (r["description"] or "").replace("\n", " ").strip(),
            ])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.csv"'},
        )

    # PDF — WeasyPrint render
    try:
        from weasyprint import HTML
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF generation unavailable on server")

    sev_color = {
        "critical": "#dc2626", "high": "#ea580c",
        "medium": "#ca8a04", "low": "#16a34a",
    }
    period_label = ""
    if from_date or to_date:
        f = from_date.date().isoformat() if from_date else "…"
        t = to_date.date().isoformat() if to_date else "…"
        period_label = f"{f} → {t}"

    rows_html = "".join(
        f"""
        <tr>
            <td class="num">{(r['incident_number'] or '')}</td>
            <td>{(r['title'] or '').replace('<', '&lt;')}</td>
            <td>{(r['incident_type'] or '').replace('_', ' ').title()}</td>
            <td><span class="sev" style="color: {sev_color.get(r['severity'] or '', '#52525b')}">{(r['severity'] or '').upper()}</span></td>
            <td>{(r['status'] or '').replace('_', ' ').title()}</td>
            <td>{_loc(r)}</td>
            <td class="num">{_fmt(r['occurred_at'])}</td>
        </tr>
        """
        for r in rows
    )
    truncated_note = (
        f"<p class='note'>Result set capped at {EXPORT_ROW_LIMIT} rows.</p>"
        if len(rows) >= EXPORT_ROW_LIMIT else ""
    )
    html_str = f"""
    <html><head><meta charset="utf-8"><style>
        @page {{ size: Letter landscape; margin: 0.5in; }}
        body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; color: #18181b; font-size: 9pt; }}
        h1 {{ font-size: 16pt; margin: 0 0 4px; }}
        .meta {{ color: #71717a; font-size: 8pt; margin-bottom: 12px; }}
        .meta strong {{ color: #18181b; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 8pt; }}
        th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #e4e4e7; vertical-align: top; }}
        th {{ background: #f4f4f5; font-size: 7pt; text-transform: uppercase; letter-spacing: 0.05em; color: #52525b; }}
        td.num {{ font-family: ui-monospace, "SF Mono", monospace; font-size: 7.5pt; color: #52525b; }}
        .sev {{ font-weight: 700; font-size: 7pt; }}
        .note {{ color: #71717a; font-size: 7pt; margin-top: 12px; font-style: italic; }}
    </style></head><body>
    <h1>Incident Report</h1>
    <div class="meta">
        <strong>{len(rows)}</strong> incident{'s' if len(rows) != 1 else ''} ·
        Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
        {f' · Period {period_label}' if period_label else ''}
    </div>
    <table>
        <thead>
            <tr><th>#</th><th>Title</th><th>Type</th><th>Severity</th><th>Status</th><th>Location</th><th>Occurred</th></tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    {truncated_note}
    </body></html>
    """

    pdf_bytes = await asyncio.to_thread(lambda: HTML(string=html_str).write_pdf())
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.pdf"'},
    )



# ===========================================
# Single Incident Endpoints
# ===========================================

@router.get("/{incident_id}", response_model=IRIncidentResponse)
async def get_incident(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get a single incident by ID."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = _company_filter(2)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT i.*, COUNT(d.id) as document_count,
                   c.name as company_name,
                   bl.name as location_name,
                   bl.city as location_city,
                   bl.state as location_state
            FROM ir_incidents i
            LEFT JOIN ir_incident_documents d ON i.id = d.incident_id
            LEFT JOIN companies c ON i.company_id = c.id
            LEFT JOIN business_locations bl ON i.location_id = bl.id
            WHERE i.id = $1 AND {company_clause}
            GROUP BY i.id, c.name, bl.name, bl.city, bl.state
            """,
            str(incident_id),
            company_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        return row_to_response(row, row["document_count"])


@router.put("/{incident_id}", response_model=IRIncidentResponse)
async def update_incident(
    incident_id: UUID,
    incident: IRIncidentUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin_or_client),
):
    """Update an incident report."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = "company_id = $2"

    async with get_connection() as conn:
        # Check exists and belongs to company
        existing = await conn.fetchrow(
            f"SELECT id, status FROM ir_incidents WHERE id = $1 AND {company_clause}",
            str(incident_id),
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Build update query dynamically
        updates = []
        params = []
        param_idx = 1
        changes = {}
        status_changed = False
        previous_status = existing["status"]

        if incident.title is not None:
            updates.append(f"title = ${param_idx}")
            params.append(incident.title)
            changes["title"] = incident.title
            param_idx += 1

        if incident.description is not None:
            updates.append(f"description = ${param_idx}")
            params.append(incident.description)
            param_idx += 1

        if incident.incident_type is not None:
            updates.append(f"incident_type = ${param_idx}")
            params.append(incident.incident_type)
            changes["incident_type"] = incident.incident_type
            param_idx += 1

        if incident.severity is not None:
            updates.append(f"severity = ${param_idx}")
            params.append(incident.severity)
            changes["severity"] = incident.severity
            param_idx += 1

        if incident.status is not None:
            updates.append(f"status = ${param_idx}")
            params.append(incident.status)
            changes["status"] = incident.status
            if incident.status != existing["status"]:
                status_changed = True
                changes["previous_status"] = existing["status"]
            param_idx += 1
            # Set resolved_at if status is resolved or closed
            if incident.status in ("resolved", "closed") and existing["status"] not in ("resolved", "closed"):
                updates.append(f"resolved_at = ${param_idx}")
                params.append(datetime.now(timezone.utc).replace(tzinfo=None))
                param_idx += 1

        if incident.occurred_at is not None:
            updates.append(f"occurred_at = ${param_idx}")
            # Ensure occurred_at is naive UTC for TIMESTAMP column
            occurred_at = incident.occurred_at
            if occurred_at.tzinfo:
                occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)
            params.append(occurred_at)
            param_idx += 1

        if incident.location is not None:
            updates.append(f"location = ${param_idx}")
            params.append(incident.location)
            param_idx += 1

        if incident.assigned_to is not None:
            updates.append(f"assigned_to = ${param_idx}")
            params.append(str(incident.assigned_to))
            changes["assigned_to"] = str(incident.assigned_to)
            param_idx += 1

        if incident.witnesses is not None:
            updates.append(f"witnesses = ${param_idx}")
            params.append(json.dumps([w.model_dump() for w in incident.witnesses]))
            param_idx += 1

        if incident.category_data is not None:
            updates.append(f"category_data = ${param_idx}")
            params.append(json.dumps(incident.category_data))
            param_idx += 1

        if incident.root_cause is not None:
            updates.append(f"root_cause = ${param_idx}")
            params.append(incident.root_cause)
            param_idx += 1

        if incident.company_id is not None:
            if current_user.role != "admin":
                raise HTTPException(status_code=403, detail="Only admins can change incident company")
            updates.append(f"company_id = ${param_idx}")
            params.append(str(incident.company_id))
            changes["company_id"] = str(incident.company_id)
            param_idx += 1

        if incident.location_id is not None:
            updates.append(f"location_id = ${param_idx}")
            params.append(str(incident.location_id))
            changes["location_id"] = str(incident.location_id)
            param_idx += 1

        if incident.corrective_actions is not None:
            updates.append(f"corrective_actions = ${param_idx}")
            params.append(incident.corrective_actions)
            param_idx += 1

        if incident.involved_employee_ids is not None:
            resolved_ids = await _resolve_employee_refs(
                conn, incident.involved_employee_ids, str(company_id)
            )
            updates.append(f"involved_employee_ids = ${param_idx}")
            params.append(resolved_ids)
            param_idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append(f"updated_at = ${param_idx}")
        params.append(datetime.now(timezone.utc).replace(tzinfo=None))
        param_idx += 1

        params.append(str(incident_id))
        query = f"""
            UPDATE ir_incidents
            SET {", ".join(updates)}
            WHERE id = ${param_idx}
            RETURNING *
        """

        row = await conn.fetchrow(query, *params)

        # Get document count
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM ir_incident_documents WHERE incident_id = $1",
            str(incident_id),
        )

        # Fetch company/location names for response
        company_name = None
        location_name = None
        location_city = None
        location_state = None

        if row.get("company_id"):
            company = await conn.fetchrow(
                "SELECT name FROM companies WHERE id = $1",
                row["company_id"],
            )
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

        # Log audit
        audit_action = "status_changed" if status_changed else "incident_updated"
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            audit_action,
            "incident",
            str(incident_id),
            changes if changes else None,
            request.client.host if request.client else None,
        )

        # Build response with context
        response_row = dict(row)
        response_row["company_name"] = company_name
        response_row["location_name"] = location_name
        response_row["location_city"] = location_city
        response_row["location_state"] = location_state

        if status_changed:
            effective_company_id = row.get("company_id") or company_id
            if effective_company_id:
                background_tasks.add_task(
                    send_ir_notifications_task,
                    company_id=str(effective_company_id),
                    incident_id=str(row["id"]),
                    incident_number=row["incident_number"],
                    incident_title=row["title"],
                    event_type="status_changed",
                    current_status=row["status"],
                    changed_by_email=current_user.email,
                    previous_status=previous_status,
                    location_name=location_name or row.get("location"),
                    occurred_at=row.get("occurred_at"),
                )

        # Re-map policies if description or category_data changed
        if incident.description is not None or incident.category_data is not None:
            effective_cid = row.get("company_id") or company_id
            if effective_cid:
                from .ai_analysis import _auto_map_policy_violations
                background_tasks.add_task(
                    _auto_map_policy_violations,
                    str(incident_id),
                    str(effective_cid),
                )

        return row_to_response(response_row, doc_count)


@router.delete("/{incident_id}")
async def delete_incident(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Delete an incident and all related data."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = "company_id = $2"

    async with get_connection() as conn:
        # Check exists and belongs to company
        row = await conn.fetchrow(
            f"SELECT id, incident_number, title FROM ir_incidents WHERE id = $1 AND {company_clause}",
            str(incident_id),
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Delete (cascade will handle documents, analysis, etc.)
        await conn.execute(
            f"DELETE FROM ir_incidents WHERE id = $1 AND {company_clause}",
            str(incident_id),
            company_id,
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "incident_deleted",
            "incident",
            str(incident_id),
            {"incident_number": row["incident_number"], "title": row["title"]},
            request.client.host if request.client else None,
        )

        return {"message": "Incident deleted successfully"}









@router.get("/{incident_id}/er-case")
async def get_linked_er_case(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get linked ER case ID for an incident (Phase 2)."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id, company_id, er_case_id FROM ir_incidents WHERE id = $1", incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        return {
            "incident_id": str(incident_id),
            "er_case_id": str(incident["er_case_id"]) if incident["er_case_id"] else None,
        }


