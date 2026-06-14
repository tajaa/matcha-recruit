"""Cappe staff-aware slot generation + any-available merge + buffer (pure, no DB).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_staff_slots.py -q
"""
import os
from datetime import datetime, time, timezone

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.slots import generate_slots, merge_any_staff_slots  # noqa: E402

NOW = datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc)  # a Monday, 08:00 UTC
BT = {"id": "cut", "duration_minutes": 60, "price_cents": 4000, "pricing_mode": "flat"}
AVAIL = [
    {"weekday": 0, "start_time": time(9, 0), "end_time": time(12, 0), "booking_type_id": None, "staff_id": "maria"},
    {"weekday": 0, "start_time": time(9, 0), "end_time": time(12, 0), "booking_type_id": None, "staff_id": "alex"},
]


def _labels(slots):
    return [s["time_label"] for s in slots]


def test_per_staff_windows_filter():
    # Only Maria's windows when generating for Maria.
    maria = generate_slots(AVAIL, BT, [], "UTC", NOW, days_ahead=1, staff_id="maria")
    assert _labels(maria) == ["9:00 AM", "10:00 AM", "11:00 AM"]


def test_staff_only_blocked_by_own_bookings():
    booked = [(datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc), datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc))]
    # Maria booked 9-10; Alex (no bookings) is unaffected.
    maria = generate_slots(AVAIL, BT, booked, "UTC", NOW, days_ahead=1, staff_id="maria")
    alex = generate_slots(AVAIL, BT, [], "UTC", NOW, days_ahead=1, staff_id="alex")
    assert "9:00 AM" not in _labels(maria) and "10:00 AM" in _labels(maria)
    assert _labels(alex) == ["9:00 AM", "10:00 AM", "11:00 AM"]


def test_buffer_blocks_adjacent_slot():
    bt = {**BT, "buffer_minutes": 15}
    booked = [(datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc), datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc))]
    # 9-10 booked + 15m buffer → 10:00 start needs 10:15, blocked; 11:00 ok.
    maria = generate_slots(AVAIL, bt, booked, "UTC", NOW, days_ahead=1, staff_id="maria")
    assert _labels(maria) == ["11:00 AM"]


def test_legacy_null_staff_uses_only_null_windows():
    # An unstaffed call (staff_id=None) ignores staff-scoped windows.
    out = generate_slots(AVAIL, BT, [], "UTC", NOW, days_ahead=1, staff_id=None)
    assert out == []
    null_av = [{"weekday": 0, "start_time": time(9, 0), "end_time": time(11, 0), "booking_type_id": None, "staff_id": None}]
    out2 = generate_slots(null_av, BT, [], "UTC", NOW, days_ahead=1, staff_id=None)
    assert _labels(out2) == ["9:00 AM", "10:00 AM"]


def test_merge_any_staff_unions_and_tracks_who():
    booked = [(datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc), datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc))]
    per = [
        ("maria", generate_slots(AVAIL, BT, booked, "UTC", NOW, days_ahead=1, staff_id="maria")),
        ("alex", generate_slots(AVAIL, BT, [], "UTC", NOW, days_ahead=1, staff_id="alex")),
    ]
    merged = merge_any_staff_slots(per)
    by_label = {m["time_label"]: m["available_staff_ids"] for m in merged}
    assert by_label["9:00 AM"] == ["alex"]            # Maria busy
    assert sorted(by_label["10:00 AM"]) == ["alex", "maria"]
    # one entry per time, sorted by start
    assert [m["time_label"] for m in merged] == ["9:00 AM", "10:00 AM", "11:00 AM"]


def test_merge_keeps_lowest_price():
    per = [
        ("a", [{"start": "2026-06-15T09:00:00", "time_label": "9:00 AM", "price_cents": 5000}]),
        ("b", [{"start": "2026-06-15T09:00:00", "time_label": "9:00 AM", "price_cents": 4000}]),
    ]
    merged = merge_any_staff_slots(per)
    assert len(merged) == 1 and merged[0]["price_cents"] == 4000
    assert sorted(merged[0]["available_staff_ids"]) == ["a", "b"]
