"""Merlin conversation persistence (migration zzzzcappe22).

Merlin's transcript moved from localStorage into `cappe_merlin_conversations` /
`cappe_merlin_messages`. These tests cover the store's pure behavior and the
route's ownership gate against a fake asyncpg connection — no live database is
touched (repo rule: DB-mutating tests are never auto-run).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_conversations.py -q
"""
import json
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.merlin import store as merlin_store  # noqa: E402

_NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


class FakeConn:
    """Minimal asyncpg stand-in: canned results keyed by a SQL substring.

    Records every statement so a test can assert what was (or wasn't) written —
    the ownership tests care that no write is attempted after a failed check.
    """

    def __init__(self, *, fetch=None, fetchrow=None, fetchval=None):
        self._fetch = fetch or {}
        self._fetchrow = fetchrow or {}
        self._fetchval = fetchval or {}
        self.statements: list[str] = []

    @staticmethod
    def _match(table, sql):
        for needle, value in table.items():
            if needle in sql:
                return value
        return None

    async def fetch(self, sql, *args):
        self.statements.append(sql)
        return self._match(self._fetch, sql) or []

    async def fetchrow(self, sql, *args):
        self.statements.append(sql)
        return self._match(self._fetchrow, sql)

    async def fetchval(self, sql, *args):
        self.statements.append(sql)
        return self._match(self._fetchval, sql)

    async def execute(self, sql, *args):
        self.statements.append(sql)
        return "OK"


# --- titles ------------------------------------------------------------------

def test_title_from_message_collapses_whitespace_and_truncates():
    """A pasted multi-line brief must not become a title with newlines in it."""
    assert merlin_store.title_from_message("make the\n  hero darker") == "make the hero darker"
    assert merlin_store.title_from_message("x" * 200) == "x" * 60
    assert merlin_store.title_from_message("   ") == "New conversation"


# --- history -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_history_rebuilds_ops_summary_from_stored_results():
    """The client used to resend `ops_summary` with every turn. Now the server
    rebuilds it from the stored result chips, so the model still sees what each
    past turn actually changed."""
    conn = FakeConn(fetch={
        "FROM cappe_merlin_messages": [
            {"role": "user", "content": "make the hero darker", "results": None,
             "created_at": _NOW, "id": uuid4()},
            {"role": "assistant", "content": "Done.",
             "results": json.dumps([
                 {"ok": True, "summary": "Edited Hero — heading"},
                 {"ok": False, "summary": "Skipped — section gone"},
             ]),
             "created_at": _NOW, "id": uuid4()},
        ],
    })
    history = await merlin_store.load_history(conn, uuid4())

    assert [t["role"] for t in history] == ["user", "assistant"]
    assert "ops_summary" not in history[0]  # a user turn has no ops
    assert history[1]["ops_summary"] == "Edited Hero — heading; Skipped — section gone"


@pytest.mark.asyncio
async def test_load_history_is_capped_to_the_prompt_window():
    """The transcript can grow without bound now that it persists; the prompt
    window can't grow with it."""
    conn = FakeConn()
    await merlin_store.load_history(conn, uuid4())
    # MESSAGES, not turns — 20 messages is ~10 actual exchanges (see
    # HISTORY_MESSAGES' docstring for the renaming-fixed-a-no-op history).
    assert merlin_store.HISTORY_MESSAGES == 20
    # The LIMIT is a bound parameter, so assert the query shape carries one.
    assert "LIMIT $2" in conn.statements[0]


@pytest.mark.asyncio
async def test_get_messages_distinguishes_absent_from_empty_json():
    """`results`/`steps`/`attachments`/`ops` are nullable. An absent agent
    trace must stay None — collapsing it to [] would render as "this turn
    did nothing"."""
    conn = FakeConn(fetch={
        "FROM cappe_merlin_messages": [
            {"id": uuid4(), "role": "assistant", "content": "Done.",
             "results": json.dumps([{"ok": True, "summary": "Edited Hero"}]),
             "steps": None, "attachments": None, "ops": None, "tier": "max", "created_at": _NOW},
        ],
    })
    [m] = await merlin_store.get_messages(conn, uuid4())

    assert m["results"] == [{"ok": True, "summary": "Edited Hero"}]
    assert m["steps"] is None
    assert m["attachments"] is None
    assert m["ops"] is None


@pytest.mark.asyncio
async def test_get_messages_returns_ops_when_stored():
    """A turn whose `ops` were persisted (migration zzzzcappe24) — what the
    panel's "apply these changes" recovery path reads back."""
    conn = FakeConn(fetch={
        "FROM cappe_merlin_messages": [
            {"id": uuid4(), "role": "assistant", "content": "Darkened the hero.",
             "results": None, "steps": None, "attachments": None,
             "ops": json.dumps([{"op": "set_field", "block": "b1", "path": "heading", "value": "New"}]),
             "tier": "max", "created_at": _NOW},
        ],
    })
    [m] = await merlin_store.get_messages(conn, uuid4())

    assert m["ops"] == [{"op": "set_field", "block": "b1", "path": "heading", "value": "New"}]
    assert m["results"] is None  # never applied — this IS the "unrecovered turn" shape


# --- ownership ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_owned_conversation_404s_for_another_account():
    """Missing and forbidden are indistinguishable, matching get_owned_site —
    otherwise the id space leaks across accounts."""
    conn = FakeConn(fetchrow={})  # the account-scoped SELECT finds nothing
    with pytest.raises(HTTPException) as exc:
        await merlin_store.get_owned_conversation(conn, uuid4(), uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_add_message_serializes_jsonb_and_bumps_the_conversation():
    """asyncpg registers no JSONB codec here, so every write goes through
    json.dumps — and the conversation's updated_at drives the panel's
    most-recently-used ordering."""
    conn = FakeConn(fetchrow={
        "INSERT INTO cappe_merlin_messages": {
            "id": uuid4(), "role": "assistant", "content": "Done.",
            "results": json.dumps([{"ok": True, "summary": "Edited Hero"}]),
            "steps": None, "attachments": None, "ops": None, "tier": "lite", "created_at": _NOW,
        },
    })
    stored = await merlin_store.add_message(
        conn, uuid4(), role="assistant", content="Done.",
        results=[{"ok": True, "summary": "Edited Hero"}], tier="lite",
    )

    assert stored["results"] == [{"ok": True, "summary": "Edited Hero"}]
    assert any("UPDATE cappe_merlin_conversations SET updated_at" in s for s in conn.statements)


@pytest.mark.asyncio
async def test_add_message_persists_ops_for_recovery():
    """`ops` (migration zzzzcappe24) is what a disconnected agent turn needs
    to be recoverable — persisted on the assistant message alongside the
    existing steps/results traces."""
    conn = FakeConn(fetchrow={
        "INSERT INTO cappe_merlin_messages": {
            "id": uuid4(), "role": "assistant", "content": "Darkened the hero.",
            "results": None, "steps": None, "attachments": None,
            "ops": json.dumps([{"op": "set_field", "block": "b1", "path": "heading", "value": "New"}]),
            "tier": "max", "created_at": _NOW,
        },
    })
    stored = await merlin_store.add_message(
        conn, uuid4(), role="assistant", content="Darkened the hero.",
        ops=[{"op": "set_field", "block": "b1", "path": "heading", "value": "New"}], tier="max",
    )

    assert stored["ops"] == [{"op": "set_field", "block": "b1", "path": "heading", "value": "New"}]
    insert_sql = next(s for s in conn.statements if "INSERT INTO cappe_merlin_messages" in s)
    assert "ops" in insert_sql


# --- route wiring ------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_conversation_opens_one_titled_from_the_message():
    """First turn of a fresh conversation: the row is created here so the
    response can hand its id back, even if the model call then degrades."""
    from app.cappe.routes.merlin import _resolve_conversation

    site_id, page_id, account_id = uuid4(), uuid4(), uuid4()
    conn = FakeConn(
        fetchval={"FROM cappe_pages": 1},
        fetchrow={"INSERT INTO cappe_merlin_conversations": {
            "id": uuid4(), "title": "make the hero darker",
            "created_at": _NOW, "updated_at": _NOW,
        }},
    )

    class _Body:
        conversation_id = None
        message = "make the hero darker"

    class _Account:
        id = account_id

    convo = await _resolve_conversation(
        conn, body=_Body(), site={"id": site_id}, page_uuid=page_id, account=_Account()
    )
    assert convo["title"] == "make the hero darker"


@pytest.mark.asyncio
async def test_resolve_conversation_returns_none_when_the_page_is_gone():
    """A page deleted mid-session leaves nothing to record against. The turn
    still runs — it just isn't persisted — rather than 4xxing an edit that
    would otherwise work."""
    from app.cappe.routes.merlin import _resolve_conversation

    conn = FakeConn(fetchval={})  # the page/site check finds nothing

    class _Body:
        conversation_id = None
        message = "make the hero darker"

    class _Account:
        id = uuid4()

    convo = await _resolve_conversation(
        conn, body=_Body(), site={"id": uuid4()}, page_uuid=uuid4(), account=_Account()
    )
    assert convo is None
    assert not any("INSERT INTO cappe_merlin_conversations" in s for s in conn.statements)


@pytest.mark.asyncio
async def test_resolve_conversation_rejects_a_setup_kind_conversation():
    """A dashboard setup-concierge conversation (`kind='setup'`, `page_id`
    NULL) named on a page-editor `/merlin/chat` request must 404, even when
    the request's own `page_id` is absent — otherwise the page-editor turn
    loads the setup transcript as history and persists into it (see the
    `_resolve_conversation` docstring)."""
    from app.cappe.routes.merlin import _resolve_conversation

    account_id, convo_id = uuid4(), uuid4()
    conn = FakeConn(
        fetchrow={"WHERE id = $1 AND account_id = $2": {
            "id": convo_id, "account_id": account_id, "site_id": uuid4(), "page_id": None,
            "kind": "setup", "staged_actions": None, "title": "setup chat",
            "created_at": _NOW, "updated_at": _NOW,
        }},
    )

    class _Body:
        conversation_id = convo_id
        message = "add a promo banner"

    class _Account:
        id = account_id

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_conversation(
            conn, body=_Body(), site={"id": uuid4()}, page_uuid=None, account=_Account()
        )
    assert exc_info.value.status_code == 404


def test_parse_page_id_degrades_rather_than_raising():
    """`page_id` predates persistence and rides in as a free string. A
    non-UUID means "can't record this turn", not "reject the edit"."""
    from app.cappe.routes.merlin import _parse_page_id

    good = uuid4()
    assert _parse_page_id(str(good)) == good
    assert _parse_page_id("not-a-uuid") is None
    assert _parse_page_id(None) is None


def test_recent_history_tail_builds_a_recap_for_the_router():
    """route_tier's classifier previously ran on the bare message with no
    context at all — this is what now feeds its `history_tail`, built from
    the client-resent `body.history` (available before any DB call)."""
    from app.cappe.routes.merlin import _recent_history_tail

    class _Turn:
        def __init__(self, role, content):
            self.role, self.content = role, content

    history = [
        _Turn("user", "make the hero darker"),
        _Turn("assistant", "Darkened the hero background."),
        _Turn("user", "now match the others"),
    ]
    tail = _recent_history_tail(history, n=2)
    assert "Darkened the hero background." in tail
    assert "match the others" in tail
    assert "make the hero darker" not in tail  # trimmed to the last 2 turns


def test_recent_history_tail_empty_history_is_none():
    from app.cappe.routes.merlin import _recent_history_tail

    assert _recent_history_tail([]) is None
