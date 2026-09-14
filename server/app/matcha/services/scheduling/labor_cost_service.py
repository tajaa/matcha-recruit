"""DB layer for scheduled labor cost — loads what `labor_cost.cost_week` needs.

Separate from the engine for the same reason `schedule_review` is pure: the
arithmetic is the part worth testing exhaustively, and it should not need a
database to do it. This module is the thin part — four reads and a call.

Feature posture: `labor_cost` is wage data. `is_labor_cost_visible` is the ONE
place that decides whether a caller sees any of it, and it answers no unless
the company has the flag AND the caller is a business admin (`client`) or a
platform admin. There is no shift-manager role today, so that is the finest
gate the role model supports — see `services/scheduling/CLAUDE.md`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

from app.core.feature_flags import get_company_features

from . import schedule_compliance
from .labor_cost import HOURLY, _CENTS, PayProfile, WeekCost, cost_week, resolve_pay_profile
from .shift_compliance import _approved_db_rules, _location_state

# Same ceiling the planner uses for a week's assignment fan-out.
_MAX_ASSIGNMENTS = 5000

COST_ROLES = ("admin", "client")

logger = logging.getLogger(__name__)


async def labor_cost_enabled(company_id: UUID, conn=None) -> bool:
    features = await get_company_features(company_id, conn=conn)
    return bool(features.get("labor_cost"))


def labor_cost_visible_from(features: Mapping[str, Any], actor_role: Optional[str]) -> bool:
    """The same verdict as `is_labor_cost_visible`, for a caller that already
    holds the company's merged features. Keep the two in step."""
    return (actor_role or "") in COST_ROLES and bool(features.get("labor_cost"))


async def is_labor_cost_visible(company_id: UUID, actor_role: Optional[str], conn=None) -> bool:
    """Flag AND role. `individual` is deliberately excluded even though
    `require_admin_or_client` admits it: a personal Espresso account has no
    business reading a company's payroll."""
    if (actor_role or "") not in COST_ROLES:
        return False
    return await labor_cost_enabled(company_id, conn=conn)


async def _load_rules(conn, company_id: UUID, location_id: Optional[UUID]) -> dict[str, Any]:
    state, _city = await _location_state(conn, company_id, location_id)
    st = (state or "").strip().upper()
    db_rules = None
    if st and not schedule_compliance.is_curated_state(st):
        db_rules, _failed = await _approved_db_rules(conn, st)
    return schedule_compliance.rules_for_state(st or None, db_rules)


async def load_week_assignment_rows(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
) -> tuple[list[dict[str, Any]], bool]:
    """Every non-cancelled assignment starting in the location's week, as
    cost-engine rows. `shift_id` rides along so the review path can apply a
    staged change to this same picture.

    Returns `(rows, truncated)`. The cap is real, and a total computed over a
    truncated week is a partial figure presented as complete — the one failure
    this feature exists to prevent. `planning_inputs` surfaces
    `roster_truncated` for the same reason.
    """
    lo = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    hi = lo + timedelta(days=7)
    rows = await conn.fetch(
        """
        SELECT a.employee_id, s.id AS shift_id, s.starts_at,
               GREATEST(
                   0,
                   (EXTRACT(EPOCH FROM (s.ends_at - s.starts_at)) / 60)::int
                   - COALESCE(s.break_minutes, 0)
               ) AS worked_minutes
        FROM schedule_shift_assignments a
        JOIN schedule_shifts s ON s.id = a.shift_id
        WHERE s.company_id = $1 AND s.location_id = $2
          AND s.status <> 'cancelled'
          AND s.starts_at >= $3 AND s.starts_at < $4
        ORDER BY s.starts_at, a.employee_id
        LIMIT $5
        """,
        company_id, location_id, lo, hi, _MAX_ASSIGNMENTS,
    )
    return [{
        "employee_id": str(row["employee_id"]),
        "shift_id": str(row["shift_id"]),
        "starts_at": row["starts_at"],
        "worked_minutes": int(row["worked_minutes"] or 0),
    } for row in rows], len(rows) >= _MAX_ASSIGNMENTS


async def load_week_cost(
    conn,
    *,
    company_id: UUID,
    location_id: UUID,
    week_start: date,
    include_open_seats: bool = True,
    job_rates: Optional[Mapping[str, Optional[Decimal]]] = None,
) -> WeekCost:
    """Cost the seven days from `week_start` at one location.

    Cancelled shifts are excluded (they cost nothing); drafts are included,
    because the whole point is seeing the bill before you publish.
    """
    assignments, truncated = await load_week_assignment_rows(
        conn, company_id=company_id, location_id=location_id, week_start=week_start,
    )

    pay: dict[str, PayProfile] = {}
    employee_ids = sorted({item["employee_id"] for item in assignments})
    if employee_ids:
        pay_rows = await conn.fetch(
            "SELECT id, pay_rate, pay_classification FROM employees "
            "WHERE org_id = $1 AND id = ANY($2::uuid[])",
            company_id, [UUID(value) for value in employee_ids],
        )
        for row in pay_rows:
            profile = resolve_pay_profile(row)
            pay[profile.employee_id] = profile

    open_seats: list[dict[str, Any]] = []
    rates: dict[str, Optional[Decimal]] = dict(job_rates or {})
    if include_open_seats:
        open_seats = await load_open_seats(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
        if job_rates is None:
            rates = await load_job_rates(conn, company_id=company_id)

    result = cost_week(
        assignments,
        pay,
        await _load_rules(conn, company_id, location_id),
        week_start=week_start,
        open_seats=open_seats,
        job_rates=rates,
    )
    result.truncated = truncated
    return result


async def load_open_seats(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
) -> list[dict[str, Any]]:
    """The week's unfilled seats as cost-engine rows."""
    from . import week_builder

    demand = await week_builder._load_vacant_demand(
        conn, company_id=company_id, location_id=location_id,
        week_start=week_start, week_end=week_start + timedelta(days=6),
    )
    return [{
        "shift_id": shift.get("key"),
        "job_id": shift.get("job_id"),
        "starts_at": shift.get("starts_at"),
        "worked_minutes": shift.get("worked_minutes") or 0,
        "open": max(
            0,
            int(shift.get("required_staff") or 1) - len(shift.get("fixed_employee_ids") or []),
        ),
    } for shift in demand]


async def load_job_rates(conn, *, company_id: UUID) -> dict[str, Optional[Decimal]]:
    """The company's per-job open-seat rates. Company-wide and therefore
    identical for every location — a caller costing several locations reads it
    once and passes it in, rather than re-running it per location."""
    rows = await conn.fetch(
        "SELECT id, default_hourly_rate FROM schedule_jobs WHERE company_id = $1", company_id,
    )
    return {
        str(row["id"]): (
            Decimal(str(row["default_hourly_rate"]))
            if row["default_hourly_rate"] is not None else None
        )
        for row in rows
    }


async def load_pay_profiles(
    conn, *, company_id: UUID, employee_ids: list[str],
) -> dict[str, PayProfile]:
    """Pay profiles for a named set — used by the review path, which already
    knows exactly whose hours are moving."""
    if not employee_ids:
        return {}
    rows = await conn.fetch(
        "SELECT id, pay_rate, pay_classification FROM employees "
        "WHERE org_id = $1 AND id = ANY($2::uuid[])",
        company_id, [UUID(value) for value in sorted(set(employee_ids))],
    )
    out: dict[str, PayProfile] = {}
    for row in rows:
        profile = resolve_pay_profile(row)
        out[profile.employee_id] = profile
    return out


# ── Review cost: what one staged change does to the bill ─────────────────


def _in_week(row: Mapping[str, Any], week_start: date) -> bool:
    starts = row.get("starts_at")
    if isinstance(starts, str):
        try:
            starts = datetime.fromisoformat(starts)
        except ValueError:
            return False
    day = starts.date() if hasattr(starts, "date") else None
    return day is not None and week_start <= day <= week_start + timedelta(days=6)


def _optional_money(value) -> Optional[float]:
    """None stays None. An unpriced person has no cost, and 0.0 would say
    their shifts are free."""
    return None if value is None else float(value.quantize(_CENTS))


def _empty_delta(basis: dict[str, Any]) -> dict[str, Any]:
    return {
        "before": 0.0, "after": 0.0, "delta": 0.0,
        "ot_premium_before": 0.0, "ot_premium_after": 0.0,
        "by_employee": {}, "unpriced_employee_ids": [], "unpriced_employee_count": 0,
        "basis": basis,
    }


async def cost_delta_for_rows(
    conn,
    *,
    company_id: UUID,
    location_id: Optional[UUID],
    weeks: Sequence[tuple[date, list[dict[str, Any]], list[dict[str, Any]]]],
    actor_role: Optional[str] = None,
    open_seats_by_week: Optional[Mapping[date, list[dict[str, Any]]]] = None,
    job_rates: Optional[Mapping[str, Optional[Decimal]]] = None,
) -> Optional[dict[str, Any]]:
    """The `cost` block a `ScheduleReview` carries: the bill before and after
    the change, and the same split per person.

    `weeks` is one `(week_start, before_rows, after_rows)` triple per week the
    change touches — a batch may straddle a week boundary, and overtime is a
    per-week question, so each week is costed on its own and the results are
    summed. Both sides of every triple must be the WHOLE week for the
    location, not only the rows the change names: overtime depends on
    everything else the person is already working, and two reviews costed over
    different subsets cannot be compared with each other.

    Returns None unless the caller may see wage data. `by_employee` is exactly
    the per-coworker figure `labor_cost.py`'s docstring says this feature must
    never hand out, and a review is NOT a manager-only surface: the fill
    preview (`POST …/fill-vacant/preview`) is mounted on
    `require_company_member`, which admits `employee` and `individual`, and an
    employee flagged `is_manager` clears `assert_manager_location`. So the same
    flag+role gate the HTTP surfaces use runs here too. `actor_role` defaults
    to None, which fails closed — a caller that forgets to pass it gets no
    cost rather than an open one.
    """
    try:
        if not await is_labor_cost_visible(company_id, actor_role, conn=conn):
            return None
    except Exception:  # noqa: BLE001
        # Cost is additive to a review. A feature read that fails must not stop
        # a manager staging a schedule change — same posture as the assignment
        # guard, which leaves ops un-annotated rather than raising.
        logger.warning("labor_cost: feature read failed for company %s", company_id)
        return None

    employee_ids = [
        str(row["employee_id"])
        for _week, before, after in weeks
        for row in (*before, *after)
        if row.get("employee_id")
    ]
    try:
        pay = await load_pay_profiles(conn, company_id=company_id, employee_ids=employee_ids)
        rules = await _load_rules(conn, company_id, location_id)
    except Exception:  # noqa: BLE001
        logger.warning("labor_cost: pricing inputs unavailable for company %s", company_id)
        return None

    totals = {"before": Decimal("0"), "after": Decimal("0"),
              "ot_before": Decimal("0"), "ot_after": Decimal("0")}
    by_employee: dict[str, dict[str, Optional[Decimal]]] = {}
    unpriced: set[str] = set()
    basis: dict[str, Any] = {}

    for week_start, before_rows, after_rows in weeks:
        in_week = [row for row in before_rows if _in_week(row, week_start)]
        out_week = [row for row in after_rows if _in_week(row, week_start)]
        # Open seats ride BOTH sides. The board's `summary.cost.total` includes
        # them, so leaving them out here would put the review and the header it
        # sits beside on different bases — and filling a seat would read as new
        # spend rather than as demand that was already projected.
        seats = list((open_seats_by_week or {}).get(week_start) or [])
        before = cost_week(
            in_week, pay, rules, week_start=week_start,
            open_seats=seats, job_rates=job_rates or {},
        )
        after = cost_week(
            out_week, pay, rules, week_start=week_start,
            open_seats=_remaining_seats(seats, in_week, out_week), job_rates=job_rates or {},
        )
        basis = after.basis
        totals["before"] += before.total
        totals["after"] += after.total
        totals["ot_before"] += before.ot_premium
        totals["ot_after"] += after.ot_premium
        unpriced.update(before.unpriced_employee_ids)
        unpriced.update(after.unpriced_employee_ids)

        for employee_id in {str(row["employee_id"]) for row in (*in_week, *out_week)}:
            # An employee who is priced but has no shifts on one side costs
            # nothing there — that is a saving, not missing data. Only a
            # missing pay rate yields None.
            absent = None if pay.get(employee_id, PayProfile(employee_id, None, HOURLY, False)).rate is None \
                else Decimal("0")
            entry = by_employee.setdefault(employee_id, {"before": None, "after": None})
            for side, cost in (("before", before), ("after", after)):
                value = cost.employee_total(employee_id, absent=absent)
                if value is None:
                    continue
                entry[side] = (entry[side] or Decimal("0")) + value

    return {
        "before": float(totals["before"].quantize(_CENTS)),
        "after": float(totals["after"].quantize(_CENTS)),
        "delta": float((totals["after"] - totals["before"]).quantize(_CENTS)),
        "ot_premium_before": float(totals["ot_before"].quantize(_CENTS)),
        "ot_premium_after": float(totals["ot_after"].quantize(_CENTS)),
        "by_employee": {
            employee_id: {"before": _optional_money(sides["before"]),
                          "after": _optional_money(sides["after"])}
            for employee_id, sides in sorted(by_employee.items())
        },
        "unpriced_employee_ids": sorted(unpriced),
        "unpriced_employee_count": len(unpriced),
        "basis": basis,
    }


def _remaining_seats(
    seats: list[dict[str, Any]],
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The open seats left AFTER the change: filling one converts projected
    open-seat cost into real assigned cost, and counting it on both sides would
    double it. Anything the change did not touch stays projected on both."""
    filled: dict[str, int] = {}
    before_counts: dict[str, int] = {}
    for row in before_rows:
        before_counts[row.get("shift_id") or ""] = before_counts.get(row.get("shift_id") or "", 0) + 1
    for row in after_rows:
        shift_id = row.get("shift_id") or ""
        filled[shift_id] = filled.get(shift_id, 0) + 1
    out = []
    for seat in seats:
        shift_id = str(seat.get("shift_id") or "")
        added = filled.get(shift_id, 0) - before_counts.get(shift_id, 0)
        remaining = max(0, int(seat.get("open") or 0) - max(0, added))
        if remaining:
            out.append({**seat, "open": remaining})
    return out


def _dt(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _op_locations(ops: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        str(raw)
        for op in ops
        for raw in (op.get("location_id"), op.get("second_location_id"))
        if raw
    }


def _apply_ops(
    rows: list[dict[str, Any]],
    ops: Sequence[Mapping[str, Any]],
    shifts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The week's assignment rows as the staged ops would leave them.

    Every kind in `schedule_chat._EDIT_KINDS` is modelled. A kind that reached
    here unmodelled would report a confident $0 for a change that costs real
    money, which is worse than reporting nothing — `_review_cost_for_ops`
    refuses the whole block rather than let that happen.
    """
    out = [dict(row) for row in rows]

    def minutes_for(shift_id: Optional[str]) -> int:
        shift = shifts.get(str(shift_id) or "")
        if not shift:
            return 0
        return max(
            0,
            int((shift["ends_at"] - shift["starts_at"]).total_seconds() // 60)
            - int(shift["break_minutes"] or 0),
        )

    for op in ops:
        kind = op.get("kind")
        shift_id = str(op.get("shift_id") or "")
        second_id = str(op.get("second_shift_id") or "")

        if kind in ("unassign", "reassign") and op.get("from_employee_id"):
            source = str(op["from_employee_id"])
            out = [r for r in out if not (r["employee_id"] == source and r["shift_id"] == shift_id)]
        if kind == "cancel":
            out = [r for r in out if r["shift_id"] != shift_id]
        if kind in ("assign", "reassign") and op.get("to_employee_id"):
            shift = shifts.get(shift_id)
            if shift:
                out.append({
                    "employee_id": str(op["to_employee_id"]), "shift_id": shift_id,
                    "starts_at": shift["starts_at"], "worked_minutes": minutes_for(shift_id),
                })
        if kind == "retime" and op.get("new_starts_at") and op.get("new_ends_at"):
            starts_at, ends_at = _dt(op["new_starts_at"]), _dt(op["new_ends_at"])
            worked = max(
                0,
                int((ends_at - starts_at).total_seconds() // 60) - int(op.get("break_minutes") or 0),
            )
            for row in out:
                if row["shift_id"] == shift_id:
                    row["starts_at"] = starts_at
                    row["worked_minutes"] = worked
        if kind == "swap" and second_id:
            # A swap exchanges the two shifts' whole assignee SETS, which is
            # why this needs the week's real rows and not the op's named
            # people: `_apply_edit_ops` reads both rosters live.
            a_shift, b_shift = shifts.get(shift_id), shifts.get(second_id)
            if a_shift and b_shift:
                a_minutes, b_minutes = minutes_for(shift_id), minutes_for(second_id)
                for row in out:
                    if row["shift_id"] == shift_id:
                        row["shift_id"] = second_id
                        row["starts_at"] = b_shift["starts_at"]
                        row["worked_minutes"] = b_minutes
                    elif row["shift_id"] == second_id:
                        row["shift_id"] = shift_id
                        row["starts_at"] = a_shift["starts_at"]
                        row["worked_minutes"] = a_minutes
    return out


async def review_cost_for_ops(
    conn,
    *,
    company_id: UUID,
    location_id: Optional[UUID],
    ops: list[dict[str, Any]],
    actor_role: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Cost block for an edit/batch proposal's accepted ops. Never raises.

    `actor_role` defaults to None and so fails closed: a surface that has not
    been taught to pass the caller's role gets no cost rather than an
    ungated one."""
    if not ops:
        return None
    try:
        if not await is_labor_cost_visible(company_id, actor_role, conn=conn):
            return None
    except Exception:  # noqa: BLE001
        logger.warning("labor_cost: feature read failed for company %s", company_id)
        return None
    try:
        return await _review_cost_for_ops(
            conn, company_id=company_id, location_id=location_id,
            ops=ops, actor_role=actor_role,
        )
    except Exception:  # noqa: BLE001
        logger.warning("labor_cost: review cost failed for company %s", company_id)
        return None


async def _review_cost_for_ops(
    conn,
    *,
    company_id: UUID,
    location_id: Optional[UUID],
    ops: list[dict[str, Any]],
    actor_role: Optional[str],
) -> Optional[dict[str, Any]]:
    from .location_profile import resolve_week_start_weekday
    from .schedule_chat import _EDIT_KINDS
    from .schedule_rules import align_week_start

    kinds = {op.get("kind") for op in ops}
    if not kinds.issubset(set(_EDIT_KINDS)):
        # An unmodelled kind would leave `after_rows` equal to `before_rows`
        # and report $0 for a change that costs money. Say nothing instead.
        logger.warning("labor_cost: unmodelled edit kind(s) %s", sorted(kinds - set(_EDIT_KINDS)))
        return None

    # One location, or no coherent week bill to state. `location_id` is the
    # editor's own selection; a channel-wide batch carries it per op instead.
    locations = _op_locations(ops)
    if location_id is not None:
        scope = location_id
    elif len(locations) == 1:
        scope = UUID(next(iter(locations)))
    else:
        return None
    if locations - {str(scope)}:
        return None

    shift_ids = {
        UUID(str(raw))
        for op in ops
        for raw in (op.get("shift_id"), op.get("second_shift_id")) if raw
    }
    shift_rows = await conn.fetch(
        "SELECT id, starts_at, ends_at, COALESCE(break_minutes, 0) AS break_minutes "
        "FROM schedule_shifts WHERE company_id = $1 AND id = ANY($2::uuid[])",
        company_id, sorted(shift_ids),
    )
    shifts = {str(row["id"]): dict(row) for row in shift_rows}

    week_start_weekday = await resolve_week_start_weekday(
        conn, company_id=company_id, location_id=scope,
    )
    moments = [
        _dt(raw)
        for op in ops
        for raw in (op.get("starts_at"), op.get("new_starts_at"), op.get("second_starts_at"))
        if raw
    ]
    if not moments:
        return None
    week_starts = sorted({align_week_start(moment.date(), week_start_weekday) for moment in moments})

    # Load every touched week FIRST and apply the ops to the combined picture.
    # Applying per week would lose a `retime`/`swap` that moves a shift ACROSS
    # a boundary: the source week drops the row and the destination week, whose
    # `before` never contained it, has nothing to match — a pure saving for a
    # change that costs the same.
    combined_before: list[dict[str, Any]] = []
    seats_by_week: dict[date, list[dict[str, Any]]] = {}
    for week_start in week_starts:
        rows, _truncated = await load_week_assignment_rows(
            conn, company_id=company_id, location_id=scope, week_start=week_start,
        )
        combined_before.extend(rows)
        seats_by_week[week_start] = await load_open_seats(
            conn, company_id=company_id, location_id=scope, week_start=week_start,
        )
    combined_after = _apply_ops(combined_before, ops, shifts)
    weeks = [(week_start, combined_before, combined_after) for week_start in week_starts]

    return await cost_delta_for_rows(
        conn, company_id=company_id, location_id=scope, weeks=weeks,
        actor_role=actor_role, open_seats_by_week=seats_by_week,
        job_rates=await load_job_rates(conn, company_id=company_id),
    )
