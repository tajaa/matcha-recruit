"""Order status rules and the refund action.

Two findings from the 2026-10 payments review meet here:

  * "Refunded" never refunded anyone — the owner's dropdown flipped a status
    word and restocked, and no money moved.
  * The status PATCH had no transition rules — any of five statuses could
    follow any other, so paid → cancelled → paid → cancelled restocked twice.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_order_lifecycle.py -q
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

from app.cappe.models.shop import CappeOrderStatusUpdate  # noqa: E402
from app.cappe.routes import shop as shop_mod  # noqa: E402
from app.cappe.services import order_lifecycle as lifecycle  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

SITE, ORDER, ACCOUNT = uuid4(), uuid4(), SimpleNamespace(id=uuid4())
STATUSES = ["pending", "paid", "fulfilled", "cancelled", "refunded", "declined"]


# ── the transition graph ─────────────────────────────────────────────────────

@pytest.mark.parametrize("current,new", [
    ("pending", "paid"), ("pending", "cancelled"), ("paid", "fulfilled"), ("fulfilled", "paid"),
])
def test_allowed_transitions_pass(current, new):
    assert lifecycle.transition_error(current, new) is None


@pytest.mark.parametrize("current", STATUSES)
def test_a_repeat_or_a_tracking_only_patch_is_never_refused(current):
    assert lifecycle.transition_error(current, current) is None
    assert lifecycle.transition_error(current, None) is None


@pytest.mark.parametrize("current", [s for s in STATUSES if s != "refunded"])
def test_refunded_is_never_reachable_by_changing_the_status(current):
    """The whole point: the word alone returns nobody's money."""
    reason = lifecycle.transition_error(current, "refunded")
    assert reason and "Refund action" in reason


@pytest.mark.parametrize("current", ["paid", "fulfilled"])
def test_a_paid_order_cannot_be_cancelled_only_refunded(current):
    assert "Refund it instead" in lifecycle.transition_error(current, "cancelled")


@pytest.mark.parametrize("current", ["cancelled", "refunded", "declined"])
@pytest.mark.parametrize("new", ["pending", "paid", "fulfilled", "cancelled"])
def test_released_orders_are_terminal(current, new):
    if current == new:
        return
    assert "can't be changed" in lifecycle.transition_error(current, new)


def test_other_illegal_moves_name_both_ends():
    assert lifecycle.transition_error("pending", "fulfilled") == "A pending order can't be moved to fulfilled."


def test_no_cycle_passes_through_a_restock_twice():
    """paid → cancelled → paid → cancelled used to restock on every lap. With
    cancelled terminal and paid un-cancellable, a restocking transition can be
    taken at most once from any start."""
    def reachable(start):
        seen, stack = set(), [start]
        while stack:
            for nxt in lifecycle.ALLOWED_TRANSITIONS[stack.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    for released in ("cancelled", "refunded", "declined"):
        assert reachable(released) == set()
    assert lifecycle.allowed_next_statuses("pending") == ["cancelled", "paid"]
    assert lifecycle.allowed_next_statuses("refunded") == []


# ── mark_order_refunded ──────────────────────────────────────────────────────

class RefundConn:
    def __init__(self, row):
        self.row, self.sql, self.args = row, None, None

    async def fetchrow(self, sql, *args):
        self.sql, self.args = sql, args
        return self.row


def _stock_log(monkeypatch):
    log = []

    async def _restock(_conn, *, site_id, order_id, reason):
        log.append(f"restock:{reason}")

    async def _bookings(_conn, *, order_id):
        log.append("bookings")
        return 1

    monkeypatch.setattr(lifecycle, "restock_order", _restock)
    monkeypatch.setattr(lifecycle, "release_order_bookings", _bookings)
    return log


def test_refunding_a_paid_order_restocks_and_frees_its_slots(monkeypatch):
    log = _stock_log(monkeypatch)
    conn = RefundConn({"id": ORDER, "site_id": SITE})
    row = asyncio.run(lifecycle.mark_order_refunded(
        conn, order_id=ORDER, site_id=SITE, refunded_cents=None, stripe_refund_id="re_1",
    ))
    assert row == {"id": ORDER, "site_id": SITE}
    assert log == ["restock:return", "bookings"]
    # Guarded on a status that actually holds money — this is what makes the
    # refund route and the charge.refunded webhook safe to both run.
    assert "status IN ('paid', 'fulfilled')" in conn.sql
    assert "status = 'refunded'" in conn.sql and "refunded_at = NOW()" in conn.sql
    assert conn.args == (ORDER, SITE, None, "re_1")


def test_an_order_not_holding_money_is_left_alone(monkeypatch):
    log = _stock_log(monkeypatch)
    assert asyncio.run(lifecycle.mark_order_refunded(
        RefundConn(None), order_id=ORDER, site_id=SITE, refunded_cents=500, stripe_refund_id=None,
    )) is None
    assert log == []


def test_a_lost_dispute_closes_the_order_without_inventing_stock(monkeypatch):
    log = _stock_log(monkeypatch)
    asyncio.run(lifecycle.mark_order_refunded(
        RefundConn({"id": ORDER, "site_id": SITE}), order_id=ORDER, site_id=SITE,
        refunded_cents=900, stripe_refund_id=None, restock=False,
    ))
    assert log == ["bookings"]


# ── route harness ────────────────────────────────────────────────────────────

class Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class SqlConn:
    """Answers by the first matching SQL fragment; records every call."""

    def __init__(self, answers):
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
    def __init__(self, exc=None, refund=None):
        self.exc, self.refund, self.refunded = exc, refund or {"id": "re_live"}, []

    async def refund_connected_charge(self, *, account_id, payment_intent, idempotency_key=None):
        self.refunded.append((account_id, payment_intent, idempotency_key))
        if self.exc:
            raise self.exc
        return self.refund


def _wire(monkeypatch, conn, stripe=None):
    log = []

    async def _owned(_conn, site_id, account_id):
        return {"id": site_id}

    async def _closed(site_id, order_id, account_id, *, then="refund it"):
        log.append("close")

    async def _restock(_conn, *, site_id, order_id, reason):
        log.append(f"restock:{reason}")

    async def _bookings(_conn, *, order_id):
        log.append("bookings")
        return 0

    async def _refunded(_conn, *, order_id, site_id, refunded_cents, stripe_refund_id, **_kw):
        log.append(f"mark_refunded:{stripe_refund_id}")
        return {"id": order_id, "site_id": site_id}

    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", _owned)
    monkeypatch.setattr(shop_mod, "_close_open_checkout", _closed)
    monkeypatch.setattr(shop_mod, "restock_order", _restock)
    monkeypatch.setattr(shop_mod, "release_order_bookings", _bookings)
    monkeypatch.setattr(shop_mod, "mark_order_refunded", _refunded)
    monkeypatch.setattr(shop_mod, "_order_row", lambda order, items: dict(order))
    monkeypatch.setattr(shop_mod, "get_cappe_stripe", lambda: stripe or FakeStripe())
    monkeypatch.setattr("app.cappe.services.push.schedule_push", lambda *_a: None)
    return log


def _patch_conn(current, updated=None):
    return SqlConn([
        ("SELECT status FROM cappe_orders", current),
        ("FOR UPDATE", {"status": current, "tracking_number": None}),
        ("UPDATE cappe_orders SET", updated or {"id": ORDER, "status": "x"}),
    ])


def _patch(conn, status, bg=None):
    return asyncio.run(shop_mod.update_order_status(
        SITE, ORDER, CappeOrderStatusUpdate(status=status), bg or Background(), account=ACCOUNT,
    ))


# ── PATCH: transitions ───────────────────────────────────────────────────────

def test_cancelling_a_pending_order_closes_checkout_then_releases(monkeypatch):
    conn = _patch_conn("pending")
    log = _wire(monkeypatch, conn)
    _patch(conn, "cancelled")
    assert log == ["close", "restock:restock", "bookings"]


def test_marking_paid_by_hand_closes_the_buyers_page_stamps_paid_at_and_receipts(monkeypatch):
    """An order paid offline used to keep its Stripe page open (the buyer could
    still be charged) and got no receipt at all."""
    conn = _patch_conn("pending")
    log = _wire(monkeypatch, conn)
    bg = Background()
    _patch(conn, "paid", bg)
    assert log == ["close"]                       # no restock: nothing is reversed
    update = conn.sql("UPDATE cappe_orders SET")[0][1]
    assert "paid_at = COALESCE(paid_at, NOW())" in update
    assert bg.tasks == [("issue_receipt_for_paid_order", (ORDER, SITE))]


def test_fulfilling_a_paid_order_touches_no_stock_and_no_checkout(monkeypatch):
    conn = _patch_conn("paid")
    log = _wire(monkeypatch, conn)
    bg = Background()
    _patch(conn, "fulfilled", bg)
    assert log == [] and bg.tasks == []
    assert "paid_at" not in conn.sql("UPDATE cappe_orders SET")[0][1]


@pytest.mark.parametrize("current,new,fragment", [
    ("paid", "refunded", "Refund action"),
    ("fulfilled", "refunded", "Refund action"),
    ("paid", "cancelled", "Refund it instead"),
    ("cancelled", "paid", "can't be changed"),
    ("refunded", "paid", "can't be changed"),
    ("pending", "fulfilled", "can't be moved"),
])
def test_refused_transitions_are_409_and_change_nothing(monkeypatch, current, new, fragment):
    conn = _patch_conn(current)
    log = _wire(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _patch(conn, new)
    assert exc.value.status_code == 409 and fragment in exc.value.detail
    # Refused BEFORE the buyer's payment page is touched or any row is written.
    assert log == []
    assert conn.sql("UPDATE cappe_orders SET") == []


def test_a_status_that_changes_between_the_precheck_and_the_lock_is_still_refused(monkeypatch):
    """The cheap pre-check is not the authority; the locked read is."""
    conn = SqlConn([
        ("SELECT status FROM cappe_orders", "pending"),
        ("FOR UPDATE", {"status": "cancelled", "tracking_number": None}),   # reaper got there
        ("UPDATE cappe_orders SET", {"id": ORDER}),
    ])
    _wire(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _patch(conn, "paid")
    assert exc.value.status_code == 409
    assert conn.sql("UPDATE cappe_orders SET") == []


def test_patch_on_a_missing_order_is_404(monkeypatch):
    conn = SqlConn([])
    _wire(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _patch(conn, "paid")
    assert exc.value.status_code == 404


def test_tracking_only_patch_skips_the_status_machinery(monkeypatch):
    conn = SqlConn([
        ("FOR UPDATE", {"status": "paid", "tracking_number": "old"}),
        ("UPDATE cappe_orders SET", {"id": ORDER, "status": "paid"}),
    ])
    log = _wire(monkeypatch, conn)
    asyncio.run(shop_mod.update_order_status(
        SITE, ORDER, CappeOrderStatusUpdate(tracking_number="1Z"), Background(), account=ACCOUNT,
    ))
    assert log == []
    assert conn.sql("SELECT status FROM cappe_orders") == []     # no pre-check needed


def test_tracking_only_patch_on_a_vanished_order_is_404(monkeypatch):
    conn = SqlConn([])
    _wire(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(shop_mod.update_order_status(
            SITE, ORDER, CappeOrderStatusUpdate(tracking_number="1Z"), Background(), account=ACCOUNT,
        ))
    assert exc.value.status_code == 404


# ── POST …/refund ────────────────────────────────────────────────────────────

def _refund_conn(status="paid", intent="pi_1", invoice=None, acct="acct_1", after=None):
    return SqlConn([
        ("a.stripe_account_id", {
            "status": status, "stripe_payment_intent": intent,
            "stripe_invoice_id": invoice, "stripe_account_id": acct,
        }),
        ("FROM cappe_orders WHERE id = $1 AND site_id = $2", after or {"id": ORDER, "status": "refunded"}),
    ])


def _refund(conn):
    return asyncio.run(shop_mod.refund_order(SITE, ORDER, account=ACCOUNT))


def test_card_order_is_refunded_at_stripe_before_anything_is_recorded(monkeypatch):
    conn, stripe = _refund_conn(), FakeStripe()
    log = _wire(monkeypatch, conn, stripe)
    out = _refund(conn)
    # On the BUSINESS's connected account (the charge lives there), with a key
    # that makes a double-click return the first refund.
    assert stripe.refunded == [("acct_1", "pi_1", f"cappe-order-refund-{ORDER}")]
    assert log == ["mark_refunded:re_live"]
    assert out["status"] == "refunded"


def test_a_refund_stripe_refuses_leaves_the_order_exactly_as_it_was(monkeypatch):
    conn, stripe = _refund_conn(), FakeStripe(exc=CappeStripeError("insufficient funds"))
    log = _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _refund(conn)
    assert exc.value.status_code == 502 and "left as is" in exc.value.detail
    assert log == []                               # never marked refunded, never restocked


def test_a_charge_already_refunded_in_stripe_still_closes_the_order(monkeypatch):
    conn = _refund_conn()
    log = _wire(monkeypatch, conn, FakeStripe(refund={"id": None, "already_refunded": True}))
    _refund(conn)
    assert log == ["mark_refunded:None"]


def test_an_order_paid_outside_stripe_is_only_recorded(monkeypatch):
    conn, stripe = _refund_conn(intent=None), FakeStripe()
    log = _wire(monkeypatch, conn, stripe)
    _refund(conn)
    assert stripe.refunded == []                   # there is no charge to reverse
    assert log == ["mark_refunded:None"]


def test_a_subscription_order_is_sent_to_stripe_not_silently_marked(monkeypatch):
    conn, stripe = _refund_conn(intent=None, invoice="in_1"), FakeStripe()
    log = _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _refund(conn)
    assert exc.value.status_code == 409 and "subscription" in exc.value.detail
    assert log == [] and stripe.refunded == []


def test_a_card_order_with_no_connected_account_cannot_be_refunded_here(monkeypatch):
    conn, stripe = _refund_conn(acct=None), FakeStripe()
    log = _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _refund(conn)
    assert exc.value.status_code == 409 and "no longer connected" in exc.value.detail
    assert log == []


@pytest.mark.parametrize("status", ["pending", "cancelled", "declined"])
def test_only_an_order_holding_money_can_be_refunded(monkeypatch, status):
    conn, stripe = _refund_conn(status=status), FakeStripe()
    log = _wire(monkeypatch, conn, stripe)
    with pytest.raises(HTTPException) as exc:
        _refund(conn)
    assert exc.value.status_code == 409
    assert log == [] and stripe.refunded == []


def test_refunding_an_already_refunded_order_is_a_no_op_that_returns_it(monkeypatch):
    conn, stripe = _refund_conn(status="refunded"), FakeStripe()
    _wire(monkeypatch, conn, stripe)
    assert _refund(conn)["status"] == "refunded"
    assert stripe.refunded == []                   # no second refund


def test_refund_of_a_missing_order_is_404(monkeypatch):
    conn = SqlConn([])
    _wire(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _refund(conn)
    assert exc.value.status_code == 404


def test_refund_404s_if_the_order_vanishes_before_it_is_read_back(monkeypatch):
    conn = SqlConn([
        ("a.stripe_account_id", {"status": "paid", "stripe_payment_intent": None,
                                 "stripe_invoice_id": None, "stripe_account_id": None}),
    ])
    _wire(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _refund(conn)
    assert exc.value.status_code == 404
