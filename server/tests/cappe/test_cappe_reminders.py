"""Cappe booking-reminder window predicate (pure — no DB).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_reminders.py -q
"""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.reminders import reminder_due  # noqa: E402

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def test_confirmed_within_window_is_due():
    assert reminder_due(NOW + timedelta(hours=5), NOW, "confirmed", None) is True
    assert reminder_due(NOW + timedelta(hours=23), NOW, "confirmed", None) is True


def test_not_due_when_pending_or_cancelled():
    assert reminder_due(NOW + timedelta(hours=5), NOW, "pending", None) is False
    assert reminder_due(NOW + timedelta(hours=5), NOW, "cancelled", None) is False


def test_not_due_when_already_reminded():
    assert reminder_due(NOW + timedelta(hours=5), NOW, "confirmed", NOW - timedelta(hours=1)) is False


def test_not_due_in_the_past():
    assert reminder_due(NOW - timedelta(minutes=1), NOW, "confirmed", None) is False


def test_not_due_beyond_window():
    assert reminder_due(NOW + timedelta(hours=30), NOW, "confirmed", None) is False
    # boundary: exactly window edge is included, just past it is not
    assert reminder_due(NOW + timedelta(hours=24), NOW, "confirmed", None) is True
    assert reminder_due(NOW + timedelta(hours=24, seconds=1), NOW, "confirmed", None) is False
