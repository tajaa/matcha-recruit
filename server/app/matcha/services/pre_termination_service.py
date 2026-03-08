"""Pre-Termination Risk Check Service.

Scans 9 risk dimensions for an employee before separation to identify
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
9. Retaliation Risk Detection
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
            company_id, containment, ninety_days_ago,
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
            "SELECT email, personal_email FROM employees WHERE id = $1",
            employee_id,
        )
        employee_email = None
        if emp_row:
            employee_email = emp_row["email"] or emp_row.get("personal_email")

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

            # Only flag sick/medical leave as potentially protected (per PRD MVP note)
            protected_types = ("sick", "medical", "fmla", "ada")
            is_protected = row["request_type"] in protected_types

            if row["status"] == "pending" and is_protected:
                pending_requests.append(leave_info)
            elif row["status"] == "approved":
                start = row["start_date"]
                end = row["end_date"]
                if start and end:
                    # Active leave: dates overlap today (only protected types)
                    if is_protected and start <= today <= end:
                        active_leaves.append(leave_info)
                    # Recently returned from sick leave
                    elif (
                        row["request_type"] == "sick"
                        and end < today
                        and end >= sixty_days_ago
                    ):
                        recent_sick_returns.append(leave_info)

        # Red: active protected leave or pending protected request
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
                f"Employee has {len(pending_requests)} pending {pending_requests[0]['request_type']} "
                f"leave request(s) — termination while request pending creates retaliation inference",
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
    """Cross-reference ER complaints, IR reports, and agency charges for protected activity."""
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

            category_lower = (row["category"] or "").lower()
            if role == "complainant" and category_lower in protected_categories:
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

        # Agency charges (EEOC, NLRB, OSHA, etc.)
        agency_charge_signals = []
        resolved_agency_signals = []
        try:
            agency_rows = await conn.fetch(
                """
                SELECT id, charge_type, filing_date, agency_name, status
                FROM agency_charges
                WHERE employee_id = $1 AND company_id = $2
                  AND filing_date > $3
                ORDER BY filing_date DESC
                """,
                employee_id, company_id, twelve_months_ago,
            )

            for row in agency_rows:
                charge_info = {
                    "source": "agency_charge",
                    "charge_id": str(row["id"]),
                    "charge_type": row["charge_type"],
                    "agency_name": row["agency_name"],
                    "filing_date": row["filing_date"].isoformat() if row["filing_date"] else None,
                    "status": row["status"],
                }
                status_lower = (row["status"] or "").lower()
                if status_lower in ("filed", "investigating", "open", "pending"):
                    agency_charge_signals.append(charge_info)
                elif status_lower in ("resolved", "dismissed", "closed"):
                    resolved_agency_signals.append(charge_info)
        except Exception:
            logger.warning("agency_charges table not available — skipping agency charge scan")

        all_signals = (
            agency_charge_signals + complainant_signals
            + ir_reporter_signals + resolved_agency_signals + witness_signals
        )

        # Red (STRONGEST): active agency charge (EEOC, NLRB, OSHA)
        if agency_charge_signals:
            sig = agency_charge_signals[0]
            return _red(
                f"Employee has active {sig['agency_name']} {sig['charge_type']} charge "
                f"(filed {sig['filing_date']}, status: {sig['status']}) — "
                f"STRONGEST protected activity signal, termination creates near-certain retaliation claim",
                signals=all_signals,
                agency_charges_active=len(agency_charge_signals),
                agency_charges_resolved=len(resolved_agency_signals),
                complainant_cases=len(complainant_signals),
                ir_reports=len(ir_reporter_signals),
                witness_involvement=len(witness_signals),
            )

        # Red: filed complaint or safety report in last 12 months
        if complainant_signals:
            sig = complainant_signals[0]
            return _red(
                f"Employee filed complaint as complainant in ER case \"{sig['title']}\" "
                f"({sig['case_number']}) — protected activity under Title VII/SOX",
                signals=all_signals,
                agency_charges_active=0,
                agency_charges_resolved=len(resolved_agency_signals),
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
                agency_charges_active=0,
                agency_charges_resolved=len(resolved_agency_signals),
                complainant_cases=len(complainant_signals),
                ir_reports=len(ir_reporter_signals),
                witness_involvement=len(witness_signals),
            )

        # Yellow: resolved/dismissed agency charge within last 12 months
        if resolved_agency_signals:
            sig = resolved_agency_signals[0]
            return _yellow(
                f"Employee had {sig['agency_name']} {sig['charge_type']} charge "
                f"({sig['status']}) within last 12 months — residual retaliation risk",
                signals=all_signals,
                agency_charges_active=0,
                agency_charges_resolved=len(resolved_agency_signals),
                complainant_cases=0,
                ir_reports=0,
                witness_involvement=len(witness_signals),
            )

        # Yellow: participated as witness
        if witness_signals:
            return _yellow(
                f"Employee participated as witness in {len(witness_signals)} "
                f"investigation(s) in the last 12 months",
                signals=all_signals,
                agency_charges_active=0,
                agency_charges_resolved=0,
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
    """Check performance review existence, recency, scores, and progressive discipline trail."""
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

        now = _NOW_UTC()
        six_months_ago = now - timedelta(days=183)
        twelve_months_ago = now - timedelta(days=365)

        # ------- Progressive discipline check -------
        discipline_records = []
        discipline_trail = None  # None = table missing, [] = no records
        try:
            disc_rows = await conn.fetch(
                """
                SELECT id, discipline_type, issued_date, status, description
                FROM progressive_discipline
                WHERE employee_id = $1 AND company_id = $2
                ORDER BY issued_date DESC
                """,
                employee_id, company_id,
            )
            discipline_records = [
                {
                    "discipline_id": str(r["id"]),
                    "discipline_type": r["discipline_type"],
                    "issued_date": r["issued_date"].isoformat() if r["issued_date"] else None,
                    "status": r["status"],
                    "description": (r["description"] or "")[:200],
                }
                for r in disc_rows
            ]
            discipline_trail = discipline_records
        except Exception:
            logger.warning("progressive_discipline table not available — skipping discipline trail scan")

        # Evaluate discipline trail quality
        has_progressive_path = False
        has_recent_pip = False
        discipline_types_present = set()
        if discipline_trail is not None and discipline_trail:
            for rec in discipline_trail:
                dtype = (rec["discipline_type"] or "").lower()
                discipline_types_present.add(dtype)
                # Check for recent PIP (within 6 months)
                if dtype in ("pip", "performance_improvement_plan"):
                    issued = rec["issued_date"]
                    status = (rec["status"] or "").lower()
                    if issued and status in ("completed", "escalated", "in_progress"):
                        try:
                            issued_dt = datetime.fromisoformat(issued)
                            if issued_dt.tzinfo is None:
                                issued_dt = issued_dt.replace(tzinfo=timezone.utc)
                            if issued_dt >= six_months_ago:
                                has_recent_pip = True
                        except (ValueError, TypeError):
                            pass

            # Check for progressive path: verbal -> written -> PIP
            progressive_steps = {"verbal_warning", "verbal", "written_warning", "written",
                                 "pip", "performance_improvement_plan"}
            steps_present = discipline_types_present & progressive_steps
            # A clear path requires at least 2 different step types
            has_progressive_path = len(steps_present) >= 2

        # ------- Performance reviews -------
        reviews = []
        if table_exists:
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

        # ------- Combined scoring logic -------

        # GREEN: Progressive discipline shows a clear documented trail
        if has_progressive_path or has_recent_pip:
            trail_desc = []
            if has_progressive_path:
                trail_desc.append(f"progressive steps: {', '.join(sorted(discipline_types_present))}")
            if has_recent_pip:
                trail_desc.append("recent PIP on file")
            trail_summary = "; ".join(trail_desc)

            review_info = None
            if reviews:
                latest = reviews[0]
                review_date = latest["completed_at"] or latest["created_at"]
                rating = float(latest["manager_overall_rating"]) if latest["manager_overall_rating"] else None
                review_info = {
                    "review_id": str(latest["id"]),
                    "rating": rating,
                    "review_date": review_date.isoformat() if review_date else None,
                    "total_reviews": len(reviews),
                }

            return _green(
                f"Strong documentation trail — {trail_summary}",
                table_exists=table_exists,
                last_review=review_info,
                discipline_records=discipline_records,
                discipline_trail_quality="strong",
            )

        # From here, no strong discipline trail — fall back to review-based logic
        has_no_reviews = not table_exists or not reviews

        if has_no_reviews:
            # Check if discipline records exist but are incomplete
            if discipline_trail is not None and discipline_trail:
                return _yellow(
                    f"Some discipline records on file ({len(discipline_trail)} record(s)) "
                    f"but incomplete trail (no PIP or progressive path) and no performance reviews",
                    table_exists=table_exists,
                    reviews=[],
                    last_review=None,
                    discipline_records=discipline_records,
                    discipline_trail_quality="incomplete",
                )
            if not table_exists:
                return _red(
                    "No performance review system configured and no discipline records — "
                    "no documentation on file",
                    table_exists=False,
                    reviews=[],
                    discipline_records=discipline_records,
                    discipline_trail_quality="none",
                )
            return _red(
                "No performance reviews on file and no progressive discipline records",
                table_exists=True,
                reviews=[],
                last_review=None,
                discipline_records=discipline_records,
                discipline_trail_quality="none" if discipline_trail is not None else "unknown",
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

        # Red: last review was positive (>= 4.0) with no discipline trail
        if rating is not None and rating >= 4.0:
            discipline_note = ""
            if discipline_trail is not None and discipline_trail:
                discipline_note = (
                    f" (note: {len(discipline_trail)} discipline record(s) on file "
                    f"but incomplete progressive path)"
                )
            return _red(
                f"Last performance review score was {rating:.1f}/5.0 — "
                f"positive review followed by termination is high-risk{discipline_note}",
                table_exists=True,
                last_review=review_info,
                reviews=[{
                    "review_id": str(r["id"]),
                    "rating": float(r["manager_overall_rating"]) if r["manager_overall_rating"] else None,
                    "date": (r["completed_at"] or r["created_at"]).isoformat() if (r["completed_at"] or r["created_at"]) else None,
                } for r in reviews[:5]],
                discipline_records=discipline_records,
                discipline_trail_quality="incomplete" if discipline_trail else "none",
            )

        # Yellow: reviews exist but > 12 months old
        if review_date and review_date < twelve_months_ago:
            months_ago = (now - review_date).days // 30
            discipline_note = ""
            if discipline_trail is not None and discipline_trail:
                discipline_note = f" ({len(discipline_trail)} discipline record(s) on file but incomplete trail)"
            return _yellow(
                f"Last performance review was {months_ago} months ago — "
                f"documentation is stale{discipline_note}",
                table_exists=True,
                last_review=review_info,
                discipline_records=discipline_records,
                discipline_trail_quality="incomplete" if discipline_trail else "none",
            )

        # Green: recent review (< 6 months) with score < 4.0
        if review_date and review_date >= six_months_ago and rating is not None and rating < 4.0:
            discipline_note = ""
            if discipline_trail is not None and discipline_trail:
                discipline_note = f" (plus {len(discipline_trail)} discipline record(s))"
            return _green(
                f"Recent performance review ({review_date.strftime('%Y-%m-%d')}) "
                f"with score {rating:.1f}/5.0 supports documented performance concerns{discipline_note}",
                table_exists=True,
                last_review=review_info,
                discipline_records=discipline_records,
                discipline_trail_quality="incomplete" if discipline_trail else "none",
            )

        # Yellow: reviews exist but between 6-12 months old, or rating is None
        if review_date and review_date < six_months_ago:
            months_ago = (now - review_date).days // 30
            return _yellow(
                f"Last performance review was {months_ago} months ago",
                table_exists=True,
                last_review=review_info,
                discipline_records=discipline_records,
                discipline_trail_quality="incomplete" if discipline_trail else "none",
            )

        # Default green for cases with recent review and no clear issue
        return _green(
            f"Performance review documentation exists (most recent: "
            f"{review_date.strftime('%Y-%m-%d') if review_date else 'unknown'})",
            table_exists=True,
            last_review=review_info,
            discipline_records=discipline_records,
            discipline_trail_quality="incomplete" if (discipline_trail is not None and discipline_trail) else "none",
        )

    except Exception as exc:
        return _safe_dimension("documentation", exc)


# ---------------------------------------------------------------------------
# Dimension 6: Tenure & Timing
# ---------------------------------------------------------------------------

async def scan_tenure_timing(
    employee_id: UUID, company_id: UUID, conn,
) -> PreTermDimensionResult:
    """Evaluate risk based on employee tenure length and benefit vesting proximity."""
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
                vesting_risks=[],
            )

        start_date = row["start_date"]
        if isinstance(start_date, datetime):
            start_date = start_date.date()

        today = date.today()
        tenure_days = (today - start_date).days
        tenure_years = round(tenure_days / 365.25, 2)

        # ------- Vesting schedule check -------
        vesting_risks = []
        approaching_6mo = []  # within 6 months of vesting
        approaching_12mo = []  # within 12 months of vesting
        try:
            company_row = await conn.fetchrow(
                "SELECT vesting_schedules FROM companies WHERE id = $1",
                company_id,
            )
            if company_row and company_row["vesting_schedules"]:
                vesting_raw = company_row["vesting_schedules"]
                if isinstance(vesting_raw, str):
                    vesting_schedules = json.loads(vesting_raw)
                else:
                    vesting_schedules = vesting_raw

                if isinstance(vesting_schedules, list):
                    for schedule in vesting_schedules:
                        if not isinstance(schedule, dict):
                            continue
                        vest_years = schedule.get("vesting_years")
                        if vest_years is None:
                            continue
                        try:
                            vest_years = float(vest_years)
                        except (ValueError, TypeError):
                            continue

                        gap = vest_years - tenure_years
                        vest_info = {
                            "type": schedule.get("type", "unknown"),
                            "vesting_years": vest_years,
                            "description": schedule.get("description", ""),
                            "gap_years": round(gap, 2),
                        }

                        if 0 < gap <= 0.5:
                            # Within 6 months of vesting milestone
                            approaching_6mo.append(vest_info)
                        elif 0 < gap <= 1.0:
                            # Within 12 months of vesting milestone
                            approaching_12mo.append(vest_info)

                        if 0 < gap <= 1.0:
                            vesting_risks.append(vest_info)
        except Exception:
            logger.warning("Could not query companies.vesting_schedules — skipping vesting check")

        details = {
            "tenure_years": tenure_years,
            "start_date": start_date.isoformat(),
            "tenure_days": tenure_days,
            "vesting_risks": vesting_risks,
        }

        # Red: tenure > 10 years OR termination within 6 months of vesting milestone
        if approaching_6mo:
            vest = approaching_6mo[0]
            return _red(
                f"Employee tenure: {tenure_years} years — termination is within "
                f"{vest['gap_years']} years of {vest['type']} vesting milestone "
                f"({vest['vesting_years']} years) — creates strong inference of "
                f"benefit-motivated termination",
                **details,
                approaching_vesting_6mo=[v["type"] for v in approaching_6mo],
            )

        if tenure_years > 10:
            return _red(
                f"Employee tenure: {tenure_years} years — long-tenured employees "
                f"generate significantly higher jury verdicts and sympathy damages",
                **details,
            )

        # Yellow: tenure 5-10 years OR approaching vesting within 12 months
        if approaching_12mo:
            vest = approaching_12mo[0]
            return _yellow(
                f"Employee tenure: {tenure_years} years — approaching "
                f"{vest['type']} vesting milestone ({vest['vesting_years']} years) "
                f"within {vest['gap_years']} years — monitor for benefit-timing risk",
                **details,
                approaching_vesting_12mo=[v["type"] for v in approaching_12mo],
            )

        if tenure_years >= 5:
            return _yellow(
                f"Employee tenure: {tenure_years} years — moderate tenure "
                f"increases potential damages in wrongful termination claims",
                **details,
            )

        # Green: tenure < 5 years with no approaching milestones
        return _green(
            f"Employee tenure: {tenure_years} years",
            **details,
        )

    except Exception as exc:
        return _safe_dimension("tenure_timing", exc)


# ---------------------------------------------------------------------------
# Dimension 7: Consistency Check
# ---------------------------------------------------------------------------

def _compute_kish_effective_n(weights: list[float]) -> float:
    """Kish effective sample size: (sum w_i)^2 / sum(w_i^2)."""
    if not weights:
        return 0.0
    sum_w = sum(weights)
    sum_w2 = sum(w * w for w in weights)
    if sum_w2 == 0:
        return 0.0
    return (sum_w * sum_w) / sum_w2


async def scan_consistency(
    employee_id: UUID,
    company_id: UUID,
    separation_reason: Optional[str],
    conn,
) -> PreTermDimensionResult:
    """Compare this termination to similar past cases using weighted precedent matching."""
    try:
        if not separation_reason:
            return _yellow(
                "No separation reason provided — unable to assess consistency",
                comparable_cases=0,
                effective_n=0.0,
            )

        # Get the current employee's context for similarity matching
        emp_row = await conn.fetchrow(
            "SELECT department, title, start_date FROM employees WHERE id = $1",
            employee_id,
        )
        current_department = emp_row["department"] if emp_row else None
        current_title = emp_row["title"] if emp_row else None
        current_start_date = emp_row["start_date"] if emp_row else None

        current_tenure_years = None
        if current_start_date:
            sd = current_start_date
            if isinstance(sd, datetime):
                sd = sd.date()
            current_tenure_years = (date.today() - sd).days / 365.25

        now = _NOW_UTC()
        twelve_months_ago = now - timedelta(days=365)

        # Query historical offboarding cases for the same company
        try:
            cases = await conn.fetch(
                """
                SELECT oc.id, oc.reason, oc.is_voluntary, oc.created_at, oc.status,
                       e.department, e.title, e.start_date,
                       EXTRACT(YEAR FROM AGE(oc.created_at, e.start_date)) as tenure_years
                FROM offboarding_cases oc
                JOIN employees e ON e.id = oc.employee_id
                WHERE oc.org_id = $1 AND oc.status = 'completed'
                  AND oc.employee_id != $2
                ORDER BY oc.created_at DESC
                LIMIT 50
                """,
                company_id, employee_id,
            )
        except Exception:
            logger.warning("Error querying offboarding_cases for consistency — falling back")
            return _yellow(
                "Unable to query offboarding history for consistency analysis",
                comparable_cases=0,
                effective_n=0.0,
                error="offboarding_cases query failed",
            )

        if not cases:
            return _yellow(
                "No prior completed offboarding cases found — insufficient data for consistency analysis",
                comparable_cases=0,
                effective_n=0.0,
            )

        # Compute similarity scores for each historical case
        reason_lower = separation_reason.lower()
        reason_keywords = set(reason_lower.split())
        stop_words = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "is", "was", "not"}
        reason_keywords -= stop_words

        scored_cases = []
        for case in cases:
            similarity = 0.0

            # Same department: +0.3
            case_dept = case.get("department")
            if current_department and case_dept and current_department.lower() == case_dept.lower():
                similarity += 0.3

            # Similar reason (keyword overlap): +0.3
            case_reason = (case["reason"] or "").lower()
            if case_reason and reason_keywords:
                case_words = set(case_reason.split()) - stop_words
                if case_words:
                    overlap = reason_keywords & case_words
                    overlap_ratio = len(overlap) / max(len(reason_keywords), 1)
                    if overlap_ratio > 0:
                        similarity += 0.3 * min(overlap_ratio * 2, 1.0)

            # Similar tenure (within 2 years): +0.2
            case_tenure = case.get("tenure_years")
            if current_tenure_years is not None and case_tenure is not None:
                try:
                    case_tenure_f = float(case_tenure)
                    tenure_diff = abs(current_tenure_years - case_tenure_f)
                    if tenure_diff <= 2.0:
                        similarity += 0.2 * (1.0 - tenure_diff / 2.0)
                except (ValueError, TypeError):
                    pass

            # Recent (within last 12 months): +0.2
            case_created = case["created_at"]
            if case_created:
                if case_created.tzinfo is None:
                    case_created = case_created.replace(tzinfo=timezone.utc)
                if case_created >= twelve_months_ago:
                    similarity += 0.2

            if similarity >= 0.3:
                scored_cases.append({
                    "case_id": str(case["id"]),
                    "reason": case["reason"],
                    "is_voluntary": case["is_voluntary"],
                    "status": case["status"],
                    "department": case.get("department"),
                    "title": case.get("title"),
                    "tenure_years": float(case["tenure_years"]) if case.get("tenure_years") is not None else None,
                    "created_at": case["created_at"].isoformat() if case["created_at"] else None,
                    "similarity_score": round(similarity, 3),
                })

        # Compute Kish effective N from similarity weights
        weights = [c["similarity_score"] for c in scored_cases]
        effective_n = round(_compute_kish_effective_n(weights), 2)

        comparable_count = len(scored_cases)

        if comparable_count < 3 or effective_n < 3:
            return _yellow(
                f"Insufficient comparable data for consistency analysis "
                f"({comparable_count} similar case(s), effective N = {effective_n}, "
                f"minimum 3 required)",
                comparable_cases=comparable_count,
                effective_n=effective_n,
                minimum_required=3,
                similar_cases=scored_cases[:5],
            )

        # With effective N >= 2, check if similar employees were given warnings
        # instead of terminated (is_voluntary=true or non-completed status would
        # indicate different treatment)
        # In completed offboarding cases, is_voluntary=false means involuntary term.
        # If we find similar cases where the outcome was voluntary or
        # the reason is similar but it wasn't involuntary, that's inconsistent.
        involuntary_terms = [c for c in scored_cases if c["is_voluntary"] is False]
        voluntary_or_other = [c for c in scored_cases if c["is_voluntary"] is not False]

        if voluntary_or_other:
            # Some similar situations had different outcomes
            inconsistent_pct = len(voluntary_or_other) / comparable_count * 100
            return _red(
                f"Inconsistent treatment detected — {len(voluntary_or_other)} of "
                f"{comparable_count} comparable cases (effective N = {effective_n}) "
                f"had different outcomes ({inconsistent_pct:.0f}% non-involuntary) — "
                f"disparate treatment risk",
                comparable_cases=comparable_count,
                effective_n=effective_n,
                similar_cases=scored_cases[:5],
                involuntary_count=len(involuntary_terms),
                non_involuntary_count=len(voluntary_or_other),
            )

        # All similar cases also resulted in involuntary termination
        return _green(
            f"Treatment is consistent with {comparable_count} similar prior cases "
            f"(effective N = {effective_n})",
            comparable_cases=comparable_count,
            effective_n=effective_n,
            similar_cases=scored_cases[:5],
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
# Dimension 9: Retaliation Risk Detection
# ---------------------------------------------------------------------------

async def scan_retaliation_risk(
    employee_id: UUID, company_id: UUID, conn,
) -> PreTermDimensionResult:
    """Detect retaliation risk: adverse actions occurring shortly after protected activity."""
    try:
        now = _NOW_UTC()
        twelve_months_ago = now - timedelta(days=365)

        # Get employee's email for reporter matching
        emp_row = await conn.fetchrow(
            "SELECT email, personal_email FROM employees WHERE id = $1",
            employee_id,
        )
        employee_email = None
        if emp_row:
            employee_email = emp_row["email"] or emp_row.get("personal_email")

        # ---------------------------------------------------------------
        # Collect protected activity events (last 12 months)
        # ---------------------------------------------------------------
        protected_events: list[dict[str, Any]] = []

        # IR incidents where employee is the reporter
        if employee_email:
            ir_rows = await conn.fetch(
                """
                SELECT id, incident_number, title, occurred_at
                FROM ir_incidents
                WHERE company_id = $1
                  AND reported_by_email = $2
                  AND occurred_at >= $3
                ORDER BY occurred_at DESC
                """,
                company_id, employee_email, twelve_months_ago,
            )
            for row in ir_rows:
                evt_date = row["occurred_at"]
                if evt_date:
                    if evt_date.tzinfo is None:
                        evt_date = evt_date.replace(tzinfo=timezone.utc)
                    protected_events.append({
                        "type": "ir_report",
                        "date": evt_date,
                        "label": f"IR report \"{row['title']}\" ({row['incident_number']})",
                    })

        # ER cases where employee is complainant
        containment = json.dumps([{"employee_id": str(employee_id)}])
        er_rows = await conn.fetch(
            """
            SELECT id, case_number, title, category, created_at,
                   involved_employees
            FROM er_cases
            WHERE company_id = $1
              AND involved_employees @> $2::jsonb
              AND created_at >= $3
            ORDER BY created_at DESC
            """,
            company_id, containment, twelve_months_ago,
        )
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

            if role == "complainant":
                evt_date = row["created_at"]
                if evt_date:
                    if evt_date.tzinfo is None:
                        evt_date = evt_date.replace(tzinfo=timezone.utc)
                    protected_events.append({
                        "type": "er_complaint",
                        "date": evt_date,
                        "label": f"ER complaint \"{row['title']}\" ({row['case_number']})",
                    })

        # Agency charges
        try:
            agency_rows = await conn.fetch(
                """
                SELECT id, charge_type, agency_name, filing_date
                FROM agency_charges
                WHERE employee_id = $1 AND company_id = $2
                  AND filing_date > $3
                ORDER BY filing_date DESC
                """,
                employee_id, company_id, twelve_months_ago,
            )
            for row in agency_rows:
                evt_date = row["filing_date"]
                if evt_date:
                    if isinstance(evt_date, date) and not isinstance(evt_date, datetime):
                        evt_date = datetime.combine(evt_date, datetime.min.time(), tzinfo=timezone.utc)
                    elif evt_date.tzinfo is None:
                        evt_date = evt_date.replace(tzinfo=timezone.utc)
                    protected_events.append({
                        "type": "agency_charge",
                        "date": evt_date,
                        "label": f"{row['agency_name']} {row['charge_type']} charge",
                    })
        except Exception:
            logger.warning("agency_charges table not available — skipping agency charge scan for retaliation")

        # ---------------------------------------------------------------
        # Collect adverse action events (last 12 months)
        # ---------------------------------------------------------------
        adverse_events: list[dict[str, Any]] = []

        # Progressive discipline
        try:
            disc_rows = await conn.fetch(
                """
                SELECT id, discipline_type, issued_date
                FROM progressive_discipline
                WHERE employee_id = $1 AND company_id = $2
                  AND issued_date >= $3
                ORDER BY issued_date DESC
                """,
                employee_id, company_id, twelve_months_ago,
            )
            for row in disc_rows:
                evt_date = row["issued_date"]
                if evt_date:
                    if isinstance(evt_date, date) and not isinstance(evt_date, datetime):
                        evt_date = datetime.combine(evt_date, datetime.min.time(), tzinfo=timezone.utc)
                    elif evt_date.tzinfo is None:
                        evt_date = evt_date.replace(tzinfo=timezone.utc)
                    adverse_events.append({
                        "type": "discipline",
                        "date": evt_date,
                        "label": f"Discipline: {row['discipline_type']}",
                    })
        except Exception:
            logger.warning("progressive_discipline table not available — skipping discipline scan for retaliation")

        # Involuntary offboarding cases
        try:
            offb_rows = await conn.fetch(
                """
                SELECT id, started_at
                FROM offboarding_cases
                WHERE employee_id = $1 AND is_voluntary = false
                  AND started_at >= $2
                ORDER BY started_at DESC
                """,
                employee_id, twelve_months_ago,
            )
            for row in offb_rows:
                evt_date = row["started_at"]
                if evt_date:
                    if evt_date.tzinfo is None:
                        evt_date = evt_date.replace(tzinfo=timezone.utc)
                    adverse_events.append({
                        "type": "involuntary_offboarding",
                        "date": evt_date,
                        "label": "Involuntary termination initiated",
                    })
        except Exception:
            logger.warning("offboarding_cases query failed — skipping offboarding scan for retaliation")

        # ---------------------------------------------------------------
        # Temporal proximity analysis
        # ---------------------------------------------------------------
        if not protected_events or not adverse_events:
            return _green(
                "No temporal overlap between protected activity and adverse actions",
                protected_events_count=len(protected_events),
                adverse_events_count=len(adverse_events),
                timeline=[],
            )

        timeline: list[dict[str, Any]] = []
        closest_days: int | None = None
        closest_entry: dict[str, Any] | None = None

        for pe in protected_events:
            pe_date = pe["date"]
            for ae in adverse_events:
                ae_date = ae["date"]
                # Only consider adverse actions AFTER the protected event
                delta = ae_date - pe_date
                days_between = delta.days
                if days_between < 0:
                    continue

                entry = {
                    "protected_event_type": pe["type"],
                    "protected_event_date": pe_date.isoformat(),
                    "protected_event_label": pe["label"],
                    "adverse_event_type": ae["type"],
                    "adverse_event_date": ae_date.isoformat(),
                    "adverse_event_label": ae["label"],
                    "days_between": days_between,
                }
                timeline.append(entry)

                if closest_days is None or days_between < closest_days:
                    closest_days = days_between
                    closest_entry = entry

        if not timeline:
            return _green(
                "No adverse actions occurred after protected activity events",
                protected_events_count=len(protected_events),
                adverse_events_count=len(adverse_events),
                timeline=[],
            )

        # Sort timeline by days_between ascending
        timeline.sort(key=lambda x: x["days_between"])

        # Red: any adverse action within 90 days of protected activity
        if closest_days is not None and closest_days <= 90:
            return _red(
                f"{closest_entry['adverse_event_label']} {closest_days} days after "
                f"{closest_entry['protected_event_type']} — high retaliation inference",
                timeline=timeline[:10],
                closest_days=closest_days,
                protected_events_count=len(protected_events),
                adverse_events_count=len(adverse_events),
            )

        # Yellow: any adverse action within 91-180 days
        if closest_days is not None and closest_days <= 180:
            return _yellow(
                f"{closest_entry['adverse_event_label']} {closest_days} days after "
                f"{closest_entry['protected_event_type']} — moderate retaliation inference",
                timeline=timeline[:10],
                closest_days=closest_days,
                protected_events_count=len(protected_events),
                adverse_events_count=len(adverse_events),
            )

        # Green: no temporal overlap within 180 days
        return _green(
            "No adverse actions within 180 days of protected activity",
            timeline=timeline[:10],
            closest_days=closest_days,
            protected_events_count=len(protected_events),
            adverse_events_count=len(adverse_events),
        )

    except Exception as exc:
        return _safe_dimension("retaliation_risk", exc)


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

    retaliation = dimensions.get("retaliation_risk")
    if retaliation and retaliation.status == "red":
        actions.append(
            "Adverse action occurred within 90 days of protected activity — "
            "strong temporal proximity creates prima facie retaliation inference. "
            "Consult employment counsel before proceeding"
        )
    elif retaliation and retaliation.status == "yellow":
        actions.append(
            "Adverse action occurred within 180 days of protected activity — "
            "document legitimate non-retaliatory business reasons thoroughly"
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
    """Run the full 9-dimension pre-termination risk scan.

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
        # Run dimension scans sequentially — asyncpg connections
        # do not support concurrent operations on the same connection.
        scan_specs = [
            ("er_cases", scan_er_cases(employee_id, company_id, conn)),
            ("ir_involvement", scan_ir_involvement(employee_id, company_id, conn)),
            ("leave_status", scan_leave_status(employee_id, conn)),
            ("protected_activity", scan_protected_activity(employee_id, company_id, conn)),
            ("documentation", scan_documentation(employee_id, company_id, conn)),
            ("tenure_timing", scan_tenure_timing(employee_id, company_id, conn)),
            ("consistency", scan_consistency(employee_id, company_id, separation_reason, conn)),
            ("manager_profile", scan_manager_profile(employee_id, company_id, conn)),
            ("retaliation_risk", scan_retaliation_risk(employee_id, company_id, conn)),
        ]

        dimensions: dict[str, PreTermDimensionResult] = {}
        for name, coro in scan_specs:
            try:
                dimensions[name] = await coro
            except Exception as exc:
                dimensions[name] = _safe_dimension(name, exc)

        # Calculate overall score: sum of dimension scores, normalized 0-100
        total_score = sum(d.score for d in dimensions.values())
        max_possible = 270  # 9 dimensions * 30 points max each
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
