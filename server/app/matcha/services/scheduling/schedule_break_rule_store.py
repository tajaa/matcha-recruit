"""Database resolution and legacy adaptation for structured break rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import schedule_compliance
from .schedule_breaks import BreakRule
from .schedule_location_readiness import get_schedule_location_readiness


@dataclass(frozen=True)
class ResolvedBreakRules:
    rules: tuple[BreakRule, ...]
    rule_set_ids: tuple[UUID, ...]
    timezone: ZoneInfo | None
    industry_code: str | None
    source: str
    advisories: tuple[dict[str, Any], ...]


def _uuid_for_legacy(state: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"matcha:schedule-break-rules:legacy:{state}")


def _as_int(value: Any, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _age_bounds(raw: dict[str, Any]) -> tuple[int | None, int | None]:
    minimum = _as_int(raw.get("minimum_age", raw.get("min_age")))
    maximum = _as_int(raw.get("maximum_age", raw.get("max_age")))
    if minimum is not None and not 0 <= minimum <= 125:
        raise ValueError("minimum_age must be between 0 and 125")
    if maximum is not None and not 0 <= maximum <= 125:
        raise ValueError("maximum_age must be between 0 and 125")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("minimum_age cannot exceed maximum_age")
    return minimum, maximum


def _rules_from_payload(rule_set_id: UUID, payload: Any, citation: str) -> list[BreakRule]:
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
            duration = _as_int(raw.get("duration_minutes"))
            trigger = _as_int(raw.get("trigger_after_minutes"))
            ordinal = _as_int(raw.get("ordinal"), default=1)
            count_bands = raw.get("count_bands") if kind == "rest" else None
            if duration is None or duration <= 0:
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
                    if band_trigger is None or band_trigger < 0 or count < 0:
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
                            paid=bool(raw.get("paid", kind == "rest")),
                            deadline_offset_minutes=_as_int(raw.get("deadline_offset_minutes")),
                            earliest_offset_minutes=_as_int(raw.get("earliest_offset_minutes")),
                            recommended_offset_minutes=_as_int(raw.get("recommended_offset_minutes")),
                            latest_offset_minutes=_as_int(raw.get("latest_offset_minutes")),
                            waiver_allowed=bool((raw.get("waiver") or {}).get("allowed", False)),
                            waiver_max_shift_minutes=_as_int((raw.get("waiver") or {}).get("max_shift_minutes")),
                            trigger_operator=raw.get("trigger_operator", "gt"),
                            minimum_age=minimum_age,
                            maximum_age=maximum_age,
                            citation=str(raw.get("citation") or citation),
                        ))
                    previous_count = count
                continue
            waiver = raw.get("waiver") or {}
            parsed.append(BreakRule(
                rule_set_id=rule_set_id,
                kind=kind,
                ordinal=ordinal or 1,
                trigger_after_minutes=trigger or 0,
                duration_minutes=duration,
                paid=bool(raw.get("paid", kind == "rest")),
                deadline_offset_minutes=_as_int(raw.get("deadline_offset_minutes")),
                earliest_offset_minutes=_as_int(raw.get("earliest_offset_minutes")),
                recommended_offset_minutes=_as_int(raw.get("recommended_offset_minutes")),
                latest_offset_minutes=_as_int(raw.get("latest_offset_minutes")),
                waiver_allowed=bool(waiver.get("allowed", False)),
                waiver_max_shift_minutes=_as_int(waiver.get("max_shift_minutes")),
                trigger_operator=raw.get("trigger_operator", "gt"),
                minimum_age=minimum_age,
                maximum_age=maximum_age,
                citation=str(raw.get("citation") or citation),
            ))
    return parsed


def _location_timezone(value: str | None) -> ZoneInfo | None:
    if not value:
        return None
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _legacy_rules(state: str) -> list[BreakRule]:
    state = (state or "").strip().upper()
    rules = schedule_compliance.rules_for_state(state)
    rule_set_id = _uuid_for_legacy(state or "UNKNOWN")
    out: list[BreakRule] = []
    meal_after = rules.get("meal_break_after_hours")
    meal_minutes = rules.get("meal_break_minutes")
    citation = rules.get("citations", {}).get("meal_break", "")
    if meal_after is not None and meal_minutes is not None:
        out.append(BreakRule(
            rule_set_id=rule_set_id,
            kind="meal",
            ordinal=1,
            trigger_after_minutes=int(float(meal_after) * 60),
            duration_minutes=int(meal_minutes),
            paid=False,
            deadline_offset_minutes=int(float(meal_after) * 60),
            citation=citation,
        ))
        second_after = rules.get("second_meal_after_hours")
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
            ))
    return out


async def resolve_break_rules(
    conn,
    *,
    company_id: UUID,
    location_id: UUID,
    shift_date: date,
) -> ResolvedBreakRules:
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
               r.industry_code, r.effective_from, r.effective_to
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
            rules = _rules_from_payload(chosen["id"], chosen["rules"], chosen["citation"])
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
        return ResolvedBreakRules(
            rules=tuple(rules),
            rule_set_ids=(chosen["id"],),
            timezone=_location_timezone(readiness.timezone),
            industry_code=readiness.industry_code,
            source="approved",
            advisories=(),
        )

    # Preserve the current curated CA/federal behavior until structured rule
    # rows are populated by the reviewed import path.
    state_row = await conn.fetchval(
        "SELECT state FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id,
        company_id,
    )
    legacy = _legacy_rules(state_row or "")
    if legacy:
        return ResolvedBreakRules(
            rules=tuple(legacy),
            rule_set_ids=tuple(dict.fromkeys(rule.rule_set_id for rule in legacy)),
            timezone=_location_timezone(readiness.timezone),
            industry_code=readiness.industry_code,
            source="legacy_curated",
            advisories=(),
        )
    return ResolvedBreakRules(
        rules=(), rule_set_ids=(),
        timezone=_location_timezone(readiness.timezone),
        industry_code=readiness.industry_code,
        source="unmapped",
        advisories=({
            "check": "break_rules",
            "code": "break_rules_unmapped",
            "severity": "advisory",
            "message": "No approved break rules are mapped for this location and industry.",
        },),
    )
