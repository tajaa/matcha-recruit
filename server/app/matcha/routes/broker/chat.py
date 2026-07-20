"""Broker side of the broker↔company chat.

Mounted at ``/broker`` (prefix in ``routes/__init__.py``); every endpoint is
``require_broker`` and re-derives the caller's ``broker_id`` from their active
membership, so a broker can only ever touch conversations with companies it is
linked to. The company-facing half lives in ``routes/broker_chat_company.py``;
both share ``services/broker_chat_service.py``.
"""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ....database import get_connection
from ...dependencies import require_broker
from ...models.broker_chat import (
    ConversationCreate,
    ConversationListOut,
    ConversationOut,
    MarkReadRequest,
    MessageCreate,
    MessageEdit,
    MessageOut,
)
from ...services import broker_chat_service as svc
from ....core.models.auth import CurrentUser

router = APIRouter()

SIDE = "broker"


async def _load_conversation(conn, conversation_id: UUID, broker_id: UUID, user_id: UUID) -> dict:
    conv = await svc.get_conversation(conn, conversation_id, user_id=user_id)
    if not conv or conv["broker_id"] != broker_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/chat/targets")
async def list_targets(current_user: CurrentUser = Depends(require_broker)):
    """Active-linked client companies the broker may open a conversation with."""
    async with get_connection() as conn:
        broker_id = await svc.resolve_broker_id(conn, current_user.id)
        rows = await conn.fetch(
            """
            SELECT l.company_id AS id, comp.name AS name
            FROM broker_company_links l
            JOIN companies comp ON comp.id = l.company_id
            WHERE l.broker_id = $1 AND l.status = ANY($2::text[])
            ORDER BY comp.name ASC
            """,
            broker_id, list(svc.ACTIVE_LINK_STATUSES),
        )
    return [{"id": str(r["id"]), "name": r["name"]} for r in rows]


@router.get("/chat/conversations", response_model=ConversationListOut)
async def list_conversations(
    company_id: UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        broker_id = await svc.resolve_broker_id(conn, current_user.id)
        if company_id is not None:
            await svc.assert_broker_reaches_company(conn, broker_id, company_id)
        convs = await svc.list_conversations(
            conn, user_id=current_user.id, broker_id=broker_id,
            company_id=company_id, include_archived=include_archived,
        )
        total = await svc.total_unread(conn, user_id=current_user.id, broker_id=broker_id)
    return {"conversations": convs, "total_unread": total}


@router.post("/chat/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_broker),
):
    if not body.company_id:
        raise HTTPException(status_code=422, detail="company_id is required")
    async with get_connection() as conn:
        broker_id = await svc.resolve_broker_id(conn, current_user.id)
        await svc.assert_broker_reaches_company(conn, broker_id, body.company_id)
        conv = await svc.create_conversation(
            conn, broker_id=broker_id, company_id=body.company_id,
            created_by=current_user.id, created_by_side=SIDE,
            subject=body.subject, reference=body.reference,
        )
        if body.body:
            msg, is_new = await svc.post_message(
                conn, conversation_id=conv["id"], sender_user_id=current_user.id,
                sender_side=SIDE, body=body.body, reference=None, client_message_id=None,
            )
            if is_new:
                _schedule_fanout(background_tasks, conv, msg)
                conv = await svc.get_conversation(conn, conv["id"], user_id=current_user.id)
    return conv


@router.get("/chat/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        broker_id = await svc.resolve_broker_id(conn, current_user.id)
        return await _load_conversation(conn, conversation_id, broker_id, current_user.id)


@router.get("/chat/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID,
    before: str | None = Query(default=None, description="ISO timestamp cursor"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(require_broker),
):
    from datetime import datetime
    async with get_connection() as conn:
        broker_id = await svc.resolve_broker_id(conn, current_user.id)
        await _load_conversation(conn, conversation_id, broker_id, current_user.id)
        cursor = None
        if before:
            try:
                cursor = datetime.fromisoformat(before)
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid 'before' cursor")
        return await svc.list_messages(conn, conversation_id, before=cursor, limit=limit)


@router.post("/chat/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    conversation_id: UUID,
    body: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        broker_id = await svc.resolve_broker_id(conn, current_user.id)
        conv = await _load_conversation(conn, conversation_id, broker_id, current_user.id)
        # Re-check the link is still live before allowing a new message.
        await svc.assert_broker_reaches_company(conn, broker_id, conv["company_id"])
        msg, is_new = await svc.post_message(
            conn, conversation_id=conversation_id, sender_user_id=current_user.id,
            sender_side=SIDE, body=body.body, reference=body.reference,
            client_message_id=body.client_message_id,
        )
        if is_new:
            _schedule_fanout(background_tasks, conv, msg)
    return msg


@router.patch("/chat/messages/{message_id}", response_model=MessageOut)
async def edit_message(
    message_id: UUID,
    body: MessageEdit,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        await svc.resolve_broker_id(conn, current_user.id)
        msg = await svc.edit_message(conn, message_id, current_user.id, body.body)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@router.delete("/chat/messages/{message_id}", status_code=204)
async def delete_message(
    message_id: UUID,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        await svc.resolve_broker_id(conn, current_user.id)
        ok = await svc.delete_message(conn, message_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")


@router.put("/chat/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: UUID,
    body: MarkReadRequest,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        broker_id = await svc.resolve_broker_id(conn, current_user.id)
        await _load_conversation(conn, conversation_id, broker_id, current_user.id)
        await svc.mark_read(conn, conversation_id, current_user.id, body.last_read_message_id)
    return {"ok": True}


@router.post("/chat/conversations/{conversation_id}/archive", response_model=ConversationOut)
async def set_archived(
    conversation_id: UUID,
    archived: bool = Query(default=True),
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        broker_id = await svc.resolve_broker_id(conn, current_user.id)
        await _load_conversation(conn, conversation_id, broker_id, current_user.id)
        await svc.set_conversation_status(conn, conversation_id, "archived" if archived else "open")
        return await svc.get_conversation(conn, conversation_id, user_id=current_user.id)


@router.get("/chat/unread-count")
async def unread_count(current_user: CurrentUser = Depends(require_broker)):
    async with get_connection() as conn:
        broker_id = await svc.resolve_broker_id(conn, current_user.id)
        total = await svc.total_unread(conn, user_id=current_user.id, broker_id=broker_id)
    return {"unread": total}


def _schedule_fanout(background_tasks: BackgroundTasks, conv: dict, msg: dict) -> None:
    preview = msg["body"]
    if len(preview) > 140:
        preview = preview[:140] + "…"
    background_tasks.add_task(
        svc.notify_new_message,
        conversation_id=conv["id"],
        company_id=conv["company_id"],
        broker_id=conv["broker_id"],
        sender_user_id=msg["sender_user_id"],
        sender_side=msg["sender_side"],
        sender_name=msg["sender_name"],
        preview=preview,
        subject=conv.get("subject"),
    )
