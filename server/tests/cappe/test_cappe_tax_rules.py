"""Tax rules — physical sellers PR 4/7 (`zzzzcappe53`, services/cart.py).

What each block pins:

  * the arithmetic: tax on top (as before) or inside the price (the part
    that is tax), on shipping when the store says so, at a zone's own rate;
    a zone that doesn't charge tax charges none either way;
  * the goods net of tax, which is what the platform fee is taken on;
  * an order and a subscription keep how they were priced, and Stripe is
    charged exactly the total: no tax line when the prices include it;
  * the bag, the receipt, the order page and the owner's view say
    "Includes VAT" under the total instead of adding it;
  * finances keep goods + tax + shipping = total for every order;
  * the settings, the zone rate, and the migration.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_tax_rules.py -q
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
from fastapi import BackgroundTasks  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.cappe.models.shop import (  # noqa: E402
    CappeCartItem,
    CappeCheckoutRequest,
    CappeShippingZoneInput,
    CappeShippingZonesReplace,
)
from app.cappe.models.sites import CappeSiteUpdate  # noqa: E402
from app.cappe.routes import financials, sites as site_routes  # noqa: E402
from app.cappe.routes import shipping as zones_routes  # noqa: E402
from app.cappe.routes import shop as shop_routes  # noqa: E402
from app.cappe.services import commerce, recurring, shipping  # noqa: E402
from app.cappe.services.cart import cart_totals, goods_net_cents, tax_in  # noqa: E402
from app.cappe.services.entitlements import ALL_FULFILLMENT  # noqa: E402
from app.cappe.services.receipt import build_receipt_html  # noqa: E402
from app.cappe.services.render.order_page import _totals_html  # noqa: E402
from app.cappe.services.shipping import Destination  # noqa: E402

SITE, ORDER = uuid4(), uuid4()
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
ASSETS = pathlib.Path(commerce.__file__).parent / "render" / "assets"
MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "zzzzcappe53_tax_rules.py"

GOODS = [{"unit_price_cents": 12000, "quantity": 1, "fulfillment": "physical"}]
UK = {"home_country": "GB", "tax_rate_bps": 2000, "tax_label": "VAT", "shipping_flat_cents": 600}
MONEY = ("subtotal_cents", "tax_cents", "shipping_cents", "total_cents", "shipping_tax_cents", "tax_included")


def _money(out):
    return tuple(out[k] for k in MONEY)


# ── the arithmetic ───────────────────────────────────────────────────────────

def test_tax_on_top_or_inside_the_price():
    assert tax_in(10000, 2000, False) == 2000          # 20% on £100
    assert tax_in(12000, 2000, True) == 2000           # the VAT inside £120
    assert tax_in(999, 875, False) == 87               # rounds down, as the exclusive rate always has
    assert tax_in(999, 875, True) == 80
    assert tax_in(0, 2000, True) == 0 and tax_in(5000, 0, False) == 0


def test_exclusive_tax_is_added_as_before():
    assert _money(cart_totals(GOODS, UK)) == (12000, 2400, 600, 15000, 0, False)


def test_tax_on_shipping_is_added_at_the_same_rate():
    out = cart_totals(GOODS, {**UK, "tax_on_shipping": True})
    assert _money(out) == (12000, 2520, 600, 15120, 120, False)


def test_included_tax_is_inside_the_price_and_not_added():
    out = cart_totals(GOODS, {**UK, "prices_include_tax": True})
    assert _money(out) == (12000, 2000, 600, 12600, 0, True)
    both = cart_totals(GOODS, {**UK, "prices_include_tax": True, "tax_on_shipping": True})
    assert _money(both) == (12000, 2100, 600, 12600, 100, True)


def test_a_zone_charges_its_own_rate_or_the_stores():
    own = Destination("FR", 900, None, True, zone_id="z", tax_rate_bps=2000)
    inherited = Destination("FR", 900, None, True, zone_id="z")
    us = {**UK, "tax_rate_bps": 875}
    assert cart_totals(GOODS, us, own)["tax_cents"] == 2400
    assert cart_totals(GOODS, us, inherited)["tax_cents"] == 1050


def test_a_zone_that_charges_no_tax_charges_none_even_on_included_prices():
    abroad = Destination("US", 1500, None, False, zone_id="z", tax_rate_bps=2000)
    out = cart_totals(GOODS, {**UK, "prices_include_tax": True, "tax_on_shipping": True}, abroad)
    assert _money(out) == (12000, 0, 1500, 13500, 0, True)


def test_only_physical_goods_are_taxed():
    lines = GOODS + [{"unit_price_cents": 5000, "quantity": 1, "fulfillment": "digital"}]
    out = cart_totals(lines, {**UK, "prices_include_tax": True})
    assert out["tax_cents"] == 2000 and out["total_cents"] == 17000 + 600


def test_a_promo_code_comes_off_before_tax():
    lines = [{**GOODS[0], "promo_discount_cents": 2400}]
    out = cart_totals(lines, {**UK, "prices_include_tax": True})
    assert out["subtotal_cents"] == 9600 and out["tax_cents"] == 1600


def test_the_fee_is_on_the_goods_net_of_tax():
    exclusive = cart_totals(GOODS, {**UK, "tax_on_shipping": True})
    assert goods_net_cents(exclusive) == 12000
    included = cart_totals(GOODS, {**UK, "prices_include_tax": True, "tax_on_shipping": True})
    assert goods_net_cents(included) == 10000  # £120 less the £20 VAT in the goods; shipping's VAT isn't goods
    assert goods_net_cents({"subtotal_cents": 500}) == 500  # an order from before zzzzcappe53


# ── an order is charged what it says ─────────────────────────────────────────

class OrderConn:
    def __init__(self, site_cfg):
        self.site_cfg, self.order, self.args = site_cfg, None, None

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
            return self.site_cfg
        if "INSERT INTO cappe_orders" in sql:
            self.args = args
            self.order = {"id": ORDER, "status": "pending", "access_token": "ab" * 16, "subtotal_cents": args[3],
                          "tax_cents": args[4], "shipping_cents": args[5], "total_cents": args[6],
                          "currency": args[7], "requires_approval": args[9], "shipping_address": None,
                          "ship_country": args[11], "shipping_method": args[16], "shipping_rate_label": args[17],
                          "tax_included": args[21], "shipping_tax_cents": args[22]}
            return self.order
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        if sql == "SELECT NOW()":
            return NOW
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        pass


def _place(monkeypatch, site_cfg):
    conn = OrderConn({"tax_label": "VAT", "shipping_label": "Delivery", **site_cfg})
    conn.product = {"id": uuid4(), "name": "Teapot", "price_cents": 12000, "currency": "GBP", "inventory": None,
                    "low_stock_threshold": None, "status": "active", "fulfillment": "physical",
                    "booking_type_id": None, "requires_approval": False, "intake_fields": "[]", "sku": None,
                    "weight_g": None, "ships_free": False, "shipping_surcharge_cents": 0}
    owner = {"plan": "business", "status": "active", "email": "owner@example.com", "name": "Owner",
             "stripe_account_id": "acct_1", "stripe_charges_enabled": True}
    stripe = SimpleNamespace(create_checkout_session=AsyncMock(return_value={"id": "cs_1", "url": "https://pay"}))
    ent = SimpleNamespace(platform_fee_bps=500, allowed_fulfillment=ALL_FULFILLMENT, has=lambda f: True)
    monkeypatch.setattr(commerce, "get_connection", lambda: conn)
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(commerce, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(commerce, "fetch_variants", AsyncMock(return_value={}))
    monkeypatch.setattr(commerce, "lock_stock_rows", AsyncMock())
    monkeypatch.setattr(commerce, "fetch_site_owner", AsyncMock(return_value=owner))
    monkeypatch.setattr(commerce, "resolve_entitlements", AsyncMock(return_value=ent))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    monkeypatch.setattr(commerce, "check_recipient_send_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(commerce, "get_cappe_stripe", lambda: stripe)
    site = {"id": SITE, "name": "Store", "timezone": "UTC", "subdomain": "shop", "custom_domain": "shop.example.com"}
    body = CappeCheckoutRequest(
        customer_email="buyer@example.com", items=[CappeCartItem(product_id=conn.product["id"], quantity=1)],
        success_url="https://shop.example.com/", cancel_url="https://shop.example.com/", ship_country="GB",
    )
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    return conn, stripe.create_checkout_session.await_args.kwargs


def _charged(kw):
    lines = sum(li["price_data"]["unit_amount"] * li["quantity"] for li in kw["line_items"])
    return lines + (kw["shipping_option"]["amount_cents"] if kw["shipping_option"] else 0)


@pytest.mark.parametrize("cfg,total,tax_line", [
    ({}, 15000, 2400),
    ({"tax_on_shipping": True}, 15120, 2520),
    ({"prices_include_tax": True}, 12600, None),
    ({"prices_include_tax": True, "tax_on_shipping": True}, 12600, None),
])
def test_stripe_is_charged_the_orders_total(monkeypatch, cfg, total, tax_line):
    conn, kw = _place(monkeypatch, {**UK, **cfg})
    assert conn.order["total_cents"] == total == _charged(kw)
    taxes = [li["price_data"]["unit_amount"] for li in kw["line_items"]
             if li["price_data"]["product_data"]["name"] == "VAT"]
    assert taxes == ([tax_line] if tax_line else [])


def test_an_included_order_keeps_how_it_was_priced_and_fees_the_net_goods(monkeypatch):
    conn, kw = _place(monkeypatch, {**UK, "prices_include_tax": True, "tax_on_shipping": True})
    assert conn.args[21:23] == (True, 100)
    # 5% of the £100 net of VAT, not of the £120 the buyer paid.
    assert kw["application_fee_cents"] == 500 and kw["metadata"]["platform_fee_cents"] == "500"


def test_pay_now_reads_how_the_order_was_priced():
    assert "o.tax_included, o.shipping_tax_cents" in inspect.getsource(commerce.pay_for_order)


# ── subscriptions ────────────────────────────────────────────────────────────

def _subscription(site):
    pid = uuid4()
    product = {"id": pid, "name": "Tea club", "price_cents": 12000, "currency": "GBP", "status": "active",
               "fulfillment": "physical", "inventory": None, "subscription_intervals": ["month"],
               "subscription_discount_bps": 0, "requires_approval": False, "option_groups": [], "variants": [],
               "discount_percent": 0}
    return recurring.build_subscription_lines({pid: product}, [CappeCartItem(product_id=pid, quantity=1)], "month", site)


def test_a_subscription_with_included_tax_bills_no_tax_line():
    lines, _snap, totals = _subscription({**UK, "prices_include_tax": True})
    names = [li["price_data"]["product_data"]["name"] for li in lines]
    assert names == ["Tea club", "Shipping"] and totals["tax_included"] is True
    assert sum(li["price_data"]["unit_amount"] * li["quantity"] for li in lines) == totals["total_cents"] == 12600
    lines, _snap, totals = _subscription(UK)
    assert [li["price_data"]["product_data"]["name"] for li in lines] == ["Tea club", "Tax", "Shipping"]
    assert sum(li["price_data"]["unit_amount"] * li["quantity"] for li in lines) == totals["total_cents"] == 15000


def test_a_subscription_fees_the_net_goods_and_its_renewals_keep_how_it_was_priced():
    src = inspect.getsource(recurring.checkout)
    assert "goods_net_cents(totals)" in src and 'totals["tax_included"], totals["shipping_tax_cents"]' in src
    renewal = inspect.getsource(recurring.record_invoice_order)
    assert "tax_included,shipping_tax_cents" in renewal
    assert 'bool(row.get("tax_included")), int(row.get("shipping_tax_cents") or 0)' in renewal


def test_a_renewal_order_is_written_as_its_subscription_was_priced():
    calls = []

    class Conn:
        async def fetchrow(self, sql, *args):
            calls.append((sql, args))
            return None  # a replayed invoice: nothing more to do

    row = {"site_id": SITE, "shopper_id": None, "id": uuid4(), "subtotal_cents": 12000, "tax_cents": 2000,
           "shipping_cents": 600, "total_cents": 12600, "currency": "GBP", "items": "[]",
           "tax_included": True, "shipping_tax_cents": 0}
    asyncio.run(recurring.record_invoice_order(Conn(), row, {"id": "in_1", "total": 12600}))
    sql, args = calls[0]
    assert "INSERT INTO cappe_orders" in sql and args[-2:] == (True, 0)


# ── what the buyer and the owner read ────────────────────────────────────────

_RECEIPT = {"currency": "GBP", "business_name": "Store", "receipt_number": "INV-1", "customer_name": "Buyer",
            "customer_email": "buyer@example.com", "subtotal_cents": 12000, "tax_cents": 2000, "shipping_cents": 600,
            "total_cents": 12600, "tax_label": "VAT", "created_at": NOW}


def test_the_receipt_says_includes_vat_under_the_total():
    html = build_receipt_html({**_RECEIPT, "tax_included": True}, [])
    assert "Includes VAT" in html and html.index("Includes VAT") > html.index(">Total<")
    assert ">VAT<" not in html
    exclusive = build_receipt_html({**_RECEIPT, "total_cents": 14600}, [])
    assert ">VAT<" in exclusive and "Includes VAT" not in exclusive


def test_the_receipt_total_fallback_doesnt_add_included_tax():
    from app.cappe.services.receipt import _fmt
    html = build_receipt_html({**_RECEIPT, "tax_included": True, "total_cents": None}, [])
    assert _fmt(12600, "GBP") in html and _fmt(14600, "GBP") not in html


def test_the_order_page_says_includes_vat_under_the_total():
    html = _totals_html({**_RECEIPT, "tax_included": True})
    assert "<dt>Includes VAT</dt>" in html and "<dt>VAT</dt>" not in html
    assert html.index("Includes VAT") > html.index("cz-order__total")
    assert "<dt>VAT</dt>" in _totals_html({**_RECEIPT, "total_cents": 14600})


def test_every_view_of_an_order_reads_how_it_was_priced():
    from app.cappe.routes import render
    from app.cappe.routes.public import shop as public_shop
    from app.cappe.routes.public import shopper
    from app.cappe.services import receipt
    assert "o.tax_included" in inspect.getsource(render)
    assert "o.tax_included" in inspect.getsource(receipt.render_order_receipt_pdf)
    assert "tax_included" in inspect.getsource(public_shop.public_order_receipt)
    assert "tax_included" in shopper.ORDER_COLS
    assert "tax_included, shipping_tax_cents" in shop_routes._ORDER_COLS


def test_the_bag_and_the_product_panel_show_included_tax_under_the_total():
    js = (ASSETS / "cart.js").read_text()
    assert "if(quote.tax_cents&&!quote.tax_included)rows.push([taxName,quote.tax_cents])" in js
    assert "rows.push(['Includes '+taxName,quote.tax_cents])" in js
    assert js.index("rows.push(['Total'") < js.index("rows.push(['Includes '")
    assert "(q.tax_included?'Includes ':'')" in (ASSETS / "store.js").read_text()


def test_the_quote_names_the_tax():
    from app.cappe.routes.public import shop as public_shop
    src = inspect.getsource(public_shop.quote)
    assert "tax_label,prices_include_tax,tax_on_shipping" in src and '"tax_label": tax_label' in src


# ── finances ─────────────────────────────────────────────────────────────────

def test_finances_report_goods_and_shipping_net_of_included_tax():
    assert financials._GOODS_NET == (
        "o.subtotal_cents - CASE WHEN o.tax_included THEN o.tax_cents - o.shipping_tax_cents ELSE 0 END")
    src = inspect.getsource(financials)
    assert "COALESCE(SUM({_GOODS_NET}), 0) AS goods" in src and "COALESCE(SUM({_SHIPPING_NET}), 0) AS shipping" in src
    assert "{_GOODS_NET} AS subtotal_cents" in src and "{_SHIPPING_NET} AS shipping_cents" in src
    # The same identity in Python: goods + tax + shipping = the total.
    order = cart_totals(GOODS, {**UK, "prices_include_tax": True, "tax_on_shipping": True})
    goods, ship = goods_net_cents(order), order["shipping_cents"] - order["shipping_tax_cents"]
    assert goods + order["tax_cents"] + ship == order["total_cents"]


# ── settings ─────────────────────────────────────────────────────────────────

def test_the_store_takes_its_tax_switches():
    body = CappeSiteUpdate(prices_include_tax=True, tax_on_shipping=False)
    assert (body.prices_include_tax, body.tax_on_shipping) == (True, False)
    assert "prices_include_tax, tax_on_shipping" in site_routes._SITE_COLS
    assert 'for key in ("prices_include_tax", "tax_on_shipping")' in inspect.getsource(site_routes)


def test_a_zone_takes_its_own_rate():
    assert CappeShippingZoneInput(name="EU", countries=["FR"], charge_tax=True, tax_rate_bps=2000).tax_rate_bps == 2000
    for bad in (-1, 10001):
        with pytest.raises(ValidationError):
            CappeShippingZoneInput(name="EU", countries=["FR"], tax_rate_bps=bad)
    zone = {"id": uuid4(), "name": "EU", "countries": ["FR"], "rest_of_world": False, "flat_cents": 900,
            "free_threshold_cents": None, "charge_tax": True, "tax_rate_bps": 2000}
    assert shipping.resolve_destination(UK, [zone], "FR").tax_rate_bps == 2000
    assert "tax_rate_bps" in shipping._ZONE_COLS


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class ZonesConn:
    def __init__(self):
        self.calls = []

    async def fetch(self, sql, *args):
        return []

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return uuid4()

    async def execute(self, sql, *args):
        self.calls.append((sql, args))

    def transaction(self):
        return _Tx()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def test_a_zone_saves_its_rate_only_while_it_charges_tax(monkeypatch):
    conn = ZonesConn()
    ent = SimpleNamespace(has=lambda f: True)
    monkeypatch.setattr(zones_routes, "get_connection", lambda: conn)
    monkeypatch.setattr(zones_routes, "get_owned_site", AsyncMock(return_value={"id": SITE, **UK}))
    monkeypatch.setattr(zones_routes, "resolve_entitlements", AsyncMock(return_value=ent))
    body = CappeShippingZonesReplace(zones=[
        {"name": "EU", "countries": ["FR"], "charge_tax": True, "tax_rate_bps": 2000},
        {"name": "US", "countries": ["US"], "charge_tax": False, "tax_rate_bps": 875},
    ])
    asyncio.run(zones_routes.replace_shipping_zones(SITE, body, SimpleNamespace(id=uuid4(), plan="business")))
    inserts = [args for sql, args in conn.calls if "INSERT INTO cappe_shipping_zones" in sql]
    assert [(a[1], a[8]) for a in inserts] == [("EU", 2000), ("US", None)]


def test_the_migration_chains_and_adds_everything_it_says():
    src = MIGRATION.read_text()
    assert 'revision = "zzzzcappe53"' in src and 'down_revision = "zzzzcappe52"' in src
    for col in ("prices_include_tax", "tax_on_shipping", "tax_rate_bps", "tax_included", "shipping_tax_cents"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src and f"DROP COLUMN IF EXISTS {col}" in src
    assert src.count("ALTER TABLE cappe_shopper_subscriptions") == 2
    assert "CHECK (tax_rate_bps BETWEEN 0 AND 10000)" in src
