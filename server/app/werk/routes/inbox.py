"""Inbox / messaging routes."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from ...database import get_connection
from ...core.dependencies import get_current_user
from ...core.models.auth import CurrentUser
from ...core.services.storage import get_storage
from ._shared import _USER_NAME_EXPR, resolve_display_name, spawn_bg

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# File upload constants
# ---------------------------------------------------------------------------

MAX_FILE_COUNT = 5
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_CONTENT_TYPES = IMAGE_CONTENT_TYPES | {
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".pdf", ".txt", ".csv", ".doc", ".docx",
}


async def _process_uploads(files: list[UploadFile]) -> list[dict]:
    """Validate and upload files to S3. Returns attachment metadata list.

    Extension is the primary gate — an OR check against content type let a
    spoofed `Content-Type: image/png` on a `.exe` through (browser-supplied
    content type is untrusted). The read is capped mid-stream via
    read_upload_capped rather than `await file.read()` first, so an oversize
    body is rejected at the cap instead of fully materialized in memory.
    """
    from ...matcha.services._shared.uploads import read_upload_capped

    if len(files) > MAX_FILE_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum is {MAX_FILE_COUNT}.",
        )

    storage = get_storage()
    attachments: list[dict] = []

    for file in files:
        filename = file.filename or "upload"
        ct = file.content_type or "application/octet-stream"
        ext = os.path.splitext(filename)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type not allowed: {filename}")
        if ct not in ALLOWED_CONTENT_TYPES and ct != "application/octet-stream":
            raise HTTPException(status_code=400, detail=f"File type not allowed: {filename}")

        file_bytes = await read_upload_capped(file, MAX_FILE_SIZE)
        size = len(file_bytes)

        url = await storage.upload_file(file_bytes, filename, prefix="inbox", content_type=ct)
        attachments.append({
            "url": url,
            "filename": filename,
            "content_type": ct,
            "size": size,
        })

    return attachments


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AttachmentResponse(BaseModel):
    url: str
    filename: str
    content_type: str
    size: int


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    sender_name: str
    content: str
    attachments: list[AttachmentResponse] = []
    created_at: datetime
    edited_at: Optional[datetime] = None


class ParticipantResponse(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: str
    avatar_url: Optional[str] = None
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
    avatar_url: Optional[str] = None
    company_name: Optional[str] = None


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
               u.email, u.role, u.avatar_url, {_USER_NAME_EXPR} AS name
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
            avatar_url=r["avatar_url"],
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
        from ...core.services.email import get_email_service
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

        # Immediate APNs push (no email cooldown) to offline, non-muted
        # participants. DMs aren't on the channels socket, so push is the only
        # realtime signal once the recipient's app is backgrounded.
        try:
            from ...core.services import apns_service
            for p in participants:
                if not await apns_service.is_user_online(p["user_id"]):
                    await apns_service.send_to_user(
                        p["user_id"], sender_name, preview[:200],
                        {"type": "inbox_message",
                         "metadata": {"conversation_id": str(conversation_id)}},
                    )
        except Exception:
            logger.warning("Inbox APNs push failed", exc_info=True)

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
                       u.email, u.role, u.avatar_url, {_USER_NAME_EXPR} AS name
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
                        avatar_url=p["avatar_url"],
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
    participant_ids: str = Form(...),
    message: str = Form(...),
    title: Optional[str] = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new conversation (or reuse an existing 1:1) and send the first message."""
    # Parse participant_ids from JSON string (FormData can't send arrays natively)
    try:
        parsed_ids = json.loads(participant_ids)
        if not isinstance(parsed_ids, list) or not parsed_ids:
            raise ValueError
        parsed_uuids = [UUID(pid) for pid in parsed_ids]
    except (json.JSONDecodeError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="participant_ids must be a JSON array of UUIDs")

    if not message.strip() and not files:
        raise HTTPException(status_code=400, detail="Message content or files required")
    if len(message) > 5000:
        raise HTTPException(status_code=400, detail="Message too long (max 5000 characters)")
    if len(parsed_uuids) > 20:
        raise HTTPException(status_code=400, detail="Too many participants (max 20)")

    attachments = await _process_uploads(files) if files else []
    attachments_json = json.dumps(attachments) if attachments else "[]"
    msg_content = message.strip()

    async with get_connection() as conn:
        all_participant_ids = list(set(parsed_uuids))
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

        preview = msg_content[:100]
        if not preview and attachments:
            preview = f"[{len(attachments)} attachment{'s' if len(attachments) > 1 else ''}]"

        async with conn.transaction():
            # For 1:1, check if conversation already exists. Locked + moved
            # inside the transaction (was a plain pre-txn SELECT) — two
            # concurrent first-DMs between the same pair would otherwise both
            # see "no existing conversation" and create duplicates.
            if not is_group:
                other_id = all_participant_ids[0]
                lock_pair = sorted((str(current_user.id), str(other_id)))
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    f"inbox-dm:{lock_pair[0]}:{lock_pair[1]}",
                )
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

            if conversation_id:
                # Existing 1:1 — add message
                msg_row = await conn.fetchrow(
                    """
                    INSERT INTO inbox_messages (conversation_id, sender_id, content, attachments)
                    VALUES ($1, $2, $3, $4::jsonb)
                    RETURNING id, conversation_id, sender_id, content, attachments, created_at, edited_at
                    """,
                    conversation_id,
                    current_user.id,
                    msg_content,
                    attachments_json,
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
                    title,
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
                    INSERT INTO inbox_messages (conversation_id, sender_id, content, attachments)
                    VALUES ($1, $2, $3, $4::jsonb)
                    RETURNING id, conversation_id, sender_id, content, attachments, created_at, edited_at
                    """,
                    conversation_id,
                    current_user.id,
                    msg_content,
                    attachments_json,
                )

        # Email notification (outside transaction, best-effort)
        sender_name, _, _ = await _resolve_user_display_name(conn, current_user.id)
        # Fire and forget — don't block response
        spawn_bg(_send_message_notification(conversation_id, current_user.id, sender_name, preview))

        # Build response
        conv_data = await conn.fetchrow(
            "SELECT id, title, is_group, created_by, last_message_at, last_message_preview, created_at FROM inbox_conversations WHERE id = $1",
            conversation_id,
        )
        participants = await _build_participant_list(conn, conversation_id)

        sender_name_for_msg, _, _ = await _resolve_user_display_name(conn, msg_row["sender_id"])
        msg_attachments = json.loads(msg_row["attachments"]) if msg_row["attachments"] else []
        message_resp = MessageResponse(
            id=msg_row["id"],
            conversation_id=msg_row["conversation_id"],
            sender_id=msg_row["sender_id"],
            sender_name=sender_name_for_msg,
            content=msg_row["content"],
            attachments=[AttachmentResponse(**a) for a in msg_attachments],
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
            messages=[message_resp],
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
                SELECT id, conversation_id, sender_id, content, attachments, created_at, edited_at
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
                SELECT id, conversation_id, sender_id, content, attachments, created_at, edited_at
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

        messages = []
        for m in msg_rows:
            m_attachments = m["attachments"] if isinstance(m["attachments"], list) else []
            messages.append(
                MessageResponse(
                    id=m["id"],
                    conversation_id=m["conversation_id"],
                    sender_id=m["sender_id"],
                    sender_name=sender_cache.get(m["sender_id"], "Unknown"),
                    content=m["content"],
                    attachments=[AttachmentResponse(**a) for a in m_attachments],
                    created_at=m["created_at"],
                    edited_at=m["edited_at"],
                )
            )

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
    content: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Send a message in an existing conversation, optionally with file attachments."""
    if not content.strip() and not files:
        raise HTTPException(status_code=400, detail="Message content or files required")
    if len(content) > 5000:
        raise HTTPException(status_code=400, detail="Message too long (max 5000 characters)")

    async with get_connection() as conn:
        await _require_participant(conn, conversation_id, current_user.id)

    # Upload after auth check to avoid orphaned S3 files on 404
    attachments = await _process_uploads(files) if files else []
    attachments_json = json.dumps(attachments) if attachments else "[]"

    async with get_connection() as conn:

        async with conn.transaction():
            msg = await conn.fetchrow(
                """
                INSERT INTO inbox_messages (conversation_id, sender_id, content, attachments)
                VALUES ($1, $2, $3, $4::jsonb)
                RETURNING id, conversation_id, sender_id, content, attachments, created_at, edited_at
                """,
                conversation_id,
                current_user.id,
                content.strip(),
                attachments_json,
            )

            preview = content.strip()[:100]
            if not preview and attachments:
                preview = f"[{len(attachments)} attachment{'s' if len(attachments) > 1 else ''}]"
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
    spawn_bg(_send_message_notification(conversation_id, current_user.id, sender_name, preview))

    msg_attachments = msg["attachments"] if isinstance(msg["attachments"], list) else []

    return MessageResponse(
        id=msg["id"],
        conversation_id=msg["conversation_id"],
        sender_id=msg["sender_id"],
        sender_name=sender_name,
        content=msg["content"],
        attachments=[AttachmentResponse(**a) for a in msg_attachments],
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
    Platform admins keep the old global substring search.
    """
    async with get_connection() as conn:
        search_pattern = f"%{q}%"

        if current_user.role == "admin":
            rows = await conn.fetch(
                f"""
                SELECT u.id, u.email, u.role, u.avatar_url,
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
        else:
            caller_company_id = await conn.fetchval(
                """
                SELECT COALESCE(c.company_id, e.org_id)
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                WHERE u.id = $1
                """,
                current_user.id,
            )
            rows = await conn.fetch(
                f"""
                SELECT u.id, u.email, u.role, u.avatar_url,
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
                    lower(u.email) = lower($3)
                    OR (
                      $4::uuid IS NOT NULL
                      AND COALESCE(c.company_id, e.org_id) = $4
                      AND (
                        c.name ILIKE $2
                        OR CONCAT(e.first_name, ' ', e.last_name) ILIKE $2
                        OR a.name ILIKE $2
                        OR u.email ILIKE $2
                      )
                    )
                  )
                ORDER BY u.email
                LIMIT 20
                """,
                current_user.id,
                search_pattern,
                q,
                caller_company_id,
            )

        return [
            UserSearchResult(
                id=r["id"],
                email=r["email"],
                name=r["name"] or r["email"],
                role=r["role"],
                avatar_url=r["avatar_url"],
                company_name=r["company_name"],
            )
            for r in rows
        ]
