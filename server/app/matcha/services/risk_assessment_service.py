"""Risk Assessment Service.

Computes a live risk score across 5 dimensions for a company:
- Compliance (30%)
- Incidents (25%)
- ER Cases (25%)
- Workforce (15%)
- Legislative (5%)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


def _band(score: int) -> str:
    if score <= 25:
        return "low"
    elif score <= 50:
        return "moderate"
    elif score <= 75:
        return "high"
    else:
        return "critical"


@dataclass
class DimensionResult:
    score: int
    band: str
    factors: list[str]
    raw_data: dict[str, Any]


@dataclass
class RiskAssessmentResult:
    overall_score: int
    overall_band: str
    dimensions: dict[str, DimensionResult]
    computed_at: datetime


async def compute_compliance_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score compliance risk based on unread alerts and check recency."""
    row = await conn.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE ca.severity = 'critical' AND ca.status = 'unread') AS critical_unread,
          COUNT(*) FILTER (WHERE ca.severity = 'warning'  AND ca.status = 'unread') AS warning_unread,
          MAX(cl.completed_at) AS last_check
        FROM compliance_alerts ca
        JOIN business_locations bl ON bl.id = ca.location_id
        LEFT JOIN compliance_check_log cl ON cl.company_id = $1
        WHERE ca.company_id = $1
        """,
        company_id,
    )

    critical_unread = int(row["critical_unread"] or 0)
    warning_unread = int(row["warning_unread"] or 0)
    last_check: Optional[datetime] = row["last_check"]

    score = 0
    factors = []

    critical_points = min(critical_unread * 35, 70)
    if critical_points > 0:
        score += critical_points
        factors.append(f"{critical_unread} unread critical alert{'s' if critical_unread != 1 else ''} (+{critical_points})")

    warning_points = min(warning_unread * 15, 30)
    if warning_points > 0:
        score += warning_points
        factors.append(f"{warning_unread} unread warning alert{'s' if warning_unread != 1 else ''} (+{warning_points})")

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

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "critical_unread": critical_unread,
            "warning_unread": warning_unread,
            "last_check": last_check.isoformat() if last_check else None,
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

    points = min(critical * 25, 100)
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

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "open_critical": critical,
            "open_high": high,
            "open_medium": medium,
            "open_low": low,
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
        pts = min(pending * 30, 100)
        score += pts
        factors.append(f"{pending} case{'s' if pending != 1 else ''} pending determination (+{pts})")

    if in_review > 0:
        pts = min(in_review * 20, max(0, 100 - score))
        score += pts
        factors.append(f"{in_review} case{'s' if in_review != 1 else ''} in review (+{pts})")

    if open_cases > 0:
        pts = min(open_cases * 10, max(0, 100 - score))
        score += pts
        factors.append(f"{open_cases} open case{'s' if open_cases != 1 else ''} (+{pts})")

    if has_major_policy_violation and score < 100:
        pts = min(15, 100 - score)
        score += pts
        factors.append(f"Major policy violation found in analysis (+{pts})")

    if has_high_discrepancy and score < 100:
        pts = min(10, 100 - score)
        score += pts
        factors.append(f"High severity discrepancy in analysis (+{pts})")

    score = min(score, 100)
    if not factors:
        factors.append("No open ER cases")

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
          AND jl.expected_effective_date > NOW()
        """,
        company_id,
    )

    now = datetime.now(timezone.utc)
    within_30 = 0
    within_90 = 0
    within_180 = 0

    for row in rows:
        effective_date = row["expected_effective_date"]
        if effective_date is None:
            continue
        if hasattr(effective_date, 'tzinfo') and effective_date.tzinfo is None:
            effective_date = effective_date.replace(tzinfo=timezone.utc)
        days_until = (effective_date - now).days
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


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_recommendations(result: RiskAssessmentResult) -> list[dict]:
    """Derive actionable recommendations from computed risk scores. Pure function, no DB calls."""
    recs: list[dict] = []

    def add(dimension: str, priority: str, action: str):
        recs.append({"dimension": dimension, "priority": priority, "action": action})

    # --- Compliance ---
    comp = result.dimensions.get("compliance")
    if comp and comp.score > 0:
        rd = comp.raw_data
        if rd.get("critical_unread", 0) > 0:
            add("compliance", "critical", f"Review and address {rd['critical_unread']} critical compliance alert{'s' if rd['critical_unread'] != 1 else ''}")
        if rd.get("warning_unread", 0) > 0:
            add("compliance", "high", f"Review {rd['warning_unread']} unread warning-level compliance alert{'s' if rd['warning_unread'] != 1 else ''}")
        last_check = rd.get("last_check")
        if last_check is None:
            add("compliance", "medium", "No compliance check on record — run one now")
        elif last_check:
            lc = datetime.fromisoformat(last_check) if isinstance(last_check, str) else last_check
            if lc.tzinfo is None:
                lc = lc.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - lc).days
            if days >= 30:
                add("compliance", "medium", f"Run a compliance check — last check was {days} days ago")

    # --- Incidents ---
    inc = result.dimensions.get("incidents")
    if inc and inc.score > 0:
        rd = inc.raw_data
        if rd.get("open_critical", 0) > 0:
            add("incidents", "critical", f"Prioritize resolution of {rd['open_critical']} critical incident{'s' if rd['open_critical'] != 1 else ''}")
        if rd.get("open_high", 0) > 0:
            add("incidents", "high", f"Address {rd['open_high']} high-severity open incident{'s' if rd['open_high'] != 1 else ''}")
        if rd.get("open_medium", 0) > 0:
            add("incidents", "medium", f"Review {rd['open_medium']} medium-severity open incident{'s' if rd['open_medium'] != 1 else ''}")
        if rd.get("open_low", 0) > 0:
            add("incidents", "low", f"Close or resolve {rd['open_low']} low-severity open incident{'s' if rd['open_low'] != 1 else ''}")

    # --- ER Cases ---
    er = result.dimensions.get("er_cases")
    if er and er.score > 0:
        rd = er.raw_data
        if rd.get("pending_determination", 0) > 0:
            add("er_cases", "critical", f"Make determinations on {rd['pending_determination']} pending ER case{'s' if rd['pending_determination'] != 1 else ''}")
        if rd.get("in_review", 0) > 0:
            add("er_cases", "high", f"Complete review of {rd['in_review']} ER case{'s' if rd['in_review'] != 1 else ''} in review")
        if rd.get("open", 0) > 0:
            add("er_cases", "medium", f"Progress {rd['open']} open ER case{'s' if rd['open'] != 1 else ''} toward resolution")
        if rd.get("major_policy_violation"):
            add("er_cases", "critical", "Investigate major policy violation flagged in case analysis")
        if rd.get("high_discrepancy"):
            add("er_cases", "high", "Review high-severity discrepancy findings in ER analysis")

    # --- Workforce ---
    wf = result.dimensions.get("workforce")
    if wf and wf.score > 0:
        rd = wf.raw_data
        states = rd.get("unique_states", 0)
        if states > 3:
            add("workforce", "medium", f"Review multi-state compliance posture — employees in {states} states")
        total = rd.get("total_employees", 0)
        contingent = rd.get("contractor_intern_count", 0)
        if total > 0 and contingent / total > 0.20:
            pct = int(contingent / total * 100)
            add("workforce", "medium", f"Audit contractor/intern classification — {pct}% contingent workforce exceeds 20% threshold")
        if total > 50:
            add("workforce", "low", f"Ensure HR processes and policies scale with {total}-person headcount")

    # --- Legislative ---
    leg = result.dimensions.get("legislative")
    if leg and leg.score > 0:
        rd = leg.raw_data
        w30 = rd.get("within_30_days", 0)
        w90 = rd.get("within_90_days", 0)
        w180 = rd.get("within_180_days", 0)
        if w30 > 0:
            add("legislative", "critical", f"Urgent: {w30} legislation change{'s' if w30 != 1 else ''} effective within 30 days — prepare compliance updates")
        if w90 > 0:
            add("legislative", "high", f"Plan for {w90} legislation change{'s' if w90 != 1 else ''} effective within 31–90 days")
        if w180 > 0:
            add("legislative", "low", f"Monitor {w180} upcoming legislation change{'s' if w180 != 1 else ''} (91–180 days out)")

    recs.sort(key=lambda r: PRIORITY_ORDER.get(r["priority"], 99))
    return recs


async def compute_risk_assessment(company_id: UUID) -> RiskAssessmentResult:
    """Compute full risk assessment for a company across all 5 dimensions."""
    async with get_connection() as conn:
        compliance = await compute_compliance_dimension(company_id, conn)
        incidents = await compute_incident_dimension(company_id, conn)
        er = await compute_er_dimension(company_id, conn)
        workforce = await compute_workforce_dimension(company_id, conn)
        legislative = await compute_legislative_dimension(company_id, conn)

    # Weighted overall score
    overall = int(
        compliance.score * 0.30
        + incidents.score * 0.25
        + er.score * 0.25
        + workforce.score * 0.15
        + legislative.score * 0.05
    )
    overall = min(overall, 100)

    return RiskAssessmentResult(
        overall_score=overall,
        overall_band=_band(overall),
        dimensions={
            "compliance": compliance,
            "incidents": incidents,
            "er_cases": er,
            "workforce": workforce,
            "legislative": legislative,
        },
        computed_at=datetime.now(timezone.utc),
    )
