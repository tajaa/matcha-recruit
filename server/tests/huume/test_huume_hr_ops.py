"""Pure-function tests for the HR-ops staged actions (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_hr_ops.py -q

Covers `evaluate_huume_action`'s ir_report / er_case / training_assign /
pto_decision / ems_promote branches, the table-driven `_build_hr_ops_staged`
confirm-match in agent.py, the registry entries, and the state-block lines
that echo the id each confirm turn must pass back. Mirrors
`test_huume_discipline.py`'s shape.

The deliberate asymmetry worth knowing: ir_report/er_case do NOT run the
hard-stop classifier that discipline_draft does — safety/harassment narrative
is exactly what those records exist to capture, so gating on it would refuse
the reports the tools were added for. `test_no_hard_stop_on_safety_narrative`
pins that.
"""

from app.matcha.services.huume.actions import evaluate_huume_action
from app.matcha.services.huume.agent import _HR_OPS_TOOL_SPECS, _build_hr_ops_staged
from app.matcha.services.huume.prompt import build_state_block
from app.matcha.services.huume.tools import TOOLS_BY_NAME

BASE_ON = {"huume": True, "matcha_work": True}
REQ_ID = "3f6b1c22-0000-4000-8000-000000000001"
EMP_ID = "3f6b1c22-0000-4000-8000-000000000002"
PTO_ID = "3f6b1c22-0000-4000-8000-000000000003"


def _features(**extra):
    return {**BASE_ON, **extra}


def _ir(**overrides):
    base = {"type": "ir_report", "status": "proposed", "confirm_id": "ab12cd34",
            "description": "Forklift clipped a pallet rack in Bay 3."}
    base.update(overrides)
    return base


def _er(**overrides):
    base = {"type": "er_case", "status": "proposed", "confirm_id": "ef56ab78",
            "description": "Two team leads escalated a dispute over shift swaps."}
    base.update(overrides)
    return base


def _training(**overrides):
    base = {"type": "training_assign", "status": "proposed",
            "requirement_id": REQ_ID, "employee_ids": [EMP_ID]}
    base.update(overrides)
    return base


EVENT_ID = "3f6b1c22-0000-4000-8000-000000000004"


def _promote(**overrides):
    base = {"type": "ems_promote", "status": "proposed", "event_id": EVENT_ID}
    base.update(overrides)
    return base


def _pto(**overrides):
    base = {"type": "pto_decision", "status": "proposed",
            "request_id": PTO_ID, "decision": "approve"}
    base.update(overrides)
    return base


def _evaluate(staged, features, *, role="client", staged_new=False):
    return evaluate_huume_action(
        staged_action=staged, features=features, role=role,
        thread_huume_mode=True, this_turn_staged_new=staged_new,
    )


class TestStageAndAuthz:
    """The shared envelope: fresh call stages, gates refuse BEFORE staging."""

    CASES = [
        (_ir(), "incidents"),
        (_er(), "er_copilot"),
        (_training(), "training"),
        (_pto(), "time_off"),
        (_promote(), "ems"),
    ]

    def test_fresh_call_stages(self):
        for staged, flag in self.CASES:
            verdict = _evaluate(staged, _features(**{flag: True}), staged_new=True)
            assert verdict.kind == "stage", staged["type"]
            assert not verdict.ok

    def test_confirm_turn_proceeds(self):
        for staged, flag in self.CASES:
            verdict = _evaluate(staged, _features(**{flag: True}))
            assert verdict.ok, staged["type"]
            assert verdict.action["type"] == staged["type"]

    def test_missing_subsystem_flag_refuses_even_when_staging(self):
        # A doomed caller is refused immediately, never told "reply confirm"
        # and only refused on the later turn.
        for staged, flag in self.CASES:
            verdict = _evaluate(staged, _features(**{flag: False}), staged_new=True)
            assert verdict.kind == "refuse", staged["type"]
            assert flag in verdict.message

    def test_employee_role_refused(self):
        for staged, flag in self.CASES:
            verdict = _evaluate(staged, _features(**{flag: True}), role="employee", staged_new=True)
            assert verdict.kind == "refuse", staged["type"]
            assert "business admin" in verdict.message

    def test_non_proposed_status_refused(self):
        for staged, flag in self.CASES:
            done = {**staged, "status": "filed"}
            verdict = _evaluate(done, _features(**{flag: True}))
            assert verdict.kind == "refuse", staged["type"]


class TestIrReportValidation:
    def test_empty_description_refuses(self):
        verdict = _evaluate(_ir(description="   "), _features(incidents=True))
        assert verdict.kind == "refuse"

    def test_unparseable_occurred_at_refuses(self):
        verdict = _evaluate(_ir(occurred_at="last tuesday-ish"), _features(incidents=True))
        assert verdict.kind == "refuse"

    def test_iso_date_accepted_as_occurred_at(self):
        verdict = _evaluate(_ir(occurred_at="2026-07-20"), _features(incidents=True))
        assert verdict.ok

    def test_unknown_type_and_severity_dropped_not_refused(self):
        # create_incident_core defaults them and the classifier fills the rest;
        # refusing would strand a real report over a model typo.
        verdict = _evaluate(_ir(incident_type="kerfuffle", severity="spicy"), _features(incidents=True))
        assert verdict.ok
        assert "incident_type" not in verdict.action
        assert "severity" not in verdict.action

    def test_known_type_and_severity_kept(self):
        verdict = _evaluate(_ir(incident_type="Safety", severity="HIGH"), _features(incidents=True))
        assert verdict.action["incident_type"] == "safety"
        assert verdict.action["severity"] == "high"

    def test_no_hard_stop_on_safety_narrative(self):
        # Unlike discipline_draft: an incident report IS the sanctioned channel
        # for this content.
        verdict = _evaluate(
            _ir(description="Employee slipped on a wet floor and hurt their wrist; possible OSHA recordable."),
            _features(incidents=True),
        )
        assert verdict.ok


class TestErCaseValidation:
    def test_empty_description_refuses(self):
        verdict = _evaluate(_er(description=""), _features(er_copilot=True))
        assert verdict.kind == "refuse"

    def test_unknown_category_dropped(self):
        verdict = _evaluate(_er(category="vibes"), _features(er_copilot=True))
        assert verdict.ok
        assert "category" not in verdict.action

    def test_known_category_normalized(self):
        verdict = _evaluate(_er(category="Harassment"), _features(er_copilot=True))
        assert verdict.action["category"] == "harassment"

    def test_no_hard_stop_on_harassment_narrative(self):
        verdict = _evaluate(
            _er(description="A supervisor is alleged to have made repeated inappropriate comments."),
            _features(er_copilot=True),
        )
        assert verdict.ok


class TestTrainingAssignValidation:
    def test_non_uuid_requirement_refuses(self):
        verdict = _evaluate(_training(requirement_id="forklift safety"), _features(training=True))
        assert verdict.kind == "refuse"
        assert "lookup_context" in verdict.message

    def test_empty_employee_ids_refuses(self):
        verdict = _evaluate(_training(employee_ids=[]), _features(training=True))
        assert verdict.kind == "refuse"

    def test_employee_name_instead_of_id_refuses(self):
        verdict = _evaluate(_training(employee_ids=["Jane Doe"]), _features(training=True))
        assert verdict.kind == "refuse"

    def test_too_many_assignees_refuses(self):
        verdict = _evaluate(_training(employee_ids=[EMP_ID] * 51), _features(training=True))
        assert verdict.kind == "refuse"
        assert "50" in verdict.message

    def test_bad_due_date_refuses(self):
        verdict = _evaluate(_training(due_date="whenever"), _features(training=True))
        assert verdict.kind == "refuse"

    def test_valid_payload_normalizes(self):
        verdict = _evaluate(_training(due_date="2026-09-01"), _features(training=True))
        assert verdict.ok
        assert verdict.action["employee_ids"] == [EMP_ID]
        assert verdict.action["due_date"] == "2026-09-01"


class TestPtoDecisionValidation:
    def test_non_uuid_request_refuses(self):
        verdict = _evaluate(_pto(request_id="jane's pto"), _features(time_off=True))
        assert verdict.kind == "refuse"

    def test_unknown_decision_refuses(self):
        verdict = _evaluate(_pto(decision="maybe"), _features(time_off=True))
        assert verdict.kind == "refuse"

    def test_deny_without_reason_refuses(self):
        # decide_pto_request_core requires denial_reason — catching it here
        # gives the model a relayable message instead of a failed execute.
        verdict = _evaluate(_pto(decision="deny"), _features(time_off=True))
        assert verdict.kind == "refuse"
        assert "reason" in verdict.message.lower()

    def test_deny_with_reason_proceeds(self):
        verdict = _evaluate(_pto(decision="deny", note="Blackout week for inventory."), _features(time_off=True))
        assert verdict.ok
        assert verdict.action["decision"] == "deny"

    def test_approve_needs_no_note(self):
        verdict = _evaluate(_pto(), _features(time_off=True))
        assert verdict.ok
        assert verdict.action["note"] is None


class TestEmsPromoteValidation:
    def test_non_uuid_event_id_refuses(self):
        verdict = _evaluate(_promote(event_id="not-a-uuid"), _features(ems=True))
        assert verdict.kind == "refuse"
        assert "lookup_context" in verdict.message

    def test_bad_occurred_at_refuses(self):
        verdict = _evaluate(_promote(occurred_at="whenever"), _features(ems=True))
        assert verdict.kind == "refuse"

    def test_valid_payload_proceeds(self):
        verdict = _evaluate(_promote(), _features(ems=True))
        assert verdict.ok
        assert verdict.action["event_id"] == EVENT_ID

    def test_iso_occurred_at_parsed_to_datetime(self):
        # Unlike ir_report (which leaves occurred_at as a raw string —
        # create_incident_core's own parser handles it), this one MUST be a
        # real datetime object: ems.promote.promote_event runs
        # naive_occurred_at on it, which checks .tzinfo — a bare string has
        # no such attribute and the check would silently no-op.
        import datetime
        verdict = _evaluate(_promote(occurred_at="2026-07-30T17:20:00"), _features(ems=True))
        assert verdict.ok
        assert isinstance(verdict.action["occurred_at"], datetime.datetime)

    def test_unknown_incident_type_and_severity_dropped(self):
        verdict = _evaluate(_promote(incident_type="kerfuffle", severity="spicy"), _features(ems=True))
        assert verdict.ok
        assert verdict.action["incident_type"] is None
        assert verdict.action["severity"] is None

    def test_known_incident_type_and_severity_kept(self):
        verdict = _evaluate(_promote(incident_type="Safety", severity="HIGH"), _features(ems=True))
        assert verdict.action["incident_type"] == "safety"
        assert verdict.action["severity"] == "high"

    def test_no_hard_stop_on_behavioral_narrative(self):
        # Same reasoning as ir_report: promoting an already-logged event is
        # not new disclosure of the content, just a status change.
        verdict = _evaluate(_promote(title="Repeated harassment complaint from front desk"), _features(ems=True))
        assert verdict.ok


class TestBuildHrOpsStaged:
    """The two-turn confirm match, compared against the TURN-START snapshot."""

    def test_no_pre_turn_action_stages_new(self):
        spec = _HR_OPS_TOOL_SPECS["report_incident"]
        staged, confirming = _build_hr_ops_staged(spec, {"description": "Rack collapse."}, None)
        assert confirming is False
        assert staged["status"] == "proposed"
        assert len(staged["confirm_id"]) == 8

    def test_echoed_confirm_id_confirms(self):
        spec = _HR_OPS_TOOL_SPECS["report_incident"]
        existing = _ir()
        staged, confirming = _build_hr_ops_staged(
            spec, {"description": "Rack collapse.", "confirm_id": existing["confirm_id"]}, existing,
        )
        assert confirming is True
        assert staged is existing

    def test_wrong_confirm_id_stages_new(self):
        spec = _HR_OPS_TOOL_SPECS["report_incident"]
        staged, confirming = _build_hr_ops_staged(
            spec, {"description": "Rack collapse.", "confirm_id": "99999999"}, _ir(),
        )
        assert confirming is False
        assert staged["confirm_id"] != "99999999"   # server mints its own

    def test_omitted_confirm_id_stages_new(self):
        spec = _HR_OPS_TOOL_SPECS["report_incident"]
        _, confirming = _build_hr_ops_staged(spec, {"description": "Rack collapse."}, _ir())
        assert confirming is False

    def test_natural_id_tools_match_on_their_own_key(self):
        spec = _HR_OPS_TOOL_SPECS["decide_pto_request"]
        existing = _pto()
        _, confirming = _build_hr_ops_staged(spec, {"request_id": PTO_ID, "decision": "approve"}, existing)
        assert confirming is True
        _, other = _build_hr_ops_staged(spec, {"request_id": REQ_ID, "decision": "approve"}, existing)
        assert other is False

    def test_terminal_pre_turn_action_is_not_confirmable(self):
        spec = _HR_OPS_TOOL_SPECS["decide_pto_request"]
        done = _pto(status="decided")
        _, confirming = _build_hr_ops_staged(spec, {"request_id": PTO_ID, "decision": "approve"}, done)
        assert confirming is False

    def test_promote_ems_event_matches_on_event_id(self):
        spec = _HR_OPS_TOOL_SPECS["promote_ems_event"]
        existing = _promote()
        _, confirming = _build_hr_ops_staged(spec, {"event_id": EVENT_ID}, existing)
        assert confirming is True
        _, other = _build_hr_ops_staged(spec, {"event_id": "3f6b1c22-0000-4000-8000-000000000099"}, existing)
        assert other is False

    def test_promote_ems_event_changed_severity_restages_instead_of_executing_stale(self):
        """The bug: admin stages a promote at severity='low', then replies
        'yes, but mark it critical' — the model calls with the SAME event_id
        but severity='critical'. Matching on event_id alone would return
        `existing` (the ORIGINAL severity) with confirming=True, silently
        filing the incident at the wrong severity."""
        spec = _HR_OPS_TOOL_SPECS["promote_ems_event"]
        existing = _promote(incident_type="safety", severity="low")
        staged, confirming = _build_hr_ops_staged(
            spec, {"event_id": EVENT_ID, "severity": "critical"}, existing,
        )
        assert confirming is False
        assert staged["severity"] == "critical"

    def test_promote_ems_event_unchanged_severity_still_confirms(self):
        spec = _HR_OPS_TOOL_SPECS["promote_ems_event"]
        existing = _promote(incident_type="safety", severity="low")
        staged, confirming = _build_hr_ops_staged(
            spec, {"event_id": EVENT_ID, "severity": "low"}, existing,
        )
        assert confirming is True
        assert staged is existing

    def test_employee_ids_coerced_to_strings(self):
        spec = _HR_OPS_TOOL_SPECS["assign_training"]
        staged, _ = _build_hr_ops_staged(spec, {"requirement_id": REQ_ID, "employee_ids": [EMP_ID]}, None)
        assert staged["employee_ids"] == [EMP_ID]
        assert "confirm_id" not in staged   # has a natural id already

    def test_changed_decision_on_confirm_turn_restages_instead_of_executing_stale(self):
        """The bug: admin stages 'approve' on record X, then on the reply says
        'no, deny it instead' — the model calls with the SAME record_id but
        decision='deny'. Matching on record_id alone would return `existing`
        (the ORIGINAL 'approve' proposal) with confirming=True, silently
        executing the approve the admin just reversed and discarding the
        denial reason. A changed decision-bearing field must force a fresh
        stage instead."""
        spec = _HR_OPS_TOOL_SPECS["decide_disciplinary_action"]
        existing = {
            "type": "discipline_decision", "status": "proposed",
            "record_id": REQ_ID, "decision": "approve", "reason": None,
        }
        staged, confirming = _build_hr_ops_staged(
            spec, {"record_id": REQ_ID, "decision": "deny", "reason": "Insufficient documentation on file."},
            existing,
        )
        assert confirming is False
        assert staged["decision"] == "deny"
        assert staged["reason"] == "Insufficient documentation on file."

    def test_unchanged_decision_on_confirm_turn_still_confirms(self):
        spec = _HR_OPS_TOOL_SPECS["decide_disciplinary_action"]
        existing = {
            "type": "discipline_decision", "status": "proposed",
            "record_id": REQ_ID, "decision": "approve", "reason": None,
        }
        staged, confirming = _build_hr_ops_staged(
            spec, {"record_id": REQ_ID, "decision": "approve"}, existing,
        )
        assert confirming is True
        assert staged is existing

    def test_free_text_field_drift_on_confirm_turn_still_confirms(self):
        """Only `decision_fields` (decision/status enums) force a re-stage — a
        free-text field the model may legitimately rephrase between turns
        (report_incident/open_er_case have no decision_fields at all) must
        not spuriously break the confirm match."""
        spec = _HR_OPS_TOOL_SPECS["report_incident"]
        existing = _ir()
        staged, confirming = _build_hr_ops_staged(
            spec, {"description": "Different wording of the same incident.", "confirm_id": existing["confirm_id"]},
            existing,
        )
        assert confirming is True
        assert staged is existing


class TestRegistry:
    def test_all_hr_ops_tools_declared_and_staged(self):
        for name in _HR_OPS_TOOL_SPECS:
            tool = TOOLS_BY_NAME.get(name)
            assert tool is not None, name
            assert tool.kind == "staged", name

    def test_required_params_declared(self):
        expected = {
            "report_incident": {"description"},
            "open_er_case": {"description"},
            "assign_training": {"requirement_id", "employee_ids"},
            "decide_pto_request": {"request_id", "decision"},
            "promote_ems_event": {"event_id"},
        }
        for name, required in expected.items():
            declared = set(TOOLS_BY_NAME[name].declaration.parameters.required or [])
            assert declared == required, name

    def test_documents_topic_registered_and_gated(self):
        from app.matcha.services.huume.onboarding_skill import _TOPIC_REQUIRED_FEATURE
        from app.matcha.services.huume.tools import LOOKUP_TOPICS

        assert "documents" in LOOKUP_TOPICS
        assert _TOPIC_REQUIRED_FEATURE["documents"] == "employees"

    def test_every_spec_action_type_has_a_feature(self):
        from app.matcha.services.huume.actions import _HUUME_ACTION_REQUIRED_FEATURE

        for spec in _HR_OPS_TOOL_SPECS.values():
            assert spec["action_type"] in _HUUME_ACTION_REQUIRED_FEATURE


class TestStateBlock:
    def test_each_type_echoes_its_confirm_key(self):
        cases = [
            (_ir(), "ab12cd34"),
            (_er(), "ef56ab78"),
            (_training(), REQ_ID),
            (_pto(), PTO_ID),
            (_promote(), EVENT_ID),
        ]
        for action, needle in cases:
            block = build_state_block({"huume_action": action})
            assert needle in block, action["type"]
            assert "STAGED ACTION" in block

    def test_terminal_action_renders_nothing_staged(self):
        block = build_state_block({"huume_action": _ir(status="filed")})
        assert "STAGED ACTION" not in block

    def test_pto_block_names_the_decision(self):
        block = build_state_block({"huume_action": _pto(decision="deny", note="Blackout week.")})
        assert "deny" in block
