"""Assign / unassign employees to a shift (`/employee-schedule/shifts/{id}/assignments`)."""

import logging
from datetime import timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.employee_schedule import AssignmentCreate
from ...services.training.training_assignment import evaluate_scheduled_role_rules, assign_training
from ._shared import (
    require_company_id, log_audit, fetch_shift_by_id, fetch_shift_for_write,
    assert_employee_in_company, assert_shift_open_for_assignment,
    find_conflicts, raise_conflict, raise_shift_full,
)
from ._compliance import check_shift_compliance, raise_for_violations, _fair_workweek_advisories

logger = logging.getLogger(__name__)

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
            fw_event="assign", fw_shift_published=(shift["status"] == "published"),
            shift_kind=shift["kind"], training_requirement_id=shift["training_requirement_id"],
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
                            "assignment.create", {
                                "employee_id": str(body.employee_id),
                                "shift_starts_at": shift["starts_at"].isoformat(),
                                "shift_ends_at": shift["ends_at"].isoformat(),
                                "shift_status": shift["status"],
                                "location_id": str(shift["location_id"]) if shift["location_id"] else None,
                            })
            if violations:  # forced advisories — record the override on the log
                await log_audit(conn, company_id, "assignment", shift_id, current_user.id,
                                "assignment.compliance_override",
                                {"employee_id": str(body.employee_id), "violations": violations})
            if shift["kind"] == "training" and shift["training_requirement_id"] is not None:
                requirement = await conn.fetchrow(
                    "SELECT id, title, training_type, frequency_months "
                    "FROM training_requirements WHERE id = $1 AND company_id = $2",
                    shift["training_requirement_id"], company_id,
                )
                if requirement:
                    await assign_training(
                        conn, company_id, dict(requirement), [body.employee_id],
                        source_type="schedule", source_ref=shift_id,
                        source_note=f"Scheduled training session {shift['starts_at'].date().isoformat()}",
                        due_date=shift["starts_at"].astimezone(timezone.utc).date(),
                        assigned_by=current_user.id,
                    )
                else:
                    logger.warning(
                        "training-kind shift %s has no resolvable training_requirement_id "
                        "(deleted?) — skipping training assignment", shift_id,
                    )
            elif shift["kind"] == "work":
                # A scheduled_role match must not fail the assignment write —
                # the shift is already staffed at this point.
                try:
                    await evaluate_scheduled_role_rules(
                        conn, company_id, body.employee_id,
                        shift_id=shift_id, shift_role=shift["role"],
                        shift_start=shift["starts_at"].astimezone(timezone.utc).date(),
                    )
                except Exception:
                    logger.exception(
                        "scheduled_role training rules failed for shift %s", shift_id
                    )
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.delete("/shifts/{shift_id}/assignments/{employee_id}")
async def unassign_employee(shift_id: UUID, employee_id: UUID,
                            force: bool = Query(False, description="Unassign despite a Fair Workweek notice advisory"),
                            current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        shift = await fetch_shift_for_write(conn, company_id, shift_id)
        if shift["status"] == "published":
            # Full check_shift_compliance would also re-run meal-break/OT/minor
            # checks that don't make sense for a REMOVAL (they exist to gate
            # scheduling someone, not un-scheduling them) — just the FW half.
            violations = await _fair_workweek_advisories(
                conn, company_id, location_id=shift["location_id"],
                starts_at=shift["starts_at"], ends_at=shift["ends_at"],
                event="unassign", shift_published=True, min_rest_gap_hours=None,
            )
            raise_for_violations(violations, force=force)
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM schedule_shift_assignments WHERE shift_id = $1 AND employee_id = $2",
                shift_id, employee_id,
            )
            await log_audit(conn, company_id, "assignment", shift_id, current_user.id,
                            "assignment.delete", {
                                "employee_id": str(employee_id),
                                "shift_starts_at": shift["starts_at"].isoformat(),
                                "shift_ends_at": shift["ends_at"].isoformat(),
                                "shift_status": shift["status"],
                                "shift_kind": shift["kind"],
                                "location_id": str(shift["location_id"]) if shift["location_id"] else None,
                            })
        return await fetch_shift_by_id(conn, company_id, shift_id)
