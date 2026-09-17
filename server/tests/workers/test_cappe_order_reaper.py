"""Cappe abandoned-order reaper — releases inventory a dead checkout is holding.

Run from server/:  ./venv/bin/python -m pytest tests/workers/test_cappe_order_reaper.py -q
"""
import asyncio
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.workers.tasks import cappe_order_reaper as mod  # noqa: E402


class FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    """Minimal asyncpg stand-in: `candidates` is the abandoned-order sweep,
    `claims` is the per-order status-guarded UPDATE (None = someone else won)."""

    def __init__(self, candidates, claims):
        self._candidates = candidates
        self._claims = list(claims)
        self.fetch_args = None
        self.closed = False

    async def fetch(self, sql, *args):
        self.fetch_args = (sql, args)
        return self._candidates

    async def fetchrow(self, sql, *args):
        return self._claims.pop(0)

    def transaction(self):
        return FakeTx()

    async def close(self):
        self.closed = True


def _patch(monkeypatch, conn, *, enabled=True, cap=100, restocks=None):
    async def _get_conn():
        return conn

    async def _setting(_conn, key):
        assert key == "cappe_order_reaper"
        return None if enabled is None else {"enabled": enabled, "max_per_cycle": cap}

    async def _restock(_conn, *, site_id, order_id, reason):
        if restocks is not None:
            restocks.append((site_id, order_id, reason))

    monkeypatch.setattr(mod, "get_db_connection", _get_conn)
    monkeypatch.setattr(mod, "scheduler_settings_row", _setting)
    monkeypatch.setattr(mod, "restock_order", _restock)


def test_disabled_scheduler_does_nothing(monkeypatch):
    conn = FakeConn([], [])
    _patch(monkeypatch, conn, enabled=False)
    assert asyncio.run(mod._run()) == {"skipped": True}
    assert conn.fetch_args is None
    assert conn.closed


def test_missing_scheduler_row_does_nothing(monkeypatch):
    conn = FakeConn([], [])
    _patch(monkeypatch, conn, enabled=None)
    assert asyncio.run(mod._run()) == {"skipped": True}


def test_abandoned_order_is_cancelled_and_restocked(monkeypatch):
    restocks = []
    conn = FakeConn(
        candidates=[{"id": "o-1", "site_id": "s-1"}],
        claims=[{"id": "o-1", "site_id": "s-1"}],
    )
    _patch(monkeypatch, conn, restocks=restocks)
    assert asyncio.run(mod._run()) == {"candidates": 1, "released": 1}
    assert restocks == [("s-1", "o-1", "restock")]


def test_only_stripe_backed_pending_orders_past_the_window_are_swept(monkeypatch):
    conn = FakeConn([], [])
    _patch(monkeypatch, conn, cap=42)
    asyncio.run(mod._run())
    sql, args = conn.fetch_args
    assert "status = 'pending'" in sql
    # An owner-created pending order (no Stripe session) must never be reaped.
    assert "stripe_session_id IS NOT NULL" in sql
    assert f"NOW() - INTERVAL '{mod.ABANDONED_AFTER}'" in sql
    assert args == (42,)


def test_order_already_released_by_the_webhook_is_skipped(monkeypatch):
    """The status-guarded UPDATE returning None means a webhook won the race —
    restocking anyway would double-count the stock back."""
    restocks = []
    conn = FakeConn(candidates=[{"id": "o-1", "site_id": "s-1"}], claims=[None])
    _patch(monkeypatch, conn, restocks=restocks)
    assert asyncio.run(mod._run()) == {"candidates": 1, "released": 0}
    assert restocks == []


def test_one_failing_order_does_not_abort_the_cycle(monkeypatch):
    restocks = []
    conn = FakeConn(
        candidates=[{"id": "o-1", "site_id": "s-1"}, {"id": "o-2", "site_id": "s-1"}],
        claims=[{"id": "o-1", "site_id": "s-1"}, {"id": "o-2", "site_id": "s-1"}],
    )

    async def _restock(_conn, *, site_id, order_id, reason):
        if order_id == "o-1":
            raise RuntimeError("restock blew up")
        restocks.append(order_id)

    _patch(monkeypatch, conn)
    monkeypatch.setattr(mod, "restock_order", _restock)
    assert asyncio.run(mod._run()) == {"candidates": 2, "released": 1}
    assert restocks == ["o-2"]


def test_connection_is_closed_even_when_the_sweep_raises(monkeypatch):
    conn = FakeConn([], [])

    async def _boom(_conn, key):
        raise RuntimeError("scheduler lookup failed")

    _patch(monkeypatch, conn)
    monkeypatch.setattr(mod, "scheduler_settings_row", _boom)
    with pytest.raises(RuntimeError):
        asyncio.run(mod._run())
    assert conn.closed
