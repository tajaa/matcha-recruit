"""Cappe Connect webhook — what happens AFTER money moves.

Covers the review findings that lived past the paid event:

  * refunds and disputes made in Stripe never synced back (order stayed paid,
    download stayed live, stock never returned; collab `refunded` never written);
  * a collab installment was marked paid on an amount mismatch, and matched on
    its id alone — so a creator could mint their own cheap session to settle it;
  * a charge that could not be applied (stale tab, cancelled offer) could only
    be logged: "No refund path exists."

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_payments_refunds.py -q
"""
import asyncio
import logging
import os
from uuid import UUID

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.routes import payments as mod  # noqa: E402
from app.cappe.services import collab as collab_svc  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

CPID = UUID("22222222-2222-4222-8222-222222222222")
ACCT = "acct_creator"


class Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class SqlConn:
    """Answers by the first matching SQL fragment; records every call."""

    def __init__(self, answers=()):
        self.answers, self.calls = list(answers), []

    def _answer(self, kind, sql, args):
        self.calls.append((kind, sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value(sql, args) if callable(value) else value
        return None

    async def fetchrow(self, sql, *args):
        return self._answer("fetchrow", sql, args)

    async def fetchval(self, sql, *args):
        return self._answer("fetchval", sql, args)

    async def execute(self, sql, *args):
        self._answer("execute", sql, args)

    def transaction(self):
        return Tx()

    def sql(self, needle):
        return [c for c in self.calls if needle in c[1]]


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args):
        self.tasks.append((fn.__name__, args))


class FakeStripe:
    def __init__(self, exc=None):
        self.exc, self.refunded = exc, []

    async def refund_connected_charge(self, *, account_id, payment_intent, idempotency_key=None):
        self.refunded.append((account_id, payment_intent, idempotency_key))
        if self.exc:
            raise self.exc
        return {"id": "re_auto"}


def _use(monkeypatch, conn, stripe=None):
    stripe = stripe or FakeStripe()
    monkeypatch.setattr(mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: stripe)
    return stripe


def _installment(**over):
    row = {
        "id": CPID, "offer_id": "off-1", "status": "processing", "trigger": "on_accept",
        "label": "Deposit", "amount_cents": 5000, "currency": "usd",
        "stripe_checkout_session_id": "cs_ours", "stripe_payment_intent": None,
    }
    row.update(over)
    return row


def _session(**over):
    obj = {"id": "cs_ours", "payment_intent": "pi_c", "amount_total": 5000, "currency": "usd"}
    obj.update(over)
    return obj


def _settle(monkeypatch, row, obj=None, *, stripe=None, completed=False, paid_row="default"):
    if paid_row == "default":
        paid_row = None if row is None else {
            "offer_id": row["offer_id"], "trigger": row["trigger"],
            "label": row["label"], "amount_cents": row["amount_cents"],
        }
    conn = SqlConn([
        ("FOR UPDATE OF cp", row),
        ("UPDATE cappe_collab_payments", paid_row),
    ])
    stripe = _use(monkeypatch, conn, stripe)

    async def _done(_conn, offer_id):
        return completed

    monkeypatch.setattr(collab_svc, "check_completion", _done)
    bg = Background()
    asyncio.run(mod._settle_collab_installment(CPID, obj or _session(), ACCT, bg))
    return conn, stripe, bg


# ── a session is only applied when it is exactly the one we asked for ────────

def test_the_installments_own_session_settles_it_and_activates_the_offer(monkeypatch):
    conn, stripe, bg = _settle(monkeypatch, _installment(), completed=True)
    assert conn.sql("SET status = 'paid'")
    assert conn.sql("UPDATE cappe_collab_offers SET status = 'active'")
    assert stripe.refunded == []
    assert [t[0] for t in bg.tasks] == ["_notify_collab_paid", "_notify_collab_completed"]
    # The lookup is joined to the EVENT's connected account and locked.
    lookup = conn.sql("FOR UPDATE OF cp")[0]
    assert "ca.stripe_account_id = $2" in lookup[1] and lookup[2] == (CPID, ACCT)


def test_a_later_installment_does_not_re_activate_the_offer(monkeypatch):
    conn, _stripe, bg = _settle(monkeypatch, _installment(trigger="on_all_approved", status="due"))
    assert conn.sql("SET status = 'paid'")
    assert conn.sql("UPDATE cappe_collab_offers SET status = 'active'") == []
    assert [t[0] for t in bg.tasks] == ["_notify_collab_paid"]


@pytest.mark.parametrize("row_over,obj_over,fragment", [
    # A creator minting their own cheap session carrying the installment id.
    ({}, {"amount_total": 50}, "does not match the installment's 5000"),
    ({}, {"amount_total": None}, "does not match"),
    ({}, {"amount_total": "abc"}, "unreadable Stripe total"),
    # Right amount, but not a session OUR server created — the platform fee on
    # it is whatever its author chose, including none.
    ({}, {"id": "cs_forged"}, "not this installment's current one"),
    # A stale tab paying a session the brand had re-opened past.
    ({"stripe_checkout_session_id": "cs_newer"}, {}, "not this installment's current one"),
    ({"stripe_checkout_session_id": None}, {}, "not this installment's current one"),
    # Paid after the offer (and so the installment) was cancelled.
    ({"status": "cancelled"}, {}, "already cancelled"),
    # A second, different payment for an installment that is already settled.
    ({"status": "paid", "stripe_payment_intent": "pi_first"}, {}, "already paid"),
    ({}, {"currency": "eur"}, "currency eur does not match"),
])
def test_a_session_that_cannot_be_applied_is_refunded_not_marked_paid(
    monkeypatch, caplog, row_over, obj_over, fragment,
):
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        conn, stripe, bg = _settle(monkeypatch, _installment(**row_over), _session(**obj_over))
    assert conn.sql("SET status = 'paid'") == []          # never marked paid
    assert conn.sql("UPDATE cappe_collab_offers") == []   # offer never activated
    assert bg.tasks == []
    # The money goes back, on the creator's account, exactly once per charge.
    assert stripe.refunded == [(ACCT, "pi_c", "cappe-collab-unapplied-pi_c")]
    message = " ".join(r.getMessage() for r in caplog.records)
    assert fragment in message and "refunded automatically" in message


def test_a_replay_of_the_payment_already_recorded_refunds_nothing(monkeypatch):
    row = _installment(status="paid", stripe_payment_intent="pi_c")
    conn, stripe, bg = _settle(monkeypatch, row)
    assert stripe.refunded == [] and bg.tasks == []
    assert conn.sql("SET status = 'paid'") == []


def test_an_installment_unknown_to_this_account_is_logged_and_never_refunded(monkeypatch, caplog):
    """Not provably ours, so not ours to refund: a connected account naming
    someone else's installment id gets nothing done to its own charge."""
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        _conn, stripe, bg = _settle(monkeypatch, None)
    assert stripe.refunded == [] and bg.tasks == []
    assert any("does not exist for that account" in r.getMessage() for r in caplog.records)


def test_a_failed_automatic_refund_is_loud(monkeypatch, caplog):
    stripe = FakeStripe(exc=CappeStripeError("balance insufficient"))
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        _settle(monkeypatch, _installment(status="cancelled"), stripe=stripe)
    assert any("MANUAL REFUND REQUIRED" in r.getMessage() for r in caplog.records)


def test_an_unappliable_session_with_no_payment_intent_asks_for_a_human(monkeypatch, caplog):
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        _conn, stripe, _bg = _settle(
            monkeypatch, _installment(status="cancelled"), _session(payment_intent=None),
        )
    assert stripe.refunded == []
    assert any("MANUAL REFUND REQUIRED" in r.getMessage() for r in caplog.records)


def test_losing_the_status_race_inside_the_lock_notifies_nobody(monkeypatch):
    _conn, stripe, bg = _settle(monkeypatch, _installment(), paid_row=None)
    assert bg.tasks == [] and stripe.refunded == []


# ── a dead checkout puts the installment back to `due` ───────────────────────

def test_expired_current_session_reopens_the_installment(monkeypatch):
    conn = SqlConn([("UPDATE cappe_collab_payments", CPID)])
    _use(monkeypatch, conn)
    asyncio.run(mod._reopen_collab_installment(str(CPID), {"id": "cs_ours"}, ACCT, "checkout.session.expired"))
    _, sql, args = conn.calls[0]
    assert "SET status = 'due'" in sql and "cp.status = 'processing'" in sql
    # Only when the dead session is the CURRENT one: an older session expiring
    # must not reopen an installment whose newer checkout is still in flight.
    assert "cp.stripe_checkout_session_id = $2" in sql
    assert args == (CPID, "cs_ours", ACCT)


def test_reopen_ignores_an_unparseable_installment_id(monkeypatch):
    conn = SqlConn()
    _use(monkeypatch, conn)
    asyncio.run(mod._reopen_collab_installment("nope", {"id": "cs"}, ACCT, "checkout.session.expired"))
    assert conn.calls == []


def test_reopen_that_matches_nothing_is_quiet(monkeypatch):
    conn = SqlConn()
    _use(monkeypatch, conn)
    asyncio.run(mod._reopen_collab_installment(str(CPID), {"id": "cs_old"}, ACCT, "checkout.session.expired"))
    assert len(conn.calls) == 1


# ── charge.refunded ──────────────────────────────────────────────────────────

ORDER = {"id": "o-1", "site_id": "s-1", "status": "paid"}


def _refund_harness(monkeypatch, conn, outcome=None):
    """Fake the refund ledger: what the webhook hands it lands in `seen`."""
    seen = []

    async def _sync(_conn, *, order_id, site_id, amount_refunded, stripe_refund_id):
        seen.append({"order": order_id, "cents": amount_refunded, "refund": stripe_refund_id})
        return outcome or ("refunded" if amount_refunded >= 5000 else "partially_refunded")

    async def _full(_conn, *, order_id, site_id, source, restock, stripe_refund_id=None):
        seen.append({"order": order_id, "source": source, "restock": restock})
        return {"id": "r-1"}

    _use(monkeypatch, conn)
    monkeypatch.setattr(mod, "sync_stripe_refunds", _sync)
    monkeypatch.setattr(mod, "refund_in_full", _full)
    return seen


def _charge(**over):
    obj = {"payment_intent": "pi_1", "amount": 5000, "amount_refunded": 5000, "refunded": True,
           "refunds": {"data": [{"id": "re_dash"}]}}
    obj.update(over)
    return obj


def test_a_refund_made_in_stripe_brings_the_ledger_up_to_stripes_total(monkeypatch):
    conn = SqlConn([("o.stripe_payment_intent = $1", ORDER)])
    seen = _refund_harness(monkeypatch, conn)
    out = asyncio.run(mod._sync_charge_refunded(_charge(), {"account": "acct_1"}))
    assert out == {"received": True, "status": "refunded"}
    assert seen == [{"order": "o-1", "cents": 5000, "refund": "re_dash"}]
    # Scoped to the event's own connected account, and locked.
    lookup = conn.calls[0]
    assert "a.stripe_account_id = $2" in lookup[1] and "FOR UPDATE OF o" in lookup[1]
    assert lookup[2] == ("pi_1", "acct_1")


def test_a_full_refund_flag_without_an_amount_counts_the_whole_charge(monkeypatch):
    conn = SqlConn([("o.stripe_payment_intent = $1", ORDER)])
    seen = _refund_harness(monkeypatch, conn)
    asyncio.run(mod._sync_charge_refunded(_charge(amount_refunded=0, refunds=None), {"account": "acct_1"}))
    assert seen[0]["cents"] == 5000 and seen[0]["refund"] is None


def test_a_partial_refund_is_handed_to_the_ledger_as_a_part(monkeypatch):
    conn = SqlConn([("o.stripe_payment_intent = $1", ORDER)])
    seen = _refund_harness(monkeypatch, conn)
    out = asyncio.run(mod._sync_charge_refunded(
        _charge(amount_refunded=1200, refunded=False), {"account": "acct_1"},
    ))
    assert out == {"received": True, "status": "partially_refunded"}
    assert seen == [{"order": "o-1", "cents": 1200, "refund": "re_dash"}]
    assert conn.sql(" SET ") == []                       # the ledger writes, not the webhook


def test_a_subscription_orders_refund_is_matched_by_its_invoice(monkeypatch):
    conn = SqlConn([("o.stripe_invoice_id = $1", ORDER)])
    seen = _refund_harness(monkeypatch, conn)
    asyncio.run(mod._sync_charge_refunded(
        _charge(payment_intent="pi_sub", invoice="in_1"), {"account": "acct_1"},
    ))
    assert seen and conn.sql("o.stripe_invoice_id = $1")[0][2] == ("in_1", "acct_1")


def test_a_refunded_collab_installment_is_marked_refunded(monkeypatch, caplog):
    """`refunded` has been in the CHECK since the table was created and nothing
    ever wrote it."""
    conn = SqlConn([("UPDATE cappe_collab_payments", {"id": CPID, "offer_id": "off-1"})])
    _refund_harness(monkeypatch, conn)
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        out = asyncio.run(mod._sync_charge_refunded(_charge(), {"account": ACCT}))
    assert out == {"received": True, "status": "collab_refunded"}
    _, sql, args = conn.sql("UPDATE cappe_collab_payments")[0]
    assert "SET status = 'refunded'" in sql and "cp.status = 'paid'" in sql
    assert "ca.stripe_account_id = $2" in sql and args == ("pi_1", ACCT, "re_dash")
    assert any("review the offer's status" in r.getMessage() for r in caplog.records)


def test_a_partial_refund_of_something_that_is_not_an_order_changes_nothing(monkeypatch):
    conn = SqlConn()
    _refund_harness(monkeypatch, conn)
    out = asyncio.run(mod._sync_charge_refunded(
        _charge(amount_refunded=100, refunded=False), {"account": ACCT},
    ))
    assert out == {"received": True}
    assert conn.sql(" SET ") == []                       # nothing written


def test_a_refund_event_with_no_connected_account_is_ignored(monkeypatch):
    conn = SqlConn()
    _refund_harness(monkeypatch, conn)
    assert asyncio.run(mod._sync_charge_refunded(_charge(), {})) == {"received": True}
    assert conn.calls == []


def test_a_refund_matching_nothing_is_acknowledged(monkeypatch):
    conn = SqlConn()
    _refund_harness(monkeypatch, conn)
    assert asyncio.run(mod._sync_charge_refunded(_charge(), {"account": "acct_1"})) == {"received": True}


# ── charge.dispute.* ─────────────────────────────────────────────────────────

def test_an_opened_dispute_is_recorded_on_the_order(monkeypatch, caplog):
    conn = SqlConn([("o.stripe_payment_intent = $1", ORDER)])
    seen = _refund_harness(monkeypatch, conn)
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        out = asyncio.run(mod._sync_dispute(
            {"id": "dp_1", "payment_intent": "pi_1", "status": "needs_response", "reason": "fraudulent"},
            {"account": "acct_1"},
        ))
    assert out == {"received": True, "status": "dispute_recorded"}
    _, sql, args = conn.sql("SET dispute_status = $2")[0]
    assert "disputed_at = COALESCE(disputed_at, NOW())" in sql and args == ("o-1", "needs_response")
    assert seen == []                                    # an open dispute is not a refund
    assert any("fraudulent" in r.getMessage() for r in caplog.records)


def test_a_lost_dispute_closes_the_order_without_restocking(monkeypatch):
    conn = SqlConn([("o.stripe_payment_intent = $1", ORDER)])
    seen = _refund_harness(monkeypatch, conn)
    asyncio.run(mod._sync_dispute(
        {"id": "dp_1", "payment_intent": "pi_1", "status": "lost", "amount": 5000},
        {"account": "acct_1"},
    ))
    # The money is gone but so are the goods — crediting the shelf would
    # invent inventory.
    assert seen == [{"order": "o-1", "source": "dispute", "restock": False}]


@pytest.mark.parametrize("obj,event", [
    ({"payment_intent": "pi_1", "status": "lost"}, {}),                       # no account
    ({"status": "lost"}, {"account": "acct_1"}),                              # no intent
    ({"payment_intent": {"id": "pi_1"}, "status": "lost"}, {"account": "a"}),  # expanded object
])
def test_a_dispute_that_cannot_be_tied_to_an_order_is_ignored(monkeypatch, obj, event):
    conn = SqlConn()
    seen = _refund_harness(monkeypatch, conn)
    assert asyncio.run(mod._sync_dispute(obj, event)) == {"received": True}
    assert conn.calls == [] and seen == []


def test_a_dispute_for_an_unknown_charge_writes_nothing(monkeypatch):
    conn = SqlConn()
    seen = _refund_harness(monkeypatch, conn)
    out = asyncio.run(mod._sync_dispute(
        {"payment_intent": "pi_x", "status": "needs_response"}, {"account": "acct_1"},
    ))
    assert out == {"received": True}
    assert conn.sql(" SET ") == [] and seen == []


# ── dispatch ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("etype,handler", [
    ("charge.refunded", "_sync_charge_refunded"),
    ("charge.dispute.created", "_sync_dispute"),
    ("charge.dispute.updated", "_sync_dispute"),
    ("charge.dispute.closed", "_sync_dispute"),
])
def test_refund_and_dispute_events_reach_their_handlers(monkeypatch, etype, handler):
    seen = []

    async def _handler(obj, event):
        seen.append(handler)
        return {"received": True, "status": "handled"}

    monkeypatch.setattr(mod, handler, _handler)
    out = asyncio.run(mod._handle_connect_event(etype, {"payment_intent": "pi_1"}, {"account": "a"}, Background()))
    assert seen == [handler] and out["status"] == "handled"
