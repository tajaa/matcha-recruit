"""Append-only delivery record for break reminders (email digest + push).

Every producer that tells someone about a meal or rest break records the
ATTEMPT here with the outcome the provider reported at send time. The table
(migration ``empsched28``) refuses UPDATEs, so nothing written here can later
be restated. What a row proves is narrow and the UI says so: ``accepted`` means
the email or push provider took the message, not that anyone received or read
it, and never that a break was taken — that is a timekeeping question.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

Channel = Literal["email", "push"]
ReminderType = Literal["daily_digest", "break_start"]
RecipientType = Literal["employee", "manager"]
Outcome = Literal["accepted", "failed", "unavailable"]

OUTCOMES: tuple[Outcome, ...] = ("accepted", "failed", "unavailable")
_DETAIL_MAX = 500


def valid_zone(name: str | None) -> tuple[str, ZoneInfo | timezone]:
    """The location's zone, falling back to UTC for a missing or bad name.

    The stored name is what later readers see, so a bad one is recorded as
    ``UTC`` rather than copied into the audit trail."""
    try:
        return (name or "UTC"), ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC", timezone.utc


def local_date(now: datetime, timezone_name: str | None) -> date:
    return now.astimezone(valid_zone(timezone_name)[1]).date()


async def record_event(
    conn,
    *,
    company_id: UUID,
    channel: Channel,
    reminder_type: ReminderType,
    recipient_type: RecipientType,
    outcome: Outcome,
    event_date: date,
    outcome_detail: str | None = None,
    recipient: str | None = None,
    recipient_user_id: UUID | None = None,
    employee_id: UUID | None = None,
    employee_name: str | None = None,
    covered_employee_ids: list[UUID] | None = None,
    location_id: UUID | None = None,
    location_name: str | None = None,
    location_timezone: str | None = None,
    shift_id: UUID | None = None,
    assignment_id: UUID | None = None,
    break_kind: str | None = None,
    break_start_local: datetime | None = None,
    break_duration_minutes: int | None = None,
    context: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> bool:
    """Insert one attempt; False only when ``dedupe_key`` was already recorded."""
    if outcome not in OUTCOMES:
        raise ValueError(f"Unknown break reminder outcome: {outcome}")
    covered = list(dict.fromkeys(covered_employee_ids or ([employee_id] if employee_id else [])))
    row = await conn.fetchval(
        """
        INSERT INTO schedule_break_reminder_events
            (company_id, event_date, channel, reminder_type, recipient_type,
             recipient, recipient_user_id, employee_id, employee_name,
             covered_employee_ids, location_id, location_name, location_timezone,
             shift_id, assignment_id, break_kind, break_start_local,
             break_duration_minutes, context, outcome, outcome_detail, dedupe_key)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::uuid[],$11,$12,$13,$14,$15,$16,$17,
                $18,$19::jsonb,$20,$21,$22)
        ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
        RETURNING id
        """,
        company_id, event_date, channel, reminder_type, recipient_type,
        (recipient or "").lower() or None, recipient_user_id, employee_id, employee_name,
        covered, location_id, location_name,
        valid_zone(location_timezone)[0] if location_timezone else None,
        shift_id, assignment_id, break_kind,
        break_start_local.replace(tzinfo=None) if break_start_local else None,
        break_duration_minutes, json.dumps(context or {}, default=str), outcome,
        (outcome_detail or None) and outcome_detail[:_DETAIL_MAX], dedupe_key,
    )
    return row is not None


# ---------------------------------------------------------------------------
# Read side
# ---------------------------------------------------------------------------

def event_filters(
    company_id: UUID,
    *,
    start: date | None,
    end: date | None,
    location_id: UUID | None,
    employee_id: UUID | None,
) -> tuple[str, list[Any]]:
    """WHERE clause for the history view. Tenant scope is always the first term.

    ``start``/``end`` are both inclusive location-local calendar days. The
    employee filter also matches a manager digest that listed that employee,
    since telling the supervisor is part of that employee's history.
    """
    params: list[Any] = [company_id]
    where = ["ev.company_id = $1"]
    for value, expression in (
        (start, "ev.event_date >= ${}"),
        (end, "ev.event_date <= ${}"),
        (location_id, "ev.location_id = ${}"),
    ):
        if value is not None:
            params.append(value)
            where.append(expression.format(len(params)))
    if employee_id is not None:
        params.append(employee_id)
        position = len(params)
        where.append(f"(ev.employee_id = ${position} OR ${position} = ANY(ev.covered_employee_ids))")
    return " AND ".join(where), params


async def list_events(
    conn,
    company_id: UUID,
    *,
    start: date | None = None,
    end: date | None = None,
    location_id: UUID | None = None,
    employee_id: UUID | None = None,
    limit: int,
    offset: int = 0,
) -> tuple[list[dict], int]:
    where, params = event_filters(
        company_id, start=start, end=end, location_id=location_id, employee_id=employee_id,
    )
    total = int(await conn.fetchval(
        f"SELECT COUNT(*) FROM schedule_break_reminder_events ev WHERE {where}", *params,
    ))
    rows = await conn.fetch(
        f"""
        SELECT ev.*
        FROM schedule_break_reminder_events ev
        WHERE {where}
        ORDER BY ev.occurred_at DESC, ev.id DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset,
    )
    return [serialize_event(row) for row in rows], total


async def filter_options(conn, company_id: UUID) -> dict:
    """Every location and employee that appears in this company's history.

    Read from the events themselves (not the live roster) so a former employee
    or a closed store stays filterable, under the name recorded at send time.
    """
    locations = await conn.fetch(
        """
        SELECT DISTINCT ON (location_id) location_id, location_name
        FROM schedule_break_reminder_events
        WHERE company_id = $1 AND location_id IS NOT NULL
        ORDER BY location_id, occurred_at DESC
        """,
        company_id,
    )
    employees = await conn.fetch(
        """
        SELECT DISTINCT ON (employee_id) employee_id, employee_name
        FROM schedule_break_reminder_events
        WHERE company_id = $1 AND employee_id IS NOT NULL
        ORDER BY employee_id, occurred_at DESC
        """,
        company_id,
    )
    return {
        "locations": sorted(
            ({"id": str(row["location_id"]), "name": row["location_name"]} for row in locations),
            key=lambda item: (item["name"] or "").casefold(),
        ),
        "employees": sorted(
            ({"id": str(row["employee_id"]), "name": row["employee_name"]} for row in employees),
            key=lambda item: (item["name"] or "").casefold(),
        ),
    }


def _context(value: Any) -> dict:
    # Worker and pool connections differ on whether jsonb arrives decoded.
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def serialize_event(row) -> dict:
    occurred_at = row["occurred_at"]
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return {
        "id": str(row["id"]),
        "occurred_at": occurred_at.isoformat(),
        "event_date": row["event_date"].isoformat(),
        "channel": row["channel"],
        "reminder_type": row["reminder_type"],
        "recipient_type": row["recipient_type"],
        "recipient": row["recipient"],
        "employee": (
            {"id": str(row["employee_id"]), "name": row["employee_name"]}
            if row["employee_id"] else None
        ),
        "covered_employee_count": len(row["covered_employee_ids"] or []),
        "location": (
            {"id": str(row["location_id"]), "name": row["location_name"],
             "timezone": row["location_timezone"]}
            if row["location_id"] else None
        ),
        "shift_id": str(row["shift_id"]) if row["shift_id"] else None,
        "break": (
            {
                "kind": row["break_kind"],
                "start_local": row["break_start_local"].isoformat() if row["break_start_local"] else None,
                "duration_minutes": row["break_duration_minutes"],
            }
            if row["break_kind"] else None
        ),
        "context": _context(row["context"]),
        "outcome": row["outcome"],
        "outcome_detail": row["outcome_detail"],
    }
