"""Pre-Termination Risk Check Service.

Scans 8 risk dimensions for an employee before separation to identify
legal, compliance, and reputational risks. Each dimension produces a
green/yellow/red flag contributing to an overall 0-100 risk score.

Dimensions:
1. Active ER Cases
2. Recent IR Involvement
3. Leave & Accommodation Status
4. Protected Activity Signals
5. Documentation Completeness
6. Tenure & Timing
7. Consistency Check
8. Manager Risk Profile
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from google import genai

from ...config import get_settings
from ...database import get_connection
from .risk_assessment_service import _band, _parse_json_response, _is_model_unavailable_error, FALLBACK_MODELS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PreTermDimensionResult:
    status: str   # "green", "yellow", "red"
    score: int    # 0, 15, or 30
    summary: str
    details: dict[str, Any]


@dataclass
class PreTermCheckResult:
    overall_score: int          # 0-100 normalized
    overall_band: str           # low / moderate / high / critical
    dimensions: dict[str, PreTermDimensionResult]
    recommended_actions: list[str]
    ai_narrative: Optional[str]
    requires_acknowledgment: bool
    computed_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW_UTC = lambda: datetime.now(timezone.utc)


def _green(summary: str, **details: Any) -> PreTermDimensionResult:
    return PreTermDimensionResult(status="green", score=0, summary=summary, details=dict(details))


def _yellow(summary: str, **details: Any) -> PreTermDimensionResult:
    return PreTermDimensionResult(status="yellow", score=15, summary=summary, details=dict(details))


def _red(summary: str, **details: Any) -> PreTermDimensionResult:
    return PreTermDimensionResult(status="red", score=30, summary=summary, details=dict(details))


def _safe_dimension(name: str, exc: Exception) -> PreTermDimensionResult:
    """Return a yellow result when a dimension scan fails unexpectedly."""
    logger.exception("Error scanning dimension %s", name)
    return _yellow(
        f"Error scanning this dimension: {type(exc).__name__}",
        error=str(exc),
    )


# ---------------------------------------------------------------------------
# Dimension 1: Active ER Cases
# ---------------------------------------------------------------------------

async def scan_er_cases(
    employee_id: UUID, company_id: UUID, conn,
) -> PreTermDimensionResult:
    """Check for ER cases where employee is involved."""
    try:
        now = _NOW_UTC()
        twelve_months_ago = now - timedelta(days=365)
        ninety_days_ago = now - timedelta(days=90)

        containment = json.dumps([{"employee_id": str(employee_id)}])

        rows = await conn.fetch(
            """
            SELECT id, case_number, title, status, category,
                   involved_employees, created_at, closed_at
            FROM er_cases
            WHERE company_id = $1
              AND involved_employees @> $2::jsonb
              AND (
                  status IN ('open', 'in_review', 'pending_determination')
                  OR (status = 'closed' AND closed_at >= $3)
              )
            ORDER BY created_at DESC
            """,
            company_id, containment, twelve_months_ago,
        )

        if not rows:
            return _green("No ER case involvement in the last 12 months")

        # Determine employee's role in each case from involved_employees JSONB
        open_cases = []
        recent_closed = []

        for row in rows:
            case_info = {
                "case_id": str(row["id"]),
                "case_number": row["case_number"],
                "title": row["title"],
                "status": row["status"],
                "category": row["category"],
            }

            # Parse involved_employees to find the employee's role
            involved = row["involved_employees"]
            if isinstance(involved, str):
                try:
                    involved = json.loads(involved)
                except (json.JSONDecodeError, TypeError):
                    involved = []
            if not isinstance(involved, list):
                involved = []

            role = "involved"
            for entry in involved:
                if isinstance(entry, dict) and str(entry.get("employee_id")) == str(employee_id):
                    role = entry.get("role", "involved")
                    break
            case_info["role"] = role

            if row["status"] in ("open", "in_review", "pending_determination"):
                open_cases.append(case_info)
            else:
                recent_closed.append(case_info)

        # Red: complainant or respondent in open/in_review case
        for case in open_cases:
            if case["role"] in ("complainant", "respondent"):
                return _red(
                    f"Employee is {case['role']} in open case \"{case['title']}\" "
                    f"(status: {case['case_number']}, {case.get('status', 'open')})",
                    open_cases=open_cases,
                    recent_closed_cases=recent_closed,
                )

        # Red: involved in any open case (even without specific role)
        if open_cases:
            case = open_cases[0]
            return _red(
                f"Employee is involved in open ER case \"{case['title']}\" "
                f"(status: {case.get('status', 'open')})",
                open_cases=open_cases,
                recent_closed_cases=recent_closed,
            )

        # Yellow: case closed within last 90 days
        for case in recent_closed:
            return _yellow(
                f"Employee was involved in ER case \"{case['title']}\" closed within the last 90 days",
                open_cases=open_cases,
                recent_closed_cases=recent_closed,
            )

        return _green(
            "No ER case involvement in the last 12 months",
            open_cases=open_cases,
            recent_closed_cases=recent_closed,
        )

    except Exception as exc:
        return _safe_dimension("er_cases", exc)


# ---------------------------------------------------------------------------
# Dimension 2: Recent IR Involvement
# ---------------------------------------------------------------------------

async def scan_ir_involvement(
    employee_id: UUID, company_id: UUID, conn,
) -> PreTermDimensionResult:
    """Check for IR incident involvement or reporting."""
    try:
        now = _NOW_UTC()
        thirty_days_ago = now - timedelta(days=30)
        ninety_days_ago = now - timedelta(days=90)

        # Get employee's email for reporter matching
        emp_row = await conn.fetchrow(
            "SELECT work_email, email FROM employees WHERE id = $1",
            employee_id,
        )
        employee_email = None
        if emp_row:
            employee_email = emp_row["work_email"] or emp_row.get("email")

        # Query incidents where employee is involved or is the reporter
        if employee_email:
            rows = await conn.fetch(
                """
                SELECT id, incident_number, title, status, severity,
                       occurred_at, reported_by_email, involved_employee_ids
                FROM ir_incidents
                WHERE company_id = $1
                  AND (
                      $2 = ANY(involved_employee_ids)
                      OR reported_by_email = $3
                  )
                  AND occurred_at >= $4
                ORDER BY occurred_at DESC
                """,
                company_id, employee_id, employee_email, ninety_days_ago,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, incident_number, title, status, severity,
                       occurred_at, reported_by_email, involved_employee_ids
                FROM ir_incidents
                WHERE company_id = $1
                  AND $2 = ANY(involved_employee_ids)
                  AND occurred_at >= $3
                ORDER BY occurred_at DESC
                """,
                company_id, employee_id, ninety_days_ago,
            )

        if not rows:
            return _green("No incident involvement in the last 90 days")

        incidents = []
        reporter_incidents_recent = []

        for row in rows:
            inc_info = {
                "incident_id": str(row["id"]),
                "incident_number": row["incident_number"],
                "title": row["title"],
                "status": row["status"],
                "severity": row["severity"],
                "occurred_at": row["occurred_at"].isoformat() if row["occurred_at"] else None,
            }

            is_reporter = (
                employee_email
                and row["reported_by_email"]
                and row["reported_by_email"].lower() == employee_email.lower()
            )
            inc_info["is_reporter"] = is_reporter
            incidents.append(inc_info)

            occurred_at = row["occurred_at"]
            if occurred_at:
                if occurred_at.tzinfo is None:
                    occurred_at = occurred_at.replace(tzinfo=timezone.utc)
                if is_reporter and occurred_at >= thirty_days_ago:
                    reporter_incidents_recent.append(inc_info)

        # Red: employee filed a report in the last 30 days
        if reporter_incidents_recent:
            inc = reporter_incidents_recent[0]
            return _red(
                f"Employee filed incident report \"{inc['title']}\" "
                f"({inc['incident_number']}) in the last 30 days — protected activity",
                incidents=incidents,
                reporter_incidents_recent=reporter_incidents_recent,
            )

        # Yellow: involved in incident in last 90 days
        return _yellow(
            f"Employee involved in {len(incidents)} incident(s) in the last 90 days",
            incidents=incidents,
        )

    except Exception as exc:
        return _safe_dimension("ir_involvement", exc)


# ---------------------------------------------------------------------------
# Dimension 3: Leave & Accommodation Status
# ---------------------------------------------------------------------------

async def scan_leave_status(
    employee_id: UUID, conn,
) -> PreTermDimensionResult:
    """Check for active leave, pending requests, or recent sick leave."""
    try:
        today = date.today()
        sixty_days_ago = today - timedelta(days=60)

        rows = await conn.fetch(
            """
            SELECT id, request_type, start_date, end_date, status,
                   hours, reason, approved_at
            FROM pto_requests
            WHERE employee_id = $1
              AND (
                  status IN ('pending', 'approved')
                  AND end_date >= $2
              )
            ORDER BY start_date DESC
            """,
            employee_id, sixty_days_ago,
        )

        if not rows:
            return _green("No active or recent leave activity")

        active_leaves = []
        pending_requests = []
        recent_sick_returns = []

        for row in rows:
            leave_info = {
                "request_id": str(row["id"]),
                "request_type": row["request_type"],
                "start_date": row["start_date"].isoformat() if row["start_date"] else None,
                "end_date": row["end_date"].isoformat() if row["end_date"] else None,
                "status": row["status"],
                "hours": float(row["hours"]) if row["hours"] else None,
            }

            if row["status"] == "pending":
                pending_requests.append(leave_info)
            elif row["status"] == "approved":
                start = row["start_date"]
                end = row["end_date"]
                if start and end:
                    # Active leave: dates overlap today
                    if start <= today <= end:
                        active_leaves.append(leave_info)
                    # Recently returned from sick leave
                    elif (
                        row["request_type"] == "sick"
                        and end < today
                        and end >= sixty_days_ago
                    ):
                        recent_sick_returns.append(leave_info)

        # Red: active leave or pending request
        if active_leaves:
            leave = active_leaves[0]
            return _red(
                f"Employee is currently on approved {leave['request_type']} leave "
                f"({leave['start_date']} to {leave['end_date']}) — "
                f"termination during leave may violate FMLA/ADA",
                active_leaves=active_leaves,
                pending_requests=pending_requests,
                recent_sick_returns=recent_sick_returns,
            )

        if pending_requests:
            return _red(
                f"Employee has {len(pending_requests)} pending leave request(s) — "
                f"termination while request pending creates retaliation inference",
                active_leaves=active_leaves,
                pending_requests=pending_requests,
                recent_sick_returns=recent_sick_returns,
            )

        # Yellow: returned from sick leave within 60 days
        if recent_sick_returns:
            leave = recent_sick_returns[0]
            return _yellow(
                f"Employee returned from sick leave on {leave['end_date']} "
                f"(within last 60 days) — potential protected leave",
                active_leaves=active_leaves,
                pending_requests=pending_requests,
                recent_sick_returns=recent_sick_returns,
            )

        return _green(
            "No active or recent protected leave activity",
            active_leaves=active_leaves,
            pending_requests=pending_requests,
            recent_sick_returns=recent_sick_returns,
        )

    except Exception as exc:
        return _safe_dimension("leave_status", exc)


# ---------------------------------------------------------------------------
# Dimension 4: Protected Activity Signals
# ---------------------------------------------------------------------------

async def scan_protected_activity(
    employee_id: UUID, company_id: UUID, conn,
) -> PreTermDimensionResult:
    """Cross-reference ER complaints and IR reports for protected activity."""
    try:
        now = _NOW_UTC()
        twelve_months_ago = now - timedelta(days=365)

        containment = json.dumps([{"employee_id": str(employee_id)}])
        protected_categories = (
            "whistleblower", "retaliation", "harassment",
            "discrimination", "safety", "wage_theft",
        )

        # ER cases where employee is complainant with protected categories
        er_rows = await conn.fetch(
            """
            SELECT id, case_number, title, category, status, created_at,
                   involved_employees
            FROM er_cases
            WHERE company_id = $1
              AND involved_employees @> $2::jsonb
              AND created_at >= $3
            ORDER BY created_at DESC
            """,
            company_id, containment, twelve_months_ago,
        )

        complainant_signals = []
        witness_signals = []

        for row in er_rows:
            involved = row["involved_employees"]
            if isinstance(involved, str):
                try:
                    involved = json.loads(involved)
                except (json.JSONDecodeError, TypeError):
                    involved = []
            if not isinstance(involved, list):
                involved = []

            role = "involved"
            for entry in involved:
                if isinstance(entry, dict) and str(entry.get("employee_id")) == str(employee_id):
                    role = entry.get("role", "involved")
                    break

            signal = {
                "source": "er_case",
                "case_id": str(row["id"]),
                "case_number": row["case_number"],
                "title": row["title"],
                "category": row["category"],
                "role": role,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }

            if role == "complainant":
                complainant_signals.append(signal)
            elif role == "witness":
                witness_signals.append(signal)

        # IR incidents where employee is the reporter
        emp_row = await conn.fetchrow(
            "SELECT work_email, email FROM employees WHERE id = $1",
            employee_id,
        )
        employee_email = None
        if emp_row:
            employee_email = emp_row["work_email"] or emp_row.get("email")

        ir_reporter_signals = []
        if employee_email:
            ir_rows = await conn.fetch(
                """
                SELECT id, incident_number, title, incident_type,
                       reported_by_email, occurred_at
                FROM ir_incidents
                WHERE company_id = $1
                  AND reported_by_email = $2
                  AND occurred_at >= $3
                ORDER BY occurred_at DESC
                """,
                company_id, employee_email, twelve_months_ago,
            )

            for row in ir_rows:
                ir_reporter_signals.append({
                    "source": "ir_incident",
                    "incident_id": str(row["id"]),
                    "incident_number": row["incident_number"],
                    "title": row["title"],
                    "incident_type": row["incident_type"],
                    "occurred_at": row["occurred_at"].isoformat() if row["occurred_at"] else None,
                })

        all_signals = complainant_signals + ir_reporter_signals + witness_signals

        # Red: filed complaint or safety report in last 12 months
        if complainant_signals:
            sig = complainant_signals[0]
            return _red(
                f"Employee filed complaint as complainant in ER case \"{sig['title']}\" "
                f"({sig['case_number']}) — protected activity under Title VII/SOX",
                signals=all_signals,
                complainant_cases=len(complainant_signals),
                ir_reports=len(ir_reporter_signals),
                witness_involvement=len(witness_signals),
            )

        if ir_reporter_signals:
            sig = ir_reporter_signals[0]
            return _red(
                f"Employee filed safety/incident report \"{sig['title']}\" "
                f"({sig['incident_number']}) — protected activity under OSHA Section 11(c)",
                signals=all_signals,
                complainant_cases=len(complainant_signals),
                ir_reports=len(ir_reporter_signals),
                witness_involvement=len(witness_signals),
            )

        # Yellow: participated as witness
        if witness_signals:
            return _yellow(
                f"Employee participated as witness in {len(witness_signals)} "
                f"investigation(s) in the last 12 months",
                signals=all_signals,
                complainant_cases=0,
                ir_reports=0,
                witness_involvement=len(witness_signals),
            )

        return _green("No protected activity signals detected")

    except Exception as exc:
        return _safe_dimension("protected_activity", exc)


# ---------------------------------------------------------------------------
# Dimension 5: Documentation Completeness
# ---------------------------------------------------------------------------

async def scan_documentation(
    employee_id: UUID, company_id: UUID, conn,
) -> PreTermDimensionResult:
    """Check performance review existence, recency, and scores."""
    try:
        # Check if performance_reviews table exists
        table_exists = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'performance_reviews'
            )
            """
        )

        if not table_exists:
            return _red(
                "No performance review system configured — no documentation on file",
                table_exists=False,
                reviews=[],
            )

        now = _NOW_UTC()
        six_months_ago = now - timedelta(days=183)
        twelve_months_ago = now - timedelta(days=365)

        # Get performance reviews for this employee, most recent first
        reviews = await conn.fetch(
            """
            SELECT id, status, manager_overall_rating, completed_at, created_at
            FROM performance_reviews
            WHERE employee_id = $1
              AND status IN ('completed', 'manager_submitted')
            ORDER BY COALESCE(completed_at, created_at) DESC
            """,
            employee_id,
        )

        if not reviews:
            return _red(
                "No performance reviews on file for this employee",
                table_exists=True,
                reviews=[],
                last_review=None,
            )

        latest = reviews[0]
        review_date = latest["completed_at"] or latest["created_at"]
        if review_date and review_date.tzinfo is None:
            review_date = review_date.replace(tzinfo=timezone.utc)

        rating = float(latest["manager_overall_rating"]) if latest["manager_overall_rating"] else None
        review_info = {
            "review_id": str(latest["id"]),
            "rating": rating,
            "review_date": review_date.isoformat() if review_date else None,
            "total_reviews": len(reviews),
        }

        # Red: last review was positive (>= 4.0) with no subsequent documented issues
        # A positive review followed by sudden termination is the plaintiff's best exhibit
        if rating is not None and rating >= 4.0:
            return _red(
                f"Last performance review score was {rating:.1f}/5.0 — "
                f"positive review followed by termination is high-risk",
                table_exists=True,
                last_review=review_info,
                reviews=[{
                    "review_id": str(r["id"]),
                    "rating": float(r["manager_overall_rating"]) if r["manager_overall_rating"] else None,
                    "date": (r["completed_at"] or r["created_at"]).isoformat() if (r["completed_at"] or r["created_at"]) else None,
                } for r in reviews[:5]],
            )

        # Yellow: reviews exist but > 12 months old
        if review_date and review_date < twelve_months_ago:
            months_ago = (now - review_date).days // 30
            return _yellow(
                f"Last performance review was {months_ago} months ago — documentation is stale",
                table_exists=True,
                last_review=review_info,
            )

        # Green: recent review (< 6 months) with score < 4.0
        if review_date and review_date >= six_months_ago and rating is not None and rating < 4.0:
            return _green(
                f"Recent performance review ({review_date.strftime('%Y-%m-%d')}) "
                f"with score {rating:.1f}/5.0 supports documented performance concerns",
                table_exists=True,
                last_review=review_info,
            )

        # Yellow: reviews exist but between 6-12 months old, or rating is None
        if review_date and review_date < six_months_ago:
            months_ago = (now - review_date).days // 30
            return _yellow(
                f"Last performance review was {months_ago} months ago",
                table_exists=True,
                last_review=review_info,
            )

        # Default green for cases with recent review and no clear issue
        return _green(
            f"Performance review documentation exists (most recent: "
            f"{review_date.strftime('%Y-%m-%d') if review_date else 'unknown'})",
            table_exists=True,
            last_review=review_info,
        )

    except Exception as exc:
        return _safe_dimension("documentation", exc)


# ---------------------------------------------------------------------------
# Dimension 6: Tenure & Timing
# ---------------------------------------------------------------------------

async def scan_tenure_timing(
    employee_id: UUID, conn,
) -> PreTermDimensionResult:
    """Evaluate risk based on employee tenure length."""
    try:
        row = await conn.fetchrow(
            "SELECT start_date FROM employees WHERE id = $1",
            employee_id,
        )

        if not row or not row["start_date"]:
            return _yellow(
                "No start date on file — unable to calculate tenure",
                tenure_years=None,
                start_date=None,
            )

        start_date = row["start_date"]
        if isinstance(start_date, datetime):
            start_date = start_date.date()

        today = date.today()
        tenure_days = (today - start_date).days
        tenure_years = round(tenure_days / 365.25, 1)

        details = {
            "tenure_years": tenure_years,
            "start_date": start_date.isoformat(),
            "tenure_days": tenure_days,
        }

        # Red: tenure > 10 years
        if tenure_years > 10:
            return _red(
                f"Employee tenure: {tenure_years} years — long-tenured employees "
                f"generate significantly higher jury verdicts and sympathy damages",
                **details,
            )

        # Yellow: tenure 5-10 years
        if tenure_years >= 5:
            return _yellow(
                f"Employee tenure: {tenure_years} years — moderate tenure "
                f"increases potential damages in wrongful termination claims",
                **details,
            )

        # Green: tenure < 5 years
        return _green(
            f"Employee tenure: {tenure_years} years",
            **details,
        )

    except Exception as exc:
        return _safe_dimension("tenure_timing", exc)


# ---------------------------------------------------------------------------
# Dimension 7: Consistency Check
# ---------------------------------------------------------------------------

async def scan_consistency(
    employee_id: UUID,
    company_id: UUID,
    separation_reason: Optional[str],
    conn,
) -> PreTermDimensionResult:
    """Compare this termination to similar past cases for consistency."""
    try:
        if not separation_reason:
            return _yellow(
                "No separation reason provided — unable to assess consistency",
                comparable_cases=0,
                minimum_required=3,
            )

        # Find offboarding cases for same company with any reason
        cases = await conn.fetch(
            """
            SELECT oc.id, oc.reason, oc.is_voluntary, oc.status,
                   oc.created_at, e.department, e.job_title
            FROM offboarding_cases oc
            JOIN employees e ON oc.employee_id = e.id
            WHERE oc.org_id = $1
              AND oc.employee_id != $2
            ORDER BY oc.created_at DESC
            LIMIT 50
            """,
            company_id, employee_id,
        )

        if not cases:
            return _yellow(
                "No prior offboarding cases found — insufficient data for consistency analysis",
                comparable_cases=0,
                minimum_required=3,
            )

        # Simple keyword-matching for similar reason
        reason_lower = separation_reason.lower()
        reason_keywords = set(reason_lower.split())
        # Filter out very common words
        stop_words = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "is", "was", "not"}
        reason_keywords -= stop_words

        similar_cases = []
        for case in cases:
            case_reason = (case["reason"] or "").lower()
            if not case_reason:
                continue
            case_words = set(case_reason.split()) - stop_words
            overlap = reason_keywords & case_words
            if overlap and len(overlap) >= max(1, len(reason_keywords) // 2):
                similar_cases.append({
                    "case_id": str(case["id"]),
                    "reason": case["reason"],
                    "is_voluntary": case["is_voluntary"],
                    "status": case["status"],
                    "department": case.get("department"),
                    "created_at": case["created_at"].isoformat() if case["created_at"] else None,
                })

        comparable_count = len(similar_cases)

        if comparable_count < 3:
            return _yellow(
                f"Insufficient comparable cases ({comparable_count} found, "
                f"minimum 3 required for consistency analysis)",
                comparable_cases=comparable_count,
                minimum_required=3,
                similar_cases=similar_cases,
            )

        # Check if any similar cases resulted in non-termination outcomes
        # (i.e., status != 'completed' which might indicate warnings were given instead)
        non_terminated = [
            c for c in similar_cases
            if c["status"] not in ("completed", "in_progress")
        ]

        if non_terminated:
            return _red(
                f"Similar situations were handled differently — "
                f"{len(non_terminated)} of {comparable_count} comparable cases "
                f"did not result in termination — inconsistent treatment creates "
                f"disparate treatment risk",
                comparable_cases=comparable_count,
                minimum_required=3,
                similar_cases=similar_cases,
                non_terminated_count=len(non_terminated),
            )

        return _green(
            f"Treatment is consistent with {comparable_count} similar prior cases",
            comparable_cases=comparable_count,
            minimum_required=3,
            similar_cases=similar_cases[:5],
        )

    except Exception as exc:
        return _safe_dimension("consistency", exc)


# ---------------------------------------------------------------------------
# Dimension 8: Manager Risk Profile
# ---------------------------------------------------------------------------

async def scan_manager_profile(
    employee_id: UUID, company_id: UUID, conn,
) -> PreTermDimensionResult:
    """Evaluate the employee's manager for elevated ER/termination rates."""
    try:
        # Get employee's manager
        emp_row = await conn.fetchrow(
            "SELECT manager_id FROM employees WHERE id = $1",
            employee_id,
        )

        if not emp_row or not emp_row["manager_id"]:
            return _green(
                "No manager assigned",
                manager_id=None,
            )

        manager_id = emp_row["manager_id"]

        # Count manager's ER cases (involved in via JSONB)
        mgr_containment = json.dumps([{"employee_id": str(manager_id)}])
        manager_er_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM er_cases
            WHERE company_id = $1
              AND involved_employees @> $2::jsonb
            """,
            company_id, mgr_containment,
        ) or 0

        # Count manager's terminations via offboarding_cases for their direct reports
        manager_term_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM offboarding_cases oc
            JOIN employees e ON oc.employee_id = e.id
            WHERE oc.org_id = $1
              AND e.manager_id = $2
              AND oc.is_voluntary = false
            """,
            company_id, manager_id,
        ) or 0

        # Calculate company averages per manager
        # Get total number of managers in the company
        manager_stats = await conn.fetchrow(
            """
            SELECT
                COUNT(DISTINCT e.manager_id) FILTER (WHERE e.manager_id IS NOT NULL) AS total_managers,
                COUNT(*) AS total_er_cases
            FROM employees e
            LEFT JOIN er_cases ec ON ec.company_id = $1
            WHERE e.org_id = $1
              AND e.termination_date IS NULL
              AND e.manager_id IS NOT NULL
            """,
            company_id,
        )

        total_managers = int(manager_stats["total_managers"] or 1) if manager_stats else 1
        if total_managers == 0:
            total_managers = 1

        # Company-wide ER case count
        company_er_total = await conn.fetchval(
            "SELECT COUNT(*) FROM er_cases WHERE company_id = $1",
            company_id,
        ) or 0

        # Company-wide involuntary termination count
        company_term_total = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM offboarding_cases
            WHERE org_id = $1 AND is_voluntary = false
            """,
            company_id,
        ) or 0

        avg_er_per_manager = company_er_total / total_managers if total_managers > 0 else 0
        avg_term_per_manager = company_term_total / total_managers if total_managers > 0 else 0

        details = {
            "manager_id": str(manager_id),
            "manager_er_cases": manager_er_count,
            "manager_terminations": manager_term_count,
            "company_avg_er_per_manager": round(avg_er_per_manager, 2),
            "company_avg_term_per_manager": round(avg_term_per_manager, 2),
            "total_managers": total_managers,
        }

        # Compute the ratio for the more concerning metric
        er_ratio = manager_er_count / avg_er_per_manager if avg_er_per_manager > 0 else 0
        term_ratio = manager_term_count / avg_term_per_manager if avg_term_per_manager > 0 else 0
        max_ratio = max(er_ratio, term_ratio)
        ratio_type = "ER case" if er_ratio >= term_ratio else "termination"

        # Red: > 2x company average
        if max_ratio > 2.0 and (manager_er_count > 1 or manager_term_count > 1):
            return _red(
                f"Manager has {max_ratio:.1f}x the company average {ratio_type} rate — "
                f"elevated pattern suggests management or process concerns",
                **details,
                er_ratio=round(er_ratio, 2),
                term_ratio=round(term_ratio, 2),
            )

        # Yellow: 1.5-2x average
        if max_ratio >= 1.5 and (manager_er_count > 1 or manager_term_count > 1):
            return _yellow(
                f"Manager has {max_ratio:.1f}x the company average {ratio_type} rate — "
                f"moderately elevated compared to peers",
                **details,
                er_ratio=round(er_ratio, 2),
                term_ratio=round(term_ratio, 2),
            )

        # Green: at or below average
        return _green(
            f"Manager {ratio_type} rate is at or below company average",
            **details,
            er_ratio=round(er_ratio, 2),
            term_ratio=round(term_ratio, 2),
        )

    except Exception as exc:
        return _safe_dimension("manager_profile", exc)


# ---------------------------------------------------------------------------
# Recommended Actions Generator
# ---------------------------------------------------------------------------

def _generate_recommended_actions(
    dimensions: dict[str, PreTermDimensionResult],
    overall_band: str,
) -> list[str]:
    """Produce rule-based recommended actions from dimension results."""
    actions: list[str] = []

    er = dimensions.get("er_cases")
    if er and er.status == "red":
        actions.append(
            "Do NOT proceed with termination while open ER case exists — high retaliation risk"
        )

    ir = dimensions.get("ir_involvement")
    if ir and ir.status == "red":
        actions.append(
            "Employee recently filed a protected report — consult counsel before proceeding"
        )

    leave = dimensions.get("leave_status")
    if leave and leave.status == "red":
        actions.append(
            "Employee is on active leave or has a pending leave request — "
            "termination during leave may violate FMLA/ADA"
        )

    pa = dimensions.get("protected_activity")
    if pa and pa.status == "red":
        actions.append(
            "Protected activity detected — termination may constitute retaliation "
            "under Title VII/SOX"
        )

    doc = dimensions.get("documentation")
    if doc and doc.status in ("red", "yellow"):
        actions.append(
            "Document specific performance deficiencies before proceeding — "
            "ensure contemporaneous written records exist"
        )

    consistency = dimensions.get("consistency")
    if consistency and consistency.status == "red":
        actions.append(
            "Similar situations were handled differently — ensure consistent treatment "
            "to avoid disparate treatment claims"
        )

    mgr = dimensions.get("manager_profile")
    if mgr and mgr.status == "red":
        actions.append(
            "Manager has elevated ER/termination rates — consider independent review "
            "by HR director or outside counsel"
        )

    if overall_band in ("high", "critical"):
        actions.append("Consult employment counsel before proceeding")

    return actions


# ---------------------------------------------------------------------------
# AI Narrative Prompt
# ---------------------------------------------------------------------------

PRE_TERM_NARRATIVE_PROMPT = """You are a senior employment attorney conducting a pre-termination risk assessment for an HR team. You are reviewing the automated risk screening results for an employee separation and producing a written memo suitable for sharing with in-house counsel or outside employment counsel.

IMPORTANT FRAMING: This is a risk screening tool, not legal advice. The analysis identifies potential areas of legal exposure based on the employee's data footprint across the HR platform. It does not make legal conclusions and should not be treated as a substitute for individualized legal counsel.

## Employee Context
- Employee ID: {employee_id}
- Tenure: {tenure_info}
- Separation reason: {separation_reason}
- Separation type: {separation_type}

## Risk Scan Results

Overall Score: {overall_score}/100 ({overall_band})

{dimension_summary}

## Instructions

Write a 2-3 paragraph narrative:

1. **First paragraph**: State the overall risk level and summarize the most significant flags. Be specific — name the ER case numbers, incident reports, leave dates, or other concrete data points from the dimension results. Do not generalize.

2. **Second paragraph**: Identify the specific federal and state statutes that may be implicated by the flagged dimensions. For each statute, explain the risk mechanism (e.g., "The temporal proximity between the employee's harassment complaint and the proposed termination creates a prima facie inference of retaliation under Title VII Section 704(a)"). Be precise about statutory references.

3. **Third paragraph**: Provide specific next steps the employer should take before proceeding. These should be concrete actions (not "consult counsel" generically, but "have employment counsel review the ER case file and provide a written opinion on whether the legitimate business reason can withstand a but-for causation analysis under Comcast v. Nat'l Assn. of African American-Owned Media").

Tone: objective, legally precise, suitable for a board-level audience. Avoid definitive legal conclusions — use "creates risk," "may constitute," "raises inference" rather than "is illegal" or "will result in."

End with: "This pre-termination risk screening is an automated assessment and does not constitute legal advice. The findings should be reviewed by qualified employment counsel before any employment action is taken."

Return ONLY the narrative text, no JSON wrapping or markdown fencing."""


async def _generate_ai_narrative(
    employee_id: UUID,
    dimensions: dict[str, PreTermDimensionResult],
    overall_score: int,
    overall_band: str,
    separation_reason: Optional[str],
    is_voluntary: bool,
) -> Optional[str]:
    """Generate AI narrative via Gemini for the pre-termination check."""
    try:
        settings = get_settings()

        if settings.use_vertex:
            client = genai.Client(
                vertexai=True,
                project=settings.vertex_project,
                location=settings.vertex_location,
            )
        elif settings.gemini_api_key:
            client = genai.Client(api_key=settings.gemini_api_key)
        else:
            logger.warning("No Gemini credentials configured — skipping AI narrative")
            return None

        # Build dimension summary text
        dim_lines = []
        for dim_name, dim_result in dimensions.items():
            dim_lines.append(
                f"**{dim_name}**: {dim_result.status.upper()} (score: {dim_result.score})\n"
                f"  Summary: {dim_result.summary}\n"
                f"  Details: {json.dumps(dim_result.details, default=str)}"
            )

        tenure_info = "Unknown"
        tenure_dim = dimensions.get("tenure_timing")
        if tenure_dim and tenure_dim.details:
            years = tenure_dim.details.get("tenure_years")
            start = tenure_dim.details.get("start_date")
            if years is not None:
                tenure_info = f"{years} years (start date: {start})"

        prompt = PRE_TERM_NARRATIVE_PROMPT.format(
            employee_id=str(employee_id),
            tenure_info=tenure_info,
            separation_reason=separation_reason or "Not specified",
            separation_type="Voluntary" if is_voluntary else "Involuntary",
            overall_score=overall_score,
            overall_band=overall_band,
            dimension_summary="\n\n".join(dim_lines),
        )

        models_to_try = [settings.analysis_model] + [
            m for m in FALLBACK_MODELS if m != settings.analysis_model
        ]

        last_error = None
        for model in models_to_try:
            try:
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as e:
                last_error = e
                if _is_model_unavailable_error(e):
                    logger.warning("Model %s unavailable for narrative, trying next: %s", model, e)
                    continue
                raise

        raise last_error  # type: ignore[misc]

    except Exception:
        logger.exception("Failed to generate pre-termination AI narrative")
        return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_pre_termination_check(
    employee_id: UUID,
    company_id: UUID,
    initiated_by: UUID,
    separation_reason: Optional[str] = None,
    is_voluntary: bool = False,
) -> dict[str, Any]:
    """Run the full 8-dimension pre-termination risk scan.

    Args:
        employee_id: Employee being considered for separation.
        company_id: Company (org) the employee belongs to.
        initiated_by: User ID of the person initiating the check.
        separation_reason: Optional reason for the separation.
        is_voluntary: Whether the separation is voluntary.

    Returns:
        Full risk report as a dict, ready for JSON serialization.
    """
    async with get_connection() as conn:
        # Run all 8 dimension scans in parallel
        results = await asyncio.gather(
            scan_er_cases(employee_id, company_id, conn),
            scan_ir_involvement(employee_id, company_id, conn),
            scan_leave_status(employee_id, conn),
            scan_protected_activity(employee_id, company_id, conn),
            scan_documentation(employee_id, company_id, conn),
            scan_tenure_timing(employee_id, conn),
            scan_consistency(employee_id, company_id, separation_reason, conn),
            scan_manager_profile(employee_id, company_id, conn),
            return_exceptions=True,
        )

        dimension_names = [
            "er_cases",
            "ir_involvement",
            "leave_status",
            "protected_activity",
            "documentation",
            "tenure_timing",
            "consistency",
            "manager_profile",
        ]

        dimensions: dict[str, PreTermDimensionResult] = {}
        for name, result in zip(dimension_names, results):
            if isinstance(result, Exception):
                dimensions[name] = _safe_dimension(name, result)
            else:
                dimensions[name] = result

        # Calculate overall score: sum of dimension scores, normalized 0-100
        total_score = sum(d.score for d in dimensions.values())
        max_possible = 240  # 8 dimensions * 30 points max each
        overall_score = int(total_score / max_possible * 100)
        overall_band = _band(overall_score)

        # Generate recommended actions (rule-based)
        recommended_actions = _generate_recommended_actions(dimensions, overall_band)

        # Generate AI narrative
        ai_narrative = await _generate_ai_narrative(
            employee_id,
            dimensions,
            overall_score,
            overall_band,
            separation_reason,
            is_voluntary,
        )

        requires_acknowledgment = overall_band in ("high", "critical")
        computed_at = _NOW_UTC()

        # Build dimensions JSONB for storage
        dimensions_jsonb = {
            name: asdict(dim) for name, dim in dimensions.items()
        }

        # INSERT into pre_termination_checks table
        check_id = await conn.fetchval(
            """
            INSERT INTO pre_termination_checks (
                employee_id, company_id, initiated_by,
                overall_score, overall_band, dimensions,
                ai_narrative, recommended_actions,
                requires_acknowledgment,
                separation_reason, is_voluntary,
                outcome, computed_at
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8::jsonb, $9, $10, $11, 'pending', $12)
            RETURNING id
            """,
            employee_id,
            company_id,
            initiated_by,
            overall_score,
            overall_band,
            json.dumps(dimensions_jsonb, default=str),
            ai_narrative,
            json.dumps(recommended_actions),
            requires_acknowledgment,
            separation_reason,
            is_voluntary,
            computed_at,
        )

        return {
            "id": str(check_id),
            "employee_id": str(employee_id),
            "company_id": str(company_id),
            "initiated_by": str(initiated_by),
            "overall_score": overall_score,
            "overall_band": overall_band,
            "dimensions": dimensions_jsonb,
            "recommended_actions": recommended_actions,
            "ai_narrative": ai_narrative,
            "requires_acknowledgment": requires_acknowledgment,
            "acknowledged": False,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "acknowledgment_notes": None,
            "offboarding_case_id": None,
            "separation_reason": separation_reason,
            "is_voluntary": is_voluntary,
            "outcome": "pending",
            "computed_at": computed_at.isoformat(),
            "created_at": computed_at.isoformat(),
        }
