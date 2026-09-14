"""Scheduled labor cost — what a week of shifts will cost, before it is published.

Pure and DB-free, like `schedule_review`: the callers hand it assignments,
pay profiles and the state's rule dict, and it returns a `WeekCost`. One
engine feeds every surface that already shows hours (the board's day columns,
the inputs rail's per-person bar, the `ScheduleReview` before/after, and
Huume's `roster_load`), so no two of them can disagree about the number.

Three rules it inherits from the modules next to it:

- **Thresholds and multipliers are law, and they live in the cited table.**
  `schedule_compliance._SCHEDULING_RULES` already carried `weekly_ot_hours`
  (FLSA § 207(a)), CA's `daily_ot_hours` / `daily_doubletime_hours`
  (Cal. Lab. Code § 510) and NY's deliberate `daily_ot_hours: None`; this
  change added the `ot_multiplier` / `doubletime_multiplier` those same
  statutes state. Nothing here hardcodes 40, 1.5 or 2.0. An unmapped state
  therefore prices on the federal floor alone — correct, and labelled as such
  by the `jurisdiction` block the callers already carry.

- **No rate on file ⇒ counted, never zero.** Same degradation as
  `fair_workweek.predictability_pay_estimate`: an employee with no `pay_rate`,
  or an open seat whose job has no `default_hourly_rate`, is reported in
  `unpriced_*` and contributes nothing. A $0 line reads as "free", which is
  the one thing it never means.

- **As-scheduled, never as-worked.** There is no time-clock data in this
  codebase. `worked_minutes` is the planned span minus the planned break, so
  UI copy says "scheduled labor cost". Callers must not present this as payroll.

Overtime does not pyramid: an hour is paid at the single highest rate that
applies to it, so a CA hour past the 8th is daily OT and is NOT counted again
when the week crosses 40.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

_CENTS = Decimal("0.01")
_MINUTES_PER_HOUR = Decimal("60")
_WEEKS_PER_YEAR = Decimal("52")

# Mirrors `insurance/wc_classmap.py`'s documented disambiguation: that module
# already has to tell an hourly rate from an annual salary when
# `pay_classification` is NULL, and two engines guessing differently about the
# same row would be worse than either guess. Keep them in step.
_ANNUAL_RATE_FLOOR = Decimal("2000")

HOURLY = "hourly"
EXEMPT = "exempt"


def _money(value: Optional[Decimal]) -> float:
    return float((value or Decimal("0")).quantize(_CENTS))


def _hours(minutes: int) -> Decimal:
    return Decimal(int(minutes)) / _MINUTES_PER_HOUR


def _threshold_minutes(rules: Mapping[str, Any], key: str) -> Optional[int]:
    """Hours threshold from the cited table, as minutes. `None` (the table's
    "explicitly no such rule here") and a missing key both mean "do not apply"
    — an absent key is "not researched", and inventing a threshold for it is
    exactly what `_SCHEDULING_RULES` forbids."""
    raw = rules.get(key)
    # `isinstance(True, int)` is True, so the bool guard is load-bearing: an
    # extracted `{"weekly_ot_hours": true}` would otherwise become a ONE-HOUR
    # weekly threshold and price the whole week at time-and-a-half. Same guard
    # `_multiplier` already carries.
    if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float, Decimal)):
        return None
    try:
        return int(Decimal(str(raw)) * _MINUTES_PER_HOUR)
    except (ArithmeticError, ValueError):
        return None


def _multiplier(rules: Mapping[str, Any], key: str) -> Optional[Decimal]:
    """A premium multiplier from the cited table, or None when the table does
    not state one.

    Same type guard `_threshold_minutes` needs and for the same reason: this
    table's values are merged with catalog-extracted `db_rules`, which can
    carry the `NO_CAP` sentinel or any other non-numeric a reviewer approved.
    `Decimal(str(NO_CAP))` raises `InvalidOperation`, and on the `/week` path
    that would take down the whole schedule board over a pay figure.

    None is NOT a 1.0 fallback and NOT a borrow from the overtime rate: a
    threshold whose rate the table does not state is a rate we do not know,
    and guessing one prices real hours wrong in a number a manager acts on.
    """
    raw = rules.get(key)
    if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float, Decimal, str)):
        return None
    try:
        return Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return None


# ── Pay profiles ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PayProfile:
    """One person's pay as the cost engine needs it."""
    employee_id: str
    rate: Optional[Decimal]      # $/hour when hourly; annual $ when exempt
    classification: str          # HOURLY | EXEMPT
    inferred: bool               # classification came from the magnitude heuristic

    @property
    def priced(self) -> bool:
        return self.rate is not None and self.rate >= 0


def resolve_pay_profile(row: Mapping[str, Any]) -> PayProfile:
    """Build a `PayProfile` from an `employees` row (or any mapping carrying
    `id`/`employee_id`, `pay_rate`, `pay_classification`)."""
    employee_id = str(row.get("employee_id") or row.get("id") or "")
    raw_rate = row.get("pay_rate")
    rate: Optional[Decimal] = None
    if raw_rate is not None:
        try:
            candidate = Decimal(str(raw_rate))
        except (ArithmeticError, ValueError):
            candidate = None
        # A negative rate is corrupt data, not a discount — refuse to price it.
        if candidate is not None and candidate >= 0:
            rate = candidate

    stored = (row.get("pay_classification") or "").strip().lower()
    if stored in (HOURLY, EXEMPT):
        return PayProfile(employee_id, rate, stored, inferred=False)
    if rate is None:
        # Nothing to infer from, and it does not matter: unpriced either way.
        return PayProfile(employee_id, None, HOURLY, inferred=False)
    return PayProfile(
        employee_id, rate,
        EXEMPT if rate >= _ANNUAL_RATE_FLOOR else HOURLY,
        inferred=True,
    )


# ── Results ──────────────────────────────────────────────────────────────


@dataclass
class DayCost:
    day: date
    minutes: int = 0
    straight_minutes: int = 0
    ot_minutes: int = 0
    doubletime_minutes: int = 0
    straight_cost: Decimal = Decimal("0")
    ot_cost: Decimal = Decimal("0")
    doubletime_cost: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return self.straight_cost + self.ot_cost + self.doubletime_cost

    def payload(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "minutes": self.minutes,
            "ot_minutes": self.ot_minutes,
            "doubletime_minutes": self.doubletime_minutes,
            "total": _money(self.total),
        }


@dataclass
class EmployeeCost:
    employee_id: str
    classification: str
    priced: bool
    reason: Optional[str] = None          # 'no_pay_rate' when unpriced
    inferred_classification: bool = False
    minutes: int = 0
    ot_minutes: int = 0
    doubletime_minutes: int = 0
    straight_cost: Decimal = Decimal("0")
    ot_cost: Decimal = Decimal("0")
    doubletime_cost: Decimal = Decimal("0")
    salaried_cost: Decimal = Decimal("0")
    days: list[DayCost] = field(default_factory=list)
    # Hourly rate, kept so `ot_premium` can price the OT hours at base and
    # report only the difference. None for exempt (their pay is not hourly).
    _base_rate: Optional[Decimal] = None

    @property
    def total(self) -> Decimal:
        return self.straight_cost + self.ot_cost + self.doubletime_cost + self.salaried_cost

    @property
    def ot_premium(self) -> Decimal:
        """The avoidable part: what the OT and doubletime hours cost ABOVE
        their own base rate. `ot_cost` is the whole of their pay."""
        base_ot = _hours(self.ot_minutes + self.doubletime_minutes)
        if not base_ot:
            return Decimal("0")
        paid = self.ot_cost + self.doubletime_cost
        at_base = self._base_rate * base_ot if self._base_rate is not None else Decimal("0")
        return paid - at_base

    def payload(self) -> dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "classification": self.classification,
            "inferred_classification": self.inferred_classification,
            "priced": self.priced,
            "reason": self.reason,
            "minutes": self.minutes,
            "ot_minutes": self.ot_minutes,
            "doubletime_minutes": self.doubletime_minutes,
            "straight_cost": _money(self.straight_cost),
            "ot_cost": _money(self.ot_cost),
            "doubletime_cost": _money(self.doubletime_cost),
            "salaried_cost": _money(self.salaried_cost),
            "ot_premium": _money(self.ot_premium),
            "total": _money(self.total),
            "days": [day.payload() for day in self.days],
        }


@dataclass
class WeekCost:
    week_start: date
    employees: list[EmployeeCost] = field(default_factory=list)
    by_day: dict[str, Decimal] = field(default_factory=dict)
    hourly_total: Decimal = Decimal("0")
    salaried_total: Decimal = Decimal("0")
    open_seat_total: Decimal = Decimal("0")
    ot_premium: Decimal = Decimal("0")
    ot_minutes: int = 0
    unpriced_employee_ids: list[str] = field(default_factory=list)
    unpriced_open_seats: int = 0
    #ISO days on which somebody worked whose pay could not be priced. `by_day`
    # is zero-filled across the week, so without this a day staffed entirely by
    # people with no rate on file is indistinguishable from a day off — and
    # "$0" next to a fully-staffed Tuesday reads as "Tuesday is free".
    unpriced_days: list[str] = field(default_factory=list)
    # The week hit the assignment read cap, so this total covers only part of
    # it. Never let a partial figure render as a complete one.
    truncated: bool = False
    basis: dict[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> Decimal:
        return self.hourly_total + self.salaried_total + self.open_seat_total

    def employee_total(self, employee_id: str, *, absent: Optional[Decimal] = None) -> Optional[Decimal]:
        """This person's cost in this scenario.

        `None` means UNPRICED (no pay rate on file). Someone who simply has no
        shifts here is a different thing — they cost nothing — so the caller
        passes `absent=Decimal(0)` when it knows the person is priced and just
        not scheduled. Collapsing the two is how an unassignment rendered as
        "$620 → —, no pay rate on file" instead of as a $620 saving.
        """
        for item in self.employees:
            if item.employee_id == employee_id:
                return item.total if item.priced else None
        return absent

    def payload(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat(),
            "total": _money(self.total),
            "hourly_total": _money(self.hourly_total),
            "salaried_total": _money(self.salaried_total),
            "open_seat_total": _money(self.open_seat_total),
            "ot_premium": _money(self.ot_premium),
            "ot_minutes": self.ot_minutes,
            "by_day": {day: _money(value) for day, value in sorted(self.by_day.items())},
            "employees": [item.payload() for item in self.employees],
            "unpriced_employee_ids": list(self.unpriced_employee_ids),
            "unpriced_employee_count": len(self.unpriced_employee_ids),
            "unpriced_open_seats": self.unpriced_open_seats,
            "unpriced_days": sorted(self.unpriced_days),
            "truncated": self.truncated,
            "basis": dict(self.basis),
        }


# ── The math ─────────────────────────────────────────────────────────────


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def _split_day(
    day_minutes: int, *, daily_ot: Optional[int], daily_dt: Optional[int],
) -> tuple[int, int, int]:
    """(straight, daily overtime, doubletime) minutes for ONE day, before the
    weekly rule. No pyramiding: a minute lands in exactly one bucket."""
    doubletime = max(0, day_minutes - daily_dt) if daily_dt is not None else 0
    if daily_ot is None:
        return day_minutes - doubletime, 0, doubletime
    ceiling = daily_dt if daily_dt is not None else day_minutes
    overtime = max(0, min(day_minutes, ceiling) - daily_ot)
    return day_minutes - overtime - doubletime, overtime, doubletime


def _allocate(total: Decimal, weights: Sequence[int]) -> list[Decimal]:
    """Split `total` across `weights`, largest-remainder, so the parts sum to
    the whole exactly — a salaried week must not gain or lose a cent to
    rounding when it is spread over its days."""
    quantized = total.quantize(_CENTS)
    weight_sum = sum(weights)
    if weight_sum <= 0 or not weights:
        return [Decimal("0") for _ in weights]
    cents = int(quantized * 100)
    raw = [cents * weight / weight_sum for weight in weights]
    parts = [int(value) for value in raw]
    remainder = cents - sum(parts)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - parts[i]), i))
    for index in order[:remainder]:
        parts[index] += 1
    return [Decimal(part) / 100 for part in parts]


def cost_week(
    assignments: Sequence[Mapping[str, Any]],
    pay: Mapping[str, PayProfile],
    rules: Mapping[str, Any],
    *,
    week_start: date,
    open_seats: Sequence[Mapping[str, Any]] = (),
    job_rates: Optional[Mapping[str, Optional[Decimal]]] = None,
) -> WeekCost:
    """Cost one location-week.

    `assignments` are `{employee_id, starts_at, worked_minutes}` rows — the
    shape `planning_inputs` and `schedule_review._week_bucket` already pass
    around. `rules` is a `schedule_compliance.rules_for_state()` dict.
    `open_seats` are `_load_vacant_demand` rows (`job_id`, `worked_minutes`,
    `open`), priced from `job_rates`.

    The caller decides which week the rows belong to; nothing is filtered
    here, so the same function costs a proposed week and an existing one.
    """
    job_rates = job_rates or {}
    daily_ot = _threshold_minutes(rules, "daily_ot_hours")
    daily_dt = _threshold_minutes(rules, "daily_doubletime_hours")
    weekly_ot = _threshold_minutes(rules, "weekly_ot_hours")
    ot_multiplier = _multiplier(rules, "ot_multiplier")
    dt_multiplier = _multiplier(rules, "doubletime_multiplier")

    # A threshold is only usable with the rate that goes with it. A state whose
    # rules state an overtime hour but not its premium (possible once
    # catalog-extracted `db_rules` merge in) gets no overtime split at all,
    # rather than one priced at an invented rate; same for doubletime, which
    # must never silently borrow the 1.5x overtime multiplier.
    if ot_multiplier is None:
        daily_ot = weekly_ot = None
        ot_multiplier = Decimal("1")
    if dt_multiplier is None:
        daily_dt = None
        dt_multiplier = Decimal("1")

    result = WeekCost(week_start=week_start)
    result.basis = {
        "daily_ot_hours": rules.get("daily_ot_hours") if daily_ot is not None else None,
        "daily_doubletime_hours": rules.get("daily_doubletime_hours") if daily_dt is not None else None,
        "weekly_ot_hours": rules.get("weekly_ot_hours") if weekly_ot is not None else None,
        "ot_multiplier": float(ot_multiplier),
        "doubletime_multiplier": float(dt_multiplier),
        "overtime_citation": (rules.get("citations") or {}).get("overtime_rate"),
        "as_scheduled": True,
    }
    # Zero-filled so a day off and a day nobody could be priced on are not the
    # same absent key; `unpriced_days` is what tells them apart.
    for offset in range(7):
        result.by_day[(week_start + timedelta(days=offset)).isoformat()] = Decimal("0")
    unpriced_days: set[str] = set()

    by_employee: dict[str, dict[date, int]] = {}
    for row in assignments:
        employee_id = str(row.get("employee_id") or "")
        day = _as_date(row.get("starts_at"))
        if not employee_id or day is None:
            continue
        minutes = int(row.get("worked_minutes") or 0)
        if minutes <= 0:
            continue
        by_employee.setdefault(employee_id, {})
        by_employee[employee_id][day] = by_employee[employee_id].get(day, 0) + minutes

    for employee_id in sorted(by_employee):
        days = by_employee[employee_id]
        profile = pay.get(employee_id) or PayProfile(employee_id, None, HOURLY, False)
        entry = EmployeeCost(
            employee_id=employee_id,
            classification=profile.classification,
            priced=profile.priced,
            reason=None if profile.priced else "no_pay_rate",
            inferred_classification=profile.inferred,
            minutes=sum(days.values()),
            _base_rate=profile.rate if profile.classification == HOURLY else None,
        )

        if profile.classification == EXEMPT and not profile.priced:
            # Exempt with no rate on file: unpriced AND still exempt. Falling
            # through to the hourly loop would mint overtime minutes for
            # someone statutorily incapable of accruing them, and those land in
            # `ot_minutes`, which Huume and the HR Pilot both report.
            unpriced_days.update(day.isoformat() for day in days)
            for day in sorted(days):
                entry.days.append(DayCost(
                    day=day, minutes=days[day], straight_minutes=days[day],
                ))
            result.unpriced_employee_ids.append(employee_id)
            result.employees.append(entry)
            continue
        if profile.classification == EXEMPT and profile.priced:
            # Salary does not move with hours. Spread the weekly share over the
            # days worked so the board's day columns add up, but keep it out of
            # `hourly_total` — mixing it in would make the marginal cost of one
            # more shift look wrong, which is the number a scheduler acts on.
            ordered = sorted(days)
            weekly = (profile.rate or Decimal("0")) / _WEEKS_PER_YEAR
            shares = _allocate(weekly, [days[day] for day in ordered])
            entry.salaried_cost = sum(shares, Decimal("0"))
            for day, share in zip(ordered, shares):
                cost = DayCost(day=day, minutes=days[day], straight_minutes=days[day])
                cost.straight_cost = share
                entry.days.append(cost)
                result.by_day[day.isoformat()] = result.by_day.get(day.isoformat(), Decimal("0")) + share
            result.salaried_total += entry.salaried_cost
            result.employees.append(entry)
            continue

        weekly_straight = 0
        for day in sorted(days):
            minutes = days[day]
            straight, overtime, doubletime = _split_day(
                minutes, daily_ot=daily_ot, daily_dt=daily_dt,
            )
            if weekly_ot is not None:
                headroom = max(0, weekly_ot - weekly_straight)
                kept = min(straight, headroom)
                overtime += straight - kept
                straight = kept
            weekly_straight += straight

            cost = DayCost(
                day=day, minutes=minutes, straight_minutes=straight,
                ot_minutes=overtime, doubletime_minutes=doubletime,
            )
            if profile.priced:
                rate = profile.rate or Decimal("0")
                cost.straight_cost = _hours(straight) * rate
                cost.ot_cost = _hours(overtime) * rate * ot_multiplier
                cost.doubletime_cost = _hours(doubletime) * rate * dt_multiplier
                result.by_day[day.isoformat()] = (
                    result.by_day.get(day.isoformat(), Decimal("0")) + cost.total
                )
            if not profile.priced:
                unpriced_days.add(day.isoformat())
            entry.days.append(cost)
            entry.straight_cost += cost.straight_cost
            entry.ot_cost += cost.ot_cost
            entry.doubletime_cost += cost.doubletime_cost
            entry.ot_minutes += overtime
            entry.doubletime_minutes += doubletime

        if profile.priced:
            result.hourly_total += entry.total
            result.ot_premium += entry.ot_premium
        else:
            result.unpriced_employee_ids.append(employee_id)
        result.ot_minutes += entry.ot_minutes + entry.doubletime_minutes
        result.employees.append(entry)

    for seat in open_seats:
        open_count = int(seat.get("open") or 0)
        minutes = int(seat.get("worked_minutes") or 0)
        if open_count <= 0 or minutes <= 0:
            continue
        job_id = seat.get("job_id")
        rate = job_rates.get(str(job_id)) if job_id else None
        if rate is None:
            result.unpriced_open_seats += open_count
            continue
        # No person, so no position in anyone's week: an open seat is priced at
        # straight time. It becomes OT-aware the moment it is actually filled.
        cost = _hours(minutes) * Decimal(str(rate)) * open_count
        result.open_seat_total += cost
        day = _as_date(seat.get("starts_at"))
        if day is not None:
            result.by_day[day.isoformat()] = result.by_day.get(day.isoformat(), Decimal("0")) + cost

    result.unpriced_days = sorted(unpriced_days)
    return result
