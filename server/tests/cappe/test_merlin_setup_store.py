"""`merlin_store.mutate_staged_actions`/`lock_conversation_actions` — the
staged-action queue's persistence layer, driven by a small fake asyncpg
connection (no real DB — see root CLAUDE.md's rule against DB-dependent
tests in the unit suite; the full concurrent-confirm race this queue's
locking exists for is covered by manual verification, not here).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_setup_store.py -q
"""
import asyncio
import json
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.merlin import store as merlin_store  # noqa: E402


class _FakeTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False


class _FakeConn:
    """Backs `staged_actions` with an in-memory JSON string, exactly like a
    real JSONB column round-trips through asyncpg."""

    def __init__(self, initial):
        self.row = {"staged_actions": json.dumps(initial) if initial is not None else None}
        self.writes = []

    def transaction(self):
        return _FakeTxn()

    async def fetchrow(self, _sql, _conversation_id):
        return dict(self.row)

    async def execute(self, _sql, _conversation_id, payload):
        self.writes.append(json.loads(payload))
        self.row["staged_actions"] = payload


def _entry(entry_id, status="proposed", created_at="2026-01-01T00:00:00+00:00"):
    return {
        "id": entry_id, "type": "create_page", "summary": f"entry {entry_id}", "payload": {},
        "status": status, "result": None, "message": None, "created_at": created_at, "executed_at": None,
    }


def test_lock_conversation_actions_decodes_a_json_string_row():
    conn = _FakeConn([_entry("a")])
    result = asyncio.run(merlin_store.lock_conversation_actions(conn, "convo-1"))
    assert result == [_entry("a")]


def test_lock_conversation_actions_returns_empty_list_for_a_null_column():
    conn = _FakeConn(None)
    result = asyncio.run(merlin_store.lock_conversation_actions(conn, "convo-1"))
    assert result == []


def test_mutate_staged_actions_prunes_oldest_proposed_past_the_cap():
    # 10 already at the cap (created_at ascending), plus one settled entry
    # that must never be counted against the cap or pruned.
    existing = [
        _entry(f"p{i}", created_at=f"2026-01-01T00:00:{i:02d}+00:00") for i in range(10)
    ]
    existing.append(_entry("settled", status="executed", created_at="2025-01-01T00:00:00+00:00"))
    conn = _FakeConn(existing)

    new_entry = _entry("new", created_at="2026-01-01T00:00:99+00:00")
    result = asyncio.run(
        merlin_store.mutate_staged_actions(conn, "convo-1", lambda cur: [*cur, new_entry])
    )

    proposed_ids = [e["id"] for e in result if e["status"] == "proposed"]
    assert len(proposed_ids) == merlin_store.MAX_PENDING_STAGED_ACTIONS
    assert "p0" not in proposed_ids, "the oldest proposed entry must be the one dropped"
    assert "new" in proposed_ids, "the entry just staged must survive the prune"
    assert any(e["id"] == "settled" for e in result), "a settled entry is never pruned"
    # The write actually persisted the pruned shape, not the pre-prune one.
    assert conn.writes[-1] == result


def test_mutate_staged_actions_leaves_a_short_queue_untouched():
    conn = _FakeConn([_entry("a"), _entry("b", status="dismissed")])
    result = asyncio.run(merlin_store.mutate_staged_actions(conn, "convo-1", lambda cur: cur))
    assert {e["id"] for e in result} == {"a", "b"}


def test_mutate_staged_actions_prunes_oldest_settled_past_the_total_cap():
    # 5 proposed (well under the pending cap) + settled entries past the
    # total cap — executed/dismissed/blocked entries are never touched by
    # MAX_PENDING_STAGED_ACTIONS, so without a total cap they'd grow forever.
    proposed = [_entry(f"p{i}", created_at=f"2026-02-01T00:00:{i:02d}+00:00") for i in range(5)]
    settled_count = merlin_store.MAX_STAGED_ACTIONS - len(proposed) + 5
    settled = [
        _entry(f"s{i}", status="executed", created_at=f"2026-01-01T00:00:{i:02d}+00:00")
        for i in range(settled_count)
    ]
    conn = _FakeConn([*proposed, *settled])

    result = asyncio.run(merlin_store.mutate_staged_actions(conn, "convo-1", lambda cur: cur))

    assert len(result) == merlin_store.MAX_STAGED_ACTIONS
    proposed_ids = {e["id"] for e in result if e["status"] == "proposed"}
    assert proposed_ids == {e["id"] for e in proposed}, "no proposed entry is ever dropped for a settled one"
    surviving_settled = [e for e in result if e["status"] != "proposed"]
    assert all(e["id"] not in {"s0", "s1", "s2", "s3", "s4"} for e in surviving_settled), (
        "the oldest settled entries must be the ones dropped"
    )
