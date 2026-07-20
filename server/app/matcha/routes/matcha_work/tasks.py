"""Project kanban tasks: pipeline mode, task CRUD/reject/approve/ai-draft,
subtasks, review rounds, and the 1-click task summary.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). Ticket drafts, task history/activity, task files, and research
tasks were split out into sibling modules on 2026-07-19 -- see
matcha_work/CLAUDE.md.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, require_company_member
from app.matcha.routes.matcha_work._shared import (
    _can_edit_project,
    _resolve_file_urls,
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

    # 1. Open the round boundary AND re-scope the checklist, atomically —
    #    see project_subtask_service.start_new_round for the ordering rules.
    #    Shared with the reject/send-back flow in project_task_service.
    async with get_connection() as conn:
        async with conn.transaction():
            await st_svc.start_new_round(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=current_user.id,
                title=title,
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
    #    create_subtask stamps round_index = current round = the round just opened.
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
