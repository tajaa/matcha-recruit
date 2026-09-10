"""Persistence boundary for individualized assignment break guidance."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.database import decode_jsonb
from .schedule_break_rule_store import get_employer_employee_count, resolve_break_rules
from .schedule_breaks import (
    BreakPlan,
    MealWaiverAttestation,
    evaluate_break_plan,
    guidance_payload,
    minimum_meal_break_minutes,
    reinterpret_schedule_wall_time,
)
from .schedule_break_stagger import (
    FloorWindow,
    LockedBreak,
    StaggerAssignment,
    StaggerPlan,
    locked_breaks_from_planned,
    prune_planned_breaks,
    stagger_shift_breaks,
)
from .shift_compliance import _age_on

_EMPLOYER_EMPLOYEE_COUNT_UNSET = object()


async def resolve_shift_break_plan(
    conn,
    company_id: UUID,
    *,
    location_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime,
    employee_id: UUID | None = None,
    employer_employee_count: int | None | object = _EMPLOYER_EMPLOYEE_COUNT_UNSET,
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
    rule_kwargs: dict[str, Any] = {
        "company_id": company_id,
        "location_id": location_id,
        "shift_date": shift_date,
    }
    if employer_employee_count is not _EMPLOYER_EMPLOYEE_COUNT_UNSET:
        rule_kwargs["employer_employee_count"] = employer_employee_count
    resolved = await resolve_break_rules(conn, **rule_kwargs)
    effective_employer_employee_count = resolved.employer_employee_count
    if (
        effective_employer_employee_count is None
        and employer_employee_count is not _EMPLOYER_EMPLOYEE_COUNT_UNSET
    ):
        effective_employer_employee_count = employer_employee_count
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
        employer_employee_count=effective_employer_employee_count,
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
    _, plans = await resolve_shift_break_plans_localized(
        conn, company_id, location_id=location_id, starts_at=starts_at,
        ends_at=ends_at, employee_ids=employee_ids,
    )
    return plans


async def resolve_shift_break_plans_localized(
    conn,
    company_id: UUID,
    *,
    location_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime,
    employee_ids: Sequence[UUID],
) -> tuple[ZoneInfo, dict[UUID, BreakPlan]]:
    """``resolve_shift_break_plans`` plus the zone the plan times are in.

    Break staggering has to compare requirement times against the shift's own
    window, which means it needs the same effective zone the evaluator used —
    returning it here avoids a second rules read just to re-derive it.
    """
    unique_ids = list(dict.fromkeys(employee_ids))
    utc = ZoneInfo("UTC")
    if not unique_ids:
        return utc, {}
    if location_id is None:
        return utc, {
            employee_id: evaluate_break_plan(
                starts_at=starts_at, ends_at=ends_at, timezone=utc, rules=(),
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
        return utc, {
            employee_id: evaluate_break_plan(
                starts_at=starts_at, ends_at=ends_at, timezone=utc, rules=(),
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
            employer_employee_count=resolved.employer_employee_count,
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
    return effective_timezone, plans


async def resolve_week_break_plans(
    conn,
    company_id: UUID,
    *,
    location_id: UUID | None,
    shifts: Sequence[tuple[str, datetime, datetime, Sequence[UUID]]],
) -> tuple[ZoneInfo, dict[str, dict[UUID, BreakPlan]], set[date]]:
    """Evaluate every assignee's break plan across a whole proposed week.

    The per-shift resolvers above are the right shape for one shift and the
    wrong one for a week: ``resolve_break_rules`` takes a Postgres advisory
    lock on every call, and the DOB/waiver reads are per shift.  A 40-shift
    week through those would be 40 locked rule resolutions and repeated fact
    reads; this is at most 7 rule resolutions (one per local date), one shared
    employer-count read, and two batched employee-fact reads.

    ``shifts`` is ``(shift_key, starts_at, ends_at, employee_ids)``.  Returns
    the effective zone, the plans keyed by shift then employee, and the local
    dates whose rules could not be mapped — a jurisdiction with nothing in the
    catalog is reported, never silently treated as "no breaks required".
    """
    utc = ZoneInfo("UTC")
    unmapped_dates: set[date] = set()
    if not shifts:
        return utc, {}, unmapped_dates

    employee_ids = list(dict.fromkeys(
        employee_id for _key, _start, _end, ids in shifts for employee_id in ids
    ))
    if location_id is None or not employee_ids:
        return utc, {
            key: {
                employee_id: evaluate_break_plan(
                    starts_at=starts_at, ends_at=ends_at, timezone=utc, rules=(),
                )
                for employee_id in ids
            }
            for key, starts_at, ends_at, ids in shifts
        }, unmapped_dates

    timezone_name = await conn.fetchval(
        "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
        location_id, company_id,
    )
    try:
        location_timezone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        location_timezone = utc

    birth_rows = await conn.fetch(
        """
        SELECT e.id AS employee_id, ed.date_of_birth
        FROM employees e
        LEFT JOIN employee_demographics ed ON ed.employee_id = e.id
        WHERE e.org_id = $1 AND e.id = ANY($2::uuid[])
        """,
        company_id, employee_ids,
    )
    birth_dates = {row["employee_id"]: row["date_of_birth"] for row in birth_rows}

    latest_date = max(
        reinterpret_schedule_wall_time(starts_at, location_timezone).date()
        for _key, starts_at, _end, _ids in shifts
    )
    # Every waiver that could apply to any date in the week, newest first; the
    # per-date pick happens in Python rather than as seven more queries.
    waiver_rows = await conn.fetch(
        """
        SELECT employee_id, id, value, effective_from, confirmed_by, confirmed_at
        FROM employee_compliance_attestations
        WHERE company_id = $1 AND employee_id = ANY($2::uuid[])
          AND attestation_type = 'meal_break_waiver_on_file'
          AND effective_from <= $3
        ORDER BY employee_id, effective_from DESC, confirmed_at DESC
        """,
        company_id, employee_ids, latest_date,
    )
    waivers_by_employee: dict[UUID, list] = {}
    for row in waiver_rows:
        waivers_by_employee.setdefault(row["employee_id"], []).append(row)

    def _waiver(employee_id: UUID, on_date: date) -> MealWaiverAttestation | None:
        for row in waivers_by_employee.get(employee_id, ()):
            if row["effective_from"] <= on_date:
                return MealWaiverAttestation(
                    id=row["id"], on_file=row["value"],
                    effective_from=row["effective_from"],
                    confirmed_by=row["confirmed_by"], confirmed_at=row["confirmed_at"],
                )
        return None

    employer_employee_count = await get_employer_employee_count(conn, company_id)
    resolved_by_date: dict[date, Any] = {}
    plans: dict[str, dict[UUID, BreakPlan]] = {}
    effective_timezone = location_timezone
    for key, starts_at, ends_at, ids in shifts:
        shift_date = reinterpret_schedule_wall_time(starts_at, location_timezone).date()
        resolved = resolved_by_date.get(shift_date)
        if resolved is None:
            resolved = await resolve_break_rules(
                conn, company_id=company_id, location_id=location_id,
                shift_date=shift_date,
                employer_employee_count=employer_employee_count,
            )
            resolved_by_date[shift_date] = resolved
            if resolved.source in (
                "unmapped", "error", "confirmation_required", "rejected_expected",
            ):
                unmapped_dates.add(shift_date)
        effective_timezone = resolved.timezone or location_timezone
        effective_date = reinterpret_schedule_wall_time(starts_at, effective_timezone).date()
        has_age_rules = any(
            rule.minimum_age is not None or rule.maximum_age is not None
            for rule in resolved.rules
        )
        for employee_id in ids:
            employee_age = _age_on(birth_dates.get(employee_id), effective_date)
            age_unknown = employee_age is None and has_age_rules
            plan = evaluate_break_plan(
                starts_at=starts_at, ends_at=ends_at, timezone=effective_timezone,
                rules=resolved.rules, waiver=_waiver(employee_id, effective_date),
                employee_age=employee_age,
                employer_employee_count=(
                    resolved.employer_employee_count
                    if resolved.employer_employee_count is not None
                    else employer_employee_count
                ),
            )
            advisories = [*plan.advisories, *resolved.advisories]
            if age_unknown:
                advisories.append({
                    "check": "break_rules",
                    "code": "employee_age_unverified",
                    "severity": "advisory",
                    "message": "Employee age is not on file; age-specific break rules "
                               "require manual review.",
                })
            plans.setdefault(key, {})[employee_id] = replace(
                plan,
                status="error" if resolved.source == "error" or age_unknown else plan.status,
                advisories=tuple(advisories),
            )
    return effective_timezone, plans, unmapped_dates


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

    employer_employee_count = await get_employer_employee_count(conn, company_id)
    resolved_by_date = {}
    plans: list[BreakPlan] = []
    for starts_at, ends_at in windows:
        shift_date = reinterpret_schedule_wall_time(starts_at, location_timezone).date()
        resolved = resolved_by_date.get(shift_date)
        if resolved is None:
            resolved = await resolve_break_rules(
                conn, company_id=company_id, location_id=location_id,
                shift_date=shift_date,
                employer_employee_count=employer_employee_count,
            )
            resolved_by_date[shift_date] = resolved
        effective_timezone = resolved.timezone or location_timezone
        plan = evaluate_break_plan(
            starts_at=starts_at, ends_at=ends_at,
            timezone=effective_timezone, rules=resolved.rules,
            employer_employee_count=(
                resolved.employer_employee_count
                if resolved.employer_employee_count is not None
                else employer_employee_count
            ),
        )
        plans.append(replace(
            plan,
            status="error" if resolved.source == "error" else plan.status,
            advisories=(*plan.advisories, *resolved.advisories),
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
    employer_employee_count: int | None | object = _EMPLOYER_EMPLOYEE_COUNT_UNSET,
) -> BreakPlan:
    """Evaluate and store the break instructions shown for one assignment."""
    if plan is None:
        plan = await resolve_shift_break_plan(
            conn, company_id, location_id=location_id, starts_at=starts_at,
            ends_at=ends_at, employee_id=employee_id,
            employer_employee_count=employer_employee_count,
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
    # RETURNING hands back `planned_breaks` unchanged (this statement does not
    # write it), so the common case — the column is NULL, which is every row
    # nobody has reviewed — costs no extra round trip.
    saved = decode_jsonb(await conn.fetchval(
        """
        UPDATE schedule_shift_assignments
        SET compliance_guidance = $1::jsonb,
            guidance_evaluated_at = NOW(),
            guidance_ruleset_hash = $2
        WHERE company_id = $3 AND shift_id = $4 AND employee_id = $5
        RETURNING planned_breaks
        """,
        json.dumps(payload), plan.rule_set_hash, company_id, shift_id, employee_id,
    ))
    if not saved:
        return plan
    # `planned_breaks` is the manager's reviewed answer and is deliberately not
    # recomputed here — but a saved time whose requirement is gone (retimed
    # out, waived, rules changed), or that no longer lands inside the shift, is
    # not stale advice, it is wrong advice, and the employee portal renders it
    # verbatim.  This is the one write path every invalidating edit reaches.
    survivors = prune_planned_breaks(
        saved,
        requirements=plan.requirements,
        shift_start_local=starts_at,
        shift_end_local=ends_at,
    )
    if survivors != saved:
        await conn.execute(
            """
            UPDATE schedule_shift_assignments
            SET planned_breaks = $1::jsonb
            WHERE company_id = $2 AND shift_id = $3 AND employee_id = $4
            """,
            json.dumps(survivors) if survivors else None,
            company_id, shift_id, employee_id,
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
    employer_employee_count: int | None | object = _EMPLOYER_EMPLOYEE_COUNT_UNSET,
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
        employer_employee_count=employer_employee_count,
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


_CO_PLANNED_QUERY = """
    SELECT id, location_id, starts_at, ends_at, required_staff
    FROM schedule_shifts
    WHERE company_id = $1 AND location_id = $2
      AND status <> 'cancelled'
      AND starts_at < $4 AND ends_at > $3
    ORDER BY starts_at, ends_at, id
"""

# Each round widens the window to the extent of what the last one found, so a
# chain of overlapping shifts is followed rather than cut at a clock boundary.
# Three is a bound on a pathological floor (a 24/7 store whose rows overlap
# without a break in the chain, where the component is the whole week and
# co-planning it would be quadratic for no operational gain); the chain is
# truncated there, and the rows past the truncation simply reserve nothing.
_CO_PLANNED_ROUNDS = 3


def _shifts_overlap(left: Any, right: Any) -> bool:
    return left["starts_at"] < right["ends_at"] and right["starts_at"] < left["ends_at"]


def _overlap_component(rows: Sequence[Any], *, target_id: UUID) -> list[Any]:
    """The rows sharing floor time with the target, following the chain.

    Overlap is symmetric, so every member of a component reaches the same set
    no matter which one is opened — which is the whole point.  A calendar day
    is not symmetric: a 22:00-06:00 row and a 00:00-08:00 row share six hours
    of floor, but only one of the two days contains both.
    """

    by_id = {row["id"]: row for row in rows}
    component = {target_id: by_id[target_id]}
    frontier = [by_id[target_id]]
    while frontier:
        current = frontier.pop()
        for row in rows:
            if row["id"] in component or not _shifts_overlap(current, row):
                continue
            component[row["id"]] = row
            frontier.append(row)
    return sorted(
        component.values(),
        key=lambda row: (row["starts_at"], row["ends_at"], str(row["id"])),
    )


async def _co_planned_shifts(conn, company_id: UUID, *, target: Any) -> list[Any]:
    """Every shift that shares floor time with ``target``, transitively."""

    window_start, window_end = target["starts_at"], target["ends_at"]
    component: list[Any] = [target]
    for _round in range(_CO_PLANNED_ROUNDS):
        rows = list(await conn.fetch(
            _CO_PLANNED_QUERY,
            company_id, target["location_id"], window_start, window_end,
        ))
        # The tenant-scoped read of the target is authoritative.  Keeping it in
        # the set also makes this robust to a concurrently cancelled shift: the
        # manager still receives a plan for the row they opened.
        if not any(row["id"] == target["id"] for row in rows):
            rows.append(target)
        component = _overlap_component(rows, target_id=target["id"])
        extent_start = min(row["starts_at"] for row in component)
        extent_end = max(row["ends_at"] for row in component)
        if (extent_start, extent_end) == (window_start, window_end):
            # Nothing outside the window can overlap anything inside it.
            break
        window_start, window_end = extent_start, extent_end
    return component


async def resolve_shift_stagger_plan(
    conn,
    company_id: UUID,
    *,
    shift_id: UUID,
) -> StaggerPlan | None:
    """Suggest break times while accounting for the same-location day's floor.

    Read-time only: nothing here writes.  The legal requirements still come
    from the same evaluator the write path stores on each assignment, so a
    suggestion can never disagree with the guidance already shown.

    A shift row represents one staffing need, not necessarily the whole floor.
    Planning only its assignees lets two otherwise identical rows recommend the
    same time.  Every row sharing floor time with this one is therefore planned
    in a stable order, and each later row treats earlier suggestions as
    occupied floor time.  Those rows are also the floor's headcount, so they
    are what the concurrency ceiling is read from — a ceiling taken from the
    opened row alone would be a row-sized budget against a floor-sized
    occupancy.

    Only the rows up to and including the target are planned: a row that comes
    after it in the order cannot constrain it, and skipping them keeps opening
    the first inspector of a long day cheap.  Their saved times still occupy
    the floor, because those are answers, not suggestions.

    Times a manager already saved on any of those shifts are fixed inputs with
    priority over every suggestion.  Nothing here writes.
    """
    shift = await conn.fetchrow(
        """
        SELECT id, location_id, starts_at, ends_at, required_staff
        FROM schedule_shifts
        WHERE id = $1 AND company_id = $2
        """,
        shift_id, company_id,
    )
    if shift is None:
        return None
    shifts = [shift]
    if shift["location_id"] is not None:
        shifts = await _co_planned_shifts(conn, company_id, target=shift)

    shift_ids = [row["id"] for row in shifts]
    assignment_rows = await conn.fetch(
        """
        SELECT shift_id, employee_id, planned_breaks
        FROM schedule_shift_assignments
        WHERE shift_id = ANY($1::uuid[]) AND company_id = $2 AND status <> 'declined'
        ORDER BY shift_id, employee_id
        """,
        shift_ids, company_id,
    )
    assignments_by_shift: dict[UUID, list[Any]] = {}
    for row in assignment_rows:
        assignments_by_shift.setdefault(row["shift_id"], []).append(row)

    target_index = next(
        index for index, row in enumerate(shifts) if row["id"] == shift_id
    )
    planned = shifts[:target_index + 1]
    # The target is last, so the zone that comes back is the one resolved for
    # its own date rather than whichever row happened to be evaluated last.
    effective_timezone, plans_by_shift, _unmapped_dates = await resolve_week_break_plans(
        conn, company_id, location_id=shift["location_id"],
        shifts=[
            (
                str(row["id"]), row["starts_at"], row["ends_at"],
                [entry["employee_id"] for entry in assignments_by_shift.get(row["id"], [])],
            )
            for row in planned
        ],
    )
    floor = [
        FloorWindow(
            start=reinterpret_schedule_wall_time(row["starts_at"], effective_timezone),
            end=reinterpret_schedule_wall_time(row["ends_at"], effective_timezone),
            assigned=len(assignments_by_shift.get(row["id"], [])),
            required=int(row["required_staff"] or 0),
        )
        for row in shifts
    ]
    locked_by_shift: dict[UUID, list[LockedBreak]] = {}
    for row in assignment_rows:
        locked_by_shift.setdefault(row["shift_id"], []).extend(
            locked_breaks_from_planned(
                decode_jsonb(row["planned_breaks"]),
                employee_id=row["employee_id"],
                timezone=effective_timezone,
            )
        )

    earlier_suggestions: list[LockedBreak] = []
    target_plan: StaggerPlan | None = None
    for peer in planned:
        peer_id = peer["id"]
        peer_rows = assignments_by_shift.get(peer_id, [])
        peer_plans = plans_by_shift.get(str(peer_id), {})
        own_locked = locked_by_shift.get(peer_id, [])
        other_saved = [
            entry
            for other_id, entries in locked_by_shift.items()
            if other_id != peer_id
            for entry in entries
        ]
        plan = stagger_shift_breaks(
            shift_start_local=reinterpret_schedule_wall_time(
                peer["starts_at"], effective_timezone,
            ),
            shift_end_local=reinterpret_schedule_wall_time(
                peer["ends_at"], effective_timezone,
            ),
            required_staff=int(peer["required_staff"] or 0),
            assignments=[
                StaggerAssignment(
                    employee_id=row["employee_id"],
                    plan=peer_plans[row["employee_id"]],
                )
                for row in peer_rows
                if row["employee_id"] in peer_plans
            ],
            locked=own_locked,
            occupied=(*other_saved, *earlier_suggestions),
            floor=floor,
        )
        if peer_id == shift_id:
            target_plan = plan
            break
        earlier_suggestions.extend(
            LockedBreak(
                employee_id=result.employee_id,
                kind=result.kind,
                ordinal=result.ordinal,
                start=result.suggested_start,
                duration_minutes=result.duration_minutes,
            )
            for result in plan.results
            if result.status in {"suggested", "deadline_conflict"}
            and result.suggested_start is not None
        )

    if target_plan is None:
        return None

    target_break_plans = plans_by_shift.get(str(shift_id), {})
    if target_break_plans:
        rule_advisories = [
            advisory
            for break_plan in target_break_plans.values()
            for advisory in break_plan.advisories
        ]
    else:
        # An empty shift still needs to expose an applicability decision before
        # assignments are made.  The weekly resolver intentionally skips rule
        # resolution when there are no employees, so resolve the open window
        # once for this read-only inspector response.
        open_plan = await resolve_shift_break_plan(
            conn,
            company_id,
            location_id=shift["location_id"],
            starts_at=shift["starts_at"],
            ends_at=shift["ends_at"],
        )
        rule_advisories = list(open_plan.advisories)

    merged_advisories = list(target_plan.advisories)
    for advisory in rule_advisories:
        if advisory not in merged_advisories:
            merged_advisories.append(advisory)
    return replace(target_plan, advisories=tuple(merged_advisories))
