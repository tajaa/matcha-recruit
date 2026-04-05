"""Channel routes for Slack-style group chat in Matcha Work."""

import re
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import get_current_user
from ..models.auth import CurrentUser
from ...matcha.dependencies import resolve_accessible_company_scope, require_admin_or_client

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_USER_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"


class ChannelMember(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: str
    avatar_url: Optional[str] = None
    joined_at: datetime


class ChannelMessage(BaseModel):
    id: UUID
    channel_id: UUID
    sender_id: UUID
    sender_name: str
    content: str
    created_at: datetime
    edited_at: Optional[datetime] = None


class ChannelSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    member_count: int = 0
    unread_count: int = 0
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    is_member: bool = True


class ChannelDetail(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    is_archived: bool = False
    created_by: UUID
    created_at: datetime
    member_count: int = 0
    is_member: bool = False
    members: list[ChannelMember] = []
    messages: list[ChannelMessage] = []


class CreateChannelRequest(BaseModel):
    name: str
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'channel'


async def _get_company_id(current_user: CurrentUser) -> UUID:
    scope = await resolve_accessible_company_scope(current_user)
    company_id = scope.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No company associated with your account")
    return company_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ChannelSummary])
async def list_channels(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all channels in the user's company. Shows membership status."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT ch.id, ch.name, ch.slug, ch.description,
                   (SELECT COUNT(*) FROM channel_members WHERE channel_id = ch.id) AS member_count,
                   CASE WHEN cm.user_id IS NOT NULL THEN
                       (SELECT COUNT(*) FROM channel_messages msg
                        WHERE msg.channel_id = ch.id
                          AND msg.sender_id != $1
                          AND (cm.last_read_at IS NULL OR msg.created_at > cm.last_read_at))
                   ELSE 0 END AS unread_count,
                   (SELECT MAX(msg2.created_at) FROM channel_messages msg2
                    WHERE msg2.channel_id = ch.id) AS last_message_at,
                   (SELECT SUBSTRING(msg3.content, 1, 100) FROM channel_messages msg3
                    WHERE msg3.channel_id = ch.id
                    ORDER BY msg3.created_at DESC LIMIT 1) AS last_message_preview,
                   cm.user_id IS NOT NULL AS is_member
            FROM channels ch
            LEFT JOIN channel_members cm ON cm.channel_id = ch.id AND cm.user_id = $1
            WHERE ch.company_id = $2 AND ch.is_archived = false
            ORDER BY last_message_at DESC NULLS LAST, ch.created_at DESC
            """,
            current_user.id,
            company_id,
        )

        return [
            ChannelSummary(
                id=r["id"],
                name=r["name"],
                slug=r["slug"],
                description=r["description"],
                member_count=r["member_count"],
                unread_count=r["unread_count"],
                last_message_at=r["last_message_at"],
                last_message_preview=r["last_message_preview"],
                is_member=r["is_member"],
            )
            for r in rows
        ]


@router.post("", response_model=ChannelDetail, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: CreateChannelRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new channel. Only client/admin roles."""
    company_id = await _get_company_id(current_user)
    name = body.name.strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Channel name must be 1-100 characters")

    slug = _slugify(name)

    async with get_connection() as conn:
        # Check slug uniqueness, append suffix if needed
        base_slug = slug
        suffix = 0
        while True:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM channels WHERE company_id = $1 AND slug = $2)",
                company_id, slug,
            )
            if not exists:
                break
            suffix += 1
            slug = f"{base_slug}-{suffix}"

        row = await conn.fetchrow(
            """
            INSERT INTO channels (company_id, name, slug, description, created_by)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, name, slug, description, is_archived, created_by, created_at
            """,
            company_id, name, slug, body.description, current_user.id,
        )

        # Auto-join creator
        await conn.execute(
            "INSERT INTO channel_members (channel_id, user_id) VALUES ($1, $2)",
            row["id"], current_user.id,
        )

        return ChannelDetail(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            description=row["description"],
            is_archived=row["is_archived"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            member_count=1,
            is_member=True,
            members=[],
            messages=[],
        )


class InvitableUser(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    avatar_url: Optional[str] = None


@router.get("/invitable-users", response_model=list[InvitableUser])
async def search_invitable_users(
    q: str = Query(default="", max_length=100),
    channel_id: Optional[UUID] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Search for users that can be invited to a channel or project.

    Company accounts: returns users in the same company.
    Personal/individual accounts: returns users from inbox conversations.
    """
    async with get_connection() as conn:
        search = f"%{q}%" if q else "%%"
        has_search = len(q) >= 2

        # Determine if this is a real company or a personal workspace
        # Personal workspaces (is_personal=true) search inbox contacts
        # Real companies search company users
        company_id = None
        is_personal = True

        if current_user.role in ("client", "individual"):
            row = await conn.fetchrow(
                """
                SELECT c.company_id, COALESCE(comp.is_personal, false) AS is_personal
                FROM clients c JOIN companies comp ON c.company_id = comp.id
                WHERE c.user_id = $1
                """,
                current_user.id,
            )
            if row:
                company_id = row["company_id"]
                is_personal = row["is_personal"]
        elif current_user.role == "employee":
            company_id = await conn.fetchval(
                "SELECT org_id FROM employees WHERE user_id = $1", current_user.id
            )
            is_personal = False
        elif current_user.role == "admin":
            scope = await resolve_accessible_company_scope(current_user)
            company_id = scope.get("company_id")
            is_personal = False

        name_filter_2 = f"""AND (
                    c.name ILIKE $2
                    OR CONCAT(e.first_name, ' ', e.last_name) ILIKE $2
                    OR a.name ILIKE $2
                    OR u.email ILIKE $2
                  )""" if has_search else ""
        name_filter_3 = f"""AND (
                    c.name ILIKE $3
                    OR CONCAT(e.first_name, ' ', e.last_name) ILIKE $3
                    OR a.name ILIKE $3
                    OR u.email ILIKE $3
                  )""" if has_search else ""

        if company_id and not is_personal:
            rows = await conn.fetch(
                f"""
                SELECT u.id, u.email, u.role, u.avatar_url,
                       {_USER_NAME_EXPR} AS name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id != $1 AND u.is_active = true
                  AND (c.company_id = $2 OR e.org_id = $2)
                  {name_filter_3}
                ORDER BY {_USER_NAME_EXPR}
                LIMIT 20
                """,
                current_user.id, company_id, *([search] if has_search else []),
            )
        else:
            # Personal account: show inbox contacts
            rows = await conn.fetch(
                f"""
                SELECT DISTINCT u.id, u.email, u.role, u.avatar_url,
                       {_USER_NAME_EXPR} AS name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                JOIN inbox_participants ip ON ip.user_id = u.id
                JOIN inbox_participants my ON my.conversation_id = ip.conversation_id AND my.user_id = $1
                WHERE u.id != $1 AND u.is_active = true
                  {name_filter_2}
                ORDER BY {_USER_NAME_EXPR}
                LIMIT 20
                """,
                current_user.id, *([search] if has_search else []),
            )

        return [
            InvitableUser(
                id=r["id"], name=r["name"], email=r["email"],
                role=r["role"], avatar_url=r["avatar_url"],
            )
            for r in rows
        ]


@router.get("/{channel_id}", response_model=ChannelDetail)
async def get_channel(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get channel detail with members and recent messages."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        ch = await conn.fetchrow(
            "SELECT id, name, slug, description, is_archived, created_by, created_at FROM channels WHERE id = $1 AND company_id = $2",
            channel_id, company_id,
        )
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Check membership
        is_member = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM channel_members WHERE channel_id = $1 AND user_id = $2)",
            channel_id, current_user.id,
        )

        # Members
        members = await conn.fetch(
            f"""
            SELECT cm.user_id, cm.joined_at, u.email, u.role, u.avatar_url,
                   {_USER_NAME_EXPR} AS name
            FROM channel_members cm
            JOIN users u ON u.id = cm.user_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE cm.channel_id = $1
            ORDER BY cm.joined_at
            """,
            channel_id,
        )

        # Recent messages
        messages = await conn.fetch(
            f"""
            SELECT m.id, m.channel_id, m.sender_id, m.content, m.created_at, m.edited_at,
                   {_USER_NAME_EXPR} AS sender_name
            FROM channel_messages m
            JOIN users u ON u.id = m.sender_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE m.channel_id = $1
            ORDER BY m.created_at DESC
            LIMIT 50
            """,
            channel_id,
        )

        # Mark as read (only if member)
        if is_member:
            await conn.execute(
                "UPDATE channel_members SET last_read_at = NOW() WHERE channel_id = $1 AND user_id = $2",
                channel_id, current_user.id,
            )

        return ChannelDetail(
            id=ch["id"],
            name=ch["name"],
            slug=ch["slug"],
            description=ch["description"],
            is_archived=ch["is_archived"],
            created_by=ch["created_by"],
            created_at=ch["created_at"],
            member_count=len(members),
            is_member=is_member,
            members=[
                ChannelMember(
                    user_id=m["user_id"], name=m["name"], email=m["email"],
                    role=m["role"], avatar_url=m["avatar_url"], joined_at=m["joined_at"],
                )
                for m in members
            ],
            messages=[
                ChannelMessage(
                    id=m["id"], channel_id=m["channel_id"], sender_id=m["sender_id"],
                    sender_name=m["sender_name"], content=m["content"],
                    created_at=m["created_at"], edited_at=m["edited_at"],
                )
                for m in reversed(messages)  # Return chronological order
            ],
        )


@router.get("/{channel_id}/messages", response_model=list[ChannelMessage])
async def get_channel_messages(
    channel_id: UUID,
    before: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get paginated message history for a channel."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        # Verify channel + membership
        is_member = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM channels ch
                JOIN channel_members cm ON cm.channel_id = ch.id AND cm.user_id = $2
                WHERE ch.id = $1 AND ch.company_id = $3
            )
            """,
            channel_id, current_user.id, company_id,
        )
        if not is_member:
            raise HTTPException(status_code=404, detail="Channel not found or not a member")

        if before:
            try:
                before_dt = datetime.fromisoformat(before)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="Invalid 'before' cursor format")
            rows = await conn.fetch(
                f"""
                SELECT m.id, m.channel_id, m.sender_id, m.content, m.created_at, m.edited_at,
                       {_USER_NAME_EXPR} AS sender_name
                FROM channel_messages m
                JOIN users u ON u.id = m.sender_id
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE m.channel_id = $1 AND m.created_at < $2
                ORDER BY m.created_at DESC
                LIMIT $3
                """,
                channel_id, before_dt, limit,
            )
        else:
            rows = await conn.fetch(
                f"""
                SELECT m.id, m.channel_id, m.sender_id, m.content, m.created_at, m.edited_at,
                       {_USER_NAME_EXPR} AS sender_name
                FROM channel_messages m
                JOIN users u ON u.id = m.sender_id
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE m.channel_id = $1
                ORDER BY m.created_at DESC
                LIMIT $2
                """,
                channel_id, limit,
            )

        return [
            ChannelMessage(
                id=r["id"], channel_id=r["channel_id"], sender_id=r["sender_id"],
                sender_name=r["sender_name"], content=r["content"],
                created_at=r["created_at"], edited_at=r["edited_at"],
            )
            for r in reversed(rows)
        ]


@router.post("/{channel_id}/join", status_code=status.HTTP_200_OK)
async def join_channel(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Join a channel in the user's company."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        ch = await conn.fetchval(
            "SELECT id FROM channels WHERE id = $1 AND company_id = $2 AND is_archived = false",
            channel_id, company_id,
        )
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        await conn.execute(
            """
            INSERT INTO channel_members (channel_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT (channel_id, user_id) DO NOTHING
            """,
            channel_id, current_user.id,
        )

    return {"ok": True}


class AddMembersRequest(BaseModel):
    user_ids: list[UUID]


@router.post("/{channel_id}/members", status_code=status.HTTP_200_OK)
async def add_members(
    channel_id: UUID,
    body: AddMembersRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Add members to a channel. Any current member can invite others from the same company."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        # Verify channel exists + requester is a member
        is_member = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM channels ch
                JOIN channel_members cm ON cm.channel_id = ch.id AND cm.user_id = $2
                WHERE ch.id = $1 AND ch.company_id = $3
            )
            """,
            channel_id, current_user.id, company_id,
        )
        if not is_member:
            raise HTTPException(status_code=404, detail="Channel not found or not a member")

        # Verify all user_ids belong to the same company
        for uid in body.user_ids:
            in_company = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM users u
                    LEFT JOIN clients c ON c.user_id = u.id
                    LEFT JOIN employees e ON e.user_id = u.id
                    WHERE u.id = $1 AND u.is_active = true
                      AND (c.company_id = $2 OR e.org_id = $2)
                )
                """,
                uid, company_id,
            )
            if not in_company:
                continue  # silently skip users not in the company

            await conn.execute(
                """
                INSERT INTO channel_members (channel_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT (channel_id, user_id) DO NOTHING
                """,
                channel_id, uid,
            )

    return {"ok": True}


class UpdateChannelRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.patch("/{channel_id}", response_model=ChannelSummary)
async def update_channel(
    channel_id: UUID,
    body: UpdateChannelRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Rename or update a channel. Only the creator or admin can update."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT created_by, company_id FROM channels WHERE id = $1", channel_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Channel not found")

        is_admin = current_user.role == "admin"
        is_creator = str(row["created_by"]) == str(current_user.id)
        if not is_admin and not is_creator:
            raise HTTPException(status_code=403, detail="Only the channel creator or admin can update this channel")

        sets = []
        params: list = []
        idx = 1

        if body.name is not None:
            name = body.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="Channel name cannot be empty")
            slug = _slugify(name)
            sets.append(f"name = ${idx}")
            params.append(name)
            idx += 1
            sets.append(f"slug = ${idx}")
            params.append(slug)
            idx += 1

        if body.description is not None:
            sets.append(f"description = ${idx}")
            params.append(body.description.strip() or None)
            idx += 1

        if not sets:
            raise HTTPException(status_code=400, detail="No updates provided")

        params.append(channel_id)
        await conn.execute(
            f"UPDATE channels SET {', '.join(sets)} WHERE id = ${idx}",
            *params,
        )

        # Return updated channel summary
        ch = await conn.fetchrow(
            """
            SELECT c.id, c.name, c.slug, c.description,
                   (SELECT COUNT(*) FROM channel_members WHERE channel_id = c.id) AS member_count,
                   0 AS unread_count,
                   NULL::timestamptz AS last_message_at,
                   NULL AS last_message_preview,
                   TRUE AS is_member
            FROM channels c WHERE c.id = $1
            """,
            channel_id,
        )
        return dict(ch)


@router.post("/{channel_id}/leave", status_code=status.HTTP_200_OK)
async def leave_channel(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Leave a channel."""
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )

    return {"ok": True}
