"""Cross-user isolation regression tests for the Werk Journals feature.

Context — the leak this pins down (2026-06-11):
    Journals/notes are a PERSONAL feature, but multiple `client` users share a
    single `company_id`. Two queries scoped journals by company alone, so a
    coworker's notebooks + journal activity leaked across users in the same
    company:
      1. `journal_service.list_journal_folders` (+ folder CRUD) filtered only
         by `company_id` — coworker notebooks showed in the sidebar.
      2. The dashboard activity feed's `recent_journals` CTE in
         `matcha_work.list_recent_activity_endpoint` filtered only by
         `company_id` — coworker journal titles showed on Home.
    Notes themselves (`list_journals`) were already scoped by `created_by`.

    There is NO enforced Postgres RLS on the `mw_journal*` tables (the app
    connects as a BYPASSRLS superuser, so the handbook RLS policies are dormant
    too). Isolation is therefore purely application-level `WHERE` clauses — and
    these tests are the guard that those clauses keep scoping by the caller.

These are fast, DB-free unit tests (per repo rules: never auto-run
DB-mutating tests). They monkeypatch `get_connection` with a capturing fake
and assert the emitted SQL scopes by the user, with the user id bound as a
parameter. If someone drops the `created_by` filter, these fail.
"""

import os
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest

# `app.matcha.routes.__init__` imports provisioning.py, which raises at import
# time if these are unset. The activity-feed test imports the route module, so
# satisfy them with throwaway values (no network — import-time guard only).
for _k, _v in (
    ("GUSTO_OAUTH_CLIENT_ID", "test"),
    ("GUSTO_OAUTH_CLIENT_SECRET", "test"),
    ("GUSTO_OAUTH_REDIRECT_URI", "http://localhost/test"),
):
    os.environ.setdefault(_k, _v)

# ── Stub heavyweight optional deps before importing app code ──
for _name in ("bleach",
              "audioop_lts", "audioop", "stripe"):
    if _name not in sys.modules:
        sys.modules[_name] = ModuleType(_name)

# google.genai is set up once, suite-wide, in tests/conftest.py. Assigning
# onto it here mutates the REAL module process-wide and breaks later tests.
_bleach = sys.modules["bleach"]
_bleach.clean = lambda text, **kw: text
_bleach.linkify = lambda text, **kw: text


_NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


def _folder_row(created_by):
    return {
        "id": uuid4(), "name": "Notes", "parent_id": None,
        "created_by": created_by, "created_at": _NOW, "color": None,
    }


def _journal_row(created_by, folder_id):
    return {
        "id": uuid4(), "title": "A note", "description": None, "color": None,
        "icon": "note.text", "status": "active", "kind": "note",
        "folder_id": folder_id, "created_by": created_by,
        "created_at": _NOW, "updated_at": _NOW,
    }


class _FakeConn:
    """Capturing asyncpg fake. Records every (method, query, args) so tests can
    assert the WHERE clauses + bound params. Returns shapes good enough for the
    service `_parse_*` helpers to run."""

    def __init__(self, created_by):
        self._created_by = created_by
        self.calls: list[tuple] = []  # (method, query, args)

    def _record(self, method, query, args):
        self.calls.append((method, query, args))

    async def fetch(self, query, *args):
        self._record("fetch", query, args)
        return []

    async def fetchval(self, query, *args):
        self._record("fetchval", query, args)
        # _ensure_default_folder: existence SELECT returns None → forces INSERT
        if "SELECT id FROM mw_journal_folders" in query:
            return None
        if "INSERT INTO mw_journal_folders" in query:
            return uuid4()
        # all ownership/parent checks are EXISTS(...) — say "yes, you own it"
        if "EXISTS" in query:
            return True
        return None

    async def fetchrow(self, query, *args):
        self._record("fetchrow", query, args)
        if "mw_journal_folders" in query:
            return _folder_row(self._created_by)
        return _journal_row(self._created_by, args[-1] if args else None)

    async def execute(self, query, *args):
        self._record("execute", query, args)
        return "OK"


class _FakeCtx:
    def __init__(self, conn): self.conn = conn
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *a): return False


def _first(conn, needle):
    """First captured (method, query, args) whose query contains `needle`."""
    for call in conn.calls:
        if needle in call[1]:
            return call
    raise AssertionError(f"No query containing {needle!r}. Got: "
                         f"{[c[1][:60] for c in conn.calls]}")


# ============================================================
# journal_service — folders are scoped per-user (created_by)
# ============================================================

@pytest.mark.asyncio
async def test_list_journal_folders_scopes_by_user(monkeypatch):
    from app.matcha.services import journal_service as svc
    user_id, company_id = uuid4(), uuid4()
    conn = _FakeConn(user_id)
    monkeypatch.setattr(svc, "get_connection", lambda *a, **k: _FakeCtx(conn))

    await svc.list_journal_folders(company_id, user_id)

    _m, query, args = _first(conn, "FROM mw_journal_folders")
    assert "created_by = $2" in query, "folder list must filter by created_by"
    assert args == (company_id, user_id)


@pytest.mark.asyncio
async def test_ensure_default_folder_scopes_by_creator():
    """Each user gets their OWN 'Notes' notebook — the existence check must be
    keyed on created_by, not just company."""
    from app.matcha.services import journal_service as svc
    creator, company = uuid4(), uuid4()
    conn = _FakeConn(creator)

    await svc._ensure_default_folder(conn, company, creator)

    _m, query, args = _first(conn, "SELECT id FROM mw_journal_folders")
    assert "created_by = $2" in query
    assert args == (company, creator)


@pytest.mark.asyncio
async def test_create_journal_folder_parent_check_scopes_by_creator(monkeypatch):
    from app.matcha.services import journal_service as svc
    creator, company, parent = uuid4(), uuid4(), uuid4()
    conn = _FakeConn(creator)
    monkeypatch.setattr(svc, "get_connection", lambda *a, **k: _FakeCtx(conn))

    await svc.create_journal_folder(creator, company, name="Sub", parent_id=parent)

    _m, query, args = _first(conn, "EXISTS")
    assert "created_by = $3" in query, "parent folder must be owned by caller"
    assert args == (parent, company, creator)


@pytest.mark.asyncio
async def test_update_journal_folder_owner_check_scopes_by_user(monkeypatch):
    from app.matcha.services import journal_service as svc
    user_id, company, folder = uuid4(), uuid4(), uuid4()
    conn = _FakeConn(user_id)
    monkeypatch.setattr(svc, "get_connection", lambda *a, **k: _FakeCtx(conn))

    await svc.update_journal_folder(folder, company, user_id, {})

    _m, query, args = _first(conn, "EXISTS")
    assert "created_by = $3" in query, "folder ownership must include created_by"
    assert args == (folder, company, user_id)


@pytest.mark.asyncio
async def test_delete_journal_folder_owner_check_scopes_by_user(monkeypatch):
    from app.matcha.services import journal_service as svc
    user_id, company, folder = uuid4(), uuid4(), uuid4()
    conn = _FakeConn(user_id)
    monkeypatch.setattr(svc, "get_connection", lambda *a, **k: _FakeCtx(conn))

    await svc.delete_journal_folder(folder, company, user_id)

    _m, query, args = _first(conn, "EXISTS")
    assert "created_by = $3" in query
    assert args == (folder, company, user_id)


@pytest.mark.asyncio
async def test_create_journal_into_folder_validates_ownership(monkeypatch):
    """Filing a new note into a folder must verify the folder is the caller's
    own — otherwise a user could file into a coworker's notebook."""
    from app.matcha.services import journal_service as svc
    creator, company, folder = uuid4(), uuid4(), uuid4()
    conn = _FakeConn(creator)
    monkeypatch.setattr(svc, "get_connection", lambda *a, **k: _FakeCtx(conn))

    await svc.create_journal(creator, company, title="n", folder_id=folder)

    _m, query, args = _first(conn, "EXISTS")
    assert "created_by = $3" in query
    assert args == (folder, company, creator)


# ============================================================
# activity feed — recent_journals scoped per-user
# (projects/tasks/threads stay company-shared — that's intentional)
# ============================================================

@pytest.mark.asyncio
async def test_activity_feed_scopes_journals_by_user(monkeypatch):
    from app.matcha.routes.matcha_work import workspace as matcha_work
    company_id, user_id = uuid4(), uuid4()
    conn = _FakeConn(user_id)

    async def _fake_company(_cu):
        return company_id

    monkeypatch.setattr(matcha_work, "get_client_company_id", _fake_company)
    monkeypatch.setattr(matcha_work, "get_connection", lambda *a, **k: _FakeCtx(conn))

    await matcha_work.list_recent_activity_endpoint(
        current_user=SimpleNamespace(id=user_id)
    )

    _m, query, args = _first(conn, "recent_journals")
    # journals scoped to the caller (own + active collaborator)
    assert "j.created_by = $2" in query, "activity journals must scope by user"
    assert "mw_journal_collaborators" in query
    assert args == (company_id, user_id)
    # the company-shared surfaces are unchanged (still $1 = company)
    assert "p.company_id = $1" in query
    assert "t.company_id = $1" in query
    assert "th.company_id = $1" in query
