"""Cappe "open now" from structured hours + timezone (pure, no DB).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_hours.py -q
"""
import os
from datetime import datetime, timezone

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.hours import is_open_now  # noqa: E402

# Mon=0 .. Sun=6. A weekday 9–17 schedule, closed weekends.
WEEKDAY_9_5 = [{"day": d, "open": "09:00", "close": "17:00", "closed": d >= 5} for d in range(7)]


def _mon(hour, minute=0):
    # 2026-06-15 is a Monday (UTC).
    return datetime(2026, 6, 15, hour, minute, tzinfo=timezone.utc)


def test_open_mid_window_utc():
    assert is_open_now(WEEKDAY_9_5, "UTC", _mon(12, 0)) is True


def test_closed_before_open_and_after_close():
    assert is_open_now(WEEKDAY_9_5, "UTC", _mon(8, 59)) is False
    assert is_open_now(WEEKDAY_9_5, "UTC", _mon(17, 0)) is False  # close is exclusive


def test_closed_day():
    # 2026-06-20 is a Saturday → closed.
    sat = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    assert is_open_now(WEEKDAY_9_5, "UTC", sat) is False


def test_timezone_conversion():
    # 17:00 UTC = 10:00 in Los Angeles (PDT, UTC-7) → open; same instant is closed in UTC.
    dt = _mon(17, 0)
    assert is_open_now(WEEKDAY_9_5, "America/Los_Angeles", dt) is True
    assert is_open_now(WEEKDAY_9_5, "UTC", dt) is False


def test_overnight_window():
    # A bar open Fri 20:00 → 02:00 (close <= open spills to Saturday).
    bar = [{"day": 4, "open": "20:00", "close": "02:00", "closed": False}]
    fri_11pm = datetime(2026, 6, 19, 23, 0, tzinfo=timezone.utc)   # Friday
    sat_1am = datetime(2026, 6, 20, 1, 0, tzinfo=timezone.utc)     # Saturday, still open
    sat_3am = datetime(2026, 6, 20, 3, 0, tzinfo=timezone.utc)     # closed
    assert is_open_now(bar, "UTC", fri_11pm) is True
    assert is_open_now(bar, "UTC", sat_1am) is True
    assert is_open_now(bar, "UTC", sat_3am) is False


def test_no_hours_is_closed():
    assert is_open_now([], "UTC", _mon(12)) is False
