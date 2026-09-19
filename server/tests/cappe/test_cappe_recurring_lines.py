import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.models.shop import CappeCartItem, CappeProductCreate  # noqa: E402
from app.cappe.services.recurring import build_subscription_lines, validate_product_subscription  # noqa: E402


def _fixture(quantity=2):
    product_id, group_id, option_id = uuid4(), uuid4(), uuid4()
    products = {
        product_id: {
            "id": product_id,
            "name": "Large soap",
            "price_cents": 1000,
            "currency": "USD",
            "inventory": 10,
            "status": "active",
            "fulfillment": "physical",
            "requires_approval": False,
            "subscription_intervals": ["month"],
            "subscription_discount_bps": 1000,
            "option_groups": [{
                "id": group_id,
                "name": "Size",
                "select_type": "single",
                "required": True,
                "options": [{
                    "id": option_id,
                    "name": "Large",
                    "price_delta_cents": 200,
                    "inventory": 10,
                }],
            }],
        }
    }
    return products, [CappeCartItem(product_id=product_id, quantity=quantity, selected_option_ids=[option_id])]


def test_subscription_math_includes_options_discount_tax_and_shipping():
    products, items = _fixture()
    lines, snapshot, totals = build_subscription_lines(
        products,
        items,
        "month",
        {"tax_rate_bps": 1000, "shipping_flat_cents": 500, "shipping_free_threshold_cents": 3000},
    )
    assert snapshot[0]["unit_price_cents"] == 1080  # (1000 + 200) less 10%
    assert totals == {
        "subtotal_cents": 2160,
        "tax_cents": 216,
        "shipping_cents": 500,
        "total_cents": 2876,
        "currency": "USD",
    }
    assert [line["price_data"]["product_data"]["name"] for line in lines] == [
        "Large soap", "Tax", "Shipping"
    ]


def test_subscription_free_shipping_threshold_uses_discounted_goods_total():
    products, items = _fixture(quantity=3)
    _lines, _snapshot, totals = build_subscription_lines(
        products,
        items,
        "month",
        {"tax_rate_bps": 0, "shipping_flat_cents": 500, "shipping_free_threshold_cents": 3000},
    )
    assert totals["subtotal_cents"] == 3240
    assert totals["shipping_cents"] == 0


def test_product_model_rejects_duplicate_subscription_intervals():
    with pytest.raises(ValueError):
        CappeProductCreate(
            name="Soap", price_cents=1000, subscription_intervals=["month", "month"]
        )


@pytest.mark.asyncio
async def test_subscription_discount_requires_an_interval():
    with pytest.raises(Exception) as caught:
        await validate_product_subscription(
            None,
            SimpleNamespace(),
            {"subscription_intervals": [], "subscription_discount_bps": 500, "fulfillment": "physical"},
        )
    assert getattr(caught.value, "status_code", None) == 422
