"""Pure math for Schedule Intelligence.

No DB, no FastAPI — every function is a deterministic transform of plain dicts
/ datetimes, same split as `schedule_rules.py`. The DB-touching orchestration
(fetching shifts/incidents/audit rows and calling these) lives in
`schedule_intelligence.py`; the Fair Workweek ordinance table + engine lives in
its own sibling module, `fair_workweek.py`.

Everything here is directional, not causal — small tenants generate few
incidents and few shifts, so a raw rate comparison is noise dressed as signal.
`small_n_guard` is the circuit breaker: below its thresholds, callers must
render counts only, never a rate or a "X% more likely" claim.

All scheduling data is *as-scheduled*, never *as-worked* — there is no
time-clock table. Every finding here describes what the schedule said, not
what happened on the floor.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

# Below these counts, a staffing/incident rate comparison is not meaningful —
# report counts only and say so. Tuned to roughly the point where one extra
# incident could flip a computed rate by double digits.
MIN_INCIDENTS_FOR_RATES = 10
MIN_SHIFTS_FOR_RATES = 50

# A rest gap shorter than this, or a scheduled streak this long, is the
# "fatigue" signal for module 1 — same order of magnitude as the clopening
# rest-hour floor in the Fair Workweek ordinances (10-11h) and OSHA fatigue
# guidance, not a statute in itself.
FATIGUE_MIN_REST_HOURS = 10.0
FATIGUE_MAX_CONSECUTIVE_DAYS = 6

# Shift-start hour bounds (UTC wall-clock; business_locations carries no
# timezone column, so this is a documented approximation, not a true local
# night window).
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6


def _as_utc(dt: datetime) -> datetime:
    """Normalize both naive (ir_incidents.occurred_at) and aware (shifts) values
    to aware UTC so they can be compared."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def match_incidents_to_shifts(
    incidents: list[dict[str, Any]], shifts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Match each incident to the shift covering its time + location, if any.

    An incident matches a shift when they share a `location_id` and the
    incident's `occurred_at` falls inside [starts_at, ends_at). Each incident
    matches at most one shift — ties (overlapping shifts at the same location)
    resolve to the earliest-starting shift, since that is almost always the
    one actually staffed at the incident time.

    Incidents with no `location_id`, or whose location has no shift covering
    the time, count toward `unmatched_count` and are never silently dropped —
    a high unmatched count means the correlation below is under-powered, and
    callers must say so.
    """
    by_location: dict[str, list[dict[str, Any]]] = {}
    for s in shifts:
        loc = s.get("location_id")
        if not loc:
            continue
        by_location.setdefault(str(loc), []).append(s)
    for bucket in by_location.values():
        bucket.sort(key=lambda s: s["starts_at"])

    matches: dict[str, Optional[str]] = {}
    unmatched = 0
    for inc in incidents:
        loc = inc.get("location_id")
        occurred = inc.get("occurred_at")
        matched_shift_id: Optional[str] = None
        if loc and occurred:
            occurred_utc = _as_utc(occurred)
            for s in by_location.get(str(loc), []):
                if _as_utc(s["starts_at"]) <= occurred_utc < _as_utc(s["ends_at"]):
                    matched_shift_id = s["id"]
                    break
        matches[str(inc["id"])] = matched_shift_id
        if matched_shift_id is None:
            unmatched += 1

    return {"matches": matches, "unmatched_count": unmatched}


def small_n_guard(
    n_incidents: int,
    n_shifts: int,
    *,
    min_incidents: int = MIN_INCIDENTS_FOR_RATES,
    min_shifts: int = MIN_SHIFTS_FOR_RATES,
) -> Optional[str]:
    """None when a rate comparison is safe to show; otherwise the reason it's
    suppressed (counts-only fallback)."""
    if n_incidents < min_incidents:
        return f"fewer than {min_incidents} incidents in this window — showing counts only"
    if n_shifts < min_shifts:
        return f"fewer than {min_shifts} shifts in this window — showing counts only"
    return None


def staffing_ratio_split(
    shifts: list[dict[str, Any]], matches: dict[str, Optional[str]]
) -> dict[str, Any]:
    """Split shifts (and their matched incidents) into understaffed vs adequate.

    `shifts` carry `required_staff` + `assigned_count`; cancelled shifts are
    excluded (nobody was going to be there). A shift with `assigned_count <
    required_staff` is understaffed. Rates are the caller's job to compute (and
    to suppress via `small_n_guard`) — this only produces the raw counts.
    """
    incident_shift_ids = [sid for sid in matches.values() if sid]
    understaffed_ids = set()
    adequate_ids = set()
    for s in shifts:
        if s.get("status") == "cancelled":
            continue
        sid = s["id"]
        if s.get("assigned_count", 0) < s.get("required_staff", 0):
            understaffed_ids.add(sid)
        else:
            adequate_ids.add(sid)

    incidents_understaffed = sum(1 for sid in incident_shift_ids if sid in understaffed_ids)
    incidents_adequate = sum(1 for sid in incident_shift_ids if sid in adequate_ids)

    def _bucket(shift_ids: set, incident_count: int) -> dict[str, Any]:
        n_shifts = len(shift_ids)
        rate = round(incident_count / n_shifts, 4) if n_shifts else None
        return {"shifts": n_shifts, "incidents": incident_count, "incident_rate": rate}

    return {
        "understaffed": _bucket(understaffed_ids, incidents_understaffed),
        "adequate": _bucket(adequate_ids, incidents_adequate),
    }


def is_night_shift(starts_at: datetime) -> bool:
    hour = _as_utc(starts_at).hour
    return hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR


def window_split(
    shifts: list[dict[str, Any]], matches: dict[str, Optional[str]]
) -> dict[str, Any]:
    """Same split as `staffing_ratio_split`, but by night vs day shift start."""
    incident_shift_ids = [sid for sid in matches.values() if sid]
    night_ids = set()
    day_ids = set()
    for s in shifts:
        if s.get("status") == "cancelled":
            continue
        (night_ids if is_night_shift(s["starts_at"]) else day_ids).add(s["id"])

    incidents_night = sum(1 for sid in incident_shift_ids if sid in night_ids)
    incidents_day = sum(1 for sid in incident_shift_ids if sid in day_ids)

    def _bucket(shift_ids: set, incident_count: int) -> dict[str, Any]:
        n_shifts = len(shift_ids)
        rate = round(incident_count / n_shifts, 4) if n_shifts else None
        return {"shifts": n_shifts, "incidents": incident_count, "incident_rate": rate}

    return {"night": _bucket(night_ids, incidents_night), "day": _bucket(day_ids, incidents_day)}


def min_rest_gap_hours(
    shift_windows: list[tuple[datetime, datetime]], target_start: datetime, target_end: datetime
) -> Optional[float]:
    """Smallest gap (hours) between the target window and any other window in
    `shift_windows` that ends before it starts or starts after it ends. Pure
    twin of `_compliance.py:_min_rest_gap`, operating on a preloaded list
    instead of issuing SQL — the correlation engine already has every shift for
    the employees it cares about in memory."""
    target_start_u, target_end_u = _as_utc(target_start), _as_utc(target_end)
    gaps: list[float] = []
    for s, e in shift_windows:
        s_u, e_u = _as_utc(s), _as_utc(e)
        if e_u <= target_start_u:
            gaps.append((target_start_u - e_u).total_seconds() / 3600.0)
        elif s_u >= target_end_u:
            gaps.append((s_u - target_end_u).total_seconds() / 3600.0)
    return min(gaps) if gaps else None


def consecutive_scheduled_days(
    shift_days: list[date], target_day: date, *, max_lookback: int = 14
) -> int:
    """Length of the run of consecutive calendar days (ending at `target_day`,
    inclusive) on which the employee has at least one shift. `shift_days` need
    not be sorted or deduped."""
    days = set(shift_days)
    days.add(target_day)
    streak = 0
    d = target_day
    for _ in range(max_lookback):
        if d in days:
            streak += 1
            d -= timedelta(days=1)
        else:
            break
    return streak


def fatigue_flags(
    incidents: list[dict[str, Any]],
    matches: dict[str, Optional[str]],
    shifts_by_id: dict[str, dict[str, Any]],
    employee_windows: dict[str, list[tuple[datetime, datetime]]],
    employee_days: dict[str, list[date]],
) -> list[dict[str, Any]]:
    """Incidents where an involved employee had a short rest gap or a long
    consecutive-day streak going into the matched shift.

    Only runs where `involved_employee_ids` is non-empty — a location/time
    correlation alone says nothing about a specific person's fatigue.
    `employee_windows`/`employee_days` are keyed by employee_id (str) and
    pre-fetched by the caller for exactly the employees named on these
    incidents (never the whole roster).
    """
    flags: list[dict[str, Any]] = []
    for inc in incidents:
        shift_id = matches.get(str(inc["id"]))
        if not shift_id:
            continue
        shift = shifts_by_id.get(shift_id)
        if not shift:
            continue
        for emp_id in inc.get("involved_employee_ids") or []:
            emp_key = str(emp_id)
            windows = employee_windows.get(emp_key, [])
            rest_gap = min_rest_gap_hours(windows, shift["starts_at"], shift["ends_at"])
            streak = consecutive_scheduled_days(
                employee_days.get(emp_key, []), _as_utc(shift["starts_at"]).date()
            )
            short_rest = rest_gap is not None and rest_gap < FATIGUE_MIN_REST_HOURS
            long_streak = streak >= FATIGUE_MAX_CONSECUTIVE_DAYS
            if short_rest or long_streak:
                flags.append({
                    "incident_id": str(inc["id"]),
                    "shift_id": shift_id,
                    "employee_id": emp_key,
                    "rest_gap_hours": round(rest_gap, 1) if rest_gap is not None else None,
                    "consecutive_scheduled_days": streak,
                    "short_rest": short_rest,
                    "long_streak": long_streak,
                })
    return flags


# ── Module 3: schedule instability × discipline pretext ─────────────────────

# Employer-initiated audit actions that represent a change TO an employee's
# schedule (as opposed to one they asked for — see classify_audit_row).
_SHIFT_CHANGE_ACTIONS = ("shift.update", "shift.delete", "assignment.create", "assignment.delete")
SHORT_NOTICE_HOURS = 72.0

# Pretext-flag threshold: an employee needs at least this many of the three
# instability signals elevated before a discipline record is flagged. A single
# elevated signal is common noise; two together is the pattern worth an HR
# admin's attention.
_PRETEXT_MIN_SIGNALS = 2
_PRETEXT_CHANGES_THRESHOLD = 5
_PRETEXT_SHORT_NOTICE_THRESHOLD = 3
_PRETEXT_SIGMA_HOURS_THRESHOLD = 8.0


def classify_audit_row(
    row: dict[str, Any], approvals_by_shift: dict[str, list[datetime]]
) -> dict[str, Any]:
    """Employer- vs employee-initiated, and how much notice the change gave.

    A `request.approved`/`request.denied` row for the same shift, timestamped
    within `_APPROVAL_CORRELATION_SECONDS` of a `shift.update` /
    `assignment.create` / `assignment.delete` row, means that change was the
    *consequence* of an employee's own swap/drop/unavailability request —
    every Fair Workweek ordinance exempts employee-initiated changes from
    predictability pay, and an instability metric built from them would
    misread an employee's own request as employer churn.

    `notice_hours` is the gap between when the change was logged and the
    affected shift's `starts_at` (pulled from the row's enriched `details`
    where present) — None when the row predates the Phase 1 audit enrichment
    (`uncostable_legacy`).
    """
    action = row["action"]
    details = row.get("details") or {}
    created_at = row["created_at"]
    shift_id = str(row.get("entity_id")) if row.get("entity_id") else None

    employee_initiated = False
    if shift_id and action in _SHIFT_CHANGE_ACTIONS:
        for approved_at in approvals_by_shift.get(shift_id, []):
            if abs((_as_utc(approved_at) - _as_utc(created_at)).total_seconds()) <= 120:
                employee_initiated = True
                break

    shift_starts_at = None
    for key in ("shift_starts_at", "after"):
        val = details.get(key)
        if isinstance(val, dict):
            val = val.get("starts_at")
        if val:
            shift_starts_at = val
            break
    if shift_starts_at is None:
        shift_starts_at = details.get("starts_at")

    notice_hours = None
    costable = shift_starts_at is not None
    if shift_starts_at:
        try:
            starts_dt = datetime.fromisoformat(str(shift_starts_at))
            notice_hours = (_as_utc(starts_dt) - _as_utc(created_at)).total_seconds() / 3600.0
        except (ValueError, TypeError):
            costable = False

    return {
        "action": action,
        "shift_id": shift_id,
        "employee_initiated": employee_initiated,
        "notice_hours": round(notice_hours, 1) if notice_hours is not None else None,
        "costable": costable,
        "created_at": created_at,
    }


def weekly_hours_sigma(weekly_hours: list[float]) -> Optional[float]:
    """Population std-dev of an employee's scheduled hours per week. None with
    fewer than 2 weeks of data (a sigma over one point is meaningless)."""
    if len(weekly_hours) < 2:
        return None
    mean = sum(weekly_hours) / len(weekly_hours)
    variance = sum((h - mean) ** 2 for h in weekly_hours) / len(weekly_hours)
    return round(variance ** 0.5, 2)


def instability_metrics(
    classified_rows: list[dict[str, Any]], weekly_hours: list[float]
) -> dict[str, Any]:
    """Roll up one employee's classified audit rows + weekly-hours series into
    the instability signals `pretext_flags` scores against."""
    employer_rows = [r for r in classified_rows if not r["employee_initiated"]]
    uncostable_legacy = sum(1 for r in employer_rows if not r["costable"])
    short_notice = sum(
        1 for r in employer_rows
        if r["costable"] and r["notice_hours"] is not None and r["notice_hours"] < SHORT_NOTICE_HOURS
    )
    return {
        "employer_changes": len(employer_rows),
        "short_notice_changes": short_notice,
        "weekly_hours_sigma": weekly_hours_sigma(weekly_hours),
        "uncostable_legacy": uncostable_legacy,
    }


def pretext_flags(
    discipline_records: list[dict[str, Any]], metrics_by_employee: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attendance discipline records whose employee had elevated schedule
    instability in the run-up to the infraction. Advisory, not a verdict — see
    the module docstring in `schedule_intelligence.py` for why this stays
    report-only in v1."""
    flagged: list[dict[str, Any]] = []
    for rec in discipline_records:
        metrics = metrics_by_employee.get(str(rec["employee_id"]))
        if not metrics:
            continue
        signals = []
        if metrics["employer_changes"] >= _PRETEXT_CHANGES_THRESHOLD:
            signals.append(f"{metrics['employer_changes']} employer-initiated schedule changes")
        if metrics["short_notice_changes"] >= _PRETEXT_SHORT_NOTICE_THRESHOLD:
            signals.append(f"{metrics['short_notice_changes']} changes with under {int(SHORT_NOTICE_HOURS)}h notice")
        sigma = metrics.get("weekly_hours_sigma")
        if sigma is not None and sigma >= _PRETEXT_SIGMA_HOURS_THRESHOLD:
            signals.append(f"weekly hours varied by {sigma}h (std dev)")
        if len(signals) >= _PRETEXT_MIN_SIGNALS:
            flagged.append({
                "discipline_record_id": str(rec["id"]),
                "employee_id": str(rec["employee_id"]),
                "infraction_type": rec.get("infraction_type"),
                "issued_date": rec.get("issued_date"),
                "metrics": metrics,
                "signals": signals,
                "rationale": (
                    "This attendance-related discipline record was issued against an employee "
                    "whose own schedule the employer changed frequently and on short notice in "
                    "the preceding window (" + "; ".join(signals) + "). Disciplining attendance "
                    "against a schedule the employer itself destabilized is a pattern plaintiffs' "
                    "counsel can use to argue pretext — review before relying on this record."
                ),
            })
    return flagged


# ── Module 4: qualified coverage ─────────────────────────────────────────────

def qualified_headcount(
    assignee_ids: list[str], lapses_by_employee: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Split a shift's assignees into qualified vs lapsed, given a precomputed
    lapse list per employee (credential/training expirations before the shift
    date, fetched by the caller)."""
    qualified = [e for e in assignee_ids if not lapses_by_employee.get(e)]
    lapsed = [e for e in assignee_ids if lapses_by_employee.get(e)]
    return {
        "assigned": len(assignee_ids),
        "qualified": len(qualified),
        "lapsed_employee_ids": lapsed,
    }
