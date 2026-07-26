"""Canonical onboarding state machine and event payload contract."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class OnboardingState(str, Enum):
    PREHIRE = "prehire"
    INVITED = "invited"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    READY_FOR_DAY1 = "ready_for_day1"
    ACTIVE = "active"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    OFFBOARDING_IN_PROGRESS = "offboarding_in_progress"
    OFFBOARDED = "offboarded"


class OnboardingTransitionError(ValueError):
    """Raised when an invalid state transition is requested."""


class OnboardingEventSchemaError(ValueError):
    """Raised when an onboarding event payload violates the schema contract."""


BLOCK_REASONS: tuple[str, ...] = (
    "dependency",
    "missing_document",
    "integration_error",
    "approval_pending",
    "other",
)

EVENT_SCHEMA_VERSION = "1.0"
EVENT_REQUIRED_FIELDS: tuple[str, ...] = (
    "event_name",
    "case_id",
    "employee_id",
    "occurred_at",
    "state_from",
    "state_to",
)
EVENT_OPTIONAL_FIELDS: tuple[str, ...] = (
    "task_id",
    "actor_id",
    "provider",
    "metadata",
    "source_system",
    "source_event_id",
    "block_reason",
)

_ALLOWED_TRANSITIONS: dict[OnboardingState, tuple[OnboardingState, ...]] = {
    OnboardingState.PREHIRE: (
        OnboardingState.INVITED,
        OnboardingState.CANCELLED,
    ),
    OnboardingState.INVITED: (
        OnboardingState.ACCEPTED,
        OnboardingState.BLOCKED,
        OnboardingState.CANCELLED,
    ),
    OnboardingState.ACCEPTED: (
        OnboardingState.IN_PROGRESS,
        OnboardingState.BLOCKED,
        OnboardingState.CANCELLED,
    ),
    OnboardingState.IN_PROGRESS: (
        OnboardingState.READY_FOR_DAY1,
        OnboardingState.BLOCKED,
        OnboardingState.CANCELLED,
        OnboardingState.OFFBOARDING_IN_PROGRESS,
    ),
    OnboardingState.READY_FOR_DAY1: (
        OnboardingState.ACTIVE,
        OnboardingState.BLOCKED,
        OnboardingState.OFFBOARDING_IN_PROGRESS,
    ),
    OnboardingState.ACTIVE: (
        OnboardingState.OFFBOARDING_IN_PROGRESS,
    ),
    OnboardingState.BLOCKED: (
        OnboardingState.INVITED,
        OnboardingState.ACCEPTED,
        OnboardingState.IN_PROGRESS,
        OnboardingState.READY_FOR_DAY1,
        OnboardingState.ACTIVE,
        OnboardingState.OFFBOARDING_IN_PROGRESS,
        OnboardingState.CANCELLED,
    ),
    OnboardingState.CANCELLED: (),
    OnboardingState.OFFBOARDING_IN_PROGRESS: (
        OnboardingState.OFFBOARDED,
        OnboardingState.ACTIVE,
    ),
    OnboardingState.OFFBOARDED: (),
}


def _coerce_state(value: str | OnboardingState) -> OnboardingState:
    if isinstance(value, OnboardingState):
        return value
    try:
        return OnboardingState(value)
    except ValueError as exc:
        raise OnboardingTransitionError(f"Unknown onboarding state '{value}'") from exc


def all_states() -> list[str]:
    return [state.value for state in OnboardingState]


def state_machine_map() -> dict[str, list[str]]:
    return {
        source.value: [target.value for target in targets]
        for source, targets in _ALLOWED_TRANSITIONS.items()
    }


def can_transition(
    state_from: str | OnboardingState,
    state_to: str | OnboardingState,
) -> bool:
    source = _coerce_state(state_from)
    target = _coerce_state(state_to)
    return target in _ALLOWED_TRANSITIONS[source]


def validate_transition(
    state_from: str | OnboardingState,
    state_to: str | OnboardingState,
    *,
    block_reason: str | None = None,
) -> None:
    source = _coerce_state(state_from)
    target = _coerce_state(state_to)

    allowed_targets = _ALLOWED_TRANSITIONS[source]
    if target not in allowed_targets:
        allowed_str = ", ".join(t.value for t in allowed_targets) or "none"
        raise OnboardingTransitionError(
            f"Invalid onboarding transition '{source.value}' -> '{target.value}'. "
            f"Allowed targets: {allowed_str}."
        )

    if target == OnboardingState.BLOCKED:
        if not block_reason:
            raise OnboardingTransitionError("block_reason is required when transitioning to 'blocked'")
        if block_reason not in BLOCK_REASONS:
            allowed = ", ".join(BLOCK_REASONS)
            raise OnboardingTransitionError(
                f"Invalid block_reason '{block_reason}'. Allowed reasons: {allowed}."
            )
    elif block_reason is not None:
        raise OnboardingTransitionError("block_reason is only valid when transitioning to 'blocked'")


def event_schema_contract() -> dict[str, Any]:
    return {
        "version": EVENT_SCHEMA_VERSION,
        "required_fields": list(EVENT_REQUIRED_FIELDS),
        "optional_fields": list(EVENT_OPTIONAL_FIELDS),
        "block_reasons": list(BLOCK_REASONS),
    }


def validate_event_payload(payload: Mapping[str, Any]) -> None:
    missing = [
        key for key in EVENT_REQUIRED_FIELDS
        if key not in payload or payload[key] in (None, "")
    ]
    if missing:
        raise OnboardingEventSchemaError(
            f"Missing required onboarding event fields: {', '.join(missing)}"
        )

    if payload.get("block_reason") is not None and payload["block_reason"] not in BLOCK_REASONS:
        allowed = ", ".join(BLOCK_REASONS)
        raise OnboardingEventSchemaError(
            f"Invalid block_reason '{payload['block_reason']}'. Allowed reasons: {allowed}."
        )

    validate_transition(
        payload["state_from"],
        payload["state_to"],
        block_reason=payload.get("block_reason"),
    )
