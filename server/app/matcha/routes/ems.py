"""EMS (Event Management System) router — review + promote "@huume"-logged
channel events. Mounted under /ems, gated on the `ems` feature flag at
mount time (see routes/__init__.py); promotion additionally requires
`incidents` (checked in evaluate_promote, not at mount, since a company can
have ems without incidents).
"""

import json
import logging
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.core.dependencies import get_current_user
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ems import (
    EmsEventAssignmentCreateRequest, EmsEventAssignmentListResponse,
    EmsEventAssignmentOut,
    EmsEventDraftOut, EmsEventDraftRejectRequest, EmsEventListResponse,
    EmsEventOut, EmsEventResolveRequest, EmsEventUpdate, EmsProtocolOut,
    EmsProtocolUpdate, PromoteRequest, PromoteResponse,
)
from app.matcha.services.ems import categories
from app.matcha.services.ems.event_drafts import (
    EventDraftConflict,
    EventDraftForbidden,
    EventDraftNotFound,
    confirm_event_draft,
    get_event_draft,
    may_decide_event_draft,
    reject_event_draft,
)
from app.matcha.services.ems.event_intake import coerce_doc
from app.matcha.services.ems.event_assignments import (
    EventAssignmentConflict,
    EventAssignmentForbidden,
    EventAssignmentNotFound,
    cancel_event_assignment,
    complete_event_assignment,
    create_event_assignment,
    get_event_assignment,
    list_event_assignments,
)
from app.matcha.services.ems.promote import PromoteRaceError, evaluate_promote, promote_event
from app.matcha.services.ems.queries import EVENT_SELECT as _EVENT_SELECT
from app.matcha.services.ems.resolution import (
    EventResolutionConflict,
    EventResolutionError,
    EventResolutionNotFound,
    resolve_event,
)
from app.matcha.services.scheduling.schedule_eligibility_events import (
    eligibility_event_mutation_error,
)
from app.matcha.services.ops.permissions import (
    OpsCapability,
    OpsPermissionDenied,
    assert_ops_capability,
    resolve_ops_access,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _row_to_event(row) -> EmsEventOut:
    doc = row["doc"]
    if isinstance(doc, str):
        doc = json.loads(doc) if doc else {}
    return EmsEventOut(**{**dict(row), "doc": doc or {}})


def _row_to_draft(row) -> EmsEventDraftOut:
    data = dict(row)
    data["classified"] = data.get("classified") or {}
    if isinstance(data["classified"], str):
        try:
            data["classified"] = json.loads(data["classified"])
        except (TypeError, ValueError):
            data["classified"] = {}
    return EmsEventDraftOut(**data)


def _row_to_assignment(row, *, current_user, access) -> EmsEventAssignmentOut:
    data = dict(row)
    data["assignee_name"] = data.get("assignee_name") or data.get("assignee_email") or "Teammate"
    data["can_complete"] = (
        data["status"] == "assigned"
        and (
            data["assignee_user_id"] == current_user.id
            or access.allows(OpsCapability.EVENT_ASSIGN)
        )
    )
    data["can_cancel"] = (
        data["status"] == "assigned"
        and access.allows(OpsCapability.EVENT_ASSIGN)
    )
    data["can_view_event"] = access.allows(OpsCapability.EVENT_REVIEW)
    return EmsEventAssignmentOut(**data)


async def _assignment_access(conn, assignment_id: UUID, current_user, *, allow_assignee=False):
    row = await get_event_assignment(conn, assignment_id=assignment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Event assignment not found")
    access = await resolve_ops_access(
        conn, user=current_user, company_id=row["company_id"]
    )
    is_member = await conn.fetchval(
        """
        SELECT 1 FROM channel_members
         WHERE channel_id = $1 AND user_id = $2
           AND removed_for_inactivity IS NOT TRUE
        """,
        row["channel_id"],
        current_user.id,
    )
    is_assignee = row["assignee_user_id"] == current_user.id
    if not is_member and not access.allows(OpsCapability.EVENT_ASSIGN) and not (allow_assignee and is_assignee):
        raise HTTPException(status_code=404, detail="Event assignment not found")
    return row, access


async def _draft_access(conn, draft_id: UUID, current_user):
    row = await conn.fetchrow(
        "SELECT company_id, reporter_user_id FROM ems_event_drafts WHERE id = $1",
        draft_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Event draft not found")
    access = await resolve_ops_access(
        conn, user=current_user, company_id=row["company_id"]
    )
    if not may_decide_event_draft(
        reporter_user_id=row["reporter_user_id"],
        actor_user_id=current_user.id,
        access=access,
    ):
        raise HTTPException(status_code=403, detail="Event draft access denied")
    return row["company_id"], access


@router.get("/events/{event_id}/assignments", response_model=EmsEventAssignmentListResponse)
async def list_event_assignments_route(
    event_id: UUID,
    current_user=Depends(get_current_user),
):
    async with get_connection() as conn:
        company_id = await conn.fetchval(
            "SELECT company_id FROM ems_events WHERE id = $1", event_id
        )
        if not company_id:
            raise HTTPException(status_code=404, detail="Event not found")
        access = await resolve_ops_access(conn, user=current_user, company_id=company_id)
        try:
            assert_ops_capability(access, OpsCapability.EVENT_ASSIGN)
        except OpsPermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        rows = await list_event_assignments(
            conn, event_id=event_id, company_id=company_id,
        )
    return EmsEventAssignmentListResponse(
        assignments=[_row_to_assignment(r, current_user=current_user, access=access) for r in rows]
    )


@router.post("/events/{event_id}/assignments", response_model=EmsEventAssignmentOut)
async def create_event_assignment_route(
    event_id: UUID,
    body: EmsEventAssignmentCreateRequest,
    current_user=Depends(get_current_user),
):
    async with get_connection() as conn:
        event = await conn.fetchrow(
            "SELECT company_id, source_kind FROM ems_events WHERE id = $1", event_id
        )
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        mutation_error = eligibility_event_mutation_error(event["source_kind"], action="assigned")
        if mutation_error:
            raise HTTPException(status_code=409, detail=mutation_error)
        company_id = event["company_id"]
        access = await resolve_ops_access(conn, user=current_user, company_id=company_id)
        try:
            async with conn.transaction():
                result = await create_event_assignment(
                    conn,
                    event_id=event_id,
                    actor_user_id=current_user.id,
                    access=access,
                    channel_id=body.channel_id,
                    assignee_user_id=body.assignee_user_id,
                    shared_title=body.shared_title,
                    instructions=body.instructions,
                    due_at=body.due_at,
                    client_request_id=body.client_request_id,
                )
        except OpsPermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except EventAssignmentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EventAssignmentForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except EventAssignmentConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=409, detail="This event assignment already exists") from exc

    assignment = result.assignment
    try:
        from app.matcha.services.matcha_work.project_task_notifications import (
            broadcast_channel_system_message,
        )
        await broadcast_channel_system_message(
            assignment["channel_id"],
            result.message,
            mentioned_user_ids=[str(assignment["assignee_user_id"])],
        )
    except Exception:
        logger.warning("Could not broadcast event assignment message %s", assignment["id"], exc_info=True)
    try:
        from app.matcha.services.matcha_work.project_task_notifications import broadcast_channel_action_updated
        await broadcast_channel_action_updated(
            assignment["channel_id"],
            {"kind": "event_assignment", "id": str(assignment["id"]), "status": "assigned"},
        )
    except Exception:
        logger.warning("Could not broadcast event assignment action %s", assignment["id"], exc_info=True)
    try:
        from app.matcha.services.matcha_work.project_task_notifications import notify_event_assignment
        await notify_event_assignment(
            assignment_id=assignment["id"],
            event_id=assignment["event_id"],
            company_id=assignment["company_id"],
            channel_id=assignment["channel_id"],
            channel_name=assignment["channel_name"] or "channel",
            message_id=assignment["message_id"],
            assignee_user_id=assignment["assignee_user_id"],
            assigned_by=assignment["assigned_by"],
            title=assignment["shared_title"],
        )
    except Exception:
        logger.warning("Could not notify event assignment %s", assignment["id"], exc_info=True)
    return _row_to_assignment(assignment, current_user=current_user, access=access)


@router.get("/event-assignments/{assignment_id}", response_model=EmsEventAssignmentOut)
async def get_event_assignment_route(
    assignment_id: UUID,
    current_user=Depends(get_current_user),
):
    async with get_connection() as conn:
        row, access = await _assignment_access(conn, assignment_id, current_user)
    return _row_to_assignment(row, current_user=current_user, access=access)


@router.post("/event-assignments/{assignment_id}/complete", response_model=EmsEventAssignmentOut)
async def complete_event_assignment_route(
    assignment_id: UUID,
    current_user=Depends(get_current_user),
):
    async with get_connection() as conn:
        _existing, access = await _assignment_access(
            conn, assignment_id, current_user, allow_assignee=True
        )
        try:
            async with conn.transaction():
                updated = await complete_event_assignment(
                    conn,
                    assignment_id=assignment_id,
                    actor_user_id=current_user.id,
                    access=access,
                )
        except OpsPermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except EventAssignmentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EventAssignmentForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except EventAssignmentConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        from app.matcha.services.matcha_work.project_task_notifications import broadcast_channel_action_updated
        await broadcast_channel_action_updated(
            updated["channel_id"],
            {"kind": "event_assignment", "id": str(assignment_id), "status": "completed"},
        )
    except Exception:
        logger.warning("Could not broadcast completed assignment %s", assignment_id, exc_info=True)
    try:
        from app.matcha.services.matcha_work.project_task_notifications import notify_event_assignment
        await notify_event_assignment(
            assignment_id=updated["id"],
            event_id=updated["event_id"],
            company_id=updated["company_id"],
            channel_id=updated["channel_id"],
            channel_name=updated["channel_name"] or "channel",
            message_id=updated["message_id"],
            assignee_user_id=updated["assignee_user_id"],
            assigned_by=updated["assigned_by"],
            title=updated["shared_title"],
            completed=True,
        )
    except Exception:
        logger.warning("Could not notify completed assignment %s", assignment_id, exc_info=True)
    return _row_to_assignment(updated, current_user=current_user, access=access)


@router.post("/event-assignments/{assignment_id}/cancel", response_model=EmsEventAssignmentOut)
async def cancel_event_assignment_route(
    assignment_id: UUID,
    current_user=Depends(get_current_user),
):
    async with get_connection() as conn:
        _existing, access = await _assignment_access(conn, assignment_id, current_user)
        try:
            async with conn.transaction():
                updated = await cancel_event_assignment(
                    conn,
                    assignment_id=assignment_id,
                    actor_user_id=current_user.id,
                    access=access,
                )
        except OpsPermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except EventAssignmentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EventAssignmentConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        from app.matcha.services.matcha_work.project_task_notifications import broadcast_channel_action_updated
        await broadcast_channel_action_updated(
            updated["channel_id"],
            {"kind": "event_assignment", "id": str(assignment_id), "status": "cancelled"},
        )
    except Exception:
        logger.warning("Could not publish cancelled assignment %s", assignment_id, exc_info=True)
    return _row_to_assignment(updated, current_user=current_user, access=access)


@router.get("/event-drafts/{draft_id}", response_model=EmsEventDraftOut)
async def get_event_draft_route(
    draft_id: UUID,
    current_user=Depends(get_current_user),
):
    async with get_connection() as conn:
        company_id, _access = await _draft_access(conn, draft_id, current_user)
        row = await get_event_draft(conn, draft_id=draft_id, company_id=company_id)
    if not row:
        raise HTTPException(status_code=404, detail="Event draft not found")
    return _row_to_draft(row)


@router.post("/event-drafts/{draft_id}/confirm", response_model=EmsEventOut)
async def confirm_event_draft_route(
    draft_id: UUID,
    current_user=Depends(get_current_user),
):
    async with get_connection() as conn:
        company_id, access = await _draft_access(conn, draft_id, current_user)
        try:
            async with conn.transaction():
                result = await confirm_event_draft(
                    conn,
                    draft_id=draft_id,
                    actor_user_id=current_user.id,
                    access=access,
                )
        except EventDraftNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EventDraftForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except EventDraftConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result.event:
        raise HTTPException(status_code=409, detail="Event draft has no event")
    try:
        from app.matcha.services.matcha_work.project_task_notifications import (
            broadcast_channel_action_updated,
        )
        await broadcast_channel_action_updated(
            result.draft["channel_id"],
            {"kind": "event_draft", "id": str(result.draft["id"]), "status": result.draft["status"]},
        )
    except Exception:
        logger.warning("Could not broadcast event draft confirmation %s", draft_id, exc_info=True)
    return _row_to_event(result.event)


@router.post("/event-drafts/{draft_id}/reject", response_model=EmsEventDraftOut)
async def reject_event_draft_route(
    draft_id: UUID,
    body: EmsEventDraftRejectRequest,
    current_user=Depends(get_current_user),
):
    async with get_connection() as conn:
        _company_id, access = await _draft_access(conn, draft_id, current_user)
        try:
            async with conn.transaction():
                result = await reject_event_draft(
                    conn,
                    draft_id=draft_id,
                    actor_user_id=current_user.id,
                    access=access,
                    reason=body.reason,
                )
        except EventDraftNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EventDraftForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except EventDraftConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        from app.matcha.services.matcha_work.project_task_notifications import (
            broadcast_channel_action_updated,
        )
        await broadcast_channel_action_updated(
            result.draft["channel_id"],
            {"kind": "event_draft", "id": str(result.draft["id"]), "status": result.draft["status"]},
        )
    except Exception:
        logger.warning("Could not broadcast event draft rejection %s", draft_id, exc_info=True)
    return _row_to_draft(result.draft)


@router.post("/events/{event_id}/resolve", response_model=EmsEventOut)
async def resolve_event_route(
    event_id: UUID,
    body: EmsEventResolveRequest,
    current_user=Depends(get_current_user),
):
    assignment_channels: list[tuple[UUID, UUID]] = []
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT company_id, source_kind FROM ems_events WHERE id = $1", event_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Event not found")
        mutation_error = eligibility_event_mutation_error(row["source_kind"], action="resolved")
        if mutation_error:
            raise HTTPException(status_code=409, detail=mutation_error)
        company_id = row["company_id"]
        access = await resolve_ops_access(
            conn, user=current_user, company_id=company_id
        )
        try:
            async with conn.transaction():
                await resolve_event(
                    conn,
                    company_id=company_id,
                    event_id=event_id,
                    actor_user_id=current_user.id,
                    access=access,
                    resolution=body.resolution,
                    note=body.note,
                    resolution_code=body.resolution_code,
                    duplicate_of_event_id=body.duplicate_of_event_id,
                )
                updated = await conn.fetchrow(
                    f"{_EVENT_SELECT} WHERE ev.id = $1 AND ev.company_id = $2",
                    event_id,
                    company_id,
                )
                assignment_channels = [
                    (row["channel_id"], row["id"])
                    for row in await conn.fetch(
                        """
                        SELECT id, channel_id FROM ems_event_assignments
                         WHERE event_id = $1 AND status = 'assigned'
                        """,
                        event_id,
                    )
                ]
        except OpsPermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except EventResolutionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EventResolutionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except EventResolutionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        from app.matcha.services.matcha_work.project_task_notifications import broadcast_channel_action_updated
        for channel_id, assignment_id in assignment_channels:
            await broadcast_channel_action_updated(
                channel_id,
                {"kind": "event_assignment", "id": str(assignment_id), "status": updated["status"]},
            )
    except Exception:
        logger.warning("Could not publish event assignment resolution for %s", event_id, exc_info=True)
    return _row_to_event(updated)


@router.get("/events", response_model=EmsEventListResponse)
async def list_events(
    status: Optional[str] = None,
    category: Optional[str] = None,
    channel_id: Optional[UUID] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    if status is not None and status not in ("logged", "completed", "promoted", "dismissed"):
        raise HTTPException(status_code=400, detail="Invalid status")
    if category is not None and category not in categories.ALL_KEYS:
        raise HTTPException(status_code=400, detail="Invalid category")

    where = ["ev.company_id = $1"]
    params: list = [company_id]
    if status:
        params.append(status)
        where.append(f"ev.status = ${len(params)}")
    if category:
        params.append(category)
        where.append(f"ev.category = ${len(params)}")
    if channel_id:
        params.append(channel_id)
        where.append(f"ev.channel_id = ${len(params)}")

    async with get_connection() as conn:
        access = await resolve_ops_access(
            conn, user=current_user, company_id=company_id,
        )
        try:
            assert_ops_capability(access, OpsCapability.EVENT_REVIEW)
        except OpsPermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM ems_events ev WHERE {' AND '.join(where)}", *params,
        )
        params_with_paging = [*params, limit, offset]
        rows = await conn.fetch(
            f"{_EVENT_SELECT} WHERE {' AND '.join(where)} "
            f"ORDER BY ev.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params_with_paging,
        )
    return EmsEventListResponse(events=[_row_to_event(r) for r in rows], total=total or 0)


@router.get("/events/{event_id}", response_model=EmsEventOut)
async def get_event(
    event_id: UUID,
    current_user=Depends(get_current_user),
):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"{_EVENT_SELECT} WHERE ev.id = $1", event_id,
        )
        if row:
            access = await resolve_ops_access(
                conn, user=current_user, company_id=row["company_id"],
            )
            try:
                assert_ops_capability(access, OpsCapability.EVENT_REVIEW)
            except OpsPermissionDenied as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return _row_to_event(row)


@router.put("/events/{event_id}", response_model=EmsEventOut)
async def update_event(
    event_id: UUID,
    body: EmsEventUpdate,
    current_user=Depends(get_current_user),
):
    sent = body.model_fields_set
    if "category" in sent and (
        body.category is None or body.category not in categories.ALL_KEYS
    ):
        # category is NOT NULL in ems_events — an explicit null is not a
        # "clear", it's invalid input (unlike the nullable true-PATCH columns).
        raise HTTPException(status_code=400, detail="Invalid category")

    dismiss_requested = "dismissed" in sent and bool(body.dismissed)
    assignment_channels: list[tuple[UUID, UUID]] = []

    async with get_connection() as conn:
        event = await conn.fetchrow(
            "SELECT company_id, source_kind FROM ems_events WHERE id = $1", event_id,
        )
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        mutation_error = eligibility_event_mutation_error(event["source_kind"], action="edited")
        if mutation_error:
            raise HTTPException(status_code=409, detail=mutation_error)
        company_id = event["company_id"]
        access = await resolve_ops_access(
            conn, user=current_user, company_id=company_id,
        )
        try:
            assert_ops_capability(access, OpsCapability.EVENT_RESOLVE)
        except OpsPermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if dismiss_requested:
            # A promoted event must not be silently flipped to dismissed
            # (it would leave a "dismissed" event pointing at a live IR
            # incident) — mirror promote_event's own status='logged' guard.
            current_status = await conn.fetchval(
                "SELECT status FROM ems_events WHERE id = $1 AND company_id = $2",
                event_id, company_id,
            )
            if current_status is None:
                raise HTTPException(status_code=404, detail="Event not found")
            if current_status != "logged":
                raise HTTPException(
                    status_code=409, detail=f"Event is already {current_status}, not logged.",
                )

        # Column/value pairs are appended as parameterized placeholders —
        # never string-sniffed — so a `title` of literally "NOW()" can't be
        # mistaken for the SQL literal used for dismissed_at below.
        set_parts: list[str] = []
        params: list = [event_id, company_id]

        def _set(column: str, value) -> None:
            params.append(value)
            set_parts.append(f"{column} = ${len(params)}")

        classification_edited = bool({"title", "category", "doc"} & sent)
        if "title" in sent:
            _set("title", body.title)
        if "category" in sent:
            _set("category", body.category)
        if "doc" in sent:
            _set("doc", json.dumps(coerce_doc(body.doc)))
        if classification_edited:
            # An admin's manual edit must win over a clarify answer that
            # arrives later — apply_refinement only rewrites classification
            # columns WHERE status='logged', not WHERE clarify_message_id IS
            # NULL, so a still-outstanding question would otherwise let a
            # stale reply silently overwrite this edit. Disarming it here
            # leaves the question as a dangling system-message pill (a
            # reply to it just falls through apply_refinement's atomic
            # claim as a miss) rather than a race the admin can lose.
            set_parts.append("clarify_message_id = NULL")
        if dismiss_requested:
            _set("status", "dismissed")
            _set("dismissed_by", current_user.id)
            set_parts.append("dismissed_at = NOW()")

        if set_parts:
            where = "WHERE id = $1 AND company_id = $2"
            if dismiss_requested:
                where += " AND status = 'logged'"
            updated = await conn.fetchval(
                f"UPDATE ems_events SET {', '.join(set_parts)}, updated_at = NOW() "
                f"{where} RETURNING id",
                *params,
            )
            if not updated:
                if dismiss_requested:
                    # Status flipped (promote/dismiss race) between the
                    # check above and this UPDATE.
                    raise HTTPException(
                        status_code=409,
                        detail="Event was promoted or dismissed by someone else — refresh and retry.",
                    )
                raise HTTPException(status_code=404, detail="Event not found")
            await conn.execute(
                "INSERT INTO ems_event_audit_log (event_id, user_id, action, details) "
                "VALUES ($1, $2, 'updated', $3::jsonb)",
                event_id, current_user.id, json.dumps({"fields": list(sent)}),
            )
        row = await conn.fetchrow(
            f"{_EVENT_SELECT} WHERE ev.id = $1 AND ev.company_id = $2", event_id, company_id,
        )
        if dismiss_requested:
            assignment_channels = [
                (assignment["channel_id"], assignment["id"])
                for assignment in await conn.fetch(
                    """
                    SELECT id, channel_id FROM ems_event_assignments
                     WHERE event_id = $1 AND status = 'assigned'
                    """,
                    event_id,
                )
            ]
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    if assignment_channels:
        try:
            from app.matcha.services.matcha_work.project_task_notifications import broadcast_channel_action_updated
            for channel_id, assignment_id in assignment_channels:
                await broadcast_channel_action_updated(
                    channel_id,
                    {"kind": "event_assignment", "id": str(assignment_id), "status": "dismissed"},
                )
        except Exception:
            logger.warning("Could not publish event assignment dismissal for %s", event_id, exc_info=True)
    return _row_to_event(row)


@router.post("/events/{event_id}/promote", response_model=PromoteResponse)
async def promote(
    event_id: UUID,
    body: PromoteRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    assignment_channels: list[tuple[UUID, UUID]] = []
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"{_EVENT_SELECT} WHERE ev.id = $1", event_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Event not found")
        event = dict(row)
        company_id = event["company_id"]
        access = await resolve_ops_access(
            conn, user=current_user, company_id=company_id,
        )
        try:
            assert_ops_capability(access, OpsCapability.EVENT_PROMOTE)
        except OpsPermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        from app.core.feature_flags import get_company_features
        features = await get_company_features(company_id, conn=conn)
        verdict = evaluate_promote(
            capabilities=access.capabilities,
            features=features,
            event_status=event["status"],
            source_kind=event.get("source_kind"),
        )
        if not verdict.ok:
            raise HTTPException(status_code=verdict.http_status, detail=verdict.reason)

        overrides = body.model_dump(exclude_unset=True)
        try:
            async with conn.transaction():
                incident_row, bg_tasks = await promote_event(
                    conn,
                    company_id=company_id,
                    event=event,
                    channel_name=event.get("channel_name"),
                    reporter_name=event.get("reporter_name"),
                    overrides=overrides,
                    actor_user_id=current_user.id,
                    actor_email=getattr(current_user, "email", None),
                )
                assignment_channels = [
                    (assignment["channel_id"], assignment["id"])
                    for assignment in await conn.fetch(
                        """
                        SELECT id, channel_id FROM ems_event_assignments
                         WHERE event_id = $1 AND status = 'assigned'
                        """,
                        event_id,
                    )
                ]
        except PromoteRaceError as e:
            raise HTTPException(status_code=409, detail=str(e))

    for fn, args, kwargs in bg_tasks:
        background_tasks.add_task(fn, *args, **kwargs)

    try:
        from app.matcha.services.matcha_work.project_task_notifications import broadcast_channel_action_updated
        for channel_id, assignment_id in assignment_channels:
            await broadcast_channel_action_updated(
                channel_id,
                {"kind": "event_assignment", "id": str(assignment_id), "status": "promoted"},
            )
    except Exception:
        logger.warning("Could not publish event assignment promotion for %s", event_id, exc_info=True)

    return PromoteResponse(incident_id=UUID(str(incident_row["id"])))


@router.get("/protocol", response_model=EmsProtocolOut)
async def get_protocol(
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """The company's event-protocol file; defaults when never saved (no
    bootstrap insert — mirrors onboarding notification-settings)."""
    from app.matcha.services.ems.protocols import fetch_protocol
    async with get_connection() as conn:
        row = await fetch_protocol(conn, company_id)
    if not row:
        return EmsProtocolOut()
    return EmsProtocolOut(**{k: row[k] for k in EmsProtocolOut.model_fields if k in row})


@router.put("/protocol", response_model=EmsProtocolOut)
async def put_protocol(
    body: EmsProtocolUpdate,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    from app.matcha.services.ems.protocols import upsert_protocol
    emails: list[str] = []
    seen: set[str] = set()
    for raw in body.notify_emails:
        e = (raw or "").strip()
        if not e:
            continue
        if "@" not in e or " " in e:
            raise HTTPException(status_code=400, detail=f"Invalid notify email: {e}")
        if e.lower() not in seen:
            seen.add(e.lower())
            emails.append(e)
    async with get_connection() as conn:
        row = await upsert_protocol(
            conn, company_id=company_id, updated_by=current_user.id,
            body={
                "notify_emails": emails,
                "notify_all_admins": body.notify_all_admins,
                "incident_definition": body.incident_definition.strip(),
                "culture_notes": body.culture_notes.strip(),
                "corrective_actions": body.corrective_actions.strip(),
            },
        )
    return EmsProtocolOut(**{k: row[k] for k in EmsProtocolOut.model_fields if k in row})
