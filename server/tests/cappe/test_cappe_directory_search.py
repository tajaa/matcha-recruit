"""`services/directory.refresh_site_search` — best-effort search-vector
refresh, callable from inside a caller's own open transaction (Merlin's
`execute_setup_action` for `create_product`).

The real bug this guards against is Postgres-level: a bare failing statement
inside an already-open transaction aborts the WHOLE transaction server-side
(subsequent statements fail with `InFailedSqlTransactionError` even though
Python's own try/except caught the original error) — real savepoint
rollback semantics aren't reproducible with a fake connection (see root
CLAUDE.md's rule against DB-mutating tests in the unit suite), so this only
guards the code SHAPE: the write must run inside its own `conn.transaction()`
(a SAVEPOINT when nested), not a bare `conn.execute`. Manual/integration
verification against real Postgres is what proves the deeper guarantee.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_directory_search.py -q
"""
import os

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.directory import refresh_site_search  # noqa: E402


class _FakeTxn:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        self._conn.txn_depth += 1
        return self

    async def __aexit__(self, *_a):
        self._conn.txn_depth -= 1
        return False  # never swallow here — matches asyncpg's real contract


class _FakeConn:
    def __init__(self, *, execute_raises=False):
        self.txn_depth = 0
        self.execute_raises = execute_raises
        self.executed_at_depth = None

    def transaction(self):
        return _FakeTxn(self)

    async def fetchval(self, *_a, **_k):
        return "photo-video"

    async def execute(self, *_a, **_k):
        self.executed_at_depth = self.txn_depth
        if self.execute_raises:
            raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_refresh_site_search_runs_the_write_inside_its_own_transaction():
    """Must be a SAVEPOINT (nested `conn.transaction()`), not a bare
    `conn.execute` — the property a Postgres-level test would confirm."""
    conn = _FakeConn()
    await refresh_site_search(conn, "site-1")
    assert conn.executed_at_depth == 1
    assert conn.txn_depth == 0  # closed back out


@pytest.mark.asyncio
async def test_refresh_site_search_never_raises_even_when_the_write_fails():
    conn = _FakeConn(execute_raises=True)
    await refresh_site_search(conn, "site-1")  # must not raise
    assert conn.txn_depth == 0


@pytest.mark.asyncio
async def test_refresh_site_search_nests_inside_a_callers_open_transaction():
    """Simulates `execute_setup_action`'s call site: already inside one
    `conn.transaction()` when `refresh_site_search` opens its own."""
    conn = _FakeConn(execute_raises=True)
    async with conn.transaction():
        assert conn.txn_depth == 1
        await refresh_site_search(conn, "site-1")  # swallows its own failure
        assert conn.txn_depth == 1, "the caller's transaction must still be open/unwound correctly"
    assert conn.txn_depth == 0
