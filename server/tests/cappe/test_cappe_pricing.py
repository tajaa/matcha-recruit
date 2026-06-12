"""Pure unit tests for the booking pricing engine (no DB)."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.cappe.services.commerce import booking_quote_cents

LA = ZoneInfo("America/Los_Angeles")


def _dt(h, m=0):
    return datetime(2026, 6, 15, h, m, tzinfo=LA)  # 2026-06-15 is a Monday


def test_flat_mode_ignores_time_and_rules():
    rules = [{"weekday": None, "start_time": time(20), "end_time": time(23), "multiplier": 2.0}]
    assert booking_quote_cents(50000, "flat", _dt(16), _dt(22), rules) == 50000


def test_hourly_base_rate_no_rules():
    # 4 hours at $200/hr = $800
    assert booking_quote_cents(20000, "hourly", _dt(16), _dt(20), []) == 80000


def test_hourly_with_extended_window_multiplier():
    # Chef: $200/hr base; 8-10pm at 2x. 4-8pm = 4*200, 8-10pm = 2*400 → $1600.
    rules = [{"weekday": None, "start_time": time(20), "end_time": time(23), "multiplier": 2.0}]
    assert booking_quote_cents(20000, "hourly", _dt(16), _dt(22), rules) == 160000


def test_weekday_scoped_rule_only_applies_on_its_day():
    # Rule is Saturday-only (weekday 5); our booking is Monday → no surcharge.
    rules = [{"weekday": 5, "start_time": time(0), "end_time": time(23, 59), "multiplier": 3.0}]
    assert booking_quote_cents(10000, "hourly", _dt(9), _dt(11), rules) == 20000


def test_overlapping_rules_take_the_max_multiplier():
    rules = [
        {"weekday": None, "start_time": time(18), "end_time": time(23), "multiplier": 1.5},
        {"weekday": None, "start_time": time(20), "end_time": time(23), "multiplier": 2.0},
    ]
    # 6-8pm at 1.5x ($150/hr*... base 100/hr): 2h*1.5*100 = 300; 8-9pm at max(2.0)=2x: 1h*2*100=200 → $500
    assert booking_quote_cents(10000, "hourly", _dt(18), _dt(21), rules) == 50000
