"""Assign / unassign employees to a shift (`/employee-schedule/shifts/{id}/assignments`)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.employee_schedule import AssignmentCreate
from ._shared import (
    require_company_id, log_audit, fetch_shift_by_id, fetch_shift_for_write,
    assert_employee_in_company, assert_shift_open_for_assignment,
    find_conflicts, raise_conflict, raise_shift_full,
)
from ._compliance import check_shift_compliance, raise_for_violations

router = APIRouter()


@router.post("/shifts/{shift_id}/assignments")
async def assign_employee(shift_id: UUID, body: AssignmentCreate,
                          force: bool = Query(False, description="Assign despite an overlapping shift or a full roster"),
                          current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        shift = await fetch_shift_for_write(conn, company_id, shift_id)
        assert_shift_open_for_assignment(shift)
        await assert_employee_in_company(conn, company_id, body.employee_id)
        if not force:
            conflicts = await find_conflicts(
                conn, company_id, body.employee_id,
                shift["starts_at"], shift["ends_at"],
                exclude_shift_id=shift_id,
            )
            if conflicts:
                raise_conflict(body.employee_id, conflicts)
            if shift["assigned_count"] >= shift["required_staff"]:
                raise_shift_full(shift["assigned_count"], shift["required_staff"])
        # Compliance runs regardless of force — a minor-hour BLOCK (422) can't be
        # overridden, advisories (409) can.
        violations = await check_shift_compliance(
            conn, company_id, location_id=shift["location_id"],
            starts_at=shift["starts_at"], ends_at=shift["ends_at"],
            break_minutes=shift["break_minutes"] or 0,
            employee_id=body.employee_id, exclude_shift_id=shift_id,
        )
        raise_for_violations(violations, force=force)
        async with conn.transaction():
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
            if violations:  # forced advisories — record the override on the log
                await log_audit(conn, company_id, "assignment", shift_id, current_user.id,
                                "assignment.compliance_override",
                                {"employee_id": str(body.employee_id), "violations": violations})
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.delete("/shifts/{shift_id}/assignments/{employee_id}")
async def unassign_employee(shift_id: UUID, employee_id: UUID,
                            current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await fetch_shift_for_write(conn, company_id, shift_id)
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM schedule_shift_assignments WHERE shift_id = $1 AND employee_id = $2",
                shift_id, employee_id,
            )
            await log_audit(conn, company_id, "assignment", shift_id, current_user.id,
                            "assignment.delete", {"employee_id": str(employee_id)})
        return await fetch_shift_by_id(conn, company_id, shift_id)
