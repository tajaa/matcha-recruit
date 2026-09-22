"""Turn labor-hour targets into deterministic per-slot staffing curves."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import ROUND_FLOOR, Decimal

from .labor import LaborTarget
from .windows import DayWindow, compress_runs, slot_start


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def slot_weights(
    window: DayWindow, *, shape: dict[int, Decimal] | None,
    hourly_sales: dict | None,
) -> tuple[list[Decimal], str]:
    values: list[Decimal] = []
    source = "flat"
    if hourly_sales:
        for index in range(window.slot_count):
            starts = slot_start(window, index)
            values.append(_d(hourly_sales.get((window.day, starts.hour), 0)))
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


def build_curve(
    window: DayWindow, target: LaborTarget, *, min_floor: int, leader_seat: bool,
    shape: dict[int, Decimal] | None, hourly_sales: dict | None, max_headcount: int,
) -> StaffingCurve:
    leader = [1 if leader_seat else 0] * window.slot_count
    weights, source = slot_weights(window, shape=shape, hourly_sales=hourly_sales)
    floor_slots = max(0, min_floor) * window.slot_count
    leader_slots = sum(leader)
    total_slots = max(floor_slots + leader_slots, int(target.hours * 2))
    extra = max(0, total_slots - floor_slots - leader_slots)
    raw = [Decimal(max(0, min_floor)) + Decimal(extra) * weight for weight in weights]
    staff = largest_remainder(raw, floor_slots + extra)
    notes: list[str] = []
    clipped = False
    for index in range(len(staff)):
        allowed = max(0, max_headcount - leader[index])
        if staff[index] > allowed:
            staff[index] = allowed
            clipped = True
    if clipped:
        notes.append("staffing curve was clipped to the qualified roster size")
    planned = Decimal(sum(staff) + sum(leader)) / 2
    return StaffingCurve(window, staff, leader, source, planned, tuple(notes))
