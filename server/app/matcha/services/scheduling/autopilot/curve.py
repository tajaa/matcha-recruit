"""Turn labor-hour targets into deterministic per-slot staffing curves."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time
from decimal import ROUND_FLOOR, Decimal

from .labor import LaborTarget
from .windows import DayWindow, compress_runs, slot_start, sunday_weekday


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def slot_weights(
    window: DayWindow, *, shape: dict[int, Decimal] | None,
    hourly_profile: Mapping[int, Mapping[int, Decimal]] | None,
) -> tuple[list[Decimal], str]:
    """Normalized per-slot demand weights: POS hourly sales, else the
    published-history shape, else flat.

    `hourly_profile` is a weekday (Sunday=0) -> hour -> share-of-day profile
    learned from PAST sales. A slot looks up its own calendar day's weekday,
    so after-midnight slots of an overnight window read the next day's early
    hours — that is where those sales were booked.
    """
    values: list[Decimal] = []
    source = "flat"
    if hourly_profile:
        for index in range(window.slot_count):
            starts = slot_start(window, index)
            profile = hourly_profile.get(sunday_weekday(starts.date())) or {}
            values.append(_d(profile.get(starts.hour, 0)))
        if sum(values, Decimal(0)) > 0:
            source = "hourly_sales"
    if not values or sum(values, Decimal(0)) <= 0:
        values = []
        if shape:
            midnight = datetime.combine(window.day, time.min, tzinfo=window.starts_at.tzinfo)
            offset = int((window.starts_at - midnight).total_seconds() // 1800)
            values = [_d(shape.get(offset + index, 0)) for index in range(window.slot_count)]
            if sum(values, Decimal(0)) > 0:
                source = "history"
        if not values or sum(values, Decimal(0)) <= 0:
            values = [Decimal(1)] * window.slot_count
            source = "flat"
    total = sum(values, Decimal(0))
    return [(value / total).quantize(Decimal("0.000001")) for value in values], source


def largest_remainder(raw: list[Decimal | float], total: int) -> list[int]:
    values = [_d(v) for v in raw]
    floors = [int(v.to_integral_value(rounding=ROUND_FLOOR)) for v in values]
    remaining = total - sum(floors)
    order = sorted(range(len(values)), key=lambda i: (-(values[i] - floors[i]), i))
    for index in order[:max(0, remaining)]:
        floors[index] += 1
    return floors


@dataclass(frozen=True)
class StaffingCurve:
    window: DayWindow
    staff: list[int]
    leader: list[int]
    shape_source: str
    planned_hours: Decimal
    notes: tuple[str, ...]

    def runs(self) -> list[dict]:
        return compress_runs([a + b for a, b in zip(self.staff, self.leader)], self.window)


def _run_labels(window: DayWindow, indexes: Sequence[int]) -> str:
    runs: list[tuple[int, int]] = []
    for index in indexes:
        if runs and runs[-1][1] == index:
            runs[-1] = (runs[-1][0], index + 1)
        else:
            runs.append((index, index + 1))
    return ", ".join(
        f"{slot_start(window, a).strftime('%H:%M')}–{slot_start(window, b).strftime('%H:%M')}"
        for a, b in runs
    )


def build_curve(
    window: DayWindow, target: LaborTarget, *, min_floor: int, leader_seat: bool,
    shape: dict[int, Decimal] | None,
    hourly_profile: Mapping[int, Mapping[int, Decimal]] | None,
    max_by_slot: Sequence[int],
) -> StaffingCurve:
    leader = [1 if leader_seat else 0] * window.slot_count
    weights, source = slot_weights(window, shape=shape, hourly_profile=hourly_profile)
    floor_slots = max(0, min_floor) * window.slot_count
    leader_slots = sum(leader)
    total_slots = max(floor_slots + leader_slots, int(target.hours * 2))
    extra = max(0, total_slots - floor_slots - leader_slots)
    raw = [Decimal(max(0, min_floor)) + Decimal(extra) * weight for weight in weights]
    staff = largest_remainder(raw, floor_slots + extra)
    notes: list[str] = []
    clipped: list[int] = []
    for index in range(len(staff)):
        available = max_by_slot[index] if index < len(max_by_slot) else 0
        allowed = max(0, available - leader[index])
        if staff[index] > allowed:
            staff[index] = allowed
            clipped.append(index)
    if clipped:
        notes.append(f"staffing curve was clipped to the staff available {_run_labels(window, clipped)}")
    planned = Decimal(sum(staff) + sum(leader)) / 2
    return StaffingCurve(window, staff, leader, source, planned, tuple(notes))
