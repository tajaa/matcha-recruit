"""Durable context and authorization for the schedule Huume surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException

from app.database import get_connection
from app.matcha.services.matcha_work.matcha_work_document import get_thread_messages
from app.matcha.services.scheduling.schedule_eligibility_authorization import (
    resolve_eligibility_manager_scope,
)

@dataclass(frozen=True)
class ScheduleAssistantScope:
    thread_id: UUID
    company_id: UUID
    user_id: UUID
    location_id: UUID
    week_start: date
    week_end: date
    actor_role: str


def _week_end(week_start: date) -> date:
    # This is the inclusive display boundary for the editor's seven-day week.
    # SQL readers derive their own exclusive timestamp boundary when querying.
    return week_start + timedelta(days=6)


def _coerce_jsonb(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return value if isinstance(value, dict) else {}


async def _assert_manager_location(
    conn, *, company_id: UUID, user_id: UUID, actor_role: str, location_id: UUID
) -> None:
    location = await conn.fetchrow(
        "SELECT is_active FROM business_locations WHERE id=$1 AND company_id=$2",
        location_id,
        company_id,
    )
    if not location or location["is_active"] is False:
        raise HTTPException(status_code=404, detail="Location not found")
    scope = await resolve_eligibility_manager_scope(
        conn,
        company_id=company_id,
        actor_user_id=user_id,
        actor_role=actor_role,
    )
    if not scope.permits(location_id):
        raise HTTPException(status_code=403, detail="You are not authorized to manage this location")


async def get_or_create_schedule_assistant_session(
    *,
    company_id: UUID,
    user_id: UUID,
    actor_role: str,
    location_id: UUID,
    week_start: date,
) -> dict:
    """Return the one Huume thread for this manager/location/week.

    The advisory lock makes concurrent panel mounts converge on one session;
    the unique constraint is the final backstop for older databases.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            await _assert_manager_location(
                conn,
                company_id=company_id,
                user_id=user_id,
                actor_role=actor_role,
                location_id=location_id,
            )
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"schedule-assistant:{company_id}:{user_id}:{location_id}:{week_start.isoformat()}",
            )
            existing = await conn.fetchrow(
                """
                SELECT s.id, s.company_id, s.user_id, s.location_id, s.week_start,
                       s.thread_id, t.current_state, t.version, t.status
                FROM schedule_assistant_sessions s
                JOIN mw_threads t ON t.id=s.thread_id
                WHERE s.company_id=$1 AND s.user_id=$2 AND s.location_id=$3 AND s.week_start=$4
                """,
                company_id,
                user_id,
                location_id,
                week_start,
            )
            if existing:
                session_id = existing["id"]
                thread_id = existing["thread_id"]
                current_state = _coerce_jsonb(existing["current_state"])
                version = existing["version"]
            else:
                current_state = {
                    "huume_surface": {
                        "kind": "schedule_assistant",
                        "location_id": str(location_id),
                        "week_start": week_start.isoformat(),
                    }
                }
                # This is deliberately a raw insert rather than the generic
                # workspace create_thread helper: the session row and its
                # surface/thread mapping must be created under this same
                # advisory-locked transaction, and schedule threads are
                # hidden from workspace element/list projections.
                thread = await conn.fetchrow(
                    f"""
                    INSERT INTO mw_threads(
                        company_id, created_by, title, current_state, surface, huume_mode
                    )
                    VALUES($1, $2, $3, $4::jsonb, 'schedule_assistant', true)
                    RETURNING id, current_state, version
                    """,
                    company_id,
                    user_id,
                    f"Schedule assistant · {week_start.isoformat()}",
                    json.dumps(current_state),
                )
                thread_id = thread["id"]
                current_state = _coerce_jsonb(thread["current_state"])
                version = thread["version"]
                session_row = await conn.fetchrow(
                    """
                    INSERT INTO schedule_assistant_sessions(
                        company_id, user_id, location_id, week_start, thread_id
                    ) VALUES($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    company_id,
                    user_id,
                    location_id,
                    week_start,
                    thread_id,
                )
                session_id = session_row["id"]

    messages = await get_thread_messages(thread_id, limit=50)
    return {
        "session_id": str(session_id),
        "thread_id": str(thread_id),
        "location_id": str(location_id),
        "week_start": week_start.isoformat(),
        "week_end": _week_end(week_start).isoformat(),
        "messages": messages,
        "current_state": current_state,
        "version": version,
    }


async def resolve_schedule_assistant_scope(
    *, thread_id: UUID, company_id: UUID, user_id: UUID, actor_role: str
) -> ScheduleAssistantScope:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT s.company_id, s.user_id, s.location_id, s.week_start,
                   t.id AS thread_id, t.surface, t.status
            FROM schedule_assistant_sessions s
            JOIN mw_threads t ON t.id=s.thread_id
            WHERE s.thread_id=$1 AND s.company_id=$2
            """,
            thread_id,
            company_id,
        )
        if not row or row["surface"] != "schedule_assistant" or row["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="Schedule assistant session not found")
        await _assert_manager_location(
            conn,
            company_id=company_id,
            user_id=user_id,
            actor_role=actor_role,
            location_id=row["location_id"],
        )
        return ScheduleAssistantScope(
            thread_id=row["thread_id"],
            company_id=row["company_id"],
            user_id=row["user_id"],
            location_id=row["location_id"],
            week_start=row["week_start"],
            week_end=_week_end(row["week_start"]),
            actor_role=actor_role,
        )
