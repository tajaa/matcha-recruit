"""Durable context and authorization for the schedule Huume surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.database import get_connection
from app.matcha.services.matcha_work.matcha_work_document import get_thread_messages
from app.matcha.services.scheduling.location_profile import (
    WEEKDAY_NAMES, resolve_week_start_weekday,
)
from app.matcha.services.scheduling.schedule_eligibility_authorization import (
    resolve_eligibility_manager_scope,
)
from app.matcha.services.scheduling.schedule_rules import align_week_start

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


def _automatic_action(row) -> dict:
    proposal = _coerce_jsonb(row["proposal"])
    metrics = _coerce_jsonb(row["metrics"])
    review = _coerce_jsonb(proposal.get("review"))
    # The per-person load / advisories / jurisdiction review the workspace's
    # review pane renders — same shape `build_week_schedule` stages.
    schedule_review = _coerce_jsonb(proposal.get("schedule_review"))
    return {
        "type": "schedule_week_draft",
        "status": "proposed",
        "confirm_id": uuid4().hex[:8],
        "generation_run_id": str(row["id"]),
        "location_id": str(row["location_id"]),
        "week_start": row["week_start"].isoformat(),
        "source_mode": row["source_mode"],
        "week_template_id": (
            str(row["week_template_id"]) if row["week_template_id"] else None
        ),
        "origin": "automatic",
        "auto_generated": True,
        "summary": review.get("summary") or "Huume prepared this week for review.",
        "metrics": metrics or proposal.get("metrics") or {},
        "unfilled": (proposal.get("unfilled") or [])[:20],
        # Read off the PLAN, not `review`: an automatic run nobody watched is
        # exactly the one where an unreported coverage hole reaches a manager
        # as "Huume prepared this week for review".
        "findings": (proposal.get("findings") or [])[:20],
        "schedule_preview": review.get("schedule_preview") or [],
        "preview_truncated": bool(review.get("preview_truncated")),
        "review": schedule_review or None,
        "compliance_status": schedule_review.get("compliance_status"),
        "jurisdiction": schedule_review.get("jurisdiction"),
    }


async def _adopt_automatic_proposal(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    thread_id: UUID, current_state: dict, version: int,
) -> tuple[dict, int]:
    """Attach a prepared proposal to this manager's durable schedule session."""
    active = current_state.get("huume_action")
    if isinstance(active, dict) and active.get("status") == "proposed":
        if active.get("type") != "schedule_week_draft" or not active.get("generation_run_id"):
            return current_state, version
        try:
            generation_run_id = UUID(str(active["generation_run_id"]))
        except (TypeError, ValueError):
            return current_state, version
        live_status = await conn.fetchval(
            """SELECT status FROM schedule_generation_runs
               WHERE id=$1 AND company_id=$2""",
            generation_run_id, company_id,
        )
        if not live_status or live_status == "proposed":
            return current_state, version
        display_status = "applied" if live_status == "applied" else (
            "cancelled" if live_status == "cancelled" else "failed"
        )
        current_state = {
            **current_state,
            "huume_action": {**active, "status": display_status},
        }
        version = int(version or 0) + 1
        await conn.execute(
            """UPDATE mw_threads
               SET current_state=$1::jsonb, version=$2, updated_at=NOW()
               WHERE id=$3""",
            json.dumps(current_state), version, thread_id,
        )
        if live_status == "applied":
            return current_state, version
    row = await conn.fetchrow(
        """
        SELECT id, location_id, week_start, source_mode, week_template_id,
               proposal, metrics
        FROM schedule_generation_runs
        WHERE company_id=$1 AND location_id=$2 AND week_start=$3
          AND origin='automatic' AND status='proposed'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        company_id, location_id, week_start,
    )
    if not row:
        return current_state, version
    next_state = {**current_state, "huume_action": _automatic_action(row)}
    next_version = int(version or 0) + 1
    await conn.execute(
        """UPDATE mw_threads
           SET current_state=$1::jsonb, version=$2, updated_at=NOW()
           WHERE id=$3""",
        json.dumps(next_state), next_version, thread_id,
    )
    return next_state, next_version


async def assert_manager_location(
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


# The location check is authoritative wherever a manager reaches per-location
# schedule setup — the Huume session and the Week Start pane both call it, so
# it is public. Kept under the old private name for existing callers.
_assert_manager_location = assert_manager_location


async def get_or_create_schedule_assistant_session(
    *,
    company_id: UUID,
    user_id: UUID,
    actor_role: str,
    location_id: UUID,
    week_start: date,
    session_id: UUID | None = None,
) -> dict:
    """Open a Huume thread for this manager/location/week.

    Opening the panel starts a NEW conversation; passing ``session_id`` resumes
    one the manager picked out of their own history. A latest session nobody
    has spoken in yet is reused rather than duplicated, so re-opening the panel
    does not leave a trail of empty threads.

    The advisory lock makes concurrent panel mounts converge on one session
    instead of racing two empty ones into existence.
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
            # Every write on this surface is bounded by the session's week, so
            # a misaligned week_start would silently scope Huume to a window
            # that matches no grid the manager can see.
            week_start_weekday = await resolve_week_start_weekday(
                conn, company_id=company_id, location_id=location_id,
            )
            if align_week_start(week_start, week_start_weekday) != week_start:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"week_start must be a {WEEKDAY_NAMES[week_start_weekday]} "
                        f"for this location."
                    ),
                )
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"schedule-assistant:{company_id}:{user_id}:{location_id}:{week_start.isoformat()}",
            )
            if session_id is not None:
                # An archived chat is resolved as gone, not resumed: the panel
                # renders the 404 as a session error, whereas handing back the
                # transcript would look live and then 400 on every turn.
                existing = await conn.fetchrow(
                    """
                    SELECT s.id, s.company_id, s.user_id, s.location_id, s.week_start,
                           s.thread_id, t.current_state, t.version, t.status
                    FROM schedule_assistant_sessions s
                    JOIN mw_threads t ON t.id=s.thread_id
                    WHERE s.id=$1 AND s.company_id=$2 AND s.user_id=$3
                      AND s.location_id=$4 AND s.week_start=$5
                      AND t.status <> 'archived'
                    FOR UPDATE OF t
                    """,
                    session_id,
                    company_id,
                    user_id,
                    location_id,
                    week_start,
                )
                if not existing:
                    raise HTTPException(
                        status_code=404, detail="Schedule assistant session not found"
                    )
            else:
                # An empty latest session IS a fresh conversation, so hand it
                # back instead of minting a second one — otherwise opening and
                # closing the panel piles up threads nobody ever spoke in.
                existing = await conn.fetchrow(
                    """
                    SELECT s.id, s.company_id, s.user_id, s.location_id, s.week_start,
                           s.thread_id, t.current_state, t.version, t.status
                    FROM schedule_assistant_sessions s
                    JOIN mw_threads t ON t.id=s.thread_id
                    LEFT JOIN LATERAL (
                        SELECT 1 AS spoken FROM mw_messages m
                        WHERE m.thread_id=s.thread_id LIMIT 1
                    ) msg ON true
                    WHERE s.company_id=$1 AND s.user_id=$2 AND s.location_id=$3
                      AND s.week_start=$4 AND t.status <> 'archived'
                      AND msg.spoken IS NULL
                    ORDER BY s.created_at DESC
                    LIMIT 1
                    FOR UPDATE OF t
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

            current_state, version = await _adopt_automatic_proposal(
                conn,
                company_id=company_id,
                location_id=location_id,
                week_start=week_start,
                thread_id=thread_id,
                current_state=current_state,
                version=version,
            )
            # The chat is named after its FIRST turn, so it has to be read
            # from the whole thread — the message window below is the newest
            # slice and disagrees once a chat passes that many turns.
            first_user_turn = await conn.fetchval(
                """
                SELECT m.content FROM mw_messages m
                WHERE m.thread_id=$1 AND m.role='user'
                ORDER BY m.created_at ASC, m.id ASC
                LIMIT 1
                """,
                thread_id,
            )

    messages = await get_thread_messages(thread_id, limit=50)
    return {
        "session_id": str(session_id),
        "thread_id": str(thread_id),
        "location_id": str(location_id),
        "week_start": week_start.isoformat(),
        "week_end": _week_end(week_start).isoformat(),
        "title": _session_title(first_user_turn),
        "messages": messages,
        "current_state": current_state,
        "version": version,
    }


_TITLE_MAX_CHARS = 80


async def adopt_editor_proposal(
    *, company_id: UUID, user_id: UUID, actor_role: str, session_id: UUID, proposal_id: UUID,
) -> dict:
    """Make a REST fill scenario THE staged action of this manager's schedule
    thread — the Schedule Pilot's "Stage this" button.

    The scenario is a `schedule_chat_proposals` row the same caller previewed
    (`routes/employee_schedule/planning.py`, `surface='editor'`). Writing it
    into `mw_threads.current_state.huume_action` as a `schedule_change` staged
    dict — the shape `schedule_skill.propose` produces, minted `confirm_id`
    included — means the confirm turn applies it exactly like a Huume-staged
    change: same `evaluate_huume_action` gate, same `execute_edit_proposal`
    rechecks, same audit row. A displaced staged action is cancelled so its
    proposal row / generation run cannot be applied later by accident.
    """
    from .schedule_batch import summarize_operations
    from .schedule_chat import edit_proposal_text
    from .schedule_review import build_review

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT s.location_id, s.week_start, s.user_id,
                       t.id AS thread_id, t.surface, t.status, t.current_state, t.version
                FROM schedule_assistant_sessions s
                JOIN mw_threads t ON t.id=s.thread_id
                WHERE s.id=$1 AND s.company_id=$2
                FOR UPDATE OF t
                """,
                session_id, company_id,
            )
            if (
                not row
                or row["surface"] != "schedule_assistant"
                or row["user_id"] != user_id
                or row["status"] == "archived"
            ):
                raise HTTPException(status_code=404, detail="Schedule assistant session not found")
            await _assert_manager_location(
                conn, company_id=company_id, user_id=user_id,
                actor_role=actor_role, location_id=row["location_id"],
            )
            proposal_row = await conn.fetchrow(
                """
                SELECT id, created_by, status, proposal, parse
                FROM schedule_chat_proposals
                WHERE id=$1 AND company_id=$2
                """,
                proposal_id, company_id,
            )
            if not proposal_row:
                raise HTTPException(status_code=404, detail="That fill preview was not found")
            if proposal_row["created_by"] != user_id:
                raise HTTPException(status_code=403, detail="Only the person who previewed this fill can stage it")
            if proposal_row["status"] != "proposed":
                raise HTTPException(status_code=409, detail="That fill preview was already applied or discarded")
            proposal = _coerce_jsonb(proposal_row["proposal"])
            parse = _coerce_jsonb(proposal_row["parse"])
            if proposal.get("surface") != "editor" or proposal.get("kind") != "edit":
                raise HTTPException(status_code=400, detail="That proposal is not an editor fill preview")
            if (
                str(parse.get("editor_location_id") or "") != str(row["location_id"])
                or str(parse.get("editor_week_start") or "") != row["week_start"].isoformat()
            ):
                raise HTTPException(
                    status_code=409,
                    detail="That fill preview belongs to a different location or week than this chat",
                )

            review = build_review(proposal, proposal_id=str(proposal_id))
            staged_ops = [item for item in review["assignments"] if item.get("verdict") != "blocked"]
            staged = {
                "type": "schedule_change",
                "status": "proposed",
                "confirm_id": uuid4().hex[:8],
                "kind": "assign",
                "proposal_id": str(proposal_id),
                # The scenario came from the strip, not a chat ask — say so
                # rather than echoing the preview route's "Got it.".
                "pill_text": edit_proposal_text({**proposal, "ack": "Staged from the scenarios strip."}),
                "operation_count": len(staged_ops),
                "operation_summary": summarize_operations([{"kind": item.get("op")} for item in staged_ops], []),
                "review": review,
                "rejected_count": len(review["rejected"]),
                "unfilled_count": len(review["unfilled"]),
                "compliance_status": review["compliance_status"],
                "location_id": str(row["location_id"]),
                "label": parse.get("label"),
                "adopted_from": "editor_scenario",
            }

            current_state = _coerce_jsonb(row["current_state"])
            displaced = current_state.get("huume_action")
            if isinstance(displaced, dict) and displaced.get("status") == "proposed":
                if displaced.get("type") == "schedule_change" and displaced.get("proposal_id") \
                        and str(displaced["proposal_id"]) != str(proposal_id):
                    try:
                        displaced_id = UUID(str(displaced["proposal_id"]))
                    except (TypeError, ValueError):
                        displaced_id = None
                    if displaced_id is not None:
                        await conn.execute(
                            """UPDATE schedule_chat_proposals
                               SET status='cancelled', updated_at=NOW()
                               WHERE id=$1 AND company_id=$2 AND status='proposed'""",
                            displaced_id, company_id,
                        )
                elif displaced.get("type") == "schedule_week_draft" and displaced.get("generation_run_id"):
                    try:
                        run_id = UUID(str(displaced["generation_run_id"]))
                    except (TypeError, ValueError):
                        run_id = None
                    if run_id is not None:
                        await conn.execute(
                            """UPDATE schedule_generation_runs
                               SET status='cancelled', updated_at=NOW()
                               WHERE id=$1 AND company_id=$2 AND status='proposed'""",
                            run_id, company_id,
                        )
            next_state = {key: value for key, value in current_state.items() if key != "huume_choice"}
            next_state["huume_action"] = staged
            next_version = int(row["version"] or 0) + 1
            await conn.execute(
                """UPDATE mw_threads
                   SET current_state=$1::jsonb, version=$2, updated_at=NOW()
                   WHERE id=$3""",
                json.dumps(next_state, default=str), next_version, row["thread_id"],
            )
    return {"current_state": next_state, "version": next_version, "confirm_id": staged["confirm_id"]}


def _session_title(first_user_content: str | None) -> str:
    """Name a chat after what the manager actually asked in it.

    A turn carries the editor's appended selected-shift context after a blank
    line; the manager's own sentence is the first line of it.
    """
    if not first_user_content:
        return "New chat"
    lines = first_user_content.strip().splitlines()
    line = lines[0].strip() if lines else ""
    if not line:
        return "New chat"
    if len(line) <= _TITLE_MAX_CHARS:
        return line
    return line[: _TITLE_MAX_CHARS - 1].rstrip() + "…"


async def list_schedule_assistant_sessions(
    *,
    company_id: UUID,
    user_id: UUID,
    actor_role: str,
    location_id: UUID,
    week_start: date,
    limit: int = 30,
) -> dict:
    """This manager's own prior chats for one location/week, newest first."""
    async with get_connection() as conn:
        await _assert_manager_location(
            conn,
            company_id=company_id,
            user_id=user_id,
            actor_role=actor_role,
            location_id=location_id,
        )
        rows = await conn.fetch(
            """
            SELECT s.id, s.thread_id, s.created_at,
                   first_turn.content AS first_content,
                   activity.message_count,
                   COALESCE(activity.last_at, s.created_at) AS last_activity_at
            FROM schedule_assistant_sessions s
            JOIN mw_threads t ON t.id=s.thread_id
            LEFT JOIN LATERAL (
                SELECT m.content FROM mw_messages m
                WHERE m.thread_id=s.thread_id AND m.role='user'
                ORDER BY m.created_at ASC, m.id ASC
                LIMIT 1
            ) first_turn ON true
            LEFT JOIN LATERAL (
                SELECT MAX(m.created_at) AS last_at, COUNT(*) AS message_count
                FROM mw_messages m WHERE m.thread_id=s.thread_id
            ) activity ON true
            WHERE s.company_id=$1 AND s.user_id=$2 AND s.location_id=$3
              AND s.week_start=$4 AND t.status <> 'archived'
            ORDER BY COALESCE(activity.last_at, s.created_at) DESC, s.created_at DESC
            LIMIT $5
            """,
            company_id,
            user_id,
            location_id,
            week_start,
            limit,
        )
    return {
        "sessions": [
            {
                "session_id": str(row["id"]),
                "thread_id": str(row["thread_id"]),
                "title": _session_title(row["first_content"]),
                "message_count": int(row["message_count"] or 0),
                "created_at": row["created_at"].isoformat(),
                "last_activity_at": row["last_activity_at"].isoformat(),
            }
            for row in rows
        ]
    }


async def archive_schedule_assistant_session(
    *,
    company_id: UUID,
    user_id: UUID,
    actor_role: str,
    session_id: UUID,
) -> dict:
    """Hide one chat from the manager's history.

    The thread is archived, never deleted: its Huume runs are the audit trail
    behind schedule writes that were actually applied.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT s.id, s.thread_id, s.location_id
                FROM schedule_assistant_sessions s
                WHERE s.id=$1 AND s.company_id=$2 AND s.user_id=$3
                """,
                session_id,
                company_id,
                user_id,
            )
            if not row:
                raise HTTPException(
                    status_code=404, detail="Schedule assistant session not found"
                )
            await _assert_manager_location(
                conn,
                company_id=company_id,
                user_id=user_id,
                actor_role=actor_role,
                location_id=row["location_id"],
            )
            await conn.execute(
                """UPDATE mw_threads SET status='archived', updated_at=NOW()
                   WHERE id=$1""",
                row["thread_id"],
            )
    return {"session_id": str(session_id), "archived": True}


async def get_automatic_suggestion_status(
    *, company_id: UUID, user_id: UUID, actor_role: str,
    location_id: UUID, week_start: date,
) -> dict:
    """Tell the editor whether a background-built proposal awaits review."""
    async with get_connection() as conn:
        await _assert_manager_location(
            conn,
            company_id=company_id,
            user_id=user_id,
            actor_role=actor_role,
            location_id=location_id,
        )
        row = await conn.fetchrow(
            """
            SELECT id, week_start, created_at
            FROM schedule_generation_runs
            WHERE company_id=$1 AND location_id=$2
              AND origin='automatic' AND status='proposed'
              AND week_start >= CURRENT_DATE
            ORDER BY (week_start=$3) DESC, week_start, created_at DESC
            LIMIT 1
            """,
            company_id, location_id, week_start,
        )
    return {
        "available": bool(row),
        "generation_run_id": str(row["id"]) if row else None,
        "week_start": row["week_start"].isoformat() if row else None,
        "created_at": row["created_at"].isoformat() if row else None,
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
        # An archived chat is gone from the manager's history, so it must not
        # keep taking turns (and staging schedule writes) behind their back.
        if (
            not row
            or row["surface"] != "schedule_assistant"
            or row["user_id"] != user_id
            or row["status"] == "archived"
        ):
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
