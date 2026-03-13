"""Dashboard stats endpoint — returns company-scoped metrics."""

import logging
from datetime import date, datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


class PendingIncident(BaseModel):
    id: UUID
    incident_number: str
    title: str
    severity: str


class ActivityItem(BaseModel):
    action: str
    timestamp: datetime
    type: str  # 'success' | 'warning' | 'neutral'


class IncidentSummary(BaseModel):
    total_open: int
    critical: int
    high: int
    medium: int
    low: int
    recent_7_days: int


class WageAlertSummary(BaseModel):
    hourly_violations: int
    salary_violations: int
    locations_affected: int


class DashboardStats(BaseModel):
    active_policies: int
    pending_signatures: int
    total_employees: int
    compliance_rate: float
    pending_incidents: List[PendingIncident]
    recent_activity: List[ActivityItem]
    incident_summary: Optional[IncidentSummary] = None
    wage_alerts: Optional[WageAlertSummary] = None


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get dashboard stats scoped to the user's company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return DashboardStats(
            active_policies=0,
            pending_signatures=0,
            total_employees=0,
            compliance_rate=0.0,
            pending_incidents=[],
            recent_activity=[],
        )

    async with get_connection() as conn:
        # Active policies
        active_policies = await conn.fetchval(
            "SELECT COUNT(*) FROM policies WHERE company_id = $1 AND status = 'active'",
            company_id,
        ) or 0

        # Pending signatures
        pending_signatures = await conn.fetchval(
            """SELECT COUNT(*) FROM policy_signatures ps
               JOIN policies p ON ps.policy_id = p.id
               WHERE p.company_id = $1 AND ps.status = 'pending'""",
            company_id,
        ) or 0

        # Total employees (active only)
        total_employees = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
            company_id,
        ) or 0

        # Compliance rate: signed / total signatures for active policies
        sig_stats = await conn.fetchrow(
            """SELECT
                 COUNT(*) FILTER (WHERE ps.status = 'signed') AS signed_count,
                 COUNT(*) AS total_count
               FROM policy_signatures ps
               JOIN policies p ON ps.policy_id = p.id
               WHERE p.company_id = $1 AND p.status = 'active'""",
            company_id,
        )
        if sig_stats and sig_stats["total_count"] > 0:
            compliance_rate = round(
                (sig_stats["signed_count"] / sig_stats["total_count"]) * 100, 1
            )
        else:
            compliance_rate = 0.0

        # Pending incidents (reported, investigating, or action_required)
        incident_rows = await conn.fetch(
            """SELECT id, incident_number, title, severity
               FROM ir_incidents
               WHERE company_id = $1 AND status IN ('reported', 'investigating', 'action_required')
               ORDER BY occurred_at DESC
               LIMIT 5""",
            company_id,
        )
        pending_incidents = [
            PendingIncident(
                id=row["id"],
                incident_number=row["incident_number"],
                title=row["title"],
                severity=row["severity"] or "medium",
            )
            for row in incident_rows
        ]

        # Incident summary (open incidents by severity + recent 7 days)
        ir_severity_rows = await conn.fetch(
            """SELECT severity, COUNT(*) AS cnt
               FROM ir_incidents
               WHERE company_id = $1 AND status IN ('reported', 'investigating', 'action_required')
               GROUP BY severity""",
            company_id,
        )
        severity_map = {row["severity"]: row["cnt"] for row in ir_severity_rows}
        total_open = sum(severity_map.values())

        recent_7_days = await conn.fetchval(
            """SELECT COUNT(*) FROM ir_incidents
               WHERE company_id = $1 AND created_at >= NOW() - INTERVAL '7 days'""",
            company_id,
        ) or 0

        incident_summary = IncidentSummary(
            total_open=total_open,
            critical=severity_map.get("critical", 0),
            high=severity_map.get("high", 0),
            medium=severity_map.get("medium", 0),
            low=severity_map.get("low", 0),
            recent_7_days=recent_7_days,
        )

        # Recent activity from audit log
        activity_rows = await conn.fetch(
            """SELECT al.action, al.created_at, al.details
               FROM ir_audit_log al
               JOIN ir_incidents i ON al.incident_id = i.id
               WHERE i.company_id = $1
               ORDER BY al.created_at DESC
               LIMIT 10""",
            company_id,
        )
        recent_activity = []
        for row in activity_rows:
            action_type = "neutral"
            action_str = row["action"]
            if "resolved" in action_str or "closed" in action_str:
                action_type = "success"
            elif "created" in action_str or "flagged" in action_str:
                action_type = "warning"
            recent_activity.append(
                ActivityItem(
                    action=_format_action(action_str, row["details"]),
                    timestamp=row["created_at"],
                    type=action_type,
                )
            )

    # Employee wage violation alerts across all locations
    wage_alerts = None
    try:
        from ...core.services.compliance_service import get_employee_impact_for_location

        async with get_connection() as conn2:
            location_ids = await conn2.fetch(
                "SELECT id FROM business_locations WHERE company_id = $1 AND is_active = true",
                company_id,
            )
        hourly_violations = 0
        salary_violations = 0
        locations_affected = 0
        for loc_row in location_ids:
            impact = await get_employee_impact_for_location(loc_row["id"], company_id)
            vbt = impact.get("violations_by_rate_type", {})
            h = len(vbt.get("general", []))
            s = len(vbt.get("exempt_salary", []))
            hourly_violations += h
            salary_violations += s
            if h or s:
                locations_affected += 1
        if hourly_violations or salary_violations:
            wage_alerts = WageAlertSummary(
                hourly_violations=hourly_violations,
                salary_violations=salary_violations,
                locations_affected=locations_affected,
            )
    except Exception:
        logger.exception("Failed to compute wage alerts for dashboard")

    return DashboardStats(
        active_policies=active_policies,
        pending_signatures=pending_signatures,
        total_employees=total_employees,
        compliance_rate=compliance_rate,
        pending_incidents=pending_incidents,
        recent_activity=recent_activity,
        incident_summary=incident_summary,
        wage_alerts=wage_alerts,
    )


def _format_action(action: str, details: dict | None) -> str:
    """Format an audit log action into a human-readable string."""
    labels = {
        "incident_created": "New incident report created",
        "incident_updated": "Incident report updated",
        "status_changed": "Incident status changed",
        "note_added": "Note added to incident",
        "document_uploaded": "Document uploaded to incident",
        "analysis_generated": "AI analysis generated for incident",
    }
    base = labels.get(action, action.replace("_", " ").title())
    if details and isinstance(details, dict):
        title = details.get("title") or details.get("incident_number")
        if title:
            base = f"{base}: {title}"
    return base


# ---------------------------------------------------------------------------
# Client notifications / activity feed
# ---------------------------------------------------------------------------


class ClientNotification(BaseModel):
    id: str
    type: str  # "incident", "employee", "offer_letter", "er_case", "handbook", "compliance_alert"
    title: str
    subtitle: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    created_at: datetime
    link: Optional[str] = None


class ClientNotificationsResponse(BaseModel):
    items: list[ClientNotification]
    total: int


_CLIENT_NOTIFICATION_LINK_MAP: dict[str, str] = {
    "incident": "/app/ir/incidents/{id}",
    "employee": "/app/matcha/employees/{id}",
    "offer_letter": "/app/matcha/offer-letters",
    "er_case": "/app/matcha/er-copilot/{id}",
    "handbook": "/app/matcha/handbook/{id}",
    "compliance_alert": "/app/matcha/compliance",
    "credential_expiry": "/app/matcha/employees",
}

# Each sub-query is parameterized with $1 = company_id.
_CLIENT_NOTIFICATION_SUBQUERIES: list[str] = [
    # Incidents
    """SELECT id::text, 'incident' AS type,
            title, incident_number AS subtitle,
            severity, status, created_at
       FROM ir_incidents
       WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'""",
    # Employees
    """SELECT e.id::text, 'employee' AS type,
            e.first_name || ' ' || e.last_name AS title,
            e.job_title AS subtitle,
            NULL AS severity, 'onboarded' AS status, e.created_at
       FROM employees e
       WHERE e.org_id = $1 AND e.created_at > NOW() - INTERVAL '30 days'""",
    # Offer letters
    """SELECT id::text, 'offer_letter' AS type,
            candidate_name || ' - ' || position_title AS title,
            status AS subtitle,
            NULL AS severity, status, created_at
       FROM offer_letters
       WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'""",
    # ER cases
    """SELECT id::text, 'er_case' AS type,
            title, case_number AS subtitle,
            NULL AS severity, status, created_at
       FROM er_cases
       WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'""",
    # Handbooks
    """SELECT id::text, 'handbook' AS type,
            title, status AS subtitle,
            NULL AS severity, status, created_at
       FROM handbooks
       WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'""",
    # Compliance alerts — only material changes with sufficient confidence
    """SELECT id::text, 'compliance_alert' AS type,
            title, message AS subtitle,
            severity, status, created_at
       FROM compliance_alerts
       WHERE company_id = $1
         AND created_at > NOW() - INTERVAL '30 days'
         AND alert_type = 'change'
         AND COALESCE(confidence_score, 1.0) >= 0.6""",
    # Credential expirations — healthcare employee licenses expiring within 90 days
    """SELECT ec.id::text, 'credential_expiry' AS type,
            e.first_name || ' ' || e.last_name || ' — ' || x.label AS title,
            'Expires ' || to_char(x.expiry_date, 'Mon DD, YYYY') AS subtitle,
            CASE WHEN x.expiry_date < CURRENT_DATE THEN 'expired'
                 WHEN x.expiry_date <= CURRENT_DATE + INTERVAL '30 days' THEN 'critical'
                 ELSE 'warning' END AS severity,
            CASE WHEN x.expiry_date < CURRENT_DATE THEN 'expired' ELSE 'expiring' END AS status,
            ec.updated_at AS created_at
       FROM employees e
       JOIN employee_credentials ec ON ec.employee_id = e.id
       CROSS JOIN LATERAL (VALUES
           ('Medical License',      ec.license_expiration),
           ('DEA Registration',     ec.dea_expiration),
           ('Board Certification',  ec.board_certification_expiration),
           ('Malpractice Insurance', ec.malpractice_expiration)
       ) AS x(label, expiry_date)
       WHERE e.org_id = $1
         AND e.termination_date IS NULL
         AND x.expiry_date IS NOT NULL
         AND x.expiry_date <= CURRENT_DATE + INTERVAL '90 days'""",
]


@router.get("/notifications", response_model=ClientNotificationsResponse)
async def get_client_notifications(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return a chronological activity feed of recent events for the client's company."""

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return ClientNotificationsResponse(items=[], total=0)

    async with get_connection() as conn:
        # Build UNION ALL dynamically, skipping tables that don't exist.
        valid_parts: list[str] = []
        for sq in _CLIENT_NOTIFICATION_SUBQUERIES:
            try:
                await conn.fetch(f"SELECT * FROM ({sq}) _probe LIMIT 0", company_id)
                valid_parts.append(sq)
            except asyncpg.UndefinedTableError:
                logger.debug("Skipping client notification subquery (table missing): %s", sq[:60])
            except asyncpg.UndefinedColumnError:
                logger.debug("Skipping client notification subquery (column missing): %s", sq[:60])

        if not valid_parts:
            return ClientNotificationsResponse(items=[], total=0)

        union_sql = " UNION ALL ".join(valid_parts)

        # Total count
        count_row = await conn.fetchrow(
            f"SELECT COUNT(*) AS total FROM ({union_sql}) AS _all",
            company_id,
        )
        total = count_row["total"] if count_row else 0

        # Paginated rows
        rows = await conn.fetch(
            f"""SELECT *
                FROM ({union_sql}) AS n
                ORDER BY n.created_at DESC
                LIMIT $2 OFFSET $3""",
            company_id,
            limit,
            offset,
        )

    items: list[ClientNotification] = []
    for row in rows:
        row_type = row["type"]
        row_id = row["id"]
        link_template = _CLIENT_NOTIFICATION_LINK_MAP.get(row_type, "")
        link = link_template.replace("{id}", row_id) if link_template else None

        items.append(
            ClientNotification(
                id=row_id,
                type=row_type,
                title=row["title"] or "",
                subtitle=row["subtitle"],
                severity=row["severity"],
                status=row["status"],
                created_at=row["created_at"],
                link=link,
            )
        )

    return ClientNotificationsResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# Credential expiration alerts (healthcare companies)
# ---------------------------------------------------------------------------

_CREDENTIAL_LABELS: dict[str, str] = {
    "medical_license": "Medical License",
    "dea_registration": "DEA Registration",
    "board_certification": "Board Certification",
    "malpractice_insurance": "Malpractice Insurance",
}


class CredentialExpiration(BaseModel):
    employee_id: str
    employee_name: str
    job_title: Optional[str] = None
    credential_type: str
    credential_label: str
    expiry_date: date
    severity: Literal["expired", "critical", "warning"]


class CredentialExpirationSummary(BaseModel):
    expired: int
    critical: int
    warning: int


class CredentialExpirationsResponse(BaseModel):
    summary: CredentialExpirationSummary
    expirations: list[CredentialExpiration]


def _classify_severity(expiry_date: date, today: date) -> str:
    days = (expiry_date - today).days
    if days < 0:
        return "expired"
    if days <= 30:
        return "critical"
    return "warning"


@router.get("/credential-expirations", response_model=CredentialExpirationsResponse)
async def get_credential_expirations(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return credentials expiring within 90 days (or already expired) for the company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return CredentialExpirationsResponse(
            summary=CredentialExpirationSummary(expired=0, critical=0, warning=0),
            expirations=[],
        )

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT e.id AS employee_id,
                   e.first_name || ' ' || e.last_name AS employee_name,
                   e.job_title,
                   x.credential_type,
                   x.expiry_date
            FROM employees e
            JOIN employee_credentials ec ON ec.employee_id = e.id
            CROSS JOIN LATERAL (VALUES
                ('medical_license',      ec.license_expiration),
                ('dea_registration',     ec.dea_expiration),
                ('board_certification',  ec.board_certification_expiration),
                ('malpractice_insurance', ec.malpractice_expiration)
            ) AS x(credential_type, expiry_date)
            WHERE e.org_id = $1
              AND e.termination_date IS NULL
              AND x.expiry_date IS NOT NULL
              AND x.expiry_date <= CURRENT_DATE + INTERVAL '90 days'
            ORDER BY x.expiry_date ASC
            """,
            company_id,
        )

    today = date.today()
    expired = 0
    critical = 0
    warning = 0
    expirations: list[CredentialExpiration] = []

    for row in rows:
        sev = _classify_severity(row["expiry_date"], today)
        if sev == "expired":
            expired += 1
        elif sev == "critical":
            critical += 1
        else:
            warning += 1

        expirations.append(
            CredentialExpiration(
                employee_id=str(row["employee_id"]),
                employee_name=row["employee_name"],
                job_title=row["job_title"],
                credential_type=row["credential_type"],
                credential_label=_CREDENTIAL_LABELS.get(row["credential_type"], row["credential_type"]),
                expiry_date=row["expiry_date"],
                severity=sev,
            )
        )

    return CredentialExpirationsResponse(
        summary=CredentialExpirationSummary(expired=expired, critical=critical, warning=warning),
        expirations=expirations,
    )
