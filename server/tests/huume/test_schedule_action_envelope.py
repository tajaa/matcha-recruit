"""Pure confirm-first tests for schedule Huume mutations."""

from uuid import uuid4

from app.matcha.services.huume.actions import evaluate_huume_action


FEATURES = {"huume": True, "employee_schedule": True, "matcha_work": False}


def _note_action(**overrides):
    action = {
        "type": "schedule_note",
        "status": "proposed",
        "confirm_id": "confirm-1",
        "location_id": str(uuid4()),
        "shift_id": str(uuid4()),
        "employee_id": str(uuid4()),
        "note": "Complete harassment training by end of day",
    }
    action.update(overrides)
    return action


def test_schedule_surface_does_not_require_matcha_work_flag():
    verdict = evaluate_huume_action(
        staged_action=_note_action(),
        features=FEATURES,
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
        schedule_surface=True,
    )
    assert verdict.kind == "proceed"


def test_location_manager_can_confirm_scoped_schedule_action():
    verdict = evaluate_huume_action(
        staged_action=_note_action(),
        features=FEATURES,
        role="employee",
        thread_huume_mode=True,
        this_turn_staged_new=False,
        schedule_surface=True,
    )
    assert verdict.kind == "proceed"


def test_schedule_action_rejects_invalid_writer_inputs_before_execution():
    malformed = evaluate_huume_action(
        staged_action=_note_action(employee_id="not-a-uuid"),
        features=FEATURES,
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
        schedule_surface=True,
    )
    assert malformed.kind == "refuse"

    missing_waiver_state = evaluate_huume_action(
        staged_action={
            "type": "meal_break_waiver", "status": "proposed", "confirm_id": "confirm-1",
            "location_id": str(uuid4()), "employee_id": str(uuid4()),
            "effective_from": "2026-08-21",
        },
        features=FEATURES,
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
        schedule_surface=True,
    )
    assert missing_waiver_state.kind == "refuse"


def test_non_schedule_surface_keeps_matcha_work_gate():
    verdict = evaluate_huume_action(
        staged_action=_note_action(),
        features=FEATURES,
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
    )
    assert verdict.kind == "refuse"
    assert "Matcha Work" in verdict.message


def test_keep_case_requires_written_acknowledgement():
    base = {
        "type": "eligibility_case_decision",
        "status": "proposed",
        "confirm_id": "confirm-1",
        "case_id": str(uuid4()),
        "location_id": str(uuid4()),
        "decision": "keep",
    }
    missing = evaluate_huume_action(
        staged_action=base,
        features={**FEATURES, "matcha_work": True},
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
        schedule_surface=True,
    )
    assert missing.kind == "refuse"
    assert "acknowledgement" in missing.message.lower()

    valid = evaluate_huume_action(
        staged_action={
            **base,
            "acknowledgement_confirmed": True,
            "acknowledgement_note": "I understand the cited requirement and accept the compliance risk.",
        },
        features={**FEATURES, "matcha_work": True},
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
        schedule_surface=True,
    )
    assert valid.kind == "proceed"
