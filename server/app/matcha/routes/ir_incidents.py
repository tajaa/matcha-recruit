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

from ...database import get_connection
from ...core.dependencies import require_admin
from ..dependencies import require_admin_or_client, get_client_company_id
from ...config import get_settings
from ...core.services.storage import get_storage
from ...core.services.email import get_email_service
from ..models.ir_incident import (
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
    IRAuditLogEntry,
    IRAuditLogResponse,
    Witness,
    OshaRecordabilityUpdate,
    Osha300LogEntry,
    Osha300ASummary,
)
from ..models.interview import (
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

    # Ensure occurred_at is naive UTC for TIMESTAMP column
    occurred_at = incident.occurred_at
    if occurred_at.tzinfo:
        occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ir_incidents (
                incident_number, title, description, incident_type, severity,
                occurred_at, location, reported_by_name, reported_by_email,
                witnesses, category_data, involved_employee_ids,
                company_id, location_id, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            RETURNING *
            """,
            incident_number,
            incident.title,
            incident.description,
            incident.incident_type,
            incident.severity,
            occurred_at,
            incident.location,
            incident.reported_by_name,
            incident.reported_by_email,
            json.dumps([w.model_dump() for w in incident.witnesses]),
            json.dumps(incident.category_data or {}),
            [str(uid) for uid in incident.involved_employee_ids] if incident.involved_employee_ids else None,
            effective_company_id,
            str(incident.location_id) if incident.location_id else None,
            str(current_user.id),
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
            {"title": incident.title, "type": incident.incident_type},
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
# Anonymous Reporting Token Management
# ===========================================

@router.get("/anonymous-reporting/status")
async def get_anonymous_reporting_status(
    current_user=Depends(require_admin_or_client),
):
    """Get the company's anonymous reporting token (or null if disabled)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT report_email_token, report_token_used_at FROM companies WHERE id = $1",
            company_id,
        )
    if not row or not row["report_email_token"]:
        return {"token": None, "enabled": False, "used": False}
    return {
        "token": row["report_email_token"],
        "enabled": True,
        "used": row["report_token_used_at"] is not None,
    }


@router.post("/anonymous-reporting/generate")
async def generate_anonymous_reporting_token(
    current_user=Depends(require_admin_or_client),
):
    """Generate or regenerate the anonymous reporting token."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    token = secrets.token_hex(6)
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE companies SET report_email_token = $1, report_token_used_at = NULL WHERE id = $2",
            token,
            company_id,
        )
    return {"token": token, "enabled": True, "used": False}


@router.delete("/anonymous-reporting/disable")
async def disable_anonymous_reporting(
    current_user=Depends(require_admin_or_client),
):
    """Disable anonymous reporting by clearing the token."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE companies SET report_email_token = NULL WHERE id = $1",
            company_id,
        )
    return {"token": None, "enabled": False}


# ===========================================
# OSHA 300/301 Log Endpoints
# (Registered before /{incident_id} to avoid path conflict)
# ===========================================

VALID_OSHA_CLASSIFICATIONS = {
    "death", "days_away", "restricted_duty",
    "medical_treatment", "loss_of_consciousness", "significant_injury",
}


def _safe_json_loads(val, default=None):
    """Parse a JSON string or return a dict/list as-is."""
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default


@router.get("/osha/300-log", response_model=list[Osha300LogEntry])
async def get_osha_300_log(
    year: int = Query(..., description="Calendar year for the 300 log"),
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 300 log for a given year."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                i.id,
                i.osha_case_number,
                i.title,
                i.description,
                i.location,
                i.occurred_at,
                i.osha_classification,
                COALESCE(i.days_away_from_work, 0) AS days_away_from_work,
                COALESCE(i.days_restricted_duty, 0) AS days_restricted_duty,
                i.category_data,
                i.reported_by_name,
                e.first_name AS emp_first_name,
                e.last_name AS emp_last_name,
                e.job_title AS emp_job_title
            FROM ir_incidents i
            LEFT JOIN employees e
                ON e.email = i.reported_by_email
                AND e.org_id::text = i.company_id
            WHERE i.company_id = $1
              AND i.osha_recordable = true
              AND EXTRACT(YEAR FROM i.occurred_at) = $2
            ORDER BY i.occurred_at
            """,
            company_id,
            year,
        )

    entries = []
    for row in rows:
        emp_name = row["reported_by_name"]
        if row["emp_first_name"]:
            emp_name = f"{row['emp_first_name']} {row['emp_last_name'] or ''}".strip()

        category_data = _safe_json_loads(row.get("category_data"), {})
        injury_type = category_data.get("injury_type")

        entries.append(Osha300LogEntry(
            case_number=row["osha_case_number"] or str(row["id"])[:8],
            employee_name=emp_name,
            job_title=row["emp_job_title"],
            date_of_injury=row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else "",
            location=row["location"],
            description=row["description"],
            classification=row["osha_classification"],
            days_away=row["days_away_from_work"],
            days_restricted=row["days_restricted_duty"],
            injury_type=injury_type,
            incident_id=str(row["id"]),
        ))
    return entries


@router.get("/osha/300-log/csv")
async def get_osha_300_log_csv(
    year: int = Query(..., description="Calendar year for the 300 log CSV"),
    current_user=Depends(require_admin_or_client),
):
    """Export OSHA 300 log as CSV for a given year."""
    entries = await get_osha_300_log(year=year, current_user=current_user)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Case Number", "Employee Name", "Job Title", "Date of Injury/Illness",
        "Where Event Occurred", "Description", "Classification",
        "Days Away From Work", "Days on Restricted Duty", "Injury/Illness Type",
        "Incident ID",
    ])
    for entry in entries:
        writer.writerow([
            entry.case_number,
            entry.employee_name,
            entry.job_title or "",
            entry.date_of_injury,
            entry.location or "",
            entry.description or "",
            entry.classification or "",
            entry.days_away,
            entry.days_restricted,
            entry.injury_type or "",
            entry.incident_id,
        ])

    output.seek(0)
    filename = f"osha_300_log_{year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/osha/301/{incident_id}")
async def get_osha_301_form(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 301 form data for a specific recordable incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                i.*,
                c.name AS company_name,
                c.address AS company_address,
                bl.name AS location_name,
                bl.city AS location_city,
                bl.state AS location_state,
                e.first_name AS emp_first_name,
                e.last_name AS emp_last_name,
                e.job_title AS emp_job_title,
                e.personal_email AS emp_email,
                e.start_date AS emp_start_date
            FROM ir_incidents i
            LEFT JOIN companies c ON c.id::text = i.company_id
            LEFT JOIN business_locations bl ON bl.id::text = i.location_id
            LEFT JOIN employees e
                ON e.email = i.reported_by_email
                AND e.org_id::text = i.company_id
            WHERE i.id = $1
              AND i.company_id = $2
              AND i.osha_recordable = true
            """,
            str(incident_id),
            company_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Recordable incident not found")

    category_data = _safe_json_loads(row.get("category_data"), {})
    form_301_data = _safe_json_loads(row.get("osha_form_301_data"), {})

    emp_name = row["reported_by_name"]
    if row["emp_first_name"]:
        emp_name = f"{row['emp_first_name']} {row['emp_last_name'] or ''}".strip()

    return {
        "incident_id": str(row["id"]),
        "case_number": row["osha_case_number"] or str(row["id"])[:8],
        "employee_name": emp_name,
        "employee_email": row.get("emp_email"),
        "employee_job_title": row.get("emp_job_title"),
        "employee_start_date": row["emp_start_date"].isoformat() if row.get("emp_start_date") else None,
        "employer_name": row.get("company_name"),
        "employer_address": row.get("company_address"),
        "establishment_name": row.get("location_name"),
        "establishment_city": row.get("location_city"),
        "establishment_state": row.get("location_state"),
        "date_of_injury": row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else None,
        "time_of_event": row["occurred_at"].strftime("%H:%M") if row["occurred_at"] else None,
        "location_of_event": row.get("location"),
        "description_of_injury": row.get("description"),
        "object_or_substance": category_data.get("equipment_involved"),
        "injury_type": category_data.get("injury_type"),
        "body_parts_affected": category_data.get("body_parts", []),
        "treatment": category_data.get("treatment"),
        "osha_classification": row.get("osha_classification"),
        "days_away_from_work": row.get("days_away_from_work") or 0,
        "days_restricted_duty": row.get("days_restricted_duty") or 0,
        "date_of_death": row["date_of_death"].isoformat() if row.get("date_of_death") else None,
        "additional_data": form_301_data,
    }


@router.get("/osha/300a", response_model=Osha300ASummary)
async def get_osha_300a_summary(
    year: int = Query(..., description="Calendar year for the 300A summary"),
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 300A annual summary for a given year."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        cached = await conn.fetchrow(
            "SELECT * FROM osha_annual_summaries WHERE company_id = $1 AND year = $2",
            company_id, year,
        )
        if cached:
            return Osha300ASummary(
                year=cached["year"],
                establishment_name=cached["establishment_name"],
                total_cases=cached["total_cases"],
                total_deaths=cached["total_deaths"],
                total_days_away_cases=cached["total_days_away_cases"],
                total_restricted_cases=cached["total_restricted_cases"],
                total_other_recordable=cached["total_other_recordable"],
                total_days_away=cached["total_days_away"],
                total_days_restricted=cached["total_days_restricted"],
                total_injuries=cached["total_injuries"],
                total_skin_disorders=cached["total_skin_disorders"],
                total_respiratory=cached["total_respiratory"],
                total_poisonings=cached["total_poisonings"],
                total_hearing_loss=cached["total_hearing_loss"],
                total_other_illnesses=cached["total_other_illnesses"],
                average_employees=cached["average_employees"],
                total_hours_worked=cached["total_hours_worked"],
            )

        agg = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total_cases,
                COALESCE(SUM(CASE WHEN osha_classification = 'death' THEN 1 ELSE 0 END), 0) AS total_deaths,
                COALESCE(SUM(CASE WHEN osha_classification = 'days_away' THEN 1 ELSE 0 END), 0) AS total_days_away_cases,
                COALESCE(SUM(CASE WHEN osha_classification = 'restricted_duty' THEN 1 ELSE 0 END), 0) AS total_restricted_cases,
                COALESCE(SUM(CASE WHEN osha_classification NOT IN ('death','days_away','restricted_duty') THEN 1 ELSE 0 END), 0) AS total_other_recordable,
                COALESCE(SUM(days_away_from_work), 0) AS total_days_away,
                COALESCE(SUM(days_restricted_duty), 0) AS total_days_restricted
            FROM ir_incidents
            WHERE company_id = $1
              AND osha_recordable = true
              AND EXTRACT(YEAR FROM occurred_at) = $2
            """,
            company_id, year,
        )

        company = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", company_id,
        )

        return Osha300ASummary(
            year=year,
            establishment_name=company["name"] if company else None,
            total_cases=agg["total_cases"],
            total_deaths=agg["total_deaths"],
            total_days_away_cases=agg["total_days_away_cases"],
            total_restricted_cases=agg["total_restricted_cases"],
            total_other_recordable=agg["total_other_recordable"],
            total_days_away=agg["total_days_away"],
            total_days_restricted=agg["total_days_restricted"],
            total_injuries=agg["total_cases"],
            total_skin_disorders=0,
            total_respiratory=0,
            total_poisonings=0,
            total_hearing_loss=0,
            total_other_illnesses=0,
            average_employees=None,
            total_hours_worked=None,
        )


@router.get("/osha/300a/csv")
async def get_osha_300a_csv(
    year: int = Query(..., description="Calendar year for the 300A summary CSV"),
    current_user=Depends(require_admin_or_client),
):
    """Export OSHA 300A annual summary as CSV."""
    summary = await get_osha_300a_summary(year=year, current_user=current_user)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Field", "Value"])
    writer.writerow(["Year", summary.year])
    writer.writerow(["Establishment Name", summary.establishment_name or ""])
    writer.writerow(["Total Cases", summary.total_cases])
    writer.writerow(["Total Deaths", summary.total_deaths])
    writer.writerow(["Total Days Away From Work Cases", summary.total_days_away_cases])
    writer.writerow(["Total Restricted Duty / Transfer Cases", summary.total_restricted_cases])
    writer.writerow(["Total Other Recordable Cases", summary.total_other_recordable])
    writer.writerow(["Total Days Away From Work", summary.total_days_away])
    writer.writerow(["Total Days Restricted Duty", summary.total_days_restricted])
    writer.writerow(["Total Injuries", summary.total_injuries])
    writer.writerow(["Total Skin Disorders", summary.total_skin_disorders])
    writer.writerow(["Total Respiratory Conditions", summary.total_respiratory])
    writer.writerow(["Total Poisonings", summary.total_poisonings])
    writer.writerow(["Total Hearing Loss", summary.total_hearing_loss])
    writer.writerow(["Total Other Illnesses", summary.total_other_illnesses])
    writer.writerow(["Average Number of Employees", summary.average_employees or ""])
    writer.writerow(["Total Hours Worked", summary.total_hours_worked or ""])

    output.seek(0)
    filename = f"osha_300a_summary_{year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
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
            updates.append(f"involved_employee_ids = ${param_idx}")
            params.append([str(uid) for uid in incident.involved_employee_ids])
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
# Documents
# ===========================================

@router.post("/{incident_id}/documents", response_model=IRDocumentUploadResponse)
async def upload_document(
    incident_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    current_user=Depends(require_admin_or_client),
):
    """Upload a document to an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = "company_id = $2"

    # Validate incident exists and belongs to company
    async with get_connection() as conn:
        incident = await conn.fetchrow(
            f"SELECT id FROM ir_incidents WHERE id = $1 AND {company_clause}",
            str(incident_id),
            company_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

    # Validate document type
    valid_types = ["photo", "form", "statement", "other"]
    if document_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Must be one of: {valid_types}")

    # Validate file extension
    allowed_extensions = {".pdf", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".csv", ".json"}
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Allowed: {allowed_extensions}")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Upload to storage
    storage = get_storage()
    file_path = f"ir-incidents/{incident_id}/{file.filename}"

    try:
        storage.upload_file(content, file_path, file.content_type)
    except Exception as e:
        logger.error(f"Failed to upload IR document for incident {incident_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file. Please try again.")

    # Save to database
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ir_incident_documents (
                incident_id, document_type, filename, file_path, mime_type, file_size, uploaded_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            str(incident_id),
            document_type,
            file.filename,
            file_path,
            file.content_type,
            file_size,
            str(current_user.id),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "document_uploaded",
            "document",
            str(row["id"]),
            {"filename": file.filename, "document_type": document_type},
            request.client.host if request.client else None,
        )

        return IRDocumentUploadResponse(
            document=IRDocumentResponse(
                id=row["id"],
                incident_id=row["incident_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                uploaded_by=row["uploaded_by"],
                created_at=row["created_at"],
            ),
            message="Document uploaded successfully",
        )


@router.get("/{incident_id}/documents", response_model=list[IRDocumentResponse])
async def list_documents(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """List all documents for an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = "company_id = $2"

    async with get_connection() as conn:
        # Verify incident exists and belongs to company
        incident = await conn.fetchrow(
            f"SELECT id FROM ir_incidents WHERE id = $1 AND {company_clause}",
            str(incident_id),
            company_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        rows = await conn.fetch(
            """
            SELECT * FROM ir_incident_documents
            WHERE incident_id = $1
            ORDER BY created_at DESC
            """,
            str(incident_id),
        )

        return [
            IRDocumentResponse(
                id=row["id"],
                incident_id=row["incident_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                uploaded_by=row["uploaded_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.delete("/{incident_id}/documents/{document_id}")
async def delete_document(
    incident_id: UUID,
    document_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Delete a document from an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Document not found")
    company_clause = "i.company_id = $3"

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""SELECT d.id, d.filename, d.file_path
                FROM ir_incident_documents d
                JOIN ir_incidents i ON d.incident_id = i.id
                WHERE d.id = $1 AND d.incident_id = $2 AND {company_clause}""",
            str(document_id),
            str(incident_id),
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete from storage
        try:
            storage = get_storage()
            storage.delete_file(row["file_path"])
        except Exception:
            pass  # Continue even if storage delete fails

        # Delete from database
        await conn.execute(
            "DELETE FROM ir_incident_documents WHERE id = $1",
            str(document_id),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "document_deleted",
            "document",
            str(document_id),
            {"filename": row["filename"]},
            request.client.host if request.client else None,
        )

        return {"message": "Document deleted successfully"}


# ===========================================
# Analytics
# ===========================================

@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    current_user=Depends(require_admin_or_client),
):
    """Get summary analytics for the dashboard."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return AnalyticsSummary(total_incidents=0, by_status={}, by_type={}, by_severity={}, recent_count=0, avg_resolution_days=None)
    co_filter = "company_id = $1"

    async with get_connection() as conn:
        # Total incidents
        total = await conn.fetchval(f"SELECT COUNT(*) FROM ir_incidents WHERE {co_filter}", company_id)

        # By status
        status_rows = await conn.fetch(
            f"SELECT status, COUNT(*) as count FROM ir_incidents WHERE {co_filter} GROUP BY status", company_id
        )
        by_status = {row["status"]: row["count"] for row in status_rows}

        # By type
        type_rows = await conn.fetch(
            f"SELECT incident_type, COUNT(*) as count FROM ir_incidents WHERE {co_filter} GROUP BY incident_type", company_id
        )
        by_type = {row["incident_type"]: row["count"] for row in type_rows}

        # By severity
        severity_rows = await conn.fetch(
            f"SELECT severity, COUNT(*) as count FROM ir_incidents WHERE {co_filter} GROUP BY severity", company_id
        )
        by_severity = {row["severity"]: row["count"] for row in severity_rows}

        # Recent (last 30 days)
        thirty_days_ago = _utc_now_naive() - timedelta(days=30)
        recent_count = await conn.fetchval(
            f"SELECT COUNT(*) FROM ir_incidents WHERE {co_filter} AND occurred_at >= $2",
            company_id,
            thirty_days_ago,
        )

        # Average resolution time (days) for resolved/closed incidents
        avg_resolution = await conn.fetchval(
            f"""
            SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - occurred_at)) / 86400)
            FROM ir_incidents
            WHERE {co_filter} AND resolved_at IS NOT NULL
            """,
            company_id,
        )

        return AnalyticsSummary(
            total_incidents=total or 0,
            by_status=by_status,
            by_type=by_type,
            by_severity=by_severity,
            recent_count=recent_count or 0,
            avg_resolution_days=round(avg_resolution, 1) if avg_resolution else None,
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
                incident_type
            FROM ir_incidents
            WHERE {co_filter} AND occurred_at >= $1
            GROUP BY period_start, incident_type
            ORDER BY period_start
            """,
            start_date,
            company_id,
        )

        # Aggregate by period
        data_map = {}
        for row in rows:
            date_str = row["period_start"].strftime("%Y-%m-%d")
            if date_str not in data_map:
                data_map[date_str] = {"count": 0, "by_type": {}}
            data_map[date_str]["count"] += row["count"]
            data_map[date_str]["by_type"][row["incident_type"]] = row["count"]

        data = [
            TrendDataPoint(date=date, count=info["count"], by_type=info["by_type"])
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
    """Get incident hotspots by location."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return LocationAnalysis(hotspots=[], total_locations=0)
    co_filter = "company_id = $1"

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                location,
                COUNT(*) as count,
                incident_type,
                AVG(CASE
                    WHEN severity = 'critical' THEN 4
                    WHEN severity = 'high' THEN 3
                    WHEN severity = 'medium' THEN 2
                    ELSE 1
                END) as severity_score
            FROM ir_incidents
            WHERE {co_filter} AND location IS NOT NULL AND location != ''
            GROUP BY location, incident_type
            ORDER BY count DESC
            """,
            company_id,
        )

        # Aggregate by location
        location_map = {}
        for row in rows:
            loc = row["location"]
            if loc not in location_map:
                location_map[loc] = {"count": 0, "by_type": {}, "severity_scores": []}
            location_map[loc]["count"] += row["count"]
            location_map[loc]["by_type"][row["incident_type"]] = row["count"]
            location_map[loc]["severity_scores"].append(row["severity_score"])

        # Sort by count and limit
        sorted_locations = sorted(location_map.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]

        hotspots = [
            LocationHotspot(
                location=loc,
                count=info["count"],
                by_type=info["by_type"],
                avg_severity_score=round(sum(info["severity_scores"]) / len(info["severity_scores"]), 2),
            )
            for loc, info in sorted_locations
        ]

        return LocationAnalysis(
            hotspots=hotspots,
            total_locations=len(location_map),
        )


@router.get("/analytics/consistency", response_model=ConsistencyAnalytics)
async def get_analytics_consistency(
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Get company-wide consistency analytics across all resolved incidents."""
    from ..services.ir_consistency import compute_consistency_analytics

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
# Audit Log
# ===========================================

@router.get("/{incident_id}/audit-log", response_model=IRAuditLogResponse)
async def get_audit_log(
    incident_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_admin_or_client),
):
    """Get the audit log for an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = "company_id = $2"

    async with get_connection() as conn:
        # Verify incident exists and belongs to company
        incident = await conn.fetchrow(
            f"SELECT id FROM ir_incidents WHERE id = $1 AND {company_clause}",
            str(incident_id),
            company_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM ir_audit_log WHERE incident_id = $1",
            str(incident_id),
        )

        rows = await conn.fetch(
            """
            SELECT * FROM ir_audit_log
            WHERE incident_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            str(incident_id),
            limit,
            offset,
        )

        entries = [
            IRAuditLogEntry(
                id=row["id"],
                incident_id=row["incident_id"],
                user_id=row["user_id"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                details=json.loads(row["details"]) if row["details"] else None,
                ip_address=row["ip_address"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return IRAuditLogResponse(entries=entries, total=total or 0)


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
    from ..services.ir_analysis import get_ir_analyzer, IRAnalysisError

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
    from ..services.ir_analysis import get_ir_analyzer, IRAnalysisError

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
    from ..services.ir_analysis import get_ir_analyzer, IRAnalysisError

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
    from ..services.ir_analysis import get_ir_analyzer, IRAnalysisError
    from ..models.ir_incident import RecommendationItem

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
    from ..services.ir_precedent import find_precedents_stream

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
        from ..services.ir_analysis import get_ir_analyzer

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
    from ..services.ir_analysis import get_ir_analyzer

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
    from ..services.ir_consistency import compute_outcome_distribution

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



@router.put("/{incident_id}/osha")
async def update_osha_recordability(
    incident_id: UUID,
    update: OshaRecordabilityUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Set OSHA recordability determination for an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    if update.osha_classification and update.osha_classification not in VALID_OSHA_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OSHA classification. Must be one of: {', '.join(sorted(VALID_OSHA_CLASSIFICATIONS))}",
        )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM ir_incidents WHERE id = $1 AND company_id = $2",
            str(incident_id), company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        sets = ["osha_recordable = $3"]
        params = [str(incident_id), company_id, update.osha_recordable]
        idx = 4

        if update.osha_classification is not None:
            sets.append(f"osha_classification = ${idx}")
            params.append(update.osha_classification)
            idx += 1
        if update.osha_case_number is not None:
            sets.append(f"osha_case_number = ${idx}")
            params.append(update.osha_case_number)
            idx += 1
        if update.days_away_from_work is not None:
            sets.append(f"days_away_from_work = ${idx}")
            params.append(update.days_away_from_work)
            idx += 1
        if update.days_restricted_duty is not None:
            sets.append(f"days_restricted_duty = ${idx}")
            params.append(update.days_restricted_duty)
            idx += 1

        updated = await conn.fetchrow(
            f"UPDATE ir_incidents SET {', '.join(sets)} WHERE id = $1 AND company_id = $2 RETURNING *",
            *params,
        )
        return {"message": "OSHA recordability updated", "id": str(updated["id"])}


@router.post("/{incident_id}/osha/determine")
async def osha_ai_determination(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """AI-assisted OSHA recordability determination using Gemini."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ir_incidents WHERE id = $1 AND company_id = $2",
            str(incident_id), company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        category_data = _safe_json_loads(row.get("category_data"), {})

        prompt = f"""Analyze this workplace incident for OSHA recordability.

Incident: {row['title']}
Description: {row['description']}
Type: {row['incident_type']}
Severity: {row['severity']}
Injury type: {category_data.get('injury_type', 'unknown')}
Body parts: {category_data.get('body_parts', [])}
Treatment: {category_data.get('treatment', 'unknown')}
Lost days: {category_data.get('lost_days', 0)}

OSHA recordability criteria (29 CFR 1904):
- Death
- Days away from work
- Restricted work or transfer to another job
- Medical treatment beyond first aid
- Loss of consciousness
- Significant injury or illness diagnosed by a physician

Respond in JSON:
{{"recordable": true/false, "classification": "death|days_away|restricted_duty|medical_treatment|loss_of_consciousness|significant_injury|not_recordable", "reasoning": "brief explanation"}}
"""

        settings = get_settings()
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = await asyncio.to_thread(
                model.generate_content, prompt
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(text)
        except Exception as e:
            logger.error("OSHA AI determination failed: %s", e)
            raise HTTPException(status_code=500, detail="AI determination failed")

        return {
            "incident_id": str(incident_id),
            "recordable": result.get("recordable", False),
            "classification": result.get("classification", "not_recordable"),
            "reasoning": result.get("reasoning", ""),
        }


# ===========================================
# Investigation Interview Endpoints
# ===========================================

@router.post("/{incident_id}/investigation-interviews", response_model=InvestigationInterviewStart)
async def create_investigation_interview(
    incident_id: UUID,
    request_body: InvestigationInterviewCreate,
    current_user=Depends(require_admin_or_client),
):
    """Create an investigation interview for an IR incident.

    Generates questions, creates interview + junction row, returns ws_auth_token.
    """
    from ..services.ir_interview_questions import generate_investigation_questions
    from ...core.services.auth import create_interview_ws_token

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Validate incident exists and is in an appropriate status
        incident = await conn.fetchrow(
            """
            SELECT id, title, description, incident_type, severity, status, location,
                   occurred_at, witnesses, company_id
            FROM ir_incidents WHERE id = $1
            """,
            incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Company access check
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        if incident["status"] not in ("investigating", "action_required", "reported"):
            raise HTTPException(
                status_code=400,
                detail=f"Incident must be in investigating, action_required, or reported status (current: {incident['status']})",
            )

        # Fetch prior transcripts for context-aware question generation
        prior_transcripts = []
        prior_rows = await conn.fetch(
            """
            SELECT i.transcript
            FROM ir_investigation_interviews irii
            JOIN interviews i ON irii.interview_id = i.id
            WHERE irii.incident_id = $1 AND i.transcript IS NOT NULL
            ORDER BY irii.created_at
            """,
            incident_id,
        )
        prior_transcripts = [r["transcript"] for r in prior_rows]

        # Generate questions
        settings = get_settings()
        incident_data = {
            "title": incident["title"],
            "description": incident["description"],
            "incident_type": incident["incident_type"],
            "severity": incident["severity"],
            "location": incident["location"],
            "occurred_at": str(incident["occurred_at"]) if incident["occurred_at"] else None,
        }
        questions = await generate_investigation_questions(
            incident=incident_data,
            interviewee_name=request_body.interviewee_name,
            interviewee_role=request_body.interviewee_role,
            prior_transcripts=prior_transcripts if prior_transcripts else None,
            api_key=settings.gemini_api_key,
            vertex_project=settings.vertex_project,
            vertex_location=settings.vertex_location,
            model=settings.analysis_model,
        )

        # Create interview + junction row atomically
        async with conn.transaction():
            interview_row = await conn.fetchrow(
                """
                INSERT INTO interviews (company_id, interview_type, incident_id, er_case_id, interviewee_role, status)
                VALUES ($1, 'investigation', $2, $3, $4, 'pending')
                RETURNING id
                """,
                incident["company_id"],
                incident_id,
                request_body.er_case_id,
                request_body.interviewee_role,
            )
            interview_id = interview_row["id"]

            junction_row = await conn.fetchrow(
                """
                INSERT INTO ir_investigation_interviews
                    (incident_id, interview_id, er_case_id, interviewee_role, interviewee_name, interviewee_email, questions_generated, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
                RETURNING id
                """,
                incident_id,
                interview_id,
                request_body.er_case_id,
                request_body.interviewee_role,
                request_body.interviewee_name,
                request_body.interviewee_email,
                json.dumps(questions),
            )

            # Audit log inside transaction
            await log_audit(
                conn, incident_id, current_user.id,
                "investigation_interview_created", "investigation_interview",
                junction_row["id"],
                {"interviewee_name": request_body.interviewee_name, "interviewee_role": request_body.interviewee_role},
            )

        # Send invite email if requested
        invite_sent = False
        if request_body.send_invite and request_body.interviewee_email:
            invite_token = secrets.token_urlsafe(32)
            await conn.execute(
                """
                UPDATE ir_investigation_interviews
                SET invite_token = $1, invite_sent_at = NOW()
                WHERE id = $2
                """,
                invite_token, junction_row["id"],
            )
            try:
                company_row = await conn.fetchrow(
                    "SELECT name FROM companies WHERE id = $1", incident["company_id"]
                )
                company_name = company_row["name"] if company_row else "Your Company"
                email_service = get_email_service()
                await email_service.send_investigation_interview_invite_email(
                    to_email=request_body.interviewee_email,
                    to_name=request_body.interviewee_name,
                    company_name=company_name,
                    interviewee_role=request_body.interviewee_role,
                    invite_token=invite_token,
                    custom_message=request_body.custom_message,
                )
                invite_sent = True
            except Exception as e:
                logging.getLogger(__name__).warning("Failed to send investigation invite email: %s", e)

        # Generate WS auth token (outside transaction — stateless JWT creation)
        ws_token = create_interview_ws_token(interview_id)

        return InvestigationInterviewStart(
            investigation_interview_id=junction_row["id"],
            interview_id=interview_id,
            websocket_url=f"/api/ws/interview/{interview_id}",
            ws_auth_token=ws_token,
            questions_generated=questions,
            invite_sent=invite_sent,
        )


@router.post("/{incident_id}/investigation-interviews/batch")
async def batch_create_investigation_interviews(
    incident_id: UUID,
    request_body: list[InvestigationInterviewCreate],
    current_user=Depends(require_admin_or_client),
):
    """Batch-create investigation interviews for an IR incident (max 20).

    Returns a summary of created/failed interviews.
    """
    from ..services.ir_interview_questions import generate_investigation_questions
    from ...core.services.auth import create_interview_ws_token

    if len(request_body) == 0:
        raise HTTPException(status_code=400, detail="At least one interview must be provided")
    if len(request_body) > 20:
        raise HTTPException(status_code=400, detail="Cannot create more than 20 interviews at once")

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Validate incident once
        incident = await conn.fetchrow(
            """
            SELECT id, title, description, incident_type, severity, status, location,
                   occurred_at, witnesses, company_id
            FROM ir_incidents WHERE id = $1
            """,
            incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        if incident["status"] not in ("investigating", "action_required", "reported"):
            raise HTTPException(
                status_code=400,
                detail=f"Incident must be in investigating, action_required, or reported status (current: {incident['status']})",
            )

        # Fetch prior transcripts once for context-aware question generation
        prior_rows = await conn.fetch(
            """
            SELECT i.transcript
            FROM ir_investigation_interviews irii
            JOIN interviews i ON irii.interview_id = i.id
            WHERE irii.incident_id = $1 AND i.transcript IS NOT NULL
            ORDER BY irii.created_at
            """,
            incident_id,
        )
        prior_transcripts = [r["transcript"] for r in prior_rows]

        # Fetch existing non-cancelled emails for this incident to detect duplicates
        existing_email_rows = await conn.fetch(
            """
            SELECT interviewee_email FROM ir_investigation_interviews
            WHERE incident_id = $1 AND status != 'cancelled' AND interviewee_email IS NOT NULL
            """,
            incident_id,
        )
        existing_emails = {r["interviewee_email"].lower() for r in existing_email_rows}

        # Fetch company name once for invite emails
        company_row = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", incident["company_id"]
        )
        company_name = company_row["name"] if company_row else "Your Company"

        settings = get_settings()
        incident_data = {
            "title": incident["title"],
            "description": incident["description"],
            "incident_type": incident["incident_type"],
            "severity": incident["severity"],
            "location": incident["location"],
            "occurred_at": str(incident["occurred_at"]) if incident["occurred_at"] else None,
        }

        created = []
        failed = []
        # Track emails added in this batch to catch intra-batch duplicates
        seen_emails_this_batch: set[str] = set()

        for item in request_body:
            # Duplicate email check
            if item.interviewee_email:
                email_lower = item.interviewee_email.lower()
                if email_lower in existing_emails or email_lower in seen_emails_this_batch:
                    failed.append({
                        "interviewee_name": item.interviewee_name,
                        "interviewee_email": item.interviewee_email,
                        "error": "An active investigation interview already exists for this email address",
                    })
                    continue
                seen_emails_this_batch.add(email_lower)

            try:
                questions = await generate_investigation_questions(
                    incident=incident_data,
                    interviewee_name=item.interviewee_name,
                    interviewee_role=item.interviewee_role,
                    prior_transcripts=prior_transcripts if prior_transcripts else None,
                    api_key=settings.gemini_api_key,
                    vertex_project=settings.vertex_project,
                    vertex_location=settings.vertex_location,
                    model=settings.analysis_model,
                )

                async with conn.transaction():
                    interview_row = await conn.fetchrow(
                        """
                        INSERT INTO interviews (company_id, interview_type, incident_id, er_case_id, interviewee_role, status)
                        VALUES ($1, 'investigation', $2, $3, $4, 'pending')
                        RETURNING id
                        """,
                        incident["company_id"],
                        incident_id,
                        item.er_case_id,
                        item.interviewee_role,
                    )
                    interview_id = interview_row["id"]

                    junction_row = await conn.fetchrow(
                        """
                        INSERT INTO ir_investigation_interviews
                            (incident_id, interview_id, er_case_id, interviewee_role, interviewee_name, interviewee_email, questions_generated, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
                        RETURNING id
                        """,
                        incident_id,
                        interview_id,
                        item.er_case_id,
                        item.interviewee_role,
                        item.interviewee_name,
                        item.interviewee_email,
                        json.dumps(questions),
                    )

                    await log_audit(
                        conn, incident_id, current_user.id,
                        "investigation_interview_created", "investigation_interview",
                        junction_row["id"],
                        {"interviewee_name": item.interviewee_name, "interviewee_role": item.interviewee_role},
                    )

                ws_token = create_interview_ws_token(interview_id)

                # Send invite email if requested
                invite_sent = False
                if item.send_invite and item.interviewee_email:
                    invite_token = secrets.token_urlsafe(32)
                    await conn.execute(
                        """
                        UPDATE ir_investigation_interviews
                        SET invite_token = $1, invite_sent_at = NOW()
                        WHERE id = $2
                        """,
                        invite_token, junction_row["id"],
                    )
                    try:
                        email_service = get_email_service()
                        await email_service.send_investigation_interview_invite_email(
                            to_email=item.interviewee_email,
                            to_name=item.interviewee_name,
                            company_name=company_name,
                            interviewee_role=item.interviewee_role,
                            invite_token=invite_token,
                            custom_message=item.custom_message,
                        )
                        invite_sent = True
                    except Exception as e:
                        logging.getLogger(__name__).warning("Failed to send investigation invite email: %s", e)

                created.append({
                    "investigation_interview_id": str(junction_row["id"]),
                    "interview_id": str(interview_id),
                    "interviewee_name": item.interviewee_name,
                    "interviewee_email": item.interviewee_email,
                    "websocket_url": f"/api/ws/interview/{interview_id}",
                    "ws_auth_token": ws_token,
                    "questions_generated": questions,
                    "invite_sent": invite_sent,
                })

            except HTTPException:
                raise
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "Failed to create investigation interview for %s: %s", item.interviewee_name, e
                )
                failed.append({
                    "interviewee_name": item.interviewee_name,
                    "interviewee_email": item.interviewee_email,
                    "error": str(e),
                })

        return {
            "created": len(created),
            "failed": len(failed),
            "interviews": created,
            "errors": failed,
        }


@router.post("/{incident_id}/investigation-interviews/{investigation_interview_id}/resend-invite")
async def resend_investigation_interview_invite(
    incident_id: UUID,
    investigation_interview_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Resend an investigation interview invite email."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id, company_id FROM ir_incidents WHERE id = $1", incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        row = await conn.fetchrow(
            """
            SELECT id, status, interviewee_email, interviewee_name, interviewee_role,
                   invite_token, er_case_id
            FROM ir_investigation_interviews
            WHERE id = $1 AND incident_id = $2
            """,
            investigation_interview_id, incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Investigation interview not found")

        if not row["interviewee_email"]:
            raise HTTPException(status_code=400, detail="No email address on file for this interviewee")

        if row["status"] not in ("pending", "in_progress"):
            raise HTTPException(
                status_code=400,
                detail=f"Invite can only be resent for pending or in_progress interviews (current: {row['status']})",
            )

        # Reuse existing token or generate a new one
        invite_token = row["invite_token"]
        if not invite_token:
            invite_token = secrets.token_urlsafe(32)
            await conn.execute(
                "UPDATE ir_investigation_interviews SET invite_token = $1 WHERE id = $2",
                invite_token, investigation_interview_id,
            )

        await conn.execute(
            "UPDATE ir_investigation_interviews SET invite_sent_at = NOW() WHERE id = $1",
            investigation_interview_id,
        )

        company_row = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", incident["company_id"]
        )
        company_name = company_row["name"] if company_row else "Your Company"

        try:
            email_service = get_email_service()
            await email_service.send_investigation_interview_invite_email(
                to_email=row["interviewee_email"],
                to_name=row["interviewee_name"],
                company_name=company_name,
                interviewee_role=row["interviewee_role"],
                invite_token=invite_token,
                custom_message=None,
            )
        except Exception as e:
            logger.warning("Failed to resend investigation invite email: %s", e)
            raise HTTPException(status_code=502, detail="Failed to send invite email")

        await log_audit(
            conn, incident_id, current_user.id,
            "investigation_interview_invite_resent", "investigation_interview",
            investigation_interview_id,
            {"interviewee_email": row["interviewee_email"]},
        )

        return {"status": "sent"}


@router.post("/{incident_id}/investigation-interviews/{investigation_interview_id}/generate-link")
async def generate_investigation_interview_link(
    incident_id: UUID,
    investigation_interview_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Generate (or retrieve) an invite link for an investigation interview.

    Ensures a token exists without sending an email, so admins can copy and
    share the link directly (e.g. via Slack, in-person, etc.).
    """
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id, company_id FROM ir_incidents WHERE id = $1", incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        row = await conn.fetchrow(
            """
            SELECT id, status, invite_token
            FROM ir_investigation_interviews
            WHERE id = $1 AND incident_id = $2
            """,
            investigation_interview_id, incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Investigation interview not found")

        if row["status"] in ("cancelled", "completed", "analyzed"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot generate link for {row['status']} interview",
            )

        invite_token = row["invite_token"]
        if not invite_token:
            invite_token = secrets.token_urlsafe(32)
            await conn.execute(
                "UPDATE ir_investigation_interviews SET invite_token = $1 WHERE id = $2",
                invite_token, investigation_interview_id,
            )

        return {"invite_token": invite_token}


@router.get("/{incident_id}/investigation-interviews", response_model=list[InvestigationInterviewResponse])
async def list_investigation_interviews(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """List investigation interviews for an IR incident."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id, company_id FROM ir_incidents WHERE id = $1", incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        rows = await conn.fetch(
            """
            SELECT irii.id, irii.incident_id, irii.interview_id, irii.er_case_id,
                   irii.interviewee_role, irii.interviewee_name, irii.interviewee_email,
                   irii.questions_generated, irii.status, irii.created_at, irii.completed_at,
                   irii.invite_token, irii.invite_sent_at,
                   i.transcript IS NOT NULL as has_transcript,
                   i.investigation_analysis
            FROM ir_investigation_interviews irii
            JOIN interviews i ON irii.interview_id = i.id
            WHERE irii.incident_id = $1
            ORDER BY irii.created_at DESC
            """,
            incident_id,
        )

        results = []
        for row in rows:
            analysis = row["investigation_analysis"]
            if isinstance(analysis, str):
                analysis = json.loads(analysis)
            questions = row["questions_generated"]
            if isinstance(questions, str):
                questions = json.loads(questions)
            results.append(InvestigationInterviewResponse(
                id=row["id"],
                incident_id=row["incident_id"],
                interview_id=row["interview_id"],
                er_case_id=row["er_case_id"],
                interviewee_role=row["interviewee_role"],
                interviewee_name=row["interviewee_name"],
                interviewee_email=row["interviewee_email"],
                questions_generated=questions,
                status=row["status"],
                has_transcript=row["has_transcript"],
                investigation_analysis=analysis,
                invite_token=row["invite_token"],
                invite_sent_at=row["invite_sent_at"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            ))
        return results


@router.delete("/{incident_id}/investigation-interviews/{investigation_interview_id}")
async def cancel_investigation_interview(
    incident_id: UUID,
    investigation_interview_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Cancel a pending investigation interview."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id, company_id FROM ir_incidents WHERE id = $1", incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        row = await conn.fetchrow(
            """
            SELECT id, status FROM ir_investigation_interviews
            WHERE id = $1 AND incident_id = $2
            """,
            investigation_interview_id, incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Investigation interview not found")
        if row["status"] not in ("pending",):
            raise HTTPException(status_code=400, detail="Only pending interviews can be cancelled")

        await conn.execute(
            "UPDATE ir_investigation_interviews SET status = 'cancelled' WHERE id = $1",
            investigation_interview_id,
        )
        await conn.execute(
            "UPDATE interviews SET status = 'cancelled' WHERE id = (SELECT interview_id FROM ir_investigation_interviews WHERE id = $1)",
            investigation_interview_id,
        )

        await log_audit(
            conn, incident_id, current_user.id,
            "investigation_interview_cancelled", "investigation_interview",
            investigation_interview_id, {},
        )

        return {"status": "cancelled"}


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
