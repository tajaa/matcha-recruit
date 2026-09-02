"""Notification + chat side effects for project kanban tasks.

The five notifier builders (assignment, column transition, send-back, comment)
plus the kanban-move chat post and the actor-identity lookup they share.
Extracted from project_task_service.py (refactor round 2, stage 6): ~390 lines
of message composition wrapped around the four write paths, which read better
without it.

`notification_service` is imported at module scope here. In the old file it was
a lazy in-function import repeated four times — but that module imports only
the DB pool, so there was never a cycle to dodge.
"""
import logging
from typing import Optional
from uuid import UUID

from app.database import get_connection
from app.matcha.services import notification_service as notif_svc

logger = logging.getLogger(__name__)


# Email + bell templates per destination column — every board move notifies
# collaborators (the rework-resume continuation is the one deliberate skip,
# see update_project_task). The formal review-rejection flow notifies the
# assignee separately via _notify_task_rejected; 'changes_requested' here
# covers manual drags into that lane.
_TRANSITION_TEMPLATES: dict[str, dict[str, str]] = {
    "todo":              {"subject": "Moved back to To-do: {title}",  "verb": "moved back to To-do"},
    "in_progress":       {"subject": "Task started: {title}",         "verb": "started"},
    "review":            {"subject": "Ready for review: {title}",     "verb": "moved to review"},
    "changes_requested": {"subject": "Changes requested: {title}",    "verb": "moved to Changes Requested"},
    "done":              {"subject": "Task completed: {title}",       "verb": "completed"},
}


async def post_autopr_context_request(
    *,
    project_id: UUID,
    task_id: UUID,
    actor_user_id: UUID,
    expected_progress_note: str,
    reason: str,
) -> bool:
    """Post one decision-bound Espresso request into the project chat.

    The exact progress note is stored in message metadata. A reply can safely
    become an ``autopr_additional_context`` event only while that same decision
    is still current. Repeated publisher attempts are idempotent for the same
    task+decision. Returns False when the task/decision/chat no longer exists.
    """
    expected = (expected_progress_note or "").strip()
    why = " ".join((reason or "").split())[:600]
    if not expected or not why:
        raise ValueError("AutoPR context requests require a decision and reason")

    from .project_service import ensure_discussion_channel
    from .project_agent.chat import broadcast_espresso_message, persist_espresso_message

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT t.title, t.board_column, t.progress_note,
                      p.company_id,
                      (p.project_data->>'discussion_channel_id')::uuid AS channel_id
               FROM mw_tasks t
               JOIN mw_projects p ON p.id=t.project_id
               WHERE t.id=$1 AND t.project_id=$2""",
            task_id,
            project_id,
        )
    if not row or (row["progress_note"] or "").strip() != expected:
        return False

    channel_id = row["channel_id"]
    if channel_id is None:
        try:
            channel_id = await ensure_discussion_channel(project_id, actor_user_id)
        except Exception:
            logger.warning(
                "Failed to resolve AutoPR context channel project=%s", project_id,
                exc_info=True,
            )
            return False
    if channel_id is None:
        return False

    payload = None
    async with get_connection() as conn:
        async with conn.transaction():
            # The task row is the serialization point for this decision. The
            # freshness recheck, duplicate check, and insert all happen while
            # holding the same row lock and transaction.
            row = await conn.fetchrow(
                """SELECT t.title, t.board_column, t.progress_note,
                          p.company_id,
                          (p.project_data->>'discussion_channel_id')::uuid AS channel_id
                   FROM mw_tasks t
                   JOIN mw_projects p ON p.id=t.project_id
                   WHERE t.id=$1 AND t.project_id=$2
                   FOR UPDATE OF t""",
                task_id,
                project_id,
            )
            if not row or (row["progress_note"] or "").strip() != expected:
                return False
            channel_id = row["channel_id"]
            if channel_id is None:
                return False
            already_posted = await conn.fetchval(
                """SELECT EXISTS(
                       SELECT 1 FROM channel_messages
                       WHERE channel_id=$1
                         AND metadata->>'kind'='autopr_context_request'
                         AND metadata->>'task_id'=$2
                         AND metadata->>'expected_progress_note'=$3
                   )""",
                channel_id,
                str(task_id),
                expected,
            )
            if already_posted:
                return True

            safe_title = " ".join((row["title"] or "ticket").split())
            safe_title = safe_title.replace("⟦", "").replace("⟧", "").replace("|", "/")[:200]
            column = (row["board_column"] or "todo").replace("_", " ").title()
            content = (
                f"⟦ticket:{task_id}|{safe_title}|{column}⟧\n"
                f"This ticket needs additional context because {why} "
                "Reply to this Espresso message with the missing detail, or add it "
                "from the ticket. You can attach screenshots. Start a line with "
                "`--draft-pr`, or say `you can work on this`, to require a draft — "
                "that also overrides a migration-required stop, and the draft then "
                "carries a reviewable migration version nobody runs for you. Use "
                "`--trust-still-broken` to reject "
                "another already-fixed conclusion; add `--test-route=/app/...` for an "
                "approved test-tenant replay. Your reply is bound to this exact decision."
            )
            payload = await persist_espresso_message(
                conn,
                row["company_id"],
                channel_id,
                content,
                metadata={
                    "kind": "autopr_context_request",
                    "project_id": str(project_id),
                    "task_id": str(task_id),
                    "expected_progress_note": expected,
                },
            )
    await broadcast_espresso_message(payload)
    return True


async def post_autopr_result_notification(
    *,
    project_id: UUID,
    task_id: UUID,
    reconsideration_event_id: UUID,
    expected_progress_note: str,
    message: str,
) -> bool:
    """Notify the author of one decision-bound AutoPR result exactly once.

    The current task note and the triggering additional-context event are both
    verified while the task row is locked. That lock serializes retries, so
    the notification lookup plus insert is idempotent without a new database
    constraint. Returns False when the decision or event is stale.
    """
    expected = (expected_progress_note or "").strip()
    result_message = (message or "").strip()
    if not expected or not result_message:
        raise ValueError("AutoPR result notifications require a decision and message")
    if len(result_message) > 1_600:
        raise ValueError("AutoPR result notification message must be 1-1600 characters")

    async with get_connection() as conn:
        async with conn.transaction():
            task = await conn.fetchrow(
                """SELECT t.title, t.progress_note, t.company_id,
                          p.title AS project_title
                   FROM mw_tasks t
                   LEFT JOIN mw_projects p ON p.id=t.project_id
                   WHERE t.id=$1 AND t.project_id=$2
                   FOR UPDATE OF t""",
                task_id,
                project_id,
            )
            if not task or (task["progress_note"] or "").strip() != expected:
                return False

            recipient_id = await conn.fetchval(
                """SELECT actor_user_id
                   FROM mw_task_history
                   WHERE id=$1 AND task_id=$2 AND project_id=$3
                     AND event_type='activity'
                     AND metadata->>'kind'='autopr_additional_context'
                     AND actor_user_id IS NOT NULL""",
                reconsideration_event_id,
                task_id,
                project_id,
            )
            if recipient_id is None:
                return False

            already_notified = await conn.fetchval(
                """SELECT EXISTS(
                       SELECT 1 FROM mw_notifications
                       WHERE user_id=$1 AND type='autopr_result'
                         AND metadata->>'reconsideration_event_id'=$2
                   )""",
                recipient_id,
                str(reconsideration_event_id),
            )
            if already_notified:
                return True

            await notif_svc.create_notification(
                user_id=recipient_id,
                company_id=task["company_id"],
                type="autopr_result",
                title=f"AutoPR result: {task['title']}",
                body=result_message,
                link=f"/work?project={project_id}&task={task_id}",
                metadata={
                    "project_id": str(project_id),
                    "task_id": str(task_id),
                    "project_title": task["project_title"],
                    "task_title": task["title"],
                    "reconsideration_event_id": str(reconsideration_event_id),
                },
                send_email=False,
            )
    return True


async def broadcast_channel_message(channel_id: UUID, payload: dict) -> None:
    """Fan out a persisted channel message through the established bridge.

    This module is one of the two intentional matcha→werk manager import sites.
    Keeping Huume on this bridge avoids growing that cross-app boundary.
    """
    from app.werk.routes.channels_ws import manager

    await manager.broadcast_message(str(channel_id), payload)


async def broadcast_channel_action_updated(channel_id: UUID, action: dict) -> None:
    """Use the established Matcha Work → Werk bridge for action state changes."""
    from app.werk.routes.channels_ws import manager

    await manager._broadcast_to_room(str(channel_id), {
        "type": "channel_action_updated",
        "channel_id": str(channel_id),
        "action": action,
    })


async def broadcast_channel_system_message(
    channel_id: UUID,
    row: dict,
    *,
    mentioned_user_ids: list[str] | None = None,
) -> None:
    """Broadcast a persisted system message through the Werk socket bridge."""
    from app.werk.routes.channels_ws import manager

    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            import json
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            metadata = {}

    payload = {
        "id": str(row["id"]),
        "channel_id": str(channel_id),
        "sender_id": None,
        "sender_name": "Huume",
        "sender_avatar_url": None,
        "content": row["content"],
        "attachments": [],
        "reply_to_id": None,
        "reply_preview": None,
        "reactions": [],
        "created_at": row["created_at"].isoformat(),
        "edited_at": None,
        "mentioned_user_ids": mentioned_user_ids or [],
        "client_message_id": None,
        "message_type": row.get("message_type", "system"),
        "metadata": metadata,
    }
    await manager.broadcast_message(str(channel_id), payload)


async def notify_event_assignment(
    *,
    assignment_id: UUID,
    event_id: UUID,
    company_id: UUID,
    channel_id: UUID,
    channel_name: str,
    message_id: UUID | None,
    assignee_user_id: UUID,
    assigned_by: UUID,
    title: str,
    completed: bool = False,
) -> None:
    """Send the direct assignment/completion bell notification."""
    if completed and assignee_user_id == assigned_by:
        return
    recipient = assigned_by if completed else assignee_user_id
    kind = "event_assignment_completed" if completed else "event_assigned"
    notification_title = (
        f"Assignment completed: {title}" if completed else f"Assigned: {title}"
    )
    body = (
        f"A teammate completed this assignment in #{channel_name}."
        if completed
        else f"You were assigned this event in #{channel_name}."
    )
    try:
        from app.werk.services.channel_links import resolve_channel_app_path
        channel_path = await resolve_channel_app_path(
            channel_id,
            suffix=f"?message={message_id}" if message_id else None,
        )
        await notif_svc.create_notification(
            user_id=recipient,
            company_id=company_id,
            type=kind,
            title=notification_title,
            body=body,
            link=channel_path,
            metadata={
                "assignment_id": str(assignment_id),
                "event_id": str(event_id),
                "channel_id": str(channel_id),
                "message_id": str(message_id) if message_id else None,
                "assigned_by": str(assigned_by),
            },
        )
    except Exception:
        logger.warning("Failed to notify event assignment %s", assignment_id, exc_info=True)


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


async def _lookup_actor_identity(actor_user_id: Optional[UUID]) -> tuple[str, Optional[str]]:
    """Resolve a user's display name + avatar_url for notification/chat copy.
    Shared by the task_progress notification and the kanban-move chat post so
    both agree on the same actor identity from one query. Falls back to
    ("Someone", None) when unresolvable.
    """
    if actor_user_id is None:
        return "Someone", None
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name,
                       u.avatar_url AS avatar_url
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id = $1
                """, actor_user_id
            )
        if row and row["name"]:
            return row["name"], row["avatar_url"]
    except Exception as e:
        logger.warning("Failed to look up actor %s identity: %s", actor_user_id, e)
    return "Someone", None


async def _post_kanban_move_to_chat(
    *,
    project_id: UUID,
    task_id: UUID,
    task_title: str,
    new_column: str,
    actor_user_id: Optional[UUID],
    actor_name: str,
    actor_avatar_url: Optional[str],
) -> None:
    """Auto-posts a plain chat message into the project's discussion channel
    on every board-column move, reusing the same per-column verb copy as the
    task_progress notification (_TRANSITION_TEMPLATES) so the banner and chat
    always say the same thing. Posted as a normal channel_messages row under
    the mover's own identity — not a system/bot event — so it renders through
    the existing chat pipeline with zero client changes. Deliberately skips
    channel/member activity bumps, mention parsing, and the channel_message
    in-app notification: this is an automated echo of the task_progress
    notification, not a real contribution, and double-notifying would be noise.
    """
    if actor_user_id is None:
        return
    tpl = _TRANSITION_TEMPLATES.get(new_column)
    if tpl is None:
        return

    from .project_service import ensure_discussion_channel

    try:
        channel_id = await ensure_discussion_channel(project_id, actor_user_id)
    except Exception as e:
        logger.warning("Failed to resolve discussion channel for project %s: %s", project_id, e)
        return
    if channel_id is None:
        return

    content = f'{tpl["verb"]} "{task_title}"'
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO channel_messages (channel_id, sender_id, content)
                VALUES ($1, $2, $3)
                RETURNING id, created_at
                """,
                channel_id, actor_user_id, content,
            )
    except Exception as e:
        logger.warning("Failed to insert kanban-move chat message task=%s: %s", task_id, e)
        return

    try:
        await broadcast_channel_message(channel_id, {
            "id": str(row["id"]),
            "channel_id": str(channel_id),
            "sender_id": str(actor_user_id),
            "sender_name": actor_name,
            "sender_avatar_url": actor_avatar_url,
            "content": content,
            "attachments": [],
            "reply_to_id": None,
            "reply_preview": None,
            "reactions": [],
            "created_at": row["created_at"].isoformat(),
            "edited_at": None,
            "mentioned_user_ids": [],
            "client_message_id": None,
        })
    except Exception as e:
        logger.warning("Failed to broadcast kanban-move chat message task=%s: %s", task_id, e)


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
    """Email + bell every active project collaborator (minus the actor) on
    any board-column move (per-destination copy in _TRANSITION_TEMPLATES).
    The rework-resume continuation (changes_requested → in_progress) is
    skipped by the caller.
    """
    tpl = _TRANSITION_TEMPLATES.get(new_column)
    if tpl is None:
        return

    from .project_service import list_collaborators
    actor_name, _actor_avatar_url = await _lookup_actor_identity(actor_user_id)

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
    try:
        async with get_connection() as conn:
            task = await conn.fetchrow(
                """SELECT t.company_id, t.assigned_to, t.created_by, t.title,
                          p.title AS project_title
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
