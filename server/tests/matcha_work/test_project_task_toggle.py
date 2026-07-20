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

import json
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
        self.executed: list = []

    async def fetchrow(self, query, *args):
        if "SELECT board_column, status" in query:
            return self._current
        if "UPDATE mw_tasks SET" in query:
            self.update_args = args
            return self._returning
        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query, *args):
        # `_log_task_history` writes via execute() and swallows its own
        # exceptions. Without this the history path silently never ran under
        # test (it logged "no attribute 'execute'" as a WARNING and moved on).
        self.executed.append((query, args))
        return "INSERT 0 1"

    def history_rows(self) -> list:
        """Decode the mw_task_history INSERTs captured off `executed`.

        Mirrors the arg order in `project_task_service._log_task_history`:
        ($1 task_id, $2 task_id_text, $3 project_id, $4 actor_user_id,
         $5 event_type, $6 from_value, $7 to_value, $8 metadata::jsonb).
        Returns [(event_type, metadata_dict)].
        """
        rows = []
        for query, args in self.executed:
            if "INSERT INTO mw_task_history" not in query:
                continue
            rows.append((args[4], json.loads(args[7])))
        return rows


def _assert_metadata_is_string_only(rows: list) -> None:
    """mw_task_history.metadata must be a flat [String: String] map.

    The macOS client decodes that column as `[String: String]`; a single
    non-string value (int, UUID, None, nested dict/list) fails the decode for
    the WHOLE history payload, so notes and rounds silently vanish from the
    ticket timeline rather than erroring. `project_subtask_service.start_new_round`
    and `project_task_service.reject_project_task` both carry the same warning
    in-line — this is the automated version of it.
    """
    for event_type, metadata in rows:
        assert isinstance(metadata, dict), (
            f"{event_type}: metadata must encode to a JSON object, got {type(metadata)}"
        )
        for key, value in metadata.items():
            assert isinstance(key, str), f"{event_type}: metadata key {key!r} is not a string"
            assert isinstance(value, str), (
                f"{event_type}: metadata[{key!r}] is {type(value).__name__} "
                f"({value!r}) — the desktop decodes metadata as [String: String], "
                "so this silently breaks the entire history decode. Stringify it."
            )


class _FakeCtx:
    def __init__(self, conn): self.conn = conn
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *a): return False


def _make_current(*, board_column: str, status: str) -> dict:
    """Shape that mirrors the pre-UPDATE SELECT in update_project_task.

    Must stay in sync with the column list at
    `project_task_service.update_project_task` (SELECT board_column, status,
    assigned_to, company_id, description, progress_note) — the task-history
    and column-transition notification blocks read every one of these off the
    row, so a short fixture raises KeyError *after* the UPDATE and makes every
    later assertion unreachable.
    """
    return {
        "board_column": board_column,
        "status": status,
        "assigned_to": None,
        "company_id": uuid4(),
        "description": None,
        "progress_note": None,
    }


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
        current=_make_current(board_column="todo", status="pending"),
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
        current=_make_current(board_column="todo", status="pending"),
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
        current=_make_current(board_column="done", status="completed"),
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
        current=_make_current(board_column="in_progress", status="pending"),
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
        current=_make_current(board_column="todo", status="pending"),
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
async def test_toggle_logs_column_change_history_row(monkeypatch):
    """The move must actually reach mw_task_history.

    `_log_task_history` swallows every exception it raises, so a broken INSERT
    (missing column, bad cast) shows up as a silently empty ticket timeline and
    nothing else. Assert the row is written and carries the real transition.
    """
    from app.matcha.services import project_task_service as svc

    conn = _FakeConn(
        current=_make_current(board_column="todo", status="pending"),
        returning=_make_returning(board_column="done", status="completed"),
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _FakeCtx(conn))

    await svc.update_project_task(
        uuid4(), uuid4(),
        {"board_column": "done", "status": "completed"},
    )

    rows = conn.history_rows()
    assert rows, "no mw_task_history INSERT was issued for a column move"
    events = [event_type for event_type, _ in rows]
    assert "column_change" in events, f"expected a column_change row, got {events}"
    _assert_metadata_is_string_only(rows)


@pytest.mark.asyncio
async def test_history_metadata_values_are_all_strings(monkeypatch):
    """Edits that DO carry metadata must carry string-only values.

    Description / progress-note edits are the paths that populate metadata on
    this endpoint, so they're the ones that can regress a non-string in. If
    someone writes an int, a UUID, a None, or a nested dict here, the desktop's
    [String: String] decode of mw_task_history fails wholesale.
    """
    from app.matcha.services import project_task_service as svc

    conn = _FakeConn(
        current=_make_current(board_column="todo", status="pending"),
        returning=_make_returning(board_column="todo", status="pending"),
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _FakeCtx(conn))

    await svc.update_project_task(
        uuid4(), uuid4(),
        {"description": "Rewired the intake form", "progress_note": "Halfway"},
    )

    rows = conn.history_rows()
    events = [event_type for event_type, _ in rows]
    assert "description_change" in events, f"expected description_change, got {events}"
    assert "progress_note_change" in events, f"expected progress_note_change, got {events}"

    # These rows must not be empty, or the string check below proves nothing.
    populated = [(e, m) for e, m in rows if m]
    assert populated, "expected at least one history row carrying metadata"
    _assert_metadata_is_string_only(rows)


@pytest.mark.asyncio
async def test_invalid_board_column_raises_valueerror(monkeypatch):
    """Bad payload should raise ValueError (route catches → 400). A silent
    failure here would not show as a 400 — the desktop catch block then
    calls loadTasks() and the user sees the snap-back."""
    from app.matcha.services import project_task_service as svc

    conn = _FakeConn(
        current=_make_current(board_column="todo", status="pending"),
        returning=_make_returning(board_column="todo", status="pending"),
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _FakeCtx(conn))

    with pytest.raises(ValueError, match="Invalid board_column"):
        await svc.update_project_task(
            uuid4(), uuid4(), {"board_column": "bogus"},
        )
