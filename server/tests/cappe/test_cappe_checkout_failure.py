"""Storefront checkout when the payment page cannot be opened.

`create_public_order` used to swallow a Stripe error and fall through to the
unpaid flow: the buyer saw "Order placed", got a receipt for money never taken,
and the order — with no Stripe session — held its stock where the
abandoned-order reaper could not see it.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_checkout_failure.py -q
"""
import inspect
import os
import pathlib
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import BackgroundTasks, HTTPException  # noqa: E402

from app.cappe.models.shop import CappeCartItem, CappeCheckoutRequest  # noqa: E402
from app.cappe.services import commerce  # noqa: E402
from app.cappe.services.discounts import apply_discount_cents  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

ORIGIN = "https://store.example.com"


class Conn:
    """Enough of a connection for one single-line physical order."""

    def __init__(self, site, product):
        self.site, self.product = site, product
        self.order = None
        self.cancelled = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def transaction(self):
        return self

    async def fetchrow(self, query, *args):
        if "FROM cappe_products" in query:
            return self.product
        if "FROM cappe_sites" in query:
            return {"tax_rate_bps": 0, "tax_label": None, "shipping_flat_cents": 0,
                    "shipping_free_threshold_cents": None, "shipping_label": None}
        if "INSERT INTO cappe_orders" in query:
            self.order = {
                "id": uuid4(), "status": "pending", "access_token": uuid4().hex,
                "subtotal_cents": args[3], "tax_cents": args[4],
                "shipping_cents": args[5], "total_cents": args[6],
                "currency": args[7], "requires_approval": args[9],
            }
            return self.order
        if "SET status = 'cancelled'" in query:
            self.cancelled.append(args)
            return {"id": args[0]} if self.order else None
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if query == "SELECT NOW()":
            return datetime.now(timezone.utc)
        raise AssertionError(query)

    async def execute(self, query, *_args):
        assert "cappe_order_items" in query or "UPDATE cappe_orders" in query


def _wire(monkeypatch, *, owner, stripe):
    site = {"id": uuid4(), "name": "Store", "timezone": "UTC", "custom_domain": "store.example.com"}
    product = {"id": uuid4(), "name": "Guide", "price_cents": 1000, "currency": "USD",
               "status": "active", "fulfillment": "digital", "requires_approval": False}
    conn = Conn(site, product)
    released = []

    async def _restock(_conn, *, site_id, order_id, reason):
        released.append(("restock", order_id, reason))

    async def _bookings(_conn, *, order_id):
        released.append(("bookings", order_id))
        return 0

    monkeypatch.setattr(commerce, "get_connection", lambda: conn)
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(commerce, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(commerce, "lock_stock_rows", AsyncMock())
    monkeypatch.setattr(commerce, "fetch_site_owner", AsyncMock(return_value=owner))
    monkeypatch.setattr(commerce, "resolve_entitlements",
                        AsyncMock(return_value=SimpleNamespace(platform_fee_bps=200, has=lambda _f: False)))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    monkeypatch.setattr(commerce, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(commerce, "restock_order", _restock)
    monkeypatch.setattr(commerce, "release_order_bookings", _bookings)
    body = CappeCheckoutRequest(
        customer_email="buyer@example.com",
        items=[CappeCartItem(product_id=product["id"], quantity=1)],
        success_url=ORIGIN + "/thanks", cancel_url=ORIGIN + "/cart",
    )
    return site, body, conn, released


OWNER = {"plan": "business", "status": "active", "email": "owner@example.com", "name": "Owner",
         "stripe_account_id": "acct_store", "stripe_charges_enabled": True}


@pytest.mark.asyncio
async def test_a_stripe_outage_cancels_the_order_instead_of_pretending_it_was_placed(monkeypatch):
    stripe = SimpleNamespace(create_checkout_session=AsyncMock(side_effect=CappeStripeError("down")))
    site, body, conn, released = _wire(monkeypatch, owner=OWNER, stripe=stripe)
    background = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        await commerce.create_public_order(site, body, background)
    assert exc.value.status_code == 502
    assert "not placed" in exc.value.detail and "not been charged" in exc.value.detail
    # The order is undone and everything it held is handed back …
    assert conn.cancelled == [(conn.order["id"], site["id"])]
    assert [r[0] for r in released] == ["restock", "bookings"]
    # … and nobody is emailed a receipt for money that was never taken.
    assert background.tasks == []


@pytest.mark.asyncio
async def test_a_store_without_card_payments_still_takes_a_manual_order(monkeypatch):
    """The fallback itself is legitimate — it is only wrong as a reaction to a
    FAILED attempt to take a card."""
    stripe = SimpleNamespace(create_checkout_session=AsyncMock())
    owner = {**OWNER, "stripe_account_id": None, "stripe_charges_enabled": False}
    site, body, conn, released = _wire(monkeypatch, owner=owner, stripe=stripe)
    monkeypatch.setattr(commerce, "check_recipient_send_ok", AsyncMock(return_value=True))
    out = await commerce.create_public_order(site, body, BackgroundTasks())
    assert out["checkout_url"] is None and out["status"] == "pending"
    assert conn.cancelled == [] and released == []
    stripe.create_checkout_session.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [None, {**OWNER, "status": "suspended"}, {**OWNER, "status": "deleted"}])
async def test_a_suspended_or_missing_owner_takes_no_orders(monkeypatch, owner):
    """Subscription checkout already required an active owner; one-off did not."""
    stripe = SimpleNamespace(create_checkout_session=AsyncMock())
    site, body, conn, _released = _wire(monkeypatch, owner=owner, stripe=stripe)
    with pytest.raises(HTTPException) as exc:
        await commerce.create_public_order(site, body, BackgroundTasks())
    assert exc.value.status_code == 409
    assert conn.order is None                          # refused before anything is written


@pytest.mark.asyncio
async def test_release_unpaid_order_is_a_no_op_for_an_order_no_longer_pending(monkeypatch):
    site, _body, conn, released = _wire(
        monkeypatch, owner=OWNER, stripe=SimpleNamespace(),
    )
    assert await commerce.release_unpaid_order(uuid4(), site["id"]) is False   # conn.order is None
    assert released == []


def test_the_owner_lookup_selects_the_account_status():
    assert "a.status" in inspect.getsource(commerce.fetch_site_owner)


# ── rounding: the page and the charge agree to the cent ─────────────────────

@pytest.mark.parametrize("cents,pct,expected", [
    (250, 10, 225),        # exact
    (1050, 50, 525),       # exact
    (5, 50, 3),            # 2.5 → 3  (banker's rounding gave 2)
    (15, 50, 8),           # 7.5 → 8  (banker's rounding gave 8 — even; unchanged)
    (25, 50, 13),          # 12.5 → 13 (banker's gave 12)
    (999, 33, 669),        # 669.33 → 669
    (995, 10, 896),        # 895.5 → 896 (banker's gave 896)
    (985, 10, 887),        # 886.5 → 887 (banker's gave 886)
    (10000, 0, 10000),
    (10000, 200, 1000),    # clamped to 90% off
])
def test_discounts_round_half_up(cents, pct, expected):
    assert apply_discount_cents(cents, pct) == expected


def test_server_rounding_matches_javascript_math_round_everywhere():
    """`Math.round(n / 100)` is half-up for non-negative n; the server must be
    too, for every price and percentage the storefront can show."""
    import math

    for cents in range(0, 3000):
        for pct in (1, 5, 10, 15, 25, 33, 50, 75, 90):
            js = math.floor(cents * (100 - pct) / 100 + 0.5)
            assert apply_discount_cents(cents, pct) == js, (cents, pct)


def test_the_storefront_script_uses_the_same_integer_expression():
    """The two implementations cannot share code (Python / inlined JS), so the
    JS source is pinned: if either side changes its formula this fails."""
    js = (pathlib.Path(commerce.__file__).parent / "render/assets/store.js").read_text()
    assert "Math.floor((s*(100-p.discount_percent)+50)/100)" in js
    assert "Math.round(s*(100-p.discount_percent)/100)" not in js
    server = inspect.getsource(apply_discount_cents)
    assert re.search(r"\(int\(cents\) \* \(100 - pct\) \+ 50\) // 100", server)


def test_the_storefront_asks_the_server_for_the_real_total():
    js = (pathlib.Path(commerce.__file__).parent / "render/assets/store.js").read_text()
    assert "RT.post('/quote'" in js
    # Tax and shipping are shown before the buyer commits, not first seen on
    # the receipt or on Stripe's page.
    assert "q.tax_cents" in js and "q.shipping_cents" in js and "q.total_cents" in js
