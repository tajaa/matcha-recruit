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
