"""Order page, pay after approval, the bag — the 2026-10 commerce readiness review, PR 4.

What each block pins:

  * a paying web buyer lands on their order page; one who backs out goes
    through the release handler; the app return is untouched;
  * an order that needs approval is never sent to Stripe at checkout, and the
    owner's Accept opens a pay-by window and emails the buyer a pay link;
  * "Pay now" opens one page per order, priced from the order, and refuses
    every order it shouldn't;
  * a page "Pay now" replaced can't release the order when it expires, and a
    payment on it is refunded (in test_cappe_payments_webhook.py);
  * the order page: what it says in each state, what it releases, what it
    never leaks, and that it resolves on its own store only;
  * the buyer is told when the order is accepted, declined and shipped;
  * the quote says whether checkout takes cards (the bag asks for an
    address only when it doesn't), and the address is stored with the order;
  * the storefront scripts: the bag, the product panel, the order page.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_order_page.py -q
"""
import asyncio
import json
import os
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.cappe.models.shop import CappeShippingAddressInput  # noqa: E402
from app.cappe.routes import payments as payments_mod  # noqa: E402
from app.cappe.routes import render as render_mod  # noqa: E402
from app.cappe.routes import shop as shop_mod  # noqa: E402
from app.cappe.routes.public import shop as public_shop  # noqa: E402
from app.cappe.services import commerce  # noqa: E402
from app.cappe.services import email as mail  # noqa: E402
from app.cappe.services.common import order_page_url, site_public_origin  # noqa: E402
from app.cappe.services.render import order_page as page_mod  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

SITE, ORDER = uuid4(), uuid4()
TOKEN = "ab" * 16
ACCOUNT = SimpleNamespace(id=uuid4(), plan="business")
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
ASSETS = pathlib.Path(commerce.__file__).parent / "render" / "assets"


class Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

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

    async def execute(self, sql, *args):
        self._answer("execute", sql, args)

    def transaction(self):
        return Tx()

    def sql(self, needle):
        return [c for c in self.calls if needle in c[1]]


class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn.__name__, args))

    def names(self):
        return [n for n, _a in self.tasks]


# ── links ────────────────────────────────────────────────────────────────────

def test_links_use_the_custom_domain_when_the_store_has_one():
    assert site_public_origin({"subdomain": "shop", "custom_domain": "Shop.Example.com."}) == "https://shop.example.com"
    assert order_page_url({"subdomain": "shop", "custom_domain": "shop.example.com"}, TOKEN) == \
        f"https://shop.example.com/order/{TOKEN}"
    # A Stripe return stays on the host the buyer used.
    assert order_page_url({}, TOKEN, origin="https://shop.gummfit.com") == f"https://shop.gummfit.com/order/{TOKEN}"
    assert order_page_url({}, "") is None


def test_return_urls_send_a_payer_to_the_order_page_and_a_quitter_to_the_release():
    site = {"subdomain": "shop", "custom_domain": "shop.example.com"}
    ok, back = commerce.bind_return_urls("https://shop.example.com/p/menu?x=1", "https://shop.example.com/p/menu", site, TOKEN)
    assert ok == f"https://shop.example.com/order/{TOKEN}"
    assert back.startswith("https://shop.example.com/__cappe/checkout-return?o=" + TOKEN)
    app_ok, app_back = commerce.bind_return_urls(
        "https://shop.example.com/__cappe/app-return", "https://shop.example.com/__cappe/app-return", site, TOKEN,
    )
    assert app_ok.endswith(f"/__cappe/app-return?o={TOKEN}&r=success")
    assert app_back.endswith(f"/__cappe/app-return?o={TOKEN}&r=cancel")
    assert commerce.bind_return_urls(None, None, site, TOKEN) == (None, None)


# ── checkout of an approval order ────────────────────────────────────────────

class CheckoutConn:
    def __init__(self, product):
        self.product, self.order, self.items = product, None, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return self

    async def fetch(self, sql, *args):
        return []

    async def fetchrow(self, sql, *args):
        if "FROM cappe_products" in sql:
            return self.product
        if "FROM cappe_sites" in sql:
            return {"tax_rate_bps": 0, "tax_label": None, "shipping_flat_cents": 600,
                    "shipping_free_threshold_cents": None, "shipping_label": None}
        if "INSERT INTO cappe_orders" in sql:
            self.order = {"id": ORDER, "status": "pending", "access_token": TOKEN, "subtotal_cents": args[3],
                          "tax_cents": args[4], "shipping_cents": args[5], "total_cents": args[6],
                          "currency": args[7], "requires_approval": args[9], "shipping_address": args[10]}
            return self.order
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        if sql == "SELECT NOW()":
            return NOW
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        if "INSERT INTO cappe_order_items" in sql:
            self.items.append(args)


def _wire_checkout(monkeypatch, *, requires_approval, fulfillment="digital", stripe=None, owner_cards=True):
    from app.cappe.models.shop import CappeCartItem, CappeCheckoutRequest
    product = {"id": uuid4(), "name": "Mug", "price_cents": 1500, "currency": "USD", "inventory": None,
               "low_stock_threshold": None, "status": "active", "fulfillment": fulfillment,
               "booking_type_id": None, "requires_approval": requires_approval, "intake_fields": "[]"}
    conn = CheckoutConn(product)
    owner = {"plan": "business", "status": "active", "email": "owner@example.com", "name": "Owner",
             "stripe_account_id": "acct_1" if owner_cards else None, "stripe_charges_enabled": owner_cards}
    stripe = stripe or SimpleNamespace(create_checkout_session=AsyncMock(return_value={"id": "cs_1", "url": "https://pay"}))
    monkeypatch.setattr(commerce, "get_connection", lambda: conn)
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(commerce, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(commerce, "lock_stock_rows", AsyncMock())
    monkeypatch.setattr(commerce, "fetch_site_owner", AsyncMock(return_value=owner))
    monkeypatch.setattr(commerce, "resolve_entitlements", AsyncMock(return_value=SimpleNamespace(platform_fee_bps=200, has=lambda _f: False)))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    monkeypatch.setattr(commerce, "check_recipient_send_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(commerce, "get_cappe_stripe", lambda: stripe)
    site = {"id": SITE, "name": "Store", "timezone": "UTC", "subdomain": "shop", "custom_domain": "shop.example.com"}
    body = CappeCheckoutRequest(
        customer_email="buyer@example.com", items=[CappeCartItem(product_id=product["id"], quantity=1)],
        success_url="https://shop.example.com/", cancel_url="https://shop.example.com/",
        shipping_address={"line1": "1 Main St", "city": "Oakland", "country": "US"},
    )
    return site, body, conn, stripe


@pytest.mark.asyncio
async def test_an_approval_order_is_not_charged_at_checkout(monkeypatch):
    """It used to be: the buyer was charged at once and the order skipped the
    approval queue."""
    site, body, conn, stripe = _wire_checkout(monkeypatch, requires_approval=True)
    bg = __import__("fastapi").BackgroundTasks()
    out = await commerce.create_public_order(site, body, bg)
    assert out["checkout_url"] is None and out["requires_approval"] is True
    stripe.create_checkout_session.assert_not_awaited()
    receipt = next(t for t in bg.tasks if t.func.__name__ == "send_cappe_order_receipt_email")
    assert receipt.args[7] == f"https://shop.example.com/order/{TOKEN}"
    assert receipt.args[8] == "card_after_approval"


@pytest.mark.asyncio
async def test_an_ordinary_card_order_opens_its_page_and_records_when(monkeypatch):
    site, body, conn, stripe = _wire_checkout(monkeypatch, requires_approval=False)
    executed = []
    orig_execute = conn.execute

    async def _execute(sql, *args):
        executed.append(sql)
        await orig_execute(sql, *args)

    conn.execute = _execute
    out = await commerce.create_public_order(site, body, __import__("fastapi").BackgroundTasks())
    assert out["checkout_url"] == "https://pay"
    kwargs = stripe.create_checkout_session.await_args.kwargs
    assert kwargs["success_url"] == f"https://shop.example.com/order/{TOKEN}"
    assert any("checkout_opened_at = NOW()" in s for s in executed)


@pytest.mark.asyncio
async def test_a_physical_order_keeps_the_address_the_buyer_typed(monkeypatch):
    site, body, conn, _stripe = _wire_checkout(monkeypatch, requires_approval=True, fulfillment="physical")
    await commerce.create_public_order(site, body, __import__("fastapi").BackgroundTasks())
    stored = json.loads(conn.order["shipping_address"])
    assert stored == {"name": None, "phone": None, "address": {
        "line1": "1 Main St", "line2": None, "city": "Oakland", "state": None, "postal_code": None, "country": "US"}}


@pytest.mark.asyncio
async def test_a_digital_order_ignores_a_shipping_address(monkeypatch):
    site, body, conn, _stripe = _wire_checkout(monkeypatch, requires_approval=True, fulfillment="digital")
    await commerce.create_public_order(site, body, __import__("fastapi").BackgroundTasks())
    assert conn.order["shipping_address"] is None


def test_a_shipping_address_needs_a_real_country_code():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CappeShippingAddressInput(line1="1 Main", city="Oakland", country="usa")


# ── "Pay now" ────────────────────────────────────────────────────────────────

def _pay_row(**kw):
    return {
        "id": ORDER, "site_id": SITE, "status": "pending", "requires_approval": False, "subscription_id": None,
        "pay_by": NOW + timedelta(days=2), "overdue": False, "subtotal_cents": 3000, "tax_cents": 240,
        "shipping_cents": 600, "total_cents": 3840, "currency": "USD", "customer_email": "buyer@example.com",
        "stripe_session_id": None, "access_token": TOKEN, "site_name": "Store", "slug": "shop",
        "subdomain": "shop", "custom_domain": None, "tax_label": "Sales tax", "shipping_label": None,
        "owner_id": uuid4(), "plan": "business", "owner_status": "active", "owner_email": "o@example.com",
        "owner_name": "Owner", "stripe_account_id": "acct_1", "stripe_charges_enabled": True, **kw,
    }


class PayStripe:
    def __init__(self, state="expired"):
        self.state, self.expired, self.opened = state, [], []

    async def expire_checkout_session(self, account, session):
        self.expired.append(session)
        return self.state

    async def create_checkout_session(self, **kw):
        self.opened.append(kw)
        return {"id": "cs_new", "url": "https://pay/new"}


def _wire_pay(monkeypatch, row, stripe=None):
    items = [{"product_id": uuid4(), "title": "Beans", "unit_price_cents": 1500, "quantity": 2, "fulfillment": "physical"}]
    conn = SqlConn([("WHERE o.access_token = $1", row), ("FROM cappe_order_items", items)])
    stripe = stripe or PayStripe()
    monkeypatch.setattr(commerce, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(commerce, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(commerce, "resolve_entitlements", AsyncMock(return_value=SimpleNamespace(platform_fee_bps=200, has=lambda _f: False)))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    return conn, stripe


def test_pay_now_charges_what_the_order_says_and_returns_to_its_page(monkeypatch):
    conn, stripe = _wire_pay(monkeypatch, _pay_row())
    out = asyncio.run(commerce.pay_for_order(TOKEN))
    assert out == {"checkout_url": "https://pay/new"}
    (kw,) = stripe.opened
    # Both returns are the order page: paid or not, the buyer comes back to it.
    assert kw["success_url"] == kw["cancel_url"]
    assert kw["success_url"].startswith("https://shop.") and kw["success_url"].endswith(f"/order/{TOKEN}")
    # Frozen order prices plus the tax line; the shipping row is Stripe's option.
    assert [(li["price_data"]["unit_amount"], li["quantity"]) for li in kw["line_items"]] == [(1500, 2), (240, 1)]
    assert kw["shipping_option"] == {"label": "Shipping", "amount_cents": 600}
    assert kw["metadata"]["order_id"] == str(ORDER) and kw["application_fee_cents"] == 60
    assert "checkout_opened_at = NOW()" in conn.sql("SET stripe_session_id")[0][1]


def test_pay_now_closes_the_previous_page_first(monkeypatch):
    _conn, stripe = _wire_pay(monkeypatch, _pay_row(stripe_session_id="cs_old"))
    asyncio.run(commerce.pay_for_order(TOKEN))
    assert stripe.expired == ["cs_old"] and len(stripe.opened) == 1


def test_pay_now_opens_nothing_when_the_previous_page_was_paid(monkeypatch):
    _conn, stripe = _wire_pay(monkeypatch, _pay_row(stripe_session_id="cs_old"), PayStripe(state="complete"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(commerce.pay_for_order(TOKEN))
    assert exc.value.status_code == 409 and "already being processed" in exc.value.detail
    assert stripe.opened == []


@pytest.mark.parametrize("change,code,fragment", [
    ({"status": "paid"}, 409, "already been paid"),
    ({"status": "cancelled"}, 409, "no longer open"),
    ({"requires_approval": True}, 409, "hasn't approved"),
    ({"overdue": True}, 409, "time to pay"),
    ({"subscription_id": uuid4()}, 409, "subscription"),
    ({"subtotal_cents": 0}, 409, "nothing to pay"),
    ({"stripe_charges_enabled": False}, 409, "isn't taking card payments"),
    ({"owner_status": "suspended"}, 409, "isn't taking card payments"),
])
def test_pay_now_refuses_what_it_should(monkeypatch, change, code, fragment):
    _conn, stripe = _wire_pay(monkeypatch, _pay_row(**change))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(commerce.pay_for_order(TOKEN))
    assert exc.value.status_code == code and fragment in exc.value.detail
    assert stripe.opened == [] and stripe.expired == []


def test_pay_now_for_an_unknown_token_is_a_404(monkeypatch):
    _wire_pay(monkeypatch, None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(commerce.pay_for_order(TOKEN))
    assert exc.value.status_code == 404


def test_the_pay_route_turns_a_stripe_outage_into_a_clear_502(monkeypatch):
    monkeypatch.setattr(public_shop, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(public_shop, "client_ip", lambda _r: "127.0.0.1")
    monkeypatch.setattr(public_shop, "pay_for_order", AsyncMock(side_effect=CappeStripeError("down")))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(public_shop.public_pay_order(TOKEN, None))
    assert exc.value.status_code == 502 and "Nothing was charged" in exc.value.detail


# ── a page that ends doesn't release an order it no longer stands for ────────

def test_only_the_current_page_ending_releases_an_order(monkeypatch):
    conn = SqlConn([("UPDATE cappe_orders o", None)])
    monkeypatch.setattr(payments_mod, "get_connection", lambda: Ctx(conn))
    asyncio.run(payments_mod._cancel_unpaid_session(
        "checkout.session.expired",
        {"id": "cs_old", "metadata": {"order_id": str(ORDER)}}, {"account": "acct_1"},
    ))
    (_, sql, args), = conn.sql("UPDATE cappe_orders o")
    assert "(o.stripe_session_id IS NULL OR o.stripe_session_id = $3)" in sql
    assert "(o.pay_by IS NULL OR o.pay_by < NOW())" in sql
    assert args[2] == "cs_old"


# ── the owner's Accept / Decline / shipping ──────────────────────────────────

def _order(**kw):
    return {"id": ORDER, "status": "pending", "customer_email": "buyer@example.com", "customer_name": "Buyer",
            "total_cents": 3840, "subtotal_cents": 3000, "currency": "USD", "pay_by": None,
            "carrier": None, "tracking_number": None, "metadata": "{}", "shipping_address": None, **kw}


def _wire_owner(monkeypatch, *, updated, takes_cards=True, current=None):
    items = [{"title": "Beans", "quantity": 2, "fulfillment": "physical", "id": uuid4(), "product_id": None,
              "unit_price_cents": 1500, "intake_answers": "{}", "selected_options": "[]",
              "deliverable_url": None, "booking_id": None}]
    conn = SqlConn([
        ("stripe_charges_enabled FROM cappe_accounts", takes_cards),
        ("SELECT status FROM cappe_orders", (current or {}).get("status")),
        ("FOR UPDATE", current),
        ("UPDATE cappe_orders SET shipped_notified_at = NOW() WHERE id = $1 AND shipped_notified_at IS NULL", ORDER),
        ("UPDATE cappe_orders", updated),
        ("FROM cappe_order_items", items),
        ("SELECT access_token FROM cappe_orders", TOKEN),
    ])
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", AsyncMock(return_value={
        "id": SITE, "name": "Store", "timezone": "America/New_York", "subdomain": "shop", "custom_domain": None}))
    monkeypatch.setattr(shop_mod, "_order_row", lambda order, items=None: dict(order))
    return conn


@pytest.mark.parametrize("takes_cards", [True, False])
def test_accepting_an_order_opens_a_pay_window_and_emails_the_buyer(monkeypatch, takes_cards):
    pay_by = NOW + timedelta(days=3) if takes_cards else None
    conn = _wire_owner(monkeypatch, updated=_order(pay_by=pay_by), takes_cards=takes_cards)
    bg = Background()
    asyncio.run(shop_mod.accept_order(SITE, ORDER, bg, account=ACCOUNT))
    (_, sql, args), = conn.sql("SET requires_approval = false")
    assert "pay_by = CASE WHEN $3 AND subtotal_cents > 0" in sql and f"'{shop_mod.PAY_WINDOW_DAYS} days'" in sql
    assert args[2] is takes_cards
    (name, eargs), = [t for t in bg.tasks if t[0] == "send_cappe_order_approved_email"]
    assert eargs[0] == "buyer@example.com" and eargs[4] == 3840
    assert eargs[6].endswith(f"/order/{TOKEN}")
    assert (eargs[7] is not None) is takes_cards       # a pay-by date only when the buyer pays by card


def test_accepting_an_order_with_nothing_to_pay_settles_it(monkeypatch):
    """No payment will ever come for a $0 order (a code took it all off, or
    free items), so approval is the last step: it becomes paid, which also
    releases any download."""
    conn = _wire_owner(monkeypatch, updated=_order(status="paid", subtotal_cents=0, total_cents=0))
    bg = Background()
    asyncio.run(shop_mod.accept_order(SITE, ORDER, bg, account=ACCOUNT))
    (_, sql, _args), = conn.sql("SET requires_approval = false")
    assert "status = CASE WHEN subtotal_cents <= 0 THEN 'paid' ELSE status END" in sql
    assert "paid_at = CASE WHEN subtotal_cents <= 0 THEN NOW() ELSE paid_at END" in sql
    (_name, eargs), = [t for t in bg.tasks if t[0] == "send_cappe_order_approved_email"]
    assert eargs[4] == 0 and eargs[7] is None          # nothing to pay, so no pay-by date


def test_declining_an_order_tells_the_buyer(monkeypatch):
    _wire_owner(monkeypatch, updated=_order(status="declined"))
    monkeypatch.setattr(shop_mod, "_close_open_checkout", AsyncMock())
    monkeypatch.setattr(shop_mod, "restock_order", AsyncMock())
    monkeypatch.setattr(shop_mod, "release_order_bookings", AsyncMock())
    monkeypatch.setattr("app.cappe.services.push.schedule_push", lambda *_a: None)
    bg = Background()
    asyncio.run(shop_mod.decline_order(SITE, ORDER, SimpleNamespace(reason="Sold out"), bg, account=ACCOUNT))
    (name, eargs), = bg.tasks
    assert name == "send_cappe_order_declined_email" and eargs[-1] == "Sold out"


def _patch_order(monkeypatch, body, *, current, updated, notified=True):
    from app.cappe.models.shop import CappeOrderStatusUpdate
    conn = _wire_owner(monkeypatch, updated=updated, current=current)
    if not notified:
        conn.answers.insert(0, ("shipped_notified_at IS NULL", None))
    monkeypatch.setattr(shop_mod, "_close_open_checkout", AsyncMock())
    monkeypatch.setattr("app.cappe.services.push.schedule_push", lambda *_a: None)
    bg = Background()
    asyncio.run(shop_mod.update_order_status(SITE, ORDER, CappeOrderStatusUpdate(**body), bg, account=ACCOUNT))
    return conn, bg


def test_fulfilling_a_shipped_order_emails_the_buyer_once(monkeypatch):
    _conn, bg = _patch_order(monkeypatch, {"status": "fulfilled"}, current={"status": "paid", "tracking_number": None},
                             updated=_order(status="fulfilled"))
    (name, eargs), = [t for t in bg.tasks if t[0] == "send_cappe_order_shipped_email"]
    assert eargs[6].endswith(f"/order/{TOKEN}") and eargs[7] is True   # physical → "shipped"


def test_a_second_fulfil_sends_nothing_more(monkeypatch):
    _conn, bg = _patch_order(monkeypatch, {"status": "fulfilled"}, current={"status": "paid", "tracking_number": None},
                             updated=_order(status="fulfilled"), notified=False)
    assert "send_cappe_order_shipped_email" not in bg.names()


def test_a_new_tracking_number_is_always_sent(monkeypatch):
    _conn, bg = _patch_order(monkeypatch, {"carrier": "USPS", "tracking_number": "9400"},
                             current={"status": "fulfilled", "tracking_number": "9300"},
                             updated=_order(status="fulfilled", carrier="USPS", tracking_number="9400"))
    (name, eargs), = [t for t in bg.tasks if t[0] == "send_cappe_order_shipped_email"]
    assert eargs[4:6] == ("USPS", "9400")


def test_tracking_on_an_unpaid_order_tells_nobody(monkeypatch):
    _conn, bg = _patch_order(monkeypatch, {"tracking_number": "9400"},
                             current={"status": "pending", "tracking_number": None},
                             updated=_order(status="pending", tracking_number="9400"))
    assert "send_cappe_order_shipped_email" not in bg.names()


# ── the order page ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("order,cards,headline,can_pay,poll", [
    ({"status": "paid"}, True, "Thank you — your order is confirmed", False, False),
    ({"status": "fulfilled"}, True, "Your order is complete", False, False),
    ({"status": "refunded"}, True, "This order was refunded", False, False),
    ({"status": "cancelled"}, True, "This order was cancelled", False, False),
    ({"status": "declined", "decline_reason": "Sold out"}, True, "Store couldn't accept this order", False, False),
    ({"requires_approval": True}, True, "Waiting for Store to approve your order", False, False),
    ({}, False, "Order received", False, False),
    ({"subtotal_cents": 0}, True, "Your order is confirmed", False, False),
    ({"pay_by": NOW + timedelta(days=1)}, True, "Store accepted your order", True, False),
    ({"pay_by": NOW - timedelta(days=1)}, True, "The time to pay for this order has passed", False, False),
    ({}, True, "Confirming your payment…", True, True),
])
def test_what_the_order_page_says(order, cards, headline, can_pay, poll):
    base = {"status": "pending", "site_name": "Store", "subtotal_cents": 3000, "total_cents": 3000,
            "currency": "USD", "requires_approval": False, "pay_by": None, "timezone": "UTC"}
    state = page_mod.order_state({**base, **order}, takes_cards=cards, now=NOW)
    assert (state["headline"], state["can_pay"], state["poll"]) == (headline, can_pay, poll)


def _render(order, items, **kw):
    site = {"name": "Store", "slug": "shop", "theme_config": {}, "meta_config": {}, "timezone": "UTC"}
    base = {"id": ORDER, "status": "paid", "site_name": "Store", "subtotal_cents": 3000, "tax_cents": 240,
            "shipping_cents": 0, "total_cents": 3240, "refunded_cents": 0, "currency": "USD",
            "requires_approval": False, "pay_by": None, "timezone": "UTC", "receipt_number": "ST-00042",
            "carrier": "UPS", "tracking_number": "1Z9", "shipping_address": None, "tax_label": "Tax",
            "shipping_label": "Shipping", "decline_reason": None}
    return page_mod.render_order_page(site, [], {**base, **order}, items, token=TOKEN, takes_cards=True,
                                      now=NOW, clear_cart=kw.get("clear_cart", True))


def _item(**kw):
    return {"title": "Guide", "quantity": 1, "fulfillment": "digital", "unit_price_cents": 3000,
            "selected_options": [], "download_url": "https://cdn.example.com/guide.pdf", "deliverable_url": None,
            "booking_starts_at": None, **kw}


def test_a_paid_digital_order_hands_over_the_download_and_receipt():
    html = _render({}, [_item()])
    assert 'href="https://cdn.example.com/guide.pdf"' in html and "Download your receipt" in html
    assert "Order ST-00042" in html and "Tracking" in html and "UPS 1Z9" in html
    # Ours alone: no index, no referrer, our script.
    assert 'name="robots" content="noindex,nofollow"' in html and 'name="referrer" content="no-referrer"' in html
    assert "data-czorder" in html and f'data-token="{TOKEN}"' in html


def test_nothing_is_released_before_payment():
    html = _render({"status": "pending", "pay_by": NOW + timedelta(days=1)}, [_item()])
    assert "cdn.example.com" not in html and "Download your receipt" not in html
    assert "appears here once payment is confirmed" in html
    assert "data-czpay" in html and "Pay $32.40" in html


def test_everything_typed_is_escaped():
    html = _render({"decline_reason": "<script>alert(1)</script>", "status": "declined"},
                   [_item(title="<img src=x onerror=alert(1)>", download_url="javascript:alert(1)")])
    assert "<script>alert(1)</script>" not in html and "<img src=x" not in html
    assert "javascript:alert" not in html


def _order_request(host="shop.gummfit.com"):
    return Request({"type": "http", "method": "GET", "path": f"/order/{TOKEN}", "client": ("127.0.0.1", 1),
                    "headers": [(b"host", host.encode())]})


def _wire_page(monkeypatch, *, site=None, order=None):
    site = site if site is not None else {
        "id": SITE, "name": "Store", "slug": "shop", "subdomain": "shop", "custom_domain": None,
        "theme_config": "{}", "meta_config": "{}", "timezone": "UTC", "account_id": uuid4()}
    order = order if order is not None else {
        "id": ORDER, "status": "paid", "requires_approval": False, "approved_at": None, "pay_by": None,
        "decline_reason": None, "subtotal_cents": 3000, "tax_cents": 0, "shipping_cents": 0, "total_cents": 3000,
        "refunded_cents": 0, "currency": "USD", "carrier": None, "tracking_number": None, "shipping_address": None,
        "receipt_number": None, "stripe_session_id": "cs_1", "tax_label": None, "shipping_label": None}
    conn = SqlConn([
        ("FROM cappe_sites WHERE subdomain", site),
        ("WHERE o.access_token = $1 AND o.site_id = $2", order or None),
        ("FROM cappe_order_items", []),
        ("FROM cappe_accounts", {"stripe_account_id": "acct_1", "stripe_charges_enabled": True, "status": "active"}),
        ("FROM cappe_pages", []),
        ("SELECT NOW()", NOW),
    ])
    monkeypatch.setattr(render_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(render_mod, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(render_mod, "subdomain_from_host", lambda host: "shop" if host and "gummfit" in host else None)
    monkeypatch.setattr(render_mod, "_custom_domain_candidates", lambda host: [])
    return conn


def test_the_order_page_is_never_cached_and_never_referred(monkeypatch):
    conn = _wire_page(monkeypatch)
    response = asyncio.run(render_mod.order_page(TOKEN, _order_request()))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    # The site is found by host whatever its publish state; the order by token AND site.
    assert "status" not in conn.sql("FROM cappe_sites WHERE subdomain")[0][1]
    assert conn.sql("o.access_token = $1 AND o.site_id = $2")[0][2] == (TOKEN, SITE)


def test_another_stores_order_is_not_found(monkeypatch):
    _wire_page(monkeypatch, order={})
    response = asyncio.run(render_mod.order_page(TOKEN, _order_request()))
    assert response.status_code == 404


@pytest.mark.parametrize("token", ["", "short", "AB" * 16, "../" * 11])
def test_a_malformed_token_never_reaches_the_database(monkeypatch, token):
    conn = _wire_page(monkeypatch)
    response = asyncio.run(render_mod.order_page(token, _order_request()))
    assert response.status_code == 404 and conn.calls == []


def test_the_app_host_has_no_order_page(monkeypatch):
    _wire_page(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(render_mod.order_page(TOKEN, _order_request(host="hey-matcha.com")))
    assert exc.value.status_code == 404


# ── the buyer's emails ───────────────────────────────────────────────────────

def _capture(monkeypatch):
    sent = []

    async def _send(to, name, subject, html, text, **kw):
        sent.append({"subject": subject, "html": html, "text": text})
        return True

    monkeypatch.setattr(mail, "_send", _send)
    return sent


@pytest.mark.parametrize("approval,payment,fragment", [
    (True, "card_after_approval", "link to pay"),
    (False, "store", "Nothing has been charged"),
    (False, "free", "Your order is confirmed"),
])
def test_an_unpaid_order_is_never_called_confirmed_by_mistake(monkeypatch, approval, payment, fragment):
    """'Your order is confirmed' used to go to buyers who had paid nothing."""
    sent = _capture(monkeypatch)
    asyncio.run(mail.send_cappe_order_receipt_email(
        "b@example.com", "B", "Store", "1× Mug", 1500, "USD", approval, f"https://shop.example.com/order/{TOKEN}", payment,
    ))
    assert fragment in sent[0]["text"] and f"/order/{TOKEN}" in sent[0]["html"]
    if payment != "free":
        assert "Your order is confirmed" not in sent[0]["text"]


@pytest.mark.parametrize("pay_by,total,fragment", [
    ("Oct 9", 3840, "Pay $38.40 to complete it"),
    (None, 3840, "in touch about payment"),
    (None, 0, "There's nothing to pay"),           # a code took it all off
])
def test_the_approval_email(monkeypatch, pay_by, total, fragment):
    sent = _capture(monkeypatch)
    asyncio.run(mail.send_cappe_order_approved_email(
        "b@example.com", "B", "<Store>", "2× Beans", total, "USD", "https://x/order/t", pay_by,
    ))
    assert fragment in sent[0]["text"] and "&lt;Store&gt;" in sent[0]["html"]
    assert ("Pay now" in sent[0]["html"]) is bool(pay_by)


@pytest.mark.parametrize("shipped,subject", [(True, "Shipped — Store"), (False, "Ready — Store")])
def test_the_shipped_email(monkeypatch, shipped, subject):
    sent = _capture(monkeypatch)
    asyncio.run(mail.send_cappe_order_shipped_email(
        "b@example.com", "B", "Store", "2× Beans", "USPS", "9400" if shipped else None, "https://x/order/t", shipped,
    ))
    assert sent[0]["subject"] == subject
    assert ("Tracking: USPS 9400" in sent[0]["text"]) is shipped


def test_the_declined_email_says_nothing_was_charged(monkeypatch):
    sent = _capture(monkeypatch)
    asyncio.run(mail.send_cappe_order_declined_email("b@example.com", "B", "Store", "2× Beans", "Out of season"))
    assert "You have not been charged" in sent[0]["text"] and "Reason: Out of season" in sent[0]["text"]


def test_the_receipt_email_links_to_the_order_page(monkeypatch):
    from app.cappe.services import receipt as receipt_mod
    sent = []

    class _Svc:
        async def send_email_with_fallback(self, **kw):
            sent.append(kw)
            return True

    monkeypatch.setattr(receipt_mod, "get_email_service", lambda: _Svc())
    asyncio.run(receipt_mod.email_receipt({
        "customer_email": "b@example.com", "receipt_number": "ST-1", "business_name": "Store",
        "total_cents": 1000, "currency": "USD", "access_token": TOKEN, "subdomain": "shop", "custom_domain": "shop.example.com",
    }, b"%PDF"))
    assert f"https://shop.example.com/order/{TOKEN}" in sent[0]["html_content"]


# ── the quote tells the bag whether to ask for an address ────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("cards", [True, False])
async def test_the_quote_says_whether_checkout_takes_cards(monkeypatch, cards):
    from app.cappe.models.shopper import CartQuoteRequest
    conn = SqlConn([
        ("FROM cappe_sites WHERE id", {"tax_rate_bps": 0, "shipping_flat_cents": 0, "shipping_free_threshold_cents": None}),
        ("stripe_charges_enabled", cards),
        ("SELECT NOW()", NOW),
    ])
    monkeypatch.setattr(public_shop, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_shop, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_shop, "_published_site", AsyncMock(return_value={"id": SITE, "timezone": "UTC"}))
    monkeypatch.setattr(public_shop, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(public_shop, "fetch_active_discounts", AsyncMock(return_value=[]))
    out = await public_shop.quote("shop", CartQuoteRequest(items=[{"product_id": str(uuid4()), "quantity": 1}]), request=None)
    assert out["pays_by_card"] is cards


# ── the storefront scripts ───────────────────────────────────────────────────

def _js(name):
    return (ASSETS / name).read_text()


def test_the_bag_prices_on_the_server_and_checks_out_as_one_order():
    js = _js("cart.js")
    assert "RT.post('/quote'" in js and "RT.post('/orders'" in js
    assert "quote.pays_by_card===false" in js            # address only when Stripe won't ask
    assert "localStorage.setItem(OKEY,res.order_token)" in js
    assert "window.location='/order/'+encodeURIComponent(res.order_token)" in js
    assert "l.available===false" in js                    # an unavailable line blocks checkout


def test_the_product_panel_adds_to_the_bag_but_books_directly():
    js = _js("store.js")
    assert "window.__CAPPE_CART__" in js and "if(!booking&&cart)" in js
    assert "(booking?'<input class=\"cz-field\" type=\"email\"" in js


def test_the_order_page_empties_only_the_bag_it_was_ordered_from():
    js = _js("order.js")
    assert "localStorage.getItem(k)===token" in js
    assert "'/api/cappe/public/orders/'+encodeURIComponent(token)" in js and "base+'/pay'" in js


def test_the_bag_script_is_on_live_pages_only():
    from app.cappe.services.render import render_site_html
    site = {"name": "Store", "slug": "shop", "theme_config": {}, "meta_config": {}}
    page = {"title": "Home", "slug": "home", "content": {"blocks": []}}
    assert "__CAPPE_CART__" in render_site_html(site, page, [])
    assert "__CAPPE_CART__" not in render_site_html(site, page, [], preview=True)
    assert "__CAPPE_CART__" not in render_site_html(site, page, [], editable=True)
