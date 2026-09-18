"""Cappe abandoned-order reaper — releases what a dead checkout is holding,
and never an order somebody can still pay for.

Run from server/:  ./venv/bin/python -m pytest tests/workers/test_cappe_order_reaper.py -q
"""
import asyncio
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402
from app.workers.tasks import cappe_order_reaper as mod  # noqa: E402


def _cand(oid="o-1", acct="acct_1", session="cs_1"):
    return {"id": oid, "site_id": "s-1", "stripe_session_id": session, "stripe_account_id": acct}


class FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    """`candidates` is the sweep; `claims` the per-order status-guarded UPDATE
    (None = a webhook won the race)."""

    def __init__(self, candidates, claims):
        self._candidates = candidates
        self._claims = list(claims)
        self.fetch_args = None
        self.fetchrow_sql = []
        self.executed = []
        self.closed = False

    async def fetch(self, sql, *args):
        self.fetch_args = (sql, args)
        return self._candidates

    async def fetchrow(self, sql, *args):
        self.fetchrow_sql.append(sql)
        return self._claims.pop(0)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    def transaction(self):
        return FakeTx()

    async def close(self):
        self.closed = True


class FakeStripe:
    """session id → resulting state, or an exception to raise."""

    def __init__(self, states=None, sessions=None):
        self.states = states or {}
        self.sessions = sessions or {}
        self.expired = []

    async def retrieve_checkout_session(self, account_id, session_id):
        return self.sessions.get(session_id, {"payment_status": "unpaid"})

    async def expire_checkout_session(self, account_id, session_id):
        self.expired.append((account_id, session_id))
        outcome = self.states.get(session_id, "expired")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _patch(monkeypatch, conn, *, enabled=True, cap=100, stripe=None, log=None):
    async def _get_conn():
        return conn

    async def _setting(_conn, key):
        assert key == "cappe_order_reaper"
        return None if enabled is None else {"enabled": enabled, "max_per_cycle": cap}

    async def _restock(_conn, *, site_id, order_id, reason):
        if log is not None:
            log.append(("restock", order_id, reason))

    async def _release(_conn, *, order_id):
        if log is not None:
            log.append(("bookings", order_id))
        return 0

    stripe = stripe or FakeStripe()
    monkeypatch.setattr(mod, "get_db_connection", _get_conn)
    monkeypatch.setattr(mod, "scheduler_settings_row", _setting)
    monkeypatch.setattr(mod, "restock_order", _restock)
    monkeypatch.setattr(mod, "release_order_bookings", _release)
    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: stripe)
    return stripe


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


def test_only_stripe_backed_pending_orders_past_the_window_are_swept(monkeypatch):
    conn = FakeConn([], [])
    _patch(monkeypatch, conn, cap=42)
    asyncio.run(mod._run())
    sql, args = conn.fetch_args
    assert "o.status = 'pending'" in sql
    # An owner-created pending order (no Stripe session) must never be reaped.
    assert "o.stripe_session_id IS NOT NULL" in sql
    assert f"NOW() - INTERVAL '{mod.ABANDONED_AFTER}'" in sql
    # The connected account is needed to close the session on the right account.
    assert "a.stripe_account_id" in sql
    assert args == (42,)


# ── the money rule: close the payment page BEFORE releasing the order ────────

def test_session_is_expired_before_the_order_is_released(monkeypatch):
    """A Checkout Session stays payable for 24h — far longer than the 2h window.
    Cancelling the order under an open session is how a buyer gets charged for
    an order we already threw away."""
    log = []
    conn = FakeConn([_cand()], [{"id": "o-1", "site_id": "s-1"}])
    stripe = _patch(monkeypatch, conn, log=log)

    out = asyncio.run(mod._run())

    assert stripe.expired == [("acct_1", "cs_1")]
    assert out == {"candidates": 1, "released": 1, "settling": 0, "reconciled": 0}
    assert log == [("restock", "o-1", "restock"), ("bookings", "o-1")]


def test_completed_checkout_is_never_cancelled(monkeypatch):
    """`complete` = the buyer finished checkout: paid with a late webhook, or a
    delayed method (ACH, SEPA) that settles days later. The webhook decides it."""
    log = []
    conn = FakeConn([_cand()], [])
    _patch(monkeypatch, conn, stripe=FakeStripe({"cs_1": "complete"}), log=log)

    out = asyncio.run(mod._run())

    assert out == {"candidates": 1, "released": 0, "settling": 1, "reconciled": 0}
    assert log == []
    assert conn.fetchrow_sql == []     # no order UPDATE was attempted
    # Sent to the back of the sweep so it cannot starve newer abandoned carts.
    assert [a for _, a in conn.executed] == [("o-1",)]


def test_paid_session_with_a_lost_webhook_is_reconciled(monkeypatch):
    """The `completed` webhook is the only thing that moves a paid order on. If
    it was dropped the order sat `pending` for ever — and, being oldest, was
    re-asked about on every run."""
    log, receipts = [], []
    conn = FakeConn([_cand()], [{"id": "o-1", "site_id": "s-1"}])
    stripe = FakeStripe(
        {"cs_1": "complete"},
        {"cs_1": {"payment_status": "paid", "payment_intent": "pi_9",
                  "shipping_details": {"name": "Buyer"}}},
    )
    _patch(monkeypatch, conn, stripe=stripe, log=log)

    async def _receipt(_conn, order_id, site_id):
        receipts.append((order_id, site_id))

    monkeypatch.setattr(mod, "issue_receipt_on", _receipt)
    out = asyncio.run(mod._run())

    assert out == {"candidates": 1, "released": 0, "settling": 0, "reconciled": 1}
    assert "status = 'paid'" in conn.fetchrow_sql[0] and "status = 'pending'" in conn.fetchrow_sql[0]
    assert receipts == [("o-1", "s-1")]
    assert log == []                   # paid stock is NOT handed back


def test_sweep_rotates_by_last_look_not_age(monkeypatch):
    conn = FakeConn([], [])
    _patch(monkeypatch, conn)
    asyncio.run(mod._run())
    assert "ORDER BY o.updated_at ASC" in conn.fetch_args[0]


def test_stripe_being_unreachable_leaves_the_order_for_next_cycle(monkeypatch):
    log = []
    conn = FakeConn([_cand()], [])
    _patch(monkeypatch, conn, stripe=FakeStripe({"cs_1": CappeStripeError("timeout")}), log=log)

    out = asyncio.run(mod._run())

    # Not knowing whether the page is still payable is a reason NOT to release.
    assert out == {"candidates": 1, "released": 0, "settling": 0, "reconciled": 0}
    assert log == []


def test_order_without_a_connected_account_is_skipped(monkeypatch):
    log = []
    conn = FakeConn([_cand(acct=None)], [])
    stripe = _patch(monkeypatch, conn, log=log)
    out = asyncio.run(mod._run())
    assert out["released"] == 0
    assert stripe.expired == [] and log == []


def test_booking_slots_are_released_with_the_stock(monkeypatch):
    """Stock alone coming back left the appointment slot blocked for nobody."""
    log = []
    conn = FakeConn([_cand()], [{"id": "o-1", "site_id": "s-1"}])
    _patch(monkeypatch, conn, log=log)
    asyncio.run(mod._run())
    assert ("bookings", "o-1") in log


# ── idempotency + isolation ──────────────────────────────────────────────────

def test_order_already_released_by_the_webhook_is_skipped(monkeypatch):
    log = []
    conn = FakeConn([_cand()], [None])
    _patch(monkeypatch, conn, log=log)
    assert asyncio.run(mod._run()) == {"candidates": 1, "released": 0, "settling": 0, "reconciled": 0}
    assert log == []


def test_one_failing_order_does_not_abort_the_cycle(monkeypatch):
    released = []
    conn = FakeConn(
        [_cand("o-1", session="cs_1"), _cand("o-2", session="cs_2")],
        [{"id": "o-1", "site_id": "s-1"}, {"id": "o-2", "site_id": "s-1"}],
    )
    _patch(monkeypatch, conn)

    async def _restock(_conn, *, site_id, order_id, reason):
        if order_id == "o-1":
            raise RuntimeError("restock blew up")
        released.append(order_id)

    monkeypatch.setattr(mod, "restock_order", _restock)
    out = asyncio.run(mod._run())
    assert out["candidates"] == 2 and out["released"] == 1
    assert released == ["o-2"]


def test_connection_is_closed_even_when_the_sweep_raises(monkeypatch):
    conn = FakeConn([], [])
    _patch(monkeypatch, conn)

    async def _boom(_conn, key):
        raise RuntimeError("scheduler lookup failed")

    monkeypatch.setattr(mod, "scheduler_settings_row", _boom)
    with pytest.raises(RuntimeError):
        asyncio.run(mod._run())
    assert conn.closed
