"""Shared lifetime rules for every user-facing refresh token."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from ...config import get_settings


def access_token_stale(issued_at: Optional[int], *, now: Optional[datetime] = None) -> bool:
    """Reject legacy long-lived access tokens after the configured short TTL."""
    if issued_at is None:
        return True
    try:
        issued = int(issued_at)
    except (TypeError, ValueError):
        return True
    settings = get_settings()
    now_epoch = int((now or datetime.now(timezone.utc)).timestamp())
    # One minute of clock skew is enough for hosts synchronized by NTP.
    return now_epoch - issued > settings.jwt_access_token_expire_minutes * 60 + 60


def refresh_token_times(
    session_started_at: Optional[int] = None,
) -> tuple[datetime, int, datetime]:
    """Return issued-at, original session start, and bounded expiry."""
    settings = get_settings()
    issued_at = datetime.now(timezone.utc)
    started_at = int(session_started_at or issued_at.timestamp())
    rolling_expiry = issued_at + timedelta(days=settings.jwt_refresh_token_expire_days)
    absolute_expiry = datetime.fromtimestamp(started_at, timezone.utc) + timedelta(
        hours=settings.jwt_session_absolute_expire_hours
    )
    return issued_at, started_at, min(rolling_expiry, absolute_expiry)


def refresh_session_expired(
    issued_at: Optional[int],
    session_started_at: Optional[int],
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Return whether a refresh is outside its idle or absolute window.

    Legacy tokens have no ``session_started_at`` claim, so their ``iat`` is
    treated as the original session start and the new limits apply immediately.
    """
    if issued_at is None:
        return True
    try:
        issued = int(issued_at)
        started = int(session_started_at or issued)
    except (TypeError, ValueError):
        return True

    settings = get_settings()
    now_epoch = int((now or datetime.now(timezone.utc)).timestamp())
    if now_epoch - issued > settings.jwt_refresh_idle_expire_minutes * 60:
        return True
    return now_epoch - started > settings.jwt_session_absolute_expire_hours * 3600
