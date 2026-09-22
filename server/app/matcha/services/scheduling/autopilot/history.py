"""Learn schedule shape, job mix, and sales per labor-hour from published weeks."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from statistics import median

from .policy import (
    POLICY_MIN_HISTORY_WEEKS,
    POLICY_MIN_SPLH_OBSERVATIONS,
    POLICY_SLOT_MINUTES,
)
from .windows import slot_index_from_midnight, sunday_weekday


@dataclass(frozen=True)
class HistoryModel:
    weeks_observed: int
    dates_by_weekday: dict[int, int]
    shape_by_weekday: dict[int, dict[int, Decimal]]
    hours_by_weekday: dict[int, Decimal]
    job_share_by_weekday: dict[int, dict[str, Decimal]]
    job_share_all: dict[str, Decimal]
    splh_by_weekday: dict[int, Decimal]
    splh_all: Decimal | None

    def present(self) -> bool:
        return self.weeks_observed >= POLICY_MIN_HISTORY_WEEKS

    def shape_for(self, weekday: int) -> dict[int, Decimal] | None:
        return self.shape_by_weekday.get(weekday) if self.dates_by_weekday.get(weekday, 0) >= 3 else None


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def learn_history(
    rows: list[dict], *, sales_by_day: dict[date, Decimal], week_start_weekday: int,
) -> HistoryModel:
    heads: dict[date, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    hours: dict[date, Decimal] = defaultdict(Decimal)
    jobslots: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    weeks: set[date] = set()
    for row in sorted(rows, key=lambda r: (r.get("starts_at"), str(r.get("job_id") or ""))):
        start, end = row.get("starts_at"), row.get("ends_at")
        if not isinstance(start, datetime) or not isinstance(end, datetime) or end <= start:
            continue
        seats = int(row.get("required_staff") or row.get("assigned_count") or 0)
        if seats <= 0:
            continue
        business_day = start.date()
        weeks.add(business_day - timedelta(days=(sunday_weekday(business_day) - week_start_weekday) % 7))
        first = slot_index_from_midnight(start, business_day)
        slot_count = int((end - start).total_seconds() // (POLICY_SLOT_MINUTES * 60))
        for slot in range(first, first + slot_count):
            heads[business_day][slot] += seats
        gross = Decimal(seats) * Decimal(slot_count * POLICY_SLOT_MINUTES) / Decimal(60)
        break_hours = Decimal(seats * int(row.get("break_minutes") or 0)) / Decimal(60)
        hours[business_day] += max(Decimal(0), gross - break_hours)
        if row.get("job_id"):
            jobslots[business_day][str(row["job_id"])] += Decimal(seats * slot_count)

    dates_by_weekday: dict[int, int] = defaultdict(int)
    shapes: dict[int, dict[int, list[Decimal]]] = defaultdict(lambda: defaultdict(list))
    hours_by_weekday_raw: dict[int, list[Decimal]] = defaultdict(list)
    shares_by_weekday: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    all_shares: dict[str, Decimal] = defaultdict(Decimal)
    splh_raw: dict[int, list[Decimal]] = defaultdict(list)
    splh_all_raw: list[Decimal] = []
    for business_day in sorted(heads):
        weekday = sunday_weekday(business_day)
        dates_by_weekday[weekday] += 1
        for slot, count in heads[business_day].items():
            shapes[weekday][slot].append(count)
        hours_by_weekday_raw[weekday].append(hours[business_day])
        for job, count in jobslots[business_day].items():
            shares_by_weekday[weekday][job] += count
            all_shares[job] += count
        if business_day in sales_by_day and hours[business_day] > 0:
            value = _d(sales_by_day[business_day]) / hours[business_day]
            splh_raw[weekday].append(value)
            splh_all_raw.append(value)

    shape_by_weekday = {
        weekday: {
            slot: (sum(values, Decimal(0)) / len(values)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
            for slot, values in sorted(slots.items())
        }
        for weekday, slots in sorted(shapes.items())
    }
    hours_by_weekday = {
        weekday: (sum(values, Decimal(0)) / len(values)).quantize(Decimal("0.01"))
        for weekday, values in hours_by_weekday_raw.items()
    }

    def shares(values: dict[str, Decimal]) -> dict[str, Decimal]:
        total = sum(values.values(), Decimal(0))
        return {job: (value / total).quantize(Decimal("0.0001")) for job, value in sorted(values.items())} if total else {}

    splh_by_weekday = {
        weekday: _d(median(values)).quantize(Decimal("0.01"))
        for weekday, values in splh_raw.items() if len(values) >= POLICY_MIN_SPLH_OBSERVATIONS
    }
    splh_all = (
        _d(median(splh_all_raw)).quantize(Decimal("0.01"))
        if len(splh_all_raw) >= POLICY_MIN_SPLH_OBSERVATIONS else None
    )
    return HistoryModel(
        len(weeks), dict(dates_by_weekday), shape_by_weekday, hours_by_weekday,
        {w: shares(v) for w, v in shares_by_weekday.items()}, shares(all_shares),
        splh_by_weekday, splh_all,
    )
