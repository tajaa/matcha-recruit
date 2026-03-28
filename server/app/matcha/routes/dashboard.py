"""Dashboard stats endpoint — returns company-scoped metrics."""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser
from ...core.services.redis_cache import (
    get_redis_cache, cache_get, cache_set,
    dashboard_stats_key, dashboard_credentials_key,
    dashboard_upcoming_key, dashboard_notifications_key,
)


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


class ERCaseSummary(BaseModel):
    open_cases: int
    investigating: int
    pending_action: int


class StalePolicySummary(BaseModel):
    stale_count: int
    oldest_days: int


class DashboardStats(BaseModel):
    active_policies: int
    pending_signatures: int
    total_employees: int
    compliance_rate: float
    pending_incidents: List[PendingIncident]
    recent_activity: List[ActivityItem]
    incident_summary: Optional[IncidentSummary] = None
    wage_alerts: Optional[WageAlertSummary] = None
    # New HR-admin focused fields
    critical_compliance_alerts: int = 0
    warning_compliance_alerts: int = 0
    er_case_summary: Optional[ERCaseSummary] = None
    stale_policies: Optional[StalePolicySummary] = None
    escalated_queries_open: int = 0
    escalated_queries_high: int = 0


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

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, dashboard_stats_key(company_id))
        if cached is not None:
            return cached

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

    # Compliance alerts (critical + warning)
    critical_compliance_alerts = 0
    warning_compliance_alerts = 0
    try:
        async with get_connection() as conn3:
            alert_rows = await conn3.fetch(
                """SELECT severity, COUNT(*) AS cnt
                   FROM compliance_alerts
                   WHERE company_id = $1
                     AND status != 'dismissed'
                     AND COALESCE(confidence_score, 1.0) >= 0.6
                   GROUP BY severity""",
                company_id,
            )
            for row in alert_rows:
                if row["severity"] == "critical":
                    critical_compliance_alerts = row["cnt"]
                elif row["severity"] == "warning":
                    warning_compliance_alerts = row["cnt"]
    except Exception:
        logger.exception("Failed to fetch compliance alerts for dashboard")

    # ER Copilot open cases
    er_case_summary = None
    try:
        async with get_connection() as conn4:
            er_rows = await conn4.fetch(
                """SELECT status, COUNT(*) AS cnt
                   FROM er_cases
                   WHERE company_id = $1 AND status NOT IN ('closed', 'resolved')
                   GROUP BY status""",
                company_id,
            )
            if er_rows:
                total_open = sum(r["cnt"] for r in er_rows)
                status_map = {r["status"]: r["cnt"] for r in er_rows}
                er_case_summary = ERCaseSummary(
                    open_cases=total_open,
                    investigating=status_map.get("investigating", 0),
                    pending_action=status_map.get("action_required", 0) + status_map.get("pending", 0),
                )
    except Exception:
        logger.exception("Failed to fetch ER case summary for dashboard")

    # Stale policies (not updated in 180+ days)
    stale_policies = None
    try:
        async with get_connection() as conn5:
            stale_row = await conn5.fetchrow(
                """SELECT COUNT(*) AS cnt,
                          EXTRACT(DAY FROM NOW() - MIN(updated_at))::int AS oldest_days
                   FROM policies
                   WHERE company_id = $1
                     AND status = 'active'
                     AND updated_at < NOW() - INTERVAL '180 days'""",
                company_id,
            )
            if stale_row and stale_row["cnt"] > 0:
                stale_policies = StalePolicySummary(
                    stale_count=stale_row["cnt"],
                    oldest_days=stale_row["oldest_days"] or 0,
                )
    except Exception:
        logger.exception("Failed to fetch stale policies for dashboard")

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

    # Escalated Matcha Work queries
    escalated_queries_open = 0
    escalated_queries_high = 0
    try:
        async with get_connection() as conn6:
            esc_rows = await conn6.fetch(
                """SELECT severity, COUNT(*) AS cnt
                   FROM mw_escalated_queries
                   WHERE company_id = $1 AND status IN ('open', 'in_review')
                   GROUP BY severity""",
                company_id,
            )
            for row in esc_rows:
                escalated_queries_open += row["cnt"]
                if row["severity"] == "high":
                    escalated_queries_high = row["cnt"]
    except asyncpg.UndefinedTableError:
        pass  # table not yet migrated
    except Exception:
        logger.exception("Failed to fetch escalated queries for dashboard")

    result = DashboardStats(
        active_policies=active_policies,
        pending_signatures=pending_signatures,
        total_employees=total_employees,
        compliance_rate=compliance_rate,
        pending_incidents=pending_incidents,
        recent_activity=recent_activity,
        incident_summary=incident_summary,
        wage_alerts=wage_alerts,
        critical_compliance_alerts=critical_compliance_alerts,
        warning_compliance_alerts=warning_compliance_alerts,
        er_case_summary=er_case_summary,
        stale_policies=stale_policies,
        escalated_queries_open=escalated_queries_open,
        escalated_queries_high=escalated_queries_high,
    )

    if redis:
        await cache_set(redis, dashboard_stats_key(company_id), result.model_dump(), ttl=120)

    return result


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

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, dashboard_notifications_key(company_id, limit, offset))
        if cached is not None:
            return cached

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

    result = ClientNotificationsResponse(items=items, total=total)

    if redis:
        await cache_set(redis, dashboard_notifications_key(company_id, limit, offset), result.model_dump(), ttl=180)

    return result


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

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, dashboard_credentials_key(company_id))
        if cached is not None:
            return cached

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

    result = CredentialExpirationsResponse(
        summary=CredentialExpirationSummary(expired=expired, critical=critical, warning=warning),
        expirations=expirations,
    )

    if redis:
        await cache_set(redis, dashboard_credentials_key(company_id), result.model_dump(), ttl=300)

    return result


# ---------------------------------------------------------------------------
# Upcoming deadlines — unified cross-module deadline aggregation
# ---------------------------------------------------------------------------


class UpcomingItem(BaseModel):
    category: str  # compliance, credential, training, cobra, policy, ir, er, i9, separation, onboarding
    title: str
    subtitle: Optional[str] = None
    date: date
    days_until: int
    severity: str  # critical, warning, info
    link: str


class UpcomingResponse(BaseModel):
    items: list[UpcomingItem]
    total: int


def _severity_from_days(days: int, *, critical_threshold: int = 14) -> str:
    if days < 0:
        return "critical"
    if days <= critical_threshold:
        return "warning"
    return "info"


# Each source is a (category, sql, date_column_name, link_template) tuple.
# SQL must:
#   - accept $1 = company_id (or None for admin-all), $2 = lookahead date
#   - return: title, subtitle, deadline (date)
# link_template uses {id} placeholder.

_UPCOMING_SOURCES: list[dict] = [
    # Compliance alerts — only those with an explicit deadline (not effective_date,
    # which represents when a law takes effect, not when action is due)
    {
        "category": "compliance",
        "sql": """
            SELECT ca.id::text, ca.title,
                   ca.message AS subtitle,
                   ca.deadline::date AS deadline
            FROM compliance_alerts ca
            WHERE ({company_filter})
              AND ca.status != 'dismissed'
              AND ca.deadline IS NOT NULL
              AND ca.deadline::date <= $2
        """,
        "link": "/app/matcha/compliance",
    },
    # Credential expirations
    {
        "category": "credential",
        "sql": """
            SELECT ec.id::text,
                   e.first_name || ' ' || e.last_name || ' — ' || x.label AS title,
                   x.label AS subtitle,
                   x.expiry_date::date AS deadline
            FROM employees e
            JOIN employee_credentials ec ON ec.employee_id = e.id
            CROSS JOIN LATERAL (VALUES
                ('Medical License',      ec.license_expiration),
                ('DEA Registration',     ec.dea_expiration),
                ('Board Certification',  ec.board_certification_expiration),
                ('Malpractice Insurance', ec.malpractice_expiration)
            ) AS x(label, expiry_date)
            WHERE ({company_filter_emp})
              AND e.termination_date IS NULL
              AND x.expiry_date IS NOT NULL
              AND x.expiry_date::date <= $2
        """,
        "link": "/app/matcha/employees",
    },
    # Training due dates
    {
        "category": "training",
        "sql": """
            SELECT tr.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — ' || tr.course_name AS title,
                   tr.status AS subtitle,
                   tr.due_date::date AS deadline
            FROM training_records tr
            LEFT JOIN employees e ON e.id = tr.employee_id
            WHERE ({company_filter})
              AND tr.status IN ('assigned', 'in_progress')
              AND tr.due_date IS NOT NULL
              AND tr.due_date::date <= $2
        """,
        "link": "/app/matcha/training",
    },
    # COBRA deadlines
    {
        "category": "cobra",
        "sql": """
            SELECT ce.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — COBRA ' || ce.qualifying_event_type AS title,
                   x.label AS subtitle,
                   x.deadline::date AS deadline
            FROM cobra_events ce
            LEFT JOIN employees e ON e.id = ce.employee_id
            CROSS JOIN LATERAL (VALUES
                ('Employer notice',  ce.employer_notice_deadline),
                ('Election',         ce.election_deadline)
            ) AS x(label, deadline)
            WHERE ({company_filter_cobra})
              AND ce.status NOT IN ('waived', 'expired', 'terminated')
              AND x.deadline IS NOT NULL
              AND x.deadline::date <= $2
        """,
        "link": "/app/matcha/cobra",
    },
    # Stale policies (updated_at older than 180 days → deadline = updated_at + 180d)
    {
        "category": "policy",
        "sql": """
            SELECT p.id::text,
                   p.title,
                   'Last updated ' || to_char(p.updated_at, 'Mon DD, YYYY') AS subtitle,
                   (p.updated_at + INTERVAL '180 days')::date AS deadline
            FROM policies p
            WHERE ({company_filter})
              AND p.status = 'active'
              AND (p.updated_at + INTERVAL '180 days')::date <= $2
        """,
        "link": "/app/matcha/policies/{id}",
    },
    # Open IR incidents (age tracking — deadline = created_at, so days_until is negative = how old)
    {
        "category": "ir",
        "sql": """
            SELECT i.id::text,
                   i.title,
                   i.incident_number || ' — ' || i.status AS subtitle,
                   i.created_at::date AS deadline
            FROM ir_incidents i
            WHERE ({company_filter})
              AND i.status IN ('reported', 'investigating', 'action_required')
        """,
        "link": "/app/ir/incidents/{id}",
    },
    # Open ER cases
    {
        "category": "er",
        "sql": """
            SELECT ec.id::text,
                   ec.title,
                   ec.case_number || ' — ' || ec.status AS subtitle,
                   ec.created_at::date AS deadline
            FROM er_cases ec
            WHERE ({company_filter})
              AND ec.status NOT IN ('closed', 'resolved')
        """,
        "link": "/app/matcha/er-copilot/{id}",
    },
    # I-9 expirations
    {
        "category": "i9",
        "sql": """
            SELECT i9.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — I-9' AS title,
                   x.label AS subtitle,
                   x.expiry::date AS deadline
            FROM i9_records i9
            LEFT JOIN employees e ON e.id = i9.employee_id
            CROSS JOIN LATERAL (VALUES
                ('I-9 expiration',          i9.expiration_date),
                ('I-9 reverification',      i9.reverification_expiration)
            ) AS x(label, expiry)
            WHERE ({company_filter_i9})
              AND x.expiry IS NOT NULL
              AND x.expiry::date <= $2
        """,
        "link": "/app/matcha/i9",
    },
    # Separation agreement deadlines
    {
        "category": "separation",
        "sql": """
            SELECT sa.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — Separation' AS title,
                   x.label AS subtitle,
                   x.deadline::date AS deadline
            FROM separation_agreements sa
            LEFT JOIN employees e ON e.id = sa.employee_id
            CROSS JOIN LATERAL (VALUES
                ('Consideration deadline', sa.consideration_deadline),
                ('Revocation deadline',    sa.revocation_deadline)
            ) AS x(label, deadline)
            WHERE ({company_filter})
              AND sa.status IN ('draft', 'sent', 'pending_signature', 'signed')
              AND x.deadline IS NOT NULL
              AND x.deadline::date <= $2
        """,
        "link": "/app/matcha/separations",
    },
    # Onboarding tasks
    {
        "category": "onboarding",
        "sql": """
            SELECT eot.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — ' || eot.task_name AS title,
                   'Onboarding task' AS subtitle,
                   eot.due_date::date AS deadline
            FROM employee_onboarding_tasks eot
            LEFT JOIN employees e ON e.id = eot.employee_id
            WHERE ({company_filter_onboard})
              AND eot.status = 'pending'
              AND eot.due_date IS NOT NULL
              AND eot.due_date::date <= $2
        """,
        "link": "/app/matcha/onboarding",
    },
    # Upcoming legislation — passed/signed laws about to take effect for this company's locations
    {
        "category": "legislation",
        "sql": """
            SELECT ul.id::text,
                   ul.title,
                   ul.impact_summary AS subtitle,
                   ul.expected_effective_date::date AS deadline
            FROM upcoming_legislation ul
            WHERE ({company_filter})
              AND ul.current_status IN ('passed', 'signed', 'effective_soon')
              AND ul.expected_effective_date IS NOT NULL
              AND ul.expected_effective_date::date <= $2
        """,
        "link": "/app/matcha/compliance",
    },
    # Compliance requirement expirations — requirements with an expiration date approaching
    {
        "category": "requirement",
        "sql": """
            SELECT cr.id::text,
                   cr.title,
                   cr.jurisdiction_name || ' — ' || cr.category AS subtitle,
                   cr.expiration_date::date AS deadline
            FROM compliance_requirements cr
            JOIN business_locations bl ON bl.id = cr.location_id
            WHERE ({company_filter_cr})
              AND cr.expiration_date IS NOT NULL
              AND cr.expiration_date::date <= $2
        """,
        "link": "/app/matcha/compliance",
    },
    # Upcoming compliance requirement effective dates — new rules about to take effect
    {
        "category": "legislation",
        "sql": """
            SELECT cr.id::text,
                   cr.title,
                   cr.jurisdiction_name || ' — effective ' || to_char(cr.effective_date, 'Mon DD, YYYY') AS subtitle,
                   cr.effective_date::date AS deadline
            FROM compliance_requirements cr
            JOIN business_locations bl ON bl.id = cr.location_id
            WHERE ({company_filter_cr})
              AND cr.effective_date IS NOT NULL
              AND cr.effective_date::date > CURRENT_DATE
              AND cr.effective_date::date <= $2
        """,
        "link": "/app/matcha/compliance",
    },
]


def _apply_company_filter(sql: str, company_id: UUID | None) -> str:
    """Replace {company_filter*} placeholders with real WHERE clauses."""
    if company_id is not None:
        return (
            sql
            .replace("{company_filter_emp}", "e.org_id = $1")
            .replace("{company_filter_cobra}", "ce.company_id = $1")
            .replace("{company_filter_i9}", "i9.company_id = $1")
            .replace("{company_filter_onboard}", "eot.company_id = $1")
            .replace("{company_filter_cr}", "bl.company_id = $1")
            .replace("{company_filter}", "company_id = $1")
        )
    # Admin: no company scoping — use TRUE
    return (
        sql
        .replace("{company_filter_emp}", "TRUE")
        .replace("{company_filter_cobra}", "TRUE")
        .replace("{company_filter_i9}", "TRUE")
        .replace("{company_filter_onboard}", "TRUE")
        .replace("{company_filter_cr}", "TRUE")
        .replace("{company_filter}", "TRUE")
    )


@router.get("/upcoming", response_model=UpcomingResponse)
async def get_upcoming_deadlines(
    days: int = Query(90, ge=1, le=365),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Aggregate all time-sensitive items across the platform, sorted by urgency."""
    company_id = await get_client_company_id(current_user)

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, dashboard_upcoming_key(company_id, days))
        if cached is not None:
            return cached

    today = date.today()
    lookahead = today + timedelta(days=days)

    items: list[UpcomingItem] = []

    async with get_connection() as conn:
        for source in _UPCOMING_SOURCES:
            try:
                sql = _apply_company_filter(source["sql"], company_id)
                # Pass only the args the query actually references to avoid asyncpg
                # "N args passed but server expects M" errors.
                uses_p1 = "$1" in sql
                uses_p2 = "$2" in sql
                if uses_p1 and uses_p2:
                    rows = await conn.fetch(sql, company_id, lookahead)
                elif uses_p1:
                    rows = await conn.fetch(sql, company_id)
                elif uses_p2:
                    rows = await conn.fetch(sql, lookahead)
                else:
                    rows = await conn.fetch(sql)
            except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
                logger.debug("Skipping upcoming source %s (table/column missing)", source["category"])
                continue
            except Exception:
                logger.exception("Failed to query upcoming source: %s", source["category"])
                continue

            for row in rows:
                deadline = row["deadline"]
                if deadline is None:
                    continue
                days_until = (deadline - today).days
                link = source["link"]
                row_id = row.get("id")
                if row_id and "{id}" in link:
                    link = link.replace("{id}", row_id)

                items.append(
                    UpcomingItem(
                        category=source["category"],
                        title=row["title"] or source["category"].title(),
                        subtitle=row.get("subtitle"),
                        date=deadline,
                        days_until=days_until,
                        severity=_severity_from_days(days_until),
                        link=link,
                    )
                )

    # Sort by urgency: most overdue / soonest first
    items.sort(key=lambda x: x.days_until)

    result = UpcomingResponse(items=items, total=len(items))

    if redis:
        await cache_set(redis, dashboard_upcoming_key(company_id, days), result.model_dump(), ttl=300)

    return result


# ---------------------------------------------------------------------------
# Escalated Queries — low-confidence Matcha Work queries for human review
# ---------------------------------------------------------------------------


class EscalatedQueryItem(BaseModel):
    id: str
    status: str
    severity: str
    title: str
    user_query: str
    ai_reply: Optional[str] = None
    ai_mode: Optional[str] = None
    ai_confidence: Optional[float] = None
    missing_fields: Optional[list] = None
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    thread_id: str
    created_at: datetime
    updated_at: datetime


class EscalatedQueryListResponse(BaseModel):
    items: list[EscalatedQueryItem]
    total: int


class EscalatedQueryDetail(EscalatedQueryItem):
    thread_title: Optional[str] = None
    context_messages: list[dict] = []


class ResolveBody(BaseModel):
    resolution_note: str


class DismissBody(BaseModel):
    reason: Optional[str] = None


class StatusBody(BaseModel):
    status: Literal["in_review"]


@router.get("/escalated-queries", response_model=EscalatedQueryListResponse)
async def list_escalated_queries(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List escalated queries for the user's company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return EscalatedQueryListResponse(items=[], total=0)

    where = "WHERE company_id = $1"
    params: list = [company_id]
    if status_filter:
        where += f" AND status = ${len(params) + 1}"
        params.append(status_filter)

    async with get_connection() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM mw_escalated_queries {where}", *params
        ) or 0

        rows = await conn.fetch(
            f"""SELECT id, status, severity, title, user_query, ai_reply,
                       ai_mode, ai_confidence, missing_fields, resolution_note,
                       resolved_by::text, resolved_at, thread_id::text, created_at, updated_at
                FROM mw_escalated_queries {where}
                ORDER BY
                  CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                  created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )

    items = [
        EscalatedQueryItem(
            id=str(r["id"]),
            status=r["status"],
            severity=r["severity"],
            title=r["title"],
            user_query=r["user_query"],
            ai_reply=r["ai_reply"],
            ai_mode=r["ai_mode"],
            ai_confidence=r["ai_confidence"],
            missing_fields=r["missing_fields"],
            resolution_note=r["resolution_note"],
            resolved_by=r["resolved_by"],
            resolved_at=r["resolved_at"],
            thread_id=r["thread_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
    return EscalatedQueryListResponse(items=items, total=total)


@router.get("/escalated-queries/{query_id}", response_model=EscalatedQueryDetail)
async def get_escalated_query(
    query_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get an escalated query with surrounding thread context."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT eq.*, t.title AS thread_title
               FROM mw_escalated_queries eq
               LEFT JOIN mw_threads t ON t.id = eq.thread_id
               WHERE eq.id = $1 AND eq.company_id = $2""",
            query_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Escalated query not found")

        # Fetch surrounding messages for context
        messages = await conn.fetch(
            """SELECT id::text, role, content, created_at
               FROM mw_messages
               WHERE thread_id = $1
               ORDER BY created_at ASC
               LIMIT 20""",
            row["thread_id"],
        )

    return EscalatedQueryDetail(
        id=str(row["id"]),
        status=row["status"],
        severity=row["severity"],
        title=row["title"],
        user_query=row["user_query"],
        ai_reply=row["ai_reply"],
        ai_mode=row["ai_mode"],
        ai_confidence=row["ai_confidence"],
        missing_fields=row["missing_fields"],
        resolution_note=row["resolution_note"],
        resolved_by=str(row["resolved_by"]) if row["resolved_by"] else None,
        resolved_at=row["resolved_at"],
        thread_id=str(row["thread_id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        thread_title=row["thread_title"],
        context_messages=[dict(m) for m in messages],
    )


@router.put("/escalated-queries/{query_id}/resolve")
async def resolve_escalated_query(
    query_id: UUID,
    body: ResolveBody,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Resolve an escalated query with a resolution note."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE mw_escalated_queries
               SET status = 'resolved',
                   resolution_note = $3,
                   resolved_by = $4,
                   resolved_at = NOW(),
                   updated_at = NOW()
               WHERE id = $1 AND company_id = $2 AND status != 'resolved'""",
            query_id, company_id, body.resolution_note, current_user.id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Escalated query not found or already resolved")

    return {"status": "resolved"}


@router.put("/escalated-queries/{query_id}/dismiss")
async def dismiss_escalated_query(
    query_id: UUID,
    body: DismissBody,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Dismiss an escalated query."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE mw_escalated_queries
               SET status = 'dismissed',
                   resolution_note = $3,
                   resolved_by = $4,
                   resolved_at = NOW(),
                   updated_at = NOW()
               WHERE id = $1 AND company_id = $2 AND status NOT IN ('resolved', 'dismissed')""",
            query_id, company_id, body.reason, current_user.id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Escalated query not found or already closed")

    return {"status": "dismissed"}


@router.put("/escalated-queries/{query_id}/status")
async def update_escalated_query_status(
    query_id: UUID,
    body: StatusBody,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Transition an escalated query to in_review."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE mw_escalated_queries
               SET status = $3, updated_at = NOW()
               WHERE id = $1 AND company_id = $2 AND status = 'open'""",
            query_id, company_id, body.status,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Escalated query not found or not in open status")

    return {"status": body.status}
