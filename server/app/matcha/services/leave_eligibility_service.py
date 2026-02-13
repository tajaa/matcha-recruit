"""
Leave Eligibility Service — checks FMLA and state leave program eligibility.

Self-contained: reads from employees, employee_hours_log, leave_jurisdiction_rules.
No imports from core compliance modules.
"""
import logging
from datetime import datetime, date, timedelta
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


class LeaveEligibilityService:
    """Checks employee eligibility for federal and state leave programs."""

    async def check_fmla_eligibility(self, employee_id: UUID) -> dict:
        """
        Federal FMLA check:
        - 12+ months tenure
        - 1,250+ hours in last 12 months
        - 50+ active employees in company
        """
        async with get_connection() as conn:
            emp = await conn.fetchrow(
                "SELECT id, org_id, start_date, work_state FROM employees WHERE id = $1",
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
            twelve_months_ago = today - timedelta(days=365)
            hours_row = await conn.fetchrow(
                """SELECT COALESCE(SUM(hours_worked), 0) AS total_hours
                   FROM employee_hours_log
                   WHERE employee_id = $1
                     AND period_start >= $2""",
                employee_id, twelve_months_ago,
            )
            hours_worked_12mo = float(hours_row["total_hours"])
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
                "company_employee_count": company_count,
            }

    async def check_state_programs(self, employee_id: UUID) -> dict:
        """
        Look up employee.work_state in leave_jurisdiction_rules.
        For each matching program, check employee against thresholds.
        """
        async with get_connection() as conn:
            emp = await conn.fetchrow(
                "SELECT id, org_id, start_date, work_state FROM employees WHERE id = $1",
                employee_id,
            )
            if not emp:
                return {"state": None, "programs": []}

            work_state = (emp["work_state"] or "").upper().strip()
            if not work_state:
                return {"state": None, "programs": [], "message": "No work state on record"}

            # Get all programs for this state
            rules = await conn.fetch(
                """SELECT * FROM leave_jurisdiction_rules
                   WHERE state = $1
                   ORDER BY leave_program""",
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

            twelve_months_ago = today - timedelta(days=365)
            hours_row = await conn.fetchrow(
                """SELECT COALESCE(SUM(hours_worked), 0) AS total_hours
                   FROM employee_hours_log
                   WHERE employee_id = $1
                     AND period_start >= $2""",
                employee_id, twelve_months_ago,
            )
            hours_worked = float(hours_row["total_hours"])

            company_count = await conn.fetchval(
                """SELECT COUNT(*) FROM employees
                   WHERE org_id = $1 AND termination_date IS NULL""",
                emp["org_id"],
            )

            programs = []
            for rule in rules:
                reasons = []
                eligible = True

                # Employer size threshold
                if rule["employer_size_threshold"] and company_count < rule["employer_size_threshold"]:
                    eligible = False
                    reasons.append(
                        f"Employer has {company_count} employees "
                        f"(minimum {rule['employer_size_threshold']})"
                    )

                # Tenure threshold
                if rule["employee_tenure_months"]:
                    if months_employed is None:
                        eligible = False
                        reasons.append("No start date on record")
                    elif months_employed < rule["employee_tenure_months"]:
                        eligible = False
                        reasons.append(
                            f"{months_employed:.1f} months tenure "
                            f"(minimum {rule['employee_tenure_months']})"
                        )

                # Hours threshold
                if rule["employee_hours_threshold"]:
                    if hours_worked < rule["employee_hours_threshold"]:
                        eligible = False
                        reasons.append(
                            f"{hours_worked:.0f} hours worked "
                            f"(minimum {rule['employee_hours_threshold']})"
                        )

                if eligible:
                    reasons = ["Meets program requirements"]

                programs.append({
                    "program": rule["leave_program"],
                    "label": rule["program_label"],
                    "eligible": eligible,
                    "paid": rule["paid"],
                    "max_weeks": rule["max_weeks"],
                    "wage_replacement_pct": float(rule["wage_replacement_pct"]) if rule["wage_replacement_pct"] else None,
                    "job_protection": rule["job_protection"],
                    "reasons": reasons,
                    "notes": rule["notes"],
                    "source_url": rule["source_url"],
                })

            return {"state": work_state, "programs": programs}

    async def get_eligibility_summary(self, employee_id: UUID) -> dict:
        """
        Combines FMLA + state programs into one response.
        """
        fmla = await self.check_fmla_eligibility(employee_id)
        state = await self.check_state_programs(employee_id)

        return {
            "fmla": fmla,
            "state_programs": state,
            "checked_at": datetime.utcnow().isoformat(),
        }
