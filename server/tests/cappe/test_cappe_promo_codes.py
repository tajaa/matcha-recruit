"""Promo codes — the 2026-10 commerce readiness review, PR 7.

What each block pins:

  * when a code can be used, and what it takes off (percent half-up, a fixed
    amount never more than the goods), with the reason shown when it can't;
  * the discount is split over the lines with no automatic discount, to the
    cent, before tax and shipping;
  * an order counts the use under the code's lock, refuses a code that can't
    be used, and the Stripe page shows discounted lines (never a negative one);
  * a released order gives its use back; subscriptions don't take codes;
  * the owner's endpoints, the receipt, the order page and the bag.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_promo_codes.py -q
"""
import asyncio
import inspect
import json
import os
import pathlib
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.cappe.models.shop import CappeCartItem, CappeCheckoutRequest, CappePromoCodeInput  # noqa: E402
from app.cappe.models.shopper import CartQuoteRequest  # noqa: E402
from app.cappe.routes import promo_codes as promo_routes  # noqa: E402
from app.cappe.routes.public import shop as public_shop  # noqa: E402
from app.cappe.services import cart, commerce, inventory, promos, recurring, receipt  # noqa: E402
from app.cappe.services.render import order_page  # noqa: E402

SITE, ORDER = uuid4(), uuid4()
TOKEN = "ef" * 16
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 6)
ASSETS = pathlib.Path(commerce.__file__).parent / "render" / "assets"
MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "zzzzcappe45_promo_codes.py"
CODES_ON = SimpleNamespace(platform_fee_bps=200, has=lambda f: f == "promo_codes")
CODES_OFF = SimpleNamespace(platform_fee_bps=200, has=lambda _f: False)


def code(**over):
    return {"id": uuid4(), "code": "SAVE10", "kind": "percent", "percent_off": 10, "amount_off_cents": None,
            "min_subtotal_cents": None, "starts_on": None, "ends_on": None, "max_redemptions": None,
            "once_per_customer": False, "active": True, "redemption_count": 0, **over}


# ── when a code can be used ──────────────────────────────────────────────────

@pytest.mark.parametrize("row,eligible,fragment", [
    (None, 1000, "isn't valid"),
    (code(active=False), 1000, "isn't valid"),
    (code(starts_on=date(2026, 10, 7)), 1000, "isn't active yet"),
    (code(ends_on=date(2026, 10, 5)), 1000, "has expired"),
    (code(max_redemptions=5, redemption_count=5), 1000, "used up"),
    (code(), 0, "already on sale"),
    (code(min_subtotal_cents=5000), 4999, "Spend $50.00 or more"),
])
def test_a_code_that_cant_be_used_says_why(row, eligible, fragment):
    discount, reason = promos.evaluate(row, eligible_cents=eligible, on_date=TODAY)
    assert discount == 0 and fragment in reason


def test_a_percent_code_rounds_half_up_and_a_fixed_one_never_exceeds_the_goods():
    assert promos.evaluate(code(percent_off=10), eligible_cents=1005, on_date=TODAY) == (101, None)
    assert promos.evaluate(code(kind="fixed", percent_off=None, amount_off_cents=1500),
                           eligible_cents=1000, on_date=TODAY) == (1000, None)
    # Its last day still counts; the cap counts uses below it.
    assert promos.evaluate(code(ends_on=TODAY, max_redemptions=5, redemption_count=4),
                           eligible_cents=1000, on_date=TODAY)[0] == 100


def test_codes_are_case_blind():
    assert promos.normalize_code("  save10 ") == "SAVE10"
    assert promos.normalize_code("") is None and promos.normalize_code(None) is None


@pytest.mark.parametrize("discount,totals,eligible,expected", [
    (100, [300, 300, 300], [True, True, True], [34, 33, 33]),      # leftover cent to the first
    (100, [500, 1000, 500], [True, False, True], [50, 0, 50]),       # an on-sale line takes none
    (999, [200, 300], [True, True], [200, 300]),                    # never more than the goods
    (0, [200], [True], [0]),
    (50, [0, 100], [True, True], [0, 50]),                           # a free line takes none
])
def test_the_discount_is_split_to_the_cent(discount, totals, eligible, expected):
    shares = promos.allocate(discount, totals, eligible)
    assert shares == expected
    assert sum(shares) == min(discount, sum(t for t, ok in zip(totals, eligible) if ok))


# ── the bag's quote ──────────────────────────────────────────────────────────

SITE_CFG = {"home_country": "US", "tax_rate_bps": 1000, "shipping_flat_cents": 600,
            "shipping_free_threshold_cents": 5000, "currency": "USD"}


def _products(sale=0):
    a, b = uuid4(), uuid4()
    return a, b, {
        a: {"id": a, "name": "Mug", "price_cents": 3000, "currency": "USD", "status": "active",
            "fulfillment": "physical", "inventory": None, "option_groups": [], "discount_percent": 0},
        b: {"id": b, "name": "Zine", "price_cents": 2000, "currency": "USD", "status": "active",
            "fulfillment": "digital", "inventory": None, "option_groups": [], "discount_percent": sale},
    }


def test_a_code_comes_off_before_tax_and_skips_items_on_sale():
    a, b, products = _products(sale=20)
    items = [CappeCartItem(product_id=a, quantity=2), CappeCartItem(product_id=b, quantity=1)]
    out = cart.price_cart(products, items, SITE_CFG, promo={"code": "SAVE10", "row": code(), "reason": None},
                          on_date=TODAY)
    # 10% of the mugs only (the zine is already 20% off): 6000 → 600 off.
    assert out["promo"] == {"code": "SAVE10", "valid": True, "discount_cents": 600, "message": None}
    assert [line.get("promo_discount_cents", 0) for line in out["lines"]] == [600, 0]
    assert out["subtotal_cents"] == 6000 + 1600 - 600
    assert out["tax_cents"] == 540                    # 10% of the discounted mugs
    assert out["shipping_cents"] == 0                 # 5400 of goods still clears the 50.00 threshold


def test_a_code_that_brings_the_goods_under_the_threshold_brings_shipping_back():
    a, _b, products = _products()
    items = [CappeCartItem(product_id=a, quantity=2)]
    promo = {"code": "BIG", "row": code(percent_off=20), "reason": None}
    out = cart.price_cart(products, items, SITE_CFG, promo=promo, on_date=TODAY)
    assert out["subtotal_cents"] == 4800 and out["shipping_cents"] == 600


def test_a_code_that_cant_be_used_leaves_the_prices_alone():
    a, _b, products = _products()
    items = [CappeCartItem(product_id=a, quantity=1)]
    out = cart.price_cart(products, items, SITE_CFG,
                          promo={"code": "NOPE", "row": None, "reason": None}, on_date=TODAY)
    assert out["promo"]["valid"] is False and out["promo"]["message"] == "That code isn't valid."
    assert out["subtotal_cents"] == 3000
    no_plan = cart.price_cart(products, items, SITE_CFG, on_date=TODAY,
                              promo={"code": "X1Y", "row": code(), "reason": "This store doesn't take promo codes."})
    assert no_plan["promo"]["message"] == "This store doesn't take promo codes."


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
        return Ctx(self)

    def sql(self, needle):
        return [c for c in self.calls if needle in c[1]]


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


def _wire_quote(monkeypatch, ent=CODES_ON, row=None):
    pid = uuid4()
    product = {"id": pid, "site_id": SITE, "name": "Zine", "price_cents": 2000, "currency": "USD",
               "inventory": None, "status": "active", "fulfillment": "digital",
               "subscription_intervals": ["month"], "subscription_discount_bps": 0, "requires_approval": False}
    conn = SqlConn([
        ("FROM cappe_sites WHERE id=$1", dict(SITE_CFG)),
        ("stripe_charges_enabled", True),
        ("SELECT a.plan", "business"),
        ("FROM cappe_products", [product]),
        ("SELECT NOW()", NOW),
        ("FROM cappe_promo_codes", row),
    ])
    monkeypatch.setattr(public_shop, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_shop, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_shop, "_published_site", AsyncMock(return_value={"id": SITE, "timezone": "UTC"}))
    monkeypatch.setattr(public_shop, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(public_shop, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(public_shop, "resolve_entitlements", AsyncMock(return_value=ent))
    return conn, pid


def test_the_quote_applies_a_code_and_says_the_store_takes_them(monkeypatch):
    _conn, pid = _wire_quote(monkeypatch, row=code())
    out = asyncio.run(public_shop.quote(
        "shop", CartQuoteRequest(items=[{"product_id": str(pid), "quantity": 1}], promo_code="save10"), request=None))
    assert out["promo_codes"] is True and out["promo"]["discount_cents"] == 200
    assert out["subtotal_cents"] == 1800 and out["total_cents"] == 1800


def test_a_store_without_codes_hides_the_box_and_refuses_one(monkeypatch):
    conn, pid = _wire_quote(monkeypatch, ent=CODES_OFF, row=code())
    out = asyncio.run(public_shop.quote(
        "shop", CartQuoteRequest(items=[{"product_id": str(pid), "quantity": 1}], promo_code="SAVE10"), request=None))
    assert out["promo_codes"] is False and out["promo"]["valid"] is False
    assert not conn.sql("FROM cappe_promo_codes")                 # never even looked up


def test_a_subscription_quote_takes_no_code(monkeypatch):
    _conn, pid = _wire_quote(monkeypatch, row=code())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(public_shop.quote("shop", CartQuoteRequest(
            items=[{"product_id": str(pid), "quantity": 1}], interval="month", promo_code="SAVE10"), request=None))
    assert exc.value.status_code == 422 and "subscriptions" in exc.value.detail


def test_a_subscription_checkout_takes_no_code():
    from app.cappe.models.shopper import SubscriptionCheckout
    body = SubscriptionCheckout(items=[{"product_id": str(uuid4()), "quantity": 1}], interval="month",
                                success_url="https://s.example.com/", cancel_url="https://s.example.com/",
                                promo_code="SAVE10")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(recurring.checkout({"id": SITE}, {"id": uuid4()}, body))
    assert exc.value.status_code == 422


# ── an order counts the use ──────────────────────────────────────────────────

class OrderConn:
    def __init__(self, product, promo=None, used=False):
        self.product, self.promo, self.used = product, promo, used
        self.order, self.items, self.executed = None, [], []

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
        if "FROM cappe_promo_codes" in sql:
            assert "FOR UPDATE" in sql                       # counted under the code's lock
            return self.promo
        if "FROM cappe_sites" in sql:
            return {**SITE_CFG, "tax_rate_bps": 0, "tax_label": None, "shipping_label": None}
        if "INSERT INTO cappe_orders" in sql:
            self.order = {"id": ORDER, "status": "paid" if args[14] else "pending", "access_token": TOKEN,
                          "subtotal_cents": args[3],
                          "tax_cents": args[4], "shipping_cents": args[5], "total_cents": args[6],
                          "currency": args[7], "requires_approval": args[9], "ship_country": args[11],
                          "promo_code": args[12], "discount_cents": args[13]}
            return self.order
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        if sql == "SELECT NOW()":
            return NOW
        if "FROM cappe_promo_redemptions" in sql:
            return 1 if self.used else None
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "INSERT INTO cappe_order_items" in sql:
            self.items.append(args)


def _wire_order(monkeypatch, *, promo=code(), ent=CODES_ON, used=False, sale=0, quantity=2, promo_code="save10"):
    product = {"id": uuid4(), "name": "Mug", "price_cents": 1000, "currency": "USD", "inventory": None,
               "low_stock_threshold": None, "status": "active", "fulfillment": "digital",
               "booking_type_id": None, "requires_approval": False, "intake_fields": "[]"}
    conn = OrderConn(product, promo=promo, used=used)
    owner = {"plan": "business", "status": "active", "email": "owner@example.com", "name": "Owner",
             "stripe_account_id": "acct_1", "stripe_charges_enabled": True}
    stripe = SimpleNamespace(create_checkout_session=AsyncMock(return_value={"id": "cs_1", "url": "https://pay"}))
    discounts = [{"percent_off": sale, "scope": "all", "target_id": None, "active": True,
                  "starts_on": None, "ends_on": None, "location_id": None}] if sale else []
    monkeypatch.setattr(commerce, "get_connection", lambda: conn)
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=discounts))
    monkeypatch.setattr(commerce, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(commerce, "lock_stock_rows", AsyncMock())
    monkeypatch.setattr(commerce, "fetch_site_owner", AsyncMock(return_value=owner))
    monkeypatch.setattr(commerce, "resolve_entitlements", AsyncMock(return_value=ent))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    monkeypatch.setattr(commerce, "check_recipient_send_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(commerce, "get_cappe_stripe", lambda: stripe)
    site = {"id": SITE, "name": "Store", "timezone": "UTC", "subdomain": "shop", "custom_domain": "shop.example.com"}
    body = CappeCheckoutRequest(
        customer_email="buyer@example.com", items=[CappeCartItem(product_id=product["id"], quantity=quantity)],
        success_url="https://shop.example.com/", cancel_url="https://shop.example.com/", promo_code=promo_code,
    )
    return site, body, conn, stripe


def test_an_order_with_a_code_records_it_counts_it_and_charges_the_discounted_lines(monkeypatch):
    promo = code(percent_off=15)
    site, body, conn, stripe = _wire_order(monkeypatch, promo=promo, quantity=3)
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    # 15% of 3000 = 450 off; the order's subtotal is what the goods now cost.
    assert (conn.order["promo_code"], conn.order["discount_cents"], conn.order["subtotal_cents"]) == ("SAVE10", 450, 2550)
    assert conn.items[0][-1] == 450                           # the line's share
    redemption = [a for sql, a in conn.executed if "INSERT INTO cappe_promo_redemptions" in sql]
    assert redemption == [(promo["id"], SITE, ORDER, "buyer@example.com", 450)]
    assert any("redemption_count = redemption_count + 1" in sql for sql, _a in conn.executed)
    # Stripe sees the discounted line as one item, never a negative line.
    items = stripe.create_checkout_session.await_args.kwargs["line_items"]
    assert [(li["price_data"]["unit_amount"], li["quantity"], li["price_data"]["product_data"]["name"])
            for li in items] == [(2550, 1, "Mug × 3")]
    # The fee is on what the buyer pays for the goods.
    assert stripe.create_checkout_session.await_args.kwargs["application_fee_cents"] == 51


@pytest.mark.parametrize("over,fragment", [
    ({"promo": None}, "isn't valid"),
    ({"promo": code(max_redemptions=1, redemption_count=1)}, "used up"),
    ({"used": True, "promo": code(once_per_customer=True)}, "already used"),
    ({"ent": CODES_OFF}, "doesn't take promo codes"),
    ({"sale": 20}, "already on sale"),
])
def test_an_order_with_a_code_that_cant_be_used_is_refused_whole(monkeypatch, over, fragment):
    site, body, conn, stripe = _wire_order(monkeypatch, **over)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert exc.value.status_code == 422 and fragment in exc.value.detail
    assert conn.order is None and stripe.create_checkout_session.await_count == 0


def test_an_order_without_a_code_is_untouched(monkeypatch):
    site, body, conn, _stripe = _wire_order(monkeypatch, promo_code=None)
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert (conn.order["promo_code"], conn.order["discount_cents"], conn.order["subtotal_cents"]) == (None, 0, 2000)
    assert not any("cappe_promo" in sql for sql, _a in conn.executed)


def test_undiscounted_lines_still_go_to_stripe_at_their_unit_price():
    items = commerce.build_stripe_line_items(
        [(1, "Mug", 1000, 2), (2, "Zine", 500, 1)], "usd", 0, "Tax", [0, 100])
    assert [(li["price_data"]["unit_amount"], li["quantity"]) for li in items] == [(1000, 2), (400, 1)]


def test_pay_now_charges_the_same_discounted_lines():
    src = inspect.getsource(commerce.pay_for_order)
    assert "promo_discount_cents" in src and "line_discounts=" in src


# ── the owner's codes ────────────────────────────────────────────────────────

def test_a_code_is_upper_cased_and_shaped():
    c = CappePromoCodeInput(code=" summer-10 ", kind="percent", percent_off=10, amount_off_cents=500)
    assert c.code == "SUMMER-10" and c.amount_off_cents is None
    f = CappePromoCodeInput(code="FIVE", kind="fixed", amount_off_cents=500, percent_off=10)
    assert f.percent_off is None
    for bad in ({"code": "a b"}, {"code": "x!"}, {"code": "OK1", "kind": "fixed"},
                {"code": "OK1", "percent_off": 95}, {"code": "OK1", "percent_off": 10,
                                                      "starts_on": date(2026, 10, 9), "ends_on": date(2026, 10, 1)}):
        with pytest.raises(ValidationError):
            CappePromoCodeInput(**bad)


def _wire_codes(monkeypatch, conn, ent=CODES_ON):
    account = SimpleNamespace(id=uuid4(), plan="business")
    monkeypatch.setattr(promo_routes, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(promo_routes, "get_owned_site", AsyncMock(return_value={"id": SITE, "currency": "EUR"}))
    monkeypatch.setattr(promo_routes, "resolve_entitlements", AsyncMock(return_value=ent))
    return account


def test_listing_codes_says_whether_the_plan_has_them(monkeypatch):
    account = _wire_codes(monkeypatch, SqlConn([("FROM cappe_promo_codes", [code()])]), ent=CODES_OFF)
    out = asyncio.run(promo_routes.list_promo_codes(SITE, account))
    assert out["enabled"] is False and out["currency"] == "EUR" and out["codes"][0]["code"] == "SAVE10"


def test_creating_a_code_needs_the_plan(monkeypatch):
    conn = SqlConn([])
    account = _wire_codes(monkeypatch, conn, ent=CODES_OFF)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(promo_routes.create_promo_code(SITE, CappePromoCodeInput(code="SAVE10", percent_off=10), account))
    assert exc.value.status_code == 402 and not conn.sql("INSERT")


def test_creating_a_code_writes_every_field(monkeypatch):
    conn = SqlConn([("SELECT COUNT(*)", 0), ("INSERT INTO cappe_promo_codes", code())])
    account = _wire_codes(monkeypatch, conn)
    body = CappePromoCodeInput(code="save10", percent_off=10, max_redemptions=100, once_per_customer=True)
    asyncio.run(promo_routes.create_promo_code(SITE, body, account))
    ((_k, sql, args),) = conn.sql("INSERT INTO cappe_promo_codes")
    assert args[:3] == (SITE, "SAVE10", "percent") and args[8] == 100 and args[9] is True


def test_a_duplicate_code_or_too_many_codes_is_a_409(monkeypatch):
    def dup(_sql, _args):
        raise asyncpg.UniqueViolationError("uq_cappe_promo_codes_code")

    account = _wire_codes(monkeypatch, SqlConn([("SELECT COUNT(*)", 0), ("INSERT INTO cappe_promo_codes", dup)]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(promo_routes.create_promo_code(SITE, CappePromoCodeInput(code="SAVE10", percent_off=10), account))
    assert exc.value.status_code == 409 and "already have a code called SAVE10" in exc.value.detail
    account = _wire_codes(monkeypatch, SqlConn([("SELECT COUNT(*)", promo_routes.MAX_CODES)]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(promo_routes.create_promo_code(SITE, CappePromoCodeInput(code="SAVE11", percent_off=10), account))
    assert exc.value.status_code == 409


def test_editing_keeps_the_use_count_and_404s_a_stranger(monkeypatch):
    conn = SqlConn([("UPDATE cappe_promo_codes", code(redemption_count=7))])
    account = _wire_codes(monkeypatch, conn)
    out = asyncio.run(promo_routes.update_promo_code(SITE, uuid4(), CappePromoCodeInput(code="SAVE10", percent_off=20), account))
    assert out["redemption_count"] == 7
    set_clause = conn.sql("UPDATE cappe_promo_codes")[0][1].split("SET", 1)[1].split("WHERE")[0]
    assert "redemption_count" not in set_clause
    account = _wire_codes(monkeypatch, SqlConn([]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(promo_routes.update_promo_code(SITE, uuid4(), CappePromoCodeInput(code="SAVE10", percent_off=20), account))
    assert exc.value.status_code == 404


def test_deleting_a_code(monkeypatch):
    account = _wire_codes(monkeypatch, SqlConn([("DELETE FROM cappe_promo_codes", uuid4())]), ent=CODES_OFF)
    asyncio.run(promo_routes.delete_promo_code(SITE, uuid4(), account))      # allowed on any plan
    account = _wire_codes(monkeypatch, SqlConn([]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(promo_routes.delete_promo_code(SITE, uuid4(), account))
    assert exc.value.status_code == 404


# ── what the buyer sees ──────────────────────────────────────────────────────

def test_the_order_page_shows_the_discount_on_its_own_line():
    html = order_page._totals_html({"subtotal_cents": 2550, "discount_cents": 450, "promo_code": "SAVE10",
                                    "total_cents": 2550, "currency": "USD"})
    assert "<dt>Subtotal</dt><dd>$30.00</dd>" in html
    assert "<dt>Discount (SAVE10)</dt><dd>−$4.50</dd>" in html
    assert "<dt>Total</dt><dd>$25.50</dd>" in html


def test_the_receipt_shows_the_discount_on_its_own_line():
    html = receipt.build_receipt_html({"subtotal_cents": 2550, "discount_cents": 450, "promo_code": "SAVE10",
                                       "total_cents": 2550, "currency": "USD"}, [])
    assert "Discount (SAVE10)" in html and "−$4.50" in html and "$30.00" in html


def test_the_bag_offers_a_code_box_and_sends_only_an_accepted_code():
    js = (ASSETS / "cart.js").read_text()
    assert "data-promo" in js and "req.promo_code=promoCode" in js
    assert "if(quote&&quote.promo&&quote.promo.valid)body.promo_code=quote.promo.code" in js
    assert "promoWrap.hidden=!(quote&&quote.promo_codes)" in js
    assert "cz-cart-promo:" in (ASSETS / "order.js").read_text()     # cleared with the bag


def test_the_migration_chains_and_gates_the_feature():
    src = MIGRATION.read_text()
    assert 'down_revision = "zzzzcappe44"' in src and 'revision = "zzzzcappe45"' in src
    assert "uq_cappe_promo_codes_code ON cappe_promo_codes (site_id, code)" in src
    assert "uq_cappe_promo_redemptions_order" in src
    assert "jsonb_build_object('promo_codes', true)" in src
    assert "promo_discount_cents INTEGER NOT NULL DEFAULT 0" in src


def test_shares_are_stored_with_each_line():
    src = inspect.getsource(commerce.create_public_order)
    assert "stock_decremented, decremented_option_ids, promo_discount_cents)" in src
    assert json.dumps(0) == "0"


# ── a code that takes it all off ─────────────────────────────────────────────

def test_an_order_a_code_makes_free_is_settled_at_once(monkeypatch):
    """Nothing to pay and nothing to approve: left pending, nothing would ever
    settle it (Pay now refuses a zero total) and its download stays locked."""
    site, body, conn, stripe = _wire_order(monkeypatch, promo=code(kind="fixed", percent_off=None, amount_off_cents=2000))
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert conn.order["total_cents"] == 0 and conn.order["status"] == "paid"
    assert stripe.create_checkout_session.await_count == 0


def test_an_order_with_something_to_pay_still_starts_pending(monkeypatch):
    site, body, conn, _stripe = _wire_order(monkeypatch)
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert conn.order["total_cents"] > 0 and conn.order["status"] == "pending"


# ── a released order that gets paid after all ────────────────────────────────

class _UseConn:
    def __init__(self, held_by):
        self.held_by, self.calls = held_by, []

    async def fetch(self, sql, *args):
        return []

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return self.held_by if "FROM cappe_promo_redemptions" in sql else None

    async def execute(self, sql, *args):
        self.calls.append((sql, args))


def test_paying_for_a_released_order_counts_its_code_again():
    """The release gave the use back; the late payment means the buyer got the
    discount after all, so it counts again (even past the cap — it's owed)."""
    code_id = uuid4()
    conn = _UseConn(code_id)
    asyncio.run(inventory.retake_order_stock(conn, site_id=uuid4(), order_id=ORDER))
    (find, find_args), (lock, lock_args), (move, move_args) = conn.calls
    assert find_args == (ORDER, "released")
    assert "cappe_promo_codes WHERE id = $1 FOR UPDATE" in lock and lock_args == (code_id,)
    assert move_args == (ORDER, "released", "active", 1)


def test_an_order_without_a_code_touches_no_code():
    conn = _UseConn(None)
    asyncio.run(inventory.retake_order_stock(conn, site_id=uuid4(), order_id=ORDER))
    assert len(conn.calls) == 1


def test_a_saved_code_the_server_refuses_is_dropped_not_kept():
    js = (pathlib.Path(commerce.__file__).parent / "render" / "assets" / "cart.js").read_text()
    assert ".toUpperCase().slice(0,40)" in js
    assert "if(promoCode){setPromo(null);" in js


def test_dev_refreshes_scrub_redemption_emails():
    root = pathlib.Path(__file__).resolve().parents[3]
    assert "UPDATE cappe_promo_redemptions r SET customer_email = o.customer_email" in (
        root / "scripts" / "sql" / "anonymize_dev.sql").read_text()
    assert "FROM cappe_promo_redemptions WHERE customer_email IS NOT NULL" in (
        root / "scripts" / "refresh-dev-from-prod.sh").read_text()
