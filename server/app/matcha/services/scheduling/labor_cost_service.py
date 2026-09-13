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
from typing import Any, Optional
from uuid import UUID

from app.core.feature_flags import get_company_features

from . import schedule_compliance
from .labor_cost import _CENTS, PayProfile, WeekCost, cost_week, resolve_pay_profile
from .shift_compliance import _approved_db_rules, _location_state

# Same ceiling the planner uses for a week's assignment fan-out.
_MAX_ASSIGNMENTS = 5000

COST_ROLES = ("admin", "client")

logger = logging.getLogger(__name__)


async def labor_cost_enabled(company_id: UUID, conn=None) -> bool:
    features = await get_company_features(company_id, conn=conn)
    return bool(features.get("labor_cost"))


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


async def load_week_cost(
    conn,
    *,
    company_id: UUID,
    location_id: UUID,
    week_start: date,
    include_open_seats: bool = True,
) -> WeekCost:
    """Cost the seven days from `week_start` at one location.

    Cancelled shifts are excluded (they cost nothing); drafts are included,
    because the whole point is seeing the bill before you publish.
    """
    lo = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    hi = lo + timedelta(days=7)

    rows = await conn.fetch(
        """
        SELECT a.employee_id, s.starts_at,
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
    assignments = [{
        "employee_id": str(row["employee_id"]),
        "starts_at": row["starts_at"],
        "worked_minutes": int(row["worked_minutes"] or 0),
    } for row in rows]

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
    job_rates: dict[str, Optional[Decimal]] = {}
    if include_open_seats:
        # Imported here rather than at module scope: `week_builder` imports a
        # good part of the scheduling package, and this module is pulled in by
        # route modules that must stay cheap to import.
        from . import week_builder

        demand = await week_builder._load_vacant_demand(
            conn, company_id=company_id, location_id=location_id,
            week_start=week_start, week_end=week_start + timedelta(days=6),
        )
        open_seats = [{
            "job_id": shift.get("job_id"),
            "starts_at": shift.get("starts_at"),
            "worked_minutes": shift.get("worked_minutes") or 0,
            "open": max(
                0,
                int(shift.get("required_staff") or 1) - len(shift.get("fixed_employee_ids") or []),
            ),
        } for shift in demand]
        job_rows = await conn.fetch(
            "SELECT id, default_hourly_rate FROM schedule_jobs WHERE company_id = $1",
            company_id,
        )
        job_rates = {
            str(row["id"]): (
                Decimal(str(row["default_hourly_rate"]))
                if row["default_hourly_rate"] is not None else None
            )
            for row in job_rows
        }

    return cost_week(
        assignments,
        pay,
        await _load_rules(conn, company_id, location_id),
        week_start=week_start,
        open_seats=open_seats,
        job_rates=job_rates,
    )


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


def _in_week(row: Any, week_start: date) -> bool:
    starts = row.get("starts_at")
    if isinstance(starts, str):
        try:
            starts = datetime.fromisoformat(starts)
        except ValueError:
            return False
    day = starts.date() if hasattr(starts, "date") else None
    return day is not None and week_start <= day <= week_start + timedelta(days=6)


async def cost_delta_for_rows(
    conn,
    *,
    company_id: UUID,
    location_id: Optional[UUID],
    week_start: date,
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """The `cost` block a `ScheduleReview` carries: the week's bill before and
    after the change, and the same split per person.

    Returns None when the company does not have `labor_cost` — the key is then
    absent from the review, which is what every renderer keys off. A review is
    built on manager surfaces only, so this is the flag check alone; the
    role check lives on the HTTP edge.
    """
    try:
        if not await labor_cost_enabled(company_id, conn=conn):
            return None
    except Exception:  # noqa: BLE001
        # Cost is additive to a review. A feature read that fails must not stop
        # a manager staging a schedule change — same posture as the assignment
        # guard, which leaves ops un-annotated rather than raising.
        logger.warning("labor_cost: feature read failed for company %s", company_id)
        return None

    before_rows = [row for row in before_rows if _in_week(row, week_start)]
    after_rows = [row for row in after_rows if _in_week(row, week_start)]
    employee_ids = [
        str(row["employee_id"]) for row in (*before_rows, *after_rows) if row.get("employee_id")
    ]
    try:
        pay = await load_pay_profiles(conn, company_id=company_id, employee_ids=employee_ids)
        rules = await _load_rules(conn, company_id, location_id)
    except Exception:  # noqa: BLE001
        logger.warning("labor_cost: pricing inputs unavailable for company %s", company_id)
        return None

    before = cost_week(before_rows, pay, rules, week_start=week_start)
    after = cost_week(after_rows, pay, rules, week_start=week_start)

    by_employee = {}
    for employee_id in sorted({str(row["employee_id"]) for row in (*before_rows, *after_rows)}):
        by_employee[employee_id] = {
            "before": _optional_money(before.employee_total(employee_id)),
            "after": _optional_money(after.employee_total(employee_id)),
        }
    unpriced = sorted(set(before.unpriced_employee_ids) | set(after.unpriced_employee_ids))
    return {
        "before": float(before.total.quantize(_CENTS)),
        "after": float(after.total.quantize(_CENTS)),
        "delta": float((after.total - before.total).quantize(_CENTS)),
        "ot_premium_before": float(before.ot_premium.quantize(_CENTS)),
        "ot_premium_after": float(after.ot_premium.quantize(_CENTS)),
        "by_employee": by_employee,
        "unpriced_employee_ids": unpriced,
        "unpriced_employee_count": len(unpriced),
        "basis": after.basis,
    }


def _optional_money(value) -> Optional[float]:
    """None stays None. An unpriced person has no cost, and 0.0 would say
    their shifts are free."""
    return None if value is None else float(value.quantize(_CENTS))


def _ledger_rows(ledgers: dict) -> list[dict[str, Any]]:
    """`assignment_guard.EmployeeLedger` → cost-engine assignment rows. The
    ledger is the same picture the guard judged the batch against, so the
    "before" number and the "before" hours can never disagree."""
    rows: list[dict[str, Any]] = []
    for employee_id, ledger in ledgers.items():
        for starts_at, ends_at, shift_id, _label in ledger.intervals:
            rows.append({
                "employee_id": str(employee_id),
                "shift_id": str(shift_id),
                "starts_at": starts_at,
                "worked_minutes": ledger.worked_minutes.get(
                    str(shift_id),
                    max(0, int((ends_at - starts_at).total_seconds() // 60)),
                ),
            })
    return rows


async def review_cost_for_ops(
    conn,
    *,
    company_id: UUID,
    location_id: Optional[UUID],
    ops: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Cost block for an edit/batch proposal's accepted ops.

    Rebuilds the guard's ledgers rather than reusing the ones
    `_review_assign_ops` built: that helper is called deep inside
    `_resolve_edit_ops` and returns nothing, and one extra query on a
    flag-gated path is cheaper than threading a cost channel through the
    resolver. Skipped entirely when the flag is off.
    """
    if not ops:
        return None
    try:
        if not await labor_cost_enabled(company_id, conn=conn):
            return None
    except Exception:  # noqa: BLE001
        logger.warning("labor_cost: feature read failed for company %s", company_id)
        return None
    try:
        return await _review_cost_for_ops(
            conn, company_id=company_id, location_id=location_id, ops=ops,
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
) -> Optional[dict[str, Any]]:
    from .assignment_guard import build_ledgers
    from .schedule_rules import align_week_start
    from .location_profile import resolve_week_start_weekday

    def _dt(value):
        return datetime.fromisoformat(value) if isinstance(value, str) else value

    starts = [_dt(op["starts_at"]) for op in ops if op.get("starts_at")]
    ends = [_dt(op["ends_at"]) for op in ops if op.get("ends_at")]
    if not starts or not ends:
        return None
    employee_ids = list(dict.fromkeys(
        UUID(raw) for op in ops
        for raw in (op.get("to_employee_id"), op.get("from_employee_id")) if raw
    ))
    if not employee_ids:
        return None

    ledgers = await build_ledgers(
        conn, company_id, employee_ids=employee_ids,
        window_start=min(starts), window_end=max(ends),
    )
    week_start_weekday = await resolve_week_start_weekday(
        conn, company_id=company_id, location_id=location_id,
    )
    week_start = align_week_start(min(starts).date(), week_start_weekday)

    before_rows = _ledger_rows(ledgers)
    after_rows = list(before_rows)
    for op in ops:
        kind = op.get("kind")
        shift_id = str(op.get("shift_id") or "")
        if kind in ("unassign", "reassign") and op.get("from_employee_id"):
            after_rows = [
                row for row in after_rows
                if not (row["employee_id"] == str(op["from_employee_id"]) and row["shift_id"] == shift_id)
            ]
        if kind == "cancel":
            after_rows = [row for row in after_rows if row["shift_id"] != shift_id]
        if kind in ("assign", "reassign") and op.get("to_employee_id"):
            starts_at = _dt(op["starts_at"])
            ends_at = _dt(op["ends_at"])
            after_rows.append({
                "employee_id": str(op["to_employee_id"]),
                "shift_id": shift_id,
                "starts_at": starts_at,
                "worked_minutes": max(
                    0,
                    int((ends_at - starts_at).total_seconds() // 60)
                    - int(op.get("break_minutes") or 0),
                ),
            })

    return await cost_delta_for_rows(
        conn, company_id=company_id, location_id=location_id, week_start=week_start,
        before_rows=before_rows, after_rows=after_rows,
    )
