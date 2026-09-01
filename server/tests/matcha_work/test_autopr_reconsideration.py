"""Decision-bound AutoPR reconsideration regression tests."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


class _AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        return False


class _ReconsiderationConn:
    def __init__(self, progress_note, *, board_column="todo", status="pending"):
        self.progress_note = progress_note
        self.board_column = board_column
        self.status = status
        self.insert_args = None
        self.activity_id = uuid4()
        self.created_at = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)

    def transaction(self):
        return _AsyncContext()

    async def fetchrow(self, query, *args):
        if "SELECT id, progress_note" in query:
            if self.progress_note is None:
                return None
            return {
                "id": args[0],
                "progress_note": self.progress_note,
                "board_column": self.board_column,
                "status": self.status,
            }
        if "INSERT INTO mw_task_history" in query:
            self.insert_args = args
            return {"id": self.activity_id, "created_at": self.created_at}
        raise AssertionError(f"Unexpected query: {query}")


def _connection_context(conn):
    return _AsyncContext(conn)


@pytest.mark.asyncio
async def test_reconsideration_is_bound_to_exact_no_spec_note(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    note = (
        "🤖 AUTO SETUP · NO PR: ALREADY FIXED · build 858 · prod 1065b28 · "
        "🟡 C98 · [autopr:no-spec 2026-08-28T22:37:56Z] already_fixed"
    )
    conn = _ReconsiderationConn(note)
    notify = AsyncMock()
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    monkeypatch.setattr(svc, "_notify_task_comment", notify)
    project_id, task_id, actor_id, attachment_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )

    result = await svc.request_autopr_reconsideration(
        project_id=project_id,
        task_id=task_id,
        actor_user_id=actor_id,
        expected_progress_note=note,
        body="The existing credential selector only covers employees, not jobs.",
        attachment_ids=[attachment_id],
    )

    assert result["autopr_reconsideration_pending"] is True
    assert result["activity_id"] == str(conn.activity_id)
    metadata = json.loads(conn.insert_args[4])
    assert metadata["kind"] == "autopr_additional_context"
    assert metadata["autopr_reconsideration_of"] == note
    assert metadata["attachment_ids"] == [str(attachment_id)]
    assert metadata["reply_to_name"] == "AUTO SETUP"
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconsideration_rejects_stale_decision(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = (
        "🤖 AUTO SETUP · NO PR: ALREADY FIXED · "
        "[autopr:no-spec 2026-08-30T20:00:00Z] already_fixed"
    )
    conn = _ReconsiderationConn(current)
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    with pytest.raises(svc.AutoPRReconsiderationConflict, match="decision changed"):
        await svc.request_autopr_reconsideration(
            project_id=uuid4(),
            task_id=uuid4(),
            actor_user_id=uuid4(),
            expected_progress_note=current + " stale",
            body="New evidence",
        )
    assert conn.insert_args is None


@pytest.mark.asyncio
async def test_reconsideration_rejects_non_no_spec_task(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = "🤖 AUTO SETUP · READY FOR REVIEW · PR #401"
    conn = _ReconsiderationConn(current)
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    with pytest.raises(svc.AutoPRReconsiderationConflict, match="no longer"):
        await svc.request_autopr_reconsideration(
            project_id=uuid4(),
            task_id=uuid4(),
            actor_user_id=uuid4(),
            expected_progress_note=current,
            body="New evidence",
        )


@pytest.mark.asyncio
async def test_awaiting_answers_accepts_chat_or_ticket_context(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = (
        "🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · build 900 · "
        "prod abc1234 · PR #501 · note: Which jobs screen is affected?"
    )
    conn = _ReconsiderationConn(current, board_column="changes_requested")
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    monkeypatch.setattr(svc, "_notify_task_comment", AsyncMock())

    result = await svc.request_autopr_reconsideration(
        project_id=uuid4(),
        task_id=uuid4(),
        actor_user_id=uuid4(),
        expected_progress_note=current,
        body="The jobs editor at /work/jobs is the affected screen.",
    )

    assert result["autopr_reconsideration_pending"] is True
    assert json.loads(conn.insert_args[4])["kind"] == "autopr_additional_context"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("board_column", "status"),
    [
        ("in_progress", "pending"),
        ("review", "pending"),
        ("done", "completed"),
        ("todo", "cancelled"),
    ],
)
async def test_reconsideration_rejects_ineligible_task_state(
    monkeypatch, board_column, status
):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = (
        "🤖 AUTO SETUP · NO PR: ALREADY FIXED · "
        "[autopr:no-spec 2026-08-30T20:00:00Z] already_fixed"
    )
    conn = _ReconsiderationConn(
        current, board_column=board_column, status=status
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    with pytest.raises(svc.AutoPRReconsiderationConflict, match="Todo or Changes"):
        await svc.request_autopr_reconsideration(
            project_id=uuid4(),
            task_id=uuid4(),
            actor_user_id=uuid4(),
            expected_progress_note=current,
            body="New evidence",
        )
    assert conn.insert_args is None


@pytest.mark.asyncio
async def test_reconsideration_requires_text_or_attachment():
    from app.matcha.services.matcha_work import project_task_service as svc

    with pytest.raises(ValueError, match="requires text or an attachment"):
        await svc.request_autopr_reconsideration(
            project_id=uuid4(),
            task_id=uuid4(),
            actor_user_id=uuid4(),
            expected_progress_note="unused",
            body="   ",
        )


def test_task_shape_serializes_reconsideration_fields():
    from app.matcha.services.matcha_work import project_task_service as svc

    event_id = uuid4()
    now = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
    shaped = svc._row_to_task(
        {
            "id": uuid4(),
            "autopr_reconsideration_pending": True,
            "autopr_reconsideration_event_id": event_id,
            "autopr_reconsideration_at": now,
        }
    )
    assert shaped["autopr_reconsideration_event_id"] == str(event_id)
    assert shaped["autopr_reconsideration_at"] == now.isoformat()
