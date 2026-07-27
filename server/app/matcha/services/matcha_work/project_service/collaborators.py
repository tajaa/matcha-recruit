"""Project collaborators and their discussion channel: the project chat rows, the
collaborator-scoped project view, add/remove, channel creation and membership
reconciliation, and the link list scraped from chat.
"""
import json
import logging
import re
from typing import Optional
from uuid import UUID
from app.database import get_connection
from app.matcha.services.matcha_work.matcha_work_modes import MODE_COLUMNS

from ._config import _URL_RE, _URL_TRAILING
from ._data import _parse_project

logger = logging.getLogger(__name__)


async def create_project_chat(project_id: UUID, company_id: UUID, user_id: UUID, title: str | None = None) -> dict:
    async with get_connection() as conn:
        # Count existing chats to generate title
        if not title:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mw_threads WHERE project_id = $1", project_id
            )
            title = f"Chat {count + 1}"

        # Seed initial thread state for recruiting projects so the AI
        # infers skill="project" from the first message instead of "chat"
        project_row = await conn.fetchrow(
            "SELECT project_type, title FROM mw_projects WHERE id = $1", project_id
        )
        initial_state = '{}'
        if project_row and project_row["project_type"] == 'recruiting':
            initial_state = json.dumps({
                "project_title": project_row["title"],
                "project_sections": [],
            })
        elif project_row and project_row["project_type"] == 'presentation':
            initial_state = json.dumps({
                "presentation_title": "",
                "slides": [],
            })

        row = await conn.fetchrow(
            f"""
            INSERT INTO mw_threads (company_id, created_by, title, project_id, current_state)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id, title, status, version, created_at, updated_at, is_pinned,
                      {', '.join(MODE_COLUMNS)}, project_id
            """,
            company_id, user_id, title, project_id, initial_state,
        )
        # Update project timestamp
        await conn.execute(
            "UPDATE mw_projects SET updated_at = NOW() WHERE id = $1", project_id
        )
    return dict(row)


async def list_project_chats(project_id: UUID, company_id: UUID, user_id: UUID) -> list[dict]:
    """List AI chat threads scoped to a project, private-per-person.

    A user sees threads they created in this project plus any project thread
    explicitly shared with them (via mw_thread_collaborators). Threads created
    by other collaborators that haven't been shared are hidden. `company_id` is
    accepted for signature parity / future tenant filtering; access is already
    gated by _verify_project_access at the route.
    """
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT t.id, t.title, t.task_type, t.status, t.version, t.is_pinned,
                   {', '.join(f't.{c}' for c in MODE_COLUMNS)},
                   t.created_by, t.created_at, t.updated_at,
                   (SELECT COUNT(*) FROM mw_thread_collaborators c WHERE c.thread_id = t.id)
                       AS collaborator_count
            FROM mw_threads t
            WHERE t.project_id = $1 AND (
                t.created_by = $2
                OR EXISTS (
                    SELECT 1 FROM mw_thread_collaborators c
                    WHERE c.thread_id = t.id AND c.user_id = $2
                )
            )
            ORDER BY t.is_pinned DESC, t.updated_at DESC
            """,
            project_id, user_id,
        )
    return [dict(r) for r in rows]


async def get_project_as_collaborator(project_id: UUID, user_id: UUID) -> Optional[tuple[dict, str]]:
    """Get a project if the user is an active collaborator. Returns (project, role) or None."""
    async with get_connection() as conn:
        collab = await conn.fetchrow(
            """
            SELECT role FROM mw_project_collaborators
            WHERE project_id = $1 AND user_id = $2 AND status = 'active'
            """,
            project_id, user_id,
        )
        if not collab:
            return None
        row = await conn.fetchrow("SELECT * FROM mw_projects WHERE id = $1", project_id)
        if not row:
            return None
        project = _parse_project(row)
        chats = await conn.fetch(
            """
            SELECT id, title, status, version, created_at, updated_at, is_pinned
            FROM mw_threads
            WHERE project_id = $1
            ORDER BY created_at ASC
            """,
            project_id,
        )
        project["chats"] = [dict(c) for c in chats]
        project["chat_count"] = len(chats)
        project["collaborator_role"] = collab["role"]
    return project, collab["role"]


async def list_collaborators(project_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT pc.user_id, pc.role, pc.created_at,
                   COALESCE(a.name, u.email) AS name,
                   u.email, u.avatar_url
            FROM mw_project_collaborators pc
            JOIN users u ON u.id = pc.user_id
            LEFT JOIN admins a ON a.user_id = pc.user_id
            WHERE pc.project_id = $1 AND pc.status = 'active'
            ORDER BY pc.created_at ASC
            """,
            project_id,
        )
    return [dict(r) for r in rows]


async def ensure_discussion_channel(project_id: UUID, current_user_id: UUID) -> Optional[UUID]:
    """Get or create a private channel for a collab project's discussion.

    The channel id is stored at `project_data.discussion_channel_id`. All
    active collaborators are added as channel members on creation.
    Idempotent — returns the existing channel id if already linked.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            project = await conn.fetchrow(
                "SELECT id, company_id, title, project_type, project_data FROM mw_projects WHERE id = $1 FOR UPDATE",
                project_id,
            )
            if not project:
                return None
            if project["project_type"] != "collab":
                return None

            data = project["project_data"]
            if isinstance(data, str):
                try:
                    data = json.loads(data or "{}")
                except (json.JSONDecodeError, ValueError):
                    data = {}
            data = data or {}

            title = (project["title"] or "Project").strip() or "Project"

            existing_id = data.get("discussion_channel_id")
            if existing_id:
                chan_uuid = UUID(existing_id) if isinstance(existing_id, str) else existing_id
                # Self-heal the channel name to the current project title, so a
                # project renamed before this sync existed (or via any path that
                # skipped propagation) gets a legible sidebar name on next open.
                # No-op when already in sync (IS DISTINCT FROM guard).
                await conn.execute(
                    "UPDATE channels SET name = $1 WHERE id = $2 AND name IS DISTINCT FROM $1",
                    title, chan_uuid,
                )
                return chan_uuid

            company_id = project["company_id"]

            base_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "project"
            slug = f"proj-{base_slug}"
            suffix = 0
            while await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM channels WHERE company_id = $1 AND slug = $2)",
                company_id, slug,
            ):
                suffix += 1
                slug = f"proj-{base_slug}-{suffix}"

            channel = await conn.fetchrow(
                """
                INSERT INTO channels (company_id, name, slug, description, created_by, visibility,
                    is_paid, currency, inactivity_warning_days)
                VALUES ($1, $2, $3, $4, $5, 'private', FALSE, 'usd', 3)
                RETURNING id
                """,
                company_id,
                title,
                slug,
                f"Discussion channel for collab project: {title}",
                current_user_id,
            )
            channel_id = channel["id"]

            await conn.execute(
                "INSERT INTO channel_members (channel_id, user_id, role, last_contributed_at) VALUES ($1, $2, 'owner', NOW())",
                channel_id, current_user_id,
            )

            collab_rows = await conn.fetch(
                """
                SELECT user_id FROM mw_project_collaborators
                WHERE project_id = $1 AND status = 'active' AND user_id != $2
                """,
                project_id, current_user_id,
            )
            for row in collab_rows:
                await conn.execute(
                    """
                    INSERT INTO channel_members (channel_id, user_id, role, last_contributed_at)
                    VALUES ($1, $2, 'member', NOW())
                    ON CONFLICT (channel_id, user_id) DO NOTHING
                    """,
                    channel_id, row["user_id"],
                )

            data["discussion_channel_id"] = str(channel_id)
            await conn.execute(
                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                json.dumps(data), project_id,
            )
            return channel_id


async def list_project_links(project_id: UUID) -> list[dict]:
    """Links shared in the project's collab chat: extract http(s) URLs from the
    discussion channel's messages. Deduped on URL, newest first. Returns
    [{url, sender_name, created_at}]. Empty when the project has no chat."""
    async with get_connection() as conn:
        channel_id = await conn.fetchval(
            "SELECT (project_data->>'discussion_channel_id')::uuid FROM mw_projects WHERE id = $1",
            project_id,
        )
        if not channel_id:
            return []
        rows = await conn.fetch(
            """
            SELECT m.content, m.created_at,
                   COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS sender_name
            FROM channel_messages m
            JOIN users u ON u.id = m.sender_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE m.channel_id = $1
              AND m.deleted_at IS NULL
              AND m.content ~* 'https?://'
            ORDER BY m.created_at DESC
            LIMIT 500
            """,
            channel_id,
        )
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        for raw in _URL_RE.findall(r["content"] or ""):
            url = raw.rstrip(_URL_TRAILING)
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({
                "url": url,
                "sender_name": r["sender_name"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            })
    return out


async def add_collaborator(project_id: UUID, user_id: UUID, invited_by: UUID) -> list[dict]:
    """Invite a user as a PENDING collaborator: send an inbox message + a bell
    notification, but do NOT grant access. They join only when they accept
    (accept_project_invite flips them to active and adds them to the chat).
    Returns the (still active-only) collaborator list — the invitee won't appear
    until they accept, which is the point."""
    async with get_connection() as conn:
        target = await conn.fetchrow(
            "SELECT id FROM users WHERE id = $1 AND is_active = true",
            user_id,
        )
        if not target:
            raise ValueError("User not found")
        if user_id == invited_by:
            raise ValueError("You cannot invite yourself")
        existing = await conn.fetchrow(
            "SELECT status FROM mw_project_collaborators WHERE project_id = $1 AND user_id = $2",
            project_id, user_id,
        )
        if existing and existing["status"] == "active":
            raise ValueError("User is already a collaborator")
        # Pending — not active. A prior pending/removed row is re-armed.
        await conn.execute(
            """
            INSERT INTO mw_project_collaborators (project_id, user_id, invited_by, role, status)
            VALUES ($1, $2, $3, 'collaborator', 'pending')
            ON CONFLICT (project_id, user_id)
            DO UPDATE SET status = 'pending', invited_by = $3, created_at = NOW()
            """,
            project_id, user_id, invited_by,
        )

        project = await conn.fetchrow("SELECT title, company_id FROM mw_projects WHERE id = $1", project_id)
        inviter = await conn.fetchrow("SELECT email FROM users WHERE id = $1", invited_by)
        inviter_client = await conn.fetchrow("SELECT name FROM clients WHERE user_id = $1", invited_by)
        inviter_name = (inviter_client["name"] if inviter_client and inviter_client["name"] else None) or inviter["email"].split("@")[0]
        project_title = project["title"] if project else "a project"

        msg_content = f"**{inviter_name}** invited you to join the project **{project_title}**. Open your projects to accept or decline."
        conversation = await conn.fetchrow(
            """INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
               VALUES ($1, false, $2, NOW(), $3)
               RETURNING id""",
            f"Project Invite: {project_title}", invited_by, msg_content[:100],
        )
        conv_id = conversation["id"]
        await conn.execute("INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, invited_by)
        await conn.execute("INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, user_id)
        await conn.execute("INSERT INTO inbox_messages (conversation_id, sender_id, content) VALUES ($1, $2, $3)", conv_id, invited_by, msg_content)

    # Bell notification for the invitee (own connection; best-effort — never
    # fail the invite over a notification hiccup).
    if project and project["company_id"]:
        try:
            from app.matcha.services import notification_service as notif_svc
            await notif_svc.create_notification(
                user_id=user_id,
                company_id=project["company_id"],
                type="project_invite",
                title=f"Project invite from {inviter_name}",
                body=f"You've been invited to join \"{project_title}\"",
                link="/work",
                metadata={"project_id": str(project_id), "invited_by": str(invited_by)},
            )
        except Exception as exc:
            logger.warning("Failed to create invite notification: %s", exc)

    return await list_collaborators(project_id)


async def ensure_collaborator_in_discussion_channel(project_id: UUID, user_id: UUID) -> None:
    """Add one user to the project's discussion channel (if it exists). Called
    when an invite is accepted — the chat is the collab surface, so a new active
    collaborator joins it. No-op for non-collab projects or before the channel
    is created."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT project_type, project_data FROM mw_projects WHERE id = $1",
            project_id,
        )
        if not row or row["project_type"] != "collab":
            return
        data = row["project_data"]
        if isinstance(data, str):
            try:
                data = json.loads(data or "{}")
            except (json.JSONDecodeError, ValueError):
                data = {}
        data = data or {}
        chan_id = data.get("discussion_channel_id")
        if not chan_id:
            return
        await conn.execute(
            """
            INSERT INTO channel_members (channel_id, user_id, role, last_contributed_at)
            VALUES ($1, $2, 'member', NOW())
            ON CONFLICT (channel_id, user_id) DO NOTHING
            """,
            UUID(chan_id) if isinstance(chan_id, str) else chan_id,
            user_id,
        )


async def remove_collaborator(project_id: UUID, user_id: UUID, removed_by: UUID) -> list[dict]:
    """Remove a collaborator. Only the owner can remove. Cannot remove the owner."""
    async with get_connection() as conn:
        # Check that remover is the owner
        remover = await conn.fetchrow(
            "SELECT role FROM mw_project_collaborators WHERE project_id = $1 AND user_id = $2 AND status = 'active'",
            project_id, removed_by,
        )
        if not remover or remover["role"] != "owner":
            raise PermissionError("Only the project owner can remove collaborators")
        # Cannot remove the owner
        target = await conn.fetchrow(
            "SELECT role FROM mw_project_collaborators WHERE project_id = $1 AND user_id = $2 AND status = 'active'",
            project_id, user_id,
        )
        if not target:
            raise ValueError("User is not a collaborator on this project")
        if target["role"] == "owner":
            raise PermissionError("Cannot remove the project owner")
        await conn.execute(
            "UPDATE mw_project_collaborators SET status = 'removed' WHERE project_id = $1 AND user_id = $2",
            project_id, user_id,
        )
    return await list_collaborators(project_id)
