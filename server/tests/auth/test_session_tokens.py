from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.services import session_tokens


def _settings():
    return SimpleNamespace(
        jwt_access_token_expire_minutes=15,
        jwt_refresh_token_expire_days=7,
        jwt_refresh_idle_expire_minutes=30,
        jwt_session_absolute_expire_hours=12,
    )


def test_access_token_stale_enforces_short_ttl(monkeypatch):
    monkeypatch.setattr(session_tokens, 'get_settings', _settings)
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    assert session_tokens.access_token_stale(int((now - timedelta(minutes=10)).timestamp()), now=now) is False
    assert session_tokens.access_token_stale(int((now - timedelta(minutes=17)).timestamp()), now=now) is True


def test_refresh_session_expires_after_inactivity(monkeypatch):
    monkeypatch.setattr(session_tokens, 'get_settings', _settings)
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    started = int((now - timedelta(hours=2)).timestamp())
    issued = int((now - timedelta(minutes=31)).timestamp())
    assert session_tokens.refresh_session_expired(issued, started, now=now) is True


def test_refresh_rotation_cannot_cross_absolute_boundary(monkeypatch):
    monkeypatch.setattr(session_tokens, 'get_settings', _settings)
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    started = int((now - timedelta(hours=12, seconds=1)).timestamp())
    issued = int((now - timedelta(minutes=1)).timestamp())
    assert session_tokens.refresh_session_expired(issued, started, now=now) is True


def test_missing_issued_at_is_rejected(monkeypatch):
    monkeypatch.setattr(session_tokens, 'get_settings', _settings)
    assert session_tokens.access_token_stale(None) is True
    assert session_tokens.refresh_session_expired(None, None) is True
