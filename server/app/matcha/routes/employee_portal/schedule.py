"""Employee self-service schedule views and bilateral shift requests."""
from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.models.scheduling.employee_schedule import (
    AvailabilityChangeRequestCreate, CounterpartyAccept, ScheduleRequestCreate,
)
from app.matcha.dependencies import require_employee_record
from app.matcha.services.scheduling.shift_requests import (
    WALL_CLOCK_NOW_SQL, find_same_day_assignments, same_day_conflict_detail,
    schedule_wall_clock_now,
)
from app.matcha.services.scheduling.time_off_guard import (
    PUBLISHED_WEEK_AVAILABILITY_DETAIL, PUBLISHED_WEEK_TIME_OFF_DETAIL,
    has_published_schedule_week,
)

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


@router.get("/me/schedule/open-seats", dependencies=_schedule_dep)
async def list_my_open_seats(
    start: datetime = Query(...),
    end: datetime = Query(...),
    employee: dict = Depends(require_employee_record),
):
    """Published future seats the employee may ask a manager to claim."""
    from app.matcha.routes.employee_schedule._shared import fetch_shifts
    from app.matcha.services.scheduling.schedule_profiles import fetch_effective_job_employee_ids

    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    company_id, employee_id = employee["org_id"], employee["id"]
    # Seats are only offered where a manager could actually approve them:
    # the employee's own store (a locationless shift is open to anyone, matching
    # assert_employee_schedulable_at), no other assignment that calendar day
    # (the same hard rule pickups and swaps enforce), and not yet started by the
    # store's clock — shift times are wall clock tagged UTC, so real NOW() would
    # hide a Pacific 5 PM seat from 10 AM local onwards.
    wall_now = WALL_CLOCK_NOW_SQL.format(tz="bl.timezone")
    async with get_connection() as conn:
        candidates = await conn.fetch(
            f"""
            SELECT s.id, s.job_id, s.starts_at,
                   EXISTS (
                       SELECT 1 FROM schedule_shift_assignments mine
                       JOIN schedule_shifts other ON other.id = mine.shift_id
                       WHERE mine.employee_id = $2
                         AND other.company_id = $1 AND other.status = 'published'
                         AND other.id <> s.id
                         AND other.starts_at < s.ends_at AND other.ends_at > s.starts_at
                   ) AS has_conflict
            FROM schedule_shifts s
            LEFT JOIN business_locations bl ON bl.id = s.location_id
            WHERE s.company_id = $1 AND s.status = 'published'
              AND s.starts_at >= {wall_now} AND s.starts_at >= $3 AND s.starts_at < $4
              AND (s.location_id IS NULL OR s.location_id = (
                    SELECT e.work_location_id FROM employees e WHERE e.id = $2))
              AND NOT EXISTS (
                    SELECT 1 FROM schedule_shift_assignments mine
                    JOIN schedule_shifts other ON other.id = mine.shift_id
                    WHERE mine.employee_id = $2 AND mine.status <> 'declined'
                      AND other.status <> 'cancelled' AND other.id <> s.id
                      AND other.starts_at < (date_trunc('day', s.starts_at AT TIME ZONE 'UTC') + INTERVAL '1 day') AT TIME ZONE 'UTC'
                      AND other.ends_at > date_trunc('day', s.starts_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
              AND (SELECT count(*) FROM schedule_shift_assignments a
                   WHERE a.shift_id = s.id) < s.required_staff
              AND NOT EXISTS (SELECT 1 FROM schedule_shift_assignments a
                              WHERE a.shift_id = s.id AND a.employee_id = $2)
              AND NOT EXISTS (SELECT 1 FROM schedule_requests r
                              WHERE r.shift_id = s.id AND r.employee_id = $2
                                AND r.request_type = 'claim'
                                AND r.status IN ('pending', 'awaiting_manager'))
            ORDER BY s.starts_at, s.id
            """,
            company_id, employee_id, start, end,
        )
        qualification: dict[tuple, bool] = {}
        eligible = []
        for row in candidates:
            key = (row["job_id"], row["starts_at"].date())
            if key not in qualification:
                qualified = await fetch_effective_job_employee_ids(
                    conn, company_id=company_id, job_id=row["job_id"],
                    employee_ids=[employee_id], as_of=key[1],
                )
                qualification[key] = employee_id in qualified
            if qualification[key]:
                eligible.append(row)
        shifts = await fetch_shifts(
            conn, company_id, start, end, status="published",
            shift_ids=[row["id"] for row in eligible],
        )
    conflicts = {str(row["id"]): row["has_conflict"] for row in eligible}
    for shift in shifts:
        shift["has_conflict"] = conflicts[shift["id"]]
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
    """Stage a schedule request; no assignment write occurs."""
    from app.matcha.routes.employee_schedule._shared import (
        INACTIVE_EMPLOYMENT_STATUSES, REQUEST_SELECT, log_audit, serialize_request,
    )

    company_id = employee["org_id"]
    async with get_connection() as conn:
        if (
            body.request_type == "unavailable"
            and await has_published_schedule_week(
                conn, company_id, body.unavailable_start, body.unavailable_end,
            )
        ):
            raise HTTPException(status_code=409, detail=PUBLISHED_WEEK_TIME_OFF_DETAIL)
        if body.request_type == "pickup" and body.target_employee_id is not None:
            raise HTTPException(status_code=422, detail="Pickup offers cannot name a target employee")
        # swap/drop/pickup must reference a PUBLISHED shift the employee is actually on.
        # GET /me/schedule only serves published shifts, so anything else is a
        # shift this employee was never shown — and the response would echo its
        # window back, leaking an unpublished draft.
        if body.shift_id is not None and body.request_type != "claim":
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
            if body.request_type == "claim":
                from app.matcha.routes.employee_schedule._shared import assert_employee_schedulable_at
                from app.matcha.services.scheduling.schedule_profiles import fetch_effective_job_employee_ids

                shift = await conn.fetchrow(
                    """SELECT s.id, s.status, s.starts_at, s.required_staff, s.job_id,
                              s.location_id, bl.timezone
                       FROM schedule_shifts s
                       LEFT JOIN business_locations bl ON bl.id = s.location_id
                       WHERE s.id=$1 AND s.company_id=$2 FOR UPDATE OF s""",
                    body.shift_id, company_id,
                )
                if not shift or shift["status"] != "published":
                    raise HTTPException(status_code=404, detail="Open shift not found")
                if shift["starts_at"] <= schedule_wall_clock_now(shift["timezone"]):
                    raise HTTPException(status_code=409, detail="This shift has already started")
                # Same gates approval will apply — reject now rather than let a
                # manager hit an unforceable 422 later.
                await assert_employee_schedulable_at(conn, company_id, employee["id"], shift["location_id"])
                same_day = await find_same_day_assignments(conn, company_id, employee["id"], shift["starts_at"])
                if same_day:
                    raise HTTPException(status_code=409, detail=same_day_conflict_detail(employee["id"], same_day))
                assigned = await conn.fetchval(
                    """SELECT count(*) FROM schedule_shift_assignments
                       WHERE shift_id=$1""", body.shift_id,
                )
                if assigned >= shift["required_staff"]:
                    raise HTTPException(status_code=409, detail="This shift has no open seats")
                if await conn.fetchval(
                    """SELECT 1 FROM schedule_shift_assignments
                       WHERE shift_id=$1 AND employee_id=$2""",
                    body.shift_id, employee["id"],
                ):
                    raise HTTPException(status_code=409, detail="You are already on this shift")
                if employee["id"] not in await fetch_effective_job_employee_ids(
                    conn, company_id=company_id, job_id=shift["job_id"],
                    employee_ids=[employee["id"]], as_of=shift["starts_at"].date(),
                ):
                    raise HTTPException(status_code=409, detail="You are not qualified for this shift")
                if await conn.fetchval(
                    """SELECT 1 FROM schedule_requests WHERE employee_id=$1 AND shift_id=$2
                       AND request_type='claim' AND status IN ('pending', 'awaiting_manager')""",
                    employee["id"], body.shift_id,
                ):
                    raise HTTPException(status_code=409, detail="You already claimed this shift")
            # Each drop / time-off submission emails and bells every manager, so a
            # repeat click must not fan out again. The partial unique indexes in
            # empsched25 back this up under concurrency.
            if body.request_type == "drop" and await conn.fetchval(
                """SELECT 1 FROM schedule_requests WHERE employee_id=$1 AND shift_id=$2
                   AND request_type='drop' AND status IN ('pending', 'awaiting_manager')""",
                employee["id"], body.shift_id,
            ):
                raise HTTPException(status_code=409, detail="You already asked to drop this shift")
            if body.request_type == "unavailable" and await conn.fetchval(
                """SELECT 1 FROM schedule_requests WHERE employee_id=$1
                   AND unavailable_start=$2 AND unavailable_end=$3
                   AND request_type='unavailable' AND status IN ('pending', 'awaiting_manager')""",
                employee["id"], body.unavailable_start, body.unavailable_end,
            ):
                raise HTTPException(status_code=409, detail="You already have this time-off request pending")
            try:
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
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=409, detail="You already have this request pending") from None
            await log_audit(
                conn, company_id, "request", request_id, employee.get("user_id"),
                "request.create", {"request_type": body.request_type},
            )
        row = await conn.fetchrow(
            f"{REQUEST_SELECT} WHERE r.id = $1", request_id,
        )
    if body.request_type in ("drop", "unavailable", "claim"):
        _dispatch_manager_ready(request_id)
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


def _dispatch_manager_ready(request_id: UUID) -> None:
    """Post-commit dispatch; the recovery sweep handles broker outages."""
    from app.workers.tasks.schedule_request_notifications import send_schedule_request_notifications
    try:
        send_schedule_request_notifications.delay(str(request_id))
    except Exception:
        pass


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
    """Current availability plus the change the employee is waiting on.

    There is no PUT counterpart: an employee's own availability edit is a
    request a manager approves (see the POST below), so this response has to
    carry the pending proposal or the portal cannot show what was asked for.
    """
    from app.matcha.routes.employee_schedule._shared import REQUEST_SELECT, serialize_request
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
        pending = await conn.fetchrow(
            f"{REQUEST_SELECT} WHERE r.employee_id = $1 AND r.company_id = $2 "
            "AND r.request_type = 'availability' "
            "AND r.status IN ('pending', 'awaiting_manager') "
            "ORDER BY r.created_at DESC LIMIT 1",
            employee["id"], employee["org_id"],
        )
    return {
        "availability_state": profile.availability_state,
        "windows": windows,
        "pending_request": serialize_request(dict(pending)) if pending else None,
    }


@router.post("/me/schedule/availability-requests", dependencies=_schedule_dep)
async def request_my_availability_change(
    body: AvailabilityChangeRequestCreate,
    employee: dict = Depends(require_employee_record),
):
    """Submit an availability change for manager approval.

    Nothing about the employee's live availability changes here — the proposal
    is stored on the request and only written through on approval, on or after
    ``effective_on`` (services/scheduling/availability_requests.py).
    """
    from app.matcha.routes.employee_schedule._shared import (
        REQUEST_SELECT, log_audit, serialize_request,
    )
    from app.matcha.services.scheduling.availability_requests import (
        serialize_proposed_availability,
    )
    from app.matcha.services.scheduling.schedule_profiles import (
        effective_availability_state,
    )

    company_id = employee["org_id"]
    resolved_state = effective_availability_state(
        body.availability.availability_state, body.availability.windows,
    )
    async with get_connection() as conn:
        # CURRENT_DATE, not the server process's clock: every other date rule on
        # this surface (the published-week guard, promotion) is decided by the
        # database, and two clocks would disagree at the day boundary.
        today = await conn.fetchval("SELECT CURRENT_DATE")
        if body.effective_on < today:
            raise HTTPException(
                status_code=422,
                detail="Availability changes can only start today or later.",
            )
        if await has_published_schedule_week(
            conn, company_id, body.effective_on, body.effective_on,
        ):
            raise HTTPException(
                status_code=409, detail=PUBLISHED_WEEK_AVAILABILITY_DETAIL,
            )
        async with conn.transaction():
            existing = await conn.fetchval(
                """SELECT 1 FROM schedule_requests
                    WHERE employee_id = $1 AND company_id = $2
                      AND request_type = 'availability'
                      AND status IN ('pending', 'awaiting_manager')
                    FOR UPDATE""",
                employee["id"], company_id,
            )
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "You already have an availability change awaiting review. "
                        "Withdraw it before submitting another."
                    ),
                )
            request_id = await conn.fetchval(
                """
                INSERT INTO schedule_requests
                    (company_id, employee_id, request_type, reason, status,
                     proposed_availability, availability_effective_on)
                VALUES ($1,$2,'availability',$3,'awaiting_manager',$4::jsonb,$5)
                RETURNING id
                """,
                company_id, employee["id"], body.reason,
                serialize_proposed_availability(resolved_state, body.availability.windows),
                body.effective_on,
            )
            await log_audit(
                conn, company_id, "request", request_id, employee.get("user_id"),
                "request.create",
                {"request_type": "availability",
                 "availability_state": resolved_state,
                 "windows": len(body.availability.windows),
                 "effective_on": body.effective_on.isoformat()},
            )
        row = await conn.fetchrow(f"{REQUEST_SELECT} WHERE r.id = $1", request_id)
    _dispatch_manager_ready(request_id)
    return serialize_request(dict(row))


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
