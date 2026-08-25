"""Scheduling-compliance orchestration: DB assembly + enforcement.

The verdict logic is pure and lives in `services/scheduling/schedule_compliance.py`;
this module does the I/O (resolve the shift's state, the employee's week hours, age,
adjacent-shift rest gap) and returns the violation list.

Lifted out of `routes/employee_schedule/_compliance.py` (2026-07-31) so services
outside that route package — namely `services/scheduling/schedule_chat.py`, the
@huume channel-scheduling flow — can call `check_shift_compliance` without a
services→routes import. `raise_for_violations` (HTTPException-raising) stayed
behind in the route module; it's a route concern, not this one's. The route
module now re-imports everything below under its old names so every existing
caller/test is unaffected.

`check_shift_compliance` returns the violation list (no raising) so callers that
want to collect warnings instead of raising per shift (the bulk template path,
and now the chat proposal builder) can do so.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from . import schedule_compliance

logger = logging.getLogger(__name__)

# In-process TTL cache for catalog-extraction thresholds, keyed on state. This
# gate runs on every shift create/update/assign — a plain dict cache avoids a
# query per write without needing redis; an admin approval taking up to
# `_DB_RULES_CACHE_TTL` seconds to reach the gate is a non-issue.
_DB_RULES_CACHE: dict[str, tuple[float, Optional[dict[str, Any]]]] = {}
_DB_RULES_CACHE_TTL = 60.0

# rule_key → the citation-lookup name `schedule_compliance._cite` reads
# (`rules["citations"][name]`). Several rule_keys share one check name because
# they're the same check family — e.g. a state's meal-break DURATION and its
# TRIGGER hour both cite under "meal_break".
_RULE_KEY_TO_CHECK = {
    "meal_break_after_hours": "meal_break",
    "meal_break_minutes": "meal_break",
    "second_meal_after_hours": "meal_break",
    "daily_ot_hours": "daily_overtime",
    "daily_doubletime_hours": "daily_overtime",
    "weekly_ot_hours": "weekly_overtime",
    "min_rest_between_shifts_hours": "min_rest",
    "minor_u16_day_hours": "minor_hours",
    "minor_u16_week_hours": "minor_hours",
    "minor_16_17_day_hours": "minor_hours",
    "minor_16_17_week_hours": "minor_hours",
}


async def _approved_db_rules(conn, state: str) -> tuple[Optional[dict[str, Any]], bool]:
    """(db_rules, fetch_failed) — a state's APPROVED, active catalog-extraction
    thresholds, shaped for `schedule_compliance.rules_for_state`.

    `db_rules is None` with `fetch_failed=False` means genuinely nothing is
    approved yet for this state — the caller falls through to today's
    "not researched" advisory, unchanged. `fetch_failed=True` means the query
    itself errored, which the caller must surface as a visible advisory
    ("verify manually") rather than silently evaluating the shift as if the
    state had no rules at all — a transient DB error must not read as a legal
    all-clear (same "fail visible, not open" posture as `_employee_age`'s
    `age_lookup_failed`).
    """
    now = time.monotonic()
    cached = _DB_RULES_CACHE.get(state)
    if cached and now - cached[0] < _DB_RULES_CACHE_TTL:
        return cached[1], False

    try:
        rows = await conn.fetch(
            """
            SELECT rule_key, rule_value, no_rule, citation, block_grade
            FROM schedule_rule_extractions
            WHERE state = $1 AND review_status = 'approved' AND is_active = true
            """,
            state,
        )
    except Exception:
        logger.exception("schedule compliance: DB rule fetch failed for state %s", state)
        return None, True

    if not rows:
        _DB_RULES_CACHE[state] = (now, None)
        return None, False

    db_rules: dict[str, Any] = {"citations": {}}
    minor_block_grade: dict[str, bool] = {}
    for r in rows:
        key = r["rule_key"]
        value = schedule_compliance.NO_CAP if r["no_rule"] else float(r["rule_value"])
        db_rules[key] = value
        check_name = _RULE_KEY_TO_CHECK.get(key)
        if check_name:
            db_rules["citations"][check_name] = r["citation"]
        if key.startswith("minor_"):
            minor_block_grade[key] = bool(r["block_grade"])
    if minor_block_grade:
        db_rules["_minor_block_grade"] = minor_block_grade

    _DB_RULES_CACHE[state] = (now, db_rules)
    return db_rules, False


def _hours(starts_at: datetime, ends_at: datetime, break_minutes: int = 0) -> float:
    span = (ends_at - starts_at).total_seconds() / 3600.0
    return max(0.0, span - (break_minutes or 0) / 60.0)


def _week_window(d: datetime) -> tuple[datetime, datetime]:
    """SUNDAY-anchored 7-day window containing `d` (UTC) — matching the schedule
    grid (FE startOfWeekSunday / schedule_rules.sunday_indexed_weekday), so the
    weekly-overtime advisory aggregates the same week the admin is looking at.
    FLSA permits any fixed 7-day workweek; anchoring elsewhere than the rendered
    week silently defeats the advisory (48h on the grid can split into two
    sub-40h windows). No per-company workweek config exists to key off."""
    day = d.astimezone(timezone.utc).date()
    sunday = day - timedelta(days=(day.weekday() + 1) % 7)
    lo = datetime.combine(sunday, datetime.min.time(), tzinfo=timezone.utc)
    return lo, lo + timedelta(days=7)


def _age_on(dob: Optional[date], on: date) -> Optional[int]:
    if not dob:
        return None
    years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    return years


async def _location_state(
    conn, company_id: UUID, location_id: Optional[UUID]
) -> tuple[Optional[str], Optional[str]]:
    """(state, city) — city added so the write path can look up a Fair
    Workweek ordinance (`fair_workweek.ordinance_for_location`), which keys on
    city, not just state."""
    if location_id is None:
        return None, None
    row = await conn.fetchrow(
        "SELECT state, city FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    if not row:
        return None, None
    return row["state"], row["city"]


async def _employee_age(conn, company_id: UUID, employee_id: UUID, on: date) -> tuple[Optional[int], bool]:
    """(age, lookup_failed) from the PII-segregated employee_demographics table.

    age None + lookup_failed False = DOB legitimately not on file (minor check
    skips — never block on unknown age). lookup_failed True = the query itself
    errored; the caller surfaces an 'age unverifiable' advisory instead of
    silently green-lighting, because a DB error must not invisibly disable the
    one non-overridable protection."""
    try:
        dob = await conn.fetchval(
            """
            SELECT ed.date_of_birth
            FROM employee_demographics ed
            JOIN employees e ON e.id = ed.employee_id
            WHERE ed.employee_id = $1 AND e.org_id = $2
            """,
            employee_id, company_id,
        )
    except Exception:
        logger.exception("schedule compliance: DOB lookup failed for employee %s", employee_id)
        return None, True
    return _age_on(dob, on), False


async def _week_hours(conn, company_id: UUID, employee_id: UUID,
                      shift_start: datetime, this_shift_hours: float,
                      exclude_shift_id: Optional[UUID]) -> float:
    """This employee's total scheduled worked-hours for the week containing the
    shift, including the shift under evaluation."""
    lo, hi = _week_window(shift_start)
    rows = await conn.fetch(
        """
        SELECT s.starts_at, s.ends_at, s.break_minutes
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id
        WHERE s.company_id = $1 AND a.employee_id = $2
          AND s.status <> 'cancelled'
          AND s.starts_at >= $3 AND s.starts_at < $4
          AND ($5::uuid IS NULL OR s.id <> $5)
        """,
        company_id, employee_id, lo, hi, exclude_shift_id,
    )
    total = sum(_hours(r["starts_at"], r["ends_at"], r["break_minutes"] or 0) for r in rows)
    return total + this_shift_hours


async def _min_rest_gap(conn, company_id: UUID, employee_id: UUID,
                        starts_at: datetime, ends_at: datetime,
                        exclude_shift_id: Optional[UUID]) -> Optional[float]:
    """Smallest gap (hours) to the employee's nearest shift before/after this one.
    None when they have no adjacent shift."""
    row = await conn.fetchrow(
        """
        SELECT
          (SELECT MIN($3 - s.ends_at) FROM schedule_shifts s
             JOIN schedule_shift_assignments a ON a.shift_id = s.id
             WHERE s.company_id = $1 AND a.employee_id = $2 AND s.status <> 'cancelled'
               AND s.ends_at <= $3 AND ($5::uuid IS NULL OR s.id <> $5)) AS before_gap,
          (SELECT MIN(s.starts_at - $4) FROM schedule_shifts s
             JOIN schedule_shift_assignments a ON a.shift_id = s.id
             WHERE s.company_id = $1 AND a.employee_id = $2 AND s.status <> 'cancelled'
               AND s.starts_at >= $4 AND ($5::uuid IS NULL OR s.id <> $5)) AS after_gap
        """,
        company_id, employee_id, starts_at, ends_at, exclude_shift_id,
    )
    gaps = [g for g in (row["before_gap"], row["after_gap"]) if g is not None]
    if not gaps:
        return None
    return min(g.total_seconds() / 3600.0 for g in gaps)


async def _fair_workweek_advisories(
    conn,
    company_id: UUID,
    *,
    location_id: Optional[UUID],
    starts_at: datetime,
    ends_at: datetime,
    event: Optional[str],
    shift_published: bool,
    min_rest_gap_hours: Optional[float],
    state: Optional[str] = None,
    city: Optional[str] = None,
) -> list[dict]:
    """Write-time Fair Workweek advisories for one schedule change, or `[]`
    when there's no event, no location, or no curated ordinance for it (NYC +
    LA only — see `fair_workweek._FAIR_WORKWEEK_ORDINANCES`).

    `state`/`city` may be pre-fetched by the caller (`check_shift_compliance`
    already has them) to avoid a second `business_locations` round trip;
    passed `None`/`None` fetches them here, for the callers that skip the full
    compliance suite (unassign, shift delete/cancel — see their call sites).
    """
    if event is None or location_id is None:
        return []
    if state is None or city is None:
        loc = await conn.fetchrow(
            "SELECT state, city FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not loc:
            return []
        state, city = loc["state"], loc["city"]
    if not state or not city:
        return []

    from . import fair_workweek

    company = await conn.fetchrow("SELECT industry FROM companies WHERE id = $1", company_id)
    industry = company["industry"] if company else None
    ordinance, applicability = fair_workweek.ordinance_for_location(state, city, industry)
    if ordinance is None:
        return []
    return fair_workweek.preventive_advisories(
        ordinance=ordinance, applicability=applicability, event=event,
        shift_published=shift_published, starts_at=starts_at,
        now=datetime.now(timezone.utc), min_rest_gap_hours=min_rest_gap_hours,
        state=state,
    )


async def _training_lapse_advisories(
    conn,
    company_id: UUID,
    employee_id: UUID,
    *,
    shift_date: date,
    exclude_requirement_id: Optional[UUID] = None,
) -> list[dict]:
    """Advisory-only (never BLOCK — no statute behind this, unlike minor-hour
    caps): overdue training / lapsed credentials as of `shift_date` for the
    employee being assigned. `exclude_requirement_id` drops training items for
    the requirement a training-kind shift itself teaches — attending the
    session is the fix, not a violation to warn about.

    Silent no-op when both `training` and `credential_templates` are off
    (module-off, not "checked and clean" — same three-state idiom as
    `schedule_intelligence.build_qualified_coverage`)."""
    from app.core.feature_flags import get_company_features
    from . import schedule_intelligence

    try:
        features = await get_company_features(company_id, conn=conn)
    except Exception:
        logger.exception("Could not resolve company features for training-lapse check")
        return [{
            "check": "training_lapse_unavailable", "severity": "advisory",
            "message": "Could not verify training/credential status just now — "
                       "this is a temporary issue, not an all-clear. Verify manually.",
            "statute": None, "state": "",
        }]

    training_enabled = bool(features.get("training"))
    credential_templates_enabled = bool(features.get("credential_templates"))
    if not training_enabled and not credential_templates_enabled:
        return []

    lapse_items = await schedule_intelligence.fetch_lapse_items(
        conn, company_id, [employee_id],
        credential_templates_enabled=credential_templates_enabled,
        training_enabled=training_enabled,
    )
    items = lapse_items.get(str(employee_id), [])
    return shape_lapse_advisories(
        items, shift_date=shift_date, exclude_requirement_id=exclude_requirement_id,
    )


def shape_lapse_advisories(
    items: list[dict],
    *,
    shift_date: date,
    exclude_requirement_id: Optional[UUID] = None,
) -> list[dict]:
    """Pure: `fetch_lapse_items` rows -> advisory dicts, DB-free (unit-testable
    without a connection). An item lapses only if its date is strictly before
    `shift_date` — on/after isn't overdue yet. `exclude_requirement_id` drops
    only the TRAINING items for that requirement (a training-kind shift's own
    lapsed credentials still warn — attending class doesn't fix a license)."""
    violations: list[dict] = []
    for it in items:
        if it["date"] is None or it["date"] >= shift_date:
            continue
        if (
            exclude_requirement_id is not None
            and it["source"] == "training"
            and it["requirement_id"] == exclude_requirement_id
        ):
            continue
        check = "training_lapse" if it["source"] == "training" else "credential_lapse"
        violations.append({
            "check": check, "severity": "advisory",
            "message": f"{it['item']} was due {it['date'].isoformat()} — overdue as of this shift",
            "statute": None, "state": "",
        })
    return violations


async def check_shift_compliance(
    conn,
    company_id: UUID,
    *,
    location_id: Optional[UUID],
    starts_at: datetime,
    ends_at: datetime,
    break_minutes: int,
    employee_id: Optional[UUID] = None,
    exclude_shift_id: Optional[UUID] = None,
    fw_event: Optional[str] = None,
    fw_shift_published: bool = False,
    shift_kind: str = "work",
    training_requirement_id: Optional[UUID] = None,
    lapse_items: Optional[list[dict]] = None,
) -> list[dict]:
    """Assemble context + evaluate. Returns violations (never raises). When
    `employee_id` is None (shift not yet assigned), only shift-intrinsic checks
    (meal break, daily OT, extreme-shift) run.

    `fw_event` (one of `retime`/`cancel`/`assign`/`unassign`) additionally runs
    the preventive Fair Workweek advisories for this change — see
    `_fair_workweek_advisories`; omit it for calls that aren't a
    notice-window-relevant change (e.g. the compliance-panel preview).

    `shift_kind`/`training_requirement_id`: for a `kind='training'` shift, the
    training-lapse check excludes the requirement the shift itself teaches.

    `lapse_items`: pass this employee's pre-fetched `fetch_lapse_items` rows
    (from a single batched call over the whole employee list) to skip this
    call's own feature-lookup + lapse-item query — callers looping over many
    employees (create_shift, update_shift) would otherwise re-resolve company
    features and re-query training/credential lapses once per employee."""
    violations: list[dict] = []
    state, city = await _location_state(conn, company_id, location_id)
    worked = _hours(starts_at, ends_at, break_minutes)

    week_hours: Optional[float] = None
    min_rest: Optional[float] = None
    age: Optional[int] = None
    age_lookup_failed = False
    if employee_id is not None:
        age, age_lookup_failed = await _employee_age(
            conn, company_id, employee_id, starts_at.astimezone(timezone.utc).date()
        )
        from .schedule_eligibility import schedule_eligibility_violations
        violations.extend(await schedule_eligibility_violations(
            conn,
            company_id,
            employee_id=employee_id,
            shift_date=starts_at.astimezone(timezone.utc).date(),
            location_id=location_id,
            employee_age=age,
        ))
        week_hours = await _week_hours(conn, company_id, employee_id, starts_at, worked, exclude_shift_id)
        min_rest = await _min_rest_gap(conn, company_id, employee_id, starts_at, ends_at, exclude_shift_id)

    # Only bother fetching catalog-extraction thresholds for a state the
    # in-code table doesn't already curate — `rules_for_state` would ignore
    # them anyway (per-state precedence).
    db_rules: Optional[dict] = None
    db_rules_fetch_failed = False
    if state and not schedule_compliance.is_curated_state(state):
        db_rules, db_rules_fetch_failed = await _approved_db_rules(conn, state.strip().upper())

    violations.extend(schedule_compliance.evaluate_shift_for_employee(
        state=state,
        shift_hours=worked,
        break_minutes=break_minutes or 0,
        week_hours=week_hours,
        min_rest_gap_hours=min_rest,
        age=age,
        db_rules=db_rules,
    ))
    if age_lookup_failed:
        # Fail visible, not open: the minor check couldn't run at all.
        violations.append({
            "check": "minor_hours", "severity": "advisory",
            "message": "Could not verify this employee's age — minor work-hour "
                       "limits were not checked. Verify manually.",
            "statute": None, "state": (state or "").strip().upper(),
        })
    if db_rules_fetch_failed:
        violations.append({
            "check": "state_rules_unavailable", "severity": "advisory",
            "message": f"Could not load {(state or '').strip().upper()}'s scheduling-law "
                       "thresholds just now — this is a temporary issue, not an all-clear. "
                       "Verify manually before proceeding.",
            "statute": None, "state": (state or "").strip().upper(),
        })
    violations += await _fair_workweek_advisories(
        conn, company_id, location_id=location_id, state=state, city=city,
        starts_at=starts_at, ends_at=ends_at, event=fw_event,
        shift_published=fw_shift_published, min_rest_gap_hours=min_rest,
    )
    if employee_id is not None:
        if lapse_items is not None:
            violations += shape_lapse_advisories(
                lapse_items,
                shift_date=starts_at.astimezone(timezone.utc).date(),
                exclude_requirement_id=(
                    training_requirement_id if shift_kind == "training" else None
                ),
            )
        else:
            violations += await _training_lapse_advisories(
                conn, company_id, employee_id,
                shift_date=starts_at.astimezone(timezone.utc).date(),
                exclude_requirement_id=(
                    training_requirement_id if shift_kind == "training" else None
                ),
            )
    return violations
