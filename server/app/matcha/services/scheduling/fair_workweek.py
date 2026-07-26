"""Fair Workweek / predictive-scheduling exposure estimate.

Roughly a dozen US jurisdictions require advance shift notice and pay a
premium ("predictability pay") when an employer changes a posted schedule on
short notice, plus a separate premium for "clopening" (a closing shift
followed too soon by an opening shift). This module estimates what a tenant's
*actual* schedule-change history would have cost under whichever of those
ordinances applies to its locations — using the enriched `schedule_audit_log`
rows from Phase 1 (before/after shift state, `was_published`, and whether a
change was employee- or employer-initiated) and each employee's `pay_rate`.

Same two-part split as `discipline_compliance.py` / `schedule_compliance.py`:

1. A curated, individually-cited ordinance table (`_FAIR_WORKWEEK_ORDINANCES`).
   Deliberately partial — **only NYC and Los Angeles are populated**, because
   those are the two jurisdictions this repo has already verified (the
   `compliance_evals` golden fixtures). The other ~8 US Fair Workweek cities
   (Chicago, San Francisco, Seattle, Oregon, Philadelphia, Berkeley,
   Emeryville, Evanston) are real ordinances but their exact notice windows,
   premium schedules, and industry/size scoping have NOT been verified here —
   adding them requires the same real-citation research as any other statute
   table in this codebase. A location outside the curated table is reported as
   `applicability: "unmapped"`, never treated as exempt.

2. A pure engine (`classify_event`, `predictability_pay_estimate`,
   `summarize_location_exposure`) that turns audit-log rows into dollar
   estimates.

Invariants (same as every curated statute table in this codebase):

- Unmapped jurisdiction ⇒ `applicability: "unmapped"`, never "no exposure".
- Industry-scoped ordinance + no/unknown company industry match ⇒
  `applicability: "review_industry"`, never silently covered or exempt.
- Employee-initiated churn (a schedule request the employee filed and an
  admin approved) is EXEMPT under every one of these ordinances and is
  excluded before any dollar math runs.
- A shift whose change predates the Phase 1 audit enrichment, or whose
  employee has no `pay_rate` on file, degrades to a COUNT-only line item
  (`estimate: null`) — it is never silently dropped or zero-priced.
- This is an ESTIMATE for risk-awareness, not a payroll or legal calculation.
  Every payload carries `DISCLAIMER`.

⚠️ Citations below are researched, not attorney-reviewed. Verify with counsel
before this ships to a paying tenant (same posture as every other curated
statute table in this codebase).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from .schedule_intelligence_stats import classify_audit_row

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Directional estimate of Fair Workweek / predictive-scheduling exposure, "
    "computed from this company's own schedule-change history. Not a payroll "
    "calculation or legal advice — ordinance scoping (employer size, covered "
    "job classes) is not fully verifiable from platform data. Verify with "
    "counsel before relying on this for compliance or budgeting."
)

# Actions that represent a change to a POSTED shift's timing or staffing —
# the universe of events that can trigger predictability pay. Anything else in
# schedule_audit_log (publish, template ops, compliance overrides) is not a
# schedule *change* in the Fair Workweek sense.
RELEVANT_ACTIONS = ("shift.update", "shift.delete", "assignment.create", "assignment.delete")


# ── Curated ordinance table ──────────────────────────────────────────────
#
# Keyed on (state, city_slug). city_slug=None would mean a statewide ordinance
# (none curated yet — Oregon's statewide Fair Workweek Act is real but not yet
# verified here, so it is NOT in this table; see module docstring).
#
# `predictability_pay` brackets are checked in order; the first bracket whose
# `kinds` contains the event's kind and whose notice-day range contains the
# change's notice window wins. `unit` is either:
#   "flat"          — `amount` is a dollar figure, independent of pay rate.
#   "hours_at_rate" — `amount` is a number of hours (times `rate_multiplier`,
#                     default 1.0) of the employee's own `pay_rate`; None
#                     pay_rate ⇒ the event is counted but not priced.
# `industries`: None = ordinance applies regardless of company industry;
# otherwise a list of lowercase substrings matched against `companies.industry`.
_FAIR_WORKWEEK_ORDINANCES: dict[tuple[str, str], dict[str, Any]] = {
    ("NY", "new-york-city"): {
        "name": "NYC Fair Workweek Law",
        "citation": "N.Y.C. Admin. Code § 20-1201 et seq.",
        "authority_url": "https://www.nyc.gov/site/dca/about/fairworkweek-deductions-laws.page",
        "notice_days": 14,
        "industries": ["fast food", "retail"],
        "predictability_pay": [
            {"gte_days": 7, "lt_days": 14, "kinds": ("time_change", "added_hours"), "unit": "flat", "amount": 10.0},
            {"gte_days": 1, "lt_days": 7, "kinds": ("time_change", "added_hours"), "unit": "flat", "amount": 15.0},
            {"gte_days": 0, "lt_days": 1, "kinds": ("time_change", "added_hours"), "unit": "flat", "amount": 20.0},
            {"gte_days": 7, "lt_days": 14, "kinds": ("reduced_hours", "cancellation"), "unit": "flat", "amount": 20.0},
            {"gte_days": 1, "lt_days": 7, "kinds": ("reduced_hours", "cancellation"), "unit": "flat", "amount": 45.0},
            {"gte_days": 0, "lt_days": 1, "kinds": ("reduced_hours", "cancellation"), "unit": "flat", "amount": 75.0},
        ],
        "clopening": {"rest_hours": 11, "premium": {"unit": "flat", "amount": 100.0}},
        "notes": (
            "14-day advance schedule; clopening = shifts under 11h apart, $100 flat "
            "premium; schedule-change premiums $10-$75 tiered by notice + change type. "
            "Covers fast food and retail employers."
        ),
    },
    ("CA", "los-angeles"): {
        "name": "LA City Fair Work Week Ordinance",
        "citation": "L.A. Municipal Code ch. XVIII, art. 8 (Ord. No. 187482)",
        "authority_url": "https://wagesla.lacity.gov/fair-work-week-information",
        "notice_days": 14,
        "industries": ["retail"],
        "employer_size_note": (
            "Ordinance applies to retail employers with 300+ employees GLOBALLY — "
            "not derivable from this tenant's own headcount data. Applicability below "
            "is not adjusted for this; treat as 'review' if the company is not known "
            "to meet the threshold."
        ),
        "predictability_pay": [
            # LA's ordinance pays predictability pay for changes made after the
            # 14-day posting without the same fine-grained notice/day tiering NYC
            # uses; modeled as a single flat premium per changed-shift event.
            {"gte_days": 0, "lt_days": 14, "kinds": ("time_change", "added_hours", "reduced_hours", "cancellation"),
             "unit": "hours_at_rate", "amount": 1.0, "rate_multiplier": 1.0},
        ],
        "clopening": {"rest_hours": 10, "premium": {"unit": "hours_at_rate", "amount": 1.0, "rate_multiplier": 1.0}},
        "notes": "14-day advance schedule; 10-hour rest between shifts; retail only.",
    },
}


def _slugify_city(city: Optional[str]) -> Optional[str]:
    if not city:
        return None
    return city.strip().lower().replace(" ", "-")


def ordinance_for_location(
    state: Optional[str], city: Optional[str], company_industry: Optional[str]
) -> tuple[Optional[dict[str, Any]], str]:
    """(ordinance, applicability). applicability is one of:
    "covered" | "review_industry" (ordinance found, industry scoping unclear/
    non-match) | "unmapped" (no curated ordinance for this location — NOT the
    same as "no exposure")."""
    st = (state or "").strip().upper()
    slug = _slugify_city(city)
    if not st or not slug:
        return None, "unmapped"
    ordinance = _FAIR_WORKWEEK_ORDINANCES.get((st, slug))
    if not ordinance:
        return None, "unmapped"
    industries = ordinance.get("industries")
    if industries is None:
        return ordinance, "covered"
    industry = (company_industry or "").strip().lower()
    if industry and any(tag in industry for tag in industries):
        return ordinance, "covered"
    return ordinance, "review_industry"


# ── Pure event classification + pricing ──────────────────────────────────

def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _duration_seconds(starts_at: Optional[datetime], ends_at: Optional[datetime]) -> Optional[float]:
    if not starts_at or not ends_at:
        return None
    return (ends_at - starts_at).total_seconds()


def classify_change(
    row: dict[str, Any], approvals_by_shift: dict[str, list[datetime]]
) -> Optional[dict[str, Any]]:
    """One audit row -> a Fair Workweek event dict, or None if the row isn't a
    priceable schedule change (e.g. an unpublished-shift edit, or a shift.update
    that only touched role/notes with no timing/status change).

    Reuses `schedule_intelligence_stats.classify_audit_row` for the
    employee-initiated + notice-hours determination shared with the
    instability engine, then layers on FW-specific "kind" and
    was-this-shift-published detection.
    """
    action = row["action"]
    if action not in RELEVANT_ACTIONS:
        return None
    details = row.get("details") or {}
    base = classify_audit_row(row, approvals_by_shift)
    if base["employee_initiated"]:
        return None

    kind: Optional[str] = None
    was_published = False
    affected_employee_id: Optional[str] = details.get("employee_id")

    if action == "assignment.create":
        was_published = details.get("shift_status") == "published"
        kind = "added_hours"
    elif action == "assignment.delete":
        was_published = details.get("shift_status") == "published"
        kind = "reduced_hours"
    elif action in ("shift.update", "shift.delete"):
        was_published = bool(details.get("was_published"))
        before = details.get("before") or {}
        after = details.get("after") or {}
        if action == "shift.delete":
            kind = "cancellation"
        else:
            before_dur = _duration_seconds(_parse_iso(before.get("starts_at")), _parse_iso(before.get("ends_at")))
            after_dur = _duration_seconds(_parse_iso(after.get("starts_at")), _parse_iso(after.get("ends_at")))
            if after.get("status") == "cancelled":
                kind = "cancellation"
            elif before_dur is not None and after_dur is not None and after_dur > before_dur:
                kind = "added_hours"
            elif before_dur is not None and after_dur is not None and after_dur < before_dur:
                kind = "reduced_hours"
            elif before.get("starts_at") != after.get("starts_at"):
                kind = "time_change"
        affected_employee_id = None  # resolved by the caller from current assignees

    if not was_published or kind is None:
        return None

    return {
        "action": action,
        "shift_id": base["shift_id"],
        "kind": kind,
        "notice_hours": base["notice_hours"],
        "costable": base["costable"],
        "affected_employee_id": affected_employee_id,
        "created_at": row["created_at"],
    }


def predictability_pay_estimate(
    bracket: dict[str, Any], pay_rate: Optional[Decimal]
) -> Optional[Decimal]:
    """Dollar estimate for one event under one matched bracket, or None when
    the bracket needs a pay rate the employee doesn't have on file."""
    if bracket["unit"] == "flat":
        return Decimal(str(bracket["amount"]))
    if bracket["unit"] == "hours_at_rate":
        if pay_rate is None:
            return None
        mult = Decimal(str(bracket.get("rate_multiplier", 1.0)))
        return (Decimal(str(bracket["amount"])) * mult * pay_rate).quantize(Decimal("0.01"))
    return None


def _matching_bracket(
    ordinance: dict[str, Any], kind: str, notice_days: Optional[float]
) -> Optional[dict[str, Any]]:
    if notice_days is None:
        return None
    for bracket in ordinance.get("predictability_pay", []):
        if kind in bracket["kinds"] and bracket["gte_days"] <= notice_days < bracket["lt_days"]:
            return bracket
    return None


def price_event(
    event: dict[str, Any], ordinance: dict[str, Any], pay_rate: Optional[Decimal]
) -> dict[str, Any]:
    """Attach a bracket + dollar estimate (or the reason it's count-only) to
    one classified event."""
    notice_days = event["notice_hours"] / 24.0 if event["notice_hours"] is not None else None
    bracket = _matching_bracket(ordinance, event["kind"], notice_days)
    estimate: Optional[Decimal] = None
    if not event["costable"]:
        reason = "uncostable_legacy"
    elif bracket is None:
        reason = "no_matching_bracket"
    else:
        estimate = predictability_pay_estimate(bracket, pay_rate)
        reason = None if estimate is not None else "no_pay_rate_on_file"
    return {**event, "notice_days": round(notice_days, 1) if notice_days is not None else None,
            "estimate": float(estimate) if estimate is not None else None, "uncostable_reason": reason}


# event → the classify_change `kind` vocabulary the brackets are keyed on.
_EVENT_TO_KIND = {
    "retime": "time_change",
    "cancel": "cancellation",
    "assign": "added_hours",
    "unassign": "reduced_hours",
}
# Only these events can create a NEW clopening — removing an assignment can't.
_CLOPENING_EVENTS = ("assign", "retime")


def preventive_advisories(
    *,
    ordinance: dict[str, Any],
    applicability: str,
    event: str,
    shift_published: bool,
    starts_at: datetime,
    now: datetime,
    min_rest_gap_hours: Optional[float],
    state: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Write-time advisories for a schedule change that may trigger Fair
    Workweek obligations — the preventive twin of the retrospective exposure
    engine above. Returns the same violation shape
    `schedule_compliance.py`'s checks use (`check`/`severity`/`message`/
    `statute`/`state`), so the existing 409-advisory / force-through machinery
    on the write path renders these unmodified.

    Deliberately NEVER a block — `severity` is always `"advisory"`. Skips
    entirely for a draft shift (`shift_published=False`): Fair Workweek
    obligations attach to a POSTED schedule, and a draft hasn't been posted
    yet.

    v1 fetches no employee pay_rate on this path (unlike the retrospective
    engine, which has one already loaded per assignee) — a flat-dollar bracket
    (NYC) still prices exactly; an `hours_at_rate` bracket (LA) renders
    count-only wording rather than adding a query to every shift write. The
    retrospective /schedule-intelligence report is where the precise dollar
    figure lives.
    """
    if not shift_published:
        return []

    out: list[dict[str, Any]] = []
    prefix = ""
    if applicability == "review_industry":
        prefix = f"This location may be covered by {ordinance['name']} (verify your industry) — "

    kind = _EVENT_TO_KIND.get(event)
    if kind is not None:
        notice_days = max(0.0, (starts_at - now).total_seconds() / 86400.0)
        if notice_days < ordinance["notice_days"]:
            bracket = _matching_bracket(ordinance, kind, notice_days)
            if bracket is not None:
                estimate = predictability_pay_estimate(bracket, None)
                cost_clause = (
                    f"may trigger ~${estimate:,.2f} in predictability pay"
                    if estimate is not None
                    else "may trigger predictability pay (amount depends on the employee's pay rate)"
                )
                out.append({
                    "check": "fair_workweek_notice", "severity": "advisory",
                    "message": (
                        f"{prefix}This change is inside {ordinance['name']}'s "
                        f"{ordinance['notice_days']}-day notice window ({notice_days:.1f} days' notice) — "
                        f"{cost_clause}."
                    ),
                    "statute": ordinance["citation"], "state": state,
                })

    clopening = ordinance.get("clopening")
    if (
        clopening
        and event in _CLOPENING_EVENTS
        and min_rest_gap_hours is not None
        and min_rest_gap_hours < clopening["rest_hours"]
    ):
        estimate = predictability_pay_estimate(clopening["premium"], None)
        cost_clause = (
            f"may trigger a ~${estimate:,.2f} clopening premium"
            if estimate is not None
            else "may trigger a clopening premium (amount depends on the employee's pay rate)"
        )
        out.append({
            "check": "fair_workweek_clopening", "severity": "advisory",
            "message": (
                f"{prefix}Only {min_rest_gap_hours:.1f}h rest before/after this shift — "
                f"{ordinance['name']} requires {clopening['rest_hours']}h between shifts ('clopening') — "
                f"{cost_clause}."
            ),
            "statute": ordinance["citation"], "state": state,
        })

    return out


def summarize_location_exposure(priced_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up a location's priced events into a total + breakdown. Events with
    no dollar estimate still count toward `event_count`, in their own bucket."""
    total = Decimal("0")
    costed = 0
    uncostable = 0
    for ev in priced_events:
        if ev["estimate"] is not None:
            total += Decimal(str(ev["estimate"]))
            costed += 1
        else:
            uncostable += 1
    return {
        "event_count": len(priced_events),
        "costed_event_count": costed,
        "uncostable_event_count": uncostable,
        "exposure_estimate": float(total) if costed else None,
        "events": priced_events,
    }
