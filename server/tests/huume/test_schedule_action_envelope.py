"""Pure confirm-first tests for schedule Huume mutations."""

from uuid import uuid4

from app.matcha.services.huume.actions import evaluate_huume_action


FEATURES = {"huume": True, "employee_schedule": True, "matcha_work": True}


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


def test_schedule_surface_still_requires_matcha_work_flag():
    # matcha_work is a hard prerequisite for every Huume action, schedule
    # surface included — the /matcha-work router this call arrives through is
    # gated on the flag at the mount, so a bypass here is unreachable and was
    # removed (see actions.py's evaluate_huume_action comment).
    verdict = evaluate_huume_action(
        staged_action=_note_action(),
        features={**FEATURES, "matcha_work": False},
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
        schedule_surface=True,
    )
    assert verdict.kind == "refuse"
    assert "Matcha Work" in verdict.message


def test_schedule_surface_does_not_require_global_huume_flag():
    verdict = evaluate_huume_action(
        staged_action=_note_action(),
        features={**FEATURES, "huume": False},
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
        schedule_surface=True,
    )
    assert verdict.kind == "proceed"


def test_schedule_surface_cannot_use_global_huume_actions():
    verdict = evaluate_huume_action(
        staged_action={
            "type": "send_offer", "status": "proposed", "offer_id": str(uuid4()),
        },
        features={**FEATURES, "offer_letters": True},
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
        schedule_surface=True,
    )
    assert verdict.kind == "refuse"
    assert "outside this schedule workspace" in verdict.message


def test_employee_role_passes_the_capability_gate_on_schedule_surface():
    # This only proves evaluate_huume_action's role-based capability check
    # (schedule_manager_authorized in actions.py) admits any employee role.
    # It is NOT a location-authorization test — that check runs earlier, in
    # schedule_assistant_session.resolve_schedule_assistant_scope, and is
    # covered separately (see tests/employee_schedule/test_schedule_assistant_session.py).
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
        features={**FEATURES, "matcha_work": False},
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
    )
    assert verdict.kind == "refuse"
    assert "Matcha Work" in verdict.message


def test_non_schedule_surface_keeps_global_huume_gate():
    verdict = evaluate_huume_action(
        staged_action=_note_action(),
        features={**FEATURES, "huume": False},
        role="client",
        thread_huume_mode=True,
        this_turn_staged_new=False,
    )
    assert verdict.kind == "refuse"
    assert "Huume" in verdict.message


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
