"""Booking deposits — the 2026-10 commerce readiness review, PR 11.

A service can take a deposit or its full price when it's booked. What each
block pins:

  * what's charged now and what's left for the appointment;
  * only where it can be taken (cards connected, a plan that sells);
  * the booking is made as an order with one booking line and HELD until
    paid: the payment page, the receipt-after-payment, approval first when
    the service needs it, and the hold released if the page fails to open;
  * paid → confirmed (webhook and "marked paid"), never before: the owner
    can't confirm an unpaid hold, accepting an approval approves the order;
  * a payment that lands after the hold was released is refunded;
  * shop booking lines paid by card are held the same way.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_booking_deposits.py -q
"""
import asyncio
import inspect
import os
import pathlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.cappe.models.cappe import CappeBookingRequest, CappeBookingTypeCreate  # noqa: E402
from app.cappe.routes import bookings as owner_routes  # noqa: E402
from app.cappe.routes import payments as payments_mod  # noqa: E402
from app.cappe.routes import shop as shop_mod  # noqa: E402
from app.cappe.routes.public import bookings as public_mod  # noqa: E402
from app.cappe.services import booking_payments as bp  # noqa: E402
from app.cappe.services import commerce  # noqa: E402
from app.cappe.services.render import order_page  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

SITE, TYPE, BOOKING, ORDER = uuid4(), uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)
ASSETS = pathlib.Path(commerce.__file__).parent / "render" / "assets"
MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "zzzzcappe49_booking_payments.py"
REQUEST = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1)})


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class Conn:
    def __init__(self, answers=()):
        self.answers, self.calls = list(answers), []

    def _answer(self, sql, args):
        self.calls.append((sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value
        return None

    async def fetchrow(self, sql, *args):
        return self._answer(sql, args)

    async def fetchval(self, sql, *args):
        return self._answer(sql, args)

    async def fetch(self, sql, *args):
        return self._answer(sql, args) or []

    async def execute(self, sql, *args):
        self._answer(sql, args)

    def transaction(self):
        return Ctx(self)

    def sql(self, needle):
        return [c for c in self.calls if needle in c[0]]


class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((getattr(fn, "__name__", str(fn)), args))

    def names(self):
        return [n for n, _a in self.tasks]


# ── what's charged now ───────────────────────────────────────────────────────

@pytest.mark.parametrize("btype,quote,expected", [
    ({"payment_mode": "none"}, 5000, (0, 5000)),
    ({"payment_mode": "full"}, 5000, (5000, 0)),
    ({"payment_mode": "deposit", "deposit_cents": 1500}, 5000, (1500, 3500)),
    ({"payment_mode": "deposit", "deposit_cents": 9000}, 5000, (5000, 0)),   # never more than the price
    ({"payment_mode": "deposit", "deposit_cents": 1500}, 0, (0, 0)),
])
def test_what_is_charged_now_and_left_for_the_appointment(btype, quote, expected):
    assert bp.amount_due_now(btype, quote) == expected


def test_the_line_names_the_service_and_the_time():
    assert bp.line_title({"name": "Cut"}, 3500, "Wed Oct 7, 10:00 AM PDT") == "Deposit — Cut, Wed Oct 7, 10:00 AM PDT"
    assert bp.line_title({"name": "Cut"}, 0) == "Cut"


OWNER = {"plan": "business", "status": "active", "stripe_account_id": "acct_1", "stripe_charges_enabled": True,
         "email": "owner@example.com", "name": "Owner"}
SELLS = SimpleNamespace(can_sell=True, platform_fee_bps=200, has=lambda _f: False)


@pytest.mark.parametrize("btype,owner,ent,expected", [
    ({"payment_mode": "deposit"}, OWNER, SELLS, True),
    ({"payment_mode": "none"}, OWNER, SELLS, False),
    ({"payment_mode": "full"}, {**OWNER, "stripe_charges_enabled": False}, SELLS, False),
    ({"payment_mode": "full"}, {**OWNER, "status": "suspended"}, SELLS, False),
    ({"payment_mode": "full"}, OWNER, SimpleNamespace(can_sell=False), False),
])
def test_payment_is_taken_only_where_it_can_be(btype, owner, ent, expected):
    conn = Conn()
    assert asyncio.run(bp.takes_payment_for(conn, SITE, btype, owner=owner, ent=ent)) is expected
    assert conn.calls == []


def test_a_deposit_needs_an_amount():
    with pytest.raises(ValidationError):
        CappeBookingTypeCreate(name="Cut", payment_mode="deposit")
    assert CappeBookingTypeCreate(name="Cut", payment_mode="deposit", deposit_cents=1500).deposit_cents == 1500


def test_taking_payment_needs_a_plan_that_sells(monkeypatch):
    monkeypatch.setattr(owner_routes, "resolve_entitlements", AsyncMock(return_value=SimpleNamespace(can_sell=False)))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(owner_routes._check_payment_mode(Conn(), SimpleNamespace(plan="free"), "deposit"))
    assert exc.value.status_code == 402
    asyncio.run(owner_routes._check_payment_mode(Conn(), SimpleNamespace(plan="free"), "none"))


# ── booking with a deposit ───────────────────────────────────────────────────

BTYPE = {"id": TYPE, "name": "Cut", "duration_minutes": 60, "status": "active", "price_cents": 5000,
         "pricing_mode": "flat", "requires_approval": False, "buffer_minutes": 0,
         "payment_mode": "deposit", "deposit_cents": 1500}


def _wire(monkeypatch, *, btype=BTYPE, stripe_fails=False, requires_approval=False):
    conn = Conn([("FROM cappe_booking_types", btype)])
    made = {"hold": None, "order": None}

    async def _create(_conn, _site, _btype, _starts, _name, _email, _note, **kw):
        made["hold"] = kw["hold"]
        return {"id": BOOKING, "status": "pending", "starts_at": NOW, "ends_at": NOW, "quoted_price_cents": 5000,
                "requires_approval": requires_approval, "access_token": "t" * 32}

    async def _order(_conn, **kw):
        made["order"] = kw
        return {"id": ORDER, "status": "pending", "subtotal_cents": kw["pay_now"], "tax_cents": 0,
                "shipping_cents": 0, "total_cents": kw["pay_now"], "currency": "USD", "access_token": "o" * 32,
                "requires_approval": requires_approval}

    async def _checkout(**kw):
        made["checkout"] = kw
        if stripe_fails:
            raise CappeStripeError("down")
        return {"id": "cs_1", "url": "https://pay.example.com/cs_1"}

    site = {"id": SITE, "name": "Salon", "timezone": "UTC", "subdomain": "salon", "custom_domain": None,
            "currency": "USD"}
    monkeypatch.setattr(public_mod, "client_ip", lambda _r: "127.0.0.1")
    monkeypatch.setattr(public_mod, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(public_mod, "_reject_reserved", lambda _e: None)
    monkeypatch.setattr(public_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_mod, "_published_site", AsyncMock(return_value=site))
    monkeypatch.setattr(public_mod, "_location_ctx", AsyncMock(return_value=(None, "UTC")))
    monkeypatch.setattr(public_mod, "_site_rider", AsyncMock(return_value=[]))
    monkeypatch.setattr(public_mod, "_active_staff_for_type", AsyncMock(return_value=[]))
    monkeypatch.setattr(public_mod, "create_booking_in_tx", _create)
    monkeypatch.setattr(public_mod, "create_booking_order", _order)
    monkeypatch.setattr(public_mod, "open_order_checkout", _checkout)
    release = AsyncMock(return_value=True)
    monkeypatch.setattr(public_mod, "release_unpaid_order", release)
    monkeypatch.setattr(public_mod, "fetch_site_owner", AsyncMock(return_value=OWNER))
    monkeypatch.setattr(public_mod, "resolve_entitlements", AsyncMock(return_value=SELLS))
    monkeypatch.setattr(public_mod, "site_origins", lambda _s: ["https://salon.gummfit.com"])
    monkeypatch.setattr(public_mod, "_site_owner", AsyncMock(return_value=OWNER))
    monkeypatch.setattr(public_mod, "_recipient_send_ok", AsyncMock(return_value=True))
    return conn, made, release


def _book(bg=None):
    body = CappeBookingRequest(booking_type_id=TYPE, starts_at=NOW, customer_email="ana@example.com",
                               customer_name="Ana")
    return asyncio.run(public_mod.public_create_booking("salon", body, REQUEST, bg or Background()))


def test_a_deposit_booking_is_held_made_an_order_and_sent_to_pay(monkeypatch):
    _conn, made, _release = _wire(monkeypatch)
    bg = Background()
    out = _book(bg)
    assert made["hold"] is True
    assert (made["order"]["pay_now"], made["order"]["balance"]) == (1500, 3500)
    assert made["order"]["title"].startswith("Deposit — Cut, ")
    assert out["checkout_url"] == "https://pay.example.com/cs_1"
    assert (out["pay_now_cents"], out["balance_due_cents"]) == (1500, 3500)
    # Paid → its order page; backed out → the handler that releases the hold.
    kw = made["checkout"]
    assert kw["success_url"].endswith(f"/order/{'o' * 32}") and "checkout-return" in kw["cancel_url"]
    assert kw["line_rows"][0][2:4] == (1500, 1) and kw["has_physical"] is False
    # The customer hears from us when it's paid, not before.
    assert bg.names() == []


def test_a_service_that_needs_approval_waits_for_it_before_anyone_pays(monkeypatch):
    _conn, made, _release = _wire(monkeypatch, requires_approval=True)
    bg = Background()
    out = _book(bg)
    assert out["checkout_url"] is None and out["order_url"].endswith("/order/" + "o" * 32)
    assert "checkout" not in made
    assert "send_cappe_booking_received_email" in bg.names()


def test_a_payment_page_that_wont_open_releases_the_hold(monkeypatch):
    _conn, _made, release = _wire(monkeypatch, stripe_fails=True)
    with pytest.raises(HTTPException) as exc:
        _book()
    assert exc.value.status_code == 502 and "booking wasn't made" in exc.value.detail
    release.assert_awaited_once_with(ORDER, SITE)


def test_a_service_without_payment_books_as_before(monkeypatch):
    _conn, made, _release = _wire(monkeypatch, btype={**BTYPE, "payment_mode": "none"})
    bg = Background()
    out = _book(bg)
    assert made["hold"] is False and made["order"] is None and "checkout_url" not in out
    assert "send_cappe_booking_received_email" in bg.names()
    public_mod.fetch_site_owner.assert_not_awaited()          # no extra lookups for a free-of-deposit service


def test_a_free_paid_booking_is_simply_confirmed(monkeypatch):
    conn = Conn()
    booking = {"id": BOOKING, "quoted_price_cents": 0, "requires_approval": False, "status": "pending"}
    out_booking, order, pay_now, balance = asyncio.run(public_mod._paid_booking(
        conn, {"id": SITE}, {**BTYPE, "payment_mode": "full"}, booking, "a@example.com",
        SimpleNamespace(customer_name="A", note=None), "UTC"))
    assert order is None and pay_now == 0 and out_booking["status"] == "confirmed"
    assert conn.sql("SET status = 'confirmed'")


def test_the_booking_order_is_one_line_for_whats_due_now():
    conn = Conn([("INSERT INTO cappe_orders", {"id": ORDER})])
    asyncio.run(bp.create_booking_order(
        conn, site={"id": SITE}, btype=BTYPE, booking={"id": BOOKING, "requires_approval": True},
        email="a@example.com", name="A", note=None, currency="USD", pay_now=1500, balance=3500, title="Deposit — Cut",
    ))
    (_sql, args), = conn.sql("INSERT INTO cappe_orders")
    assert args[3] == 1500 and args[-1] is True          # subtotal and total; approval carried over
    (_sql, item), = conn.sql("INSERT INTO cappe_order_items")
    assert item[2:4] == ("Deposit — Cut", 1500) and item[-2:] == (BOOKING, 3500)


# ── held until paid ──────────────────────────────────────────────────────────

def test_paying_confirms_only_the_held_bookings_of_that_order():
    conn = Conn([("UPDATE cappe_bookings", [{"id": BOOKING}])])
    assert asyncio.run(bp.confirm_paid_bookings(conn, ORDER)) == 1
    (sql, args), = conn.calls
    assert "WHERE status = 'pending'" in sql and "order_id = $1" in sql and args == (ORDER,)


def test_the_webhook_confirms_the_bookings_of_a_paid_order():
    src = inspect.getsource(payments_mod._mark_order_paid)
    assert src.index("await confirm_paid_bookings(conn, row[\"id\"])") < src.index("issue_receipt_for_paid_order")


def test_marking_an_order_paid_by_hand_confirms_its_bookings():
    src = inspect.getsource(shop_mod.update_order_status)
    assert "if became_paid:" in src and "await confirm_paid_bookings(conn, order_id)" in src


def test_accepting_an_order_the_buyer_pays_for_keeps_its_bookings_held(monkeypatch):
    conn = Conn([("UPDATE cappe_orders", {"id": ORDER, "pay_by": NOW, "customer_email": None})])
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", AsyncMock(return_value={"id": SITE, "name": "S", "timezone": "UTC"}))
    monkeypatch.setattr(shop_mod, "_order_row", lambda order, items: dict(order))
    monkeypatch.setattr(shop_mod, "_order_token", AsyncMock(return_value="tok"))
    asyncio.run(shop_mod.accept_order(SITE, ORDER, Background(), account=SimpleNamespace(id=uuid4())))
    assert conn.sql("UPDATE cappe_bookings") == []


def test_a_payment_after_the_hold_was_released_is_refunded(monkeypatch):
    refunded = AsyncMock()
    monkeypatch.setattr(payments_mod, "_refund_stray_order_payment", refunded)
    monkeypatch.setattr(payments_mod, "_holds_bookings", AsyncMock(return_value=True))

    class ConnScript(Conn):
        async def fetchrow(self, sql, *args):
            return None                                # the paid UPDATE matches nothing: it was released

        async def fetchval(self, sql, *args):
            return "cancelled"

    monkeypatch.setattr(payments_mod, "get_connection", lambda: Ctx(ConnScript()))
    obj = {"id": "cs_1", "payment_intent": "pi_1", "metadata": {"order_id": str(ORDER)}}
    out = asyncio.run(payments_mod._mark_order_paid(obj, {"account": "acct_1"}, Background()))
    assert out == {"received": True, "status": "refunded_released_booking"}
    refunded.assert_awaited_once()


# ── the owner can't confirm an unpaid hold ───────────────────────────────────

def _owner(monkeypatch, conn):
    monkeypatch.setattr(owner_routes, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(owner_routes, "get_owned_site", AsyncMock(return_value={"id": SITE, "name": "S", "timezone": "UTC"}))
    monkeypatch.setattr(owner_routes, "_booking_view", AsyncMock(return_value={"id": "view"}))
    return SimpleNamespace(id=uuid4(), plan="business")


HOLD = {"id": ORDER, "status": "pending", "requires_approval": False, "subtotal_cents": 1500}


def test_confirming_an_unpaid_hold_is_refused(monkeypatch):
    from app.cappe.models.cappe import CappeBookingStatusUpdate
    conn = Conn([("FOR UPDATE", {"status": "pending"}), ("JOIN cappe_orders o ON o.id = oi.order_id", HOLD)])
    account = _owner(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(owner_routes.update_booking_status(
            SITE, BOOKING, CappeBookingStatusUpdate(status="confirmed"), Background(), account=account))
    assert exc.value.status_code == 409 and "waiting for its payment" in exc.value.detail
    assert not conn.sql("UPDATE cappe_bookings")


def test_accepting_a_paid_booking_that_needs_approval_approves_its_order(monkeypatch):
    conn = Conn([("JOIN cappe_orders o ON o.id = oi.order_id", {**HOLD, "requires_approval": True})])
    account = _owner(monkeypatch, conn)
    accept = AsyncMock()
    monkeypatch.setattr(shop_mod, "accept_order", accept)
    assert asyncio.run(owner_routes.accept_booking(SITE, BOOKING, Background(), account=account)) == {"id": "view"}
    assert accept.await_args.args[:2] == (SITE, ORDER)
    assert not conn.sql("UPDATE cappe_bookings")      # still held: confirmed once paid


def test_accepting_a_hold_that_needs_no_approval_is_refused(monkeypatch):
    account = _owner(monkeypatch, Conn([("JOIN cappe_orders o ON o.id = oi.order_id", HOLD)]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(owner_routes.accept_booking(SITE, BOOKING, Background(), account=account))
    assert exc.value.status_code == 409


def test_the_owner_sees_what_is_awaiting_payment_and_what_is_left_to_collect():
    assert "AS awaiting_payment" in owner_routes._BOOKING_VIEW and "balance_due_cents" in owner_routes._BOOKING_VIEW


# ── the shop, the order page, the widget ─────────────────────────────────────

def test_a_shop_booking_paid_by_card_is_held_too():
    src = inspect.getsource(commerce.create_public_order)
    assert 'hold=takes_cards and (product["price_cents"] or 0) > 0' in src


def test_the_order_page_says_what_is_due_at_the_appointment():
    html = order_page._items_html({"status": "paid", "currency": "USD"}, [
        {"title": "Deposit — Cut", "quantity": 1, "unit_price_cents": 1500, "balance_due_cents": 3500}])
    assert "$35.00 more is due at the appointment." in html


def test_the_widget_sends_the_buyer_to_pay_and_names_the_deposit():
    js = (ASSETS / "booking.js").read_text()
    assert "if(res.checkout_url){" in js and "window.location=res.checkout_url" in js
    assert "' deposit'" in js


def test_the_migration_chains():
    src = MIGRATION.read_text()
    assert 'down_revision = "zzzzcappe48"' in src and 'revision = "zzzzcappe49"' in src
    assert "CHECK (payment_mode IN ('none', 'deposit', 'full'))" in src and "balance_due_cents" in src
