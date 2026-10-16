"""PUT /admin/products/{id}/price — the /admin/pricing page's price-only edit.

It must change only price_cents, keep the history snapshot every product
mutation writes, and refuse products that aren't billed through Stripe.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.routes.admin import products as routes

ADMIN = SimpleNamespace(id="admin-1", email="admin@example.com")


def _row(**overrides):
    row = dict(
        id=uuid4(), slug="schedule-comm", name="Matcha S&C", description="",
        features=json.dumps({"employee_schedule": True}), gate_feature="employee_schedule",
        pricing_model="per_location", price_cents=5000, block_size=None,
        min_headcount=1, max_headcount=300, nav=None, status="published",
        created_at=None, updated_at=None, updated_by=None, onboarding_kind=None,
    )
    row.update(overrides)
    return row


def _conn(current, updated=None):
    conn = MagicMock()
    # FOR UPDATE read, then _snapshot's read, then the UPDATE … RETURNING.
    conn.fetchrow = AsyncMock(side_effect=[current, current, updated])
    conn.execute = AsyncMock()
    txn = MagicMock()
    txn.__aenter__ = AsyncMock(return_value=None)
    txn.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return conn, MagicMock(return_value=cm)


@pytest.mark.asyncio
async def test_price_change_updates_only_the_price_and_snapshots(monkeypatch):
    current = _row()
    conn, ctx = _conn(current, _row(price_cents=4500, updated_by=ADMIN.email))
    monkeypatch.setattr(routes, "get_connection", ctx)

    result = await routes.set_product_price(current["id"], routes.PriceChange(price_cents=4500), ADMIN)

    assert result["price_cents"] == 4500
    update_sql, *update_args = conn.fetchrow.call_args_list[2].args
    assert "SET price_cents = $1, updated_at = NOW(), updated_by = $2" in update_sql
    set_clause = update_sql.split("RETURNING")[0]
    assert "features" not in set_clause and "slug" not in set_clause
    assert update_args == [4500, ADMIN.email, current["id"]]
    history_sql = conn.execute.await_args.args[0]
    assert "product_definition_history" in history_sql


@pytest.mark.asyncio
async def test_price_change_refuses_products_not_billed_through_stripe(monkeypatch):
    conn, ctx = _conn(_row(pricing_model="contact_sales", price_cents=None))
    monkeypatch.setattr(routes, "get_connection", ctx)

    with pytest.raises(HTTPException) as exc:
        await routes.set_product_price(uuid4(), routes.PriceChange(price_cents=4500), ADMIN)

    assert exc.value.status_code == 400
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_price_change_404s_on_unknown_product(monkeypatch):
    _, ctx = _conn(None)
    monkeypatch.setattr(routes, "get_connection", ctx)

    with pytest.raises(HTTPException) as exc:
        await routes.set_product_price(uuid4(), routes.PriceChange(price_cents=4500), ADMIN)

    assert exc.value.status_code == 404


def test_price_must_be_positive():
    with pytest.raises(ValidationError):
        routes.PriceChange(price_cents=0)
