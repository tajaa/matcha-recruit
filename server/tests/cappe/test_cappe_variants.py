"""Product variants — physical sellers round, PR 1 (zzzzcappe50).

What each block pins:

  * a variant is one option from each required single-pick group, found by
    its options whatever order they were picked in;
  * a variant's own price replaces the product price and its options' price
    changes, and add-ons outside it still add theirs;
  * the bag checks stock against what it takes from a variant in total, and a
    variant's own options don't also count against their option stock;
  * the editor names variants by group and option name, and a save keeps the
    id of every combination that survives;
  * checkout takes the variant's stock (not its options'), records it on the
    order line, and locks it between the product and option rows;
  * restock and re-take move exactly the variant the sale recorded;
  * checkout refuses what the store's plan doesn't sell.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_variants.py -q
"""
import asyncio
import os
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
    CappeProductVariantInput,
    CappeStockAdjust,
)
from app.cappe.routes import billing as billing_mod  # noqa: E402
from app.cappe.routes.public import shop as public_shop  # noqa: E402
from app.cappe.services import cart  # noqa: E402
from app.cappe.services import commerce  # noqa: E402
from app.cappe.services import inventory as inv_mod  # noqa: E402
from app.cappe.services import variants as var_mod  # noqa: E402
from app.cappe.services.entitlements import ALL_FULFILLMENT, Entitlements, sells  # noqa: E402

SITE, PRODUCT, ORDER = uuid4(), uuid4(), uuid4()
SIZE, COLOUR, EXTRAS = uuid4(), uuid4(), uuid4()
S, M = uuid4(), uuid4()
RED, BLUE = uuid4(), uuid4()
WRAP = uuid4()


def _groups(*, m_stock=None, wrap_stock=None):
    return [
        {"id": SIZE, "name": "Size", "select_type": "single", "required": True, "options": [
            {"id": S, "name": "S", "price_delta_cents": 0, "inventory": None},
            {"id": M, "name": "M", "price_delta_cents": 200, "inventory": m_stock},
        ]},
        {"id": COLOUR, "name": "Colour", "select_type": "single", "required": True, "options": [
            {"id": RED, "name": "Red", "price_delta_cents": 100, "inventory": None},
            {"id": BLUE, "name": "Blue", "price_delta_cents": 0, "inventory": None},
        ]},
        {"id": EXTRAS, "name": "Extras", "select_type": "multi", "required": False, "options": [
            {"id": WRAP, "name": "Gift wrap", "price_delta_cents": 300, "inventory": wrap_stock},
        ]},
    ]


def _variant(*ids, **kw):
    return {"id": kw.pop("id", uuid4()), "option_ids": var_mod.sorted_ids(ids), "sku": None,
            "price_cents": None, "inventory": None, "image_url": None, "status": "active", **kw}


# ── matching ─────────────────────────────────────────────────────────────────

def test_only_required_single_pick_groups_make_a_variant():
    assert [g["name"] for g in var_mod.variant_groups(_groups())] == ["Size", "Colour"]


def test_a_selection_finds_its_variant_whatever_order_it_was_picked_in():
    mred = _variant(M, RED)
    found = var_mod.match_variant([_variant(S, RED), mred], _groups(), [RED, WRAP, M])
    assert found is mred                       # the add-on doesn't stop the match


def test_no_variant_until_every_variant_group_has_a_pick():
    assert var_mod.match_variant([_variant(M, RED)], _groups(), [M]) is None
    assert var_mod.match_variant([_variant(M, RED)], [], [M, RED]) is None


def test_a_combination_the_store_doesnt_sell_is_refused():
    off = _variant(M, RED, status="disabled")
    assert var_mod.match_variant([off], _groups(), [M, RED]) is off
    with pytest.raises(ValueError, match="isn't available"):
        var_mod.resolve_variant([off], _groups(), [M, RED])


# ── price ────────────────────────────────────────────────────────────────────

def test_without_a_price_of_its_own_a_variant_prices_as_options_always_did():
    plain, snap = var_mod.price_selection(1000, _groups(), [M, RED, WRAP], None)
    same, _ = var_mod.price_selection(1000, _groups(), [M, RED, WRAP], _variant(M, RED))
    assert plain == same == 1000 + 200 + 100 + 300
    assert [e["name"] for e in snap] == ["M", "Red", "Gift wrap"]


def test_a_variant_price_replaces_its_options_changes_but_not_the_add_ons():
    price, snap = var_mod.price_selection(1000, _groups(), [M, RED, WRAP], _variant(M, RED, price_cents=2500))
    assert price == 2500 + 300
    # The line still adds up: the covered options are recorded at 0.
    assert [(e["name"], e["price_delta_cents"]) for e in snap] == [("M", 0), ("Red", 0), ("Gift wrap", 300)]


def test_only_options_outside_the_variant_keep_their_own_stock():
    assert var_mod.uncovered_option_ids([M, RED, WRAP], _variant(M, RED)) == [WRAP]
    assert var_mod.uncovered_option_ids([M, RED], None) == [M, RED]


def test_a_variant_is_labelled_in_the_products_group_order():
    assert var_mod.variant_label(_groups(), var_mod.sorted_ids([RED, M])) == "M / Red"


# ── the bag ──────────────────────────────────────────────────────────────────

def _bag(variants, items, **groups_kw):
    product = {"id": PRODUCT, "name": "Tee", "price_cents": 1000, "currency": "USD", "status": "active",
               "fulfillment": "physical", "inventory": None, "discount_percent": 0,
               "option_groups": _groups(**groups_kw), "variants": variants}
    site = {"tax_rate_bps": 0, "shipping_flat_cents": 0, "shipping_free_threshold_cents": None, "home_country": "US"}
    return cart.price_cart({PRODUCT: product}, items, site)


def _item(*ids, qty=1):
    return CappeCartItem(product_id=PRODUCT, quantity=qty, selected_option_ids=list(ids))


def test_the_bag_counts_a_variants_stock_over_every_line_that_takes_it():
    v = _variant(M, RED, inventory=3)
    ok = _bag([v], [_item(M, RED, qty=2)])
    assert ok["lines"][0]["available"] and ok["lines"][0]["variant_id"] == str(v["id"])
    short = _bag([v], [_item(M, RED, qty=2), _item(RED, M, WRAP, qty=2)])
    assert [line["available"] for line in short["lines"]] == [False, False]


def test_a_variants_own_options_dont_also_need_option_stock():
    """M's own count is 0, but M / Red has three: the variant's count is the one."""
    out = _bag([_variant(M, RED, inventory=3)], [_item(M, RED)], m_stock=0)
    assert out["lines"][0]["available"]
    # Without the variant row, M's own stock still decides, as it always did.
    assert not _bag([], [_item(M, RED)], m_stock=0)["lines"][0]["available"]


def test_an_add_on_outside_the_variant_still_needs_its_stock():
    out = _bag([_variant(M, RED, inventory=3)], [_item(M, RED, WRAP)], wrap_stock=0)
    assert not out["lines"][0]["available"]


def test_the_bag_prices_a_variant_and_explains_a_disabled_one():
    priced = _bag([_variant(M, RED, price_cents=2500)], [_item(M, RED)])
    assert priced["lines"][0]["unit_price_cents"] == 2500 and priced["subtotal_cents"] == 2500
    off = _bag([_variant(M, RED, status="disabled")], [_item(M, RED)])
    assert not off["lines"][0]["available"] and off["lines"][0]["reason"] == "That combination isn't available"


# ── the editor names a variant by its options ────────────────────────────────

def _ref(**names):
    return [SimpleNamespace(group=g, option=o) for g, o in names.items()]


def test_names_resolve_to_the_variants_sorted_option_ids():
    assert var_mod.resolve_refs(_groups(), _ref(Colour="Red", Size="M")) == var_mod.sorted_ids([M, RED])


@pytest.mark.parametrize("groups,refs,message", [
    ([], _ref(Size="M"), "required, pick-one option group"),
    (_groups(), _ref(Size="M", Extras="Gift wrap"), "isn't a required, pick-one"),
    (_groups(), _ref(Size="XL", Colour="Red"), 'no option called "XL"'),
    (_groups(), _ref(Size="M"), "needs a Colour"),
    (_groups(), [SimpleNamespace(group="Size", option="M"), SimpleNamespace(group="Size", option="S"),
                 SimpleNamespace(group="Colour", option="Red")], 'picks one "Size"'),
])
def test_a_combination_that_doesnt_fit_the_product_is_refused(groups, refs, message):
    with pytest.raises(HTTPException) as exc:
        var_mod.resolve_refs(groups, refs)
    assert exc.value.status_code == 422 and message in exc.value.detail


def test_two_options_with_one_name_cant_be_told_apart():
    groups = _groups()
    groups[0]["options"].append({"id": uuid4(), "name": "M", "price_delta_cents": 0, "inventory": None})
    with pytest.raises(HTTPException) as exc:
        var_mod.resolve_refs(groups, _ref(Size="M", Colour="Red"))
    assert "Two options" in exc.value.detail


class VariantConn:
    """The stored variants, and every write made to them."""

    def __init__(self, prior):
        self.prior, self.inserts, self.updates, self.deletes = prior, [], [], []

    async def fetch(self, sql, *args):
        assert "FOR UPDATE" in sql and "cappe_product_variants" in sql
        return self.prior

    async def fetchval(self, sql, *args):
        assert "INSERT INTO cappe_product_variants" in sql
        self.inserts.append(args)
        return uuid4()

    async def execute(self, sql, *args):
        (self.updates if sql.startswith("UPDATE") else self.deletes).append((sql, args))


def _wire_replace(monkeypatch, prior):
    conn = VariantConn(prior)
    monkeypatch.setattr(var_mod, "fetch_option_groups", AsyncMock(return_value={PRODUCT: _groups()}))
    ledger = []

    async def _log(_conn, **kw):
        ledger.append(kw)

    monkeypatch.setattr(var_mod, "log_adjustment", _log)
    return conn, ledger


def _vin(size, colour, **kw):
    return CappeProductVariantInput(options=[{"group": "Size", "option": size}, {"group": "Colour", "option": colour}], **kw)


def test_a_save_keeps_each_surviving_combinations_row_and_drops_the_rest(monkeypatch):
    keep, gone = _variant(M, RED, inventory=4), _variant(S, BLUE, inventory=2)
    conn, ledger = _wire_replace(monkeypatch, [keep, gone])
    asyncio.run(var_mod.replace_variants(conn, SITE, PRODUCT, [_vin("M", "Red", sku="TEE-M-R"), _vin("S", "Red", inventory=5)]))
    # M / Red is updated in place — stock untouched, because the form didn't send it.
    ((sql, args),) = conn.updates
    assert args[0] == "TEE-M-R" and args[-1] == keep["id"] and "inventory" not in sql
    # S / Red is new, with its opening stock on the ledger.
    ((_s, _p, ids, *_rest),) = conn.inserts
    assert ids == var_mod.sorted_ids([S, RED])
    assert [(e["delta"], e["note"]) for e in ledger] == [(5, "Opening stock — S / Red")]
    # S / Blue wasn't sent: it goes.
    ((_sql, (deleted, _site)),) = conn.deletes
    assert deleted == [gone["id"]]


def test_an_id_never_moves_a_row_to_another_combination(monkeypatch):
    """Order lines and the ledger point at the row: M / Red must stay M / Red."""
    was = _variant(M, RED, inventory=4)
    conn, _ledger = _wire_replace(monkeypatch, [was])
    asyncio.run(var_mod.replace_variants(conn, SITE, PRODUCT, [_vin("S", "Blue", id=was["id"])]))
    assert len(conn.inserts) == 1 and conn.updates == []
    assert conn.deletes[0][1][0] == [was["id"]]


def test_a_stock_edit_is_logged_and_a_stale_one_refused(monkeypatch):
    was = _variant(M, RED, inventory=4)
    conn, ledger = _wire_replace(monkeypatch, [was])
    asyncio.run(var_mod.replace_variants(
        conn, SITE, PRODUCT, [_vin("M", "Red", id=was["id"], inventory=9, expected_inventory=4)],
    ))
    assert "inventory = $6" in conn.updates[0][0] and ledger[0]["delta"] == 5
    conn, _ledger = _wire_replace(monkeypatch, [was])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(var_mod.replace_variants(
            conn, SITE, PRODUCT, [_vin("M", "Red", id=was["id"], inventory=9, expected_inventory=6)],
        ))
    assert exc.value.status_code == 409 and conn.updates == []


def test_one_combination_listed_twice_is_refused(monkeypatch):
    conn, _ledger = _wire_replace(monkeypatch, [])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(var_mod.replace_variants(conn, SITE, PRODUCT, [_vin("M", "Red"), _vin("M", "Red")]))
    assert "listed twice" in exc.value.detail and conn.inserts == []


def test_none_leaves_variants_alone_and_an_empty_list_removes_them():
    asyncio.run(var_mod.replace_variants(None, SITE, PRODUCT, None))     # no connection touched
    conn = VariantConn([_variant(M, RED)])
    asyncio.run(var_mod.replace_variants(conn, SITE, PRODUCT, []))
    assert len(conn.deletes) == 1


def test_a_removed_option_takes_its_variants_with_it():
    conn = VariantConn([])
    asyncio.run(var_mod.prune_variants(conn, SITE, PRODUCT, [RED]))
    ((sql, args),) = conn.deletes
    assert "option_ids && $3::uuid[]" in sql and args[2] == [RED]
    asyncio.run(var_mod.prune_variants(conn, SITE, PRODUCT, []))
    assert len(conn.deletes) == 1


def test_variants_are_fetched_per_product_in_their_order():
    a, b = uuid4(), uuid4()
    rows = [{**_variant(M, RED), "product_id": a}, {**_variant(S), "product_id": b}, {**_variant(M), "product_id": a}]
    conn = SimpleNamespace(fetch=AsyncMock(return_value=rows))
    out = asyncio.run(var_mod.fetch_variants(conn, [a, b]))
    assert [len(out[a]), len(out[b])] == [2, 1] and out[a][0]["option_ids"] == var_mod.sorted_ids([M, RED])
    assert "ORDER BY sort_order, created_at, id" in conn.fetch.await_args.args[0]
    assert asyncio.run(var_mod.fetch_variants(conn, [])) == {} and conn.fetch.await_count == 1


def test_a_stock_adjustment_names_an_option_or_a_variant_not_both():
    CappeStockAdjust(delta=1, variant_id=uuid4())
    with pytest.raises(ValidationError):
        CappeStockAdjust(delta=1, variant_id=uuid4(), option_id=uuid4())


# ── checkout ─────────────────────────────────────────────────────────────────

class CheckoutConn:
    def __init__(self, product, variant, wrap):
        self.product, self.variant, self.wrap = product, variant, wrap
        self.locks, self.items, self.variant_updates, self.option_updates, self.order = [], [], [], [], None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return self

    async def fetch(self, sql, *args):
        assert "FOR UPDATE" in sql
        table = sql.split("FROM ")[1].split()[0]
        self.locks.append((table, args[1]))
        return []

    async def fetchrow(self, sql, *args):
        if "FROM cappe_product_variants" in sql:
            return self.variant
        if "FROM cappe_product_options" in sql:
            return self.wrap
        if "FROM cappe_products" in sql:
            return self.product
        if "FROM cappe_sites" in sql:
            return {"tax_rate_bps": 0, "tax_label": None, "shipping_flat_cents": 0,
                    "shipping_free_threshold_cents": None, "shipping_label": None}
        if "INSERT INTO cappe_orders" in sql:
            self.order = {"id": uuid4(), "status": "pending", "access_token": uuid4().hex,
                          "subtotal_cents": args[3], "tax_cents": args[4], "shipping_cents": args[5],
                          "total_cents": args[6], "currency": args[7], "requires_approval": args[9]}
            return self.order
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        if sql == "SELECT NOW()":
            return datetime.now(timezone.utc)
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        if "INSERT INTO cappe_order_items" in sql:
            self.items.append(args)
        elif "UPDATE cappe_product_variants SET inventory" in sql:
            self.variant_updates.append(args)
        elif "UPDATE cappe_product_options SET inventory" in sql:
            self.option_updates.append(args)


def _wire_checkout(monkeypatch, *, variant_stock=3, status="active", vanished=False, plan_sells=ALL_FULFILLMENT,
                   intake=None):
    site = {"id": SITE, "name": "Store", "timezone": "UTC", "custom_domain": "store.example.com"}
    v = _variant(M, RED, inventory=variant_stock, sku="TEE-M-R", price_cents=2500, status=status)
    product = {"id": PRODUCT, "name": "Tee", "price_cents": 1000, "currency": "USD", "inventory": None,
               "low_stock_threshold": 2, "status": "active", "fulfillment": "physical", "booking_type_id": None,
               "requires_approval": False, "intake_fields": "[]", "sku": "TEE"}
    conn = CheckoutConn(product, None if vanished else v, {"name": "Gift wrap", "inventory": 10})
    ledger = []

    async def _log(_conn, **kw):
        ledger.append(kw)

    monkeypatch.setattr(commerce, "_inv_log", _log)
    monkeypatch.setattr(commerce, "get_connection", lambda: conn)
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(commerce, "fetch_option_groups", AsyncMock(return_value={PRODUCT: _groups(m_stock=0, wrap_stock=10)}))
    monkeypatch.setattr(commerce, "fetch_variants", AsyncMock(return_value={PRODUCT: [v]}))
    monkeypatch.setattr(commerce, "fetch_site_owner", AsyncMock(return_value={
        "plan": "business", "status": "active", "email": "owner@example.com", "name": "Owner",
        "stripe_account_id": None, "stripe_charges_enabled": False}))
    monkeypatch.setattr(commerce, "resolve_entitlements", AsyncMock(return_value=SimpleNamespace(
        platform_fee_bps=200, allowed_fulfillment=frozenset(plan_sells), has=lambda _f: False)))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    monkeypatch.setattr(commerce, "check_recipient_send_ok", AsyncMock(return_value=False))
    body = CappeCheckoutRequest(customer_email="buyer@example.com", items=[CappeCartItem(
        product_id=PRODUCT, quantity=2, selected_option_ids=[RED, WRAP, M], intake_answers=intake or {},
    )])
    return site, body, conn, ledger, v


def test_a_sale_takes_the_variants_stock_not_its_options(monkeypatch):
    site, body, conn, ledger, v = _wire_checkout(monkeypatch)
    background = BackgroundTasks()
    asyncio.run(commerce.create_public_order(site, body, background))

    # Locks: product, then the variant, then only the option outside it.
    assert conn.locks == [("cappe_products", [PRODUCT]), ("cappe_product_variants", [v["id"]]),
                          ("cappe_product_options", [WRAP])]
    assert conn.variant_updates == [(1, v["id"])]
    assert conn.option_updates == [(8, WRAP)]               # M's own (zero) count is never touched
    assert [(e.get("variant_id"), e.get("option_id"), e["delta"]) for e in ledger] == [
        (v["id"], None, -2), (None, WRAP, -2),
    ]
    line = conn.items[0]
    assert line[4] == 2500 + 300                           # the variant's price, plus the wrap
    assert line[11:13] == (False, [WRAP])
    assert line[14:] == (v["id"], "TEE-M-R", v["id"])      # bought, sold under, stock taken from
    alerts = [t for t in background.tasks if t.func.__name__ == "send_cappe_low_stock_email"]
    assert [list(t.args[3]) for t in alerts] == [[("Tee — M / Red", 1)]]


def test_an_untracked_variant_still_records_what_was_bought(monkeypatch):
    site, body, conn, _ledger, v = _wire_checkout(monkeypatch, variant_stock=None)
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert conn.variant_updates == [] and conn.items[0][14:] == (v["id"], "TEE-M-R", None)


@pytest.mark.parametrize("kw,code,message", [
    ({"variant_stock": 1}, 409, "Insufficient stock for Tee (M / Red)"),
    ({"status": "disabled"}, 400, "isn't available"),
    ({"vanished": True}, 409, "just changed"),
    ({"plan_sells": {"digital", "service", "booking"}}, 409, "Tee isn't available right now"),
])
def test_checkout_refuses_what_it_cant_sell(monkeypatch, kw, code, message):
    site, body, conn, _ledger, _v = _wire_checkout(monkeypatch, **kw)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert exc.value.status_code == code and message in exc.value.detail
    assert conn.order is None and conn.variant_updates == []


def test_answers_sent_with_a_physical_item_are_not_kept(monkeypatch):
    site, body, conn, _ledger, _v = _wire_checkout(monkeypatch, intake={"engraving": "x" * 50})
    asyncio.run(commerce.create_public_order(site, body, BackgroundTasks()))
    assert conn.items[0][7] == "{}"


def test_the_plan_decides_what_sells():
    ent = Entitlements(plan_code="free", plan_name="Free", can_sell=True, platform_fee_bps=200,
                       allowed_fulfillment=frozenset({"digital", "service", "booking"}), site_limit=1,
                       mailbox_quota_included=0)
    assert not sells(ent, "physical") and not sells(ent, None) and sells(ent, "Booking")


# ── restock and re-take ──────────────────────────────────────────────────────

class StockConn:
    def __init__(self, lines):
        self.lines, self.locks, self.updates, self.recorded = lines, [], [], []

    async def fetch(self, sql, *args):
        if "FOR UPDATE" in sql:
            self.locks.append(sql.split("FROM ")[1].split()[0])
            return []
        assert "LEFT JOIN cappe_product_variants" in sql
        return self.lines

    async def fetchval(self, sql, *args):
        if "FROM cappe_promo_redemptions" in sql:
            return None
        self.updates.append((sql.split()[1], args[0], args[1]))
        return 5

    async def execute(self, sql, *args):
        self.recorded.append((sql, args))


def _line(**kw):
    return {"id": uuid4(), "product_id": PRODUCT, "quantity": 2, "selected_option_ids": [], "restocked_quantity": 0,
            "variant_id": None, "decremented_variant_id": None, "variant_option_ids": None, **kw}


def test_a_restock_credits_the_variant_the_sale_took(monkeypatch):
    monkeypatch.setattr(inv_mod, "log_adjustment", AsyncMock())
    vid = uuid4()
    conn = StockConn([_line(selected_option_ids=[M, RED, WRAP], stock_decremented=False, variant_id=vid,
                            decremented_variant_id=vid, decremented_option_ids=[WRAP], variant_option_ids=[M, RED])])
    asyncio.run(inv_mod.restock_order(conn, site_id=SITE, order_id=ORDER, reason="restock"))
    assert conn.updates == [("cappe_product_variants", 2, vid), ("cappe_product_options", 2, WRAP)]
    assert conn.locks == ["cappe_products", "cappe_product_variants", "cappe_product_options"]


def test_a_variant_that_wasnt_tracking_when_it_sold_gets_nothing_back(monkeypatch):
    monkeypatch.setattr(inv_mod, "log_adjustment", AsyncMock())
    conn = StockConn([_line(stock_decremented=False, variant_id=uuid4(), decremented_variant_id=None,
                            decremented_option_ids=[])])
    asyncio.run(inv_mod.restock_order(conn, site_id=SITE, order_id=ORDER, reason="restock"))
    assert conn.updates == []


def test_a_renewal_line_takes_its_variant_and_records_it(monkeypatch):
    """A renewal line has no record yet: its variant is taken, its variant's own
    options are not, and what came off the shelf is written down."""
    monkeypatch.setattr(inv_mod, "log_adjustment", AsyncMock())
    vid = uuid4()
    line = _line(selected_option_ids=[M, RED, WRAP], stock_decremented=None, decremented_option_ids=None,
                 variant_id=vid, variant_option_ids=[M, RED])
    conn = StockConn([line])
    asyncio.run(inv_mod.retake_order_stock(conn, site_id=SITE, order_id=ORDER))
    assert [u[0] for u in conn.updates] == ["cappe_products", "cappe_product_variants", "cappe_product_options"]
    assert conn.updates[2][2] == WRAP
    (sql, args), = [r for r in conn.recorded if "stock_decremented = $2" in r[0]]
    assert args == (line["id"], True, [WRAP], vid)


# ── what the storefront and dashboard are told ───────────────────────────────

def test_the_storefront_lists_only_what_the_plan_sells(monkeypatch):
    rows = [{"id": uuid4(), "fulfillment": f, "subscription_intervals": [], "price_cents": 100, "intake_fields": "[]"}
            for f in ("physical", "booking")]
    conn = SimpleNamespace(fetch=AsyncMock(side_effect=lambda sql, *a: [] if "cappe_reviews" in sql else rows),
                           fetchval=AsyncMock(return_value=datetime.now(timezone.utc)))

    class Ctx:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(public_shop, "get_connection", lambda: Ctx())
    monkeypatch.setattr(public_shop, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_shop, "_published_site", AsyncMock(return_value={"id": SITE, "timezone": "UTC"}))
    monkeypatch.setattr(public_shop, "_site_entitlements", AsyncMock(
        return_value=SimpleNamespace(allowed_fulfillment=frozenset({"digital", "service", "booking"}))))
    monkeypatch.setattr(public_shop, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(public_shop, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(public_shop, "fetch_variants", AsyncMock(return_value={rows[1]["id"]: [_variant(M, RED)]}))
    monkeypatch.setattr(public_shop, "site_today", lambda *_a: None)
    out = asyncio.run(public_shop.public_products("store", SimpleNamespace()))
    assert [p["fulfillment"] for p in out] == ["booking"] and len(out[0]["variants"]) == 1


def test_the_dashboard_is_told_what_the_plan_sells(monkeypatch):
    ent = Entitlements(plan_code="creator", plan_name="Creator", can_sell=True, platform_fee_bps=300,
                       allowed_fulfillment=frozenset({"physical", "booking"}), site_limit=None,
                       mailbox_quota_included=0, features={"promo_codes": True})

    class Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(billing_mod, "get_connection", lambda: Ctx())
    monkeypatch.setattr(billing_mod, "resolve_entitlements", AsyncMock(return_value=ent))
    out = asyncio.run(billing_mod.get_entitlements(account=SimpleNamespace(plan="creator")))
    assert out.allowed_fulfillment == ["booking", "physical"] and out.platform_fee_bps == 300
    assert out.features == {"promo_codes": True}


# ── the Storefront app still decodes the catalog ─────────────────────────────

_SWIFT_MODELS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "platforms", "ios", "Storefront", "Sources", "Models.swift")


def _required_keys(struct: str) -> set[str]:
    """The non-optional `let`s of one Swift struct, as the snake_case keys the
    app's decoder (convertFromSnakeCase) reads. Missing or null → the whole
    catalog fails to load in the app."""
    import re
    src = open(_SWIFT_MODELS).read()
    body = re.search(rf"struct {struct}\b[^{{]*{{(.*?)\n}}", src, re.S).group(1)
    names = re.findall(r"^\s*let (\w+): ([^\n=]+)$", body, re.M)
    return {re.sub(r"(?<!^)([A-Z])", r"_\1", n).lower() for n, t in names if not t.strip().endswith("?")}


@pytest.mark.skipif(not os.path.exists(_SWIFT_MODELS), reason="the iOS sources aren't in this checkout")
def test_the_public_product_still_carries_every_key_the_storefront_app_requires():
    from app.cappe.models.shop import CappeProduct
    product = CappeProduct(
        id=uuid4(), site_id=SITE, name="Tee", price_cents=2000, currency="USD", status="active", sort_order=0,
        option_groups=[{"id": SIZE, "name": "Size", "select_type": "single", "required": True,
                        "options": [{"id": M, "name": "M", "price_delta_cents": 0}]}],
        variants=[_variant(M)],
    ).model_dump(mode="json")
    for key in _required_keys("Product"):
        assert product.get(key) is not None, key
    group = product["option_groups"][0]
    assert all(group.get(k) is not None for k in _required_keys("OptionGroup"))
    assert all(group["options"][0].get(k) is not None for k in _required_keys("ProductOption"))
    assert _required_keys("Product") >= {"id", "price_cents", "option_groups", "subscription_discount_bps"}
