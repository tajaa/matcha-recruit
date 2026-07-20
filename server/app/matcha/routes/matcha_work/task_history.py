"""Task history timeline, weekly board replay, and the project activity feed.

Split out of `tasks.py` (2026-07-19). Handlers moved verbatim -- no path,
signature, or response-shape change.
"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_company_member
from app.matcha.routes.matcha_work._shared import (
    _parse_task_attachment_ids,
    _verify_project_access,
)

router = APIRouter()

def _serialize_history_row(r) -> dict:
    d = dict(r)
    for k in ("id", "task_id", "actor_user_id"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    if d.get("created_at") is not None:
        d["created_at"] = d["created_at"].isoformat()
    if isinstance(d.get("metadata"), str):
        import json as _json
        try:
            d["metadata"] = _json.loads(d["metadata"])
        except Exception:
            d["metadata"] = {}
    # Surface attachment_ids at the top level so the Swift decoder sees a
    # flat field. Storage stays inside metadata JSONB (no schema change),
    # but the client should not have to introspect the metadata dict.
    meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
    raw_ids = meta.get("attachment_ids") if isinstance(meta, dict) else None
    if isinstance(raw_ids, list):
        d["attachment_ids"] = [str(x) for x in raw_ids]
    return d

@router.get("/projects/{project_id}/tasks/{task_id}/history")
async def get_task_history_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Audit-trail timeline for one task — who/when at each transition."""
    await _verify_project_access(project_id, current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT h.id, h.task_id, h.event_type, h.from_value, h.to_value,
                   h.metadata, h.created_at, h.actor_user_id,
                   COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS actor_name,
                   u.avatar_url AS actor_avatar_url
            FROM mw_task_history h
            LEFT JOIN users u ON u.id = h.actor_user_id
            LEFT JOIN clients c ON c.user_id = h.actor_user_id
            LEFT JOIN employees e ON e.user_id = h.actor_user_id
            LEFT JOIN admins a ON a.user_id = h.actor_user_id
            WHERE h.task_id = $1
            ORDER BY h.created_at ASC
            """,
            task_id,
        )
    return [_serialize_history_row(r) for r in rows]

@router.get("/projects/{project_id}/history/replay")
async def get_project_history_replay_endpoint(
    project_id: UUID,
    week_start: datetime = Query(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Weekly Work Replay data: the board's column state as of `week_start`
    (Monday 00:00 Pacific, computed client-side) plus every history event
    within that 7-day window, ascending — enough for the client to fold
    forward and animate a time-lapse. `week_end` is always exactly 7 days
    after `week_start`.

    Only 'created'/'column_change'/'review_rejected'/'review_approved' are
    board-column-mutating events (verified: reject/approve are logged by
    dedicated code paths that don't also emit a separate column_change, so
    these 4 are the complete non-overlapping set — see project_task_service.py
    reject_project_task/approve_project_task). Non-board events (comments,
    subtasks, etc.) are still returned in `events` for potential future
    flavor text, but the replay engine only acts on the 5 above (+ 'deleted').
    """
    await _verify_project_access(project_id, current_user)
    week_end = week_start + timedelta(days=7)

    _COLUMN_EVENTS = "'created', 'column_change', 'review_rejected', 'review_approved'"

    # Group by the durable text copy, falling back to the live FK for any
    # pre-migration row that predates task_id_text being stamped. Once a task
    # is hard-deleted, task_id (the FK) is nulled on EVERY row for that task
    # (ON DELETE SET NULL cascades across all referencing rows at once, not
    # just the delete event) — with 2+ deleted tasks that collapses them all
    # into one indistinguishable NULL bucket. task_id_text has no FK so it
    # survives deletion and keeps each task's timeline separate.
    #
    # Rows written before mwtaskhtxt01 whose task was later hard-deleted have
    # BOTH columns null — their identity is unrecoverable, and DISTINCT ON
    # merges every such task into one phantom card. Exclude them: a null key
    # is not addressable by the replay engine, and emitting it as a card
    # breaks the client's decode of the whole week.
    _task_key = "COALESCE(h.task_id_text, h.task_id::text)"

    async with get_connection() as conn:
        starting_rows = await conn.fetch(
            f"""
            SELECT DISTINCT ON ({_task_key})
                   {_task_key} AS task_key, h.to_value AS column_key,
                   COALESCE(t.title, h.metadata->>'title') AS title,
                   COALESCE(ac.name, CONCAT(ae.first_name, ' ', ae.last_name), aa.name) AS assignee_name,
                   au.avatar_url AS assignee_avatar_url
            FROM mw_task_history h
            LEFT JOIN mw_tasks t ON t.id = h.task_id
            LEFT JOIN users au ON au.id = t.assigned_to
            LEFT JOIN clients ac ON ac.user_id = t.assigned_to
            LEFT JOIN employees ae ON ae.user_id = t.assigned_to
            LEFT JOIN admins aa ON aa.user_id = t.assigned_to
            WHERE h.project_id = $1
              AND h.created_at < $2
              AND h.event_type IN ({_COLUMN_EVENTS})
              AND {_task_key} IS NOT NULL
            ORDER BY {_task_key}, h.created_at DESC
            """,
            project_id, week_start,
        )
        event_rows = await conn.fetch(
            f"""
            SELECT h.id, {_task_key} AS task_key, h.event_type, h.from_value, h.to_value,
                   h.created_at, h.actor_user_id,
                   COALESCE(t.title, h.metadata->>'title') AS title,
                   COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS actor_name,
                   u.avatar_url AS actor_avatar_url
            FROM mw_task_history h
            LEFT JOIN mw_tasks t ON t.id = h.task_id
            LEFT JOIN users u ON u.id = h.actor_user_id
            LEFT JOIN clients c ON c.user_id = h.actor_user_id
            LEFT JOIN employees e ON e.user_id = h.actor_user_id
            LEFT JOIN admins a ON a.user_id = h.actor_user_id
            WHERE h.project_id = $1
              AND h.created_at >= $2 AND h.created_at < $3
              AND {_task_key} IS NOT NULL
            ORDER BY h.created_at ASC
            """,
            project_id, week_start, week_end,
        )

    starting_state = [
        {
            "task_id": r["task_key"],
            "title": r["title"] or "Untitled",
            "column": r["column_key"],
            "assignee_name": r["assignee_name"],
            "assignee_avatar_url": r["assignee_avatar_url"],
        }
        for r in starting_rows
        # A task whose latest pre-week event was 'deleted' shouldn't seed the
        # board — but 'deleted' isn't in _COLUMN_EVENTS so it never wins the
        # DISTINCT ON in the first place; this filter is a no-op safeguard.
        if r["column_key"] is not None
        # The Done column resets every week. Seeding it with everything ever
        # finished makes it the all-time completed list — it only grows, dwarfs
        # the other columns, and buries the week's actual finishes. A replayed
        # week shows what THIS week finished, so work closed earlier doesn't
        # seed the board at all. (A card reopened out of Done mid-week still
        # appears: the client materializes it from the move event.)
        and r["column_key"] != "done"
    ]
    events = [
        {
            "id": str(r["id"]),
            "task_id": r["task_key"],
            "event_type": r["event_type"],
            "from_column": r["from_value"],
            "to_column": r["to_value"],
            "actor_id": str(r["actor_user_id"]) if r["actor_user_id"] else None,
            "actor_name": r["actor_name"],
            "actor_avatar_url": r["actor_avatar_url"],
            "title": r["title"] or "Untitled",
            "created_at": r["created_at"].isoformat(),
        }
        for r in event_rows
    ]
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "starting_state": starting_state,
        "events": events,
    }
@router.post("/projects/{project_id}/tasks/{task_id}/activity", status_code=201)
async def log_task_activity_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Log a sales follow-up activity (call/email/note/meeting) onto a task's
    history timeline so collaborators see the deal's touchpoints.

    Optional `attachment_ids` links the note to existing mw_project_files
    rows for this task (each must already be uploaded via the /files endpoint
    and own `task_id == task_id`). Stored in metadata JSONB; surfaced back
    out as a top-level field on history-row responses.
    """
    from app.matcha.services import project_task_service as pt_svc

    await _verify_project_access(project_id, current_user)

    # All ids must belong to mw_project_files rows for THIS task — never
    # store a dangling or cross-task ref.
    attachment_ids = await _parse_task_attachment_ids(task_id, body.get("attachment_ids") or [])

    reply_to: Optional[UUID] = None
    raw_reply = body.get("reply_to")
    if raw_reply:
        try:
            reply_to = UUID(str(raw_reply))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="reply_to must be a valid UUID")

    try:
        result = await pt_svc.log_task_activity(
            project_id=project_id,
            task_id=task_id,
            actor_user_id=current_user.id,
            kind=body.get("kind", "note"),
            body=body.get("body"),
            attachment_ids=attachment_ids or None,
            reply_to=reply_to,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result

def _serialize_activity_row(r) -> dict:
    d = dict(r)
    if d.get("actor_user_id") is not None:
        d["actor_user_id"] = str(d["actor_user_id"])
    if d.get("created_at") is not None:
        d["created_at"] = d["created_at"].isoformat()
    if isinstance(d.get("payload"), str):
        import json as _json
        try:
            d["payload"] = _json.loads(d["payload"])
        except Exception:
            d["payload"] = {}
    return d

@router.get("/projects/{project_id}/activity")
async def get_project_activity_endpoint(
    project_id: UUID,
    limit: int = 50,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Cross-domain activity feed for the Overview tab.

    UNIONs:
    - `mw_task_history` (task lifecycle events — created / column_change / assignee_change / deleted)
    - `mw_project_files` (uploads)
    - `mw_project_collaborators` (new members)

    Newest-first, capped at `limit`.
    """
    await _verify_project_access(project_id, current_user)
    limit = max(1, min(int(limit), 100))
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            WITH events AS (
                SELECT 'task_history'::text AS source, h.created_at, h.actor_user_id,
                       jsonb_build_object(
                         'event_type', h.event_type,
                         'task_id', h.task_id,
                         'task_title', COALESCE(t.title, h.metadata->>'title'),
                         'from_value', h.from_value,
                         'to_value', h.to_value
                       ) AS payload
                FROM mw_task_history h
                LEFT JOIN mw_tasks t ON t.id = h.task_id
                WHERE h.project_id = $1

                UNION ALL

                SELECT 'file_upload'::text, f.created_at, f.uploaded_by,
                       jsonb_build_object(
                         'file_id', f.id::text,
                         'filename', f.filename,
                         'task_id', f.task_id::text
                       )
                FROM mw_project_files f
                WHERE f.project_id = $1

                UNION ALL

                SELECT 'collaborator_added'::text, pc.created_at, pc.invited_by,
                       jsonb_build_object(
                         'user_id', pc.user_id::text,
                         'role', pc.role
                       )
                FROM mw_project_collaborators pc
                WHERE pc.project_id = $1 AND pc.status = 'active'
            )
            SELECT e.source, e.created_at, e.actor_user_id, e.payload,
                   COALESCE(c.name, CONCAT(em.first_name, ' ', em.last_name), a.name, u.email) AS actor_name
            FROM events e
            LEFT JOIN users u ON u.id = e.actor_user_id
            LEFT JOIN clients c ON c.user_id = e.actor_user_id
            LEFT JOIN employees em ON em.user_id = e.actor_user_id
            LEFT JOIN admins a ON a.user_id = e.actor_user_id
            ORDER BY e.created_at DESC
            LIMIT $2
            """,
            project_id, limit,
        )
    return [_serialize_activity_row(r) for r in rows]
