"""Persistence boundary for individualized assignment break guidance."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .schedule_break_rule_store import resolve_break_rules
from .schedule_breaks import (
    BreakPlan,
    MealWaiverAttestation,
    evaluate_break_plan,
    guidance_payload,
    minimum_meal_break_minutes,
    reinterpret_schedule_wall_time,
)
from .shift_compliance import _age_on


async def resolve_shift_break_plan(
    conn,
    company_id: UUID,
    *,
    location_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime,
    employee_id: UUID | None = None,
) -> BreakPlan:
    """Evaluate the approved plan for an open shift or one assignee."""
    if location_id is None:
        return evaluate_break_plan(
            starts_at=starts_at, ends_at=ends_at, timezone=ZoneInfo("UTC"), rules=(),
        )
    timezone_name = await conn.fetchval(
        "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
        location_id, company_id,
    )
    try:
        location_timezone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return evaluate_break_plan(
            starts_at=starts_at, ends_at=ends_at, timezone=ZoneInfo("UTC"), rules=(),
        )
    # Schedule timestamps are UTC-tagged wall-clock values.  Converting them
    # as real instants can move an early shift onto the previous legal day.
    shift_date = reinterpret_schedule_wall_time(starts_at, location_timezone).date()
    resolved = await resolve_break_rules(
        conn, company_id=company_id, location_id=location_id, shift_date=shift_date,
    )
    effective_timezone = resolved.timezone or location_timezone
    effective_date = reinterpret_schedule_wall_time(starts_at, effective_timezone).date()

    waiver = None
    employee_age = None
    age_unknown = False
    if employee_id is not None:
        employee_row = await conn.fetchrow(
            """
            SELECT ed.date_of_birth
            FROM employees e
            LEFT JOIN employee_demographics ed ON ed.employee_id = e.id
            WHERE e.id = $1 AND e.org_id = $2
            """,
            employee_id, company_id,
        )
        employee_age = _age_on(
            employee_row["date_of_birth"] if employee_row else None,
            effective_date,
        )
        age_unknown = employee_age is None and any(
            rule.minimum_age is not None or rule.maximum_age is not None
            for rule in resolved.rules
        )
        waiver_row = await conn.fetchrow(
            """
            SELECT id, value, effective_from, confirmed_by, confirmed_at
            FROM employee_compliance_attestations
            WHERE company_id = $1 AND employee_id = $2
              AND attestation_type = 'meal_break_waiver_on_file'
              AND effective_from <= $3
            ORDER BY effective_from DESC, confirmed_at DESC
            LIMIT 1
            """,
            company_id, employee_id, effective_date,
        )
        if waiver_row:
            waiver = MealWaiverAttestation(
                id=waiver_row["id"], on_file=waiver_row["value"],
                effective_from=waiver_row["effective_from"],
                confirmed_by=waiver_row["confirmed_by"],
                confirmed_at=waiver_row["confirmed_at"],
            )

    plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=effective_timezone,
        rules=resolved.rules, waiver=waiver, employee_age=employee_age,
    )
    advisories = list(plan.advisories) + list(resolved.advisories)
    if age_unknown:
        advisories.append({
            "check": "break_rules",
            "code": "employee_age_unverified",
            "severity": "advisory",
            "message": "Employee age is not on file; age-specific break rules require manual review.",
        })
    status = "error" if resolved.source == "error" or age_unknown else plan.status
    return replace(plan, status=status, advisories=tuple(advisories))


async def resolve_shift_break_plans(
    conn,
    company_id: UUID,
    *,
    location_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime,
    employee_ids: Sequence[UUID],
) -> dict[UUID, BreakPlan]:
    """Resolve one shift window for many employees with batched DB reads."""
    unique_ids = list(dict.fromkeys(employee_ids))
    if not unique_ids:
        return {}
    if location_id is None:
        return {
            employee_id: evaluate_break_plan(
                starts_at=starts_at, ends_at=ends_at, timezone=ZoneInfo("UTC"), rules=(),
            )
            for employee_id in unique_ids
        }

    timezone_name = await conn.fetchval(
        "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
        location_id, company_id,
    )
    try:
        location_timezone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return {
            employee_id: evaluate_break_plan(
                starts_at=starts_at, ends_at=ends_at, timezone=ZoneInfo("UTC"), rules=(),
            )
            for employee_id in unique_ids
        }
    shift_date = reinterpret_schedule_wall_time(starts_at, location_timezone).date()
    resolved = await resolve_break_rules(
        conn, company_id=company_id, location_id=location_id, shift_date=shift_date,
    )
    effective_timezone = resolved.timezone or location_timezone
    effective_date = reinterpret_schedule_wall_time(starts_at, effective_timezone).date()

    employee_rows = await conn.fetch(
        """
        SELECT e.id AS employee_id, ed.date_of_birth
        FROM employees e
        LEFT JOIN employee_demographics ed ON ed.employee_id = e.id
        WHERE e.org_id = $1 AND e.id = ANY($2::uuid[])
        """,
        company_id, unique_ids,
    )
    birth_dates = {row["employee_id"]: row["date_of_birth"] for row in employee_rows}
    waiver_rows = await conn.fetch(
        """
        SELECT DISTINCT ON (employee_id)
               employee_id, id, value, effective_from, confirmed_by, confirmed_at
        FROM employee_compliance_attestations
        WHERE company_id = $1 AND employee_id = ANY($2::uuid[])
          AND attestation_type = 'meal_break_waiver_on_file'
          AND effective_from <= $3
        ORDER BY employee_id, effective_from DESC, confirmed_at DESC
        """,
        company_id, unique_ids, effective_date,
    )
    waivers = {
        row["employee_id"]: MealWaiverAttestation(
            id=row["id"], on_file=row["value"], effective_from=row["effective_from"],
            confirmed_by=row["confirmed_by"], confirmed_at=row["confirmed_at"],
        )
        for row in waiver_rows
    }

    plans: dict[UUID, BreakPlan] = {}
    has_age_rules = any(
        rule.minimum_age is not None or rule.maximum_age is not None
        for rule in resolved.rules
    )
    for employee_id in unique_ids:
        employee_age = _age_on(birth_dates.get(employee_id), effective_date)
        age_unknown = employee_age is None and has_age_rules
        plan = evaluate_break_plan(
            starts_at=starts_at, ends_at=ends_at, timezone=effective_timezone,
            rules=resolved.rules, waiver=waivers.get(employee_id), employee_age=employee_age,
        )
        advisories = list(plan.advisories) + list(resolved.advisories)
        if age_unknown:
            advisories.append({
                "check": "break_rules",
                "code": "employee_age_unverified",
                "severity": "advisory",
                "message": "Employee age is not on file; age-specific break rules require manual review.",
            })
        status = "error" if resolved.source == "error" or age_unknown else plan.status
        plans[employee_id] = replace(plan, status=status, advisories=tuple(advisories))
    return plans


async def resolve_open_shift_break_plans(
    conn,
    company_id: UUID,
    *,
    location_id: UUID | None,
    windows: Sequence[tuple[datetime, datetime]],
) -> list[BreakPlan]:
    """Resolve many open-shift windows with one rules read per local date."""
    if not windows:
        return []
    if location_id is None:
        return [
            evaluate_break_plan(
                starts_at=starts_at, ends_at=ends_at,
                timezone=ZoneInfo("UTC"), rules=(),
            )
            for starts_at, ends_at in windows
        ]

    timezone_name = await conn.fetchval(
        "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
        location_id, company_id,
    )
    try:
        location_timezone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        location_timezone = ZoneInfo("UTC")

    resolved_by_date = {}
    plans: list[BreakPlan] = []
    for starts_at, ends_at in windows:
        shift_date = reinterpret_schedule_wall_time(starts_at, location_timezone).date()
        resolved = resolved_by_date.get(shift_date)
        if resolved is None:
            resolved = await resolve_break_rules(
                conn, company_id=company_id, location_id=location_id,
                shift_date=shift_date,
            )
            resolved_by_date[shift_date] = resolved
        effective_timezone = resolved.timezone or location_timezone
        plan = evaluate_break_plan(
            starts_at=starts_at, ends_at=ends_at,
            timezone=effective_timezone, rules=resolved.rules,
        )
        plans.append(replace(
            plan,
            status="error" if resolved.source == "error" else plan.status,
            advisories=tuple((*plan.advisories, *resolved.advisories)),
        ))
    return plans


async def refresh_assignment_break_guidance(
    conn,
    company_id: UUID,
    *,
    shift_id: UUID,
    employee_id: UUID,
    location_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime,
    plan: BreakPlan | None = None,
    timezone_name: str | None = None,
) -> BreakPlan:
    """Evaluate and store the break instructions shown for one assignment."""
    if plan is None:
        plan = await resolve_shift_break_plan(
            conn, company_id, location_id=location_id, starts_at=starts_at,
            ends_at=ends_at, employee_id=employee_id,
        )
    if location_id is None:
        return plan
    if timezone_name is None:
        timezone_name = await conn.fetchval(
            "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
            location_id, company_id,
        ) or "UTC"
    payload = guidance_payload(
        plan, timezone=timezone_name, evaluated_at=datetime.now(timezone.utc),
    )
    await conn.execute(
        """
        UPDATE schedule_shift_assignments
        SET compliance_guidance = $1::jsonb,
            guidance_evaluated_at = NOW(),
            guidance_ruleset_hash = $2
        WHERE company_id = $3 AND shift_id = $4 AND employee_id = $5
        """,
        json.dumps(payload), plan.rule_set_hash, company_id, shift_id, employee_id,
    )
    return plan


async def refresh_assignment_break_guidance_and_minimum(
    conn,
    company_id: UUID,
    *,
    shift_id: UUID,
    employee_id: UUID,
    actor_user_id: UUID | None,
    source: str,
) -> BreakPlan | None:
    """Refresh guidance and atomically preserve/enforce the shift minimum.

    The shift row is locked and re-read so DOB/waiver changes and concurrent
    edits cannot derive a write from stale location, window, or break values.
    Longer manager-entered breaks are never reduced.
    """
    shift = await conn.fetchrow(
        """
        SELECT location_id, starts_at, ends_at, break_minutes
        FROM schedule_shifts
        WHERE id = $1 AND company_id = $2
        FOR UPDATE
        """,
        shift_id, company_id,
    )
    if shift is None:
        return None
    plan = await refresh_assignment_break_guidance(
        conn, company_id, shift_id=shift_id, employee_id=employee_id,
        location_id=shift["location_id"], starts_at=shift["starts_at"],
        ends_at=shift["ends_at"],
    )
    generated_minimum = minimum_meal_break_minutes(plan)
    current_break = int(shift["break_minutes"] or 0)
    if generated_minimum > current_break:
        await conn.execute(
            "UPDATE schedule_shifts SET break_minutes = $1, updated_at = NOW() "
            "WHERE id = $2 AND company_id = $3",
            generated_minimum, shift_id, company_id,
        )
        # Imported lazily because shift_writes imports this module inside its
        # write cores; the runtime import avoids a module-load cycle.
        from .shift_writes import log_audit
        await log_audit(
            conn, company_id, "shift", shift_id, actor_user_id, "shift.update",
            {
                "fields": ["break_minutes"],
                "before": {"break_minutes": current_break},
                "after": {"break_minutes": generated_minimum},
                "source": source,
                "employee_id": str(employee_id),
            },
        )
    return plan
