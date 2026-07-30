"""`routes/merlin_setup.py` conversation-kind + staged-action-id guards.

Route handlers call `get_connection()` directly rather than taking a `conn`
param, so these monkeypatch `merlin_setup.get_connection` to hand back a fake
connection/pool — the same substring-matching `FakeConn` shape used by
`test_merlin_conversations.py`, extended with a no-op `transaction()` for the
one route (`execute_setup_staged_action`) that opens one; not exercised here.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_setup_router.py -q
"""
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.routes import merlin_setup  # noqa: E402

_NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


class _FakeConn:
    def __init__(self, *, fetchrow=None, fetch=None):
        self._fetchrow = fetchrow or {}
        self._fetch = fetch or {}

    @staticmethod
    def _match(table, sql):
        for needle, value in table.items():
            if needle in sql:
                return value
        return None

    async def fetchrow(self, sql, *args):
        return self._match(self._fetchrow, sql)

    async def fetch(self, sql, *args):
        return self._match(self._fetch, sql) or []

    async def execute(self, sql, *args):
        return "OK"


def _patch_connection(monkeypatch, conn):
    @asynccontextmanager
    async def _fake_get_connection():
        yield conn

    monkeypatch.setattr(merlin_setup, "get_connection", _fake_get_connection)


class _Account:
    def __init__(self, account_id):
        self.id = account_id


def _convo_row(*, kind, account_id, convo_id, staged_actions=None):
    return {
        "id": convo_id, "account_id": account_id, "site_id": uuid4(), "page_id": None,
        "kind": kind, "staged_actions": json.dumps(staged_actions) if staged_actions is not None else None,
        "title": "chat", "created_at": _NOW, "updated_at": _NOW,
    }


@pytest.mark.asyncio
async def test_get_setup_conversation_404s_for_a_page_kind_conversation(monkeypatch):
    """A page-editor conversation id must not be readable through the setup
    endpoint — before this fix it returned 200 with `staged_actions: None`."""
    account_id, convo_id = uuid4(), uuid4()
    conn = _FakeConn(
        fetchrow={"FROM cappe_merlin_conversations": _convo_row(kind="page", account_id=account_id, convo_id=convo_id)},
    )
    _patch_connection(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc_info:
        await merlin_setup.get_setup_conversation(convo_id, account=_Account(account_id))
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_setup_conversation_succeeds_for_a_setup_kind_conversation(monkeypatch):
    account_id, convo_id = uuid4(), uuid4()
    conn = _FakeConn(
        fetchrow={"FROM cappe_merlin_conversations": _convo_row(kind="setup", account_id=account_id, convo_id=convo_id)},
    )
    _patch_connection(monkeypatch, conn)

    result = await merlin_setup.get_setup_conversation(convo_id, account=_Account(account_id))
    assert result["id"] == convo_id


@pytest.mark.asyncio
async def test_dismiss_staged_action_404s_for_an_unknown_action_id(monkeypatch):
    """Before this fix, dismissing a stale/typo'd action id returned 200 with
    an unchanged queue — `dismiss_entry` is a silent no-op on a missing id."""
    account_id, convo_id = uuid4(), uuid4()
    conn = _FakeConn(
        fetchrow={"FROM cappe_merlin_conversations": _convo_row(
            kind="setup", account_id=account_id, convo_id=convo_id,
            staged_actions=[{"id": "real-id", "status": "proposed"}],
        )},
    )
    _patch_connection(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc_info:
        await merlin_setup.dismiss_setup_staged_action(
            convo_id, "not-the-real-id", account=_Account(account_id)
        )
    assert exc_info.value.status_code == 404
