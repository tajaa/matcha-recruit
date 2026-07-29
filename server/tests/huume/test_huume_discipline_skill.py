"""Incident-triggered discipline skill: the confirm-first envelope
(discipline_from_incident / discipline_decision), the discipline_skill
executors, and the record_view/agent wiring for the fifth show_record type.

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_discipline_skill.py -q

discipline_from_incident DOES re-run the hard-stop classifier (unlike
ir_report/er_case) — it's a discipline write-up, same rule as discipline_draft.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.matcha.services.huume import actions, discipline_skill, record_view
from app.matcha.services.huume.actions import evaluate_huume_action
from app.matcha.services.huume.agent import _HR_OPS_TOOL_SPECS
from app.matcha.services.huume.tools import SHOW_RECORD_TYPES

BASE_ON = {"huume": True, "matcha_work": True, "discipline": True}
EMP_ID = "3f6b1c22-0000-4000-8000-000000000010"
INCIDENT_ID = "3f6b1c22-0000-4000-8000-000000000011"
RECORD_ID = "3f6b1c22-0000-4000-8000-000000000012"


def _features(**extra):
    return {**BASE_ON, **extra}


def _staged_draft(**overrides):
    base = {
        "type": "discipline_from_incident", "status": "proposed", "confirm_id": "ab12cd34",
        "employee_id": EMP_ID, "incident_id": INCIDENT_ID, "infraction_type": "attendance",
        "description": "Missed three shifts without calling in.",
    }
    base.update(overrides)
    return base


def _staged_decision(**overrides):
    base = {"type": "discipline_decision", "status": "proposed", "record_id": RECORD_ID, "decision": "approve"}
    base.update(overrides)
    return base


class TestRequiredFeatureRegistry:
    def test_both_action_types_registered(self):
        assert actions._HUUME_ACTION_REQUIRED_FEATURE["discipline_from_incident"] == "discipline"
        assert actions._HUUME_ACTION_REQUIRED_FEATURE["discipline_decision"] == "discipline"

    def test_unregistered_type_is_refused_before_anything_else(self):
        verdict = evaluate_huume_action(
            staged_action={"type": "not_a_real_type", "status": "proposed"},
            features=_features(), role="client", thread_huume_mode=True, this_turn_staged_new=True,
        )
        assert verdict.kind == "refuse"


class TestStageThenConfirmTwoTurns:
    def test_new_staged_action_returns_stage_verdict(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=True,
        )
        assert verdict.kind == "stage"

    def test_confirm_turn_proceeds(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "proceed"
        assert verdict.action["employee_id"] == EMP_ID
        assert verdict.action["infraction_type"] == "attendance"


class TestDisciplineFromIncidentValidation:
    def test_requires_employee_id_as_uuid(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(employee_id="not-a-uuid"), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_requires_known_infraction_type(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(infraction_type="made_up"), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_requires_description(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(description=""), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_hard_stop_reruns_on_confirm(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(
                infraction_type="policy_violation",
                description="Employee filed a complaint alleging discrimination by a coworker.",
            ),
            features=_features(), role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_ordinary_attendance_narrative_is_not_hard_stopped(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "proceed"

    def test_invalid_incident_id_refused(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(incident_id="not-a-uuid"), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_missing_feature_refused(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(), features=_features(discipline=False), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"


class TestDisciplineDecisionValidation:
    def test_record_id_must_be_uuid(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_decision(record_id="not-a-uuid"), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_decision_must_be_approve_or_deny(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_decision(decision="maybe"), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_deny_without_reason_refused(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_decision(decision="deny"), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_deny_short_reason_refused(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_decision(decision="deny", reason="too short"), features=_features(),
            role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_deny_with_20plus_char_reason_proceeds(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_decision(decision="deny", reason="a" * 20), features=_features(),
            role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "proceed"
        assert verdict.action["reason"] == "a" * 20

    def test_approve_needs_no_reason(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_decision(decision="approve"), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "proceed"


class TestHrOpsToolSpecEntry:
    def test_decide_tool_spec_match_key_is_record_id(self):
        spec = _HR_OPS_TOOL_SPECS["decide_disciplinary_action"]
        assert spec["action_type"] == "discipline_decision"
        assert spec["match_key"] == "record_id"
        assert spec["mints_confirm_id"] is False
        assert spec["done_status"] == "decided"


class TestExecuteRoutesToDisciplineSkill:
    @pytest.mark.asyncio
    async def test_execute_huume_action_dispatches_discipline_from_incident(self, monkeypatch):
        execute_mock = AsyncMock(return_value={"status": "created", "record_id": RECORD_ID})
        monkeypatch.setattr(discipline_skill, "execute", execute_mock)
        result = await actions.execute_huume_action(
            company_id=uuid4(), actor_user_id=uuid4(),
            action={"type": "discipline_from_incident", "employee_id": EMP_ID},
        )
        execute_mock.assert_called_once()
        assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_execute_huume_action_dispatches_discipline_decision(self, monkeypatch):
        execute_mock = AsyncMock(return_value={"status": "created"})
        monkeypatch.setattr(discipline_skill, "execute", execute_mock)
        result = await actions.execute_huume_action(
            company_id=uuid4(), actor_user_id=uuid4(),
            action={"type": "discipline_decision", "record_id": RECORD_ID, "decision": "approve"},
        )
        execute_mock.assert_called_once()
        assert result["status"] == "created"


class TestDisciplineSkillExecute:
    @pytest.mark.asyncio
    async def test_from_incident_uses_incident_occurred_at_when_no_dates_given(self, monkeypatch):
        import datetime
        conn = MagicMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"id": EMP_ID, "first_name": "Jane", "last_name": "Doe"},  # employee lookup
            {"occurred_at": datetime.datetime(2026, 7, 1)},  # incident occurred_at lookup
        ])

        def _conn_ctx():
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx()))

        verdict = {"blocks": [], "advisories": []}
        check_mock = AsyncMock(return_value=verdict)
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_compliance.check_discipline_compliance", check_mock,
        )
        issued_row = {"id": RECORD_ID, "discipline_type": "verbal_warning"}
        issue_mock = AsyncMock(return_value=issued_row)
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_engine.issue_discipline_with_supersede", issue_mock,
        )

        result = await discipline_skill.execute(
            company_id=uuid4(), actor_user_id=uuid4(),
            action={
                "type": "discipline_from_incident", "employee_id": EMP_ID, "incident_id": INCIDENT_ID,
                "infraction_type": "attendance", "description": "Missed shifts.",
                "occurrence_dates": [],
            },
        )

        assert result["status"] == "created"
        assert result["record_id"] == RECORD_ID
        assert "bg_tasks" in result and len(result["bg_tasks"]) == 1
        # occurrence_dates passed to check_discipline_compliance derived from occurred_at
        _, kwargs = check_mock.await_args
        assert kwargs["occurrence_dates"] == [datetime.date(2026, 7, 1)]

    @pytest.mark.asyncio
    async def test_from_incident_blocked_by_compliance_gate(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"id": EMP_ID, "first_name": "Jane", "last_name": "Doe"})

        def _conn_ctx():
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx()))
        verdict = {"blocks": [{"detail": "Employee is on protected FMLA leave."}], "advisories": []}
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_compliance.check_discipline_compliance",
            AsyncMock(return_value=verdict),
        )
        issue_mock = AsyncMock()
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_engine.issue_discipline_with_supersede", issue_mock,
        )

        result = await discipline_skill.execute(
            company_id=uuid4(), actor_user_id=uuid4(),
            action={
                "type": "discipline_from_incident", "employee_id": EMP_ID, "incident_id": None,
                "infraction_type": "attendance", "description": "Missed shifts.",
                "occurrence_dates": [],
            },
        )

        assert result["status"] == "blocked"
        issue_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_decision_approve_none_when_not_pending(self, monkeypatch):
        conn = MagicMock()

        def _conn_ctx():
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx()))
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_engine.approve_record", AsyncMock(return_value=None),
        )

        result = await discipline_skill.execute(
            company_id=uuid4(), actor_user_id=uuid4(),
            action={"type": "discipline_decision", "record_id": RECORD_ID, "decision": "approve"},
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_decision_deny_dispatches_hr_only_notification(self, monkeypatch):
        conn = MagicMock()

        def _conn_ctx():
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx()))
        denied_row = {"id": RECORD_ID, "approval_status": "denied"}
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_engine.deny_record", AsyncMock(return_value=denied_row),
        )

        result = await discipline_skill.execute(
            company_id=uuid4(), actor_user_id=uuid4(),
            action={"type": "discipline_decision", "record_id": RECORD_ID, "decision": "deny", "reason": "x" * 25},
        )

        assert result["status"] == "created"
        assert len(result["bg_tasks"]) == 1


class TestRecordViewParity:
    def test_discipline_is_registered_in_all_four_places(self):
        assert "discipline" in SHOW_RECORD_TYPES
        assert "discipline" in record_view.RECORD_REQUIRED_FEATURE
        assert "discipline" in record_view._MODEL_BUILDERS
        assert "discipline" in record_view._VIEW_BUILDERS
        assert record_view.RECORD_REQUIRED_FEATURE["discipline"] == "discipline"

    @pytest.mark.asyncio
    async def test_model_discipline_batch_is_name_free(self, monkeypatch):
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[{
            "id": RECORD_ID, "discipline_type": "verbal_warning", "infraction_type": "attendance",
            "severity": "moderate", "status": "pending_meeting", "approval_status": "approved",
            "issued_date": None, "review_date": None,
        }])
        out = await record_view._model_disciplines_batch(conn, uuid4(), [RECORD_ID])
        summary = out[RECORD_ID]
        assert "employee_name" not in summary
        assert "description" not in summary
        assert "denial_reason" not in summary
