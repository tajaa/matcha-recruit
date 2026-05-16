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


# ===========================================
# Analytics
# ===========================================

@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    current_user=Depends(require_admin_or_client),
):
    """Get summary analytics for the dashboard."""
    company_id = await get_client_company_id(current_user)
    empty = AnalyticsSummary(
        total=0, open=0, investigating=0, resolved=0, closed=0,
        critical=0, high=0, medium=0, low=0, by_type={},
    )
    if company_id is None:
        return empty
    co_filter = "company_id = $1"

    async with get_connection() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM ir_incidents WHERE {co_filter}", company_id)

        status_rows = await conn.fetch(
            f"SELECT status, COUNT(*) as count FROM ir_incidents WHERE {co_filter} GROUP BY status", company_id
        )
        by_status = {row["status"]: row["count"] for row in status_rows}

        type_rows = await conn.fetch(
            f"SELECT incident_type, COUNT(*) as count FROM ir_incidents WHERE {co_filter} GROUP BY incident_type", company_id
        )
        by_type = {row["incident_type"]: row["count"] for row in type_rows}

        severity_rows = await conn.fetch(
            f"SELECT severity, COUNT(*) as count FROM ir_incidents WHERE {co_filter} GROUP BY severity", company_id
        )
        by_severity = {row["severity"]: row["count"] for row in severity_rows}

        return AnalyticsSummary(
            total=total or 0,
            open=by_status.get("reported", 0) + by_status.get("action_required", 0),
            investigating=by_status.get("investigating", 0),
            resolved=by_status.get("resolved", 0),
            closed=by_status.get("closed", 0),
            critical=by_severity.get("critical", 0),
            high=by_severity.get("high", 0),
            medium=by_severity.get("medium", 0),
            low=by_severity.get("low", 0),
            by_type=by_type,
        )


@router.get("/analytics/trends", response_model=TrendsAnalysis)
async def get_analytics_trends(
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
    days: int = Query(30, ge=7, le=365),
    current_user=Depends(require_admin_or_client),
):
    """Get incident trends over time."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return TrendsAnalysis(data=[], period=period, start_date="", end_date="")
    co_filter = "company_id = $2"

    # Map validated period to SQL DATE_TRUNC argument (never from user input)
    trunc_map = {"daily": "day", "weekly": "week", "monthly": "month"}
    date_trunc = trunc_map[period]

    async with get_connection() as conn:
        start_date = _utc_now_naive() - timedelta(days=days)

        rows = await conn.fetch(
            f"""
            SELECT
                DATE_TRUNC('{date_trunc}', occurred_at) as period_start,
                COUNT(*) as count,
                COALESCE(SUM(CASE WHEN osha_recordable = true THEN 1 ELSE 0 END), 0) AS recordable_count,
                incident_type,
                severity
            FROM ir_incidents
            WHERE {co_filter} AND occurred_at >= $1
            GROUP BY period_start, incident_type, severity
            ORDER BY period_start
            """,
            start_date,
            company_id,
        )

        # Aggregate by period across both type + severity dims.
        data_map: dict[str, dict] = {}
        for row in rows:
            date_str = row["period_start"].strftime("%Y-%m-%d")
            entry = data_map.setdefault(date_str, {
                "count": 0,
                "recordable_count": 0,
                "by_type": {},
                "by_severity": {},
            })
            cnt = int(row["count"])
            entry["count"] += cnt
            entry["recordable_count"] += int(row["recordable_count"] or 0)
            t = row["incident_type"] or "other"
            s = row["severity"] or "medium"
            entry["by_type"][t] = entry["by_type"].get(t, 0) + cnt
            entry["by_severity"][s] = entry["by_severity"].get(s, 0) + cnt

        data = [
            TrendDataPoint(
                date=date,
                count=info["count"],
                by_type=info["by_type"],
                by_severity=info["by_severity"],
                recordable_count=info["recordable_count"],
            )
            for date, info in sorted(data_map.items())
        ]

        return TrendsAnalysis(
            data=data,
            period=period,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=_utc_now_naive().strftime("%Y-%m-%d"),
        )


@router.get("/analytics/locations", response_model=LocationAnalysis)
async def get_analytics_locations(
    limit: int = Query(10, ge=1, le=50),
    current_user=Depends(require_admin_or_client),
):
    """Get incident hotspots by location.

    Now groups by `location_id` (joined to business_locations) so the
    same physical site doesn't double-count when its free-text label
    drifted across edits. Legacy rows with NULL location_id roll up
    under a single "Unassigned (legacy)" bucket; rows whose location_id
    points at a deleted location use the legacy free-text label as
    fallback.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return LocationAnalysis(hotspots=[], total_locations=0)

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                i.location_id,
                i.location AS legacy_location,
                bl.name AS bl_name,
                bl.city AS bl_city,
                bl.state AS bl_state,
                COUNT(*) AS cnt,
                i.incident_type,
                AVG(CASE
                    WHEN i.severity = 'critical' THEN 4
                    WHEN i.severity = 'high' THEN 3
                    WHEN i.severity = 'medium' THEN 2
                    ELSE 1
                END) AS severity_score
            FROM ir_incidents i
            LEFT JOIN business_locations bl ON bl.id = i.location_id
            WHERE i.company_id = $1
            GROUP BY i.location_id, i.location, bl.name, bl.city, bl.state, i.incident_type
            """,
            company_id,
        )

        # Aggregate by location: prefer location_id grouping; fall back to
        # free-text under a single "Unassigned" bucket for legacy rows.
        location_map: dict = {}
        for row in rows:
            loc_id = row["location_id"]
            if loc_id is None:
                key = ("__unassigned__", UNASSIGNED_LOCATION_LABEL)
            else:
                label = (row["bl_name"] or "").strip()
                if not label:
                    place = ", ".join([p for p in (row["bl_city"], row["bl_state"]) if p])
                    label = place or (row["legacy_location"] or str(loc_id)[:8])
                key = (str(loc_id), label)

            bucket = location_map.setdefault(
                key, {"count": 0, "by_type": {}, "severity_scores": []},
            )
            cnt = int(row["cnt"] or 0)
            bucket["count"] += cnt
            bucket["by_type"][row["incident_type"]] = bucket["by_type"].get(row["incident_type"], 0) + cnt
            bucket["severity_scores"].append(float(row["severity_score"] or 0))

        sorted_locations = sorted(
            location_map.items(), key=lambda x: x[1]["count"], reverse=True,
        )[:limit]

        hotspots = [
            LocationHotspot(
                location=label,
                count=info["count"],
                by_type=info["by_type"],
                avg_severity_score=round(
                    sum(info["severity_scores"]) / len(info["severity_scores"]), 2,
                ) if info["severity_scores"] else 0.0,
            )
            for (_, label), info in sorted_locations
        ]

        return LocationAnalysis(
            hotspots=hotspots,
            total_locations=len(location_map),
        )


# ===========================================
# Risk Insights — locations × type matrix + Gemini themes
#
# Cross-tier: gated by the `incidents` feature flag (the existing IR gate),
# so both Matcha Cap (ir_only_self_serve) and full Matcha (bespoke) tenants
# get this. Auto-derived business_locations rows from compliance only show
# up here when they have ≥1 incident — they fall out naturally via JOIN.
# ===========================================


SEVERITY_WEIGHT = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}

INCIDENT_TYPES_ORDER = ["safety", "behavioral", "property", "near_miss", "other"]

UNASSIGNED_LOCATION_LABEL = "Unassigned (legacy)"


def _build_risk_scope_key(location_id: Optional[UUID], period_days: int) -> str:
    """Deterministic cache key for ir_company_analysis.scope_key."""
    loc_part = str(location_id) if location_id else "all"
    return f"loc={loc_part}:days={period_days}"


async def compute_wc_metrics(conn, company_id: UUID, period_days: int = 365) -> dict:
    """Per-company Workers Comp metrics — extracted so the broker portfolio
    endpoint can reuse the same calc per linked client."""
    from app.matcha.services.wc_benchmarks import (
        lookup_benchmark, estimate_premium_impact, severity_band,
    )

    period_start = _utc_now_naive() - timedelta(days=period_days)
    prior_start = period_start - timedelta(days=period_days)
    quarter_start = _utc_now_naive() - timedelta(days=730)  # 8 quarters back
    annualization = 365.0 / period_days

    profile = await conn.fetchrow(
        """
        SELECT comp.industry, hp.headcount
        FROM companies comp
        LEFT JOIN company_handbook_profiles hp ON hp.company_id = comp.id
        WHERE comp.id = $1
        """,
        company_id,
    )
    headcount = int(profile["headcount"]) if profile and profile["headcount"] else 0
    industry = profile["industry"] if profile else None

    # Current + prior period totals.
    rows = await conn.fetch(
        """
        SELECT
            CASE WHEN occurred_at >= $2 THEN 'current' ELSE 'prior' END AS bucket,
            COUNT(*) AS recordable_cases,
            COALESCE(SUM(CASE WHEN COALESCE(days_away_from_work, 0) > 0
                               OR COALESCE(days_restricted_duty, 0) > 0
                              THEN 1 ELSE 0 END), 0) AS dart_cases,
            COALESCE(SUM(COALESCE(days_away_from_work, 0)), 0) AS lost_days,
            COALESCE(SUM(COALESCE(days_restricted_duty, 0)), 0) AS restricted_days,
            COALESCE(SUM(CASE WHEN osha_classification = 'death' THEN 1 ELSE 0 END), 0) AS deaths
        FROM ir_incidents
        WHERE company_id = $1
          AND osha_recordable = true
          AND occurred_at >= $3
        GROUP BY bucket
        """,
        company_id, period_start, prior_start,
    )

    # Quarterly bucketing — 8 quarters trailing.
    quarter_rows = await conn.fetch(
        """
        SELECT
            DATE_TRUNC('quarter', occurred_at) AS quarter_start,
            COUNT(*) AS recordable_cases,
            COALESCE(SUM(CASE WHEN COALESCE(days_away_from_work, 0) > 0
                               OR COALESCE(days_restricted_duty, 0) > 0
                              THEN 1 ELSE 0 END), 0) AS dart_cases,
            COALESCE(SUM(COALESCE(days_away_from_work, 0)), 0) AS lost_days
        FROM ir_incidents
        WHERE company_id = $1
          AND osha_recordable = true
          AND occurred_at >= $2
        GROUP BY quarter_start
        ORDER BY quarter_start
        """,
        company_id, quarter_start,
    )

    last_recordable = await conn.fetchval(
        """
        SELECT MAX(occurred_at) FROM ir_incidents
        WHERE company_id = $1 AND osha_recordable = true
        """,
        company_id,
    )

    cur = next((r for r in rows if r["bucket"] == "current"), None)
    prv = next((r for r in rows if r["bucket"] == "prior"), None)

    def _g(row, key):
        return int(row[key]) if row else 0

    recordable_cases = _g(cur, "recordable_cases")
    dart_cases = _g(cur, "dart_cases")
    lost_days = _g(cur, "lost_days")
    restricted_days = _g(cur, "restricted_days")
    deaths = _g(cur, "deaths")
    prior_recordable = _g(prv, "recordable_cases")
    prior_dart = _g(prv, "dart_cases")
    prior_lost_days = _g(prv, "lost_days")

    # Approximate hours worked over the period.
    hours_worked = float(headcount) * 2000.0 / annualization if headcount > 0 else 0.0
    insufficient = hours_worked < 50_000

    if hours_worked > 0:
        trir = round((recordable_cases * 200_000) / hours_worked, 2)
        dart_rate = round((dart_cases * 200_000) / hours_worked, 2)
        prior_trir = round((prior_recordable * 200_000) / hours_worked, 2)
        prior_dart_rate = round((prior_dart * 200_000) / hours_worked, 2)
    else:
        trir = None
        dart_rate = None
        prior_trir = None
        prior_dart_rate = None

    if last_recordable:
        days_since = (datetime.utcnow() - last_recordable).days
    else:
        days_since = None

    def _delta_pct(curr, prior):
        if prior is None or prior == 0:
            return None
        return round(((curr - prior) / prior) * 100, 1)

    benchmark = lookup_benchmark(industry)
    bench_trir = benchmark["trir"] if benchmark else None
    bench_sector = benchmark["sector"] if benchmark else None

    premium_impact = estimate_premium_impact(
        trir=trir, benchmark_trir=bench_trir,
        headcount=headcount or None, sector=bench_sector,
    )

    quarterly = []
    for qrow in quarter_rows:
        qstart = qrow["quarter_start"]
        q_label = f"{qstart.year}-Q{((qstart.month - 1) // 3) + 1}"
        quarterly.append({
            "quarter": q_label,
            "recordable": int(qrow["recordable_cases"]),
            "dart": int(qrow["dart_cases"]),
            "non_dart": int(qrow["recordable_cases"]) - int(qrow["dart_cases"]),
            "lost_days": int(qrow["lost_days"]),
        })

    return {
        "period_days": period_days,
        "industry": industry,
        "headcount": headcount or None,
        "hours_worked_assumed": int(hours_worked) if hours_worked > 0 else None,
        "recordable_cases": recordable_cases,
        "dart_cases": dart_cases,
        "lost_days": lost_days,
        "restricted_days": restricted_days,
        "deaths": deaths,
        "trir": trir,
        "dart_rate": dart_rate,
        "days_since_last_recordable": days_since,
        "ever_recordable": last_recordable is not None,
        "benchmark": benchmark,
        "premium_impact": premium_impact,
        "severity_band": severity_band(trir, bench_trir),
        "quarterly": quarterly,
        "prior": {
            "recordable_cases": prior_recordable,
            "dart_cases": prior_dart,
            "lost_days": prior_lost_days,
            "trir": prior_trir,
            "dart_rate": prior_dart_rate,
            "trir_delta_pct": _delta_pct(trir, prior_trir),
            "dart_delta_pct": _delta_pct(dart_rate, prior_dart_rate),
            "lost_days_delta_pct": _delta_pct(lost_days, prior_lost_days),
            "recordable_delta_pct": _delta_pct(recordable_cases, prior_recordable),
        },
        "data_quality": {
            "insufficient_population": insufficient,
            "headcount_missing": headcount == 0,
        },
        "generated_at": _utc_now_naive().isoformat(),
    }


@router.get("/analytics/wc-metrics")
async def get_wc_metrics(
    period_days: int = Query(365, ge=30, le=1095),
    current_user=Depends(require_admin_or_client),
):
    """OSHA-style frequency + severity metrics for Workers Comp framing.

    Returns TRIR, DART rate, lost-day totals, claims-free streak, prior-period
    deltas, NAICS-sector benchmark, premium-impact estimate, and trailing
    8-quarter recordable bars. Used by P&C brokers to frame an employer's
    E-Mod posture. See compute_wc_metrics() for the math + caveats.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")
    async with get_connection() as conn:
        return await compute_wc_metrics(conn, company_id, period_days)


@router.get("/analytics/risk-matrix", response_model=RiskMatrixResponse)
async def get_analytics_risk_matrix(
    days: int = Query(90, ge=7, le=365),
    location_id: Optional[UUID] = Query(None),
    current_user=Depends(require_admin_or_client),
):
    """SQL-driven Risk Matrix: locations × incident_type with deviation flags."""
    company_id = await get_client_company_id(current_user)
    generated_at_iso = _utc_now_naive().isoformat()
    if company_id is None:
        return RiskMatrixResponse(
            period_days=days, generated_at=generated_at_iso,
            company_total=0, location_count=0, rows=[],
        )

    start_date = _utc_now_naive() - timedelta(days=days)

    async with get_connection() as conn:
        # Optional location-scope check — if the caller filtered to a specific
        # location, ensure it belongs to their company before any query work.
        if location_id is not None:
            owns = await conn.fetchval(
                "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
                location_id, company_id,
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Location not found")

        loc_filter = "AND i.location_id = $3" if location_id else ""
        params: list = [company_id, start_date]
        if location_id:
            params.append(location_id)

        rows = await conn.fetch(
            f"""
            SELECT
                i.location_id,
                i.location AS legacy_location,
                bl.name AS bl_name,
                bl.city AS bl_city,
                bl.state AS bl_state,
                i.incident_type,
                COUNT(*) AS cnt,
                AVG(CASE
                    WHEN i.severity = 'critical' THEN 4
                    WHEN i.severity = 'high' THEN 3
                    WHEN i.severity = 'medium' THEN 2
                    ELSE 1
                END) AS severity_score
            FROM ir_incidents i
            LEFT JOIN business_locations bl ON bl.id = i.location_id
            WHERE i.company_id = $1
              AND i.occurred_at >= $2
              {loc_filter}
            GROUP BY i.location_id, i.location, bl.name, bl.city, bl.state, i.incident_type
            """,
            *params,
        )

    # Aggregate per (location_id-or-Unassigned) and per incident_type.
    per_location: dict = {}  # key: (loc_id_str_or_None, label) -> {totals, by_type}
    company_by_type: dict = {t: 0 for t in INCIDENT_TYPES_ORDER}
    company_total = 0

    for row in rows:
        loc_id = row["location_id"]
        if loc_id is None:
            # Legacy free-text fallback. Roll all NULL-location_id rows under
            # one synthesized bucket so the matrix stays compact.
            key = (None, UNASSIGNED_LOCATION_LABEL)
        else:
            label = (row["bl_name"] or "").strip()
            if not label:
                place = ", ".join([p for p in (row["bl_city"], row["bl_state"]) if p])
                label = place or str(loc_id)[:8]
            key = (str(loc_id), label)

        bucket = per_location.setdefault(key, {"total": 0, "by_type": {}})
        cnt = int(row["cnt"] or 0)
        itype = row["incident_type"] or "other"
        bucket["total"] += cnt
        # Multiple severity buckets can exist per type — aggregate weighted score.
        prev = bucket["by_type"].get(itype, {"count": 0, "score_sum": 0.0})
        prev["count"] += cnt
        prev["score_sum"] += float(row["severity_score"] or 0) * cnt
        bucket["by_type"][itype] = prev

        company_by_type[itype] = company_by_type.get(itype, 0) + cnt
        company_total += cnt

    # Baseline rates compare a single location to the average location. When the
    # caller has filtered to one location, the company total still includes only
    # that location's incidents (because of loc_filter) — so deviation in that
    # case is always 1.0 and the matrix reads as a single-location report.
    location_count = len(per_location) or 1

    matrix_rows: list[RiskMatrixRow] = []
    for (loc_id_str, label), info in sorted(per_location.items(), key=lambda kv: -kv[1]["total"]):
        cells: list[RiskMatrixCell] = []
        for itype in INCIDENT_TYPES_ORDER:
            agg = info["by_type"].get(itype, {"count": 0, "score_sum": 0.0})
            count = int(agg["count"])
            severity_score = round(agg["score_sum"] / count, 2) if count else 0.0
            company_count = company_by_type.get(itype, 0)
            baseline_rate = (company_count / location_count / days) if days > 0 else 0.0
            location_rate = (count / days) if days > 0 else 0.0
            deviation_ratio = (location_rate / baseline_rate) if baseline_rate > 0 else (0.0 if count == 0 else float("inf"))
            # Cap infinite ratios for JSON safety; a value > 999 is functionally "way above baseline".
            if deviation_ratio == float("inf") or deviation_ratio > 999.0:
                deviation_ratio = 999.0
            flagged = bool(deviation_ratio >= 2.0 and count >= 3)
            cells.append(RiskMatrixCell(
                incident_type=itype,
                count=count,
                severity_score=severity_score,
                baseline_rate=round(baseline_rate, 4),
                location_rate=round(location_rate, 4),
                deviation_ratio=round(deviation_ratio, 2),
                flagged=flagged,
            ))
        matrix_rows.append(RiskMatrixRow(
            location_id=UUID(loc_id_str) if loc_id_str else None,
            location_name=label,
            total_incidents=info["total"],
            cells=cells,
        ))

    return RiskMatrixResponse(
        period_days=days,
        generated_at=generated_at_iso,
        company_total=company_total,
        location_count=len(per_location),
        rows=matrix_rows,
    )


@router.get("/analytics/risk-insights", response_model=RiskInsightsResponse)
async def get_analytics_risk_insights(
    days: int = Query(30, ge=7, le=180),
    location_id: Optional[UUID] = Query(None),
    regenerate: bool = Query(False),
    current_user=Depends(require_admin_or_client),
):
    """Gemini-driven theme detection across recent IR corpus. 24h cache."""
    from app.matcha.services.ir_analysis import get_ir_analyzer

    company_id = await get_client_company_id(current_user)
    generated_at_iso = _utc_now_naive().isoformat()
    if company_id is None:
        return RiskInsightsResponse(
            period_days=days, generated_at=generated_at_iso,
            location_id=None, themes=[], from_cache=False,
        )

    scope_key = _build_risk_scope_key(location_id, days)
    start_date = _utc_now_naive() - timedelta(days=days)

    async with get_connection() as conn:
        if location_id is not None:
            owns = await conn.fetchval(
                "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
                location_id, company_id,
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Location not found")

        # Cache check (24h TTL) unless caller asked to regenerate.
        if not regenerate:
            cached = await conn.fetchrow(
                """
                SELECT analysis_data, generated_at FROM ir_company_analysis
                WHERE company_id = $1 AND analysis_type = 'risk_insights' AND scope_key = $2
                """,
                company_id, scope_key,
            )
            if cached and (_utc_now_naive() - cached["generated_at"]) < timedelta(hours=24):
                payload = _safe_json_loads(cached["analysis_data"])
                payload["from_cache"] = True
                payload["generated_at"] = cached["generated_at"].isoformat()
                return RiskInsightsResponse(**payload)

        # Pull the corpus. Cap at 200 most recent so the prompt stays focused.
        loc_clause = "AND i.location_id = $3" if location_id else ""
        params: list = [company_id, start_date]
        if location_id:
            params.append(location_id)

        incident_rows = await conn.fetch(
            f"""
            SELECT i.id, i.occurred_at, i.incident_type, i.severity, i.location_id,
                   i.description, i.root_cause, i.witnesses, i.involved_employee_ids,
                   i.er_case_id
            FROM ir_incidents i
            WHERE i.company_id = $1 AND i.occurred_at >= $2 {loc_clause}
            ORDER BY i.occurred_at DESC
            LIMIT 200
            """,
            *params,
        )

        # Locations registry — every active location for this company so themes
        # can attribute patterns by location name even if a location had zero
        # incidents in the window (Gemini picks from this registry).
        location_rows = await conn.fetch(
            """
            SELECT id, name, city, state
            FROM business_locations
            WHERE company_id = $1 AND is_active = true
            """,
            company_id,
        )
        location_lookup: dict[str, str] = {}
        for lr in location_rows:
            label = (lr["name"] or "").strip()
            if not label:
                place = ", ".join([p for p in (lr["city"], lr["state"]) if p])
                label = place or str(lr["id"])[:8]
            location_lookup[str(lr["id"])] = label

        # Employees registry — only when full-platform tenant has employees data.
        # Resolve names for IDs that appear in the corpus' involved_employee_ids;
        # if `employees` table is unreachable or empty for this tenant we just
        # pass None and the prompt degrades gracefully.
        employee_lookup: Optional[dict[str, str]] = None
        involved_ids: set[str] = set()
        for ir in incident_rows:
            for eid in (ir["involved_employee_ids"] or []):
                involved_ids.add(str(eid))
        if involved_ids:
            try:
                emp_rows = await conn.fetch(
                    """
                    SELECT id, first_name, last_name
                    FROM employees
                    WHERE org_id = $1 AND id = ANY($2::uuid[])
                    """,
                    company_id, list(involved_ids),
                )
                if emp_rows:
                    employee_lookup = {}
                    for er in emp_rows:
                        name = " ".join([s for s in (er["first_name"], er["last_name"]) if s]).strip()
                        employee_lookup[str(er["id"])] = name or str(er["id"])[:8]
            except Exception as e:
                # Cap tenants don't have employees populated; the table may exist
                # but the org_id filter returns empty. Don't fail the analysis.
                logger.info("[IR risk-insights] employees lookup skipped: %s", e)
                employee_lookup = None

        company_row = await conn.fetchrow(
            "SELECT name, industry FROM companies WHERE id = $1",
            company_id,
        )

    company_context = None
    if company_row:
        bits = [company_row["name"]]
        if company_row["industry"]:
            bits.append(f"Industry: {company_row['industry']}")
        company_context = " — ".join(bits)

    # Empty corpus short-circuit — don't burn a Gemini call.
    incidents_payload = [dict(r) for r in incident_rows]
    if not incidents_payload:
        empty = RiskInsightsResponse(
            period_days=days,
            generated_at=generated_at_iso,
            location_id=location_id,
            themes=[],
            from_cache=False,
        )
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO ir_company_analysis (company_id, analysis_type, scope_key, analysis_data)
                VALUES ($1, 'risk_insights', $2, $3)
                ON CONFLICT (company_id, analysis_type, scope_key)
                DO UPDATE SET analysis_data = $3, generated_at = NOW()
                """,
                company_id, scope_key,
                json.dumps(empty.model_dump(mode="json"), default=str),
            )
        return empty

    analyzer = get_ir_analyzer()
    gemini_failed = False
    try:
        themes_result = await analyzer.detect_risk_themes(
            incidents=incidents_payload,
            location_lookup=location_lookup,
            employee_lookup=employee_lookup,
            company_context=company_context,
        )
    except Exception as e:
        logger.warning("[IR risk-insights] Gemini theme detection failed: %s", e)
        themes_result = {"themes": []}
        gemini_failed = True

    themes: list[RiskTheme] = []
    for t in themes_result.get("themes", []):
        loc_id_str = t.get("location_id")
        loc_name = location_lookup.get(loc_id_str) if loc_id_str else None
        try:
            themes.append(RiskTheme(
                label=t["label"],
                severity=t["severity"],
                location_id=UUID(loc_id_str) if loc_id_str else None,
                location_name=loc_name,
                incident_count=int(t["incident_count"]),
                evidence_incident_ids=[UUID(eid) for eid in t.get("evidence_incident_ids", [])],
                insight=t["insight"],
                recommendation=t["recommendation"],
            ))
        except (KeyError, ValueError, TypeError) as e:
            # Skip malformed theme rather than 500 the whole response.
            logger.info("[IR risk-insights] dropping malformed theme: %s", e)

    response = RiskInsightsResponse(
        period_days=days,
        generated_at=generated_at_iso,
        location_id=location_id,
        themes=themes,
        from_cache=False,
    )

    # Only cache on success. A Gemini outage shouldn't pin "no themes" for 24h.
    if not gemini_failed:
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO ir_company_analysis (company_id, analysis_type, scope_key, analysis_data)
                VALUES ($1, 'risk_insights', $2, $3)
                ON CONFLICT (company_id, analysis_type, scope_key)
                DO UPDATE SET analysis_data = $3, generated_at = NOW()
                """,
                company_id, scope_key,
                json.dumps(response.model_dump(mode="json"), default=str),
            )

    return response


@router.get("/analytics/consistency", response_model=ConsistencyAnalytics)
async def get_analytics_consistency(
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Get company-wide consistency analytics across all resolved incidents."""
    from app.matcha.services.ir_consistency import compute_consistency_analytics

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return ConsistencyAnalytics(
            total_resolved=0, total_with_actions=0,
            action_distribution=[], by_incident_type=[], by_severity=[],
            avg_resolution_by_action={}, generated_at=_utc_now_naive().isoformat(),
        )

    async with get_connection() as conn:
        # Fetch all resolved/closed incidents
        rows = await conn.fetch(
            """
            SELECT id, incident_type, severity, corrective_actions,
                   occurred_at, resolved_at
            FROM ir_incidents
            WHERE company_id = $1 AND status IN ('resolved', 'closed')
            ORDER BY resolved_at DESC
            """,
            company_id,
        )

        if not rows:
            return ConsistencyAnalytics(
                total_resolved=0, total_with_actions=0,
                action_distribution=[], by_incident_type=[], by_severity=[],
                avg_resolution_by_action={}, generated_at=_utc_now_naive().isoformat(),
            )

        # Use the most recently resolved incident as cache anchor for writes
        anchor_id = str(rows[0]["id"])

        # Check for cached result (<24h) anywhere in the company (not just anchor)
        cached = await conn.fetchrow(
            """
            SELECT a.analysis_data, a.generated_at FROM ir_incident_analysis a
            JOIN ir_incidents i ON i.id = a.incident_id
            WHERE i.company_id = $1 AND a.analysis_type = 'company_consistency'
            ORDER BY a.generated_at DESC LIMIT 1
            """,
            company_id,
        )

        if cached:
            cache_age = _utc_now_naive() - cached["generated_at"]
            if cache_age < timedelta(hours=24):
                result = _safe_json_loads(cached["analysis_data"])
                result["from_cache"] = True
                return ConsistencyAnalytics(**result)

        incidents = [dict(r) for r in rows]

        settings = get_settings()
        try:
            result = await compute_consistency_analytics(
                incidents,
                api_key=settings.gemini_api_key if not settings.use_vertex else None,
                vertex_project=settings.vertex_project if settings.use_vertex else None,
            )
        except Exception as e:
            logger.warning(f"Consistency analytics computation failed: {e}")
            return ConsistencyAnalytics(
                total_resolved=len(incidents),
                total_with_actions=len([i for i in incidents if i.get("corrective_actions")]),
                action_distribution=[], by_incident_type=[], by_severity=[],
                avg_resolution_by_action={}, generated_at=_utc_now_naive().isoformat(),
            )

        # Cache on the anchor incident
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'company_consistency', $2)
            ON CONFLICT (incident_id, analysis_type)
            DO UPDATE SET analysis_data = $2, generated_at = now()
            """,
            anchor_id,
            json.dumps(result, default=str),
        )

        return ConsistencyAnalytics(**result)


# ===========================================
# AI Analysis
# ===========================================

@router.post("/{incident_id}/analyze/categorize", response_model=CategorizationAnalysis)
async def analyze_categorization(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Auto-categorize an incident using AI."""
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError

    async with get_connection() as conn:
        row = await _get_incident_with_company_check(
            conn, incident_id, current_user,
            columns="id, title, description, location, reported_by_name",
        )

        # Check for cached analysis
        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'categorization'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            result = _safe_json_loads(cached["analysis_data"])
            return CategorizationAnalysis(
                suggested_type=result["suggested_type"],
                confidence=result["confidence"],
                reasoning=result["reasoning"],
                generated_at=result["generated_at"],
            )

        # Run AI analysis with fallback to stale cache on failure
        try:
            analyzer = get_ir_analyzer()
            result = await analyzer.categorize_incident(
                title=row["title"],
                description=row["description"],
                location=row["location"],
                reported_by=row["reported_by_name"],
            )
        except IRAnalysisError as e:
            # Gemini failed - try to return stale cache if available
            if cached:
                result = _safe_json_loads(cached["analysis_data"])
                return CategorizationAnalysis(
                    suggested_type=result["suggested_type"],
                    confidence=result["confidence"],
                    reasoning=result["reasoning"],
                    generated_at=result["generated_at"],
                    from_cache=True,
                    cache_reason=str(e),
                )
            logger.error(f"AI analysis failed for incident {incident_id}: {e}")
            raise HTTPException(status_code=503, detail="Analysis temporarily unavailable. Please try again later.")

        # Cache the result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'categorization', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "categorization"},
            request.client.host if request.client else None,
        )

        return CategorizationAnalysis(
            suggested_type=result["suggested_type"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
            generated_at=result["generated_at"],
        )


@router.post("/{incident_id}/analyze/severity", response_model=SeverityAnalysis)
async def analyze_severity(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Assess incident severity using AI."""
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError

    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)

        # Check for cached analysis
        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'severity'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            result = _safe_json_loads(cached["analysis_data"])
            return SeverityAnalysis(
                suggested_severity=result["suggested_severity"],
                factors=result["factors"],
                reasoning=result["reasoning"],
                generated_at=result["generated_at"],
            )

        # Run AI analysis with fallback to stale cache on failure
        try:
            analyzer = get_ir_analyzer()
            category_data = json.loads(row["category_data"]) if isinstance(row.get("category_data"), str) else row.get("category_data")

            result = await analyzer.assess_severity(
                title=row["title"],
                description=row["description"],
                incident_type=row["incident_type"],
                location=row["location"],
                category_data=category_data,
            )
        except IRAnalysisError as e:
            # Gemini failed - try to return stale cache if available
            if cached:
                result = _safe_json_loads(cached["analysis_data"])
                return SeverityAnalysis(
                    suggested_severity=result["suggested_severity"],
                    factors=result["factors"],
                    reasoning=result["reasoning"],
                    generated_at=result["generated_at"],
                    from_cache=True,
                    cache_reason=str(e),
                )
            logger.error(f"AI analysis failed for incident {incident_id}: {e}")
            raise HTTPException(status_code=503, detail="Analysis temporarily unavailable. Please try again later.")

        # Cache the result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'severity', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "severity"},
            request.client.host if request.client else None,
        )

        return SeverityAnalysis(
            suggested_severity=result["suggested_severity"],
            factors=result["factors"],
            reasoning=result["reasoning"],
            generated_at=result["generated_at"],
        )


@router.post("/{incident_id}/analyze/root-cause")
async def analyze_root_cause(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Perform root cause analysis using AI (SSE stream)."""
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError

    # Pre-fetch data before starting the stream (auth + data validation)
    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)
        row = dict(row)

        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'root_cause'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

    async def event_stream():
        yield _sse({"type": "phase", "step": "loading_incident", "message": "Loading incident data..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "checking_cache", "message": "Checking analysis cache..."})
        await asyncio.sleep(0.05)

        if cached:
            result = _safe_json_loads(cached["analysis_data"])
            rc = RootCauseAnalysis(
                primary_cause=result["primary_cause"],
                contributing_factors=result["contributing_factors"],
                prevention_suggestions=result["prevention_suggestions"],
                reasoning=result["reasoning"],
                generated_at=result["generated_at"],
                from_cache=True,
            )
            yield _sse({"type": "cached", "message": "Using cached analysis result", "result": rc.model_dump(mode='json')})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "preparing_context", "message": "Preparing incident context for AI..."})
        await asyncio.sleep(0.05)

        category_data = json.loads(row["category_data"]) if isinstance(row.get("category_data"), str) else row.get("category_data")
        witnesses = parse_witnesses(row.get("witnesses"))

        yield _sse({"type": "phase", "step": "analyzing", "message": "AI analyzing root cause..."})

        try:
            analyzer = get_ir_analyzer()
            result = await analyzer.analyze_root_cause(
                title=row["title"],
                description=row["description"],
                incident_type=row["incident_type"],
                severity=row["severity"],
                location=row["location"],
                category_data=category_data,
                witnesses=[w.model_dump() for w in witnesses],
            )
        except IRAnalysisError as e:
            if cached:
                result_data = _safe_json_loads(cached["analysis_data"])
                rc = RootCauseAnalysis(
                    primary_cause=result_data["primary_cause"],
                    contributing_factors=result_data["contributing_factors"],
                    prevention_suggestions=result_data["prevention_suggestions"],
                    reasoning=result_data["reasoning"],
                    generated_at=result_data["generated_at"],
                    from_cache=True,
                    cache_reason=str(e),
                )
                yield _sse({"type": "cached", "message": f"AI failed, using stale cache: {e}", "result": rc.model_dump(mode='json')})
                yield "data: [DONE]\n\n"
                return
            logger.error(f"AI analysis failed for incident {incident_id}: {e}")
            yield _sse({"type": "error", "message": "Analysis temporarily unavailable. Please try again later."})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "validating", "message": "Validating AI response..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "caching", "message": "Caching analysis result..."})

        async with get_connection() as conn2:
            await conn2.execute(
                """
                INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                VALUES ($1, 'root_cause', $2)
                """,
                str(incident_id),
                json.dumps(result),
            )
            await log_audit(
                conn2,
                str(incident_id),
                str(current_user.id),
                "analysis_run",
                "analysis",
                None,
                {"type": "root_cause"},
                request.client.host if request.client else None,
            )

        rc = RootCauseAnalysis(
            primary_cause=result["primary_cause"],
            contributing_factors=result["contributing_factors"],
            prevention_suggestions=result["prevention_suggestions"],
            reasoning=result["reasoning"],
            generated_at=result["generated_at"],
        )
        yield _sse({"type": "complete", "result": rc.model_dump(mode='json')})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{incident_id}/analyze/recommendations")
async def analyze_recommendations(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Generate corrective action recommendations using AI (SSE stream)."""
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError
    from app.matcha.models.ir_incident import RecommendationItem

    # Pre-fetch all data before starting the stream
    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)
        row = dict(row)

        company_name = None
        industry = None
        company_size = None
        ir_guidance_blurb = None

        if row.get("company_id"):
            company = await conn.fetchrow(
                "SELECT name, industry, size, ir_guidance_blurb FROM companies WHERE id = $1",
                row["company_id"],
            )
            if company:
                company_name = company["name"]
                industry = company["industry"]
                company_size = company["size"]
                ir_guidance_blurb = company["ir_guidance_blurb"]

        city = None
        state = None

        if row.get("location_id"):
            location = await conn.fetchrow(
                "SELECT city, state FROM business_locations WHERE id = $1",
                row["location_id"],
            )
            if location:
                city = location["city"]
                state = location["state"]

        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'recommendations'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

    async def event_stream():
        yield _sse({"type": "phase", "step": "loading_incident", "message": "Loading incident data..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "loading_context", "message": "Loading company & location context..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "checking_cache", "message": "Checking analysis cache..."})
        await asyncio.sleep(0.05)

        if cached:
            result = _safe_json_loads(cached["analysis_data"])
            rec = RecommendationsAnalysis(
                recommendations=[RecommendationItem(**r) for r in result["recommendations"]],
                summary=result["summary"],
                generated_at=result["generated_at"],
                from_cache=True,
            )
            yield _sse({"type": "cached", "message": "Using cached analysis result", "result": rec.model_dump(mode='json')})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "building_context", "message": "Building analysis context..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "analyzing", "message": "AI generating recommendations..."})

        try:
            analyzer = get_ir_analyzer()
            result = await analyzer.generate_recommendations(
                title=row["title"],
                description=row["description"],
                incident_type=row["incident_type"],
                severity=row["severity"],
                root_cause=row["root_cause"],
                company_name=company_name,
                industry=industry,
                company_size=company_size,
                city=city,
                state=state,
                ir_guidance_blurb=ir_guidance_blurb,
            )
        except IRAnalysisError as e:
            if cached:
                result_data = _safe_json_loads(cached["analysis_data"])
                rec = RecommendationsAnalysis(
                    recommendations=[RecommendationItem(**r) for r in result_data["recommendations"]],
                    summary=result_data["summary"],
                    generated_at=result_data["generated_at"],
                    from_cache=True,
                    cache_reason=str(e),
                )
                yield _sse({"type": "cached", "message": f"AI failed, using stale cache: {e}", "result": rec.model_dump(mode='json')})
                yield "data: [DONE]\n\n"
                return
            logger.error(f"AI analysis failed for incident {incident_id}: {e}")
            yield _sse({"type": "error", "message": "Analysis temporarily unavailable. Please try again later."})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "validating", "message": "Validating AI response..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "caching", "message": "Caching analysis result..."})

        async with get_connection() as conn2:
            await conn2.execute(
                """
                INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                VALUES ($1, 'recommendations', $2)
                """,
                str(incident_id),
                json.dumps(result),
            )
            await log_audit(
                conn2,
                str(incident_id),
                str(current_user.id),
                "analysis_run",
                "analysis",
                None,
                {"type": "recommendations"},
                request.client.host if request.client else None,
            )

        rec = RecommendationsAnalysis(
            recommendations=[RecommendationItem(**r) for r in result["recommendations"]],
            summary=result["summary"],
            generated_at=result["generated_at"],
        )
        yield _sse({"type": "complete", "result": rec.model_dump(mode='json')})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{incident_id}/analyze/similar")
async def analyze_similar_incidents(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Find precedent incidents using hybrid similarity scoring (SSE stream)."""
    from app.matcha.services.ir_precedent import find_precedents_stream

    # Pre-fetch data before starting the stream
    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)
        row = dict(row)

        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'similar'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

    async def event_stream():
        yield _sse({"type": "phase", "step": "loading_incident", "message": "Loading incident data..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "checking_cache", "message": "Checking analysis cache..."})
        await asyncio.sleep(0.05)

        if cached:
            result = _safe_json_loads(cached["analysis_data"])
            if "precedents" in result:
                result["from_cache"] = True
                pa = PrecedentAnalysis(**result)
                yield _sse({"type": "cached", "message": "Using cached precedent analysis", "result": pa.model_dump(mode='json')})
                yield "data: [DONE]\n\n"
                return

        # Stream precedent analysis phases
        result = None
        async with get_connection() as conn2:
            async for event in find_precedents_stream(str(incident_id), conn2, incident_row=row):
                if event.get("type") == "result":
                    result = event["data"]
                else:
                    yield _sse(event)

        if result is None:
            yield _sse({"type": "error", "message": "Analysis produced no result."})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "caching", "message": "Caching precedent analysis..."})

        async with get_connection() as conn3:
            await conn3.execute(
                """
                INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                VALUES ($1, 'similar', $2)
                ON CONFLICT (incident_id, analysis_type)
                DO UPDATE SET analysis_data = $2, generated_at = now()
                """,
                str(incident_id),
                json.dumps(result),
            )
            # Invalidate stale consistency guidance since precedents changed
            await conn3.execute(
                "DELETE FROM ir_incident_analysis WHERE incident_id = $1 AND analysis_type = 'consistency'",
                str(incident_id),
            )
            await log_audit(
                conn3,
                str(incident_id),
                str(current_user.id),
                "analysis_run",
                "analysis",
                None,
                {"type": "similar"},
                request.client.host if request.client else None,
            )

        pa = PrecedentAnalysis(**result)
        yield _sse({"type": "complete", "result": pa.model_dump(mode='json')})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ===========================================
# Policy Mapping
# ===========================================


async def _get_handbook_policy_entries(conn, company_id) -> list[dict]:
    """Fetch active handbook sections as policy-compatible dicts for policy mapping."""
    handbook = await conn.fetchrow(
        """
        SELECT id, title, active_version
        FROM handbooks
        WHERE company_id = $1 AND status = 'active'
        ORDER BY published_at DESC NULLS LAST, updated_at DESC
        LIMIT 1
        """,
        company_id,
    )
    if not handbook:
        return []

    version_id = await conn.fetchval(
        "SELECT id FROM handbook_versions WHERE handbook_id = $1 AND version_number = $2",
        handbook["id"], handbook["active_version"],
    )
    if version_id is None:
        version_id = await conn.fetchval(
            "SELECT id FROM handbook_versions WHERE handbook_id = $1 ORDER BY version_number DESC LIMIT 1",
            handbook["id"],
        )
    if version_id is None:
        return []

    sections = await conn.fetch(
        """
        SELECT id, title, content
        FROM handbook_sections
        WHERE handbook_version_id = $1 AND content IS NOT NULL AND content != ''
        ORDER BY section_order ASC
        """,
        version_id,
    )
    handbook_title = handbook["title"] or "Employee Handbook"
    return [
        {
            "id": str(s["id"]),
            "title": f"{handbook_title} — {s['title']}" if s["title"] else handbook_title,
            "description": (s["content"] or "")[:300],
            "content": s["content"],
        }
        for s in sections
        if (s["content"] or "").strip()
    ]


async def _auto_map_policy_violations(incident_id: str, company_id: str):
    """Background task: auto-map incident to company policies."""
    try:
        from app.matcha.services.ir_analysis import get_ir_analyzer

        async with get_connection() as conn:
            # Fetch incident
            row = await conn.fetchrow(
                "SELECT title, description, incident_type, severity, category_data FROM ir_incidents WHERE id = $1",
                incident_id,
            )
            if not row:
                return

            # Fetch active policies + handbook sections
            policies = await conn.fetch(
                "SELECT id, title, description, content FROM policies WHERE company_id = $1 AND status = 'active'",
                company_id,
            )
            handbook_policies = await _get_handbook_policy_entries(conn, company_id)

            if not policies and not handbook_policies:
                # Cache empty result
                empty_result = {
                    "matches": [],
                    "summary": "No active policies or handbook found for this company.",
                    "no_matching_policies": True,
                    "generated_at": _utc_now_naive().isoformat(),
                }
                await conn.execute(
                    """
                    INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                    VALUES ($1, 'policy_mapping', $2)
                    ON CONFLICT (incident_id, analysis_type)
                    DO UPDATE SET analysis_data = $2, generated_at = now()
                    """,
                    incident_id,
                    json.dumps(empty_result),
                )
                return

            policies_list = [
                {"id": str(p["id"]), "title": p["title"], "description": p.get("description"), "content": p.get("content")}
                for p in policies
            ] + handbook_policies

            analyzer = get_ir_analyzer()
            result = await analyzer.map_policy_violations(
                title=row["title"],
                description=row.get("description") or "",
                incident_type=row["incident_type"],
                severity=row["severity"],
                category_data=_safe_json_loads(row.get("category_data"), {}),
                policies=policies_list,
            )

            await conn.execute(
                """
                INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                VALUES ($1, 'policy_mapping', $2)
                ON CONFLICT (incident_id, analysis_type)
                DO UPDATE SET analysis_data = $2, generated_at = now()
                """,
                incident_id,
                json.dumps(result),
            )
    except Exception as e:
        logger.warning(f"Auto policy mapping failed for incident {incident_id}: {e}")


@router.get("/{incident_id}/policy-mapping", response_model=PolicyMappingAnalysis)
async def get_policy_mapping(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Get policy violation mapping for an incident."""
    from app.matcha.services.ir_analysis import get_ir_analyzer

    async with get_connection() as conn:
        inc = await _get_incident_with_company_check(conn, incident_id, current_user, columns="id, title, description, incident_type, severity, category_data, company_id")

        # Check cache (<24h)
        cached = await conn.fetchrow(
            """
            SELECT analysis_data, generated_at FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'policy_mapping'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            cache_age = _utc_now_naive() - cached["generated_at"]
            if cache_age < timedelta(hours=24):
                result = _safe_json_loads(cached["analysis_data"])
                result["from_cache"] = True
                return PolicyMappingAnalysis(**result)

        # Fetch active policies + handbook sections
        company_id = inc.get("company_id")
        if not company_id:
            return PolicyMappingAnalysis(
                matches=[], summary="No company associated with this incident.",
                no_matching_policies=True, generated_at=_utc_now_naive().isoformat(),
            )

        policies = await conn.fetch(
            "SELECT id, title, description, content FROM policies WHERE company_id = $1 AND status = 'active'",
            company_id,
        )

        # Also include active handbook sections as policy sources
        handbook_policies = await _get_handbook_policy_entries(conn, company_id)

        all_policies = list(policies) + handbook_policies

        if not all_policies:
            empty = PolicyMappingAnalysis(
                matches=[], summary="No active policies or handbook found for this company.",
                no_matching_policies=True, generated_at=_utc_now_naive().isoformat(),
            )
            # Cache
            await conn.execute(
                """
                INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                VALUES ($1, 'policy_mapping', $2)
                ON CONFLICT (incident_id, analysis_type)
                DO UPDATE SET analysis_data = $2, generated_at = now()
                """,
                str(incident_id),
                json.dumps(empty.model_dump(mode='json')),
            )
            return empty

        policies_list = [
            {"id": str(p["id"]), "title": p["title"], "description": p.get("description"), "content": p.get("content")}
            for p in policies
        ] + handbook_policies

        try:
            analyzer = get_ir_analyzer()
            result = await analyzer.map_policy_violations(
                title=inc["title"],
                description=inc.get("description") or "",
                incident_type=inc["incident_type"],
                severity=inc["severity"],
                category_data=_safe_json_loads(inc.get("category_data"), {}),
                policies=policies_list,
            )
        except Exception as e:
            logger.warning(f"Policy mapping failed: {e}")
            raise HTTPException(status_code=502, detail="Policy mapping analysis failed")

        # Cache result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'policy_mapping', $2)
            ON CONFLICT (incident_id, analysis_type)
            DO UPDATE SET analysis_data = $2, generated_at = now()
            """,
            str(incident_id),
            json.dumps(result),
        )

        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "policy_mapping"},
            request.client.host if request.client else None,
        )

        return PolicyMappingAnalysis(**result)


@router.post("/{incident_id}/analyze/policy-mapping", response_model=PolicyMappingAnalysis)
async def refresh_policy_mapping(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Force-refresh policy mapping for an incident."""
    async with get_connection() as conn:
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")

        # Delete existing cache
        await conn.execute(
            "DELETE FROM ir_incident_analysis WHERE incident_id = $1 AND analysis_type = 'policy_mapping'",
            str(incident_id),
        )

    # Delegate to the GET handler which will compute fresh
    return await get_policy_mapping(incident_id, request, current_user)


@router.get("/{incident_id}/consistency-guidance", response_model=ConsistencyGuidance)
async def get_consistency_guidance(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Get consistency guidance based on precedent analysis for an incident."""
    from app.matcha.services.ir_consistency import compute_outcome_distribution

    async with get_connection() as conn:
        # Verify incident exists and belongs to company
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")

        # Read cached similar analysis to get precedents
        similar_row = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'similar'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if not similar_row:
            return ConsistencyGuidance(
                sample_size=0,
                effective_sample_size=0.0,
                confidence="insufficient",
                unprecedented=True,
                generated_at=_utc_now_naive().isoformat(),
            )

        similar_data = _safe_json_loads(similar_row["analysis_data"])
        precedents = similar_data.get("precedents", [])

        if not precedents:
            return ConsistencyGuidance(
                sample_size=0,
                effective_sample_size=0.0,
                confidence="insufficient",
                unprecedented=True,
                generated_at=_utc_now_naive().isoformat(),
            )

        # Check for cached consistency result (<24h)
        cached = await conn.fetchrow(
            """
            SELECT analysis_data, generated_at FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'consistency'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            cache_age = _utc_now_naive() - cached["generated_at"]
            if cache_age < timedelta(hours=24):
                result = _safe_json_loads(cached["analysis_data"])
                result["from_cache"] = True
                return ConsistencyGuidance(**result)

        # Compute fresh guidance
        settings = get_settings()
        try:
            result = await compute_outcome_distribution(
                precedents,
                api_key=settings.gemini_api_key if not settings.use_vertex else None,
                vertex_project=settings.vertex_project if settings.use_vertex else None,
            )
        except Exception as e:
            logger.warning(f"Consistency guidance computation failed: {e}")
            return ConsistencyGuidance(
                sample_size=len(precedents),
                effective_sample_size=0.0,
                confidence="insufficient",
                unprecedented=False,
                generated_at=_utc_now_naive().isoformat(),
            )

        # Cache result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'consistency', $2)
            ON CONFLICT (incident_id, analysis_type)
            DO UPDATE SET analysis_data = $2, generated_at = now()
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "consistency"},
            request.client.host if request.client else None,
        )

        return ConsistencyGuidance(**result)


@router.delete("/{incident_id}/analyze/{analysis_type}")
async def clear_analysis_cache(
    incident_id: UUID,
    analysis_type: ANALYSIS_TYPES,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Clear cached analysis to force re-analysis."""
    async with get_connection() as conn:
        # Verify incident exists and belongs to company
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")

        # Delete cached analysis
        await conn.execute(
            """
            DELETE FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = $2
            """,
            str(incident_id),
            analysis_type,
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_cleared",
            "analysis",
            None,
            {"type": analysis_type},
            request.client.host if request.client else None,
        )

        return {"message": f"Analysis cache cleared for {analysis_type}"}







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


# ===========================================
# IR Copilot — orchestrator endpoints
# ===========================================


def _coerce_metadata_dict(value):
    """asyncpg returns JSONB as str when no codec is registered."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def _serialize_message(row) -> IRCopilotMessage:
    return IRCopilotMessage(
        id=row["id"],
        role=row["role"],
        message_type=row.get("message_type", "text") if isinstance(row, dict) else row["message_type"],
        content=row["content"],
        metadata=_coerce_metadata_dict(row["metadata"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _extract_current_cards(messages: list) -> list[IRCopilotCard]:
    """Latest assistant card-set is everything between the last assistant text and now."""
    cards: list[dict] = []
    saw_assistant_text = False
    for m in messages:
        role = m["role"] if isinstance(m, dict) else m.role
        mtype = (m["message_type"] if isinstance(m, dict) else m.message_type) if hasattr(m, 'message_type') or isinstance(m, dict) else "text"
        if role == "assistant" and mtype == "text":
            saw_assistant_text = True
            cards = []  # reset — start fresh after each assistant text
            continue
        if saw_assistant_text and role == "assistant" and mtype == "card":
            md = _coerce_metadata_dict(m["metadata"] if isinstance(m, dict) else m.metadata) or {}
            card = md.get("card")
            if isinstance(card, dict):
                # Only include cards that haven't been accepted, superseded, or skipped.
                if not md.get("accepted") and not md.get("superseded") and not md.get("skipped"):
                    try:
                        cards.append(IRCopilotCard.model_validate(card))
                    except Exception:
                        continue
    return cards


def _extract_summary_and_open_questions(messages: list) -> tuple[Optional[str], list[str]]:
    summary: Optional[str] = None
    open_questions: list[str] = []
    for m in reversed(messages):
        role = m["role"] if isinstance(m, dict) else m.role
        mtype = m["message_type"] if isinstance(m, dict) else m.message_type
        if role == "assistant" and mtype == "text":
            summary = m["content"] if isinstance(m, dict) else m.content
            md = _coerce_metadata_dict(m["metadata"] if isinstance(m, dict) else m.metadata) or {}
            raw_q = md.get("open_questions") or []
            if isinstance(raw_q, list):
                open_questions = [str(q)[:280] for q in raw_q if isinstance(q, str)]
            break
    return summary, open_questions


@router.get("/{incident_id}/copilot", response_model=IRCopilotTranscript)
async def get_copilot_transcript(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Return the full chat transcript + currently-active cards for an incident."""
    async with get_connection() as conn:
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")
        rows = await conn.fetch(
            "SELECT id, role, message_type, content, metadata, created_by, created_at "
            "FROM ir_incident_ai_messages WHERE incident_id = $1 ORDER BY created_at",
            incident_id,
        )

    messages = [_serialize_message(r) for r in rows]
    cards = _extract_current_cards(messages)
    summary, open_questions = _extract_summary_and_open_questions(messages)
    return IRCopilotTranscript(
        incident_id=incident_id,
        messages=messages,
        current_cards=cards,
        summary=summary,
        open_questions=open_questions,
    )


@router.post("/{incident_id}/copilot/stream")
async def stream_copilot_round(
    incident_id: UUID,
    body: IRCopilotStreamRequest,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Run one guidance round. Empty body = cold start. SSE stream of:
      - {type:'status', stage:'thinking'}
      - {type:'summary', text:...}
      - {type:'card', card:...}  (one event per card)
      - {type:'open_question', text:...}
      - {type:'done'}
    Persists user message + assistant text + one row per card.
    """
    from app.matcha.services.ir_ai_orchestrator import (
        generate_guidance,
        load_incident_state,
        persist_assistant_round,
    )

    company_id = await get_client_company_id(current_user)

    async def event_stream():
        # Acquire connection inside generator so it lives for the full stream
        async with get_connection() as conn:
            incident, analyses, messages = await load_incident_state(
                conn, incident_id, company_id
            )
            if incident is None:
                yield _sse({"type": "error", "detail": "Incident not found"})
                return

            yield _sse({"type": "status", "stage": "thinking"})

            # Append the user's message FIRST so the orchestrator includes it.
            user_msg = (body.message or "").strip()
            if user_msg:
                from app.matcha.services.ir_ai_orchestrator import append_message
                user_row = await append_message(
                    conn,
                    incident_id=incident_id,
                    role="user",
                    message_type="text",
                    content=user_msg[:4000],
                    created_by=current_user.id,
                )
                messages.append(user_row)

            try:
                payload = await generate_guidance(
                    incident=incident,
                    analyses=analyses,
                    messages=messages,
                )
            except Exception as exc:
                logger.exception("IR Copilot round failed for incident %s", incident_id)
                yield _sse({"type": "error", "detail": "Failed to generate guidance"})
                return

            # Persist assistant text + cards
            await persist_assistant_round(
                conn,
                incident_id=incident_id,
                user_id=current_user.id,
                user_message=None,  # already inserted above
                guidance_payload=payload,
            )

            yield _sse({"type": "summary", "text": payload.get("summary") or ""})
            for q in payload.get("open_questions") or []:
                yield _sse({"type": "open_question", "text": q})
            for card in payload.get("cards") or []:
                yield _sse({"type": "card", "card": card})
            yield _sse({"type": "done", "model": payload.get("model")})

            await log_audit(
                conn,
                incident_id=str(incident_id),
                user_id=str(current_user.id),
                action="copilot_message",
                entity_type="incident",
                entity_id=str(incident_id),
                details={"cards": len(payload.get("cards") or []), "user_message_len": len(user_msg)},
                ip_address=request.client.host if request.client else None,
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


_FIELD_WHITELIST = {
    "category": "incident_type",  # alias — DB col is incident_type
    "incident_type": "incident_type",
    "severity": "severity",
    "status": "status",
    "root_cause": "root_cause",
    "corrective_actions": "corrective_actions",
}

_FIELD_LABELS = {
    "incident_type": "Type",
    "severity": "Severity",
    "status": "Status",
    "root_cause": "Root cause",
    "corrective_actions": "Corrective actions",
}


_VALID_INCIDENT_TYPES = {"safety", "behavioral", "property", "near_miss", "other"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}
_VALID_STATUSES = {"reported", "investigating", "action_required", "resolved", "closed"}


def _validate_field_value(field: str, value):
    if field == "incident_type" and value not in _VALID_INCIDENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid incident_type: {value}")
    if field == "severity" and value not in _VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity: {value}")
    if field == "status" and value not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {value}")


@router.post("/{incident_id}/copilot/skip")
async def skip_copilot_card(
    incident_id: UUID,
    body: IRCopilotAcceptRequest,
    current_user=Depends(require_admin_or_client),
):
    """Persist a Skip on a copilot card so it doesn't re-surface on refresh
    or in the next round. Same body shape as /copilot/accept (message_id,
    card_id) — accept and skip are sibling actions on the same card row."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")

        row = await conn.fetchrow(
            """
            SELECT id, metadata
            FROM ir_incident_ai_messages
            WHERE id = $1 AND incident_id = $2 AND message_type = 'card'
            """,
            body.message_id, incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Card message not found")

        meta = _coerce_metadata_dict(row["metadata"]) or {}
        # Verify card_id matches what's stored — defense in depth.
        stored_card = meta.get("card") or {}
        if isinstance(stored_card, dict) and stored_card.get("id") != body.card_id:
            raise HTTPException(status_code=400, detail="Card id mismatch")

        meta["skipped"] = True
        meta["skipped_at"] = _utc_now_naive().isoformat()

        await conn.execute(
            "UPDATE ir_incident_ai_messages SET metadata = $1::jsonb WHERE id = $2",
            json.dumps(meta), body.message_id,
        )

        await log_audit(
            conn,
            incident_id=str(incident_id),
            user_id=str(current_user.id),
            action="copilot_skip",
            entity_type="incident",
            entity_id=str(incident_id),
            details={"card_id": body.card_id, "message_id": str(body.message_id)},
            ip_address=None,
        )

    _ = company_id  # company access already verified by _get_incident_with_company_check
    return {"ok": True}


async def _close_incident_via_copilot(
    conn,
    *,
    incident_id: UUID,
    source_card_id: Optional[UUID] = None,
) -> dict:
    """Close an incident and supersede any open card recommendations.

    Called from both the card-accept path (with source_card_id set) and the
    direct-button path (source_card_id None — supersede ALL open cards).
    Idempotent: returns ``already_closed=True`` and skips writes when the
    incident is already in 'closed' status.
    """
    prev_status = await conn.fetchval(
        "SELECT status FROM ir_incidents WHERE id = $1", incident_id,
    )
    if prev_status == "closed":
        return {"already_closed": True, "previous_value": prev_status, "new_value": "closed"}

    await conn.execute(
        "UPDATE ir_incidents SET status = 'closed', resolved_at = NOW(), "
        "updated_at = NOW() WHERE id = $1",
        incident_id,
    )
    if source_card_id is not None:
        await conn.execute(
            """
            UPDATE ir_incident_ai_messages
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{superseded}', 'true'::jsonb, true
            )
            WHERE incident_id = $1
              AND message_type = 'card'
              AND id != $2
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
            """,
            incident_id, source_card_id,
        )
    else:
        await conn.execute(
            """
            UPDATE ir_incident_ai_messages
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{superseded}', 'true'::jsonb, true
            )
            WHERE incident_id = $1
              AND message_type = 'card'
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
            """,
            incident_id,
        )

    return {
        "already_closed": False,
        "previous_value": prev_status,
        "new_value": "closed",
        "field": "status",
        "field_label": "Status",
    }


@router.post("/{incident_id}/copilot/close")
async def close_incident_via_copilot(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Direct close — no card required. Used by the panel's Close button."""
    from app.matcha.services.ir_ai_orchestrator import append_message

    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _get_incident_with_company_check(
            conn, incident_id, current_user, columns="id"
        )
        result = await _close_incident_via_copilot(
            conn, incident_id=incident_id, source_card_id=None,
        )
        if result.get("already_closed"):
            _ = company_id
            return {"ok": True, "already_closed": True}

        await append_message(
            conn,
            incident_id=incident_id,
            role="system",
            message_type="event",
            content="Updated Status",
            metadata={
                "action": "close_incident",
                "card_id": None,
                "source": "direct_button",
                "field": "status",
                "field_label": "Status",
                "previous_value": result["previous_value"],
                "new_value": "closed",
                "note": "Closed directly from copilot. Other recommendations cleared.",
            },
            created_by=current_user.id,
        )
        await log_audit(
            conn,
            incident_id=str(incident_id),
            user_id=str(current_user.id),
            action="copilot_close_direct",
            entity_type="incident",
            entity_id=str(incident_id),
            details={"previous_status": result["previous_value"]},
            ip_address=request.client.host if request.client else None,
        )
    _ = company_id
    return {"ok": True, **result}


@router.post("/{incident_id}/copilot/accept")
async def accept_copilot_card(
    incident_id: UUID,
    body: IRCopilotAcceptRequest,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Execute a card action and stream stage progression to the client.

    SSE events:
      - {type:'status', stage:'starting'}
      - {type:'status', stage:'running_analysis', analysis_type:'policy_mapping'}
      - {type:'status', stage:'analysis_complete', analysis_type:...}
      - {type:'event', text:...}              event summary persisted
      - {type:'status', stage:'thinking'}     guidance round starting
      - {type:'summary', text:...}
      - {type:'card', card:...}                one event per card
      - {type:'open_question', text:...}
      - {type:'done'}
      - {type:'error', detail:...}
    """
    from app.matcha.services.ir_ai_orchestrator import (
        _canonical_analysis_type,
        append_message,
        generate_guidance,
        load_incident_state,
        persist_assistant_round,
    )

    company_id = await get_client_company_id(current_user)

    async def event_stream():
        async with get_connection() as conn:
            incident, analyses, messages = await load_incident_state(
                conn, incident_id, company_id
            )
            if incident is None:
                yield _sse({"type": "error", "detail": "Incident not found"})
                return

            card_row = await conn.fetchrow(
                "SELECT id, metadata FROM ir_incident_ai_messages "
                "WHERE id = $1 AND incident_id = $2 AND message_type = 'card'",
                body.message_id, incident_id,
            )
            if not card_row:
                yield _sse({"type": "error", "detail": "Card not found"})
                return

            md = _coerce_metadata_dict(card_row["metadata"]) or {}
            card = md.get("card") or {}
            if card.get("id") != body.card_id:
                yield _sse({"type": "error", "detail": "Card id mismatch"})
                return
            if md.get("accepted"):
                yield _sse({"type": "error", "detail": "Card already accepted"})
                return

            action = card.get("action") or {}
            action_type = action.get("type")
            event_summary = ""
            event_extra: dict = {}

            yield _sse({"type": "status", "stage": "starting", "action_type": action_type})

            try:
                if action_type == "set_field":
                    raw_field = (action.get("field_name") or "").strip()
                    new_value = action.get("field_value")
                    if raw_field not in _FIELD_WHITELIST:
                        yield _sse({"type": "error", "detail": "Field not editable via copilot"})
                        return
                    db_field = _FIELD_WHITELIST[raw_field]
                    try:
                        _validate_field_value(db_field, new_value)
                    except HTTPException as exc:
                        yield _sse({"type": "error", "detail": exc.detail})
                        return
                    prev = await conn.fetchval(
                        f"SELECT {db_field} FROM ir_incidents WHERE id = $1", incident_id,
                    )
                    await conn.execute(
                        f"UPDATE ir_incidents SET {db_field} = $1, updated_at = NOW() WHERE id = $2",
                        new_value, incident_id,
                    )
                    field_label = _FIELD_LABELS.get(db_field, db_field.replace("_", " ").title())
                    event_summary = f"Updated {field_label}"
                    event_extra = {
                        "field": db_field,
                        "field_label": field_label,
                        "previous_value": prev,
                        "new_value": new_value,
                    }

                elif action_type == "run_analysis":
                    analysis_type = _canonical_analysis_type(action.get("analysis_type"))
                    if analysis_type is None:
                        # Stale card from before the orchestrator filter landed.
                        # Surface as ephemeral SSE error — no DB event row, so the
                        # transcript stays clean instead of accumulating noise.
                        yield _sse({
                            "type": "error",
                            "detail": "Couldn't determine which analysis to run. Open the AI Analysis tab and pick one manually.",
                        })
                        return
                    if analysis_type == "policy_mapping":
                        yield _sse({
                            "type": "status",
                            "stage": "running_analysis",
                            "analysis_type": "policy_mapping",
                            "label": "Reading active handbook + policies, running policy mapping…",
                        })
                        try:
                            await _auto_map_policy_violations(str(incident_id), str(incident["company_id"]))
                            yield _sse({
                                "type": "status",
                                "stage": "analysis_complete",
                                "analysis_type": "policy_mapping",
                            })
                            event_summary = "Policy mapping complete (uses active handbook + policies)."
                        except Exception as exc:
                            logger.exception("policy_mapping failed for incident %s", incident_id)
                            event_summary = f"Policy mapping failed: {exc}"
                    else:
                        event_summary = (
                            f"Open the AI Analysis tab and click Run on '{analysis_type.replace('_', ' ').title()}'."
                        )

                elif action_type == "escalate":
                    existing_er = await conn.fetchval(
                        "SELECT er_case_id FROM ir_incidents WHERE id = $1", incident_id,
                    )
                    if existing_er:
                        event_summary = f"Already linked to ER case {existing_er}"
                    else:
                        event_summary = "Marked for ER escalation — open ER Copilot to create the case."

                elif action_type == "close_incident":
                    close_result = await _close_incident_via_copilot(
                        conn,
                        incident_id=incident_id,
                        source_card_id=card_row["id"],
                    )
                    event_summary = "Updated Status"
                    event_extra = {
                        "field": "status",
                        "field_label": "Status",
                        "previous_value": close_result["previous_value"],
                        "new_value": "closed",
                        "note": "Other recommendations cleared.",
                    }

                elif action_type == "request_info":
                    event_summary = "Request acknowledged — answer in chat below."

                else:
                    yield _sse({"type": "error", "detail": f"Unknown action type: {action_type}"})
                    return

                # Mark the card accepted
                new_md = dict(md)
                new_md["accepted"] = True
                new_md["accepted_at"] = datetime.now(timezone.utc).isoformat()
                new_md["accepted_by"] = str(current_user.id)
                await conn.execute(
                    "UPDATE ir_incident_ai_messages SET metadata = $1::jsonb WHERE id = $2",
                    json.dumps(new_md), card_row["id"],
                )

                event_metadata = {"action": action_type, "card_id": body.card_id, **event_extra}
                await append_message(
                    conn,
                    incident_id=incident_id,
                    role="system",
                    message_type="event",
                    content=event_summary,
                    metadata=event_metadata,
                    created_by=current_user.id,
                )
                yield _sse({"type": "event", "text": event_summary, **event_extra, "action": action_type})

                await log_audit(
                    conn,
                    incident_id=str(incident_id),
                    user_id=str(current_user.id),
                    action="copilot_card_accepted",
                    entity_type="incident",
                    entity_id=str(incident_id),
                    details={"card_id": body.card_id, "action_type": action_type},
                    ip_address=request.client.host if request.client else None,
                )

                # Re-run guidance with fresh state
                yield _sse({"type": "status", "stage": "thinking"})
                incident, analyses, messages = await load_incident_state(
                    conn, incident_id, company_id
                )
                try:
                    payload = await generate_guidance(
                        incident=incident, analyses=analyses, messages=messages,
                    )
                except Exception:
                    logger.exception("Follow-up guidance failed after accept")
                    payload = {"summary": event_summary, "open_questions": [], "cards": []}

                await persist_assistant_round(
                    conn,
                    incident_id=incident_id,
                    user_id=current_user.id,
                    user_message=None,
                    guidance_payload=payload,
                )

                yield _sse({"type": "summary", "text": payload.get("summary") or ""})
                for q in payload.get("open_questions") or []:
                    yield _sse({"type": "open_question", "text": q})
                for new_card in payload.get("cards") or []:
                    yield _sse({"type": "card", "card": new_card})
                yield _sse({"type": "done", "model": payload.get("model")})
            except Exception:
                logger.exception("copilot accept failed for incident %s", incident_id)
                yield _sse({"type": "error", "detail": "Action failed — see server logs"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
