"""Pure Huume registry, confirmation-envelope, and prompt tests."""

from app.matcha.services.huume.actions import evaluate_huume_action
from app.matcha.services.huume.assets import ASSET_SPECS
from app.matcha.services.huume.agent import _HR_OPS_TOOL_SPECS, _build_hr_ops_staged
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


def test_schedule_surface_exposes_readiness_build_and_cancel():
    assert {"get_week_build_readiness", "build_week_schedule", "cancel_staged"} <= SCHEDULE_TOOLS
    assert TOOLS_BY_NAME["get_week_build_readiness"].kind == "read"
    assert TOOLS_BY_NAME["build_week_schedule"].kind == "staged"
    assert not (TOOLS_BY_NAME["build_week_schedule"].declaration.parameters.required or [])
    assert ASSET_SPECS["schedule_week_draft"].ref_table == "schedule_generation_runs"


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
