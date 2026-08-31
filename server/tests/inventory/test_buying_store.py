import asyncio
import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.matcha.services.inventory import buying_store


COMPANY = UUID("10000000-0000-0000-0000-000000000001")
USER = UUID("20000000-0000-0000-0000-000000000001")
ITEM = UUID("30000000-0000-0000-0000-000000000001")
SUPPLIER = UUID("40000000-0000-0000-0000-000000000001")
SUPPLIER_ITEM = UUID("50000000-0000-0000-0000-000000000001")
FORECAST = UUID("60000000-0000-0000-0000-000000000001")


def _run(coro):
    return asyncio.run(coro)


class _SupplierItemConn:
    def __init__(self):
        self.insert_query = ""
        self.insert_args = ()
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        if "SELECT id,location_id FROM inventory_items" in query:
            return {"id": ITEM, "location_id": None}
        self.insert_query = query
        self.insert_args = args
        return {"id": SUPPLIER_ITEM}

    async def fetchval(self, _query, *_args):
        return 1

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


def test_supplier_item_patch_preserves_omitted_terms():
    conn = _SupplierItemConn()
    _run(buying_store.upsert_supplier_item(
        conn, company_id=COMPANY, item_id=ITEM, user_id=USER,
        values={"supplier_id": SUPPLIER, "unit_price": Decimal("4.25")},
    ))

    patch_keys = json.loads(conn.insert_args[15])
    assert patch_keys == ["supplier_id", "unit_price"]
    assert "$16::jsonb ? 'unit_price'" in conn.insert_query
    assert "$16::jsonb ? 'vendor_sku'" in conn.insert_query
    assert conn.insert_args[9] == Decimal("4.25")
    assert len(conn.execute_calls) == 1


def test_buying_fingerprint_changes_with_decision_date():
    kwargs = {
        "forecast_run_id": FORECAST,
        "shortages": [],
        "attention": [],
        "transfers": [],
        "offers": [],
    }
    first = buying_store._input_fingerprint(**kwargs, today=date(2026, 8, 31))
    second = buying_store._input_fingerprint(**kwargs, today=date(2026, 9, 1))
    assert first != second


def test_older_receipt_does_not_replace_current_price(monkeypatch):
    conn = _SupplierItemConn()

    async def fake_upsert_supplier(*_args, **_kwargs):
        return {"id": SUPPLIER}

    monkeypatch.setattr(buying_store, "upsert_supplier", fake_upsert_supplier)
    _run(buying_store.record_reviewed_receipt_price(
        conn, company_id=COMPANY, user_id=USER, item_id=ITEM, location_id=None,
        vendor="Supplier A", vendor_sku="SKU-1", pack_size="6/case",
        unit_price=Decimal("4.25"), quantity=Decimal("6"),
        observed_on=date(2026, 1, 1), invoice_number="OLD-1",
    ))

    assert "EXCLUDED.price_observed_on >= inventory_supplier_items.price_observed_on" in conn.insert_query
    assert len(conn.execute_calls) == 1
    assert "inventory_supplier_price_history" in conn.execute_calls[0][0]
