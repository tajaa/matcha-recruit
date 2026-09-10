"""Database resolution and legacy adaptation for structured break rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, time
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import schedule_compliance, shift_compliance
from .schedule_breaks import BreakRule
from .schedule_location_readiness import get_schedule_location_readiness

MAX_SHIFT_BREAK_MINUTES = 1440
_GUIDANCE_RULE_LOCK_KEY = "schedule-break-rules:guidance:v1"
_EMPLOYER_EMPLOYEE_COUNT_UNSET = object()


async def lock_schedule_break_rule_guidance(conn, *, exclusive: bool) -> None:
    """Serialize persisted guidance with rule review transitions.

    Resolvers take the shared transaction lock while rule approvals/rejections
    take the exclusive form.  This prevents an old rule snapshot from being
    written after a newly committed review decision.
    """
    query = (
        "SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))"
        if exclusive
        else "SELECT pg_advisory_xact_lock_shared(hashtextextended($1::text, 0))"
    )
    await conn.fetchval(query, _GUIDANCE_RULE_LOCK_KEY)


@dataclass(frozen=True)
class ResolvedBreakRules:
    rules: tuple[BreakRule, ...]
    rule_set_ids: tuple[UUID, ...]
    timezone: ZoneInfo | None
    industry_code: str | None
    source: str
    advisories: tuple[dict[str, Any], ...]
    employer_employee_count: int | None = None
    expected_rules: tuple[BreakRule, ...] = ()
    applicability_context_hash: str | None = None
    applicability_decision: str | None = None


def _uuid_for_legacy(state: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"matcha:schedule-break-rules:legacy:{state}")


def _as_int(value: Any, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("numeric rule values must be whole numbers")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    raise ValueError("numeric rule values must be whole numbers")


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError("boolean rule values must be true or false")
    return value


def _age_bounds(raw: dict[str, Any]) -> tuple[int | None, int | None]:
    def supplied_int(*keys: str) -> int | None:
        found = next((key for key in keys if key in raw), None)
        if found is None or raw[found] is None:
            return None
        value = raw[found]
        if isinstance(value, bool):
            raise ValueError(f"{keys[0]} must be a whole number")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
        raise ValueError(f"{keys[0]} must be a whole number")

    minimum = supplied_int("minimum_age", "min_age")
    maximum = supplied_int("maximum_age", "max_age")
    if minimum is not None and not 0 <= minimum <= 125:
        raise ValueError("minimum_age must be between 0 and 125")
    if maximum is not None and not 0 <= maximum <= 125:
        raise ValueError("maximum_age must be between 0 and 125")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("minimum_age cannot exceed maximum_age")
    return minimum, maximum


def _as_time(value: Any, *, field: str) -> time | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an HH:MM string")
    try:
        parsed = time.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be an HH:MM string") from exc
    if parsed.second or parsed.microsecond or parsed.tzinfo is not None:
        raise ValueError(f"{field} must be an HH:MM string")
    return parsed


def _rules_from_payload(
    rule_set_id: UUID,
    payload: Any,
    citation: str,
    *,
    effective_from: date | None = None,
    effective_to: date | None = None,
    authority_url: str | None = None,
    source_type: str | None = None,
) -> list[BreakRule]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("break rule payload must be an object")

    parsed: list[BreakRule] = []
    for kind, key in (("meal", "meal_periods"), ("rest", "rest_periods")):
        periods = payload.get(key) or []
        if not isinstance(periods, list):
            raise ValueError(f"{key} must be a list")
        for raw in periods:
            if not isinstance(raw, dict):
                raise ValueError(f"{key} entries must be objects")
            minimum_age, maximum_age = _age_bounds(raw)
            minimum_employees = _as_int(raw.get("minimum_employees"))
            maximum_employees = _as_int(raw.get("maximum_employees"))
            if minimum_employees is not None and minimum_employees < 0:
                raise ValueError("minimum_employees cannot be negative")
            if maximum_employees is not None and maximum_employees < 0:
                raise ValueError("maximum_employees cannot be negative")
            if (
                minimum_employees is not None
                and maximum_employees is not None
                and minimum_employees > maximum_employees
            ):
                raise ValueError("minimum_employees cannot exceed maximum_employees")
            clock_fields = {
                key: _as_time(raw.get(key), field=key)
                for key in (
                    "shift_start_window_from", "shift_start_window_before",
                    "shift_spans_window_start", "shift_spans_window_end",
                    "shift_starts_before", "shift_ends_after", "window_start", "window_end",
                )
            }
            for first, second in (
                ("shift_start_window_from", "shift_start_window_before"),
                ("shift_spans_window_start", "shift_spans_window_end"),
                ("window_start", "window_end"),
            ):
                if (clock_fields[first] is None) != (clock_fields[second] is None):
                    raise ValueError(f"{first} and {second} must be supplied together")
            duration = _as_int(raw.get("duration_minutes"))
            trigger = _as_int(raw.get("trigger_after_minutes"))
            ordinal = _as_int(raw.get("ordinal"), default=1)
            if ordinal is None or ordinal < 1:
                raise ValueError(f"invalid {kind} break ordinal")
            trigger_operator = raw.get("trigger_operator", "gt")
            if trigger_operator not in ("gt", "gte"):
                raise ValueError("trigger_operator must be 'gt' or 'gte'")
            paid = _as_bool(raw.get("paid"), default=kind == "rest")
            waiver = raw.get("waiver") or {}
            if not isinstance(waiver, dict):
                raise ValueError("waiver must be an object")
            waiver_allowed = _as_bool(waiver.get("allowed"), default=False)
            waiver_max = _as_int(waiver.get("max_shift_minutes"))
            if waiver_max is not None and waiver_max < 0:
                raise ValueError("waiver max_shift_minutes cannot be negative")
            count_bands = raw.get("count_bands") if kind == "rest" else None
            if duration is None or not 0 < duration <= MAX_SHIFT_BREAK_MINUTES:
                raise ValueError(f"invalid {kind} break duration")
            if not count_bands and (trigger is None or trigger < 0):
                raise ValueError(f"invalid {kind} break trigger")
            if count_bands:
                if not isinstance(count_bands, list):
                    raise ValueError("count_bands must be a list")
                # A band states the *total* number of rest periods required
                # once its threshold is reached.  Materialize each ordinal at
                # the first threshold at which it becomes required, so a
                # 6-hour shift with 1 break does not also receive the 4-hour
                # break rule a second time.
                bands: list[tuple[int, int]] = []
                for band in count_bands:
                    if not isinstance(band, dict):
                        raise ValueError("count_bands entries must be objects")
                    band_trigger = _as_int(band.get("min_minutes"), default=trigger)
                    count = _as_int(band.get("count"), default=0) or 0
                    if (
                        band_trigger is None or band_trigger < 0
                        or count < 0 or count > MAX_SHIFT_BREAK_MINUTES
                    ):
                        raise ValueError("invalid count_bands threshold/count")
                    bands.append((band_trigger, count))
                previous_count = 0
                for band_trigger, count in sorted(bands):
                    if count < previous_count:
                        raise ValueError("count_bands counts must not decrease")
                    for ordinal_value in range(previous_count + 1, count + 1):
                        parsed.append(BreakRule(
                            rule_set_id=rule_set_id,
                            kind=kind,
                            ordinal=ordinal_value,
                            trigger_after_minutes=band_trigger,
                            duration_minutes=duration,
                            paid=paid,
                            deadline_offset_minutes=_as_int(raw.get("deadline_offset_minutes")),
                            earliest_offset_minutes=_as_int(raw.get("earliest_offset_minutes")),
                            recommended_offset_minutes=_as_int(raw.get("recommended_offset_minutes")),
                            latest_offset_minutes=_as_int(raw.get("latest_offset_minutes")),
                            waiver_allowed=waiver_allowed,
                            waiver_max_shift_minutes=waiver_max,
                            trigger_operator=trigger_operator,
                            minimum_age=minimum_age,
                            maximum_age=maximum_age,
                            citation=str(raw.get("citation") or citation),
                            effective_from=effective_from,
                            effective_to=effective_to,
                            authority_url=authority_url,
                            source_type=source_type,
                            minimum_employees=minimum_employees,
                            maximum_employees=maximum_employees,
                            **clock_fields,
                            recommend_midpoint=_as_bool(raw.get("recommend_midpoint"), default=False),
                        ))
                    previous_count = count
                continue
            parsed.append(BreakRule(
                rule_set_id=rule_set_id,
                kind=kind,
                ordinal=ordinal or 1,
                trigger_after_minutes=trigger or 0,
                duration_minutes=duration,
                paid=paid,
                deadline_offset_minutes=_as_int(raw.get("deadline_offset_minutes")),
                earliest_offset_minutes=_as_int(raw.get("earliest_offset_minutes")),
                recommended_offset_minutes=_as_int(raw.get("recommended_offset_minutes")),
                latest_offset_minutes=_as_int(raw.get("latest_offset_minutes")),
                waiver_allowed=waiver_allowed,
                waiver_max_shift_minutes=waiver_max,
                trigger_operator=trigger_operator,
                minimum_age=minimum_age,
                maximum_age=maximum_age,
                citation=str(raw.get("citation") or citation),
                effective_from=effective_from,
                effective_to=effective_to,
                authority_url=authority_url,
                source_type=source_type,
                minimum_employees=minimum_employees,
                maximum_employees=maximum_employees,
                **clock_fields,
                recommend_midpoint=_as_bool(raw.get("recommend_midpoint"), default=False),
            ))
    # The public shift contract and editor both cap the aggregate planned
    # break at one day.  Check every possible employee age so overlapping
    # scoped rules cannot synthesize an unwritable value after approval.
    for employee_age in (None, *range(126)):
        meal_total = sum(
            rule.duration_minutes
            for rule in parsed
            if rule.kind == "meal"
            and (rule.minimum_age is None or employee_age is not None and employee_age >= rule.minimum_age)
            and (rule.maximum_age is None or employee_age is not None and employee_age <= rule.maximum_age)
        )
        if meal_total > MAX_SHIFT_BREAK_MINUTES:
            raise ValueError("aggregate meal break duration exceeds 1440 minutes")
    return parsed


def validate_break_rule_payload(payload: Any, citation: str = "") -> None:
    """Validate persisted/imported rules with the runtime parser.

    Keeping one parser for import, approval, and resolution prevents shape or
    bounds accepted at one boundary from failing at another. An explicitly
    empty meal/rest collection remains a valid reviewed no-rule result.
    """
    _rules_from_payload(UUID(int=0), payload, citation)


def _location_timezone(value: str | None) -> ZoneInfo | None:
    if not value:
        return None
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _applicability_context_hash(
    *,
    company_id: UUID,
    location_id: UUID,
    rule_set_id: UUID,
    jurisdiction_id: UUID,
    industry_code: str | None,
    effective_from: date,
    effective_to: date | None,
    rules: Any,
) -> str:
    """Bind a tenant decision to the reviewed rule and stable scope inputs.

    Headcount deliberately is not part of this identity. Employer-size bounds
    are evaluated against the current count on every plan; routine hiring and
    termination must not revoke the organization's rule-set decision.
    """

    if isinstance(rules, str):
        rules = json.loads(rules)

    payload = {
        "company_id": str(company_id),
        "location_id": str(location_id),
        "rule_set_id": str(rule_set_id),
        "jurisdiction_id": str(jurisdiction_id),
        "industry_code": industry_code,
        "effective_from": effective_from.isoformat(),
        "effective_to": effective_to.isoformat() if effective_to else None,
        "rules": rules,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


async def get_employer_employee_count(conn, company_id: UUID) -> int | None:
    """Return declared headcount, else a known non-empty active roster count.

    Zero active employee rows cannot distinguish an employer with no workers
    from a tenant that has not imported its roster yet. Preserve that case as
    ``None`` so size-scoped rules fail visibly instead of being dropped as if
    the organization had affirmatively declared zero employees.
    """

    value = await conn.fetchval(
        """
        SELECT COALESCE(
            (SELECT headcount FROM company_handbook_profiles
             WHERE company_id = $1 AND headcount IS NOT NULL),
            (SELECT NULLIF(COUNT(*)::int, 0) FROM employees
             WHERE org_id = $1 AND termination_date IS NULL)
        )
        """,
        company_id,
    )
    return int(value) if value is not None else None


def _expected_rules_metadata(
    rules: list[BreakRule], *, context_hash: str, decision: str | None,
) -> dict[str, Any]:
    def summary(rule: BreakRule) -> str:
        comparison = "at least" if rule.trigger_operator == "gte" else "over"
        parts = [
            f"{rule.duration_minutes}-minute {rule.kind} break for shifts "
            f"{comparison} {rule.trigger_after_minutes / 60:g} hours"
        ]
        if rule.shift_start_window_from and rule.shift_start_window_before:
            parts.append(
                f"starting {rule.shift_start_window_from.strftime('%H:%M')}–"
                f"{rule.shift_start_window_before.strftime('%H:%M')}"
            )
        if rule.shift_spans_window_start and rule.shift_spans_window_end:
            parts.append(
                f"spanning {rule.shift_spans_window_start.strftime('%H:%M')}–"
                f"{rule.shift_spans_window_end.strftime('%H:%M')}"
            )
        if rule.shift_starts_before:
            parts.append(f"starting before {rule.shift_starts_before.strftime('%H:%M')}")
        if rule.shift_ends_after:
            parts.append(f"ending after {rule.shift_ends_after.strftime('%H:%M')}")
        if rule.window_start and rule.window_end:
            parts.append(
                f"taken {rule.window_start.strftime('%H:%M')}–"
                f"{rule.window_end.strftime('%H:%M')}"
            )
        if rule.recommend_midpoint:
            parts.append("placed around the shift midpoint")
        if rule.minimum_employees is not None:
            parts.append(f"for employers with at least {rule.minimum_employees} employees")
        if rule.maximum_employees is not None:
            parts.append(f"for employers with at most {rule.maximum_employees} employees")
        return "; ".join(parts)

    return {
        "rule_set_id": str(rules[0].rule_set_id),
        "context_hash": context_hash,
        "decision": decision,
        "citation": rules[0].citation,
        "authority_url": rules[0].authority_url,
        "effective_from": rules[0].effective_from.isoformat() if rules[0].effective_from else None,
        "effective_to": rules[0].effective_to.isoformat() if rules[0].effective_to else None,
        "requirements": [
            {
                "kind": rule.kind,
                "ordinal": rule.ordinal,
                "duration_minutes": rule.duration_minutes,
                "trigger_after_minutes": rule.trigger_after_minutes,
                "summary": summary(rule),
            }
            for rule in rules
        ],
    }


def _threshold(value: Any) -> Any:
    """A threshold's value, or `None` when there is no such boundary at all.

    The curated table writes `None` for "explicitly no such rule here" and
    `NO_CAP` for "the law affirmatively imposes no limit"; an approved
    extraction row carrying `no_rule=true` arrives here as `NO_CAP` too. Every
    reader below wants the same answer from both — there is no boundary to
    place a break against — and `NO_CAP` is a bare `object()`, so letting it
    reach `float()` raises `TypeError` instead of degrading gracefully. Before
    the legacy fallback merged `db_rules`, only the curated table reached these
    reads and no meal key in it was ever `NO_CAP`.
    """
    return None if value is schedule_compliance.NO_CAP else value


def _hours_to_offset_minutes(value: Any) -> int | None:
    """Whole minutes for a curated/extracted hour threshold, or None."""
    value = _threshold(value)
    if value is None:
        return None
    return int(float(value) * 60)


def _inconsistent_window_advisory(earliest_minutes: int, deadline_minutes: int) -> dict[str, Any]:
    """Said out loud when a state's own two meal thresholds cannot both hold.

    `meal_break_earliest_after_hours` and `meal_break_after_hours` are approved
    one row at a time and range-checked independently, so an earliest at or
    past the deadline is reachable. That pair describes a window no break can
    sit inside, which the stagger renders as a permanent `deadline_conflict` on
    every shift at the location with nothing on screen saying why.
    """
    return {
        "check": "break_rules",
        "code": "break_rules_inconsistent",
        "severity": "advisory",
        "message": (
            "This location's meal-break thresholds conflict: the earliest start "
            "is not before the deadline. The deadline is being applied on its "
            "own — verify the earliest start manually."
        ),
        "metadata": {
            "earliest_after_hours": round(earliest_minutes / 60, 2),
            "meal_break_after_hours": round(deadline_minutes / 60, 2),
        },
    }


def _legacy_rules(
    state: str,
    db_rules: dict[str, Any] | None = None,
    industry_code: str | None = None,
) -> tuple[list[BreakRule], list[dict[str, Any]]]:
    """Curated/extracted thresholds adapted into break rules, plus advisories.

    A state whose meal periods are legislated by TIME OF DAY (New York) is
    curated as a full period payload rather than as scalar thresholds, and that
    payload is parsed here by the same function the reviewed import path uses —
    so the scalar adaptation below never gets to invent an
    hours-from-start deadline the statute does not impose.

    The rules handed back are always internally consistent; a threshold pair
    that cannot both be true is dropped down to the one whose breach is the
    actual violation, and reaches the manager as an advisory instead.
    """
    state = (state or "").strip().upper()
    curated = schedule_compliance.curated_break_periods(state, industry_code)
    if curated is not None:
        # A malformed curated payload is a code bug, not a tenant condition:
        # let it raise here rather than degrade to "this state has no rules".
        # `test_curated_break_payloads_parse` is what keeps it from shipping.
        return _rules_from_payload(
            _uuid_for_legacy(f"{state}:{curated['scope']}"),
            curated["payload"],
            curated["citation"],
            authority_url=curated.get("authority_url"),
            source_type="legacy_curated",
        ), []
    rules = schedule_compliance.rules_for_state(state, db_rules)
    rule_set_id = _uuid_for_legacy(state or "UNKNOWN")
    out: list[BreakRule] = []
    advisories: list[dict[str, Any]] = []
    meal_after = _threshold(rules.get("meal_break_after_hours"))
    meal_minutes = _threshold(rules.get("meal_break_minutes"))
    citation = rules.get("citations", {}).get("meal_break", "")
    if meal_after is not None and meal_minutes is not None:
        deadline_offset = int(float(meal_after) * 60)
        # States that legislate an earliest measure it from the shift start
        # for the FIRST meal only (WAC 296-126-092(1), OAR
        # 839-020-0050(2)(d)); ordinal 2 keeps no earliest rather than
        # inheriting one that was never written about it.
        earliest_offset = _hours_to_offset_minutes(
            rules.get("meal_break_earliest_after_hours")
        )
        if earliest_offset is not None and earliest_offset >= deadline_offset:
            advisories.append(
                _inconsistent_window_advisory(earliest_offset, deadline_offset)
            )
            earliest_offset = None
        out.append(BreakRule(
            rule_set_id=rule_set_id,
            kind="meal",
            ordinal=1,
            trigger_after_minutes=deadline_offset,
            duration_minutes=int(meal_minutes),
            paid=False,
            deadline_offset_minutes=deadline_offset,
            earliest_offset_minutes=earliest_offset,
            citation=citation,
            source_type="legacy_curated",
        ))
        second_after = _threshold(rules.get("second_meal_after_hours"))
        if second_after is not None:
            out.append(BreakRule(
                rule_set_id=rule_set_id,
                kind="meal",
                ordinal=2,
                trigger_after_minutes=int(float(second_after) * 60),
                duration_minutes=int(meal_minutes),
                paid=False,
                deadline_offset_minutes=int(float(second_after) * 60),
                citation=citation,
                source_type="legacy_curated",
            ))
    return out, advisories


async def resolve_break_rules(
    conn,
    *,
    company_id: UUID,
    location_id: UUID,
    shift_date: date,
    employer_employee_count: int | None | object = _EMPLOYER_EMPLOYEE_COUNT_UNSET,
) -> ResolvedBreakRules:
    await lock_schedule_break_rule_guidance(conn, exclusive=False)
    readiness = await get_schedule_location_readiness(conn, company_id, location_id)
    if readiness.jurisdiction_id is None:
        return ResolvedBreakRules(
            rules=(), rule_set_ids=(), timezone=None,
            industry_code=readiness.industry_code, source="unmapped",
            advisories=({
                "check": "break_rules",
                "code": "break_rules_unmapped",
                "severity": "advisory",
                "message": "This location has no resolved jurisdiction for break rules.",
            },),
        )

    rows = await conn.fetch(
        """
        WITH RECURSIVE jurisdiction_chain AS (
            SELECT id, parent_id, 0 AS depth
            FROM jurisdictions
            WHERE id = $1
            UNION ALL
            SELECT j.id, j.parent_id, c.depth + 1
            FROM jurisdictions j
            JOIN jurisdiction_chain c ON c.parent_id = j.id
        )
        SELECT r.id, r.rules, r.citation, c.depth,
               r.industry_code, r.effective_from, r.effective_to,
               r.authority_url, r.source_type,
               r.jurisdiction_id
        FROM schedule_break_rule_sets r
        JOIN jurisdiction_chain c ON c.id = r.jurisdiction_id
        WHERE r.review_status = 'approved'
          AND r.is_active = true
          AND r.effective_from <= $2
          AND (r.effective_to IS NULL OR r.effective_to >= $2)
          AND (r.industry_code IS NULL OR r.industry_code = $3)
        ORDER BY c.depth ASC, (r.industry_code IS NULL) ASC, r.effective_from DESC
        """,
        readiness.jurisdiction_id,
        shift_date,
        readiness.industry_code,
    )
    if rows:
        chosen = rows[0]
        try:
            rules = _rules_from_payload(
                chosen["id"], chosen["rules"], chosen["citation"],
                effective_from=chosen["effective_from"],
                effective_to=chosen["effective_to"],
                authority_url=chosen.get("authority_url"),
                source_type=chosen.get("source_type"),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return ResolvedBreakRules(
                rules=(), rule_set_ids=(chosen["id"],),
                timezone=_location_timezone(readiness.timezone),
                industry_code=readiness.industry_code,
                source="error",
                advisories=({
                    "check": "break_rules",
                    "code": "break_rules_invalid",
                    "severity": "advisory",
                    "message": "Approved break rules could not be evaluated; verify manually.",
                    "metadata": {"reason": str(exc)},
                },),
            )
        # An approved empty collection explicitly records that this catalog
        # scope has no meal/rest periods. It needs no organization decision and
        # retains the pre-confirmation runtime contract.
        if not rules:
            return ResolvedBreakRules(
                rules=(), rule_set_ids=(chosen["id"],),
                timezone=_location_timezone(readiness.timezone),
                industry_code=readiness.industry_code,
                source="approved", advisories=(),
            )
        employee_count = (
            await get_employer_employee_count(conn, company_id)
            if employer_employee_count is _EMPLOYER_EMPLOYEE_COUNT_UNSET
            else (
                int(employer_employee_count)
                if employer_employee_count is not None
                else None
            )
        )
        context_hash = _applicability_context_hash(
            company_id=company_id,
            location_id=location_id,
            rule_set_id=chosen["id"],
            jurisdiction_id=chosen.get("jurisdiction_id") or readiness.jurisdiction_id,
            # The selected rule set's own industry is the stable scope input.
            # A generic rule remains the same rule if the company industry is
            # corrected, while a different industry-specific set has a new id.
            industry_code=chosen.get("industry_code"),
            effective_from=chosen["effective_from"],
            effective_to=chosen["effective_to"],
            rules=chosen["rules"],
        )
        decision = await conn.fetchval(
            """
            SELECT decision
            FROM company_schedule_break_rule_confirmations
            WHERE company_id = $1 AND location_id = $2 AND rule_set_id = $3
              AND (
                  context_hash = $4
                  OR (decision = 'grandfathered' AND context_hash IS NULL)
              )
            ORDER BY CASE WHEN context_hash = $4 THEN 0 ELSE 1 END
            LIMIT 1
            """,
            company_id, location_id, chosen["id"], context_hash,
        )
        if decision not in {"confirmed", "grandfathered"}:
            metadata = _expected_rules_metadata(
                rules, context_hash=context_hash, decision=decision,
            )
            message = (
                "Your organization marked these expected break rules as not applicable; "
                "no alternative reviewed coverage is mapped."
                if decision == "rejected"
                else "Matcha expects these reviewed break rules may apply to this organization. "
                     "Confirm or reject their applicability before Matcha uses them."
            )
            return ResolvedBreakRules(
                rules=(), rule_set_ids=(chosen["id"],),
                timezone=_location_timezone(readiness.timezone),
                industry_code=readiness.industry_code,
                source="rejected_expected" if decision == "rejected" else "confirmation_required",
                advisories=({
                    "check": "break_rules",
                    "code": "break_rules_applicability_rejected"
                    if decision == "rejected" else "break_rules_confirmation_required",
                    "severity": "advisory",
                    "message": message,
                    "metadata": metadata,
                },),
                employer_employee_count=employee_count,
                expected_rules=tuple(rules),
                applicability_context_hash=context_hash,
                applicability_decision=decision,
            )

        return ResolvedBreakRules(
            rules=tuple(rules),
            rule_set_ids=(chosen["id"],),
            timezone=_location_timezone(readiness.timezone),
            industry_code=readiness.industry_code,
            source=(
                "approved"
                if decision == "grandfathered"
                else "approved_and_organization_confirmed"
            ),
            # Confirmation is the normal success state, not an advisory to
            # duplicate into every assignment's persisted guidance.
            advisories=(),
            employer_employee_count=employee_count,
            expected_rules=tuple(rules),
            applicability_context_hash=context_hash,
            applicability_decision=decision,
        )

    # Preserve the current curated CA/federal behavior until structured rule
    # rows are populated by the reviewed import path.  A state the curated
    # table has never covered still gets its approved catalog extractions, so
    # break TIMING comes from the same merged source the write-path gate
    # already enforces against — `rules_for_state`'s per-state precedence keeps
    # a curated state from picking up a shadow DB copy of itself.
    state_row = await conn.fetchval(
        "SELECT state FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id,
        company_id,
    )
    state_code = (state_row or "").strip().upper()
    db_rules: dict[str, Any] | None = None
    fallback_advisories: tuple[dict[str, Any], ...] = ()
    if state_code and not schedule_compliance.is_curated_state(state_code):
        db_rules, fetch_failed = await shift_compliance._approved_db_rules(conn, state_code)
        if fetch_failed:
            # A transient catalog read must not silently read as "this state
            # legislates no break timing" — same fail-visible posture the write
            # path takes.
            fallback_advisories = ({
                "check": "break_rules",
                "code": "break_rules_catalog_unavailable",
                "severity": "advisory",
                "message": (
                    "Approved scheduling-law thresholds could not be read for this "
                    "location; verify break timing manually."
                ),
            },)
    legacy, legacy_advisories = _legacy_rules(
        state_code, db_rules, readiness.industry_code,
    )
    if legacy:
        return ResolvedBreakRules(
            rules=tuple(legacy),
            rule_set_ids=tuple(dict.fromkeys(rule.rule_set_id for rule in legacy)),
            timezone=_location_timezone(readiness.timezone),
            industry_code=readiness.industry_code,
            source="catalog_extraction" if db_rules else "legacy_curated",
            advisories=(*fallback_advisories, *legacy_advisories, {
                "check": "break_rules",
                "code": "break_rules_effective_date_unverified",
                "severity": "advisory",
                "message": (
                    "The fallback break rule has a cited source but no reviewed "
                    "effective date; verify current coverage manually."
                ),
            }),
        )
    return ResolvedBreakRules(
        rules=(), rule_set_ids=(),
        timezone=_location_timezone(readiness.timezone),
        industry_code=readiness.industry_code,
        source="unmapped",
        advisories=(*fallback_advisories, *legacy_advisories, {
            "check": "break_rules",
            "code": "break_rules_unmapped",
            "severity": "advisory",
            "message": "No approved break rules are mapped for this location and industry.",
        }),
    )


async def record_break_rule_applicability_decision(
    conn,
    *,
    company_id: UUID,
    location_id: UUID,
    shift_date: date,
    rule_set_id: UUID,
    context_hash: str,
    decision: str,
    actor_user_id: UUID,
) -> ResolvedBreakRules:
    """Record a tenant decision only when it matches the current expected context."""

    if decision not in {"confirmed", "rejected"}:
        raise ValueError("decision must be confirmed or rejected")
    await lock_schedule_break_rule_guidance(conn, exclusive=True)
    resolved = await resolve_break_rules(
        conn,
        company_id=company_id,
        location_id=location_id,
        shift_date=shift_date,
    )
    if (
        not resolved.expected_rules
        or resolved.expected_rules[0].rule_set_id != rule_set_id
        or resolved.applicability_context_hash != context_hash
    ):
        raise LookupError("Expected break-rule context changed; review the current rules again")
    await conn.execute(
        """
        INSERT INTO company_schedule_break_rule_confirmations
            (company_id, location_id, rule_set_id, context_hash, decision,
             confirmed_by, confirmed_at)
        VALUES ($1, $2, $3, $4, $5, $6, clock_timestamp())
        ON CONFLICT (company_id, location_id, rule_set_id, context_hash)
        DO UPDATE SET decision = EXCLUDED.decision,
                      confirmed_by = EXCLUDED.confirmed_by,
                      confirmed_at = clock_timestamp()
        """,
        company_id, location_id, rule_set_id, context_hash, decision, actor_user_id,
    )
    return resolved
