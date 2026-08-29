"""Employee self-service schedule views and bilateral shift requests."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.models.scheduling.employee_schedule import (
    AvailabilityReplace, CounterpartyAccept, ScheduleRequestCreate,
)
from app.matcha.dependencies import require_employee_record

from ._shared import _schedule_dep

router = APIRouter()


@router.get("/me/schedule", dependencies=_schedule_dep)
async def get_my_schedule(
    start: datetime = Query(...),
    end: datetime = Query(...),
    team: bool = Query(False),
    employee: dict = Depends(require_employee_record),
):
    """Published shifts for the signed-in employee or their company team."""
    from app.matcha.routes.employee_schedule._shared import fetch_shifts

    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    async with get_connection() as conn:
        shifts = await fetch_shifts(
            conn, employee["org_id"], start, end,
            status="published", employee_id=None if team else employee["id"],
        )
    if team:
        # Team visibility supports finding coverage without exposing private
        # manager notes, individualized guidance, or assignment controls.
        for shift in shifts:
            shift["assignments"] = [
                {key: assignment[key] for key in ("employee_id", "name", "job_title", "status")}
                for assignment in shift["assignments"]
            ]
    return {"shifts": shifts}


@router.get("/me/schedule/requests", dependencies=_schedule_dep)
async def list_my_schedule_requests(
    employee: dict = Depends(require_employee_record),
):
    from app.matcha.routes.employee_schedule._shared import REQUEST_SELECT, serialize_request

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{REQUEST_SELECT} WHERE (r.employee_id = $1 OR r.target_employee_id = $1) "
            "ORDER BY r.created_at DESC LIMIT 200",
            employee["id"],
        )
    return {"requests": [
        {**serialize_request(dict(r)), "can_withdraw": r["employee_id"] == employee["id"]}
        for r in rows
    ]}


@router.get("/me/schedule/offers", dependencies=_schedule_dep)
async def list_schedule_offers(employee: dict = Depends(require_employee_record)):
    """Return open pickup offers and swaps addressed to this employee."""
    from app.matcha.routes.employee_schedule._shared import REQUEST_SELECT, serialize_request

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{REQUEST_SELECT} WHERE r.company_id = $1 "
            "AND r.status = 'awaiting_counterparty' "
            "AND ((r.request_type = 'pickup' AND r.employee_id <> $2) "
            "OR (r.request_type = 'swap' AND r.target_employee_id = $2)) "
            "ORDER BY r.created_at ASC LIMIT 200",
            employee["org_id"], employee["id"],
        )
    return {"offers": [serialize_request(dict(r)) for r in rows]}


@router.get("/me/schedule/coworkers", dependencies=_schedule_dep)
async def list_schedule_coworkers(employee: dict = Depends(require_employee_record)):
    """Active same-company employees available as named swap partners."""
    from app.matcha.routes.employee_schedule._shared import INACTIVE_EMPLOYMENT_STATUSES

    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, first_name, last_name
               FROM employees
               WHERE org_id = $1 AND id <> $2
                 AND COALESCE(employment_status, 'active') <> ALL($3::text[])
               ORDER BY first_name, last_name""",
            employee["org_id"], employee["id"], list(INACTIVE_EMPLOYMENT_STATUSES),
        )
    return {"employees": [
        {"id": str(r["id"]), "name": f"{(r['first_name'] or '').strip()} {(r['last_name'] or '').strip()}".strip() or "Unnamed"}
        for r in rows
    ]}


@router.post("/me/schedule/requests", dependencies=_schedule_dep)
async def create_my_schedule_request(
    body: ScheduleRequestCreate,
    employee: dict = Depends(require_employee_record),
):
    """Stage a pickup/swap for counterparty acceptance; no schedule write occurs."""
    from app.matcha.routes.employee_schedule._shared import (
        INACTIVE_EMPLOYMENT_STATUSES, REQUEST_SELECT, log_audit, serialize_request,
    )

    company_id = employee["org_id"]
    async with get_connection() as conn:
        if body.request_type == "unavailable":
            published_week_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM schedule_shifts s
                    WHERE s.company_id = $1
                      AND s.status = 'published'
                      AND s.starts_at::date - EXTRACT(DOW FROM s.starts_at)::integer <= $3
                      AND s.starts_at::date - EXTRACT(DOW FROM s.starts_at)::integer + 6 >= $2
                )
                """,
                company_id, body.unavailable_start, body.unavailable_end,
            )
            if published_week_exists:
                raise HTTPException(
                    status_code=409,
                    detail="Time-off requests cannot be submitted for a week with published shifts. Choose a different week.",
                )
        if body.request_type == "pickup" and body.target_employee_id is not None:
            raise HTTPException(status_code=422, detail="Pickup offers cannot name a target employee")
        # swap/drop/pickup must reference a PUBLISHED shift the employee is actually on.
        # GET /me/schedule only serves published shifts, so anything else is a
        # shift this employee was never shown — and the response would echo its
        # window back, leaking an unpublished draft.
        if body.shift_id is not None:
            shift = await conn.fetchrow(
                """
                SELECT s.status
                FROM schedule_shifts s
                JOIN schedule_shift_assignments a
                  ON a.shift_id = s.id AND a.employee_id = $2 AND a.status <> 'declined'
                WHERE s.id = $1 AND s.company_id = $3
                """,
                body.shift_id, employee["id"], company_id,
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
        if body.counter_shift_id is not None:
            counter = await conn.fetchrow(
                """
                SELECT s.status
                FROM schedule_shifts s
                JOIN schedule_shift_assignments a
                  ON a.shift_id = s.id AND a.employee_id = $2 AND a.status <> 'declined'
                WHERE s.id = $1 AND s.company_id = $3
                """,
                body.counter_shift_id, body.target_employee_id, company_id,
            )
            if not counter or counter["status"] != "published":
                raise HTTPException(
                    status_code=404,
                    detail="Selected coworker shift is no longer available",
                )

        async with conn.transaction():
            request_id = await conn.fetchval(
                """
                INSERT INTO schedule_requests
                    (company_id, employee_id, request_type, shift_id, target_employee_id, counter_shift_id,
                     unavailable_start, unavailable_end, reason, status)
                VALUES ($1,$2,$3::text,$4,$5,$6,$7,$8,$9,
                        CASE WHEN $3::text IN ('pickup', 'swap')
                              THEN 'awaiting_counterparty' ELSE 'awaiting_manager' END)
                RETURNING id
                """,
                company_id, employee["id"], body.request_type, body.shift_id,
                body.target_employee_id, body.counter_shift_id, body.unavailable_start,
                body.unavailable_end, body.reason,
            )
            await log_audit(
                conn, company_id, "request", request_id, employee.get("user_id"),
                "request.create", {"request_type": body.request_type},
            )
        row = await conn.fetchrow(
            f"{REQUEST_SELECT} WHERE r.id = $1", request_id,
        )
    return serialize_request(dict(row))


@router.post("/me/schedule/requests/{request_id}/accept", dependencies=_schedule_dep)
async def accept_schedule_request(
    request_id: UUID,
    body: CounterpartyAccept,
    employee: dict = Depends(require_employee_record),
):
    """Accept a pickup/swap and move it into the manager approval queue.

    The request and involved shifts are locked in one transaction.  A same-day
    assignment is a hard conflict and cannot be overridden by a manager.
    """
    from app.matcha.routes.employee_schedule._shared import (
        log_audit, REQUEST_SELECT, serialize_request, fetch_locked_shift_pair,
    )
    from app.matcha.services.scheduling.shift_requests import (
        find_same_day_assignments, same_day_conflict_detail,
    )

    company_id = employee["org_id"]
    async with get_connection() as conn:
        async with conn.transaction():
            request = await conn.fetchrow(
                """SELECT id, employee_id, request_type, shift_id, target_employee_id,
                          counter_shift_id, status
                   FROM schedule_requests
                   WHERE id = $1 AND company_id = $2
                   FOR UPDATE""",
                request_id, company_id,
            )
            if not request or request["status"] != "awaiting_counterparty":
                raise HTTPException(status_code=404, detail="Offer is no longer available")
            if request["employee_id"] == employee["id"]:
                raise HTTPException(status_code=409, detail="You cannot accept your own offer")
            active = await conn.fetchval(
                """SELECT COALESCE(employment_status, 'active')
                   FROM employees WHERE id = $1 AND org_id = $2""",
                employee["id"], company_id,
            )
            if active is None or active in ("terminated", "offboarded"):
                raise HTTPException(status_code=409, detail="Inactive employees cannot accept shifts")
            if request["request_type"] == "swap":
                if request["target_employee_id"] != employee["id"]:
                    raise HTTPException(status_code=403, detail="Swap is addressed to another employee")
                counter_shift_id = request["counter_shift_id"] or body.counter_shift_id
                if counter_shift_id is None:
                    raise HTTPException(status_code=422, detail="counter_shift_id is required for a swap")
                if request["counter_shift_id"] and body.counter_shift_id not in (None, request["counter_shift_id"]):
                    raise HTTPException(status_code=422, detail="Accept the shift selected in the swap request")
                if counter_shift_id == request["shift_id"]:
                    raise HTTPException(status_code=422, detail="A swap needs two different shifts")
            elif request["request_type"] == "pickup":
                counter_shift_id = None
                if body.counter_shift_id is not None:
                    raise HTTPException(status_code=422, detail="Pickup acceptance cannot include a counter shift")
            else:
                raise HTTPException(status_code=409, detail="This request cannot be accepted")

            lock_ids = [request["shift_id"]]
            if counter_shift_id is not None:
                lock_ids.append(counter_shift_id)
            locked = await fetch_locked_shift_pair(conn, company_id, *lock_ids)
            offered = locked.get(str(request["shift_id"]))
            if not offered or offered["status"] != "published":
                raise HTTPException(status_code=409, detail="Offered shift is no longer published")
            owner_assignment = await conn.fetchval(
                """SELECT 1 FROM schedule_shift_assignments
                   WHERE company_id = $1 AND shift_id = $2 AND employee_id = $3
                     AND status <> 'declined'""",
                company_id, request["shift_id"], request["employee_id"],
            )
            if not owner_assignment:
                raise HTTPException(status_code=409, detail="Offered shift is no longer assigned to its owner")

            if counter_shift_id is not None:
                counter = locked.get(str(counter_shift_id))
                if not counter or counter["status"] != "published":
                    raise HTTPException(status_code=409, detail="Counter shift is no longer published")
                counter_assignment = await conn.fetchval(
                    """SELECT 1 FROM schedule_shift_assignments
                       WHERE company_id = $1 AND shift_id = $2 AND employee_id = $3
                         AND status <> 'declined'""",
                    company_id, counter_shift_id, employee["id"],
                )
                if not counter_assignment:
                    raise HTTPException(status_code=409, detail="You are not assigned to the counter shift")

            conflicts = await find_same_day_assignments(
                conn, company_id, employee["id"], offered["starts_at"],
                exclude_shift_ids=([counter_shift_id] if counter_shift_id else []),
            )
            if conflicts:
                raise HTTPException(
                    status_code=409,
                    detail=same_day_conflict_detail(employee["id"], conflicts),
                )
            if request["request_type"] == "swap":
                reverse_conflicts = await find_same_day_assignments(
                    conn, company_id, request["employee_id"], counter["starts_at"],
                    exclude_shift_ids=[request["shift_id"]],
                )
                if reverse_conflicts:
                    raise HTTPException(
                        status_code=409,
                        detail=same_day_conflict_detail(request["employee_id"], reverse_conflicts),
                    )

            await conn.execute(
                """UPDATE schedule_requests
                   SET target_employee_id = CASE WHEN request_type = 'pickup'
                                                 THEN $2 ELSE target_employee_id END,
                       counter_shift_id = $3, counterparty_confirmed_at = NOW(),
                       status = 'awaiting_manager', updated_at = NOW()
                   WHERE id = $1""",
                request_id, employee["id"], counter_shift_id,
            )
            await log_audit(
                conn, company_id, "request", request_id, employee.get("user_id"),
                "request.counterparty_confirmed",
                {"counterparty_employee_id": str(employee["id"]),
                 "counter_shift_id": str(counter_shift_id) if counter_shift_id else None},
            )
        row = await conn.fetchrow(f"{REQUEST_SELECT} WHERE r.id = $1", request_id)
    # Queue after the transaction commits: delivery can retry, but cannot
    # produce a notification for a confirmation that later rolled back.
    from app.workers.tasks.schedule_request_notifications import send_schedule_request_notifications
    try:
        send_schedule_request_notifications.delay(str(request_id))
    except Exception:
        # Confirmation is committed and must not be reported as failed merely
        # because the broker is momentarily unavailable. The pool-free worker
        # recovery sweep discovers the manager-ready request later.
        pass
    return serialize_request(dict(row))


@router.post("/me/schedule/requests/{request_id}/withdraw", dependencies=_schedule_dep)
async def withdraw_schedule_request(
    request_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Withdraw an offer or a counterparty acceptance before manager review."""
    from app.matcha.routes.employee_schedule._shared import log_audit
    from app.matcha.services.scheduling.schedule_request_notifications import (
        mark_manager_ready_notifications_resolved,
    )

    company_id = employee["org_id"]
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT id, employee_id, request_type, target_employee_id, status
                   FROM schedule_requests WHERE id = $1 AND company_id = $2 FOR UPDATE""",
                request_id, company_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Request not found")
            if row["status"] not in ("awaiting_counterparty", "awaiting_manager"):
                raise HTTPException(status_code=409, detail="Request cannot be withdrawn now")
            if row["employee_id"] == employee["id"]:
                await conn.execute(
                    "UPDATE schedule_requests SET status = 'cancelled', updated_at = NOW() WHERE id = $1",
                    request_id,
                )
            elif row["status"] == "awaiting_manager" and row["target_employee_id"] == employee["id"]:
                await conn.execute(
                    """UPDATE schedule_requests
                       SET target_employee_id = CASE WHEN request_type = 'pickup' THEN NULL ELSE target_employee_id END,
                           counter_shift_id = CASE WHEN request_type = 'pickup' THEN NULL ELSE counter_shift_id END,
                           counterparty_confirmed_at = NULL,
                           status = 'awaiting_counterparty', updated_at = NOW()
                       WHERE id = $1""",
                    request_id,
                )
            else:
                raise HTTPException(status_code=403, detail="You cannot withdraw this request")
            if row["status"] == "awaiting_manager":
                await mark_manager_ready_notifications_resolved(
                    conn, company_id=company_id, request_id=request_id,
                )
            await log_audit(
                conn, company_id, "request", request_id, employee.get("user_id"),
                "request.withdraw", {"employee_id": str(employee["id"])},
            )
    return {"status": "withdrawn", "request_id": str(request_id)}


@router.get("/me/schedule/availability", dependencies=_schedule_dep)
async def get_my_availability(employee: dict = Depends(require_employee_record)):
    from app.matcha.services.scheduling.schedule_profiles import (
        fetch_availability_windows, fetch_schedule_profile,
    )
    async with get_connection() as conn:
        windows = await fetch_availability_windows(
            conn, company_id=employee["org_id"], employee_id=employee["id"],
        )
        profile = await fetch_schedule_profile(
            conn, company_id=employee["org_id"], employee_id=employee["id"],
        )
    return {"availability_state": profile.availability_state, "windows": windows}


@router.put("/me/schedule/availability", dependencies=_schedule_dep)
async def replace_my_availability(
    body: AvailabilityReplace,
    employee: dict = Depends(require_employee_record),
):
    """Full replacement; omitted state preserves legacy empty=always behavior."""
    from app.matcha.services.scheduling.schedule_profiles import replace_availability_core

    company_id = employee["org_id"]
    async with get_connection() as conn:
        async with conn.transaction():
            result = await replace_availability_core(
                conn, company_id=company_id, employee_id=employee["id"],
                availability_state=body.availability_state, windows=body.windows,
                actor_user_id=employee.get("user_id"), actor_kind="employee",
            )
    return {"saved": result["saved"], "availability_state": result["state"]}


@router.delete("/me/schedule/requests/{request_id}", dependencies=_schedule_dep)
async def cancel_my_schedule_request(
    request_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Backward-compatible cancellation endpoint for requests I filed."""
    from app.matcha.services.scheduling.schedule_request_notifications import (
        mark_manager_ready_notifications_resolved,
    )

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE schedule_requests
                SET status = 'cancelled', updated_at = NOW()
                WHERE id = $1 AND employee_id = $2
                  AND status IN ('pending', 'awaiting_counterparty', 'awaiting_manager')
                RETURNING id
                """,
                request_id, employee["id"],
            )
            if not row:
                raise HTTPException(status_code=404, detail="Pending request not found")
            await mark_manager_ready_notifications_resolved(
                conn, company_id=employee["org_id"], request_id=request_id,
            )
    return {"status": "cancelled", "request_id": str(request_id)}
