"""Pure-function tests for the public offer sign-flow (/offer/:token).

    cd server && ./venv/bin/python -m pytest tests/huume/test_offer_accept_validation.py -q

Covers the DB-free helpers in routes/employee_lifecycle/offer_letters.py:
token expiry, typed-name signature validation, and the accept/decline
status-transition guard. No DB, no Gemini, no network.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.matcha.routes.employee_lifecycle.offer_letters import (
    _token_expired,
    _validate_signed_name,
    _acceptable_transition,
)


class TestTokenExpired:
    def test_none_expiry_never_expires(self):
        assert _token_expired(None) is False

    def test_future_expiry_not_expired(self):
        future = datetime.now(timezone.utc) + timedelta(days=1)
        assert _token_expired(future) is False

    def test_past_expiry_is_expired(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        assert _token_expired(past) is True

    def test_naive_datetime_treated_as_utc(self):
        # Older rows may have naive timestamps; must not raise a
        # can't-compare-naive-and-aware TypeError.
        past_naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        assert _token_expired(past_naive) is True

    def test_exact_boundary_not_expired(self):
        now = datetime.now(timezone.utc)
        assert _token_expired(now + timedelta(seconds=1), now=now) is False


class TestValidateSignedName:
    def test_strips_whitespace(self):
        assert _validate_signed_name("  Jane Doe  ") == "Jane Doe"

    def test_blank_raises(self):
        with pytest.raises(ValueError):
            _validate_signed_name("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            _validate_signed_name("   ")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            _validate_signed_name(None)

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            _validate_signed_name("x" * 256)

    def test_max_length_ok(self):
        assert _validate_signed_name("x" * 255) == "x" * 255


class TestAcceptableTransition:
    @pytest.mark.parametrize("to", ["accepted", "declined"])
    def test_sent_is_acceptable(self, to):
        assert _acceptable_transition("sent", to=to) is True

    @pytest.mark.parametrize("status", ["draft", "accepted", "rejected", "expired", None])
    @pytest.mark.parametrize("to", ["accepted", "declined"])
    def test_non_sent_is_not_acceptable(self, status, to):
        assert _acceptable_transition(status, to=to) is False
