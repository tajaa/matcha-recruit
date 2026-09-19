import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.cappe.models.shop import CappeCartItem
from app.cappe.models.shopper import SubscriptionCheckout
from app.cappe.services import recurring


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args):
        self.tasks.append((getattr(fn, "__name__", str(fn)), args))


class _CheckoutConn:
    def __init__(self, site, shopper, product, row):
        self.site, self.shopper, self.product, self.row = site, shopper, product, row
        self.calls = []

    def transaction(self):
        return _Tx()

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if "FROM cappe_accounts" in query:
            return {"stripe_account_id": "acct_owner", "stripe_charges_enabled": True, "plan": "business"}
        if "SELECT deleting" in query:
            return {"deleting": False}
        if "INSERT INTO cappe_shopper_subscriptions" in query:
            return self.row
        raise AssertionError(query)

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        if "FROM cappe_products" in query:
            return [self.product]
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        if "count(*)" in query:
            return 0
        return None

    async def execute(self, query, *args):
        self.calls.append((query, args))


@pytest.mark.asyncio
async def test_subscription_checkout_uses_connected_customer_fee_and_app_callback(monkeypatch):
    site_id, shopper_id, product_id, row_id = uuid4(), uuid4(), uuid4(), uuid4()
    site = {
        "id": site_id, "account_id": uuid4(), "tax_rate_bps": 0, "shipping_flat_cents": 0,
        "shipping_free_threshold_cents": None, "slug": "ahnimal", "subdomain": "ahnimal",
        "custom_domain": "ahnimal.gummfit.com",
    }
    shopper = {"id": shopper_id, "site_id": site_id, "email": "buyer@example.com"}
    product = {"id": product_id}
    row = {
        "id": row_id, "checkout_token": "a" * 32, "stripe_account_id": "acct_owner",
    }
    conn = _CheckoutConn(site, shopper, product, row)
    item = CappeCartItem(product_id=product_id, quantity=1)
    body = SubscriptionCheckout(
        items=[item], interval="month",
        success_url="https://ahnimal.gummfit.com/__cappe/app-return",
        cancel_url="https://ahnimal.gummfit.com/__cappe/app-return",
    )

    entitlement = SimpleNamespace(has=lambda key: key == "recurring_orders", platform_fee_bps=250)
    monkeypatch.setattr(recurring, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(recurring, "resolve_entitlements", lambda *_args, **_kwargs: _async(entitlement))
    monkeypatch.setattr(recurring, "require_can_sell", lambda _ent: None)
    monkeypatch.setattr(recurring, "fetch_option_groups", lambda *_args: _async({}))
    monkeypatch.setattr(recurring, "build_subscription_lines", lambda *_args: (
        [{"price_data": {"unit_amount": 1000}}],
        [{"product_id": str(product_id), "title": "Soap", "quantity": 1,
          "unit_price_cents": 1000, "fulfillment": "physical"}],
        {"subtotal_cents": 1000, "tax_cents": 0, "shipping_cents": 0,
         "total_cents": 1000, "currency": "USD"},
    ))
    monkeypatch.setattr(recurring, "connected_customer", lambda *_args: _async("cus_buyer"))
    stripe_calls = []

    class _Stripe:
        async def create_subscription_checkout(self, **kwargs):
            stripe_calls.append(kwargs)
            return {"id": "cs_sub", "url": "https://checkout.stripe.test/session"}

    monkeypatch.setattr(recurring, "get_cappe_stripe", lambda: _Stripe())
    result = await recurring.checkout(site, shopper, body)
    assert result["subscription_id"] == str(row_id)
    assert stripe_calls[0]["application_fee_percent"] == 2.5
    assert stripe_calls[0]["customer_id"] == "cus_buyer"
    assert stripe_calls[0]["success_url"].endswith(f"?o={'a' * 32}&r=success")
    assert stripe_calls[0]["collect_shipping"] is True
    assert any("stripe_checkout_session_id" in query for query, _ in conn.calls)


async def _async(value):
    return value


@pytest.mark.asyncio
async def test_checkout_rejects_foreign_returns_and_product_gate_branches():
    with pytest.raises(HTTPException) as caught:
        await recurring.checkout(
            {"id": uuid4(), "slug": "ahnimal", "subdomain": "ahnimal", "custom_domain": None},
            {"id": uuid4()},
            SubscriptionCheckout(
                items=[CappeCartItem(product_id=uuid4(), quantity=1)], interval="month",
                success_url="https://evil.test/return", cancel_url="https://evil.test/return",
            ),
        )
    assert caught.value.status_code == 422

    for product in (
        {"subscription_intervals": ["month"], "subscription_discount_bps": 0,
         "fulfillment": "service", "requires_approval": False},
        {"subscription_intervals": ["month"], "subscription_discount_bps": 0,
         "fulfillment": "physical", "requires_approval": True},
    ):
        with pytest.raises(HTTPException) as invalid:
            await recurring.validate_product_subscription(None, "business", product)
        assert invalid.value.status_code == 422


class _RecordConn:
    def __init__(self, row, *, short=True):
        self.row = row
        self.short = short
        self.calls = []

    def transaction(self):
        return _Tx()

    async def execute(self, query, *args):
        self.calls.append((query, args))

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if "FROM cappe_shoppers" in query:
            return {"email": "buyer@example.com", "name": "Buyer"}
        if "INSERT INTO cappe_orders" in query:
            return {"id": uuid4()}
        if "FROM cappe_shopper_subscriptions" in query:
            return self.row
        return None

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        if "SELECT id FROM cappe_products" in query:
            return args[0]
        if "SELECT EXISTS" in query:
            return self.short
        return None

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return []


def _subscription_row():
    product_id = uuid4()
    return {
        "id": uuid4(), "site_id": uuid4(), "shopper_id": uuid4(),
        "stripe_account_id": "acct_owner", "stripe_subscription_id": "sub_1",
        "stripe_checkout_session_id": "cs_1", "status": "active",
        "subtotal_cents": 1000, "tax_cents": 100, "shipping_cents": 200,
        "total_cents": 1300, "currency": "USD",
        "items": json.dumps([{
            "product_id": str(product_id), "title": "Soap", "unit_price_cents": 1000,
            "quantity": 1, "fulfillment": "physical", "selected_options": [],
            "selected_option_ids": [],
        }]),
    }


@pytest.mark.asyncio
async def test_invoice_order_is_idempotent_and_records_stock_shortfall(monkeypatch):
    row = _subscription_row()
    conn = _RecordConn(row)
    retaken = []

    async def retake(_conn, *, site_id, order_id):
        retaken.append((site_id, order_id))

    monkeypatch.setattr("app.cappe.services.inventory.retake_order_stock", retake)
    order_id, short = await recurring.record_invoice_order(
        conn, row, {"id": "in_1", "total": 1350, "customer_shipping": {"name": "Buyer"}},
    )
    assert order_id and short is True and retaken[0][0] == row["site_id"]
    assert any("stock_shortfall" in str(args) for query, args in conn.calls if "metadata=metadata" in query)

    duplicate = _RecordConn(row)
    original = duplicate.fetchrow

    async def no_insert(query, *args):
        if "INSERT INTO cappe_orders" in query:
            return None
        return await original(query, *args)

    duplicate.fetchrow = no_insert
    assert await recurring.record_invoice_order(duplicate, row, {"id": "in_1"}) == (None, False)


@pytest.mark.asyncio
async def test_subscription_webhooks_are_account_scoped_ordered_and_schedule_side_effects(monkeypatch):
    row = _subscription_row()
    conn = _RecordConn(row)
    monkeypatch.setattr(recurring, "get_connection", lambda: _Ctx(conn))
    synced = []

    async def sync(_conn, local, stripe_sub, event_at):
        synced.append((local["id"], stripe_sub["id"], stripe_sub["status"], event_at))

    async def record(_conn, local, invoice):
        return uuid4(), True

    class _Stripe:
        async def retrieve_connected_subscription(self, account, sub_id):
            assert (account, sub_id) == ("acct_owner", "sub_1")
            return {"id": "sub_1", "status": "active", "metadata": {
                "cappe_shopper_subscription_id": str(row["id"]),
            }}

    monkeypatch.setattr(recurring, "sync_subscription", sync)
    monkeypatch.setattr(recurring, "record_invoice_order", record)
    monkeypatch.setattr(recurring, "get_cappe_stripe", lambda: _Stripe())
    background = _Background()
    event = {"account": "acct_owner", "created": 1_700_000_000}
    invoice = {"id": "in_1", "subscription": "sub_1", "paid": True,
               "billing_reason": "subscription_cycle"}
    assert await recurring.handle_event("invoice.paid", invoice, event, background) == {"received": True}
    names = [name for name, _ in background.tasks]
    assert "issue_receipt_for_paid_order" in names and "notify_order_event" in names
    assert synced and synced[0][3].tzinfo is not None

    # Subscription update payloads can arrive out of order within the same
    # second. The handler must retrieve current Stripe state instead of applying
    # the stale event object.
    stale = {"id": "sub_1", "status": "past_due", "metadata": {
        "cappe_shopper_subscription_id": str(row["id"]),
    }}
    background.tasks.clear()
    await recurring.handle_event("customer.subscription.updated", stale, event, background)
    assert synced[-1][2] == "active"

    # A delayed failed invoice must not notify after Stripe has recovered.
    await recurring.handle_event(
        "invoice.payment_failed", {"id": "in_old", "subscription": "sub_1"}, event, background,
    )
    assert background.tasks == []

    conn.row = None
    background.tasks.clear()
    await recurring.handle_event("invoice.paid", invoice, event, background)
    assert background.tasks == []


@pytest.mark.asyncio
async def test_sync_cancel_resume_and_delete_paths(monkeypatch):
    row = _subscription_row()
    conn = _RecordConn(row)
    subscription = {
        "id": "sub_1", "status": "active", "cancel_at_period_end": True,
        "current_period_end": 1_800_000_000, "items": {"data": []},
    }
    await recurring.sync_subscription(conn, row, subscription, None)
    await recurring.sync_subscription(conn, row, subscription, SimpleNamespace())
    assert any("stripe_event_at=GREATEST" in query for query, _ in conn.calls)

    class _Stripe:
        async def modify_connected_subscription(self, **kwargs):
            assert kwargs["cancel_at_period_end"] is True
            return subscription

        async def expire_checkout_session(self, account, session):
            return "expired"

        async def cancel_connected_subscription(self, account, subscription_id):
            return {**subscription, "status": "canceled"}

    monkeypatch.setattr(recurring, "get_cappe_stripe", lambda: _Stripe())
    monkeypatch.setattr(recurring, "get_connection", lambda: _Ctx(conn))
    changed = await recurring.change_subscription(row, True)
    assert changed["cancel_at_period_end"] is True

    pending = {**row, "stripe_subscription_id": None}
    assert await recurring.change_subscription(pending, True) == {"status": "incomplete_expired"}
    pending["stripe_checkout_session_id"] = None
    assert await recurring.change_subscription(pending, True) == {"status": "incomplete_expired"}
    assert any("stripe_checkout_session_id IS NULL" in query for query, _ in conn.calls)

    await recurring.delete_shopper_subscriptions(
        {"id": row["site_id"]}, {"id": row["shopper_id"]},
    )
    assert any("deleting=TRUE" in query for query, _ in conn.calls)
