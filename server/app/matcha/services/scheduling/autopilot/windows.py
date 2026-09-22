"""Operating-window normalization and 30-minute grid helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from ..location_profile import parse_clock
from .policy import POLICY_MAX_WINDOW_MINUTES, POLICY_SLOT_MINUTES


def sunday_weekday(day: date) -> int:
    return (day.weekday() + 1) % 7


def _floor_grid(value: datetime) -> datetime:
    minute = value.minute - value.minute % POLICY_SLOT_MINUTES
    return value.replace(minute=minute, second=0, microsecond=0)


def _ceil_grid(value: datetime) -> datetime:
    floor = _floor_grid(value)
    return floor if floor == value else floor + timedelta(minutes=POLICY_SLOT_MINUTES)


@dataclass(frozen=True)
class DayWindow:
    day: date
    weekday: int
    open: str | None
    close: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    slot_count: int
    overnight: bool
    closed: bool
    note: str | None = None

    def to_dict(self) -> dict:
        return {
            "date": self.day.isoformat(), "weekday": self.weekday,
            "open": self.open, "close": self.close, "closed": self.closed,
            "overnight": self.overnight, "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "slot_count": self.slot_count,
        }


def day_window(day: date, profile: dict) -> DayWindow:
    weekday = sunday_weekday(day)
    value = (profile.get("operating_hours") or {}).get(str(weekday))
    if not isinstance(value, dict):
        return DayWindow(day, weekday, None, None, None, None, 0, False, True)
    opens, closes = parse_clock(value.get("open")), parse_clock(value.get("close"))
    overnight = closes <= opens
    start = datetime.combine(day, opens, tzinfo=timezone.utc) - timedelta(
        minutes=int(profile.get("open_buffer_minutes") or 0),
    )
    end_day = day + timedelta(days=1 if overnight else 0)
    end = datetime.combine(end_day, closes, tzinfo=timezone.utc) + timedelta(
        minutes=int(profile.get("close_buffer_minutes") or 0),
    )
    start, end = _floor_grid(start), _ceil_grid(end)
    note = None
    if (end - start).total_seconds() / 60 > POLICY_MAX_WINDOW_MINUTES:
        end = start + timedelta(minutes=POLICY_MAX_WINDOW_MINUTES)
        note = "operating window was capped at 32 hours"
    slots = max(0, int((end - start).total_seconds() // (POLICY_SLOT_MINUTES * 60)))
    return DayWindow(
        day, weekday, opens.strftime("%H:%M"), closes.strftime("%H:%M"),
        start, end, slots, overnight, False, note,
    )


def slot_start(window: DayWindow, index: int) -> datetime:
    assert window.starts_at is not None
    return window.starts_at + timedelta(minutes=POLICY_SLOT_MINUTES * index)


def slot_index_from_midnight(moment: datetime, day: date) -> int:
    midnight = datetime.combine(day, time.min, tzinfo=moment.tzinfo or timezone.utc)
    return int((moment - midnight).total_seconds() // (POLICY_SLOT_MINUTES * 60))


def compress_runs(values: list[int], window: DayWindow) -> list[dict]:
    if not values:
        return []
    runs: list[dict] = []
    start = 0
    for index in range(1, len(values) + 1):
        if index < len(values) and values[index] == values[start]:
            continue
        if values[start] > 0:
            runs.append({
                "start": slot_start(window, start).strftime("%H:%M"),
                "end": slot_start(window, index).strftime("%H:%M"),
                "headcount": values[start],
            })
        start = index
    return runs
