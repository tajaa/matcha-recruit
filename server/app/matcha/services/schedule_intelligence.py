"""Schedule Intelligence — DB orchestration for the four analytics modules.

Pure math lives in `schedule_intelligence_stats.py` (incident correlation,
instability metrics, qualified coverage) and `fair_workweek.py` (the Fair
Workweek exposure engine); this module does the I/O — fetching shifts,
incidents, audit rows, discipline records, and credential/training data — and
hands plain dicts to those pure functions.

Read-time only: no new tables, no precompute cache, no Celery task. Tenant
windows are low-thousands of rows, so every builder here runs a handful of
indexed queries per request. If that stops being true, a v2 nightly precompute
can sit behind the same function signatures without changing the endpoints.

Every builder returns `disclaimer` (or the caller attaches the shared
constants below) — this is directional risk-awareness data computed from
*scheduled*, not worked, time, and none of it is a legal or payroll
calculation.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from . import fair_workweek
from . import schedule_intelligence_stats as stats
from .discipline_compliance import ATTENDANCE_INFRACTION_TYPES

INCIDENT_CORRELATION_DISCLAIMER = (
    "Directional correlation between this company's scheduled staffing and its own "
    "incident reports — not a causal or statistical claim, and based on scheduled "
    "presence, not confirmed attendance (no time-clock data exists)."
)
PRETEXT_SHIELD_DISCLAIMER = (
    "Advisory only. Flags attendance discipline records where the employee's own "
    "schedule was frequently changed by the employer beforehand — a pattern worth "
    "reviewing, not a legal determination. Metric quality improves as schedule-change "
    "history accumulates after this feature's release."
)
QUALIFIED_COVERAGE_DISCLAIMER = (
    "Reflects credential/training records as stored on the platform as of now — "
    "verify against the source system before relying on it for a compliance decision."
)

_ATTENDANCE_LOOKBACK_DAYS = 90
_PRETEXT_LOOKBACK_MONTHS = 6


def _details(raw: Any) -> dict:
    """schedule_audit_log.details is jsonb, but asyncpg hands it back as a raw
    JSON string (no codec registered on the pool) — every reader has to parse
    it itself, same convention as feature_flags.merge_company_features."""
    if isinstance(raw, str):
        try:
            return json.loads(raw) or {}
        except json.JSONDecodeError:
            return {}
    return raw or {}


# ── Module 1: incident × schedule correlation ────────────────────────────

async def build_incident_correlation(conn, company_id: UUID, *, days: int = 180) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)

    incident_rows = await conn.fetch(
        """
        SELECT id, occurred_at, location_id, severity, incident_type, involved_employee_ids
        FROM ir_incidents
        WHERE company_id = $1 AND occurred_at >= $2 AND location_id IS NOT NULL
        """,
        company_id, window_start.replace(tzinfo=None),  # occurred_at is naive UTC (no tz column)
    )
    incidents = [dict(r) for r in incident_rows]

    shift_rows = await conn.fetch(
        """
        SELECT s.id, s.location_id, s.starts_at, s.ends_at, s.required_staff, s.status,
               (SELECT COUNT(*) FROM schedule_shift_assignments a
                WHERE a.shift_id = s.id AND a.status <> 'declined') AS assigned_count
        FROM schedule_shifts s
        WHERE s.company_id = $1 AND s.starts_at < $3 AND s.ends_at > $2
        """,
        company_id, window_start, now,
    )
    shifts = [
        {**dict(r), "id": str(r["id"]), "location_id": str(r["location_id"]) if r["location_id"] else None}
        for r in shift_rows
    ]
    shifts_by_id = {s["id"]: s for s in shifts}

    match_result = stats.match_incidents_to_shifts(incidents, shifts)
    matches = match_result["matches"]

    suppressed_reason = stats.small_n_guard(len(incidents), len(shifts))
    by_staffing = stats.staffing_ratio_split(shifts, matches) if not suppressed_reason else None
    by_window = stats.window_split(shifts, matches) if not suppressed_reason else None

    by_location: dict[str, dict[str, Any]] = {}
    loc_rows = await conn.fetch(
        "SELECT id, name FROM business_locations WHERE company_id = $1", company_id,
    )
    loc_names = {str(r["id"]): r["name"] for r in loc_rows}
    shifts_by_location: dict[str, list[dict]] = defaultdict(list)
    for s in shifts:
        if s["location_id"]:
            shifts_by_location[s["location_id"]].append(s)
    incidents_by_location: dict[str, int] = defaultdict(int)
    for inc in incidents:
        loc = str(inc["location_id"]) if inc.get("location_id") else None
        if loc and matches.get(str(inc["id"])):
            incidents_by_location[loc] += 1
    for loc_id, loc_shifts in shifts_by_location.items():
        by_location[loc_id] = {
            "location_name": loc_names.get(loc_id, "Unknown"),
            "shifts": len(loc_shifts),
            "incidents": incidents_by_location.get(loc_id, 0),
        }

    # Fatigue: only for incidents naming employees, and only fetch shift history
    # for exactly those employees (never the whole roster).
    named_employee_ids = sorted({
        str(emp_id) for inc in incidents for emp_id in (inc.get("involved_employee_ids") or [])
    })
    employee_windows: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    employee_days: dict[str, list[date]] = defaultdict(list)
    if named_employee_ids:
        history_start = window_start - timedelta(days=14)
        hist_rows = await conn.fetch(
            """
            SELECT a.employee_id, s.starts_at, s.ends_at
            FROM schedule_shifts s
            JOIN schedule_shift_assignments a ON a.shift_id = s.id
            WHERE s.company_id = $1 AND a.employee_id = ANY($2::uuid[])
              AND s.status <> 'cancelled' AND s.starts_at >= $3 AND s.starts_at < $4
            """,
            company_id, [UUID(e) for e in named_employee_ids], history_start, now,
        )
        for r in hist_rows:
            emp = str(r["employee_id"])
            employee_windows[emp].append((r["starts_at"], r["ends_at"]))
            employee_days[emp].append(r["starts_at"].astimezone(timezone.utc).date())

    fatigue = stats.fatigue_flags(incidents, matches, shifts_by_id, employee_windows, employee_days)

    return {
        "days": days,
        "n_incidents": len(incidents),
        "n_shifts": len(shifts),
        "unmatched_count": match_result["unmatched_count"],
        "suppressed": suppressed_reason is not None,
        "suppressed_reason": suppressed_reason,
        "by_staffing": by_staffing,
        "by_window": by_window,
        "by_location": by_location,
        "fatigue_flags": fatigue,
        "disclaimer": INCIDENT_CORRELATION_DISCLAIMER,
    }


# ── Module 2: Fair Workweek exposure ─────────────────────────────────────

async def build_fair_workweek_exposure(conn, company_id: UUID, *, days: int = 90) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)

    company = await conn.fetchrow("SELECT industry FROM companies WHERE id = $1", company_id)
    industry = company["industry"] if company else None

    loc_rows = await conn.fetch(
        "SELECT id, name, city, state FROM business_locations WHERE company_id = $1", company_id,
    )
    ordinance_by_location: dict[str, tuple[Optional[dict], str, str]] = {}
    for r in loc_rows:
        ordinance, applicability = fair_workweek.ordinance_for_location(r["state"], r["city"], industry)
        ordinance_by_location[str(r["id"])] = (ordinance, applicability, r["name"])

    change_rows = await conn.fetch(
        """
        SELECT entity_id, action, details, created_at
        FROM schedule_audit_log
        WHERE company_id = $1 AND action = ANY($2::text[]) AND created_at >= $3
        """,
        company_id, list(fair_workweek.RELEVANT_ACTIONS), window_start,
    )
    approval_rows = await conn.fetch(
        """
        SELECT entity_id, action, details, created_at
        FROM schedule_audit_log
        WHERE company_id = $1 AND action IN ('request.approved', 'request.denied')
          AND created_at >= $2
        """,
        company_id, window_start - timedelta(days=1),
    )
    approvals_by_shift: dict[str, list[datetime]] = defaultdict(list)
    for r in approval_rows:
        details = _details(r["details"])
        shift_id = details.get("shift_id")
        if shift_id:
            approvals_by_shift[str(shift_id)].append(r["created_at"])

    raw_events = []
    shift_ids_needing_assignees: set[str] = set()
    for r in change_rows:
        row = {"entity_id": r["entity_id"], "action": r["action"], "details": _details(r["details"]),
               "created_at": r["created_at"]}
        event = fair_workweek.classify_change(row, approvals_by_shift)
        if event is None:
            continue
        details = row["details"]
        if row["action"] in ("assignment.create", "assignment.delete"):
            location_id = details.get("location_id")
        else:
            location_id = (details.get("before") or {}).get("location_id")
        event["_location_id"] = location_id
        if event["affected_employee_id"] is None and event["shift_id"]:
            shift_ids_needing_assignees.add(event["shift_id"])
        raw_events.append(event)

    assignees_by_shift: dict[str, list[str]] = defaultdict(list)
    if shift_ids_needing_assignees:
        assign_rows = await conn.fetch(
            "SELECT shift_id, employee_id FROM schedule_shift_assignments WHERE shift_id = ANY($1::uuid[])",
            [UUID(sid) for sid in shift_ids_needing_assignees],
        )
        for r in assign_rows:
            assignees_by_shift[str(r["shift_id"])].append(str(r["employee_id"]))

    all_employee_ids: set[str] = set()
    for ev in raw_events:
        if ev["affected_employee_id"]:
            all_employee_ids.add(ev["affected_employee_id"])
        elif ev["shift_id"]:
            all_employee_ids.update(assignees_by_shift.get(ev["shift_id"], []))
    pay_rates: dict[str, Optional[Decimal]] = {}
    if all_employee_ids:
        rate_rows = await conn.fetch(
            "SELECT id, pay_rate FROM employees WHERE id = ANY($1::uuid[])",
            [UUID(e) for e in all_employee_ids],
        )
        pay_rates = {str(r["id"]): r["pay_rate"] for r in rate_rows}

    priced_by_location: dict[str, list[dict]] = defaultdict(list)
    skipped_no_location = 0
    for ev in raw_events:
        loc = ev.pop("_location_id")
        if not loc:
            skipped_no_location += 1
            continue
        entry = ordinance_by_location.get(str(loc))
        if not entry or entry[0] is None:
            continue  # unmapped location — reported separately below, no math attempted
        ordinance, _applicability, _name = entry
        affected = [ev["affected_employee_id"]] if ev["affected_employee_id"] else assignees_by_shift.get(ev["shift_id"], [])
        if not affected:
            priced_by_location[str(loc)].append(fair_workweek.price_event(ev, ordinance, None))
            continue
        for emp_id in affected:
            priced_by_location[str(loc)].append(
                fair_workweek.price_event(ev, ordinance, pay_rates.get(emp_id))
            )

    locations_out = []
    unmapped_locations = []
    for loc_id, (ordinance, applicability, name) in ordinance_by_location.items():
        if ordinance is None:
            unmapped_locations.append({"location_id": loc_id, "name": name})
            continue
        summary = fair_workweek.summarize_location_exposure(priced_by_location.get(loc_id, []))
        locations_out.append({
            "location_id": loc_id,
            "name": name,
            "ordinance": {
                "name": ordinance["name"], "citation": ordinance["citation"],
                "authority_url": ordinance["authority_url"],
            },
            "applicability": applicability,
            **summary,
        })

    return {
        "days": days,
        "locations": locations_out,
        "unmapped_locations": unmapped_locations,
        "skipped_no_location_events": skipped_no_location,
        "disclaimer": fair_workweek.DISCLAIMER,
    }


# ── Module 3: pretext shield ──────────────────────────────────────────────

def _week_start_sunday(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)


async def _employee_weekly_hours(conn, company_id: UUID, employee_id: UUID,
                                  start: datetime, end: datetime) -> list[float]:
    rows = await conn.fetch(
        """
        SELECT s.starts_at, s.ends_at, s.break_minutes
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id
        WHERE s.company_id = $1 AND a.employee_id = $2 AND s.status <> 'cancelled'
          AND s.starts_at >= $3 AND s.starts_at < $4
        """,
        company_id, employee_id, start, end,
    )
    by_week: dict[date, float] = defaultdict(float)
    for r in rows:
        hours = max(0.0, (r["ends_at"] - r["starts_at"]).total_seconds() / 3600.0 - (r["break_minutes"] or 0) / 60.0)
        by_week[_week_start_sunday(r["starts_at"].astimezone(timezone.utc).date())] += hours
    return list(by_week.values())


async def _employee_change_metrics(conn, company_id: UUID, employee_id: UUID,
                                    start: datetime, end: datetime) -> dict[str, Any]:
    assignment_rows = await conn.fetch(
        """
        SELECT entity_id, action, details, created_at FROM schedule_audit_log
        WHERE company_id = $1 AND action IN ('assignment.create', 'assignment.delete')
          AND created_at >= $2 AND created_at < $3
          AND details->>'employee_id' = $4
        """,
        company_id, start, end, str(employee_id),
    )
    shift_rows = await conn.fetch(
        """
        SELECT sal.entity_id, sal.action, sal.details, sal.created_at
        FROM schedule_audit_log sal
        JOIN schedule_shift_assignments a ON a.shift_id = sal.entity_id
        WHERE sal.company_id = $1 AND sal.action IN ('shift.update', 'shift.delete')
          AND sal.created_at >= $2 AND sal.created_at < $3 AND a.employee_id = $4
        """,
        company_id, start, end, employee_id,
    )
    approval_rows = await conn.fetch(
        """
        SELECT entity_id, action, details, created_at FROM schedule_audit_log
        WHERE company_id = $1 AND action IN ('request.approved', 'request.denied')
          AND created_at >= $2 AND created_at < ($3::timestamptz + interval '1 day')
        """,
        company_id, start - timedelta(days=1), end,
    )
    approvals_by_shift: dict[str, list[datetime]] = defaultdict(list)
    for r in approval_rows:
        shift_id = _details(r["details"]).get("shift_id")
        if shift_id:
            approvals_by_shift[str(shift_id)].append(r["created_at"])

    classified = [
        stats.classify_audit_row(
            {"entity_id": r["entity_id"], "action": r["action"], "details": _details(r["details"]),
             "created_at": r["created_at"]},
            approvals_by_shift,
        )
        for r in list(assignment_rows) + list(shift_rows)
    ]
    weekly_hours = await _employee_weekly_hours(conn, company_id, employee_id, start, end)
    return stats.instability_metrics(classified, weekly_hours)


async def build_pretext_shield(conn, company_id: UUID, *, months: int = _PRETEXT_LOOKBACK_MONTHS) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=months * 30)
    discipline_rows = await conn.fetch(
        """
        SELECT id, employee_id, infraction_type, issued_date
        FROM progressive_discipline
        WHERE company_id = $1 AND infraction_type = ANY($2::text[]) AND issued_date >= $3
        """,
        company_id, list(ATTENDANCE_INFRACTION_TYPES), since.date(),
    )
    discipline_records = [dict(r) for r in discipline_rows]

    metrics_by_employee: dict[str, dict[str, Any]] = {}
    for rec in discipline_records:
        emp_id = rec["employee_id"]
        issued = rec["issued_date"]
        issued_dt = datetime.combine(issued, datetime.min.time(), tzinfo=timezone.utc)
        lookback_start = issued_dt - timedelta(days=_ATTENDANCE_LOOKBACK_DAYS)
        metrics_by_employee[str(emp_id)] = await _employee_change_metrics(
            conn, company_id, emp_id, lookback_start, issued_dt,
        )

    flagged = stats.pretext_flags(
        [{**r, "issued_date": r["issued_date"].isoformat()} for r in discipline_records],
        metrics_by_employee,
    )
    return {
        "months": months,
        "records_reviewed": len(discipline_records),
        "flagged": flagged,
        "data_note": (
            "Instability metrics rely on schedule-change history logged after this "
            "feature's release — records from before that date show as low-instability "
            "by default, not because nothing changed."
        ),
        "disclaimer": PRETEXT_SHIELD_DISCLAIMER,
    }


# ── Module 4: qualified coverage ─────────────────────────────────────────

async def build_qualified_coverage(
    conn, company_id: UUID, *, credential_templates_enabled: bool, training_enabled: bool, days: int = 14,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    shift_rows = await conn.fetch(
        """
        SELECT id, starts_at, ends_at, location_id, required_staff
        FROM schedule_shifts
        WHERE company_id = $1 AND status = 'published' AND starts_at >= $2 AND starts_at < $3
        ORDER BY starts_at
        """,
        company_id, now, horizon,
    )
    shifts = [dict(r) for r in shift_rows]
    if not shifts:
        return {
            "days": days, "shifts": [],
            "sources": {"credentials": None if not credential_templates_enabled else [],
                        "training": None if not training_enabled else []},
            "disclaimer": QUALIFIED_COVERAGE_DISCLAIMER,
        }

    shift_ids = [s["id"] for s in shifts]
    assign_rows = await conn.fetch(
        "SELECT shift_id, employee_id FROM schedule_shift_assignments WHERE shift_id = ANY($1::uuid[])",
        shift_ids,
    )
    assignees_by_shift: dict[str, list[str]] = defaultdict(list)
    all_employee_ids: set[str] = set()
    for r in assign_rows:
        emp = str(r["employee_id"])
        assignees_by_shift[str(r["shift_id"])].append(emp)
        all_employee_ids.add(emp)

    lapse_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if all_employee_ids and credential_templates_enabled:
        emp_uuids = [UUID(e) for e in all_employee_ids]
        req_rows = await conn.fetch(
            """
            SELECT ecr.employee_id, ct.label AS credential_name, ecr.due_date
            FROM employee_credential_requirements ecr
            JOIN employees e ON e.id = ecr.employee_id
            LEFT JOIN credential_types ct ON ct.id = ecr.credential_type_id
            WHERE e.org_id = $1 AND ecr.employee_id = ANY($2::uuid[])
              AND ecr.status NOT IN ('verified', 'waived') AND ecr.due_date IS NOT NULL
            """,
            company_id, emp_uuids,
        )
        for r in req_rows:
            lapse_items[str(r["employee_id"])].append({
                "source": "credential_requirement", "item": r["credential_name"] or "Credential",
                "date": r["due_date"],
            })
        cred_rows = await conn.fetch(
            """
            SELECT employee_id, license_expiration, dea_expiration,
                   board_certification_expiration, malpractice_expiration
            FROM employee_credentials WHERE org_id = $1 AND employee_id = ANY($2::uuid[])
            """,
            company_id, emp_uuids,
        )
        for r in cred_rows:
            for col, label in (
                ("license_expiration", "License"), ("dea_expiration", "DEA registration"),
                ("board_certification_expiration", "Board certification"),
                ("malpractice_expiration", "Malpractice coverage"),
            ):
                if r[col]:
                    lapse_items[str(r["employee_id"])].append(
                        {"source": "credential", "item": label, "date": r[col]}
                    )

    if all_employee_ids and training_enabled:
        emp_uuids = [UUID(e) for e in all_employee_ids]
        train_rows = await conn.fetch(
            """
            SELECT employee_id, title, status, due_date, expiration_date
            FROM training_records
            WHERE company_id = $1 AND employee_id = ANY($2::uuid[]) AND requirement_id IS NOT NULL
            """,
            company_id, emp_uuids,
        )
        for r in train_rows:
            if r["status"] != "completed" and r["due_date"]:
                lapse_items[str(r["employee_id"])].append(
                    {"source": "training", "item": r["title"], "date": r["due_date"]}
                )
            if r["expiration_date"]:
                lapse_items[str(r["employee_id"])].append(
                    {"source": "training", "item": r["title"], "date": r["expiration_date"]}
                )

    shifts_out = []
    for s in shifts:
        sid = str(s["id"])
        assignee_ids = assignees_by_shift.get(sid, [])
        shift_date = s["starts_at"].astimezone(timezone.utc).date()
        lapses_for_shift = {}
        for emp in assignee_ids:
            hits = [it for it in lapse_items.get(emp, []) if it["date"] and it["date"] < shift_date]
            if hits:
                lapses_for_shift[emp] = hits
        result = stats.qualified_headcount(assignee_ids, lapses_for_shift)
        shifts_out.append({
            "shift_id": sid, "starts_at": s["starts_at"].isoformat(),
            "location_id": str(s["location_id"]) if s["location_id"] else None,
            "required_staff": s["required_staff"], **result,
            "lapses": {
                emp: [{"source": it["source"], "item": it["item"], "expired_or_due": it["date"].isoformat()}
                      for it in items]
                for emp, items in lapses_for_shift.items()
            },
        })

    return {
        "days": days,
        "shifts": shifts_out,
        "sources": {
            "credentials": [] if credential_templates_enabled else None,
            "training": [] if training_enabled else None,
        },
        "disclaimer": QUALIFIED_COVERAGE_DISCLAIMER,
    }


# ── Overview ──────────────────────────────────────────────────────────────

async def build_overview(
    conn, company_id: UUID, *, credential_templates_enabled: bool, training_enabled: bool,
) -> dict[str, Any]:
    incidents = await build_incident_correlation(conn, company_id)
    fw = await build_fair_workweek_exposure(conn, company_id)
    pretext = await build_pretext_shield(conn, company_id)
    coverage = await build_qualified_coverage(
        conn, company_id,
        credential_templates_enabled=credential_templates_enabled,
        training_enabled=training_enabled,
    )
    total_exposure = sum(
        (loc["exposure_estimate"] or 0) for loc in fw["locations"] if loc["exposure_estimate"] is not None
    )
    understaffed_lapsed = sum(1 for s in coverage["shifts"] if s["qualified"] < s["assigned"])
    return {
        "modules": {
            "incidents": {
                "suppressed": incidents["suppressed"],
                "n_incidents": incidents["n_incidents"],
                "n_shifts": incidents["n_shifts"],
                "by_staffing": incidents["by_staffing"],
            },
            "fair_workweek": {
                "total_exposure_estimate": round(total_exposure, 2) if total_exposure else None,
                "location_count": len(fw["locations"]),
                "unmapped_location_count": len(fw["unmapped_locations"]),
            },
            "pretext": {
                "records_reviewed": pretext["records_reviewed"],
                "flagged_count": len(pretext["flagged"]),
            },
            "coverage": {
                "shifts_checked": len(coverage["shifts"]),
                "shifts_with_lapses": understaffed_lapsed,
                "sources": coverage["sources"],
            },
        },
        "disclaimer": (
            "All Schedule Intelligence figures are directional estimates computed from "
            "this company's own platform data — not legal, payroll, or actuarial advice."
        ),
    }
