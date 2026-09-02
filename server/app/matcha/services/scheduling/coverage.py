"""Who is free to cover a published shift on a given date — the standalone
extraction of `schedule_chat.build_proposal`'s candidate-assembly steps
(busy-overlap filter, availability filter, week-hours ranking, lapse
annotation), pulled out so channel `@huume` can answer "who can cover for
Aisha tomorrow?" without going through proposal-building. Read-only, no LLM.

Deliberately does NOT run `schedule_compliance` — that engine answers "is
THIS shift legal", which only matters once someone is actually being
assigned. A coverage suggestion is not an assignment; the compliance check
still runs (via `schedule_chat`/the REST route) at the point someone actually
gets scheduled.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from app.matcha.services.scheduling.schedule_intelligence import fetch_lapse_items
from app.matcha.services.scheduling.schedule_rules import (
    INACTIVE_EMPLOYMENT_STATUSES,
    availability_violations,
    sunday_indexed_weekday,
)
from app.matcha.services.scheduling.schedule_profiles import fetch_effective_job_employee_ids
from app.matcha.services.scheduling.shift_writes import fetch_availability

_SHIFT_CAP = 3
_CANDIDATE_CAP = 5


async def find_coverage_candidates(
    conn, *, company_id: UUID, target_date: date, location_id: Optional[UUID],
    role_hint: Optional[str], features: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """{"shifts": [...], "role_note": Optional[str]}.

    Each shift dict: starts_at/ends_at (datetime), role, required_staff,
    assignees (list[str] names), candidates (list of {name, week_hours,
    job_title, title_mismatch, flags}), ranked least-hours-first, capped at
    `_CANDIDATE_CAP`. No published shifts that day -> {"shifts": []}.
    """
    day_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    shift_rows = await _fetch_day_shifts(conn, company_id, day_start, day_end, location_id, role_hint)
    role_note = None
    if not shift_rows and role_hint:
        shift_rows = await _fetch_day_shifts(conn, company_id, day_start, day_end, location_id, None)
        if shift_rows:
            role_note = f"Nothing matched \"{role_hint}\" — showing every published shift that day instead."

    if not shift_rows:
        return {"shifts": [], "role_note": None}

    shift_rows = [dict(r) for r in shift_rows]

    shift_ids = [r["id"] for r in shift_rows]
    assignee_rows = await conn.fetch(
        """
        SELECT a.shift_id, e.id AS employee_id, e.first_name, e.last_name
        FROM schedule_shift_assignments a
        JOIN employees e ON e.id = a.employee_id
        WHERE a.shift_id = ANY($1::uuid[])
        """,
        shift_ids,
    )
    assignees_by_shift: dict[Any, list[dict]] = {}
    assigned_ids_by_shift: dict[Any, set] = {}
    for r in assignee_rows:
        assignees_by_shift.setdefault(r["shift_id"], []).append(
            {"id": r["employee_id"], "name": f"{r['first_name']} {r['last_name']}".strip()}
        )
        assigned_ids_by_shift.setdefault(r["shift_id"], set()).add(str(r["employee_id"]))

    # A coverage candidate must actually be schedulable at this shift's
    # location — same strict (no NULL-fallback) rule as fetch_roster/
    # assert_employee_schedulable_at, so Huume never proposes someone the
    # REST assignment path would then refuse with employee_has_no_location.
    roster_params: list[Any] = [company_id, list(INACTIVE_EMPLOYMENT_STATUSES)]
    roster_where = "org_id = $1 AND COALESCE(employment_status, 'active') <> ALL($2::text[])"
    if location_id is not None:
        roster_params.append(location_id)
        roster_where += f" AND work_location_id = ${len(roster_params)}"
    roster_rows = await conn.fetch(
        f"""
        SELECT id, first_name, last_name, job_title
        FROM employees
        WHERE {roster_where}
        ORDER BY first_name, last_name, id
        """,
        *roster_params,
    )
    roster = [dict(r) for r in roster_rows]

    week_start = target_date - timedelta(days=sunday_indexed_weekday(target_date))
    week_lo = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    week_hi = week_lo + timedelta(days=7)
    hours_rows = await conn.fetch(
        """
        SELECT a.employee_id,
               SUM(EXTRACT(EPOCH FROM (s.ends_at - s.starts_at))) / 3600.0 AS hrs
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id
        WHERE s.company_id = $1 AND s.status <> 'cancelled'
          AND s.starts_at >= $2 AND s.starts_at < $3
        GROUP BY a.employee_id
        """,
        company_id, week_lo, week_hi,
    )
    hours_by_id: dict[str, float] = {str(r["employee_id"]): float(r["hrs"] or 0.0) for r in hours_rows}

    training_enabled = bool((features or {}).get("training"))
    credential_templates_enabled = bool((features or {}).get("credential_templates"))
    lapse_map: dict[str, list[dict]] = {}
    if roster:
        lapse_map = await fetch_lapse_items(
            conn, company_id, [r["id"] for r in roster],
            credential_templates_enabled=credential_templates_enabled,
            training_enabled=training_enabled,
        )

    result_shifts = []
    for shift in shift_rows:
        starts_at, ends_at = shift["starts_at"], shift["ends_at"]
        assigned_ids = assigned_ids_by_shift.get(shift["id"], set())

        busy_rows = await conn.fetch(
            """
            SELECT DISTINCT a.employee_id
            FROM schedule_shifts s
            JOIN schedule_shift_assignments a ON a.shift_id = s.id
            WHERE s.company_id = $1 AND s.status <> 'cancelled'
              AND s.starts_at < $3 AND s.ends_at > $2
            """,
            company_id, starts_at, ends_at,
        )
        busy = {str(r["employee_id"]) for r in busy_rows} | assigned_ids
        free = [r for r in roster if str(r["id"]) not in busy]

        qualified_ids = await fetch_effective_job_employee_ids(
            conn, company_id=company_id, job_id=shift.get("job_id"),
            employee_ids=[r["id"] for r in free], as_of=starts_at.date(),
        )
        free = [r for r in free if r["id"] in qualified_ids]

        avail_map = await fetch_availability(conn, company_id, [r["id"] for r in free])
        survivors = [
            r for r in free
            if not availability_violations(avail_map.get(r["id"], {}), starts_at, ends_at)
        ]

        candidates = []
        for r in survivors:
            eid = str(r["id"])
            flags = [
                f"{item['item']} lapsed"
                for item in lapse_map.get(eid, [])
                if item["date"] is not None and item["date"] <= target_date
            ]
            title_mismatch = bool(
                shift.get("role") and r.get("job_title")
                and shift["role"].strip().lower() not in r["job_title"].strip().lower()
                and r["job_title"].strip().lower() not in shift["role"].strip().lower()
            )
            candidates.append({
                "employee_id": eid,
                "name": f"{r['first_name']} {r['last_name']}".strip(),
                "week_hours": hours_by_id.get(eid, 0.0),
                "job_title": r.get("job_title"),
                "title_mismatch": title_mismatch,
                "flags": flags,
            })
        candidates.sort(key=lambda c: (c["week_hours"], c["name"], c["employee_id"]))

        result_shifts.append({
            "id": shift["id"], "starts_at": starts_at, "ends_at": ends_at,
            "role": shift.get("role"), "required_staff": shift.get("required_staff", 1),
            "assignees": [a["name"] for a in assignees_by_shift.get(shift["id"], [])],
            "candidates": candidates[:_CANDIDATE_CAP],
        })

    return {"shifts": result_shifts, "role_note": role_note}


async def _fetch_day_shifts(conn, company_id, day_start, day_end, location_id, role_hint):
    if role_hint:
        return await conn.fetch(
            """
            SELECT id, starts_at, ends_at, role, required_staff, location_id, job_id
            FROM schedule_shifts
            WHERE company_id = $1 AND status = 'published'
              AND starts_at < $3 AND ends_at > $2
              AND ($4::uuid IS NULL OR location_id IS NULL OR location_id = $4)
              AND role ILIKE '%' || $5 || '%'
            ORDER BY starts_at LIMIT $6
            """,
            company_id, day_start, day_end, location_id, role_hint, _SHIFT_CAP,
        )
    return await conn.fetch(
        """
        SELECT id, starts_at, ends_at, role, required_staff, location_id, job_id
        FROM schedule_shifts
        WHERE company_id = $1 AND status = 'published'
          AND starts_at < $3 AND ends_at > $2
          AND ($4::uuid IS NULL OR location_id IS NULL OR location_id = $4)
        ORDER BY starts_at LIMIT $5
        """,
        company_id, day_start, day_end, location_id, _SHIFT_CAP,
    )
