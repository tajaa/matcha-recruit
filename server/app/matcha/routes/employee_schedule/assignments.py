"""Assign / unassign employees to a shift (`/employee-schedule/shifts/{id}/assignments`)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ...database import get_connection
from ...dependencies import require_admin_or_client
from ...models.employee_schedule import AssignmentCreate
from ._shared import (
    require_company_id, log_audit, fetch_shift_by_id,
    assert_employee_in_company,
)

router = APIRouter()


async def _assert_shift(conn, company_id: UUID, shift_id: UUID) -> None:
    row = await conn.fetchrow(
        "SELECT 1 FROM schedule_shifts WHERE id = $1 AND company_id = $2",
        shift_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Shift not found")


@router.post("/shifts/{shift_id}/assignments")
async def assign_employee(shift_id: UUID, body: AssignmentCreate,
                          current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await _assert_shift(conn, company_id, shift_id)
        await assert_employee_in_company(conn, company_id, body.employee_id)
        await conn.execute(
            """
            INSERT INTO schedule_shift_assignments
                (company_id, shift_id, employee_id, assigned_by)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (shift_id, employee_id) DO NOTHING
            """,
            company_id, shift_id, body.employee_id, current_user.id,
        )
        await log_audit(conn, company_id, "assignment", shift_id, current_user.id,
                        "assignment.create", {"employee_id": str(body.employee_id)})
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.delete("/shifts/{shift_id}/assignments/{employee_id}")
async def unassign_employee(shift_id: UUID, employee_id: UUID,
                            current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await _assert_shift(conn, company_id, shift_id)
        await conn.execute(
            "DELETE FROM schedule_shift_assignments WHERE shift_id = $1 AND employee_id = $2",
            shift_id, employee_id,
        )
        await log_audit(conn, company_id, "assignment", shift_id, current_user.id,
                        "assignment.delete", {"employee_id": str(employee_id)})
        return await fetch_shift_by_id(conn, company_id, shift_id)
