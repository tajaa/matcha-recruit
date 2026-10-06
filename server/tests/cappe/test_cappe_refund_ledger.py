"""The refund ledger and the finances page — the 2026-10 commerce readiness review, PR 6.

What each block pins:

  * a refund is written pending, then settled once: units back on the shelf,
    money on the order, the order closed out only when nothing is left;
  * part refunds add up, never restock the same unit twice, and leave the
    order paid;
  * the `charge.refunded` webhook applies OUR pending refund with the owner's
    restock choice (it used to arrive first and guess), records anything
    else as a refund made in Stripe, and is a no-op on its own echo;
  * a lost dispute refunds what's left without restocking;
  * the finances summary, its window and buckets, the CSV export (plan
    gated, safe to open in a spreadsheet) and the Stripe balance.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_refund_ledger.py -q
"""
import asyncio
import csv
import io
import json
import os
import pathlib
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.models.shop import CappeRefundLine, CappeRefundRequest  # noqa: E402
from app.cappe.routes import financials as fin  # noqa: E402
from app.cappe.services import inventory as inv_mod  # noqa: E402
from app.cappe.services import refunds  # noqa: E402
from app.cappe.services import stripe_connect  # noqa: E402

SITE, ORDER = uuid4(), uuid4()
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "zzzzcappe44_refund_ledger.py"


class LedgerDB:
    """Just enough of Postgres for services/refunds.py, with real state."""

    def __init__(self, status="paid", total=5000, refunded=0, items=()):
        self.order = {"id": ORDER, "site_id": SITE, "status": status, "total_cents": total,
                      "subtotal_cents": total, "refunded_cents": refunded, "currency": "USD",
                      "stripe_payment_intent": "pi_1", "stripe_invoice_id": None, "stripe_refund_id": None}
        self.items = {str(i["id"]): dict(i) for i in items}
        self.refunds: list[dict] = []

    def _refund(self, refund_id):
        return next((r for r in self.refunds if r["id"] == refund_id), None)

    async def fetchrow(self, sql, *args):
        if "FROM cappe_orders WHERE id = $1 AND site_id = $2 FOR UPDATE" in sql:
            return dict(self.order) if self.order and args[0] == ORDER else None
        if "INSERT INTO cappe_order_refunds" in sql:
            if any(r["status"] == "pending" for r in self.refunds):
                raise asyncpg.UniqueViolationError("uq_cappe_order_refunds_pending")
            row = {"id": uuid4(), "order_id": args[0], "site_id": args[1], "amount_cents": args[2],
                   "restock": args[3], "lines": args[4], "reason": args[5], "source": args[6],
                   "status": "pending", "stripe_refund_id": None, "failure": None, "created_at": NOW}
            self.refunds.append(row)
            return dict(row)
        if "SET status = 'succeeded'" in sql:
            row = self._refund(args[0])
            if row is None or row["status"] != "pending":
                return None
            row.update(status="succeeded", stripe_refund_id=args[2] or row["stripe_refund_id"])
            return dict(row)
        if "EXTRACT(EPOCH" in sql:
            row = next((r for r in self.refunds if r["status"] == "pending"), None)
            return {**row, "age": 1} if row else None
        raise AssertionError(sql)

    async def fetch(self, sql, *args):
        if "status IN ('pending', 'succeeded')" in sql:
            return [dict(r) for r in self.refunds if r["status"] in ("pending", "succeeded")]
        if "FROM cappe_order_items" in sql:
            return [dict(self.items[str(i)]) for i in args[1] if str(i) in self.items]
        if "FROM cappe_order_refunds WHERE order_id = $1 ORDER BY" in sql:
            return [dict(r) for r in self.refunds]
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        if "WHERE stripe_refund_id = $1" in sql:
            return 1 if any(r["stripe_refund_id"] == args[0] for r in self.refunds) else None
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        if "SET status = 'failed'" in sql:
            row = self._refund(args[0])
            if row and row["status"] == "pending":
                row.update(status="failed", failure=args[1])
        elif "SET status = 'refunded'" in sql:
            self.order.update(status="refunded", refunded_cents=args[1],
                              stripe_refund_id=args[2] or self.order["stripe_refund_id"])
        elif "UPDATE cappe_orders SET refunded_cents" in sql:
            self.order.update(refunded_cents=args[1], stripe_refund_id=args[2] or self.order["stripe_refund_id"])
        else:
            raise AssertionError(sql)


@pytest.fixture
def stock(monkeypatch):
    """What went back on the shelf, and which slots were freed."""
    log = []

    async def _restock(_conn, *, site_id, order_id, reason, only=None):
        log.append(("restock", only))

    async def _bookings(_conn, *, order_id):
        log.append(("bookings",))
        return 0

    monkeypatch.setattr(refunds, "restock_order", _restock)
    monkeypatch.setattr(refunds, "release_order_bookings", _bookings)
    return log


def _run(coro):
    return asyncio.run(coro)


def _start(db, amount, *, restock=False, lines=(), source="dashboard"):
    return _run(refunds.start_refund(
        db, order=db.order, amount_cents=amount, restock=restock, lines=list(lines), reason=None, source=source,
    ))


# ── settling a refund ────────────────────────────────────────────────────────

def test_a_full_refund_closes_the_order_restocks_and_frees_its_slots(stock):
    db = LedgerDB()
    row = _start(db, 5000, restock=True)
    assert row["status"] == "pending" and db.order["status"] == "paid"   # nothing moves before Stripe
    _run(refunds.apply_refund(db, refund_id=row["id"], site_id=SITE, stripe_refund_id="re_1"))
    assert db.order["status"] == "refunded" and db.order["refunded_cents"] == 5000
    assert db.order["stripe_refund_id"] == "re_1"
    assert stock == [("restock", None), ("bookings",)]


def test_a_part_refund_leaves_the_order_paid_and_restocks_only_its_lines(stock):
    db = LedgerDB()
    line = {"item_id": "i-1", "quantity": 1}
    row = _start(db, 1200, lines=[line])
    _run(refunds.apply_refund(db, refund_id=row["id"], site_id=SITE))
    assert db.order["status"] == "paid" and db.order["refunded_cents"] == 1200
    assert stock == [("restock", {"i-1": 1})]


def test_part_refunds_add_up_to_a_full_one(stock):
    db = LedgerDB()
    for amount in (1200, 3800):
        row = _start(db, amount)
        _run(refunds.apply_refund(db, refund_id=row["id"], site_id=SITE))
    assert db.order["status"] == "refunded" and db.order["refunded_cents"] == 5000
    # The last one had no restock and no lines: nothing goes back.
    assert stock == [("bookings",)]


def test_a_refund_is_settled_once(stock):
    db = LedgerDB()
    row = _start(db, 5000, restock=True)
    first = _run(refunds.apply_refund(db, refund_id=row["id"], site_id=SITE))
    again = _run(refunds.apply_refund(db, refund_id=row["id"], site_id=SITE))
    assert first is not None and again is None
    assert db.order["refunded_cents"] == 5000 and stock.count(("restock", None)) == 1


def test_one_refund_in_flight_at_a_time(stock):
    db = LedgerDB()
    _start(db, 1000)
    with pytest.raises(HTTPException) as exc:
        _start(db, 1000)
    assert exc.value.status_code == 409 and "still being processed" in exc.value.detail


def test_a_failed_refund_moves_nothing_and_frees_the_slot_for_another(stock):
    db = LedgerDB()
    row = _start(db, 1000)
    _run(refunds.fail_refund(db, row["id"], "card closed"))
    assert db.refunds[0]["status"] == "failed" and db.refunds[0]["failure"] == "card closed"
    assert _run(refunds.apply_refund(db, refund_id=row["id"], site_id=SITE)) is None
    assert db.order["refunded_cents"] == 0
    _start(db, 1000)                                       # no longer blocked


def test_whats_left_to_refund():
    assert refunds.refundable_left({"total_cents": 5000, "refunded_cents": 1200}) == 3800
    assert refunds.refundable_left({"total_cents": None, "subtotal_cents": 900}) == 900
    assert refunds.refundable_left({"total_cents": 100, "refunded_cents": 300}) == 0


# ── which units go back ──────────────────────────────────────────────────────

ITEM = {"id": uuid4(), "title": "Mug", "quantity": 3, "restocked_quantity": 1, "fulfillment": "physical"}
DIGITAL = {"id": uuid4(), "title": "Zine", "quantity": 1, "restocked_quantity": 0, "fulfillment": "digital"}


def test_lines_are_capped_at_what_is_still_out():
    db = LedgerDB(items=[ITEM, DIGITAL])
    plan = _run(refunds.plan_restock_lines(db, ORDER, [CappeRefundLine(item_id=ITEM["id"], quantity=2)]))
    assert plan == [{"item_id": str(ITEM["id"]), "quantity": 2}]
    with pytest.raises(HTTPException) as exc:
        _run(refunds.plan_restock_lines(db, ORDER, [CappeRefundLine(item_id=ITEM["id"], quantity=3)]))
    assert exc.value.status_code == 422 and "Only 2 of “Mug”" in exc.value.detail


@pytest.mark.parametrize("item_id", [DIGITAL["id"], uuid4()])
def test_only_this_orders_shipped_goods_go_back(item_id):
    db = LedgerDB(items=[ITEM, DIGITAL])
    with pytest.raises(HTTPException) as exc:
        _run(refunds.plan_restock_lines(db, ORDER, [CappeRefundLine(item_id=item_id, quantity=1)]))
    assert exc.value.status_code == 422


def test_no_lines_plan_nothing():
    assert _run(refunds.plan_restock_lines(LedgerDB(), ORDER, [])) == []


class StockConn:
    def __init__(self, lines):
        self.lines, self.credits, self.marked = lines, [], []

    async def fetch(self, sql, *args):
        return [] if "FOR UPDATE" in sql else self.lines

    async def fetchval(self, sql, *args):
        self.credits.append(("option" if "cappe_product_options" in sql else "product", args[0]))
        return 10

    async def execute(self, sql, *args):
        if "restocked_quantity = restocked_quantity + $2" in sql:
            self.marked.append(args)


def test_a_restock_never_returns_the_same_unit_twice(monkeypatch):
    monkeypatch.setattr(inv_mod, "log_adjustment", AsyncMock())
    line = {"id": uuid4(), "product_id": uuid4(), "quantity": 3, "restocked_quantity": 2,
            "selected_option_ids": [], "stock_decremented": True, "decremented_option_ids": []}
    conn = StockConn([line])
    asyncio.run(inv_mod.restock_order(conn, site_id=SITE, order_id=ORDER, reason="return"))
    assert conn.credits == [("product", 1)] and conn.marked == [(line["id"], 1)]
    done = StockConn([{**line, "restocked_quantity": 3}])
    asyncio.run(inv_mod.restock_order(done, site_id=SITE, order_id=ORDER, reason="return"))
    assert done.credits == [] and done.marked == []


def test_a_part_restock_returns_only_the_units_asked_for(monkeypatch):
    monkeypatch.setattr(inv_mod, "log_adjustment", AsyncMock())
    a = {"id": uuid4(), "product_id": uuid4(), "quantity": 3, "restocked_quantity": 0,
         "selected_option_ids": [], "stock_decremented": True, "decremented_option_ids": []}
    b = {**a, "id": uuid4(), "product_id": uuid4()}
    conn = StockConn([a, b])
    asyncio.run(inv_mod.restock_order(conn, site_id=SITE, order_id=ORDER, reason="return", only={str(a["id"]): 1}))
    assert conn.credits == [("product", 1)] and conn.marked == [(a["id"], 1)]


# ── charge.refunded catches the ledger up to Stripe ──────────────────────────

def test_our_pending_refund_is_applied_with_the_owners_choice(stock):
    """The webhook can land before Stripe's answer reaches the route. It used to
    apply its own default (restock an unshipped order) over the owner's "these
    aren't coming back"."""
    db = LedgerDB()
    _start(db, 5000, restock=False)
    out = _run(refunds.sync_stripe_refunds(db, order_id=ORDER, site_id=SITE, amount_refunded=5000,
                                           stripe_refund_id="re_1"))
    assert out == "refunded" and db.order["status"] == "refunded"
    assert len(db.refunds) == 1 and db.refunds[0]["status"] == "succeeded"
    assert ("restock", None) not in stock


def test_the_routes_echo_changes_nothing(stock):
    db = LedgerDB()
    row = _start(db, 1200)
    _run(refunds.apply_refund(db, refund_id=row["id"], site_id=SITE, stripe_refund_id="re_1"))
    out = _run(refunds.sync_stripe_refunds(db, order_id=ORDER, site_id=SITE, amount_refunded=1200,
                                           stripe_refund_id="re_1"))
    assert out == "partially_refunded" and len(db.refunds) == 1 and db.order["refunded_cents"] == 1200


@pytest.mark.parametrize("status_now,restocked", [("paid", True), ("fulfilled", False)])
def test_a_full_refund_made_in_stripe_is_recorded_and_restocks_unshipped_goods(stock, status_now, restocked):
    db = LedgerDB(status=status_now)
    out = _run(refunds.sync_stripe_refunds(db, order_id=ORDER, site_id=SITE, amount_refunded=5000,
                                           stripe_refund_id="re_dash"))
    assert out == "refunded"
    (row,) = db.refunds
    assert (row["source"], row["amount_cents"], row["stripe_refund_id"]) == ("stripe", 5000, "re_dash")
    assert (("restock", None) in stock) is restocked


def test_a_part_refund_made_in_stripe_restocks_nothing(stock):
    db = LedgerDB()
    out = _run(refunds.sync_stripe_refunds(db, order_id=ORDER, site_id=SITE, amount_refunded=700,
                                           stripe_refund_id="re_dash"))
    assert out == "partially_refunded" and db.order["status"] == "paid"
    assert db.refunds[0]["amount_cents"] == 700 and stock == []


def test_a_second_refund_in_stripe_records_only_the_difference(stock):
    db = LedgerDB()
    _run(refunds.sync_stripe_refunds(db, order_id=ORDER, site_id=SITE, amount_refunded=700, stripe_refund_id="re_a"))
    _run(refunds.sync_stripe_refunds(db, order_id=ORDER, site_id=SITE, amount_refunded=1000, stripe_refund_id="re_a"))
    assert [r["amount_cents"] for r in db.refunds] == [700, 300]
    # The same Stripe id can't be on two rows; the second carries none.
    assert [r["stripe_refund_id"] for r in db.refunds] == ["re_a", None]


def test_a_refund_on_an_order_we_dont_know_is_ignored(stock):
    db = LedgerDB()
    db.order = None
    assert _run(refunds.sync_stripe_refunds(db, order_id=ORDER, site_id=SITE, amount_refunded=500,
                                            stripe_refund_id=None)) == "unknown"


def test_a_lost_dispute_refunds_whats_left_without_restocking(stock):
    db = LedgerDB(refunded=1000)
    row = _run(refunds.refund_in_full(db, order_id=ORDER, site_id=SITE, source="dispute", restock=False))
    assert row["source"] == "dispute" and row["amount_cents"] == 4000
    assert db.order["status"] == "refunded" and stock == [("bookings",)]


@pytest.mark.parametrize("status_now", ["pending", "refunded", "cancelled"])
def test_refund_in_full_leaves_an_order_holding_no_money_alone(stock, status_now):
    db = LedgerDB(status=status_now)
    assert _run(refunds.refund_in_full(db, order_id=ORDER, site_id=SITE, source="dispute", restock=False)) is None
    assert db.refunds == []


def test_the_ledger_reads_back_with_its_lines():
    db = LedgerDB()
    _start(db, 500, lines=[{"item_id": "i-1", "quantity": 1}])
    db.refunds[0]["lines"] = json.dumps([{"item_id": "i-1", "quantity": 1}])
    (row,) = _run(refunds.list_refunds(db, ORDER))
    assert row["lines"] == [{"item_id": "i-1", "quantity": 1}]
    assert refunds.decode_lines("not json") == []


def test_the_refund_request_bounds():
    assert CappeRefundRequest().amount_cents is None
    with pytest.raises(Exception):
        CappeRefundRequest(amount_cents=0)
    with pytest.raises(Exception):
        CappeRefundLine(item_id=uuid4(), quantity=0)


def test_the_migration_chains_backfills_and_gates_the_export():
    src = MIGRATION.read_text()
    assert 'down_revision = "zzzzcappe43"' in src and 'revision = "zzzzcappe44"' in src
    assert "WHERE status = 'pending'" in src and "uq_cappe_order_refunds_pending" in src
    assert "'legacy'" in src and "o.refunded_cents > 0" in src
    assert "jsonb_build_object('financials_export', true)" in src
    assert "restocked_quantity INTEGER NOT NULL DEFAULT 0" in src


# ── Stripe ───────────────────────────────────────────────────────────────────

class FakeStripeModule:
    def __init__(self, refunds_page=()):
        self.created = []
        self.Refund = SimpleNamespace(create=self._create, list=lambda **kw: {"data": list(refunds_page)})
        self.Balance = SimpleNamespace(retrieve=lambda **kw: {
            "available": [{"amount": 1234, "currency": "usd"}], "pending": [{"amount": 50, "currency": "usd"}]})
        self.Payout = SimpleNamespace(list=lambda **kw: {"data": [
            {"id": "po_1", "amount": 9000, "currency": "usd", "status": "paid", "arrival_date": 1760000000}]})

    def _create(self, **kw):
        self.created.append(kw)
        return {"id": "re_1"}


def _client(monkeypatch, fake):
    monkeypatch.setattr(stripe_connect, "stripe", fake)
    client = stripe_connect.CappeStripe.__new__(stripe_connect.CappeStripe)
    client._ensure_key = lambda: None
    return client


def test_a_part_refund_asks_stripe_for_its_amount_and_tags_the_ledger_row(monkeypatch):
    fake = FakeStripeModule()
    client = _client(monkeypatch, fake)
    asyncio.run(client.refund_connected_charge(
        account_id="acct_1", payment_intent="pi_1", idempotency_key="k", amount_cents=1200,
        metadata={"cappe_refund_id": "r-1"}))
    (kw,) = fake.created
    assert kw["amount"] == 1200 and kw["metadata"] == {"cappe_refund_id": "r-1"}
    assert kw["refund_application_fee"] is True and kw["stripe_account"] == "acct_1"


def test_a_lost_request_is_found_by_its_ledger_id(monkeypatch):
    client = _client(monkeypatch, FakeStripeModule([
        {"id": "re_x", "metadata": {"cappe_refund_id": "other"}},
        {"id": "re_ours", "metadata": {"cappe_refund_id": "r-1"}, "status": "succeeded"},
    ]))
    found = asyncio.run(client.find_connected_refund(account_id="a", payment_intent="pi", cappe_refund_id="r-1"))
    assert found["id"] == "re_ours"
    assert asyncio.run(client.find_connected_refund(account_id="a", payment_intent="pi", cappe_refund_id="r-2")) is None


def test_the_balance_reads_the_connected_account(monkeypatch):
    client = _client(monkeypatch, FakeStripeModule())
    out = asyncio.run(client.connected_balance("acct_1"))
    assert out["available"] == [{"amount_cents": 1234, "currency": "USD"}]
    assert out["payouts"][0] == {"id": "po_1", "amount_cents": 9000, "currency": "USD", "status": "paid",
                                 "arrival_date": 1760000000}


# ── finances ─────────────────────────────────────────────────────────────────

LA = ZoneInfo("America/Los_Angeles")


def test_the_default_window_is_the_last_thirty_days_in_the_stores_zone():
    start, end, lo, hi = fin.window(None, None, LA, date(2026, 10, 6))
    assert (start, end) == (date(2026, 9, 7), date(2026, 10, 6))
    assert lo == datetime(2026, 9, 7, tzinfo=LA) and hi == datetime(2026, 10, 7, tzinfo=LA)


@pytest.mark.parametrize("start,end,fragment", [
    (date(2026, 10, 6), date(2026, 10, 1), "on or before"),
    (date(2023, 1, 1), date(2026, 10, 1), "two years"),
])
def test_a_window_that_makes_no_sense_is_refused(start, end, fragment):
    with pytest.raises(HTTPException) as exc:
        fin.window(start, end, LA, date(2026, 10, 6))
    assert exc.value.status_code == 422 and fragment in exc.value.detail


def test_every_bucket_is_listed_even_when_empty():
    assert fin.periods(date(2026, 10, 1), date(2026, 10, 3), "day") == [
        date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]
    assert fin.periods(date(2026, 10, 1), date(2026, 10, 14), "week") == [
        date(2026, 9, 28), date(2026, 10, 5), date(2026, 10, 12)]
    assert fin.periods(date(2026, 11, 15), date(2027, 1, 2), "month") == [
        date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)]


class FinConn:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    async def _answer(self, sql, args):
        self.calls.append((sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value
        return None

    async def fetchrow(self, sql, *args):
        return await self._answer(sql, args)

    async def fetch(self, sql, *args):
        return await self._answer(sql, args) or []

    async def fetchval(self, sql, *args):
        return await self._answer(sql, args)


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


SITE_ROW = {"id": SITE, "timezone": "America/Los_Angeles", "currency": "USD", "slug": "lumiere"}


def _wire_fin(monkeypatch, conn, *, export=True):
    account = SimpleNamespace(id=uuid4(), plan="business")
    monkeypatch.setattr(fin, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(fin, "get_owned_site", AsyncMock(return_value=SITE_ROW))
    monkeypatch.setattr(fin, "resolve_entitlements", AsyncMock(
        return_value=SimpleNamespace(has=lambda f: export and f == "financials_export")))
    monkeypatch.setattr(fin, "_today", lambda tz: date(2026, 10, 6))
    return account


def test_the_summary_adds_up(monkeypatch):
    conn = FinConn([
        ("date_trunc('day', COALESCE", [{"period": date(2026, 10, 5), "orders": 4, "gross": 20000}]),
        ("date_trunc('day', r.created_at", [{"period": date(2026, 10, 6), "amount": 3000}]),
        ("COUNT(*) AS orders", {"orders": 4, "gross": 20000, "goods": 17000, "tax": 1500,
                                "shipping": 1500, "fees": 400}),
        ("COUNT(*) AS n", {"amount": 3000, "n": 2}),
        ("ORDER BY revenue DESC", [{"product_id": None, "title": "Mug", "units": 5, "revenue": 10000}]),
        ("o.currency <> $4", 1),
    ])
    account = _wire_fin(monkeypatch, conn)
    out = asyncio.run(fin.financials(SITE, account, start=date(2026, 10, 4), end=date(2026, 10, 6), group="day"))
    assert out["net_cents"] == 20000 - 3000 - 400 and out["average_order_cents"] == 5000
    assert out["refund_count"] == 2 and out["other_currency_orders"] == 1 and out["export_enabled"] is True
    assert [(p["period"], p["gross_cents"], p["refunds_cents"]) for p in out["series"]] == [
        (date(2026, 10, 4), 0, 0), (date(2026, 10, 5), 20000, 0), (date(2026, 10, 6), 0, 3000)]
    assert out["top_products"] == [{"product_id": None, "title": "Mug", "units": 5, "revenue_cents": 10000}]
    # Only the store's currency is totalled, in its own timezone.
    totals_sql, totals_args = conn.calls[0]
    assert "o.currency = $4" in totals_sql and totals_args[3] == "USD"
    assert totals_args[1] == datetime(2026, 10, 4, tzinfo=LA)


def test_an_empty_store_has_no_average_to_divide_by(monkeypatch):
    conn = FinConn([("date_trunc", []), ("COUNT(*) AS orders", {"orders": 0, "gross": 0, "goods": 0, "tax": 0, "shipping": 0, "fees": 0}),
                    ("COUNT(*) AS n", {"amount": 0, "n": 0})])
    account = _wire_fin(monkeypatch, conn, export=False)
    out = asyncio.run(fin.financials(SITE, account, start=None, end=None, group="week"))
    assert out["average_order_cents"] == 0 and out["net_cents"] == 0 and out["export_enabled"] is False


def test_the_export_needs_the_plan(monkeypatch):
    account = _wire_fin(monkeypatch, FinConn([]), export=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fin.export_financials(SITE, account, start=None, end=None, kind="orders"))
    assert exc.value.status_code == 402


def test_the_orders_export_is_safe_to_open_in_a_spreadsheet(monkeypatch):
    rows = [{"at": datetime(2026, 10, 5, 20, 30, tzinfo=timezone.utc), "receipt_number": None, "id": ORDER,
             "status": "paid", "customer_name": "=HYPERLINK(\"http://x\")", "customer_email": "b@example.com",
             "currency": "USD", "subtotal_cents": 4500, "tax_cents": 0, "shipping_cents": 500,
             "total_cents": 5000, "refunded_cents": 1200, "platform_fee_cents": 90, "ship_country": "CA",
             "card": True}]
    account = _wire_fin(monkeypatch, FinConn([("FROM cappe_orders o", rows)]))
    resp = asyncio.run(fin.export_financials(SITE, account, start=date(2026, 10, 1), end=date(2026, 10, 6), kind="orders"))
    assert resp.headers["content-disposition"] == 'attachment; filename="lumiere-orders-2026-10-01-to-2026-10-06.csv"'
    header, line = list(csv.reader(io.StringIO(resp.body.decode())))
    assert header[0] == "Date" and line[0] == "2026-10-05 13:30"        # the store's local time
    assert line[3].startswith("'=")                                     # a formula is text, not code
    assert line[9:13] == ["50.00", "12.00", "0.90", "CA"] and line[13] == "card"


def test_the_refunds_export_says_where_each_was_made(monkeypatch):
    rows = [{"at": datetime(2026, 10, 5, 20, 30, tzinfo=timezone.utc), "receipt_number": "LUM-00042", "id": ORDER,
             "amount_cents": 1200, "currency": "USD", "source": "stripe", "reason": None,
             "stripe_refund_id": "re_1", "customer_email": "b@example.com"}]
    account = _wire_fin(monkeypatch, FinConn([("FROM cappe_order_refunds r", rows)]))
    resp = asyncio.run(fin.export_financials(SITE, account, start=None, end=None, kind="refunds"))
    _header, line = list(csv.reader(io.StringIO(resp.body.decode())))
    assert line[1:5] == ["LUM-00042", "12.00", "USD", "Stripe"]


def test_the_balance_says_when_stripe_isnt_connected(monkeypatch):
    conn = FinConn([("stripe_account_id", None)])
    monkeypatch.setattr(fin, "get_connection", lambda: Ctx(conn))
    out = asyncio.run(fin.payments_balance(SimpleNamespace(id=uuid4())))
    assert out == {"connected": False, "available": [], "pending": [], "payouts": []}


def test_the_balance_comes_from_stripe_or_says_it_couldnt(monkeypatch):
    conn = FinConn([("stripe_account_id", "acct_1")])
    monkeypatch.setattr(fin, "get_connection", lambda: Ctx(conn))
    good = SimpleNamespace(connected_balance=AsyncMock(return_value={"available": [], "pending": [], "payouts": []}))
    monkeypatch.setattr(fin, "get_cappe_stripe", lambda: good)
    assert asyncio.run(fin.payments_balance(SimpleNamespace(id=uuid4())))["connected"] is True
    bad = SimpleNamespace(connected_balance=AsyncMock(side_effect=stripe_connect.CappeStripeError("down")))
    monkeypatch.setattr(fin, "get_cappe_stripe", lambda: bad)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fin.payments_balance(SimpleNamespace(id=uuid4())))
    assert exc.value.status_code == 502


@pytest.mark.parametrize("full,fragment", [(True, "refunded your order: $12.00"), (False, "refunded part of your order: $12.00")])
def test_the_refund_email_says_how_much_and_links_the_order(monkeypatch, full, fragment):
    from app.cappe.services import email as mail
    sent = []

    async def _send(to, name, subject, html, text, *, label):
        sent.append((subject, html, text))

    monkeypatch.setattr(mail, "_send", _send)
    asyncio.run(mail.send_cappe_order_refunded_email(
        "b@example.com", "B", "Lumière <Spa>", 1200, "USD", full, "https://lumiere.gummfit.com/order/tok"))
    ((subject, html, text),) = sent
    assert subject == "Refund from Lumière <Spa>" and "Lumière &lt;Spa&gt;" in html
    assert fragment in text and "https://lumiere.gummfit.com/order/tok" in html
