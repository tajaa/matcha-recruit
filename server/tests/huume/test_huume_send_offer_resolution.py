"""Tests for onboarding_skill.resolve_offer_for_send + execute_send_offer's
recipient_email override (fake conn, no DB).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_send_offer_resolution.py -q

Both functions do `from app.database import get_connection` INSIDE the
function body (lazy import) — per server/CLAUDE.md's patching rule, that
means the name is re-bound fresh from app.database on every call, so a
monkeypatch on onboarding_skill.get_connection would be silently ignored.
Patch app.database.get_connection directly instead.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

import app.database as database
from app.matcha.services.huume import onboarding_skill

COMPANY_ID = uuid4()


class _ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, *, fetch_rows=None, fetchrow_row=None):
        self._fetch_rows = fetch_rows or []
        self._fetchrow_row = fetchrow_row
        self.fetchrow_calls = []

    async def fetch(self, query, *args):
        return self._fetch_rows

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((" ".join(query.split()), args))
        return self._fetchrow_row


def _patch_conn(monkeypatch, conn):
    monkeypatch.setattr(database, "get_connection", lambda: _ConnCtx(conn))


def _offer(**overrides):
    base = {
        "id": uuid4(), "candidate_name": "Maria Lopez", "candidate_email": "maria@example.com",
        "position_title": "Dental Hygienist", "status": "draft", "created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


class TestResolveOfferForSend:
    @pytest.mark.asyncio
    async def test_unique_candidate_latest_draft_wins(self, monkeypatch):
        older = _offer(candidate_name="Maria Lopez", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        newer = _offer(candidate_name="Maria Lopez", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
        # ORDER BY created_at DESC — newest first, as the real query returns.
        conn = _FakeConn(fetch_rows=[newer, older])
        _patch_conn(monkeypatch, conn)

        result = await onboarding_skill.resolve_offer_for_send(company_id=COMPANY_ID, candidate_name="Maria")
        assert result["status"] == "ok"
        assert result["offer"]["id"] == newer["id"]

    @pytest.mark.asyncio
    async def test_two_distinct_candidates_returns_ambiguous(self, monkeypatch):
        maria = _offer(candidate_name="Maria Lopez")
        mario = _offer(candidate_name="Mario Rossi")
        conn = _FakeConn(fetch_rows=[maria, mario])
        _patch_conn(monkeypatch, conn)

        result = await onboarding_skill.resolve_offer_for_send(company_id=COMPANY_ID, candidate_name="Mar")
        assert result["status"] == "ambiguous"
        names = {m["candidate_name"] for m in result["matches"]}
        assert names == {"Maria Lopez", "Mario Rossi"}

    @pytest.mark.asyncio
    async def test_no_match_returns_not_found(self, monkeypatch):
        conn = _FakeConn(fetch_rows=[])
        _patch_conn(monkeypatch, conn)

        result = await onboarding_skill.resolve_offer_for_send(company_id=COMPANY_ID, candidate_name="Nobody")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_latest_not_draft_refuses_with_status(self, monkeypatch):
        sent = _offer(candidate_name="Maria Lopez", status="sent")
        conn = _FakeConn(fetch_rows=[sent])
        _patch_conn(monkeypatch, conn)

        result = await onboarding_skill.resolve_offer_for_send(company_id=COMPANY_ID, candidate_name="Maria")
        assert result["status"] == "not_draft"
        assert "sent" in result["message"]

    @pytest.mark.asyncio
    async def test_no_name_and_no_offer_id_returns_not_found(self, monkeypatch):
        conn = _FakeConn()
        _patch_conn(monkeypatch, conn)
        result = await onboarding_skill.resolve_offer_for_send(company_id=COMPANY_ID)
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_offer_id_given_skips_name_logic(self, monkeypatch):
        row = _offer()
        conn = _FakeConn(fetchrow_row=row)
        _patch_conn(monkeypatch, conn)
        result = await onboarding_skill.resolve_offer_for_send(company_id=COMPANY_ID, offer_id=str(row["id"]))
        assert result["status"] == "ok"
        assert result["offer"]["id"] == row["id"]


class TestExecuteSendOfferOverride:
    @pytest.mark.asyncio
    async def test_override_coalesced_into_update(self, monkeypatch):
        draft = _offer(status="draft")
        sent = dict(draft, status="sent", candidate_email="override@example.com",
                    company_name="Sunset Smile", position_title="Dental Hygienist")

        class _Conn(_FakeConn):
            async def fetchrow(self, query, *args):
                self.fetchrow_calls.append((" ".join(query.split()), args))
                if "UPDATE offer_letters" in query:
                    return sent
                return draft

        conn = _Conn()
        _patch_conn(monkeypatch, conn)
        monkeypatch.setattr(
            "app.core.services.email.EmailService.is_configured", lambda self: False,
        )

        result = await onboarding_skill.execute_send_offer(
            company_id=COMPANY_ID, actor_user_id=uuid4(), offer_id=str(draft["id"]),
            recipient_email="override@example.com",
        )
        assert result["status"] == "created"
        update_query, update_args = conn.fetchrow_calls[-1]
        assert "candidate_email = COALESCE($4, candidate_email)" in update_query
        assert "override@example.com" in update_args

    @pytest.mark.asyncio
    async def test_no_email_no_override_errors(self, monkeypatch):
        draft = _offer(status="draft", candidate_email=None)
        conn = _FakeConn(fetchrow_row=draft)
        _patch_conn(monkeypatch, conn)

        result = await onboarding_skill.execute_send_offer(
            company_id=COMPANY_ID, actor_user_id=uuid4(), offer_id=str(draft["id"]),
        )
        assert result["status"] == "error"
        assert "candidate email" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_override_satisfies_missing_email_guard(self, monkeypatch):
        draft = _offer(status="draft", candidate_email=None)
        sent = dict(draft, status="sent", candidate_email="new@example.com",
                    company_name="Sunset Smile", position_title="Dental Hygienist")

        class _Conn(_FakeConn):
            async def fetchrow(self, query, *args):
                self.fetchrow_calls.append((" ".join(query.split()), args))
                if "UPDATE offer_letters" in query:
                    return sent
                return draft

        conn = _Conn()
        _patch_conn(monkeypatch, conn)
        monkeypatch.setattr(
            "app.core.services.email.EmailService.is_configured", lambda self: False,
        )

        result = await onboarding_skill.execute_send_offer(
            company_id=COMPANY_ID, actor_user_id=uuid4(), offer_id=str(draft["id"]),
            recipient_email="new@example.com",
        )
        assert result["status"] == "created"
