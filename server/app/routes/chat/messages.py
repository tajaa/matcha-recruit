"""Chat message routes."""

from typing import Optional
from uuid import UUID
from datetime import datetime
import base64

from fastapi import APIRouter, HTTPException, Depends, Query

from ...database import get_connection
from ...models.chat import (
    ChatMessage,
    ChatMessageCreate,
    ChatMessageUpdate,
    MessagePage,
    ChatUserPublic,
)
from .auth import get_current_chat_user

router = APIRouter()


def encode_cursor(timestamp: datetime, message_id: UUID) -> str:
    """Encode a cursor for pagination."""
    cursor_str = f"{timestamp.isoformat()}:{message_id}"
    return base64.urlsafe_b64encode(cursor_str.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode a cursor for pagination."""
    cursor_str = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts_str, id_str = cursor_str.split(":", 1)
    return datetime.fromisoformat(ts_str), UUID(id_str)


@router.get("/{slug}/messages", response_model=MessagePage)
async def get_messages(
    slug: str,
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = None,
    current_user: ChatUserPublic = Depends(get_current_chat_user)
):
    """Get messages from a room with cursor-based pagination."""
    async with get_connection() as conn:
        # Get room
        room = await conn.fetchrow(
            "SELECT id FROM chat_rooms WHERE slug = $1",
            slug
        )
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        # Check membership
        is_member = await conn.fetchval(
            """
            SELECT 1 FROM chat_room_members
            WHERE room_id = $1 AND user_id = $2
            """,
            room["id"],
            current_user.id
        )
        if not is_member:
            raise HTTPException(status_code=403, detail="You must join the room to view messages")

        # Build query based on cursor
        if cursor:
            cursor_ts, cursor_id = decode_cursor(cursor)
            rows = await conn.fetch(
                """
                SELECT
                    m.id, m.room_id, m.user_id, m.content, m.created_at, m.edited_at,
                    u.id as u_id, u.email, u.first_name, u.last_name,
                    u.avatar_url, u.bio, u.last_seen
                FROM chat_messages m
                LEFT JOIN chat_users u ON m.user_id = u.id
                WHERE m.room_id = $1
                AND (m.created_at < $2 OR (m.created_at = $2 AND m.id < $3))
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT $4
                """,
                room["id"],
                cursor_ts,
                cursor_id,
                limit + 1  # Fetch one extra to check if there's more
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    m.id, m.room_id, m.user_id, m.content, m.created_at, m.edited_at,
                    u.id as u_id, u.email, u.first_name, u.last_name,
                    u.avatar_url, u.bio, u.last_seen
                FROM chat_messages m
                LEFT JOIN chat_users u ON m.user_id = u.id
                WHERE m.room_id = $1
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT $2
                """,
                room["id"],
                limit + 1
            )

        # Check if there's more
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # Build response (reverse to chronological order)
        messages = []
        for row in reversed(rows):
            user = None
            if row["u_id"]:
                user = ChatUserPublic(
                    id=row["u_id"],
                    email=row["email"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    avatar_url=row["avatar_url"],
                    bio=row["bio"],
                    last_seen=row["last_seen"]
                )
            messages.append(ChatMessage(
                id=row["id"],
                room_id=row["room_id"],
                user_id=row["user_id"],
                content=row["content"],
                created_at=row["created_at"],
                edited_at=row["edited_at"],
                user=user
            ))

        # Create next cursor from last message (in original order)
        next_cursor = None
        if has_more and rows:
            last_row = rows[-1]
            next_cursor = encode_cursor(last_row["created_at"], last_row["id"])

        return MessagePage(
            messages=messages,
            next_cursor=next_cursor,
            has_more=has_more
        )


@router.post("/{slug}/messages", response_model=ChatMessage)
async def post_message(
    slug: str,
    data: ChatMessageCreate,
    current_user: ChatUserPublic = Depends(get_current_chat_user)
):
    """Post a new message to a room."""
    async with get_connection() as conn:
        # Get room
        room = await conn.fetchrow(
            "SELECT id FROM chat_rooms WHERE slug = $1",
            slug
        )
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        # Check membership
        is_member = await conn.fetchval(
            """
            SELECT 1 FROM chat_room_members
            WHERE room_id = $1 AND user_id = $2
            """,
            room["id"],
            current_user.id
        )
        if not is_member:
            raise HTTPException(status_code=403, detail="You must join the room to post messages")

        # Create message
        row = await conn.fetchrow(
            """
            INSERT INTO chat_messages (room_id, user_id, content)
            VALUES ($1, $2, $3)
            RETURNING id, room_id, user_id, content, created_at, edited_at
            """,
            room["id"],
            current_user.id,
            data.content
        )

        return ChatMessage(
            id=row["id"],
            room_id=row["room_id"],
            user_id=row["user_id"],
            content=row["content"],
            created_at=row["created_at"],
            edited_at=row["edited_at"],
            user=current_user
        )


@router.patch("/{slug}/messages/{message_id}", response_model=ChatMessage)
async def edit_message(
    slug: str,
    message_id: UUID,
    data: ChatMessageUpdate,
    current_user: ChatUserPublic = Depends(get_current_chat_user)
):
    """Edit a message (own messages only)."""
    async with get_connection() as conn:
        # Get message
        message = await conn.fetchrow(
            """
            SELECT m.id, m.room_id, m.user_id, r.slug
            FROM chat_messages m
            JOIN chat_rooms r ON m.room_id = r.id
            WHERE m.id = $1 AND r.slug = $2
            """,
            message_id,
            slug
        )
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Check ownership
        if message["user_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="You can only edit your own messages")

        # Update message
        row = await conn.fetchrow(
            """
            UPDATE chat_messages
            SET content = $1, edited_at = CURRENT_TIMESTAMP
            WHERE id = $2
            RETURNING id, room_id, user_id, content, created_at, edited_at
            """,
            data.content,
            message_id
        )

        return ChatMessage(
            id=row["id"],
            room_id=row["room_id"],
            user_id=row["user_id"],
            content=row["content"],
            created_at=row["created_at"],
            edited_at=row["edited_at"],
            user=current_user
        )


@router.delete("/{slug}/messages/{message_id}")
async def delete_message(
    slug: str,
    message_id: UUID,
    current_user: ChatUserPublic = Depends(get_current_chat_user)
):
    """Delete a message (own messages only)."""
    async with get_connection() as conn:
        # Get message
        message = await conn.fetchrow(
            """
            SELECT m.id, m.room_id, m.user_id, r.slug
            FROM chat_messages m
            JOIN chat_rooms r ON m.room_id = r.id
            WHERE m.id = $1 AND r.slug = $2
            """,
            message_id,
            slug
        )
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Check ownership
        if message["user_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="You can only delete your own messages")

        # Delete message
        await conn.execute(
            "DELETE FROM chat_messages WHERE id = $1",
            message_id
        )

        return {"status": "deleted", "message_id": str(message_id)}
