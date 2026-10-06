"""Collab checkout: one installment, at most one payable Stripe page.

The 2026-10 payments review found two windows in which a brand could be
charged twice for the same installment:

  * re-opening checkout on a `processing` installment minted a second session
    and left the first one payable;
  * cancelling an offer voided its `processing` installments without closing
    their Stripe pages.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_collab_checkout.py -q
"""
import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.routes import collab as mod  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

OFFER, PAYMENT = uuid4(), uuid4()
BRAND = SimpleNamespace(id=uuid4(), email="brand@example.com")
CREATOR_ACCT = "acct_creator"


class Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class SqlConn:
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

    async def fetch(self, sql, *args):
        return self._answer("fetch", sql, args) or []

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


class FakeStripe:
    def __init__(self, states=None, create_exc=None):
        self.states = states or {}
        self.create_exc = create_exc
        self.expired, self.created = [], []

    async def expire_checkout_session(self, account_id, session_id):
        self.expired.append((account_id, session_id))
        outcome = self.states.get(session_id, "expired")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def create_checkout_session(self, **kwargs):
        if self.create_exc:
            raise self.create_exc
        self.created.append(kwargs)
        return {"id": "cs_new", "url": "https://checkout.example.com/new"}


def _offer(**over):
    row = {
        "id": OFFER, "title": "Spring launch", "status": "active",
        "creator_stripe_account_id": CREATOR_ACCT, "creator_charges_enabled": True,
    }
    row.update(over)
    return row


def _payment(**over):
    row = {"id": PAYMENT, "status": "due", "amount_cents": 5000, "currency": "usd",
           "label": "Deposit", "stripe_checkout_session_id": None}
    row.update(over)
    return row


def _wire(monkeypatch, conn, stripe, *, offer=None, side="brand"):
    async def _side(_conn, offer_id, account_id):
        return offer or _offer(), side

    async def _fee(_conn):
        return 500

    monkeypatch.setattr(mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(mod.svc, "get_offer_side", _side)
    monkeypatch.setattr(mod.svc, "resolve_collab_fee_bps", _fee)
    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: stripe)


def _checkout(conn, stripe):
    return asyncio.run(mod.checkout_payment(OFFER, PAYMENT, account=BRAND))


# ── checkout ─────────────────────────────────────────────────────────────────

def test_first_checkout_opens_one_session_and_records_it(monkeypatch):
    conn = SqlConn([("SELECT * FROM cappe_collab_payments", _payment()),
                    ("UPDATE cappe_collab_payments", PAYMENT)])
    stripe = FakeStripe()
    _wire(monkeypatch, conn, stripe)
    assert _checkout(conn, stripe) == {"url": "https://checkout.example.com/new"}
    assert stripe.expired == []                       # nothing earlier to close
    created = stripe.created[0]
    assert created["account_id"] == CREATOR_ACCT
    assert created["application_fee_cents"] == 250     # 5% of 5000
    assert created["metadata"]["collab_payment_id"] == str(PAYMENT)
    _, sql, args = conn.sql("UPDATE cappe_collab_payments")[0]
    # Guarded on the session id read at the start, not only the status.
    assert "stripe_checkout_session_id IS NOT DISTINCT FROM $5" in sql
    assert args == (PAYMENT, "cs_new", 500, 250, None)


def test_reopening_checkout_closes_the_earlier_page_first(monkeypatch):
    """The stale-tab double charge: the first session used to stay payable."""
    conn = SqlConn([("SELECT * FROM cappe_collab_payments",
                     _payment(status="processing", stripe_checkout_session_id="cs_old")),
                    ("UPDATE cappe_collab_payments", PAYMENT)])
    stripe = FakeStripe()
    _wire(monkeypatch, conn, stripe)
    _checkout(conn, stripe)
    assert stripe.expired == [(CREATOR_ACCT, "cs_old")]
    assert len(stripe.created) == 1
    assert conn.sql("UPDATE cappe_collab_payments")[0][2][-1] == "cs_old"


def test_an_earlier_page_that_was_already_paid_stands_and_no_new_one_opens(monkeypatch):
    conn = SqlConn([("SELECT * FROM cappe_collab_payments",
                     _payment(status="processing", stripe_checkout_session_id="cs_old"))])
    stripe = FakeStripe(states={"cs_old": "complete"})
    _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _checkout(conn, stripe)
    assert exc.value.status_code == 409 and "already been completed" in exc.value.detail
    assert stripe.created == []                        # no second way to pay
    assert conn.sql("UPDATE cappe_collab_payments") == []


def test_stripe_being_unreachable_opens_nothing(monkeypatch):
    conn = SqlConn([("SELECT * FROM cappe_collab_payments",
                     _payment(status="processing", stripe_checkout_session_id="cs_old"))])
    stripe = FakeStripe(states={"cs_old": CappeStripeError("timeout")})
    _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _checkout(conn, stripe)
    assert exc.value.status_code == 502
    assert stripe.created == []


def test_a_due_installment_with_an_old_dead_session_is_not_re_expired(monkeypatch):
    """`due` means the previous session already expired or failed (the webhook
    put it back) — only `processing` has a page that may still be open."""
    conn = SqlConn([("SELECT * FROM cappe_collab_payments",
                     _payment(status="due", stripe_checkout_session_id="cs_dead")),
                    ("UPDATE cappe_collab_payments", PAYMENT)])
    stripe = FakeStripe()
    _wire(monkeypatch, conn, stripe)
    _checkout(conn, stripe)
    assert stripe.expired == []
    assert conn.sql("UPDATE cappe_collab_payments")[0][2][-1] == "cs_dead"


def test_losing_a_race_closes_the_session_just_created(monkeypatch):
    """Two tabs clicking Pay at once, or the offer being cancelled while we
    were at Stripe: the session we minted must not outlive the installment."""
    conn = SqlConn([("SELECT * FROM cappe_collab_payments", _payment()),
                    ("UPDATE cappe_collab_payments", None)])
    stripe = FakeStripe()
    _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _checkout(conn, stripe)
    assert exc.value.status_code == 409
    assert stripe.expired == [(CREATOR_ACCT, "cs_new")]


def test_failing_to_close_the_superseded_session_is_still_a_409(monkeypatch):
    conn = SqlConn([("SELECT * FROM cappe_collab_payments", _payment()),
                    ("UPDATE cappe_collab_payments", None)])
    stripe = FakeStripe(states={"cs_new": CappeStripeError("timeout")})
    _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _checkout(conn, stripe)
    assert exc.value.status_code == 409


def test_session_creation_failure_is_a_502(monkeypatch):
    conn = SqlConn([("SELECT * FROM cappe_collab_payments", _payment())])
    stripe = FakeStripe(create_exc=CappeStripeError("boom"))
    _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _checkout(conn, stripe)
    assert exc.value.status_code == 502


@pytest.mark.parametrize("payment", [None, _payment(status="paid"), _payment(status="cancelled")])
def test_only_a_due_or_processing_installment_can_be_paid(monkeypatch, payment):
    conn = SqlConn([("SELECT * FROM cappe_collab_payments", payment)])
    stripe = FakeStripe()
    _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _checkout(conn, stripe)
    assert exc.value.status_code == 409
    assert stripe.created == []


def test_only_the_brand_can_pay(monkeypatch):
    conn = SqlConn()
    stripe = FakeStripe()
    _wire(monkeypatch, conn, stripe, side="creator")
    with pytest.raises(HTTPException) as exc:
        _checkout(conn, stripe)
    assert exc.value.status_code == 403


def test_checkout_waits_for_the_creators_payout_setup(monkeypatch):
    conn = SqlConn([("SELECT * FROM cappe_collab_payments", _payment())])
    stripe = FakeStripe()
    _wire(monkeypatch, conn, stripe, offer=_offer(creator_charges_enabled=False))
    with pytest.raises(HTTPException) as exc:
        _checkout(conn, stripe)
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "payouts_not_ready"


# ── cancel ───────────────────────────────────────────────────────────────────

class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args):
        self.tasks.append(fn.__name__)


def _cancel(monkeypatch, conn, stripe, *, offer, side):
    _wire(monkeypatch, conn, stripe, offer=offer, side=side)
    cancelled = []

    async def _cancel_offer(_conn, offer_row, who, reason):
        cancelled.append((who, reason))

    async def _contact(_conn, offer_row, who):
        return "other@example.com", "Other"

    async def _detail(_conn, offer_id, account_id):
        return {"id": offer_id}

    monkeypatch.setattr(mod.svc, "cancel_offer", _cancel_offer)
    monkeypatch.setattr(mod, "_resolve_contact", _contact)
    monkeypatch.setattr(mod, "_offer_detail", _detail)
    body = SimpleNamespace(reason="changed plans")
    return cancelled, lambda: asyncio.run(mod.cancel_offer_route(OFFER, body, Background(), account=BRAND))


@pytest.mark.parametrize("side,status", [("creator", "active"), ("brand", "accepted"), ("creator", "accepted")])
def test_cancel_closes_open_payment_pages_before_voiding_installments(monkeypatch, side, status):
    conn = SqlConn([("status = 'processing'", [{"stripe_checkout_session_id": "cs_open"}])])
    stripe = FakeStripe()
    cancelled, run = _cancel(monkeypatch, conn, stripe, offer=_offer(status=status), side=side)
    run()
    assert stripe.expired == [(CREATOR_ACCT, "cs_open")]
    assert cancelled == [(side, "changed plans")]


def test_a_brand_cancelling_an_active_offer_leaves_earned_installments_payable(monkeypatch):
    """`cancel_offer` keeps due/processing installments in that case — their
    pages must stay open."""
    conn = SqlConn([("status = 'processing'", [{"stripe_checkout_session_id": "cs_open"}])])
    stripe = FakeStripe()
    cancelled, run = _cancel(monkeypatch, conn, stripe, offer=_offer(status="active"), side="brand")
    run()
    assert stripe.expired == []
    assert conn.sql("status = 'processing'") == []     # not even looked up
    assert cancelled == [("brand", "changed plans")]


def test_cancel_is_refused_while_a_payment_is_settling(monkeypatch):
    conn = SqlConn([("status = 'processing'", [{"stripe_checkout_session_id": "cs_open"}])])
    stripe = FakeStripe(states={"cs_open": "complete"})
    cancelled, run = _cancel(monkeypatch, conn, stripe, offer=_offer(status="accepted"), side="brand")
    with pytest.raises(HTTPException) as exc:
        run()
    assert exc.value.status_code == 409 and "settling" in exc.value.detail
    assert cancelled == []                             # the offer was NOT cancelled


def test_cancel_is_refused_when_a_page_cannot_be_closed(monkeypatch):
    conn = SqlConn([("status = 'processing'", [{"stripe_checkout_session_id": "cs_open"}])])
    stripe = FakeStripe(states={"cs_open": CappeStripeError("timeout")})
    cancelled, run = _cancel(monkeypatch, conn, stripe, offer=_offer(status="accepted"), side="brand")
    with pytest.raises(HTTPException) as exc:
        run()
    assert exc.value.status_code == 502
    assert cancelled == []


def test_closing_sessions_is_a_no_op_without_a_connected_account():
    asyncio.run(mod._close_collab_sessions(None, ["cs_1"], settling_detail="x"))
