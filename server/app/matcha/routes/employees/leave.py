"""Per-employee leave endpoints on the main employees router.

Routes:
  GET  /{employee_id}/leave/eligibility — FMLA + state program eligibility
  POST /{employee_id}/leave/place       — admin places employee on leave (auto-approved)

Distinct from the leave admin router (leave_admin.py) which manages leave
REQUESTS at /employees/leave/* — these are EMPLOYEE-scoped at /employees/{id}/leave/*.
"""
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client

router = APIRouter()


@router.get("/{employee_id}/leave/eligibility")
async def get_employee_leave_eligibility(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get FMLA + state program eligibility for an employee with job protection summary."""
    from app.matcha.services.leave_eligibility_service import LeaveEligibilityService

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

    service = LeaveEligibilityService()
    summary = await service.get_eligibility_summary(employee_id)
    protection = await service.get_job_protection_summary(employee_id)

    return {**summary, "protection": protection}


class PlaceOnLeaveRequest(BaseModel):
    leave_type: str
    start_date: date
    end_date: Optional[date] = None
    expected_return_date: Optional[date] = None
    reason: Optional[str] = None
    notes: Optional[str] = None


@router.post("/{employee_id}/leave/place")
async def place_employee_on_leave(
    employee_id: UUID,
    body: PlaceOnLeaveRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Place an employee on leave directly (admin action, auto-approved). Updates employment_status."""
    from app.matcha.services.leave_agent import get_leave_agent

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        leave_row = await conn.fetchrow(
            """INSERT INTO leave_requests
                   (employee_id, org_id, leave_type, start_date, end_date, expected_return_date,
                    reason, notes, status, reviewed_by, reviewed_at, intermittent)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'approved', $9, NOW(), false)
               RETURNING id""",
            employee_id, company_id, body.leave_type, body.start_date,
            body.end_date, body.expected_return_date,
            body.reason, body.notes, current_user.id,
        )
        leave_id = leave_row["id"]

        await conn.execute(
            """UPDATE employees
               SET employment_status = 'on_leave', status_changed_at = NOW(),
                   status_reason = $1, updated_at = NOW()
               WHERE id = $2""",
            body.reason or "Placed on leave by admin",
            employee_id,
        )

    background_tasks.add_task(get_leave_agent().on_leave_request_approved, leave_id)
    return {"leave_id": str(leave_id), "employment_status": "on_leave"}
