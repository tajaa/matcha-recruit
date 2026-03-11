"""
Leave Eligibility Service — checks FMLA and state leave program eligibility.

Reads leave program data from jurisdiction_requirements (category='leave'),
which is the unified compliance/jurisdictions system.
"""
import json
import logging
from datetime import datetime, date, timedelta
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)

# Whether the leave data backfill has been verified this process lifetime
_leave_data_checked = False


class LeaveEligibilityService:
    """Checks employee eligibility for federal and state leave programs."""

    @staticmethod
    def _estimate_weekly_hours(emp) -> tuple[float | None, str | None]:
        employment_type = (emp.get("employment_type") or "").strip().lower()
        pay_classification = (emp.get("pay_classification") or "").strip().lower()

        if employment_type == "full_time" and pay_classification == "exempt":
            return 40.0, "Estimated using 40 hours/week for a full-time exempt employee because no time records were found."
        if employment_type == "full_time":
            return 30.0, "Estimated using 30 hours/week for a full-time employee because no time records were found."
        if employment_type == "part_time":
            return 20.0, "Estimated using 20 hours/week for a part-time employee because no time records were found."
        return None, None

    @classmethod
    def _estimate_hours_worked(
        cls,
        emp,
        *,
        today: date,
        twelve_months_ago: date,
    ) -> tuple[float | None, float | None, str | None]:
        if not emp.get("start_date"):
            return None, None, None

        weekly_hours, note = cls._estimate_weekly_hours(emp)
        if weekly_hours is None:
            return None, None, None

        window_start = max(emp["start_date"], twelve_months_ago)
        active_days = max((today - window_start).days, 0)
        weeks_in_window = min(active_days / 7.0, 52.0)
        return weekly_hours * weeks_in_window, weekly_hours, note

    @classmethod
    async def _get_hours_worked_snapshot(
        cls,
        conn,
        employee_id: UUID,
        emp,
        *,
        today: date,
    ) -> dict:
        twelve_months_ago = today - timedelta(days=365)

        try:
            hours_row = await conn.fetchrow(
                """SELECT COALESCE(SUM(hours_worked), 0) AS total_hours,
                          COUNT(*) AS entry_count
                   FROM employee_hours_log
                   WHERE employee_id = $1
                     AND period_start >= $2""",
                employee_id, twelve_months_ago,
            )
            entry_count = int(hours_row["entry_count"] or 0)
            total_hours = float(hours_row["total_hours"] or 0.0)
        except Exception:
            logger.warning("employee_hours_log query failed for %s — falling back to estimated hours", employee_id)
            entry_count = 0
            total_hours = 0.0

        if entry_count > 0:
            return {
                "hours": total_hours,
                "source": "logged",
                "assumed_weekly_hours": None,
                "note": "Based on recorded hours in the past 12 months.",
            }

        estimated_hours, assumed_weekly_hours, note = cls._estimate_hours_worked(
            emp,
            today=today,
            twelve_months_ago=twelve_months_ago,
        )
        if estimated_hours is not None:
            return {
                "hours": estimated_hours,
                "source": "estimated",
                "assumed_weekly_hours": assumed_weekly_hours,
                "note": note,
            }

        return {
            "hours": total_hours,
            "source": "missing",
            "assumed_weekly_hours": None,
            "note": "No time records were found and Matcha could not estimate hours from the employee classification.",
        }

    async def check_fmla_eligibility(self, employee_id: UUID) -> dict:
        """
        Federal FMLA check:
        - 12+ months tenure
        - 1,250+ hours in last 12 months
        - 50+ active employees in company
        """
        async with get_connection() as conn:
            emp = await conn.fetchrow(
                """SELECT id, org_id, start_date, work_state, employment_type, pay_classification
                   FROM employees
                   WHERE id = $1""",
                employee_id,
            )
            if not emp:
                return {"eligible": False, "reasons": ["Employee not found"]}

            reasons = []
            today = date.today()

            # Tenure check
            months_employed = None
            if emp["start_date"]:
                delta = today - emp["start_date"]
                months_employed = delta.days / 30.44  # average days per month
                if months_employed < 12:
                    reasons.append(
                        f"Less than 12 months tenure ({months_employed:.1f} months)"
                    )
            else:
                reasons.append("No start date on record")

            # Hours check (last 12 months)
            hours_snapshot = await self._get_hours_worked_snapshot(
                conn,
                employee_id,
                emp,
                today=today,
            )
            hours_worked_12mo = hours_snapshot["hours"]
            if hours_worked_12mo < 1250:
                reasons.append(
                    f"Less than 1,250 hours in past 12 months ({hours_worked_12mo:.0f} hours)"
                )

            # Company size check (50+ active employees)
            company_count = await conn.fetchval(
                """SELECT COUNT(*) FROM employees
                   WHERE org_id = $1 AND termination_date IS NULL""",
                emp["org_id"],
            )
            if company_count < 50:
                reasons.append(
                    f"Employer has fewer than 50 employees ({company_count})"
                )

            eligible = len(reasons) == 0

            return {
                "program": "fmla",
                "label": "Family and Medical Leave Act (FMLA)",
                "eligible": eligible,
                "reasons": reasons if not eligible else ["Meets all FMLA requirements"],
                "months_employed": round(months_employed, 1) if months_employed else None,
                "hours_worked_12mo": round(hours_worked_12mo, 1),
                "hours_worked_12mo_source": hours_snapshot["source"],
                "hours_worked_assumed_weekly": hours_snapshot["assumed_weekly_hours"],
                "hours_worked_note": hours_snapshot["note"],
                "company_employee_count": company_count,
            }

    @staticmethod
    def _parse_leave_meta(description: str | None, current_value: str | None = None) -> dict:
        """Parse JSON metadata from jurisdiction_requirements.description.

        Falls back to current_value for rows written before the column switch.
        """
        for field in (description, current_value):
            if not field or not isinstance(field, str):
                continue
            try:
                parsed = json.loads(field)
                if isinstance(parsed, dict) and parsed:
                    return parsed
            except (json.JSONDecodeError, TypeError):
                continue
        return {}

    async def check_state_programs(self, employee_id: UUID) -> dict:
        """
        Look up employee.work_state in jurisdiction_requirements (category='leave').
        Falls back to leave_jurisdiction_rules if no data in jurisdictions system.
        """
        async with get_connection() as conn:
            emp = await conn.fetchrow(
                """SELECT id, org_id, start_date, work_state, employment_type, pay_classification
                   FROM employees
                   WHERE id = $1""",
                employee_id,
            )
            if not emp:
                return {"state": None, "programs": []}

            work_state = (emp["work_state"] or "").upper().strip()
            if not work_state:
                return {"state": None, "programs": [], "message": "No work state on record"}

            # Query jurisdiction_requirements for leave programs
            rules = await conn.fetch(
                """SELECT jr.requirement_key, jr.title, jr.description,
                          jr.current_value, jr.numeric_value, jr.source_url
                   FROM jurisdiction_requirements jr
                   JOIN jurisdictions j ON jr.jurisdiction_id = j.id
                   WHERE j.state = $1 AND j.city = ''
                     AND jr.category = 'leave'
                   ORDER BY jr.requirement_key""",
                work_state,
            )

            if not rules:
                return {"state": work_state, "programs": [], "message": "No state programs found"}

            today = date.today()

            # Pre-calculate employee data
            months_employed = None
            if emp["start_date"]:
                delta = today - emp["start_date"]
                months_employed = delta.days / 30.44

            hours_snapshot = await self._get_hours_worked_snapshot(
                conn,
                employee_id,
                emp,
                today=today,
            )
            hours_worked = hours_snapshot["hours"]

            company_count = await conn.fetchval(
                """SELECT COUNT(*) FROM employees
                   WHERE org_id = $1 AND termination_date IS NULL""",
                emp["org_id"],
            )

            programs = []
            for rule in rules:
                meta = self._parse_leave_meta(rule["description"], rule["current_value"])
                reasons = []
                eligible = True

                emp_min = meta.get("emp_min")
                tenure_mo = meta.get("tenure_mo")
                hrs_min = meta.get("hrs_min")

                # Employer size threshold
                if emp_min and company_count < emp_min:
                    eligible = False
                    reasons.append(
                        f"Employer has {company_count} employees "
                        f"(minimum {emp_min})"
                    )

                # Tenure threshold
                if tenure_mo:
                    if months_employed is None:
                        eligible = False
                        reasons.append("No start date on record")
                    elif months_employed < tenure_mo:
                        eligible = False
                        reasons.append(
                            f"{months_employed:.1f} months tenure "
                            f"(minimum {tenure_mo})"
                        )

                # Hours threshold
                if hrs_min:
                    if hours_worked < hrs_min:
                        eligible = False
                        reasons.append(
                            f"{hours_worked:.0f} hours worked "
                            f"(minimum {hrs_min})"
                        )

                if eligible:
                    reasons = ["Meets program requirements"]

                paid = meta.get("paid", False)
                max_weeks = meta.get("max_weeks") or (int(rule["numeric_value"]) if rule["numeric_value"] else None)
                wage_pct = meta.get("wage_pct")

                programs.append({
                    "program": rule["requirement_key"],
                    "label": rule["title"],
                    "eligible": eligible,
                    "paid": paid,
                    "max_weeks": max_weeks,
                    "wage_replacement_pct": float(wage_pct) if wage_pct else None,
                    "job_protection": meta.get("job_prot", False),
                    "reasons": reasons,
                    "notes": rule["description"],
                    "source_url": rule["source_url"],
                })

            return {
                "state": work_state,
                "programs": programs,
                "hours_worked_12mo": round(hours_worked, 1),
                "hours_worked_12mo_source": hours_snapshot["source"],
                "hours_worked_assumed_weekly": hours_snapshot["assumed_weekly_hours"],
                "hours_worked_note": hours_snapshot["note"],
            }

    @staticmethod
    async def ensure_leave_data():
        """Lazily backfill leave data from leave_jurisdiction_rules into
        jurisdiction_requirements if no leave rows exist yet.  Runs once per
        process lifetime."""
        global _leave_data_checked
        if _leave_data_checked:
            return
        _leave_data_checked = True

        try:
            async with get_connection() as conn:
                has_leave = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM jurisdiction_requirements WHERE category = 'leave')"
                )
                if has_leave:
                    return

                # Check if source table exists
                has_source = await conn.fetchval(
                    "SELECT to_regclass('public.leave_jurisdiction_rules') IS NOT NULL"
                )
                if not has_source:
                    logger.info("No leave_jurisdiction_rules table — skipping backfill")
                    return

                # Ensure state-level jurisdiction rows exist
                await conn.execute("""
                    INSERT INTO jurisdictions (city, state)
                    SELECT DISTINCT '', UPPER(ljr.state)
                    FROM leave_jurisdiction_rules ljr
                    WHERE ljr.state != 'US'
                    ON CONFLICT (city, state) DO NOTHING
                """)

                await conn.execute("""
                    INSERT INTO jurisdiction_requirements
                        (jurisdiction_id, requirement_key, category,
                         jurisdiction_level, jurisdiction_name,
                         title, description, current_value, numeric_value,
                         source_url, last_verified_at)
                    SELECT
                        j.id,
                        ljr.leave_program,
                        'leave',
                        CASE WHEN ljr.state = 'US' THEN 'federal' ELSE 'state' END,
                        CASE WHEN ljr.state = 'US' THEN 'Federal' ELSE ljr.state END,
                        ljr.program_label,
                        json_build_object(
                            'paid', ljr.paid,
                            'max_weeks', ljr.max_weeks,
                            'wage_pct', ljr.wage_replacement_pct,
                            'job_prot', ljr.job_protection,
                            'emp_min', ljr.employer_size_threshold,
                            'tenure_mo', ljr.employee_tenure_months,
                            'hrs_min', ljr.employee_hours_threshold
                        )::TEXT,
                        LEFT(
                            CONCAT_WS(', ',
                                CASE WHEN ljr.max_weeks IS NOT NULL
                                     THEN ljr.max_weeks || ' weeks' END,
                                CASE WHEN ljr.wage_replacement_pct IS NOT NULL
                                     THEN ljr.wage_replacement_pct || '% pay' END,
                                CASE WHEN ljr.job_protection THEN 'job protected' END,
                                CASE WHEN ljr.paid THEN 'paid' END
                            ), 100
                        ),
                        ljr.max_weeks,
                        ljr.source_url,
                        COALESCE(ljr.last_verified_at, NOW())
                    FROM leave_jurisdiction_rules ljr
                    JOIN jurisdictions j ON j.state = UPPER(ljr.state) AND j.city = ''
                    WHERE ljr.state != 'US'
                    ON CONFLICT (jurisdiction_id, requirement_key) DO NOTHING
                """)
                logger.info("Backfilled leave data from leave_jurisdiction_rules → jurisdiction_requirements")
        except Exception:
            logger.exception("Failed to ensure leave data — eligibility may be incomplete")

    async def get_eligibility_summary(self, employee_id: UUID) -> dict:
        """
        Combines FMLA + state programs into one response.
        """
        await self.ensure_leave_data()
        fmla = await self.check_fmla_eligibility(employee_id)
        state = await self.check_state_programs(employee_id)

        return {
            "fmla": fmla,
            "state_programs": state,
            "checked_at": datetime.utcnow().isoformat(),
        }

    async def get_job_protection_summary(self, employee_id: UUID) -> dict:
        """
        Returns remaining job-protected weeks for an employee across all qualifying programs,
        accounting for leave already taken.
        """
        summary = await self.get_eligibility_summary(employee_id)

        fmla_protected = 12 if summary["fmla"]["eligible"] else 0

        state_protected = 0
        qualifying_state_programs = []
        for prog in summary["state_programs"].get("programs", []):
            if prog["eligible"] and prog["job_protection"] and prog.get("max_weeks"):
                state_protected = max(state_protected, prog["max_weeks"])
                qualifying_state_programs.append(prog["program"])

        total_protected = fmla_protected + state_protected

        # Calculate weeks already used from approved/active/completed leaves
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(
                    (COALESCE(actual_return_date, end_date, expected_return_date, CURRENT_DATE) - start_date) / 7.0
                ), 0) AS weeks_used
                FROM leave_requests
                WHERE employee_id = $1
                  AND status IN ('approved', 'active', 'completed')
                """,
                employee_id,
            )
            weeks_used = float(row["weeks_used"])

        remaining = max(0.0, total_protected - weeks_used)

        return {
            "fmla_protected_weeks": fmla_protected,
            "state_protected_weeks": state_protected,
            "total_protected_weeks": total_protected,
            "weeks_used": round(weeks_used, 1),
            "weeks_remaining": round(remaining, 1),
            "qualifying_state_programs": qualifying_state_programs,
        }
