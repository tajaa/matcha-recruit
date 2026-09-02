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


def issue_stamp_ms(issued_at: datetime) -> int:
    """Millisecond issue stamp minted alongside the whole-second ``iat`` claim."""
    return int(issued_at.timestamp() * 1000)


def token_predates_watermark(
    issued_at: Optional[int],
    issued_at_ms: Optional[int],
    tokens_valid_after,
) -> bool:
    """Whether a token was minted before an account's revocation watermark.

    ``iat`` is whole-second by JWT convention, so comparing it against a
    microsecond ``NOW()`` watermark rejects every token minted in the same
    second as the logout — including a legitimate immediate re-login. Flooring
    the watermark fixes that but leaves a one-second window in which a token
    minted just *before* the logout survives it, which is exactly the token
    revocation exists to kill.

    ``iat_ms`` carries the precision needed to decide both cases exactly. It is
    minted by every helper in this package, so only tokens predating that claim
    fall back to the floored whole-second comparison.
    """
    if tokens_valid_after is None:
        return False
    try:
        watermark = tokens_valid_after.timestamp()
    except AttributeError:
        return False

    if issued_at_ms is not None:
        try:
            return int(issued_at_ms) / 1000.0 < watermark
        except (TypeError, ValueError):
            return False

    if issued_at is None:
        return False
    try:
        return float(issued_at) < int(watermark)
    except (TypeError, ValueError):
        return False
