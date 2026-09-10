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
from datetime import date, datetime, time, timedelta
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
    effective_from: date | None = None
    effective_to: date | None = None
    authority_url: str | None = None
    source_type: str | None = None
    minimum_employees: int | None = None
    maximum_employees: int | None = None
    shift_start_window_from: time | None = None
    shift_start_window_before: time | None = None
    shift_spans_window_start: time | None = None
    shift_spans_window_end: time | None = None
    shift_starts_before: time | None = None
    shift_ends_after: time | None = None
    window_start: time | None = None
    window_end: time | None = None
    recommend_midpoint: bool = False


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
    effective_from: date | None = None
    effective_to: date | None = None
    authority_url: str | None = None
    source_type: str | None = None
    # True when `earliest_local` came from a WALL-CLOCK window (New York's
    # 11 a.m. noon day period) rather than an offset from the shift's own start
    # (Washington's "no less than two hours"). An offset already states how far
    # into the shift the break may open; a clock time says nothing about that —
    # 11 a.m. is 4.5 hours into a 06:30 shift and 30 minutes into a 10:30 one —
    # so only the clock-anchored kind yields to the stagger's placement floor.
    earliest_clock_anchored: bool = False


@dataclass(frozen=True)
class BreakPlan:
    status: BreakPlanStatus
    requirements: tuple[BreakRequirement, ...]
    advisories: tuple[dict[str, Any], ...]
    rule_set_ids: tuple[UUID, ...]
    rule_set_hash: str
    employer_employee_count: int | None = None


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


def _clock_in_window(value: time, start: time, end: time) -> bool:
    """Half-open clock window, including windows that cross midnight."""

    if start < end:
        return start <= value < end
    return value >= start or value < end


def _rule_context_applies(
    rule: BreakRule,
    *,
    starts_local: datetime,
    ends_local: datetime,
    employer_employee_count: int | None,
) -> tuple[bool, bool]:
    """Return ``(applies, context_missing)`` for non-duration conditions."""

    if rule.minimum_employees is not None or rule.maximum_employees is not None:
        if employer_employee_count is None:
            return False, True
        if rule.minimum_employees is not None and employer_employee_count < rule.minimum_employees:
            return False, False
        if rule.maximum_employees is not None and employer_employee_count > rule.maximum_employees:
            return False, False

    start_clock = starts_local.time().replace(tzinfo=None)
    if rule.shift_start_window_from is not None and rule.shift_start_window_before is not None:
        if not _clock_in_window(
            start_clock, rule.shift_start_window_from, rule.shift_start_window_before,
        ):
            return False, False
    if rule.shift_spans_window_start is not None and rule.shift_spans_window_end is not None:
        base_start = datetime.combine(
            starts_local.date(), rule.shift_spans_window_start, starts_local.tzinfo,
        )
        base_end = datetime.combine(
            starts_local.date(), rule.shift_spans_window_end, starts_local.tzinfo,
        )
        if base_end <= base_start:
            base_end += timedelta(days=1)
        windows = (
            (base_start + timedelta(days=delta), base_end + timedelta(days=delta))
            for delta in (-1, 0, 1)
        )
        if not any(
            starts_local <= window_start and ends_local >= window_end
            for window_start, window_end in windows
        ):
            return False, False
    if rule.shift_starts_before is not None:
        starts_before = datetime.combine(
            starts_local.date(), rule.shift_starts_before, starts_local.tzinfo,
        )
        if not starts_local < starts_before:
            return False, False
    if rule.shift_ends_after is not None:
        ends_after = datetime.combine(
            starts_local.date(), rule.shift_ends_after, starts_local.tzinfo,
        )
        if not ends_local > ends_after:
            return False, False
    return True, False


def _stable_rule_value(rule: BreakRule) -> dict[str, Any]:
    value = asdict(rule)
    value["rule_set_id"] = str(rule.rule_set_id)
    for key, item in tuple(value.items()):
        if isinstance(item, (date, time)):
            value[key] = item.isoformat()
    return value


def _plan_hash(
    rules: Sequence[BreakRule],
    waiver: MealWaiverAttestation | None,
    employer_employee_count: int | None,
) -> str:
    payload = {
        "rules": [_stable_rule_value(rule) for rule in rules],
        "waiver": {
            "id": str(waiver.id),
            "on_file": waiver.on_file,
            "effective_from": waiver.effective_from.isoformat(),
        } if waiver else None,
        "employer_employee_count": employer_employee_count,
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
    employer_employee_count: int | None = None,
) -> BreakPlan:
    """Evaluate every applicable meal/rest rule for one scheduled shift.

    The evaluator intentionally does not inspect ``break_minutes``.  That
    field describes the aggregate planned break on a shift and cannot tell us
    whether a particular employee actually received each meal/rest period.
    Existing write-time violations continue to validate that field separately.
    """

    shift_minutes = _shift_minutes(starts_at, ends_at)
    starts_local = reinterpret_schedule_wall_time(starts_at, timezone)
    ends_local = reinterpret_schedule_wall_time(ends_at, timezone)
    ordered: list[tuple[datetime, str, int, BreakRequirement]] = []
    advisories: list[dict[str, Any]] = []

    ordered_rules = sorted(rules, key=lambda rule: (rule.trigger_after_minutes, rule.kind, rule.ordinal))
    for rule in ordered_rules:
        if rule.minimum_age is not None and (employee_age is None or employee_age < rule.minimum_age):
            continue
        if rule.maximum_age is not None and (employee_age is None or employee_age > rule.maximum_age):
            continue
        context_applies, context_missing = _rule_context_applies(
            rule,
            starts_local=starts_local,
            ends_local=ends_local,
            employer_employee_count=employer_employee_count,
        )
        if context_missing:
            advisories.append({
                "check": "break_rules",
                "code": "employer_context_unverified",
                "severity": "advisory",
                "message": "Employer headcount is unavailable; size-specific break rules require manual review.",
                "statute": rule.citation or None,
            })
            continue
        if not context_applies:
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

        def _distance_from_shift(window_start: datetime, window_end: datetime) -> timedelta:
            if window_end <= starts_local:
                return starts_local - window_end
            if window_start >= ends_local:
                return window_start - ends_local
            return timedelta(0)

        def _clock(value: time | None) -> datetime | None:
            if value is None:
                return None
            base = datetime.combine(starts_local.date(), value, starts_local.tzinfo)
            candidates = [base + timedelta(days=delta) for delta in (-1, 0, 1)]
            return min(
                candidates,
                key=lambda candidate: (
                    _distance_from_shift(candidate, candidate),
                    abs((candidate - starts_local).total_seconds()),
                ),
            )

        def _clock_window(start: time, end: time) -> tuple[datetime, datetime]:
            base_start = datetime.combine(starts_local.date(), start, starts_local.tzinfo)
            base_end = datetime.combine(starts_local.date(), end, starts_local.tzinfo)
            if base_end <= base_start:
                base_end += timedelta(days=1)
            candidates = [
                (base_start + timedelta(days=delta), base_end + timedelta(days=delta))
                for delta in (-1, 0, 1)
            ]
            return min(
                candidates,
                key=lambda window: (
                    _distance_from_shift(*window),
                    abs((window[0] - starts_local).total_seconds()),
                ),
            )

        if rule.window_start is not None and rule.window_end is not None:
            earliest, deadline = _clock_window(rule.window_start, rule.window_end)
        else:
            earliest = _clock(rule.window_start) or _offset(rule.earliest_offset_minutes)
            deadline = _clock(rule.window_end) or _offset(rule.deadline_offset_minutes)
        recommended = _offset(rule.recommended_offset_minutes)
        if rule.recommend_midpoint:
            recommended = starts_local + timedelta(
                minutes=max(0, (shift_minutes - rule.duration_minutes) // 2),
            )

        # Order the plan by when each period may actually be taken, not by the
        # shift length that triggers it: New York's extra evening period
        # (§ 162(3)) is owed from minute one of a qualifying shift, so a
        # trigger-ordered list renders it before the noon day meal it follows.
        # Every requirement gets an anchor, so a rule with no times at all
        # keeps its trigger-ordered place.
        anchor = earliest or recommended or deadline or _offset(rule.trigger_after_minutes)
        ordered.append((anchor, rule.kind, rule.ordinal, BreakRequirement(
            kind=rule.kind,
            ordinal=rule.ordinal,
            duration_minutes=rule.duration_minutes,
            paid=rule.paid,
            earliest_local=earliest,
            recommended_local=recommended,
            deadline_local=deadline,
            waived=waived,
            waiver_attestation_id=waiver.id if waived and waiver else None,
            citation=rule.citation,
            rule_set_id=rule.rule_set_id,
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
            authority_url=rule.authority_url,
            source_type=rule.source_type,
            earliest_clock_anchored=rule.window_start is not None,
        )))

    ordered.sort(key=lambda item: item[:3])
    requirements = [item[3] for item in ordered]

    return BreakPlan(
        status="error" if any(a.get("code") == "employer_context_unverified" for a in advisories)
        else "complete" if rules else "unmapped",
        requirements=tuple(requirements),
        advisories=tuple(advisories),
        rule_set_ids=tuple(dict.fromkeys(rule.rule_set_id for rule in rules)),
        rule_set_hash=_plan_hash(rules, waiver, employer_employee_count),
        employer_employee_count=employer_employee_count,
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
        "schema_version": 2,
        "status": plan.status,
        "evaluated_at": evaluated_at.isoformat(),
        "timezone": timezone,
        "rule_set_ids": [str(value) for value in plan.rule_set_ids],
        "rule_set_hash": plan.rule_set_hash,
        "context": {"employer_employee_count": plan.employer_employee_count},
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
                "effective_from": requirement.effective_from.isoformat() if requirement.effective_from else None,
                "effective_to": requirement.effective_to.isoformat() if requirement.effective_to else None,
                "authority_url": requirement.authority_url,
                "source_type": requirement.source_type,
                "earliest_clock_anchored": requirement.earliest_clock_anchored,
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
