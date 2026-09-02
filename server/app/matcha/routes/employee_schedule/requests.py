"""Manager review of bilateral employee schedule requests.

Requests enter this router only after the counterparty has accepted. Every
assignment mutation uses the shared scheduling writers in one transaction.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from ...dependencies import require_admin_or_client
from app.matcha.models.scheduling.employee_schedule import RequestReview
from ...services.scheduling.shift_writes import (
    apply_assignment_core, log_availability_override, remove_assignment_core,
)
from ...services.scheduling.shift_requests import find_same_day_assignments, same_day_conflict_detail
from ...services.scheduling.schedule_request_notifications import (
    mark_manager_ready_notifications_resolved,
)
from ...services.scheduling.schedule_breaks import minimum_meal_break_minutes
from ...services.scheduling.schedule_guidance import resolve_shift_break_plan
from ._shared import (
    require_company_id, log_audit, serialize_request, REQUEST_SELECT,
    INACTIVE_EMPLOYMENT_STATUSES, assert_employee_schedulable_at,
    check_job_qualification, find_conflicts, raise_conflict, raise_not_qualified,
    fetch_availability, availability_violations, raise_outside_availability,
    reconcile_warning_events, fetch_locked_shift_pair, lock_scheduling_employees,
)
from ._compliance import check_shift_compliance, raise_for_violations

router = APIRouter()
_MAX_REQUESTS = 200


@router.get("/requests")
async def list_requests(
    status: str | None = Query(None),
    limit: int = Query(_MAX_REQUESTS, ge=1, le=500),
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    params: list = [company_id]
    where = "r.company_id = $1"
    params.append(status or "awaiting_manager")
    where += f" AND r.status = ${len(params)}"
    params.append(limit)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{REQUEST_SELECT} WHERE {where} ORDER BY r.created_at DESC LIMIT ${len(params)}",
            *params,
        )
    return {"requests": [serialize_request(dict(r)) for r in rows]}


async def _active_employee(conn, company_id: UUID, employee_id: UUID) -> None:
    row = await conn.fetchrow(
        """SELECT COALESCE(employment_status, 'active') AS employment_status
           FROM employees WHERE id = $1 AND org_id = $2""", employee_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=409, detail="Employee is no longer in this company")
    if row["employment_status"] in INACTIVE_EMPLOYMENT_STATUSES:
        raise HTTPException(status_code=409, detail=f"Employee is {row['employment_status']} and cannot be scheduled")


async def _check_recipient(conn, company_id: UUID, shift, employee_id: UUID,
                           *, exclude_shift_id: UUID | None, force: bool) -> tuple[list[dict], dict | None]:
    await _active_employee(conn, company_id, employee_id)
    await assert_employee_schedulable_at(conn, company_id, employee_id, shift["location_id"])
    conflicts = await find_conflicts(conn, company_id, employee_id, shift["starts_at"], shift["ends_at"],
                                     exclude_shift_id=exclude_shift_id)
    if conflicts and not force:
        raise_conflict(employee_id, conflicts)
    availability = await fetch_availability(conn, company_id, [employee_id])
    outside = availability_violations(availability[employee_id], shift["starts_at"], shift["ends_at"])
    if outside and not force:
        raise_outside_availability(employee_id, outside)
    unqualified = await check_job_qualification(
        conn, company_id, employee_id, shift["job_id"], starts_at=shift["starts_at"],
    )
    if unqualified and not force:
        raise_not_qualified(unqualified)
    break_plan = await resolve_shift_break_plan(
        conn, company_id, location_id=shift["location_id"],
        starts_at=shift["starts_at"], ends_at=shift["ends_at"],
        employee_id=employee_id,
    )
    effective_break = max(
        int(shift["break_minutes"] or 0),
        minimum_meal_break_minutes(break_plan),
    )
    violations = await check_shift_compliance(
        conn, company_id, location_id=shift["location_id"], job_id=shift["job_id"], starts_at=shift["starts_at"],
        ends_at=shift["ends_at"], break_minutes=effective_break,
        employee_id=employee_id, exclude_shift_id=exclude_shift_id, fw_event="assign",
        fw_shift_published=(shift["status"] == "published"), shift_kind=shift["kind"],
        training_requirement_id=shift["training_requirement_id"],
    )
    raise_for_violations(violations, force=force)
    return outside, unqualified


@router.post("/requests/{request_id}/review")
async def review_request(request_id: UUID, body: RequestReview,
                         current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    new_status = "approved" if body.decision == "approved" else "denied"
    changed_shift_ids: list[UUID] = []
    async with get_connection() as conn:
        async with conn.transaction():
            req = await conn.fetchrow(
                """SELECT id, request_type, shift_id, employee_id, target_employee_id,
                          counter_shift_id, counterparty_confirmed_at, status
                   FROM schedule_requests WHERE id = $1 AND company_id = $2 FOR UPDATE""",
                request_id, company_id,
            )
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")
            if req["status"] not in ("awaiting_manager", "pending"):
                raise HTTPException(status_code=409, detail={"code": "request_not_manager_ready", "status": req["status"]})

            if new_status == "approved" and req["request_type"] in ("pickup", "swap", "drop"):
                if req["shift_id"] is None:
                    raise HTTPException(status_code=409, detail="Request has no shift")
                if req["request_type"] in ("pickup", "swap") and not req["counterparty_confirmed_at"]:
                    raise HTTPException(status_code=409, detail="Both employees must confirm first")
                shift_ids = [req["shift_id"]]
                legacy_one_way_swap = req["request_type"] == "swap" and req["counter_shift_id"] is None
                if req["request_type"] == "swap" and not legacy_one_way_swap:
                    if not req["target_employee_id"] or not req["counter_shift_id"]:
                        raise HTTPException(status_code=409, detail="Swap is missing its counterparty shift")
                    shift_ids.append(req["counter_shift_id"])
                locked = await fetch_locked_shift_pair(conn, company_id, *shift_ids)
                await lock_scheduling_employees(
                    conn, company_id,
                    [employee_id for employee_id in (
                        req["employee_id"], req["target_employee_id"],
                    ) if employee_id is not None],
                )
                offered = locked.get(str(req["shift_id"]))
                if offered is None or offered["status"] != "published":
                    raise HTTPException(status_code=409, detail="Offered shift is no longer published")

                recipient = None if req["request_type"] == "drop" else req["target_employee_id"]
                if req["request_type"] in ("pickup", "swap") and recipient is None:
                    raise HTTPException(status_code=409, detail="Request has no confirmed counterparty")
                if recipient is not None:
                    counter = locked.get(str(req["counter_shift_id"])) if req["request_type"] == "swap" and not legacy_one_way_swap else None
                    if counter is not None and counter["status"] != "published":
                        raise HTTPException(status_code=409, detail="Counter shift is no longer published")
                    same_day = await find_same_day_assignments(
                        conn, company_id, recipient, offered["starts_at"],
                        exclude_shift_ids=([req["counter_shift_id"]] if req["request_type"] == "swap" and not legacy_one_way_swap else []),
                    )
                    if same_day:
                        raise HTTPException(status_code=409, detail=same_day_conflict_detail(recipient, same_day))
                    if req["request_type"] == "swap" and not legacy_one_way_swap:
                        reverse_same_day = await find_same_day_assignments(
                            conn, company_id, req["employee_id"], counter["starts_at"],
                            exclude_shift_ids=[req["shift_id"]],
                        )
                        if reverse_same_day:
                            raise HTTPException(
                                status_code=409,
                                detail=same_day_conflict_detail(req["employee_id"], reverse_same_day),
                            )
                    recipient_outside, recipient_unqualified = await _check_recipient(
                        conn, company_id, offered, recipient,
                        exclude_shift_id=req["counter_shift_id"] if req["request_type"] == "swap" and not legacy_one_way_swap else None,
                        force=body.force,
                    )
                    if req["request_type"] == "swap" and not legacy_one_way_swap:
                        # Validate the reverse leg too: the original owner is
                        # gaining the counter shift, so it must still pass the
                        # normal overlap/availability/compliance gates.
                        counter_outside, counter_unqualified = await _check_recipient(
                            conn, company_id, counter, req["employee_id"],
                            exclude_shift_id=req["shift_id"], force=body.force,
                        )
                    else:
                        counter_outside, counter_unqualified = [], None

                removed = await remove_assignment_core(
                    conn, company_id, shift_id=req["shift_id"], employee_id=req["employee_id"],
                    actor_user_id=current_user.id, shift_row=offered,
                    audit_details={"request_id": str(request_id), "request_type": req["request_type"]},
                )
                if not removed:
                    raise HTTPException(status_code=409, detail="Offered shift is no longer assigned to its owner")
                changed_shift_ids.append(req["shift_id"])
                if req["request_type"] == "swap" and not legacy_one_way_swap:
                    counter = locked[str(req["counter_shift_id"])]
                    removed_counter = await remove_assignment_core(
                        conn, company_id, shift_id=req["counter_shift_id"], employee_id=req["target_employee_id"],
                        actor_user_id=current_user.id, shift_row=counter,
                        audit_details={"request_id": str(request_id), "request_type": req["request_type"]},
                    )
                    if not removed_counter:
                        raise HTTPException(status_code=409, detail="Counter shift is no longer assigned to its owner")
                    await apply_assignment_core(
                        conn, company_id, shift_row=offered, employee_id=req["target_employee_id"],
                        actor_user_id=current_user.id,
                        audit_details={"request_id": str(request_id), "request_type": "swap"},
                    )
                    await apply_assignment_core(
                        conn, company_id, shift_row=counter, employee_id=req["employee_id"],
                        actor_user_id=current_user.id,
                        audit_details={"request_id": str(request_id), "request_type": "swap"},
                    )
                    changed_shift_ids.append(req["counter_shift_id"])
                elif recipient is not None:
                    await apply_assignment_core(
                        conn, company_id, shift_row=offered, employee_id=recipient,
                        actor_user_id=current_user.id,
                        audit_details={"request_id": str(request_id), "request_type": req["request_type"]},
                    )
                if recipient is not None and recipient_outside:
                    await log_availability_override(
                        conn, company_id, req["shift_id"], current_user.id,
                        recipient, recipient_outside,
                    )
                if recipient is not None and recipient_unqualified:
                    await log_audit(
                        conn, company_id, "assignment", req["shift_id"], current_user.id,
                        "assignment.qualification_override",
                        {"employee_id": str(recipient), **recipient_unqualified},
                    )
                if req["request_type"] == "swap" and not legacy_one_way_swap:
                    if counter_outside:
                        await log_availability_override(
                            conn, company_id, req["counter_shift_id"], current_user.id,
                            req["employee_id"], counter_outside,
                        )
                    if counter_unqualified:
                        await log_audit(
                            conn, company_id, "assignment", req["counter_shift_id"], current_user.id,
                            "assignment.qualification_override",
                            {"employee_id": str(req["employee_id"]), **counter_unqualified},
                        )

            await conn.execute(
                """UPDATE schedule_requests SET status = $3, review_notes = $4,
                   reviewed_by = $5, reviewed_at = NOW(), updated_at = NOW()
                   WHERE id = $1 AND company_id = $2""",
                request_id, company_id, new_status, body.review_notes, current_user.id,
            )
            await mark_manager_ready_notifications_resolved(
                conn, company_id=company_id, request_id=request_id,
            )
            shift_start = None
            if req["shift_id"]:
                shift_start = await conn.fetchval("SELECT starts_at FROM schedule_shifts WHERE id = $1", req["shift_id"])
            await log_audit(
                conn, company_id, "request", request_id, current_user.id, f"request.{new_status}",
                {"request_type": req["request_type"], "shift_id": str(req["shift_id"]) if req["shift_id"] else None,
                 "counter_shift_id": str(req["counter_shift_id"]) if req["counter_shift_id"] else None,
                 "employee_id": str(req["employee_id"]),
                 "target_employee_id": str(req["target_employee_id"]) if req["target_employee_id"] else None,
                 "shift_starts_at": shift_start.isoformat() if shift_start else None},
            )
        if changed_shift_ids:
            await reconcile_warning_events(conn, company_id, changed_shift_ids)
        row = await conn.fetchrow(f"{REQUEST_SELECT} WHERE r.id = $1 AND r.company_id = $2", request_id, company_id)
    return serialize_request(dict(row))
