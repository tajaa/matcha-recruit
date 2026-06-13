"""Pure unit tests for concrete booking-slot generation (no DB)."""
from datetime import datetime, time, timezone

from app.cappe.services.slots import generate_slots

# 2026-06-12 is a Friday; 06-13 Saturday, 06-20 next Saturday.
NOW = datetime(2026, 6, 12, 0, 0, tzinfo=timezone.utc)
SAT_4_TO_10 = [{"weekday": 5, "start_time": time(16), "end_time": time(22), "booking_type_id": None}]


def _bt(**kw):
    return {"id": "t1", "duration_minutes": 120, "price_cents": 40000, "pricing_mode": "hourly", **kw}


def test_expands_window_into_fixed_duration_slots():
    slots = generate_slots(SAT_4_TO_10, _bt(), [], "America/Los_Angeles", NOW, [], days_ahead=10)
    # 4-10pm in 2hr steps = 4pm, 6pm, 8pm — two Saturdays in 10 days.
    assert [s["time_label"] for s in slots] == ["4:00 PM", "6:00 PM", "8:00 PM"] * 2


def test_slot_price_applies_rate_rules():
    rules = [{"weekday": None, "start_time": time(20), "end_time": time(23), "multiplier": 2.0}]
    slots = generate_slots(SAT_4_TO_10, _bt(), [], "America/Los_Angeles", NOW, rules, days_ahead=8)
    by_time = {s["time_label"]: s["price_cents"] for s in slots}
    assert by_time["4:00 PM"] == 80000   # 2hr * $400/hr
    assert by_time["8:00 PM"] == 160000  # 2hr * $400/hr * 2x after 8pm


def test_overlapping_booking_is_subtracted():
    # Book 4-6pm PT on the first Saturday (06-13 → 23:00-01:00 UTC).
    busy = [(datetime(2026, 6, 13, 23, tzinfo=timezone.utc), datetime(2026, 6, 14, 1, tzinfo=timezone.utc))]
    slots = generate_slots(SAT_4_TO_10, _bt(), busy, "America/Los_Angeles", NOW, [], days_ahead=8)
    first_sat = [s for s in slots if s["date"] == "2026-06-13"]
    assert [s["time_label"] for s in first_sat] == ["6:00 PM", "8:00 PM"]  # 4pm gone


def test_no_availability_returns_empty():
    assert generate_slots([], _bt(), [], "America/Los_Angeles", NOW, [], days_ahead=10) == []


def test_flat_type_priced_per_slot_at_base():
    bt = _bt(pricing_mode="flat", duration_minutes=60, price_cents=9000)
    slots = generate_slots(SAT_4_TO_10, bt, [], "America/Los_Angeles", NOW, [], days_ahead=8)
    assert all(s["price_cents"] == 9000 for s in slots)


def test_site_wide_window_applies_when_type_specific_absent():
    # NULL booking_type_id window applies to any type id.
    slots = generate_slots(SAT_4_TO_10, _bt(id="other"), [], "America/Los_Angeles", NOW, [], days_ahead=8)
    assert len(slots) > 0


def test_type_scoped_window_excludes_other_types():
    avail = [{"weekday": 5, "start_time": time(16), "end_time": time(22), "booking_type_id": "t1"}]
    assert generate_slots(avail, _bt(id="t2"), [], "America/Los_Angeles", NOW, [], days_ahead=8) == []
