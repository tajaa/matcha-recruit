import pytest

from app.matcha.services.onboarding_state_machine import (
    OnboardingEventSchemaError,
    OnboardingTransitionError,
    all_states,
    can_transition,
    validate_event_payload,
    validate_transition,
)


def test_state_list_contains_core_lifecycle_states():
    states = all_states()
    assert "prehire" in states
    assert "invited" in states
    assert "accepted" in states
    assert "in_progress" in states
    assert "ready_for_day1" in states
    assert "active" in states


def test_can_transition_for_valid_path():
    assert can_transition("prehire", "invited") is True
    assert can_transition("invited", "accepted") is True


def test_validate_transition_rejects_invalid_path():
    with pytest.raises(OnboardingTransitionError, match="Invalid onboarding transition"):
        validate_transition("prehire", "active")


def test_transition_to_blocked_requires_reason():
    with pytest.raises(OnboardingTransitionError, match="block_reason is required"):
        validate_transition("invited", "blocked")

    validate_transition("invited", "blocked", block_reason="dependency")


def test_transition_rejects_unknown_block_reason():
    with pytest.raises(OnboardingTransitionError, match="Invalid block_reason"):
        validate_transition("invited", "blocked", block_reason="bad_reason")


def test_validate_event_payload_requires_core_fields():
    payload = {
        "event_name": "onboarding.case.transitioned",
        "case_id": "case-1",
        "employee_id": "employee-1",
        "occurred_at": "2026-02-18T17:00:00Z",
        "state_from": "prehire",
        "state_to": "invited",
    }
    validate_event_payload(payload)

    payload_missing = {
        "event_name": "onboarding.case.transitioned",
        "case_id": "case-1",
    }
    with pytest.raises(OnboardingEventSchemaError, match="Missing required onboarding event fields"):
        validate_event_payload(payload_missing)


def test_validate_event_payload_checks_state_transition_and_block_reason():
    with pytest.raises(OnboardingTransitionError, match="Invalid onboarding transition"):
        validate_event_payload(
            {
                "event_name": "onboarding.case.transitioned",
                "case_id": "case-1",
                "employee_id": "employee-1",
                "occurred_at": "2026-02-18T17:00:00Z",
                "state_from": "invited",
                "state_to": "active",
            }
        )

    with pytest.raises(OnboardingEventSchemaError, match="Invalid block_reason"):
        validate_event_payload(
            {
                "event_name": "onboarding.case.transitioned",
                "case_id": "case-1",
                "employee_id": "employee-1",
                "occurred_at": "2026-02-18T17:00:00Z",
                "state_from": "invited",
                "state_to": "blocked",
                "block_reason": "not_valid",
            }
        )
