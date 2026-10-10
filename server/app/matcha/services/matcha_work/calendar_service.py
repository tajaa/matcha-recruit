"""The Espresso calendar: a person's own events (`mw_calendar_events`) and the
timezone their app reports (`mw_calendar_prefs`).

User-scoped like the productivity boards. One wire shape for an event,
everywhere (the REST routes, the assistant's tools, the email suggestions):

    {id, title, notes, location, all_day, start, end,
     source_kind, source_ref, source_label, created_at, updated_at}

`start`/`end` are RFC 3339 with an offset for a timed event and `YYYY-MM-DD`
for an all-day one, whose `end` is the LAST day (inclusive), not Google's
exclusive end. Times are written in the zone the caller asks for (the person's
own when known), UTC otherwise.

Pool-free (`connection_or_direct`): the assistant's tools call it from a worker.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg

from ....database import connection_or_direct

logger = logging.getLogger(__name__)

MAX_TITLE = 300
MAX_LOCATION = 300
MAX_NOTES = 4000
MAX_SOURCE_LABEL = 300
MAX_SPAN = timedelta(days=31)
MAX_WINDOW = timedelta(days=100)
MAX_ROWS = 500
DEFAULT_LENGTH = timedelta(hours=1)
SOURCE_KINDS = ("manual", "assistant", "email", "journal")

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+\-]\d{2}:\d{2})")
_WHEN_RULE = (
    "Times are RFC 3339 with an offset, like 2026-10-02T19:00:00-07:00, "
    "or a date like 2026-10-02 for all day."
)
_COLUMNS = """id, title, notes, location, all_day, starts_at, ends_at, start_date, end_date,
              source_kind, source_ref, source_label, created_at, updated_at"""

When = date | datetime


# ── Parsing and validation ───────────────────────────────────────────────


def zone(name: Optional[str]) -> Optional[ZoneInfo]:
    """The IANA zone `name` names, or None for anything else."""
    text = (name or "").strip()
    if not text or len(text) > 64:
        return None
    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError, OSError):  # "America" is a directory
        return None


def parse_when(value: Any) -> When:
    """A date (all day) or an aware datetime. Raises ValueError otherwise."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError(_WHEN_RULE)
        return value
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    try:
        if _DATE.fullmatch(text):
            return date.fromisoformat(text)
        if _DATETIME.fullmatch(text):
            return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("That date does not exist.") from exc
    raise ValueError(_WHEN_RULE)


def _line(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _text(value: Any, limit: int) -> Optional[str]:
    text = str(value or "").strip()[:limit]
    return text or None


def event_fields(*, title: Any, start: Any, end: Any = None,
                 location: Any = None, notes: Any = None) -> dict:
    """The validated columns of one event. A timed event with no end lasts an
    hour; an all-day event with no end is one day. Raises ValueError with a
    message fit to show the person (or the model)."""
    clean_title = _line(title, MAX_TITLE)
    if not clean_title:
        raise ValueError("An event needs a title.")
    if start is None or (isinstance(start, str) and not start.strip()):
        raise ValueError("An event needs a start.")
    begin = parse_when(start)
    finish = None if end is None or (isinstance(end, str) and not end.strip()) else parse_when(end)
    fields = {
        "title": clean_title,
        "location": _text(_line(location, MAX_LOCATION), MAX_LOCATION),
        "notes": _text(notes, MAX_NOTES),
    }
    if isinstance(begin, datetime):
        finish = begin + DEFAULT_LENGTH if finish is None else finish
        if not isinstance(finish, datetime):
            raise ValueError("A timed event ends at a time, not a date.")
        if finish < begin:
            raise ValueError("An event cannot end before it starts.")
        if finish - begin > MAX_SPAN:
            raise ValueError("An event can last at most 31 days.")
        return {**fields, "all_day": False, "starts_at": begin, "ends_at": finish,
                "start_date": None, "end_date": None}
    finish = begin if finish is None else finish
    if isinstance(finish, datetime):
        raise ValueError("An all-day event ends on a date, not a time.")
    if finish < begin:
        raise ValueError("An event cannot end before it starts.")
    if finish - begin > MAX_SPAN:
        raise ValueError("An event can last at most 31 days.")
    return {**fields, "all_day": True, "starts_at": None, "ends_at": None,
            "start_date": begin, "end_date": finish}


def _bounds(row) -> tuple[When, When]:
    if row["all_day"]:
        return row["start_date"], row["end_date"]
    return row["starts_at"], row["ends_at"]


def merged_fields(row, patch: dict) -> dict:
    """`row` with `patch` applied, validated as a whole. Moving the start alone
    keeps the event's length; a start of the other kind (a date for a timed
    event, or a time for an all-day one) starts over from that kind's default."""
    cur_start, cur_end = _bounds(row)
    start: Any = cur_start
    end: Any = cur_end
    if patch.get("start"):
        start = parse_when(patch["start"])
        if patch.get("end"):
            end = patch["end"]
        elif isinstance(start, datetime) == isinstance(cur_start, datetime):
            end = start + (cur_end - cur_start)
        else:
            end = None
    elif patch.get("end"):
        end = patch["end"]
    return event_fields(
        title=patch["title"] if patch.get("title") is not None else row["title"],
        start=start, end=end,
        location=patch["location"] if "location" in patch else row["location"],
        notes=patch["notes"] if "notes" in patch else row["notes"],
    )


def window(start: Any, end: Any) -> tuple[datetime, datetime]:
    """A [start, end) range to list, both aware times, at most 100 days."""
    begin, finish = parse_when(start), parse_when(end)
    if not isinstance(begin, datetime) or not isinstance(finish, datetime):
        raise ValueError("A range is two times with an offset. " + _WHEN_RULE)
    if finish <= begin:
        raise ValueError("A range must end after it starts.")
    if finish - begin > MAX_WINDOW:
        raise ValueError("A range can cover at most 100 days.")
    return begin, finish


def days_touched(begin: datetime, finish: datetime) -> tuple[date, date]:
    """The calendar days a range touches, each in its own offset."""
    return begin.date(), (finish - timedelta(microseconds=1)).date()


# ── Wire shape ───────────────────────────────────────────────────────────


def render_when(value: When, tz: Optional[ZoneInfo]) -> str:
    if isinstance(value, datetime):
        moment = value.astimezone(tz or timezone.utc)
        text = moment.isoformat(timespec="seconds")
        return text[:-6] + "Z" if text.endswith("+00:00") and tz is None else text
    return value.isoformat()


def event_view(row, tz: Optional[ZoneInfo] = None) -> dict:
    start, end = _bounds(row)
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "notes": row["notes"],
        "location": row["location"],
        "all_day": bool(row["all_day"]),
        "start": render_when(start, tz),
        "end": render_when(end, tz),
        "source_kind": row["source_kind"],
        "source_ref": row["source_ref"],
        "source_label": row["source_label"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def todo_view(row) -> dict:
    return {
        "id": str(row["id"]),
        "board_id": str(row["board_id"]),
        "board_title": row["board_title"],
        "title": row["title"],
        "board_column": row["board_column"],
        "due_date": row["due_date"].isoformat(),
        "source_journal_id": str(row["source_journal_id"]) if row["source_journal_id"] else None,
    }


# ── Reads ────────────────────────────────────────────────────────────────


async def list_events(user_id: UUID, begin: datetime, finish: datetime, *,
                      tz: Optional[ZoneInfo] = None, query: Optional[str] = None) -> list[dict]:
    """Events touching [begin, finish): timed ones that overlap it (an instant
    at `begin` counts) and all-day ones on any day it touches."""
    first_day, last_day = days_touched(begin, finish)
    params: list[Any] = [user_id, begin, finish, first_day, last_day]
    match = ""
    if query and query.strip():
        params.append(f"%{_line(query, 200)}%")
        match = f"AND (title ILIKE ${len(params)} OR location ILIKE ${len(params)} OR notes ILIKE ${len(params)})"
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {_COLUMNS}
            FROM mw_calendar_events
            WHERE user_id = $1
              AND ((NOT all_day AND starts_at < $3 AND (ends_at > $2 OR starts_at >= $2))
                   OR (all_day AND start_date <= $5 AND end_date >= $4))
              {match}
            ORDER BY COALESCE(start_date, (starts_at AT TIME ZONE 'UTC')::date), all_day DESC, starts_at, id
            LIMIT {MAX_ROWS}
            """,
            *params,
        )
    return [event_view(r, tz) for r in rows]


async def list_dated_todos(user_id: UUID, first_day: date, last_day: date) -> list[dict]:
    """To-dos with a due date in [first_day, last_day] on the person's active boards."""
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""
            SELECT c.id, c.board_id, b.title AS board_title, c.title, c.board_column,
                   c.due_date, c.source_journal_id
            FROM mw_productivity_cards c
            JOIN mw_productivity_boards b ON b.id = c.board_id
            WHERE c.user_id = $1 AND b.status = 'active'
              AND c.due_date BETWEEN $2 AND $3
            ORDER BY c.due_date, c.board_column, c.position, c.id
            LIMIT {MAX_ROWS}
            """,
            user_id, first_day, last_day,
        )
    return [todo_view(r) for r in rows]


async def events_from_source(user_id: UUID, source_kind: str, source_ref: str, *,
                             tz: Optional[ZoneInfo] = None) -> list[dict]:
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {_COLUMNS} FROM mw_calendar_events
            WHERE user_id = $1 AND source_kind = $2 AND source_ref = $3
            ORDER BY created_at, id
            LIMIT 20
            """,
            user_id, source_kind, source_ref,
        )
    return [event_view(r, tz) for r in rows]


# ── Writes ───────────────────────────────────────────────────────────────


async def create_event(user_id: UUID, company_id: Optional[UUID], fields: dict, *,
                       source_kind: str = "manual", source_ref: Optional[str] = None,
                       source_label: Optional[str] = None,
                       tz: Optional[ZoneInfo] = None) -> dict:
    """`fields` comes from `event_fields`."""
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"unknown source {source_kind!r}")
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO mw_calendar_events
                (user_id, company_id, title, notes, location, all_day,
                 starts_at, ends_at, start_date, end_date, source_kind, source_ref, source_label)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING {_COLUMNS}
            """,
            user_id, company_id, fields["title"], fields["notes"], fields["location"],
            fields["all_day"], fields["starts_at"], fields["ends_at"],
            fields["start_date"], fields["end_date"], source_kind,
            _text(source_ref, 200), _text(_line(source_label, MAX_SOURCE_LABEL), MAX_SOURCE_LABEL),
        )
    return event_view(row, tz)


async def get_event(event_id: UUID, user_id: UUID, *, tz: Optional[ZoneInfo] = None) -> Optional[dict]:
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM mw_calendar_events WHERE id = $1 AND user_id = $2",
            event_id, user_id,
        )
    return event_view(row, tz) if row else None


async def update_event(event_id: UUID, user_id: UUID, patch: dict, *,
                       tz: Optional[ZoneInfo] = None) -> Optional[dict]:
    """None when the person has no such event. Raises ValueError for a patch
    that leaves the event invalid."""
    async with connection_or_direct() as conn, conn.transaction():
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM mw_calendar_events WHERE id = $1 AND user_id = $2 FOR UPDATE",
            event_id, user_id,
        )
        if row is None:
            return None
        fields = merged_fields(row, patch)
        updated = await conn.fetchrow(
            f"""
            UPDATE mw_calendar_events
            SET title = $3, notes = $4, location = $5, all_day = $6, starts_at = $7, ends_at = $8,
                start_date = $9, end_date = $10, updated_at = NOW()
            WHERE id = $1 AND user_id = $2
            RETURNING {_COLUMNS}
            """,
            event_id, user_id, fields["title"], fields["notes"], fields["location"], fields["all_day"],
            fields["starts_at"], fields["ends_at"], fields["start_date"], fields["end_date"],
        )
    return event_view(updated, tz)


async def delete_event(event_id: UUID, user_id: UUID) -> bool:
    async with connection_or_direct() as conn:
        result = await conn.execute(
            "DELETE FROM mw_calendar_events WHERE id = $1 AND user_id = $2",
            event_id, user_id,
        )
    return result.endswith(" 1")


# ── The person's timezone ────────────────────────────────────────────────


async def get_timezone(user_id: UUID, conn=None) -> Optional[str]:
    """The IANA zone the person's app last reported, or None. Never raises:
    the assistant reads it on every run, and a missing table (a deploy ahead
    of its migration) or a bad value must not stop a run."""
    query = "SELECT timezone FROM mw_calendar_prefs WHERE user_id = $1"
    try:
        if conn is not None:
            name = await conn.fetchval(query, user_id)
        else:
            async with connection_or_direct() as own:
                name = await own.fetchval(query, user_id)
    except asyncpg.UndefinedTableError:
        logger.warning("mw_calendar_prefs is missing; is migration mwcal01 applied?")
        return None
    return name if zone(name) is not None else None


async def set_timezone(user_id: UUID, name: str) -> str:
    if zone(name) is None:
        raise ValueError("Not a timezone name (like America/Los_Angeles).")
    clean = name.strip()
    async with connection_or_direct() as conn:
        await conn.execute(
            """
            INSERT INTO mw_calendar_prefs (user_id, timezone) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone, updated_at = NOW()
            WHERE mw_calendar_prefs.timezone IS DISTINCT FROM EXCLUDED.timezone
            """,
            user_id, clean,
        )
    return clean
