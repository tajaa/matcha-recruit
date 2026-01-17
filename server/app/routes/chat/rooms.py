"""Chat room routes."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends

from ...database import get_connection
from ...models.chat import (
    ChatRoom,
    ChatRoomWithUnread,
    ChatRoomMember,
    ChatUserPublic,
)
from .auth import get_current_chat_user, get_optional_chat_user

router = APIRouter()


@router.get("", response_model=List[ChatRoomWithUnread])
async def list_rooms(
    current_user: ChatUserPublic | None = Depends(get_optional_chat_user)
):
    """List all chat rooms with unread counts for current user."""
    async with get_connection() as conn:
        if current_user:
            # Get rooms with membership and unread counts
            rows = await conn.fetch(
                """
                SELECT
                    r.id, r.name, r.slug, r.description, r.icon, r.is_default, r.created_at,
                    (SELECT COUNT(*) FROM chat_room_members WHERE room_id = r.id) as member_count,
                    CASE WHEN m.user_id IS NOT NULL THEN TRUE ELSE FALSE END as is_member,
                    COALESCE(
                        (SELECT COUNT(*) FROM chat_messages msg
                         WHERE msg.room_id = r.id
                         AND msg.created_at > COALESCE(m.last_read_at, '1970-01-01')),
                        0
                    ) as unread_count
                FROM chat_rooms r
                LEFT JOIN chat_room_members m ON r.id = m.room_id AND m.user_id = $1
                ORDER BY r.is_default DESC, r.name ASC
                """,
                current_user.id
            )
        else:
            # Anonymous: just get room info
            rows = await conn.fetch(
                """
                SELECT
                    r.id, r.name, r.slug, r.description, r.icon, r.is_default, r.created_at,
                    (SELECT COUNT(*) FROM chat_room_members WHERE room_id = r.id) as member_count,
                    FALSE as is_member,
                    0 as unread_count
                FROM chat_rooms r
                ORDER BY r.is_default DESC, r.name ASC
                """
            )

        return [
            ChatRoomWithUnread(
                id=row["id"],
                name=row["name"],
                slug=row["slug"],
                description=row["description"],
                icon=row["icon"],
                is_default=row["is_default"],
                member_count=row["member_count"],
                created_at=row["created_at"],
                is_member=row["is_member"],
                unread_count=row["unread_count"]
            )
            for row in rows
        ]


@router.get("/{slug}", response_model=ChatRoom)
async def get_room(slug: str):
    """Get a specific room by slug."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                r.id, r.name, r.slug, r.description, r.icon, r.is_default, r.created_at,
                (SELECT COUNT(*) FROM chat_room_members WHERE room_id = r.id) as member_count
            FROM chat_rooms r
            WHERE r.slug = $1
            """,
            slug
        )
        if not row:
            raise HTTPException(status_code=404, detail="Room not found")

        return ChatRoom(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            description=row["description"],
            icon=row["icon"],
            is_default=row["is_default"],
            member_count=row["member_count"],
            created_at=row["created_at"]
        )


@router.post("/{slug}/join")
async def join_room(
    slug: str,
    current_user: ChatUserPublic = Depends(get_current_chat_user)
):
    """Join a chat room."""
    async with get_connection() as conn:
        room = await conn.fetchrow(
            "SELECT id FROM chat_rooms WHERE slug = $1",
            slug
        )
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        await conn.execute(
            """
            INSERT INTO chat_room_members (room_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            room["id"],
            current_user.id
        )

        return {"status": "joined", "room": slug}


@router.post("/{slug}/leave")
async def leave_room(
    slug: str,
    current_user: ChatUserPublic = Depends(get_current_chat_user)
):
    """Leave a chat room."""
    async with get_connection() as conn:
        room = await conn.fetchrow(
            "SELECT id FROM chat_rooms WHERE slug = $1",
            slug
        )
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        await conn.execute(
            """
            DELETE FROM chat_room_members
            WHERE room_id = $1 AND user_id = $2
            """,
            room["id"],
            current_user.id
        )

        return {"status": "left", "room": slug}


@router.get("/{slug}/members", response_model=List[ChatRoomMember])
async def get_room_members(slug: str):
    """Get members of a chat room."""
    async with get_connection() as conn:
        room = await conn.fetchrow(
            "SELECT id FROM chat_rooms WHERE slug = $1",
            slug
        )
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        rows = await conn.fetch(
            """
            SELECT
                u.id, u.email, u.first_name, u.last_name, u.avatar_url, u.bio, u.last_seen,
                m.joined_at
            FROM chat_room_members m
            JOIN chat_users u ON m.user_id = u.id
            WHERE m.room_id = $1
            ORDER BY m.joined_at ASC
            """,
            room["id"]
        )

        return [
            ChatRoomMember(
                user=ChatUserPublic(
                    id=row["id"],
                    email=row["email"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    avatar_url=row["avatar_url"],
                    bio=row["bio"],
                    last_seen=row["last_seen"]
                ),
                joined_at=row["joined_at"]
            )
            for row in rows
        ]


@router.post("/{slug}/mark-read")
async def mark_room_read(
    slug: str,
    current_user: ChatUserPublic = Depends(get_current_chat_user)
):
    """Mark all messages in a room as read."""
    async with get_connection() as conn:
        room = await conn.fetchrow(
            "SELECT id FROM chat_rooms WHERE slug = $1",
            slug
        )
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        await conn.execute(
            """
            UPDATE chat_room_members
            SET last_read_at = CURRENT_TIMESTAMP
            WHERE room_id = $1 AND user_id = $2
            """,
            room["id"],
            current_user.id
        )

        return {"status": "marked_read", "room": slug}
