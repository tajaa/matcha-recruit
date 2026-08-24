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


class FakeRecordConn:
    """Fakes the INSERT ... RETURNING * / UPDATE current_quantity pair
    record_movements runs per line. fetchrow echoes the bound params back
    as a row (matching real Postgres RETURNING * behavior closely enough
    to assert on); execute just records what it was called with."""

    _COLUMNS_WITH_SALES_IMPORT = (
        "company_id", "item_id", "channel_id", "source_message_id", "recorded_by",
        "kind", "quantity", "quantity_delta", "quantity_estimated", "note", "narrative",
        "sales_import_id", "audit_run_id", "waste_reason",
    )
    _COLUMNS_WITHOUT_SALES_IMPORT = (
        "company_id", "item_id", "channel_id", "source_message_id", "recorded_by",
        "kind", "quantity", "quantity_delta", "quantity_estimated", "note", "narrative",
        "audit_run_id", "waste_reason",
    )

    def __init__(self):
        self.fetchrow_calls = []
        self.execute_calls = []
        self.fetch_calls = []
        self._next_id = 0

    class _Transaction:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False

    def transaction(self):
        return self._Transaction()

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        columns = (
            self._COLUMNS_WITH_SALES_IMPORT if "sales_import_id, audit_run_id, waste_reason" in query
            else self._COLUMNS_WITHOUT_SALES_IMPORT
        )
        self._next_id += 1
        row = dict(zip(columns, args))
        row["id"] = f"movement-{self._next_id}"
        return row

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))

    async def fetch(self, query, *args):
        # Advisory FEFO consumption sees no open lots in this unit double.
        self.fetch_calls.append((query, args))
        return []


class TestRecordMovementsWaste:
    def test_waste_delta_is_negative(self):
        conn = FakeRecordConn()

        _run(movements.record_movements(
            conn, company_id="company-1", channel_id=None, source_message_id="msg-1",
            recorded_by="user-1", kind="waste",
            lines=[{"item_id": "item-1", "quantity": 3, "estimated": False, "waste_reason": "spoilage"}],
            narrative="tossed 3", note=None,
        ))

        update_calls = [c for c in conn.execute_calls if "current_quantity" in c[0]]
        assert len(update_calls) == 1
        _query, args = update_calls[0]
        assert args == ("item-1", -3.0)  # depletes, never adds
        assert any("inventory_lots" in query for query, _args in conn.fetch_calls)

    def test_waste_reason_threaded_into_insert(self):
        conn = FakeRecordConn()

        _run(movements.record_movements(
            conn, company_id="company-1", channel_id=None, source_message_id="msg-1",
            recorded_by="user-1", kind="waste",
            lines=[{"item_id": "item-1", "quantity": 2, "estimated": False, "waste_reason": "spoilage"}],
            narrative="tossed 2", note=None,
        ))

        _query, args = conn.fetchrow_calls[0]
        assert args[-1] == "spoilage"  # waste_reason is the last bound param

    def test_waste_reason_rejected_on_non_waste_kind(self):
        # A 'waste_reason' key on a non-waste-kind line must never reach
        # the DB — the CHECK constraint would reject it, but the Python
        # side should never even try.
        conn = FakeRecordConn()

        _run(movements.record_movements(
            conn, company_id="company-1", channel_id=None, source_message_id="msg-1",
            recorded_by="user-1", kind="out",
            lines=[{"item_id": "item-1", "quantity": 2, "estimated": False, "waste_reason": "spoilage"}],
            narrative="gave some away", note=None,
        ))

        _query, args = conn.fetchrow_calls[0]
        assert args[-1] is None


class FakeAmendConn:
    """amend_movement_quantity: fetchrow(get old row), fetchrow(UPDATE...
    RETURNING), execute(item current_quantity update)."""

    def __init__(self, old_row):
        self._old_row = old_row
        self.execute_calls = []
        self._fetchrow_n = 0

    async def fetchrow(self, query, *args):
        self._fetchrow_n += 1
        if self._fetchrow_n == 1:
            return self._old_row
        # UPDATE inventory_movements ... RETURNING *
        return {"id": self._old_row.get("id", "movement-1"), "quantity": args[1]}

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class TestAmendMovementQuantitySign:
    def test_amend_out_uses_negative_sign(self):
        # Existing behavior, pinned so the fix below can't silently flip it.
        conn = FakeAmendConn(old_row={"item_id": "item-1", "quantity": 2, "kind": "out"})

        _run(movements.amend_movement_quantity(
            conn, movement_id="movement-1", quantity=5, user_id="user-1",
        ))

        _query, args = conn.execute_calls[0]
        assert args == ("item-1", -3.0)  # sign=-1 * (5-2)

    def test_amend_waste_uses_negative_sign(self):
        # Bug fixed 2026-08-24: amend_movement_quantity's sign map used to
        # only special-case 'out', so amending an estimated waste quantity
        # would ADD stock back instead of correcting a deduction.
        conn = FakeAmendConn(old_row={"item_id": "item-1", "quantity": 2, "kind": "waste"})

        _run(movements.amend_movement_quantity(
            conn, movement_id="movement-1", quantity=5, user_id="user-1",
        ))

        _query, args = conn.execute_calls[0]
        assert args == ("item-1", -3.0)  # sign=-1 * (5-2), NOT +3.0

    def test_amend_in_uses_positive_sign(self):
        # Unaffected sibling case, pinned for the same reason.
        conn = FakeAmendConn(old_row={"item_id": "item-1", "quantity": 2, "kind": "in"})

        _run(movements.amend_movement_quantity(
            conn, movement_id="movement-1", quantity=5, user_id="user-1",
        ))

        _query, args = conn.execute_calls[0]
        assert args == ("item-1", 3.0)
