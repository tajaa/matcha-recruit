"""Broad-stroke federal + California compliance calendar baselines.

These are the headline annual deadlines every employer in CA / federal
jurisdiction is expected to know — W-2, OSHA 300A posting, EEO-1, ACA
filings, 401(k) Form 5500, CA quarterly DE 9, DFEH pay data reporting,
etc. They render in the compliance calendar without requiring the
deeper jurisdiction-research pipeline to run first.

Design choices:
- Pure function — no DB writes, no new tables. The calendar route calls
  this each request and merges results with alert-backed items.
- Synthetic ids `baseline:<scope>:<slug>:<year>`. Frontend hides the
  dismiss / mark-read buttons for these (they aren't persisted).
- Headcount-gated. Pass `employee_count`; rules with thresholds (11+,
  20+, 50+, 100+) self-filter.
- Annual rollover: each rule has a fixed (month, day). If this year's
  date is in the past beyond the keep-recent window, roll to next year.
- Scope: emit no more than ~14 months of look-ahead so the calendar
  doesn't fill with year-out items. User asked for broad strokes, not
  exhaustive multi-year planning.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from ..models.compliance import CalendarItem


# Keep recently-passed deadlines visible for a couple weeks so the UI
# still shows e.g. an "overdue" Form 300A right after Feb 1. Beyond
# that, roll to next year.
_RECENT_WINDOW_DAYS = 14
# Don't surface items more than ~14 months out — broad-strokes calendar
# is for near-term planning, not multi-year roadmaps.
_LOOKAHEAD_DAYS = 14 * 30


def _bucket(days_until_due: int) -> str:
    if days_until_due < 0:
        return "overdue"
    if days_until_due <= 30:
        return "due_soon"
    if days_until_due <= 90:
        return "upcoming"
    return "future"


def _resolve_date(today: date, month: int, day: int) -> date:
    """Pick this year's occurrence of (month, day) unless it's stale.

    "Stale" = more than _RECENT_WINDOW_DAYS in the past. Rolls forward
    to next year so each fixed deadline always has exactly one upcoming
    or recently-passed instance in the feed.
    """
    candidate = date(today.year, month, day)
    if (today - candidate).days > _RECENT_WINDOW_DAYS:
        candidate = date(today.year + 1, month, day)
    return candidate


def _second_wednesday(year: int, month: int) -> date:
    """California Pay Data Reporting deadline is the second Wednesday of May."""
    d = date(year, month, 1)
    # Mon=0 .. Sun=6, Wed=2
    first_wed = d + timedelta(days=(2 - d.weekday()) % 7)
    return first_wed + timedelta(days=7)


def _resolve_second_wed_may(today: date) -> date:
    candidate = _second_wednesday(today.year, 5)
    if (today - candidate).days > _RECENT_WINDOW_DAYS:
        candidate = _second_wednesday(today.year + 1, 5)
    return candidate


def _make(
    *,
    slug: str,
    scope: str,  # "fed" or "ca"
    title: str,
    category: str,
    severity: str,
    deadline: date,
    today: date,
    action: str,
    jurisdiction_name: str,
    location_state: Optional[str] = None,
) -> CalendarItem:
    days_until_due = (deadline - today).days
    return CalendarItem(
        id=f"baseline:{scope}:{slug}:{deadline.year}",
        location_id=None,
        location_name=None,
        location_state=location_state,
        jurisdiction_name=jurisdiction_name,
        requirement_id=None,
        title=title,
        category=category,
        severity=severity,
        deadline=deadline.isoformat(),
        derived_status=_bucket(days_until_due),
        days_until_due=days_until_due,
        action_required=action,
        alert_status="baseline",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def get_baseline_calendar_items(
    *,
    today: date,
    employee_count: int,
    has_ca_location: bool,
    has_ny_location: bool = False,
) -> list[CalendarItem]:
    """Compute the broad-strokes baseline calendar feed.

    Returns federal items always; CA / NY items only when the company has
    at least one location in that state. Rules with headcount thresholds
    self-filter: a 5-employee tenant sees W-2 / 1099 / IIPP but not
    OSHA 300A or EEO-1.
    """
    out: list[CalendarItem] = []

    # ── Federal — universal (every employer)
    out.append(_make(
        slug="w2-to-employees", scope="fed", today=today,
        title="W-2 forms to employees",
        category="payroll_tax",
        severity="high",
        deadline=_resolve_date(today, 1, 31),
        action="Distribute Form W-2 to every employee paid in the prior calendar year.",
        jurisdiction_name="Federal",
    ))
    out.append(_make(
        slug="1099-nec-to-contractors", scope="fed", today=today,
        title="1099-NEC to contractors",
        category="payroll_tax",
        severity="high",
        deadline=_resolve_date(today, 1, 31),
        action="Issue Form 1099-NEC to any contractor paid $600+ in the prior year.",
        jurisdiction_name="Federal",
    ))
    out.append(_make(
        slug="w2-w3-ssa", scope="fed", today=today,
        title="W-2 / W-3 filing with SSA",
        category="payroll_tax",
        severity="high",
        deadline=_resolve_date(today, 1, 31),
        action="Transmit Forms W-2 (with W-3 summary) to the Social Security Administration.",
        jurisdiction_name="Federal",
    ))

    # ── Federal — OSHA Form 300A (11+ employees, most industries)
    if employee_count >= 11:
        out.append(_make(
            slug="osha-300a-post", scope="fed", today=today,
            title="Post OSHA Form 300A summary",
            category="safety",
            severity="medium",
            deadline=_resolve_date(today, 2, 1),
            action="Post the prior year's Form 300A injury summary in a visible workplace location through April 30.",
            jurisdiction_name="Federal",
        ))

    # ── Federal — OSHA 300A electronic submission (20-249 hazardous + 250+)
    if employee_count >= 20:
        out.append(_make(
            slug="osha-300a-efile", scope="fed", today=today,
            title="OSHA 300A electronic submission",
            category="safety",
            severity="medium",
            deadline=_resolve_date(today, 3, 2),
            action="Submit Form 300A electronically via OSHA's ITA portal (covered industries 20–249 employees, all 250+).",
            jurisdiction_name="Federal",
        ))

    # ── Federal — ACA reporting (50+ FT or FT-equivalents)
    if employee_count >= 50:
        out.append(_make(
            slug="aca-1095c-employees", scope="fed", today=today,
            title="ACA 1095-C forms to employees",
            category="benefits",
            severity="high",
            deadline=_resolve_date(today, 3, 2),
            action="Distribute Form 1095-C to all full-time employees (ALE coverage offer reporting).",
            jurisdiction_name="Federal",
        ))
        out.append(_make(
            slug="aca-1094c-irs", scope="fed", today=today,
            title="ACA 1094-C / 1095-C e-file with IRS",
            category="benefits",
            severity="high",
            deadline=_resolve_date(today, 3, 31),
            action="Electronic IRS filing of Forms 1094-C transmittal and 1095-C employee statements.",
            jurisdiction_name="Federal",
        ))

    # ── Federal — EEO-1 (100+; 50+ federal contractors)
    if employee_count >= 100:
        out.append(_make(
            slug="eeo1", scope="fed", today=today,
            title="EEO-1 Component 1 filing",
            category="employment_law",
            severity="medium",
            # Final deadline historically falls in early-to-mid June; check
            # the current year's EEOC announcement for the exact date.
            deadline=_resolve_date(today, 6, 4),
            action="File EEO-1 Component 1 demographic report with the EEOC.",
            jurisdiction_name="Federal",
        ))

    # ── Federal — Form 5500 (any 401(k) / qualifying plan, calendar-year)
    out.append(_make(
        slug="form-5500", scope="fed", today=today,
        title="Form 5500 (401(k) / employee benefit plans)",
        category="benefits",
        severity="medium",
        deadline=_resolve_date(today, 7, 31),
        action="File Form 5500 for calendar-year 401(k) and welfare benefit plans (or file Form 5558 for an extension).",
        jurisdiction_name="Federal",
    ))

    if has_ca_location:
        # ── California — DE 9 / DE 9C quarterly (every employer)
        for q_label, q_due in (
            ("Q1", (4, 30)),
            ("Q2", (7, 31)),
            ("Q3", (10, 31)),
            ("Q4", (1, 31)),
        ):
            out.append(_make(
                slug=f"ca-de9-{q_label.lower()}", scope="ca", today=today,
                title=f"CA DE 9 / DE 9C — {q_label} payroll filing",
                category="payroll_tax",
                severity="high",
                deadline=_resolve_date(today, *q_due),
                action="File quarterly DE 9 (contribution return) and DE 9C (wage detail) with the California EDD.",
                jurisdiction_name="California",
                location_state="CA",
            ))

        # ── California — IIPP annual review (1+ employees, every CA employer)
        out.append(_make(
            slug="ca-iipp-review", scope="ca", today=today,
            title="CA IIPP annual review",
            category="safety",
            severity="medium",
            deadline=_resolve_date(today, 12, 31),
            action="Review and update the Injury & Illness Prevention Program — required of every CA employer with at least one employee.",
            jurisdiction_name="California",
            location_state="CA",
        ))

        # ── California — DFEH/CRD harassment prevention training (5+, biennial)
        if employee_count >= 5:
            out.append(_make(
                slug="ca-harassment-training", scope="ca", today=today,
                title="CA harassment prevention training (biennial)",
                category="employment_law",
                severity="medium",
                deadline=_resolve_date(today, 12, 31),
                action="Provide CRD-compliant sexual harassment prevention training — supervisors 2 hours, non-supervisors 1 hour, every 2 years.",
                jurisdiction_name="California",
                location_state="CA",
            ))

        # ── California — Pay Data Reporting SB 1162 (100+)
        if employee_count >= 100:
            out.append(_make(
                slug="ca-pay-data-report", scope="ca", today=today,
                title="CA Pay Data Reporting (SB 1162)",
                category="employment_law",
                severity="high",
                deadline=_resolve_second_wed_may(today),
                action="File pay data report with the California Civil Rights Department (second Wednesday of May).",
                jurisdiction_name="California",
                location_state="CA",
            ))

    if has_ny_location:
        # ── New York — NYS-45 quarterly combined withholding/wage/UI
        # (every NY employer). Same Q-end-month-plus-one cadence as CA DE 9.
        for q_label, q_due in (
            ("Q1", (4, 30)),
            ("Q2", (7, 31)),
            ("Q3", (10, 31)),
            ("Q4", (1, 31)),
        ):
            out.append(_make(
                slug=f"ny-nys45-{q_label.lower()}", scope="ny", today=today,
                title=f"NY NYS-45 — {q_label} combined withholding & UI return",
                category="payroll_tax",
                severity="high",
                deadline=_resolve_date(today, *q_due),
                action="File NYS-45 (combined NYS-1 withholding + UI Form 45 wage detail) with the NY Department of Taxation and Finance.",
                jurisdiction_name="New York",
                location_state="NY",
            ))

        # ── NY — Sexual Harassment Prevention Training (every employee, annual)
        # NYSHRL applies to every NY employer regardless of size — no threshold.
        out.append(_make(
            slug="ny-harassment-training", scope="ny", today=today,
            title="NY sexual harassment prevention training (annual)",
            category="employment_law",
            severity="medium",
            deadline=_resolve_date(today, 12, 31),
            action="Provide NY DOL/Division of Human Rights compliant interactive sexual-harassment training to every employee — required annually under §201-g.",
            jurisdiction_name="New York",
            location_state="NY",
        ))

        # ── NY — Paid Family Leave annual employee notice (every NY employer)
        out.append(_make(
            slug="ny-pfl-notice", scope="ny", today=today,
            title="NY Paid Family Leave annual employee notice",
            category="benefits",
            severity="medium",
            deadline=_resolve_date(today, 12, 31),
            action="Distribute the NY PFL Statement of Rights notice to all eligible employees and post the required PFL workplace poster.",
            jurisdiction_name="New York",
            location_state="NY",
        ))

        # ── NY — HERO Act airborne infectious disease plan (every employer)
        out.append(_make(
            slug="ny-hero-act-review", scope="ny", today=today,
            title="NY HERO Act airborne disease plan review",
            category="safety",
            severity="medium",
            deadline=_resolve_date(today, 12, 31),
            action="Review and update the NY HERO Act airborne infectious disease exposure prevention plan; distribute current plan to employees.",
            jurisdiction_name="New York",
            location_state="NY",
        ))

        # ── NY — Pay Transparency Act (4+; effective Sept 17, 2023)
        if employee_count >= 4:
            out.append(_make(
                slug="ny-pay-transparency-review", scope="ny", today=today,
                title="NY Pay Transparency compliance review",
                category="employment_law",
                severity="medium",
                deadline=_resolve_date(today, 12, 31),
                action="Audit current job postings — all NY-advertised roles must include a good-faith salary range and job description (Labor Law §194-b, 4+ employees).",
                jurisdiction_name="New York",
                location_state="NY",
            ))

    # Trim items past the lookahead window — keeps the feed near-term.
    cutoff = today + timedelta(days=_LOOKAHEAD_DAYS)
    out = [i for i in out if date.fromisoformat(i.deadline) <= cutoff]
    return sorted(out, key=lambda i: i.deadline)
