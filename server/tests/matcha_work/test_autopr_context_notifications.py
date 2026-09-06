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


class _ResultConn:
    def __init__(
        self,
        expected_note: str,
        *,
        current_note: str | None = None,
        already_notified: bool = False,
    ):
        self.expected_note = expected_note
        self.current_note = current_note or expected_note
        self.company_id = uuid4()
        self.recipient_id = uuid4()
        self.already_notified = already_notified
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
        return {
            "title": "Fix intake",
            "progress_note": self.current_note,
            "company_id": self.company_id,
            "project_title": "Hiring",
        }

    async def fetchval(self, query, *_args):
        self.queries.append(query)
        if "FROM mw_task_history" in query:
            return self.recipient_id
        if "FROM mw_notifications" in query:
            return self.already_notified
        raise AssertionError(f"Unexpected query: {query}")


class _CommentConn:
    def __init__(self):
        self.company_id = uuid4()
        self.assigned_to = uuid4()
        self.created_by = uuid4()
        self.queries: list[str] = []

    async def fetchrow(self, query, *_args):
        self.queries.append(query)
        if "FROM mw_tasks" in query:
            return {
                "company_id": self.company_id,
                "assigned_to": self.assigned_to,
                "created_by": self.created_by,
                "title": "Fix intake",
                "project_title": "Hiring",
            }
        if "FROM users" in query:
            return {"name": "Reviewer"}
        raise AssertionError(f"Unexpected query: {query}")

    async def fetch(self, query, *_args):
        self.queries.append(query)
        return []


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
    message = persisted.await_args.args[3]
    assert "Migration changes are drafted automatically" in message
    assert "migration-required stop" not in message
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
async def test_result_notification_targets_context_author_once_under_task_lock(monkeypatch):
    from app.matcha.services.matcha_work import project_task_notifications as svc

    expected = "🤖 AUTO SETUP · READY FOR REVIEW · PR #501"
    conn = _ResultConn(expected)
    create_notification = AsyncMock(return_value={"id": uuid4()})
    monkeypatch.setattr(svc, "get_connection", lambda: _Context(conn))
    monkeypatch.setattr(svc.notif_svc, "create_notification", create_notification)
    event_id = uuid4()
    project_id = uuid4()
    task_id = uuid4()

    posted = await svc.post_autopr_result_notification(
        project_id=project_id,
        task_id=task_id,
        reconsideration_event_id=event_id,
        expected_progress_note=expected,
        message="AutoPR accepted this context and drafted PR #501.",
    )

    assert posted is True
    assert any("FOR UPDATE OF t" in query for query in conn.queries)
    assert any("p.title AS project_title" in query for query in conn.queries)
    assert all("p.name AS project_title" not in query for query in conn.queries)
    create_notification.assert_awaited_once()
    kwargs = create_notification.await_args.kwargs
    assert kwargs["user_id"] == conn.recipient_id
    assert kwargs["type"] == "autopr_result"
    assert kwargs["metadata"]["reconsideration_event_id"] == str(event_id)
    assert conn.in_transaction is False


@pytest.mark.asyncio
async def test_result_notification_rejects_changed_result_note(monkeypatch):
    from app.matcha.services.matcha_work import project_task_notifications as svc

    expected = "🤖 AUTO SETUP · READY FOR REVIEW · PR #501"
    conn = _ResultConn(expected, current_note="🤖 AUTO SETUP · READY FOR REVIEW · PR #502")
    create_notification = AsyncMock()
    monkeypatch.setattr(svc, "get_connection", lambda: _Context(conn))
    monkeypatch.setattr(svc.notif_svc, "create_notification", create_notification)

    posted = await svc.post_autopr_result_notification(
        project_id=uuid4(),
        task_id=uuid4(),
        reconsideration_event_id=uuid4(),
        expected_progress_note=expected,
        message="AutoPR drafted PR #501.",
    )

    assert posted is False
    create_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_result_notification_retry_is_idempotent(monkeypatch):
    from app.matcha.services.matcha_work import project_task_notifications as svc

    expected = "🤖 AUTO SETUP · READY FOR REVIEW · PR #501"
    conn = _ResultConn(expected, already_notified=True)
    create_notification = AsyncMock()
    monkeypatch.setattr(svc, "get_connection", lambda: _Context(conn))
    monkeypatch.setattr(svc.notif_svc, "create_notification", create_notification)

    posted = await svc.post_autopr_result_notification(
        project_id=uuid4(),
        task_id=uuid4(),
        reconsideration_event_id=uuid4(),
        expected_progress_note=expected,
        message="AutoPR drafted PR #501.",
    )

    assert posted is True
    create_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_comment_notification_queries_canonical_project_title(monkeypatch):
    from app.matcha.services.matcha_work import project_task_notifications as svc

    conn = _CommentConn()
    create_notification = AsyncMock(return_value={"id": uuid4()})
    monkeypatch.setattr(svc, "get_connection", lambda: _Context(conn))
    monkeypatch.setattr(svc.notif_svc, "create_notification", create_notification)

    await svc._notify_task_comment(
        project_id=uuid4(),
        task_id=uuid4(),
        actor_user_id=uuid4(),
        body="The intake details are ready.",
    )

    assert any("p.title AS project_title" in query for query in conn.queries)
    assert all("p.name AS project_title" not in query for query in conn.queries)
    assert create_notification.await_count == 2


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
