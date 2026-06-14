"""Cappe structured business hours — pure "open now" logic (no DB, unit-tested).

`hours` is a 7-entry-ish list of {day:0-6 (Mon=0), open:'HH:MM', close:'HH:MM',
closed:bool}. This is the test oracle; the published "Open now" badge is computed
client-side from the same hours+timezone (so it's immune to HTML caching), but
the logic mirrors this exactly.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo


def _parse_hm(s) -> time | None:
    try:
        h, m = str(s).split(":")
        return time(int(h), int(m))
    except Exception:
        return None


def _entry_for(hours, day) -> dict | None:
    return next((h for h in hours if int(h.get("day", -1)) == day), None)


def _open_in(entry, now_t: time) -> bool:
    """Open per a single day's entry (overnight close → open from `open` to midnight)."""
    if not entry or entry.get("closed"):
        return False
    o, c = _parse_hm(entry.get("open")), _parse_hm(entry.get("close"))
    if not o or not c:
        return False
    if c > o:
        return o <= now_t < c
    return now_t >= o  # close <= open → spills past midnight; open until 24:00 today


def is_open_now(hours, tz_name, now_utc: datetime) -> bool:
    """True if the business is open at `now_utc`, evaluated in its timezone."""
    if not hours:
        return False
    try:
        local = now_utc.astimezone(ZoneInfo(tz_name or "UTC"))
    except Exception:
        local = now_utc.astimezone(ZoneInfo("UTC"))
    wd = local.weekday()  # Mon=0
    now_t = local.time()

    if _open_in(_entry_for(hours, wd), now_t):
        return True

    # Overnight spillover: yesterday's window may still be running past midnight.
    yest = _entry_for(hours, (wd - 1) % 7)
    if yest and not yest.get("closed"):
        o, c = _parse_hm(yest.get("open")), _parse_hm(yest.get("close"))
        if o and c and c <= o and now_t < c:
            return True
    return False
