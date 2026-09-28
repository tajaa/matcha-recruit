"""Break-start push reminders for published planned breaks.

A manager-reviewed ``planned_breaks`` entry (``empsched21``) says when one
employee's meal or rest break starts, as a wall-clock time at the shift's
location. The sweep (``workers/tasks/schedule_break_reminders.py``, every
``SWEEP_SECONDS``) pushes each one to the employee's Matcha Schedule app just
before it starts, and records every attempt in the append-only
``schedule_break_reminder_events`` (see ``break_reminder_events``).

- **Due is judged on the location's wall clock**, never real ``NOW()``: shift
  and break times are the store's clock face (scheduling CLAUDE.md), so a
  Pacific noon break is due at noon Pacific.
- **One attempt per break start.** The dedupe key names the assignment, the
  ``(kind, ordinal)`` slot and the start minute, so a retimed break gets its
  own reminder and a re-run of the same one never re-pushes. An advisory lock
  covers two sweeps racing; if a worker dies between the push and the insert
  the next sweep pushes again rather than leaving a send with no record.
- **Late is skipped, not sent.** Past ``GRACE`` after the start (a stalled
  worker), a "your break starts at 12:00" push is wrong, so nothing is sent
  and nothing is recorded as attempted.
- **Locationless shifts are skipped**: with no store there is no timezone, and
  guessing UTC would buzz the phone hours off.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.services import apns_service
from app.matcha.services.scheduling.break_reminder_events import (
    record_event,
    valid_zone,
)

logger = logging.getLogger(__name__)

PUSH_KIND = "schedule_break_reminder"
PUSH_LINK = "matchaschedule://schedule"
SWEEP_SECONDS = 120
# Pushed up to LEAD before the start; a sweep every SWEEP_SECONDS means a
# break lands between LEAD and LEAD - SWEEP_SECONDS early.
LEAD = timedelta(minutes=3)
GRACE = timedelta(minutes=10)
# Stored shift times are wall clock tagged UTC and real zones run UTC-12 to
# UTC+14, so a break due now sits on a shift that started at most a day plus
# those offsets ago. The window only bounds the scan; `_is_due` decides.
_SHIFT_LOOKBACK = timedelta(hours=38)
_SHIFT_LOOKAHEAD = timedelta(hours=15)

_CANDIDATES_SQL = """
    SELECT a.id AS assignment_id, a.shift_id, a.planned_breaks,
           s.company_id, s.location_id, l.name AS location_name, l.timezone,
           e.id AS employee_id, e.user_id,
           COALESCE(NULLIF(TRIM(e.first_name || ' ' || e.last_name), ''), e.email) AS employee_name
    FROM schedule_shift_assignments a
    JOIN schedule_shifts s ON s.id = a.shift_id AND s.company_id = a.company_id
    JOIN business_locations l ON l.id = s.location_id AND l.company_id = s.company_id
    JOIN companies c ON c.id = s.company_id
    JOIN employees e ON e.id = a.employee_id AND e.org_id = s.company_id
    WHERE s.status = 'published' AND a.status <> 'declined'
      AND s.starts_at >= $1 AND s.starts_at < $2
      -- No jsonb_array_length: AND does not short-circuit in SQL, and it
      -- raises on a non-array value.
      AND jsonb_typeof(a.planned_breaks) = 'array'
      AND a.planned_breaks <> '[]'::jsonb
      AND l.is_active IS NOT FALSE
      AND COALESCE(e.employment_status, 'active') = 'active'
      AND COALESCE(c.status, 'approved') = 'approved'
      AND COALESCE((c.enabled_features->>'employee_schedule')::boolean, false)
    ORDER BY s.starts_at, a.id
"""


@dataclass(frozen=True)
class DueBreak:
    company_id: UUID
    location_id: UUID
    location_name: str | None
    timezone: str | None
    shift_id: UUID
    assignment_id: UUID
    employee_id: UUID
    employee_name: str | None
    user_id: UUID | None
    kind: str
    ordinal: int
    start_local: datetime
    duration_minutes: int
    source: str | None

    @property
    def dedupe_key(self) -> str:
        return (
            f"break_start:{self.assignment_id}:{self.kind}:{self.ordinal}:"
            f"{self.start_local:%Y-%m-%dT%H:%M}"
        )


def _planned_breaks(value) -> list[dict]:
    """Well-formed entries only; worker connections hand jsonb back as text."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, list):
        return []
    entries = []
    for entry in value:
        if not isinstance(entry, dict) or entry.get("kind") not in ("meal", "rest"):
            continue
        try:
            # Clock fields only: `start_local` may carry an offset, and the
            # wall clock is the time that means something at the store.
            start = datetime.fromisoformat(str(entry["start_local"])).replace(tzinfo=None)
            duration = int(entry["duration_minutes"])
            ordinal = int(entry["ordinal"])
        except (KeyError, TypeError, ValueError):
            continue
        entries.append({**entry, "start": start, "duration": duration, "ordinal": ordinal})
    return entries


def wall_now(now: datetime, timezone_name: str | None) -> datetime:
    """The location's current clock face, naive, for comparison with ``start_local``."""
    return now.astimezone(valid_zone(timezone_name)[1]).replace(tzinfo=None)


def is_due(start_local: datetime, location_now: datetime) -> bool:
    return start_local - LEAD <= location_now <= start_local + GRACE


def due_breaks(rows, *, now: datetime) -> list[DueBreak]:
    due: list[DueBreak] = []
    for row in rows:
        location_now = wall_now(now, row["timezone"])
        for entry in _planned_breaks(row["planned_breaks"]):
            if not is_due(entry["start"], location_now):
                continue
            due.append(DueBreak(
                company_id=row["company_id"],
                location_id=row["location_id"],
                location_name=row["location_name"],
                timezone=row["timezone"],
                shift_id=row["shift_id"],
                assignment_id=row["assignment_id"],
                employee_id=row["employee_id"],
                employee_name=row["employee_name"],
                user_id=row["user_id"],
                kind=entry["kind"],
                ordinal=entry["ordinal"],
                start_local=entry["start"],
                duration_minutes=entry["duration"],
                source=entry.get("source"),
            ))
    return due


def clock(value: datetime) -> str:
    hour = value.hour % 12 or 12
    return f"{hour}:{value.minute:02d} {'AM' if value.hour < 12 else 'PM'}"


def push_message(item: DueBreak) -> tuple[str, str]:
    return (
        f"{item.kind.capitalize()} break",
        f"Your {item.duration_minutes}-minute {item.kind} break is scheduled for {clock(item.start_local)}.",
    )


async def _attempt_push(conn, item: DueBreak) -> tuple[str, str]:
    """(outcome, detail) for one push. Never raises."""
    if item.user_id is None:
        return "unavailable", "Employee has no Matcha Schedule account"
    if not apns_service.is_configured():
        return "unavailable", "Push notifications are not configured"
    title, body = push_message(item)
    payload = {
        "type": PUSH_KIND,
        "link": PUSH_LINK,
        "metadata": {
            "shift_id": str(item.shift_id),
            "assignment_id": str(item.assignment_id),
            "break_kind": item.kind,
            "start_local": item.start_local.isoformat(),
        },
    }
    try:
        # A savepoint: a failed device-token query must not abort the outer
        # transaction the delivery record is written in.
        async with conn.transaction():
            result = await apns_service.send_to_user(
                item.user_id, title, body, payload, kind=PUSH_KIND, conn=conn,
            )
    except Exception as exc:  # noqa: BLE001 — recorded, never lost
        return "failed", f"{type(exc).__name__}: {exc}"
    if result.sent:
        return "accepted", f"Accepted by Apple Push Notification service for {result.sent} device(s)"
    if result.transient:
        return "failed", f"Apple Push Notification service did not accept it for {result.transient} device(s)"
    if result.dead:
        return "failed", "The registered device is no longer valid"
    return "unavailable", "No Matcha Schedule device registered"


async def send_break_reminder(conn, item: DueBreak, *, now: datetime) -> str:
    """Push one break once and record it. Returns the outcome, or ``skipped``."""
    async with conn.transaction():
        locked = await conn.fetchval(
            "SELECT pg_try_advisory_xact_lock(hashtextextended($1, 0))", item.dedupe_key,
        )
        if not locked:
            return "skipped"
        if await conn.fetchval(
            "SELECT 1 FROM schedule_break_reminder_events WHERE dedupe_key = $1", item.dedupe_key,
        ):
            return "skipped"
        outcome, detail = await _attempt_push(conn, item)
        location_now = wall_now(now, item.timezone)
        await record_event(
            conn,
            company_id=item.company_id,
            channel="push",
            reminder_type="break_start",
            recipient_type="employee",
            outcome=outcome,
            outcome_detail=detail,
            event_date=location_now.date(),
            recipient_user_id=item.user_id,
            employee_id=item.employee_id,
            employee_name=item.employee_name,
            location_id=item.location_id,
            location_name=item.location_name,
            location_timezone=item.timezone,
            shift_id=item.shift_id,
            assignment_id=item.assignment_id,
            break_kind=item.kind,
            break_start_local=item.start_local,
            break_duration_minutes=item.duration_minutes,
            context={
                "ordinal": item.ordinal,
                "source": item.source,
                "sent_minutes_before_start": round(
                    (item.start_local - location_now).total_seconds() / 60, 1,
                ),
            },
            dedupe_key=item.dedupe_key,
        )
    return outcome


async def send_due_break_reminders(conn, *, now: datetime | None = None, limit: int = 500) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = await conn.fetch(_CANDIDATES_SQL, now - _SHIFT_LOOKBACK, now + _SHIFT_LOOKAHEAD)
    due = due_breaks(rows, now=now)
    if len(due) > limit:
        logger.warning("break reminders: %d due, sending the first %d this sweep", len(due), limit)
        due = due[:limit]
    recorded = set()
    if due:
        recorded = {
            row["dedupe_key"] for row in await conn.fetch(
                "SELECT dedupe_key FROM schedule_break_reminder_events WHERE dedupe_key = ANY($1::text[])",
                [item.dedupe_key for item in due],
            )
        }
    counts: Counter[str] = Counter()
    for item in due:
        if item.dedupe_key in recorded:
            counts["skipped"] += 1
            continue
        try:
            counts[await send_break_reminder(conn, item, now=now)] += 1
        except Exception:
            # One bad row must not stop every other employee's reminder.
            logger.exception("break reminder failed for assignment %s", item.assignment_id)
            counts["errors"] += 1
    return {"due": len(due), **counts}
