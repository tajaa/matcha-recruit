"""The five dimension scorers (compliance, incident, ER, workforce, legislative)
plus the minimum-wage violation metrics collector the compliance one reads.
"""
import logging
from dataclasses import field
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from ._config import COMPLIANCE_CRITICAL_ALERT_CAP, COMPLIANCE_CRITICAL_ALERT_POINTS, COMPLIANCE_WAGE_LOCATION_CAP, COMPLIANCE_WAGE_LOCATION_POINTS, COMPLIANCE_WAGE_VIOLATION_CAP, COMPLIANCE_WAGE_VIOLATION_POINTS, COMPLIANCE_WARNING_ALERT_CAP, COMPLIANCE_WARNING_ALERT_POINTS, ER_HIGH_DISCREPANCY_POINTS, ER_IN_REVIEW_CAP, ER_IN_REVIEW_POINTS, ER_MAJOR_POLICY_POINTS, ER_OPEN_CAP, ER_OPEN_POINTS, ER_PENDING_CAP, ER_PENDING_POINTS
from ._shared import DimensionResult, _band
from .cost_of_risk import (
    compute_compliance_cost_of_risk, compute_er_cost_of_risk,
    compute_incident_cost_of_risk,
)

logger = logging.getLogger(__name__)


async def _collect_minimum_wage_violation_metrics(
    company_id: UUID, conn
) -> dict[str, Any]:
    """Aggregate employee minimum wage violations across active locations."""
    from app.core.services.compliance_service import get_employee_impact_for_location

    location_rows = await conn.fetch(
        """
        SELECT id, name, city, state
        FROM business_locations
        WHERE company_id = $1
          AND COALESCE(is_active, TRUE) = TRUE
        """,
        company_id,
    )

    violating_employee_ids: set[str] = set()
    hourly_employee_ids: set[str] = set()
    salary_employee_ids: set[str] = set()
    location_summaries: list[dict[str, Any]] = []
    employee_violations: list[dict[str, Any]] = []
    seen_employee_violations: set[str] = set()

    for location in location_rows:
        try:
            impact = await get_employee_impact_for_location(location["id"], company_id)
        except Exception:
            logger.exception(
                "Failed to compute employee impact for risk assessment location %s",
                location["id"],
            )
            continue

        location_employee_ids: set[str] = set()
        violations_by_rate_type = impact.get("violations_by_rate_type", {})

        for violation in violations_by_rate_type.get("general", []):
            employee_id = violation.get("employee_id")
            if not employee_id:
                continue
            violating_employee_ids.add(employee_id)
            hourly_employee_ids.add(employee_id)
            location_employee_ids.add(employee_id)
            if employee_id not in seen_employee_violations:
                seen_employee_violations.add(employee_id)
                employee_violations.append({
                    "employee_name": violation.get("employee_name"),
                    "pay_rate": violation.get("pay_rate"),
                    "threshold": violation.get("threshold"),
                    "shortfall": violation.get("shortfall"),
                    "pay_classification": violation.get("pay_classification"),
                    "location_city": location["city"],
                    "location_state": location["state"],
                })

        for violation in violations_by_rate_type.get("exempt_salary", []):
            employee_id = violation.get("employee_id")
            if not employee_id:
                continue
            violating_employee_ids.add(employee_id)
            salary_employee_ids.add(employee_id)
            location_employee_ids.add(employee_id)
            if employee_id not in seen_employee_violations:
                seen_employee_violations.add(employee_id)
                employee_violations.append({
                    "employee_name": violation.get("employee_name"),
                    "pay_rate": violation.get("pay_rate"),
                    "threshold": violation.get("threshold"),
                    "shortfall": violation.get("shortfall"),
                    "pay_classification": violation.get("pay_classification"),
                    "location_city": location["city"],
                    "location_state": location["state"],
                })

        if location_employee_ids:
            location_summaries.append(
                {
                    "location_id": str(location["id"]),
                    "location_name": location["name"],
                    "city": location["city"],
                    "state": location["state"],
                    "violation_count": len(location_employee_ids),
                }
            )

    location_summaries.sort(
        key=lambda item: (
            -int(item["violation_count"]),
            (item["location_name"] or item["city"] or "").lower(),
            (item["state"] or "").lower(),
        )
    )

    employee_violations.sort(key=lambda v: -(v.get("shortfall") or 0))

    return {
        "minimum_wage_violation_employee_count": len(violating_employee_ids),
        "hourly_minimum_wage_violation_count": len(hourly_employee_ids),
        "salary_minimum_wage_violation_count": len(salary_employee_ids),
        "locations_with_minimum_wage_violations": len(location_summaries),
        "top_minimum_wage_violation_locations": location_summaries[:5],
        "employee_violations": employee_violations[:10],
        "all_employee_violations": employee_violations,
    }


async def compute_compliance_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score compliance risk based on unread alerts and check recency."""
    row = await conn.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE ca.severity = 'critical' AND ca.status = 'unread') AS critical_unread,
          COUNT(*) FILTER (WHERE ca.severity = 'warning'  AND ca.status = 'unread') AS warning_unread,
          (SELECT MAX(completed_at) FROM compliance_check_log WHERE company_id = $1) AS last_check
        FROM compliance_alerts ca
        JOIN business_locations bl ON bl.id = ca.location_id
        WHERE ca.company_id = $1
        """,
        company_id,
    )

    critical_unread = int(row["critical_unread"] or 0)
    warning_unread = int(row["warning_unread"] or 0)
    last_check: Optional[datetime] = row["last_check"]
    from app.core.services.compliance_service import _get_company_canonical_industry

    wage_violation_metrics = await _collect_minimum_wage_violation_metrics(company_id, conn)
    all_violations = wage_violation_metrics.pop("all_employee_violations", [])
    total_wage_violations = int(
        wage_violation_metrics["minimum_wage_violation_employee_count"] or 0
    )
    hourly_wage_violations = int(
        wage_violation_metrics["hourly_minimum_wage_violation_count"] or 0
    )
    salary_wage_violations = int(
        wage_violation_metrics["salary_minimum_wage_violation_count"] or 0
    )
    wage_violation_locations = int(
        wage_violation_metrics["locations_with_minimum_wage_violations"] or 0
    )

    score = 0
    factors = []

    critical_points = min(
        critical_unread * COMPLIANCE_CRITICAL_ALERT_POINTS,
        COMPLIANCE_CRITICAL_ALERT_CAP,
    )
    if critical_points > 0:
        score += critical_points
        factors.append(f"{critical_unread} unread critical alert{'s' if critical_unread != 1 else ''} (+{critical_points})")

    warning_points = min(
        warning_unread * COMPLIANCE_WARNING_ALERT_POINTS,
        COMPLIANCE_WARNING_ALERT_CAP,
    )
    if warning_points > 0:
        score += warning_points
        factors.append(f"{warning_unread} unread warning alert{'s' if warning_unread != 1 else ''} (+{warning_points})")

    wage_points = min(
        total_wage_violations * COMPLIANCE_WAGE_VIOLATION_POINTS,
        COMPLIANCE_WAGE_VIOLATION_CAP,
    )
    if wage_points > 0:
        awarded = min(wage_points, max(0, 100 - score))
        score += awarded
        factors.append(
            f"{total_wage_violations} employee{'s' if total_wage_violations != 1 else ''} below minimum wage across "
            f"{wage_violation_locations} location{'s' if wage_violation_locations != 1 else ''} (+{awarded})"
        )

    location_points = min(
        wage_violation_locations * COMPLIANCE_WAGE_LOCATION_POINTS,
        COMPLIANCE_WAGE_LOCATION_CAP,
    )
    if location_points > 0 and score < 100:
        awarded = min(location_points, max(0, 100 - score))
        score += awarded
        factors.append(
            f"{wage_violation_locations} location{'s' if wage_violation_locations != 1 else ''} with active wage violations (+{awarded})"
        )

    if hourly_wage_violations > 0:
        factors.append(
            f"{hourly_wage_violations} hourly employee{'s' if hourly_wage_violations != 1 else ''} below local minimum wage"
        )
    if salary_wage_violations > 0:
        factors.append(
            f"{salary_wage_violations} salaried employee{'s' if salary_wage_violations != 1 else ''} below exempt salary minimum"
        )

    stale_points = 0
    if last_check is None:
        stale_points = 20
        score += stale_points
        factors.append(f"No compliance check on record (+{stale_points})")
    else:
        if last_check.tzinfo is None:
            last_check = last_check.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - last_check).days
        if days_since >= 30:
            stale_points = 20
            score += stale_points
            factors.append(f"Last compliance check {days_since} days ago (+{stale_points})")

    score = min(score, 100)
    if not factors:
        factors.append("No compliance issues detected")

    canonical_industry = await _get_company_canonical_industry(conn, company_id)
    is_healthcare = canonical_industry == "healthcare"
    total_employees = await conn.fetchval(
        "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
        company_id,
    )
    # Query actual credential expiration data for affected employee names
    credential_at_risk = []
    if is_healthcare:
        cred_rows = await conn.fetch(
            """
            SELECT e.first_name, e.last_name, ec.license_type, ec.license_expiration,
                   ec.dea_expiration, ec.board_certification_expiration, ec.malpractice_expiration
            FROM employee_credentials ec
            JOIN employees e ON e.id = ec.employee_id AND e.org_id = ec.org_id
            WHERE ec.org_id = $1 AND e.termination_date IS NULL
              AND (
                  ec.license_expiration < NOW() + INTERVAL '90 days'
                  OR ec.dea_expiration < NOW() + INTERVAL '90 days'
                  OR ec.board_certification_expiration < NOW() + INTERVAL '90 days'
                  OR ec.malpractice_expiration < NOW() + INTERVAL '90 days'
              )
            ORDER BY LEAST(
                COALESCE(ec.license_expiration, '2999-01-01'),
                COALESCE(ec.dea_expiration, '2999-01-01'),
                COALESCE(ec.board_certification_expiration, '2999-01-01'),
                COALESCE(ec.malpractice_expiration, '2999-01-01')
            )
            LIMIT 10
            """,
            company_id,
        )
        from datetime import date as _date
        today = _date.today()
        for r in cred_rows:
            name = f"{r['first_name']} {r['last_name']}"
            expiring = []
            for field, label in [
                ("license_expiration", r.get("license_type") or "License"),
                ("dea_expiration", "DEA"),
                ("board_certification_expiration", "Board Cert"),
                ("malpractice_expiration", "Malpractice"),
            ]:
                exp = r.get(field)
                if exp and exp < today:
                    expiring.append(f"{label} expired {exp.strftime('%m/%d/%Y')}")
                elif exp and (exp - today).days < 90:
                    expiring.append(f"{label} expires {exp.strftime('%m/%d/%Y')}")
            if expiring:
                credential_at_risk.append({"name": name, "detail": "; ".join(expiring)})

    compliance_cost = compute_compliance_cost_of_risk(
        all_violations, int(total_employees or 0), is_healthcare,
        credential_at_risk=credential_at_risk,
    )

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "critical_unread": critical_unread,
            "warning_unread": warning_unread,
            "last_check": last_check.isoformat() if last_check else None,
            **wage_violation_metrics,
            "cost_of_risk": compliance_cost,
            "is_healthcare": is_healthcare,
        },
    )


async def compute_incident_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score incident risk based on open IR incidents by severity."""
    rows = await conn.fetch(
        """
        SELECT severity, COUNT(*) AS cnt
        FROM ir_incidents
        WHERE company_id = $1
          AND status NOT IN ('resolved', 'closed')
        GROUP BY severity
        """,
        company_id,
    )

    counts: dict[str, int] = {row["severity"]: int(row["cnt"]) for row in rows}
    critical = counts.get("critical", 0)
    high = counts.get("high", 0)
    medium = counts.get("medium", 0)
    low = counts.get("low", 0)

    score = 0
    factors = []

    if critical > 0:
        score += min(critical * 25, 100 - score)
        factors.append(f"{critical} open critical incident{'s' if critical != 1 else ''} (+{critical * 25})")

    if high > 0:
        pts = min(high * 15, max(0, 100 - score))
        score += pts
        factors.append(f"{high} open high severity incident{'s' if high != 1 else ''} (+{high * 15})")

    if medium > 0:
        pts = min(medium * 8, max(0, 100 - score))
        score += pts
        factors.append(f"{medium} open medium severity incident{'s' if medium != 1 else ''} (+{medium * 8})")

    if low > 0:
        pts = min(low * 3, max(0, 100 - score))
        score += pts
        factors.append(f"{low} open low severity incident{'s' if low != 1 else ''} (+{low * 3})")

    score = min(score, 100)
    if not factors:
        factors.append("No open incidents")

    incident_cost = compute_incident_cost_of_risk(critical, high, medium)

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "open_critical": critical,
            "open_high": high,
            "open_medium": medium,
            "open_low": low,
            "cost_of_risk": incident_cost,
        },
    )


async def compute_er_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score ER risk based on open cases and analysis findings."""
    status_rows = await conn.fetch(
        """
        SELECT status, COUNT(*) AS cnt
        FROM er_cases
        WHERE company_id = $1 AND status != 'closed'
        GROUP BY status
        """,
        company_id,
    )

    status_counts: dict[str, int] = {row["status"]: int(row["cnt"]) for row in status_rows}
    pending = status_counts.get("pending_determination", 0)
    in_review = status_counts.get("in_review", 0)
    open_cases = status_counts.get("open", 0)

    analysis_rows = await conn.fetch(
        """
        SELECT analysis_type, analysis_data
        FROM er_case_analysis
        WHERE case_id IN (SELECT id FROM er_cases WHERE company_id = $1)
          AND analysis_type IN ('policy_check', 'discrepancies')
        """,
        company_id,
    )

    has_major_policy_violation = False
    has_high_discrepancy = False

    import json as _json
    for row in analysis_rows:
        data = row["analysis_data"]
        if isinstance(data, str):
            try:
                data = _json.loads(data)
            except Exception:
                continue
        if not isinstance(data, dict):
            continue

        if row["analysis_type"] == "policy_check":
            violation_level = data.get("violation_level", "") or data.get("severity", "")
            if isinstance(violation_level, str) and "major" in violation_level.lower():
                has_major_policy_violation = True
        elif row["analysis_type"] == "discrepancies":
            severity = data.get("severity", "") or data.get("overall_severity", "")
            if isinstance(severity, str) and severity.lower() == "high":
                has_high_discrepancy = True

    score = 0
    factors = []

    if pending > 0:
        pts = min(pending * ER_PENDING_POINTS, ER_PENDING_CAP)
        score += pts
        factors.append(f"{pending} case{'s' if pending != 1 else ''} pending determination (+{pts})")

    if in_review > 0:
        pts = min(in_review * ER_IN_REVIEW_POINTS, min(ER_IN_REVIEW_CAP, max(0, 100 - score)))
        score += pts
        factors.append(f"{in_review} case{'s' if in_review != 1 else ''} in review (+{pts})")

    if open_cases > 0:
        pts = min(open_cases * ER_OPEN_POINTS, min(ER_OPEN_CAP, max(0, 100 - score)))
        score += pts
        factors.append(f"{open_cases} open case{'s' if open_cases != 1 else ''} (+{pts})")

    if has_major_policy_violation and score < 100:
        pts = min(ER_MAJOR_POLICY_POINTS, 100 - score)
        score += pts
        factors.append(f"Major policy violation found in analysis (+{pts})")

    if has_high_discrepancy and score < 100:
        pts = min(ER_HIGH_DISCREPANCY_POINTS, 100 - score)
        score += pts
        factors.append(f"High severity discrepancy in analysis (+{pts})")

    score = min(score, 100)
    if not factors:
        factors.append("No open ER cases")

    # Fetch individual non-closed cases for action items
    case_rows = await conn.fetch(
        """
        SELECT id, title, status, category, created_at
        FROM er_cases
        WHERE company_id = $1 AND status != 'closed'
        ORDER BY
            CASE status
                WHEN 'pending_determination' THEN 1
                WHEN 'in_review' THEN 2
                ELSE 3
            END,
            created_at DESC
        LIMIT 10
        """,
        company_id,
    )
    open_case_details = [
        {
            "case_id": str(row["id"]),
            "title": row["title"],
            "status": row["status"],
            "category": row["category"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in case_rows
    ]

    er_cost = compute_er_cost_of_risk(
        pending, in_review, open_cases,
        has_major_policy_violation, has_high_discrepancy,
    )

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "pending_determination": pending,
            "in_review": in_review,
            "open": open_cases,
            "major_policy_violation": has_major_policy_violation,
            "high_discrepancy": has_high_discrepancy,
            "open_cases": open_case_details,
            "cost_of_risk": er_cost,
        },
    )


async def compute_workforce_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score workforce risk based on multi-jurisdictional exposure and workforce composition."""
    rows = await conn.fetch(
        """
        SELECT work_state, employment_type, COUNT(*) AS cnt
        FROM employees
        WHERE org_id = $1 AND termination_date IS NULL
        GROUP BY work_state, employment_type
        """,
        company_id,
    )

    total_employees = sum(int(row["cnt"]) for row in rows)
    unique_states = len({row["work_state"] for row in rows if row["work_state"]})

    contractor_intern_count = sum(
        int(row["cnt"])
        for row in rows
        if row["employment_type"] in ("contractor", "intern")
    )

    score = 0
    factors = []

    state_pts = unique_states * 5
    if unique_states > 0:
        score += min(state_pts, 100)
        factors.append(f"{unique_states} state{'s' if unique_states != 1 else ''} with active employees (+{state_pts})")

    if total_employees > 10:
        over_10 = total_employees - 10
        scale_pts = min((over_10 // 10) * 3, 30)
        if scale_pts > 0:
            score += min(scale_pts, max(0, 100 - score))
            factors.append(f"{total_employees} total employees (scale factor +{scale_pts})")

    if total_employees > 0:
        pct_contingent = contractor_intern_count / total_employees
        if pct_contingent > 0.20:
            pts = min(15, max(0, 100 - score))
            score += pts
            pct_display = int(pct_contingent * 100)
            factors.append(f"{pct_display}% contingent workforce (contractors/interns) (+{pts})")

    score = min(score, 100)
    if not factors:
        factors.append("No workforce risk indicators")

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "total_employees": total_employees,
            "unique_states": unique_states,
            "contractor_intern_count": contractor_intern_count,
        },
    )


async def compute_legislative_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score legislative risk based on upcoming legislation affecting company locations."""
    rows = await conn.fetch(
        """
        SELECT jl.expected_effective_date
        FROM jurisdiction_legislation jl
        JOIN business_locations bl ON bl.jurisdiction_id = jl.jurisdiction_id
        WHERE bl.company_id = $1
          AND jl.current_status IN ('passed', 'signed', 'effective_soon')
          AND jl.expected_effective_date > CURRENT_DATE
        """,
        company_id,
    )

    today = datetime.now(timezone.utc).date()
    within_30 = 0
    within_90 = 0
    within_180 = 0

    for row in rows:
        effective_date = row["expected_effective_date"]
        if effective_date is None:
            continue
        if isinstance(effective_date, datetime):
            effective_date = effective_date.date()
        if not isinstance(effective_date, date):
            continue

        days_until = (effective_date - today).days
        if days_until < 30:
            within_30 += 1
        elif days_until < 90:
            within_90 += 1
        elif days_until < 180:
            within_180 += 1

    score = 0
    factors = []

    if within_30 > 0:
        pts = min(within_30 * 40, 100)
        score += pts
        factors.append(f"{within_30} legislation item{'s' if within_30 != 1 else ''} effective within 30 days (+{pts})")

    if within_90 > 0:
        pts = min(within_90 * 20, max(0, 100 - score))
        score += pts
        factors.append(f"{within_90} legislation item{'s' if within_90 != 1 else ''} effective within 31–90 days (+{pts})")

    if within_180 > 0:
        pts = min(within_180 * 5, max(0, 100 - score))
        score += pts
        factors.append(f"{within_180} legislation item{'s' if within_180 != 1 else ''} effective within 91–180 days (+{pts})")

    score = min(score, 100)
    if not factors:
        factors.append("No upcoming legislation changes")

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "within_30_days": within_30,
            "within_90_days": within_90,
            "within_180_days": within_180,
        },
    )
