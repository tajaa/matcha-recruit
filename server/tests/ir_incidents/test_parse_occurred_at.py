"""Pure-logic tests for the IR occurred_at free-text parser.

No network / no DB — only _parse_occurred_at and its relative-date helpers.
The parser backs every intake path (authed create, public /report + /intake,
voice prefill), where "yesterday around 3pm" is the literal UI placeholder —
dateutil alone has no relative-date support and silently recorded TODAY 3pm.
"""

import sys
from types import ModuleType

# Stub google.genai before any app imports (mirrors test_ir_incidents.py).
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

from datetime import datetime, timedelta, timezone

from app.matcha.routes.ir_incidents._shared import (
    _clamp_future_occurred_at,
    _parse_occurred_at,
    _relative_day_match,
)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _assert_about_now(dt, tolerance_seconds=120):
    assert abs((dt - _now()).total_seconds()) < tolerance_seconds


# ============================================================
# Relative-day terms (the bug: dateutil fuzzy drops "yesterday")
# ============================================================

def test_yesterday_around_3pm_lands_on_yesterday():
    parsed = _parse_occurred_at("yesterday around 3pm")
    assert parsed.date() == (_now() - timedelta(days=1)).date()
    assert parsed.hour == 15


def test_yesterday_alone_defaults_to_noon():
    parsed = _parse_occurred_at("yesterday")
    assert parsed.date() == (_now() - timedelta(days=1)).date()
    assert parsed.hour == 12


def test_day_before_yesterday_not_shadowed():
    parsed = _parse_occurred_at("day before yesterday at 9am")
    assert parsed.date() == (_now() - timedelta(days=2)).date()
    assert parsed.hour == 9


def test_last_night_gets_evening_default():
    parsed = _parse_occurred_at("last night")
    assert parsed.date() == (_now() - timedelta(days=1)).date()
    assert parsed.hour == 21


def test_n_days_ago():
    parsed = _parse_occurred_at("2 days ago around 10am")
    assert parsed.date() == (_now() - timedelta(days=2)).date()
    assert parsed.hour == 10


def test_today_at_9am():
    parsed = _parse_occurred_at("today at 9am")
    assert parsed.date() == _now().date()
    assert parsed.hour == 9


def test_this_morning():
    parsed = _parse_occurred_at("this morning")
    assert parsed.date() == _now().date()
    assert parsed.hour == 12  # bare day-part defaults to noon


def test_relative_match_helper_prefers_days_ago():
    offset, default_hour, remainder = _relative_day_match("3 days ago at noon")
    assert offset == -3 and default_hour == 12
    assert "ago" not in remainder and "noon" in remainder


# ============================================================
# Absolute dates (pre-existing behavior preserved)
# ============================================================

def test_absolute_date_with_time():
    parsed = _parse_occurred_at("May 1 at 4pm")
    assert parsed.month == 5 and parsed.day == 1 and parsed.hour == 16
    # Current-year default must never land in the future (year rolls back).
    assert parsed <= _now() + timedelta(hours=26)


def test_absolute_date_with_explicit_year():
    parsed = _parse_occurred_at("May 1 2025 4pm")
    assert parsed == datetime(2025, 5, 1, 16, 0)


# ============================================================
# Future clamp
# ============================================================

def test_yearless_future_date_rolls_back_a_year():
    # A month/day later in the year than today: dateutil defaults to the
    # current year (future) — the clamp retries with year-1.
    probe = _now() + timedelta(days=90)
    parsed = _parse_occurred_at(probe.strftime("%B %d"))  # e.g. "October 03"
    assert parsed <= _now() + timedelta(hours=26)
    assert parsed.year == probe.year - 1
    assert parsed.month == probe.month and parsed.day == probe.day


def test_explicit_future_year_falls_back_to_now():
    parsed = _parse_occurred_at("May 1 2099 4pm")
    _assert_about_now(parsed)


def test_clamp_passes_near_past_dates_through():
    dt = _now() - timedelta(days=3)
    assert _clamp_future_occurred_at(dt, "whatever") == dt


def test_clamp_feb29_rollback_does_not_crash():
    # year-1 of a Feb 29 is invalid — helper falls back to -365 days.
    future_leap = datetime(2028, 2, 29, 10, 0)
    clamped = _clamp_future_occurred_at(future_leap, "Feb 29")
    assert clamped <= _now() + timedelta(hours=26)


# ============================================================
# Fallbacks + passthrough (never-raises contract)
# ============================================================

def test_garbage_falls_back_to_now():
    _assert_about_now(_parse_occurred_at("no date here at all zzz"))


def test_empty_string_falls_back_to_now():
    _assert_about_now(_parse_occurred_at(""))


def test_none_falls_back_to_now():
    _assert_about_now(_parse_occurred_at(None))


def test_datetime_passthrough_naive():
    dt = datetime(2026, 3, 4, 8, 30)
    assert _parse_occurred_at(dt) == dt


def test_datetime_tz_aware_converted_to_naive_utc():
    dt = datetime(2026, 3, 4, 8, 30, tzinfo=timezone(timedelta(hours=-5)))
    assert _parse_occurred_at(dt) == datetime(2026, 3, 4, 13, 30)
