"""Sym-chat kind registry + config materialization.

A kind fixes three things: what the organizer configures at create time
(`materialize_config`), what a participant's structured stance looks like
(`stance_template`, filled by `extract.py`), and how stances roll up into the
shared shape (`aggregate.py`). Only `schedule` and `decide` exist in the MVP.

Everything here is pure: the route turns a `ValueError` into a 400.
"""
from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

KINDS: dict[str, dict[str, str]] = {
    "schedule": {
        "label": "Find a time",
        "description": "Everyone shares when they're free; the chat settles on a slot that works for all.",
    },
    "decide": {
        "label": "Decide together",
        "description": "Everyone weighs in on the options; the chat settles on one nobody vetoes.",
    },
}

DEFAULT_TIMEZONE = "America/Los_Angeles"
DEFAULT_WINDOW_START = "09:00"
DEFAULT_WINDOW_END = "17:00"
DEFAULT_DURATION_MIN = 30
MIN_DURATION_MIN = 15
MAX_DURATION_MIN = 480
STEP_MIN = 15
MAX_OPTIONS = 20
MAX_OPTION_CHARS = 60


def parse_hhmm(value: Any) -> int | None:
    """'HH:MM' (24h) → minutes since midnight, or None. '24:00' is allowed as
    an end-of-day bound."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    parts = text.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts) or len(parts[1]) != 2:
        return None
    hours, minutes = int(parts[0]), int(parts[1])
    if minutes > 59 or hours > 24 or (hours == 24 and minutes):
        return None
    return hours * 60 + minutes


def fmt_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def clean_option(value: Any) -> str | None:
    """One option name: whitespace-collapsed, capped, non-empty."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())[:MAX_OPTION_CHARS].strip()
    return cleaned or None


def _schedule_config(raw: dict, today: date_cls | None) -> dict:
    tz_name = raw.get("timezone") or DEFAULT_TIMEZONE
    if not isinstance(tz_name, str):
        raise ValueError("timezone must be an IANA zone name")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone: {tz_name}")

    raw_date = raw.get("date")
    if not isinstance(raw_date, str):
        raise ValueError("date is required (YYYY-MM-DD)")
    try:
        day = date_cls.fromisoformat(raw_date.strip())
    except ValueError:
        raise ValueError("date must be YYYY-MM-DD")
    local_today = today or datetime.now(dt_timezone.utc).astimezone(tz).date()
    if day < local_today:
        raise ValueError("date is in the past")

    start = parse_hhmm(raw.get("window_start") or DEFAULT_WINDOW_START)
    end = parse_hhmm(raw.get("window_end") or DEFAULT_WINDOW_END)
    if start is None or end is None:
        raise ValueError("window_start / window_end must be HH:MM")
    if start % STEP_MIN or end % STEP_MIN:
        raise ValueError(f"window bounds must fall on a {STEP_MIN}-minute boundary")

    duration = raw.get("duration_min", DEFAULT_DURATION_MIN)
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise ValueError("duration_min must be a whole number of minutes")
    if not MIN_DURATION_MIN <= duration <= MAX_DURATION_MIN or duration % STEP_MIN:
        raise ValueError(
            f"duration_min must be {MIN_DURATION_MIN}..{MAX_DURATION_MIN} in {STEP_MIN}-minute steps"
        )
    if end - start < duration:
        raise ValueError("the window is shorter than the meeting")

    return {
        "date": day.isoformat(),
        "window_start": fmt_hhmm(start),
        "window_end": fmt_hhmm(end),
        "duration_min": duration,
        "step_min": STEP_MIN,
        "timezone": tz_name,
    }


def _decide_config(raw: dict) -> dict:
    options_raw = raw.get("options") or []
    if not isinstance(options_raw, list):
        raise ValueError("options must be a list of names")
    if len(options_raw) > MAX_OPTIONS:
        raise ValueError(f"at most {MAX_OPTIONS} options")
    options: list[str] = []
    seen: set[str] = set()
    for item in options_raw:
        name = clean_option(item)
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            options.append(name)
    return {"options": options}


def materialize_config(kind: str, raw: dict | None, *, today: date_cls | None = None) -> dict:
    """Organizer input → the stored config. Unknown keys are dropped; invalid
    values raise ValueError with a user-facing message."""
    if kind not in KINDS:
        raise ValueError(f"Unknown sym-chat kind: {kind}")
    raw = raw if isinstance(raw, dict) else {}
    if kind == "schedule":
        return _schedule_config(raw, today)
    return _decide_config(raw)


def stance_template(kind: str) -> dict:
    """An empty stance of the kind's shape."""
    if kind == "schedule":
        return {"available": [], "unavailable": [], "preferred": []}
    if kind == "decide":
        return {"proposals": [], "ok_with": [], "vetoes": [], "top_pick": None}
    raise ValueError(f"Unknown sym-chat kind: {kind}")
