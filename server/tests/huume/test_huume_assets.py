"""Tests for services/huume/assets.py's asset registry (fake conn, no DB).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_assets.py -q

get_connection IS a module-level import in assets.py, so it's patched
directly on the module (same pattern as test_ems_skill.py's _patch_conn).
"""

from uuid import uuid4

import pytest

from app.matcha.services.huume import assets
from app.matcha.services.huume.actions import _HUUME_ACTION_REQUIRED_FEATURE

COMPANY_ID = uuid4()
THREAD_ID = uuid4()
ACTOR_ID = uuid4()


class _FakeConn:
    def __init__(self):
        self.executed: list[tuple] = []
        self.raise_on_execute = False

    async def execute(self, query, *params):
        if self.raise_on_execute:
            raise RuntimeError("boom")
        self.executed.append((" ".join(query.split()), params))
        return "INSERT 0 1"


class _ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


def _patch_conn(monkeypatch, conn=None):
    conn = conn or _FakeConn()
    monkeypatch.setattr(assets, "get_connection", lambda: _ConnCtx(conn))
    return conn


class TestSpecCoverage:
    def test_every_action_type_mapped_or_explicitly_excluded(self):
        # Drift guard: a new staged type added to _HUUME_ACTION_REQUIRED_FEATURE
        # must pick a side here — mapped (gets an asset row) or explicitly
        # excluded with a documented reason, never silently forgotten.
        for action_type in _HUUME_ACTION_REQUIRED_FEATURE:
            assert action_type in assets.ASSET_SPECS or action_type in assets._NO_ASSET_TYPES, (
                f"{action_type} is in neither ASSET_SPECS nor _NO_ASSET_TYPES"
            )

    def test_legal_record_labels_are_name_free(self):
        # discipline/ir/er are legal-record types — same rule as
        # lookup_context: labels may carry numbers, never employee names.
        action = {"employee_name": "Jane Doe", "candidate_name": "Jane Doe", "infraction_type": "attendance"}
        for action_type in ("discipline_draft", "discipline_from_incident", "discipline_decision",
                            "ir_report", "er_case"):
            spec = assets.ASSET_SPECS[action_type]
            label = spec.label_fn({**action, "type": action_type}, {"record_id": "x"})
            assert "Jane" not in label and "Doe" not in label

    def test_send_offer_label_may_carry_candidate_name(self):
        spec = assets.ASSET_SPECS["send_offer"]
        label = spec.label_fn({"candidate_name": "Maria Lopez"}, {"record_id": "x"})
        assert "Maria Lopez" in label


class TestRecordAsset:
    @pytest.mark.asyncio
    async def test_error_result_is_noop(self, monkeypatch):
        conn = _patch_conn(monkeypatch)
        await assets.record_asset(
            company_id=COMPANY_ID, thread_id=THREAD_ID, actor_user_id=ACTOR_ID,
            action={"type": "ir_report"}, result={"status": "error", "message": "nope"},
        )
        assert conn.executed == []

    @pytest.mark.asyncio
    async def test_missing_record_id_is_noop(self, monkeypatch):
        conn = _patch_conn(monkeypatch)
        await assets.record_asset(
            company_id=COMPANY_ID, thread_id=THREAD_ID, actor_user_id=ACTOR_ID,
            action={"type": "ir_report"}, result={"status": "created"},
        )
        assert conn.executed == []

    @pytest.mark.asyncio
    async def test_unmapped_type_is_noop(self, monkeypatch):
        conn = _patch_conn(monkeypatch)
        await assets.record_asset(
            company_id=COMPANY_ID, thread_id=THREAD_ID, actor_user_id=ACTOR_ID,
            action={"type": "amend_handbook"}, result={"status": "created", "record_id": "x"},
        )
        assert conn.executed == []

    @pytest.mark.asyncio
    async def test_upsert_sql_and_label_from_record_label(self, monkeypatch):
        conn = _patch_conn(monkeypatch)
        await assets.record_asset(
            company_id=COMPANY_ID, thread_id=THREAD_ID, actor_user_id=ACTOR_ID,
            action={"type": "ir_report"},
            result={"status": "created", "record_id": "rec-1", "record_label": "IR-2026-004"},
        )
        assert len(conn.executed) == 1
        sql, params = conn.executed[0]
        assert "ON CONFLICT (company_id, ref_table, ref_id)" in sql
        assert "DO UPDATE SET label = EXCLUDED.label" in sql
        # A re-write (e.g. an offer drafted in one thread, later sent from a
        # different one) must refresh thread_id/source too, not just the
        # label — a stale thread_id/source ('draft' after it was really
        # sent) is the bug this pins.
        assert "source = EXCLUDED.source" in sql
        assert "thread_id = COALESCE(EXCLUDED.thread_id, huume_assets.thread_id)" in sql
        assert params == (COMPANY_ID, THREAD_ID, "ir_incident", "ir_incidents", "rec-1", "IR-2026-004", ACTOR_ID)

    @pytest.mark.asyncio
    async def test_never_raises_on_conn_failure(self, monkeypatch):
        conn = _FakeConn()
        conn.raise_on_execute = True
        _patch_conn(monkeypatch, conn)
        # Must not raise — a registry failure can't fail the real write it annotates.
        await assets.record_asset(
            company_id=COMPANY_ID, thread_id=THREAD_ID, actor_user_id=ACTOR_ID,
            action={"type": "ir_report"}, result={"status": "created", "record_id": "rec-1"},
        )


class TestRecordOfferDraftAsset:
    @pytest.mark.asyncio
    async def test_writes_draft_source_with_candidate_label(self, monkeypatch):
        conn = _patch_conn(monkeypatch)
        await assets.record_offer_draft_asset(
            company_id=COMPANY_ID, thread_id=THREAD_ID, actor_user_id=ACTOR_ID,
            offer_id="offer-1", candidate_name="Maria Lopez", position_title="Dental Hygienist",
        )
        assert len(conn.executed) == 1
        sql, params = conn.executed[0]
        assert "'draft'" in sql
        assert "Maria Lopez" in params[3]
        assert "Dental Hygienist" in params[3]

    @pytest.mark.asyncio
    async def test_never_raises_on_conn_failure(self, monkeypatch):
        conn = _FakeConn()
        conn.raise_on_execute = True
        _patch_conn(monkeypatch, conn)
        await assets.record_offer_draft_asset(
            company_id=COMPANY_ID, thread_id=THREAD_ID, actor_user_id=ACTOR_ID,
            offer_id="offer-1", candidate_name="Maria", position_title="",
        )


class TestStatusSqlSchema:
    """Pins the two real-schema mismatches a review caught: inventory_items
    has no is_archived column (archived_at TIMESTAMPTZ instead), and
    pto_requests has no company_id at all (employee-scoped only) — both
    would UndefinedColumnError on the first inventory/PTO asset, taking
    down the whole /huume/assets listing (both the thread and company
    routes) with an unguarded 500, not just that one row."""

    def test_inventory_items_uses_archived_at_not_is_archived(self):
        sql = assets._STATUS_SQL["inventory_items"]
        assert "is_archived" not in sql
        assert "archived_at" in sql

    def test_pto_requests_joins_employees_for_company_scope(self):
        sql = assets._STATUS_SQL["pto_requests"]
        assert "JOIN employees" in sql
        assert "e.org_id = $1" in sql
        # pto_requests has no company_id column — a bare "WHERE company_id"
        # against that table is exactly the crash this pins.
        assert "pto_requests.company_id" not in sql
        assert "pr.company_id" not in sql


class TestListAssetsQueryEscaping:
    @pytest.mark.asyncio
    async def test_percent_and_underscore_in_query_are_escaped(self, monkeypatch):
        class _FetchConn:
            def __init__(self):
                self.fetch_calls = []

            async def fetch(self, sql, *params):
                self.fetch_calls.append((sql, params))
                return []

        conn = _FetchConn()
        monkeypatch.setattr(assets, "get_connection", lambda: _ConnCtx(conn))

        await assets.list_assets(company_id=COMPANY_ID, query="50%_off")

        sql, params = conn.fetch_calls[0]
        assert "ESCAPE '\\'" in sql
        # The literal % and _ arrive escaped so they match literally, not as
        # ILIKE wildcards — a search for "50%_off" must not become
        # "match any 2+ chars starting with 50, then anything, then off".
        like_param = next(p for p in params if isinstance(p, str) and p.startswith("%"))
        assert like_param == "%50\\%\\_off%"


class TestAsUuid:
    def test_valid_uuid_parses(self):
        u = uuid4()
        assert assets._as_uuid(str(u)) == u

    def test_comma_joined_ids_return_none(self):
        # inventory_receipt's record_id is a comma-joined list of movement
        # ids, not a single UUID — status hydration must skip it, not crash.
        assert assets._as_uuid(f"{uuid4()},{uuid4()}") is None

    def test_garbage_returns_none(self):
        assert assets._as_uuid("not-a-uuid") is None
