"""Deterministic daily schedule/break/note email composition and delivery."""

from __future__ import annotations

import json
from datetime import date
from html import escape
from uuid import UUID

from app.core.services.email import get_email_service
from app.core.services.email._shared import _is_reserved_test_domain


def _parse_guidance(value):
    """Worker connections have no jsonb type codec — this can arrive as a str."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _guidance_text(value) -> str:
    """Render the JSONB guidance payload safely in plain-text email HTML."""
    value = _parse_guidance(value)
    if isinstance(value, dict):
        return str(value.get("summary") or "Break guidance recorded.")
    return str(value)


def _planned_text(value) -> str:
    """Render the reviewed break times a manager staggered and saved.

    Without this the digest sends every assignee the same legal requirement,
    so the whole crew reads it as the same instruction and walks off the floor
    together — which is the outcome staggering exists to prevent.  Schedule
    times are wall clock: the characters ARE this location's time.
    """
    entries = _parse_guidance(value)
    if not isinstance(entries, list):
        return ""
    parts = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        start = entry.get("start_local")
        if not isinstance(start, str) or len(start) < 16:
            continue
        parts.append(
            f"{start[11:16]} ({entry.get('duration_minutes')} min {entry.get('kind')})"
        )
    return " · ".join(parts)


async def _claim(conn, *, company_id, location_id, digest_date, email, recipient_type) -> bool:
    # recipient_email has no case-insensitive constraint at the DB level —
    # normalize on write so Bob@x.com and bob@x.com converge on one claim
    # instead of each getting their own (the sibling table this UNIONs
    # against, schedule_location_notification_recipients, normalizes with
    # LOWER(email) — see empsched08).
    row = await conn.fetchval(
        """
        INSERT INTO schedule_digest_deliveries
            (company_id, location_id, digest_date, recipient_email, recipient_type)
        VALUES ($1,$2,$3,$4,$5)
        ON CONFLICT (location_id, digest_date, recipient_email, recipient_type) DO NOTHING
        RETURNING id
        """,
        company_id, location_id, digest_date, (email or "").lower(), recipient_type,
    )
    return row is not None


async def _deliver(conn, service, *, company_id, location_id, digest_date, email, recipient_type, to_name, subject, html) -> str:
    """Claim -> send -> release-on-transient-failure, in one place so all
    three recipient loops share the same idempotency and retry semantics.

    Returns one of: "sent", "skipped_duplicate", "skipped_permanent" (claim
    kept — a reserved/test domain or an unconfigured provider will never
    succeed, so retrying it every worker restart would just be noise),
    "failed_released" (claim removed — genuinely transient, eligible for the
    next scheduled run to retry)."""
    if not await _claim(conn, company_id=company_id, location_id=location_id, digest_date=digest_date, email=email, recipient_type=recipient_type):
        return "skipped_duplicate"
    if not service.is_configured() or _is_reserved_test_domain(email):
        return "skipped_permanent"
    try:
        ok = await service.send_email(email, to_name, subject, html)
    except Exception:
        ok = False
    if ok:
        return "sent"
    await conn.execute(
        "DELETE FROM schedule_digest_deliveries WHERE location_id=$1 AND digest_date=$2 AND recipient_email=LOWER($3) AND recipient_type=$4",
        location_id, digest_date, email, recipient_type,
    )
    return "failed_released"


def _manager_html(location_name: str, rows: list[dict], digest_date: date) -> str:
    """Named, per-employee view — for employee-managers with an actual
    supervisory relationship to this location (is_manager/is_supervisor)."""
    lines = []
    for row in rows:
        requirements = _guidance_text(row.get("compliance_guidance")) if row.get("compliance_guidance") else "No break guidance recorded."
        planned = _planned_text(row.get("planned_breaks"))
        note = row.get("manager_note") if row.get("manager_note_include_in_location_digest") else None
        lines.append(
            f"<li><b>{escape(row['name'] or 'Unnamed employee')}</b> — {escape(requirements)}"
            f"{f' — Break times: {escape(planned)}' if planned else ''}"
            f"{f' — Note: {escape(note)}' if note else ''}</li>"
        )
    return (
        f"<p>Good morning {escape(location_name)} team.</p>"
        f"<p><b>Today's breaks and shift notes ({digest_date.isoformat()}):</b></p>"
        f"<ul>{''.join(lines) or '<li>No break requirements or visible notes.</li>'}</ul>"
        "<p>Have a great shift.</p>"
    )


def _operational_html(location_name: str, rows: list[dict], digest_date: date) -> str:
    """Redacted view — for schedule_location_notification_recipients, an
    admin-entered address (often a shared/operational mailbox, not
    necessarily a person with a supervisory relationship to any named
    employee here). No employee names or note text; aggregate counts only."""
    with_guidance = sum(1 for row in rows if row.get("compliance_guidance"))
    with_planned = sum(1 for row in rows if _planned_text(row.get("planned_breaks")))
    digest_notes = sum(1 for row in rows if row.get("manager_note") and row.get("manager_note_include_in_location_digest"))
    return (
        f"<p>Today's schedule summary for {escape(location_name)} ({digest_date.isoformat()}):</p>"
        f"<ul>"
        f"<li>{len(rows)} shift assignment(s) today.</li>"
        f"<li>{with_guidance} with break/compliance guidance on file.</li>"
        f"<li>{with_planned} with reviewed break times scheduled.</li>"
        f"<li>{digest_notes} with a manager note visible in this digest.</li>"
        f"</ul>"
        "<p>Employee-level detail is available to that employee's manager or supervisor.</p>"
    )


def _employee_html(rows: list[dict], digest_date: date) -> str:
    """rows: every one of this employee's shift assignments today — an
    employee with two shifts gets one email covering both, since the
    per-recipient digest claim is keyed on (date, email), not per-shift."""
    lines = []
    for row in rows:
        if row.get("compliance_guidance"):
            lines.append(escape(_guidance_text(row["compliance_guidance"])))
        planned = _planned_text(row.get("planned_breaks"))
        if planned:
            lines.append(escape(f"Your break time(s) today: {planned}"))
        if row.get("manager_note") and row.get("manager_note_visible_to_employee"):
            lines.append(escape(row["manager_note"]))
    return f"<p>Your schedule notes for {digest_date.isoformat()}:</p><ul>{''.join(f'<li>{line}</li>' for line in lines)}</ul>"


async def send_location_daily_digest(conn, *, company_id: UUID, location_id: UUID, digest_date: date) -> dict:
    location = await conn.fetchrow(
        "SELECT name, timezone FROM business_locations WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE",
        location_id, company_id,
    )
    if not location:
        return {"sent": 0, "skipped": 1}
    rows = await conn.fetch(
        """
        SELECT COALESCE(NULLIF(TRIM(e.first_name || ' ' || e.last_name), ''), e.email) AS name,
               COALESCE(u.email, e.email) AS email, a.compliance_guidance,
               a.planned_breaks,
               a.manager_note, a.manager_note_visible_to_employee,
               a.manager_note_include_in_location_digest,
               a.manager_note_send_employee_notice
        FROM schedule_shift_assignments a
        JOIN schedule_shifts s ON s.id=a.shift_id
        JOIN employees e ON e.id=a.employee_id
        LEFT JOIN users u ON u.id=e.user_id
        WHERE s.company_id=$1 AND s.location_id=$2
          AND (s.starts_at AT TIME ZONE $4)::date=$3
          AND s.status = 'published' AND a.status <> 'declined'
          AND COALESCE(e.employment_status,'active')='active'
        ORDER BY s.starts_at, e.first_name, e.last_name
        """,
        company_id, location_id, digest_date, location["timezone"] or "UTC",
    )
    row_dicts = [dict(row) for row in rows]
    # Two distinct recipient populations, deliberately not unioned: an
    # employee-manager has a real supervisory relationship to this location
    # (is_manager/is_supervisor) and gets the named per-employee digest;
    # schedule_location_notification_recipients is an admin-entered address —
    # often a shared operational mailbox with no such relationship — and gets
    # a redacted, aggregate-only summary instead.
    managers = await conn.fetch(
        """
        SELECT DISTINCT COALESCE(u.email, e.email) AS email
        FROM employees e LEFT JOIN users u ON u.id=e.user_id
        WHERE e.org_id=$1 AND e.work_location_id=$2
          AND COALESCE(e.employment_status,'active')='active'
          AND (COALESCE(e.is_manager,false) OR COALESCE(e.is_supervisor,false))
          AND COALESCE(u.email,e.email) IS NOT NULL
        """,
        company_id, location_id,
    )
    operational_recipients = await conn.fetch(
        """
        SELECT email FROM schedule_location_notification_recipients
        WHERE company_id=$1 AND location_id=$2 AND is_active
        """,
        company_id, location_id,
    )
    sent = 0
    service = get_email_service()
    for recipient in managers:
        outcome = await _deliver(
            conn, service, company_id=company_id, location_id=location_id, digest_date=digest_date,
            email=recipient["email"], recipient_type="manager", to_name=None,
            subject=f"Today's schedule breaks · {location['name']}",
            html=_manager_html(location["name"], row_dicts, digest_date),
        )
        if outcome == "sent":
            sent += 1
    for recipient in operational_recipients:
        # schedule_digest_deliveries.recipient_type is CHECK-constrained to
        # ('manager', 'employee') — reuse 'manager' for the dedupe claim
        # rather than adding a migration for a third label; the content sent
        # (_operational_html, redacted) is what actually differs.
        outcome = await _deliver(
            conn, service, company_id=company_id, location_id=location_id, digest_date=digest_date,
            email=recipient["email"], recipient_type="manager", to_name=None,
            subject=f"Today's schedule summary · {location['name']}",
            html=_operational_html(location["name"], row_dicts, digest_date),
        )
        if outcome == "sent":
            sent += 1
    # Group by email BEFORE sending — an employee with two shifts today
    # would otherwise claim the (date, email) digest slot on the first row
    # and silently drop the second shift's guidance from every email ever
    # sent for that date (the claim is per-recipient-per-day, not per-shift).
    employee_rows_by_email: dict[str, list[dict]] = {}
    for row in row_dicts:
        if not row.get("email") or not row.get("manager_note_send_employee_notice"):
            continue
        if not row.get("compliance_guidance") and not (row.get("manager_note") and row.get("manager_note_visible_to_employee")):
            continue
        employee_rows_by_email.setdefault(str(row["email"]).lower(), []).append(row)
    for email, rows_for_employee in employee_rows_by_email.items():
        outcome = await _deliver(
            conn, service, company_id=company_id, location_id=location_id, digest_date=digest_date,
            email=email, recipient_type="employee", to_name=rows_for_employee[0].get("name"),
            subject=f"Your schedule notes · {digest_date.isoformat()}",
            html=_employee_html(rows_for_employee, digest_date),
        )
        if outcome == "sent":
            sent += 1
    return {
        "sent": sent, "managers": len(managers),
        "operational_recipients": len(operational_recipients),
        "employees": len(row_dicts),
    }
