"""Stock-audit bulk-count commit — fake conn, no real DB.

    cd server && ./venv/bin/python -m pytest tests/inventory/test_audits.py -q

Patches go on the live `movements` module object (not a local alias) since
adjust_item_count/find_or_create_item/list_item_names are looked up as
attributes at call time — same pattern test_receipts.py uses for
resolve_lines' collaborator.
"""

import asyncio

import pytest

from app.matcha.services.inventory import audits


def _run(coro):
    return asyncio.run(coro)


class _TxnCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, location_ok=True):
        self.location_ok = location_ok

    async def fetchval(self, query, *args):
        return self.location_ok

    def transaction(self):
        return _TxnCtx()


def _patch_adjust(monkeypatch, calls):
    async def fake_adjust(conn, *, item_id, company_id, quantity, user_id, note=None):
        calls.append({"item_id": item_id, "quantity": quantity, "note": note})
        return {"id": "movement-1"}

    monkeypatch.setattr(
        "app.matcha.services.inventory.movements.adjust_item_count", fake_adjust,
    )


def _patch_list_item_names(monkeypatch, rows=None):
    async def fake_list(conn, company_id, location_id=None):
        return rows or []

    monkeypatch.setattr(
        "app.matcha.services.inventory.movements.list_item_names", fake_list,
    )


class TestCommitAuditLines:
    def test_adjust_called_with_default_note(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        _patch_list_item_names(monkeypatch)
        conn = FakeConn()
        result = _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[{"item_id": "item-1", "counted_quantity": 6}],
        ))
        assert result == {"total": 1, "applied": 1, "failed": 0, "errors": []}
        assert calls[0]["note"] == "Stock audit"
        assert calls[0]["quantity"] == 6

    def test_custom_note_passes_through(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        _patch_list_item_names(monkeypatch)
        conn = FakeConn()
        _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note="Weekly audit",
            lines=[{"item_id": "item-1", "counted_quantity": 3}],
        ))
        assert calls[0]["note"] == "Weekly audit"

    def test_zero_count_is_legal(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        _patch_list_item_names(monkeypatch)
        conn = FakeConn()
        result = _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[{"item_id": "item-1", "counted_quantity": 0}],
        ))
        assert result["applied"] == 1
        assert calls[0]["quantity"] == 0

    def test_bad_row_fails_alone(self, monkeypatch):
        calls = []

        async def flaky_adjust(conn, *, item_id, company_id, quantity, user_id, note=None):
            if item_id == "item-bad":
                raise ValueError("item not found")
            calls.append(item_id)
            return {"id": "m"}

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.adjust_item_count", flaky_adjust,
        )
        _patch_list_item_names(monkeypatch)
        conn = FakeConn()
        result = _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[
                {"item_id": "item-1", "counted_quantity": 1},
                {"item_id": "item-bad", "counted_quantity": 2},
                {"item_id": "item-3", "counted_quantity": 3},
            ],
        ))
        assert result["applied"] == 2
        assert result["failed"] == 1
        assert result["errors"][0]["row"] == 2
        assert calls == ["item-1", "item-3"]

    def test_new_item_name_creates_then_adjusts(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        _patch_list_item_names(monkeypatch)

        async def fake_create(conn, company_id, raw_name, *, created_by, location_id=None, existing=None):
            return {"id": "new-item-1", "name": raw_name, "normalized_name": "gloves", "location_id": None}

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.find_or_create_item", fake_create,
        )
        conn = FakeConn()
        result = _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[{"new_item_name": "Gloves", "counted_quantity": 12}],
        ))
        assert result["applied"] == 1
        assert calls[0]["item_id"] == "new-item-1"

    def test_line_needs_item_or_name(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        _patch_list_item_names(monkeypatch)
        conn = FakeConn()
        result = _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[
                {"counted_quantity": 5},
                {"item_id": "item-1", "counted_quantity": 1},
            ],
        ))
        assert result["applied"] == 1
        assert result["failed"] == 1
        assert calls == [{"item_id": "item-1", "quantity": 1, "note": "Stock audit"}]

    def test_negative_quantity_rejected(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        _patch_list_item_names(monkeypatch)
        conn = FakeConn()
        result = _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[{"item_id": "item-1", "counted_quantity": -1}],
        ))
        assert result["failed"] == 1
        assert calls == []

    def test_bool_quantity_rejected(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        _patch_list_item_names(monkeypatch)
        conn = FakeConn()
        result = _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[{"item_id": "item-1", "counted_quantity": True}],
        ))
        assert result["failed"] == 1
        assert calls == []

    def test_location_not_found_raises_before_any_line(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        _patch_list_item_names(monkeypatch)
        conn = FakeConn(location_ok=False)
        with pytest.raises(ValueError, match="location not found"):
            _run(audits.commit_audit_lines(
                conn, company_id="c1", user_id="u1", location_id="loc-1", note=None,
                lines=[{"item_id": "item-1", "counted_quantity": 1}],
            ))
        assert calls == []

    def test_both_item_id_and_new_item_name_rejected(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        _patch_list_item_names(monkeypatch)
        conn = FakeConn()
        result = _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[{"item_id": "item-1", "new_item_name": "Gloves", "counted_quantity": 1}],
        ))
        assert result["applied"] == 0
        assert result["failed"] == 1
        assert calls == []

    def test_catalog_not_fetched_when_all_lines_are_item_id(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        fetch_count = {"n": 0}

        async def fake_list(conn, company_id, location_id=None):
            fetch_count["n"] += 1
            return []

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.list_item_names", fake_list,
        )
        conn = FakeConn()
        _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[
                {"item_id": "item-1", "counted_quantity": 1},
                {"item_id": "item-2", "counted_quantity": 2},
            ],
        ))
        assert fetch_count["n"] == 0  # no new_item_name line, so no lazy catalog fetch at all

    def test_catalog_fetched_once_regardless_of_line_count(self, monkeypatch):
        calls = []
        _patch_adjust(monkeypatch, calls)
        fetch_count = {"n": 0}

        async def fake_list(conn, company_id, location_id=None):
            fetch_count["n"] += 1
            return []

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.list_item_names", fake_list,
        )

        async def fake_create(conn, company_id, raw_name, *, created_by, location_id=None, existing=None):
            return {"id": f"new-{raw_name}", "name": raw_name, "normalized_name": raw_name.lower(), "location_id": None}

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.find_or_create_item", fake_create,
        )
        conn = FakeConn()
        _run(audits.commit_audit_lines(
            conn, company_id="c1", user_id="u1", location_id=None, note=None,
            lines=[
                {"new_item_name": "Gloves", "counted_quantity": 1},
                {"new_item_name": "Cups", "counted_quantity": 2},
            ],
        ))
        assert fetch_count["n"] == 1
