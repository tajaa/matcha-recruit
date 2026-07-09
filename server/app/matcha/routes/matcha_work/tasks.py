"""Project kanban tasks + subtasks, ticket drafts, task history/rounds/
activity/files, and research tasks (AI-driven browse-and-summarize inputs).

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile

from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, require_company_member, get_client_company_id
from app.matcha.routes.matcha_work.projects import ALLOWED_PROJECT_FILE_EXTENSIONS, PROJECT_FILE_MAX_BYTES
from app.matcha.routes.matcha_work._shared import (
    _can_edit_project,
    _project_company_id,
    _resolve_file_urls,
    _sse_data,
    _verify_project_access,
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.patch("/projects/{project_id}/pipeline-mode")
async def set_project_pipeline_mode_endpoint(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Toggle sales-pipeline mode for a collab project. Stored in
    mw_projects.project_data.pipeline_mode via a non-destructive merge so the
    board can render sales stages / deal fields. Other project_data keys are
    preserved."""
    from app.matcha.services import project_service as proj_svc

    await _verify_project_access(project_id, current_user)
    enabled = bool(body.get("enabled", False))
    return await proj_svc.update_project_data(project_id, {"pipeline_mode": enabled})

@router.get("/projects/{project_id}/tasks/done-count")
async def count_done_tasks_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """`{total, this_week}` for the Done column. The board needs the total to
    label its "show N finished earlier" expander, which the task list itself
    can't supply — it never returns the whole column."""
    from app.matcha.services import project_task_service as pt_svc
    await _verify_project_access(project_id, current_user)
    return await pt_svc.count_done_tasks(project_id)

@router.get("/projects/{project_id}/tasks")
async def list_project_tasks_endpoint(
    project_id: UUID,
    done_scope: str = Query("all", pattern="^(week|all)$"),
    current_user: CurrentUser = Depends(require_company_member),
):
    """List a project's kanban tasks. Embeds attachments per task so the kanban
    card can render thumbnails without N+1 follow-up requests.

    Every column comes back whole EXCEPT Done, which grows without bound as a
    project ages. `done_scope=week` returns only what was finished this Pacific
    week; `all` (the default) returns the most recently finished, capped at
    `DONE_MAX_ROWS`.

    The default is `all` so the web board — which doesn't ask for a scope and has
    no "show earlier" expander — keeps its cumulative Done column, now merely
    bounded rather than unbounded. The desktop board opens on `week` and
    re-requests `all` when the user expands Done."""
    from app.matcha.services import project_task_service as pt_svc
    from app.matcha.services import project_file_service
    await _verify_project_access(project_id, current_user)
    tasks = await pt_svc.list_project_tasks(project_id, viewer_id=current_user.id,
                                            done_scope=done_scope)
    if not tasks:
        return tasks
    task_ids = [UUID(t["id"]) for t in tasks if t.get("id")]
    grouped = await project_file_service.list_files_for_tasks(project_id, task_ids)
    for t in tasks:
        t["attachments"] = _resolve_file_urls(grouped.get(t["id"], []))
    return tasks

@router.post("/projects/{project_id}/tasks", status_code=201)
async def create_project_task_endpoint(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Create a kanban task in a project."""
    from datetime import date as _date
    from app.matcha.services import project_task_service as pt_svc

    project, _role = await _verify_project_access(project_id, current_user)

    def _opt_date(field):
        raw = body.get(field)
        if not raw:
            return None
        try:
            return _date.fromisoformat(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid {field}")

    def _opt_num(field, cast):
        v = body.get(field)
        if v is None or v == "":
            return None
        try:
            return cast(v)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid {field}")

    due_date = _opt_date("due_date")

    assigned_raw = body.get("assigned_to")
    assigned_to = UUID(assigned_raw) if assigned_raw else None

    try:
        result = await pt_svc.create_project_task(
            project_id=project_id,
            company_id=project["company_id"],
            created_by=current_user.id,
            title=body.get("title", ""),
            description=body.get("description"),
            board_column=body.get("board_column", "todo"),
            pipeline_column=body.get("pipeline_column", "lead"),
            priority=body.get("priority", "medium"),
            due_date=due_date,
            assigned_to=assigned_to,
            progress_note=body.get("progress_note"),
            project_title=project.get("title"),
            category=body.get("category", "manual"),
            element_id=body.get("element_id") or None,
            # Sales-pipeline fields (optional; NULL for normal tasks)
            deal_value=_opt_num("deal_value", float),
            probability=_opt_num("probability", int),
            contact_name=body.get("contact_name"),
            contact_company=body.get("contact_company"),
            contact_email=body.get("contact_email"),
            contact_phone=body.get("contact_phone"),
            outcome=body.get("outcome"),
            loss_reason=body.get("loss_reason"),
            next_action_at=_opt_date("next_action_at"),
            expected_close=_opt_date("expected_close"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Optional sub-task checklist (e.g. AI-drafted). Best-effort: create each in
    # order; a bad item is skipped rather than failing the whole task create.
    raw_subtasks = body.get("subtasks")
    if isinstance(raw_subtasks, list) and result.get("id"):
        from app.matcha.services import project_subtask_service as st_svc
        task_uuid = UUID(result["id"]) if isinstance(result["id"], str) else result["id"]
        created = 0
        for item in raw_subtasks[:50]:
            title = (item if isinstance(item, str) else "").strip()
            if not title:
                continue
            try:
                await st_svc.create_subtask(
                    project_id, task_uuid, title=title[:500], created_by=current_user.id
                )
                created += 1
            except ValueError:
                continue
        if created:
            # Surface counts on the returned task so the new card shows N/0
            # immediately, without waiting for a board reload.
            result["subtask_total"] = created
            result["subtask_done"] = 0

    return result

@router.patch("/projects/{project_id}/tasks/{task_id}")
async def update_project_task_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    """Partial update. Drag-drop updates board_column; checkbox updates status."""
    from datetime import date as _date
    from app.matcha.services import project_task_service as pt_svc

    project, _role = await _verify_project_access(project_id, current_user)

    patch: dict = {}
    for key in (
        "title", "description", "priority", "board_column", "pipeline_column",
        "status", "progress_note",
        # Sales-pipeline text fields
        "contact_name", "contact_company", "contact_email", "contact_phone",
        "outcome", "loss_reason",
    ):
        if key in body:
            patch[key] = body[key]

    # Sales-pipeline numeric fields — coerce so the asyncpg numeric/smallint
    # casts never receive a JSON string. Empty / null clears the value.
    for num_key, cast in (("deal_value", float), ("probability", int)):
        if num_key in body:
            v = body[num_key]
            if v is None or v == "":
                patch[num_key] = None
            else:
                try:
                    patch[num_key] = cast(v)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"Invalid {num_key}")

    # Date fields (due_date + sales follow-up dates). Empty / null clears.
    for date_key in ("due_date", "next_action_at", "expected_close"):
        if date_key in body:
            v = body[date_key]
            if v is None or v == "":
                patch[date_key] = None
            else:
                try:
                    patch[date_key] = _date.fromisoformat(v)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"Invalid {date_key}")

    if "assigned_to" in body:
        v = body["assigned_to"]
        patch["assigned_to"] = UUID(v) if v else None

    if "element_id" in body:
        patch["element_id"] = body["element_id"] or None

    try:
        result = await pt_svc.update_project_task(
            project_id,
            task_id,
            patch,
            actor_user_id=current_user.id,
            project_title=project.get("title"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result

@router.post("/projects/{project_id}/tasks/{task_id}/reject")
async def reject_project_task_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reviewer sends a task back for changes: bounce review → changes_requested,
    store the reason, and email the assignee. Requires the task to be in the
    review column and a non-empty note explaining what's incomplete.
    """
    from app.matcha.services import project_task_service as pt_svc

    project, _role = await _verify_project_access(project_id, current_user)

    note = (body.get("note") or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="A note explaining what's incomplete is required")

    try:
        result = await pt_svc.reject_project_task(
            project_id,
            task_id,
            note,
            actor_user_id=current_user.id,
            project_title=project.get("title"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result

@router.post("/projects/{project_id}/tasks/{task_id}/approve")
async def approve_project_task_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(default={}),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reviewer approves a task out of review → done, recording a `review_approved`
    sign-off (approver + timestamp + optional note). Requires the task in review."""
    from app.matcha.services import project_task_service as pt_svc

    project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")

    note = (body.get("note") or "").strip() or None
    try:
        result = await pt_svc.approve_project_task(
            project_id, task_id, note=note, actor_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result

@router.post("/projects/{project_id}/tasks/ai-draft")
async def ai_draft_task_endpoint(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Turn a natural-language request into a structured ticket draft (no DB
    write). The client reviews/edits, then creates via POST .../tasks."""
    from app.matcha.services import project_service as proj_svc
    from app.matcha.services import matcha_work_ai

    project, _role = await _verify_project_access(project_id, current_user)

    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Describe the task you want to create")

    # Rate limit: 50 AI drafts per user per rolling 24h (Redis fixed-window from
    # first call). Best-effort — a Redis hiccup never blocks drafting.
    from app.core.services.redis_cache import get_redis_cache
    _redis = get_redis_cache()
    if _redis is not None:
        try:
            _key = f"ai_draft_limit:{current_user.id}"
            _count = await _redis.incr(_key)
            if _count == 1:
                await _redis.expire(_key, 86400)
            if _count > 50:
                raise HTTPException(
                    status_code=429,
                    detail="Daily AI ticket limit reached (50 per 24 hours). Create tickets manually or try again later.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("AI draft rate-limit check failed (allowing): %s", e)

    collaborators = await proj_svc.list_collaborators(project_id)
    async with get_connection() as conn:
        element_rows = await conn.fetch(
            "SELECT id, name, description FROM mw_project_elements WHERE project_id = $1 ORDER BY \"order\" ASC, created_at ASC",
            str(project_id),
        )
        # Element context notes (one query, grouped client-side).
        note_rows = await conn.fetch(
            """SELECT element_id, kind, body, url FROM mw_element_notes
               WHERE project_id = $1 ORDER BY created_at DESC""",
            project_id,
        )
        # What the team finished this week — soft context for the draft.
        done_rows = await conn.fetch(
            """SELECT title FROM mw_tasks
               WHERE project_id = $1 AND status = 'completed'
                 AND completed_at >= NOW() - INTERVAL '7 days'
               ORDER BY completed_at DESC LIMIT 15""",
            project_id,
        )

    notes_by_element: dict[str, list[str]] = {}
    for r in note_rows:
        eid = str(r["element_id"])
        text = (r["url"] if r["kind"] == "link" else r["body"]) or ""
        text = text.strip()
        if text:
            notes_by_element.setdefault(eid, []).append(text)

    elements = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "description": r["description"],
            "notes": notes_by_element.get(str(r["id"]), []),
        }
        for r in element_rows
    ]
    recent_done = [r["title"] for r in done_rows if r["title"]]

    # Repo conventions (CLAUDE.md etc.) from the synced element snapshot — grounds
    # the model in this codebase so subtasks reference real files/migrations/tests.
    # "" when nothing is synced (graceful).
    from app.matcha.services import element_repo_service as repo_svc
    try:
        conventions = await repo_svc.fetch_convention_docs(project_id)
    except Exception:  # noqa: BLE001 — advisory context, never block a draft
        conventions = ""

    try:
        draft = await matcha_work_ai.generate_task_draft(
            prompt=prompt,
            project_title=project.get("title"),
            collaborator_names=[c["name"] for c in collaborators if c.get("name")],
            elements=elements,
            recent_done=recent_done,
            model_override=(body.get("model") or None),
            company_id=str(project.get("company_id")) if project.get("company_id") else None,
            user_id=str(current_user.id),
            conventions=conventions or None,
        )
    except Exception as e:
        logger.warning("AI task draft failed project=%s: %s", project_id, e)
        raise HTTPException(status_code=502, detail="Couldn't draft the task — try again")

    # Resolve assignee NAME → user_id (exact, then first-name / substring).
    assigned_to = None
    assigned_name = None
    if draft.get("assignee_name"):
        want = draft["assignee_name"].strip().lower()
        match = (
            next((c for c in collaborators if (c.get("name") or "").lower() == want), None)
            or next((c for c in collaborators if want and want in (c.get("name") or "").lower()), None)
            or next((c for c in collaborators if (c.get("name") or "").lower().split(" ")[0] == want), None)
        )
        if match:
            assigned_to = str(match["user_id"])
            assigned_name = match["name"]

    # Resolve element NAME → id (exact, then substring).
    element_id = None
    element_name = None
    if draft.get("element_name"):
        want = draft["element_name"].strip().lower()
        match = (
            next((e for e in elements if e["name"].lower() == want), None)
            or next((e for e in elements if want and want in e["name"].lower()), None)
        )
        if match:
            element_id = match["id"]
            element_name = match["name"]

    return {
        "title": draft["title"],
        "description": draft["description"],
        "priority": draft["priority"],
        "category": draft["category"],
        "board_column": draft["board_column"],
        "assigned_to": assigned_to,
        "assigned_name": assigned_name,
        "element_id": element_id,
        "element_name": element_name,
        "subtasks": draft.get("subtasks", []),
    }

@router.delete("/projects/{project_id}/tasks/{task_id}")
async def delete_project_task_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    from app.matcha.services import project_task_service as pt_svc
    await _verify_project_access(project_id, current_user)
    if not await pt_svc.delete_project_task(
        project_id, task_id, actor_user_id=current_user.id
    ):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}

@router.get("/projects/{project_id}/tasks/{task_id}/subtasks")
async def list_task_subtasks_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    from app.matcha.services import project_subtask_service as st_svc
    await _verify_project_access(project_id, current_user)
    rows = await st_svc.list_subtasks(project_id, task_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return rows

@router.post("/projects/{project_id}/tasks/{task_id}/subtasks")
async def create_task_subtask_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    from app.matcha.services import project_subtask_service as st_svc
    await _verify_project_access(project_id, current_user)
    assigned_raw = body.get("assigned_to")
    try:
        row = await st_svc.create_subtask(
            project_id,
            task_id,
            title=body.get("title", ""),
            created_by=current_user.id,
            assigned_to=UUID(assigned_raw) if assigned_raw else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return row

@router.patch("/projects/{project_id}/tasks/{task_id}/subtasks/{subtask_id}")
async def update_task_subtask_endpoint(
    project_id: UUID,
    task_id: UUID,
    subtask_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    from app.matcha.services import project_subtask_service as st_svc
    await _verify_project_access(project_id, current_user)

    patch: dict = {}
    if "is_done" in body:
        patch["is_done"] = bool(body["is_done"])
    if "title" in body:
        patch["title"] = body["title"]
    if "position" in body:
        try:
            patch["position"] = int(body["position"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid position")
    if "assigned_to" in body:
        v = body["assigned_to"]
        patch["assigned_to"] = UUID(v) if v else None

    # A reviewer denying a completed item (is_done=false + reason) logs a
    # `subtask_rejected` audit event instead of a plain uncheck. `severity`
    # (blocker|nit) rides in the same event metadata.
    reason = body.get("reason") if isinstance(body.get("reason"), str) else None
    severity = body.get("severity") if body.get("severity") in ("blocker", "nit") else None

    try:
        row = await st_svc.update_subtask(
            project_id, task_id, subtask_id, patch,
            actor_user_id=current_user.id, reason=reason, severity=severity,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Subtask not found")

    # Review denial (reopen + reason): overturn any accepted commit→completion
    # for this subtask, so the card stops crediting that commit and the same
    # commit won't silently re-auto-check it.
    if reason and patch.get("is_done") is False:
        from app.matcha.services import commit_scan_service as cs_svc
        await cs_svc.dismiss_accepted_for_subtask(
            project_id, subtask_id, actor_user_id=current_user.id,
        )
    return row

@router.delete("/projects/{project_id}/tasks/{task_id}/subtasks/{subtask_id}")
async def delete_task_subtask_endpoint(
    project_id: UUID,
    task_id: UUID,
    subtask_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    from app.matcha.services import project_subtask_service as st_svc
    await _verify_project_access(project_id, current_user)
    if not await st_svc.delete_subtask(
        project_id, task_id, subtask_id,
        actor_user_id=current_user.id,
    ):
        raise HTTPException(status_code=404, detail="Subtask not found")
    return {"deleted": True}

@router.get("/projects/{project_id}/ticket-drafts")
async def list_ticket_drafts_endpoint(
    project_id: UUID,
    status: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    return await td_svc.list_drafts(project_id, status)

@router.post("/projects/{project_id}/ticket-drafts", status_code=201)
async def create_ticket_draft_endpoint(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = _project_company_id(project) or await get_client_company_id(current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="No company context")
    from app.matcha.services import ticket_draft_service as td_svc
    try:
        return await td_svc.create_draft(
            project_id, company_id, current_user.id,
            kind=body.get("kind") or "feat",
            title=(body.get("title") or None),
            element_id=body.get("element_id") or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/projects/{project_id}/ticket-drafts/{draft_id}")
async def get_ticket_draft_endpoint(
    project_id: UUID,
    draft_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    draft = await td_svc.get_draft(project_id, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft

@router.patch("/projects/{project_id}/ticket-drafts/{draft_id}")
async def update_ticket_draft_endpoint(
    project_id: UUID,
    draft_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    draft = await td_svc.update_draft(project_id, draft_id, body)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft

@router.delete("/projects/{project_id}/ticket-drafts/{draft_id}")
async def delete_ticket_draft_endpoint(
    project_id: UUID,
    draft_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    if not await td_svc.delete_draft(project_id, draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"deleted": True}

@router.get("/projects/{project_id}/ticket-drafts/{draft_id}/messages")
async def list_ticket_draft_messages_endpoint(
    project_id: UUID,
    draft_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    return await td_svc.list_messages(project_id, draft_id)

@router.post("/projects/{project_id}/ticket-drafts/{draft_id}/messages")
async def post_ticket_draft_message_endpoint(
    project_id: UUID,
    draft_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = _project_company_id(project) or await get_client_company_id(current_user)
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    from app.matcha.services import ticket_draft_service as td_svc
    result = await td_svc.chat(
        project_id, draft_id, company_id, user_content=content, actor_user_id=current_user.id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Draft not found")
    return result

@router.post("/projects/{project_id}/ticket-drafts/{draft_id}/generate")
async def generate_ticket_draft_fields_endpoint(
    project_id: UUID,
    draft_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = _project_company_id(project) or await get_client_company_id(current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    draft = await td_svc.generate_fields(project_id, draft_id, company_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft

@router.post("/projects/{project_id}/ticket-drafts/{draft_id}/promote")
async def promote_ticket_draft_endpoint(
    project_id: UUID,
    draft_id: UUID,
    body: dict = Body(default={}),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    company_id = _project_company_id(project) or await get_client_company_id(current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    try:
        task = await td_svc.promote(
            project_id, draft_id, company_id,
            actor_user_id=current_user.id, overrides=body or {},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not task:
        raise HTTPException(status_code=404, detail="Draft not found or already promoted")
    return task

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

@router.post("/projects/{project_id}/tasks/{task_id}/summarize")
async def summarize_task_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """1-click Gemini Flash Lite catch-up summary of a ticket — where the work
    stands + what's been done recently. Ephemeral (not persisted); read-only."""
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import task_summary_service
    summary = await task_summary_service.generate_task_summary(project_id, task_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not summary:
        summary = "Couldn't generate a summary right now — try again in a moment."
    return {"summary": summary}

@router.post("/projects/{project_id}/tasks/{task_id}/rounds", status_code=201)
async def start_task_round_endpoint(
    project_id: UUID,
    task_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Open a new round on a kanban ticket: creates a "suggested fix" subtask
    (the round's headline work item), then logs a `round_started` row to
    mw_task_history so the client can group subsequent events under the new
    round. Rounds chain together as modular sub-todos inside one ticket —
    each round has a title, owns the events that follow until the next
    round_started, and surfaces what got "fixed" in the prior round.

    Body:
        suggested_fix_title (str, required): becomes a new subtask AND the
            round's display title.
        body (str, optional): kick-off note logged as the first activity row
            of the new round.
        attachment_ids ([uuid], optional): images already uploaded to this
            task (mw_project_files) to attach to the kick-off note.

    Returns: {round_event, subtask, note}. The note is None if no body+no
    attachments were supplied.
    """
    from app.matcha.services import project_subtask_service as st_svc
    from app.matcha.services import project_task_service as pt_svc

    await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)

    title = (body.get("suggested_fix_title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="suggested_fix_title required")

    kickoff_body = (body.get("body") or "").strip() or None

    raw_attachments = body.get("attachment_ids") or []
    attachment_ids: list[UUID] = []
    if raw_attachments:
        if not isinstance(raw_attachments, list):
            raise HTTPException(status_code=400, detail="attachment_ids must be a list")
        try:
            attachment_ids = [UUID(str(x)) for x in raw_attachments]
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="attachment_ids contains invalid UUID")
        async with get_connection() as conn:
            found = await conn.fetch(
                "SELECT id FROM mw_project_files WHERE task_id = $1 AND id = ANY($2::uuid[])",
                task_id, attachment_ids,
            )
        if len(found) != len(attachment_ids):
            raise HTTPException(status_code=400, detail="attachment not found on this task")

    # 1. Open the round boundary AND re-scope the checklist, atomically:
    #    - log the `round_started` row (client groups events between
    #      consecutive round_started rows into one round),
    #    - roll every UNCOMPLETED checklist item forward into the new round so
    #      outstanding work carries over,
    #    - leave COMPLETED items stamped on their old round so they archive out
    #      of the live (current-round) checklist and only surface in that
    #      round's "Fixed in Round N" history rollup.
    async with get_connection() as conn:
        async with conn.transaction():
            await pt_svc._log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=current_user.id,
                event_type="round_started",
                metadata={"title": title},
            )
            # round_started is now logged, so the current round = new round.
            new_round = await st_svc._current_round(conn, task_id)
            await conn.execute(
                "UPDATE mw_subtasks SET round_index = $2, updated_at = NOW() "
                "WHERE task_id = $1 AND is_done = false",
                task_id, new_round,
            )
            # The kickoff attachments were uploaded by the client BEFORE this
            # call, so their created_at predates the round_started row we just
            # logged. A file's round is derived at read time as
            # 1 + COUNT(round_started rows with created_at <= file.created_at)
            # (see project_file_service.list_task_files — there's no round_index
            # column), so without this they'd be attributed to the PREVIOUS
            # round and never show up under the new round's ATTACHMENTS. Stamp
            # them just past the boundary (clock_timestamp() advances within the
            # txn, so it's strictly after the round_started insert) to pull them
            # into the round they actually belong to.
            if attachment_ids:
                await conn.execute(
                    "UPDATE mw_project_files SET created_at = clock_timestamp() "
                    "WHERE task_id = $1 AND id = ANY($2::uuid[])",
                    task_id, attachment_ids,
                )

    # 2. Create the headline subtask (fires its own `subtask_added` history row).
    #    create_subtask stamps round_index = current round = new_round.
    try:
        subtask = await st_svc.create_subtask(
            project_id, task_id,
            title=title,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if subtask is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 3. Optional kick-off note (text + images) — landed AFTER round_started
    # so it falls inside the new round on the timeline.
    note = None
    if kickoff_body or attachment_ids:
        try:
            note = await pt_svc.log_task_activity(
                project_id=project_id,
                task_id=task_id,
                actor_user_id=current_user.id,
                kind="note",
                body=kickoff_body,
                attachment_ids=attachment_ids or None,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"ok": True, "title": title, "subtask": subtask, "note": note}

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

    raw_attachments = body.get("attachment_ids") or []
    attachment_ids: list[UUID] = []
    if raw_attachments:
        if not isinstance(raw_attachments, list):
            raise HTTPException(status_code=400, detail="attachment_ids must be a list")
        try:
            attachment_ids = [UUID(str(x)) for x in raw_attachments]
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="attachment_ids contains invalid UUID")
        # All ids must belong to mw_project_files rows for THIS task — never
        # store a dangling or cross-task ref.
        async with get_connection() as conn:
            found = await conn.fetch(
                "SELECT id FROM mw_project_files WHERE task_id = $1 AND id = ANY($2::uuid[])",
                task_id, attachment_ids,
            )
        if len(found) != len(attachment_ids):
            raise HTTPException(status_code=400, detail="attachment not found on this task")

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

async def _verify_task_belongs_to_project(project_id: UUID, task_id: UUID) -> None:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

@router.post("/projects/{project_id}/tasks/{task_id}/files")
async def upload_task_file_endpoint(
    project_id: UUID,
    task_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload an attachment scoped to a single kanban task."""
    from app.matcha.services import project_file_service

    project, _role = await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)
    company_id = project.get("company_id") or await get_client_company_id(current_user)

    fname = file.filename or "file"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_PROJECT_FILE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    content = await file.read()
    if len(content) > PROJECT_FILE_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    storage_url = await get_storage().upload_file(
        content, fname,
        prefix=f"matcha-work/{company_id}/{project_id}/tasks/{task_id}/files",
        content_type=file.content_type,
    )

    record = await project_file_service.add_project_file(
        project_id=project_id,
        uploaded_by=current_user.id,
        filename=fname,
        storage_url=storage_url,
        content_type=file.content_type,
        file_size=len(content),
        task_id=task_id,
    )
    return _resolve_file_urls([record])[0]

@router.get("/projects/{project_id}/tasks/{task_id}/files")
async def list_task_files_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import project_file_service
    await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)
    files = await project_file_service.list_task_files(project_id, task_id)
    return _resolve_file_urls(files)

@router.delete("/projects/{project_id}/tasks/{task_id}/files/{file_id}")
async def delete_task_file_endpoint(
    project_id: UUID,
    task_id: UUID,
    file_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    record = await project_file_service.get_task_file(file_id, project_id, task_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        await get_storage().delete_file(record["storage_url"])
    except Exception:
        pass

    await project_file_service.delete_project_file(file_id, project_id)
    return {"deleted": True}

@router.post("/projects/{project_id}/research-tasks")
async def create_research_task(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new research task in a project."""
    from app.matcha.services import project_service as proj_svc
    import uuid as _uuid

    await _verify_project_access(project_id, current_user)

    task = {
        "id": str(_uuid.uuid4()),
        "name": body.get("name", "Untitled Research"),
        "instructions": body.get("instructions", ""),
        "inputs": [],
        "results": [],
    }

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = row["project_data"] if row else {}
            if isinstance(data, str):
                data = json.loads(data)
            data = data or {}
            tasks = data.get("research_tasks", [])
            tasks.append(task)
            data["research_tasks"] = tasks
            await conn.execute(
                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                json.dumps(data), project_id,
            )

    return task

@router.put("/projects/{project_id}/research-tasks/{task_id}")
async def update_research_task(
    project_id: UUID,
    task_id: str,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a research task definition."""
    await _verify_project_access(project_id, current_user)

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = row["project_data"] if row else {}
            if isinstance(data, str):
                data = json.loads(data)
            data = data or {}

            for task in data.get("research_tasks", []):
                if task["id"] == task_id:
                    if "name" in body:
                        task["name"] = body["name"]
                    if "instructions" in body:
                        task["instructions"] = body["instructions"]
                    await conn.execute(
                        "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                        json.dumps(data), project_id,
                    )
                    return task

    raise HTTPException(status_code=404, detail="Research task not found")

@router.delete("/projects/{project_id}/research-tasks/{task_id}")
async def delete_research_task(
    project_id: UUID,
    task_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a research task and all its results."""
    await _verify_project_access(project_id, current_user)

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = row["project_data"] if row else {}
            if isinstance(data, str):
                data = json.loads(data)
            data = data or {}
            data["research_tasks"] = [t for t in data.get("research_tasks", []) if t["id"] != task_id]
            await conn.execute(
                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                json.dumps(data), project_id,
            )

    return {"deleted": True}

@router.post("/projects/{project_id}/research-tasks/{task_id}/inputs")
async def add_research_inputs(
    project_id: UUID,
    task_id: str,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Add URLs to a research task."""
    import uuid as _uuid

    await _verify_project_access(project_id, current_user)
    urls = body.get("urls", [])
    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    new_inputs = []
    for url in urls:
        url = url.strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            continue
        new_inputs.append({
            "id": str(_uuid.uuid4()),
            "url": url,
            "status": "pending",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        })

    if not new_inputs:
        raise HTTPException(status_code=400, detail="No valid URLs provided")

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = row["project_data"] if row else {}
            if isinstance(data, str):
                data = json.loads(data)
            data = data or {}

            for task in data.get("research_tasks", []):
                if task["id"] == task_id:
                    task.setdefault("inputs", []).extend(new_inputs)
                    await conn.execute(
                        "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                        json.dumps(data), project_id,
                    )
                    return {"added": len(new_inputs), "inputs": new_inputs}

    raise HTTPException(status_code=404, detail="Research task not found")

@router.delete("/projects/{project_id}/research-tasks/{task_id}/inputs/{input_id}")
async def delete_research_input(
    project_id: UUID,
    task_id: str,
    input_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove a URL from a research task."""
    await _verify_project_access(project_id, current_user)

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = row["project_data"] if row else {}
            if isinstance(data, str):
                data = json.loads(data)
            data = data or {}

            for task in data.get("research_tasks", []):
                if task["id"] == task_id:
                    task["inputs"] = [i for i in task.get("inputs", []) if i["id"] != input_id]
                    task["results"] = [r for r in task.get("results", []) if r.get("input_id") != input_id]
                    await conn.execute(
                        "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                        json.dumps(data), project_id,
                    )
                    return {"deleted": True}

    raise HTTPException(status_code=404, detail="Research task not found")

@router.post("/projects/{project_id}/research-tasks/{task_id}/run")
async def run_research_task(
    project_id: UUID,
    task_id: str,
    capture_screenshot: bool = Query(False),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Run all pending research inputs sequentially with SSE status streaming."""
    from app.matcha.services.research_browse_service import run_research_for_input
    from starlette.responses import StreamingResponse

    project, _role = await _verify_project_access(project_id, current_user)
    company_id = str(project.get("company_id") or await get_client_company_id(current_user))

    # Collect pending inputs
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = row["project_data"] if row else {}
            if isinstance(data, str):
                data = json.loads(data)
            data = data or {}

            pending_inputs = []
            instructions = ""
            for task in data.get("research_tasks", []):
                if task["id"] == task_id:
                    instructions = task.get("instructions", "")
                    if not instructions:
                        raise HTTPException(status_code=400, detail="Task has no instructions")
                    for inp in task.get("inputs", []):
                        if inp["status"] in ("pending", "error"):
                            inp["status"] = "running"
                            inp.pop("error", None)
                            pending_inputs.append({"id": inp["id"], "url": inp["url"]})

                    await conn.execute(
                        "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                        json.dumps(data), project_id,
                    )
                    break

    if not pending_inputs:
        return {"queued": 0}

    async def event_stream():
        for i, inp in enumerate(pending_inputs):
            yield _sse_data({"type": "status", "input_id": inp["id"], "url": inp["url"],
                             "message": f"Starting research ({i + 1}/{len(pending_inputs)}): {inp['url']}"})

            async def on_status(msg):
                pass  # will be replaced per-input below

            status_queue: asyncio.Queue = asyncio.Queue()

            async def stream_status(msg: str):
                await status_queue.put(msg)

            # Run browse in background, stream statuses
            browse_task = asyncio.create_task(
                run_research_for_input(
                    project_id, task_id, inp["id"], inp["url"], instructions,
                    on_status=stream_status,
                    capture_screenshot=capture_screenshot, company_id=company_id,
                )
            )

            while not browse_task.done():
                try:
                    msg = await asyncio.wait_for(status_queue.get(), timeout=1.0)
                    yield _sse_data({"type": "status", "input_id": inp["id"], "message": msg})
                except asyncio.TimeoutError:
                    pass

            # Drain remaining messages
            while not status_queue.empty():
                msg = status_queue.get_nowait()
                yield _sse_data({"type": "status", "input_id": inp["id"], "message": msg})

            result = browse_task.result()
            yield _sse_data({
                "type": "complete" if not result.get("error") else "error",
                "input_id": inp["id"],
                "url": inp["url"],
                "findings": result.get("findings", {}),
                "summary": result.get("summary", ""),
                "error": result.get("error"),
            })

        yield _sse_data({"type": "done", "message": f"Finished researching {len(pending_inputs)} URL(s)"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/projects/{project_id}/research-tasks/{task_id}/inputs/{input_id}/follow-up")
async def follow_up_research_input(
    project_id: UUID,
    task_id: str,
    input_id: str,
    body: dict = Body(...),
    capture_screenshot: bool = Query(False),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Re-research a URL with additional instructions, building on previous findings."""
    from app.matcha.services.research_browse_service import run_research_for_input
    from starlette.responses import StreamingResponse

    project, _role = await _verify_project_access(project_id, current_user)
    company_id = str(project.get("company_id") or await get_client_company_id(current_user))

    follow_up = body.get("follow_up", "").strip()
    if not follow_up:
        raise HTTPException(status_code=400, detail="follow_up is required")

    follow_url = ""
    combined_instructions = ""

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = row["project_data"] if row else {}
            if isinstance(data, str):
                data = json.loads(data)
            data = data or {}

            for task in data.get("research_tasks", []):
                if task["id"] == task_id:
                    base_instructions = task.get("instructions", "")

                    # Find previous findings for context
                    prev_findings = {}
                    for r in task.get("results", []):
                        if r.get("input_id") == input_id:
                            prev_findings = r.get("findings", {})
                            break

                    # Build combined instructions with previous context
                    combined_instructions = base_instructions
                    if prev_findings:
                        combined_instructions += f"\n\nPREVIOUS FINDINGS (already gathered):\n{json.dumps(prev_findings, indent=2)}"
                    combined_instructions += f"\n\nADDITIONAL REQUEST:\n{follow_up}"

                    for inp in task.get("inputs", []):
                        if inp["id"] == input_id:
                            inp["status"] = "running"
                            inp.pop("error", None)
                            inp.pop("completed_at", None)
                            follow_url = inp["url"]
                            # Keep old results — new ones will merge
                            break

                    await conn.execute(
                        "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                        json.dumps(data), project_id,
                    )
                    break

    if not follow_url:
        raise HTTPException(status_code=404, detail="Input not found")

    async def event_stream():
        status_queue: asyncio.Queue = asyncio.Queue()

        async def stream_status(msg: str):
            await status_queue.put(msg)

        browse_task = asyncio.create_task(
            run_research_for_input(
                project_id, task_id, input_id, follow_url, combined_instructions,
                on_status=stream_status,
                capture_screenshot=capture_screenshot, company_id=company_id,
            )
        )

        while not browse_task.done():
            try:
                msg = await asyncio.wait_for(status_queue.get(), timeout=1.0)
                yield _sse_data({"type": "status", "input_id": input_id, "message": msg})
            except asyncio.TimeoutError:
                pass

        while not status_queue.empty():
            msg = status_queue.get_nowait()
            yield _sse_data({"type": "status", "input_id": input_id, "message": msg})

        result = browse_task.result()
        yield _sse_data({
            "type": "complete" if not result.get("error") else "error",
            "input_id": input_id, "url": follow_url,
            "findings": result.get("findings", {}),
            "summary": result.get("summary", ""),
            "error": result.get("error"),
        })
        yield _sse_data({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/projects/{project_id}/research-tasks/{task_id}/inputs/{input_id}/retry")
async def retry_research_input(
    project_id: UUID,
    task_id: str,
    input_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Retry a failed research input with SSE streaming."""
    from app.matcha.services.research_browse_service import run_research_for_input
    from starlette.responses import StreamingResponse

    await _verify_project_access(project_id, current_user)

    retry_url = ""
    retry_instructions = ""

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = row["project_data"] if row else {}
            if isinstance(data, str):
                data = json.loads(data)
            data = data or {}

            for task in data.get("research_tasks", []):
                if task["id"] == task_id:
                    retry_instructions = task.get("instructions", "")
                    for inp in task.get("inputs", []):
                        if inp["id"] == input_id:
                            inp["status"] = "running"
                            inp.pop("error", None)
                            inp.pop("completed_at", None)
                            retry_url = inp["url"]
                            task["results"] = [r for r in task.get("results", []) if r.get("input_id") != input_id]

                            await conn.execute(
                                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                                json.dumps(data), project_id,
                            )
                            break
                    break

    if not retry_url:
        raise HTTPException(status_code=404, detail="Input not found")

    async def event_stream():
        status_queue: asyncio.Queue = asyncio.Queue()

        async def stream_status(msg: str):
            await status_queue.put(msg)

        browse_task = asyncio.create_task(
            run_research_for_input(
                project_id, task_id, input_id, retry_url, retry_instructions,
                on_status=stream_status,
            )
        )

        while not browse_task.done():
            try:
                msg = await asyncio.wait_for(status_queue.get(), timeout=1.0)
                yield _sse_data({"type": "status", "input_id": input_id, "message": msg})
            except asyncio.TimeoutError:
                pass

        while not status_queue.empty():
            msg = status_queue.get_nowait()
            yield _sse_data({"type": "status", "input_id": input_id, "message": msg})

        result = browse_task.result()
        yield _sse_data({
            "type": "complete" if not result.get("error") else "error",
            "input_id": input_id, "url": retry_url,
            "findings": result.get("findings", {}),
            "summary": result.get("summary", ""),
            "error": result.get("error"),
        })
        yield _sse_data({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/projects/{project_id}/research-tasks/{task_id}/stop")
async def stop_research_task(
    project_id: UUID,
    task_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reset all running inputs back to pending (cancel in-flight research)."""
    await _verify_project_access(project_id, current_user)

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = row["project_data"] if row else {}
            if isinstance(data, str):
                data = json.loads(data)
            data = data or {}

            reset_count = 0
            for task in data.get("research_tasks", []):
                if task["id"] == task_id:
                    for inp in task.get("inputs", []):
                        if inp["status"] == "running":
                            inp["status"] = "pending"
                            reset_count += 1
                    break

            if reset_count:
                await conn.execute(
                    "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                    json.dumps(data), project_id,
                )

    return {"reset": reset_count}
