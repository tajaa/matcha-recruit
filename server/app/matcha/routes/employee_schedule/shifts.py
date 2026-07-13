"""Shift CRUD, publish, weekly view + roster (`/employee-schedule`).

Owns the package `router`; templates/assignments/requests attach their own
routers in __init__.py. Business-facing (admin/client), tenant-isolated.
"""

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.employee_schedule import (
    ShiftCreate, ShiftUpdate, PublishRange,
)
from ...services.schedule_rules import (
    build_patch, summarize_shifts as _summarize, week_bounds as _week_bounds,
)
from ._shared import (
    require_company_id, log_audit, fetch_shifts, fetch_roster, fetch_shift_by_id,
    assert_employee_in_company, assert_location_in_company,
    find_conflicts, raise_conflict,
)

router = APIRouter()


@router.get("/roster")
async def get_roster(current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        return {"employees": await fetch_roster(conn, company_id)}


@router.get("/shifts")
async def list_shifts(
    start: datetime = Query(...),
    end: datetime = Query(...),
    status: str | None = Query(None),
    current_user=Depends(require_admin_or_client),
):
    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        shifts = await fetch_shifts(conn, company_id, start, end, status=status)
    return {"shifts": shifts, "summary": _summarize(shifts)}


@router.get("/week")
async def get_week(
    start: date = Query(..., description="Week start date (YYYY-MM-DD)"),
    current_user=Depends(require_admin_or_client),
):
    """Weekly grid: the 7 days from `start`, plus the roster for the picker."""
    company_id = await require_company_id(current_user)
    lo, hi = _week_bounds(start)
    async with get_connection() as conn:
        # starts_within: the grid buckets by start date and publish_range only
        # publishes shifts starting in the window — matching on overlap here
        # would count a shift in the summary that no day column renders and no
        # publish touches.
        shifts = await fetch_shifts(conn, company_id, lo, hi, starts_within=True)
        roster = await fetch_roster(conn, company_id)
    return {
        "week_start": start.isoformat(),
        "shifts": shifts,
        "roster": roster,
        "summary": _summarize(shifts),
    }


@router.post("/shifts")
async def create_shift(body: ShiftCreate,
                       force: bool = Query(False, description="Assign despite overlapping shifts"),
                       current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, body.location_id)
        for emp_id in body.employee_ids:
            await assert_employee_in_company(conn, company_id, emp_id)
            if not force:
                conflicts = await find_conflicts(
                    conn, company_id, emp_id, body.starts_at, body.ends_at,
                )
                if conflicts:
                    raise_conflict(emp_id, conflicts)
        async with conn.transaction():
            shift_id = await conn.fetchval(
                """
                INSERT INTO schedule_shifts
                    (company_id, location_id, role, department, starts_at, ends_at,
                     break_minutes, required_staff, color, notes, created_by)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                RETURNING id
                """,
                company_id, body.location_id, body.role, body.department,
                body.starts_at, body.ends_at, body.break_minutes, body.required_staff,
                body.color, body.notes, current_user.id,
            )
            for emp_id in dict.fromkeys(body.employee_ids):
                await conn.execute(
                    """
                    INSERT INTO schedule_shift_assignments
                        (company_id, shift_id, employee_id, assigned_by)
                    VALUES ($1,$2,$3,$4)
                    ON CONFLICT (shift_id, employee_id) DO NOTHING
                    """,
                    company_id, shift_id, emp_id, current_user.id,
                )
            await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                            "shift.create", {"starts_at": body.starts_at.isoformat()})
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.put("/shifts/{shift_id}")
async def update_shift(shift_id: UUID, body: ShiftUpdate,
                       force: bool = Query(False, description="Retime despite overlapping shifts"),
                       current_user=Depends(require_admin_or_client)):
    """True PATCH: only the fields the caller sent are written, so an explicit
    null clears a nullable column (role, department, location, colour, notes).
    """
    company_id = await require_company_id(current_user)
    patch = body.model_dump(exclude_unset=True)
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT starts_at, ends_at, status, published_at
            FROM schedule_shifts WHERE id = $1 AND company_id = $2
            """,
            shift_id, company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Shift not found")
        if not patch:
            return await fetch_shift_by_id(conn, company_id, shift_id)
        if "location_id" in patch:
            await assert_location_in_company(conn, company_id, patch["location_id"])

        new_status = patch.get("status", existing["status"])
        # Cancelled is terminal for publication — POST /publish already refuses it
        # (`AND status <> 'cancelled'`), and a resurrected shift would reappear on
        # every assignee's portal. Reopening as a draft is the supported path.
        if existing["status"] == "cancelled" and new_status == "published":
            raise HTTPException(
                status_code=409,
                detail="Cannot publish a cancelled shift — reopen it as a draft first",
            )

        new_start = patch.get("starts_at") or existing["starts_at"]
        new_end = patch.get("ends_at") or existing["ends_at"]
        if new_end <= new_start:
            raise HTTPException(status_code=422, detail="ends_at must be after starts_at")

        # Retiming a staffed shift is an assignment path like any other: it can
        # double-book everyone already on it, so it takes the same guard + force.
        retimed = new_start != existing["starts_at"] or new_end != existing["ends_at"]
        if retimed and not force and new_status != "cancelled":
            assignees = await conn.fetch(
                "SELECT employee_id FROM schedule_shift_assignments WHERE shift_id = $1",
                shift_id,
            )
            for row in assignees:
                conflicts = await find_conflicts(
                    conn, company_id, row["employee_id"], new_start, new_end,
                    exclude_shift_id=shift_id,
                )
                if conflicts:
                    raise_conflict(row["employee_id"], conflicts)

        # published_at rides along as a patched column — no spliced CASE clause
        # whose hardcoded $10 silently rebinds when a column is added above it.
        if "status" in patch:
            if new_status == "published":
                if existing["published_at"] is None:
                    patch["published_at"] = datetime.now(timezone.utc)
            else:
                patch["published_at"] = None

        set_sql, params = build_patch(patch, first_param=3)
        async with conn.transaction():
            await conn.execute(
                f"""
                UPDATE schedule_shifts SET {set_sql}, updated_at = NOW()
                WHERE id = $1 AND company_id = $2
                """,
                shift_id, company_id, *params,
            )
            await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                            "shift.update", {"fields": sorted(patch)})
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.delete("/shifts/{shift_id}")
async def delete_shift(shift_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "DELETE FROM schedule_shifts WHERE id = $1 AND company_id = $2",
                shift_id, company_id,
            )
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Shift not found")
            await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                            "shift.delete", {})
    return {"ok": True, "id": str(shift_id)}


@router.post("/shifts/{shift_id}/publish")
async def publish_shift(shift_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE schedule_shifts
                SET status = 'published',
                    published_at = COALESCE(published_at, NOW()),
                    updated_at = NOW()
                WHERE id = $1 AND company_id = $2 AND status <> 'cancelled'
                RETURNING id
                """,
                shift_id, company_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Shift not found")
            await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                            "shift.publish", {})
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.post("/shifts/publish")
async def publish_range(body: PublishRange, current_user=Depends(require_admin_or_client)):
    """Publish every draft shift starting within [start, end)."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            count = await conn.fetchval(
                """
                WITH updated AS (
                    UPDATE schedule_shifts
                    SET status = 'published',
                        published_at = COALESCE(published_at, NOW()),
                        updated_at = NOW()
                    WHERE company_id = $1 AND status = 'draft'
                      AND starts_at >= $2 AND starts_at < $3
                    RETURNING id
                )
                SELECT COUNT(*) FROM updated
                """,
                company_id, body.start, body.end,
            )
            await log_audit(conn, company_id, "shift", None, current_user.id,
                            "shift.publish_range", {"count": count})
        # Same window semantics as the UPDATE above, so the returned summary
        # counts exactly the shifts this call could have published.
        shifts = await fetch_shifts(conn, company_id, body.start, body.end,
                                    starts_within=True)
    return {"published": count, "shifts": shifts, "summary": _summarize(shifts)}
