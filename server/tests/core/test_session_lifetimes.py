from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.services import session_tokens
from app.core.services.session_tokens import SessionLifetimes


def test_default_lifetimes_keep_existing_global_clamps(monkeypatch):
    monkeypatch.setattr(
        session_tokens,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_access_token_expire_minutes=15,
            jwt_refresh_token_expire_days=7,
            jwt_refresh_idle_expire_minutes=60,
            jwt_session_absolute_expire_hours=24,
        ),
    )
    now = datetime(2026, 9, 19, tzinfo=timezone.utc)
    assert not session_tokens.access_token_stale(int((now - timedelta(minutes=15)).timestamp()), now=now)
    assert session_tokens.access_token_stale(int((now - timedelta(minutes=17)).timestamp()), now=now)
    assert not session_tokens.refresh_session_expired(
        int((now - timedelta(minutes=59)).timestamp()),
        int((now - timedelta(hours=23)).timestamp()),
        now=now,
    )
    assert session_tokens.refresh_session_expired(
        int((now - timedelta(minutes=61)).timestamp()),
        int((now - timedelta(hours=23)).timestamp()),
        now=now,
    )


def test_shopper_refresh_allows_29_day_idle_but_rejects_31_days():
    lifetime = SessionLifetimes(
        refresh_idle_minutes=30 * 24 * 60,
        refresh_absolute_minutes=180 * 24 * 60,
    )
    now = datetime(2026, 9, 19, tzinfo=timezone.utc)
    session_start = int((now - timedelta(days=90)).timestamp())
    assert not session_tokens.refresh_session_expired(
        int((now - timedelta(days=29)).timestamp()), session_start, now=now, lifetimes=lifetime
    )
    assert session_tokens.refresh_session_expired(
        int((now - timedelta(days=31)).timestamp()), session_start, now=now, lifetimes=lifetime
    )


def test_shopper_refresh_absolute_limit_still_wins():
    lifetime = SessionLifetimes(
        refresh_idle_minutes=30 * 24 * 60,
        refresh_absolute_minutes=180 * 24 * 60,
    )
    now = datetime(2026, 9, 19, tzinfo=timezone.utc)
    assert session_tokens.refresh_session_expired(
        int((now - timedelta(days=1)).timestamp()),
        int((now - timedelta(days=181)).timestamp()),
        now=now,
        lifetimes=lifetime,
    )
