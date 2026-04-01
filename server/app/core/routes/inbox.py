"""Inbox / messaging routes."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...database import get_connection
from ..dependencies import get_current_user
from ..models.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateConversationRequest(BaseModel):
    participant_ids: list[UUID] = Field(..., min_length=1, max_length=20)
    message: str = Field(..., min_length=1, max_length=5000)
    title: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    sender_name: str
    content: str
    created_at: datetime
    edited_at: Optional[datetime] = None


class ParticipantResponse(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: str
    last_read_at: Optional[datetime] = None
    is_muted: bool = False


class ConversationResponse(BaseModel):
    id: UUID
    title: Optional[str] = None
    is_group: bool = False
    created_by: UUID
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    participants: list[ParticipantResponse] = []
    messages: list[MessageResponse] = []
    unread_count: int = 0
    created_at: datetime


class ConversationSummary(BaseModel):
    id: UUID
    title: Optional[str] = None
    is_group: bool = False
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    participants: list[ParticipantResponse] = []
    unread_count: int = 0


class UserSearchResult(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    company_name: Optional[str] = None


# ---------------------------------------------------------------------------
# SQL fragments — shared join for resolving display names
# ---------------------------------------------------------------------------

_USER_NAME_JOIN = """
    JOIN users u ON u.id = {alias}.user_id
    LEFT JOIN clients c ON c.user_id = u.id
    LEFT JOIN employees e ON e.user_id = u.id
    LEFT JOIN admins a ON a.user_id = u.id
"""

_USER_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_user_display_name(conn, user_id: UUID) -> tuple[str, str, str]:
    """Return (name, email, role) for a user."""
    row = await conn.fetchrow(
        f"""
        SELECT u.email, u.role, {_USER_NAME_EXPR} AS name
        FROM users u
        LEFT JOIN clients c ON c.user_id = u.id
        LEFT JOIN employees e ON e.user_id = u.id
        LEFT JOIN admins a ON a.user_id = u.id
        WHERE u.id = $1
        """,
        user_id,
    )
    if not row:
        return ("Unknown", "", "unknown")
    return (row["name"], row["email"], row["role"])


async def _require_participant(conn, conversation_id: UUID, user_id: UUID) -> None:
    """Raise 404 if user is not a participant in the conversation."""
    is_member = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM inbox_participants WHERE conversation_id = $1 AND user_id = $2)",
        conversation_id,
        user_id,
    )
    if not is_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


async def _build_participant_list(conn, conversation_id: UUID) -> list[ParticipantResponse]:
    """Build the participant response list for a conversation."""
    rows = await conn.fetch(
        f"""
        SELECT ip.user_id, ip.last_read_at, ip.is_muted,
               u.email, u.role, {_USER_NAME_EXPR} AS name
        FROM inbox_participants ip
        JOIN users u ON u.id = ip.user_id
        LEFT JOIN clients c ON c.user_id = u.id
        LEFT JOIN employees e ON e.user_id = u.id
        LEFT JOIN admins a ON a.user_id = u.id
        WHERE ip.conversation_id = $1
        ORDER BY ip.joined_at
        """,
        conversation_id,
    )
    return [
        ParticipantResponse(
            user_id=r["user_id"],
            name=r["name"],
            email=r["email"],
            role=r["role"],
            last_read_at=r["last_read_at"],
            is_muted=r["is_muted"],
        )
        for r in rows
    ]


async def _send_message_notification(
    conversation_id: UUID,
    sender_id: UUID,
    sender_name: str,
    preview: str,
) -> None:
    """Best-effort email notification to other participants (batched, 15-min cooldown).

    Opens its own DB connection so the caller's connection isn't held during email I/O.
    """
    try:
        from ..services.email import get_email_service
        email_svc = get_email_service()
        if not email_svc.is_configured():
            return

        from ...config import get_settings
        base_url = get_settings().app_base_url.rstrip("/")

        # Gather recipient info + batch state in one connection
        async with get_connection() as conn:
            participants = await conn.fetch(
                f"""
                SELECT ip.user_id, u.email, {_USER_NAME_EXPR} AS name
                FROM inbox_participants ip
                JOIN users u ON u.id = ip.user_id
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE ip.conversation_id = $1
                  AND ip.user_id != $2
                  AND ip.is_muted = false
                """,
                conversation_id,
                sender_id,
            )

            to_notify: list[dict] = []
            now = datetime.now(timezone.utc)
            for p in participants:
                batch = await conn.fetchrow(
                    "SELECT last_sent_at FROM inbox_email_batches WHERE recipient_id = $1 AND sender_id = $2",
                    p["user_id"],
                    sender_id,
                )
                if batch and batch["last_sent_at"]:
                    last_sent = batch["last_sent_at"]
                    if last_sent.tzinfo is None:
                        last_sent = last_sent.replace(tzinfo=timezone.utc)
                    if (now - last_sent).total_seconds() < 900:
                        continue
                to_notify.append({"user_id": p["user_id"], "email": p["email"], "name": p["name"]})

        # Send emails outside DB connection
        for recipient in to_notify:
            try:
                await email_svc.send_email(
                    to_email=recipient["email"],
                    to_name=recipient["name"],
                    subject=f"New message from {sender_name}",
                    html_content=(
                        f"<p><strong>{sender_name}</strong> sent you a message:</p>"
                        f"<blockquote>{preview[:200]}</blockquote>"
                        f"<p><a href=\"{base_url}/app/inbox\">View in Matcha</a></p>"
                    ),
                )
                # Update batch tracking
                async with get_connection() as conn:
                    await conn.execute(
                        """
                        INSERT INTO inbox_email_batches (recipient_id, sender_id, last_sent_at)
                        VALUES ($1, $2, NOW())
                        ON CONFLICT (recipient_id, sender_id)
                        DO UPDATE SET last_sent_at = NOW()
                        """,
                        recipient["user_id"],
                        sender_id,
                    )
            except Exception:
                logger.warning("Failed to send inbox notification to %s", recipient["email"], exc_info=True)
    except Exception:
        logger.warning("Inbox email notification failed", exc_info=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List the current user's conversations, sorted by most recent activity."""
    async with get_connection() as conn:
        # Single query: fetch conversations with unread counts
        rows = await conn.fetch(
            """
            SELECT ic.id, ic.title, ic.is_group, ic.last_message_at, ic.last_message_preview,
                   (SELECT COUNT(*) FROM inbox_messages im
                    WHERE im.conversation_id = ic.id
                      AND im.sender_id != $1
                      AND (ip.last_read_at IS NULL OR im.created_at > ip.last_read_at)
                   ) AS unread_count
            FROM inbox_conversations ic
            JOIN inbox_participants ip ON ip.conversation_id = ic.id AND ip.user_id = $1
            ORDER BY ic.last_message_at DESC NULLS LAST
            LIMIT $2 OFFSET $3
            """,
            current_user.id,
            limit,
            offset,
        )

        # Batch-fetch participants for all conversations in one query
        conv_ids = [r["id"] for r in rows]
        if conv_ids:
            all_participants = await conn.fetch(
                f"""
                SELECT ip.conversation_id, ip.user_id, ip.last_read_at, ip.is_muted,
                       u.email, u.role, {_USER_NAME_EXPR} AS name
                FROM inbox_participants ip
                JOIN users u ON u.id = ip.user_id
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE ip.conversation_id = ANY($1::uuid[])
                ORDER BY ip.joined_at
                """,
                conv_ids,
            )
            participants_by_conv: dict[UUID, list[ParticipantResponse]] = {}
            for p in all_participants:
                cid = p["conversation_id"]
                if cid not in participants_by_conv:
                    participants_by_conv[cid] = []
                participants_by_conv[cid].append(
                    ParticipantResponse(
                        user_id=p["user_id"],
                        name=p["name"],
                        email=p["email"],
                        role=p["role"],
                        last_read_at=p["last_read_at"],
                        is_muted=p["is_muted"],
                    )
                )
        else:
            participants_by_conv = {}

        return [
            ConversationSummary(
                id=r["id"],
                title=r["title"],
                is_group=r["is_group"],
                last_message_at=r["last_message_at"],
                last_message_preview=r["last_message_preview"],
                participants=participants_by_conv.get(r["id"], []),
                unread_count=r["unread_count"],
            )
            for r in rows
        ]


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new conversation (or reuse an existing 1:1) and send the first message."""
    async with get_connection() as conn:
        all_participant_ids = list(set(body.participant_ids))
        all_participant_ids = [pid for pid in all_participant_ids if pid != current_user.id]
        if not all_participant_ids:
            raise HTTPException(status_code=400, detail="Must include at least one other participant")

        existing = await conn.fetch(
            "SELECT id FROM users WHERE id = ANY($1::uuid[]) AND is_active = true",
            all_participant_ids,
        )
        existing_ids = {r["id"] for r in existing}
        missing = [pid for pid in all_participant_ids if pid not in existing_ids]
        if missing:
            raise HTTPException(status_code=400, detail=f"Users not found: {[str(m) for m in missing]}")

        is_group = len(all_participant_ids) > 1
        conversation_id: Optional[UUID] = None

        # For 1:1, check if conversation already exists
        if not is_group:
            other_id = all_participant_ids[0]
            conversation_id = await conn.fetchval(
                """
                SELECT ic.id
                FROM inbox_conversations ic
                WHERE ic.is_group = false
                  AND (SELECT COUNT(*) FROM inbox_participants WHERE conversation_id = ic.id) = 2
                  AND EXISTS (SELECT 1 FROM inbox_participants WHERE conversation_id = ic.id AND user_id = $1)
                  AND EXISTS (SELECT 1 FROM inbox_participants WHERE conversation_id = ic.id AND user_id = $2)
                LIMIT 1
                """,
                current_user.id,
                other_id,
            )

        preview = body.message[:100]

        async with conn.transaction():
            if conversation_id:
                # Existing 1:1 — add message
                msg_row = await conn.fetchrow(
                    """
                    INSERT INTO inbox_messages (conversation_id, sender_id, content)
                    VALUES ($1, $2, $3)
                    RETURNING id, conversation_id, sender_id, content, created_at, edited_at
                    """,
                    conversation_id,
                    current_user.id,
                    body.message,
                )
                await conn.execute(
                    "UPDATE inbox_conversations SET last_message_at = NOW(), last_message_preview = $2, updated_at = NOW() WHERE id = $1",
                    conversation_id,
                    preview,
                )
                await conn.execute(
                    "UPDATE inbox_participants SET last_read_at = NOW() WHERE conversation_id = $1 AND user_id = $2",
                    conversation_id,
                    current_user.id,
                )
            else:
                # Create new conversation
                conv_row = await conn.fetchrow(
                    """
                    INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
                    VALUES ($1, $2, $3, NOW(), $4)
                    RETURNING id, created_at
                    """,
                    body.title,
                    is_group,
                    current_user.id,
                    preview,
                )
                conversation_id = conv_row["id"]

                # Add participants
                full_participant_ids = [current_user.id] + all_participant_ids
                for pid in full_participant_ids:
                    last_read = datetime.now(timezone.utc) if pid == current_user.id else None
                    await conn.execute(
                        "INSERT INTO inbox_participants (conversation_id, user_id, last_read_at) VALUES ($1, $2, $3)",
                        conversation_id,
                        pid,
                        last_read,
                    )

                # First message
                msg_row = await conn.fetchrow(
                    """
                    INSERT INTO inbox_messages (conversation_id, sender_id, content)
                    VALUES ($1, $2, $3)
                    RETURNING id, conversation_id, sender_id, content, created_at, edited_at
                    """,
                    conversation_id,
                    current_user.id,
                    body.message,
                )

        # Email notification (outside transaction, best-effort)
        sender_name, _, _ = await _resolve_user_display_name(conn, current_user.id)
        # Fire and forget — don't block response
        import asyncio
        asyncio.create_task(_send_message_notification(conversation_id, current_user.id, sender_name, preview))

        # Build response
        conv_data = await conn.fetchrow(
            "SELECT id, title, is_group, created_by, last_message_at, last_message_preview, created_at FROM inbox_conversations WHERE id = $1",
            conversation_id,
        )
        participants = await _build_participant_list(conn, conversation_id)

        sender_name_for_msg, _, _ = await _resolve_user_display_name(conn, msg_row["sender_id"])
        message = MessageResponse(
            id=msg_row["id"],
            conversation_id=msg_row["conversation_id"],
            sender_id=msg_row["sender_id"],
            sender_name=sender_name_for_msg,
            content=msg_row["content"],
            created_at=msg_row["created_at"],
            edited_at=msg_row["edited_at"],
        )

        return ConversationResponse(
            id=conv_data["id"],
            title=conv_data["title"],
            is_group=conv_data["is_group"],
            created_by=conv_data["created_by"],
            last_message_at=conv_data["last_message_at"],
            last_message_preview=conv_data["last_message_preview"],
            participants=participants,
            messages=[message],
            unread_count=0,
            created_at=conv_data["created_at"],
        )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before: Optional[UUID] = Query(default=None, description="Message ID cursor for pagination"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a conversation with its messages (newest first). Marks it as read."""
    async with get_connection() as conn:
        await _require_participant(conn, conversation_id, current_user.id)

        # Mark as read first (before building response)
        await conn.execute(
            "UPDATE inbox_participants SET last_read_at = NOW() WHERE conversation_id = $1 AND user_id = $2",
            conversation_id,
            current_user.id,
        )

        conv = await conn.fetchrow(
            "SELECT id, title, is_group, created_by, last_message_at, last_message_preview, created_at FROM inbox_conversations WHERE id = $1",
            conversation_id,
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Fetch messages
        if before:
            cursor_ts = await conn.fetchval(
                "SELECT created_at FROM inbox_messages WHERE id = $1 AND conversation_id = $2",
                before,
                conversation_id,
            )
            if not cursor_ts:
                raise HTTPException(status_code=400, detail="Invalid pagination cursor")

            msg_rows = await conn.fetch(
                """
                SELECT id, conversation_id, sender_id, content, created_at, edited_at
                FROM inbox_messages
                WHERE conversation_id = $1 AND created_at < $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                conversation_id,
                cursor_ts,
                limit,
            )
        else:
            msg_rows = await conn.fetch(
                """
                SELECT id, conversation_id, sender_id, content, created_at, edited_at
                FROM inbox_messages
                WHERE conversation_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                conversation_id,
                limit,
            )

        # Batch-resolve sender names
        sender_ids = list({m["sender_id"] for m in msg_rows})
        sender_cache: dict[UUID, str] = {}
        if sender_ids:
            name_rows = await conn.fetch(
                f"""
                SELECT u.id, {_USER_NAME_EXPR} AS name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id = ANY($1::uuid[])
                """,
                sender_ids,
            )
            sender_cache = {r["id"]: r["name"] for r in name_rows}

        messages = [
            MessageResponse(
                id=m["id"],
                conversation_id=m["conversation_id"],
                sender_id=m["sender_id"],
                sender_name=sender_cache.get(m["sender_id"], "Unknown"),
                content=m["content"],
                created_at=m["created_at"],
                edited_at=m["edited_at"],
            )
            for m in msg_rows
        ]

        participants = await _build_participant_list(conn, conversation_id)

        return ConversationResponse(
            id=conv["id"],
            title=conv["title"],
            is_group=conv["is_group"],
            created_by=conv["created_by"],
            last_message_at=conv["last_message_at"],
            last_message_preview=conv["last_message_preview"],
            participants=participants,
            messages=messages,
            unread_count=0,
            created_at=conv["created_at"],
        )


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Send a message in an existing conversation."""
    async with get_connection() as conn:
        await _require_participant(conn, conversation_id, current_user.id)

        async with conn.transaction():
            msg = await conn.fetchrow(
                """
                INSERT INTO inbox_messages (conversation_id, sender_id, content)
                VALUES ($1, $2, $3)
                RETURNING id, conversation_id, sender_id, content, created_at, edited_at
                """,
                conversation_id,
                current_user.id,
                body.content,
            )

            preview = body.content[:100]
            await conn.execute(
                "UPDATE inbox_conversations SET last_message_at = NOW(), last_message_preview = $2, updated_at = NOW() WHERE id = $1",
                conversation_id,
                preview,
            )

            await conn.execute(
                "UPDATE inbox_participants SET last_read_at = NOW() WHERE conversation_id = $1 AND user_id = $2",
                conversation_id,
                current_user.id,
            )

        sender_name, _, _ = await _resolve_user_display_name(conn, current_user.id)

    # Email notification outside DB connection (fire and forget)
    import asyncio
    asyncio.create_task(_send_message_notification(conversation_id, current_user.id, sender_name, body.content[:100]))

    return MessageResponse(
        id=msg["id"],
        conversation_id=msg["conversation_id"],
        sender_id=msg["sender_id"],
        sender_name=sender_name,
        content=msg["content"],
        created_at=msg["created_at"],
        edited_at=msg["edited_at"],
    )


@router.put("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark a conversation as read for the current user."""
    async with get_connection() as conn:
        await _require_participant(conn, conversation_id, current_user.id)
        await conn.execute(
            "UPDATE inbox_participants SET last_read_at = NOW() WHERE conversation_id = $1 AND user_id = $2",
            conversation_id,
            current_user.id,
        )
        return {"ok": True}


@router.put("/conversations/{conversation_id}/mute")
async def toggle_mute(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Toggle mute on a conversation for the current user."""
    async with get_connection() as conn:
        await _require_participant(conn, conversation_id, current_user.id)
        new_muted = await conn.fetchval(
            """
            UPDATE inbox_participants
            SET is_muted = NOT is_muted
            WHERE conversation_id = $1 AND user_id = $2
            RETURNING is_muted
            """,
            conversation_id,
            current_user.id,
        )
        return {"muted": new_muted}


@router.get("/unread-count")
async def get_unread_count(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get the number of conversations with unread messages."""
    async with get_connection() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT ip.conversation_id)
            FROM inbox_participants ip
            WHERE ip.user_id = $1
              AND EXISTS (
                SELECT 1 FROM inbox_messages im
                WHERE im.conversation_id = ip.conversation_id
                  AND im.sender_id != $1
                  AND (ip.last_read_at IS NULL OR im.created_at > ip.last_read_at)
              )
            """,
            current_user.id,
        )
        return {"count": count}


@router.get("/search-users", response_model=list[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=2, max_length=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Search for users to start a conversation with.

    Same-company users are matched by name or email substring.
    Cross-company users are only matched by exact email address.
    """
    async with get_connection() as conn:
        search_pattern = f"%{q}%"

        rows = await conn.fetch(
            f"""
            SELECT u.id, u.email, u.role,
                   {_USER_NAME_EXPR} AS name,
                   co.name AS company_name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            LEFT JOIN companies co ON co.id = COALESCE(c.company_id, e.org_id)
            WHERE u.id != $1
              AND u.is_active = true
              AND (
                c.name ILIKE $2
                OR CONCAT(e.first_name, ' ', e.last_name) ILIKE $2
                OR a.name ILIKE $2
                OR u.email ILIKE $2
              )
            ORDER BY u.email
            LIMIT 20
            """,
            current_user.id,
            search_pattern,
        )

        return [
            UserSearchResult(
                id=r["id"],
                email=r["email"],
                name=r["name"] or r["email"],
                role=r["role"],
                company_name=r["company_name"],
            )
            for r in rows
        ]
