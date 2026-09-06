"""Pure Huume registry, confirmation-envelope, and prompt tests."""

import pytest

from app.matcha.services.huume.actions import evaluate_huume_action
from app.matcha.services.huume.assets import ASSET_SPECS
from app.matcha.services.huume.agent import (
    _HR_OPS_TOOL_SPECS, _build_choice, _build_hr_ops_staged,
)
from app.matcha.services.huume.prompt import build_state_block
from app.matcha.services.huume.scope import SCHEDULE_TOOLS
from app.matcha.services.huume.tools import TOOLS_BY_NAME


FEATURES = {"huume": True, "matcha_work": True, "employee_schedule": True}
RUN_ID = "3f6b1c22-2000-4000-8000-000000000001"
LOCATION_ID = "3f6b1c22-2000-4000-8000-000000000002"


def _action(**overrides):
    action = {
        "type": "schedule_week_draft",
        "status": "proposed",
        "confirm_id": "ab12cd34",
        "generation_run_id": RUN_ID,
        "location_id": LOCATION_ID,
        "week_start": "2026-08-23",
        "source_mode": "existing",
        "metrics": {"filled_positions": 8, "required_positions": 10, "open_positions": 2},
    }
    action.update(overrides)
    return action


def _profile_action(**overrides):
    action = {
        "type": "schedule_location_profile",
        "status": "proposed",
        "confirm_id": "ef56ab78",
        "location_id": LOCATION_ID,
        "operating_hours": {"1": {"open": "08:00", "close": "17:00"}},
        "blocks": [{
            "name": "Opener", "job_id": "3f6b1c22-2000-4000-8000-000000000003",
            "days_of_week": [1, 2], "start_time": "08:00", "end_time": "16:00",
            "required_staff": 2,
        }],
        "leader_job_id": None,
        "summary": "hours on 1 day, 1 shift block (2 positions/day-slot)",
    }
    action.update(overrides)
    return action


def test_schedule_surface_exposes_readiness_build_and_cancel():
    assert {"get_week_build_readiness", "build_week_schedule", "cancel_staged"} <= SCHEDULE_TOOLS
    assert TOOLS_BY_NAME["get_week_build_readiness"].kind == "read"
    assert TOOLS_BY_NAME["build_week_schedule"].kind == "staged"
    assert not (TOOLS_BY_NAME["build_week_schedule"].declaration.parameters.required or [])
    assert ASSET_SPECS["schedule_week_draft"].ref_table == "schedule_generation_runs"


def test_schedule_surface_exposes_the_location_profile_tools():
    assert {"get_location_schedule_profile", "save_location_schedule_profile"} <= SCHEDULE_TOOLS
    assert TOOLS_BY_NAME["get_location_schedule_profile"].kind == "read"
    assert TOOLS_BY_NAME["save_location_schedule_profile"].kind == "staged"
    # Nothing is required: the model interviews for the fields one at a time.
    assert not (TOOLS_BY_NAME["save_location_schedule_profile"].declaration.parameters.required or [])


def test_finish_can_carry_a_tappable_question():
    finish_properties = TOOLS_BY_NAME["finish"].declaration.parameters.properties
    assert {"question", "options"} <= set(finish_properties)
    assert (TOOLS_BY_NAME["finish"].declaration.parameters.required or []) == ["message"]


def test_profile_spec_mints_and_matches_confirmation_id():
    spec = _HR_OPS_TOOL_SPECS["save_location_schedule_profile"]
    staged, confirming = _build_hr_ops_staged(spec, {"notes": "Busy on match days"}, None)
    assert confirming is False
    assert staged["type"] == "schedule_location_profile"
    assert len(staged["confirm_id"]) == 8

    same, confirming = _build_hr_ops_staged(spec, {"confirm_id": staged["confirm_id"]}, staged)
    assert confirming is True
    assert same is staged


def test_state_block_names_the_profile_confirm_id():
    """The generic fallback line omits confirm_id, and a model that can't read
    the real id guesses the action type string instead — which silently
    re-stages rather than saving (the propose_schedule_change bug of 2026-08)."""
    block = build_state_block({"huume_action": _profile_action()}, schedule_surface=True)
    assert "ef56ab78" in block
    assert "save_location_schedule_profile" in block
    assert "1 shift block" in block


def test_profile_envelope_stages_then_allows_a_valid_save():
    staged = evaluate_huume_action(
        staged_action=_profile_action(), features=FEATURES, role="admin",
        thread_huume_mode=True, this_turn_staged_new=True, schedule_surface=True,
    )
    assert staged.kind == "stage"

    confirmed = evaluate_huume_action(
        staged_action=_profile_action(), features=FEATURES, role="admin",
        thread_huume_mode=True, this_turn_staged_new=False, schedule_surface=True,
    )
    assert confirmed.ok


def test_profile_envelope_refuses_an_empty_save():
    verdict = evaluate_huume_action(
        staged_action=_profile_action(operating_hours={}, blocks=[], summary="no changes"),
        features=FEATURES, role="admin", thread_huume_mode=True,
        this_turn_staged_new=False, schedule_surface=True,
    )
    assert not verdict.ok


def test_profile_envelope_requires_a_job_on_every_block():
    """A block with a free-text role generates ungated shifts nothing can
    match back to a job."""
    verdict = evaluate_huume_action(
        staged_action=_profile_action(blocks=[{
            "name": "Opener", "days_of_week": [1], "start_time": "08:00",
            "end_time": "16:00", "required_staff": 1,
        }]),
        features=FEATURES, role="admin", thread_huume_mode=True,
        this_turn_staged_new=False, schedule_surface=True,
    )
    assert not verdict.ok


def test_profile_envelope_refuses_without_employee_schedule():
    verdict = evaluate_huume_action(
        staged_action=_profile_action(),
        features={"huume": True, "matcha_work": True}, role="admin",
        thread_huume_mode=True, this_turn_staged_new=False, schedule_surface=True,
    )
    assert not verdict.ok


@pytest.mark.parametrize("question,options,expected", [
    ("Which store?", ["Downtown", "Wilshire"], ["Downtown", "Wilshire"]),
    ("Which store?", ["Downtown", "Downtown"], None),   # deduped to one — not a choice
    ("Which store?", ["Downtown"], None),               # a single option is not a question
    ("", ["Downtown", "Wilshire"], None),               # no question, no chips
    ("Which store?", [], None),
])
def test_choice_coercion_only_builds_a_real_finite_choice(question, options, expected):
    choice = _build_choice(question, options)
    if expected is None:
        assert choice is None
    else:
        assert [option["label"] for option in choice["options"]] == expected


def test_choice_coercion_caps_options_and_label_length():
    choice = _build_choice("Which store?", [f"Store {i}" for i in range(12)])
    assert len(choice["options"]) == 6
    long_choice = _build_choice("Which store?", ["x" * 80, "y" * 80])
    assert all(len(option["label"]) <= 40 for option in long_choice["options"])


def test_week_builder_spec_mints_and_matches_confirmation_id():
    spec = _HR_OPS_TOOL_SPECS["build_week_schedule"]
    staged, confirming = _build_hr_ops_staged(spec, {"source_mode": "auto"}, None)
    assert confirming is False
    assert staged["type"] == "schedule_week_draft"
    assert len(staged["confirm_id"]) == 8

    same, confirming = _build_hr_ops_staged(
        spec, {"confirm_id": staged["confirm_id"]}, staged,
    )
    assert confirming is True
    assert same is staged


def test_confirmation_envelope_stages_then_allows_valid_generated_week():
    staged = evaluate_huume_action(
        staged_action=_action(), features=FEATURES, role="admin",
        thread_huume_mode=True, this_turn_staged_new=True, schedule_surface=True,
    )
    assert staged.kind == "stage"

    confirmed = evaluate_huume_action(
        staged_action=_action(), features=FEATURES, role="admin",
        thread_huume_mode=True, this_turn_staged_new=False, schedule_surface=True,
    )
    assert confirmed.ok


def test_confirmation_envelope_rejects_missing_generation_run():
    verdict = evaluate_huume_action(
        staged_action=_action(generation_run_id=None), features=FEATURES, role="admin",
        thread_huume_mode=True, this_turn_staged_new=False, schedule_surface=True,
    )
    assert not verdict.ok


def test_state_block_carries_metrics_and_exact_confirm_tool():
    block = build_state_block({"huume_action": _action()}, schedule_surface=True)
    assert "8/10 positions filled" in block
    assert "2 open" in block
    assert "ab12cd34" in block
    assert "build_week_schedule" in block
    assert "as drafts" in block
