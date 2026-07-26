"""Compliance checks for the employee-schedule write paths.

Two halves, the same split `discipline_compliance.py` uses:

1. **A curated, individually-cited threshold table** (`_SCHEDULING_RULES`) + pure
   evaluators. This is where the bright-line verdicts come from — NOT the
   `jurisdiction_requirements` catalog, whose `numeric_value` is semantically
   overloaded (a meal-break `30` is a break *duration*, an overtime `1.5` is a
   pay *multiplier*) and whose actual triggers ("meal break by the 5th hour")
   live in prose. A deterministic gate can't read those, so the thresholds are
   hand-authored and cited here.

2. **Catalog citations** (`get_schedule_statutes`) — the codified-gated read that
   surfaces the statutes behind the verdicts for display, mirroring
   `ir_statute_grounding.get_incident_statutes`.

Three invariants, copied from discipline_compliance:

- **Unmapped state ⇒ never silently "clear".** The table is deliberately partial
  (CA + federal today). An extreme shift in an unmapped state still yields an
  advisory telling the admin to verify; ordinary shifts yield nothing, but the
  table's partialness is documented — a missing state is "not researched", never
  "permitted". Add a state only with a real citation, never by inference.
- **Minor-hour violations BLOCK (non-overridable).** Everything else is an
  advisory the admin may force through with a logged reason. A child-labor
  hour cap is a bright-line statutory prohibition, not a judgment call.
- **The catalog never decides a verdict.** Catalog rows are citation *display*
  only; the verdict is this table's.

⚠️ Citations are researched, not attorney-reviewed. Verify with counsel before
this ships to a paying tenant (same posture as discipline_compliance).

Checks are "as-scheduled", not "as-worked": `break_minutes` is the shift's
planned break, not a clock-out record (no time-clock data exists). UI copy must
say "scheduled shift violates…", not "employee worked…".
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Curated threshold table ──────────────────────────────────────────────
# Keyed on business_locations.state (2-letter). 'US' = federal baseline that
# applies everywhere. Only bright-line, nationally-or-state-settled thresholds
# with a real citation. `None` = "explicitly no such rule here — do not invent";
# NO_CAP = "the law affirmatively imposes no limit" (distinct from an absent key,
# which means "not researched" and yields a verify-manually advisory).
#
# School-day caps (3h for under-16s, 29 C.F.R. § 570.35 / Cal. Lab. Code § 1391)
# are deliberately NOT modeled: no school-calendar signal exists, and a dead key
# pretending coverage is worse than a documented gap. Future work.
NO_CAP = object()

_SCHEDULING_RULES: dict[str, dict[str, Any]] = {
    "US": {
        "weekly_ot_hours": 40,                 # FLSA 29 U.S.C. § 207(a)
        "minor_u16_day_hours": 8,              # 29 C.F.R. § 570.35 (non-school day)
        "minor_u16_week_hours": 40,            # (non-school week)
        # FLSA affirmatively imposes NO hour cap on 16-17 year-olds (hazardous-
        # occupation rules aside, out of scope) — encode that so a 16-17 hire
        # outside a state with its own cap doesn't get a bogus "not researched"
        # advisory on every shift.
        "minor_16_17_day_hours": NO_CAP,
        "minor_16_17_week_hours": NO_CAP,
        "citations": {
            "weekly_overtime": "FLSA, 29 U.S.C. § 207(a)",
            "minor_hours": "FLSA child labor, 29 C.F.R. § 570.35",
        },
    },
    "CA": {
        "meal_break_after_hours": 5,           # Cal. Lab. Code § 512
        "meal_break_minutes": 30,
        "second_meal_after_hours": 10,
        "daily_ot_hours": 8,                   # Cal. Lab. Code § 510
        "daily_doubletime_hours": 12,
        "weekly_ot_hours": 40,
        "min_rest_between_shifts_hours": None,  # no general CA right-to-rest statute
        "minor_u16_day_hours": 8,              # Cal. Lab. Code § 1391 (non-school day)
        "minor_16_17_day_hours": 8,            # Cal. Lab. Code § 1391 (school in session)
        "citations": {
            "meal_break": "Cal. Lab. Code § 512",
            "daily_overtime": "Cal. Lab. Code § 510",
            "weekly_overtime": "Cal. Lab. Code § 510",
            "minor_hours": "Cal. Lab. Code § 1391",
        },
    },
}

# Codified catalog categories that carry scheduling law, for citation display.
SCHEDULE_CATEGORIES = [
    "overtime", "meal_breaks", "scheduling_reporting", "minor_work_permit", "sick_leave",
]

_EXTREME_SHIFT_HOURS = 12  # an unmapped-state shift past this still warns


def is_curated_state(state: Optional[str]) -> bool:
    """True when `_SCHEDULING_RULES` hand-curates this state — the
    catalog-extraction gate (`_approved_db_rules`) is never consulted for
    these, per `rules_for_state`'s per-state precedence."""
    st = (state or "").strip().upper()
    return bool(st) and st in _SCHEDULING_RULES


def rules_for_state(
    state: Optional[str], db_rules: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Merged federal + state thresholds. State keys win over the US baseline.

    `db_rules` is the catalog-extraction gate's own contribution — approved
    rows from `schedule_rule_extraction`, shaped by
    `routes/employee_schedule/_compliance.py:_approved_db_rules` into this same
    `{rule_key: value|NO_CAP, "citations": {...}, "_minor_block_grade": {...}}`
    form. **Per-state precedence, not per-key**: a state present in the
    hand-curated `_SCHEDULING_RULES` table ignores `db_rules` entirely — mixed
    provenance within one state (some thresholds hand-verified, others
    AI-extracted) is unexplainable in the compliance panel, and the curated
    table is the attorney-facing baseline. `db_rules` only applies to states
    `_SCHEDULING_RULES` has never covered.
    """
    merged = dict(_SCHEDULING_RULES["US"])
    merged["citations"] = dict(_SCHEDULING_RULES["US"]["citations"])
    st = (state or "").strip().upper()
    if st and st in _SCHEDULING_RULES and st != "US":
        override = _SCHEDULING_RULES[st]
        for k, v in override.items():
            if k == "citations":
                merged["citations"].update(v)
            else:
                merged[k] = v
    elif st and db_rules:
        for k, v in db_rules.items():
            if k == "citations":
                merged["citations"].update(v)
            else:
                merged[k] = v
    return merged


def rules_summary(
    state: Optional[str], db_rules: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """JSON-safe view of rules_for_state: the NO_CAP sentinel (a bare object(),
    unserializable) renders as the string 'no_cap'. Carries a `source` marker
    so the location-law panel can tell a hand-curated threshold from an
    approved catalog extraction."""
    st = (state or "").strip().upper()
    if st in _SCHEDULING_RULES:
        source = "curated"
    elif db_rules:
        source = "catalog_extraction"
    else:
        source = "unmapped"
    return {
        "source": source,
        **{
            k: ("no_cap" if v is NO_CAP else v)
            for k, v in rules_for_state(state, db_rules).items()
            if k != "_minor_block_grade"
        },
    }


def _violation(check: str, severity: str, message: str, statute: Optional[str], state: str) -> dict:
    return {"check": check, "severity": severity, "message": message,
            "statute": statute, "state": state}


def _cite(rules: dict, key: str) -> Optional[str]:
    return rules.get("citations", {}).get(key)


# ── Pure per-check evaluators ────────────────────────────────────────────

def check_meal_break(shift_hours: float, break_minutes: int, rules: dict, state: str) -> list[dict]:
    after = rules.get("meal_break_after_hours")
    need = rules.get("meal_break_minutes")
    if after is None or need is None:
        return []
    out: list[dict] = []
    if shift_hours > after and (break_minutes or 0) < need:
        out.append(_violation(
            "meal_break", "advisory",
            f"Shift is {shift_hours:.1f}h but is scheduled with only "
            f"{break_minutes or 0} min break; a {need}-min meal break is required "
            f"for shifts over {after}h.",
            _cite(rules, "meal_break"), state,
        ))
    second = rules.get("second_meal_after_hours")
    if second is not None and shift_hours > second and (break_minutes or 0) < need * 2:
        out.append(_violation(
            "meal_break", "advisory",
            f"Shift over {second}h requires a second meal break "
            f"({need * 2} min total scheduled break).",
            _cite(rules, "meal_break"), state,
        ))
    return out


def check_daily_overtime(shift_hours: float, rules: dict, state: str) -> list[dict]:
    cap = rules.get("daily_ot_hours")
    if cap is None or shift_hours <= cap:
        return []
    dt = rules.get("daily_doubletime_hours")
    tail = f" (double-time past {dt}h)" if dt and shift_hours > dt else ""
    return [_violation(
        "daily_overtime", "advisory",
        f"Shift is {shift_hours:.1f}h — incurs daily overtime past {cap}h{tail}; "
        f"ensure overtime pay.",
        _cite(rules, "daily_overtime"), state,
    )]


def check_weekly_hours(week_hours: Optional[float], rules: dict, state: str) -> list[dict]:
    cap = rules.get("weekly_ot_hours")
    if cap is None or week_hours is None or week_hours <= cap:
        return []
    return [_violation(
        "weekly_overtime", "advisory",
        f"Employee is scheduled {week_hours:.1f}h this week — past {cap}h incurs "
        f"weekly overtime; ensure overtime pay.",
        _cite(rules, "weekly_overtime"), state,
    )]


def check_min_rest(min_gap_hours: Optional[float], rules: dict, state: str) -> list[dict]:
    threshold = rules.get("min_rest_between_shifts_hours")
    if threshold is None or min_gap_hours is None or min_gap_hours >= threshold:
        return []
    return [_violation(
        "min_rest", "advisory",
        f"Only {min_gap_hours:.1f}h rest between consecutive shifts; "
        f"{threshold}h is required.",
        _cite(rules, "min_rest"), state,
    )]


def check_minor_hours(age: Optional[int], shift_hours: float, week_hours: Optional[float],
                      rules: dict, state: str,
                      *, block_grade: Optional[dict[str, bool]] = None) -> list[dict]:
    """Minor hour caps. Age unknown (no DOB) ⇒ no result (can't assert).

    `block_grade` distinguishes the hand-curated caps (US/CA — always BLOCK,
    the historical behavior, preserved by leaving this `None`) from
    catalog-extraction-derived caps, which are advisory by default and BLOCK
    only for the specific `rule_key` a human explicitly marked block-grade
    (`schedule_rule_extraction` / the admin review surface) — an approved
    citation is not by itself license for a non-overridable 422 across an
    entire bulk-approved state.
    """
    if age is None or age >= 18:
        return []
    statute = _cite(rules, "minor_hours")
    if age < 16:
        day_cap = rules.get("minor_u16_day_hours")
        week_cap = rules.get("minor_u16_week_hours")
        day_key, week_key = "minor_u16_day_hours", "minor_u16_week_hours"
    else:  # 16-17
        day_cap = rules.get("minor_16_17_day_hours")
        week_cap = rules.get("minor_16_17_week_hours")
        day_key, week_key = "minor_16_17_day_hours", "minor_16_17_week_hours"

    def _severity(rule_key: str) -> str:
        if block_grade is None:
            return "block"
        return "block" if block_grade.get(rule_key) else "advisory"

    # NO_CAP = the law affirmatively imposes no limit for this bracket (e.g.
    # FLSA for 16-17) — a determination, not a gap. Treat as "no cap to check".
    if day_cap is NO_CAP:
        day_cap = None
        determined = True
    else:
        determined = day_cap is not None
    if week_cap is NO_CAP:
        week_cap = None
        determined = True
    else:
        determined = determined or week_cap is not None

    if not determined:
        # Minor scheduled but this bracket genuinely has no researched rule —
        # advisory, never a silent pass (unmapped-state invariant).
        return [_violation(
            "minor_hours", "advisory",
            f"Employee is a minor (age {age}); {state} minor-hour limits are not "
            f"researched — verify manually before scheduling.",
            statute, state,
        )]
    out: list[dict] = []
    if day_cap is not None and shift_hours > day_cap:
        out.append(_violation(
            "minor_hours", _severity(day_key),
            f"Employee is {age} — a {shift_hours:.1f}h shift exceeds the "
            f"{day_cap}h daily limit for minors.",
            statute, state,
        ))
    if week_cap is not None and week_hours is not None and week_hours > week_cap:
        out.append(_violation(
            "minor_hours", _severity(week_key),
            f"Employee is {age} — {week_hours:.1f}h this week exceeds the "
            f"{week_cap}h weekly limit for minors.",
            statute, state,
        ))
    return out


def evaluate_shift_for_employee(
    *,
    state: Optional[str],
    shift_hours: float,
    break_minutes: int,
    week_hours: Optional[float] = None,
    min_rest_gap_hours: Optional[float] = None,
    age: Optional[int] = None,
    db_rules: Optional[dict[str, Any]] = None,
) -> list[dict]:
    """Run every applicable check for one (shift, employee) pair.

    All args are plain values — no DB. `week_hours`/`min_rest_gap_hours`/`age`
    are optional; a None simply skips that check (the route supplies what it has).
    `db_rules` is the caller's fetch of this state's APPROVED catalog-extraction
    thresholds (see `rules_for_state`); ignored for states `_SCHEDULING_RULES`
    already curates.
    """
    st = (state or "").strip().upper()
    rules = rules_for_state(st, db_rules)
    block_grade = rules.get("_minor_block_grade")
    out: list[dict] = []
    out += check_meal_break(shift_hours, break_minutes, rules, st)
    out += check_daily_overtime(shift_hours, rules, st)
    out += check_weekly_hours(week_hours, rules, st)
    out += check_min_rest(min_rest_gap_hours, rules, st)
    out += check_minor_hours(age, shift_hours, week_hours, rules, st, block_grade=block_grade)

    # Unmapped-state safety net: an extreme shift in a state we have no rules
    # for must not read as clear. Partial DB coverage (e.g. only weekly OT was
    # approved) must not silence this — it fires unless the meal-break trigger
    # OR the daily-OT cap is actually determined.
    meal_or_ot_determined = (
        rules.get("meal_break_after_hours") is not None or rules.get("daily_ot_hours") is not None
    )
    if (not out and st and st not in _SCHEDULING_RULES and not meal_or_ot_determined
            and shift_hours >= _EXTREME_SHIFT_HOURS):
        out.append(_violation(
            "unmapped_state", "advisory",
            f"{shift_hours:.1f}h shift in {st}, which has no researched scheduling "
            f"thresholds — verify meal-break/overtime rules manually.",
            None, st,
        ))
    return out


def has_block(violations: list[dict]) -> bool:
    return any(v.get("severity") == "block" for v in violations)


# ── Catalog citations (display only) ─────────────────────────────────────

async def get_schedule_statutes(location_id, company_id, conn=None) -> list[dict]:
    """Codified scheduling-law rows for a location's state (+ federal), for the
    "Scheduling law for this location" panel. Mirrors
    `ir_statute_grounding.get_incident_statutes`: codified-gated,
    `_filter_requirements_for_company` applied (raw catalog query bypasses the
    tenant projection), degrade to [] on any failure. Optional `conn=` avoids a
    nested pool checkout when the caller already holds one.
    """
    from uuid import UUID
    try:
        loc_uuid = location_id if isinstance(location_id, UUID) else UUID(str(location_id))
        comp_uuid = company_id if isinstance(company_id, UUID) else UUID(str(company_id))
    except (ValueError, TypeError):
        return []

    async def _run(c) -> list[dict]:
        from app.core.services.compliance_service import (
            codified_gate_sql, _filter_requirements_for_company,
        )
        loc = await c.fetchrow(
            "SELECT state FROM business_locations WHERE id = $1 AND company_id = $2",
            loc_uuid, comp_uuid,
        )
        if not loc or not loc["state"]:
            return []
        state = (loc["state"] or "").strip().upper()
        gate = await codified_gate_sql("jr", conn=c)
        rows = await c.fetch(
            f"""
            SELECT jr.id, j.state, jr.category, jr.title, jr.description,
                   jr.statute_citation, jr.source_url, jr.applicable_industries,
                   j.display_name AS authority_name
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE j.state = ANY($1::varchar[])
              AND jr.status = 'active'
              AND (jr.expiration_date IS NULL OR jr.expiration_date >= CURRENT_DATE)
              AND jr.category = ANY($2::varchar[])
              {gate}
            ORDER BY (j.state = 'US') ASC, jr.category
            LIMIT 60
            """,
            sorted({state, "US"}),
            list(SCHEDULE_CATEGORIES),
        )
        filtered = await _filter_requirements_for_company(c, comp_uuid, [dict(r) for r in rows])
        return [{
            "requirement_id": str(r["id"]),
            "state": r.get("authority_name") or r.get("state") or "",
            "category": (r.get("category") or "").strip().lower(),
            "title": r.get("title") or "Requirement",
            "statute_citation": r.get("statute_citation"),
            "source_url": r.get("source_url"),
        } for r in filtered]

    try:
        if conn is not None:
            return await _run(conn)
        from app.database import get_connection
        async with get_connection() as c:
            return await _run(c)
    except Exception:
        logger.exception("schedule_compliance: statute fetch failed")
        return []
