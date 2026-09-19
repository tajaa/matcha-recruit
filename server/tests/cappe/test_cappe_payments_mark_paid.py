"""Cappe Connect webhook — the mark-paid path, executed end to end.

`test_cappe_payments_webhook.py` pins the event dispatch and the release path.
This module drives `_mark_order_paid` itself through a scripted connection:
the pending→paid UPDATE, the unmatched-order retry, shipping recovery, the
collab-installment branch, and the capability refresh on `account.updated`.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_payments_mark_paid.py -q
"""
import asyncio
import logging
import os
from types import SimpleNamespace

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.routes import payments as mod  # noqa: E402
from app.cappe.services import collab as collab_svc  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

ORDER_ID = "11111111-1111-4111-8111-111111111111"
COLLAB_ID = "22222222-2222-4222-8222-222222222222"


class ScriptedConn:
    """Answers fetchrow/fetchval from queues and records every statement."""

    def __init__(self, rows=(), vals=()):
        self.rows, self.vals = list(rows), list(vals)
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        return self.rows.pop(0)

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        return self.vals.pop(0)

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        return "UPDATE 1"


class ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args):
        self.tasks.append((fn.__name__, args))


def _use(monkeypatch, conn):
    monkeypatch.setattr(mod, "get_connection", lambda: ConnCtx(conn))
    return conn


def _run(obj, event, bg=None):
    return asyncio.run(mod._mark_order_paid(obj, event, bg or Background()))


# ── storefront orders ────────────────────────────────────────────────────────

def test_pending_order_is_marked_paid_and_receipted(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn(rows=[{
        "id": "o-1", "site_id": "s-1", "customer_email": "buyer@example.com",
        "customer_name": "Buyer",
    }]))
    bg = Background()
    out = _run(
        {"id": "cs_1", "payment_intent": "pi_1",
         "shipping_details": {"name": "Buyer", "address": {"city": "Oakland"}},
         "metadata": {"order_id": ORDER_ID, "platform_fee_cents": "150"}},
        {"account": "acct_1"},
        bg,
    )
    assert out == {"received": True}
    _, sql, args = conn.calls[0]
    assert "o.status = 'pending'" in sql and "a.stripe_account_id = $4" in sql
    assert args[1] == "pi_1" and args[2] == 150 and args[3] == "acct_1"
    assert '"city": "Oakland"' in args[4]
    assert bg.tasks == [("issue_receipt_for_paid_order", ("o-1", "s-1"))]


def test_unreadable_fee_is_ignored_not_fatal(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn(rows=[{"id": "o-1", "site_id": "s-1"}]))
    _run(
        {"id": "cs_1", "metadata": {"order_id": ORDER_ID, "platform_fee_cents": "abc"}},
        {"account": "acct_1"},
    )
    assert conn.calls[0][2][2] is None   # COALESCE keeps the stored fee


def test_shipping_is_recovered_from_the_session_when_the_event_omits_it(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn(rows=[{"id": "o-1", "site_id": "s-1"}]))
    seen = []

    class Stripe:
        async def retrieve_checkout_session(self, account_id, session_id):
            seen.append((account_id, session_id))
            return {"collected_information": {"shipping_details": {"name": "Buyer"}}}

    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: Stripe())
    _run(
        {"id": "cs_1", "shipping_cost": {"amount_total": 500},
         "metadata": {"order_id": ORDER_ID}},
        {"account": "acct_1"},
    )
    assert seen == [("acct_1", "cs_1")]
    assert '"name": "Buyer"' in conn.calls[0][2][4]


def test_shipping_lookup_failure_never_blocks_marking_paid(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn(rows=[{"id": "o-1", "site_id": "s-1"}]))

    class Stripe:
        async def retrieve_checkout_session(self, account_id, session_id):
            raise CappeStripeError("stripe down")

    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: Stripe())
    bg = Background()
    _run(
        {"id": "cs_1", "shipping_cost": {"amount_total": 500},
         "metadata": {"order_id": ORDER_ID}},
        {"account": "acct_1"},
        bg,
    )
    assert conn.calls[0][2][4] is None
    assert [t[0] for t in bg.tasks] == ["issue_receipt_for_paid_order"]


def test_unmatched_order_releases_the_event_for_retry(monkeypatch):
    """No row for this order on this account yet: 503 so Stripe redelivers,
    rather than acknowledging money we have not recorded."""
    _use(monkeypatch, ScriptedConn(rows=[None], vals=[None]))
    with pytest.raises(HTTPException) as exc:
        _run({"id": "cs_1", "metadata": {"order_id": ORDER_ID}}, {"account": "acct_1"})
    assert exc.value.status_code == 503


def test_unparseable_order_id_touches_nothing(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn())
    assert _run({"id": "cs_1", "metadata": {"order_id": "nope"}}, {"account": "acct_1"}) == {
        "received": True
    }
    assert conn.calls == []


def test_order_without_an_event_account_is_not_updated(monkeypatch, caplog):
    conn = _use(monkeypatch, ScriptedConn())
    with caplog.at_level(logging.WARNING, logger=mod.logger.name):
        _run({"id": "cs_1", "metadata": {"order_id": ORDER_ID}}, {})
    assert conn.calls == []
    assert any("no event account" in r.getMessage() for r in caplog.records)


# ── collab installments ──────────────────────────────────────────────────────

def _collab_obj(amount_total=5000):
    return {"id": "cs_c", "payment_intent": "pi_c", "amount_total": amount_total,
            "metadata": {"collab_payment_id": COLLAB_ID}}


def test_on_accept_installment_activates_the_offer_and_notifies(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn(rows=[{
        "offer_id": "off-1", "trigger": "on_accept", "label": "Deposit", "amount_cents": 5000,
    }]))

    async def _done(_conn, offer_id):
        return True

    monkeypatch.setattr(collab_svc, "check_completion", _done)
    bg = Background()
    assert _run(_collab_obj(), {"account": "acct_c"}, bg) == {"received": True}

    kinds = [c[0] for c in conn.calls]
    assert kinds == ["fetchrow", "execute"]
    assert "status = 'active'" in conn.calls[1][1]
    assert [t[0] for t in bg.tasks] == ["_notify_collab_paid", "_notify_collab_completed"]


def test_installment_total_mismatch_is_logged(monkeypatch, caplog):
    _use(monkeypatch, ScriptedConn(rows=[{
        "offer_id": "off-1", "trigger": "on_delivery", "label": "Final", "amount_cents": 5000,
    }]))

    async def _not_done(_conn, offer_id):
        return False

    monkeypatch.setattr(collab_svc, "check_completion", _not_done)
    bg = Background()
    with caplog.at_level(logging.WARNING, logger=mod.logger.name):
        _run(_collab_obj(amount_total=4200), {"account": "acct_c"}, bg)
    assert any("!= stored" in r.getMessage() for r in caplog.records)
    assert [t[0] for t in bg.tasks] == ["_notify_collab_paid"]


def test_unmatched_installment_is_an_error_for_manual_reconciliation(monkeypatch, caplog):
    _use(monkeypatch, ScriptedConn(rows=[None]))
    bg = Background()
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        _run(_collab_obj(), {"account": "acct_c"}, bg)
    assert bg.tasks == []
    assert any("manual reconciliation" in r.getMessage() for r in caplog.records)


def test_unparseable_collab_id_touches_nothing(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn())
    _run({"id": "cs_c", "metadata": {"collab_payment_id": "nope"}}, {"account": "acct_c"})
    assert conn.calls == []


# ── account.updated + onboarding link ────────────────────────────────────────

def test_account_updated_refreshes_capability_flags(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn())
    out = asyncio.run(mod._handle_connect_event(
        "account.updated",
        {"id": "acct_1", "charges_enabled": True, "details_submitted": False},
        {},
        None,
    ))
    assert out == {"received": True}
    _, sql, args = conn.calls[0]
    assert "stripe_charges_enabled" in sql
    assert args == (True, False, "acct_1")


def test_onboarding_link_falls_back_to_our_dashboard(monkeypatch):
    """A caller-supplied off-origin return URL is dropped for our own."""
    _use(monkeypatch, ScriptedConn(vals=["acct_existing"]))
    seen = []

    class Stripe:
        async def create_account_link(self, acct_id, refresh_url, return_url):
            seen.append((acct_id, refresh_url, return_url))
            return {"url": "https://connect.stripe.test/setup"}

    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: Stripe())
    out = asyncio.run(mod.connect_account(
        mod.ConnectLinkRequest(return_url="https://evil.example.net/phish"),
        account=SimpleNamespace(id="a-1", email="owner@example.com"),
    ))
    assert out == {"url": "https://connect.stripe.test/setup"}
    acct_id, refresh_url, return_url = seen[0]
    assert acct_id == "acct_existing"
    assert "evil.example.net" not in return_url and return_url.endswith("/sites")
    assert refresh_url == return_url


def test_onboarding_link_stripe_failure_is_a_502(monkeypatch):
    _use(monkeypatch, ScriptedConn(vals=["acct_existing"]))

    class Stripe:
        async def create_account_link(self, *a):
            raise CappeStripeError("stripe down")

    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: Stripe())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.connect_account(
            mod.ConnectLinkRequest(),
            account=SimpleNamespace(id="a-1", email="owner@example.com"),
        ))
    assert exc.value.status_code == 502
