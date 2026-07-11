"""Cohort Analysis Service.

Groups employees by department, location, hire quarter, or tenure band
and computes per-cohort risk metrics for department heat maps.
"""

import logging
import math
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any
from uuid import UUID

from ...database import get_connection
from .flight_risk_service import _calendar_months_between

logger = logging.getLogger(__name__)


@dataclass
class CohortResult:
    label: str
    headcount: int
    headcount_pct: float
    incident_count: int
    incident_rate: float  # per 100 FTE annualized
    er_case_count: int         # always 0 — ER cases carry no employee link (not cohort-attributable)
    discipline_count: int
    risk_concentration: float  # cohort's % of risk / % of headcount
    flags: list[str]
    # How trustworthy the concentration ratio is given the cohort's event count
    # (a 1-person / 1-event cohort reads as extreme by chance). high/moderate/low.
    concentration_confidence: str = "low"
    # ER cases are not attributable to a cohort (er_cases has no employee_id and
    # no party link table), so er_case_count stays 0 for every cohort. Surfaced
    # so consumers can label it rather than read the 0 as "no ER exposure".
    er_attributable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _quarter_label(dt: date) -> str:
    """Convert a date to a quarter label like 'Q1-2025'."""
    q = (dt.month - 1) // 3 + 1
    return f"Q{q}-{dt.year}"


def _concentration_confidence(
    observed: int, total_events: int, headcount: int, total_headcount: int
) -> str:
    """How credible is a cohort's risk concentration, vs. small-sample noise.

    Null model: risk events land proportional to headcount, so the cohort's
    expected count is ``total_events × headcount/total_headcount`` and, treated
    as Poisson, has sd ≈ √expected. A concentration is only trustworthy when the
    cohort has enough events AND sits several sd above its expectation.
    Returns 'high' / 'moderate' / 'low'.
    """
    if observed < 2 or total_events <= 0 or headcount <= 0 or total_headcount <= 0:
        return "low"
    expected = total_events * (headcount / total_headcount)
    if expected <= 0:
        return "low"
    z = (observed - expected) / math.sqrt(expected)
    if observed >= 3 and z >= 2.0:
        return "high"
    if observed >= 2 and z >= 1.0:
        return "moderate"
    return "low"


def _tenure_band(start_date: date, today: date) -> str:
    """Classify tenure into bands."""
    # Shared day-of-month-aware month count (a start day-of-month later than
    # today's means the final month hasn't completed) so boundary hires land
    # in the same band the flight-risk tenure score uses.
    months = _calendar_months_between(start_date, today)
    if months < 6:
        return "0-6mo"
    elif months < 12:
        return "6-12mo"
    elif months < 24:
        return "1-2yr"
    elif months < 60:
        return "2-5yr"
    else:
        return "5yr+"


async def compute_cohort_analysis(
    company_id: UUID,
    dimension: str = "department",
) -> list[CohortResult]:
    """Compute cohort-level risk metrics grouped by the specified dimension.

    Args:
        company_id: The company to analyze.
        dimension: One of 'department', 'location', 'hire_quarter', 'tenure', 'manager'.

    Returns:
        List of CohortResult, one per cohort, sorted by risk_concentration descending.
    """
    async with get_connection() as conn:
        # Fetch all active employees
        employees = await conn.fetch(
            """
            SELECT id, department, work_state, start_date, employment_type, manager_id
            FROM employees
            WHERE org_id = $1 AND termination_date IS NULL
            """,
            company_id,
        )

        if not employees:
            return []

        today = date.today()

        # Manager-name lookup is only needed when grouping by manager.
        manager_name_by_id: dict[UUID, str] = {}
        if dimension == "manager":
            mgr_ids = {emp["manager_id"] for emp in employees if emp["manager_id"]}
            if mgr_ids:
                mgr_rows = await conn.fetch(
                    """
                    SELECT id, first_name, last_name FROM employees
                    WHERE id = ANY($1::uuid[]) AND org_id = $2
                    """,
                    list(mgr_ids),
                    company_id,
                )
                for row in mgr_rows:
                    fn = row["first_name"] or ""
                    ln = row["last_name"] or ""
                    manager_name_by_id[row["id"]] = f"{fn} {ln}".strip() or "Unassigned"

        # Group employees into cohorts
        cohorts: dict[str, list] = {}
        for emp in employees:
            if dimension == "department":
                key = emp["department"] or "Unassigned"
            elif dimension == "location":
                key = emp["work_state"] or "Unknown"
            elif dimension == "hire_quarter":
                hd = emp["start_date"]
                if hd is None:
                    key = "Unknown"
                else:
                    if isinstance(hd, datetime):
                        hd = hd.date()
                    key = _quarter_label(hd)
            elif dimension == "tenure":
                hd = emp["start_date"]
                if hd is None:
                    key = "Unknown"
                else:
                    if isinstance(hd, datetime):
                        hd = hd.date()
                    key = _tenure_band(hd, today)
            elif dimension == "manager":
                mid = emp["manager_id"]
                key = manager_name_by_id.get(mid, "Unassigned") if mid else "Unassigned"
            else:
                key = emp["department"] or "Unassigned"

            cohorts.setdefault(key, []).append(emp)

        total_headcount = len(employees)

        # Fetch incidents with involved employee IDs
        incident_rows = await conn.fetch(
            """
            SELECT id, involved_employee_ids
            FROM ir_incidents
            WHERE company_id = $1
              AND status NOT IN ('resolved', 'closed')
            """,
            company_id,
        )
        # Build a lookup of employee_id -> incident count
        incident_by_emp_id: dict[UUID, int] = {}
        total_incidents = 0
        for row in incident_rows:
            total_incidents += 1
            for eid in (row["involved_employee_ids"] or []):
                incident_by_emp_id[eid] = incident_by_emp_id.get(eid, 0) + 1

        # Discipline IS cohort-attributable — progressive_discipline.employee_id
        # links each record to an employee, so place it in cohorts the same way
        # as incidents (last 24 months, matching the discipline lookback window).
        discipline_rows = await conn.fetch(
            """
            SELECT employee_id, COUNT(*) AS cnt
            FROM progressive_discipline
            WHERE company_id = $1
              AND issued_date >= CURRENT_DATE - INTERVAL '24 months'
            GROUP BY employee_id
            """,
            company_id,
        )
        discipline_by_emp_id: dict[UUID, int] = {
            row["employee_id"]: int(row["cnt"]) for row in discipline_rows
        }
        total_discipline = sum(discipline_by_emp_id.values())

        # Risk concentration is now measured over the risk events we CAN place in
        # a cohort: incidents + discipline. ER cases stay excluded — er_cases has
        # no employee link (no FK, no party table), so they are not attributable
        # to any cohort (er_case_count is reported as 0, er_attributable=False).
        total_risk_events = total_incidents + total_discipline
        results: list[CohortResult] = []

        for label, emps in cohorts.items():
            headcount = len(emps)
            headcount_pct = round((headcount / total_headcount) * 100, 1)

            # Count incidents for this cohort via involved_employee_ids
            cohort_incidents = 0
            for emp in emps:
                cohort_incidents += incident_by_emp_id.get(emp["id"], 0)

            # Annualized incident rate per 100 FTE
            incident_rate = round((cohort_incidents / headcount) * 100, 2) if headcount > 0 else 0.0

            # Discipline is attributable (see lookup above); ER is not.
            discipline_count = sum(discipline_by_emp_id.get(emp["id"], 0) for emp in emps)
            er_case_count = 0
            cohort_risk_events = cohort_incidents + discipline_count

            # Risk concentration: (cohort's % of risk events) / (cohort's % of headcount).
            # Risk events = incidents + discipline (the ones we can place in a cohort).
            if total_risk_events > 0 and headcount_pct > 0:
                cohort_risk_pct = (cohort_risk_events / total_risk_events) * 100
                risk_concentration = round(cohort_risk_pct / headcount_pct, 2)
            else:
                risk_concentration = 0.0

            # Significance: is this concentration real or small-sample noise?
            # Under a null of events spread proportional to headcount, the cohort's
            # expected event count is total_risk_events × headcount share; compare
            # the observed count to that Poisson expectation (sd = sqrt(expected)).
            concentration_confidence = _concentration_confidence(
                cohort_risk_events, total_risk_events, headcount, total_headcount
            )

            # Compute average incident rate across all cohorts for comparison
            avg_incident_rate = round((total_incidents / total_headcount) * 100, 2) if total_headcount > 0 else 0.0

            flags: list[str] = []
            if avg_incident_rate > 0 and incident_rate > 0:
                ratio = incident_rate / avg_incident_rate
                if ratio >= 2.0:
                    flags.append(f"{ratio:.1f}x incident rate vs avg")
            # Only flag an elevated concentration when it's statistically credible —
            # a 1-person cohort with 1 event no longer reads as an extreme hot-spot.
            if risk_concentration > 2.0 and concentration_confidence != "low":
                flags.append(f"Risk concentration {risk_concentration:.1f}x")
            if headcount_pct < 15 and cohort_risk_events >= 3:
                flags.append(f"Small cohort ({headcount_pct}%) with {cohort_risk_events} risk events")

            results.append(CohortResult(
                label=label,
                headcount=headcount,
                headcount_pct=headcount_pct,
                incident_count=cohort_incidents,
                incident_rate=incident_rate,
                er_case_count=er_case_count,
                discipline_count=discipline_count,
                risk_concentration=risk_concentration,
                flags=flags,
                concentration_confidence=concentration_confidence,
                er_attributable=False,
            ))

        # Sort by risk_concentration descending (highest risk first)
        results.sort(key=lambda r: r.risk_concentration, reverse=True)
        return results
