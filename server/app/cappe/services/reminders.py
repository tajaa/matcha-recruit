"""Cappe booking-reminder window logic (pure — unit-tested without a DB)."""
from datetime import datetime, timedelta


def reminder_due(
    starts_at: datetime, now: datetime, status: str,
    reminder_sent_at: datetime | None, window_hours: int = 24,
) -> bool:
    """True when a booking should get its single pre-start reminder: a confirmed,
    not-yet-reminded booking whose start is in the future but within the window.
    Mirrors the worker's SQL filter (used as a defensive in-loop guard)."""
    if status != "confirmed" or reminder_sent_at is not None:
        return False
    return now < starts_at <= now + timedelta(hours=window_hours)
