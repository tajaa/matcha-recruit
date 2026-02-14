"""
Leave Agent Orchestrator.

Coordinates leave, deadlines, accommodation, return-to-work tasks, and
notifications across route-driven and scheduled workflows.
"""

import asyncio
import json
import logging
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from ...core.services.email import get_email_service
from ...database import get_connection
from .leave_eligibility_service import LeaveEligibilityService
from .leave_notices_service import LeaveNoticeService

logger = logging.getLogger(__name__)

RETURN_TO_WORK_DEFAULT_TEMPLATES = [
    {
        "title": "Fitness-for-Duty Certification",
        "description": "Submit medical clearance from healthcare provider",
        "category": "return_to_work",
        "is_employee_task": True,
        "due_days": 0,
        "sort_order": 1,
    },
    {
        "title": "Modified Duty Agreement",
        "description": "Review and sign modified duty or accommodation plan",
        "category": "return_to_work",
        "is_employee_task": True,
        "due_days": 1,
        "sort_order": 2,
    },
    {
        "title": "Accommodation Review",
        "description": "Meet with HR to review workplace accommodations",
        "category": "return_to_work",
        "is_employee_task": False,
        "due_days": 3,
        "sort_order": 3,
    },
    {
        "title": "Gradual Return Schedule",
        "description": "Confirm phased return-to-work schedule",
        "category": "return_to_work",
        "is_employee_task": False,
        "due_days": 1,
        "sort_order": 4,
    },
    {
        "title": "Benefits Reinstatement Review",
        "description": "Verify benefits and leave balances are current",
        "category": "return_to_work",
        "is_employee_task": False,
        "due_days": 5,
        "sort_order": 5,
    },
    {
        "title": "Manager Check-in",
        "description": "Schedule return meeting with direct manager",
        "category": "return_to_work",
        "is_employee_task": True,
        "due_days": 3,
        "sort_order": 6,
    },
]


def _normalize_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class LeaveAgent:
    """Orchestrates leave and accommodation lifecycle operations."""

    def __init__(self):
        self.email_service = get_email_service()

    async def _get_company_admin_contacts(self, conn, company_id: UUID) -> list[dict[str, str]]:
        rows = await conn.fetch(
            """
            SELECT DISTINCT
                u.email,
                COALESCE(NULLIF(c.name, ''), split_part(u.email, '@', 1)) AS name
            FROM clients c
            JOIN users u ON u.id = c.user_id
            WHERE c.company_id = $1
              AND u.is_active = true
              AND u.email IS NOT NULL
            ORDER BY u.email
            """,
            company_id,
        )
        return [{"email": r["email"], "name": r["name"] or r["email"]} for r in rows]

    async def _send_leave_notifications(
        self,
        recipients: list[dict[str, str]],
        *,
        company_name: str,
        employee_name: str,
        leave_type: str,
        event_type: str,
        leave_id: UUID,
        start_date,
        end_date=None,
        deadline_date=None,
        deadline_type: Optional[str] = None,
    ) -> int:
        if not self.email_service.is_configured() or not recipients:
            return 0

        tasks = [
            self.email_service.send_leave_request_notification_email(
                to_email=recipient["email"],
                to_name=recipient.get("name"),
                company_name=company_name,
                employee_name=employee_name,
                leave_type=leave_type,
                event_type=event_type,
                leave_id=str(leave_id),
                start_date=str(start_date),
                end_date=str(end_date) if end_date else None,
                deadline_date=str(deadline_date) if deadline_date else None,
                deadline_type=deadline_type,
            )
            for recipient in recipients
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        sent = 0
        for recipient, result in zip(recipients, results):
            if isinstance(result, Exception):
                logger.warning("[LeaveAgent] Failed leave notification to %s: %s", recipient["email"], result)
                continue
            if result:
                sent += 1
        return sent

    async def _send_accommodation_notifications(
        self,
        recipients: list[dict[str, str]],
        *,
        company_name: str,
        case_number: str,
        event_type: str,
        employee_name: Optional[str] = None,
        details: Optional[str] = None,
    ) -> int:
        if not self.email_service.is_configured() or not recipients:
            return 0

        tasks = [
            self.email_service.send_accommodation_notification_email(
                to_email=recipient["email"],
                to_name=recipient.get("name"),
                company_name=company_name,
                case_number=case_number,
                event_type=event_type,
                employee_name=employee_name,
                details=details,
            )
            for recipient in recipients
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        sent = 0
        for recipient, result in zip(recipients, results):
            if isinstance(result, Exception):
                logger.warning("[LeaveAgent] Failed accommodation notification to %s: %s", recipient["email"], result)
                continue
            if result:
                sent += 1
        return sent

    async def _ensure_rtw_templates(self, conn, company_id: UUID) -> None:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM onboarding_tasks WHERE org_id = $1 AND category = 'return_to_work'",
            company_id,
        )
        if count and count > 0:
            return

        for template in RETURN_TO_WORK_DEFAULT_TEMPLATES:
            await conn.execute(
                """
                INSERT INTO onboarding_tasks
                    (org_id, title, description, category, is_employee_task, due_days, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                company_id,
                template["title"],
                template["description"],
                template["category"],
                template["is_employee_task"],
                template["due_days"],
                template["sort_order"],
            )

    async def _assign_rtw_tasks(self, conn, leave_row) -> int:
        await self._ensure_rtw_templates(conn, leave_row["org_id"])
        templates = await conn.fetch(
            """
            SELECT id, title, description, category, is_employee_task, due_days
            FROM onboarding_tasks
            WHERE org_id = $1 AND is_active = true AND category = 'return_to_work'
            ORDER BY sort_order, title
            """,
            leave_row["org_id"],
        )

        base_date = leave_row["expected_return_date"] or leave_row["end_date"] or date.today()
        created = 0
        for template in templates:
            due_date = base_date + timedelta(days=template["due_days"] or 0)
            row = await conn.fetchrow(
                """
                INSERT INTO employee_onboarding_tasks
                    (employee_id, task_id, leave_request_id, title, description, category, is_employee_task, due_date)
                SELECT $1, $2, $3, $4, $5, $6, $7, $8
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM employee_onboarding_tasks
                    WHERE employee_id = $1
                      AND leave_request_id = $3
                      AND title = $4
                )
                RETURNING id
                """,
                leave_row["employee_id"],
                template["id"],
                leave_row["id"],
                template["title"],
                template["description"],
                template["category"],
                template["is_employee_task"],
                due_date,
            )
            if row:
                created += 1
        return created

    async def on_leave_request_created(self, leave_request_id: UUID | str) -> dict:
        """Run initial orchestration after a leave request is submitted."""
        leave_request_id = _normalize_uuid(leave_request_id)
        async with get_connection() as conn:
            leave = await conn.fetchrow(
                """
                SELECT lr.id, lr.org_id, lr.employee_id, lr.leave_type, lr.start_date, lr.end_date,
                       lr.expected_return_date, lr.status,
                       e.first_name, e.last_name, e.email,
                       mgr_u.email AS manager_email,
                       COALESCE(NULLIF(mgr_e.first_name || ' ' || mgr_e.last_name, ' '), mgr_u.email) AS manager_name,
                       c.name AS company_name
                FROM leave_requests lr
                JOIN employees e ON e.id = lr.employee_id
                LEFT JOIN employees mgr_e ON e.manager_id = mgr_e.id
                LEFT JOIN users mgr_u ON mgr_e.user_id = mgr_u.id
                LEFT JOIN companies c ON c.id = lr.org_id
                WHERE lr.id = $1
                """,
                leave_request_id,
            )
            if not leave:
                return {"status": "not_found"}

            employee_name = f"{leave['first_name']} {leave['last_name']}".strip()
            company_name = leave["company_name"] or "Your company"

            try:
                eligibility = await LeaveEligibilityService().get_eligibility_summary(leave["employee_id"])
                await conn.execute(
                    "UPDATE leave_requests SET eligibility_data = $1, updated_at = NOW() WHERE id = $2",
                    json.dumps(eligibility),
                    leave["id"],
                )
            except Exception as e:
                logger.warning("[LeaveAgent] Eligibility precheck failed for %s: %s", leave["id"], e)

            if leave["leave_type"] == "fmla":
                try:
                    await LeaveNoticeService().create_notice(
                        conn,
                        notice_type="fmla_eligibility_notice",
                        employee_id=leave["employee_id"],
                        org_id=leave["org_id"],
                        leave_request_id=leave["id"],
                    )
                except Exception as e:
                    logger.warning("[LeaveAgent] FMLA eligibility notice generation failed for %s: %s", leave["id"], e)

            contacts = await self._get_company_admin_contacts(conn, leave["org_id"])
            if leave["manager_email"] and not any(c["email"] == leave["manager_email"] for c in contacts):
                contacts.append(
                    {
                        "email": leave["manager_email"],
                        "name": leave["manager_name"] or leave["manager_email"],
                    }
                )

            sent = await self._send_leave_notifications(
                contacts,
                company_name=company_name,
                employee_name=employee_name,
                leave_type=leave["leave_type"],
                event_type="submitted",
                leave_id=leave["id"],
                start_date=leave["start_date"],
                end_date=leave["end_date"],
            )
            return {"status": "ok", "notifications_sent": sent}

    async def on_leave_request_approved(self, leave_request_id: UUID | str) -> dict:
        """Run orchestration after admin approval of a leave request."""
        leave_request_id = _normalize_uuid(leave_request_id)
        async with get_connection() as conn:
            leave = await conn.fetchrow(
                """
                SELECT lr.id, lr.org_id, lr.employee_id, lr.leave_type, lr.start_date, lr.end_date,
                       lr.expected_return_date, lr.status,
                       e.first_name, e.last_name, e.email,
                       c.name AS company_name
                FROM leave_requests lr
                JOIN employees e ON e.id = lr.employee_id
                LEFT JOIN companies c ON c.id = lr.org_id
                WHERE lr.id = $1
                """,
                leave_request_id,
            )
            if not leave:
                return {"status": "not_found"}

            if leave["leave_type"] == "fmla":
                try:
                    await LeaveNoticeService().create_notice(
                        conn,
                        notice_type="fmla_designation_notice",
                        employee_id=leave["employee_id"],
                        org_id=leave["org_id"],
                        leave_request_id=leave["id"],
                    )
                except Exception as e:
                    logger.warning("[LeaveAgent] FMLA designation notice generation failed for %s: %s", leave["id"], e)

            employee_name = f"{leave['first_name']} {leave['last_name']}".strip()
            sent = await self._send_leave_notifications(
                [{"email": leave["email"], "name": employee_name}] if leave["email"] else [],
                company_name=leave["company_name"] or "Your company",
                employee_name=employee_name,
                leave_type=leave["leave_type"],
                event_type="approved",
                leave_id=leave["id"],
                start_date=leave["start_date"],
                end_date=leave["end_date"],
            )
            return {"status": "ok", "notifications_sent": sent}

    async def on_leave_status_changed(self, leave_request_id: UUID | str, new_status: str) -> dict:
        """Handle generic leave status transitions."""
        leave_request_id = _normalize_uuid(leave_request_id)
        async with get_connection() as conn:
            leave = await conn.fetchrow(
                """
                SELECT lr.id, lr.org_id, lr.employee_id, lr.leave_type, lr.start_date, lr.end_date,
                       lr.expected_return_date, lr.status,
                       e.first_name, e.last_name, e.email,
                       c.name AS company_name
                FROM leave_requests lr
                JOIN employees e ON e.id = lr.employee_id
                LEFT JOIN companies c ON c.id = lr.org_id
                WHERE lr.id = $1
                """,
                leave_request_id,
            )
            if not leave:
                return {"status": "not_found"}

            employee_name = f"{leave['first_name']} {leave['last_name']}".strip()
            company_name = leave["company_name"] or "Your company"
            if new_status == "denied":
                sent = await self._send_leave_notifications(
                    [{"email": leave["email"], "name": employee_name}] if leave["email"] else [],
                    company_name=company_name,
                    employee_name=employee_name,
                    leave_type=leave["leave_type"],
                    event_type="denied",
                    leave_id=leave["id"],
                    start_date=leave["start_date"],
                    end_date=leave["end_date"],
                )
                return {"status": "ok", "notifications_sent": sent}

            if new_status == "completed":
                await conn.execute(
                    """
                    UPDATE leave_deadlines
                    SET status = 'completed',
                        completed_at = COALESCE(completed_at, NOW()),
                        updated_at = NOW()
                    WHERE leave_request_id = $1
                      AND status IN ('pending', 'overdue')
                    """,
                    leave["id"],
                )
                return {"status": "ok", "deadlines_closed": True}

            return {"status": "ok", "message": "No-op for this status"}

    async def on_leave_notice_ready(self, leave_request_id: UUID | str) -> dict:
        """Notify employee that a leave notice document is available."""
        leave_request_id = _normalize_uuid(leave_request_id)
        async with get_connection() as conn:
            leave = await conn.fetchrow(
                """
                SELECT lr.id, lr.leave_type, lr.start_date, lr.end_date,
                       e.first_name, e.last_name, e.email,
                       c.name AS company_name
                FROM leave_requests lr
                JOIN employees e ON e.id = lr.employee_id
                LEFT JOIN companies c ON c.id = lr.org_id
                WHERE lr.id = $1
                """,
                leave_request_id,
            )
            if not leave:
                return {"status": "not_found"}

            employee_name = f"{leave['first_name']} {leave['last_name']}".strip()
            sent = await self._send_leave_notifications(
                [{"email": leave["email"], "name": employee_name}] if leave["email"] else [],
                company_name=leave["company_name"] or "Your company",
                employee_name=employee_name,
                leave_type=leave["leave_type"],
                event_type="notice_ready",
                leave_id=leave["id"],
                start_date=leave["start_date"],
                end_date=leave["end_date"],
            )
            return {"status": "ok", "notifications_sent": sent}

    async def on_deadline_approaching(self, deadline_id: UUID | str) -> dict:
        """Send notifications for leave deadlines that moved to warning/overdue/escalated."""
        deadline_id = _normalize_uuid(deadline_id)
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT ld.id, ld.leave_request_id, ld.org_id, ld.deadline_type, ld.due_date,
                       ld.status, ld.escalation_level,
                       lr.leave_type, lr.start_date, lr.end_date,
                       e.first_name, e.last_name, e.email,
                       c.name AS company_name
                FROM leave_deadlines ld
                JOIN leave_requests lr ON lr.id = ld.leave_request_id
                JOIN employees e ON e.id = lr.employee_id
                LEFT JOIN companies c ON c.id = ld.org_id
                WHERE ld.id = $1
                """,
                deadline_id,
            )
            if not row:
                return {"status": "not_found"}

            employee_name = f"{row['first_name']} {row['last_name']}".strip()
            company_name = row["company_name"] or "Your company"
            contacts = await self._get_company_admin_contacts(conn, row["org_id"])
            sent_admin = await self._send_leave_notifications(
                contacts,
                company_name=company_name,
                employee_name=employee_name,
                leave_type=row["leave_type"],
                event_type="deadline_approaching",
                leave_id=row["leave_request_id"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                deadline_date=row["due_date"],
                deadline_type=row["deadline_type"],
            )

            sent_employee = 0
            if row["deadline_type"] in ("fitness_for_duty_due", "return_date") and row["email"]:
                sent_employee = await self._send_leave_notifications(
                    [{"email": row["email"], "name": employee_name}],
                    company_name=company_name,
                    employee_name=employee_name,
                    leave_type=row["leave_type"],
                    event_type="deadline_approaching",
                    leave_id=row["leave_request_id"],
                    start_date=row["start_date"],
                    end_date=row["end_date"],
                    deadline_date=row["due_date"],
                    deadline_type=row["deadline_type"],
                )

            return {"status": "ok", "notifications_sent": sent_admin + sent_employee}

    async def on_accommodation_request_created(self, case_id: UUID | str) -> dict:
        """Send initial accommodation notifications and create baseline SLA deadline."""
        case_id = _normalize_uuid(case_id)
        try:
            async with get_connection() as conn:
                case = await conn.fetchrow(
                    """
                    SELECT ac.id, ac.case_number, ac.org_id, ac.employee_id, ac.linked_leave_id, ac.status,
                           e.first_name, e.last_name, e.email,
                           c.name AS company_name
                    FROM accommodation_cases ac
                    JOIN employees e ON e.id = ac.employee_id
                    LEFT JOIN companies c ON c.id = ac.org_id
                    WHERE ac.id = $1
                    """,
                    case_id,
                )
                if not case:
                    return {"status": "not_found"}

                # The deadline insert is best-effort so case creation never fails if
                # schema drift exists across environments.
                try:
                    await conn.execute(
                        """
                        INSERT INTO leave_deadlines (leave_request_id, org_id, deadline_type, due_date, accommodation_case_id, notes)
                        SELECT $1, $2, 'accommodation_interactive_process_due', CURRENT_DATE + 14, $3,
                               'Created by LeaveAgent for ADA interactive process SLA'
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM leave_deadlines
                            WHERE accommodation_case_id = $3
                              AND deadline_type = 'accommodation_interactive_process_due'
                        )
                        """,
                        case["linked_leave_id"],
                        case["org_id"],
                        case["id"],
                    )
                except Exception as deadline_error:
                    logger.warning(
                        "[LeaveAgent] Failed to create accommodation SLA deadline for case %s: %s",
                        case_id,
                        deadline_error,
                    )

                    # Fallback path for older schemas lacking accommodation_case_id.
                    if case["linked_leave_id"]:
                        try:
                            await conn.execute(
                                """
                                INSERT INTO leave_deadlines (leave_request_id, org_id, deadline_type, due_date, notes)
                                SELECT $1, $2, 'accommodation_interactive_process_due', CURRENT_DATE + 14,
                                       'Created by LeaveAgent for ADA interactive process SLA'
                                WHERE NOT EXISTS (
                                    SELECT 1
                                    FROM leave_deadlines
                                    WHERE leave_request_id = $1
                                      AND deadline_type = 'accommodation_interactive_process_due'
                                )
                                """,
                                case["linked_leave_id"],
                                case["org_id"],
                            )
                        except Exception as fallback_error:
                            logger.warning(
                                "[LeaveAgent] Fallback deadline insert failed for case %s: %s",
                                case_id,
                                fallback_error,
                            )

                employee_name = f"{case['first_name']} {case['last_name']}".strip()
                contacts = await self._get_company_admin_contacts(conn, case["org_id"])
                sent = await self._send_accommodation_notifications(
                    contacts,
                    company_name=case["company_name"] or "Your company",
                    case_number=case["case_number"],
                    event_type="case_opened",
                    employee_name=employee_name,
                )
                return {"status": "ok", "notifications_sent": sent}
        except Exception as exc:
            logger.exception("[LeaveAgent] on_accommodation_request_created failed for case %s: %s", case_id, exc)
            return {"status": "error", "error": str(exc)}

    async def on_accommodation_status_changed(self, case_id: UUID | str, status: str) -> dict:
        """Send notifications for key accommodation status transitions."""
        case_id = _normalize_uuid(case_id)
        async with get_connection() as conn:
            case = await conn.fetchrow(
                """
                SELECT ac.id, ac.case_number, ac.org_id, ac.status, ac.assigned_to,
                       e.first_name, e.last_name, e.email,
                       au.email AS assigned_email,
                       c.name AS company_name
                FROM accommodation_cases ac
                JOIN employees e ON e.id = ac.employee_id
                LEFT JOIN users au ON au.id = ac.assigned_to
                LEFT JOIN companies c ON c.id = ac.org_id
                WHERE ac.id = $1
                """,
                case_id,
            )
            if not case:
                return {"status": "not_found"}

            employee_name = f"{case['first_name']} {case['last_name']}".strip()
            company_name = case["company_name"] or "Your company"

            if status in ("interactive_process", "medical_review"):
                recipients = []
                if case["assigned_email"]:
                    recipients.append({"email": case["assigned_email"], "name": case["assigned_email"]})
                if not recipients:
                    recipients = await self._get_company_admin_contacts(conn, case["org_id"])
                sent = await self._send_accommodation_notifications(
                    recipients,
                    company_name=company_name,
                    case_number=case["case_number"],
                    event_type="action_needed",
                    employee_name=employee_name,
                    details=f"Case moved to {status.replace('_', ' ')}.",
                )
                return {"status": "ok", "notifications_sent": sent}

            if status in ("approved", "denied", "implemented", "closed"):
                recipients = [{"email": case["email"], "name": employee_name}] if case["email"] else []
                sent = await self._send_accommodation_notifications(
                    recipients,
                    company_name=company_name,
                    case_number=case["case_number"],
                    event_type="determination_made",
                    employee_name=employee_name,
                    details=f"Case status is now {status.replace('_', ' ')}.",
                )
                return {"status": "ok", "notifications_sent": sent}

            return {"status": "ok", "message": "No-op for this status"}

    async def on_accommodation_stalled(self, case_id: UUID | str) -> dict:
        """Escalate accommodation cases stalled in interactive process for 14+ days."""
        case_id = _normalize_uuid(case_id)
        async with get_connection() as conn:
            case = await conn.fetchrow(
                """
                SELECT ac.id, ac.case_number, ac.org_id, ac.status, ac.assigned_to, ac.updated_at,
                       e.first_name, e.last_name, e.email,
                       au.email AS assigned_email,
                       c.name AS company_name
                FROM accommodation_cases ac
                JOIN employees e ON e.id = ac.employee_id
                LEFT JOIN users au ON au.id = ac.assigned_to
                LEFT JOIN companies c ON c.id = ac.org_id
                WHERE ac.id = $1
                  AND ac.status = 'interactive_process'
                  AND ac.updated_at <= NOW() - INTERVAL '14 days'
                """,
                case_id,
            )
            if not case:
                return {"status": "not_found_or_not_stalled"}

            already_alerted = await conn.fetchval(
                """
                SELECT 1
                FROM accommodation_audit_log
                WHERE case_id = $1
                  AND action = 'accommodation_stalled_alert'
                  AND created_at >= NOW() - INTERVAL '24 hours'
                LIMIT 1
                """,
                case["id"],
            )
            if already_alerted:
                return {"status": "already_alerted_recently"}

            recipients = []
            if case["assigned_email"]:
                recipients.append({"email": case["assigned_email"], "name": case["assigned_email"]})
            if not recipients:
                recipients = await self._get_company_admin_contacts(conn, case["org_id"])

            employee_name = f"{case['first_name']} {case['last_name']}".strip()
            sent = await self._send_accommodation_notifications(
                recipients,
                company_name=case["company_name"] or "Your company",
                case_number=case["case_number"],
                event_type="action_needed",
                employee_name=employee_name,
                details="Case has been in interactive process for 14+ days without updates.",
            )

            await conn.execute(
                """
                INSERT INTO accommodation_audit_log (case_id, user_id, action, entity_type, entity_id, details)
                VALUES ($1, NULL, 'accommodation_stalled_alert', 'case', $1, $2)
                """,
                case["id"],
                json.dumps({"sent_notifications": sent}),
            )
            return {"status": "ok", "notifications_sent": sent}

    async def on_return_to_work(self, leave_request_id: UUID | str) -> dict:
        """Assign RTW tasks and notify stakeholders as return date approaches."""
        leave_request_id = _normalize_uuid(leave_request_id)
        async with get_connection() as conn:
            leave = await conn.fetchrow(
                """
                SELECT lr.id, lr.org_id, lr.employee_id, lr.leave_type, lr.status,
                       lr.start_date, lr.end_date, lr.expected_return_date,
                       e.first_name, e.last_name, e.email,
                       mgr_u.email AS manager_email,
                       COALESCE(NULLIF(mgr_e.first_name || ' ' || mgr_e.last_name, ' '), mgr_u.email) AS manager_name,
                       c.name AS company_name
                FROM leave_requests lr
                JOIN employees e ON e.id = lr.employee_id
                LEFT JOIN employees mgr_e ON e.manager_id = mgr_e.id
                LEFT JOIN users mgr_u ON mgr_e.user_id = mgr_u.id
                LEFT JOIN companies c ON c.id = lr.org_id
                WHERE lr.id = $1
                """,
                leave_request_id,
            )
            if not leave:
                return {"status": "not_found"}

            if leave["status"] in ("cancelled", "denied", "completed"):
                return {"status": "skip_terminal_status"}

            return_date = leave["expected_return_date"] or leave["end_date"]
            if not return_date:
                return {"status": "skip_no_return_date"}
            if return_date > date.today() + timedelta(days=7):
                return {"status": "skip_not_due"}

            created = await self._assign_rtw_tasks(conn, leave)
            if created <= 0:
                return {"status": "ok", "rtw_tasks_created": 0}

            employee_name = f"{leave['first_name']} {leave['last_name']}".strip()
            company_name = leave["company_name"] or "Your company"

            recipients = []
            if leave["email"]:
                recipients.append({"email": leave["email"], "name": employee_name})
            if leave["manager_email"]:
                recipients.append({"email": leave["manager_email"], "name": leave["manager_name"] or leave["manager_email"]})

            sent = await self._send_leave_notifications(
                recipients,
                company_name=company_name,
                employee_name=employee_name,
                leave_type=leave["leave_type"],
                event_type="return_pending",
                leave_id=leave["id"],
                start_date=leave["start_date"],
                end_date=leave["end_date"],
            )
            return {"status": "ok", "rtw_tasks_created": created, "notifications_sent": sent}

    async def run_scheduled_orchestration(self, max_per_cycle: int = 20) -> dict:
        """Run periodic leave/accommodation orchestration checks."""
        async with get_connection() as conn:
            leave_rows = await conn.fetch(
                """
                SELECT id
                FROM leave_requests
                WHERE status IN ('approved', 'active')
                  AND COALESCE(expected_return_date, end_date) IS NOT NULL
                  AND COALESCE(expected_return_date, end_date) <= CURRENT_DATE + 7
                ORDER BY COALESCE(expected_return_date, end_date) ASC
                LIMIT $1
                """,
                max_per_cycle,
            )

            stalled_rows = await conn.fetch(
                """
                SELECT id
                FROM accommodation_cases
                WHERE status = 'interactive_process'
                  AND updated_at <= NOW() - INTERVAL '14 days'
                ORDER BY updated_at ASC
                LIMIT $1
                """,
                max_per_cycle,
            )

        returns_triggered = 0
        stalled_triggered = 0
        for row in leave_rows:
            result = await self.on_return_to_work(row["id"])
            if result.get("rtw_tasks_created", 0) > 0:
                returns_triggered += 1

        for row in stalled_rows:
            result = await self.on_accommodation_stalled(row["id"])
            if result.get("notifications_sent", 0) > 0:
                stalled_triggered += 1

        return {
            "checked_upcoming_returns": len(leave_rows),
            "return_workflows_triggered": returns_triggered,
            "checked_stalled_accommodations": len(stalled_rows),
            "stalled_alerts_triggered": stalled_triggered,
        }


_leave_agent: Optional[LeaveAgent] = None


def get_leave_agent() -> LeaveAgent:
    """Get singleton LeaveAgent instance."""
    global _leave_agent
    if _leave_agent is None:
        _leave_agent = LeaveAgent()
    return _leave_agent
