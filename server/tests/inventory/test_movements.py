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
