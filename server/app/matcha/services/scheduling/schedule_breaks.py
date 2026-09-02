"""Deterministic break-plan evaluation for scheduled shifts.

The existing schedule compliance module returns write-time violations.  This
module is deliberately separate: it produces structured, employee-facing
guidance that can be cached on an assignment and rendered by the API/email
surfaces.  It contains no database or FastAPI dependencies.

Schedule timestamps in this project are UTC wall-clock values.  A stored
``09:00+00:00`` means 9 AM at the work location, not 9 AM UTC to be converted
to another local hour.  ``reinterpret_schedule_wall_time`` preserves the
clock fields and attaches the location zone for deadline labels.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo


BreakKind = Literal["meal", "rest"]
BreakPlanStatus = Literal["complete", "unmapped", "error"]
TriggerOperator = Literal["gt", "gte"]


@dataclass(frozen=True)
class BreakRule:
    rule_set_id: UUID
    kind: BreakKind
    ordinal: int
    trigger_after_minutes: int
    duration_minutes: int
    paid: bool
    deadline_offset_minutes: int | None = None
    earliest_offset_minutes: int | None = None
    recommended_offset_minutes: int | None = None
    latest_offset_minutes: int | None = None
    waiver_allowed: bool = False
    waiver_max_shift_minutes: int | None = None
    trigger_operator: TriggerOperator = "gt"
    minimum_age: int | None = None
    maximum_age: int | None = None
    citation: str = ""


@dataclass(frozen=True)
class MealWaiverAttestation:
    id: UUID
    on_file: bool
    effective_from: date
    confirmed_by: UUID
    confirmed_at: datetime


@dataclass(frozen=True)
class BreakRequirement:
    kind: BreakKind
    ordinal: int
    duration_minutes: int
    paid: bool
    earliest_local: datetime | None
    recommended_local: datetime | None
    deadline_local: datetime | None
    waived: bool
    waiver_attestation_id: UUID | None
    citation: str
    rule_set_id: UUID


@dataclass(frozen=True)
class BreakPlan:
    status: BreakPlanStatus
    requirements: tuple[BreakRequirement, ...]
    advisories: tuple[dict[str, Any], ...]
    rule_set_ids: tuple[UUID, ...]
    rule_set_hash: str


def reinterpret_schedule_wall_time(value: datetime, timezone: ZoneInfo) -> datetime:
    """Attach ``timezone`` without changing the scheduled clock fields."""

    naive = value.replace(tzinfo=None)
    return naive.replace(tzinfo=timezone)


def _shift_minutes(starts_at: datetime, ends_at: datetime) -> int:
    start = starts_at.replace(tzinfo=None)
    end = ends_at.replace(tzinfo=None)
    return max(0, int((end - start).total_seconds() // 60))


def _rule_applies(rule: BreakRule, shift_minutes: int) -> bool:
    if rule.trigger_operator == "gte":
        return shift_minutes >= rule.trigger_after_minutes
    return shift_minutes > rule.trigger_after_minutes


def _stable_rule_value(rule: BreakRule) -> dict[str, Any]:
    value = asdict(rule)
    value["rule_set_id"] = str(rule.rule_set_id)
    return value


def _plan_hash(
    rules: Sequence[BreakRule],
    waiver: MealWaiverAttestation | None,
) -> str:
    payload = {
        "rules": [_stable_rule_value(rule) for rule in rules],
        "waiver": {
            "id": str(waiver.id),
            "on_file": waiver.on_file,
            "effective_from": waiver.effective_from.isoformat(),
        } if waiver else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _format_local_time(value: datetime) -> str:
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    if value.minute:
        return f"{hour}:{value.minute:02d} {suffix}"
    return f"{hour} {suffix}"


def _paid_label(paid: bool) -> str:
    return "paid" if paid else "unpaid"


def _article_count(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def evaluate_break_plan(
    *,
    starts_at: datetime,
    ends_at: datetime,
    timezone: ZoneInfo,
    rules: Sequence[BreakRule],
    waiver: MealWaiverAttestation | None = None,
    employee_age: int | None = None,
) -> BreakPlan:
    """Evaluate every applicable meal/rest rule for one scheduled shift.

    The evaluator intentionally does not inspect ``break_minutes``.  That
    field describes the aggregate planned break on a shift and cannot tell us
    whether a particular employee actually received each meal/rest period.
    Existing write-time violations continue to validate that field separately.
    """

    shift_minutes = _shift_minutes(starts_at, ends_at)
    starts_local = reinterpret_schedule_wall_time(starts_at, timezone)
    requirements: list[BreakRequirement] = []
    advisories: list[dict[str, Any]] = []

    ordered_rules = sorted(rules, key=lambda rule: (rule.trigger_after_minutes, rule.kind, rule.ordinal))
    for rule in ordered_rules:
        if rule.minimum_age is not None and (employee_age is None or employee_age < rule.minimum_age):
            continue
        if rule.maximum_age is not None and (employee_age is None or employee_age > rule.maximum_age):
            continue
        if not _rule_applies(rule, shift_minutes):
            continue

        waived = False
        if rule.kind == "meal" and waiver and waiver.on_file:
            max_minutes = rule.waiver_max_shift_minutes
            if rule.waiver_allowed and (max_minutes is None or shift_minutes <= max_minutes):
                if waiver.effective_from <= starts_local.date():
                    waived = True
            elif rule.waiver_allowed:
                advisories.append({
                    "check": "meal_waiver",
                    "code": "meal_waiver_inapplicable",
                    "severity": "advisory",
                    "message": "Meal waiver is on file but does not apply to this shift length.",
                    "statute": rule.citation or None,
                })
            else:
                advisories.append({
                    "check": "meal_waiver",
                    "code": "meal_waiver_inapplicable",
                    "severity": "advisory",
                    "message": "Meal waiver is on file, but the applicable rule does not permit a waiver.",
                    "statute": rule.citation or None,
                })

        def _offset(value: int | None) -> datetime | None:
            return starts_local + timedelta(minutes=value) if value is not None else None

        requirements.append(BreakRequirement(
            kind=rule.kind,
            ordinal=rule.ordinal,
            duration_minutes=rule.duration_minutes,
            paid=rule.paid,
            earliest_local=_offset(rule.earliest_offset_minutes),
            recommended_local=_offset(rule.recommended_offset_minutes),
            deadline_local=_offset(rule.deadline_offset_minutes),
            waived=waived,
            waiver_attestation_id=waiver.id if waived and waiver else None,
            citation=rule.citation,
            rule_set_id=rule.rule_set_id,
        ))

    return BreakPlan(
        status="complete" if rules else "unmapped",
        requirements=tuple(requirements),
        advisories=tuple(advisories),
        rule_set_ids=tuple(dict.fromkeys(rule.rule_set_id for rule in rules)),
        rule_set_hash=_plan_hash(rules, waiver),
    )


def render_break_requirement(requirement: BreakRequirement) -> str:
    """Render one requirement with deterministic, employee-safe wording."""

    if requirement.waived:
        return "Meal break waiver on file; meal requirement waived for this shift"

    duration = f"{requirement.duration_minutes}-minute"
    paid = _paid_label(requirement.paid)
    if requirement.kind == "meal":
        text = f"Mandatory {duration} {paid} meal break"
    else:
        text = f"{duration} {paid} rest break"

    if requirement.deadline_local is not None:
        return f"{text} by {_format_local_time(requirement.deadline_local)}"
    if requirement.recommended_local is not None:
        return f"{text} around {_format_local_time(requirement.recommended_local)}"
    return text


def render_break_plan(plan: BreakPlan) -> str | None:
    """Render a plan summary, or ``None`` when no employee action is needed."""

    if plan.status == "error":
        return "Break requirements could not be fully evaluated; verify manually."
    if plan.status == "unmapped":
        return "Break requirements could not be mapped for this location; verify manually."
    active = [requirement for requirement in plan.requirements if not requirement.waived]
    waived_meals = [
        requirement for requirement in plan.requirements
        if requirement.waived and requirement.kind == "meal"
    ]
    if not active:
        return "Meal break waiver on file; no mandatory meal break applies to this shift." if waived_meals else None

    rendered: list[str] = []
    meal_requirements = [requirement for requirement in active if requirement.kind == "meal"]
    rest_requirements = [requirement for requirement in active if requirement.kind == "rest"]
    rendered.extend(render_break_requirement(requirement) for requirement in meal_requirements)
    if rest_requirements:
        grouped: dict[tuple[int, bool, str | None], int] = {}
        for requirement in rest_requirements:
            deadline = _format_local_time(requirement.deadline_local) if requirement.deadline_local else None
            key = (requirement.duration_minutes, requirement.paid, deadline)
            grouped[key] = grouped.get(key, 0) + 1
        for (duration, paid, deadline), count in grouped.items():
            text = (
                f"{count} {duration}-minute "
                f"{_paid_label(paid)} rest {_article_count(count, 'break', 'breaks')}"
            )
            if deadline:
                text += f" by {deadline}"
            rendered.append(text)
    return " + ".join(rendered)


def guidance_payload(plan: BreakPlan, *, timezone: str, evaluated_at: datetime) -> dict[str, Any]:
    """Convert the immutable plan into the JSON shape stored on assignments."""

    return {
        "schema_version": 1,
        "status": plan.status,
        "evaluated_at": evaluated_at.isoformat(),
        "timezone": timezone,
        "rule_set_ids": [str(value) for value in plan.rule_set_ids],
        "rule_set_hash": plan.rule_set_hash,
        "summary": render_break_plan(plan),
        "requirements": [
            {
                "kind": requirement.kind,
                "ordinal": requirement.ordinal,
                "duration_minutes": requirement.duration_minutes,
                "paid": requirement.paid,
                "earliest_local": requirement.earliest_local.isoformat() if requirement.earliest_local else None,
                "recommended_local": requirement.recommended_local.isoformat() if requirement.recommended_local else None,
                "deadline_local": requirement.deadline_local.isoformat() if requirement.deadline_local else None,
                "waived": requirement.waived,
                "waiver_attestation_id": str(requirement.waiver_attestation_id) if requirement.waiver_attestation_id else None,
                "citation": requirement.citation or None,
                "rule_set_id": str(requirement.rule_set_id),
            }
            for requirement in plan.requirements
        ],
        "advisories": list(plan.advisories),
    }


def minimum_meal_break_minutes(plan: BreakPlan) -> int:
    """Aggregate the active meal periods represented by ``break_minutes``."""

    return sum(
        requirement.duration_minutes
        for requirement in plan.requirements
        if requirement.kind == "meal" and not requirement.waived
    )
