"""Incident-triggered discipline skill: the confirm-first envelope
(discipline_from_incident / discipline_decision), the discipline_skill
executors, and the record_view/agent wiring for the fifth show_record type.

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_discipline_skill.py -q

discipline_from_incident re-runs the hard-stop classifier ONLY on a STANDALONE
draft. With an incident_id the content already reached the company through its
sanctioned legal-record channel (the ir_report asymmetry), and the classifier's
safety patterns match nearly every real safety incident — re-running it there
would refuse the flagship incident->discipline path outright.
"""

from datetime import datetime
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

    def test_hard_stop_reruns_on_confirm_for_a_standalone_draft(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(
                incident_id=None,
                infraction_type="policy_violation",
                description="Employee filed a complaint alleging discrimination by a coworker.",
            ),
            features=_features(), role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_incident_sourced_safety_narrative_proceeds(self):
        """The carve-out that makes the skill usable: an incident is already the
        company's filed legal record of this conduct, and an approver reviews the
        write-up before anything issues. Without it the supervisor-surface
        workplace_safety patterns (`injury`, `accident`, `bleeding`, `OSHA`)
        refuse nearly every real safety incident's own narrative."""
        narrative = "Employee removed the machine guard; the resulting accident caused an injury to a coworker."
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(infraction_type="safety", description=narrative),
            features=_features(), role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "proceed"

    def test_same_narrative_standalone_is_refused(self):
        narrative = "Employee removed the machine guard; the resulting accident caused an injury to a coworker."
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(incident_id=None, infraction_type="safety", description=narrative),
            features=_features(), role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_severity_vocabulary_matches_the_engine(self):
        """A narrower set here silently downgrades the record: an unrecognized
        severity becomes None and then the executor's "moderate" default."""
        from app.matcha.services.discipline.discipline_engine import VALID_SEVERITIES
        assert actions._DISCIPLINE_SEVERITIES == set(VALID_SEVERITIES)
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(severity="immediate_written"),
            features=_features(), role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "proceed"
        assert verdict.action["severity"] == "immediate_written"

    def test_ordinary_attendance_narrative_is_not_hard_stopped(self):
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(), features=_features(), role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "proceed"

    def test_standalone_draft_without_occurrence_dates_is_refused(self):
        """Without an incident_id there's no _resolve_occurrence_dates fallback
        to the incident's own occurred_at — an empty occurrence_dates list
        would leave check_discipline_compliance nothing to test against
        protected leave, so the statutory hard block could silently never
        fire for a standalone attendance write-up."""
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(incident_id=None, occurrence_dates=[]),
            features=_features(), role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

    def test_incident_sourced_draft_without_occurrence_dates_proceeds(self):
        """With an incident_id, the fallback to the incident's occurred_at
        happens downstream in discipline_skill._resolve_occurrence_dates —
        an empty list here is fine, it's only the standalone case that's
        refused."""
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(occurrence_dates=[]),
            features=_features(), role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "proceed"

    def test_too_many_occurrence_dates_refused(self):
        dates = [f"2026-01-{d:02d}" for d in range(1, 32)]  # 31 > cap of 30
        verdict = evaluate_huume_action(
            staged_action=_staged_draft(occurrence_dates=dates),
            features=_features(), role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.kind == "refuse"

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
    async def test_from_incident_refuses_when_incident_unresolved_for_company(self, monkeypatch):
        """A supplied incident_id that doesn't resolve for THIS company (wrong
        tenant, or simply doesn't exist) must refuse rather than silently
        writing the unvalidated id as source_incident_id — a foreign-tenant
        id landing on the record would later let discipline_filing insert the
        signed letter's storage_path into another company's
        ir_incident_documents."""
        conn = MagicMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"id": EMP_ID, "first_name": "Jane", "last_name": "Doe"},  # employee lookup
            None,  # incident lookup — no row for this company_id
        ])

        def _conn_ctx():
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx()))
        check_mock = AsyncMock()
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_compliance.check_discipline_compliance", check_mock,
        )
        issue_mock = AsyncMock()
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

        assert result["status"] == "error"
        check_mock.assert_not_awaited()
        issue_mock.assert_not_awaited()

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

    @pytest.mark.asyncio
    async def test_decision_label_reads_denied_not_denyd(self, monkeypatch):
        conn = MagicMock()

        def _conn_ctx():
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx()))
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_engine.deny_record",
            AsyncMock(return_value={"id": RECORD_ID, "approval_status": "denied"}),
        )

        result = await discipline_skill.execute(
            company_id=uuid4(), actor_user_id=uuid4(),
            action={"type": "discipline_decision", "record_id": RECORD_ID, "decision": "deny", "reason": "x" * 25},
        )
        assert result["record_label"] == "Discipline decision — denied"


class TestStageEnrichment:
    """The staged dict the Huume panel renders. employee_name is display-only —
    the executor always uses employee_id — but without it every banner reads
    "Stage disciplinary action for employee"."""

    @pytest.mark.asyncio
    async def test_adds_employee_name_for_display(self):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": EMP_ID, "first_name": "Jane", "last_name": "Doe",
            "job_title": "RDA", "manager_id": None,
        })
        conn.fetch = AsyncMock(return_value=[])       # no templates
        conn.fetchval = AsyncMock(return_value=None)

        enriched = await discipline_skill.stage_enrichment(
            conn, company_id=uuid4(),
            staged={"employee_id": EMP_ID, "infraction_type": "attendance",
                    "description": "Missed shifts.", "incident_id": None},
        )
        assert enriched["employee_name"] == "Jane Doe"

    @pytest.mark.asyncio
    async def test_unknown_employee_returns_the_staged_dict_untouched(self):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=None)
        staged = {"employee_id": EMP_ID, "infraction_type": "attendance", "description": "d"}

        enriched = await discipline_skill.stage_enrichment(conn, company_id=uuid4(), staged=staged)
        assert enriched == staged
        assert "employee_name" not in enriched


class TestResolveOccurrenceDates:
    """Found on a live tenant: the preview rendered "conduct occurring on ,"
    while the filed record carried the incident's own date, because the preview
    and the executor each derived the dates separately. The letter the admin
    approved was not the letter that got filed. One helper now, used by both."""

    def test_admin_supplied_dates_win(self):
        from datetime import date
        row = {"occurred_at": datetime(2026, 7, 4)}
        assert discipline_skill._resolve_occurrence_dates(["2026-07-20"], row) == [date(2026, 7, 20)]

    def test_falls_back_to_the_incident_date(self):
        from datetime import date
        row = {"occurred_at": datetime(2026, 7, 4, 3, 6)}
        assert discipline_skill._resolve_occurrence_dates([], row) == [date(2026, 7, 4)]

    def test_no_dates_and_no_incident_is_empty(self):
        assert discipline_skill._resolve_occurrence_dates(None, None) == []

    def test_accepts_date_objects_as_well_as_iso_strings(self):
        from datetime import date
        assert discipline_skill._resolve_occurrence_dates([date(2026, 7, 20)], None) == [date(2026, 7, 20)]

    @pytest.mark.asyncio
    async def test_preview_carries_the_dates_the_executor_will_file(self):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"id": EMP_ID, "first_name": "Jane", "last_name": "Doe", "job_title": "RDA", "manager_id": None},
            {"id": INCIDENT_ID, "incident_number": "IR-1", "occurred_at": datetime(2026, 7, 4)},
        ])
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchval = AsyncMock(return_value=None)

        enriched = await discipline_skill.stage_enrichment(
            conn, company_id=uuid4(),
            staged={"employee_id": EMP_ID, "incident_id": INCIDENT_ID,
                    "infraction_type": "safety", "description": "d", "occurrence_dates": []},
        )
        assert enriched["occurrence_dates"] == ["2026-07-04"]


class TestCheckIncidentPolicyFeatureGate:
    @pytest.mark.asyncio
    async def test_handbooks_off_is_module_off_not_a_clean_result(self, monkeypatch):
        """Three-state: without a corpus there is nothing to check against, and an
        empty violations list would read as "your handbook has nothing relevant"."""
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": INCIDENT_ID, "title": "t", "description": "d",
            "incident_type": "safety", "severity": "high", "incident_number": "IR-1",
        })

        def _conn_ctx():
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        # check_incident_policy uses a raw non-pooled connection
        # (connection_or_direct, force_direct=True) rather than the shared
        # pool — see its docstring — so that's what needs patching here.
        monkeypatch.setattr("app.database.pool.connection_or_direct", lambda **kw: _conn_ctx())
        monkeypatch.setattr(
            "app.core.feature_flags.get_company_features",
            AsyncMock(return_value={"handbooks": False, "discipline": True}),
        )
        check = AsyncMock()
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_policy_check.check_incident_against_handbook", check,
        )

        result = await discipline_skill.check_incident_policy(company_id=uuid4(), incident_id=INCIDENT_ID)

        assert result["status"] == "module_off"
        check.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_discipline_off_is_module_off_even_with_handbooks_on(self, monkeypatch):
        """tool_declarations() advertises this tool regardless of company flags —
        unlike the staged HR-ops actions it had no per-call `discipline` re-check
        at all, only `handbooks`. A company with handbooks but not discipline
        must not be able to run the check."""
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": INCIDENT_ID, "title": "t", "description": "d",
            "incident_type": "safety", "severity": "high", "incident_number": "IR-1",
        })

        def _conn_ctx():
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        monkeypatch.setattr("app.database.pool.connection_or_direct", lambda **kw: _conn_ctx())
        monkeypatch.setattr(
            "app.core.feature_flags.get_company_features",
            AsyncMock(return_value={"handbooks": True, "discipline": False}),
        )
        check = AsyncMock()
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_policy_check.check_incident_against_handbook", check,
        )

        result = await discipline_skill.check_incident_policy(company_id=uuid4(), incident_id=INCIDENT_ID)

        assert result["status"] == "module_off"
        check.assert_not_awaited()


class TestListPendingFeatureGate:
    @pytest.mark.asyncio
    async def test_discipline_off_is_module_off(self, monkeypatch):
        conn = MagicMock()

        def _conn_ctx():
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx()))
        monkeypatch.setattr(
            "app.core.feature_flags.get_company_features",
            AsyncMock(return_value={"discipline": False}),
        )
        list_mock = AsyncMock()
        monkeypatch.setattr(
            "app.matcha.services.discipline.discipline_engine.list_pending_approval", list_mock,
        )

        result = await discipline_skill.list_pending(company_id=uuid4())

        assert result["status"] == "module_off"
        list_mock.assert_not_awaited()


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
