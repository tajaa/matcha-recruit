"""Week templates: a named, reusable week of shift-block definitions
(`/employee-schedule/week-templates`).

A week template is one row in schedule_week_templates plus N child rows in
schedule_shift_templates (week_template_id set, location_id inherited from
the parent). `POST /week-templates/{id}/generate` materializes concrete draft
shifts for every block across a date range, sharing one series_id per call so
the whole week's worth of shifts can be managed as a set (same convention as
the old single-template generate).

Superseded the flat schedule_shift_templates CRUD in templates.py (removed) —
schedule_chat.py's single-shift template save/match flow is untouched and
keeps writing schedule_shift_templates rows directly with week_template_id
left NULL (standalone, legacy shape); see the empsched03 migration.
"""

import json
from datetime import datetime, timedelta, time, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from ...dependencies import require_admin_or_client
from app.matcha.models.scheduling.employee_schedule import (
    WeekTemplateCreate, WeekTemplateUpdate, BlockCreate, BlockUpdate,
    WeekTemplateReplace, GenerateFromWeekTemplate,
)
from ...services.scheduling.schedule_rules import build_patch
from ...services.scheduling.shift_writes import generate_week_template_shifts
from ...services.scheduling.week_template_writes import (
    BLOCK_COLS as _BLOCK_COLS, WEEK_COLS as _WEEK_COLS,
    JobUnavailable, WeekTemplateNotFound,
    create_week_template_core, insert_block_core, replace_week_template_contents_core,
)
from ._shared import (
    require_company_id, log_audit, serialize_week_template, serialize_block,
    fetch_shifts, assert_location_in_company, assert_job_in_company, reconcile_warning_events,
)

router = APIRouter()


@router.get("/week-templates")
async def list_week_templates(
    location: UUID = Query(..., description="Business location to scope templates to"),
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, location)
        # location_id IS NULL means a company-wide template — stays visible
        # from every location's picker, same convention as the old templates.
        tpl_rows = await conn.fetch(
            f"SELECT {_WEEK_COLS} FROM schedule_week_templates "
            "WHERE company_id = $1 AND (location_id = $2 OR location_id IS NULL) "
            "ORDER BY name ASC",
            company_id, location,
        )
        if not tpl_rows:
            return {"week_templates": []}
        tpl_ids = [r["id"] for r in tpl_rows]
        block_rows = await conn.fetch(
            f"SELECT {_BLOCK_COLS} FROM schedule_shift_templates "
            "WHERE week_template_id = ANY($1::uuid[]) ORDER BY start_time ASC",
            tpl_ids,
        )
    blocks_by_tpl: dict[str, list[dict]] = {}
    for b in block_rows:
        blocks_by_tpl.setdefault(str(b["week_template_id"]), []).append(serialize_block(b))
    return {
        "week_templates": [
            serialize_week_template(r, blocks_by_tpl.get(str(r["id"]), []))
            for r in tpl_rows
        ]
    }


@router.post("/week-templates")
async def create_week_template(body: WeekTemplateCreate, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, body.location_id)
        async with conn.transaction():
            try:
                tpl, block_rows = await create_week_template_core(
                    conn, company_id=company_id, actor_user_id=current_user.id, body=body,
                )
            except JobUnavailable as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            blocks = [serialize_block(r) for r in block_rows]
            await log_audit(conn, company_id, "week_template", tpl["id"], current_user.id,
                            "week_template.create", {"name": body.name, "blocks": len(blocks)})
    return serialize_week_template(tpl, blocks)


@router.put("/week-templates/{week_template_id}")
async def update_week_template(week_template_id: UUID, body: WeekTemplateUpdate,
                               current_user=Depends(require_admin_or_client)):
    """True PATCH on the parent only. If location_id changes, every existing
    child block's location_id is re-synced to match — blocks never carry a
    location independent of their parent."""
    company_id = await require_company_id(current_user)
    patch = body.model_dump(exclude_unset=True)
    async with get_connection() as conn:
        if "location_id" in patch:
            await assert_location_in_company(conn, company_id, patch["location_id"])
        if not patch:
            tpl = await _fetch_week_template_or_404(conn, company_id, week_template_id)
            blocks = await _fetch_blocks(conn, week_template_id)
            return serialize_week_template(tpl, blocks)

        set_sql, params = build_patch(patch, first_param=3)
        async with conn.transaction():
            tpl = await conn.fetchrow(
                f"""
                UPDATE schedule_week_templates SET {set_sql}, updated_at = NOW()
                WHERE id = $1 AND company_id = $2
                RETURNING {_WEEK_COLS}
                """,
                week_template_id, company_id, *params,
            )
            if not tpl:
                raise HTTPException(status_code=404, detail="Week template not found")
            if "location_id" in patch:
                await conn.execute(
                    "UPDATE schedule_shift_templates SET location_id = $1, updated_at = NOW() "
                    "WHERE week_template_id = $2",
                    patch["location_id"], week_template_id,
                )
            await log_audit(conn, company_id, "week_template", week_template_id, current_user.id,
                            "week_template.update", {"fields": sorted(patch)})
            blocks = await _fetch_blocks(conn, week_template_id)
    return serialize_week_template(tpl, blocks)


@router.delete("/week-templates/{week_template_id}")
async def delete_week_template(week_template_id: UUID, current_user=Depends(require_admin_or_client)):
    """ON DELETE CASCADE removes the child blocks; schedule_shifts.template_id
    SET NULLs on each. Any auto schedule using this template is paused so its
    already-queued occurrence becomes stale instead of recurring as not-ready."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            await _fetch_week_template_for_update_or_404(conn, company_id, week_template_id)
            paused_rules = await conn.fetch(
                """
                UPDATE schedule_automation_rules
                SET week_template_id = NULL, enabled = false, next_run_at = NULL,
                    schedule_version = schedule_version + 1,
                    last_status = 'template_deleted',
                    last_message = 'Paused because its saved week template was deleted.',
                    updated_at = NOW(), updated_by = $3
                WHERE company_id = $1 AND week_template_id = $2
                RETURNING id, location_id
                """,
                company_id, week_template_id, current_user.id,
            )
            result = await conn.execute(
                "DELETE FROM schedule_week_templates WHERE id = $1 AND company_id = $2",
                week_template_id, company_id,
            )
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Week template not found")
            await log_audit(conn, company_id, "week_template", week_template_id, current_user.id,
                            "week_template.delete", {"paused_auto_schedules": len(paused_rules)})
            for rule in paused_rules:
                await log_audit(
                    conn, company_id, "schedule_automation", rule["id"], current_user.id,
                    "schedule_automation.pause_template_deleted",
                    {"location_id": str(rule["location_id"]), "week_template_id": str(week_template_id)},
                )
    return {"ok": True, "id": str(week_template_id), "paused_auto_schedules": len(paused_rules)}


@router.put("/week-templates/{week_template_id}/contents")
async def replace_week_template_contents(
    week_template_id: UUID, body: WeekTemplateReplace,
    current_user=Depends(require_admin_or_client),
):
    """Atomically reconcile the complete block list shown by the template editor.

    Existing block IDs are updated in place so historical generated shifts keep
    their template links. New blocks are inserted and omitted IDs are deleted,
    all in the same transaction as the parent rename.
    """
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            try:
                tpl, block_rows, counts = await replace_week_template_contents_core(
                    conn, company_id=company_id, week_template_id=week_template_id,
                    name=body.name, blocks=body.blocks, actor_user_id=current_user.id,
                )
            except WeekTemplateNotFound as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except JobUnavailable as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            await log_audit(
                conn, company_id, "week_template", week_template_id, current_user.id,
                "week_template.reconcile_blocks", counts,
            )
            blocks = [serialize_block(r) for r in block_rows]
    return serialize_week_template(tpl, blocks)


@router.post("/week-templates/{week_template_id}/blocks")
async def add_block(week_template_id: UUID, body: BlockCreate, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            tpl = await _fetch_week_template_for_update_or_404(conn, company_id, week_template_id)
            try:
                row = await insert_block_core(
                    conn, company_id=company_id, week_template_id=week_template_id,
                    location_id=tpl["location_id"], block=body, actor_user_id=current_user.id,
                )
            except JobUnavailable as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            block = serialize_block(row)
            await log_audit(conn, company_id, "week_template_block", block["id"], current_user.id,
                            "week_template.block.add", {"name": body.name, "week_template_id": str(week_template_id)})
    return block


@router.put("/week-templates/{week_template_id}/blocks/{block_id}")
async def update_block(week_template_id: UUID, block_id: UUID, body: BlockUpdate,
                       current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    patch = body.model_dump(exclude_unset=True)
    if "days_of_week" in patch and patch["days_of_week"] is not None:
        patch["days_of_week"] = json.dumps(sorted(set(patch["days_of_week"])))
    async with get_connection() as conn:
        if not patch:
            await _fetch_week_template_or_404(conn, company_id, week_template_id)
            row = await conn.fetchrow(
                f"SELECT {_BLOCK_COLS} FROM schedule_shift_templates "
                "WHERE id = $1 AND week_template_id = $2",
                block_id, week_template_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Block not found")
            return serialize_block(row)
        set_sql, params = build_patch(patch, first_param=3, casts={"days_of_week": "jsonb"})
        async with conn.transaction():
            tpl = await _fetch_week_template_for_update_or_404(conn, company_id, week_template_id)
            await assert_job_in_company(
                conn, company_id, patch.get("job_id"), location_id=tpl["location_id"],
            )
            row = await conn.fetchrow(
                f"""
                UPDATE schedule_shift_templates SET {set_sql}, updated_at = NOW()
                WHERE id = $1 AND week_template_id = $2
                RETURNING {_BLOCK_COLS}
                """,
                block_id, week_template_id, *params,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Block not found")
            await log_audit(conn, company_id, "week_template_block", block_id, current_user.id,
                            "week_template.block.update", {"fields": sorted(patch)})
    return serialize_block(row)


@router.delete("/week-templates/{week_template_id}/blocks/{block_id}")
async def delete_block(week_template_id: UUID, block_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            await _fetch_week_template_for_update_or_404(conn, company_id, week_template_id)
            result = await conn.execute(
                "DELETE FROM schedule_shift_templates WHERE id = $1 AND week_template_id = $2",
                block_id, week_template_id,
            )
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Block not found")
            await log_audit(conn, company_id, "week_template_block", block_id, current_user.id,
                            "week_template.block.delete", {})
    return {"ok": True, "id": str(block_id)}


@router.post("/week-templates/{week_template_id}/generate")
async def generate_from_week_template(week_template_id: UUID, body: GenerateFromWeekTemplate,
                                      current_user=Depends(require_admin_or_client)):
    """Materialize draft shifts for every block, all sharing one series_id.
    Delegates to shift_writes.generate_week_template_shifts — the chat "apply
    a week template" confirm flow shares this exact writer."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await _fetch_week_template_or_404(conn, company_id, week_template_id)
        blocks = await conn.fetch(
            f"SELECT {_BLOCK_COLS} FROM schedule_shift_templates WHERE week_template_id = $1",
            week_template_id,
        )
        if not blocks:
            raise HTTPException(status_code=422, detail="Week template has no blocks — add at least one")

        async with conn.transaction():
            result = await generate_week_template_shifts(
                conn, company_id, blocks=blocks, start_date=body.start_date,
                end_date=body.end_date, created_by=current_user.id,
            )
            await log_audit(conn, company_id, "week_template", week_template_id, current_user.id,
                            "week_template.generate",
                            {"series_id": str(result["series_id"]), "created": result["created"],
                             "blocks": len(blocks)})

        await reconcile_warning_events(conn, company_id)
        lo = datetime.combine(body.start_date, time.min, tzinfo=timezone.utc)
        hi = datetime.combine(body.end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        shifts = await fetch_shifts(conn, company_id, lo, hi)
    return {"created": result["created"], "series_id": str(result["series_id"]), "shifts": shifts,
            "compliance_warnings": result["compliance_warnings"]}


async def _fetch_week_template_or_404(conn, company_id: UUID, week_template_id: UUID):
    tpl = await conn.fetchrow(
        f"SELECT {_WEEK_COLS} FROM schedule_week_templates WHERE id = $1 AND company_id = $2",
        week_template_id, company_id,
    )
    if not tpl:
        raise HTTPException(status_code=404, detail="Week template not found")
    return tpl


async def _fetch_week_template_for_update_or_404(conn, company_id: UUID, week_template_id: UUID):
    """Lock the parent before mutating it or its child block collection."""
    tpl = await conn.fetchrow(
        f"SELECT {_WEEK_COLS} FROM schedule_week_templates "
        "WHERE id = $1 AND company_id = $2 FOR UPDATE",
        week_template_id, company_id,
    )
    if not tpl:
        raise HTTPException(status_code=404, detail="Week template not found")
    return tpl


async def _fetch_blocks(conn, week_template_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {_BLOCK_COLS} FROM schedule_shift_templates "
        "WHERE week_template_id = $1 ORDER BY start_time ASC",
        week_template_id,
    )
    return [serialize_block(r) for r in rows]


