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
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


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

    import logging
    logger = logging.getLogger(__name__)

    shift_id = await conn.fetchval(
        """
        INSERT INTO schedule_shifts
            (company_id, location_id, role, department, starts_at, ends_at,
             break_minutes, required_staff, color, notes, kind, template_id,
             training_requirement_id, created_by, status, published_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::varchar,
                CASE WHEN $15::varchar = 'published' THEN NOW() END)
        RETURNING id
        """,
        company_id, location_id, role, department, starts_at, ends_at,
        break_minutes, required_staff, color, notes, kind, template_id,
        training_requirement_id, created_by, status,
    )
    for emp_id in dict.fromkeys(employee_ids):
        await conn.execute(
            """
            INSERT INTO schedule_shift_assignments
                (company_id, shift_id, employee_id, assigned_by)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (shift_id, employee_id) DO NOTHING
            """,
            company_id, shift_id, emp_id, created_by,
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
