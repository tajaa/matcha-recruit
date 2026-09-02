"""Shared scheduling writers: conflict lookup, audit logging, and the shift
+ assignment write core.

`find_conflicts` and `log_audit` were lifted out of
`routes/employee_schedule/_shared.py` (2026-07-31, alongside the
`shift_compliance` lift) so services outside that route package —
`services/scheduling/schedule_chat.py`, the @huume channel-scheduling flow —
can call them without a services→routes import. `_shared.py` re-imports both
under their old names.

`create_shift_core` is new: the write block of `routes/employee_schedule/
shifts.py:create_shift` (INSERT shift + assignments + training/scheduled-role
hooks + audit), pulled into a shared function so both the REST route and the
chat confirm flow create shifts identically. The route keeps every gate
(location assert, training feature check, conflicts, compliance,
`raise_for_violations`, forced-override audit) — only the write block
delegates here.

`apply_assignment_core` / `remove_assignment_core` / `retime_shift_core` /
`cancel_shift_core` (2026-08-04) are the edit-side counterparts, added so
`schedule_chat.py`'s edit proposals (swap/reassign/retime/cancel via
@huume) can write through the exact same path `routes/employee_schedule/
assignments.py` and `shifts.py` use — same audit action names
(`assignment.create`/`assignment.delete`/`shift.update`) and the same
`shift_snapshot`-shaped `before`/`after` schedule_intelligence reads for
Fair Workweek exposure. `shift_snapshot` itself moved here (from routes'
`_shared.py`) so these cores can build it without a services→routes
import; `_shared.py` re-exports it under its old name.

These are callers-own-the-checks writers, same posture as
`create_shift_core`: conflict/availability/compliance checks stay in the
caller (route handler or `schedule_chat`'s proposal builder/executor) —
the core only performs the write + audit once the caller has decided to
proceed.

`generate_week_template_shifts` (2026-08-17) is the last unshared writer:
`routes/employee_schedule/week_templates.py`'s per-block generate loop,
lifted so `schedule_chat.py`'s "apply a week template" confirm flow stamps
out a week identically to the Templates-tab Generate button. Caller owns
the tenant guard and the transaction.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def _audit_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


async def log_audit(
    conn,
    company_id: UUID,
    entity_type: str,
    entity_id: Optional[UUID],
    actor_user_id: Optional[UUID],
    action: str,
    details: Optional[dict] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO schedule_audit_log
            (company_id, entity_type, entity_id, actor_user_id, action, details)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        company_id, entity_type, entity_id, actor_user_id, action,
        json.dumps(details or {}),
    )


async def log_availability_override(
    conn,
    company_id: UUID,
    shift_id: UUID,
    actor_user_id: UUID,
    employee_id: UUID,
    violations: list[dict],
) -> None:
    """Record a forced assignment outside the employee's availability."""
    await log_audit(
        conn, company_id, "assignment", shift_id, actor_user_id,
        "assignment.availability_override",
        {"employee_id": str(employee_id), "violations": violations},
    )


async def find_conflicts(
    conn,
    company_id: UUID,
    employee_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    *,
    exclude_shift_id: Optional[UUID] = None,
) -> list[dict]:
    """Non-cancelled shifts this employee is already on that overlap the window.

    Used to block accidental double-booking on the assignment paths; callers
    expose a `force` override for deliberate back-to-back/overlap scheduling.
    """
    # A transaction-scoped employee lock makes "check then assign" atomic
    # across different target shifts.  Without it, two requests can lock two
    # different shift rows, both observe no conflict, and double-book the same
    # person.  Write callers run this inside their mutation transaction;
    # preview callers merely hold the lock for these two read statements.
    await lock_scheduling_employees(conn, company_id, [employee_id])
    rows = await conn.fetch(
        """
        SELECT s.id, s.starts_at, s.ends_at, s.role, s.status
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id
        WHERE s.company_id = $1 AND a.employee_id = $2
          AND s.status <> 'cancelled'
          AND s.starts_at < $4 AND s.ends_at > $3
          AND ($5::uuid IS NULL OR s.id <> $5)
        ORDER BY s.starts_at
        """,
        company_id, employee_id, starts_at, ends_at, exclude_shift_id,
    )
    return [
        {
            "shift_id": str(r["id"]),
            "starts_at": _iso(r["starts_at"]),
            "ends_at": _iso(r["ends_at"]),
            "role": r["role"],
            "status": r["status"],
        }
        for r in rows
    ]


async def lock_scheduling_employees(
    conn, company_id: UUID, employee_ids: list[UUID],
) -> None:
    """Take stable transaction locks for cross-shift conflict decisions."""
    for employee_id in sorted(set(employee_ids)):
        await conn.fetchval(
            "SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))",
            f"schedule-assignment:{company_id}:{employee_id}",
        )


async def fetch_availability(
    conn, company_id: UUID, employee_ids: list[UUID],
) -> dict:
    """{employee_id: {weekday: [(start_time, end_time), ...]}} — employees
    with no rows map to {} (= fully available per
    schedule_rules.availability_violations)."""
    out: dict = {eid: {} for eid in employee_ids}
    if not employee_ids:
        return out
    rows = await conn.fetch(
        """
        SELECT employee_id, weekday, start_time, end_time
        FROM schedule_employee_availability
        WHERE company_id = $1 AND employee_id = ANY($2::uuid[])
        ORDER BY weekday, start_time
        """,
        company_id, employee_ids,
    )
    for r in rows:
        out[r["employee_id"]].setdefault(r["weekday"], []).append(
            (r["start_time"], r["end_time"]))
    return out


async def create_shift_core(
    conn,
    company_id: UUID,
    *,
    location_id: Optional[UUID],
    role: Optional[str],
    department: Optional[str],
    starts_at: datetime,
    ends_at: datetime,
    break_minutes: int,
    required_staff: int,
    color: Optional[str] = None,
    notes: Optional[str] = None,
    kind: str = "work",
    template_id: Optional[UUID] = None,
    series_id: Optional[UUID] = None,
    job_id: Optional[UUID] = None,
    training_requirement: Optional[dict] = None,
    training_requirement_id: Optional[UUID] = None,
    employee_ids: list[UUID],
    created_by: UUID,
    status: str = "draft",
    audit_details: Optional[dict] = None,
) -> UUID:
    """INSERT one shift + its assignments + training/scheduled-role hooks +
    the `shift.create` audit row. Caller owns the transaction (both the REST
    route and the chat confirm flow wrap several of these in one
    `async with conn.transaction():`).

    `status='published'` also stamps `published_at = NOW()` — draft is silent
    on the portal (only published shifts are ever shown there), so a chat
    mistake with `status='draft'` never reaches an employee.
    """
    from app.matcha.services.training.training_assignment import (
        assign_training, evaluate_scheduled_role_rules,
    )
    from app.matcha.services.scheduling.schedule_breaks import minimum_meal_break_minutes
    from app.matcha.services.scheduling.schedule_guidance import (
        refresh_assignment_break_guidance,
        resolve_shift_break_plan,
        resolve_shift_break_plans,
    )

    import logging
    logger = logging.getLogger(__name__)

    plan_employee_ids = list(dict.fromkeys(employee_ids))
    if plan_employee_ids:
        break_plans = await resolve_shift_break_plans(
            conn, company_id, location_id=location_id, starts_at=starts_at,
            ends_at=ends_at, employee_ids=plan_employee_ids,
        )
    else:
        break_plans = {
            None: await resolve_shift_break_plan(
                conn, company_id, location_id=location_id, starts_at=starts_at,
                ends_at=ends_at,
            )
        }
    plans = list(break_plans.values())
    break_minutes = max(
        break_minutes,
        max(minimum_meal_break_minutes(plan) for plan in plans),
    )
    guidance_timezone = None
    if location_id is not None and plan_employee_ids:
        guidance_timezone = await conn.fetchval(
            "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
            location_id, company_id,
        ) or "UTC"

    shift_id = await conn.fetchval(
        """
        INSERT INTO schedule_shifts
            (company_id, location_id, role, department, starts_at, ends_at,
             break_minutes, required_staff, color, notes, kind, template_id,
             training_requirement_id, created_by, status, published_at, job_id,
             series_id)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::varchar,
                CASE WHEN $15::varchar = 'published' THEN NOW() END, $16,$17)
        RETURNING id
        """,
        company_id, location_id, role, department, starts_at, ends_at,
        break_minutes, required_staff, color, notes, kind, template_id,
        training_requirement_id, created_by, status, job_id,
        series_id,
    )
    for emp_id in plan_employee_ids:
        await conn.execute(
            """
            INSERT INTO schedule_shift_assignments
                (company_id, shift_id, employee_id, assigned_by)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (shift_id, employee_id) DO NOTHING
            """,
            company_id, shift_id, emp_id, created_by,
        )
        await refresh_assignment_break_guidance(
            conn, company_id, shift_id=shift_id, employee_id=emp_id,
            location_id=location_id, starts_at=starts_at, ends_at=ends_at,
            plan=break_plans[emp_id],
            timezone_name=guidance_timezone,
        )
        if kind == "training" and training_requirement is not None:
            await assign_training(
                conn, company_id, dict(training_requirement), [emp_id],
                source_type="schedule", source_ref=shift_id,
                source_note=f"Scheduled training session {starts_at.date().isoformat()}",
                due_date=starts_at.astimezone(timezone.utc).date(),
                assigned_by=created_by,
            )
        elif kind == "work":
            try:
                await evaluate_scheduled_role_rules(
                    conn, company_id, emp_id,
                    shift_id=shift_id, shift_role=role,
                    shift_start=starts_at.astimezone(timezone.utc).date(),
                )
            except Exception:
                logger.exception(
                    "scheduled_role training rules failed for shift %s", shift_id
                )

    details = {
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "location_id": str(location_id) if location_id else None,
        "status": status,
        **(audit_details or {}),
    }
    await log_audit(conn, company_id, "shift", shift_id, created_by, "shift.create", details)
    return shift_id


def shift_snapshot(row) -> dict:
    """Before/after change-detail shape for schedule_audit_log.

    Feeds the Schedule Intelligence engine's Fair Workweek / instability
    analysis, which needs to know what a shift looked like before a change —
    the plain audit log recorded only which fields changed, not their values.
    """
    fields = (
        "starts_at", "ends_at", "status", "location_id", "role", "department",
        "break_minutes", "required_staff", "color", "notes", "job_id", "published_at",
    )
    available = set(row.keys())
    return {field: _audit_value(row[field]) for field in fields if field in available}


async def restore_assignment_raw(
    conn,
    company_id: UUID,
    *,
    shift_id: UUID,
    employee_id: UUID,
    assigned_by: Optional[UUID],
) -> None:
    """Re-INSERT an assignment removed earlier in the SAME transaction, with
    no audit row and no training/scheduled-role side effects. Used only to
    undo a phase-1 removal when a later phase refuses the op (schedule_chat.
    py's two-phase edit executor) — a refused op must be a true no-op, not
    an `assignment.delete` + `assignment.create` pair, which `fair_workweek.
    RELEVANT_ACTIONS` would double-count as churn. `assigned_by` should be
    the original assignment's own value, not the confirming actor, since
    this isn't a new assignment decision."""
    await conn.execute(
        """
        INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, assigned_by)
        VALUES ($1,$2,$3,$4)
        ON CONFLICT (shift_id, employee_id) DO NOTHING
        """,
        company_id, shift_id, employee_id, assigned_by,
    )


async def apply_assignment_core(
    conn,
    company_id: UUID,
    *,
    shift_row,
    employee_id: UUID,
    actor_user_id: UUID,
    audit_details: Optional[dict] = None,
) -> None:
    """INSERT one assignment + the `assignment.create` audit row + the same
    training/scheduled-role hooks `create_shift_core` runs. `shift_row` must
    carry id/starts_at/ends_at/status/kind/role/training_requirement_id/
    location_id (the `fetch_shift_for_write` shape). Caller has already run
    conflict/headcount/availability/compliance checks and owns the
    transaction — this only writes."""
    from app.matcha.services.training.training_assignment import (
        assign_training, evaluate_scheduled_role_rules,
    )
    from app.matcha.services.scheduling.schedule_guidance import (
        refresh_assignment_break_guidance_and_minimum,
    )

    import logging
    logger = logging.getLogger(__name__)

    shift_id = shift_row["id"]
    await conn.execute(
        """
        INSERT INTO schedule_shift_assignments
            (company_id, shift_id, employee_id, assigned_by)
        VALUES ($1,$2,$3,$4)
        ON CONFLICT (shift_id, employee_id) DO NOTHING
        """,
        company_id, shift_id, employee_id, actor_user_id,
    )
    await refresh_assignment_break_guidance_and_minimum(
        conn, company_id, shift_id=shift_id, employee_id=employee_id,
        actor_user_id=actor_user_id, source="automatic_break_assignment",
    )
    await log_audit(conn, company_id, "assignment", shift_id, actor_user_id,
                    "assignment.create", {
                        "employee_id": str(employee_id),
                        "shift_starts_at": shift_row["starts_at"].isoformat(),
                        "shift_ends_at": shift_row["ends_at"].isoformat(),
                        "shift_status": shift_row["status"],
                        "location_id": str(shift_row["location_id"]) if shift_row["location_id"] else None,
                        **(audit_details or {}),
                    })
    if shift_row["kind"] == "training" and shift_row["training_requirement_id"] is not None:
        requirement = await conn.fetchrow(
            "SELECT id, title, training_type, frequency_months "
            "FROM training_requirements WHERE id = $1 AND company_id = $2",
            shift_row["training_requirement_id"], company_id,
        )
        if requirement:
            await assign_training(
                conn, company_id, dict(requirement), [employee_id],
                source_type="schedule", source_ref=shift_id,
                source_note=f"Scheduled training session {shift_row['starts_at'].date().isoformat()}",
                due_date=shift_row["starts_at"].astimezone(timezone.utc).date(),
                assigned_by=actor_user_id,
            )
        else:
            logger.warning(
                "training-kind shift %s has no resolvable training_requirement_id "
                "(deleted?) — skipping training assignment", shift_id,
            )
    elif shift_row["kind"] == "work":
        # A scheduled_role match must not fail the assignment write — the
        # shift is already staffed at this point.
        try:
            await evaluate_scheduled_role_rules(
                conn, company_id, employee_id,
                shift_id=shift_id, shift_role=shift_row["role"],
                shift_start=shift_row["starts_at"].astimezone(timezone.utc).date(),
            )
        except Exception:
            logger.exception(
                "scheduled_role training rules failed for shift %s", shift_id
            )


def removal_audit_details(shift_row, employee_id: UUID, audit_details: Optional[dict] = None) -> dict:
    """The `assignment.delete` details shape, factored out so a caller that
    defers the audit write (schedule_chat.py's two-phase edit executor)
    can't drift from what `remove_assignment_core` writes inline."""
    return {
        "employee_id": str(employee_id),
        "shift_starts_at": shift_row["starts_at"].isoformat(),
        "shift_ends_at": shift_row["ends_at"].isoformat(),
        "shift_status": shift_row["status"],
        "shift_kind": shift_row["kind"],
        "location_id": str(shift_row["location_id"]) if shift_row["location_id"] else None,
        **(audit_details or {}),
    }


async def remove_assignment_core(
    conn,
    company_id: UUID,
    *,
    shift_id: UUID,
    employee_id: UUID,
    actor_user_id: UUID | None,
    shift_row,
    audit_details: Optional[dict] = None,
    write_audit: bool = True,
) -> int:
    """DELETE one assignment + (unless suppressed) the `assignment.delete`
    audit row. `shift_row` must carry starts_at/ends_at/status/kind/
    location_id. Caller runs the FW advisory check (if any) and owns the
    transaction. Returns the number of rows deleted (0 or 1) — a zero-row
    delete means "they weren't on that shift" and never gets an audit row,
    even when `write_audit` is True, so a phantom unassign can't feed Fair
    Workweek/pretext-shield history. `write_audit=False` lets a caller that
    needs the removal to be restorable (schedule_chat.py's two-phase edit
    executor) defer the audit write until it knows the op actually
    succeeds — use `removal_audit_details` to write it later with the same
    shape."""
    status = await conn.execute(
        "DELETE FROM schedule_shift_assignments WHERE shift_id = $1 AND employee_id = $2",
        shift_id, employee_id,
    )
    deleted = int(status.split()[-1])
    if deleted and write_audit:
        await log_audit(conn, company_id, "assignment", shift_id, actor_user_id,
                        "assignment.delete", removal_audit_details(shift_row, employee_id, audit_details))
    return deleted


async def retime_shift_core(
    conn,
    company_id: UUID,
    *,
    shift_id: UUID,
    existing_row,
    new_starts_at: datetime,
    new_ends_at: datetime,
    actor_user_id: UUID,
    audit_details: Optional[dict] = None,
) -> None:
    """UPDATE a shift's starts_at/ends_at + the `shift.update` audit row with
    a `shift_snapshot`-shaped before/after (what schedule_intelligence's Fair
    Workweek exposure reads). `existing_row` must carry starts_at/ends_at/
    status/location_id/published_at. Caller has already run conflict/
    availability/compliance re-checks (with `exclude_shift_id=shift_id`) and
    owns the transaction."""
    from app.matcha.services.scheduling.schedule_breaks import minimum_meal_break_minutes
    from app.matcha.services.scheduling.schedule_guidance import (
        refresh_assignment_break_guidance,
        resolve_shift_break_plan,
        resolve_shift_break_plans,
    )

    assignees = await conn.fetch(
        "SELECT employee_id FROM schedule_shift_assignments WHERE shift_id = $1",
        shift_id,
    )
    plan_employee_ids = [row["employee_id"] for row in assignees] or [None]
    if assignees:
        plans_by_employee = await resolve_shift_break_plans(
            conn, company_id, location_id=existing_row["location_id"],
            starts_at=new_starts_at, ends_at=new_ends_at,
            employee_ids=[row["employee_id"] for row in assignees],
        )
    else:
        plans_by_employee = {
            None: await resolve_shift_break_plan(
                conn, company_id, location_id=existing_row["location_id"],
                starts_at=new_starts_at, ends_at=new_ends_at,
            )
        }
    plans = list(plans_by_employee.values())
    generated_minimum = max(minimum_meal_break_minutes(plan) for plan in plans)
    current_break = int(existing_row["break_minutes"] or 0)
    new_break = max(current_break, generated_minimum)
    guidance_timezone = None
    if existing_row["location_id"] is not None and assignees:
        guidance_timezone = await conn.fetchval(
            "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
            existing_row["location_id"], company_id,
        ) or "UTC"

    before = shift_snapshot(existing_row)
    after = {
        "starts_at": new_starts_at.isoformat(),
        "ends_at": new_ends_at.isoformat(),
        "status": existing_row["status"],
        "location_id": str(existing_row["location_id"]) if existing_row["location_id"] else None,
        "break_minutes": new_break,
    }
    was_published = existing_row["published_at"] is not None
    await conn.execute(
        "UPDATE schedule_shifts SET starts_at = $1, ends_at = $2, "
        "break_minutes = $3, updated_at = NOW() "
        "WHERE id = $4 AND company_id = $5",
        new_starts_at, new_ends_at, new_break, shift_id, company_id,
    )
    for assignee in assignees:
        await refresh_assignment_break_guidance(
            conn, company_id, shift_id=shift_id,
            employee_id=assignee["employee_id"],
            location_id=existing_row["location_id"],
            starts_at=new_starts_at, ends_at=new_ends_at,
            plan=plans_by_employee[assignee["employee_id"]],
            timezone_name=guidance_timezone,
        )
    await log_audit(conn, company_id, "shift", shift_id, actor_user_id,
                    "shift.update", {
                        "fields": [
                            "starts_at", "ends_at",
                            *(["break_minutes"] if new_break != current_break else []),
                        ],
                        "before": before, "after": after,
                        "was_published": was_published,
                        "assigned_employee_ids": (
                            [str(row["employee_id"]) for row in assignees]
                            if was_published else []
                        ),
                        **(audit_details or {}),
                    })


async def cancel_shift_core(
    conn,
    company_id: UUID,
    *,
    shift_id: UUID,
    existing_row,
    actor_user_id: UUID,
    audit_details: Optional[dict] = None,
) -> None:
    """Set a shift `status='cancelled'` (terminal — publish already refuses
    a cancelled shift, and reopening as a draft is the only supported path
    back) + the `shift.update` audit row. `existing_row` must carry
    starts_at/ends_at/status/location_id/published_at. Caller has already
    run the FW cancel-advisory check and owns the transaction."""
    before = shift_snapshot(existing_row)
    after = {**before, "status": "cancelled", "published_at": None}
    was_published = existing_row["published_at"] is not None
    assignees = await conn.fetch(
        "SELECT employee_id FROM schedule_shift_assignments WHERE shift_id = $1",
        shift_id,
    ) if was_published else []
    await conn.execute(
        "UPDATE schedule_shifts SET status = 'cancelled', published_at = NULL, "
        "updated_at = NOW() WHERE id = $1 AND company_id = $2",
        shift_id, company_id,
    )
    await log_audit(conn, company_id, "shift", shift_id, actor_user_id,
                    "shift.update", {
                        "fields": ["published_at", "status"],
                        "before": before, "after": after,
                        "was_published": was_published,
                        "assigned_employee_ids": [str(row["employee_id"]) for row in assignees],
                        **(audit_details or {}),
                    })


async def generate_week_template_shifts(
    conn,
    company_id: UUID,
    *,
    blocks: list,
    start_date: date,
    end_date: date,
    created_by: UUID,
) -> dict:
    """Materialize draft shifts for every block under ONE series_id.

    `blocks` are `schedule_shift_templates` rows (the `_BLOCK_COLS` shape:
    id/role/department/location_id/start_time/end_time/break_minutes/
    required_staff/days_of_week/color/notes/job_id). A block with no
    weekdays configured is silently skipped, not a 422 — one misconfigured
    block shouldn't block the others. Caller owns the tenant guard and wraps
    this in `async with conn.transaction():`; this only writes. Every shift
    generated from a block inherits that block's job_id, so a job set on
    "Box Office" once carries into every generated week.
    """
    from .schedule_rules import template_windows
    from .shift_compliance import check_shift_compliance
    from .schedule_breaks import minimum_meal_break_minutes
    from .schedule_guidance import resolve_open_shift_break_plans

    series_id = uuid4()
    total_created = 0
    shift_ids: list[UUID] = []
    compliance_warnings: list[dict] = []
    per_block: list[dict] = []

    prepared: list[dict] = []
    windows_by_location: dict[UUID | None, list[tuple[int, int, datetime, datetime]]] = {}
    for blk in blocks:
        days = blk["days_of_week"]
        if isinstance(days, str):
            try:
                days = json.loads(days)
            except json.JSONDecodeError:
                days = []
        day_set = set(days or [])
        if not day_set:
            continue

        starts, ends = template_windows(
            start_date, end_date, day_set, blk["start_time"], blk["end_time"],
        )
        if not starts:
            continue
        total_created += len(starts)
        entry_index = len(prepared)
        prepared.append({"block": blk, "starts": starts, "ends": ends, "plans": []})
        location_windows = windows_by_location.setdefault(blk["location_id"], [])
        location_windows.extend(
            (entry_index, window_index, starts_at, ends_at)
            for window_index, (starts_at, ends_at) in enumerate(zip(starts, ends))
        )

    # Resolve location metadata once and rule sets once per local calendar
    # date, rather than issuing several queries for every materialized shift.
    for location_id, indexed_windows in windows_by_location.items():
        plans = await resolve_open_shift_break_plans(
            conn, company_id, location_id=location_id,
            windows=[(item[2], item[3]) for item in indexed_windows],
        )
        for (entry_index, _window_index, _starts_at, _ends_at), plan in zip(indexed_windows, plans):
            prepared[entry_index]["plans"].append(plan)

    for entry in prepared:
        blk = entry["block"]
        starts = entry["starts"]
        ends = entry["ends"]
        effective_breaks = [
            max(int(blk["break_minutes"] or 0), minimum_meal_break_minutes(plan))
            for plan in entry["plans"]
        ]

        # One compliance check per block (not per shift, not once for the
        # whole template) — each block can have a different time
        # window/break/role, so its advisories differ; all shifts
        # generated from the SAME block share the same intrinsic
        # advisories.
        compliance_warnings.extend(
            await check_shift_compliance(
                conn, company_id, location_id=blk["location_id"], job_id=blk["job_id"],
                starts_at=starts[0], ends_at=ends[0],
                break_minutes=effective_breaks[0], shift_kind="work",
            )
        )

        rows = await conn.fetch(
            """
            INSERT INTO schedule_shifts
                (company_id, location_id, template_id, series_id, role,
                 department, starts_at, ends_at, break_minutes,
                 required_staff, color, notes, created_by, job_id)
            SELECT $1,$2,$3,$4,$5,$6, w.starts_at, w.ends_at, w.break_minutes,
                   $10,$11,$12,$13,$14
            FROM unnest($7::timestamptz[], $8::timestamptz[], $9::integer[])
                 AS w(starts_at, ends_at, break_minutes)
            RETURNING id
            """,
            company_id, blk["location_id"], blk["id"], series_id, blk["role"],
            blk["department"], starts, ends, effective_breaks,
            blk["required_staff"], blk["color"], blk["notes"], created_by, blk["job_id"],
        )
        shift_ids.extend(r["id"] for r in rows)
        per_block.append({"block_id": str(blk["id"]), "name": blk["name"], "count": len(starts)})

    return {
        "series_id": series_id, "created": total_created, "shift_ids": shift_ids,
        "compliance_warnings": compliance_warnings, "per_block": per_block,
    }
