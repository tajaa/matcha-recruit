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
    require_company_id, log_audit, serialize_request,
    find_conflicts, raise_conflict,
)

router = APIRouter()

_REQUEST_SELECT = """
    SELECT r.id, r.employee_id, r.request_type, r.shift_id, r.target_employee_id,
           r.unavailable_start, r.unavailable_end, r.reason, r.status,
           r.review_notes, r.reviewed_at, r.created_at,
           e.first_name, e.last_name,
           s.starts_at AS shift_starts_at, s.ends_at AS shift_ends_at
    FROM schedule_requests r
    JOIN employees e ON e.id = r.employee_id
    LEFT JOIN schedule_shifts s ON s.id = r.shift_id
"""


@router.get("/requests")
async def list_requests(
    status: str | None = Query(None),
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    params = [company_id]
    where = "r.company_id = $1"
    if status is not None:
        params.append(status)
        where += " AND r.status = $2"
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{_REQUEST_SELECT} WHERE {where} ORDER BY r.created_at DESC",
            *params,
        )
    return {"requests": [serialize_request(dict(r)) for r in rows]}


@router.post("/requests/{request_id}/review")
async def review_request(request_id: UUID, body: RequestReview,
                         current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    new_status = "approved" if body.decision == "approved" else "denied"
    async with get_connection() as conn:
        req = await conn.fetchrow(
            """
            SELECT id, request_type, shift_id, employee_id, target_employee_id, status
            FROM schedule_requests
            WHERE id = $1 AND company_id = $2
            """,
            request_id, company_id,
        )
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        if req["status"] != "pending":
            raise HTTPException(status_code=409, detail="Request already reviewed")

        # Approving a swap onto a target who's already scheduled then would
        # silently double-book them — surface it (admin can re-approve with force).
        if (
            new_status == "approved"
            and not body.force
            and req["request_type"] == "swap"
            and req["shift_id"] is not None
            and req["target_employee_id"] is not None
        ):
            window = await conn.fetchrow(
                "SELECT starts_at, ends_at FROM schedule_shifts WHERE id = $1",
                req["shift_id"],
            )
            if window:
                conflicts = await find_conflicts(
                    conn, company_id, req["target_employee_id"],
                    window["starts_at"], window["ends_at"],
                    exclude_shift_id=req["shift_id"],
                )
                if conflicts:
                    raise_conflict(req["target_employee_id"], conflicts)

        async with conn.transaction():
            await conn.execute(
                """
                UPDATE schedule_requests
                SET status = $3, review_notes = $4, reviewed_by = $5,
                    reviewed_at = NOW(), updated_at = NOW()
                WHERE id = $1 AND company_id = $2
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
                if req["request_type"] == "swap" and req["target_employee_id"] is not None:
                    # Only assign a target that still belongs to the company.
                    valid = await conn.fetchval(
                        "SELECT 1 FROM employees WHERE id = $1 AND org_id = $2",
                        req["target_employee_id"], company_id,
                    )
                    if valid:
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

            await log_audit(conn, company_id, "request", request_id, current_user.id,
                            f"request.{new_status}", {"request_type": req["request_type"]})

        row = await conn.fetchrow(
            f"{_REQUEST_SELECT} WHERE r.id = $1 AND r.company_id = $2",
            request_id, company_id,
        )
    return serialize_request(dict(row))
