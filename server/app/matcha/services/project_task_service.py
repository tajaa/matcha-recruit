"""Project task service — project-scoped kanban tasks for collab projects.

Project tasks live in `mw_tasks` with `project_id` set (null project_id is reserved for
company-wide dashboard tasks surfaced via /tasks). Board state is tracked in
`board_column` (todo|in_progress|changes_requested|review|done). The existing
`status` column (pending|completed|cancelled) stays in sync with `board_column`:
- moving to 'done'   → status='completed', completed_at=now
- moving out of 'done' → status='pending',  completed_at=null
- toggling status complete ↔ moves column to 'done' / 'todo' accordingly

Review send-back (`reject_project_task`) drops a card from review back to `todo`
and auto-opens the next round: unfixed checklist items roll forward into the new
round (the live, foreground checklist) while items the reviewer accepted stay
archived on the prior round (background). review_note + the round_started title
carry the feedback; the churn count tracks how many times it bounced. The
`changes_requested` column remains valid for manual drag but is no longer
auto-populated by send-back.
"""

import json
import logging
from datetime import date as _date, datetime, timezone
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


async def _log_task_history(
    conn,
    *,
    task_id: UUID,
    project_id: UUID,
    actor_user_id: Optional[UUID],
    event_type: str,
    from_value: Optional[str] = None,
    to_value: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Insert a row into mw_task_history. Best-effort — if the table
    doesn't exist yet (migration not run), warn and continue so the
    underlying task write still succeeds.
    """
    try:
        await conn.execute(
            """
            INSERT INTO mw_task_history
                (task_id, project_id, actor_user_id, event_type, from_value, to_value, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            """,
            task_id, project_id, actor_user_id, event_type,
            from_value, to_value, json.dumps(metadata or {}),
        )
    except Exception as e:
        logger.warning(
            "Failed to log task history task=%s event=%s: %s",
            task_id, event_type, e,
        )


_ALLOWED_COLUMNS = {
    "todo", "in_progress", "changes_requested", "review", "done",
    # Sales-pipeline stages kept here for backward compat (pre-migration rows).
    # New tasks place the stage in pipeline_column, not board_column.
    "lead", "qualified", "proposal", "negotiation", "closed",
}
_ALLOWED_PIPELINE_COLUMNS = {"lead", "qualified", "proposal", "negotiation", "closed"}
_ALLOWED_PRIORITIES = {"critical", "high", "medium", "low"}
# Ticket-template kinds stored in mw_tasks.category. "manual" = no template
# (blank task / legacy rows) and renders without a badge on the client.
_ALLOWED_CATEGORIES = {"manual", "engineering", "sales", "product", "bug", "general"}
# Sales-pipeline deal outcome. "open" = still in the funnel; won/lost are
# terminal and independent of board_column (a deal can be lost from any stage).
_ALLOWED_OUTCOMES = {"open", "won", "lost"}
# Sales follow-up activity kinds, logged onto the task history timeline.
_ALLOWED_ACTIVITY_KINDS = {"call", "email", "note", "meeting"}

# Email + bell templates for forward-only column transitions. Destinations
# other than these (e.g. moving back to 'todo') intentionally fire nothing.
_TRANSITION_TEMPLATES: dict[str, dict[str, str]] = {
    "in_progress": {"subject": "Task started: {title}",     "verb": "started"},
    "review":      {"subject": "Ready for review: {title}", "verb": "moved to review"},
    "done":        {"subject": "Task completed: {title}",   "verb": "completed"},
}


async def _broadcast_task_event_safe(project_id: UUID, event: str, payload: dict) -> None:
    """Wrapped broadcast — never fails the caller; logs at warning level.

    Lazy import dodges the routes→services circular at module load time.
    """
    try:
        from ..routes.project_ws import broadcast_task_event
        logger.info("dispatching %s for project=%s", event, project_id)
        await broadcast_task_event(project_id, event, payload)
    except Exception as e:
        logger.warning("Failed to broadcast %s for project %s: %s", event, project_id, e)


def _row_to_task(row: dict) -> dict:
    d = dict(row)
    for key in ("id", "project_id", "created_by", "assigned_to"):
        if d.get(key) is not None:
            d[key] = str(d[key])
    if d.get("due_date") is not None:
        d["due_date"] = d["due_date"].isoformat()
    for key in ("completed_at", "created_at", "updated_at", "last_moved_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    # Sales-pipeline fields (present only once the salespipe0001 migration is
    # applied; NULL on non-sales boards). Dates → ISO; NUMERIC → float so the
    # JSON response carries a plain number rather than a Decimal.
    for key in ("next_action_at", "expected_close"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    if d.get("deal_value") is not None:
        d["deal_value"] = float(d["deal_value"])
    return d


async def log_task_activity(
    *,
    project_id: UUID,
    task_id: UUID,
    actor_user_id: Optional[UUID],
    kind: str,
    body: Optional[str] = None,
    attachment_ids: Optional[list[UUID]] = None,
    reply_to: Optional[UUID] = None,
) -> Optional[dict]:
    """Log a sales follow-up activity (call/email/note/meeting) onto a task's
    history timeline. Reuses mw_task_history (event_type='activity') so it
    renders in the existing task viewer timeline — no separate table.
    Returns None if the task doesn't belong to the project.

    `attachment_ids` (optional) links this note to N existing mw_project_files
    rows for the task. Caller is responsible for validating ownership before
    invoking. Stored inside metadata JSONB so no schema change is needed.

    `reply_to` (optional) is the mw_task_history id of an existing comment this
    note replies to. We resolve the parent's author + a short body excerpt
    server-side and stash them in metadata (reply_to / reply_to_name /
    reply_to_excerpt) so the client can render the quoted parent without a
    second round-trip. A reply to a non-note row is ignored.
    """
    kind = (kind or "note").strip().lower()
    if kind not in _ALLOWED_ACTIVITY_KINDS:
        raise ValueError(f"Invalid activity kind: {kind}")
    async with get_connection() as conn:
        exists = await conn.fetchrow(
            "SELECT id FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
        if not exists:
            return None
        metadata: dict = {"kind": kind, "body": (body or "").strip()}
        if attachment_ids:
            metadata["attachment_ids"] = [str(a) for a in attachment_ids]
        if reply_to:
            parent = await conn.fetchrow(
                """
                SELECT h.metadata,
                       COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name),
                                a.name, u.email) AS actor_name
                FROM mw_task_history h
                LEFT JOIN users u     ON u.id      = h.actor_user_id
                LEFT JOIN clients c   ON c.user_id = h.actor_user_id
                LEFT JOIN employees e ON e.user_id = h.actor_user_id
                LEFT JOIN admins a    ON a.user_id = h.actor_user_id
                WHERE h.id = $1 AND h.task_id = $2 AND h.event_type = 'activity'
                """,
                reply_to, task_id,
            )
            if parent:
                metadata["reply_to"] = str(reply_to)
                if parent["actor_name"]:
                    metadata["reply_to_name"] = parent["actor_name"]
                pmeta = parent["metadata"]
                if isinstance(pmeta, str):
                    import json as _json
                    try:
                        pmeta = _json.loads(pmeta)
                    except Exception:
                        pmeta = {}
                parent_body = (pmeta or {}).get("body") if isinstance(pmeta, dict) else None
                if parent_body:
                    excerpt = parent_body.strip().replace("\n", " ")
                    metadata["reply_to_excerpt"] = excerpt[:140]
        await _log_task_history(
            conn,
            task_id=task_id,
            project_id=project_id,
            actor_user_id=actor_user_id,
            event_type="activity",
            metadata=metadata,
        )
    # Notify the other participants of a new in-ticket comment (the discussion
    # channel). Only plain notes — sales touchpoints (call/email/meeting) don't
    # ping collaborators. Best-effort; never blocks the log.
    if kind == "note":
        await _notify_task_comment(
            project_id=project_id,
            task_id=task_id,
            actor_user_id=actor_user_id,
            body=body or "",
        )
    return {"ok": True, "kind": kind}


async def list_project_tasks(project_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.project_id, t.company_id, t.created_by, t.title, t.description,
                   t.due_date, t.priority, t.status, t.board_column, t.assigned_to,
                   t.completed_at, t.created_at, t.updated_at, t.progress_note, t.category,
                   t.element_id, t.review_note,
                   t.deal_value, t.probability, t.contact_name, t.contact_company,
                   t.contact_email, t.contact_phone, t.outcome, t.loss_reason,
                   t.next_action_at, t.expected_close,
                   COALESCE(t.pipeline_column, 'lead') AS pipeline_column,
                   -- Last time this card crossed columns, for the "Moved …" stamp
                   -- on the kanban card. Null until the first move. Counts a
                   -- review_rejected as a move too (review → changes_requested)
                   -- so a freshly bounced card resets its aging clock instead
                   -- of inheriting the time it entered review.
                   (SELECT MAX(h.created_at) FROM mw_task_history h
                      WHERE h.task_id = t.id
                        AND h.event_type IN ('column_change', 'review_rejected')) AS last_moved_at,
                   -- How many times this card has been sent back from review.
                   -- Drives the "↻ ×N" churn chip so thrashing tickets are
                   -- visible at board glance, not just in the card history.
                   (SELECT COUNT(*) FROM mw_task_history h2
                      WHERE h2.task_id = t.id AND h2.event_type = 'review_rejected') AS review_cycle_count,
                   -- Checklist progress for the card face ("done/total"),
                   -- scoped to the ticket's CURRENT round (max round_index) so
                   -- the card matches the live (current-round) checklist —
                   -- archived past-round items don't inflate the count.
                   (SELECT COUNT(*) FROM mw_subtasks s
                      WHERE s.task_id = t.id
                        AND s.round_index = (SELECT COALESCE(MAX(round_index), 1)
                                             FROM mw_subtasks s3 WHERE s3.task_id = t.id)) AS subtask_total,
                   (SELECT COUNT(*) FROM mw_subtasks s
                      WHERE s.task_id = t.id AND s.is_done
                        AND s.round_index = (SELECT COALESCE(MAX(round_index), 1)
                                             FROM mw_subtasks s3 WHERE s3.task_id = t.id)) AS subtask_done,
                   -- Split assignee fields so the client can pick a
                   -- human-readable name and never fall back to showing
                   -- a raw email in cards / tooltips. Older callsites
                   -- expected `assigned_name` to fall back to email; that
                   -- behavior moves to the client via AssigneeDisplay.
                   COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name) AS assigned_name,
                   u.email AS assigned_email,
                   el.name AS element_name
            FROM mw_tasks t
            LEFT JOIN users u ON u.id = t.assigned_to
            LEFT JOIN clients c ON c.user_id = t.assigned_to
            LEFT JOIN employees e ON e.user_id = t.assigned_to
            LEFT JOIN admins a ON a.user_id = t.assigned_to
            LEFT JOIN mw_project_elements el ON el.id = t.element_id
            WHERE t.project_id = $1 AND t.status != 'cancelled'
            ORDER BY
                CASE t.priority
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4
                END,
                t.created_at DESC
            """,
            project_id,
        )
    return [_row_to_task(dict(r)) for r in rows]


async def create_project_task(
    *,
    project_id: UUID,
    company_id: UUID,
    created_by: UUID,
    title: str,
    description: Optional[str] = None,
    board_column: str = "todo",
    pipeline_column: str = "lead",
    priority: str = "medium",
    due_date: Optional[_date] = None,
    assigned_to: Optional[UUID] = None,
    progress_note: Optional[str] = None,
    project_title: Optional[str] = None,
    category: str = "manual",
    element_id: Optional[str] = None,
    deal_value: Optional[float] = None,
    probability: Optional[int] = None,
    contact_name: Optional[str] = None,
    contact_company: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
    outcome: Optional[str] = None,
    loss_reason: Optional[str] = None,
    next_action_at: Optional[_date] = None,
    expected_close: Optional[_date] = None,
) -> dict:
    if board_column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Invalid board_column: {board_column}")
    if pipeline_column not in _ALLOWED_PIPELINE_COLUMNS:
        raise ValueError(f"Invalid pipeline_column: {pipeline_column}")
    if priority not in _ALLOWED_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority}")
    if category not in _ALLOWED_CATEGORIES:
        raise ValueError(f"Invalid category: {category}")
    if outcome is not None and outcome not in _ALLOWED_OUTCOMES:
        raise ValueError(f"Invalid outcome: {outcome}")
    if not title or not title.strip():
        raise ValueError("Title required")

    status = "completed" if board_column == "done" else "pending"
    completed_at = datetime.now(timezone.utc) if status == "completed" else None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_tasks (
                company_id, created_by, project_id, title, description,
                due_date, priority, status, board_column, pipeline_column, assigned_to,
                completed_at, category, progress_note, element_id,
                deal_value, probability, contact_name, contact_company,
                contact_email, contact_phone, outcome, loss_reason,
                next_action_at, expected_close
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18,
                    $19, $20, $21, $22, $23, $24, $25)
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column,
                      COALESCE(pipeline_column, 'lead') AS pipeline_column,
                      assigned_to, completed_at, created_at, updated_at,
                      progress_note, category, element_id,
                      deal_value, probability, contact_name, contact_company,
                      contact_email, contact_phone, outcome, loss_reason,
                      next_action_at, expected_close
            """,
            company_id, created_by, project_id, title.strip(), description,
            due_date, priority, status, board_column, pipeline_column, assigned_to,
            completed_at, category, progress_note, element_id,
            deal_value, probability, contact_name, contact_company,
            contact_email, contact_phone, outcome, loss_reason,
            next_action_at, expected_close,
        )

        await _log_task_history(
            conn,
            task_id=row["id"],
            project_id=project_id,
            actor_user_id=created_by,
            event_type="created",
            to_value=board_column,
            metadata={"title": title.strip()},
        )
        if assigned_to is not None:
            await _log_task_history(
                conn,
                task_id=row["id"],
                project_id=project_id,
                actor_user_id=created_by,
                event_type="assignee_change",
                to_value=str(assigned_to),
            )

    if assigned_to is not None and assigned_to != created_by:
        await _notify_task_assigned(
            assigned_to=assigned_to,
            company_id=company_id,
            actor_user_id=created_by,
            project_id=project_id,
            project_title=project_title,
            task_id=row["id"],
            task_title=title.strip(),
        )

    task_payload = _row_to_task(dict(row))
    task_payload["actor_id"] = str(created_by)
    await _broadcast_task_event_safe(project_id, "task.created", task_payload)
    return _row_to_task(dict(row))


async def _notify_task_assigned(
    *,
    assigned_to: UUID,
    company_id: UUID,
    actor_user_id: UUID,
    project_id: UUID,
    project_title: Optional[str],
    task_id: UUID,
    task_title: str,
) -> None:
    """Dispatch a `task_assigned` bell notification + email to the assignee."""
    from . import notification_service as notif_svc

    assigner_name = "Someone"
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                    SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
                    FROM users u
                    LEFT JOIN clients c ON c.user_id = u.id
                    LEFT JOIN employees e ON e.user_id = u.id
                    LEFT JOIN admins a ON a.user_id = u.id
                    WHERE u.id = $1
                    """, actor_user_id
            )
        if row and row["name"]:
            assigner_name = row["name"]
    except Exception as e:
        logger.warning("Failed to look up assigner %s name: %s", actor_user_id, e)

    if project_title:
        body = f"{assigner_name} assigned this to you in {project_title}."
    else:
        body = f"{assigner_name} assigned this to you."

    try:
        await notif_svc.create_notification(
            user_id=assigned_to,
            company_id=company_id,
            type="task_assigned",
            title=f"Assigned: {task_title}",
            body=body,
            link=f"/work?project={project_id}&task={task_id}",
            metadata={
                "project_id": str(project_id),
                "task_id": str(task_id),
                "assigned_by": str(actor_user_id),
                "project_title": project_title,
                "task_title": task_title,
                "actor_name": assigner_name,
            },
            send_email=True,
            email_subject=f"You were assigned: {task_title}",
        )
    except Exception as e:
        logger.warning("Failed to notify task assignment %s -> %s: %s", task_id, assigned_to, e)


async def _notify_task_column_transition(
    *,
    project_id: UUID,
    company_id: UUID,
    actor_user_id: Optional[UUID],
    task_id: UUID,
    task_title: str,
    new_column: str,
    project_title: Optional[str],
) -> None:
    """Email + bell every active project collaborator (minus the actor) when
    a task crosses into in_progress / review / done. Transitions back to
    'todo' (or any other destination) are intentionally silent.
    """
    tpl = _TRANSITION_TEMPLATES.get(new_column)
    if tpl is None:
        return

    from .project_service import list_collaborators
    from . import notification_service as notif_svc

    actor_name = "Someone"
    if actor_user_id is not None:
        try:
            async with get_connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
                    FROM users u
                    LEFT JOIN clients c ON c.user_id = u.id
                    LEFT JOIN employees e ON e.user_id = u.id
                    LEFT JOIN admins a ON a.user_id = u.id
                    WHERE u.id = $1
                    """, actor_user_id
                )
            if row and row["name"]:
                actor_name = row["name"]
        except Exception as e:
            logger.warning("Failed to look up actor %s name: %s", actor_user_id, e)

    try:
        collaborators = await list_collaborators(project_id)
    except Exception as e:
        logger.warning("Failed to load collaborators for project %s: %s", project_id, e)
        return

    recipients = [
        c for c in collaborators
        if actor_user_id is None or c["user_id"] != actor_user_id
    ]
    logger.info(
        "task_progress notify: task=%s project=%s new_column=%s actor=%s "
        "collab_total=%d recipients=%d emails=%s",
        task_id, project_id, new_column, actor_user_id,
        len(collaborators), len(recipients),
        [c["email"] for c in recipients],
    )

    where = f"in {project_title}" if project_title else "in this project"
    body = f"{actor_name} {tpl['verb']} “{task_title}” {where}."
    subject = tpl["subject"].format(title=task_title)
    link = f"/work?project={project_id}&task={task_id}"

    for c in recipients:
        try:
            await notif_svc.create_notification(
                user_id=c["user_id"],
                company_id=company_id,
                type="task_progress",
                title=subject,
                body=body,
                link=link,
                metadata={
                    "project_id": str(project_id),
                    "task_id": str(task_id),
                    "to_column": new_column,
                    "actor_id": str(actor_user_id) if actor_user_id else None,
                    "project_title": project_title,
                    "task_title": task_title,
                    "actor_name": actor_name,
                },
                send_email=True,
                email_subject=subject,
            )
        except Exception as e:
            logger.warning(
                "Failed task-progress notify task=%s recipient=%s: %s",
                task_id, c["user_id"], e,
            )


async def _notify_task_rejected(
    *,
    assigned_to: UUID,
    company_id: UUID,
    actor_user_id: Optional[UUID],
    project_id: UUID,
    project_title: Optional[str],
    task_id: UUID,
    task_title: str,
    note: str,
) -> None:
    """Bell + email the assignee when a reviewer sends their task back for
    changes. Assignee-only on purpose — this is a direct hand-back, not the
    fan-out broadcast that `_notify_task_column_transition` does for forward
    moves (which is silent on backward moves anyway).
    """
    from . import notification_service as notif_svc

    reviewer_name = "A reviewer"
    if actor_user_id is not None:
        try:
            async with get_connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
                    FROM users u
                    LEFT JOIN clients c ON c.user_id = u.id
                    LEFT JOIN employees e ON e.user_id = u.id
                    LEFT JOIN admins a ON a.user_id = u.id
                    WHERE u.id = $1
                    """, actor_user_id
                )
            if row and row["name"]:
                reviewer_name = row["name"]
        except Exception as e:
            logger.warning("Failed to look up reviewer %s name: %s", actor_user_id, e)

    where = f" in {project_title}" if project_title else ""
    body = f"{reviewer_name} sent this back for changes{where}:\n\n“{note}”"

    try:
        await notif_svc.create_notification(
            user_id=assigned_to,
            company_id=company_id,
            type="task_rejected",
            title=f"Sent back for changes: {task_title}",
            body=body,
            link=f"/work?project={project_id}&task={task_id}",
            metadata={
                "project_id": str(project_id),
                "task_id": str(task_id),
                "reviewer_id": str(actor_user_id) if actor_user_id else None,
                "project_title": project_title,
                "task_title": task_title,
                "actor_name": reviewer_name,
            },
            send_email=True,
            email_subject=f"Sent back for changes: {task_title}",
        )
    except Exception as e:
        logger.warning("Failed to notify task rejection %s -> %s: %s", task_id, assigned_to, e)


async def _notify_task_comment(
    *,
    project_id: UUID,
    task_id: UUID,
    actor_user_id: Optional[UUID],
    body: str,
) -> None:
    """Bell + in-app toast the OTHER participants when someone posts a comment
    on a ticket — the in-ticket clarification channel. Recipients = the
    assignee + the creator + anyone who previously commented, minus the author.
    No email (comments are high-frequency; the bell + live toast are enough).
    Best-effort — never raises into the caller.
    """
    from . import notification_service as notif_svc
    try:
        async with get_connection() as conn:
            task = await conn.fetchrow(
                """SELECT t.company_id, t.assigned_to, t.created_by, t.title,
                          p.name AS project_title
                   FROM mw_tasks t
                   LEFT JOIN mw_projects p ON p.id = t.project_id
                   WHERE t.id = $1 AND t.project_id = $2""",
                task_id, project_id,
            )
            if not task:
                return
            prior = await conn.fetch(
                """SELECT DISTINCT actor_user_id FROM mw_task_history
                   WHERE task_id = $1 AND event_type = 'activity'
                     AND actor_user_id IS NOT NULL""",
                task_id,
            )
            actor_name = "Someone"
            if actor_user_id is not None:
                arow = await conn.fetchrow(
                    """
                    SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
                    FROM users u
                    LEFT JOIN clients c ON c.user_id = u.id
                    LEFT JOIN employees e ON e.user_id = u.id
                    LEFT JOIN admins a ON a.user_id = u.id
                    WHERE u.id = $1
                    """, actor_user_id
                )
                if arow and arow["name"]:
                    actor_name = arow["name"]

        recipients: set = set()
        for uid in (task["assigned_to"], task["created_by"]):
            if uid is not None:
                recipients.add(uid)
        for r in prior:
            recipients.add(r["actor_user_id"])
        if actor_user_id is not None:
            recipients.discard(actor_user_id)
        if not recipients:
            return

        project_title = task["project_title"]
        task_title = task["title"]
        snippet = (body or "").strip()
        if len(snippet) > 140:
            snippet = snippet[:140] + "…"
        where = f" in {project_title}" if project_title else ""
        nbody = f"{actor_name} commented on “{task_title}”{where}:\n\n“{snippet}”"
        link = f"/work?project={project_id}&task={task_id}"
        for uid in recipients:
            try:
                await notif_svc.create_notification(
                    user_id=uid,
                    company_id=task["company_id"],
                    type="task_comment",
                    title=f"New comment: {task_title}",
                    body=nbody,
                    link=link,
                    metadata={
                        "project_id": str(project_id),
                        "task_id": str(task_id),
                        "actor_id": str(actor_user_id) if actor_user_id else None,
                        "project_title": project_title,
                        "task_title": task_title,
                        "actor_name": actor_name,
                        "snippet": snippet,
                    },
                    send_email=False,
                )
            except Exception as e:
                logger.warning(
                    "Failed task-comment notify task=%s recipient=%s: %s",
                    task_id, uid, e,
                )
    except Exception as e:
        logger.warning("task-comment notify failed task=%s: %s", task_id, e)


async def reject_project_task(
    project_id: UUID,
    task_id: UUID,
    note: str,
    *,
    actor_user_id: Optional[UUID] = None,
    project_title: Optional[str] = None,
) -> Optional[dict]:
    """Reviewer sends a task back: bounce review → todo, store the reason in
    review_note, auto-open the next round (roll unfixed checklist items forward,
    archive accepted ones), log a `review_rejected` history event, and email the
    assignee. Only valid from the `review` column. Returns the updated task row
    (same shape as `update_project_task`) or None if not found.
    """
    note = (note or "").strip()
    async with get_connection() as conn:
        current = await conn.fetchrow(
            """
            SELECT board_column, company_id, assigned_to, title
            FROM mw_tasks WHERE id = $1 AND project_id = $2
            """,
            task_id, project_id,
        )
        if not current:
            return None
        if current["board_column"] != "review":
            raise ValueError("Task must be in review to send it back")

        row = await conn.fetchrow(
            """
            UPDATE mw_tasks SET
                board_column = 'todo',
                status = 'pending',
                completed_at = NULL,
                review_note = $3::text,
                updated_at = NOW()
            WHERE id = $1 AND project_id = $2
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column,
                      COALESCE(pipeline_column, 'lead') AS pipeline_column,
                      assigned_to, completed_at, created_at, updated_at,
                      progress_note, category, element_id, review_note,
                      deal_value, probability, contact_name, contact_company,
                      contact_email, contact_phone, outcome, loss_reason,
                      next_action_at, expected_close
            """,
            task_id, project_id, note,
        )
        cycle_count = 0
        if row:
            # Auto-open the next round so the rework cycle reads as
            # foreground/background: log the round boundary FIRST, roll every
            # UNFIXED (uncompleted) checklist item into the new round (the live
            # foreground checklist), and leave items the reviewer accepted
            # stamped on the prior round so they archive into the background.
            # The reviewer's "re-open these items" taps already flipped the
            # rejected pieces to not-done, so they roll forward here as the new
            # round's work.
            from . import project_subtask_service as st_svc
            round_title = note[:80] if note else "Reviewer requested changes"
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="round_started",
                # Keep metadata string-only — the desktop client decodes
                # mw_task_history.metadata as [String: String], so a non-string
                # value (e.g. a bool) fails the whole history decode and the
                # ticket's notes + rounds silently vanish.
                metadata={"title": round_title},
            )
            new_round = await st_svc._current_round(conn, task_id)
            await conn.execute(
                "UPDATE mw_subtasks SET round_index = $2, updated_at = NOW() "
                "WHERE task_id = $1 AND is_done = false",
                task_id, new_round,
            )
            # The bounce event lands AFTER round_started so it falls inside the
            # new round on the history feed ("Round N · sent back · <note>").
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="review_rejected",
                from_value="review",
                to_value="todo",
                metadata={"note": note[:500]},
            )
            # Count includes the bounce we just logged, so the card's churn chip
            # reflects the new total immediately (optimistic update + broadcast)
            # without waiting for the next full board reload.
            cycle_count = await conn.fetchval(
                """SELECT COUNT(*) FROM mw_task_history
                   WHERE task_id = $1 AND event_type = 'review_rejected'""",
                task_id,
            )

    if not row:
        return None

    # Email + bell the assignee only (skip if unassigned — banner + history
    # still record the bounce-back).
    if current["assigned_to"] is not None:
        await _notify_task_rejected(
            assigned_to=current["assigned_to"],
            company_id=current["company_id"],
            actor_user_id=actor_user_id,
            project_id=project_id,
            project_title=project_title,
            task_id=task_id,
            task_title=row["title"],
            note=note,
        )

    result = _row_to_task(dict(row))
    result["last_moved_at"] = datetime.now(timezone.utc).isoformat()
    result["review_cycle_count"] = cycle_count
    task_payload = dict(result)
    if actor_user_id is not None:
        task_payload["actor_id"] = str(actor_user_id)
    await _broadcast_task_event_safe(project_id, "task.updated", task_payload)
    return result


async def update_project_task(
    project_id: UUID,
    task_id: UUID,
    patch: dict,
    *,
    actor_user_id: Optional[UUID] = None,
    project_title: Optional[str] = None,
) -> Optional[dict]:
    """Partial update. Enforces status↔board_column sync rules."""
    async with get_connection() as conn:
        current = await conn.fetchrow(
            """
            SELECT board_column, status, assigned_to, company_id,
                   description, progress_note
            FROM mw_tasks WHERE id = $1 AND project_id = $2
            """,
            task_id, project_id,
        )
        if not current:
            return None

        # Resolve target column + status with sync rules
        new_column = patch.get("board_column", current["board_column"])
        new_status = patch.get("status", current["status"])

        if "board_column" in patch:
            if new_column not in _ALLOWED_COLUMNS:
                raise ValueError(f"Invalid board_column: {new_column}")
            if new_column == "done":
                new_status = "completed"
            elif current["board_column"] == "done":
                new_status = "pending"

        if "status" in patch:
            if new_status not in ("pending", "completed", "cancelled"):
                raise ValueError(f"Invalid status: {new_status}")
            if new_status == "completed" and new_column != "done":
                new_column = "done"
            elif new_status == "pending" and new_column == "done":
                new_column = "todo"

        # Collect simple field updates
        title = patch.get("title")
        description = patch.get("description")
        priority = patch.get("priority")
        due_date = patch.get("due_date")
        assigned_to = patch.get("assigned_to")
        progress_note = patch.get("progress_note")
        element_id = patch.get("element_id")
        deal_value = patch.get("deal_value")
        probability = patch.get("probability")
        contact_name = patch.get("contact_name")
        contact_company = patch.get("contact_company")
        contact_email = patch.get("contact_email")
        contact_phone = patch.get("contact_phone")
        outcome = patch.get("outcome")
        loss_reason = patch.get("loss_reason")
        next_action_at = patch.get("next_action_at")
        expected_close = patch.get("expected_close")
        pipeline_column = patch.get("pipeline_column")

        if priority is not None and priority not in _ALLOWED_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}")
        if outcome is not None and outcome not in _ALLOWED_OUTCOMES:
            raise ValueError(f"Invalid outcome: {outcome}")
        if pipeline_column is not None and pipeline_column not in _ALLOWED_PIPELINE_COLUMNS:
            raise ValueError(f"Invalid pipeline_column: {pipeline_column}")

        # Compute completed_at in Python rather than via a SQL CASE on $3.
        # asyncpg infers each $N's type from how it's used. $3 is assigned to
        # `status` (varchar column) AND compared to text inside the CASE; the
        # previous attempt cast only the CASE site (`$3::text = 'completed'`)
        # but PG saw two contexts demanding different types for the same
        # parameter and raised
        #   AmbiguousParameterError: inconsistent types deduced for $3
        #   DETAIL: text versus character varying
        # Fix: cast at every use of $3 (and $1) so all references are
        # unambiguously text. PG assignment-casts text -> varchar implicitly.
        completed_at_value = (
            datetime.now(timezone.utc) if new_status == "completed" else None
        )

        row = await conn.fetchrow(
            """
            UPDATE mw_tasks SET
                board_column = $1::text,
                status = $3::text,
                completed_at = CASE
                    WHEN $3::text = 'completed' THEN COALESCE(completed_at, $13::timestamptz)
                    ELSE NULL
                END,
                title = COALESCE($4::text, title),
                description = CASE WHEN $5::boolean THEN $6::text ELSE description END,
                priority = COALESCE($7::text, priority),
                due_date = CASE WHEN $8::boolean THEN $9::date ELSE due_date END,
                assigned_to = CASE WHEN $10::boolean THEN $11::uuid ELSE assigned_to END,
                progress_note = CASE WHEN $14::boolean THEN $15::text ELSE progress_note END,
                element_id = CASE WHEN $16::boolean THEN $17::text ELSE element_id END,
                deal_value = CASE WHEN $18::boolean THEN $19::numeric ELSE deal_value END,
                probability = CASE WHEN $20::boolean THEN $21::smallint ELSE probability END,
                contact_name = CASE WHEN $22::boolean THEN $23::text ELSE contact_name END,
                contact_company = CASE WHEN $24::boolean THEN $25::text ELSE contact_company END,
                contact_email = CASE WHEN $26::boolean THEN $27::text ELSE contact_email END,
                contact_phone = CASE WHEN $28::boolean THEN $29::text ELSE contact_phone END,
                outcome = CASE WHEN $30::boolean THEN $31::text ELSE outcome END,
                loss_reason = CASE WHEN $32::boolean THEN $33::text ELSE loss_reason END,
                next_action_at = CASE WHEN $34::boolean THEN $35::date ELSE next_action_at END,
                expected_close = CASE WHEN $36::boolean THEN $37::date ELSE expected_close END,
                pipeline_column = CASE WHEN $38::boolean THEN $39::text ELSE COALESCE(pipeline_column, 'lead') END,
                -- Clear the reviewer's "needs work" note once the task is
                -- re-submitted to review or marked done — the bounce-back
                -- banner only applies while it sits back in todo/in_progress.
                review_note = CASE WHEN $1::text IN ('review', 'done') THEN NULL ELSE review_note END,
                updated_at = NOW()
            WHERE id = $2 AND project_id = $12
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column,
                      COALESCE(pipeline_column, 'lead') AS pipeline_column,
                      assigned_to, completed_at, created_at, updated_at,
                      progress_note, category, element_id, review_note,
                      deal_value, probability, contact_name, contact_company,
                      contact_email, contact_phone, outcome, loss_reason,
                      next_action_at, expected_close
            """,
            new_column,                   # $1
            task_id,                      # $2
            new_status,                   # $3
            title,                        # $4
            "description" in patch,       # $5
            description,                  # $6
            priority,                     # $7
            "due_date" in patch,          # $8
            due_date,                     # $9
            "assigned_to" in patch,       # $10
            assigned_to,                  # $11
            project_id,                   # $12
            completed_at_value,           # $13
            "progress_note" in patch,     # $14
            progress_note,                # $15
            "element_id" in patch,        # $16
            element_id,                   # $17
            "deal_value" in patch,        # $18
            deal_value,                   # $19
            "probability" in patch,       # $20
            probability,                  # $21
            "contact_name" in patch,      # $22
            contact_name,                 # $23
            "contact_company" in patch,   # $24
            contact_company,              # $25
            "contact_email" in patch,     # $26
            contact_email,                # $27
            "contact_phone" in patch,     # $28
            contact_phone,                # $29
            "outcome" in patch,           # $30
            outcome,                      # $31
            "loss_reason" in patch,       # $32
            loss_reason,                  # $33
            "next_action_at" in patch,    # $34
            next_action_at,               # $35
            "expected_close" in patch,    # $36
            expected_close,               # $37
            "pipeline_column" in patch,   # $38
            pipeline_column,              # $39
        )

        if row and new_column != current["board_column"]:
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="column_change",
                from_value=current["board_column"],
                to_value=new_column,
            )
        if row and "assigned_to" in patch and patch.get("assigned_to") != current["assigned_to"]:
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="assignee_change",
                from_value=str(current["assigned_to"]) if current["assigned_to"] else None,
                to_value=str(patch["assigned_to"]) if patch.get("assigned_to") else None,
            )
        # Surface description / "where we're at" edits in the task viewer
        # timeline so collaborators see when someone added new info.
        # Short previews land in metadata; the full text is already on
        # the task row itself so a follow-up read can pull it.
        if row and "description" in patch and (description or "") != (current["description"] or ""):
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="description_change",
                metadata={
                    "from_preview": (current["description"] or "")[:120],
                    "to_preview": (description or "")[:120],
                },
            )
        if row and "progress_note" in patch and (progress_note or "") != (current["progress_note"] or ""):
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="progress_note_change",
                metadata={
                    "from_preview": (current["progress_note"] or "")[:120],
                    "to_preview": (progress_note or "")[:120],
                },
            )

    if row and "assigned_to" in patch:
        new_assignee = row["assigned_to"]
        old_assignee = current["assigned_to"]
        if (
            new_assignee is not None
            and new_assignee != old_assignee
            and new_assignee != actor_user_id
        ):
            await _notify_task_assigned(
                assigned_to=new_assignee,
                company_id=current["company_id"],
                actor_user_id=actor_user_id or new_assignee,
                project_id=project_id,
                project_title=project_title,
                task_id=task_id,
                task_title=row["title"],
            )

    # Resuming rework (changes_requested → in_progress) is a continuation, not a
    # fresh start — skip the "Task started" blast. Re-submitting to review/done
    # still notifies.
    _is_rework_resume = (
        current["board_column"] == "changes_requested" and new_column == "in_progress"
    )
    if row and new_column != current["board_column"] and not _is_rework_resume:
        await _notify_task_column_transition(
            project_id=project_id,
            company_id=current["company_id"],
            actor_user_id=actor_user_id,
            task_id=task_id,
            task_title=row["title"],
            new_column=new_column,
            project_title=project_title,
        )

    result = _row_to_task(dict(row)) if row else None
    # Stamp the fresh move time so the card's "Moved …" line updates without
    # waiting for the next list reload (the list query derives last_moved_at
    # from mw_task_history; here we approximate it with now()).
    if result is not None and new_column != current["board_column"]:
        result["last_moved_at"] = datetime.now(timezone.utc).isoformat()

    if result is not None:
        task_payload = dict(result)
        if actor_user_id is not None:
            task_payload["actor_id"] = str(actor_user_id)
        await _broadcast_task_event_safe(project_id, "task.updated", task_payload)

    return result


async def delete_project_task(
    project_id: UUID, task_id: UUID, *, actor_user_id: Optional[UUID] = None
) -> bool:
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT title FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
        if existing:
            # Log BEFORE the delete so the FK still resolves. ON DELETE
            # SET NULL on task_id then nulls the reference when the task
            # row is gone — leaving the history row in place with the
            # title cached in metadata so the activity feed can still
            # render "X deleted Task Y".
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="deleted",
                metadata={"title": existing["title"]},
            )
        result = await conn.execute(
            "DELETE FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
        deleted = result.endswith(" 1")
    if deleted:
        payload: dict = {"id": str(task_id)}
        if actor_user_id is not None:
            payload["actor_id"] = str(actor_user_id)
        await _broadcast_task_event_safe(project_id, "task.deleted", payload)
    return deleted


async def mark_project_complete(project_id: UUID) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE mw_projects SET status = 'completed', updated_at = NOW()
            WHERE id = $1
            RETURNING id, status, updated_at
            """,
            project_id,
        )
    if not row:
        raise ValueError("Project not found")
    d = dict(row)
    d["id"] = str(d["id"])
    if d.get("updated_at") is not None:
        d["updated_at"] = d["updated_at"].isoformat()
    return d
