"""Pure Huume registry, confirmation-envelope, and prompt tests."""

from datetime import date
from uuid import UUID

import pytest

from app.matcha.services.huume.actions import evaluate_huume_action
from app.matcha.services.huume.assets import ASSET_SPECS
from app.matcha.services.huume.agent import (
    _HR_OPS_TOOL_SPECS, _build_choice, _build_hr_ops_staged,
)
from app.matcha.services.huume.prompt import build_state_block, build_system_prompt
from app.matcha.services.huume.scope import SCHEDULE_TOOLS, HuumeSurfaceContext
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


def _schedule_surface() -> HuumeSurfaceContext:
    return HuumeSurfaceContext(
        surface="schedule_assistant",
        location_id=UUID(LOCATION_ID),
        week_start=date(2026, 8, 23),
        week_end=date(2026, 8, 29),
        allowed_tools=SCHEDULE_TOOLS,
    )


def test_system_prompt_carries_the_locations_saved_profile():
    """The schedule surface has no per-turn context builder, so the saved setup
    rides in the system prompt — otherwise the model spends a tool call
    rediscovering it before every intake question."""
    prompt = build_system_prompt(
        company_name="Sunset Smile", today="2026-08-23",
        surface_context=_schedule_surface(),
        location_profile_block="Hours: Mon 08:00–17:00\nMissing: leader_rule",
    )
    assert "Hours: Mon 08:00–17:00" in prompt
    assert "Missing: leader_rule" in prompt


def test_system_prompt_says_so_when_no_profile_is_saved_yet():
    prompt = build_system_prompt(
        company_name="Sunset Smile", today="2026-08-23",
        surface_context=_schedule_surface(),
    )
    assert "No scheduling profile saved yet" in prompt
    # ...and the model is told to interview rather than refuse.
    assert "interview them instead" in prompt


def test_choice_keeps_the_send_text_for_an_over_long_option():
    """The label is trimmed for the button; the send text is keyed on the FULL
    option, or a long template name would post back a chopped name that
    resolves to nothing."""
    names = ["Downtown weekday coverage — standard rotation v2", "Weekend"]
    choice = _build_choice(
        "Which week template should I use?", names,
        sends={name: f"Use the week template named {name}" for name in names},
    )
    assert len(choice["options"][0]["label"]) == 40
    assert choice["options"][0]["send"] == f"Use the week template named {names[0]}"
    assert choice["options"][1]["send"] == "Use the week template named Weekend"


# --- coverage + break findings -------------------------------------------------

FINDINGS = [
    {"kind": "close_buffer_uncovered", "severity": "gap", "day": "2026-08-24",
     "weekday": 1, "window": {"start": "17:00", "end": "17:20"}, "shift_key": None,
     "job_id": None, "job_name": None, "employee_name": None, "minutes": 20,
     "detail": "Nobody is scheduled to close on Monday (17:00–17:20, 20 min after the doors shut)."},
    {"kind": "break_relief_uncovered", "severity": "gap", "day": "2026-08-25",
     "weekday": 2, "window": {"start": "08:00", "end": "17:00"}, "shift_key": "s2",
     "job_id": None, "job_name": "Barista", "employee_name": "Amy", "minutes": 30,
     "detail": "Nobody can relieve Amy for their 30-minute break on this shift."},
    {"kind": "thin_close", "severity": "advisory", "day": "2026-08-26", "weekday": 3,
     "window": {"start": "16:00", "end": "17:00"}, "shift_key": None, "job_id": None,
     "job_name": None, "employee_name": None, "minutes": None,
     "detail": "Wednesday opens with 3 on but closes with one."},
]


def test_state_block_names_the_gaps_not_just_a_count():
    """A later turn sees only this text. "3 gaps" with no detail is a number
    the model cannot turn into anything the manager can act on."""
    block = build_state_block({"huume_action": _action(
        findings=FINDINGS,
        metrics={"filled_positions": 8, "required_positions": 10, "open_positions": 2,
                 "gap_count": 2, "operating_hours_known": True},
    )}, schedule_surface=True)

    assert "2 coverage/break gap(s), 3 finding(s)" in block
    assert "Nobody is scheduled to close on Monday" in block
    assert "Nobody can relieve Amy" in block


def test_state_block_says_coverage_was_not_checked_without_saved_hours():
    """"No gaps found" and "I could not look" must never read the same."""
    block = build_state_block({"huume_action": _action(
        findings=[],
        metrics={"filled_positions": 8, "required_positions": 8, "open_positions": 0,
                 "operating_hours_known": False},
    )}, schedule_surface=True)

    assert "hours are not saved" in block
    assert "was NOT checked" in block


def test_the_profile_spec_carries_the_open_and_close_buffers():
    """A field missing from `fields` is dropped from the staged dict, so the
    confirm turn would write a profile without the buffer the manager gave."""
    spec = _HR_OPS_TOOL_SPECS["save_location_schedule_profile"]
    assert {"open_buffer_minutes", "close_buffer_minutes"} <= set(spec["fields"])

    staged, _confirming = _build_hr_ops_staged(
        spec, {"open_buffer_minutes": 30, "close_buffer_minutes": 0}, None,
    )
    assert staged["open_buffer_minutes"] == 30
    assert staged["close_buffer_minutes"] == 0


def test_the_profile_tool_exposes_the_buffers_to_the_model():
    properties = TOOLS_BY_NAME["save_location_schedule_profile"].declaration.parameters.properties
    assert {"open_buffer_minutes", "close_buffer_minutes"} <= set(properties)


def test_a_week_with_gaps_still_needs_an_explicit_confirmation():
    """Findings are information, not authorization: a staged week with holes
    is staged exactly like a clean one, and confirm stays a separate turn."""
    staged = evaluate_huume_action(
        staged_action=_action(findings=FINDINGS, metrics={
            "filled_positions": 8, "required_positions": 10, "open_positions": 2,
            "gap_count": 2, "operating_hours_known": True,
        }),
        features=FEATURES, role="admin", thread_huume_mode=True,
        this_turn_staged_new=True, schedule_surface=True,
    )
    assert staged.kind == "stage"

    confirmed = evaluate_huume_action(
        staged_action=_action(findings=FINDINGS), features=FEATURES, role="admin",
        thread_huume_mode=True, this_turn_staged_new=False, schedule_surface=True,
    )
    assert confirmed.ok


# ── load + honesty in the week-draft state block (2026-09-07) ────────────────

def _week_review(**overrides):
    review = {
        "kind": "week_draft", "compliance_status": "verified", "assignments": [], "rejected": [], "unfilled": [],
        "employees": [], "advisories": [], "findings": [],
        "jurisdiction": {"state": "CA", "status": "curated", "message": "Scheduling law for CA is on file (hand-curated)."},
    }
    review.update(overrides)
    return review


def test_state_block_names_who_carries_the_week_and_an_unverified_state():
    concentration = ("Dana Reyes carries 6 of 6 proposed positions (24h scheduled this week) — "
                     "spread the load across the roster or confirm this is intended.")
    block = build_state_block({"huume_action": _action(
        metrics={"filled_positions": 6, "required_positions": 14, "open_positions": 8, "gap_count": 0,
                 "operating_hours_known": True,
                 "top_load": [{"employee_id": "e1", "name": "Dana Reyes", "shifts": 6, "hours": 24.0}]},
        review=_week_review(
            compliance_status="unmapped",
            employees=[{"employee_id": "e1", "name": "Dana Reyes", "before": {}, "after": {}, "warnings": [concentration]}],
            jurisdiction={"state": "TX", "status": "unmapped",
                          "message": "Legality was NOT verified for TX — Matcha has no researched scheduling thresholds for it."},
        ),
    )}, schedule_surface=True)

    assert "Load: Dana Reyes 6 shift(s) / 24.0h" in block
    assert "Policy warning: Dana Reyes carries 6 of 6 proposed positions" in block
    assert "Compliance: NOT verified — Legality was NOT verified for TX" in block
    assert "Never describe this week as compliant" in block


def test_state_block_counts_statutory_advisories_on_a_verified_state():
    block = build_state_block({"huume_action": _action(
        review=_week_review(compliance_status="advisory", advisories=[{"message": "a"}, {"message": "b"}]),
    )}, schedule_surface=True)
    assert "Compliance: 2 statutory advisory(ies) attached to this week" in block
    assert "NOT verified" not in block


def test_a_clean_verified_week_adds_no_compliance_line():
    block = build_state_block({"huume_action": _action(review=_week_review())}, schedule_surface=True)
    assert "Compliance:" not in block and "Load:" not in block
