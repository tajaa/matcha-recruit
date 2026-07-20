"""Shared logic for the broker↔company chat.

Both the broker-facing router (``routes/broker/chat.py``) and the company-facing
router (``routes/broker_chat_company.py``) go through here so the access rules,
message insert, read watermarks and notification fan-out live in exactly one
place. Routers own auth (which *side* the caller is on and which broker/company
they may touch); this module owns the data.

Access spine: ``broker_company_links`` (status IN ('active','grace')) decides
which (broker, company) pairs may hold a conversation. A conversation is only
reachable while that link is live — a terminated relationship hides the history
from both sides.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from ..models.broker_chat import MessageReference
from ..services import notification_service

logger = logging.getLogger(__name__)

ACTIVE_LINK_STATUSES = ("active", "grace")

# Sender display name: company users resolve to clients.name; broker members
# have no name row, so they fall back to their login email.
_SENDER_NAME_EXPR = "COALESCE(cl.name, u.email)"


# --------------------------------------------------------------------------- #
# Access resolution
# --------------------------------------------------------------------------- #
async def resolve_broker_id(conn, user_id: UUID) -> UUID:
    """The broker_id for a broker member. 403 if the user has no active seat."""
    broker_id = await conn.fetchval(
        """
        SELECT broker_id FROM broker_members
        WHERE user_id = $1 AND is_active = true
        ORDER BY created_at ASC LIMIT 1
        """,
        user_id,
    )
    if not broker_id:
        raise HTTPException(status_code=403, detail="No active broker membership")
    return broker_id


async def broker_can_reach_company(conn, broker_id: UUID, company_id: UUID) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT 1 FROM broker_company_links
            WHERE broker_id = $1 AND company_id = $2 AND status = ANY($3::text[])
            """,
            broker_id, company_id, list(ACTIVE_LINK_STATUSES),
        )
    )


async def assert_broker_reaches_company(conn, broker_id: UUID, company_id: UUID) -> None:
    if not await broker_can_reach_company(conn, broker_id, company_id):
        raise HTTPException(status_code=403, detail="Broker is not linked to that company")


async def company_active_broker_ids(conn, company_id: UUID) -> list[UUID]:
    rows = await conn.fetch(
        """
        SELECT broker_id FROM broker_company_links
        WHERE company_id = $1 AND status = ANY($2::text[])
        ORDER BY activated_at ASC NULLS LAST, linked_at ASC
        """,
        company_id, list(ACTIVE_LINK_STATUSES),
    )
    return [r["broker_id"] for r in rows]


# --------------------------------------------------------------------------- #
# Conversations
# --------------------------------------------------------------------------- #
def _reference_from_row(row) -> Optional[dict]:
    if not row["reference_type"]:
        return None
    return {
        "type": row["reference_type"],
        "id": row["reference_id"],
        "label": row["reference_label"] or row["reference_type"],
    }


def _conversation_dict(row) -> dict:
    return {
        "id": row["id"],
        "broker_id": row["broker_id"],
        "company_id": row["company_id"],
        "company_name": row["company_name"],
        "broker_name": row["broker_name"],
        "subject": row["subject"],
        "status": row["status"],
        "reference": _reference_from_row(row),
        "created_by_side": row["created_by_side"],
        "last_message_at": row["last_message_at"],
        "last_message_preview": row["last_message_preview"],
        "unread_count": int(row["unread_count"] or 0),
        "created_at": row["created_at"],
    }


async def list_conversations(
    conn,
    *,
    user_id: UUID,
    broker_id: Optional[UUID] = None,
    company_id: Optional[UUID] = None,
    broker_ids: Optional[list[UUID]] = None,
    include_archived: bool = False,
) -> list[dict]:
    """List conversations for one side, newest-active first, with unread counts.

    Exactly one selector is used: ``broker_id`` (broker side, scoped to one
    company optionally) or ``company_id`` + ``broker_ids`` (company side).
    """
    where = ["1=1"]
    params: list = []

    def p(v):
        params.append(v)
        return f"${len(params)}"

    if broker_id is not None:
        where.append(f"c.broker_id = {p(broker_id)}")
        if company_id is not None:
            where.append(f"c.company_id = {p(company_id)}")
    else:
        where.append(f"c.company_id = {p(company_id)}")
        ids = broker_ids or []
        if not ids:
            return []
        where.append(f"c.broker_id = ANY({p(ids)}::uuid[])")

    if not include_archived:
        where.append("c.status <> 'archived'")

    uid = p(user_id)
    rows = await conn.fetch(
        f"""
        SELECT c.id, c.broker_id, c.company_id, c.subject, c.status,
               c.reference_type, c.reference_id, c.reference_label,
               c.created_by_side, c.last_message_at, c.last_message_preview,
               c.created_at,
               comp.name AS company_name,
               b.name AS broker_name,
               (
                   SELECT COUNT(*) FROM broker_company_messages m
                   LEFT JOIN broker_company_conversation_reads r
                     ON r.conversation_id = m.conversation_id AND r.user_id = {uid}
                   WHERE m.conversation_id = c.id
                     AND m.deleted_at IS NULL
                     AND m.sender_user_id <> {uid}
                     AND (r.last_read_at IS NULL OR m.created_at > r.last_read_at)
               ) AS unread_count
        FROM broker_company_conversations c
        JOIN companies comp ON comp.id = c.company_id
        JOIN brokers b ON b.id = c.broker_id
        WHERE {' AND '.join(where)}
        ORDER BY c.last_message_at DESC NULLS LAST, c.created_at DESC
        """,
        *params,
    )
    return [_conversation_dict(r) for r in rows]


async def get_conversation(conn, conversation_id: UUID, *, user_id: UUID) -> Optional[dict]:
    """Fetch one conversation with its unread count. Access is checked by caller."""
    row = await conn.fetchrow(
        """
        SELECT c.id, c.broker_id, c.company_id, c.subject, c.status,
               c.reference_type, c.reference_id, c.reference_label,
               c.created_by_side, c.last_message_at, c.last_message_preview,
               c.created_at,
               comp.name AS company_name,
               b.name AS broker_name,
               (
                   SELECT COUNT(*) FROM broker_company_messages m
                   LEFT JOIN broker_company_conversation_reads r
                     ON r.conversation_id = m.conversation_id AND r.user_id = $2
                   WHERE m.conversation_id = c.id
                     AND m.deleted_at IS NULL
                     AND m.sender_user_id <> $2
                     AND (r.last_read_at IS NULL OR m.created_at > r.last_read_at)
               ) AS unread_count
        FROM broker_company_conversations c
        JOIN companies comp ON comp.id = c.company_id
        JOIN brokers b ON b.id = c.broker_id
        WHERE c.id = $1
        """,
        conversation_id, user_id,
    )
    return _conversation_dict(row) if row else None


async def create_conversation(
    conn,
    *,
    broker_id: UUID,
    company_id: UUID,
    created_by: UUID,
    created_by_side: str,
    subject: Optional[str],
    reference: Optional[MessageReference],
) -> dict:
    ref_type = reference.type if reference else None
    ref_id = reference.id if reference else None
    ref_label = reference.label if reference else None
    row = await conn.fetchrow(
        """
        INSERT INTO broker_company_conversations
            (broker_id, company_id, subject, reference_type, reference_id,
             reference_label, created_by, created_by_side)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, broker_id, company_id, subject, status,
                  reference_type, reference_id, reference_label,
                  created_by_side, last_message_at, last_message_preview, created_at
        """,
        broker_id, company_id, subject, ref_type, ref_id, ref_label,
        created_by, created_by_side,
    )
    d = dict(row)
    d["unread_count"] = 0
    d["company_name"] = await conn.fetchval("SELECT name FROM companies WHERE id = $1", company_id)
    d["broker_name"] = await conn.fetchval("SELECT name FROM brokers WHERE id = $1", broker_id)
    return _conversation_dict(d)


async def set_conversation_status(conn, conversation_id: UUID, status: str) -> None:
    await conn.execute(
        "UPDATE broker_company_conversations SET status = $2, updated_at = NOW() WHERE id = $1",
        conversation_id, status,
    )


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
def _message_dict(row) -> dict:
    ref = None
    if row["reference_type"]:
        ref = {
            "type": row["reference_type"],
            "id": row["reference_id"],
            "label": row["reference_label"] or row["reference_type"],
        }
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "sender_user_id": row["sender_user_id"],
        "sender_side": row["sender_side"],
        "sender_name": row["sender_name"],
        "body": row["body"],
        "reference": ref,
        "client_message_id": row["client_message_id"],
        "created_at": row["created_at"],
        "edited_at": row["edited_at"],
    }


async def list_messages(
    conn, conversation_id: UUID, *, before=None, limit: int = 50
) -> list[dict]:
    limit = max(1, min(limit, 100))
    params: list = [conversation_id]
    cursor = ""
    if before is not None:
        params.append(before)
        cursor = f"AND m.created_at < ${len(params)}"
    params.append(limit)
    rows = await conn.fetch(
        f"""
        SELECT m.id, m.conversation_id, m.sender_user_id, m.sender_side,
               m.body, m.reference_type, m.reference_id, m.reference_label,
               m.client_message_id, m.created_at, m.edited_at,
               {_SENDER_NAME_EXPR} AS sender_name
        FROM broker_company_messages m
        JOIN users u ON u.id = m.sender_user_id
        LEFT JOIN clients cl ON cl.user_id = m.sender_user_id
        WHERE m.conversation_id = $1 AND m.deleted_at IS NULL {cursor}
        ORDER BY m.created_at DESC
        LIMIT ${len(params)}
        """,
        *params,
    )
    # Return chronological (oldest → newest) for rendering.
    return [_message_dict(r) for r in reversed(rows)]


async def post_message(
    conn,
    *,
    conversation_id: UUID,
    sender_user_id: UUID,
    sender_side: str,
    body: str,
    reference: Optional[MessageReference],
    client_message_id: Optional[UUID],
) -> tuple[dict, bool]:
    """Insert a message (idempotent on client_message_id). Returns (message, is_new).

    On a fresh insert the conversation's last-message fields advance and the
    sender's own read watermark is bumped. Caller handles notification fan-out.
    """
    ref_type = reference.type if reference else None
    ref_id = reference.id if reference else None
    ref_label = reference.label if reference else None
    row = await conn.fetchrow(
        """
        INSERT INTO broker_company_messages
            (conversation_id, sender_user_id, sender_side, body,
             reference_type, reference_id, reference_label, client_message_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (sender_user_id, client_message_id)
            WHERE client_message_id IS NOT NULL
            DO UPDATE SET id = broker_company_messages.id
        RETURNING id, conversation_id, sender_user_id, sender_side, body,
                  reference_type, reference_id, reference_label, client_message_id,
                  created_at, edited_at, (xmax = 0) AS inserted
        """,
        conversation_id, sender_user_id, sender_side, body,
        ref_type, ref_id, ref_label, client_message_id,
    )
    is_new = bool(row["inserted"])
    sender_name = await conn.fetchval(
        f"""
        SELECT {_SENDER_NAME_EXPR}
        FROM users u LEFT JOIN clients cl ON cl.user_id = u.id
        WHERE u.id = $1
        """,
        sender_user_id,
    )
    msg = dict(row)
    msg["sender_name"] = sender_name or "Unknown"

    if is_new:
        preview = (body[:140] + "…") if len(body) > 140 else body
        await conn.execute(
            """
            UPDATE broker_company_conversations
            SET last_message_at = $2, last_message_preview = $3,
                updated_at = NOW(),
                status = CASE WHEN status = 'archived' THEN 'open' ELSE status END
            WHERE id = $1
            """,
            conversation_id, row["created_at"], preview,
        )
        # The sender has, by definition, read their own message.
        await mark_read(conn, conversation_id, sender_user_id, row["id"])

    return _message_dict(msg), is_new


async def edit_message(conn, message_id: UUID, sender_user_id: UUID, body: str) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        UPDATE broker_company_messages
        SET body = $3, edited_at = NOW()
        WHERE id = $1 AND sender_user_id = $2 AND deleted_at IS NULL
        RETURNING id, conversation_id, sender_user_id, sender_side, body,
                  reference_type, reference_id, reference_label, client_message_id,
                  created_at, edited_at
        """,
        message_id, sender_user_id, body,
    )
    if not row:
        return None
    sender_name = await conn.fetchval(
        f"""SELECT {_SENDER_NAME_EXPR} FROM users u
            LEFT JOIN clients cl ON cl.user_id = u.id WHERE u.id = $1""",
        sender_user_id,
    )
    d = dict(row)
    d["sender_name"] = sender_name or "Unknown"
    return _message_dict(d)


async def delete_message(conn, message_id: UUID, sender_user_id: UUID) -> bool:
    result = await conn.execute(
        """
        UPDATE broker_company_messages SET deleted_at = NOW()
        WHERE id = $1 AND sender_user_id = $2 AND deleted_at IS NULL
        """,
        message_id, sender_user_id,
    )
    return result.endswith("1")


# --------------------------------------------------------------------------- #
# Read watermarks
# --------------------------------------------------------------------------- #
async def mark_read(conn, conversation_id: UUID, user_id: UUID, last_read_message_id=None) -> None:
    await conn.execute(
        """
        INSERT INTO broker_company_conversation_reads
            (conversation_id, user_id, last_read_at, last_read_message_id)
        VALUES ($1, $2, NOW(), $3)
        ON CONFLICT (conversation_id, user_id)
        DO UPDATE SET last_read_at = NOW(),
                      last_read_message_id = COALESCE($3, broker_company_conversation_reads.last_read_message_id)
        """,
        conversation_id, user_id, last_read_message_id,
    )


async def total_unread(
    conn,
    *,
    user_id: UUID,
    broker_id: Optional[UUID] = None,
    company_id: Optional[UUID] = None,
    broker_ids: Optional[list[UUID]] = None,
) -> int:
    where = ["m.deleted_at IS NULL", "m.sender_user_id <> $1",
             "(r.last_read_at IS NULL OR m.created_at > r.last_read_at)",
             "c.status <> 'archived'"]
    params: list = [user_id]

    def p(v):
        params.append(v)
        return f"${len(params)}"

    if broker_id is not None:
        where.append(f"c.broker_id = {p(broker_id)}")
    else:
        where.append(f"c.company_id = {p(company_id)}")
        ids = broker_ids or []
        if not ids:
            return 0
        where.append(f"c.broker_id = ANY({p(ids)}::uuid[])")

    return int(await conn.fetchval(
        f"""
        SELECT COUNT(*)
        FROM broker_company_messages m
        JOIN broker_company_conversations c ON c.id = m.conversation_id
        LEFT JOIN broker_company_conversation_reads r
          ON r.conversation_id = m.conversation_id AND r.user_id = $1
        WHERE {' AND '.join(where)}
        """,
        *params,
    ) or 0)


# --------------------------------------------------------------------------- #
# Notification fan-out (best-effort, runs after the send commits)
# --------------------------------------------------------------------------- #
async def notify_new_message(
    *,
    conversation_id: UUID,
    company_id: UUID,
    broker_id: UUID,
    sender_user_id: UUID,
    sender_side: str,
    sender_name: str,
    preview: str,
    subject: Optional[str],
) -> None:
    """Fan a bell notification out to the *other* side's users.

    Reuses ``notification_service.create_notification`` — which pushes over the
    live channels WebSocket, does an APNs fallback, and records the bell row —
    so this is the real-time delivery path for new messages.
    """
    from ...database import get_connection

    try:
        async with get_connection() as conn:
            if sender_side == "broker":
                rows = await conn.fetch(
                    "SELECT user_id FROM clients WHERE company_id = $1", company_id,
                )
                link = f"/app/broker-chat?c={conversation_id}"
            else:
                rows = await conn.fetch(
                    "SELECT user_id FROM broker_members WHERE broker_id = $1 AND is_active = true",
                    broker_id,
                )
                link = f"/broker/messages?c={conversation_id}"
        recipients = [r["user_id"] for r in rows if r["user_id"] != sender_user_id]
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("broker-chat fan-out recipient lookup failed: %s", e)
        return

    title = f"{sender_name}" + (f" · {subject}" if subject else "")
    for uid in recipients:
        try:
            await notification_service.create_notification(
                user_id=uid,
                company_id=company_id,
                type="broker_chat_message",
                title=title or "New message",
                body=preview,
                link=link,
                metadata={"conversation_id": str(conversation_id), "sender_side": sender_side},
            )
        except Exception as e:  # pragma: no cover - a bad recipient must not sink the rest
            logger.warning("broker-chat notify failed for %s: %s", uid, e)
