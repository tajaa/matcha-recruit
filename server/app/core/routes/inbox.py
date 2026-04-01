"""Inbox / messaging routes."""

import logging
from datetime import datetime
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
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_user_display_name(conn, user_id: UUID) -> tuple[str, str, str]:
    """Return (name, email, role) for a user by checking clients -> employees -> admins -> users."""
    row = await conn.fetchrow(
        """
        SELECT u.email, u.role,
               COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
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
        """
        SELECT ip.user_id, ip.last_read_at, ip.is_muted,
               u.email, u.role,
               COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
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


async def _send_message_notification(conn, conversation_id: UUID, sender_id: UUID, sender_name: str, preview: str) -> None:
    """Best-effort email notification to other participants (batched at 15-min intervals)."""
    try:
        from ..services.email import get_email_service
        email_svc = get_email_service()
        if not email_svc.is_configured():
            logger.debug("Email not configured — skipping inbox notification")
            return

        participants = await conn.fetch(
            """
            SELECT ip.user_id, u.email,
                   COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
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

        for p in participants:
            try:
                # Check batch window — only send if last email to this recipient
                # from this sender was >15 minutes ago (or never sent).
                batch = await conn.fetchrow(
                    """
                    SELECT last_sent_at FROM inbox_email_batches
                    WHERE recipient_id = $1 AND sender_id = $2
                    """,
                    p["user_id"],
                    sender_id,
                )

                should_send = True
                if batch and batch["last_sent_at"]:
                    from datetime import timezone
                    last_sent = batch["last_sent_at"]
                    if last_sent.tzinfo is None:
                        last_sent = last_sent.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    if (now - last_sent).total_seconds() < 900:  # 15 minutes
                        should_send = False

                if not should_send:
                    continue

                await email_svc.send_email(
                    to_email=p["email"],
                    to_name=p["name"],
                    subject=f"New message from {sender_name}",
                    html_content=(
                        f"<p><strong>{sender_name}</strong> sent you a message:</p>"
                        f"<blockquote>{preview[:200]}</blockquote>"
                        f"<p><a href=\"https://hey-matcha.com/inbox\">View in Matcha</a></p>"
                    ),
                )

                # Upsert the batch tracking row
                await conn.execute(
                    """
                    INSERT INTO inbox_email_batches (recipient_id, sender_id, last_sent_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (recipient_id, sender_id)
                    DO UPDATE SET last_sent_at = NOW()
                    """,
                    p["user_id"],
                    sender_id,
                )
            except Exception:
                logger.warning("Failed to send inbox notification to %s", p["email"], exc_info=True)
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
        rows = await conn.fetch(
            """
            SELECT ic.id, ic.title, ic.is_group, ic.last_message_at, ic.last_message_preview
            FROM inbox_conversations ic
            JOIN inbox_participants ip ON ip.conversation_id = ic.id
            WHERE ip.user_id = $1
            ORDER BY ic.last_message_at DESC NULLS LAST
            LIMIT $2 OFFSET $3
            """,
            current_user.id,
            limit,
            offset,
        )

        result: list[ConversationSummary] = []
        for r in rows:
            conv_id = r["id"]
            participants = await _build_participant_list(conn, conv_id)

            # Count unread messages for this user
            participant_row = await conn.fetchrow(
                "SELECT last_read_at FROM inbox_participants WHERE conversation_id = $1 AND user_id = $2",
                conv_id,
                current_user.id,
            )
            last_read = participant_row["last_read_at"] if participant_row else None

            if last_read:
                unread = await conn.fetchval(
                    "SELECT COUNT(*) FROM inbox_messages WHERE conversation_id = $1 AND created_at > $2 AND sender_id != $3",
                    conv_id,
                    last_read,
                    current_user.id,
                )
            else:
                # Never read — all messages from others are unread
                unread = await conn.fetchval(
                    "SELECT COUNT(*) FROM inbox_messages WHERE conversation_id = $1 AND sender_id != $2",
                    conv_id,
                    current_user.id,
                )

            result.append(
                ConversationSummary(
                    id=r["id"],
                    title=r["title"],
                    is_group=r["is_group"],
                    last_message_at=r["last_message_at"],
                    last_message_preview=r["last_message_preview"],
                    participants=participants,
                    unread_count=unread,
                )
            )

        return result


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new conversation (or reuse an existing 1:1) and send the first message."""
    async with get_connection() as conn:
        # Validate all participant IDs exist
        all_participant_ids = list(set(body.participant_ids))
        # Remove self if accidentally included
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

        # For 1:1 conversations, check if one already exists between these two users
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

        if conversation_id:
            # Existing 1:1 — just add the new message
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
                "UPDATE inbox_conversations SET last_message_at = NOW(), last_message_preview = $2 WHERE id = $1",
                conversation_id,
                preview,
            )
            # Mark sender as read
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

            # Add all participants (including the sender)
            full_participant_ids = [current_user.id] + all_participant_ids
            for pid in full_participant_ids:
                last_read = datetime.utcnow() if pid == current_user.id else None
                await conn.execute(
                    """
                    INSERT INTO inbox_participants (conversation_id, user_id, last_read_at)
                    VALUES ($1, $2, $3)
                    """,
                    conversation_id,
                    pid,
                    last_read,
                )

            # Insert the first message
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

        # Send email notification (best-effort)
        sender_name, _, _ = await _resolve_user_display_name(conn, current_user.id)
        await _send_message_notification(conn, conversation_id, current_user.id, sender_name, preview)

        # Build full response
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

        conv = await conn.fetchrow(
            "SELECT id, title, is_group, created_by, last_message_at, last_message_preview, created_at FROM inbox_conversations WHERE id = $1",
            conversation_id,
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Fetch messages with optional cursor-based pagination
        if before:
            # Get the created_at of the cursor message for keyset pagination
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

        # Resolve sender names for all messages
        sender_cache: dict[UUID, str] = {}
        messages: list[MessageResponse] = []
        for m in msg_rows:
            sid = m["sender_id"]
            if sid not in sender_cache:
                name, _, _ = await _resolve_user_display_name(conn, sid)
                sender_cache[sid] = name
            messages.append(
                MessageResponse(
                    id=m["id"],
                    conversation_id=m["conversation_id"],
                    sender_id=sid,
                    sender_name=sender_cache[sid],
                    content=m["content"],
                    created_at=m["created_at"],
                    edited_at=m["edited_at"],
                )
            )

        participants = await _build_participant_list(conn, conversation_id)

        # Side effect: mark as read
        await conn.execute(
            "UPDATE inbox_participants SET last_read_at = NOW() WHERE conversation_id = $1 AND user_id = $2",
            conversation_id,
            current_user.id,
        )

        return ConversationResponse(
            id=conv["id"],
            title=conv["title"],
            is_group=conv["is_group"],
            created_by=conv["created_by"],
            last_message_at=conv["last_message_at"],
            last_message_preview=conv["last_message_preview"],
            participants=participants,
            messages=messages,
            unread_count=0,  # Just marked as read
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
            "UPDATE inbox_conversations SET last_message_at = NOW(), last_message_preview = $2 WHERE id = $1",
            conversation_id,
            preview,
        )

        # Mark sender as having read up to now
        await conn.execute(
            "UPDATE inbox_participants SET last_read_at = NOW() WHERE conversation_id = $1 AND user_id = $2",
            conversation_id,
            current_user.id,
        )

        sender_name, _, _ = await _resolve_user_display_name(conn, current_user.id)

        # Best-effort email notifications
        await _send_message_notification(conn, conversation_id, current_user.id, sender_name, preview)

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
        # Determine the current user's company
        company_id = await conn.fetchval(
            "SELECT company_id FROM clients WHERE user_id = $1", current_user.id
        )
        if not company_id:
            company_id = await conn.fetchval(
                "SELECT company_id FROM employees WHERE user_id = $1", current_user.id
            )

        results: list[UserSearchResult] = []
        search_pattern = f"%{q}%"

        if company_id:
            # Same-company: search by name/email ILIKE
            same_company_rows = await conn.fetch(
                """
                SELECT u.id, u.email, u.role,
                       COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name)) AS name,
                       co.name AS company_name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id AND c.company_id = $1
                LEFT JOIN employees e ON e.user_id = u.id AND e.company_id = $1
                LEFT JOIN companies co ON co.id = $1
                WHERE u.id != $2
                  AND u.is_active = true
                  AND (c.company_id = $1 OR e.company_id = $1)
                  AND (
                    c.name ILIKE $3
                    OR CONCAT(e.first_name, ' ', e.last_name) ILIKE $3
                    OR u.email ILIKE $3
                  )
                LIMIT 20
                """,
                company_id,
                current_user.id,
                search_pattern,
            )
            for r in same_company_rows:
                results.append(
                    UserSearchResult(
                        id=r["id"],
                        email=r["email"],
                        name=r["name"] or r["email"],
                        role=r["role"],
                        company_name=r["company_name"],
                    )
                )

        # Cross-company: exact email match only
        if len(results) < 20:
            existing_ids = {r.id for r in results}
            cross_rows = await conn.fetch(
                """
                SELECT u.id, u.email, u.role,
                       COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name,
                       co.name AS company_name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                LEFT JOIN companies co ON co.id = COALESCE(c.company_id, e.company_id)
                WHERE u.id != $1
                  AND u.is_active = true
                  AND u.email = $2
                LIMIT $3
                """,
                current_user.id,
                q.lower().strip(),
                20 - len(results),
            )
            for r in cross_rows:
                if r["id"] not in existing_ids:
                    results.append(
                        UserSearchResult(
                            id=r["id"],
                            email=r["email"],
                            name=r["name"] or r["email"],
                            role=r["role"],
                            company_name=r["company_name"],
                        )
                    )

        return results
