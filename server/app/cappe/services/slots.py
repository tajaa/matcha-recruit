"""Concrete bookable-slot generation (pure, no DB/I/O — unit-testable).

The public booking widget shouldn't make a visitor *guess* a valid time. Given a
booking type's weekly availability windows, its duration, the already-booked
ranges, and the dynamic rate rules, this expands the next few weeks into a flat
list of discrete, openable slots the widget renders as one-tap chips.

Each slot's `start`/`end` are naive wall-clock strings in the SITE's timezone —
exactly what the booking-intake endpoint expects (it anchors a naive datetime to
the site tz). Price is pre-computed per slot so the widget needs no live quote.
"""
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from .commerce import booking_quote_cents


def _fmt_time(dt: datetime) -> str:
    """4:00 PM (no leading zero, platform-independent)."""
    s = dt.strftime("%I:%M %p")
    return s[1:] if s.startswith("0") else s


def generate_slots(
    availability: Sequence[dict],
    btype: dict,
    bookings: Sequence[tuple[datetime, datetime]],
    tz_name: Optional[str],
    now_utc: datetime,
    rules: Optional[Sequence[dict]] = None,
    days_ahead: int = 21,
    max_slots: int = 60,
) -> list[dict]:
    """Expand availability windows into concrete open slots for one booking type.

    - `availability`: rows with keys weekday(int 0=Mon), start_time(time),
      end_time(time), booking_type_id(str|None). NULL type = applies to all.
    - `btype`: dict with id, duration_minutes, price_cents, pricing_mode.
    - `bookings`: existing (start_utc, end_utc) aware ranges to subtract.
    - Slots are fixed `duration_minutes` windows stepped through each window;
      hourly types still get per-minute rate-rule pricing within the slot.
    """
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    rules = rules or []
    duration = int(btype.get("duration_minutes") or 30)
    base = int(btype.get("price_cents") or 0)
    mode = btype.get("pricing_mode") or "flat"
    bt_id = btype.get("id")
    step = timedelta(minutes=duration)

    # Windows that apply to this type (its own + site-wide NULL windows).
    windows = [w for w in availability if w.get("booking_type_id") in (None, bt_id)]
    if not windows:
        return []

    now_local = now_utc.astimezone(tz)
    busy = [(bs, be) for bs, be in bookings]
    out: list[dict] = []

    for d in range(days_ahead):
        day = (now_local + timedelta(days=d)).date()
        wd = day.weekday()
        day_windows = sorted(
            (w for w in windows if int(w["weekday"]) == wd),
            key=lambda x: x["start_time"],
        )
        for w in day_windows:
            win_start: dt_time = w["start_time"]
            win_end: dt_time = w["end_time"]
            window_end = datetime.combine(day, win_end, tzinfo=tz)
            cursor = datetime.combine(day, win_start, tzinfo=tz)
            while cursor + step <= window_end:
                local_start, local_end = cursor, cursor + step
                cursor += step
                if local_start <= now_local:
                    continue
                s_utc = local_start.astimezone(timezone.utc)
                e_utc = local_end.astimezone(timezone.utc)
                if any(s_utc < be and bs < e_utc for bs, be in busy):
                    continue  # overlaps an existing pending/confirmed booking
                price = booking_quote_cents(base, mode, local_start, local_end, rules)
                out.append({
                    "start": local_start.strftime("%Y-%m-%dT%H:%M:%S"),
                    "end": local_end.strftime("%Y-%m-%dT%H:%M:%S"),
                    "date": day.isoformat(),
                    "day_label": local_start.strftime("%a %b ") + str(day.day),
                    "time_label": _fmt_time(local_start),
                    "price_cents": price,
                })
                if len(out) >= max_slots:
                    return out
    return out
