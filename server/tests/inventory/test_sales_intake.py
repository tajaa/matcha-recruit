from datetime import datetime, timezone
from decimal import Decimal

from app.matcha.services.inventory.reorder import suggest_order
from app.matcha.services.inventory.sales_parse import parse_sales_csv_bytes
from app.matcha.services.inventory.expected import variance_rollup


def test_parse_sales_csv_accepts_pos_aliases_money_and_refunds():
    draft = parse_sales_csv_bytes(
        b"Product,Items Sold,Net Sales,Business Date\n"
        b"Latte,12,\"$1,234.50\",2026-08-16\n"
        b"Refund,-2,-$8.00,2026-08-16\n"
    )
    assert draft["lines"] == [
        {"item_name": "Latte", "quantity": 12.0, "gross_sales": 1234.5},
        {"item_name": "Refund", "quantity": -2.0, "gross_sales": -8.0},
    ]


def test_parse_sales_csv_handles_quoted_currency_and_generic_headers():
    draft = parse_sales_csv_bytes(
        "item,qty,sales,date\nCookie 6-pack,3,\"$1,234.50\",2026-08-16\n".encode()
    )
    assert draft["business_date"] == "2026-08-16"
    assert draft["lines"][0]["quantity"] == 3
    assert draft["lines"][0]["gross_sales"] == 1234.5


def test_variance_rollup_weights_values_and_finds_extremes():
    result = variance_rollup(
        [
            {"item_id": "a", "expected": 10, "counted_quantity": 7},
            {"item_id": "b", "expected": 2, "counted_quantity": 5},
        ],
        {"a": {"name": "Beans", "unit_cost": Decimal("2.50")},
         "b": {"name": "Cups", "unit_cost": None}},
    )
    assert result["total_units"] == Decimal("0")
    assert result["total_value"] == Decimal("-7.50")
    assert result["biggest_short"][0]["name"] == "Beans"
    assert result["biggest_over"][0]["name"] == "Cups"


def test_reorder_counts_sale_movements_as_consumption():
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    movements = [
        {"kind": "sale", "quantity": 4, "quantity_delta": -4,
         "created_at": datetime(2026, 8, 10, tzinfo=timezone.utc)},
        {"kind": "sale", "quantity": 3, "quantity_delta": -3,
         "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc)},
    ]
    result = suggest_order(movements, now)
    assert result is not None
    assert result["daily_rate"] > 0
