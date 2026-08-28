"""Assign / unassign employees to a shift (`/employee-schedule/shifts/{id}/assignments`)."""

import logging
from datetime import timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from ...dependencies import require_admin_or_client
from app.matcha.models.scheduling.employee_schedule import (
    AssignmentCreate, AssignmentMove, AssignmentNoteUpdate,
)
from ...services.training.training_assignment import evaluate_scheduled_role_rules, assign_training
from ...services.scheduling.shift_writes import (
    apply_assignment_core, log_availability_override, remove_assignment_core,
)
from ...services.scheduling.schedule_guidance import refresh_assignment_break_guidance
from ._shared import (
    require_company_id, log_audit, fetch_shift_by_id, fetch_shift_for_write,
    assert_employee_in_company, assert_employee_schedulable_at, assert_shift_open_for_assignment,
    find_conflicts, raise_conflict, raise_shift_full,
    fetch_availability, availability_violations, raise_outside_availability,
    fetch_locked_shift_pair, check_job_qualification, raise_not_qualified,
    reconcile_warning_events,
)
from ._compliance import check_shift_compliance, raise_for_violations, _fair_workweek_advisories

logger = logging.getLogger(__name__)

router = APIRouter()


@router.put("/shifts/{shift_id}/assignments/{employee_id}/note")
async def update_assignment_note(
    shift_id: UUID,
    employee_id: UUID,
    body: AssignmentNoteUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Set the one manager-owned note for an employee's shift assignment.

    History is retained in schedule_audit_log rather than overwriting the
    previous value without an accountable record.
    """
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                """
                SELECT a.manager_note, a.manager_note_visible_to_employee,
                       a.manager_note_include_in_location_digest,
                       a.manager_note_send_employee_notice
                FROM schedule_shift_assignments a
                JOIN schedule_shifts s ON s.id = a.shift_id
                WHERE a.shift_id = $1 AND a.employee_id = $2 AND s.company_id = $3
                FOR UPDATE
                """,
                shift_id, employee_id, company_id,
            )
            if not existing:
                raise HTTPException(status_code=404, detail="Assignment not found")
            await conn.execute(
                """
                UPDATE schedule_shift_assignments
                SET manager_note = $1,
                    manager_note_visible_to_employee = $2,
                    manager_note_include_in_location_digest = $3,
                    manager_note_send_employee_notice = $4,
                    manager_note_updated_by = $5,
                    manager_note_updated_at = NOW()
                WHERE shift_id = $6 AND employee_id = $7
                """,
                body.note.strip() if body.note else None,
                body.visible_to_employee,
                body.include_in_location_digest,
                body.send_employee_notice,
                current_user.id, shift_id, employee_id,
            )
            await log_audit(
                conn, company_id, "assignment", shift_id, current_user.id,
                "assignment.note.update",
                {
                    "employee_id": str(employee_id),
                    "before": dict(existing),
                    "after": body.model_dump(),
                },
            )
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.post("/assignments/move")
async def move_employee_assignment(
    body: AssignmentMove,
    force: bool = Query(False, description="Move despite overlap, capacity, availability, or advisory violations"),
    current_user=Depends(require_admin_or_client),
):
    """Move one assignment atomically between two tenant-owned shifts."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            shifts = await fetch_locked_shift_pair(
                conn, company_id, body.from_shift_id, body.to_shift_id,
            )
            source = shifts.get(str(body.from_shift_id))
            target = shifts.get(str(body.to_shift_id))
            if source is None or target is None:
                raise HTTPException(status_code=404, detail="Shift not found")
            if source["status"] == "cancelled":
                raise HTTPException(status_code=409, detail="Cannot move an assignment from a cancelled shift")
            if target["status"] == "cancelled":
                raise HTTPException(status_code=409, detail="Cannot move an assignment to a cancelled shift")

            await assert_employee_in_company(conn, company_id, body.employee_id)
            await assert_employee_schedulable_at(conn, company_id, body.employee_id, target["location_id"])
            assignment = await conn.fetchrow(
                """
                SELECT assigned_by
                FROM schedule_shift_assignments
                WHERE shift_id = $1 AND employee_id = $2
                """,
                body.from_shift_id, body.employee_id,
            )
            if assignment is None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "assignment_missing",
                        "message": "Employee is not assigned to the source shift",
                    },
                )
            already_target = await conn.fetchval(
                """
                SELECT 1
                FROM schedule_shift_assignments
                WHERE shift_id = $1 AND employee_id = $2
                """,
                body.to_shift_id, body.employee_id,
            )
            if already_target:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "assignment_exists",
                        "message": "Employee is already assigned to the destination shift",
                    },
                )

            target_availability: list[dict] = []
            if not force:
                if target["assigned_count"] >= target["required_staff"]:
                    raise_shift_full(target["assigned_count"], target["required_staff"])
                conflicts = await find_conflicts(
                    conn, company_id, body.employee_id,
                    target["starts_at"], target["ends_at"],
                    exclude_shift_id=body.from_shift_id,
                )
                if conflicts:
                    raise_conflict(body.employee_id, conflicts)
            availability = await fetch_availability(conn, company_id, [body.employee_id])
            target_availability = availability_violations(
                availability[body.employee_id], target["starts_at"], target["ends_at"],
            )
            if target_availability and not force:
                raise_outside_availability(body.employee_id, target_availability)
            unqualified = await check_job_qualification(
                conn, company_id, body.employee_id, target["job_id"],
                starts_at=target["starts_at"],
            )
            if unqualified and not force:
                raise_not_qualified(unqualified)

            if source["published_at"] is not None:
                source_violations = await _fair_workweek_advisories(
                    conn, company_id,
                    location_id=source["location_id"],
                    starts_at=source["starts_at"], ends_at=source["ends_at"],
                    event="unassign", shift_published=True, min_rest_gap_hours=None,
                )
                raise_for_violations(source_violations, force=force)
            else:
                source_violations = []

            target_violations = await check_shift_compliance(
                conn, company_id, location_id=target["location_id"], job_id=target["job_id"],
                starts_at=target["starts_at"], ends_at=target["ends_at"],
                break_minutes=target["break_minutes"] or 0,
                employee_id=body.employee_id,
                exclude_shift_id=body.from_shift_id,
                fw_event="assign",
                fw_shift_published=(target["published_at"] is not None),
                shift_kind=target["kind"],
                training_requirement_id=target["training_requirement_id"],
            )
            raise_for_violations(target_violations, force=force)

            audit_details = {
                "source": "schedule_editor_move",
                "from_shift_id": str(body.from_shift_id),
                "to_shift_id": str(body.to_shift_id),
            }
            await remove_assignment_core(
                conn, company_id,
                shift_id=body.from_shift_id,
                employee_id=body.employee_id,
                actor_user_id=current_user.id,
                shift_row=source,
                audit_details=audit_details,
            )
            await apply_assignment_core(
                conn, company_id,
                shift_row=target,
                employee_id=body.employee_id,
                actor_user_id=current_user.id,
                audit_details=audit_details,
            )
            if target_availability:
                await log_availability_override(
                    conn, company_id, body.to_shift_id, current_user.id,
                    body.employee_id, target_availability,
                )
            if source_violations or target_violations:
                await log_audit(
                    conn, company_id, "assignment", body.to_shift_id,
                    current_user.id, "assignment.compliance_override",
                    {"employee_id": str(body.employee_id), "violations": source_violations + target_violations},
                )
            if unqualified:  # forced past the qualification gate — record the override
                await log_audit(conn, company_id, "assignment", body.to_shift_id, current_user.id,
                                 "assignment.qualification_override",
                                 {"employee_id": str(body.employee_id), **unqualified})

        await reconcile_warning_events(conn, company_id, [body.from_shift_id, body.to_shift_id])
        return {
            "source_shift": await fetch_shift_by_id(conn, company_id, body.from_shift_id),
            "target_shift": await fetch_shift_by_id(conn, company_id, body.to_shift_id),
        }


@router.post("/shifts/{shift_id}/assignments")
async def assign_employee(shift_id: UUID, body: AssignmentCreate,
                          force: bool = Query(False, description="Assign despite an overlapping shift or a full roster"),
                          current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        shift = await fetch_shift_for_write(conn, company_id, shift_id)
        assert_shift_open_for_assignment(shift)
        await assert_employee_in_company(conn, company_id, body.employee_id)
        await assert_employee_schedulable_at(conn, company_id, body.employee_id, shift["location_id"])
        avail_map = await fetch_availability(conn, company_id, [body.employee_id])
        availability = availability_violations(
            avail_map[body.employee_id], shift["starts_at"], shift["ends_at"],
        )
        unqualified = await check_job_qualification(
            conn, company_id, body.employee_id, shift["job_id"],
            starts_at=shift["starts_at"],
        )
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
            if availability:
                raise_outside_availability(body.employee_id, availability)
            if unqualified:
                raise_not_qualified(unqualified)
        # Compliance runs regardless of force — a minor-hour BLOCK (422) can't be
        # overridden, advisories (409) can.
        violations = await check_shift_compliance(
            conn, company_id, location_id=shift["location_id"], job_id=shift["job_id"],
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
            await refresh_assignment_break_guidance(
                conn, company_id, shift_id=shift_id, employee_id=body.employee_id,
                location_id=shift["location_id"], starts_at=shift["starts_at"],
                ends_at=shift["ends_at"],
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
            if availability:
                await log_availability_override(
                    conn, company_id, shift_id, current_user.id,
                    body.employee_id, availability,
                )
            if unqualified:  # forced past the qualification gate — record the override
                await log_audit(conn, company_id, "assignment", shift_id, current_user.id,
                                 "assignment.qualification_override",
                                 {"employee_id": str(body.employee_id), **unqualified})
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
        await reconcile_warning_events(conn, company_id, [shift_id])
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
        await reconcile_warning_events(conn, company_id, [shift_id])
        return await fetch_shift_by_id(conn, company_id, shift_id)
