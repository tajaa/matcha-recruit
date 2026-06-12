"""Pure commerce/booking helpers (no DB, no I/O) — unit-testable.

Used by the public intake endpoints so the money + time math is exercised in
isolation from the route/transaction plumbing.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence
from zoneinfo import ZoneInfo


def order_subtotal(line_items: Iterable[tuple[int, int]]) -> int:
    """Sum unit_price_cents * quantity over (price, qty) pairs."""
    return sum(int(price) * int(qty) for price, qty in line_items)


def _minute_multiplier(
    minute_t: time, weekday: int, rules: Sequence[dict]
) -> float:
    """Highest multiplier among rules covering this wall-clock minute, else 1.0.

    A rule matches when its weekday is None (every day) or equals `weekday`, and
    its [start_time, end_time) window contains `minute_t`. Overlapping rules take
    the max so a 2x extended-hours rule always wins over a baseline rule."""
    best = 1.0
    for r in rules:
        rw = r.get("weekday")
        if rw is not None and int(rw) != weekday:
            continue
        if r["start_time"] <= minute_t < r["end_time"]:
            m = float(r["multiplier"])
            if m > best:
                best = m
    return best


def booking_quote_cents(
    base_price_cents: int,
    pricing_mode: str,
    local_start: datetime,
    local_end: datetime,
    rules: Optional[Sequence[dict]] = None,
) -> int:
    """Price a booking.

    - flat   → `base_price_cents` regardless of length (today's behavior).
    - hourly → `base_price_cents` is the base rate per HOUR; each minute of the
      booking is charged at base/60 times the highest matching rate-rule
      multiplier (e.g. after-8pm = 2x). Summed and rounded to whole cents.

    `local_start`/`local_end` are wall-clock in the site timezone (a booking
    can't span midnight, enforced upstream), so weekday is taken from the start.
    """
    base = int(base_price_cents or 0)
    if pricing_mode != "hourly":
        return base
    rules = rules or []
    weekday = local_start.weekday()  # Mon=0..Sun=6
    per_minute = Decimal(base) / Decimal(60)
    total = Decimal(0)
    cursor = local_start
    step = timedelta(minutes=1)
    # Iterate minutes of the booking; bounded (<= 1440) since no midnight span.
    while cursor < local_end:
        mult = _minute_multiplier(cursor.time(), weekday, rules)
        total += per_minute * Decimal(str(mult))
        cursor += step
    return int(total.to_integral_value())


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
