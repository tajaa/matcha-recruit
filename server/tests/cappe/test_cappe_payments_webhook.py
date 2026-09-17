"""Cappe Connect webhook — money only counts once Stripe says it cleared.

Before the 2026-09 audit `checkout.session.completed` alone marked an order
paid, released its digital deliverables and emailed a numbered receipt. Stripe
fires that event immediately with `payment_status: "unpaid"` for every
delayed-notification method (ACH debit, SEPA, Klarna...), which a Connect
Standard merchant enables on their own account, entirely outside our control.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_payments_webhook.py -q
"""
import asyncio
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.routes import payments as mod  # noqa: E402


# ── session_is_paid (pure) ────────────────────────────────────────────────────

@pytest.mark.parametrize("obj", [
    {"payment_status": "paid"},
    {"payment_status": "paid", "mode": "payment"},
])
def test_paid_session_is_paid(obj):
    assert mod.session_is_paid(obj) is True


@pytest.mark.parametrize("obj", [
    {"payment_status": "unpaid"},                      # ACH/SEPA/Klarna, pre-settlement
    {"payment_status": "no_payment_required"},         # not money for a storefront order
    {"payment_status": "unpaid", "mode": "payment"},
])
def test_unsettled_session_is_not_paid(obj):
    assert mod.session_is_paid(obj) is False


def test_payment_mode_without_a_status_is_not_paid():
    """`mode="payment"` always carries a payment_status; its absence means the
    payload is not one we can read, so it must not be treated as money."""
    assert mod.session_is_paid({"mode": "payment"}) is False


def test_non_payment_mode_without_a_status_is_honoured():
    assert mod.session_is_paid({"mode": "setup"}) is True
    assert mod.session_is_paid({}) is True


# ── event dispatch ────────────────────────────────────────────────────────────

class Recorder:
    def __init__(self):
        self.paid = []
        self.cancelled = []

    def install(self, monkeypatch):
        async def _paid(obj, event, background):
            self.paid.append(obj)
            return {"received": True, "status": "paid"}

        async def _cancel(etype, obj, event):
            self.cancelled.append((etype, obj))
            return {"received": True, "status": "cancelled"}

        monkeypatch.setattr(mod, "_mark_order_paid", _paid)
        monkeypatch.setattr(mod, "_cancel_unpaid_session", _cancel)
        return self


def _handle(etype, obj, event=None):
    return asyncio.run(mod._handle_connect_event(etype, obj, event or {}, None))


def test_completed_but_unpaid_does_not_mark_the_order_paid(monkeypatch):
    rec = Recorder().install(monkeypatch)
    out = _handle("checkout.session.completed", {"id": "cs_1", "payment_status": "unpaid"})
    assert out == {"received": True, "status": "unpaid"}
    assert rec.paid == []          # no receipt, no deliverable release
    assert rec.cancelled == []     # and not cancelled either — settlement may still come


def test_completed_and_paid_marks_the_order_paid(monkeypatch):
    rec = Recorder().install(monkeypatch)
    out = _handle("checkout.session.completed", {"id": "cs_1", "payment_status": "paid"})
    assert out == {"received": True, "status": "paid"}
    assert len(rec.paid) == 1


def test_async_settlement_marks_the_order_paid(monkeypatch):
    """The event that actually carries the money for a delayed method."""
    rec = Recorder().install(monkeypatch)
    out = _handle(
        "checkout.session.async_payment_succeeded", {"id": "cs_1", "payment_status": "paid"}
    )
    assert out == {"received": True, "status": "paid"}
    assert len(rec.paid) == 1


@pytest.mark.parametrize("etype", [
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
])
def test_failed_or_expired_session_releases_the_order(monkeypatch, etype):
    rec = Recorder().install(monkeypatch)
    out = _handle(etype, {"id": "cs_1"})
    assert out == {"received": True, "status": "cancelled"}
    assert rec.cancelled and rec.cancelled[0][0] == etype
    assert rec.paid == []


def test_unrelated_event_is_acknowledged_without_touching_an_order(monkeypatch):
    rec = Recorder().install(monkeypatch)
    assert _handle("payment_intent.succeeded", {"id": "pi_1"}) == {"received": True}
    assert rec.paid == [] and rec.cancelled == []


# ── cancel + restock ─────────────────────────────────────────────────────────

class FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, row):
        self._row = row
        self.fetchrow_args = None

    async def fetchrow(self, sql, *args):
        self.fetchrow_args = (sql, args)
        return self._row

    def transaction(self):
        return FakeTx()


class FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


def _patch_conn(monkeypatch, conn, restocks):
    monkeypatch.setattr(mod, "get_connection", lambda: FakeConnCtx(conn))

    async def _restock(_conn, *, site_id, order_id, reason):
        restocks.append((site_id, order_id, reason))

    monkeypatch.setattr(mod, "restock_order", _restock)


def test_expired_session_cancels_and_restocks_its_own_order(monkeypatch):
    conn = FakeConn({"id": "o-1", "site_id": "s-1"})
    restocks = []
    _patch_conn(monkeypatch, conn, restocks)

    out = asyncio.run(mod._cancel_unpaid_session(
        "checkout.session.expired",
        {"metadata": {"order_id": "11111111-1111-4111-8111-111111111111"}},
        {"account": "acct_1"},
    ))
    assert out == {"received": True}
    assert restocks == [("s-1", "o-1", "restock")]

    sql, args = conn.fetchrow_args
    # Idempotent, and aimed only at an order belonging to the event's own
    # connected account — the same guard the mark-paid UPDATE carries.
    assert "status = 'cancelled'" in sql
    assert "o.status = 'pending'" in sql
    assert "a.stripe_account_id = $2" in sql
    assert args[1] == "acct_1"


def test_already_settled_order_is_not_restocked(monkeypatch):
    """The status-guarded UPDATE matching nothing means the order is no longer
    pending; restocking anyway would hand back stock that was really sold."""
    conn = FakeConn(None)
    restocks = []
    _patch_conn(monkeypatch, conn, restocks)

    out = asyncio.run(mod._cancel_unpaid_session(
        "checkout.session.expired",
        {"metadata": {"order_id": "11111111-1111-4111-8111-111111111111"}},
        {"account": "acct_1"},
    ))
    assert out == {"received": True}
    assert restocks == []


@pytest.mark.parametrize("meta,event", [
    ({}, {"account": "acct_1"}),                                     # no order id
    ({"order_id": "not-a-uuid"}, {"account": "acct_1"}),             # unparseable
    ({"order_id": "11111111-1111-4111-8111-111111111111"}, {}),      # no connected account
])
def test_cancel_without_a_resolvable_order_touches_nothing(monkeypatch, meta, event):
    conn = FakeConn({"id": "o-1", "site_id": "s-1"})
    restocks = []
    _patch_conn(monkeypatch, conn, restocks)

    out = asyncio.run(mod._cancel_unpaid_session(
        "checkout.session.expired", {"metadata": meta}, event
    ))
    assert out == {"received": True}
    assert conn.fetchrow_args is None
    assert restocks == []


def test_collab_installment_is_left_for_manual_retry(monkeypatch):
    """A collab payment is not a storefront order: there is no stock to release
    and the brand can re-open checkout, so the webhook must not rewrite it."""
    conn = FakeConn({"id": "o-1", "site_id": "s-1"})
    restocks = []
    _patch_conn(monkeypatch, conn, restocks)

    out = asyncio.run(mod._cancel_unpaid_session(
        "checkout.session.expired",
        {"metadata": {"collab_payment_id": "cp-1"}},
        {"account": "acct_1"},
    ))
    assert out == {"received": True}
    assert conn.fetchrow_args is None
    assert restocks == []
