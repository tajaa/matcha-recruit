"""Discipline compliance gate — the legal check that runs before discipline issues.

Progressive discipline can be procedurally perfect and still illegal. The
canonical case: an employee misses a shift, the company's attendance policy is
followed to the letter, a warning issues — but the missed shift was the
employee using state-mandated paid sick leave. In California and a growing list
of states, counting that absence toward discipline is unlawful *regardless* of
whether policy was followed. No amount of process cures it.

So the gate is deterministic, not AI. A model that "usually" catches this is
worse than useless — a hallucinated all-clear on a bright-line statutory
protection is precisely the failure mode that ends in a retaliation claim. The
hard verdict comes from SQL over the company's own leave records plus a curated
statute table; the AI (`discipline_ai.py`) only drafts letter prose and raises
*advisory* soft risks on top of what this module already decided.

Two invariants, both load-bearing:

1. **Unmapped state ⇒ advisory, never "clear".** `_STATE_SICK_LEAVE_PROTECTIONS`
   is deliberately partial. A state's absence from it means "we have not
   researched this jurisdiction", NOT "this state permits the discipline". An
   overlap in an unmapped state surfaces as an advisory telling HR to check —
   it never silently passes. Add rows only with a real, verified citation; never
   by inference from a neighboring state.

2. **Blocks are not overridable.** An advisory is a judgment call and HR may
   proceed with a logged reason. A block is a statutory prohibition — there is
   no business justification field for "discipline them anyway." The route
   refuses the write (422). If a block is wrong, the fix is correcting the leave
   record or the statute table, not bypassing the gate.

⚠️ The citations below are researched, not attorney-reviewed. They must be
verified by counsel before this ships to a paying tenant. Getting a citation
wrong in the *blocking* direction is the safer failure (a spurious block is
visible and annoying; a spurious all-clear is invisible and expensive), but
neither is acceptable in production.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


# ── Curated statute table ────────────────────────────────────────────────
#
# Keyed on the employee's `work_state`. Each row cites the provision that makes
# disciplining an employee for protected sick-leave use unlawful. Most of these
# states go further than a general anti-retaliation rule and explicitly bar
# *counting the leave as an absence* under a no-fault attendance policy — which
# is exactly what progressive discipline does — so the block fires on the
# attendance path even where the employer had no retaliatory intent.
#
# To add a state: read the statute, quote the operative prohibition in `note`,
# cite it precisely. Do not extrapolate from a neighboring state's law.

_STATE_SICK_LEAVE_PROTECTIONS: dict[str, dict[str, str]] = {
    "CA": {
        "statute": "Cal. Lab. Code § 246.5(c)",
        "protection": "paid_sick_leave_retaliation",
        "note": (
            "An employer may not deny an employee the right to use accrued sick days, "
            "or discharge, threaten to discharge, demote, suspend, or in any manner "
            "discriminate against an employee for using accrued sick days."
        ),
    },
    "AZ": {
        "statute": "A.R.S. § 23-374(B)",
        "protection": "earned_paid_sick_time_no_fault_attendance",
        "note": (
            "An employer may not count earned paid sick time taken as an absence that "
            "may lead to or result in discipline, discharge, demotion, suspension or "
            "any other adverse action."
        ),
    },
    "WA": {
        "statute": "RCW 49.46.210(2)",
        "protection": "paid_sick_leave_no_fault_attendance",
        "note": (
            "An employer may not adopt or enforce any policy that counts the use of "
            "paid sick leave as an absence that may lead to or result in discipline."
        ),
    },
    "OR": {
        "statute": "ORS 653.641",
        "protection": "sick_time_retaliation",
        "note": (
            "Unlawful practice for an employer to deny, interfere with, restrain, or "
            "retaliate or discriminate against an employee with respect to discipline "
            "because the employee inquired about, submitted a request for, or used "
            "sick time."
        ),
    },
    "CO": {
        "statute": "C.R.S. § 8-13.3-407",
        "protection": "hfwa_retaliation",
        "note": (
            "Healthy Families and Workplaces Act — an employer may not retaliate or "
            "take adverse action against an employee for using paid sick leave, "
            "including counting the leave under an absence-control policy."
        ),
    },
    "NJ": {
        "statute": "N.J. Stat. § 34:11D-4",
        "protection": "earned_sick_leave_retaliation",
        "note": (
            "No employer shall take retaliatory personnel action or discriminate "
            "against an employee because the employee requests or uses earned sick "
            "leave."
        ),
    },
    "NY": {
        "statute": "N.Y. Lab. Law § 196-b(6)",
        "protection": "paid_sick_leave_retaliation",
        "note": (
            "No employer shall discharge, threaten, penalize, or in any other manner "
            "discriminate or retaliate against an employee for exercising sick-leave "
            "rights under this section."
        ),
    },
    "MA": {
        "statute": "Mass. Gen. Laws ch. 149, § 148C",
        "protection": "earned_sick_time_retaliation",
        "note": (
            "Unlawful for an employer to interfere with, restrain, or deny the "
            "exercise of earned sick time rights, including counting earned sick time "
            "under an absence-control policy."
        ),
    },
}


# ── Which records count as protected ────────────────────────────────────
#
# v1 bright line = *medical / sick* leave. `parental` and `unpaid_loa` are
# deliberately excluded: FMLA-adjacent parental leave carries its own (federal)
# protections that deserve their own analysis rather than being folded into the
# sick-leave statute table, and `unpaid_loa` is a catch-all whose protection
# depends entirely on why it was granted. Widening this tuple without widening
# the statute reasoning would produce blocks the citations don't support.

PROTECTED_LEAVE_TYPES = ("fmla", "state_pfml", "medical")
PROTECTED_LEAVE_STATUSES = ("approved", "active", "completed")

SICK_PTO_TYPES = ("sick",)
SICK_PTO_STATUSES = ("approved",)

# The infraction the bright-line rule actually bites on. Disciplining for
# *conduct* that happened to occur on a leave day (e.g. harassment) is a
# different question from counting the absence itself — so non-attendance
# infractions that overlap leave get an advisory, not a block.
ATTENDANCE_INFRACTION_TYPES = ("attendance",)

# Protected-activity lookback for the retaliation-timing advisory.
RETALIATION_WINDOW_DAYS = 90

# How far back we pull leave/PTO history when testing overlap.
_LEAVE_HISTORY_MONTHS = 24

VERDICT_VERSION = 1


# ── Pure helpers ────────────────────────────────────────────────────────

def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _normalize_state(value: Any) -> Optional[str]:
    if not value:
        return None
    s = str(value).strip().upper()
    return s if len(s) == 2 else None


def statute_for_state(work_state: Any) -> Optional[dict[str, str]]:
    """Curated statute row for a state, or None if the state is unmapped."""
    st = _normalize_state(work_state)
    if not st:
        return None
    row = _STATE_SICK_LEAVE_PROTECTIONS.get(st)
    return {**row, "state": st} if row else None


def overlap_hits(
    occurrence_dates: list[date],
    leave_rows: list[dict[str, Any]],
    pto_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Dates being disciplined that fall inside a protected leave/sick-PTO window.

    Pure. `leave_rows` / `pto_rows` are already filtered to protected types and
    approved-ish statuses by the caller's SQL; this only does the date math. An
    open-ended leave (`end_date IS NULL`) is treated as a single day, not as
    running forever — an unbounded window would let a stale open row block every
    future discipline.
    """
    days = sorted({d for d in (_as_date(d) for d in occurrence_dates or []) if d})
    if not days:
        return []

    hits: list[dict[str, Any]] = []
    for source, rows, type_key in (
        ("leave_request", leave_rows or [], "leave_type"),
        ("pto_request", pto_rows or [], "request_type"),
    ):
        for row in rows:
            start = _as_date(row.get("start_date"))
            if not start:
                continue
            end = _as_date(row.get("end_date")) or start
            matched = [d for d in days if start <= d <= end]
            if not matched:
                continue
            hits.append({
                "source": source,
                "record_id": str(row.get("id")),
                "leave_type": row.get(type_key),
                "status": row.get("status"),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "dates": [d.isoformat() for d in matched],
            })
    return hits


def retaliation_hits(
    occurrence_dates: list[date],
    report_events: list[dict[str, Any]],
    window_days: int = RETALIATION_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Protected activity by this employee shortly *before* the conduct at issue.

    Not a legal verdict — close timing between an employee's complaint and
    discipline is what a plaintiff's lawyer builds a retaliation claim from, so
    HR should see it and document a legitimate basis. Events *after* the conduct
    don't count: they can't have motivated discipline for something that already
    happened.
    """
    days = sorted({d for d in (_as_date(d) for d in occurrence_dates or []) if d})
    if not days:
        return []
    earliest = days[0]
    window_start = earliest - timedelta(days=window_days)

    hits = []
    for ev in report_events or []:
        ev_date = _as_date(ev.get("event_date"))
        if not ev_date:
            continue
        if window_start <= ev_date <= earliest:
            hits.append({
                "source": ev.get("source"),
                "record_id": str(ev.get("id")) if ev.get("id") else None,
                "event_date": ev_date.isoformat(),
                "label": ev.get("label"),
                "days_before": (earliest - ev_date).days,
            })
    return sorted(hits, key=lambda h: h["days_before"])


def build_verdict(
    *,
    infraction_type: str,
    work_state: Any,
    overlaps: list[dict[str, Any]],
    retaliation: list[dict[str, Any]],
    ai_advisories: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Turn raw findings into blocks + advisories. Pure — the whole legal rule.

    Blocks fire only where all three hold: the infraction is attendance (we are
    disciplining the absence *as* an absence), a protected leave day overlaps,
    and the state has a verified statute barring it. Loosen any one of those and
    the block is no longer something we can cite a law for — so it degrades to
    an advisory instead.
    """
    state_row = statute_for_state(work_state)
    is_attendance = infraction_type in ATTENDANCE_INFRACTION_TYPES

    blocks: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []

    for hit in overlaps or []:
        if is_attendance and state_row:
            blocks.append({
                "code": "protected_leave_overlap",
                "statute": state_row["statute"],
                "state": state_row["state"],
                "detail": (
                    f"The absence on {', '.join(hit['dates'])} is protected leave "
                    f"({hit['leave_type']}). Disciplining for it is barred by "
                    f"{state_row['statute']}: {state_row['note']}"
                ),
                "source": hit["source"],
                "record_id": hit["record_id"],
                "dates": hit["dates"],
            })
        elif is_attendance and not state_row:
            # Unmapped state: we don't know that it's legal, so we don't say it is.
            advisories.append({
                "code": "leave_overlap_unmapped_state",
                "detail": (
                    f"The absence on {', '.join(hit['dates'])} overlaps protected leave "
                    f"({hit['leave_type']}), but this employee's work state is not in "
                    "our verified statute table. Most states bar counting protected "
                    "sick leave toward attendance discipline — confirm with counsel "
                    "before proceeding."
                ),
                "source": hit["source"],
                "record_id": hit["record_id"],
                "dates": hit["dates"],
            })
        else:
            # Non-attendance conduct that merely happened on a leave day.
            advisories.append({
                "code": "leave_overlap_non_attendance",
                "detail": (
                    f"This {infraction_type.replace('_', ' ')} infraction falls on a day "
                    f"the employee was on protected leave ({hit['leave_type']}, "
                    f"{', '.join(hit['dates'])}). Disciplining the conduct may be lawful, "
                    "but document that the basis is the conduct and not the absence."
                ),
                "source": hit["source"],
                "record_id": hit["record_id"],
                "dates": hit["dates"],
            })

    for hit in retaliation or []:
        advisories.append({
            "code": "retaliation_timing",
            "detail": (
                f"This employee engaged in protected activity {hit['days_before']} days "
                f"before the conduct at issue ({hit['label']}, {hit['event_date']}). "
                "Close timing invites a retaliation claim — document the independent, "
                "documented basis for this discipline."
            ),
            "source": hit["source"],
            "record_id": hit["record_id"],
        })

    if not state_row:
        advisories.append({
            "code": "unmapped_state",
            "detail": (
                f"Work state {_normalize_state(work_state) or 'unknown'} is not in the "
                "verified sick-leave statute table, so state-specific protections were "
                "not checked. This is not an all-clear."
            ),
        })

    for adv in ai_advisories or []:
        advisories.append(adv)

    return {
        "version": VERDICT_VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "work_state": _normalize_state(work_state),
        "state_row": state_row,
        "blocks": blocks,
        "advisories": advisories,
    }


# ── DB-touching orchestrator ────────────────────────────────────────────

async def _fetch_protected_leave(
    conn, employee_id: UUID, company_id: UUID
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, leave_type, start_date, end_date, status
        FROM leave_requests
        WHERE employee_id = $1
          AND org_id = $2
          AND leave_type = ANY($3::text[])
          AND status = ANY($4::text[])
          AND start_date >= (CURRENT_DATE - make_interval(months => $5::int))
        """,
        employee_id, company_id,
        list(PROTECTED_LEAVE_TYPES), list(PROTECTED_LEAVE_STATUSES),
        _LEAVE_HISTORY_MONTHS,
    )
    return [dict(r) for r in rows]


async def _fetch_sick_pto(
    conn, employee_id: UUID, company_id: UUID
) -> list[dict[str, Any]]:
    # pto_requests has no org_id — tenant scope comes from the employees join.
    rows = await conn.fetch(
        """
        SELECT p.id, p.request_type, p.start_date, p.end_date, p.status
        FROM pto_requests p
        JOIN employees e ON e.id = p.employee_id
        WHERE p.employee_id = $1
          AND e.org_id = $2
          AND p.request_type = ANY($3::text[])
          AND p.status = ANY($4::text[])
          AND p.start_date >= (CURRENT_DATE - make_interval(months => $5::int))
        """,
        employee_id, company_id,
        list(SICK_PTO_TYPES), list(SICK_PTO_STATUSES),
        _LEAVE_HISTORY_MONTHS,
    )
    return [dict(r) for r in rows]


async def _fetch_protected_activity(
    conn, employee_id: UUID, company_id: UUID, employee_email: Optional[str]
) -> list[dict[str, Any]]:
    """Reports this employee filed / cases they're party to — the retaliation signal.

    Best-effort: a missing table or a schema drift here must not take down the
    legal gate, whose blocking half doesn't depend on it.
    """
    events: list[dict[str, Any]] = []

    try:
        rows = await conn.fetch(
            """
            SELECT id, incident_type, occurred_at, created_at
            FROM ir_incidents
            WHERE company_id = $1
              AND ($2::text IS NOT NULL AND LOWER(reported_by_email) = LOWER($2::text))
            ORDER BY created_at DESC
            LIMIT 25
            """,
            company_id, employee_email,
        )
        for r in rows:
            events.append({
                "source": "ir_incident",
                "id": r["id"],
                "event_date": r["created_at"],
                "label": f"filed a {r['incident_type'] or 'safety'} incident report",
            })
    except Exception:
        logger.exception("[discipline_compliance] IR protected-activity lookup failed")

    try:
        rows = await conn.fetch(
            """
            SELECT id, title, category, created_at
            FROM er_cases
            WHERE company_id = $1
              AND involved_employees @> $2::jsonb
            ORDER BY created_at DESC
            LIMIT 25
            """,
            company_id,
            f'[{{"employee_id": "{employee_id}"}}]',
        )
        for r in rows:
            events.append({
                "source": "er_case",
                "id": r["id"],
                "event_date": r["created_at"],
                "label": f"party to an ER case ({r['category'] or 'investigation'})",
            })
    except Exception:
        logger.exception("[discipline_compliance] ER protected-activity lookup failed")

    return events


async def check_discipline_compliance(
    conn,
    *,
    company_id: UUID,
    employee_id: UUID,
    infraction_type: str,
    occurrence_dates: list[date],
    ai_advisories: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Run the full gate for one prospective discipline action.

    Returns the verdict dict (see `build_verdict`). Callers treat a non-empty
    `blocks` as a refusal; `advisories` require acknowledgement.
    """
    emp = await conn.fetchrow(
        "SELECT id, work_state, email FROM employees WHERE id = $1 AND org_id = $2",
        employee_id, company_id,
    )
    work_state = emp["work_state"] if emp else None
    employee_email = emp["email"] if emp else None

    leave_rows = await _fetch_protected_leave(conn, employee_id, company_id)
    pto_rows = await _fetch_sick_pto(conn, employee_id, company_id)
    events = await _fetch_protected_activity(conn, employee_id, company_id, employee_email)

    return build_verdict(
        infraction_type=infraction_type,
        work_state=work_state,
        overlaps=overlap_hits(occurrence_dates, leave_rows, pto_rows),
        retaliation=retaliation_hits(occurrence_dates, events),
        ai_advisories=ai_advisories,
    )
