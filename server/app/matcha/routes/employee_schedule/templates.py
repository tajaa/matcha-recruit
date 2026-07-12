"""Shift templates + recurrence generation (`/employee-schedule/templates`).

A template is a reusable shift definition (role/location/time-of-day/staffing +
a weekday mask). `POST /templates/{id}/generate` materializes concrete draft
shifts for every matching weekday in a date range, tagged with a shared
`series_id` so the run can be managed as a set.
"""

import json
from datetime import datetime, timedelta, time, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from ...database import get_connection
from ...dependencies import require_admin_or_client
from ...models.employee_schedule import (
    TemplateCreate, TemplateUpdate, GenerateFromTemplate,
)
from ._shared import (
    require_company_id, log_audit, serialize_template, fetch_shifts,
    assert_location_in_company,
)

router = APIRouter()

_TEMPLATE_COLS = (
    "id, name, role, department, location_id, start_time, end_time, "
    "break_minutes, required_staff, days_of_week, color, notes"
)


def _sunday_indexed_weekday(d) -> int:
    """date.weekday() is Mon=0..Sun=6; our mask is Sun=0..Sat=6."""
    return (d.weekday() + 1) % 7


@router.get("/templates")
async def list_templates(current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT {_TEMPLATE_COLS} FROM schedule_shift_templates "
            "WHERE company_id = $1 ORDER BY name ASC",
            company_id,
        )
    return {"templates": [serialize_template(r) for r in rows]}


@router.post("/templates")
async def create_template(body: TemplateCreate, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, body.location_id)
        row = await conn.fetchrow(
            f"""
            INSERT INTO schedule_shift_templates
                (company_id, name, role, department, location_id, start_time, end_time,
                 break_minutes, required_staff, days_of_week, color, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12,$13)
            RETURNING {_TEMPLATE_COLS}
            """,
            company_id, body.name.strip(), body.role, body.department, body.location_id,
            body.start_time, body.end_time, body.break_minutes, body.required_staff,
            json.dumps(sorted(set(body.days_of_week))), body.color, body.notes, current_user.id,
        )
        await log_audit(conn, company_id, "template", row["id"], current_user.id,
                        "template.create", {"name": body.name})
    return serialize_template(row)


@router.put("/templates/{template_id}")
async def update_template(template_id: UUID, body: TemplateUpdate,
                          current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    days_json = json.dumps(sorted(set(body.days_of_week))) if body.days_of_week is not None else None
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, body.location_id)
        row = await conn.fetchrow(
            f"""
            UPDATE schedule_shift_templates SET
                name = COALESCE($3, name),
                role = COALESCE($4, role),
                department = COALESCE($5, department),
                location_id = COALESCE($6, location_id),
                start_time = COALESCE($7, start_time),
                end_time = COALESCE($8, end_time),
                break_minutes = COALESCE($9, break_minutes),
                required_staff = COALESCE($10, required_staff),
                days_of_week = COALESCE($11::jsonb, days_of_week),
                color = COALESCE($12, color),
                notes = COALESCE($13, notes),
                updated_at = NOW()
            WHERE id = $1 AND company_id = $2
            RETURNING {_TEMPLATE_COLS}
            """,
            template_id, company_id, body.name, body.role, body.department,
            body.location_id, body.start_time, body.end_time, body.break_minutes,
            body.required_staff, days_json, body.color, body.notes,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Template not found")
    return serialize_template(row)


@router.delete("/templates/{template_id}")
async def delete_template(template_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM schedule_shift_templates WHERE id = $1 AND company_id = $2",
            template_id, company_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Template not found")
        await log_audit(conn, company_id, "template", template_id, current_user.id,
                        "template.delete", {})
    return {"ok": True, "id": str(template_id)}


@router.post("/templates/{template_id}/generate")
async def generate_from_template(template_id: UUID, body: GenerateFromTemplate,
                                 current_user=Depends(require_admin_or_client)):
    """Create draft shifts for each matching weekday in [start_date, end_date]."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        tpl = await conn.fetchrow(
            f"SELECT {_TEMPLATE_COLS} FROM schedule_shift_templates "
            "WHERE id = $1 AND company_id = $2",
            template_id, company_id,
        )
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")

        days = tpl["days_of_week"]
        if isinstance(days, str):
            try:
                days = json.loads(days)
            except json.JSONDecodeError:
                days = []
        day_set = set(days or [])
        if not day_set:
            raise HTTPException(
                status_code=422,
                detail="Template has no weekdays configured — set days_of_week first",
            )

        start_t: time = tpl["start_time"]
        end_t: time = tpl["end_time"]
        overnight = end_t <= start_t
        series_id = uuid4()

        created = 0
        async with conn.transaction():
            d = body.start_date
            while d <= body.end_date:
                if _sunday_indexed_weekday(d) in day_set:
                    starts_at = datetime.combine(d, start_t, tzinfo=timezone.utc)
                    end_date = d + timedelta(days=1) if overnight else d
                    ends_at = datetime.combine(end_date, end_t, tzinfo=timezone.utc)
                    await conn.execute(
                        """
                        INSERT INTO schedule_shifts
                            (company_id, location_id, template_id, series_id, role,
                             department, starts_at, ends_at, break_minutes,
                             required_staff, color, notes, created_by)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                        """,
                        company_id, tpl["location_id"], template_id, series_id, tpl["role"],
                        tpl["department"], starts_at, ends_at, tpl["break_minutes"],
                        tpl["required_staff"], tpl["color"], tpl["notes"], current_user.id,
                    )
                    created += 1
                d += timedelta(days=1)
            await log_audit(conn, company_id, "template", template_id, current_user.id,
                            "template.generate",
                            {"series_id": str(series_id), "created": created})

        lo = datetime.combine(body.start_date, time.min, tzinfo=timezone.utc)
        hi = datetime.combine(body.end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        shifts = await fetch_shifts(conn, company_id, lo, hi)
    return {"created": created, "series_id": str(series_id), "shifts": shifts}
