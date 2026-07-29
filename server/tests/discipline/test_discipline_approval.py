"""discipline_engine approval-workflow tests: GAP-1 (approval-gate bypass via
transition_status) and GAP-2 (remedial training assigned before HR approves).

    cd server && ./venv/bin/python -m pytest tests/discipline/test_discipline_approval.py -q
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.matcha.services.discipline import discipline_engine

MOD = "app.matcha.services.discipline.discipline_engine"

NEW_ID = uuid4()
EMPLOYEE_ID = uuid4()
COMPANY_ID = uuid4()
ACTOR_ID = uuid4()
REQUIREMENT_ID = uuid4()


def _conn_ctx(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _noop_transaction():
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _insert_row_from_args(args) -> dict:
    """Rebuild the RETURNING row from the INSERT INTO progressive_discipline
    positional args, in the exact column order discipline_engine.py writes
    them (see issue_discipline_with_supersede). Precise for the tail columns
    this test cares about (remedial_requirement_id .. pending_remedial_requirement_id)."""
    return {
        "id": NEW_ID,
        "employee_id": args[0], "company_id": args[1], "discipline_type": args[2],
        "issued_date": args[3], "issued_by": args[4], "description": args[5],
        "expected_improvement": args[6], "review_date": args[7],
        "status": "draft", "documents": args[8], "infraction_type": args[9],
        "severity": args[10], "lookback_months": args[11], "expires_at": None,
        "escalated_from_id": args[12], "override_level": args[13], "override_reason": args[14],
        "signature_status": "pending", "occurrence_dates": args[15], "situation_narrative": args[16],
        "compliance_check": args[17], "advisory_ack_reason": args[18],
        "remedial_requirement_id": args[19],
        "approval_status": args[20], "approval_requested_at": args[21],
        "source_incident_id": args[22], "template_id": args[23],
        "pending_remedial_requirement_id": args[24],
        "created_at": None, "updated_at": None,
        "approved_by": None, "approval_decided_at": None, "denial_reason": None,
    }


def _make_conn():
    """A conn stub that answers issue_discipline_with_supersede's queries by
    sniffing the SQL text — fetch_active_history returns no active records
    (no supersede path), the policy-mapping lookup returns None (falls to the
    engine's built-in default), and the INSERT RETURNING is rebuilt from its
    own args so the test can assert on exactly what was written."""
    conn = MagicMock()

    async def fetchrow(query, *args):
        if "INSERT INTO progressive_discipline" in query:
            return _insert_row_from_args(args)
        if "FROM training_requirements" in query:
            return {"id": args[0], "title": "Remedial", "training_type": "compliance", "frequency_months": 12}
        if "FROM discipline_policy_mapping" in query:
            return None
        return None

    async def fetch(query, *args):
        if "FROM progressive_discipline" in query and "status = 'active'" in query:
            return []  # fetch_active_history — no active records, no supersede
        return []

    conn.fetchrow = AsyncMock(side_effect=fetchrow)
    conn.fetch = AsyncMock(side_effect=fetch)
    conn.execute = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=_noop_transaction())
    return conn


class TestIssueDisciplineApprovalDefer:
    @pytest.mark.asyncio
    async def test_defers_remedial_when_approval_pending(self, monkeypatch):
        conn = _make_conn()
        monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))
        assign_training_mock = AsyncMock()
        monkeypatch.setattr(f"{MOD}._assign_training", assign_training_mock)

        result = await discipline_engine.issue_discipline_with_supersede(
            actor_user_id=ACTOR_ID, company_id=COMPANY_ID, employee_id=EMPLOYEE_ID,
            infraction_type="attendance", severity="moderate", discipline_type="verbal_warning",
            issued_date="2026-07-28", description="desc", expected_improvement=None,
            remedial_requirement_id=REQUIREMENT_ID, approval_status="pending",
        )

        assert result["remedial_requirement_id"] is None
        assert result["pending_remedial_requirement_id"] == REQUIREMENT_ID
        assert result["approval_status"] == "pending"
        assert result["approval_requested_at"] is not None
        assign_training_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_assigns_remedial_immediately_when_not_required(self, monkeypatch):
        conn = _make_conn()
        monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))
        assign_training_mock = AsyncMock()
        monkeypatch.setattr(f"{MOD}._assign_training", assign_training_mock)

        result = await discipline_engine.issue_discipline_with_supersede(
            actor_user_id=ACTOR_ID, company_id=COMPANY_ID, employee_id=EMPLOYEE_ID,
            infraction_type="attendance", severity="moderate", discipline_type="verbal_warning",
            issued_date="2026-07-28", description="desc", expected_improvement=None,
            remedial_requirement_id=REQUIREMENT_ID,
        )

        assert result["remedial_requirement_id"] == REQUIREMENT_ID
        assert result["pending_remedial_requirement_id"] is None
        assign_training_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_direct_issue_defaults_not_required(self, monkeypatch):
        conn = _make_conn()
        monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))
        monkeypatch.setattr(f"{MOD}._assign_training", AsyncMock())

        result = await discipline_engine.issue_discipline_with_supersede(
            actor_user_id=ACTOR_ID, company_id=COMPANY_ID, employee_id=EMPLOYEE_ID,
            infraction_type="attendance", severity="moderate", discipline_type="verbal_warning",
            issued_date="2026-07-28", description="desc", expected_improvement=None,
        )

        assert result["approval_status"] == "not_required"
        assert result["approval_requested_at"] is None

    @pytest.mark.asyncio
    async def test_invalid_approval_status_raises(self, monkeypatch):
        conn = _make_conn()
        monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))
        with pytest.raises(ValueError):
            await discipline_engine.issue_discipline_with_supersede(
                actor_user_id=ACTOR_ID, company_id=COMPANY_ID, employee_id=EMPLOYEE_ID,
                infraction_type="attendance", severity="moderate", discipline_type="verbal_warning",
                issued_date="2026-07-28", description="desc", expected_improvement=None,
                approval_status="bogus",
            )


class TestTransitionStatusApprovalGuard:
    @pytest.mark.asyncio
    async def test_sql_guards_on_approval_status(self, monkeypatch):
        """GAP-1 pinned at the choke point: the guard clause must be present
        in the SQL text so every one of the 6 real callsites is protected,
        not just whichever ones a caller-level test happens to exercise."""
        conn = MagicMock()
        captured = {}

        async def fetchrow(query, *args):
            captured["query"] = query
            return None

        conn.fetchrow = AsyncMock(side_effect=fetchrow)

        result = await discipline_engine.transition_status(
            conn, NEW_ID, expected_from=["draft", "pending_meeting"], to="pending_signature",
        )

        assert "COALESCE(approval_status, 'not_required') NOT IN ('pending', 'denied')" in captured["query"]
        assert result is None


class TestApproveDenyRecord:
    @pytest.mark.asyncio
    async def test_approve_only_from_pending_returns_none_otherwise(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=None)  # 0-row UPDATE — not pending / wrong tenant
        conn.execute = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=_noop_transaction())

        result = await discipline_engine.approve_record(
            conn, discipline_id=NEW_ID, company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_deny_only_from_pending_returns_none_otherwise(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=None)
        conn.execute = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=_noop_transaction())

        result = await discipline_engine.deny_record(
            conn, discipline_id=NEW_ID, company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            reason="a" * 25,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_deny_writes_denial_reason_and_terminal_status(self, monkeypatch):
        conn = MagicMock()
        captured = {}

        async def fetchrow(query, *args):
            captured["query"] = query
            captured["args"] = args
            row = {c.strip(): None for c in discipline_engine.RECORD_COLUMNS.split(",")}
            row.update({
                "id": NEW_ID, "company_id": COMPANY_ID, "employee_id": EMPLOYEE_ID,
                "approval_status": "denied", "status": "denied", "denial_reason": args[-1],
                "occurrence_dates": [], "compliance_check": None,
            })
            return row

        conn.fetchrow = AsyncMock(side_effect=fetchrow)
        conn.execute = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=_noop_transaction())

        reason = "the incident timeline does not match the write-up" * 1
        result = await discipline_engine.deny_record(
            conn, discipline_id=NEW_ID, company_id=COMPANY_ID, actor_user_id=ACTOR_ID, reason=reason,
        )

        assert result["approval_status"] == "denied"
        assert result["status"] == "denied"
        assert "approval_status = 'pending'" in captured["query"]

    @pytest.mark.asyncio
    async def test_approve_assigns_pending_remedial_and_transitions(self, monkeypatch):
        conn = MagicMock()
        assign_training_mock = AsyncMock()
        monkeypatch.setattr(f"{MOD}._assign_training", assign_training_mock)

        approve_update_row = {
            "id": NEW_ID, "company_id": COMPANY_ID, "employee_id": EMPLOYEE_ID,
            "discipline_type": "verbal_warning", "approval_status": "approved",
            "pending_remedial_requirement_id": REQUIREMENT_ID,
            "status": "draft",
        }
        requirement_row = {"id": REQUIREMENT_ID, "title": "Remedial", "training_type": "compliance", "frequency_months": 12}
        transitioned_row = {c.strip(): None for c in discipline_engine.RECORD_COLUMNS.split(",")}
        transitioned_row.update({
            "id": NEW_ID, "status": "pending_meeting", "approval_status": "approved",
            "occurrence_dates": [], "compliance_check": None,
        })

        calls = {"n": 0}

        async def fetchrow(query, *args):
            calls["n"] += 1
            if "SET approval_status = 'approved'" in query:
                return approve_update_row
            if "FROM training_requirements" in query:
                return requirement_row
            if "UPDATE progressive_discipline" in query and "SET status" in query:
                return transitioned_row
            return None

        conn.fetchrow = AsyncMock(side_effect=fetchrow)
        conn.execute = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=_noop_transaction())

        result = await discipline_engine.approve_record(
            conn, discipline_id=NEW_ID, company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        )

        assign_training_mock.assert_called_once()
        assert result["status"] == "pending_meeting"
        assert result["approval_status"] == "approved"

        # The staged column is CLEARED as the id moves across — a record must not
        # read as both "training staged" and "training assigned".
        moves = [
            c.args for c in conn.execute.await_args_list
            if "remedial_requirement_id" in c.args[0]
        ]
        assert len(moves) == 1
        assert "pending_remedial_requirement_id = NULL" in moves[0][0]

    @pytest.mark.asyncio
    async def test_approve_stamps_advisory_ack_when_the_verdict_had_advisories(self, monkeypatch):
        """POST /records 409s until HR types an ack reason. On the approval path HR
        approval IS the acknowledgment, so the column must not stay NULL on exactly
        the records that carried advisories."""
        conn = MagicMock()
        monkeypatch.setattr(f"{MOD}._assign_training", AsyncMock())

        approved_row = {c.strip(): None for c in discipline_engine.RECORD_COLUMNS.split(",")}
        approved_row.update({
            "id": NEW_ID, "company_id": COMPANY_ID, "employee_id": EMPLOYEE_ID,
            "discipline_type": "verbal_warning", "approval_status": "approved", "status": "draft",
            "pending_remedial_requirement_id": None, "advisory_ack_reason": None,
            "compliance_check": {"blocks": [], "advisories": [{"detail": "recent protected leave"}]},
            "occurrence_dates": [],
        })

        async def fetchrow(query, *args):
            if "SET approval_status = 'approved'" in query:
                return approved_row
            return None

        conn.fetchrow = AsyncMock(side_effect=fetchrow)
        conn.execute = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=_noop_transaction())

        await discipline_engine.approve_record(
            conn, discipline_id=NEW_ID, company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        )

        acks = [c.args for c in conn.execute.await_args_list if "advisory_ack_reason" in c.args[0]]
        assert len(acks) == 1
        query, discipline_id, ack = acks[0]
        assert discipline_id == NEW_ID
        assert str(ACTOR_ID) in ack

    @pytest.mark.asyncio
    async def test_approve_does_not_stamp_ack_without_advisories(self, monkeypatch):
        conn = MagicMock()
        monkeypatch.setattr(f"{MOD}._assign_training", AsyncMock())

        approved_row = {c.strip(): None for c in discipline_engine.RECORD_COLUMNS.split(",")}
        approved_row.update({
            "id": NEW_ID, "company_id": COMPANY_ID, "employee_id": EMPLOYEE_ID,
            "discipline_type": "verbal_warning", "approval_status": "approved", "status": "draft",
            "pending_remedial_requirement_id": None, "advisory_ack_reason": None,
            "compliance_check": {"blocks": [], "advisories": []}, "occurrence_dates": [],
        })

        conn.fetchrow = AsyncMock(side_effect=lambda q, *a: approved_row if "SET approval_status = 'approved'" in q else None)
        conn.execute = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=_noop_transaction())

        await discipline_engine.approve_record(
            conn, discipline_id=NEW_ID, company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        )

        assert not [c for c in conn.execute.await_args_list if "advisory_ack_reason" in c.args[0]]


class TestListRecordsApprovalFilter:
    @pytest.mark.asyncio
    async def test_approval_filter_adds_where_clause(self, monkeypatch):
        conn = MagicMock()
        captured = {}

        async def fetch(query, *args):
            captured["query"] = query
            captured["args"] = args
            return []

        conn.fetch = AsyncMock(side_effect=fetch)

        await discipline_engine.list_records_for_company(
            conn, COMPANY_ID, approval_filter="pending",
        )

        assert "approval_status = $2" in captured["query"]
        assert captured["args"][1] == "pending"


class TestRoutePendingApprovalDeclaredFirst:
    def test_pending_approval_declared_before_id_route(self):
        """FastAPI matches routes in registration order — GET
        /records/pending-approval MUST be declared before
        GET /records/{discipline_id} or the path param swallows it."""
        from app.matcha.routes.employee_lifecycle.discipline import router

        paths = [r.path for r in router.routes if getattr(r, "path", None) and r.path.startswith("/records")]
        pending_idx = paths.index("/records/pending-approval")
        id_idx = paths.index("/records/{discipline_id}")
        assert pending_idx < id_idx
