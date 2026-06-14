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
    staff_id: Optional[str] = None,
) -> list[dict]:
    """Expand availability windows into concrete open slots for one booking type.

    - `availability`: rows with keys weekday(int 0=Mon), start_time(time),
      end_time(time), booking_type_id(str|None), staff_id(str|None). NULL type =
      applies to all types; NULL staff = a site-wide window any staff can use.
    - `btype`: dict with id, duration_minutes, price_cents, pricing_mode, and
      optional buffer_minutes (a gap enforced on both sides of each booking).
    - `bookings`: existing (start_utc, end_utc) aware ranges to subtract — pass
      only the relevant staff's bookings when generating for a concrete staff.
    - `staff_id`: when set, only windows for that staff (or NULL/site-wide) are
      used; when None (legacy / unstaffed), only NULL-staff windows are used.
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
    buf = timedelta(minutes=int(btype.get("buffer_minutes") or 0))

    # Windows that apply to this type (its own + site-wide NULL windows) and to
    # this staff (their own + site-wide NULL-staff windows).
    sid = str(staff_id) if staff_id is not None else None
    windows = [
        w for w in availability
        if w.get("booking_type_id") in (None, bt_id)
        and (w.get("staff_id") in (None, sid))
    ]
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
                # Buffer enforces a gap on both sides of each existing booking.
                if any(s_utc < be + buf and bs < e_utc + buf for bs, be in busy):
                    continue  # overlaps an existing booking (or its buffer)
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


def merge_any_staff_slots(per_staff: Sequence[tuple]) -> list[dict]:
    """Union per-staff slot lists for an "any available" booking.

    `per_staff`: [(staff_id, [slot dicts]), …]. A slot time appears once with an
    `available_staff_ids` list of the staff free then (so the booking step can
    assign a concrete one), keeping the lowest price among them. Sorted by start.
    """
    by_start: dict[str, dict] = {}
    for staff_id, slots in per_staff:
        for s in slots:
            key = s["start"]
            m = by_start.get(key)
            if m is None:
                m = dict(s)
                m["available_staff_ids"] = []
                by_start[key] = m
            m["available_staff_ids"].append(str(staff_id))
            sp = s.get("price_cents")
            if sp is not None and (m.get("price_cents") is None or sp < m["price_cents"]):
                m["price_cents"] = sp
    return [by_start[k] for k in sorted(by_start)]

