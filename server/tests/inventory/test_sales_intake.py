import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

from app.matcha.services.inventory.reorder import suggest_order
from app.matcha.services.inventory.sales_parse import parse_sales_csv_bytes
from app.matcha.services.inventory.expected import variance_rollup
from app.matcha.services.inventory import sales_mappings


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


class _FakeMappingConn:
    """asyncpg returns jsonb_agg(...) as a raw JSON string (no jsonb codec
    registered app-wide) — list_mappings/resolve_sold_lines must decode it,
    not hand a string straight to the caller."""

    def __init__(self, components):
        self._components_json = json.dumps(components)

    async def fetch(self, query, *_args):
        if "inventory_sales_mappings" in query:
            return [{
                "id": "mapping-latte", "company_id": "co-1", "location_id": None,
                "sold_name": "Vanilla latte", "normalized_name": "vanilla latte",
                "kind": "recipe", "components": self._components_json,
            }]
        if "inventory_items" in query:
            return []
        raise AssertionError(f"unexpected fetch: {query}")


def test_list_mappings_decodes_jsonb_string_components():
    components = [{"item_id": "cup", "quantity_per_sale": 1, "unit": "each"}]
    conn = _FakeMappingConn(components)
    result = asyncio.run(sales_mappings.list_mappings(conn, "co-1"))
    assert result[0]["components"] == components


def test_resolve_sold_lines_does_not_choke_on_string_components():
    components = [
        {"item_id": "cup", "quantity_per_sale": 1, "unit": "each"},
        {"item_id": "milk", "quantity_per_sale": 0.25, "unit": "l"},
    ]
    conn = _FakeMappingConn(components)
    resolved = asyncio.run(sales_mappings.resolve_sold_lines(
        conn, company_id="co-1", location_id=None,
        lines=[{"item_name": "Vanilla latte", "quantity": 3, "gross_sales": 18}],
    ))
    assert resolved[0]["status"] == "mapped"
    assert resolved[0]["components"] == components
