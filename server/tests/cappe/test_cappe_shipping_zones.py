"""Shipping zones and a currency per store — the 2026-10 commerce readiness review, PR 5.

What each block pins:

  * where a store ships: the home country always, a zone's countries, the
    rest of the world when a zone covers it, nowhere else; the home country
    beats a zone, a named country beats "everywhere else";
  * what it costs: a zone's flat rate and free-shipping threshold, and tax
    only at home or in a zone that says to charge it;
  * a zone set that can't price unambiguously is refused, and the plan gate;
  * the bag's quote prices the chosen country, says when the store doesn't
    ship there, and keeps subscriptions at home;
  * an order stores the country it was priced for, and Stripe's payment page
    then takes an address in that country only (it used to be US only);
  * the store's currency: allowlisted, inherited by products, refused while
    subscriptions are billing, and on every booking price (bookings were
    hard-coded to USD);
  * the bag script asks where to ship.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_shipping_zones.py -q
"""
import asyncio
import inspect
import json
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
from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.cappe.models.shop import (  # noqa: E402
    CappeCartItem,
    CappeCheckoutRequest,
    CappeShippingAddressInput,
    CappeShippingZoneInput,
    CappeShippingZonesReplace,
)
from app.cappe.models.shopper import CartQuoteRequest  # noqa: E402
from app.cappe.models.sites import CappeSiteUpdate  # noqa: E402
from app.cappe.routes import bookings as owner_bookings  # noqa: E402
from app.cappe.routes import shipping as zones_routes  # noqa: E402
from app.cappe.routes import shop as shop_routes  # noqa: E402
from app.cappe.routes import sites as site_routes  # noqa: E402
from app.cappe.routes.public import booking_selfserve  # noqa: E402
from app.cappe.routes.public import bookings as public_bookings  # noqa: E402
from app.cappe.routes.public import shop as public_shop  # noqa: E402
from app.cappe.services import cart, commerce, entitlements, recurring, shipping  # noqa: E402
from app.cappe.services import stripe_connect  # noqa: E402

SITE, ORDER = uuid4(), uuid4()
TOKEN = "cd" * 16
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
ASSETS = pathlib.Path(commerce.__file__).parent / "render" / "assets"
MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "zzzzcappe43_shipping_zones.py"

HOME = {"home_country": "US", "shipping_flat_cents": 600, "shipping_free_threshold_cents": 5000,
        "tax_rate_bps": 1000, "currency": "USD"}
CANADA = {"id": uuid4(), "name": "North America", "countries": ["CA", "MX"], "rest_of_world": False,
          "flat_cents": 1500, "free_threshold_cents": None, "charge_tax": False}
WORLD = {"id": uuid4(), "name": "Everywhere else", "countries": [], "rest_of_world": True,
         "flat_cents": 3000, "free_threshold_cents": 20000, "charge_tax": False}
ZONES_ON = SimpleNamespace(platform_fee_bps=200, has=lambda f: f == "shipping_zones")
ZONES_OFF = SimpleNamespace(platform_fee_bps=200, has=lambda _f: False)


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
    """Answers by SQL fragment; records every call."""

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


# ── where a store ships ──────────────────────────────────────────────────────

def test_the_home_country_ships_at_the_stores_own_rates_with_tax():
    dest = shipping.resolve_destination(HOME, [CANADA, WORLD], None)
    assert dest.country == "US" and dest.is_home and dest.charge_tax
    assert (dest.flat_cents, dest.free_threshold_cents) == (600, 5000)


def test_a_zone_country_ships_at_the_zones_rates():
    dest = shipping.resolve_destination(HOME, [CANADA], "ca")
    assert dest.country == "CA" and not dest.is_home and dest.zone_id == str(CANADA["id"])
    assert (dest.flat_cents, dest.free_threshold_cents, dest.charge_tax) == (1500, None, False)


def test_everywhere_else_covers_any_shippable_country_but_a_named_zone_wins():
    assert shipping.resolve_destination(HOME, [WORLD, CANADA], "MX").zone_id == str(CANADA["id"])
    assert shipping.resolve_destination(HOME, [CANADA, WORLD], "FR").zone_id == str(WORLD["id"])
    # Not a country Stripe can ship to: nobody covers it.
    assert shipping.resolve_destination(HOME, [WORLD], "ZZ") is None


def test_a_country_nobody_covers_is_not_shippable():
    assert shipping.resolve_destination(HOME, [CANADA], "FR") is None
    # No zones at all = the home country only (the old behaviour).
    assert shipping.resolve_destination(HOME, [], "CA") is None


def test_the_home_country_beats_a_zone_that_also_lists_it():
    zone = {**CANADA, "countries": ["US", "CA"]}
    assert shipping.resolve_destination(HOME, [zone], "US").is_home


def test_a_store_that_never_set_a_home_country_or_currency_is_us_and_usd():
    assert shipping.home_country({}) == "US" and shipping.site_currency({}) == "USD"
    assert shipping.home_country(None) == "US"
    assert shipping.home_country({"home_country": "gb"}) == "GB"
    assert shipping.site_currency({"currency": "eur"}) == "EUR"
    # A row type without .get (e.g. a tuple) falls back too.
    assert shipping.home_country(("US",)) == "US"


def test_the_picker_lists_home_first_then_alphabetical():
    assert shipping.ship_countries(HOME, [CANADA]) == ["US", "CA", "MX"]
    everywhere = shipping.ship_countries({"home_country": "GB"}, [WORLD])
    assert everywhere[0] == "GB" and len(everywhere) == len(shipping.SHIP_COUNTRIES)
    assert everywhere[1:] == sorted(everywhere[1:])


def test_the_country_list_is_stripes_own_without_its_placeholder():
    assert "ZZ" not in shipping.SHIP_COUNTRIES
    assert {"US", "CA", "GB", "DE", "AU", "JP", "XK"} <= shipping.SHIP_COUNTRIES
    # Territories Stripe doesn't accept an address in are not offered.
    assert not {"AS", "VI", "CU", "KP"} & shipping.SHIP_COUNTRIES


# ── what it costs ────────────────────────────────────────────────────────────

LINES = [{"unit_price_cents": 2000, "quantity": 1, "fulfillment": "physical"},
         {"unit_price_cents": 500, "quantity": 1, "fulfillment": "digital"}]


def test_home_charges_tax_on_goods_and_the_flat_rate():
    out = cart.cart_totals(LINES, HOME)
    assert out == {"subtotal_cents": 2500, "tax_cents": 200, "shipping_cents": 600, "total_cents": 3300}


def test_a_zone_charges_its_rate_and_no_tax_unless_it_says_so():
    ca = shipping.resolve_destination(HOME, [CANADA], "CA")
    assert cart.cart_totals(LINES, HOME, ca) == {
        "subtotal_cents": 2500, "tax_cents": 0, "shipping_cents": 1500, "total_cents": 4000}
    taxed = shipping.resolve_destination(HOME, [{**CANADA, "charge_tax": True}], "CA")
    assert cart.cart_totals(LINES, HOME, taxed)["tax_cents"] == 200


def test_a_zones_free_shipping_threshold_compares_the_goods():
    world = shipping.resolve_destination(HOME, [WORLD], "FR")
    big = [{"unit_price_cents": 20000, "quantity": 1, "fulfillment": "physical"}]
    assert cart.cart_totals(big, HOME, world)["shipping_cents"] == 0
    assert cart.cart_totals(LINES, HOME, world)["shipping_cents"] == 3000


# ── zone sets that can't price unambiguously ─────────────────────────────────

def _zone(name, countries=(), rest=False):
    return CappeShippingZoneInput(name=name, countries=list(countries), rest_of_world=rest)


@pytest.mark.parametrize("zones,fragment", [
    ([_zone("Home", ["US"])], "home country"),
    ([_zone("A", ["CA"]), _zone("B", ["ca"])], "in both"),
    ([_zone("A", rest=True), _zone("B", rest=True)], "Only one zone"),
    ([_zone("Empty")], "at least one country"),
])
def test_a_zone_set_that_cant_price_is_refused(zones, fragment):
    with pytest.raises(HTTPException) as exc:
        shipping.validate_zones(zones, home="US")
    assert exc.value.status_code == 422 and fragment in exc.value.detail


def test_too_many_zones_are_refused():
    with pytest.raises(HTTPException):
        shipping.validate_zones([_zone(f"Z{i}", [c]) for i, c in enumerate(["CA"] * 21)], home="US")
    with pytest.raises(ValidationError):
        CappeShippingZonesReplace(zones=[{"name": f"Z{i}", "countries": ["CA"]} for i in range(21)])


def test_zone_input_cleans_its_countries():
    z = CappeShippingZoneInput(name="  EU ", countries=["fr", "DE", "fr"])
    assert z.name == "EU" and z.countries == ["FR", "DE"]
    assert CappeShippingZoneInput(name="Rest", countries=["FR"], rest_of_world=True).countries == []
    with pytest.raises(ValidationError):
        CappeShippingZoneInput(name="Bad", countries=["XX"])
    with pytest.raises(ValidationError):
        CappeShippingZoneInput(name="   ", countries=["FR"])


def test_valid_zones_pass():
    shipping.validate_zones([_zone("NA", ["CA", "MX"]), _zone("World", rest=True)], home="US")


# ── plan gate ────────────────────────────────────────────────────────────────

def test_a_plan_without_zones_ships_home_only_and_never_reads_them():
    conn = SqlConn([("cappe_shipping_zones", [CANADA])])
    assert asyncio.run(shipping.load_zones(conn, SITE, ZONES_OFF)) == []
    assert conn.calls == []
    assert asyncio.run(shipping.load_zones(conn, SITE, ZONES_ON)) == [CANADA]


def test_an_unreadable_catalog_keeps_a_paying_stores_zones():
    assert entitlements._legacy_fallback("business").has("shipping_zones")
    assert entitlements._legacy_fallback("pro").has("shipping_zones")
    assert not entitlements._legacy_fallback("free").has("shipping_zones")


def test_the_migration_chains_and_grants_the_feature():
    src = MIGRATION.read_text()
    assert 'down_revision = "zzzzcappe42"' in src and 'revision = "zzzzcappe43"' in src
    assert "jsonb_build_object('shipping_zones', true)" in src
    assert "WHERE code IN ('business', 'pro', 'hosting')" in src
    assert "ON cappe_shipping_zones (site_id) WHERE rest_of_world" in src
    # The two currency lists agree.
    for code in shipping.SITE_CURRENCIES:
        assert f"'{code}'" in src


# ── the zones endpoints ──────────────────────────────────────────────────────

def _wire_zones(monkeypatch, ent, zones=()):
    conn = SqlConn([("FROM cappe_shipping_zones", list(zones))])
    account = SimpleNamespace(id=uuid4(), plan="business")
    monkeypatch.setattr(zones_routes, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(zones_routes, "get_owned_site", AsyncMock(return_value={"id": SITE, **HOME}))
    monkeypatch.setattr(zones_routes, "resolve_entitlements", AsyncMock(return_value=ent))
    return conn, account


def test_the_owner_sees_every_saved_zone_even_when_the_plan_pauses_them(monkeypatch):
    conn, account = _wire_zones(monkeypatch, ZONES_OFF, [CANADA])
    out = asyncio.run(zones_routes.get_shipping_zones(SITE, account))
    assert out["enabled"] is False and out["home_country"] == "US" and out["currency"] == "USD"
    assert out["zones"][0]["countries"] == ["CA", "MX"]
    assert "US" in out["countries"] and "ZZ" not in out["countries"]


def test_saving_zones_replaces_the_set_in_order(monkeypatch):
    conn, account = _wire_zones(monkeypatch, ZONES_ON)
    body = CappeShippingZonesReplace(zones=[
        {"name": "NA", "countries": ["ca", "MX"], "flat_cents": 1500},
        {"name": "World", "rest_of_world": True, "flat_cents": 3000, "charge_tax": True},
    ])
    asyncio.run(zones_routes.replace_shipping_zones(SITE, body, account))
    assert conn.sql("FOR UPDATE") and conn.sql("DELETE FROM cappe_shipping_zones")
    inserts = [c[2] for c in conn.sql("INSERT INTO cappe_shipping_zones")]
    assert [(a[1], a[2], a[3], a[4], a[6], a[7]) for a in inserts] == [
        ("NA", ["CA", "MX"], False, 1500, False, 0),
        ("World", [], True, 3000, True, 1),
    ]


def test_saving_zones_needs_the_plan_but_clearing_them_does_not(monkeypatch):
    conn, account = _wire_zones(monkeypatch, ZONES_OFF)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(zones_routes.replace_shipping_zones(
            SITE, CappeShippingZonesReplace(zones=[{"name": "NA", "countries": ["CA"]}]), account))
    assert exc.value.status_code == 402 and not conn.sql("DELETE")
    asyncio.run(zones_routes.replace_shipping_zones(SITE, CappeShippingZonesReplace(zones=[]), account))
    assert conn.sql("DELETE FROM cappe_shipping_zones") and not conn.sql("INSERT")


def test_saving_a_zone_with_the_home_country_is_refused(monkeypatch):
    conn, account = _wire_zones(monkeypatch, ZONES_ON)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(zones_routes.replace_shipping_zones(
            SITE, CappeShippingZonesReplace(zones=[{"name": "Home", "countries": ["US"]}]), account))
    assert exc.value.status_code == 422 and not conn.sql("DELETE")


# ── the bag's quote ──────────────────────────────────────────────────────────

def _wire_quote(monkeypatch, *, fulfillment="physical", ent=ZONES_ON, zones=(CANADA,)):
    product = {"id": uuid4(), "site_id": SITE, "name": "Mug", "price_cents": 2000, "currency": "USD",
               "inventory": None, "status": "active", "fulfillment": fulfillment,
               "subscription_intervals": ["month"], "subscription_discount_bps": 0, "requires_approval": False}
    conn = SqlConn([
        ("FROM cappe_sites WHERE id=$1", {**HOME}),
        ("stripe_charges_enabled", True),
        ("SELECT a.plan", "business"),
        ("FROM cappe_products", [product]),
        ("SELECT NOW()", NOW),
        ("FROM cappe_shipping_zones", list(zones)),
    ])
    monkeypatch.setattr(public_shop, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_shop, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_shop, "_published_site", AsyncMock(return_value={"id": SITE, "timezone": "UTC"}))
    monkeypatch.setattr(public_shop, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(public_shop, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(public_shop, "resolve_entitlements", AsyncMock(return_value=ent))
    return conn, product


def _quote(product, **kw):
    return public_shop.quote(
        "shop", CartQuoteRequest(items=[{"product_id": str(product["id"]), "quantity": 1}], **kw), request=None)


def test_the_quote_prices_the_chosen_country(monkeypatch):
    _conn, product = _wire_quote(monkeypatch)
    out = asyncio.run(_quote(product, ship_country="CA"))
    assert out["ship_country"] == "CA" and out["ships_to"] is True
    assert (out["tax_cents"], out["shipping_cents"], out["total_cents"]) == (0, 1500, 3500)
    assert out["ship_countries"] == ["US", "CA", "MX"] and out["home_country"] == "US"


def test_the_quote_defaults_to_home(monkeypatch):
    _conn, product = _wire_quote(monkeypatch)
    out = asyncio.run(_quote(product))
    assert out["ship_country"] == "US" and (out["tax_cents"], out["shipping_cents"]) == (200, 600)


def test_the_quote_says_when_the_store_doesnt_ship_there(monkeypatch):
    _conn, product = _wire_quote(monkeypatch)
    out = asyncio.run(_quote(product, ship_country="FR"))
    assert out["ships_to"] is False
    # Nothing misleading: no shipping or tax priced for a place it won't go.
    assert (out["tax_cents"], out["shipping_cents"], out["total_cents"]) == (0, 0, 2000)


def test_a_plan_without_zones_quotes_home_only(monkeypatch):
    _conn, product = _wire_quote(monkeypatch, ent=ZONES_OFF)
    out = asyncio.run(_quote(product, ship_country="CA"))
    assert out["ships_to"] is False and out["ship_countries"] == ["US"]


def test_a_bag_with_nothing_to_ship_has_no_ship_to(monkeypatch):
    conn, product = _wire_quote(monkeypatch, fulfillment="digital")
    out = asyncio.run(_quote(product, ship_country="FR"))
    assert "ships_to" not in out and out["shipping_cents"] == 0
    assert not conn.sql("cappe_shipping_zones")


def test_a_subscription_ships_within_the_home_country_only(monkeypatch):
    _conn, product = _wire_quote(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_quote(product, ship_country="CA", interval="month"))
    assert exc.value.status_code == 422 and "within US" in exc.value.detail
    out = asyncio.run(_quote(product, interval="month"))
    assert out["ship_country"] == "US"


def test_quote_and_checkout_requests_take_only_shippable_codes():
    item = [{"product_id": str(uuid4()), "quantity": 1}]
    assert CartQuoteRequest(items=item, ship_country="gb").ship_country == "GB"
    for bad in ("ZZ", "GBR", "1A"):
        with pytest.raises(ValidationError):
            CartQuoteRequest(items=item, ship_country=bad)
    with pytest.raises(ValidationError):
        CappeCheckoutRequest(customer_email="b@example.com", items=item, ship_country="ZZ")


# ── an order stores where it ships; Stripe takes that country only ───────────

class OrderConn:
    def __init__(self, product, zones=(CANADA,)):
        self.product, self.zones, self.order, self.items = product, list(zones), None, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return self

    async def fetch(self, sql, *args):
        return self.zones if "cappe_shipping_zones" in sql else []

    async def fetchrow(self, sql, *args):
        if "FROM cappe_products" in sql:
            return self.product
        if "FROM cappe_sites" in sql:
            return {**HOME, "tax_label": None, "shipping_label": None}
        if "INSERT INTO cappe_orders" in sql:
            self.order = {"id": ORDER, "status": "pending", "access_token": TOKEN, "subtotal_cents": args[3],
                          "tax_cents": args[4], "shipping_cents": args[5], "total_cents": args[6],
                          "currency": args[7], "requires_approval": args[9], "shipping_address": args[10],
                          "ship_country": args[11]}
            return self.order
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        if sql == "SELECT NOW()":
            return NOW
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        if "INSERT INTO cappe_order_items" in sql:
            self.items.append(args)


def _wire_order(monkeypatch, *, fulfillment="physical", ent=ZONES_ON, cards=True, **body_kw):
    product = {"id": uuid4(), "name": "Mug", "price_cents": 2000, "currency": "USD", "inventory": None,
               "low_stock_threshold": None, "status": "active", "fulfillment": fulfillment,
               "booking_type_id": None, "requires_approval": False, "intake_fields": "[]"}
    conn = OrderConn(product)
    owner = {"plan": "business", "status": "active", "email": "owner@example.com", "name": "Owner",
             "stripe_account_id": "acct_1" if cards else None, "stripe_charges_enabled": cards}
    stripe = SimpleNamespace(create_checkout_session=AsyncMock(return_value={"id": "cs_1", "url": "https://pay"}))
    monkeypatch.setattr(commerce, "get_connection", lambda: conn)
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(commerce, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(commerce, "lock_stock_rows", AsyncMock())
    monkeypatch.setattr(commerce, "fetch_site_owner", AsyncMock(return_value=owner))
    monkeypatch.setattr(commerce, "resolve_entitlements", AsyncMock(return_value=ent))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    monkeypatch.setattr(commerce, "check_recipient_send_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(commerce, "get_cappe_stripe", lambda: stripe)
    site = {"id": SITE, "name": "Store", "timezone": "UTC", "subdomain": "shop", "custom_domain": "shop.example.com"}
    body = CappeCheckoutRequest(
        customer_email="buyer@example.com", items=[CappeCartItem(product_id=product["id"], quantity=1)],
        success_url="https://shop.example.com/", cancel_url="https://shop.example.com/", **body_kw,
    )
    return site, body, conn, stripe


def test_an_order_abroad_is_priced_for_its_zone_and_stripe_takes_that_country_only(monkeypatch):
    site, body, conn, stripe = _wire_order(monkeypatch, ship_country="CA")
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert conn.order["ship_country"] == "CA"
    assert (conn.order["tax_cents"], conn.order["shipping_cents"], conn.order["total_cents"]) == (0, 1500, 3500)
    kw = stripe.create_checkout_session.await_args.kwargs
    assert kw["ship_countries"] == ["CA"] and kw["shipping_option"]["amount_cents"] == 1500


def test_an_order_without_a_country_ships_home_like_an_old_app_expects(monkeypatch):
    site, body, conn, stripe = _wire_order(monkeypatch)
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert conn.order["ship_country"] == "US" and conn.order["tax_cents"] == 200
    assert stripe.create_checkout_session.await_args.kwargs["ship_countries"] == ["US"]


def test_an_order_to_a_country_the_store_doesnt_ship_to_is_refused(monkeypatch):
    site, body, conn, stripe = _wire_order(monkeypatch, ship_country="FR")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert exc.value.status_code == 422 and "doesn't ship to FR" in exc.value.detail
    assert conn.order is None


def test_a_typed_address_in_another_country_than_priced_is_refused(monkeypatch):
    site, body, conn, _stripe = _wire_order(
        monkeypatch, cards=False, ship_country="CA",
        shipping_address={"line1": "1 Main", "city": "Paris", "country": "FR"},
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert exc.value.status_code == 422 and "priced for shipping to CA" in exc.value.detail


def test_a_typed_address_takes_the_order_country_when_it_names_none(monkeypatch):
    site, body, conn, _stripe = _wire_order(
        monkeypatch, cards=False, ship_country="MX",
        shipping_address={"line1": "1 Calle", "city": "Monterrey"},
    )
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert json.loads(conn.order["shipping_address"])["address"]["country"] == "MX"
    assert conn.order["ship_country"] == "MX"


def test_a_typed_address_alone_decides_the_country(monkeypatch):
    site, body, conn, _stripe = _wire_order(
        monkeypatch, cards=False, shipping_address={"line1": "1 Main", "city": "Toronto", "country": "CA"},
    )
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert conn.order["ship_country"] == "CA" and conn.order["shipping_cents"] == 1500


def test_a_digital_order_has_no_ship_country(monkeypatch):
    site, body, conn, stripe = _wire_order(monkeypatch, fulfillment="digital", ship_country="FR")
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert conn.order["ship_country"] is None
    assert stripe.create_checkout_session.await_args.kwargs["ship_countries"] is None


def test_pay_now_reuses_the_orders_country():
    src = inspect.getsource(commerce.pay_for_order)
    assert "COALESCE(o.ship_country, s.home_country) AS ship_country" in src


class _FakeStripeModule:
    def __init__(self):
        self.created = []
        self.checkout = SimpleNamespace(Session=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.created.append(kw)
        return {"id": "cs_1", "url": "https://pay"}


def test_stripe_is_told_the_orders_country(monkeypatch):
    fake = _FakeStripeModule()
    monkeypatch.setattr(stripe_connect, "stripe", fake)
    client = stripe_connect.CappeStripe.__new__(stripe_connect.CappeStripe)
    client._ensure_key = lambda: None
    common = dict(account_id="acct_1", currency="cad", line_items=[], application_fee_cents=0,
                  success_url="https://s", cancel_url="https://c", metadata={},
                  collect_shipping_address=True, shipping_option={"label": "Shipping", "amount_cents": 0})
    asyncio.run(client.create_checkout_session(**common, ship_countries=["CA"]))
    asyncio.run(client.create_checkout_session(**common))
    assert [c["shipping_address_collection"]["allowed_countries"] for c in fake.created] == [["CA"], ["US"]]
    asyncio.run(client.create_subscription_checkout(
        account_id="acct_1", customer_id="cus_1", line_items=[], application_fee_percent=2,
        success_url="https://s", cancel_url="https://c", metadata={}, collect_shipping=True,
        idempotency_key="k", ship_countries=["GB"]))
    assert fake.created[-1]["shipping_address_collection"]["allowed_countries"] == ["GB"]


def test_a_subscription_checkout_ships_to_the_home_country():
    src = inspect.getsource(recurring.checkout)
    assert "ship_countries=[home_country(site)]" in src


# ── the store's currency ─────────────────────────────────────────────────────

def test_a_store_charges_in_a_two_decimal_currency_only():
    assert CappeSiteUpdate(currency="eur", home_country="de").model_dump(exclude_none=True) == {
        "currency": "EUR", "home_country": "DE"}
    for bad in ("JPY", "KRW", "XYZ"):
        with pytest.raises(ValidationError):
            CappeSiteUpdate(currency=bad)
    with pytest.raises(ValidationError):
        CappeSiteUpdate(home_country="ZZ")


def _wire_site_update(monkeypatch, *, current="USD", live_subs=0):
    row = {"id": SITE, "theme_config": "{}", "meta_config": "{}", "currency": "EUR"}
    conn = SqlConn([
        ("SELECT currency FROM cappe_sites", current),
        ("FROM cappe_shopper_subscriptions", live_subs),
        ("UPDATE cappe_sites SET", row),
    ])
    monkeypatch.setattr(site_routes, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(site_routes, "get_owned_site", AsyncMock(return_value=row))
    monkeypatch.setattr(site_routes, "invalidate_render_cache", AsyncMock())
    return conn, SimpleNamespace(id=uuid4(), plan="business")


def test_changing_the_currency_reprices_every_product_in_it(monkeypatch):
    conn, account = _wire_site_update(monkeypatch)
    asyncio.run(site_routes.update_site(SITE, CappeSiteUpdate(currency="EUR", home_country="DE"), account))
    (update,) = conn.sql("UPDATE cappe_sites SET")
    assert "home_country = $" in update[1] and "currency = $" in update[1]
    assert "DE" in update[2] and "EUR" in update[2]
    assert conn.sql("FOR UPDATE")
    (products,) = conn.sql("UPDATE cappe_products SET currency")
    assert products[2] == ("EUR", SITE)


def test_saving_the_same_currency_touches_no_product(monkeypatch):
    conn, account = _wire_site_update(monkeypatch, current="EUR")
    asyncio.run(site_routes.update_site(SITE, CappeSiteUpdate(currency="EUR"), account))
    assert not conn.sql("cappe_products") and not conn.sql("cappe_shopper_subscriptions")


def test_a_store_with_live_subscriptions_cant_change_currency(monkeypatch):
    conn, account = _wire_site_update(monkeypatch, live_subs=2)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(site_routes.update_site(SITE, CappeSiteUpdate(currency="EUR"), account))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "has_subscriptions" and exc.value.detail["count"] == 2
    assert "2 subscriptions are still billing" in exc.value.detail["message"]
    assert not conn.sql("UPDATE cappe_products")


def test_a_product_is_priced_in_its_stores_currency():
    create_src = inspect.getsource(shop_routes.create_product)
    assert "COALESCE((SELECT currency FROM cappe_sites WHERE id = $1), $5)" in create_src
    update_src = inspect.getsource(shop_routes.update_product)
    assert '"price_cents", "image_url"' in update_src and '"currency", "image_url"' not in update_src
    from app.cappe.services.merlin import setup_actions
    assert "SELECT currency FROM cappe_sites WHERE id = $1" in inspect.getsource(setup_actions)


def test_booking_prices_are_in_the_stores_currency():
    assert "currency=site_currency(site)" in inspect.getsource(booking_selfserve.public_booking_quote)
    assert '"currency": site_currency(site)' in inspect.getsource(public_bookings)
    assert '"currency": currency' in inspect.getsource(public_bookings.public_booking_types)
    assert "currency = site_currency(await get_owned_site(" in inspect.getsource(owner_bookings.list_requests)


def test_public_booking_types_carry_the_currency(monkeypatch):
    conn = SqlConn([("FROM cappe_booking_types", [{"id": uuid4(), "name": "Cut"}]), ("cappe_staff_services", [])])
    monkeypatch.setattr(public_bookings, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_bookings, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_bookings, "_published_site",
                        AsyncMock(return_value={"id": SITE, "currency": "GBP"}))
    out = asyncio.run(public_bookings.public_booking_types("shop", request=None, location_id=None))
    assert out[0]["currency"] == "GBP"


# ── the storefront scripts ───────────────────────────────────────────────────

def _js(name):
    return (ASSETS / name).read_text()


def test_the_bag_asks_where_to_ship_and_quotes_that_country():
    js = _js("cart.js")
    assert "req.ship_country=shipTo" in js and "data-ship" in js
    assert "body.ship_country=quote.ship_country" in js   # the order is priced where the bag was
    assert "quote.ships_to===false" in js            # checkout refused, and said why
    assert "Intl.DisplayNames" in js                 # country names, not codes
    assert "cz-cart-country:" in js                  # the choice survives a reload


def test_the_booking_widget_shows_the_stores_currency():
    js = _js("booking.js")
    assert "RT.money(t.price_cents,'USD')" not in js
    assert "t.currency" in js and "res.currency" in js
