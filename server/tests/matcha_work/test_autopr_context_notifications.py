"""Atomic AutoPR project-chat request regression tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


class _Context:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self, expected_note: str, *, locked_note: str | None = None):
        self.expected_note = expected_note
        self.locked_note = locked_note or expected_note
        self.channel_id = uuid4()
        self.company_id = uuid4()
        self.queries: list[str] = []
        self.in_transaction = False

    def transaction(self):
        conn = self

        class _Transaction:
            async def __aenter__(self):
                conn.in_transaction = True

            async def __aexit__(self, *_args):
                conn.in_transaction = False
                return False

        return _Transaction()

    async def fetchrow(self, query, *_args):
        self.queries.append(query)
        note = self.locked_note if "FOR UPDATE OF t" in query else self.expected_note
        return {
            "title": "Fix intake",
            "board_column": "changes_requested",
            "progress_note": note,
            "company_id": self.company_id,
            "channel_id": self.channel_id,
        }

    async def fetchval(self, query, *_args):
        self.queries.append(query)
        return False


@pytest.mark.asyncio
async def test_context_request_rechecks_and_inserts_under_one_task_lock(monkeypatch):
    from app.matcha.services.matcha_work import project_task_notifications as svc
    from app.matcha.services.matcha_work.project_agent import chat

    expected = "🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS"
    conn = _Conn(expected)
    persisted = AsyncMock(return_value={
        "channel_id": str(conn.channel_id),
        "id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    broadcast = AsyncMock()

    async def persist_while_locked(*args, **kwargs):
        assert conn.in_transaction is True
        return await persisted(*args, **kwargs)

    monkeypatch.setattr(svc, "get_connection", lambda: _Context(conn))
    monkeypatch.setattr(chat, "persist_espresso_message", persist_while_locked)
    monkeypatch.setattr(chat, "broadcast_espresso_message", broadcast)

    posted = await svc.post_autopr_context_request(
        project_id=uuid4(),
        task_id=uuid4(),
        actor_user_id=uuid4(),
        expected_progress_note=expected,
        reason="the affected screen is unknown",
    )

    assert posted is True
    assert any("FOR UPDATE OF t" in query for query in conn.queries)
    persisted.assert_awaited_once()
    broadcast.assert_awaited_once()
    assert conn.in_transaction is False


@pytest.mark.asyncio
async def test_context_request_rejects_a_decision_changed_before_insert(monkeypatch):
    from app.matcha.services.matcha_work import project_task_notifications as svc
    from app.matcha.services.matcha_work.project_agent import chat

    expected = "🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS"
    conn = _Conn(expected, locked_note="🤖 AUTO SETUP · READY FOR REVIEW")
    persist = AsyncMock()
    monkeypatch.setattr(svc, "get_connection", lambda: _Context(conn))
    monkeypatch.setattr(chat, "persist_espresso_message", persist)

    posted = await svc.post_autopr_context_request(
        project_id=uuid4(),
        task_id=uuid4(),
        actor_user_id=uuid4(),
        expected_progress_note=expected,
        reason="the affected screen is unknown",
    )

    assert posted is False
    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_espresso_post_persists_before_broadcast(monkeypatch):
    from app.matcha.services.matcha_work import project_task_notifications as notifications
    from app.matcha.services.matcha_work.project_agent import chat

    channel_id = uuid4()
    bot_id = uuid4()
    message_id = uuid4()
    connection_open = False

    class _ChatConn:
        async def fetchrow(self, query, *_args):
            assert "INSERT INTO channel_messages" in query
            return {"id": message_id, "created_at": datetime.now(timezone.utc)}

    class _ChatContext:
        async def __aenter__(self):
            nonlocal connection_open
            connection_open = True
            return _ChatConn()

        async def __aexit__(self, *_args):
            nonlocal connection_open
            connection_open = False
            return False

    async def broadcast_after_commit(_channel_id, payload):
        assert connection_open is False
        assert payload["id"] == str(message_id)

    monkeypatch.setattr(chat, "connection_or_direct", lambda: _ChatContext())
    monkeypatch.setattr(chat, "ensure_espresso_bot_user", AsyncMock(return_value=bot_id))
    monkeypatch.setattr(notifications, "broadcast_channel_message", broadcast_after_commit)

    await chat.post_as_espresso(
        uuid4(),
        channel_id,
        "Need more context",
        metadata={"kind": "autopr_context_request"},
    )
