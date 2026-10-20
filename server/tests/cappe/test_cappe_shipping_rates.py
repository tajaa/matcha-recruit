"""Delivery options — physical sellers PR 3/7 (`zzzzcappe52`, services/shipping.py).

What each block pins:

  * what an option costs: its amount, each item after the first, the
    products' own surcharges, free over an amount, offered only inside its
    value and weight bands and (local delivery) its postal codes; free when
    nothing in the bag counts or the goods cost nothing, as the flat rate was;
  * a destination with no options is its flat rate, as one option ("flat");
    the first option is the default, estimates are handling + transit;
  * the request models clean what the owner typed, by method;
  * the settings route saves options with their zones, keeps what a save
    leaves out, and gates them with zones;
  * the quote offers the options, picks the one asked for (or the default),
    and asks for a postal code when local delivery needs one;
  * an order keeps the option it was priced with, refuses one it no longer
    gets, needs an address for local delivery and none for pickup; Stripe
    asks for an address only for a shipped order and shows the estimate;
  * the order page says where to collect it and when it arrives;
  * the migration, and the bag script.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_shipping_rates.py -q
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
    CappeProductCreate,
    CappeProductUpdate,
    CappeShippingRateInput,
    CappeShippingZonesReplace,
)
from app.cappe.models.shopper import CartQuoteRequest  # noqa: E402
from app.cappe.models.sites import CappeSiteUpdate  # noqa: E402
from app.cappe.routes import shipping as zones_routes  # noqa: E402
from app.cappe.routes import shop as shop_routes  # noqa: E402
from app.cappe.routes import sites as site_routes  # noqa: E402
from app.cappe.routes.public import shop as public_shop  # noqa: E402
from app.cappe.services import cart, commerce, shipping, stripe_connect  # noqa: E402
from app.cappe.services.commerce import build_stripe_line_items  # noqa: E402
from app.cappe.services.entitlements import ALL_FULFILLMENT  # noqa: E402
from app.cappe.services.render.order_page import _shipping_html, delivery_estimate  # noqa: E402
from app.cappe.services.shipping import Destination, ShipLoad, ShipRate  # noqa: E402

SITE, ORDER = uuid4(), uuid4()
TOKEN = "ab" * 16
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
ASSETS = pathlib.Path(commerce.__file__).parent / "render" / "assets"
MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "zzzzcappe52_shipping_rates.py"

HOME = {"home_country": "US", "shipping_flat_cents": 600, "shipping_free_threshold_cents": 5000,
        "tax_rate_bps": 1000, "currency": "USD", "shipping_label": "Shipping",
        "handling_days_min": 1, "handling_days_max": 2}
ZONES_ON = SimpleNamespace(platform_fee_bps=200, allowed_fulfillment=ALL_FULFILLMENT, has=lambda f: f == "shipping_zones")
ZONES_OFF = SimpleNamespace(platform_fee_bps=200, allowed_fulfillment=ALL_FULFILLMENT, has=lambda _f: False)


def rate_row(name, method="ship", zone_id=None, **kw):
    """A `cappe_shipping_rates` row as asyncpg would return it."""
    row = {"id": uuid4(), "zone_id": zone_id, "name": name, "method": method, "amount_cents": 0,
           "per_item_cents": 0, "min_subtotal_cents": None, "max_subtotal_cents": None,
           "min_weight_g": None, "max_weight_g": None, "free_over_cents": None,
           "delivery_min_days": None, "delivery_max_days": None, "postal_codes": [],
           "instructions": None, "sort_order": 0}
    row.update(kw)
    return row


STANDARD = rate_row("Standard", amount_cents=500, per_item_cents=100, delivery_min_days=3, delivery_max_days=5)
EXPRESS = rate_row("Express", amount_cents=1500, max_weight_g=2000, delivery_min_days=1, delivery_max_days=1)
PICKUP = rate_row("Pickup", "pickup", instructions="12 Market St, 9–5")
LOCAL = rate_row("Local", "local_delivery", amount_cents=700, postal_codes=["941"])


# ── what an option costs ─────────────────────────────────────────────────────

def test_an_option_is_its_amount_plus_each_extra_item_plus_surcharges():
    rate = ShipRate(id="r", name="Standard", amount_cents=500, per_item_cents=100)
    assert shipping.rate_price(rate, ShipLoad(units=1), 3000) == 500
    assert shipping.rate_price(rate, ShipLoad(units=3, surcharge_cents=250), 3000) == 500 + 200 + 250


def test_an_option_is_free_over_its_amount():
    rate = ShipRate(id="r", name="Standard", amount_cents=500, free_over_cents=4000)
    assert shipping.rate_price(rate, ShipLoad(units=1, surcharge_cents=300), 3999) == 800
    assert shipping.rate_price(rate, ShipLoad(units=1, surcharge_cents=300), 4000) == 0


@pytest.mark.parametrize("load,goods,offered", [
    (ShipLoad(units=1, weight_g=2000), 3000, True),     # bands are inclusive
    (ShipLoad(units=1, weight_g=2001), 3000, False),    # too heavy
    (ShipLoad(units=1, weight_g=10), 999, False),       # below its order value
    (ShipLoad(units=1, weight_g=10), 10001, False),     # above it
])
def test_an_option_is_offered_inside_its_bands_only(load, goods, offered):
    rate = ShipRate(id="r", name="Express", amount_cents=1500, max_weight_g=2000,
                    min_subtotal_cents=1000, max_subtotal_cents=10000)
    assert (shipping.rate_price(rate, load, goods) is not None) is offered


def test_pickup_charges_its_amount_and_nothing_per_item():
    rate = ShipRate(id="p", name="Pickup", method="pickup", amount_cents=200, per_item_cents=999)
    assert shipping.rate_price(rate, ShipLoad(units=4, surcharge_cents=500), 3000) == 200


def test_nothing_that_counts_or_nothing_to_pay_ships_free():
    rate = ShipRate(id="r", name="Standard", amount_cents=500)
    pickup = ShipRate(id="p", name="Pickup", method="pickup", amount_cents=200)
    assert shipping.rate_price(rate, ShipLoad(units=0), 3000) == 0     # every item ships free
    assert shipping.rate_price(rate, ShipLoad(units=2), 0) == 0        # a giveaway
    assert shipping.rate_price(pickup, ShipLoad(units=1), 0) == 0      # no payment would settle it


@pytest.mark.parametrize("postal,matches", [
    ("94110", True), ("941 10", True), ("94210", False), ("", False), (None, False),
])
def test_local_delivery_covers_its_postal_codes(postal, matches):
    rate = ShipRate(id="l", name="Local", method="local_delivery", postal_codes=("941",))
    assert shipping.postal_matches(rate, postal) is matches
    # An area-less local delivery covers the destination, but still needs to know where.
    anywhere = ShipRate(id="l", name="Anywhere", method="local_delivery")
    assert shipping.postal_matches(anywhere, "10001") is True and shipping.postal_matches(anywhere, None) is False
    sw = ShipRate(id="l", name="London", method="local_delivery", postal_codes=("sw1",))
    assert shipping.postal_matches(sw, "SW1A 1AA") is True


def test_the_load_skips_what_ships_free_and_counts_the_rest():
    load = shipping.ship_load([
        ({"weight_g": 500, "shipping_surcharge_cents": 100}, 2),
        ({"weight_g": 9000, "ships_free": True, "shipping_surcharge_cents": 900}, 1),
        ({"weight_g": None}, 1),
        (None, 3),
    ], "94110")
    assert load == ShipLoad(units=3, weight_g=1000, surcharge_cents=200, postal_code="94110")


# ── the options a destination offers ─────────────────────────────────────────

def _dest(*rows, **kw):
    return Destination("US", 600, 5000, True, rates=tuple(shipping._rate(r) for r in rows), **kw)


def test_no_options_is_the_flat_rate_as_one_option():
    [flat] = shipping.shipping_options(Destination("US", 600, 5000, True), ShipLoad(units=1), 3000,
                                       label="Postage", handling=(1, 2))
    assert flat == {"id": "flat", "label": "Postage", "method": "ship", "amount_cents": 600,
                    "delivery_min_days": 1, "delivery_max_days": 2, "instructions": None}


def test_options_come_in_the_owners_order_with_handling_added():
    opts = shipping.shipping_options(_dest(STANDARD, EXPRESS, PICKUP), ShipLoad(units=2, weight_g=500), 3000,
                                     handling=(1, 2))
    assert [(o["label"], o["amount_cents"], o["delivery_min_days"], o["delivery_max_days"]) for o in opts] == [
        ("Standard", 600, 4, 7), ("Express", 1500, 2, 3), ("Pickup", 0, 1, 2)]
    assert [o["instructions"] for o in opts] == [None, None, "12 Market St, 9–5"]


def test_an_option_the_bag_doesnt_fit_is_left_out():
    opts = shipping.shipping_options(_dest(STANDARD, EXPRESS, LOCAL), ShipLoad(units=1, weight_g=5000), 3000)
    assert [o["label"] for o in opts] == ["Standard"]


def test_choosing_an_option():
    opts = shipping.shipping_options(_dest(STANDARD, PICKUP), ShipLoad(units=1), 3000)
    pickup_id = str(PICKUP["id"])
    assert shipping.choose_option(opts, pickup_id, strict=True)["label"] == "Pickup"
    assert shipping.choose_option(opts, None, strict=True)["label"] == "Standard"
    # A quote falls back to the default; an order refuses rather than reprice.
    assert shipping.choose_option(opts, "gone", strict=False)["label"] == "Standard"
    with pytest.raises(HTTPException) as exc:
        shipping.choose_option(opts, "gone", strict=True)
    assert exc.value.status_code == 409
    assert shipping.choose_option([], None, strict=False) is None


def test_the_handling_time_reads_either_end():
    assert shipping.handling_days({}) == (None, None)
    assert shipping.handling_days({"handling_days_min": 2}) == (2, 2)
    assert shipping.handling_days({"handling_days_min": 3, "handling_days_max": 1}) == (1, 3)


def test_a_destination_gets_its_own_options():
    zone = {"id": uuid4(), "name": "Canada", "countries": ["CA"], "rest_of_world": False,
            "flat_cents": 1500, "free_threshold_cents": None, "charge_tax": False}
    rates = {None: [shipping._rate(PICKUP)], str(zone["id"]): [shipping._rate(EXPRESS)]}
    assert [r.name for r in shipping.resolve_destination(HOME, [zone], "US", rates).rates] == ["Pickup"]
    assert [r.name for r in shipping.resolve_destination(HOME, [zone], "CA", rates).rates] == ["Express"]
    assert shipping.resolve_destination(HOME, [zone], "FR", rates) is None
    assert shipping.resolve_destination(HOME, [zone], "US").rates == ()


def test_the_cart_prices_the_option_picked_and_refuses_none_at_checkout():
    lines = [{"unit_price_cents": 3000, "quantity": 1, "fulfillment": "physical"}]
    dest = _dest(STANDARD, PICKUP)
    out = cart.cart_totals(lines, HOME, dest, load=ShipLoad(units=1), rate_id=str(PICKUP["id"]))
    assert out["shipping_cents"] == 0 and out["shipping_option"]["method"] == "pickup"
    assert out["total_cents"] == 3000 + 300
    nothing_fits = _dest(LOCAL)
    quote = cart.cart_totals(lines, HOME, nothing_fits, load=ShipLoad(units=1, postal_code="10001"))
    assert quote["shipping_options"] == [] and quote["shipping_cents"] == 0
    with pytest.raises(HTTPException) as exc:
        cart.cart_totals(lines, HOME, nothing_fits, load=ShipLoad(units=1, postal_code="10001"), strict=True)
    assert exc.value.status_code == 422 and "delivery options fits" in exc.value.detail


def test_rates_are_read_only_with_the_plan_feature():
    rows = [STANDARD, rate_row("Express CA", zone_id=uuid4())]
    conn = SimpleNamespace(fetch=AsyncMock(return_value=rows))
    assert asyncio.run(shipping.load_rates(conn, SITE, ZONES_OFF)) == {}
    conn.fetch.assert_not_awaited()
    out = asyncio.run(shipping.load_rates(conn, SITE, ZONES_ON))
    assert [r.name for r in out[None]] == ["Standard"]
    assert [r.name for r in out[str(rows[1]["zone_id"])]] == ["Express CA"]
    assert "ORDER BY sort_order" in conn.fetch.await_args.args[0]


def test_options_that_cant_be_priced_are_refused():
    ok = CappeShippingRateInput(name="Standard")
    with pytest.raises(HTTPException) as exc:
        shipping.validate_rates([ok] * 11, where="Home")
    assert exc.value.status_code == 422 and "at most 10" in exc.value.detail
    for field in (("min_subtotal_cents", "max_subtotal_cents"), ("min_weight_g", "max_weight_g"),
                  ("delivery_min_days", "delivery_max_days")):
        bad = CappeShippingRateInput(name="Odd", **{field[0]: 9, field[1]: 2})
        with pytest.raises(HTTPException):
            shipping.validate_rates([bad], where="Home")
    shipping.validate_rates([ok, CappeShippingRateInput(name="Band", min_weight_g=1, max_weight_g=1)], where="Home")


# ── what the owner types ─────────────────────────────────────────────────────

def test_the_rate_model_cleans_by_method():
    local = CappeShippingRateInput(name=" Local ", method="local_delivery", postal_codes=["941 1", "941 1", " ", "sw1a"],
                                   instructions="ignored")
    assert local.name == "Local" and local.postal_codes == ["9411", "SW1A"] and local.instructions is None
    pickup = CappeShippingRateInput(name="Pickup", method="pickup", per_item_cents=500, postal_codes=["941"],
                                    instructions="  back door ")
    assert pickup.per_item_cents == 0 and pickup.postal_codes == [] and pickup.instructions == "back door"
    for bad in ({"name": "  "}, {"name": "x", "method": "drone"}, {"name": "x", "postal_codes": ["9!1"]},
                {"name": "x", "amount_cents": -1}, {"name": "x", "delivery_max_days": 91}):
        with pytest.raises(ValidationError):
            CappeShippingRateInput(**bad)


def test_products_and_the_store_take_their_shipping_fields():
    created = CappeProductCreate(name="Tiles", weight_g=25000, shipping_surcharge_cents=1500)
    assert (created.weight_g, created.shipping_surcharge_cents, created.ships_free) == (25000, 1500, False)
    assert CappeProductUpdate(weight_g=None).model_fields_set == {"weight_g"}
    with pytest.raises(ValidationError):
        CappeProductCreate(name="x", weight_g=-1)
    assert CappeSiteUpdate(handling_days_min=1, handling_days_max=3).handling_days_max == 3
    with pytest.raises(ValidationError):
        CappeSiteUpdate(handling_days_min=61)


def test_the_owner_routes_write_the_new_columns():
    create = inspect.getsource(shop_routes.create_product)
    assert "weight_g, shipping_surcharge_cents, ships_free)" in create and "body.ships_free" in create
    assert '"weight_g", "shipping_surcharge_cents", "ships_free"' in inspect.getsource(shop_routes.update_product)
    for col in ("weight_g", "shipping_surcharge_cents", "ships_free"):
        assert col in shop_routes._PRODUCT_COLS
    for col in ("shipping_method", "shipping_rate_label", "delivery_min_days", "shipping_instructions"):
        assert col in shop_routes._ORDER_COLS
    assert "handling_days_min, handling_days_max" in site_routes._SITE_COLS
    assert 'for key in ("handling_days_min", "handling_days_max")' in inspect.getsource(site_routes)


# ── the settings route ───────────────────────────────────────────────────────

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


class ZonesConn:
    """The zones route's queries: saved rates (with their zone's name), the
    zone set, and the inserts, recorded."""

    def __init__(self, old_rates=(), zones=()):
        self.old_rates, self.zones, self.calls, self.zone_ids = list(old_rates), list(zones), [], []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        if "z.name AS zone_name" in sql:
            return self.old_rates
        if "FROM cappe_shipping_rates" in sql:
            return [r for r in self.old_rates]
        if "FROM cappe_shipping_zones" in sql:
            return self.zones
        return []

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        zone_id = uuid4()
        self.zone_ids.append(zone_id)
        return zone_id

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))

    def transaction(self):
        return Tx()

    def sql(self, needle):
        return [c for c in self.calls if needle in c[1]]


def _wire_zones(monkeypatch, ent, conn):
    account = SimpleNamespace(id=uuid4(), plan="business")
    monkeypatch.setattr(zones_routes, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(zones_routes, "get_owned_site", AsyncMock(return_value={"id": SITE, **HOME}))
    monkeypatch.setattr(zones_routes, "resolve_entitlements", AsyncMock(return_value=ent))
    return account


def test_options_are_saved_with_their_zone_and_home(monkeypatch):
    conn = ZonesConn()
    account = _wire_zones(monkeypatch, ZONES_ON, conn)
    body = CappeShippingZonesReplace(
        zones=[{"name": "Canada", "countries": ["CA"], "flat_cents": 1500,
                "rates": [{"name": "Tracked", "amount_cents": 2000, "delivery_min_days": 5}]}],
        home_rates=[{"name": "Pickup", "method": "pickup", "instructions": "Shop"},
                    {"name": "Local", "method": "local_delivery", "postal_codes": ["94110"], "amount_cents": 700}],
    )
    asyncio.run(zones_routes.replace_shipping_zones(SITE, body, account))
    assert conn.sql("DELETE FROM cappe_shipping_rates") and conn.sql("DELETE FROM cappe_shipping_zones")
    inserts = [c[2] for c in conn.sql("INSERT INTO cappe_shipping_rates")]
    # (zone, name, method, amount, postal codes, instructions, sort order)
    assert [(a[1], a[2], a[3], a[4], a[13], a[14], a[15]) for a in inserts] == [
        (conn.zone_ids[0], "Tracked", "ship", 2000, [], None, 0),
        (None, "Pickup", "pickup", 0, [], "Shop", 0),
        (None, "Local", "local_delivery", 700, ["94110"], None, 1),
    ]


def test_a_save_that_leaves_options_out_keeps_them(monkeypatch):
    old_zone = uuid4()
    conn = ZonesConn(old_rates=[
        {**PICKUP, "zone_name": None},
        {**rate_row("Tracked", zone_id=old_zone, amount_cents=2000), "zone_name": "Canada"},
        {**rate_row("Gone", zone_id=uuid4()), "zone_name": "Removed zone"},
    ])
    account = _wire_zones(monkeypatch, ZONES_ON, conn)
    body = CappeShippingZonesReplace(zones=[{"name": "Canada", "countries": ["CA"]}, {"name": "EU", "countries": ["FR"]}])
    asyncio.run(zones_routes.replace_shipping_zones(SITE, body, account))
    inserts = [(c[2][1], c[2][2]) for c in conn.sql("INSERT INTO cappe_shipping_rates")]
    # The Canada zone's option follows it to its new id; home keeps its own.
    assert inserts == [(conn.zone_ids[0], "Tracked"), (None, "Pickup")]


def test_options_need_the_plan_but_clearing_them_does_not(monkeypatch):
    conn = ZonesConn()
    account = _wire_zones(monkeypatch, ZONES_OFF, conn)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(zones_routes.replace_shipping_zones(
            SITE, CappeShippingZonesReplace(home_rates=[{"name": "Pickup", "method": "pickup"}]), account))
    assert exc.value.status_code == 402 and not conn.sql("DELETE")
    asyncio.run(zones_routes.replace_shipping_zones(SITE, CappeShippingZonesReplace(home_rates=[]), account))
    assert conn.sql("DELETE FROM cappe_shipping_rates") and not conn.sql("INSERT")


def test_bad_options_are_refused_before_anything_is_deleted(monkeypatch):
    conn = ZonesConn()
    account = _wire_zones(monkeypatch, ZONES_ON, conn)
    body = CappeShippingZonesReplace(home_rates=[{"name": "Odd", "min_weight_g": 5, "max_weight_g": 1}])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(zones_routes.replace_shipping_zones(SITE, body, account))
    assert exc.value.status_code == 422 and not conn.sql("DELETE")


def test_the_owner_sees_each_destinations_options(monkeypatch):
    zone = {"id": uuid4(), "name": "Canada", "countries": ["CA"], "rest_of_world": False,
            "flat_cents": 1500, "free_threshold_cents": None, "charge_tax": False, "sort_order": 0}
    express = rate_row("Express", zone_id=zone["id"])
    conn = ZonesConn(old_rates=[PICKUP, express], zones=[zone])
    account = _wire_zones(monkeypatch, ZONES_OFF, conn)
    out = asyncio.run(zones_routes.get_shipping_zones(SITE, account))
    assert [r["name"] for r in out["home_rates"]] == ["Pickup"]
    assert [r["name"] for r in out["zones"][0]["rates"]] == ["Express"]
    assert out["enabled"] is False  # shown paused, not hidden


# ── the bag's quote ──────────────────────────────────────────────────────────

class QuoteConn:
    def __init__(self, product, rates):
        self.product, self.rates = product, rates

    async def fetchrow(self, sql, *args):
        return {**HOME} if "FROM cappe_sites WHERE id=$1" in sql else None

    async def fetchval(self, sql, *args):
        if "stripe_charges_enabled" in sql:
            return True
        if "SELECT NOW()" in sql:
            return NOW
        return "business"

    async def fetch(self, sql, *args):
        if "FROM cappe_products" in sql:
            return [self.product]
        if "FROM cappe_shipping_rates" in sql:
            return self.rates
        return []


def _wire_quote(monkeypatch, rates, *, ent=ZONES_ON, **product_kw):
    product = {"id": uuid4(), "site_id": SITE, "name": "Mug", "price_cents": 2000, "currency": "USD",
               "inventory": None, "status": "active", "fulfillment": "physical", "weight_g": 400,
               "ships_free": False, "shipping_surcharge_cents": 0, "subscription_intervals": [],
               "subscription_discount_bps": 0, "requires_approval": False, **product_kw}
    monkeypatch.setattr(public_shop, "get_connection", lambda: Ctx(QuoteConn(product, rates)))
    monkeypatch.setattr(public_shop, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_shop, "_published_site", AsyncMock(return_value={"id": SITE, "timezone": "UTC"}))
    monkeypatch.setattr(public_shop, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(public_shop, "fetch_variants", AsyncMock(return_value={}))
    monkeypatch.setattr(public_shop, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(public_shop, "resolve_entitlements", AsyncMock(return_value=ent))
    return product


def _quote(product, quantity=1, **kw):
    return asyncio.run(public_shop.quote(
        "shop", CartQuoteRequest(items=[{"product_id": str(product["id"]), "quantity": quantity}], **kw), request=None))


def test_the_quote_offers_the_options_and_prices_the_default(monkeypatch):
    product = _wire_quote(monkeypatch, [STANDARD, PICKUP])
    out = _quote(product, quantity=2)
    assert [o["label"] for o in out["shipping_options"]] == ["Standard", "Pickup"]
    assert out["shipping_option"]["label"] == "Standard" and out["shipping_cents"] == 600
    assert out["asks_postal_code"] is False
    assert out["shipping_option"]["delivery_min_days"] == 4  # handling 1 + transit 3


def test_the_quote_prices_the_option_asked_for(monkeypatch):
    product = _wire_quote(monkeypatch, [STANDARD, PICKUP])
    out = _quote(product, shipping_rate_id=str(PICKUP["id"]))
    assert out["shipping_option"]["method"] == "pickup" and out["shipping_cents"] == 0


def test_the_quote_asks_for_a_postal_code_for_local_delivery(monkeypatch):
    product = _wire_quote(monkeypatch, [LOCAL])
    out = _quote(product)
    assert out["asks_postal_code"] is True and out["shipping_options"] == []
    assert _quote(product, postal_code="10001")["shipping_options"] == []  # outside the area
    out = _quote(product, postal_code="94110")
    assert out["shipping_option"]["label"] == "Local" and out["shipping_cents"] == 700


def test_a_product_that_ships_free_adds_nothing(monkeypatch):
    product = _wire_quote(monkeypatch, [STANDARD], ships_free=True)
    assert _quote(product, quantity=3)["shipping_cents"] == 0


def test_a_plan_without_zones_quotes_the_flat_rate(monkeypatch):
    product = _wire_quote(monkeypatch, [STANDARD, PICKUP], ent=ZONES_OFF)
    out = _quote(product)
    assert [o["id"] for o in out["shipping_options"]] == ["flat"] and out["shipping_cents"] == 600


# ── an order keeps the option it was priced with ─────────────────────────────

class OrderConn:
    def __init__(self, product, rates):
        self.product, self.rates, self.order, self.insert_args = product, list(rates), None, None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return self

    async def fetch(self, sql, *args):
        return self.rates if "FROM cappe_shipping_rates" in sql else []

    async def fetchrow(self, sql, *args):
        if "FROM cappe_products" in sql:
            return self.product
        if "FROM cappe_sites" in sql:
            return {**HOME, "tax_label": None}
        if "INSERT INTO cappe_orders" in sql:
            self.insert_args = args
            self.order = {"id": ORDER, "status": "pending", "access_token": TOKEN, "subtotal_cents": args[3],
                          "tax_cents": args[4], "shipping_cents": args[5], "total_cents": args[6],
                          "currency": args[7], "requires_approval": args[9], "shipping_address": args[10],
                          "ship_country": args[11], "shipping_method": args[16], "shipping_rate_label": args[17],
                          "delivery_min_days": args[18], "delivery_max_days": args[19]}
            return self.order
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        if sql == "SELECT NOW()":
            return NOW
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        pass


def _wire_order(monkeypatch, rates, *, cards=True, quantity=1, **body_kw):
    product = {"id": uuid4(), "name": "Mug", "price_cents": 2000, "currency": "USD", "inventory": None,
               "low_stock_threshold": None, "status": "active", "fulfillment": "physical",
               "booking_type_id": None, "requires_approval": False, "intake_fields": "[]", "sku": None,
               "weight_g": 400, "ships_free": False, "shipping_surcharge_cents": 100}
    conn = OrderConn(product, rates)
    owner = {"plan": "business", "status": "active", "email": "owner@example.com", "name": "Owner",
             "stripe_account_id": "acct_1" if cards else None, "stripe_charges_enabled": cards}
    stripe = SimpleNamespace(create_checkout_session=AsyncMock(return_value={"id": "cs_1", "url": "https://pay"}))
    monkeypatch.setattr(commerce, "get_connection", lambda: conn)
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(commerce, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(commerce, "fetch_variants", AsyncMock(return_value={}))
    monkeypatch.setattr(commerce, "lock_stock_rows", AsyncMock())
    monkeypatch.setattr(commerce, "fetch_site_owner", AsyncMock(return_value=owner))
    monkeypatch.setattr(commerce, "resolve_entitlements", AsyncMock(return_value=ZONES_ON))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    monkeypatch.setattr(commerce, "check_recipient_send_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(commerce, "get_cappe_stripe", lambda: stripe)
    site = {"id": SITE, "name": "Store", "timezone": "UTC", "subdomain": "shop", "custom_domain": "shop.example.com"}
    body = CappeCheckoutRequest(
        customer_email="buyer@example.com", items=[CappeCartItem(product_id=product["id"], quantity=quantity)],
        success_url="https://shop.example.com/", cancel_url="https://shop.example.com/", **body_kw,
    )
    return site, body, conn, stripe


def _place(site, body):
    return asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))


def test_a_shipped_order_keeps_its_option_and_stripe_shows_the_estimate(monkeypatch):
    site, body, conn, stripe = _wire_order(monkeypatch, [STANDARD, PICKUP], quantity=2)
    _place(site, body)
    # 500 + 100 for the second item + the product's 100 surcharge on each.
    assert conn.order["shipping_cents"] == 800
    assert conn.insert_args[15:21] == (str(STANDARD["id"]), "ship", "Standard", 4, 7, None)
    kw = stripe.create_checkout_session.await_args.kwargs
    assert kw["collect_shipping_address"] is True and kw["ship_countries"] == ["US"]
    assert kw["shipping_option"] == {"label": "Standard", "amount_cents": 800,
                                     "delivery_min_days": 4, "delivery_max_days": 7}


def test_a_pickup_needs_no_address_and_stripe_asks_for_none(monkeypatch):
    site, body, conn, stripe = _wire_order(
        monkeypatch, [STANDARD, rate_row("Pickup", "pickup", amount_cents=150, instructions="Back door")],
        cards=False, shipping_address={"line1": "1 Main", "city": "Oakland"},
    )
    pickup_id = str(conn.rates[1]["id"])  # the default is shipped; pick the pickup
    body.shipping_rate_id = pickup_id
    _place(site, body)
    assert conn.order["shipping_address"] is None  # nothing is sent anywhere
    assert conn.order["shipping_cents"] == 150
    assert conn.insert_args[15:21] == (pickup_id, "pickup", "Pickup", 1, 2, "Back door")


def test_a_card_pickup_charges_its_fee_as_a_line(monkeypatch):
    pickup = rate_row("Pickup", "pickup", amount_cents=150)
    site, body, conn, stripe = _wire_order(monkeypatch, [pickup], shipping_rate_id=str(pickup["id"]))
    _place(site, body)
    kw = stripe.create_checkout_session.await_args.kwargs
    assert kw["collect_shipping_address"] is False and kw["shipping_option"] is None and kw["ship_countries"] is None
    assert ("Pickup", 150) in [(li["price_data"]["product_data"]["name"], li["price_data"]["unit_amount"])
                               for li in kw["line_items"]]


def test_local_delivery_needs_an_address_in_its_area(monkeypatch):
    site, body, conn, _stripe = _wire_order(monkeypatch, [LOCAL], shipping_rate_id=str(LOCAL["id"]))
    with pytest.raises(HTTPException) as exc:
        _place(site, body)  # no address: the area can't be checked, so it isn't offered
    assert exc.value.status_code == 409 and conn.order is None
    site, body, conn, stripe = _wire_order(
        monkeypatch, [LOCAL], shipping_rate_id=str(LOCAL["id"]),
        shipping_address={"line1": "1 Valencia", "city": "San Francisco", "postal_code": "94110"},
    )
    _place(site, body)
    assert conn.order["shipping_cents"] == 800 and json.loads(conn.order["shipping_address"])["address"]["postal_code"] == "94110"
    kw = stripe.create_checkout_session.await_args.kwargs
    assert kw["collect_shipping_address"] is False  # the typed address is the one priced


def test_local_delivery_is_never_the_default_without_an_address(monkeypatch):
    # An app that predates delivery options sends no option and (paying by
    # card) no address: it gets the next option, as its quote showed.
    anywhere = rate_row("Local", "local_delivery", amount_cents=700)
    site, body, conn, stripe = _wire_order(monkeypatch, [anywhere, STANDARD])
    _place(site, body)
    assert conn.insert_args[16:18] == ("ship", "Standard")
    assert stripe.create_checkout_session.await_args.kwargs["collect_shipping_address"] is True
    site, body, conn, _stripe = _wire_order(monkeypatch, [anywhere])
    with pytest.raises(HTTPException) as exc:
        _place(site, body)
    assert exc.value.status_code == 422 and "delivery options fits" in exc.value.detail


def test_an_option_the_order_no_longer_gets_is_refused(monkeypatch):
    site, body, conn, _stripe = _wire_order(monkeypatch, [STANDARD], shipping_rate_id=str(uuid4()))
    with pytest.raises(HTTPException) as exc:
        _place(site, body)
    assert exc.value.status_code == 409 and conn.order is None


def test_an_order_with_no_options_keeps_the_flat_rate_and_no_rate_id(monkeypatch):
    site, body, conn, _stripe = _wire_order(monkeypatch, [])
    _place(site, body)
    assert conn.order["shipping_cents"] == 700  # 600 flat + the product's 100 surcharge
    assert conn.insert_args[15:18] == (None, "ship", "Shipping")


def test_pay_now_uses_the_orders_own_option():
    src = inspect.getsource(commerce.pay_for_order)
    assert "o.shipping_method, o.shipping_rate_label, o.delivery_min_days, o.delivery_max_days" in src


def test_stripe_gets_a_delivery_estimate_only_when_there_is_one():
    [opt] = stripe_connect.build_shipping_options(
        {"label": "Express", "amount_cents": 1500, "delivery_min_days": 2, "delivery_max_days": 3}, "USD")
    assert opt["shipping_rate_data"]["delivery_estimate"] == {
        "minimum": {"unit": "business_day", "value": 2}, "maximum": {"unit": "business_day", "value": 3}}
    [plain] = stripe_connect.build_shipping_options({"label": "Shipping", "amount_cents": 0, "delivery_min_days": 0}, "USD")
    assert "delivery_estimate" not in plain["shipping_rate_data"]


def test_shipping_rides_the_line_items_only_when_asked():
    rows = [(uuid4(), "Mug", 2000, 1, "physical")]
    assert len(build_stripe_line_items(rows, "usd", 0, "Tax")) == 1
    assert len(build_stripe_line_items(rows, "usd", 0, "Tax", shipping=("Local", 0))) == 1
    items = build_stripe_line_items(rows, "usd", 200, "Tax", shipping=("Local", 700))
    assert [(i["price_data"]["product_data"]["name"], i["price_data"]["unit_amount"]) for i in items] == [
        ("Mug", 2000), ("Tax", 200), ("Local", 700)]


# ── the order page ───────────────────────────────────────────────────────────

def test_the_order_page_says_where_to_collect_and_when():
    pickup = {"status": "paid", "shipping_method": "pickup", "shipping_instructions": "12 Market St <9–5>",
              "delivery_min_days": 1, "delivery_max_days": 1,
              "shipping_address": {"address": {"line1": "never shown"}}}
    html = _shipping_html(pickup)
    assert "Pickup" in html and "12 Market St &lt;9–5&gt;" in html and "never shown" not in html
    assert "Ready for pickup in 1 business day" in html
    shipped = {"status": "paid", "shipping_method": "ship", "delivery_min_days": 3, "delivery_max_days": 5,
               "shipping_address": {"name": "Ann", "address": {"line1": "1 Main", "country": "US"}}}
    assert "Arrives in 3–5 business days" in _shipping_html(shipped) and "1 Main" in _shipping_html(shipped)
    assert "Arrives" not in _shipping_html({**shipped, "status": "fulfilled"})
    assert delivery_estimate({"delivery_max_days": 2}) == "Arrives in 2 business days"
    assert delivery_estimate({}) is None


def test_the_order_page_and_receipt_name_the_option_the_buyer_chose():
    from app.cappe.routes import render
    from app.cappe.services import receipt
    for src in (inspect.getsource(render), inspect.getsource(receipt.render_order_receipt_pdf)):
        assert "COALESCE(o.shipping_rate_label, s.shipping_label) AS shipping_label" in src


# ── the migration and the bag ────────────────────────────────────────────────

def test_the_migration_chains_and_adds_everything_it_says():
    src = MIGRATION.read_text()
    assert 'revision = "zzzzcappe52"' in src and 'down_revision = "zzzzcappe51"' in src
    assert "CREATE TABLE IF NOT EXISTS cappe_shipping_rates" in src
    assert "zone_id UUID REFERENCES cappe_shipping_zones(id) ON DELETE CASCADE" in src
    assert "CHECK (method IN ('ship', 'pickup', 'local_delivery'))" in src
    for col in ("weight_g", "shipping_surcharge_cents", "ships_free", "handling_days_min", "handling_days_max",
                "shipping_rate_id", "shipping_method", "shipping_rate_label", "delivery_min_days",
                "shipping_instructions"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src and f"DROP COLUMN IF EXISTS {col}" in src
    assert "DROP TABLE IF EXISTS cappe_shipping_rates" in src


def test_the_bag_offers_the_options_and_sends_the_one_it_priced():
    js = (ASSETS / "cart.js").read_text()
    assert "req.shipping_rate_id=rateId" in js and "req.postal_code=postal" in js
    assert "body.shipping_rate_id=chosen().id" in js
    assert "cz-cart-rate:" in js                                   # the choice survives a reload
    assert "method()==='pickup')return false" in js                # a pickup asks for no address
    assert "method()==='local_delivery'" in js                     # a local delivery always does
    assert "quote.asks_postal_code" in js
    assert "body.note=note.slice(0,1000)" in js                    # the note box finally sends
    assert ".cz-bag__rate{" in (ASSETS / "base.css").read_text()


def test_a_subscription_prices_shipping_by_the_same_load():
    from app.cappe.models.shop import CappeCartItem as Item
    from app.cappe.services import recurring
    pid, free_id = uuid4(), uuid4()
    product = {"id": pid, "name": "Coffee", "price_cents": 2000, "currency": "USD", "status": "active",
               "fulfillment": "physical", "inventory": None, "subscription_intervals": ["month"],
               "subscription_discount_bps": 0, "requires_approval": False, "option_groups": [], "variants": [],
               "discount_percent": 0, "shipping_surcharge_cents": 150}
    products = {pid: product, free_id: {**product, "id": free_id, "ships_free": True}}
    site = {"tax_rate_bps": 0, "shipping_flat_cents": 600, "shipping_free_threshold_cents": None}
    _lines, _snap, totals = recurring.build_subscription_lines(products, [Item(product_id=pid, quantity=1)], "month", site)
    assert totals["shipping_cents"] == 750
    _lines, _snap, totals = recurring.build_subscription_lines(products, [Item(product_id=free_id, quantity=2)], "month", site)
    assert totals["shipping_cents"] == 0
