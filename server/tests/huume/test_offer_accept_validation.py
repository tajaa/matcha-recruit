"""Pure-function tests for the public offer sign-flow (/offer/:token).

    cd server && ./venv/bin/python -m pytest tests/huume/test_offer_accept_validation.py -q

Covers the DB-free helpers in routes/employee_lifecycle/offer_letters.py:
token expiry, typed-name signature validation, and the accept/decline
status-transition guard. No DB, no Gemini, no network.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from app.matcha.routes.employee_lifecycle import offer_letters as offer_letters_mod
from app.matcha.routes.employee_lifecycle.offer_letters import (
    _token_expired,
    _validate_signed_name,
    _acceptable_transition,
)


def _conn_ctx(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


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


class TestAcceptAlertOrdering:
    @pytest.mark.asyncio
    async def test_persists_huume_event_before_scheduling_pdf_work(self, monkeypatch):
        company_id = uuid4()
        offer_id = uuid4()
        offer = {
            "id": offer_id,
            "company_id": company_id,
            "candidate_token": "offer-token",
            "candidate_token_expires_at": None,
            "status": "sent",
        }
        updated = {
            **offer,
            "status": "accepted",
            "candidate_name": "Jane Doe",
            "position_title": "Dental Assistant",
            "signed_name": "Jane Doe",
            "signed_at": datetime.now(timezone.utc),
            "signer_ip": "127.0.0.1",
        }
        conn = MagicMock()
        conn.fetchrow = AsyncMock(side_effect=[offer, updated])
        monkeypatch.setattr(
            f"{offer_letters_mod.__name__}.get_connection",
            MagicMock(return_value=_conn_ctx(conn)),
        )
        monkeypatch.setattr(f"{offer_letters_mod.__name__}.check_rate_limit", AsyncMock())
        monkeypatch.setattr(f"{offer_letters_mod.__name__}.get_redis_cache", MagicMock(return_value=None))
        monkeypatch.setattr(f"{offer_letters_mod.__name__}.OfferLetter", lambda **row: row)

        background_tasks = BackgroundTasks()

        async def notify(*args, **kwargs):
            assert background_tasks.tasks == []

        notify_mock = AsyncMock(side_effect=notify)
        monkeypatch.setattr(
            f"{offer_letters_mod.__name__}._notify_huume_thread_of_offer_event",
            notify_mock,
        )
        request = Request({
            "type": "http", "method": "POST", "path": "/",
            "headers": [], "client": ("127.0.0.1", 1234),
            "scheme": "http", "server": ("testserver", 80),
        })

        await offer_letters_mod.accept_candidate_offer(
            "offer-token",
            offer_letters_mod.OfferAcceptRequest(signed_name="Jane Doe"),
            request,
            background_tasks,
        )

        notify_mock.assert_awaited_once()
        assert len(background_tasks.tasks) == 1
        assert background_tasks.tasks[0].func is offer_letters_mod._finish_offer_accept
