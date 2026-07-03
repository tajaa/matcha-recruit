"""Project collaboration: discussion channel bootstrap, project collaborators
CRUD, invite send/accept/decline, pending-invite listing, admin-user search,
and thread collaborators (list/add/remove/search).

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.routes.matcha_work._shared import _verify_project_access
from app.matcha.services import matcha_work_document as doc_svc

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/projects/{project_id}/discussion-channel")
async def ensure_project_discussion_channel(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get or create the private channel for a collab project's discussion.

    Idempotent. The channel is shared by all active collaborators and is
    the recommended chat surface for the collab project type. Returns
    `{ "channel_id": "<uuid>" }` for collab projects, or 404 for any
    other project type.

    Authorisation: the caller is allowed if they own the project's
    company OR are an active collaborator. This mirrors the visibility
    rule used by list_projects.
    """
    from app.matcha.services import project_service as proj_svc

    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        proj = await conn.fetchrow(
            "SELECT company_id FROM mw_projects WHERE id = $1",
            project_id,
        )
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")

        is_owner_tenant = company_id is not None and proj["company_id"] == company_id
        is_collaborator = False
        if not is_owner_tenant:
            is_collaborator = bool(await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM mw_project_collaborators
                    WHERE project_id = $1 AND user_id = $2 AND status = 'active'
                )
                """,
                project_id, current_user.id,
            ))
        if not is_owner_tenant and not is_collaborator:
            raise HTTPException(status_code=404, detail="Project not found")

    channel_id = await proj_svc.ensure_discussion_channel(project_id, current_user.id)
    if channel_id is None:
        raise HTTPException(status_code=400, detail="Discussion channels are only available for collab projects")
    return {"channel_id": str(channel_id)}

@router.get("/projects/{project_id}/collaborators")
async def list_project_collaborators(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List collaborators on a project."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.list_collaborators(project_id)

@router.post("/projects/{project_id}/collaborators")
async def add_project_collaborator(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Add a user as a collaborator. Only the project owner can invite."""
    from app.matcha.services import project_service as proj_svc
    _project, role = await _verify_project_access(project_id, current_user)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the project owner can add collaborators")
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        return await proj_svc.add_collaborator(project_id, UUID(user_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/projects/{project_id}/collaborators/{user_id}")
async def remove_project_collaborator(
    project_id: UUID,
    user_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove a collaborator from a project. Only the owner can do this."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    try:
        return await proj_svc.remove_collaborator(project_id, user_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/projects/{project_id}/invite")
async def invite_to_project(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Invite a user to a project by email. Creates pending collaborator + inbox notification + email."""
    from app.core.services.email import get_email_service

    await _verify_project_access(project_id, current_user)

    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")

    async with get_connection() as conn:
        # Look up user by email
        invitee = await conn.fetchrow("SELECT id, email FROM users WHERE email = $1 AND is_active = true", email)
        if not invitee:
            raise HTTPException(status_code=404, detail="User not found. They need to create an account first.")

        invitee_id = invitee["id"]

        if invitee_id == current_user.id:
            raise HTTPException(status_code=400, detail="You cannot invite yourself")

        # Check if already a collaborator
        existing = await conn.fetchrow(
            "SELECT status FROM mw_project_collaborators WHERE project_id = $1 AND user_id = $2",
            project_id, invitee_id,
        )
        if existing:
            if existing["status"] == "active":
                raise HTTPException(status_code=400, detail="User is already a collaborator")
            # Was pending or removed — re-invite as pending
            await conn.execute(
                "UPDATE mw_project_collaborators SET status = 'pending', invited_by = $3, created_at = NOW() WHERE project_id = $1 AND user_id = $2",
                project_id, invitee_id, current_user.id,
            )
        else:
            await conn.execute(
                """INSERT INTO mw_project_collaborators (project_id, user_id, invited_by, role, status)
                   VALUES ($1, $2, $3, 'collaborator', 'pending')""",
                project_id, invitee_id, current_user.id,
            )

        # Get project title and inviter name for notifications
        project = await conn.fetchrow("SELECT title FROM mw_projects WHERE id = $1", project_id)
        inviter = await conn.fetchrow("SELECT email FROM users WHERE id = $1", current_user.id)
        inviter_client = await conn.fetchrow("SELECT name FROM clients WHERE user_id = $1", current_user.id)
        inviter_name = (inviter_client["name"] if inviter_client else None) or inviter["email"].split("@")[0]
        project_title = project["title"] if project else "a project"

        # Create inbox notification
        msg_content = f"**{inviter_name}** has invited you to join the project **{project_title}**. Go to your projects to accept or decline."
        conversation = await conn.fetchrow(
            """INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
               VALUES ($1, false, $2, NOW(), $3)
               RETURNING id""",
            f"Project Invite: {project_title}", current_user.id, msg_content[:100],
        )
        conv_id = conversation["id"]
        await conn.execute(
            "INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, current_user.id,
        )
        await conn.execute(
            "INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, invitee_id,
        )
        await conn.execute(
            """INSERT INTO inbox_messages (conversation_id, sender_id, content)
               VALUES ($1, $2, $3)""",
            conv_id, current_user.id, msg_content,
        )

    # Send email notification
    email_svc = get_email_service()
    if email_svc.is_configured():
        settings = get_settings()
        base_url = settings.app_base_url.rstrip("/")
        try:
            await email_svc.send_email(
                to_email=email,
                to_name=email.split("@")[0],
                subject=f"{inviter_name} invited you to a project on Matcha",
                html_content=f"""
                <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto;">
                    <h2 style="color: #e4e4e7;">Project Invitation</h2>
                    <p style="color: #a1a1aa;"><strong>{inviter_name}</strong> invited you to join <strong>{project_title}</strong>.</p>
                    <a href="{base_url}/work"
                       style="display: inline-block; background: #10b981; color: white; padding: 12px 28px;
                              border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: 600;">
                        View Projects
                    </a>
                </div>
                """,
            )
        except Exception as exc:
            logger.warning("Failed to send project invite email: %s", exc)

    # Create MW notification for the invitee
    try:
        from app.matcha.services import notification_service as notif_svc
        company_id = await get_client_company_id(current_user)
        await notif_svc.create_notification(
            user_id=invitee_id,
            company_id=company_id,
            type="project_invite",
            title=f"Project invite from {inviter_name}",
            body=f"You've been invited to join \"{project_title}\"",
            link=f"/work",
            metadata={"project_id": str(project_id), "invited_by": str(current_user.id)},
        )
    except Exception as e:
        logger.warning("Failed to create invite notification: %s", e)

    return {"invited": True, "email": email}

async def _create_inbox_dm(*, from_user_id: UUID, to_user_id: UUID, conv_title: str, content: str) -> None:
    """Create a 1:1 inbox conversation carrying a single message. Used for the
    project invite-accepted ("X joined") notice."""
    async with get_connection() as conn:
        conv = await conn.fetchrow(
            """INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
               VALUES ($1, false, $2, NOW(), $3) RETURNING id""",
            conv_title, from_user_id, content[:100],
        )
        cid = conv["id"]
        await conn.execute("INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", cid, from_user_id)
        await conn.execute("INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", cid, to_user_id)
        await conn.execute("INSERT INTO inbox_messages (conversation_id, sender_id, content) VALUES ($1, $2, $3)", cid, from_user_id, content)

@router.post("/projects/{project_id}/invite/accept")
async def accept_project_invite(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Accept a pending invite — join the project + its chat, and tell the
    creator/inviter you've joined (toast + inbox + bell)."""
    from app.matcha.services import project_service as proj_svc
    from app.matcha.services import notification_service as notif_svc

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE mw_project_collaborators
               SET status = 'active'
               WHERE project_id = $1 AND user_id = $2 AND status = 'pending'
               RETURNING invited_by""",
            project_id, current_user.id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="No pending invitation found")
        invited_by = row["invited_by"]
        proj = await conn.fetchrow(
            "SELECT title, created_by, company_id FROM mw_projects WHERE id = $1", project_id
        )

    # Now active → join the discussion channel (the collab chat surface).
    try:
        await proj_svc.ensure_collaborator_in_discussion_channel(project_id, current_user.id)
    except Exception as e:
        logger.warning("add accepted collaborator to channel failed: %s", e)

    # Tell the creator + inviter that someone joined: bell + inbox now, and the
    # WS push behind create_notification drives the in-app toast on their client.
    joiner_name = await proj_svc._resolve_actor_name(current_user.id) or "Someone"
    title = proj["title"] if proj else "a project"
    company_id = proj["company_id"] if proj else None
    recipients = {
        r for r in [(proj["created_by"] if proj else None), invited_by]
        if r is not None and r != current_user.id
    }
    for rid in recipients:
        try:
            await notif_svc.create_notification(
                user_id=rid,
                company_id=company_id,
                type="collab_joined",
                title=f"{joiner_name} joined {title}",
                body=f"{joiner_name} has joined the collab",
                link="/work",
                metadata={"project_id": str(project_id), "project_title": title, "joiner_name": joiner_name},
            )
            await _create_inbox_dm(
                from_user_id=current_user.id, to_user_id=rid,
                conv_title=f"Joined: {title}",
                content=f"**{joiner_name}** has joined **{title}**.",
            )
        except Exception as e:
            logger.warning("collab_joined notify failed for %s: %s", rid, e)

    return {"accepted": True}

@router.post("/projects/{project_id}/invite/decline")
async def decline_project_invite(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Decline a pending project invitation."""
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE mw_project_collaborators
               SET status = 'removed'
               WHERE project_id = $1 AND user_id = $2 AND status = 'pending'""",
            project_id, current_user.id,
        )
        if result.endswith("0"):
            raise HTTPException(status_code=404, detail="No pending invitation found")
    return {"declined": True}

@router.get("/project-invites")
async def list_pending_invites(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all pending project invitations for the current user."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT c.project_id, p.title AS project_title,
                      u.email AS invited_by_email, cl.name AS invited_by_name,
                      c.created_at
               FROM mw_project_collaborators c
               JOIN mw_projects p ON p.id = c.project_id
               JOIN users u ON u.id = c.invited_by
               LEFT JOIN clients cl ON cl.user_id = c.invited_by
               WHERE c.user_id = $1 AND c.status = 'pending'
               ORDER BY c.created_at DESC""",
            current_user.id,
        )
    return [
        {
            "project_id": str(r["project_id"]),
            "project_title": r["project_title"],
            "invited_by": r["invited_by_name"] or r["invited_by_email"].split("@")[0],
            "invited_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]

@router.get("/admin-users/search")
async def search_admin_users_endpoint(
    q: str = Query(..., min_length=2, max_length=100),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Search admin users for the collaborator invite picker."""
    from app.matcha.services import project_service as proj_svc
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can search admin users")
    return await proj_svc.search_admin_users(q, current_user.id)

@router.get("/threads/{thread_id}/collaborators")
async def list_thread_collaborators(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List collaborators on a thread with user info.

    Always includes the thread creator as a synthetic 'owner' row even if
    they don't have an explicit mw_thread_collaborators entry. Without this,
    the moment the first invitee is added the owner disappears from the
    collaborator list and their client-side `isOwner` flag flips to false.
    """
    company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    owner_id = thread.get("created_by")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT tc.user_id, tc.role, tc.created_at,
                   u.email, u.avatar_url,
                   COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM mw_thread_collaborators tc
            JOIN users u ON u.id = tc.user_id
            LEFT JOIN clients cl ON cl.user_id = tc.user_id
            LEFT JOIN employees e ON e.user_id = tc.user_id
            LEFT JOIN admins a ON a.user_id = tc.user_id
            WHERE tc.thread_id = $1
            ORDER BY tc.created_at
            """,
            thread_id,
        )

        result = [
            {
                "user_id": str(r["user_id"]),
                "name": r["name"],
                "email": r["email"],
                "role": r["role"],
                "avatar_url": r["avatar_url"],
                "added_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

        # Include the thread creator as a synthetic owner row if not already present
        if owner_id is not None and not any(c["user_id"] == str(owner_id) for c in result):
            owner_row = await conn.fetchrow(
                """
                SELECT u.id, u.email, u.avatar_url,
                       COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
                FROM users u
                LEFT JOIN clients cl ON cl.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id = $1
                """,
                owner_id,
            )
            if owner_row:
                result.insert(0, {
                    "user_id": str(owner_row["id"]),
                    "name": owner_row["name"],
                    "email": owner_row["email"],
                    "role": "owner",
                    "avatar_url": owner_row["avatar_url"],
                    "added_at": None,
                })

    return result

@router.post("/threads/{thread_id}/collaborators")
async def add_thread_collaborator(
    thread_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Add a collaborator to a thread. Only the thread owner or admin can invite."""
    company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Only the owner or an admin can add collaborators
    if current_user.role != "admin" and thread["created_by"] != current_user.id:
        raise HTTPException(status_code=403, detail="Only the thread owner can add collaborators")

    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        collab_user_id = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid user_id")

    if collab_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot add yourself as a collaborator")

    async with get_connection() as conn:
        # Verify user exists and is active
        target_user = await conn.fetchrow(
            "SELECT id, email FROM users WHERE id = $1 AND is_active = true",
            collab_user_id,
        )
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if already a collaborator
        existing = await conn.fetchval(
            "SELECT id FROM mw_thread_collaborators WHERE thread_id = $1 AND user_id = $2",
            thread_id, collab_user_id,
        )
        if existing:
            raise HTTPException(status_code=400, detail="User is already a collaborator")

        await conn.execute(
            """INSERT INTO mw_thread_collaborators (thread_id, user_id, invited_by, role)
               VALUES ($1, $2, $3, 'collaborator')""",
            thread_id, collab_user_id, current_user.id,
        )

        # Send inbox notification
        try:
            inviter = await conn.fetchrow("SELECT email FROM users WHERE id = $1", current_user.id)
            inviter_client = await conn.fetchrow("SELECT name FROM clients WHERE user_id = $1", current_user.id)
            inviter_name = (inviter_client["name"] if inviter_client else None) or inviter["email"].split("@")[0]
            thread_title = thread.get("title") or "a thread"

            msg_content = f"**{inviter_name}** has invited you to collaborate on the thread **{thread_title}**."
            conversation = await conn.fetchrow(
                """INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
                   VALUES ($1, false, $2, NOW(), $3)
                   RETURNING id""",
                f"Thread Invite: {thread_title}", current_user.id, msg_content[:100],
            )
            conv_id = conversation["id"]
            await conn.execute(
                "INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, current_user.id,
            )
            await conn.execute(
                "INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, collab_user_id,
            )
            await conn.execute(
                """INSERT INTO inbox_messages (conversation_id, sender_id, content)
                   VALUES ($1, $2, $3)""",
                conv_id, current_user.id, msg_content,
            )
        except Exception as e:
            logger.warning("Failed to send thread collaborator inbox notification: %s", e)

        # Create MW notification
        try:
            from app.matcha.services import notification_service as notif_svc
            inviter_client = await conn.fetchrow("SELECT name FROM clients WHERE user_id = $1", current_user.id)
            inviter_name = (inviter_client["name"] if inviter_client else None) or "Someone"
            await notif_svc.create_notification(
                user_id=collab_user_id,
                company_id=company_id,
                type="thread_collaborator_added",
                title=f"{inviter_name} added you to a thread",
                body=f"You've been added as a collaborator on \"{thread.get('title', 'a thread')}\"",
                link="/work",
                metadata={"thread_id": str(thread_id), "invited_by": str(current_user.id)},
            )
        except Exception as e:
            logger.warning("Failed to create thread collaborator notification: %s", e)

    return {"added": True, "user_id": str(collab_user_id)}

@router.delete("/threads/{thread_id}/collaborators/{user_id}")
async def remove_thread_collaborator(
    thread_id: UUID,
    user_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove a collaborator from a thread. Owner, admin, or the collaborator themselves can do this."""
    company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Allow removal if: admin, thread owner, or self-removal
    is_owner = thread["created_by"] == current_user.id
    is_self = user_id == current_user.id
    if current_user.role != "admin" and not is_owner and not is_self:
        raise HTTPException(status_code=403, detail="Only the thread owner can remove collaborators")

    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_thread_collaborators WHERE thread_id = $1 AND user_id = $2",
            thread_id, user_id,
        )
        if result.endswith("0"):
            raise HTTPException(status_code=404, detail="Collaborator not found")

    return {"removed": True, "user_id": str(user_id)}

@router.get("/threads/{thread_id}/collaborators/search")
async def search_thread_collaborator_candidates(
    thread_id: UUID,
    q: str = Query(..., min_length=2, max_length=100),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Search users to invite as thread collaborators."""
    company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    pattern = f"%{q}%"
    async with get_connection() as conn:
        # Search eligible invitees: same-company users + admins + accepted cross-tenant connections
        rows = await conn.fetch(
            """
            SELECT DISTINCT u.id AS user_id, u.email, u.avatar_url,
                   COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM users u
            LEFT JOIN clients cl ON cl.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id != $1
              AND u.is_active = true
              AND (
                  COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, '') ILIKE $2
                  OR u.email ILIKE $2
              )
              AND (
                  (cl.company_id = $3)
                  OR (e.org_id = $3)
                  OR (a.user_id IS NOT NULL)
                  OR EXISTS (
                      SELECT 1 FROM user_connections uc
                      WHERE uc.status = 'accepted'
                        AND (
                          (uc.user_id = $1 AND uc.connected_user_id = u.id)
                          OR (uc.connected_user_id = $1 AND uc.user_id = u.id)
                        )
                  )
              )
              AND NOT EXISTS(
                  SELECT 1 FROM mw_thread_collaborators tc
                  WHERE tc.thread_id = $4 AND tc.user_id = u.id
              )
            ORDER BY u.email
            LIMIT 10
            """,
            current_user.id, pattern, company_id, thread_id,
        )
    return [
        {
            "user_id": str(r["user_id"]),
            "name": r["name"],
            "email": r["email"],
            "avatar_url": r["avatar_url"],
        }
        for r in rows
    ]
