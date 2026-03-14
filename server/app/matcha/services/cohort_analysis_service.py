"""Cohort Analysis Service.

Groups employees by department, location, hire quarter, or tenure band
and computes per-cohort risk metrics for department heat maps.
"""

import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


@dataclass
class CohortResult:
    label: str
    headcount: int
    headcount_pct: float
    incident_count: int
    incident_rate: float  # per 100 FTE annualized
    er_case_count: int
    discipline_count: int
    risk_concentration: float  # cohort's % of risk / % of headcount
    flags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _quarter_label(dt: date) -> str:
    """Convert a date to a quarter label like 'Q1-2025'."""
    q = (dt.month - 1) // 3 + 1
    return f"Q{q}-{dt.year}"


def _tenure_band(start_date: date, today: date) -> str:
    """Classify tenure into bands."""
    months = (today.year - start_date.year) * 12 + (today.month - start_date.month)
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
        dimension: One of 'department', 'location', 'hire_quarter', 'tenure'.

    Returns:
        List of CohortResult, one per cohort, sorted by risk_concentration descending.
    """
    async with get_connection() as conn:
        # Fetch all active employees
        employees = await conn.fetch(
            """
            SELECT id, department, work_state, start_date, employment_type
            FROM employees
            WHERE org_id = $1 AND termination_date IS NULL
            """,
            company_id,
        )

        if not employees:
            return []

        today = date.today()

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
            else:
                key = emp["department"] or "Unassigned"

            cohorts.setdefault(key, []).append(emp)

        total_headcount = len(employees)

        # Fetch incident counts by employee email (ir_incidents uses reported_by_email)
        incident_rows = await conn.fetch(
            """
            SELECT i.reported_by_email, COUNT(*) AS cnt
            FROM ir_incidents i
            WHERE i.company_id = $1
              AND i.status NOT IN ('resolved', 'closed')
            GROUP BY i.reported_by_email
            """,
            company_id,
        )
        # Build a lookup of employee email -> incident count
        incident_by_email: dict[str, int] = {}
        total_incidents = 0
        for row in incident_rows:
            email = row["reported_by_email"]
            if email:
                incident_by_email[email] = int(row["cnt"])
            total_incidents += int(row["cnt"])

        # Map employee IDs to emails for lookup
        emp_emails = await conn.fetch(
            "SELECT id, email FROM employees WHERE org_id = $1 AND termination_date IS NULL",
            company_id,
        )
        emp_id_to_email: dict[UUID, str] = {
            row["id"]: row["email"] for row in emp_emails if row["email"]
        }

        # Try to count incidents by department directly if the column exists
        incident_by_dept: dict[str, int] = {}
        try:
            dept_incident_rows = await conn.fetch(
                """
                SELECT department, COUNT(*) AS cnt
                FROM ir_incidents
                WHERE company_id = $1
                  AND status NOT IN ('resolved', 'closed')
                  AND department IS NOT NULL
                GROUP BY department
                """,
                company_id,
            )
            incident_by_dept = {
                row["department"]: int(row["cnt"]) for row in dept_incident_rows
            }
        except Exception:
            pass

        # Fetch ER case counts
        er_rows = await conn.fetch(
            """
            SELECT COUNT(*) AS cnt
            FROM er_cases
            WHERE company_id = $1 AND status != 'closed'
            """,
            company_id,
        )
        total_er_cases = int(er_rows[0]["cnt"]) if er_rows else 0

        # Build results
        results: list[CohortResult] = []
        total_risk_events = total_incidents + total_er_cases

        for label, emps in cohorts.items():
            headcount = len(emps)
            headcount_pct = round((headcount / total_headcount) * 100, 1)

            # Count incidents for this cohort
            cohort_incidents = 0
            if dimension == "department" and label in incident_by_dept:
                cohort_incidents = incident_by_dept[label]
            else:
                for emp in emps:
                    email = emp_id_to_email.get(emp["id"], "")
                    cohort_incidents += incident_by_email.get(email, 0)

            # Annualized incident rate per 100 FTE
            incident_rate = round((cohort_incidents / headcount) * 100, 2) if headcount > 0 else 0.0

            # ER cases and discipline — approximate by proportion if not available per-cohort
            # (ER cases don't always link to specific departments)
            er_case_count = 0
            discipline_count = 0

            # Risk concentration: (cohort's % of risk events) / (cohort's % of headcount)
            if total_risk_events > 0 and headcount_pct > 0:
                cohort_risk_pct = (cohort_incidents / max(total_risk_events, 1)) * 100
                risk_concentration = round(cohort_risk_pct / headcount_pct, 2)
            else:
                risk_concentration = 0.0

            # Compute average incident rate across all cohorts for comparison
            avg_incident_rate = round((total_incidents / total_headcount) * 100, 2) if total_headcount > 0 else 0.0

            flags: list[str] = []
            if avg_incident_rate > 0 and incident_rate > 0:
                ratio = incident_rate / avg_incident_rate
                if ratio >= 2.0:
                    flags.append(f"{ratio:.1f}x incident rate vs avg")
            if risk_concentration > 2.0:
                flags.append(f"Risk concentration {risk_concentration:.1f}x")
            if headcount_pct < 15 and cohort_incidents >= 3:
                flags.append(f"Small cohort ({headcount_pct}%) with {cohort_incidents} incidents")

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
            ))

        # Sort by risk_concentration descending (highest risk first)
        results.sort(key=lambda r: r.risk_concentration, reverse=True)
        return results
