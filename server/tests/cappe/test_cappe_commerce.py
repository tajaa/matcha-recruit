"""Cappe commerce/booking pure-function tests — no DB, no app boot.

Covers the money + time math the public intake endpoints rely on, and the
reserved-domain guard applied to every public email field. Run from server/.
"""
import os
from datetime import datetime, timedelta, timezone

# Defensive: some transitive imports read settings at import time.
os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.commerce import booking_times, normalize_to_utc, order_subtotal  # noqa: E402
from app.core.services.email._shared import _is_reserved_test_domain  # noqa: E402


def test_order_subtotal():
    assert order_subtotal([(1000, 2), (500, 1)]) == 2500
    assert order_subtotal([]) == 0
    assert order_subtotal([(999, 3)]) == 2997


def test_normalize_to_utc():
    naive = datetime(2026, 6, 15, 14, 0)
    assert normalize_to_utc(naive).tzinfo == timezone.utc
    aware = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
    assert normalize_to_utc(aware) == aware


def test_booking_times_utc():
    start = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
    bt = booking_times(start, 30, "UTC")
    assert bt["start_utc"] == start
    assert bt["end_utc"] == start + timedelta(minutes=30)
    assert bt["local_start"].hour == 14
    assert bt["spans_midnight"] is False
    assert bt["weekday"] == start.weekday()


def test_booking_times_timezone_conversion():
    # June → America/New_York is EDT (UTC-4): 14:00Z == 10:00 local.
    start = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
    bt = booking_times(start, 60, "America/New_York")
    assert bt["local_start"].hour == 10
    assert bt["local_end"].hour == 11


def test_booking_times_naive_input_assumed_utc():
    bt = booking_times(datetime(2026, 6, 15, 14, 0), 30, "UTC")
    assert bt["start_utc"].tzinfo == timezone.utc
    assert bt["start_utc"].hour == 14


def test_booking_times_spans_midnight():
    bt = booking_times(datetime(2026, 6, 15, 23, 50, tzinfo=timezone.utc), 30, "UTC")
    assert bt["spans_midnight"] is True


def test_booking_times_bad_timezone_falls_back_to_utc():
    bt = booking_times(datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc), 30, "Not/AZone")
    assert bt["local_start"].hour == 14  # UTC fallback, no crash


def test_reserved_domain_guard_on_public_intake():
    # Applied to subscribe/order/booking/form email fields.
    assert _is_reserved_test_domain("buyer@example.com") is True
    assert _is_reserved_test_domain("lead@acme.test") is True
    assert _is_reserved_test_domain("x@y.invalid") is True
    assert _is_reserved_test_domain("buyer@realstore.com") is False
