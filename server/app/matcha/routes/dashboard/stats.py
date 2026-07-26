"""Dashboard stats endpoint — returns company-scoped metrics."""
import logging

import asyncpg
from fastapi import APIRouter, Depends

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.core.models.auth import CurrentUser
from app.core.services.redis_cache import get_redis_cache, cache_get, cache_set, dashboard_stats_key
from app.matcha.models.dashboard import (
    PendingIncident,
    ActivityItem,
    IncidentSummary,
    WageAlertSummary,
    ERCaseSummary,
    StalePolicySummary,
    ManagerHotspot,
    FlightRiskWidgetSummary,
    WageGapSummary,
    DashboardStats,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
                    open=status_map.get("open", 0),
                    in_review=status_map.get("in_review", 0),
                    pending_determination=status_map.get("pending_determination", 0),
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
        from app.core.services.compliance_service import get_employee_impact_for_location

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

    # Hourly wage gap vs. BLS market (§3.1, QSR_RETENTION_PLAN.md)
    wage_gap_summary = None
    try:
        from app.matcha.services.workforce.wage_benchmark_service import compute_company_wage_gap
        gap = await compute_company_wage_gap(company_id)
        # Only surface when there's an hourly population to talk about — the
        # widget is noise on companies with 0 hourly employees.
        if gap.hourly_employees_count > 0:
            wage_gap_summary = WageGapSummary(
                hourly_employees_count=gap.hourly_employees_count,
                employees_evaluated=gap.employees_evaluated,
                employees_below_market=gap.employees_below_market,
                employees_at_or_above_market=gap.employees_at_or_above_market,
                employees_unclassified=gap.employees_unclassified,
                median_delta_percent=gap.median_delta_percent,
                dollars_per_hour_to_close_gap=gap.dollars_per_hour_to_close_gap,
                annual_cost_to_lift=gap.annual_cost_to_lift,
                max_replacement_cost_exposure=gap.max_replacement_cost_exposure,
            )
    except asyncpg.UndefinedTableError:
        pass  # wage_benchmarks table not yet migrated — silent
    except Exception:
        logger.exception("Failed to compute wage gap summary for dashboard")

    # Composite flight-risk score (§3.3, QSR_RETENTION_PLAN.md)
    flight_risk_summary = None
    try:
        from app.matcha.services.workforce.flight_risk_service import compute_company_summary
        fr = await compute_company_summary(company_id)
        # Only surface when there are employees to evaluate — avoids a
        # widget that always reads "0 evaluated" on empty companies.
        if fr.employees_evaluated > 0:
            flight_risk_summary = FlightRiskWidgetSummary(
                employees_evaluated=fr.employees_evaluated,
                critical_count=fr.critical_count,
                high_count=fr.high_count,
                elevated_count=fr.elevated_count,
                low_count=fr.low_count,
                expected_loss_at_replacement=fr.expected_loss_at_replacement,
                top_driver=fr.top_driver,
                top_driver_count=fr.top_driver_count,
                early_tenure_count=fr.early_tenure_count,
                manager_hotspots=[ManagerHotspot(**h) for h in fr.manager_hotspots],
            )
    except asyncpg.UndefinedTableError:
        pass  # employees / wage_benchmarks not yet migrated — silent
    except Exception:
        logger.exception("Failed to compute flight-risk summary for dashboard")

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
        wage_gap_summary=wage_gap_summary,
        flight_risk_summary=flight_risk_summary,
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
