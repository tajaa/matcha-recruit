"""Apple Calendar bridge: private snapshots and bounded, single-claim writes.

EventKit runs on the connected Mac. The server never receives Apple credentials.
A reconnect invalidates old work. Claimed writes are never retried after a lost
acknowledgment, since the device might already have changed the calendar.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.database import connection_or_direct, decode_jsonb
from . import calendar_service as cal
from .agent_runtime import grants

SCOPE = "espresso:apple_calendar"


def _decode(row):
    if not row:
        return None
    return {**dict(row), "calendars": decode_jsonb(row["calendars"], []),
            "snapshot": decode_jsonb(row["snapshot"], [])}


async def connection(user_id: UUID):
    try:
        async with connection_or_direct() as conn:
            row = await conn.fetchrow("SELECT * FROM mw_apple_calendar_connections WHERE user_id = $1", user_id)
    except asyncpg.UndefinedTableError:
        return None  # deploy ahead of the additive migration
    return _decode(row)


def configured(row) -> bool:
    return bool(row and row["calendars"])


async def connect(user_id: UUID, body):
    calendars = [c.model_dump() for c in body.calendars]
    ids = {c["id"] for c in calendars}
    if len(ids) != len(calendars) or not any(c["id"] == body.destination and c["editable"] for c in calendars):
        raise ValueError("Choose a writable destination among the selected calendars.")
    async with connection_or_direct() as conn, conn.transaction():
        await conn.execute("""INSERT INTO mw_apple_calendar_connections (user_id, connection_id, calendars, destination)
            VALUES ($1, $2, $3::jsonb, $4) ON CONFLICT (user_id) DO UPDATE
            SET connection_id = EXCLUDED.connection_id, calendars = EXCLUDED.calendars,
                destination = EXCLUDED.destination, snapshot = '[]'::jsonb,
                synced_at = NULL, window_start = NULL, window_end = NULL""",
            user_id, body.connection_id, json.dumps(calendars), body.destination)
        await conn.execute("""UPDATE mw_apple_calendar_actions SET status = 'cancelled', completed_at = NOW()
            WHERE user_id = $1 AND status = 'pending'""", user_id)


async def disconnect(user_id: UUID, connection_id: UUID):
    async with connection_or_direct() as conn, conn.transaction():
        await conn.execute("DELETE FROM mw_apple_calendar_connections WHERE user_id = $1 AND connection_id = $2",
                           user_id, connection_id)
        await conn.execute("""UPDATE mw_apple_calendar_actions SET status = 'cancelled', completed_at = NOW()
            WHERE user_id = $1 AND connection_id = $2 AND status = 'pending'""", user_id, connection_id)


async def snapshot(user_id: UUID, body):
    begin, finish = cal.parse_when(body.start), cal.parse_when(body.end)
    if not isinstance(begin, datetime) or not isinstance(finish, datetime) or not begin < finish <= begin + timedelta(days=400):
        raise ValueError("Sync covers two times, at most 400 days apart.")
    events = [e.model_dump() for e in body.events]
    if len({e["id"] for e in events}) != len(events):
        raise ValueError("The snapshot contains duplicate events.")
    for event in events:
        start, end = cal.parse_when(event["start"]), cal.parse_when(event["end"])
        if isinstance(start, datetime) != isinstance(end, datetime) or end < start:
            raise ValueError("An event has invalid times.")
        if event["all_day"] == isinstance(start, datetime):
            raise ValueError("An event's all-day flag disagrees with its times.")
    async with connection_or_direct() as conn, conn.transaction():
        row = _decode(await conn.fetchrow("""SELECT * FROM mw_apple_calendar_connections
            WHERE user_id = $1 AND connection_id = $2 FOR UPDATE""", user_id, body.connection_id))
        if row is None:
            raise HTTPException(409, "This Mac is no longer connected. Reconnect it in Calendar settings.")
        ids = {c["id"] for c in row["calendars"]}
        if any(e["calendar_id"] not in ids for e in events):
            raise ValueError("An event belongs to a calendar you did not select.")
        await conn.execute("""UPDATE mw_apple_calendar_connections SET snapshot = $3::jsonb,
            window_start = $4, window_end = $5, complete = $6, synced_at = NOW()
            WHERE user_id = $1 AND connection_id = $2""",
            user_id, body.connection_id, json.dumps(events), begin, finish, body.complete)


def events_in(row, begin, finish, query=None):
    if not configured(row) or row["synced_at"] is None:
        return {"status": "not_connected", "events": []}
    status = "ok" if row["complete"] else "partial"
    if datetime.now(timezone.utc) - row["synced_at"] > timedelta(minutes=5):
        status = "stale"
    if begin < row["window_start"] or finish > row["window_end"]:
        status = "out_of_range"
    first, last = cal.days_touched(begin, finish)
    events = []
    for event in row["snapshot"]:
        start, end = cal.parse_when(event["start"]), cal.parse_when(event["end"])
        overlaps = (start < finish and end >= begin) if isinstance(start, datetime) else (start <= last and end >= first)
        if overlaps and (not query or query.casefold() in event["title"].casefold()):
            events.append(event)
    return {"status": status, "events": sorted(events, key=lambda e: e["start"]),
            "synced_at": row["synced_at"].isoformat(), "connection_id": str(row["connection_id"])}


async def feed(user_id: UUID, begin, finish, query=None):
    return events_in(await connection(user_id), begin, finish, query)


def _require_live(row, connection_id):
    if not configured(row) or str(row["connection_id"]) != str(connection_id):
        raise ValueError("The Apple Calendar connection changed. List its events again.")
    if row["synced_at"] is None or datetime.now(timezone.utc) - row["synced_at"] > timedelta(minutes=5):
        raise ValueError("Open Espresso on your connected Mac to sync Apple Calendar first.")


async def enqueue(user_id: UUID, connection_id: str, operation: str, payload: dict) -> str:
    if operation not in {"create", "update", "delete"}:
        raise ValueError("Unknown calendar operation.")
    async with connection_or_direct() as conn, conn.transaction():
        row = _decode(await conn.fetchrow("""SELECT * FROM mw_apple_calendar_connections
            WHERE user_id = $1 FOR UPDATE""", user_id))
        _require_live(row, connection_id)
        if operation != "create":
            event = next((e for e in row["snapshot"] if e["id"] == payload["event"]["id"]), None)
            if not event or event != payload["event"] or not event["editable"]:
                raise ValueError("That event changed or cannot be edited. List the events again.")
        pending = await conn.fetchval("""SELECT count(*) FROM mw_apple_calendar_actions
            WHERE user_id = $1 AND status IN ('pending', 'claimed')""", user_id)
        if pending >= 30:
            raise ValueError("Wait for your Mac to finish the pending calendar changes.")
        action_id = await conn.fetchval("""INSERT INTO mw_apple_calendar_actions
            (user_id, connection_id, operation, payload) VALUES ($1, $2, $3, $4::jsonb) RETURNING id""",
            user_id, row["connection_id"], operation, json.dumps(payload))
    return str(action_id)


async def claim(user_id: UUID, connection_id: UUID):
    async with connection_or_direct() as conn, conn.transaction():
        row = _decode(await conn.fetchrow("""SELECT * FROM mw_apple_calendar_connections
            WHERE user_id = $1 FOR UPDATE""", user_id))
        _require_live(row, connection_id)
        active = await grants.load_grants(conn, user_id)
        if "calendar" not in active:
            await conn.execute("""UPDATE mw_apple_calendar_actions SET status = 'cancelled', completed_at = NOW()
                WHERE user_id = $1 AND status = 'pending'""", user_id)
            return []
        await conn.execute("""UPDATE mw_apple_calendar_actions SET status = 'unknown', completed_at = NOW(),
            error = 'The Mac did not acknowledge the write; check Calendar before trying again.'
            WHERE user_id = $1 AND status = 'claimed' AND claimed_at < NOW() - INTERVAL '5 minutes'""", user_id)
        await conn.execute("""UPDATE mw_apple_calendar_actions SET status = 'failed', completed_at = NOW(),
            error = 'The Mac did not pick up this change in time.'
            WHERE user_id = $1 AND status = 'pending' AND created_at < NOW() - INTERVAL '5 minutes'""", user_id)
        rows = await conn.fetch("""UPDATE mw_apple_calendar_actions SET status = 'claimed', claimed_at = NOW()
            WHERE id IN (SELECT id FROM mw_apple_calendar_actions WHERE user_id = $1 AND connection_id = $2
                AND status = 'pending' ORDER BY created_at, id LIMIT 10 FOR UPDATE SKIP LOCKED)
            RETURNING id, operation, payload""", user_id, connection_id)
    return [{"id": str(r["id"]), "operation": r["operation"], "payload": decode_jsonb(r["payload"], {})} for r in rows]


async def acknowledge(user_id: UUID, connection_id: UUID, action_id: UUID, body):
    async with connection_or_direct() as conn:
        await conn.execute("""UPDATE mw_apple_calendar_actions SET status = $4, error = $5, completed_at = NOW()
            WHERE id = $1 AND user_id = $2 AND connection_id = $3 AND status = 'claimed'""",
            action_id, user_id, connection_id, body.status, body.error)


async def recent(user_id: UUID):
    async with connection_or_direct() as conn:
        rows = await conn.fetch("""SELECT id, operation, status, error FROM mw_apple_calendar_actions
            WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10""", user_id)
    return [{**dict(r), "id": str(r["id"])} for r in rows]
