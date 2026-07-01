"""Unit tests for creating journal entries without a folder association.

Context: `create_journal` used to always land a new note in *some* folder —
an omitted `folder_id` fell back to the caller's default "Notes" notebook via
`_ensure_default_folder` (the "Evernote model"), so there was no way to
create a genuinely unfiled note. `folder_id_provided` distinguishes "omitted"
from "explicitly null" (same trick `JournalPatch` already used for moves),
so a caller that explicitly sends `folder_id: null` gets a real NULL instead
of being auto-filed.

These are fast, DB-free unit tests (per repo rules: never auto-run
DB-mutating tests) — same `_FakeConn` capturing-fake pattern as
`test_journal_isolation.py`.
"""

from uuid import uuid4

import pytest


class _FakeConn:
    """Capturing asyncpg fake for `create_journal`. `folder_owned` controls
    the answer to the folder-ownership EXISTS check."""

    def __init__(self, folder_owned: bool = True):
        self.folder_owned = folder_owned
        self.calls: list[tuple] = []  # (method, query, args)

    def _record(self, method, query, args):
        self.calls.append((method, query, args))

    async def fetchval(self, query, *args):
        self._record("fetchval", query, args)
        if "SELECT EXISTS(SELECT 1 FROM mw_journal_folders" in query:
            return self.folder_owned
        if "SELECT id FROM mw_journal_folders" in query:
            return None  # _ensure_default_folder: no existing "Notes" folder
        if "INSERT INTO mw_journal_folders" in query:
            return uuid4()  # _ensure_default_folder: create + return new id
        return None

    async def fetchrow(self, query, *args):
        self._record("fetchrow", query, args)
        folder_id = args[-1] if args else None
        return {
            "id": uuid4(), "title": "n", "description": None, "color": None,
            "icon": None, "status": "active", "kind": "note",
            "folder_id": folder_id, "created_by": uuid4(),
            "created_at": None, "updated_at": None,
        }

    async def execute(self, query, *args):
        self._record("execute", query, args)
        return "OK"


class _FakeCtx:
    def __init__(self, conn): self.conn = conn
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *a): return False


def _insert_journal_call(conn):
    for method, query, args in conn.calls:
        if "INSERT INTO mw_journals" in query:
            return args
    raise AssertionError(f"No INSERT INTO mw_journals call. Got: {[c[1][:60] for c in conn.calls]}")


def _touched_folders_table(conn) -> bool:
    return any("mw_journal_folders" in query for _m, query, _a in conn.calls)


@pytest.mark.asyncio
async def test_omitted_folder_id_still_auto_files_into_default_folder(monkeypatch):
    """Unchanged existing behavior: folder_id_provided=False (the default)
    means "not specified" -> auto-assign the caller's "Notes" notebook."""
    from app.matcha.services import journal_service as svc
    creator, company = uuid4(), uuid4()
    conn = _FakeConn()
    monkeypatch.setattr(svc, "get_connection", lambda *a, **k: _FakeCtx(conn))

    await svc.create_journal(creator, company, title="n")

    assert _touched_folders_table(conn), "omitted folder_id must still auto-assign a default folder"
    args = _insert_journal_call(conn)
    assert args[-1] is not None, "auto-assigned folder_id must not be NULL"


@pytest.mark.asyncio
async def test_explicit_null_folder_id_creates_unfiled_journal(monkeypatch):
    """The new capability: folder_id=None + folder_id_provided=True means the
    caller genuinely wants no folder -> skip the default-folder auto-assign,
    insert with folder_id NULL."""
    from app.matcha.services import journal_service as svc
    creator, company = uuid4(), uuid4()
    conn = _FakeConn()
    monkeypatch.setattr(svc, "get_connection", lambda *a, **k: _FakeCtx(conn))

    result = await svc.create_journal(
        creator, company, title="n", folder_id=None, folder_id_provided=True,
    )

    assert not _touched_folders_table(conn), "explicit unfiled create must not touch mw_journal_folders"
    args = _insert_journal_call(conn)
    assert args[-1] is None, "explicitly unfiled journal must insert with folder_id NULL"
    assert result["folder_id"] is None


@pytest.mark.asyncio
async def test_invalid_folder_id_falls_back_to_default_not_unfiled(monkeypatch):
    """A real folder_id that fails the ownership check is NOT the same as
    "explicitly unfiled" — it still falls back to the default "Notes" folder,
    matching the pre-existing behavior for a bad/foreign folder reference."""
    from app.matcha.services import journal_service as svc
    creator, company, foreign_folder = uuid4(), uuid4(), uuid4()
    conn = _FakeConn(folder_owned=False)
    monkeypatch.setattr(svc, "get_connection", lambda *a, **k: _FakeCtx(conn))

    await svc.create_journal(
        creator, company, title="n", folder_id=foreign_folder, folder_id_provided=True,
    )

    args = _insert_journal_call(conn)
    assert args[-1] is not None, "invalid folder_id must still auto-assign a default folder, not end up unfiled"
