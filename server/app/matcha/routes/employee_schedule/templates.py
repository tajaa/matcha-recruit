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

from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.employee_schedule import (
    TemplateCreate, TemplateUpdate, GenerateFromTemplate,
)
from ...services.schedule_rules import build_patch, template_windows
from ._shared import (
    require_company_id, log_audit, serialize_template, fetch_shifts,
    assert_location_in_company,
)
from ._compliance import check_shift_compliance

router = APIRouter()

_TEMPLATE_COLS = (
    "id, name, role, department, location_id, start_time, end_time, "
    "break_minutes, required_staff, days_of_week, color, notes"
)


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
        async with conn.transaction():
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
                json.dumps(sorted(set(body.days_of_week))), body.color, body.notes,
                current_user.id,
            )
            await log_audit(conn, company_id, "template", row["id"], current_user.id,
                            "template.create", {"name": body.name})
    return serialize_template(row)


@router.put("/templates/{template_id}")
async def update_template(template_id: UUID, body: TemplateUpdate,
                          current_user=Depends(require_admin_or_client)):
    """True PATCH, like update_shift: an explicit null clears a nullable column."""
    company_id = await require_company_id(current_user)
    patch = body.model_dump(exclude_unset=True)
    if "days_of_week" in patch and patch["days_of_week"] is not None:
        patch["days_of_week"] = json.dumps(sorted(set(patch["days_of_week"])))
    async with get_connection() as conn:
        if "location_id" in patch:
            await assert_location_in_company(conn, company_id, patch["location_id"])
        if not patch:
            row = await conn.fetchrow(
                f"SELECT {_TEMPLATE_COLS} FROM schedule_shift_templates "
                "WHERE id = $1 AND company_id = $2",
                template_id, company_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Template not found")
            return serialize_template(row)

        set_sql, params = build_patch(
            patch, first_param=3, casts={"days_of_week": "jsonb"},
        )
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""
                UPDATE schedule_shift_templates SET {set_sql}, updated_at = NOW()
                WHERE id = $1 AND company_id = $2
                RETURNING {_TEMPLATE_COLS}
                """,
                template_id, company_id, *params,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Template not found")
            await log_audit(conn, company_id, "template", template_id, current_user.id,
                            "template.update", {"fields": sorted(patch)})
    return serialize_template(row)


@router.delete("/templates/{template_id}")
async def delete_template(template_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
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

        series_id = uuid4()
        starts, ends = template_windows(
            body.start_date, body.end_date, day_set,
            tpl["start_time"], tpl["end_time"],
        )
        created = len(starts)

        # Every generated shift shares this template's duration/break/location, so
        # the shift-intrinsic advisories (meal break, daily OT) are identical for
        # all of them — check once. Unassigned drafts, so no per-employee (minor)
        # checks and nothing to BLOCK; surfaced as warnings, not a 409 (a bulk
        # 409 would make generation unusable).
        compliance_warnings = (
            await check_shift_compliance(
                conn, company_id, location_id=tpl["location_id"],
                starts_at=starts[0], ends_at=ends[0],
                break_minutes=tpl["break_minutes"] or 0,
            )
            if created else []
        )

        # One set-based INSERT: a 6-month daily template is ~180 rows, and one
        # awaited round trip per row held the transaction (and its pooled
        # connection) open for all of them.
        async with conn.transaction():
            if created:
                await conn.execute(
                    """
                    INSERT INTO schedule_shifts
                        (company_id, location_id, template_id, series_id, role,
                         department, starts_at, ends_at, break_minutes,
                         required_staff, color, notes, created_by)
                    SELECT $1,$2,$3,$4,$5,$6, w.starts_at, w.ends_at, $9,$10,$11,$12,$13
                    FROM unnest($7::timestamptz[], $8::timestamptz[])
                         AS w(starts_at, ends_at)
                    """,
                    company_id, tpl["location_id"], template_id, series_id, tpl["role"],
                    tpl["department"], starts, ends, tpl["break_minutes"],
                    tpl["required_staff"], tpl["color"], tpl["notes"], current_user.id,
                )
            await log_audit(conn, company_id, "template", template_id, current_user.id,
                            "template.generate",
                            {"series_id": str(series_id), "created": created})

        lo = datetime.combine(body.start_date, time.min, tzinfo=timezone.utc)
        hi = datetime.combine(body.end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        shifts = await fetch_shifts(conn, company_id, lo, hi)
    return {"created": created, "series_id": str(series_id), "shifts": shifts,
            "compliance_warnings": compliance_warnings}
