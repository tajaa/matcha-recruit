import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.cappe.models.shop import CappeCartItem
from app.cappe.models.shopper import CartQuoteRequest, SubscriptionCheckout
from app.cappe.routes.public import shop as public_shop
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
    def __init__(self, site, shopper, product, row, *, discounts=None):
        self.site, self.shopper, self.product, self.row = site, shopper, product, row
        self.discounts = discounts or []
        self.deleting = False
        self.calls = []

    def transaction(self):
        return _Tx()

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if "FROM cappe_accounts" in query:
            return {"stripe_account_id": "acct_owner", "stripe_charges_enabled": True, "plan": "business"}
        if "tax_rate_bps" in query:
            return {
                "tax_rate_bps": self.site["tax_rate_bps"],
                "shipping_flat_cents": self.site["shipping_flat_cents"],
                "shipping_free_threshold_cents": self.site["shipping_free_threshold_cents"],
            }
        if "SELECT deleting" in query:
            return {"deleting": self.deleting}
        if "SELECT status,stripe_checkout_session_id" in query:
            return {
                "status": self.row["status"],
                "stripe_checkout_session_id": self.row.get("stripe_checkout_session_id"),
                "stripe_subscription_id": self.row.get("stripe_subscription_id"),
            }
        if "SELECT sub.*" in query:
            return {**self.row, "preparation_stale": self.row.get("preparation_stale", False)}
        if "UPDATE cappe_shopper_subscriptions" in query and "RETURNING *" in query:
            if "cancel_requested" in query:
                self.row["status"] = "cancel_requested"
            elif "incomplete_expired" in query:
                self.row["status"] = "incomplete_expired"
            return dict(self.row)
        if "INSERT INTO cappe_shopper_subscriptions" in query:
            self.row["status"] = "preparing"
            self.row.update(
                interval=args[3], items=args[4], subtotal_cents=args[5],
                tax_cents=args[6], shipping_cents=args[7],
                total_cents=args[8], currency=args[9],
            )
            return self.row
        raise AssertionError(query)

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        if "FROM cappe_products" in query:
            return [self.product]
        if "FROM cappe_discounts" in query:
            return self.discounts
        if "FROM cappe_shopper_subscriptions" in query:
            return [dict(self.row)]
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        if "SELECT NOW()" in query:
            return datetime(2026, 9, 19, tzinfo=timezone.utc)
        if "count(*)" in query:
            return 0
        if "SET status='incomplete'" in query and self.row["status"] == "preparing":
            self.row["status"] = "incomplete"
            return self.row["id"]
        return None

    async def execute(self, query, *args):
        self.calls.append((query, args))
        if "SET stripe_checkout_session_id" in query:
            self.row["stripe_checkout_session_id"] = args[1]
        elif "SET status='cancel_requested'" in query:
            self.row["status"] = "cancel_requested"
        elif "SET status='incomplete_expired'" in query:
            self.row["status"] = "incomplete_expired"
        elif "SET deleting=TRUE" in query:
            self.deleting = True


class _RollbackTx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.row = dict(self.conn.row)
        self.deleting = self.conn.deleting
        return self

    async def __aexit__(self, exc_type, *_args):
        if exc_type is not None:
            self.conn.row.clear()
            self.conn.row.update(self.row)
            self.conn.deleting = self.deleting
        return False


class _CancelConn:
    """Stateful subscription fake whose transactions really roll back."""

    def __init__(self, row, *, snapshot=None):
        self.row = dict(row)
        self.snapshot = dict(snapshot) if snapshot is not None else None
        self.deleting = False
        self.calls = []

    def transaction(self):
        return _RollbackTx(self)

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if "SELECT sub.*" in query:
            return {**self.row, "preparation_stale": self.row.get("preparation_stale", False)}
        if "UPDATE cappe_shopper_subscriptions" in query and "RETURNING *" in query:
            if "cancel_requested" in query:
                self.row["status"] = "cancel_requested"
            elif "incomplete_expired" in query:
                self.row["status"] = "incomplete_expired"
            return dict(self.row)
        raise AssertionError(query)

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        if "FROM cappe_shopper_subscriptions" in query:
            row = self.snapshot if self.snapshot is not None else self.row
            return [] if row["status"] in ("canceled", "incomplete_expired") else [dict(row)]
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        if "SELECT id FROM cappe_shopper_subscriptions" in query:
            return self.row["id"]
        raise AssertionError(query)

    async def execute(self, query, *args):
        self.calls.append((query, args))
        if "SET deleting=TRUE" in query:
            self.deleting = True
        elif "SET stripe_subscription_id=$2,status=$3" in query:
            self.row["stripe_subscription_id"] = args[1]
            self.row["status"] = args[2]
            self.row["cancel_at_period_end"] = args[3]
        elif "SET status='incomplete_expired'" in query:
            self.row["status"] = "incomplete_expired"
        elif "SET status='cancel_requested'" in query:
            self.row["status"] = "cancel_requested"


@pytest.mark.asyncio
async def test_subscription_checkout_uses_connected_customer_fee_and_app_callback(monkeypatch):
    site_id, shopper_id, product_id, row_id = uuid4(), uuid4(), uuid4(), uuid4()
    site = {
        "id": site_id, "account_id": uuid4(), "tax_rate_bps": 0, "shipping_flat_cents": 0,
        "shipping_free_threshold_cents": None, "slug": "ahnimal", "subdomain": "ahnimal",
        "custom_domain": "ahnimal.gummfit.com", "timezone": "UTC",
    }
    shopper = {"id": shopper_id, "site_id": site_id, "email": "buyer@example.com"}
    product = {"id": product_id}
    row = {
        "id": row_id, "checkout_token": "a" * 32, "stripe_account_id": "acct_owner",
        "site_id": site_id, "shopper_id": shopper_id, "status": "preparing",
        "stripe_checkout_session_id": None, "stripe_subscription_id": None,
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
    assert conn.row["stripe_checkout_session_id"] == "cs_sub"
    assert conn.row["status"] == "incomplete"


@pytest.mark.asyncio
async def test_subscription_checkout_charges_the_promotional_quote_amount(monkeypatch):
    site_id, shopper_id, product_id, row_id = uuid4(), uuid4(), uuid4(), uuid4()
    site = {
        "id": site_id, "account_id": uuid4(), "tax_rate_bps": 1000,
        "shipping_flat_cents": 500, "shipping_free_threshold_cents": 2000,
        "slug": "ahnimal", "subdomain": "ahnimal",
        "custom_domain": "ahnimal.gummfit.com", "timezone": "America/Los_Angeles",
    }
    shopper = {"id": shopper_id, "site_id": site_id, "email": "buyer@example.com"}
    product = {
        "id": product_id, "name": "Sale soap", "price_cents": 1000,
        "currency": "USD", "inventory": 10, "status": "active",
        "fulfillment": "physical", "requires_approval": False,
        "subscription_intervals": ["month"], "subscription_discount_bps": 1000,
    }
    row = {
        "id": row_id, "checkout_token": "b" * 32, "stripe_account_id": "acct_owner",
        "site_id": site_id, "shopper_id": shopper_id, "status": "preparing",
        "stripe_checkout_session_id": None, "stripe_subscription_id": None,
    }
    discounts = [{
        "percent_off": 20, "scope": "product", "target_id": product_id,
        # 2026-09-19 00:00 UTC is still 2026-09-18 at the site.
        "active": True, "starts_on": date(2026, 9, 18), "ends_on": date(2026, 9, 18),
    }]
    conn = _CheckoutConn(site, shopper, product, row, discounts=discounts)
    body = SubscriptionCheckout(
        items=[CappeCartItem(product_id=product_id, quantity=1)], interval="month",
        success_url="https://ahnimal.gummfit.com/__cappe/app-return",
        cancel_url="https://ahnimal.gummfit.com/__cappe/app-return",
    )
    entitlement = SimpleNamespace(has=lambda key: key == "recurring_orders", platform_fee_bps=250)
    monkeypatch.setattr(public_shop, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(public_shop, "_published_site", lambda *_args: _async(site))
    monkeypatch.setattr(public_shop, "_read_rate_limit", lambda *_args: _async(None))
    monkeypatch.setattr(public_shop, "fetch_option_groups", lambda *_args: _async({}))
    monkeypatch.setattr(recurring, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(recurring, "resolve_entitlements", lambda *_args, **_kwargs: _async(entitlement))
    monkeypatch.setattr(recurring, "require_can_sell", lambda _ent: None)
    monkeypatch.setattr(recurring, "fetch_option_groups", lambda *_args: _async({}))
    monkeypatch.setattr(recurring, "connected_customer", lambda *_args: _async("cus_buyer"))
    stripe_calls = []

    class _Stripe:
        async def create_subscription_checkout(self, **kwargs):
            stripe_calls.append(kwargs)
            return {"id": "cs_sale", "url": "https://checkout.stripe.test/sale"}

    monkeypatch.setattr(recurring, "get_cappe_stripe", lambda: _Stripe())
    request = Request({
        "type": "http", "method": "POST", "path": "/", "headers": [],
        "client": ("127.0.0.1", 1234),
    })
    quote = await public_shop.quote(
        "ahnimal", CartQuoteRequest(items=body.items, interval="month"), request,
    )
    await recurring.checkout(site, shopper, body)

    # 20% active promotion, then the product's 10% subscription discount,
    # followed by physical-goods tax and shipping.
    assert quote == {
        "lines": [{
            "product_id": str(product_id), "quantity": 1,
            "unit_price_cents": 720, "available": True,
            "fulfillment": "physical", "selected_options": [],
            "title": "Sale soap", "selected_option_ids": [],
        }],
        "subtotal_cents": 720, "tax_cents": 72, "shipping_cents": 500,
        "total_cents": 1292, "currency": "USD",
    }
    billed = sum(
        line["price_data"]["unit_amount"] * line["quantity"]
        for line in stripe_calls[0]["line_items"]
    )
    assert billed == quote["total_cents"]
    assert {
        key: conn.row[key]
        for key in ("subtotal_cents", "tax_cents", "shipping_cents", "total_cents", "currency")
    } == {
        key: quote[key]
        for key in ("subtotal_cents", "tax_cents", "shipping_cents", "total_cents", "currency")
    }


@pytest.mark.asyncio
async def test_checkout_compensates_cancellation_that_wins_during_stripe_creation(monkeypatch):
    site_id, shopper_id, product_id, row_id = uuid4(), uuid4(), uuid4(), uuid4()
    site = {
        "id": site_id, "account_id": uuid4(), "tax_rate_bps": 0,
        "shipping_flat_cents": 0, "shipping_free_threshold_cents": None,
        "slug": "ahnimal", "subdomain": "ahnimal", "custom_domain": "ahnimal.gummfit.com",
        "timezone": "UTC",
    }
    shopper = {"id": shopper_id, "site_id": site_id, "email": "buyer@example.com"}
    product = {
        "id": product_id, "name": "Soap", "price_cents": 1000, "currency": "USD",
        "inventory": 10, "status": "active", "fulfillment": "physical",
        "requires_approval": False, "subscription_intervals": ["month"],
        "subscription_discount_bps": 0,
    }
    row = {
        "id": row_id, "checkout_token": "c" * 32, "stripe_account_id": "acct_owner",
        "site_id": site_id, "shopper_id": shopper_id, "status": "preparing",
        "stripe_checkout_session_id": None, "stripe_subscription_id": None,
    }
    conn = _CheckoutConn(site, shopper, product, row)
    body = SubscriptionCheckout(
        items=[CappeCartItem(product_id=product_id, quantity=1)], interval="month",
        success_url="https://ahnimal.gummfit.com/__cappe/app-return",
        cancel_url="https://ahnimal.gummfit.com/__cappe/app-return",
    )
    entitlement = SimpleNamespace(has=lambda key: key == "recurring_orders", platform_fee_bps=250)
    monkeypatch.setattr(recurring, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(recurring, "resolve_entitlements", lambda *_args, **_kwargs: _async(entitlement))
    monkeypatch.setattr(recurring, "require_can_sell", lambda _ent: None)
    monkeypatch.setattr(recurring, "fetch_option_groups", lambda *_args: _async({}))
    monkeypatch.setattr(recurring, "connected_customer", lambda *_args: _async("cus_buyer"))
    expired = []

    class _Stripe:
        async def create_subscription_checkout(self, **_kwargs):
            # A concurrent account deletion claims this row while Stripe is in flight.
            conn.deleting = True
            conn.row["status"] = "cancel_requested"
            return {"id": "cs_race", "url": "https://checkout.stripe.test/race"}

        async def expire_checkout_session(self, account, session):
            expired.append((account, session))
            return "expired"

    monkeypatch.setattr(recurring, "get_cappe_stripe", lambda: _Stripe())
    with pytest.raises(HTTPException) as caught:
        await recurring.checkout(site, shopper, body)

    assert caught.value.status_code == 409
    assert expired == [("acct_owner", "cs_race")]
    assert conn.row["stripe_checkout_session_id"] == "cs_race"
    assert conn.row["status"] == "incomplete_expired"


@pytest.mark.asyncio
async def test_failed_checkout_compensation_keeps_session_retryable(monkeypatch):
    site_id, shopper_id, product_id, row_id = uuid4(), uuid4(), uuid4(), uuid4()
    site = {
        "id": site_id, "account_id": uuid4(), "tax_rate_bps": 0,
        "shipping_flat_cents": 0, "shipping_free_threshold_cents": None,
        "slug": "ahnimal", "subdomain": "ahnimal", "custom_domain": "ahnimal.gummfit.com",
        "timezone": "UTC",
    }
    shopper = {"id": shopper_id, "site_id": site_id, "email": "buyer@example.com"}
    product = {
        "id": product_id, "name": "Soap", "price_cents": 1000, "currency": "USD",
        "inventory": 10, "status": "active", "fulfillment": "physical",
        "requires_approval": False, "subscription_intervals": ["month"],
        "subscription_discount_bps": 0,
    }
    row = {
        "id": row_id, "checkout_token": "d" * 32, "stripe_account_id": "acct_owner",
        "site_id": site_id, "shopper_id": shopper_id, "status": "preparing",
        "stripe_checkout_session_id": None, "stripe_subscription_id": None,
    }
    conn = _CheckoutConn(site, shopper, product, row)
    body = SubscriptionCheckout(
        items=[CappeCartItem(product_id=product_id, quantity=1)], interval="month",
        success_url="https://ahnimal.gummfit.com/__cappe/app-return",
        cancel_url="https://ahnimal.gummfit.com/__cappe/app-return",
    )
    entitlement = SimpleNamespace(has=lambda key: key == "recurring_orders", platform_fee_bps=250)
    monkeypatch.setattr(recurring, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(recurring, "resolve_entitlements", lambda *_args, **_kwargs: _async(entitlement))
    monkeypatch.setattr(recurring, "require_can_sell", lambda _ent: None)
    monkeypatch.setattr(recurring, "fetch_option_groups", lambda *_args: _async({}))
    monkeypatch.setattr(recurring, "connected_customer", lambda *_args: _async("cus_buyer"))

    class _Stripe:
        def __init__(self):
            self.expirations = 0

        async def create_subscription_checkout(self, **_kwargs):
            conn.deleting = True
            conn.row["status"] = "cancel_requested"
            return {"id": "cs_retry", "url": "https://checkout.stripe.test/retry"}

        async def expire_checkout_session(self, _account, _session):
            self.expirations += 1
            if self.expirations == 1:
                raise recurring.CappeStripeError("timeout")
            return "expired"

    stripe = _Stripe()
    monkeypatch.setattr(recurring, "get_cappe_stripe", lambda: stripe)
    with pytest.raises(HTTPException) as caught:
        await recurring.checkout(site, shopper, body)
    assert caught.value.status_code == 503
    assert conn.row["status"] == "cancel_requested"
    assert conn.row["stripe_checkout_session_id"] == "cs_retry"

    assert await recurring.change_subscription(conn.row, True) == {
        "status": "incomplete_expired"
    }
    assert stripe.expirations == 2
    assert conn.row["status"] == "incomplete_expired"


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
    assert all(
        "stripe_subscription_id IS NULL AND $2 IS NOT NULL" in query
        for query, _ in conn.calls
        if "SET stripe_subscription_id=$2" in query
    )

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


@pytest.mark.asyncio
async def test_delete_claims_fresh_preparation_then_stale_retry_finishes(monkeypatch):
    row = {
        "id": uuid4(), "site_id": uuid4(), "shopper_id": uuid4(),
        "stripe_account_id": "acct_owner", "stripe_checkout_session_id": None,
        "stripe_subscription_id": None, "status": "preparing",
        "preparation_stale": False,
    }
    conn = _CancelConn(row)
    monkeypatch.setattr(recurring, "get_connection", lambda: _Ctx(conn))

    with pytest.raises(HTTPException) as caught:
        await recurring.delete_shopper_subscriptions(
            {"id": row["site_id"]}, {"id": row["shopper_id"]},
        )
    assert caught.value.status_code == 409
    assert conn.deleting is True
    # The 409 is raised after the claim transaction commits. _RollbackTx would
    # restore this state if an exception escaped from inside that transaction.
    assert conn.row["status"] == "cancel_requested"

    conn.row["preparation_stale"] = True
    await recurring.delete_shopper_subscriptions(
        {"id": row["site_id"]}, {"id": row["shopper_id"]},
    )
    assert conn.row["status"] == "incomplete_expired"


@pytest.mark.asyncio
async def test_delete_immediately_cancels_subscription_attached_after_snapshot(monkeypatch):
    site_id, shopper_id = uuid4(), uuid4()
    stale_snapshot = {
        "id": uuid4(), "site_id": site_id, "shopper_id": shopper_id,
        "stripe_account_id": "acct_owner", "stripe_checkout_session_id": "cs_1",
        "stripe_subscription_id": None, "status": "incomplete",
    }
    live = {
        **stale_snapshot, "stripe_subscription_id": "sub_late", "status": "active",
        "preparation_stale": False,
    }
    conn = _CancelConn(live, snapshot=stale_snapshot)
    monkeypatch.setattr(recurring, "get_connection", lambda: _Ctx(conn))
    canceled = []

    class _Stripe:
        async def cancel_connected_subscription(self, account, subscription_id):
            canceled.append((account, subscription_id))
            return {
                "id": subscription_id, "status": "canceled",
                "cancel_at_period_end": False, "current_period_end": None,
                "items": {"data": []},
            }

        async def modify_connected_subscription(self, **_kwargs):
            raise AssertionError("account deletion must cancel immediately")

    monkeypatch.setattr(recurring, "get_cappe_stripe", lambda: _Stripe())
    await recurring.delete_shopper_subscriptions(
        {"id": site_id}, {"id": shopper_id},
    )

    assert canceled == [("acct_owner", "sub_late")]
    assert conn.row["status"] == "canceled"
    assert conn.row["cancel_at_period_end"] is False
