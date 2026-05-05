"""Regression tests for the kanban toggle PATCH path.

The desktop app sends `PATCH /matcha-work/projects/{pid}/tasks/{tid}` with
`{"board_column": "done", "status": "completed"}` when the user clicks the
checkbox. Symptom users have reported in COLLAB projects: card flickers to
Done, then snaps back to Todo. The Swift catch block then calls loadTasks(),
which reverts the optimistic update — so any uncaught exception in the
service layer manifests as that snap-back.

These tests pin down the sync rules in
`project_task_service.update_project_task` so a regression in the SQL or the
sync logic (board_column ↔ status invariants) doesn't slip through silently.
"""

import sys
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

# Stub heavyweight optional deps before importing app code
for _name in ("google", "google.genai", "google.genai.types", "bleach",
              "audioop_lts", "audioop", "stripe"):
    if _name not in sys.modules:
        sys.modules[_name] = ModuleType(_name)

_genai = sys.modules["google.genai"]
_genai.Client = object
_genai.types = sys.modules["google.genai.types"]
_gt = sys.modules["google.genai.types"]
_gt.Tool = lambda **kw: None
_gt.GoogleSearch = lambda **kw: None
_gt.GenerateContentConfig = lambda **kw: None
_bleach = sys.modules["bleach"]
_bleach.clean = lambda text, **kw: text
_bleach.linkify = lambda text, **kw: text


class _FakeConn:
    """Minimal asyncpg connection fake. Records the last UPDATE args so
    tests can assert which (board_column, status) pair was written."""

    def __init__(self, current: dict, returning: dict):
        self._current = current
        self._returning = returning
        self.update_args: tuple = ()

    async def fetchrow(self, query, *args):
        if "SELECT board_column, status" in query:
            return self._current
        if "UPDATE mw_tasks SET" in query:
            self.update_args = args
            return self._returning
        raise AssertionError(f"Unexpected query: {query}")


class _FakeCtx:
    def __init__(self, conn): self.conn = conn
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *a): return False


def _make_returning(*, board_column: str, status: str) -> dict:
    """Shape that mirrors the RETURNING clause in update_project_task."""
    now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
    completed_at = now if status == "completed" else None
    return {
        "id": uuid4(),
        "project_id": uuid4(),
        "company_id": uuid4(),
        "created_by": uuid4(),
        "title": "Some task",
        "description": None,
        "due_date": None,
        "priority": "medium",
        "status": status,
        "board_column": board_column,
        "assigned_to": None,
        "completed_at": completed_at,
        "created_at": now,
        "updated_at": now,
    }


@pytest.mark.asyncio
async def test_toggle_to_done_sends_completed_status_and_done_column(monkeypatch):
    """Desktop sends {board_column:'done', status:'completed'}. Service must
    write status='completed' and board_column='done' to the DB."""
    from app.matcha.services import project_task_service as svc

    conn = _FakeConn(
        current={"board_column": "todo", "status": "pending"},
        returning=_make_returning(board_column="done", status="completed"),
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _FakeCtx(conn))

    result = await svc.update_project_task(
        uuid4(), uuid4(),
        {"board_column": "done", "status": "completed"},
    )

    # $1 = new_column, $3 = new_status (matches the SQL parameter order).
    assert conn.update_args[0] == "done"
    assert conn.update_args[2] == "completed"
    assert result["status"] == "completed"
    assert result["board_column"] == "done"


@pytest.mark.asyncio
async def test_toggle_to_done_with_only_status_in_patch(monkeypatch):
    """If desktop only sends `status: completed` (older client), service
    must still derive board_column='done' from the sync rule."""
    from app.matcha.services import project_task_service as svc

    conn = _FakeConn(
        current={"board_column": "todo", "status": "pending"},
        returning=_make_returning(board_column="done", status="completed"),
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _FakeCtx(conn))

    result = await svc.update_project_task(
        uuid4(), uuid4(), {"status": "completed"},
    )

    assert conn.update_args[0] == "done", "status='completed' must force column='done'"
    assert conn.update_args[2] == "completed"
    assert result["board_column"] == "done"


@pytest.mark.asyncio
async def test_toggle_to_pending_sends_todo_column(monkeypatch):
    """Reverse toggle: status='pending' from a 'done' card moves column
    back to 'todo' so the unchecked card lands in the Todo lane."""
    from app.matcha.services import project_task_service as svc

    conn = _FakeConn(
        current={"board_column": "done", "status": "completed"},
        returning=_make_returning(board_column="todo", status="pending"),
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _FakeCtx(conn))

    result = await svc.update_project_task(
        uuid4(), uuid4(),
        {"board_column": "todo", "status": "pending"},
    )

    assert conn.update_args[0] == "todo"
    assert conn.update_args[2] == "pending"
    assert result["status"] == "pending"
    assert result["board_column"] == "todo"


@pytest.mark.asyncio
async def test_drag_to_done_only_board_column_in_patch(monkeypatch):
    """Drag-drop sends just `board_column`. Service derives status='completed'."""
    from app.matcha.services import project_task_service as svc

    conn = _FakeConn(
        current={"board_column": "in_progress", "status": "pending"},
        returning=_make_returning(board_column="done", status="completed"),
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _FakeCtx(conn))

    await svc.update_project_task(
        uuid4(), uuid4(), {"board_column": "done"},
    )

    assert conn.update_args[0] == "done"
    assert conn.update_args[2] == "completed"


@pytest.mark.asyncio
async def test_response_shape_matches_swift_decoder(monkeypatch):
    """The Mac client's MWProjectTask Codable struct expects: id, title,
    project_id, board_column, priority, status (required) plus optional
    description, assigned_to, due_date, completed_at, created_at, updated_at,
    assigned_name. _row_to_task must stringify UUIDs and isoformat datetimes
    so JSON round-trips cleanly through Swift's JSONDecoder."""
    from app.matcha.services import project_task_service as svc

    conn = _FakeConn(
        current={"board_column": "todo", "status": "pending"},
        returning=_make_returning(board_column="done", status="completed"),
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _FakeCtx(conn))

    result = await svc.update_project_task(
        uuid4(), uuid4(),
        {"board_column": "done", "status": "completed"},
    )

    # Required fields for Swift decode
    for key in ("id", "title", "board_column", "priority", "status"):
        assert key in result and result[key] is not None, f"missing {key}"

    # UUIDs stringified
    assert isinstance(result["id"], str)
    assert isinstance(result["project_id"], str)

    # datetimes ISO-formatted
    assert isinstance(result["completed_at"], str)
    assert "T" in result["completed_at"], "expected ISO datetime"
    assert isinstance(result["created_at"], str)
    assert isinstance(result["updated_at"], str)


@pytest.mark.asyncio
async def test_invalid_board_column_raises_valueerror(monkeypatch):
    """Bad payload should raise ValueError (route catches → 400). A silent
    failure here would not show as a 400 — the desktop catch block then
    calls loadTasks() and the user sees the snap-back."""
    from app.matcha.services import project_task_service as svc

    conn = _FakeConn(
        current={"board_column": "todo", "status": "pending"},
        returning=_make_returning(board_column="todo", status="pending"),
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _FakeCtx(conn))

    with pytest.raises(ValueError, match="Invalid board_column"):
        await svc.update_project_task(
            uuid4(), uuid4(), {"board_column": "bogus"},
        )
