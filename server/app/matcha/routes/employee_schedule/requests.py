"""Admin review of employee schedule requests (`/employee-schedule/requests`).

Employees file swap / drop / unavailability requests from the portal (see
employee_portal.py). Admins list them and approve/deny here. Approving a `drop`
unassigns the requester from the shift; approving a `swap` unassigns the
requester and assigns the named target (if any); `unavailable` is informational
(no shift mutation).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.employee_schedule import RequestReview
from ._shared import (
    require_company_id, log_audit, serialize_request, REQUEST_SELECT,
    INACTIVE_EMPLOYMENT_STATUSES, find_conflicts, raise_conflict,
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
    if status is not None:
        params.append(status)
        where += f" AND r.status = ${len(params)}"
    params.append(limit)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{REQUEST_SELECT} WHERE {where} "
            f"ORDER BY r.created_at DESC LIMIT ${len(params)}",
            *params,
        )
    return {"requests": [serialize_request(dict(r)) for r in rows]}


@router.post("/requests/{request_id}/review")
async def review_request(request_id: UUID, body: RequestReview,
                         current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    new_status = "approved" if body.decision == "approved" else "denied"
    async with get_connection() as conn:
        async with conn.transaction():
            # FOR UPDATE + the status guard on the UPDATE: two admins reviewing
            # the same request would otherwise both pass a pre-transaction
            # status check and both run their side effects (approve's assignment
            # mutations landing under a final status of 'denied').
            req = await conn.fetchrow(
                """
                SELECT id, request_type, shift_id, employee_id, target_employee_id, status
                FROM schedule_requests
                WHERE id = $1 AND company_id = $2
                FOR UPDATE
                """,
                request_id, company_id,
            )
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")
            if req["status"] != "pending":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "request_already_reviewed",
                        "message": f"Request was already {req['status']}",
                        "status": req["status"],
                    },
                )

            is_swap_with_target = (
                req["request_type"] == "swap"
                and req["shift_id"] is not None
                and req["target_employee_id"] is not None
            )
            swap_violations: list[dict] = []
            if new_status == "approved" and is_swap_with_target:
                # The target has to still be employable AND free, or approving
                # would unassign the requester and silently staff nobody.
                target = await conn.fetchrow(
                    """
                    SELECT COALESCE(employment_status, 'active') AS employment_status
                    FROM employees WHERE id = $1 AND org_id = $2
                    """,
                    req["target_employee_id"], company_id,
                )
                if not target:
                    raise HTTPException(
                        status_code=409,
                        detail="Swap target is no longer an employee of this company — "
                               "deny this request, or ask the employee to file a drop instead",
                    )
                if target["employment_status"] in INACTIVE_EMPLOYMENT_STATUSES:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Swap target is {target['employment_status']} and cannot be scheduled",
                    )
                window = await conn.fetchrow(
                    "SELECT starts_at, ends_at, location_id, break_minutes "
                    "FROM schedule_shifts WHERE id = $1 AND company_id = $2",
                    req["shift_id"], company_id,
                )
                if window and not body.force:
                    conflicts = await find_conflicts(
                        conn, company_id, req["target_employee_id"],
                        window["starts_at"], window["ends_at"],
                        exclude_shift_id=req["shift_id"],
                    )
                    if conflicts:
                        raise_conflict(req["target_employee_id"], conflicts)
                if window:
                    # Approving a swap is an assignment write like any other —
                    # without this, a swap was the one path that bypassed the
                    # compliance gate (incl. the non-overridable minor BLOCK).
                    swap_violations = await check_shift_compliance(
                        conn, company_id, location_id=window["location_id"],
                        starts_at=window["starts_at"], ends_at=window["ends_at"],
                        break_minutes=window["break_minutes"] or 0,
                        employee_id=req["target_employee_id"],
                        exclude_shift_id=req["shift_id"],
                    )
                    raise_for_violations(swap_violations, force=body.force)

            await conn.execute(
                """
                UPDATE schedule_requests
                SET status = $3, review_notes = $4, reviewed_by = $5,
                    reviewed_at = NOW(), updated_at = NOW()
                WHERE id = $1 AND company_id = $2 AND status = 'pending'
                """,
                request_id, company_id, new_status, body.review_notes, current_user.id,
            )

            if new_status == "approved" and req["shift_id"] is not None:
                if req["request_type"] in ("swap", "drop"):
                    await conn.execute(
                        "DELETE FROM schedule_shift_assignments "
                        "WHERE shift_id = $1 AND employee_id = $2",
                        req["shift_id"], req["employee_id"],
                    )
                if is_swap_with_target:
                    await conn.execute(
                        """
                        INSERT INTO schedule_shift_assignments
                            (company_id, shift_id, employee_id, assigned_by)
                        VALUES ($1,$2,$3,$4)
                        ON CONFLICT (shift_id, employee_id) DO NOTHING
                        """,
                        company_id, req["shift_id"], req["target_employee_id"],
                        current_user.id,
                    )

            audit_details: dict = {"request_type": req["request_type"]}
            if new_status == "approved" and is_swap_with_target and swap_violations:
                audit_details["compliance_override"] = swap_violations
            await log_audit(conn, company_id, "request", request_id, current_user.id,
                            f"request.{new_status}", audit_details)

        row = await conn.fetchrow(
            f"{REQUEST_SELECT} WHERE r.id = $1 AND r.company_id = $2",
            request_id, company_id,
        )
    return serialize_request(dict(row))
