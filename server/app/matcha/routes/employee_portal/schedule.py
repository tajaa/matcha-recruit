"""Employee self-service schedule views + swap/drop/unavailability requests."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.models.scheduling.employee_schedule import (
    AvailabilityReplace, ScheduleRequestCreate,
)
from app.matcha.dependencies import require_employee_record

from ._shared import _schedule_dep

router = APIRouter()


@router.get("/me/schedule", dependencies=_schedule_dep)
async def get_my_schedule(
    start: datetime = Query(...),
    end: datetime = Query(...),
    employee: dict = Depends(require_employee_record),
):
    """The signed-in employee's PUBLISHED shifts overlapping [start, end)."""
    from app.matcha.routes.employee_schedule._shared import fetch_shifts

    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    async with get_connection() as conn:
        shifts = await fetch_shifts(
            conn, employee["org_id"], start, end,
            status="published", employee_id=employee["id"],
        )
    return {"shifts": shifts}


@router.get("/me/schedule/requests", dependencies=_schedule_dep)
async def list_my_schedule_requests(
    employee: dict = Depends(require_employee_record),
):
    from app.matcha.routes.employee_schedule._shared import REQUEST_SELECT, serialize_request

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{REQUEST_SELECT} WHERE r.employee_id = $1 ORDER BY r.created_at DESC LIMIT 200",
            employee["id"],
        )
    return {"requests": [serialize_request(dict(r)) for r in rows]}


@router.post("/me/schedule/requests", dependencies=_schedule_dep)
async def create_my_schedule_request(
    body: ScheduleRequestCreate,
    employee: dict = Depends(require_employee_record),
):
    """File a swap / drop / unavailability request against my own schedule."""
    from app.matcha.routes.employee_schedule._shared import (
        INACTIVE_EMPLOYMENT_STATUSES, REQUEST_SELECT, log_audit, serialize_request,
    )

    company_id = employee["org_id"]
    async with get_connection() as conn:
        # swap/drop must reference a PUBLISHED shift the employee is actually on.
        # GET /me/schedule only serves published shifts, so anything else is a
        # shift this employee was never shown — and the response would echo its
        # window back, leaking an unpublished draft.
        if body.shift_id is not None:
            shift = await conn.fetchrow(
                """
                SELECT s.status
                FROM schedule_shifts s
                JOIN schedule_shift_assignments a
                  ON a.shift_id = s.id AND a.employee_id = $2
                WHERE s.id = $1
                """,
                body.shift_id, employee["id"],
            )
            if not shift or shift["status"] != "published":
                raise HTTPException(
                    status_code=404,
                    detail="Shift not found on your schedule",
                )
        # A named swap target must belong to the same company and still be employable.
        if body.target_employee_id is not None:
            target = await conn.fetchrow(
                """
                SELECT COALESCE(employment_status, 'active') AS employment_status
                FROM employees WHERE id = $1 AND org_id = $2
                """,
                body.target_employee_id, company_id,
            )
            if not target:
                raise HTTPException(status_code=404, detail="Target employee not found")
            if target["employment_status"] in INACTIVE_EMPLOYMENT_STATUSES:
                raise HTTPException(
                    status_code=409,
                    detail="That coworker is no longer active and can't take the shift",
                )

        async with conn.transaction():
            request_id = await conn.fetchval(
                """
                INSERT INTO schedule_requests
                    (company_id, employee_id, request_type, shift_id, target_employee_id,
                     unavailable_start, unavailable_end, reason)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                RETURNING id
                """,
                company_id, employee["id"], body.request_type, body.shift_id,
                body.target_employee_id, body.unavailable_start, body.unavailable_end,
                body.reason,
            )
            await log_audit(
                conn, company_id, "request", request_id, employee.get("user_id"),
                "request.create", {"request_type": body.request_type},
            )
        row = await conn.fetchrow(
            f"{REQUEST_SELECT} WHERE r.id = $1", request_id,
        )
    return serialize_request(dict(row))


@router.get("/me/schedule/availability", dependencies=_schedule_dep)
async def get_my_availability(employee: dict = Depends(require_employee_record)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT weekday, start_time, end_time FROM schedule_employee_availability "
            "WHERE company_id = $1 AND employee_id = $2 ORDER BY weekday, start_time",
            employee["org_id"], employee["id"],
        )
    return {"windows": [
        {"weekday": r["weekday"], "start_time": str(r["start_time"])[:5],
         "end_time": str(r["end_time"])[:5]} for r in rows]}


@router.put("/me/schedule/availability", dependencies=_schedule_dep)
async def replace_my_availability(
    body: AvailabilityReplace,
    employee: dict = Depends(require_employee_record),
):
    """Full replacement. Empty windows list clears availability entirely
    (= back to fully available)."""
    from app.matcha.routes.employee_schedule._shared import log_audit

    company_id = employee["org_id"]
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM schedule_employee_availability WHERE company_id = $1 AND employee_id = $2",
                company_id, employee["id"],
            )
            for w in body.windows:
                await conn.execute(
                    "INSERT INTO schedule_employee_availability "
                    "(company_id, employee_id, weekday, start_time, end_time) "
                    "VALUES ($1,$2,$3,$4,$5)",
                    company_id, employee["id"], w.weekday, w.start_time, w.end_time,
                )
            await log_audit(conn, company_id, "availability", employee["id"],
                            employee.get("user_id"), "availability.update",
                            {"windows": len(body.windows), "actor": "employee"})
    return {"saved": len(body.windows)}


@router.delete("/me/schedule/requests/{request_id}", dependencies=_schedule_dep)
async def cancel_my_schedule_request(
    request_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Cancel a still-pending request I filed."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE schedule_requests
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = $1 AND employee_id = $2 AND status = 'pending'
            RETURNING id
            """,
            request_id, employee["id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="Pending request not found")
    return {"status": "cancelled", "request_id": str(request_id)}
