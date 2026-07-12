"""Shift CRUD, publish, weekly view + roster (`/employee-schedule`).

Owns the package `router`; templates/assignments/requests attach their own
routers in __init__.py. Business-facing (admin/client), tenant-isolated.
"""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import get_connection
from ...dependencies import require_admin_or_client
from ...models.employee_schedule import (
    ShiftCreate, ShiftUpdate, PublishRange,
)
from ._shared import (
    require_company_id, log_audit, fetch_shifts, fetch_roster, fetch_shift_by_id,
    assert_employee_in_company, assert_location_in_company,
)

router = APIRouter()


def _week_bounds(start: date) -> tuple[datetime, datetime]:
    lo = datetime.combine(start, time.min, tzinfo=timezone.utc)
    return lo, lo + timedelta(days=7)


def _summarize(shifts: list[dict]) -> dict:
    published = sum(1 for s in shifts if s["status"] == "published")
    draft = sum(1 for s in shifts if s["status"] == "draft")
    open_shifts = sum(
        1 for s in shifts
        if s["status"] != "cancelled" and len(s["assignments"]) < s["required_staff"]
    )
    assigned = sum(len(s["assignments"]) for s in shifts)
    return {
        "total_shifts": len(shifts),
        "published": published,
        "draft": draft,
        "open_shifts": open_shifts,
        "assigned": assigned,
    }


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
        shifts = await fetch_shifts(conn, company_id, lo, hi)
        roster = await fetch_roster(conn, company_id)
    return {
        "week_start": start.isoformat(),
        "shifts": shifts,
        "roster": roster,
        "summary": _summarize(shifts),
    }


@router.post("/shifts")
async def create_shift(body: ShiftCreate, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, body.location_id)
        for emp_id in body.employee_ids:
            await assert_employee_in_company(conn, company_id, emp_id)
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
                       current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT starts_at, ends_at FROM schedule_shifts WHERE id = $1 AND company_id = $2",
            shift_id, company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Shift not found")
        await assert_location_in_company(conn, company_id, body.location_id)

        new_start = body.starts_at or existing["starts_at"]
        new_end = body.ends_at or existing["ends_at"]
        if new_end <= new_start:
            raise HTTPException(status_code=422, detail="ends_at must be after starts_at")

        # published_at is stamped when status flips to published, cleared otherwise.
        publish_clause = ""
        if body.status is not None:
            publish_clause = (
                ", published_at = CASE WHEN $10 = 'published' AND published_at IS NULL "
                "THEN NOW() WHEN $10 <> 'published' THEN NULL ELSE published_at END"
            )
        await conn.execute(
            f"""
            UPDATE schedule_shifts SET
                starts_at = COALESCE($3, starts_at),
                ends_at = COALESCE($4, ends_at),
                role = COALESCE($5, role),
                department = COALESCE($6, department),
                location_id = $7,
                break_minutes = COALESCE($8, break_minutes),
                required_staff = COALESCE($9, required_staff),
                status = COALESCE($10, status),
                color = COALESCE($11, color),
                notes = COALESCE($12, notes),
                updated_at = NOW()
                {publish_clause}
            WHERE id = $1 AND company_id = $2
            """,
            shift_id, company_id, body.starts_at, body.ends_at, body.role,
            body.department, body.location_id, body.break_minutes, body.required_staff,
            body.status, body.color, body.notes,
        )
        await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                        "shift.update", {})
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.delete("/shifts/{shift_id}")
async def delete_shift(shift_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
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
        shifts = await fetch_shifts(conn, company_id, body.start, body.end)
    return {"published": count, "shifts": shifts, "summary": _summarize(shifts)}
