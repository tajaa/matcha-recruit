"""Vendor invoice / packing-slip ingest — pure clamp logic, deterministic
CSV path never touching Gemini, and resolve_lines' item/order matching
against a fake connection. No real DB, no real Gemini call.

    cd server && ./venv/bin/python -m pytest tests/inventory/test_receipts.py -q
"""

import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.matcha.services.inventory import orders, receipts


def _run(coro):
    return asyncio.run(coro)


class TestCoerceReceiptLine:
    def test_no_item_name_returns_none(self):
        assert receipts.coerce_receipt_line({}) is None
        assert receipts.coerce_receipt_line({"item_name": "  "}) is None

    def test_negative_and_zero_quantity_clamped_to_none(self):
        line = receipts.coerce_receipt_line({"item_name": "Gloves", "quantity": -5})
        assert line["quantity"] is None
        line2 = receipts.coerce_receipt_line({"item_name": "Gloves", "quantity": 0})
        assert line2["quantity"] is None

    def test_garbage_quantity_clamped_to_none(self):
        line = receipts.coerce_receipt_line({"item_name": "Gloves", "quantity": "a dozen"})
        assert line["quantity"] is None

    def test_dollar_string_price_parses(self):
        line = receipts.coerce_receipt_line({"item_name": "Gloves", "unit_price": "$8.99"})
        assert line["unit_price"] == 8.99

    def test_comma_thousands_price_parses(self):
        line = receipts.coerce_receipt_line({"item_name": "Gloves", "unit_price": "1,234.56"})
        assert line["unit_price"] == 1234.56

    def test_fields_clamped_to_length_limits(self):
        line = receipts.coerce_receipt_line({"item_name": "x" * 500, "unit": "y" * 100})
        assert len(line["item_name"]) == 200
        assert len(line["unit"]) == 40

    def test_not_a_dict_returns_none(self):
        assert receipts.coerce_receipt_line("not a dict") is None
        assert receipts.coerce_receipt_line(None) is None


class TestParseCsv:
    def test_template_csv_parses(self):
        raw = (
            b"item_name,quantity,unit,pack_size,vendor_sku,unit_price\n"
            b"Nitrile Gloves (M),10,BX,100/BX,NG-100-M,8.99\n"
        )
        receipt = receipts._parse_csv(raw)
        assert len(receipt["lines"]) == 1
        assert receipt["lines"][0]["item_name"] == "Nitrile Gloves (M)"
        assert receipt["lines"][0]["quantity"] == 10.0

    def test_case_insensitive_headers(self):
        raw = b"Item_Name,Quantity\nGloves,5\n"
        receipt = receipts._parse_csv(raw)
        assert receipt["lines"][0]["item_name"] == "Gloves"
        assert receipt["lines"][0]["quantity"] == 5.0

    def test_extra_columns_ignored(self):
        raw = b"item_name,quantity,warehouse_bin\nGloves,5,A-12\n"
        receipt = receipts._parse_csv(raw)
        assert receipt["lines"][0]["item_name"] == "Gloves"

    def test_bom_prefix_handled(self):
        raw = b"\xef\xbb\xbfitem_name,quantity\nGloves,5\n"
        receipt = receipts._parse_csv(raw)
        assert len(receipt["lines"]) == 1
        assert receipt["lines"][0]["item_name"] == "Gloves"

    def test_blank_item_name_row_dropped(self):
        raw = b"item_name,quantity\n,5\nGloves,5\n"
        receipt = receipts._parse_csv(raw)
        assert len(receipt["lines"]) == 1

    def test_truncates_at_max_lines(self, monkeypatch):
        monkeypatch.setattr(receipts, "MAX_LINES", 2)
        raw = b"item_name,quantity\n" + b"".join(f"item{i},1\n".encode() for i in range(5))
        receipt = receipts._parse_csv(raw)
        assert len(receipt["lines"]) == 2


class TestParseReceiptCsvNeverCallsGemini:
    def test_csv_filename_skips_analyzer(self, monkeypatch):
        def boom():
            raise AssertionError("CSV path must not call _get_analyzer")

        monkeypatch.setattr(receipts, "_get_analyzer", boom)
        raw = b"item_name,quantity\nGloves,5\n"
        result = _run(receipts.parse_receipt(raw, "text/csv", "invoice.csv"))
        assert result["available"] is True
        assert result["lines"][0]["item_name"] == "Gloves"

    def test_csv_mime_without_csv_extension_also_skips_analyzer(self, monkeypatch):
        def boom():
            raise AssertionError("CSV path must not call _get_analyzer")

        monkeypatch.setattr(receipts, "_get_analyzer", boom)
        raw = b"item_name,quantity\nGloves,5\n"
        result = _run(receipts.parse_receipt(raw, "text/csv", "upload"))
        assert result["available"] is True


class _FakeModels:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises

    async def generate_content(self, *, model, contents):
        if self._raises:
            raise self._raises
        return self._response


class _FakeAio:
    def __init__(self, **kwargs):
        self.models = _FakeModels(**kwargs)


class _FakeClient:
    def __init__(self, **kwargs):
        self.aio = _FakeAio(**kwargs)


class _FakeAnalyzer:
    def __init__(self, **kwargs):
        self.model = "gemini-fake"
        self.client = _FakeClient(**kwargs)

    def _parse_json_response(self, text):
        import json
        try:
            return json.loads(text)
        except Exception:
            return {}


class _FakeResp:
    def __init__(self, text):
        self.text = text


class TestParseReceiptGeminiPath:
    def test_gemini_failure_never_raises(self, monkeypatch):
        monkeypatch.setattr(receipts, "_get_analyzer", lambda: _FakeAnalyzer(raises=RuntimeError("boom")))
        result = _run(receipts.parse_receipt(b"%PDF-1.4 fake", "application/pdf", "invoice.pdf"))
        assert result["available"] is False
        assert result["lines"] == []

    def test_gemini_success_coerces_lines(self, monkeypatch):
        payload = '{"vendor": "Henry Schein", "invoice_number": "INV-1", "lines": [{"item_name": "Gloves", "quantity": 10}]}'
        monkeypatch.setattr(receipts, "_get_analyzer", lambda: _FakeAnalyzer(response=_FakeResp(payload)))
        result = _run(receipts.parse_receipt(b"%PDF-1.4 fake", "application/pdf", "invoice.pdf"))
        assert result["available"] is True
        assert result["vendor"] == "Henry Schein"
        assert result["lines"][0]["item_name"] == "Gloves"


class FakeConn:
    def __init__(self, open_order_id=None):
        self._open_order_id = open_order_id
        self.fetchval_calls = []

    async def fetchval(self, query, *args):
        self.fetchval_calls.append((query, args))
        return self._open_order_id


class TestResolveLines:
    def test_fuzzy_match_attaches_item_and_not_exact(self, monkeypatch):
        async def fake_list_item_names(conn, company_id, location_id):
            return [{"id": "item-1", "name": "Nitrile Gloves (M)", "normalized_name": "nitrile glove m"}]

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.list_item_names", fake_list_item_names,
        )
        conn = FakeConn(open_order_id=None)
        lines = _run(receipts.resolve_lines(
            conn, company_id="c1", location_id=None,
            lines=[{"item_name": "nitrile glove", "quantity": 5}],
        ))
        assert lines[0]["item_id"] == "item-1"
        assert lines[0]["matched_name"] == "Nitrile Gloves (M)"
        assert lines[0]["exact"] is False

    def test_no_match_leaves_item_id_none(self, monkeypatch):
        async def fake_list_item_names(conn, company_id, location_id):
            return []

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.list_item_names", fake_list_item_names,
        )
        conn = FakeConn()
        lines = _run(receipts.resolve_lines(
            conn, company_id="c1", location_id=None,
            lines=[{"item_name": "Brand New Widget", "quantity": 1}],
        ))
        assert lines[0]["item_id"] is None
        assert lines[0]["open_order_id"] is None

    def test_open_order_lookup_is_deterministic(self, monkeypatch):
        async def fake_list_item_names(conn, company_id, location_id):
            return [{"id": "item-1", "name": "Gloves", "normalized_name": "glove"}]

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.list_item_names", fake_list_item_names,
        )
        conn = FakeConn(open_order_id="order-latest")
        lines = _run(receipts.resolve_lines(
            conn, company_id="c1", location_id=None,
            lines=[{"item_name": "Gloves", "quantity": 5}],
        ))
        assert lines[0]["open_order_id"] == "order-latest"
        query = conn.fetchval_calls[0][0]
        assert "ORDER BY created_at DESC, id DESC" in query
        assert "status IN ('queued', 'ordered')" in query


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _CommitConn:
    def transaction(self):
        return _Transaction()

    async def fetchval(self, query, *_args):
        if "inventory_items" in query or "business_locations" in query:
            return 1
        return None


def test_reviewed_receipt_preserves_supplier_price_evidence(monkeypatch):
    item_id = UUID("10000000-0000-0000-0000-000000000001")
    movement_id = UUID("20000000-0000-0000-0000-000000000001")
    evidence = []

    async def fake_record_movements(*_args, **_kwargs):
        return [{"id": movement_id}]

    async def fake_record_lot(*_args, **_kwargs):
        return None

    async def fake_record_evidence(*_args, **kwargs):
        evidence.append(kwargs)

    monkeypatch.setattr("app.matcha.services.inventory.movements.record_movements", fake_record_movements)
    monkeypatch.setattr("app.matcha.services.inventory.receipts.lots_service.record_lot", fake_record_lot)
    monkeypatch.setattr("app.matcha.services.inventory.buying_store.record_reviewed_receipt_price", fake_record_evidence)
    result = _run(receipts.commit_receipt_lines(
        _CommitConn(), company_id=UUID("30000000-0000-0000-0000-000000000001"),
        user_id=UUID("40000000-0000-0000-0000-000000000001"), location_id=None,
        vendor="Supplier A", invoice_number="INV-9", force=False, received_on=date(2026, 8, 31),
        lines=[{"item_id": item_id, "quantity": 6.0, "vendor_sku": "OA-6", "pack_size": "6/case", "unit_price": 5.25}],
    ))
    assert result["created"] == 1
    assert evidence[0]["item_id"] == item_id
    assert evidence[0]["vendor"] == "Supplier A"
    assert evidence[0]["unit_price"] == 5.25
    assert evidence[0]["invoice_number"] == "INV-9"


def test_matched_order_receipt_passes_reviewed_lot_metadata(monkeypatch):
    item_id = UUID("10000000-0000-0000-0000-000000000001")
    order_id = UUID("20000000-0000-0000-0000-000000000001")
    movement_id = UUID("30000000-0000-0000-0000-000000000001")
    location_id = UUID("40000000-0000-0000-0000-000000000001")
    received = []

    async def fake_mark_received(*_args, **kwargs):
        received.append(kwargs)
        return {"receipt_movement_id": movement_id, "item_id": item_id}

    async def fake_record_evidence(*_args, **_kwargs):
        return None

    monkeypatch.setattr(orders, "mark_received", fake_mark_received)
    monkeypatch.setattr("app.matcha.services.inventory.buying_store.record_reviewed_receipt_price", fake_record_evidence)
    result = _run(receipts.commit_receipt_lines(
        _CommitConn(), company_id=UUID("50000000-0000-0000-0000-000000000001"),
        user_id=UUID("60000000-0000-0000-0000-000000000001"), location_id=location_id,
        vendor="Supplier A", invoice_number="INV-10", force=False, received_on=date(2026, 8, 30),
        lines=[{
            "order_id": order_id, "quantity": 6.0, "unit_price": 5.25,
            "expires_on": date(2026, 9, 30),
        }],
    ))

    assert result["created"] == 1
    assert received[0]["received_on"] == date(2026, 8, 30)
    assert received[0]["expires_on"] == date(2026, 9, 30)
    assert received[0]["unit_cost"] == 5.25
    assert received[0]["location_id"] == location_id


class _ReceiveOrderConn:
    async def fetchrow(self, query, *_args):
        if "SELECT * FROM inventory_orders" in query:
            return {"item_id": UUID("70000000-0000-0000-0000-000000000001"),
                    "channel_id": None, "quantity": Decimal("6")}
        return {"suggestion": None}


def test_mark_received_records_reviewed_lot_metadata(monkeypatch):
    movement_id = UUID("80000000-0000-0000-0000-000000000001")
    location_id = UUID("90000000-0000-0000-0000-000000000001")
    lot_calls = []

    async def fake_record_movements(*_args, **_kwargs):
        return [{"id": movement_id}]

    async def fake_record_lot(*_args, **kwargs):
        lot_calls.append(kwargs)

    monkeypatch.setattr(orders.movements_service, "record_movements", fake_record_movements)
    monkeypatch.setattr(orders.lots_service, "record_lot", fake_record_lot)
    _run(orders.mark_received(
        _ReceiveOrderConn(), order_id=UUID("a0000000-0000-0000-0000-000000000001"),
        company_id=UUID("b0000000-0000-0000-0000-000000000001"),
        user_id=UUID("c0000000-0000-0000-0000-000000000001"), quantity=6,
        received_on=date(2026, 8, 30), expires_on=date(2026, 9, 30),
        unit_cost=Decimal("5.25"), location_id=location_id,
    ))

    assert lot_calls[0]["received_on"] == date(2026, 8, 30)
    assert lot_calls[0]["expires_on"] == date(2026, 9, 30)
    assert lot_calls[0]["unit_cost"] == Decimal("5.25")
    assert lot_calls[0]["location_id"] == location_id
