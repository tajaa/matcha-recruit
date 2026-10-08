"""Stock and order integrity — the 2026-10 commerce readiness review, PR 1.

What each block pins:

  * the stock ledger endpoint answers at all (its response model demanded a
    column the table never had, so every product with history returned a 500);
  * a product edit cannot write a stale stock count over sales made since the
    form loaded, and a deliberate stock edit leaves a ledger row;
  * option ids survive a product save (orders, subscriptions and the ledger
    all point at them);
  * a restock credits only what the sale took;
  * stock rows are locked in one global order;
  * an abandoned payment page hands its stock back;
  * a location's discount stays at that location;
  * a refund of shipped goods does not invent stock.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_stock_integrity.py -q
"""
import asyncio
import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.cappe.models.shop import (  # noqa: E402
    CappeCartItem,
    CappeCheckoutRequest,
    CappeInventoryAdjustment,
    CappeProductOptionGroupInput,
    CappeProductOptionInput,
    CappeProductUpdate,
    CappeRefundRequest,
)
from app.cappe.routes import payments as payments_mod  # noqa: E402
from app.cappe.routes import render as render_mod  # noqa: E402
from app.cappe.routes import shop as shop_mod  # noqa: E402
from app.cappe.routes.public import shop as public_shop  # noqa: E402
from app.cappe.services import commerce  # noqa: E402
from app.cappe.services import inventory as inv_mod  # noqa: E402
from app.cappe.services.discounts import best_discount_percent  # noqa: E402
from app.cappe.services.options import match_prior_rows  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

SITE, PRODUCT, ORDER = uuid4(), uuid4(), uuid4()
ACCOUNT = SimpleNamespace(id=uuid4(), plan="business")


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

    async def fetch(self, sql, *args):
        return self._answer("fetch", sql, args) or []

    async def execute(self, sql, *args):
        self._answer("execute", sql, args)

    def transaction(self):
        return Tx()

    def sql(self, needle):
        return [c for c in self.calls if needle in c[1]]


def _ledger(monkeypatch, module, name="log_adjustment"):
    rows = []

    async def _log(_conn, **kw):
        rows.append(kw)

    monkeypatch.setattr(module, name, _log)
    return rows


def _set_clause(call):
    """The SET part of a recorded UPDATE (RETURNING lists every column)."""
    return call[1].split("WHERE")[0]


# ── the ledger endpoint ──────────────────────────────────────────────────────

def test_a_ledger_row_validates_with_exactly_the_columns_the_table_has():
    """`updated_at` was required by the model and absent from the table."""
    row = {
        "id": uuid4(), "product_id": PRODUCT, "option_id": None, "delta": -1,
        "balance_after": 4, "reason": "sale", "note": None,
        "created_at": datetime.now(timezone.utc),
    }
    assert CappeInventoryAdjustment(**row).balance_after == 4
    assert "updated_at" not in CappeInventoryAdjustment.model_fields


def test_the_ledger_route_selects_only_real_columns(monkeypatch):
    row = {
        "id": uuid4(), "product_id": PRODUCT, "option_id": None, "delta": 3,
        "balance_after": 7, "reason": "restock", "note": "delivery",
        "created_at": datetime.now(timezone.utc),
    }
    conn = SqlConn([("FROM cappe_inventory_adjustments", [row])])
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", AsyncMock())
    out = asyncio.run(shop_mod.inventory_log(SITE, PRODUCT, account=ACCOUNT))
    assert [CappeInventoryAdjustment(**r).delta for r in out] == [3]
    assert "updated_at" not in conn.calls[0][1]


# ── option ids survive a save ────────────────────────────────────────────────

def _opt(name, **kw):
    return CappeProductOptionInput(name=name, **kw)


def test_ids_are_matched_before_names_and_each_stored_row_is_claimed_once():
    a, b, c = ({"id": uuid4(), "name": n} for n in ("Small", "Small", "Large"))
    incoming = [_opt("Small"), _opt("Renamed", id=a["id"]), _opt("XL")]
    paired, gone = match_prior_rows([a, b, c], incoming)
    # The id wins `a` even though an earlier incoming row shares its old name;
    # that row then takes the other "Small"; "XL" is new; "Large" is dropped.
    assert paired == [b, a, None]
    assert gone == [c]


def test_a_stale_id_falls_back_to_the_name():
    stored = {"id": uuid4(), "name": "Oat"}
    paired, gone = match_prior_rows([stored], [_opt("Oat", id=uuid4())])
    assert paired == [stored] and gone == []


def _groups_conn(group_id, options):
    return SqlConn([
        ("FROM cappe_product_option_groups", [{"id": group_id, "name": "Size"}]),
        ("FROM cappe_product_options o", options),
        ("INSERT INTO cappe_product_options", lambda _s, _a: uuid4()),
        ("INSERT INTO cappe_product_option_groups", lambda _s, _a: uuid4()),
    ])


def test_saving_a_product_keeps_its_option_ids(monkeypatch):
    """The old code deleted every group and re-inserted the set."""
    ledger = _ledger(monkeypatch, shop_mod)
    gid, small, large = uuid4(), uuid4(), uuid4()
    conn = _groups_conn(gid, [
        {"id": small, "group_id": gid, "name": "Small", "inventory": 5},
        {"id": large, "group_id": gid, "name": "Large", "inventory": 2},
    ])
    groups = [CappeProductOptionGroupInput(id=gid, name="Size", options=[
        _opt("Small", id=small), _opt("Medium", inventory=4),
    ])]
    asyncio.run(shop_mod._replace_option_groups(conn, SITE, PRODUCT, groups))

    assert not conn.sql("INSERT INTO cappe_product_option_groups")       # group kept
    assert not conn.sql("DELETE FROM cappe_product_option_groups")
    updated = conn.sql("UPDATE cappe_product_options SET")
    assert [c[2][-1] for c in updated] == [small]                        # same row, same id
    # Stock was not sent for "Small", so the UPDATE does not touch it.
    assert "inventory" not in updated[0][1]
    assert len(conn.sql("INSERT INTO cappe_product_options")) == 1       # Medium
    assert conn.sql("DELETE FROM cappe_product_options")[0][2] == ([large], SITE)
    assert [(e["delta"], e["note"]) for e in ledger] == [(4, "Opening stock")]
    # Stock rows are read under a lock, in id order.
    assert "ORDER BY o.id FOR UPDATE OF o" in conn.sql("FROM cappe_product_options o")[0][1]


def test_option_stock_is_tri_state_and_a_change_is_logged(monkeypatch):
    ledger = _ledger(monkeypatch, shop_mod)
    gid, a, b = uuid4(), uuid4(), uuid4()
    conn = _groups_conn(gid, [
        {"id": a, "group_id": gid, "name": "Red", "inventory": 5},
        {"id": b, "group_id": gid, "name": "Blue", "inventory": 3},
    ])
    groups = [CappeProductOptionGroupInput(id=gid, name="Size", options=[
        _opt("Red", id=a, inventory=9),      # a number sets it
        _opt("Blue", id=b, inventory=None),  # an explicit null stops tracking
    ])]
    asyncio.run(shop_mod._replace_option_groups(conn, SITE, PRODUCT, groups))
    red, blue = conn.sql("UPDATE cappe_product_options SET")
    assert "inventory = $4" in red[1] and red[2][3] == 9
    assert "inventory = $4" in blue[1] and blue[2][3] is None
    assert [(e["option_id"], e["delta"], e["balance_after"]) for e in ledger] == [(a, 4, 9)]


def test_a_stale_option_stock_edit_is_refused(monkeypatch):
    _ledger(monkeypatch, shop_mod)
    gid, a = uuid4(), uuid4()
    conn = _groups_conn(gid, [{"id": a, "group_id": gid, "name": "Red", "inventory": 2}])
    groups = [CappeProductOptionGroupInput(id=gid, name="Size", options=[
        _opt("Red", id=a, inventory=10, expected_inventory=5),   # the form showed 5; 3 sold since
    ])]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(shop_mod._replace_option_groups(conn, SITE, PRODUCT, groups))
    assert exc.value.status_code == 409 and "is now 2" in exc.value.detail
    assert not conn.sql("UPDATE cappe_product_options SET")


def test_position_is_the_order_unless_the_caller_pins_one(monkeypatch):
    _ledger(monkeypatch, shop_mod)
    conn = SqlConn([("INSERT INTO cappe_product_option_groups", lambda _s, _a: uuid4())])
    groups = [
        CappeProductOptionGroupInput(name="Size"),
        CappeProductOptionGroupInput(name="Milk", sort_order=7),
        CappeProductOptionGroupInput(name="Extras"),
    ]
    asyncio.run(shop_mod._replace_option_groups(conn, SITE, PRODUCT, groups))
    assert [c[2][5] for c in conn.sql("INSERT INTO cappe_product_option_groups")] == [0, 7, 2]


def test_none_leaves_option_groups_alone():
    conn = SqlConn()
    asyncio.run(shop_mod._replace_option_groups(conn, SITE, PRODUCT, None))
    assert conn.calls == []


# ── product edits and stock ──────────────────────────────────────────────────

def _existing(**kw):
    return {
        "id": PRODUCT, "site_id": SITE, "name": "Mug", "fulfillment": "physical",
        "requires_approval": False, "inventory": 7,
        "subscription_intervals": ["month"], "subscription_discount_bps": 500, **kw,
    }


def _wire_update(monkeypatch, *, shelf):
    conn = SqlConn([
        ("SELECT * FROM cappe_products", _existing()),
        ("SELECT inventory FROM cappe_products", None if shelf is ... else {"inventory": shelf}),
        ("UPDATE cappe_products SET", {"id": PRODUCT}),
        ("SELECT subscription_intervals", {"id": PRODUCT}),
    ])
    validated = AsyncMock()
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", AsyncMock())
    monkeypatch.setattr("app.cappe.services.recurring.validate_product_subscription", validated)
    monkeypatch.setattr(shop_mod, "_replace_option_groups", AsyncMock())
    monkeypatch.setattr(shop_mod, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(shop_mod, "refresh_site_search", AsyncMock())
    monkeypatch.setattr(shop_mod, "_product_row", lambda row, groups=None: dict(row))
    return conn, validated, _ledger(monkeypatch, shop_mod)


def _update(body):
    return asyncio.run(shop_mod.update_product(SITE, PRODUCT, body, account=ACCOUNT))


def test_an_edit_that_is_not_about_stock_does_not_write_stock(monkeypatch):
    """The form used to send the stock it loaded with every save."""
    conn, _validated, ledger = _wire_update(monkeypatch, shelf=4)
    _update(CappeProductUpdate(name="Mug (blue)"))
    assert "inventory" not in _set_clause(conn.sql("UPDATE cappe_products SET")[0]) and ledger == []
    # The shelf is still read under the row lock before anything is written.
    assert "FOR UPDATE" in conn.sql("SELECT inventory FROM cappe_products")[0][1]


def test_a_stock_edit_is_logged_with_its_delta(monkeypatch):
    conn, _validated, ledger = _wire_update(monkeypatch, shelf=4)
    _update(CappeProductUpdate(inventory=10, expected_inventory=4))
    assert "inventory = $1" in _set_clause(conn.sql("UPDATE cappe_products SET")[0])
    assert [(e["delta"], e["balance_after"], e["reason"]) for e in ledger] == [(6, 10, "adjustment")]
    # `expected_inventory` is a guard, never a column.
    assert "expected_inventory" not in conn.sql("UPDATE cappe_products SET")[0][1]


def test_starting_to_track_stock_logs_the_opening_balance(monkeypatch):
    _conn, _validated, ledger = _wire_update(monkeypatch, shelf=None)
    _update(CappeProductUpdate(inventory=12))
    assert [(e["delta"], e["balance_after"]) for e in ledger] == [(12, 12)]


def test_a_stale_stock_edit_is_refused_and_nothing_is_written(monkeypatch):
    """Form loaded at 10, three sold, owner types 12: writing 12 would invent
    three units. The save is refused and says what the shelf holds now."""
    conn, _validated, ledger = _wire_update(monkeypatch, shelf=7)
    with pytest.raises(HTTPException) as exc:
        _update(CappeProductUpdate(inventory=12, expected_inventory=10))
    assert exc.value.status_code == 409 and "is now 7" in exc.value.detail
    assert not conn.sql("UPDATE cappe_products SET") and ledger == []


def test_resending_the_current_stock_is_not_a_stock_edit(monkeypatch):
    conn, _validated, ledger = _wire_update(monkeypatch, shelf=7)
    _update(CappeProductUpdate(inventory=7, expected_inventory=3))   # stale guard, but no change
    assert ledger == []
    assert conn.sql("UPDATE cappe_products SET")


def test_a_product_that_vanished_mid_edit_is_a_404(monkeypatch):
    _wire_update(monkeypatch, shelf=...)
    with pytest.raises(HTTPException) as exc:
        _update(CappeProductUpdate(name="x"))
    assert exc.value.status_code == 404


@pytest.mark.parametrize("body,changed", [
    (CappeProductUpdate(subscription_intervals=["month"], subscription_discount_bps=500), False),
    (CappeProductUpdate(name="x"), False),
    (CappeProductUpdate(subscription_intervals=["week", "month"]), True),
    (CappeProductUpdate(subscription_discount_bps=1000), True),
    (CappeProductUpdate(subscription_intervals=[]), True),
])
def test_resending_unchanged_subscription_settings_is_not_a_change(monkeypatch, body, changed):
    """The editor sends them on every save; "present" used to mean "changed",
    so a plan without recurring orders got a 402 for fixing a typo."""
    _conn, validated, _ledger_rows = _wire_update(monkeypatch, shelf=7)
    _update(body)
    assert validated.await_args.kwargs["changed"] is changed


def test_creating_a_tracked_product_logs_its_opening_stock(monkeypatch):
    from app.cappe.models.shop import CappeProductCreate
    conn = SqlConn([("INSERT INTO cappe_products", {"id": PRODUCT})])
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", AsyncMock())
    monkeypatch.setattr(shop_mod, "require_fulfillment", lambda *_a: None)
    monkeypatch.setattr(shop_mod, "resolve_entitlements", AsyncMock())
    monkeypatch.setattr("app.cappe.services.recurring.validate_product_subscription", AsyncMock())
    monkeypatch.setattr(shop_mod, "_replace_option_groups", AsyncMock())
    monkeypatch.setattr(shop_mod, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(shop_mod, "refresh_site_search", AsyncMock())
    monkeypatch.setattr(shop_mod, "_product_row", lambda row, groups=None: dict(row))
    ledger = _ledger(monkeypatch, shop_mod)
    asyncio.run(shop_mod.create_product(SITE, CappeProductCreate(name="Mug", inventory=8), account=ACCOUNT))
    asyncio.run(shop_mod.create_product(SITE, CappeProductCreate(name="PDF", fulfillment="digital"), account=ACCOUNT))
    assert [(e["delta"], e["note"]) for e in ledger] == [(8, "Opening stock")]


# ── locks ────────────────────────────────────────────────────────────────────

def test_stock_rows_are_locked_products_first_each_in_id_order():
    conn = SqlConn()
    p = sorted((uuid4() for _ in range(3)), key=str)
    o = sorted((uuid4() for _ in range(2)), key=str)
    asyncio.run(inv_mod.lock_stock_rows(
        conn, site_id=SITE, product_ids=[p[2], p[0], None, p[1], p[0]], option_ids=[o[1], o[0]],
    ))
    (_, psql, pargs), (_, osql, oargs) = conn.calls
    assert "cappe_products" in psql and "ORDER BY id FOR UPDATE" in psql and pargs == (SITE, p)
    assert "cappe_product_options" in osql and "ORDER BY id FOR UPDATE" in osql and oargs == (SITE, o)


def test_nothing_to_lock_issues_no_query():
    conn = SqlConn()
    asyncio.run(inv_mod.lock_stock_rows(conn, site_id=SITE, product_ids=[None], option_ids=[]))
    assert conn.calls == []


# ── a restock credits only what the sale took ────────────────────────────────

class StockConn:
    def __init__(self, lines, balance=5):
        self.lines, self.balance = lines, balance
        self.updates, self.recorded = [], []

    async def fetch(self, sql, *args):
        return [] if "FOR UPDATE" in sql else self.lines

    async def fetchval(self, sql, *args):
        if "FROM cappe_promo_redemptions" in sql:
            return None                                  # no promo-code use on these orders
        self.updates.append((sql, args))
        return self.balance

    async def execute(self, sql, *args):
        self.recorded.append((sql, args))


def _line(**kw):
    return {"id": uuid4(), "product_id": PRODUCT, "quantity": 2, "selected_option_ids": [], **kw}


def _targets(conn):
    return [("option" if "cappe_product_options" in sql else "product", args[1]) for sql, args in conn.updates]


def test_restock_skips_a_product_that_was_not_tracked_when_it_sold(monkeypatch):
    """Sold untracked, switched to tracked, then cancelled: the shelf used to
    gain units it had never lost."""
    _ledger(monkeypatch, inv_mod)
    o1, o2 = uuid4(), uuid4()
    conn = StockConn([_line(
        selected_option_ids=[o1, o2], stock_decremented=False, decremented_option_ids=[o2],
    )])
    asyncio.run(inv_mod.restock_order(conn, site_id=SITE, order_id=ORDER, reason="restock"))
    assert _targets(conn) == [("option", o2)]


def test_restock_credits_what_a_recorded_sale_took(monkeypatch):
    ledger = _ledger(monkeypatch, inv_mod)
    o1 = uuid4()
    conn = StockConn([_line(stock_decremented=True, decremented_option_ids=[o1])])
    asyncio.run(inv_mod.restock_order(conn, site_id=SITE, order_id=ORDER, reason="return"))
    assert _targets(conn) == [("product", PRODUCT), ("option", o1)]
    assert [(e["delta"], e["reason"]) for e in ledger] == [(2, "return"), (2, "return")]


def test_a_line_from_before_the_record_existed_restocks_as_it_always_did(monkeypatch):
    _ledger(monkeypatch, inv_mod)
    o1 = uuid4()
    conn = StockConn([_line(selected_option_ids=[o1], stock_decremented=None, decremented_option_ids=None)])
    asyncio.run(inv_mod.restock_order(conn, site_id=SITE, order_id=ORDER, reason="restock"))
    assert _targets(conn) == [("product", PRODUCT), ("option", o1)]


def test_retake_writes_down_what_it_took_when_the_line_had_no_record(monkeypatch):
    """A renewal order's lines are inserted, then their stock is taken here —
    the eventual refund has to be able to reverse exactly that."""
    _ledger(monkeypatch, inv_mod)
    o1 = uuid4()
    line = _line(selected_option_ids=[o1])
    conn = StockConn([line])
    asyncio.run(inv_mod.retake_order_stock(conn, site_id=SITE, order_id=ORDER))
    reset, (sql, args) = conn.recorded
    assert "stock_decremented = $2" in sql and args == (line["id"], True, [o1])
    # Every unit is out again, so none counts as back on the shelf.
    assert "restocked_quantity = 0" in reset[0] and reset[1] == (line["id"],)


def test_retake_of_a_recorded_line_takes_only_that_and_records_nothing_new(monkeypatch):
    _ledger(monkeypatch, inv_mod)
    o1, o2 = uuid4(), uuid4()
    conn = StockConn([_line(
        selected_option_ids=[o1, o2], stock_decremented=False, decremented_option_ids=[o1],
    )])
    asyncio.run(inv_mod.retake_order_stock(conn, site_id=SITE, order_id=ORDER))
    assert _targets(conn) == [("option", o1)]
    assert [sql for sql, _a in conn.recorded] == ["UPDATE cappe_order_items SET restocked_quantity = 0 WHERE id = $1"]


# ── checkout: the physical branch ────────────────────────────────────────────

@pytest.mark.parametrize("before,after,threshold,expected", [
    (6, 5, 5, True),      # crosses onto the threshold
    (8, 3, 5, True),      # jumps past it
    (5, 4, 5, False),     # already low — the owner has been told
    (9, 7, 5, False),
    (3, 1, None, False),  # no threshold set
])
def test_the_low_stock_alert_fires_only_on_crossing(before, after, threshold, expected):
    assert commerce.crossed_low_stock(before, after, threshold) is expected


class CheckoutConn:
    def __init__(self, product, option, *, balance):
        self.product, self.option, self.balance = product, option, balance
        self.locks, self.items, self.option_updates, self.order = [], [], [], None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return self

    async def fetch(self, sql, *args):
        assert "FOR UPDATE" in sql
        self.locks.append(("options" if "cappe_product_options" in sql else "products", args[1]))
        return []

    async def fetchrow(self, sql, *args):
        if "FROM cappe_product_options" in sql:
            return self.option
        if "FROM cappe_products" in sql:
            return self.product
        if "FROM cappe_sites" in sql:
            return {"tax_rate_bps": 0, "tax_label": None, "shipping_flat_cents": 0,
                    "shipping_free_threshold_cents": None, "shipping_label": None}
        if "INSERT INTO cappe_orders" in sql:
            self.order = {
                "id": uuid4(), "status": "pending", "access_token": uuid4().hex,
                "subtotal_cents": args[3], "tax_cents": args[4], "shipping_cents": args[5],
                "total_cents": args[6], "currency": args[7], "requires_approval": args[9],
            }
            return self.order
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        if sql == "SELECT NOW()":
            return datetime.now(timezone.utc)
        if "UPDATE cappe_products SET inventory = inventory - $1" in sql:
            assert "inventory >= $1" in sql          # the oversell guard
            return self.balance
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        if "INSERT INTO cappe_order_items" in sql:
            self.items.append(args)
        elif "UPDATE cappe_product_options SET inventory" in sql:
            self.option_updates.append(args)


def _wire_checkout(monkeypatch, *, tracked=True, balance=4, option_stock=6, threshold=5):
    site = {"id": SITE, "name": "Store", "timezone": "UTC", "custom_domain": "store.example.com"}
    option_id = uuid4()
    product = {
        "id": PRODUCT, "name": "Mug", "price_cents": 1500, "currency": "USD",
        "inventory": 5 if tracked else None, "low_stock_threshold": threshold,
        "status": "active", "fulfillment": "physical", "booking_type_id": None,
        "requires_approval": False, "intake_fields": "[]",
    }
    conn = CheckoutConn(product, {"name": "Blue", "inventory": option_stock}, balance=balance)
    groups = {PRODUCT: [{
        "id": uuid4(), "name": "Colour", "select_type": "single", "required": False,
        "options": [{"id": option_id, "name": "Blue", "price_delta_cents": 0, "inventory": option_stock}],
    }]}
    owner = {"plan": "business", "status": "active", "email": "owner@example.com", "name": "Owner",
             "stripe_account_id": None, "stripe_charges_enabled": False}
    ledger = _ledger(monkeypatch, commerce, "_inv_log")
    monkeypatch.setattr(commerce, "get_connection", lambda: conn)
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(commerce, "fetch_option_groups", AsyncMock(return_value=groups))
    monkeypatch.setattr(commerce, "fetch_site_owner", AsyncMock(return_value=owner))
    monkeypatch.setattr(commerce, "resolve_entitlements",
                        AsyncMock(return_value=SimpleNamespace(platform_fee_bps=200, has=lambda _f: False)))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    monkeypatch.setattr(commerce, "check_recipient_send_ok", AsyncMock(return_value=False))
    body = CappeCheckoutRequest(
        customer_email="buyer@example.com",
        items=[CappeCartItem(product_id=PRODUCT, quantity=1, selected_option_ids=[option_id])],
    )
    return site, body, conn, ledger, option_id


@pytest.mark.asyncio
async def test_a_physical_sale_locks_first_and_records_what_it_took(monkeypatch):
    site, body, conn, ledger, option_id = _wire_checkout(monkeypatch)
    background = BackgroundTasks()
    out = await commerce.create_public_order(site, body, background)

    assert out["status"] == "pending" and out["checkout_url"] is None
    # Every stock lock is taken up front: products, then options.
    assert conn.locks == [("products", [PRODUCT]), ("options", [option_id])]
    # The line remembers what came off the shelf.
    assert conn.items[0][-3:-1] == (True, [option_id])
    assert conn.option_updates == [(5, option_id)]
    assert [(e.get("option_id"), e["delta"], e["balance_after"]) for e in ledger] == [
        (None, -1, 4), (option_id, -1, 5),
    ]
    # 5 → 4 crosses the product's threshold of 5? No: 5 was already at it.
    # The variant goes 6 → 5 and does cross.
    alerts = [t for t in background.tasks if t.func.__name__ == "send_cappe_low_stock_email"]
    assert [list(t.args[3]) for t in alerts] == [[("Mug — Blue", 5)]]


@pytest.mark.asyncio
async def test_an_untracked_product_is_recorded_as_not_decremented(monkeypatch):
    site, body, conn, ledger, _option_id = _wire_checkout(monkeypatch, tracked=False, option_stock=None)
    await commerce.create_public_order(site, body, BackgroundTasks())
    assert conn.items[0][-3:-1] == (False, [])
    assert ledger == []


@pytest.mark.asyncio
async def test_the_last_unit_cannot_be_sold_twice(monkeypatch):
    site, body, conn, _ledger_rows, _option_id = _wire_checkout(monkeypatch, balance=None)
    with pytest.raises(HTTPException) as exc:
        await commerce.create_public_order(site, body, BackgroundTasks())
    assert exc.value.status_code == 409 and "Insufficient stock for Mug" in exc.value.detail
    assert conn.order is None


@pytest.mark.asyncio
async def test_a_variant_without_enough_stock_blocks_the_sale(monkeypatch):
    site, body, conn, _ledger_rows, _option_id = _wire_checkout(monkeypatch, option_stock=0)
    with pytest.raises(HTTPException) as exc:
        await commerce.create_public_order(site, body, BackgroundTasks())
    assert exc.value.status_code == 409 and "selected option" in exc.value.detail
    assert conn.order is None and conn.option_updates == []


# ── an abandoned payment page ────────────────────────────────────────────────

class FakeStripe:
    def __init__(self, state="expired", exc=None):
        self.state, self.exc, self.expired = state, exc, []

    async def expire_checkout_session(self, account_id, session_id):
        self.expired.append((account_id, session_id))
        if self.exc:
            raise self.exc
        return self.state


def _wire_release(monkeypatch, row, stripe):
    conn = SqlConn([("WHERE o.access_token = $1", row)])
    released = AsyncMock(return_value=True)
    monkeypatch.setattr(commerce, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(commerce, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(commerce, "release_unpaid_order", released)
    return released


PENDING = {"id": ORDER, "site_id": SITE, "status": "pending",
           "stripe_session_id": "cs_1", "stripe_account_id": "acct_1", "pay_by": None}


def test_an_abandoned_page_is_closed_before_its_order_is_released(monkeypatch):
    stripe = FakeStripe()
    released = _wire_release(monkeypatch, PENDING, stripe)
    assert asyncio.run(commerce.release_abandoned_checkout("tok")) == "released"
    assert stripe.expired == [("acct_1", "cs_1")]
    released.assert_awaited_once_with(ORDER, SITE)


def test_a_buyer_who_actually_paid_keeps_their_order(monkeypatch):
    released = _wire_release(monkeypatch, PENDING, FakeStripe(state="complete"))
    assert asyncio.run(commerce.release_abandoned_checkout("tok")) == "paid"
    released.assert_not_awaited()


@pytest.mark.parametrize("row", [
    None,
    {**PENDING, "status": "paid"},
    {**PENDING, "status": "cancelled"},
    {**PENDING, "stripe_session_id": None},     # a manual order belongs to the owner
    {**PENDING, "stripe_account_id": None},
])
def test_only_a_pending_order_on_an_open_page_is_released(monkeypatch, row):
    stripe = FakeStripe()
    released = _wire_release(monkeypatch, row, stripe)
    assert asyncio.run(commerce.release_abandoned_checkout("tok")) == "unchanged"
    assert stripe.expired == [] and not released.await_count


def test_an_approved_order_awaiting_payment_only_loses_its_page(monkeypatch):
    """The owner approved it; the buyer can come back and pay until pay_by."""
    stripe = FakeStripe()
    released = _wire_release(monkeypatch, {**PENDING, "pay_by": datetime.now(timezone.utc)}, stripe)
    assert asyncio.run(commerce.release_abandoned_checkout("tok")) == "unchanged"
    assert stripe.expired == [("acct_1", "cs_1")]
    released.assert_not_awaited()


def test_a_stripe_outage_leaves_the_order_exactly_as_it_was(monkeypatch):
    released = _wire_release(monkeypatch, PENDING, FakeStripe(exc=CappeStripeError("down")))
    with pytest.raises(CappeStripeError):
        asyncio.run(commerce.release_abandoned_checkout("tok"))
    released.assert_not_awaited()


def test_the_cancel_url_carries_the_token_on_our_handler_only():
    token = "ab" * 16
    url = commerce.checkout_cancel_url("https://store.example.com/shop?tab=new#mug", token)
    assert url.startswith("https://store.example.com/__cappe/checkout-return?")
    assert f"o={token}" in url and "next=%2Fshop%3Ftab%3Dnew%23mug" in url
    assert commerce.checkout_cancel_url("https://store.example.com", token).endswith("next=%2F")


@pytest.mark.parametrize("value,expected", [
    ("/shop?tab=new#mug", "/shop?tab=new#mug"),
    ("//evil.test/x", "/"),
    ("/\\evil.test", "/"),
    ("https://evil.test", "/"),
    ("", "/"),
    ("/a\nb", "/"),
])
def test_the_return_redirect_cannot_leave_the_site(value, expected):
    assert render_mod._local_path(value) == expected


def _return_request():
    return Request({"type": "http", "method": "GET", "path": "/__cappe/checkout-return",
                    "headers": [(b"host", b"store.example.com")]})


def _wire_return(monkeypatch, *, mine=1, site={"id": SITE}, release=None):
    conn = SqlConn([("FROM cappe_orders WHERE access_token", mine)])
    release = release or AsyncMock(return_value="released")
    monkeypatch.setattr(render_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(render_mod, "_resolve_published_site", AsyncMock(return_value=site))
    monkeypatch.setattr(render_mod, "release_abandoned_checkout", release)
    return release


def test_the_return_handler_releases_then_redirects_without_the_token(monkeypatch):
    token = "cd" * 16
    release = _wire_return(monkeypatch)
    response = asyncio.run(render_mod.checkout_return(_return_request(), o=token, next="/shop"))
    assert response.status_code == 302 and response.headers["location"] == "/shop"
    assert response.headers["referrer-policy"] == "no-referrer"
    release.assert_awaited_once_with(token)


def test_another_sites_token_releases_nothing_but_still_redirects(monkeypatch):
    release = _wire_return(monkeypatch, mine=None)
    response = asyncio.run(render_mod.checkout_return(_return_request(), o="cd" * 16, next="//evil.test"))
    assert response.headers["location"] == "/"
    release.assert_not_awaited()


def test_a_stripe_outage_does_not_strand_the_returning_buyer(monkeypatch):
    _wire_return(monkeypatch, release=AsyncMock(side_effect=CappeStripeError("down")))
    response = asyncio.run(render_mod.checkout_return(_return_request(), o="cd" * 16, next="/shop"))
    assert response.status_code == 302


@pytest.mark.parametrize("token", ["", "not-a-token", "AB" * 16])
def test_a_malformed_token_is_rejected(monkeypatch, token):
    _wire_return(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(render_mod.checkout_return(_return_request(), o=token))
    assert exc.value.status_code == 400


def test_an_unknown_host_is_a_404(monkeypatch):
    _wire_return(monkeypatch, site=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(render_mod.checkout_return(_return_request(), o="cd" * 16))
    assert exc.value.status_code == 404


# ── discounts stay where they were set ───────────────────────────────────────

TODAY = date(2026, 10, 6)
LOCATION, ELSEWHERE = str(uuid4()), str(uuid4())


def _discount(**kw):
    return {"percent_off": 10, "scope": "all", "target_id": None, "active": True,
            "starts_on": None, "ends_on": None, **kw}


def test_a_locations_discount_never_reaches_the_online_shop():
    discounts = [_discount(location_id=LOCATION, percent_off=25), _discount(percent_off=5)]
    assert best_discount_percent(discounts, kind="product", target_id="p", on_date=TODAY) == 5


@pytest.mark.parametrize("at,expected", [(LOCATION, 25), (ELSEWHERE, 5), (None, 5)])
def test_a_locations_discount_applies_to_bookings_at_that_location_only(at, expected):
    discounts = [_discount(location_id=LOCATION, percent_off=25), _discount(percent_off=5)]
    assert best_discount_percent(
        discounts, kind="booking_type", target_id="b", on_date=TODAY, location_id=at,
    ) == expected


# ── a quote does not describe a draft ────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_public_quote_reads_active_products_only(monkeypatch):
    from app.cappe.models.shopper import CartQuoteRequest
    conn = SqlConn([
        ("FROM cappe_sites WHERE id", {"tax_rate_bps": 0, "shipping_flat_cents": 0,
                                       "shipping_free_threshold_cents": None}),
        ("SELECT NOW()", datetime.now(timezone.utc)),
    ])
    monkeypatch.setattr(public_shop, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_shop, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_shop, "_published_site", AsyncMock(return_value={"id": SITE, "timezone": "UTC"}))
    monkeypatch.setattr(public_shop, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(public_shop, "fetch_active_discounts", AsyncMock(return_value=[]))
    out = await public_shop.quote(
        "store", CartQuoteRequest(items=[{"product_id": str(PRODUCT), "quantity": 1}]), request=None,
    )
    assert "status='active'" in conn.sql("FROM cappe_products")[0][1]
    # A draft (not returned by that query) prices as an unavailable line that
    # says nothing about the product.
    assert out["lines"] == [{"product_id": str(PRODUCT), "quantity": 1, "unit_price_cents": 0,
                             "available": False, "fulfillment": "physical"}]


# ── refunds and restocking ───────────────────────────────────────────────────

def test_a_refund_made_in_stripe_restocks_only_on_a_full_refund_of_unshipped_goods():
    """Moved to the refund ledger (test_cappe_refund_ledger.py); pinned here by
    source so the rule can't drift from the one the refund route uses."""
    import inspect
    from app.cappe.services import refunds
    src = inspect.getsource(refunds.sync_stripe_refunds)
    assert 'restock=extra >= left and order["status"] != "fulfilled"' in src


# ── the owner hears about a card order ───────────────────────────────────────

class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args):
        self.tasks.append((fn.__name__, args))


def test_a_card_paid_order_alerts_the_owner(monkeypatch):
    """The alert used to be sent only for orders that took NO card."""
    order_id = "11111111-1111-4111-8111-111111111111"
    conn = SqlConn([("UPDATE cappe_orders o", {
        "id": "o-1", "site_id": "s-1", "customer_email": "buyer@example.com",
        "customer_name": "Buyer", "shopper_id": None, "total_cents": 2150, "subtotal_cents": 2000,
        "currency": "USD", "site_name": "Store", "owner_email": "owner@example.com",
        "owner_name": "Owner",
    })])
    monkeypatch.setattr(payments_mod, "get_connection", lambda: Ctx(conn))
    bg = Background()
    asyncio.run(payments_mod._mark_order_paid(
        {"id": "cs_1", "payment_intent": "pi_1", "metadata": {"order_id": order_id}},
        {"account": "acct_1"}, bg,
    ))
    sql = conn.calls[0][1]
    assert "a.email AS owner_email" in sql and "s.name AS site_name" in sql
    names = [name for name, _ in bg.tasks]
    assert names == ["issue_receipt_for_paid_order", "send_cappe_order_alert_email"]
    args = bg.tasks[1][1]
    assert args[:6] == ("owner@example.com", "Owner", "Store", "Buyer", 2150, "USD")
    assert args[6].endswith("/sites/s-1/orders")


# ── the orders list ──────────────────────────────────────────────────────────

def _wire_orders(monkeypatch):
    conn = SqlConn()
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", AsyncMock())
    return conn


def test_the_orders_list_is_bounded_and_summarises_each_order(monkeypatch):
    conn = _wire_orders(monkeypatch)
    assert asyncio.run(shop_mod.list_orders(SITE, account=ACCOUNT)) == []
    _, sql, args = conn.calls[0]
    assert "AS item_count" in sql and "AS items_summary" in sql
    assert "LIMIT $2 OFFSET $3" in sql and args == (SITE, 200, 0)


def test_the_orders_list_filters_by_status_and_a_literal_search(monkeypatch):
    conn = _wire_orders(monkeypatch)
    asyncio.run(shop_mod.list_orders(
        SITE, account=ACCOUNT, order_status="paid", q=" 50%_off ", limit=25, offset=50,
    ))
    _, sql, args = conn.calls[0]
    assert "status = $2" in sql and "customer_email ILIKE $3" in sql and "receipt_number ILIKE $3" in sql
    # LIKE wildcards in the search are escaped: "50%" is a literal.
    assert args == (SITE, "paid", "%50\\%\\_off%", 25, 50)
    assert "LIMIT $4 OFFSET $5" in sql


# ── the storefront scripts ───────────────────────────────────────────────────
# Inlined JS cannot be executed here; like the discount-rounding pin in
# test_cappe_checkout_failure.py, the source is asserted on.

def _asset(name):
    import pathlib
    return (pathlib.Path(commerce.__file__).parent / "render/assets" / name).read_text()


def test_a_validation_error_is_shown_as_text_not_object_object():
    js = _asset("runtime.js")
    # A 422's `detail` is a list of {msg}; it used to go straight into Error().
    assert "Array.isArray(x)" in js and "throw new Error(errText(d))" in js
    assert "new Error((d&&d.detail)" not in js


def test_the_storefront_shows_sold_out_and_obeys_the_servers_availability():
    js = _asset("store.js")
    assert "function soldOut(p){return p.fulfillment==='physical'&&out(p.inventory);}" in js
    assert "sb.textContent='Sold out'" in js
    # The quote knows about variant stock the product row does not carry.
    assert "l.available===false" in js and "sb.textContent='Out of stock'" in js
