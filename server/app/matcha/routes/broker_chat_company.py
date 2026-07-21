"""Company side of the broker↔company chat.

Mounted at ``/broker-chat`` (prefix in ``routes/__init__.py``); every endpoint is
``require_client`` and re-derives the caller's company. A company user can only
reach conversations that belong to their own company and one of their
currently-linked brokers. The broker-facing half lives in
``routes/broker/chat.py``; both share ``services/broker_chat_service.py``.

Deliberately ``require_client``, not ``require_admin_or_client``: for an ``admin``
``resolve_accessible_company_scope`` falls back to the *oldest company in the
table*, so a platform admin would silently be bound to an arbitrary tenant and
post into that tenant's broker thread as if they were the client. Messages here
are attributed to a side and read by an outside party — the actor has to be a
real member of the company, not a superuser standing in for one.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ...database import get_connection
from ..dependencies import get_client_company_id, require_client
from ..models.broker_chat import (
    ConversationCreate,
    ConversationListOut,
    ConversationOut,
    MarkReadRequest,
    MessageCreate,
    MessageEdit,
    MessageOut,
)
from ..services import broker_chat_service as svc
from ...core.models.auth import CurrentUser

router = APIRouter()

SIDE = "company"


async def _resolve_scope(conn, current_user: CurrentUser) -> tuple[UUID, list[UUID]]:
    company_id = await get_client_company_id(current_user)
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    broker_ids = await svc.company_active_broker_ids(conn, company_id)
    return company_id, broker_ids


async def _load_conversation(conn, conversation_id: UUID, company_id: UUID,
                             broker_ids: list[UUID], user_id: UUID) -> dict:
    conv = await svc.get_conversation(conn, conversation_id, user_id=user_id)
    if not conv or conv["company_id"] != company_id or conv["broker_id"] not in broker_ids:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/summary")
async def summary(current_user: CurrentUser = Depends(require_client)):
    """Lightweight sidebar helper: does this company have a broker, and unread count."""
    async with get_connection() as conn:
        company_id, broker_ids = await _resolve_scope(conn, current_user)
        if not broker_ids:
            return {"has_active_broker": False, "unread": 0, "brokers": []}
        brokers = await conn.fetch(
            "SELECT id, name FROM brokers WHERE id = ANY($1::uuid[])", broker_ids,
        )
        total = await svc.total_unread(
            conn, user_id=current_user.id, company_id=company_id, broker_ids=broker_ids,
        )
    return {
        "has_active_broker": True,
        "unread": total,
        "brokers": [{"id": str(b["id"]), "name": b["name"]} for b in brokers],
    }


@router.get("/conversations", response_model=ConversationListOut)
async def list_conversations(
    include_archived: bool = Query(default=False),
    current_user: CurrentUser = Depends(require_client),
):
    async with get_connection() as conn:
        company_id, broker_ids = await _resolve_scope(conn, current_user)
        convs = await svc.list_conversations(
            conn, user_id=current_user.id, company_id=company_id,
            broker_ids=broker_ids, include_archived=include_archived,
        )
        total = await svc.total_unread(
            conn, user_id=current_user.id, company_id=company_id, broker_ids=broker_ids,
        )
    return {"conversations": convs, "total_unread": total}


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_client),
):
    async with get_connection() as conn:
        company_id, broker_ids = await _resolve_scope(conn, current_user)
        if not broker_ids:
            raise HTTPException(status_code=400, detail="No broker is linked to your company")
        if body.broker_id is not None:
            if body.broker_id not in broker_ids:
                raise HTTPException(status_code=403, detail="Not linked to that broker")
            broker_id = body.broker_id
        elif len(broker_ids) == 1:
            broker_id = broker_ids[0]
        else:
            raise HTTPException(status_code=422, detail="broker_id is required (multiple brokers linked)")
        conv = await svc.create_conversation(
            conn, broker_id=broker_id, company_id=company_id,
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


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(require_client),
):
    async with get_connection() as conn:
        company_id, broker_ids = await _resolve_scope(conn, current_user)
        return await _load_conversation(conn, conversation_id, company_id, broker_ids, current_user.id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID,
    before: str | None = Query(default=None, description="ISO timestamp cursor"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(require_client),
):
    async with get_connection() as conn:
        company_id, broker_ids = await _resolve_scope(conn, current_user)
        await _load_conversation(conn, conversation_id, company_id, broker_ids, current_user.id)
        cursor = None
        if before:
            try:
                cursor = datetime.fromisoformat(before)
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid 'before' cursor")
        return await svc.list_messages(conn, conversation_id, before=cursor, limit=limit)


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    conversation_id: UUID,
    body: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_client),
):
    async with get_connection() as conn:
        company_id, broker_ids = await _resolve_scope(conn, current_user)
        conv = await _load_conversation(conn, conversation_id, company_id, broker_ids, current_user.id)
        msg, is_new = await svc.post_message(
            conn, conversation_id=conversation_id, sender_user_id=current_user.id,
            sender_side=SIDE, body=body.body, reference=body.reference,
            client_message_id=body.client_message_id,
        )
        if is_new:
            _schedule_fanout(background_tasks, conv, msg)
    return msg


@router.patch("/messages/{message_id}", response_model=MessageOut)
async def edit_message(
    message_id: UUID,
    body: MessageEdit,
    current_user: CurrentUser = Depends(require_client),
):
    async with get_connection() as conn:
        msg = await svc.edit_message(conn, message_id, current_user.id, body.body)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@router.delete("/messages/{message_id}", status_code=204)
async def delete_message(
    message_id: UUID,
    current_user: CurrentUser = Depends(require_client),
):
    async with get_connection() as conn:
        ok = await svc.delete_message(conn, message_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")


@router.put("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: UUID,
    body: MarkReadRequest,
    current_user: CurrentUser = Depends(require_client),
):
    async with get_connection() as conn:
        company_id, broker_ids = await _resolve_scope(conn, current_user)
        await _load_conversation(conn, conversation_id, company_id, broker_ids, current_user.id)
        await svc.mark_read(conn, conversation_id, current_user.id, body.last_read_message_id)
    return {"ok": True}


@router.post("/conversations/{conversation_id}/archive", response_model=ConversationOut)
async def set_archived(
    conversation_id: UUID,
    archived: bool = Query(default=True),
    current_user: CurrentUser = Depends(require_client),
):
    """Archive/unarchive from the company side.

    Status is a property of the shared thread, so the broker archiving one hid it
    from the company as well — with no company-side way back. Both sides get the
    same control rather than the company depending on the broker to undo it.
    """
    async with get_connection() as conn:
        company_id, broker_ids = await _resolve_scope(conn, current_user)
        await _load_conversation(conn, conversation_id, company_id, broker_ids, current_user.id)
        await svc.set_conversation_status(conn, conversation_id, "archived" if archived else "open")
        return await svc.get_conversation(conn, conversation_id, user_id=current_user.id)


@router.get("/unread-count")
async def unread_count(current_user: CurrentUser = Depends(require_client)):
    async with get_connection() as conn:
        company_id, broker_ids = await _resolve_scope(conn, current_user)
        total = await svc.total_unread(
            conn, user_id=current_user.id, company_id=company_id, broker_ids=broker_ids,
        )
    return {"unread": total}


def _schedule_fanout(background_tasks: BackgroundTasks, conv: dict, msg: dict) -> None:
    preview = svc.preview_text(msg["body"])
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
