"""Pure commerce/booking helpers (no DB, no I/O) — unit-testable.

Used by the public intake endpoints so the money + time math is exercised in
isolation from the route/transaction plumbing.
"""
from datetime import datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo


def order_subtotal(line_items: Iterable[tuple[int, int]]) -> int:
    """Sum unit_price_cents * quantity over (price, qty) pairs."""
    return sum(int(price) * int(qty) for price, qty in line_items)


def normalize_to_utc(dt: datetime) -> datetime:
    """Treat a naive datetime as UTC; leave aware datetimes unchanged."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def booking_times(starts_at: datetime, duration_minutes: int, tz_name: str | None) -> dict:
    """Resolve a booking's UTC span and its wall-clock representation in the
    site's timezone. `spans_midnight` flags a window the simple TIME-based
    availability check can't represent."""
    start = normalize_to_utc(starts_at)
    end = start + timedelta(minutes=int(duration_minutes))
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    return {
        "start_utc": start,
        "end_utc": end,
        "local_start": local_start,
        "local_end": local_end,
        "weekday": local_start.weekday(),  # Mon=0 .. Sun=6
        "spans_midnight": local_end.date() != local_start.date(),
    }
