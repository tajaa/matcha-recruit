"""Task history timeline, weekly board replay, and the project activity feed.

Split out of `tasks.py` (2026-07-19). Handlers moved verbatim -- no path,
signature, or response-shape change.
"""
import logging
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
    _verify_task_belongs_to_project,
)

logger = logging.getLogger(__name__)

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
    from app.matcha.services.matcha_work import project_task_service as pt_svc

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


@router.post(
    "/projects/{project_id}/tasks/{task_id}/autopr/reconsider",
    status_code=201,
)
async def request_autopr_reconsideration_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Submit evidence for one exact AutoPR context-blocked decision."""
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    await _verify_project_access(project_id, current_user)
    attachment_ids = await _parse_task_attachment_ids(
        task_id, body.get("attachment_ids") or []
    )
    try:
        result = await pt_svc.request_autopr_reconsideration(
            project_id=project_id,
            task_id=task_id,
            actor_user_id=current_user.id,
            expected_progress_note=body.get("expected_progress_note") or "",
            body=body.get("body"),
            attachment_ids=attachment_ids or None,
        )
    except pt_svc.AutoPRReconsiderationConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.post(
    "/projects/{project_id}/tasks/{task_id}/autopr/run-now",
    status_code=201,
)
async def request_autopr_run_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Queue this ticket for the next AutoPR pass instead of waiting for the clock."""
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    await _verify_project_access(project_id, current_user)
    try:
        result = await pt_svc.request_autopr_run(
            project_id=project_id,
            task_id=task_id,
            actor_user_id=current_user.id,
        )
    except pt_svc.AutoPRReconsiderationConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.post(
    "/projects/{project_id}/tasks/{task_id}/autopr/run-claim",
    status_code=201,
)
async def claim_autopr_run_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Consume a pending run request — posted by the harness as it starts work."""
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    await _verify_project_access(project_id, current_user)
    result = await pt_svc.claim_autopr_run(
        project_id=project_id,
        task_id=task_id,
        actor_user_id=current_user.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.get("/autopr/run-requests")
async def list_autopr_run_requests_endpoint(
    project_ids: str = Query(..., description="Comma-separated project ids"),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Pending "run now" requests for the given projects.

    The local dispatcher polls this every minute, so it stays a single bounded
    query rather than a board bundle. Access is verified per project, so the
    poller can never learn about a board it could not already open.
    """
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    raw = [p.strip() for p in (project_ids or "").split(",") if p.strip()]
    if not raw or len(raw) > 20:
        raise HTTPException(status_code=400, detail="project_ids must name 1-20 projects")
    try:
        parsed = [UUID(p) for p in raw]
    except ValueError:
        raise HTTPException(status_code=400, detail="project_ids must be UUIDs")
    for project_id in parsed:
        await _verify_project_access(project_id, current_user)
    return {"requests": await pt_svc.list_autopr_run_requests(parsed)}


@router.get("/projects/{project_id}/tasks/{task_id}/autopr/staged-actions")
async def list_autopr_staged_actions_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Outreach a run proposed on this card, with each item's outcome.

    Nothing here has been sent. `state` is `pending` until a person approves or
    dismisses that exact item.
    """
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)
    return {
        "actions": await pt_svc.list_autopr_staged_actions(
            project_id=project_id, task_id=task_id
        )
    }


@router.post("/projects/{project_id}/tasks/{task_id}/autopr/staged-actions", status_code=201)
async def stage_autopr_actions_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Record what a run proposed. Posted by the harness; sends nothing.

    Two checks, both in the service so they cannot be bypassed: the poster must
    be the AutoPR service account, and the board must hold the `outreach`
    grant. Project membership alone is not enough — this endpoint is what puts
    a one-click-sendable draft, labelled as the bot's work, in front of a
    colleague who will send it from their own mailbox.
    """
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)
    actions = body.get("actions")
    if not isinstance(actions, list):
        raise HTTPException(status_code=400, detail="actions must be a list")
    try:
        result = await pt_svc.stage_autopr_actions(
            project_id=project_id,
            task_id=task_id,
            actor_user_id=current_user.id,
            actions=actions,
        )
    except pt_svc.AutoPRActorNotPermitted as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except pt_svc.AutoPRReconsiderationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.post("/projects/{project_id}/tasks/{task_id}/autopr/staged-actions/{action_id}/send")
async def send_autopr_staged_action_endpoint(
    project_id: UUID,
    task_id: UUID,
    action_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Approve one staged email and send it, from the approver's own mailbox.

    Every guard is re-checked here, because this is the single point where
    model-drafted text leaves the building:

    * the board must still hold the `outreach` grant;
    * the action must still be unresolved (the outcome row is unique, so two
      concurrent approvals cannot both send);
    * the approver's Gmail must be connected — we never send as anyone else;
    * a per-approver hourly ceiling, because gmail_service's own limiter is
      per-instance and every request builds a fresh one.

    A `sending` claim is written BEFORE the send and the real outcome (`sent`
    or `failed`) is appended after it. The claim is what makes a second
    approval impossible while the first is in flight; writing `sent` up front
    instead — as this route once did — meant a send that threw was recorded as
    delivered forever, with `failed` unreachable and the mail never sent.
    A claim left with no outcome means the process died mid-send, which the
    card shows as interrupted rather than as delivered.
    """
    from app.core.services.platform_settings import board_has_autopr_capability
    from app.matcha.services.matcha_work import project_task_service as pt_svc
    from app.matcha.services.matcha_work.gmail_service import GmailService

    await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)

    if not await board_has_autopr_capability(project_id, "outreach"):
        raise HTTPException(
            status_code=403,
            detail="This board has not been granted the outreach capability",
        )

    action = await pt_svc.get_autopr_staged_action(
        project_id=project_id, task_id=task_id, action_id=action_id
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Staged action not found")
    if action["state"] != "pending":
        raise HTTPException(status_code=409, detail=f"This action was already {action['state']}")
    if action["kind"] not in pt_svc._SENDABLE_STAGED_ACTION_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"A {action['kind']} action is done by a person; mark it handled instead",
        )

    recent = await pt_svc.count_recent_staged_sends(actor_user_id=current_user.id)
    if recent >= pt_svc._STAGED_SEND_MAX_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"Hourly limit reached ({pt_svc._STAGED_SEND_MAX_PER_HOUR} approved sends per person)",
        )

    gmail = GmailService(current_user.id)
    await gmail.load_token()
    if not gmail.is_configured:
        raise HTTPException(
            status_code=400,
            detail="Connect your Gmail before approving a send — mail goes out from your own mailbox",
        )

    try:
        claimed = await pt_svc.resolve_autopr_staged_action(
            project_id=project_id,
            task_id=task_id,
            action_id=action_id,
            actor_user_id=current_user.id,
            state="sending",
            detail=f"to {action['to']}",
        )
    except pt_svc.AutoPRReconsiderationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if claimed is None:
        raise HTTPException(status_code=404, detail="Staged action not found")

    try:
        result = await gmail.send_email(
            to=action["to"], subject=action["subject"], body=action["body"]
        )
    except Exception as exc:
        # The claim is immutable, so the failure is its own row on top of it.
        # Recording it is what keeps the card honest; if even that write fails
        # the claim stands alone and reads as an interrupted send, which is
        # still true and still not a claim that mail went out.
        logger.warning("Staged action %s failed to send: %s", action_id, exc, exc_info=True)
        try:
            await pt_svc.record_autopr_staged_send_outcome(
                project_id=project_id,
                task_id=task_id,
                action_id=action_id,
                actor_user_id=current_user.id,
                state="failed",
                detail=str(exc),
            )
        except Exception:
            logger.exception("Could not record the failed send for staged action %s", action_id)
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}")

    recorded = await pt_svc.record_autopr_staged_send_outcome(
        project_id=project_id,
        task_id=task_id,
        action_id=action_id,
        actor_user_id=current_user.id,
        state="sent",
        detail=f"to {action['to']}",
    )
    return {
        "ok": True,
        "staged_action_id": str(action_id),
        "state": "sent",
        "message_id": result.get("id"),
        "to": action["to"],
        "resolved_at": (recorded or claimed)["resolved_at"],
    }


@router.post("/projects/{project_id}/tasks/{task_id}/autopr/staged-actions/{action_id}/resolve")
async def resolve_autopr_staged_action_endpoint(
    project_id: UUID,
    task_id: UUID,
    action_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Close a staged action without this system sending anything.

    `handled` = a person did it themselves; `dismissed` = it will not be done.
    `sent` is deliberately not accepted here: only the send route above may
    claim that mail actually went out.
    """
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)

    state = str(body.get("state") or "").strip().lower()
    if state not in ("handled", "dismissed"):
        raise HTTPException(status_code=400, detail="state must be handled or dismissed")
    try:
        result = await pt_svc.resolve_autopr_staged_action(
            project_id=project_id,
            task_id=task_id,
            action_id=action_id,
            actor_user_id=current_user.id,
            state=state,
            detail=body.get("detail"),
        )
    except pt_svc.AutoPRReconsiderationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Staged action not found")
    return result


@router.get("/autopr/board-capabilities")
async def list_autopr_board_capabilities_endpoint(
    project_ids: str = Query(..., description="Comma-separated project ids"),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Which AutoPR capabilities each named board has been granted.

    The harness reads this once per pass and refuses to run a capability the
    board was not granted. That refusal is a spend guard, not the security
    boundary: the acts these capabilities describe — sending an email, driving
    a browser — are each re-checked server-side at the moment they happen, so
    a stale or tampered harness copy cannot widen its own reach.
    """
    from app.core.services.platform_settings import get_autopr_board_capabilities

    raw = [p.strip() for p in (project_ids or "").split(",") if p.strip()]
    if not raw or len(raw) > 20:
        raise HTTPException(status_code=400, detail="project_ids must name 1-20 projects")
    try:
        parsed = [UUID(p) for p in raw]
    except ValueError:
        raise HTTPException(status_code=400, detail="project_ids must be UUIDs")
    for project_id in parsed:
        await _verify_project_access(project_id, current_user)
    grants = await get_autopr_board_capabilities()
    return {"capabilities": {str(p): grants.get(str(p), []) for p in parsed}}


@router.post(
    "/projects/{project_id}/tasks/{task_id}/autopr/context-request",
    status_code=201,
)
async def post_autopr_context_request_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Ask for decision-bound AutoPR context in the project's Espresso chat."""
    from app.matcha.services.matcha_work.project_task_notifications import (
        post_autopr_context_request,
    )

    await _verify_project_access(project_id, current_user)
    raw_reason = body.get("reason")
    raw_expected = body.get("expected_progress_note")
    if not isinstance(raw_reason, str) or not isinstance(raw_expected, str):
        raise HTTPException(status_code=400, detail="reason and expected_progress_note must be strings")
    reason = raw_reason.strip()
    expected = raw_expected.strip()
    # Long enough to carry per-criterion acceptance evidence. A card can name up
    # to 40 criteria of 500 characters each, and truncating that at 600 threw
    # away the very thing the human is being asked to look at.
    if not reason or len(reason) > 4000:
        raise HTTPException(status_code=400, detail="reason must be 1-4000 characters")
    try:
        posted = await post_autopr_context_request(
            project_id=project_id,
            task_id=task_id,
            actor_user_id=current_user.id,
            expected_progress_note=expected,
            reason=reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not posted:
        raise HTTPException(status_code=409, detail="The AutoPR decision or project chat changed")
    return {"ok": True}


@router.post(
    "/projects/{project_id}/tasks/{task_id}/autopr/result-notification",
    status_code=201,
)
async def post_autopr_result_notification_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Notify the author of the additional context about AutoPR's result."""
    from app.matcha.services.matcha_work.project_task_notifications import (
        post_autopr_result_notification,
    )

    await _verify_project_access(project_id, current_user)
    raw_event_id = body.get("reconsideration_event_id")
    raw_expected = body.get("expected_progress_note")
    raw_message = body.get("message")
    if not isinstance(raw_expected, str) or not isinstance(raw_message, str):
        raise HTTPException(
            status_code=400,
            detail="expected_progress_note and message must be strings",
        )
    try:
        event_id = UUID(str(raw_event_id))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="reconsideration_event_id must be a valid UUID",
        )
    expected = raw_expected.strip()
    message = raw_message.strip()
    if not message or len(message) > 1_600:
        raise HTTPException(status_code=400, detail="message must be 1-1600 characters")
    try:
        posted = await post_autopr_result_notification(
            project_id=project_id,
            task_id=task_id,
            reconsideration_event_id=event_id,
            expected_progress_note=expected,
            message=message,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not posted:
        raise HTTPException(
            status_code=409,
            detail="The AutoPR result or reconsideration event changed",
        )
    return {"ok": True}


@router.post(
    "/projects/{project_id}/tasks/{task_id}/autopr/pr-closed",
    status_code=200,
)
async def post_autopr_pr_closed_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Hand a card back to Todo after its own AutoPR draft was closed unmerged.

    The GitHub webhook already does exactly this; reconcile-merged-cards.sh is
    the catch-up path for a delivery the webhook missed. Both go through the
    same note rewrite here so a reconciled card cannot sit in Todo still
    claiming READY FOR REVIEW — a bash reimplementation of the structured-note
    parser would drift from the webhook the first time either changed.
    """
    from app.matcha.routes.matcha_work.github import _with_autopr_closed_note
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    await _verify_project_access(project_id, current_user)
    raw_pr_number = body.get("pr_number")
    if not isinstance(raw_pr_number, int) or isinstance(raw_pr_number, bool) \
            or raw_pr_number <= 0:
        raise HTTPException(status_code=400, detail="pr_number must be a positive integer")
    async with get_connection() as conn:
        task = await conn.fetchrow(
            """SELECT id, project_id, board_column, progress_note
                 FROM mw_tasks WHERE id = $1 AND project_id = $2""",
            task_id,
            project_id,
        )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["board_column"] not in ("in_progress", "changes_requested"):
        return {"ok": True, "moved": False}
    patch = {"board_column": "todo"}
    closed_note = _with_autopr_closed_note(
        task["progress_note"], pr_number=raw_pr_number,
    )
    if closed_note != task["progress_note"]:
        patch["progress_note"] = closed_note
    await pt_svc.update_project_task(project_id, task_id, patch)
    return {"ok": True, "moved": True}


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
