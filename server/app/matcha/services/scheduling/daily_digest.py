"""Deterministic daily schedule/break/note email composition and delivery."""

from __future__ import annotations

import json
from datetime import date
from html import escape
from uuid import UUID

from app.core.services.email import get_email_service


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


async def _claim(conn, *, company_id, location_id, digest_date, email, recipient_type) -> bool:
    row = await conn.fetchval(
        """
        INSERT INTO schedule_digest_deliveries
            (company_id, location_id, digest_date, recipient_email, recipient_type)
        VALUES ($1,$2,$3,$4,$5)
        ON CONFLICT (location_id, digest_date, recipient_email, recipient_type) DO NOTHING
        RETURNING id
        """,
        company_id, location_id, digest_date, email, recipient_type,
    )
    return row is not None


def _manager_html(location_name: str, rows: list[dict], digest_date: date) -> str:
    lines = []
    for row in rows:
        requirements = _guidance_text(row.get("compliance_guidance")) if row.get("compliance_guidance") else "No break guidance recorded."
        note = row.get("manager_note") if row.get("manager_note_include_in_location_digest") else None
        lines.append(
            f"<li><b>{escape(row['name'] or 'Unnamed employee')}</b> — {escape(requirements)}"
            f"{f' — Note: {escape(note)}' if note else ''}</li>"
        )
    return (
        f"<p>Good morning {escape(location_name)} team.</p>"
        f"<p><b>Today's breaks and shift notes ({digest_date.isoformat()}):</b></p>"
        f"<ul>{''.join(lines) or '<li>No break requirements or visible notes.</li>'}</ul>"
        "<p>Have a great shift.</p>"
    )


def _employee_html(row: dict, digest_date: date) -> str:
    lines = []
    if row.get("compliance_guidance"):
        lines.append(escape(_guidance_text(row["compliance_guidance"])))
    if row.get("manager_note") and row.get("manager_note_visible_to_employee"):
        lines.append(escape(row["manager_note"]))
    return f"<p>Your schedule notes for {digest_date.isoformat()}:</p><ul>{''.join(f'<li>{line}</li>' for line in lines)}</ul>"


async def send_location_daily_digest(conn, *, company_id: UUID, location_id: UUID, digest_date: date) -> dict:
    location = await conn.fetchrow(
        "SELECT name FROM business_locations WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE",
        location_id, company_id,
    )
    if not location:
        return {"sent": 0, "skipped": 1}
    rows = await conn.fetch(
        """
        SELECT COALESCE(NULLIF(TRIM(e.first_name || ' ' || e.last_name), ''), e.email) AS name,
               COALESCE(u.email, e.email) AS email, a.compliance_guidance,
               a.manager_note, a.manager_note_visible_to_employee,
               a.manager_note_include_in_location_digest,
               a.manager_note_send_employee_notice
        FROM schedule_shift_assignments a
        JOIN schedule_shifts s ON s.id=a.shift_id
        JOIN employees e ON e.id=a.employee_id
        LEFT JOIN users u ON u.id=e.user_id
        WHERE s.company_id=$1 AND s.location_id=$2 AND s.starts_at::date=$3
          AND s.status = 'published' AND a.status <> 'declined'
          AND COALESCE(e.employment_status,'active')='active'
        ORDER BY s.starts_at, e.first_name, e.last_name
        """,
        company_id, location_id, digest_date,
    )
    row_dicts = [dict(row) for row in rows]
    managers = await conn.fetch(
        """
        SELECT DISTINCT COALESCE(u.email, e.email) AS email
        FROM employees e LEFT JOIN users u ON u.id=e.user_id
        WHERE e.org_id=$1 AND e.work_location_id=$2
          AND COALESCE(e.employment_status,'active')='active'
          AND (COALESCE(e.is_manager,false) OR COALESCE(e.is_supervisor,false))
          AND COALESCE(u.email,e.email) IS NOT NULL
        UNION
        SELECT email FROM schedule_location_notification_recipients
        WHERE company_id=$1 AND location_id=$2 AND is_active
        """,
        company_id, location_id,
    )
    sent = 0
    service = get_email_service()
    for recipient in managers:
        email = recipient["email"]
        if not await _claim(conn, company_id=company_id, location_id=location_id, digest_date=digest_date, email=email, recipient_type="manager"):
            continue
        try:
            ok = await service.send_email(email, None, f"Today's schedule breaks · {location['name']}", _manager_html(location["name"], row_dicts, digest_date))
        except Exception:
            ok = False
        if not ok:
            await conn.execute("DELETE FROM schedule_digest_deliveries WHERE location_id=$1 AND digest_date=$2 AND recipient_email=$3 AND recipient_type='manager'", location_id, digest_date, email)
        else:
            sent += 1
    for row in row_dicts:
        if not row.get("email") or not row.get("manager_note_send_employee_notice"):
            continue
        if not row.get("compliance_guidance") and not (row.get("manager_note") and row.get("manager_note_visible_to_employee")):
            continue
        email = row["email"]
        if not await _claim(conn, company_id=company_id, location_id=location_id, digest_date=digest_date, email=email, recipient_type="employee"):
            continue
        try:
            ok = await service.send_email(email, row.get("name"), f"Your schedule notes · {digest_date.isoformat()}", _employee_html(row, digest_date))
        except Exception:
            ok = False
        if not ok:
            await conn.execute("DELETE FROM schedule_digest_deliveries WHERE location_id=$1 AND digest_date=$2 AND recipient_email=$3 AND recipient_type='employee'", location_id, digest_date, email)
        else:
            sent += 1
    return {"sent": sent, "managers": len(managers), "employees": len(row_dicts)}
