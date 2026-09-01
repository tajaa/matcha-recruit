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


def _watermark(now, **delta):
    return now + timedelta(**delta)


def test_revocation_kills_a_token_minted_a_fraction_of_a_second_earlier():
    """The whole-second `iat` fallback let a token minted at T=100.2 survive a
    logout at T=100.7, because both floor to 100. `iat_ms` decides exactly."""
    logout_at = datetime(2026, 9, 1, 12, 0, 0, 700_000, tzinfo=timezone.utc)
    minted_at = datetime(2026, 9, 1, 12, 0, 0, 200_000, tzinfo=timezone.utc)
    assert session_tokens.token_predates_watermark(
        int(minted_at.timestamp()),
        session_tokens.issue_stamp_ms(minted_at),
        logout_at,
    ) is True


def test_same_second_relogin_after_logout_is_not_self_revoked():
    logout_at = datetime(2026, 9, 1, 12, 0, 0, 200_000, tzinfo=timezone.utc)
    minted_at = datetime(2026, 9, 1, 12, 0, 0, 900_000, tzinfo=timezone.utc)
    assert session_tokens.token_predates_watermark(
        int(minted_at.timestamp()),
        session_tokens.issue_stamp_ms(minted_at),
        logout_at,
    ) is False


def test_legacy_token_without_iat_ms_falls_back_to_floored_second():
    logout_at = datetime(2026, 9, 1, 12, 0, 0, 700_000, tzinfo=timezone.utc)
    same_second = int(logout_at.timestamp())
    # Legacy tokens keep the lenient whole-second behaviour: a same-second
    # re-login must not 401 itself just because it predates iat_ms.
    assert session_tokens.token_predates_watermark(same_second, None, logout_at) is False
    assert session_tokens.token_predates_watermark(same_second - 1, None, logout_at) is True


def test_no_watermark_never_revokes():
    assert session_tokens.token_predates_watermark(1, 1000, None) is False
