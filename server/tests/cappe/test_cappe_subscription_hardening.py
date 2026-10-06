"""Shopper subscriptions hardening — the 2026-10 commerce readiness review, PR 3.

What each block pins:

  * a renewal is recorded on every Stripe API version (`status == "paid"`,
    not the removed `paid` flag), with the payment intent that paid it and
    the fee Stripe took;
  * the platform fee is taken on the goods, not on tax and shipping;
  * the shopper is told when a subscription starts, when a renewal fails
    (once per invoice) and when it ends (once); the owner hears of renewals;
  * deleting a site cancels its subscriptions at Stripe first, and refuses
    to delete if it can't;
  * archiving or deleting a subscribed product needs the owner's say-so;
  * a shopper can list and cancel while the store is unpublished;
  * the owner's list names the customer and hides abandoned checkouts;
  * a default address reaches the Stripe customer that renewals ship to;
  * sign-in codes have their own email budget.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_subscription_hardening.py -q
"""
import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe import dependencies as deps  # noqa: E402
from app.cappe.routes import shop as shop_mod  # noqa: E402
from app.cappe.routes import shopper_subscriptions as sub_routes  # noqa: E402
from app.cappe.routes import sites as sites_mod  # noqa: E402
from app.cappe.routes.public import shopper as shopper_routes  # noqa: E402
from app.cappe.services import commerce  # noqa: E402
from app.cappe.services import email as mail  # noqa: E402
from app.cappe.services import recurring  # noqa: E402
from app.cappe.services import stripe_connect  # noqa: E402

SITE, SUB, SHOPPER, PRODUCT = uuid4(), uuid4(), uuid4(), uuid4()
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


class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn.__name__, args))

    def names(self):
        return [name for name, _a in self.tasks]


def _sub_row(**kw):
    return {
        "id": SUB, "site_id": SITE, "shopper_id": SHOPPER, "stripe_account_id": "acct_owner",
        "stripe_subscription_id": "sub_1", "stripe_checkout_session_id": "cs_1", "status": "active",
        "interval": "month", "subtotal_cents": 2000, "tax_cents": 160, "shipping_cents": 500,
        "total_cents": 2660, "currency": "USD",
        "items": json.dumps([{"product_id": str(PRODUCT), "title": "Coffee beans", "unit_price_cents": 2000,
                              "quantity": 1, "fulfillment": "physical", "selected_options": [],
                              "selected_option_ids": []}]),
        **kw,
    }


# ── paid, on every API version ───────────────────────────────────────────────

@pytest.mark.parametrize("invoice,paid", [
    ({"status": "paid"}, True),                       # current API versions
    ({"paid": True, "status": "paid"}, True),          # older ones
    ({"paid": True}, True),
    ({"status": "open"}, False),
    ({}, False),
])
def test_an_invoice_is_paid_on_any_api_version(invoice, paid):
    assert recurring.invoice_is_paid(invoice) is paid


@pytest.mark.parametrize("bps,subtotal,total,pct", [
    (200, 2000, 2660, 1.5),      # 2% of goods, expressed against the whole invoice
    (200, 2000, 2000, 2.0),      # nothing but goods
    (150, 1000, 1500, 1.0),
    (0, 2000, 2660, 0.0),
    (200, 0, 500, 0.0),
])
def test_the_subscription_fee_is_taken_on_the_goods(bps, subtotal, total, pct):
    assert recurring.goods_fee_percent(bps, subtotal, total) == pct


def test_a_renewal_order_keeps_its_payment_intent_and_fee():
    conn = SqlConn([
        ("FROM cappe_shoppers", {"email": "buyer@example.com", "name": "Buyer"}),
        ("INSERT INTO cappe_orders", {"id": uuid4()}),
        ("SELECT id FROM cappe_products", PRODUCT),
        ("SELECT EXISTS", False),
    ])
    import app.cappe.services.inventory as inv
    original = inv.retake_order_stock
    inv.retake_order_stock = AsyncMock()
    try:
        order_id, short = asyncio.run(recurring.record_invoice_order(
            conn, _sub_row(), {"id": "in_1", "total": 2660, "application_fee_amount": 40}, "pi_9",
        ))
    finally:
        inv.retake_order_stock = original
    assert order_id and short is False
    (_, sql, args), = conn.sql("INSERT INTO cappe_orders")
    assert "stripe_payment_intent,payment_ref,platform_fee_cents" in sql
    assert args[12] == "pi_9" and args[13] == 40


# ── finding the payment intent ───────────────────────────────────────────────

def test_the_intent_comes_from_the_invoice_on_older_api_versions():
    cs = stripe_connect.CappeStripe.__new__(stripe_connect.CappeStripe)
    assert asyncio.run(cs.connected_invoice_payment_intent("acct_1", {"id": "in_1", "payment_intent": "pi_old"})) == "pi_old"
    assert asyncio.run(cs.connected_invoice_payment_intent("acct_1", {"id": "in_1", "payment_intent": {"id": "pi_x"}})) == "pi_x"


def test_the_intent_comes_from_invoice_payments_on_current_versions(monkeypatch):
    cs = stripe_connect.CappeStripe.__new__(stripe_connect.CappeStripe)
    monkeypatch.setattr(cs, "_ensure_key", lambda: None, raising=False)
    seen = {}

    class InvoicePayment:
        @staticmethod
        def list(**kw):
            seen.update(kw)
            return {"data": [
                {"status": "open", "payment": {"payment_intent": "pi_open"}},
                {"status": "paid", "payment": {"payment_intent": "pi_paid"}},
            ]}

    monkeypatch.setattr(stripe_connect.stripe, "InvoicePayment", InvoicePayment, raising=False)
    assert asyncio.run(cs.connected_invoice_payment_intent("acct_1", {"id": "in_1"})) == "pi_paid"
    assert seen["stripe_account"] == "acct_1" and seen["invoice"] == "in_1"


def test_a_stripe_error_finding_the_intent_does_not_lose_the_order(monkeypatch):
    cs = stripe_connect.CappeStripe.__new__(stripe_connect.CappeStripe)
    monkeypatch.setattr(cs, "_ensure_key", lambda: None, raising=False)

    class InvoicePayment:
        @staticmethod
        def list(**kw):
            raise RuntimeError("stripe down")

    monkeypatch.setattr(stripe_connect.stripe, "InvoicePayment", InvoicePayment, raising=False)
    assert asyncio.run(cs.connected_invoice_payment_intent("acct_1", {"id": "in_1"})) is None


# ── the emails a subscription owes ───────────────────────────────────────────

class _Stripe:
    def __init__(self, status="active"):
        self.status = status

    async def retrieve_connected_subscription(self, account, sid):
        return {"id": "sub_1", "status": self.status,
                "metadata": {"cappe_shopper_subscription_id": str(SUB)}}

    async def connected_invoice_payment_intent(self, account, invoice):
        return "pi_new"


def _wire_events(monkeypatch, *, notify_update=SUB, stripe_status="active", row=None):
    conn = SqlConn([
        ("FROM cappe_shopper_subscriptions sub JOIN", row or _sub_row()),
        ("failure_notified_invoice_id", notify_update),
        ("cancel_notified_at", notify_update),
        ("FROM cappe_sites s JOIN cappe_accounts a", {
            "site_name": "Roastery", "owner_email": "owner@example.com", "owner_name": "Owner",
            "shopper_email": "buyer@example.com", "shopper_name": "Buyer",
        }),
    ])
    monkeypatch.setattr(recurring, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(recurring, "get_cappe_stripe", lambda: _Stripe(stripe_status))
    monkeypatch.setattr(recurring, "sync_subscription", AsyncMock())
    recorded = AsyncMock(return_value=(uuid4(), False))
    monkeypatch.setattr(recurring, "record_invoice_order", recorded)
    return conn, recorded


EVENT = {"account": "acct_owner", "created": 1_800_000_000}


def test_a_first_payment_records_the_order_and_tells_both_sides(monkeypatch):
    _conn, recorded = _wire_events(monkeypatch)
    bg = Background()
    invoice = {"id": "in_1", "subscription": "sub_1", "status": "paid", "billing_reason": "subscription_create", "total": 2660}
    asyncio.run(recurring.handle_event("invoice.paid", invoice, EVENT, bg))
    assert recorded.await_args.args[3] == "pi_new"
    assert {"send_cappe_order_alert_email", "send_cappe_subscription_started_email",
            "issue_receipt_for_paid_order"} <= set(bg.names())
    started = dict(bg.tasks)["send_cappe_subscription_started_email"]
    assert started[0] == "buyer@example.com" and started[3] == "1× Coffee beans" and started[6] == "month"


def test_a_renewal_alerts_the_owner_but_does_not_re_announce_the_subscription(monkeypatch):
    _wire_events(monkeypatch)
    bg = Background()
    invoice = {"id": "in_2", "subscription": "sub_1", "status": "paid", "billing_reason": "subscription_cycle"}
    asyncio.run(recurring.handle_event("invoice.paid", invoice, EVENT, bg))
    assert "send_cappe_order_alert_email" in bg.names()
    assert "send_cappe_subscription_started_email" not in bg.names()


def test_an_unpaid_invoice_event_records_nothing(monkeypatch):
    _conn, recorded = _wire_events(monkeypatch)
    asyncio.run(recurring.handle_event(
        "invoice.paid", {"id": "in_3", "subscription": "sub_1", "status": "open", "billing_reason": "subscription_cycle"},
        EVENT, Background(),
    ))
    recorded.assert_not_awaited()


@pytest.mark.parametrize("first_time", [True, False])
def test_a_failed_renewal_is_told_once_per_invoice(monkeypatch, first_time):
    conn, _recorded = _wire_events(monkeypatch, notify_update=SUB if first_time else None, stripe_status="past_due")
    bg = Background()
    asyncio.run(recurring.handle_event("invoice.payment_failed", {"id": "in_4", "subscription": "sub_1"}, EVENT, bg))
    (_, sql, args), = conn.sql("failure_notified_invoice_id")
    assert "IS DISTINCT FROM $2" in sql and args == (SUB, "in_4")
    if first_time:
        assert set(bg.names()) == {"send_cappe_subscription_payment_failed_email", "send_to_shopper"}
    else:
        assert bg.tasks == []


@pytest.mark.parametrize("first_time", [True, False])
def test_an_ended_subscription_is_told_once(monkeypatch, first_time):
    _wire_events(monkeypatch, notify_update=SUB if first_time else None)
    bg = Background()
    deleted = {"id": "sub_1", "status": "canceled", "metadata": {"cappe_shopper_subscription_id": str(SUB)}}
    asyncio.run(recurring.handle_event("customer.subscription.deleted", deleted, EVENT, bg))
    assert bg.names() == (["send_cappe_subscription_cancelled_email"] if first_time else [])


@pytest.mark.parametrize("sender,fragment", [
    ("send_cappe_subscription_started_email", "has started"),
    ("send_cappe_subscription_payment_failed_email", "couldn't charge your card"),
    ("send_cappe_subscription_cancelled_email", "has ended"),
])
def test_the_subscription_emails_escape_and_say_what_happened(monkeypatch, sender, fragment):
    sent = []

    async def _send(to, name, subject, html, text, **kw):
        sent.append((subject, html, text))
        return True

    monkeypatch.setattr(mail, "_send", _send)
    args = ["buyer@example.com", "Buyer", "<b>Roast</b>", "Beans × 2"]
    if sender == "send_cappe_subscription_started_email":
        args += [2660, "USD", "month"]
    asyncio.run(getattr(mail, sender)(*args))
    (subject, html, text), = sent
    assert fragment in html and fragment in text
    assert "<b>Roast</b>" not in html and "&lt;b&gt;Roast&lt;/b&gt;" in html
    if sender == "send_cappe_subscription_started_email":
        assert "$26.60 every month" in text


# ── deleting a site ──────────────────────────────────────────────────────────

def test_a_sites_subscriptions_are_cancelled_now_at_stripe(monkeypatch):
    rows = [_sub_row(), _sub_row(id=uuid4())]
    monkeypatch.setattr(recurring, "get_connection", lambda: Ctx(SqlConn([("FROM cappe_shopper_subscriptions", rows)])))
    changed = AsyncMock()
    monkeypatch.setattr(recurring, "change_subscription", changed)
    assert asyncio.run(recurring.cancel_site_subscriptions(SITE)) == 2
    assert [c.args[1] for c in changed.await_args_list] == [True, True]
    assert all(c.kwargs == {"immediate": True} for c in changed.await_args_list)


def test_a_site_whose_subscriptions_cant_be_cancelled_is_not_deleted(monkeypatch):
    conn = SqlConn([("SELECT * FROM cappe_sites", {"id": SITE})])
    monkeypatch.setattr(sites_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(sites_mod, "get_owned_site", AsyncMock(return_value={"id": SITE}))
    monkeypatch.setattr(recurring, "cancel_site_subscriptions",
                        AsyncMock(side_effect=HTTPException(503, "Subscription update could not be confirmed")))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(sites_mod.delete_site(SITE, Background(), account=ACCOUNT))
    assert exc.value.status_code == 409 and "nobody keeps being charged" in exc.value.detail
    assert not conn.sql("DELETE FROM cappe_sites")


def test_a_site_deletes_once_its_subscriptions_are_cancelled(monkeypatch):
    conn = SqlConn()
    monkeypatch.setattr(sites_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(sites_mod, "get_owned_site", AsyncMock(return_value={"id": SITE}))
    monkeypatch.setattr(sites_mod, "invalidate_render_cache", AsyncMock())
    cancel = AsyncMock(return_value=1)
    monkeypatch.setattr(recurring, "cancel_site_subscriptions", cancel)
    asyncio.run(sites_mod.delete_site(SITE, Background(), account=ACCOUNT))
    cancel.assert_awaited_once_with(SITE)
    assert conn.sql("DELETE FROM cappe_sites")


# ── a subscribed product leaving the shop ────────────────────────────────────

def _wire_guard(monkeypatch, rows):
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(SqlConn([("FROM cappe_shopper_subscriptions", rows)])))
    ended = AsyncMock()
    monkeypatch.setattr(recurring, "end_subscriptions_at_period_end", ended)
    return ended


def test_archiving_a_subscribed_product_needs_the_owners_say_so(monkeypatch):
    ended = _wire_guard(monkeypatch, [_sub_row(), _sub_row(id=uuid4())])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(shop_mod._guard_subscribers(SITE, PRODUCT, False))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "has_subscriptions" and exc.value.detail["count"] == 2
    ended.assert_not_awaited()


def test_with_the_owners_say_so_the_subscriptions_stop_after_the_paid_period(monkeypatch):
    rows = [_sub_row()]
    ended = _wire_guard(monkeypatch, rows)
    asyncio.run(shop_mod._guard_subscribers(SITE, PRODUCT, True))
    ended.assert_awaited_once_with(rows)


def test_a_product_nobody_subscribes_to_leaves_freely(monkeypatch):
    ended = _wire_guard(monkeypatch, [])
    asyncio.run(shop_mod._guard_subscribers(SITE, PRODUCT, False))
    ended.assert_not_awaited()


def test_live_subscriptions_are_found_by_product_inside_their_items():
    conn = SqlConn()
    asyncio.run(recurring.live_subscriptions_for_product(conn, SITE, PRODUCT))
    _, sql, args = conn.calls[0]
    assert "items @> jsonb_build_array(jsonb_build_object('product_id', $2::text))" in sql
    assert "status NOT IN ('canceled','incomplete_expired')" in sql and args == (SITE, str(PRODUCT))


def test_ending_at_period_end_does_not_cancel_now(monkeypatch):
    changed = AsyncMock()
    monkeypatch.setattr(recurring, "change_subscription", changed)
    asyncio.run(recurring.end_subscriptions_at_period_end([_sub_row()]))
    assert changed.await_args.args[1] is True and changed.await_args.kwargs == {}


@pytest.mark.parametrize("status_new,guarded", [("archived", True), ("draft", True), ("active", False), (None, False)])
def test_only_taking_a_product_off_sale_is_guarded(monkeypatch, status_new, guarded):
    from app.cappe.models.shop import CappeProductUpdate

    guard = AsyncMock(side_effect=HTTPException(409, "stop here"))
    monkeypatch.setattr(shop_mod, "_guard_subscribers", guard)
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(SqlConn([("SELECT * FROM cappe_products", None)])))
    monkeypatch.setattr(shop_mod, "get_owned_site", AsyncMock())
    body = CappeProductUpdate(**({"status": status_new} if status_new else {"name": "x"}))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(shop_mod.update_product(SITE, PRODUCT, body, account=ACCOUNT, end_subscriptions=False))
    assert (exc.value.detail == "stop here") is guarded


# ── getting out while the store is closed ────────────────────────────────────

def test_a_shopper_session_works_on_an_unpublished_store(monkeypatch):
    site = {"id": SITE, "status": "draft", "slug": "roastery"}
    conn = SqlConn([("FROM cappe_sites WHERE slug", site)])
    monkeypatch.setattr(deps, "get_connection", lambda: Ctx(conn))
    from app.cappe.services import shopper_auth
    monkeypatch.setattr(shopper_auth, "resolve_shopper", AsyncMock(return_value=({"id": SHOPPER}, {})))
    got_site, shopper = asyncio.run(deps.require_shopper_session("roastery", SimpleNamespace(credentials="tok")))
    assert got_site["id"] == SITE and shopper["id"] == SHOPPER
    # No publish / owner / plan condition — only the slug.
    assert "status" not in conn.calls[0][1]


def test_a_shopper_session_still_needs_a_token_and_a_real_store(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(deps.require_shopper_session("roastery", None))
    assert exc.value.status_code == 401
    monkeypatch.setattr(deps, "get_connection", lambda: Ctx(SqlConn()))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(deps.require_shopper_session("gone", SimpleNamespace(credentials="tok")))
    assert exc.value.status_code == 404


def test_listing_and_cancelling_use_the_lenient_session_but_resume_does_not():
    import inspect

    def dep(fn):
        return inspect.signature(fn).parameters["context"].default.dependency

    assert dep(sub_routes.list_mine) is deps.require_shopper_session
    assert dep(sub_routes.cancel_mine) is deps.require_shopper_session
    assert dep(sub_routes.resume_mine) is deps.require_shopper
    assert dep(sub_routes.checkout) is deps.require_shopper


# ── the owner's view ─────────────────────────────────────────────────────────

def _wire_owner(monkeypatch, row=None):
    conn = SqlConn([("SELECT * FROM cappe_shopper_subscriptions", row)])
    monkeypatch.setattr(sub_routes, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(sub_routes, "get_owned_site", AsyncMock())
    return conn


@pytest.mark.parametrize("include,abandoned_filter", [(False, True), (True, False)])
def test_the_owners_list_names_the_customer_and_hides_abandoned_checkouts(monkeypatch, include, abandoned_filter):
    conn = _wire_owner(monkeypatch)
    asyncio.run(sub_routes.list_owned(SITE, limit=50, offset=0, include_abandoned=include, account=ACCOUNT))
    _, sql, args = conn.calls[0]
    assert "sh.email AS customer_email" in sql and "AS order_count" in sql and "AS last_order_at" in sql
    assert ("sub.status <> ALL($4::text[])" in sql) is abandoned_filter
    if abandoned_filter:
        assert set(args[3]) == {"preparing", "incomplete", "cancel_requested", "incomplete_expired"}


def test_the_owner_can_end_now_or_at_period_end_and_resume(monkeypatch):
    _wire_owner(monkeypatch, row=_sub_row())
    changed = AsyncMock(return_value={"status": "active"})
    monkeypatch.setattr(recurring, "change_subscription", changed)
    asyncio.run(sub_routes.cancel_owned(SITE, SUB, immediate=True, account=ACCOUNT))
    asyncio.run(sub_routes.cancel_owned(SITE, SUB, immediate=False, account=ACCOUNT))
    asyncio.run(sub_routes.resume_owned(SITE, SUB, account=ACCOUNT))
    assert [(c.args[1], c.kwargs.get("immediate")) for c in changed.await_args_list] == [
        (True, True), (True, False), (False, None),
    ]


def test_another_sites_subscription_is_a_404(monkeypatch):
    _wire_owner(monkeypatch, row=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(sub_routes.resume_owned(SITE, SUB, account=ACCOUNT))
    assert exc.value.status_code == 404


# ── addresses and sign-in codes ──────────────────────────────────────────────

def test_a_default_address_reaches_the_stripe_customer(monkeypatch):
    monkeypatch.setattr(shopper_routes, "get_connection", lambda: Ctx(SqlConn([("stripe_account_id", "acct_owner")])))
    from app.cappe.services import shopper_customers
    pushed = AsyncMock()
    monkeypatch.setattr(shopper_customers, "connected_customer", pushed)
    shopper = {"id": SHOPPER, "site_id": SITE, "stripe_customer_id": "cus_1"}
    asyncio.run(shopper_routes.push_default_address({"id": SITE, "account_id": uuid4()}, shopper))
    pushed.assert_awaited_once_with(shopper, "acct_owner")


def test_a_shopper_without_a_stripe_customer_is_left_alone(monkeypatch):
    from app.cappe.services import shopper_customers
    pushed = AsyncMock()
    monkeypatch.setattr(shopper_customers, "connected_customer", pushed)
    asyncio.run(shopper_routes.push_default_address({"id": SITE, "account_id": uuid4()}, {"id": SHOPPER}))
    pushed.assert_not_awaited()


def test_a_stripe_failure_on_the_address_push_is_swallowed(monkeypatch):
    monkeypatch.setattr(shopper_routes, "get_connection", lambda: Ctx(SqlConn([("stripe_account_id", "acct_owner")])))
    from app.cappe.services import shopper_customers
    monkeypatch.setattr(shopper_customers, "connected_customer",
                        AsyncMock(side_effect=stripe_connect.CappeStripeError("down")))
    asyncio.run(shopper_routes.push_default_address({"id": SITE, "account_id": uuid4()},
                                                    {"id": SHOPPER, "stripe_customer_id": "cus_1"}))


def test_sign_in_codes_have_their_own_email_budget(monkeypatch):
    calls = []

    async def _limit(key, bucket, limit, window):
        calls.append((bucket, limit))

    monkeypatch.setattr(commerce, "check_rate_limit", _limit)
    assert asyncio.run(commerce.check_recipient_send_ok("buyer@example.com")) is True
    assert asyncio.run(commerce.check_recipient_send_ok("buyer@example.com", bucket="cappe_shopper_code_email", limit=8))
    assert calls == [("cappe_recipient_email", 5), ("cappe_shopper_code_email", 8)]
