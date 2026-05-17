"""Employee offboarding case + tasks + return-to-work templates.

Routes:
  POST   /{employee_id}/offboard                       — create/get active offboarding case
  GET    /{employee_id}/offboard                       — get latest offboarding case
  PATCH  /{employee_id}/offboard/tasks/{task_id}       — update offboarding task
  POST   /{employee_id}/offboard/{case_id}/complete    — complete an offboarding case

Also exports `assign_rtw_tasks` (called lazily from the onboarding submodule's
`/{employee_id}/onboarding/assign-rtw/{leave_request_id}` route — kept here
because its templates + `_ensure_rtw_templates` helper live alongside
offboarding semantically).
"""
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client

from ._shared import _employee_status_fields_available

logger = logging.getLogger(__name__)

router = APIRouter()


VALID_OFFBOARDING_CASE_STATUS = {"in_progress", "completed", "cancelled"}
VALID_OFFBOARDING_TASK_STATUS = {"pending", "completed", "skipped"}

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

OFFBOARDING_DEFAULT_TASKS = [
    {
        "title": "Disable SaaS and identity access",
        "description": "Disable SSO, email, and application access for the employee.",
        "category": "access_revocation",
        "assignee_type": "it",
        "due_offset_days": 0,
    },
    {
        "title": "Collect company equipment",
        "description": "Retrieve laptop, badge, and any other assigned hardware.",
        "category": "equipment_return",
        "assignee_type": "it",
        "due_offset_days": 3,
    },
    {
        "title": "Run knowledge transfer handoff",
        "description": "Capture handoff notes, docs, and transition ownership.",
        "category": "knowledge_transfer",
        "assignee_type": "manager",
        "due_offset_days": -2,
    },
    {
        "title": "Schedule exit interview",
        "description": "Coordinate and document employee exit interview.",
        "category": "exit_interview",
        "assignee_type": "hr",
        "due_offset_days": 1,
    },
    {
        "title": "Finalize payroll and benefits termination",
        "description": "Process final payroll and confirm benefits termination timing.",
        "category": "final_payroll",
        "assignee_type": "payroll",
        "due_offset_days": 2,
    },
]


class OffboardingCaseCreateRequest(BaseModel):
    last_day: date
    reason: Optional[str] = None
    is_voluntary: bool = True
    assign_default_tasks: bool = True


class OffboardingCaseCompleteRequest(BaseModel):
    force: bool = False


class OffboardingTaskUpdateRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class OffboardingTaskResponse(BaseModel):
    id: UUID
    case_id: UUID
    employee_id: UUID
    title: str
    description: Optional[str]
    category: str
    assignee_type: str
    due_date: Optional[str]
    status: str
    completed_at: Optional[datetime]
    completed_by: Optional[UUID]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class OffboardingCaseResponse(BaseModel):
    id: UUID
    org_id: UUID
    employee_id: UUID
    status: str
    reason: Optional[str]
    is_voluntary: bool
    last_day: str
    started_at: datetime
    completed_at: Optional[datetime]
    created_by: Optional[UUID]
    created_at: datetime
    tasks: list[OffboardingTaskResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


def _to_offboarding_task_response(row) -> OffboardingTaskResponse:
    return OffboardingTaskResponse(
        id=row["id"],
        case_id=row["case_id"],
        employee_id=row["employee_id"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        assignee_type=row["assignee_type"],
        due_date=str(row["due_date"]) if row["due_date"] else None,
        status=row["status"],
        completed_at=row["completed_at"],
        completed_by=row["completed_by"],
        notes=row["notes"],
        created_at=row["created_at"],
    )


def _to_offboarding_case_response(case_row, task_rows: list) -> OffboardingCaseResponse:
    return OffboardingCaseResponse(
        id=case_row["id"],
        org_id=case_row["org_id"],
        employee_id=case_row["employee_id"],
        status=case_row["status"],
        reason=case_row["reason"],
        is_voluntary=bool(case_row["is_voluntary"]),
        last_day=str(case_row["last_day"]),
        started_at=case_row["started_at"],
        completed_at=case_row["completed_at"],
        created_by=case_row["created_by"],
        created_at=case_row["created_at"],
        tasks=[_to_offboarding_task_response(row) for row in task_rows],
    )


async def _ensure_rtw_templates(conn, company_id: UUID) -> None:
    """Create default return-to-work templates if they do not exist for the company."""
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM onboarding_tasks WHERE org_id = $1 AND category = 'return_to_work'",
        company_id,
    )
    if count and count > 0:
        return

    for template in RETURN_TO_WORK_DEFAULT_TEMPLATES:
        await conn.execute(
            """
            INSERT INTO onboarding_tasks (org_id, title, description, category, is_employee_task, due_days, sort_order)
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


async def assign_rtw_tasks(
    employee_id: UUID,
    leave_request_id: UUID,
    company_id: UUID,
    conn,
) -> list:
    """Assign return-to-work onboarding tasks linked to a leave request."""
    leave = await conn.fetchrow(
        """
        SELECT id, employee_id, expected_return_date, end_date
        FROM leave_requests
        WHERE id = $1 AND org_id = $2
        """,
        leave_request_id,
        company_id,
    )
    if not leave or leave["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Leave request not found for employee")

    await _ensure_rtw_templates(conn, company_id)

    templates = await conn.fetch(
        """
        SELECT id, title, description, category, is_employee_task, due_days
        FROM onboarding_tasks
        WHERE org_id = $1 AND is_active = true AND category = 'return_to_work'
        ORDER BY sort_order, title
        """,
        company_id,
    )

    base_date = leave["expected_return_date"] or leave["end_date"] or date.today()
    assigned_tasks = []

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
            RETURNING *
            """,
            employee_id,
            template["id"],
            leave_request_id,
            template["title"],
            template["description"],
            template["category"],
            template["is_employee_task"],
            due_date,
        )
        if row:
            assigned_tasks.append(row)

    return assigned_tasks


@router.post("/{employee_id}/offboard", response_model=OffboardingCaseResponse)
async def create_offboarding_case(
    employee_id: UUID,
    request: OffboardingCaseCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create or return the active offboarding case for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        async with conn.transaction():
            employee = await conn.fetchrow(
                """
                SELECT id, org_id, start_date
                FROM employees
                WHERE id = $1 AND org_id = $2
                FOR UPDATE
                """,
                employee_id,
                company_id,
            )
            if not employee:
                raise HTTPException(status_code=404, detail="Employee not found")

            if employee["start_date"] and request.last_day < employee["start_date"]:
                raise HTTPException(status_code=400, detail="last_day cannot be before employee start_date")

            existing_case = await conn.fetchrow(
                """
                SELECT *
                FROM offboarding_cases
                WHERE employee_id = $1 AND status = 'in_progress'
                ORDER BY created_at DESC
                LIMIT 1
                FOR UPDATE
                """,
                employee_id,
            )

            if existing_case:
                case_row = existing_case
            else:
                case_row = await conn.fetchrow(
                    """
                    INSERT INTO offboarding_cases
                    (org_id, employee_id, status, reason, is_voluntary, last_day, created_by)
                    VALUES ($1, $2, 'in_progress', $3, $4, $5, $6)
                    RETURNING *
                    """,
                    company_id,
                    employee_id,
                    request.reason,
                    request.is_voluntary,
                    request.last_day,
                    current_user.id,
                )

                await conn.execute(
                    """
                    UPDATE employees
                    SET termination_date = $2, updated_at = NOW()
                    WHERE id = $1
                    """,
                    employee_id,
                    request.last_day,
                )

                # Update employment status to on_notice if status columns exist
                if await _employee_status_fields_available(conn):
                    await conn.execute(
                        """
                        UPDATE employees
                        SET employment_status = 'on_notice', status_changed_at = NOW(),
                            status_reason = 'Offboarding initiated'
                        WHERE id = $1
                        """,
                        employee_id,
                    )

                if request.assign_default_tasks:
                    for template in OFFBOARDING_DEFAULT_TASKS:
                        due_date = request.last_day + timedelta(days=template["due_offset_days"])
                        await conn.execute(
                            """
                            INSERT INTO offboarding_tasks
                            (case_id, employee_id, title, description, category, assignee_type, due_date)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            """,
                            case_row["id"],
                            employee_id,
                            template["title"],
                            template["description"],
                            template["category"],
                            template["assignee_type"],
                            due_date,
                        )

            task_rows = await conn.fetch(
                """
                SELECT *
                FROM offboarding_tasks
                WHERE case_id = $1
                ORDER BY due_date NULLS LAST, created_at
                """,
                case_row["id"],
            )

        return _to_offboarding_case_response(case_row, list(task_rows))


@router.get("/{employee_id}/offboard", response_model=OffboardingCaseResponse)
async def get_offboarding_case(
    employee_id: UUID,
    status: Optional[str] = Query(None, description="Filter case status"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get the latest offboarding case for an employee."""
    company_id = await get_client_company_id(current_user)
    if status and status not in VALID_OFFBOARDING_CASE_STATUS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {sorted(VALID_OFFBOARDING_CASE_STATUS)}",
        )

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id,
            company_id,
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        if status:
            case_row = await conn.fetchrow(
                """
                SELECT *
                FROM offboarding_cases
                WHERE employee_id = $1 AND org_id = $2 AND status = $3
                ORDER BY created_at DESC
                LIMIT 1
                """,
                employee_id,
                company_id,
                status,
            )
        else:
            case_row = await conn.fetchrow(
                """
                SELECT *
                FROM offboarding_cases
                WHERE employee_id = $1 AND org_id = $2
                ORDER BY created_at DESC
                LIMIT 1
                """,
                employee_id,
                company_id,
            )

        if not case_row:
            raise HTTPException(status_code=404, detail="Offboarding case not found")

        task_rows = await conn.fetch(
            """
            SELECT *
            FROM offboarding_tasks
            WHERE case_id = $1
            ORDER BY due_date NULLS LAST, created_at
            """,
            case_row["id"],
        )

        return _to_offboarding_case_response(case_row, list(task_rows))


@router.patch("/{employee_id}/offboard/tasks/{task_id}", response_model=OffboardingTaskResponse)
async def update_offboarding_task(
    employee_id: UUID,
    task_id: UUID,
    request: OffboardingTaskUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update offboarding task status/notes."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        task = await conn.fetchrow(
            """
            SELECT t.*
            FROM offboarding_tasks t
            JOIN offboarding_cases c ON c.id = t.case_id
            WHERE t.id = $1 AND t.employee_id = $2 AND c.org_id = $3
            """,
            task_id,
            employee_id,
            company_id,
        )
        if not task:
            raise HTTPException(status_code=404, detail="Offboarding task not found")

        updates = []
        values = []
        idx = 1

        if request.status is not None:
            if request.status not in VALID_OFFBOARDING_TASK_STATUS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {sorted(VALID_OFFBOARDING_TASK_STATUS)}",
                )
            updates.append(f"status = ${idx}")
            values.append(request.status)
            idx += 1

            if request.status == "completed":
                updates.append("completed_at = NOW()")
                updates.append(f"completed_by = ${idx}")
                values.append(current_user.id)
                idx += 1
            elif request.status == "pending":
                updates.append("completed_at = NULL")
                updates.append("completed_by = NULL")

        if request.notes is not None:
            updates.append(f"notes = ${idx}")
            values.append(request.notes)
            idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        values.append(task_id)

        row = await conn.fetchrow(
            f"""
            UPDATE offboarding_tasks
            SET {', '.join(updates)}
            WHERE id = ${idx}
            RETURNING *
            """,
            *values,
        )
        return _to_offboarding_task_response(row)


@router.post("/{employee_id}/offboard/{case_id}/complete", response_model=OffboardingCaseResponse)
async def complete_offboarding_case(
    employee_id: UUID,
    case_id: UUID,
    request: OffboardingCaseCompleteRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Complete an offboarding case and finalize access revocation status."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        async with conn.transaction():
            case_row = await conn.fetchrow(
                """
                SELECT *
                FROM offboarding_cases
                WHERE id = $1 AND employee_id = $2 AND org_id = $3
                FOR UPDATE
                """,
                case_id,
                employee_id,
                company_id,
            )
            if not case_row:
                raise HTTPException(status_code=404, detail="Offboarding case not found")

            if case_row["status"] == "completed":
                task_rows = await conn.fetch(
                    "SELECT * FROM offboarding_tasks WHERE case_id = $1 ORDER BY due_date NULLS LAST, created_at",
                    case_id,
                )
                return _to_offboarding_case_response(case_row, list(task_rows))

            pending_count = await conn.fetchval(
                "SELECT COUNT(*) FROM offboarding_tasks WHERE case_id = $1 AND status = 'pending'",
                case_id,
            )
            if pending_count > 0 and not request.force:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot complete case with {pending_count} pending tasks unless force=true",
                )

            if pending_count > 0 and request.force:
                await conn.execute(
                    """
                    UPDATE offboarding_tasks
                    SET status = 'skipped',
                        notes = COALESCE(notes || E'\\n', '') || 'Auto-skipped during forced case completion.',
                        updated_at = NOW()
                    WHERE case_id = $1 AND status = 'pending'
                    """,
                    case_id,
                )

            case_row = await conn.fetchrow(
                """
                UPDATE offboarding_cases
                SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                case_id,
            )

            # Update employment status to offboarded if status columns exist
            if await _employee_status_fields_available(conn):
                await conn.execute(
                    """
                    UPDATE employees
                    SET employment_status = 'offboarded', status_changed_at = NOW(),
                        status_reason = 'Offboarding completed'
                    WHERE id = $1
                    """,
                    employee_id,
                )

            if case_row["last_day"] <= date.today():
                try:
                    identities = await conn.fetch(
                        """
                        SELECT id, provider
                        FROM external_identities
                        WHERE employee_id = $1 AND company_id = $2 AND status <> 'deprovisioned'
                        """,
                        employee_id,
                        company_id,
                    )
                except Exception:
                    identities = []

                for identity in identities:
                    try:
                        await conn.execute(
                            """
                            UPDATE external_identities
                            SET status = 'deprovisioned', updated_at = NOW()
                            WHERE id = $1
                            """,
                            identity["id"],
                        )
                        await conn.execute(
                            """
                            INSERT INTO provisioning_audit_logs (
                                company_id, employee_id, actor_user_id, provider, action, status, detail, payload
                            )
                            VALUES ($1, $2, $3, $4, $5, 'info', $6, $7::jsonb)
                            """,
                            company_id,
                            employee_id,
                            current_user.id,
                            identity["provider"],
                            "offboarding_case_completed",
                            "Marked external identity as deprovisioned during offboarding completion.",
                            json.dumps({"offboarding_case_id": str(case_id)}),
                        )
                    except Exception:
                        continue

            task_rows = await conn.fetch(
                "SELECT * FROM offboarding_tasks WHERE case_id = $1 ORDER BY due_date NULLS LAST, created_at",
                case_id,
            )

        return _to_offboarding_case_response(case_row, list(task_rows))
