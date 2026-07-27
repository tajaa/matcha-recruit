"""Extended leave requests (FMLA, state PFML, parental, etc.)."""
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.database import get_connection
from app.matcha.models.employees.employee import (
    LeaveRequestCreate, LeaveRequestResponse, LeaveRequestListResponse,
)
from app.matcha.dependencies import require_employee_record

from ._shared import _pto_dep, _compliance_plus_dep

router = APIRouter()

LEAVE_TYPES = {"fmla", "state_pfml", "parental", "bereavement", "jury_duty", "medical", "military", "unpaid_loa"}


@router.get("/me/leave", response_model=LeaveRequestListResponse, dependencies=_pto_dep)
async def get_my_leave_requests(
    status_filter: Optional[str] = None,
    employee: dict = Depends(require_employee_record),
):
    """List the current employee's extended leave requests."""
    async with get_connection() as conn:
        if status_filter:
            rows = await conn.fetch(
                """SELECT * FROM leave_requests
                   WHERE employee_id = $1 AND status = $2
                   ORDER BY created_at DESC""",
                employee["id"], status_filter,
            )
        else:
            rows = await conn.fetch(
                """SELECT * FROM leave_requests
                   WHERE employee_id = $1
                   ORDER BY created_at DESC""",
                employee["id"],
            )
        return LeaveRequestListResponse(
            requests=[LeaveRequestResponse(**dict(r)) for r in rows],
            total=len(rows),
        )


@router.get("/me/leave/eligibility", dependencies=_compliance_plus_dep)
async def get_my_leave_eligibility(
    employee: dict = Depends(require_employee_record),
):
    """Check what leave programs the employee may qualify for.

    Requires the ``compliance_plus`` feature flag.
    Returns FMLA eligibility and applicable state programs.
    """
    from app.matcha.services.leave.leave_eligibility_service import LeaveEligibilityService

    service = LeaveEligibilityService()
    return await service.get_eligibility_summary(employee["id"])


@router.get("/me/leave/{leave_id}", response_model=LeaveRequestResponse, dependencies=_pto_dep)
async def get_my_leave_request(
    leave_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Get a specific leave request belonging to the current employee."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM leave_requests WHERE id = $1 AND employee_id = $2",
            leave_id, employee["id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found")
        return LeaveRequestResponse(**dict(row))


@router.post("/me/leave/request", response_model=LeaveRequestResponse, dependencies=_pto_dep)
async def submit_leave_request(
    request: LeaveRequestCreate,
    background_tasks: BackgroundTasks,
    employee: dict = Depends(require_employee_record),
):
    """Submit an extended leave request."""
    if request.leave_type not in LEAVE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid leave type: {request.leave_type}")

    if request.start_date < date.today():
        raise HTTPException(status_code=400, detail="Start date cannot be in the past")

    if request.end_date and request.end_date < request.start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO leave_requests
               (employee_id, org_id, leave_type, start_date, end_date,
                expected_return_date, reason, intermittent, intermittent_schedule, status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'requested')
               RETURNING *""",
            employee["id"], employee["org_id"],
            request.leave_type, request.start_date, request.end_date,
            request.expected_return_date, request.reason,
            request.intermittent, request.intermittent_schedule,
        )
        from app.matcha.services.leave.leave_agent import get_leave_agent

        background_tasks.add_task(get_leave_agent().on_leave_request_created, row["id"])
        return LeaveRequestResponse(**dict(row))


@router.delete("/me/leave/{leave_id}", dependencies=_pto_dep)
async def cancel_leave_request(
    leave_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Cancel a pending leave request."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, status FROM leave_requests WHERE id = $1 AND employee_id = $2",
            leave_id, employee["id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found")
        if row["status"] != "requested":
            raise HTTPException(status_code=400, detail="Can only cancel requests in 'requested' status")

        await conn.execute(
            "UPDATE leave_requests SET status = 'cancelled', updated_at = NOW() WHERE id = $1",
            leave_id,
        )
        return {"status": "cancelled", "leave_id": str(leave_id)}
