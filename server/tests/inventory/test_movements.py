"""find_item — the match-only lookup the F7 return branch uses, deliberately
NOT find_or_create_item's insert-on-miss behavior (returning stock the
company never tracked must never mint a catalog row from an unreviewed chat
claim). No real DB.

    cd server && ./venv/bin/python -m pytest tests/inventory/test_movements.py -q
"""

import asyncio

from app.matcha.services.inventory import movements

def _run(coro):
    return asyncio.run(coro)


class FakeConn:
    def __init__(self, row=None):
        self._row = row
        self.fetchrow_calls = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self._row


class TestFindItem:
    def test_match_returns_full_row_never_inserts(self, monkeypatch):
        async def fake_list_item_names(conn, company_id, location_id):
            return [{"id": "item-1", "name": "Nitrile Gloves (M)", "normalized_name": "nitrile glove m"}]

        monkeypatch.setattr(movements, "list_item_names", fake_list_item_names)
        conn = FakeConn(row={"id": "item-1", "name": "Nitrile Gloves (M)", "current_quantity": 32})

        result = _run(movements.find_item(conn, "company-1", "nitrile gloves"))

        assert result == {"id": "item-1", "name": "Nitrile Gloves (M)", "current_quantity": 32}
        assert len(conn.fetchrow_calls) == 1
        query = conn.fetchrow_calls[0][0]
        assert "INSERT" not in query.upper()

    def test_no_match_returns_none_no_query_run(self, monkeypatch):
        async def fake_list_item_names(conn, company_id, location_id):
            return []

        monkeypatch.setattr(movements, "list_item_names", fake_list_item_names)
        conn = FakeConn()

        result = _run(movements.find_item(conn, "company-1", "brand new widget"))

        assert result is None
        assert conn.fetchrow_calls == []  # no fetch, and definitely no insert

    def test_location_scoped_lookup_passed_through(self, monkeypatch):
        seen = {}

        async def fake_list_item_names(conn, company_id, location_id):
            seen["location_id"] = location_id
            return []

        monkeypatch.setattr(movements, "list_item_names", fake_list_item_names)
        conn = FakeConn()

        _run(movements.find_item(conn, "company-1", "gloves", "loc-1"))

        assert seen["location_id"] == "loc-1"

    def test_existing_list_skips_the_catalog_requery(self, monkeypatch):
        # channels_ws.py already holds item_rows from the initial
        # list_item_names call in _bg_inventory_request — a per-line
        # find_item in the return branch must not re-run it.
        calls = {"n": 0}

        async def fake_list_item_names(conn, company_id, location_id):
            calls["n"] += 1
            return []

        monkeypatch.setattr(movements, "list_item_names", fake_list_item_names)
        conn = FakeConn(row={"id": "item-1", "name": "Nitrile Gloves (M)"})
        existing = [{"id": "item-1", "name": "Nitrile Gloves (M)", "normalized_name": "nitrile glove m"}]

        result = _run(movements.find_item(conn, "company-1", "nitrile gloves", existing=existing))

        assert result == {"id": "item-1", "name": "Nitrile Gloves (M)"}
        assert calls["n"] == 0


class FakeConnWithInsert(FakeConn):
    """find_or_create_item's insert-on-miss path also runs an execute() and
    a second fetchrow(), beyond the plain-lookup FakeConn above."""

    def __init__(self, rows_by_query=None):
        super().__init__()
        self._rows_by_query = rows_by_query or {}
        self.execute_calls = []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "INSERT" in query.upper() or "SELECT * FROM inventory_items WHERE id" in query:
            return self._rows_by_query.get("match")
        return self._rows_by_query.get("post_insert")


class TestFindOrCreateItem:
    def test_match_delegates_to_find_item_never_inserts(self, monkeypatch):
        async def fake_list_item_names(conn, company_id, location_id):
            return [{"id": "item-1", "name": "Nitrile Gloves (M)", "normalized_name": "nitrile glove m"}]

        monkeypatch.setattr(movements, "list_item_names", fake_list_item_names)
        conn = FakeConnWithInsert(rows_by_query={"match": {"id": "item-1", "name": "Nitrile Gloves (M)"}})

        result = _run(movements.find_or_create_item(
            conn, "company-1", "nitrile gloves", created_by="user-1",
        ))

        assert result == {"id": "item-1", "name": "Nitrile Gloves (M)"}
        assert conn.execute_calls == []  # no INSERT on a match

    def test_no_match_inserts_new_item(self, monkeypatch):
        async def fake_list_item_names(conn, company_id, location_id):
            return []

        monkeypatch.setattr(movements, "list_item_names", fake_list_item_names)
        conn = FakeConnWithInsert(rows_by_query={
            "post_insert": {"id": "item-new", "name": "Brand New Widget", "auto_created": True},
        })

        result = _run(movements.find_or_create_item(
            conn, "company-1", "brand new widget", created_by="user-1",
        ))

        assert result["id"] == "item-new"
        assert len(conn.execute_calls) == 1
        assert "INSERT" in conn.execute_calls[0][0].upper()

    def test_existing_list_skips_the_catalog_requery(self, monkeypatch):
        # audits.commit_audit_lines threads its own `existing` catalog
        # across every new_item_name line in a batch — a per-line
        # find_or_create_item must not re-run list_item_names.
        calls = {"n": 0}

        async def fake_list_item_names(conn, company_id, location_id):
            calls["n"] += 1
            return []

        monkeypatch.setattr(movements, "list_item_names", fake_list_item_names)
        conn = FakeConnWithInsert(rows_by_query={"match": {"id": "item-1", "name": "Nitrile Gloves (M)"}})
        existing = [{"id": "item-1", "name": "Nitrile Gloves (M)", "normalized_name": "nitrile glove m"}]

        result = _run(movements.find_or_create_item(
            conn, "company-1", "nitrile gloves", created_by="user-1", existing=existing,
        ))

        assert result == {"id": "item-1", "name": "Nitrile Gloves (M)"}
        assert conn.execute_calls == []  # matched against `existing`, no INSERT
        assert calls["n"] == 0  # and no catalog requery
