"""Week-template create/reconcile cores, callable outside the route layer.

`routes/employee_schedule/week_templates.py` owned this logic inline, which put
it out of reach of Huume's location-profile executor — services must not import
routes. The bodies moved here verbatim; the route keeps its own auth, audit
rows and serialization and maps these errors onto HTTP status codes.

Error contract: `ValueError` subclasses only. `shift_writes.py` imports no
`HTTPException` and this module follows it, so a Celery task or an agent tool
can call these without a FastAPI request in scope.
"""

import json
from typing import Any, Optional
from uuid import UUID

from app.matcha.models.scheduling.employee_schedule import (
    BlockCreate, WeekTemplateBlockReplace, WeekTemplateCreate,
)


class WeekTemplateNotFound(ValueError):
    """The template (or one of the block ids supplied for it) does not exist."""


class JobUnavailable(ValueError):
    """The job is not this company's, or not available at the row's location."""


WEEK_COLS = "id, name, location_id, color, notes"
BLOCK_COLS = (
    "id, week_template_id, name, role, department, location_id, start_time, "
    "end_time, break_minutes, required_staff, days_of_week, color, notes, job_id"
)

# Mirrors routes/employee_schedule/_shared.UNSCOPED_LOCATION: "this caller has
# no location to check against" is not the same as "the row has no location".
UNSCOPED_LOCATION: Any = object()


async def assert_job_available(
    conn, company_id: UUID, job_id: Optional[UUID], *,
    location_id: Any = UNSCOPED_LOCATION, lock: bool = False,
) -> Optional[dict]:
    """Service twin of `_shared.assert_job_in_company`, raising ValueErrors.

    Returns the job row (name + location_id) so callers can persist the job's
    current name as the canonical role label.
    """
    if job_id is None:
        return None
    row = await conn.fetchrow(
        "SELECT name, location_id FROM schedule_jobs WHERE id = $1 AND company_id = $2"
        + (" FOR SHARE" if lock else ""),
        job_id, company_id,
    )
    if not row:
        raise JobUnavailable("Job not found")
    if (
        location_id is not UNSCOPED_LOCATION
        and row["location_id"] is not None
        and row["location_id"] != location_id
    ):
        raise JobUnavailable("Job is not available at this location")
    return row


async def insert_block_core(
    conn, *, company_id: UUID, week_template_id: UUID, location_id: Optional[UUID],
    block: BlockCreate, actor_user_id: Optional[UUID],
) -> dict:
    """Insert one child block, scoped to the template's location.

    A block carrying another store's job would generate concrete shifts that
    `create_shift_core` itself refuses.
    """
    await assert_job_available(conn, company_id, block.job_id, location_id=location_id, lock=True)
    return await conn.fetchrow(
        f"""
        INSERT INTO schedule_shift_templates
            (company_id, week_template_id, name, role, department, location_id,
             start_time, end_time, break_minutes, required_staff, days_of_week,
             color, notes, created_by, job_id)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$13,$14,$15)
        RETURNING {BLOCK_COLS}
        """,
        company_id, week_template_id, block.name.strip(), block.role, block.department,
        location_id, block.start_time, block.end_time, block.break_minutes,
        block.required_staff, json.dumps(sorted(set(block.days_of_week))),
        block.color, block.notes, actor_user_id, block.job_id,
    )


async def create_week_template_core(
    conn, *, company_id: UUID, actor_user_id: Optional[UUID], body: WeekTemplateCreate,
) -> tuple[dict, list[dict]]:
    """Insert the parent plus its blocks. Caller owns the transaction."""
    tpl = await conn.fetchrow(
        f"""
        INSERT INTO schedule_week_templates (company_id, name, location_id, color, notes, created_by)
        VALUES ($1,$2,$3,$4,$5,$6)
        RETURNING {WEEK_COLS}
        """,
        company_id, body.name.strip(), body.location_id, body.color, body.notes, actor_user_id,
    )
    blocks = [
        await insert_block_core(
            conn, company_id=company_id, week_template_id=tpl["id"],
            location_id=body.location_id, block=b, actor_user_id=actor_user_id,
        )
        for b in body.blocks
    ]
    return tpl, blocks


async def replace_week_template_contents_core(
    conn, *, company_id: UUID, week_template_id: UUID, name: Optional[str],
    blocks: list[WeekTemplateBlockReplace], actor_user_id: Optional[UUID],
) -> tuple[dict, list[dict], dict]:
    """Atomically reconcile a template's complete block list.

    Supplied ids are updated in place so historical generated shifts keep their
    template links; blocks without an id are inserted; existing ids omitted from
    the list are deleted. Caller owns the transaction.
    """
    tpl = await conn.fetchrow(
        f"SELECT {WEEK_COLS} FROM schedule_week_templates "
        "WHERE id = $1 AND company_id = $2 FOR UPDATE",
        week_template_id, company_id,
    )
    if not tpl:
        raise WeekTemplateNotFound("Week template not found")

    existing_rows = await conn.fetch(
        f"SELECT {BLOCK_COLS} FROM schedule_shift_templates "
        "WHERE week_template_id = $1 FOR UPDATE",
        week_template_id,
    )
    existing_ids = {row["id"] for row in existing_rows}
    supplied_ids = {b.id for b in blocks if b.id is not None}
    if supplied_ids - existing_ids:
        raise WeekTemplateNotFound("Template block not found")

    if name is not None:
        tpl = await conn.fetchrow(
            f"""
            UPDATE schedule_week_templates SET name = $3, updated_at = NOW()
            WHERE id = $1 AND company_id = $2
            RETURNING {WEEK_COLS}
            """,
            week_template_id, company_id, name.strip(),
        )
        if not tpl:
            raise WeekTemplateNotFound("Week template not found")

    added = 0
    updated = 0
    for block in blocks:
        if block.id is None:
            await insert_block_core(
                conn, company_id=company_id, week_template_id=week_template_id,
                location_id=tpl["location_id"],
                block=BlockCreate(**block.model_dump(exclude={"id"})),
                actor_user_id=actor_user_id,
            )
            added += 1
            continue
        # job_id is written here too: without it the editor's own save silently
        # strips the job link an agent-authored block was created with.
        await assert_job_available(
            conn, company_id, block.job_id, location_id=tpl["location_id"], lock=True,
        )
        await conn.execute(
            """
            UPDATE schedule_shift_templates
            SET name = $3, role = $4, start_time = $5,
                end_time = $6, break_minutes = $7, required_staff = $8,
                days_of_week = $9::jsonb, job_id = $10, updated_at = NOW()
            WHERE id = $1 AND week_template_id = $2
            """,
            block.id, week_template_id, block.name.strip(), block.role,
            block.start_time, block.end_time, block.break_minutes,
            block.required_staff, json.dumps(sorted(set(block.days_of_week))),
            block.job_id,
        )
        updated += 1

    removed_ids = list(existing_ids - supplied_ids)
    if removed_ids:
        await conn.execute(
            "DELETE FROM schedule_shift_templates WHERE id = ANY($1::uuid[])",
            removed_ids,
        )

    final_blocks = await conn.fetch(
        f"SELECT {BLOCK_COLS} FROM schedule_shift_templates "
        "WHERE week_template_id = $1 ORDER BY start_time ASC",
        week_template_id,
    )
    counts = {"added": added, "updated": updated, "removed": len(removed_ids)}
    return tpl, list(final_blocks), counts
