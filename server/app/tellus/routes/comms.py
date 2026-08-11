"""Tellus Comms — general consumer-to-business conversations.

Feedback DMs keep their legacy endpoints in ``dms.py``. This router provides
the named /comms surface and a unified inbox over both conversation kinds.
"""
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_tellus_account, require_verified_consumer
from ..models.tellus import (
    TellusAccount, TellusCommsStart, TellusDmAssign, TellusDmMessage,
    TellusDmSend, TellusDmThread, TellusFollowedBrand, TellusInboxToggle,
)
from ..services.comms_service import (
    get_thread_access, next_status, resolve_inbox_brand, thread_to_model,
)
from ..services.email import send_tellus_dm_email
from ..services.points_service import notify_account

router = APIRouter()


async def _notify_recipients(conn, thread, sender_role: str, body: str):
    """Return email jobs after inserting in-app notifications."""
    if sender_role == "consumer":
        ids = await conn.fetch(
            """SELECT account_id FROM tellus_brand_members
                WHERE brand_id = $1 AND can_manage_inbox = TRUE""", thread["brand_id"]
        )
        recipient_ids = {r["account_id"] for r in ids}
        owner_id = await conn.fetchval("SELECT owner_account_id FROM tellus_brands WHERE id = $1", thread["brand_id"])
        if owner_id:
            recipient_ids.add(owner_id)
        recipient_ids.discard(thread["consumer_account_id"])
        title, text = "New Comms question", "A customer sent a new question."
    else:
        recipient_ids = {thread["consumer_account_id"]}
        title, text = "New Comms reply", "A business replied to your question."
    for account_id in recipient_ids:
        await notify_account(
            conn, account_id, "dm_message", title, text,
            reference_type="dm_thread", reference_id=str(thread["id"]),
        )
    if not recipient_ids:
        return []
    rows = await conn.fetch(
        "SELECT id, email, display_name FROM tellus_accounts WHERE id = ANY($1::uuid[])",
        list(recipient_ids),
    )
    brand_name = await conn.fetchval("SELECT name FROM tellus_brands WHERE id = $1", thread["brand_id"])
    return [
        (r["email"], r["display_name"], brand_name or "A business", "/brand/messages" if sender_role == "consumer" else "/messages")
        for r in rows if r["email"]
    ]


async def _thread_response(conn, thread_id: UUID, account: TellusAccount):
    row, role = await get_thread_access(conn, thread_id, account)
    return thread_to_model(row, role), row, role


@router.get("/comms/inbox-brands")
async def list_inbox_brands(account: TellusAccount = Depends(require_tellus_account)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT b.id AS brand_id, b.name, b.slug, b.plan_status,
                      m.role, m.can_manage_inbox
                 FROM tellus_brand_members m
                 JOIN tellus_brands b ON b.id = m.brand_id
                WHERE m.account_id = $1 AND m.can_manage_inbox = TRUE
                ORDER BY b.name""", account.id,
        )
        if account.account_type == "brand" and account.brand_id:
            owner = await conn.fetchrow(
                "SELECT id AS brand_id, name, slug, plan_status FROM tellus_brands WHERE id = $1",
                account.brand_id,
            )
            if owner and not any(r["brand_id"] == owner["brand_id"] for r in rows):
                rows = list(rows) + [{**dict(owner), "role": "owner", "can_manage_inbox": True}]
    return [dict(r) for r in rows]


@router.get("/comms/following", response_model=list[TellusFollowedBrand])
async def list_followed_brands(account: TellusAccount = Depends(require_verified_consumer)):
    """Consumer's followed businesses, used as the Comms quick-start list."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT b.slug, b.name, b.logo_url, b.messaging_enabled, s.city, s.state
               FROM tellus_brand_follows f
               JOIN tellus_brands b ON b.id = f.brand_id
               LEFT JOIN LATERAL (SELECT city, state FROM tellus_stores
                                  WHERE brand_id = b.id ORDER BY created_at LIMIT 1) s ON TRUE
               WHERE f.consumer_account_id = $1 AND b.owner_account_id IS NOT NULL
               ORDER BY f.created_at DESC""",
            account.id,
        )
    return [TellusFollowedBrand(**dict(row)) for row in rows]


@router.post("/comms/brands/{slug}/threads", response_model=dict, status_code=status.HTTP_201_CREATED)
async def start_comms(
    slug: str, body: TellusCommsStart, background: BackgroundTasks,
    account: TellusAccount = Depends(require_verified_consumer),
):
    await check_rate_limit(str(account.id), "tellus_comms_new_thread_day", 10, 86400)
    await check_rate_limit(str(account.id), "tellus_comms_send", 30, 3600)
    email_jobs = []
    async with get_connection() as conn:
        async with conn.transaction():
            brand = await conn.fetchrow(
                "SELECT * FROM tellus_brands WHERE slug = $1 FOR UPDATE", slug
            )
            if brand is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
            if brand["owner_account_id"] == account.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot message your own business as a customer")
            manages = await conn.fetchval(
                "SELECT 1 FROM tellus_brand_members WHERE brand_id = $1 AND account_id = $2 AND can_manage_inbox = TRUE",
                brand["id"], account.id,
            )
            if manages:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot message a business inbox you manage")
            if not brand["owner_account_id"] or not brand["messaging_enabled"]:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "messaging_unavailable", "message": "This business is not accepting Comms messages."})
            await check_rate_limit(
                f"{account.id}:{brand['id']}", "tellus_comms_new_thread_brand_day", 3, 86400,
            )
            stores = await conn.fetch(
                "SELECT id FROM tellus_stores WHERE brand_id = $1 ORDER BY created_at", brand["id"]
            )
            store_ids = {r["id"] for r in stores}
            if body.store_id is not None and body.store_id not in store_ids:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
            if len(store_ids) > 1 and body.store_id is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Choose a store for this business")
            store_id = body.store_id or (next(iter(store_ids)) if store_ids else None)
            lock_key = f"comms:{brand['id']}:{account.id}:{store_id or 'brand'}"
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", lock_key)
            if store_id:
                thread = await conn.fetchrow(
                    """SELECT * FROM tellus_dm_threads
                       WHERE brand_id = $1 AND consumer_account_id = $2 AND store_id = $3
                         AND kind = 'general' AND status <> 'closed' FOR UPDATE""",
                    brand["id"], account.id, store_id,
                )
            else:
                thread = await conn.fetchrow(
                    """SELECT * FROM tellus_dm_threads
                       WHERE brand_id = $1 AND consumer_account_id = $2 AND store_id IS NULL
                         AND kind = 'general' AND status <> 'closed' FOR UPDATE""",
                    brand["id"], account.id,
                )
            if thread is None:
                thread = await conn.fetchrow(
                    """INSERT INTO tellus_dm_threads
                       (brand_id, consumer_account_id, kind, store_id, topic, status)
                       VALUES ($1, $2, 'general', $3, $4, 'waiting_brand') RETURNING *""",
                    brand["id"], account.id, store_id, body.topic,
                )
            message_id = body.client_message_id
            message = await conn.fetchrow(
                """INSERT INTO tellus_dm_messages
                   (thread_id, sender_role, sender_account_id, body, client_message_id)
                   VALUES ($1, 'consumer', $2, $3, $4)
                   ON CONFLICT (sender_account_id, client_message_id)
                   WHERE client_message_id IS NOT NULL DO NOTHING RETURNING *""",
                thread["id"], account.id, body.body, message_id,
            )
            if message is not None:
                await conn.execute(
                    "UPDATE tellus_dm_threads SET topic = $2, status = 'waiting_brand', last_message_at = NOW() WHERE id = $1",
                    thread["id"], body.topic,
                )
                thread = await conn.fetchrow("SELECT * FROM tellus_dm_threads WHERE id = $1", thread["id"])
                email_jobs = await _notify_recipients(conn, thread, "consumer", body.body)
            else:
                message = await conn.fetchrow(
                    "SELECT * FROM tellus_dm_messages WHERE thread_id = $1 AND sender_account_id = $2 AND client_message_id = $3",
                    thread["id"], account.id, message_id,
                )
                if message is None:
                    raise HTTPException(status_code=409, detail="client_message_id was already used")
        model, row, _ = await _thread_response(conn, thread["id"], account)
    for email, name, from_label, path in email_jobs:
        background.add_task(send_tellus_dm_email, email, name, from_label, path)
    return {"thread": model, "message": TellusDmMessage(**{**dict(message), "is_mine": True})}


@router.get("/comms/threads", response_model=list[TellusDmThread])
async def list_comms_threads(
    brand_id: Optional[UUID] = Query(None),
    kind: Optional[str] = Query(None, pattern="^(feedback|general)$"),
    thread_status: Optional[str] = Query(None, alias="status", pattern="^(waiting_brand|waiting_consumer|closed)$"),
    assigned: Optional[str] = Query(None, pattern="^(any|unassigned|mine)$"),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        role = "consumer"
        params: list = []
        clauses = []
        if brand_id is not None or account.account_type == "brand":
            brand, member = await resolve_inbox_brand(conn, account, brand_id)
            role = "brand"
            clauses.append(f"t.brand_id = ${len(params) + 1}"); params.append(brand["id"])
            if assigned == "unassigned": clauses.append("t.assigned_member_id IS NULL")
            elif assigned == "mine":
                member_id = member.get("id")
                if member_id is None: raise HTTPException(status_code=409, detail="Inbox membership is incomplete")
                clauses.append(f"t.assigned_member_id = ${len(params) + 1}"); params.append(member_id)
        else:
            if account.account_type != "consumer":
                raise HTTPException(status_code=400, detail="Specify brand_id")
            clauses.append(f"t.consumer_account_id = ${len(params) + 1}"); params.append(account.id)
        if kind:
            clauses.append(f"t.kind = ${len(params) + 1}"); params.append(kind)
        if thread_status:
            clauses.append(f"t.status = ${len(params) + 1}"); params.append(thread_status)
        where = " AND ".join(clauses)
        role_param = len(params) + 1
        limit_param = len(params) + 2
        offset_param = len(params) + 3
        rows = await conn.fetch(
            f"""SELECT t.*, b.name AS brand_name, r.title AS report_title,
                      r.report_number, r.review_state, r.publish_at,
                      ca.display_name AS consumer_display_name,
                      s.name AS store_name, s.city AS store_city,
                      am.account_id AS assigned_account_id,
                      aa.display_name AS assigned_member_name,
                      (SELECT COUNT(*) FROM tellus_dm_messages m
                       WHERE m.thread_id = t.id AND m.read_at IS NULL
                         AND m.sender_role <> ${role_param}) AS unread_count
                 FROM tellus_dm_threads t
                 JOIN tellus_brands b ON b.id = t.brand_id
                 LEFT JOIN tellus_reports r ON r.id = t.report_id
                 JOIN tellus_accounts ca ON ca.id = t.consumer_account_id
                 LEFT JOIN tellus_stores s ON s.id = t.store_id
                 LEFT JOIN tellus_brand_members am ON am.id = t.assigned_member_id
                 LEFT JOIN tellus_accounts aa ON aa.id = am.account_id
                WHERE {where}
                ORDER BY t.last_message_at DESC LIMIT ${limit_param} OFFSET ${offset_param}""",
            *params, role, limit, offset,
        )
    return [thread_to_model(dict(r), role) for r in rows]


@router.get("/comms/threads/{thread_id}/messages", response_model=list[TellusDmMessage])
async def get_comms_messages(
    thread_id: UUID, after: Optional[UUID] = None,
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        _, role = await get_thread_access(conn, thread_id, account)
        await conn.execute("UPDATE tellus_dm_messages SET read_at = NOW() WHERE thread_id = $1 AND sender_role <> $2 AND read_at IS NULL", thread_id, role)
        if after:
            anchor = await conn.fetchrow("SELECT created_at, id FROM tellus_dm_messages WHERE id = $1 AND thread_id = $2", after, thread_id)
            if anchor is None:
                raise HTTPException(status_code=404, detail="Message cursor not found")
            rows = await conn.fetch("SELECT * FROM tellus_dm_messages WHERE thread_id = $1 AND (created_at, id) > ($2, $3) ORDER BY created_at, id LIMIT 200", thread_id, anchor["created_at"], anchor["id"])
        else:
            rows = await conn.fetch("SELECT * FROM (SELECT * FROM tellus_dm_messages WHERE thread_id = $1 ORDER BY created_at DESC, id DESC LIMIT 200) x ORDER BY created_at, id", thread_id)
    return [TellusDmMessage(**{**dict(r), "is_mine": r["sender_role"] == role}) for r in rows]


@router.post("/comms/threads/{thread_id}/messages", response_model=TellusDmMessage)
async def send_comms_message(
    thread_id: UUID, body: TellusDmSend, background: BackgroundTasks,
    account: TellusAccount = Depends(require_tellus_account),
):
    await check_rate_limit(str(account.id), "tellus_comms_send_burst", 10, 60)
    await check_rate_limit(str(account.id), "tellus_comms_send", 30, 3600)
    email_jobs = []
    async with get_connection() as conn:
        async with conn.transaction():
            thread, role = await get_thread_access(conn, thread_id, account)
            if role == "consumer" and not await conn.fetchval(
                "SELECT 1 FROM tellus_accounts WHERE id = $1 AND email_verified_at IS NOT NULL", account.id,
            ):
                raise HTTPException(status_code=403, detail="Verify your email before using Comms.")
            locked = await conn.fetchrow("SELECT * FROM tellus_dm_threads WHERE id = $1 FOR UPDATE", thread_id)
            if locked["blocked_at"] is not None:
                raise HTTPException(status_code=403, detail="This conversation has been ended.")
            if locked["status"] == "closed":
                raise HTTPException(status_code=409, detail="This conversation is closed.")
            client_id = body.client_message_id or uuid4()
            row = await conn.fetchrow(
                """INSERT INTO tellus_dm_messages (thread_id, sender_role, sender_account_id, body, client_message_id)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (sender_account_id, client_message_id)
                   WHERE client_message_id IS NOT NULL DO NOTHING RETURNING *""",
                thread_id, role, account.id, body.body, client_id,
            )
            if row is not None:
                await conn.execute("UPDATE tellus_dm_threads SET status = $2, last_message_at = NOW(), first_brand_response_at = CASE WHEN $3 = 'brand' THEN COALESCE(first_brand_response_at, NOW()) ELSE first_brand_response_at END WHERE id = $1", thread_id, next_status(role), role)
                thread = await conn.fetchrow("SELECT * FROM tellus_dm_threads WHERE id = $1", thread_id)
                email_jobs = await _notify_recipients(conn, thread, role, body.body)
            else:
                row = await conn.fetchrow("SELECT * FROM tellus_dm_messages WHERE thread_id = $1 AND sender_account_id = $2 AND client_message_id = $3", thread_id, account.id, client_id)
                if row is None:
                    raise HTTPException(status_code=409, detail="client_message_id was already used")
    for email, name, from_label, path in email_jobs:
        background.add_task(send_tellus_dm_email, email, name, from_label, path)
    return TellusDmMessage(**{**dict(row), "is_mine": True})


@router.post("/comms/threads/{thread_id}/take", response_model=TellusDmThread)
async def take_comms_thread(thread_id: UUID, background: BackgroundTasks, account: TellusAccount = Depends(require_tellus_account)):
    async with get_connection() as conn:
        thread, role = await get_thread_access(conn, thread_id, account)
        if role != "brand": raise HTTPException(status_code=403, detail="Inbox access required")
        brand, member = await resolve_inbox_brand(conn, account, thread["brand_id"])
        member_id = member.get("id")
        if member_id is None: raise HTTPException(status_code=409, detail="Inbox membership is incomplete")
        row = await conn.fetchrow("UPDATE tellus_dm_threads SET assigned_member_id = $2 WHERE id = $1 AND status <> 'closed' AND (assigned_member_id IS NULL OR assigned_member_id = $2) RETURNING id", thread_id, member_id)
        if row is None: raise HTTPException(status_code=409, detail="Conversation is assigned to another agent")
        if thread.get("assigned_member_id") is None:
            await notify_account(
                conn, account.id, "dm_assignment", "Comms conversation assigned",
                "You took a conversation.", reference_type="dm_thread", reference_id=str(thread_id),
            )
        model, _, _ = await _thread_response(conn, thread_id, account)
    return model


@router.patch("/comms/threads/{thread_id}/assignment", response_model=TellusDmThread)
async def assign_comms_thread(
    thread_id: UUID, body: TellusDmAssign, background: BackgroundTasks,
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        thread, role = await get_thread_access(conn, thread_id, account)
        if role != "brand" or account.account_type != "brand":
            raise HTTPException(status_code=403, detail="Only the business owner can assign conversations")
        if account.brand_id != thread["brand_id"]:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if body.member_id is not None and body.member_id != thread.get("assigned_member_id"):
            ok = await conn.fetchval(
                "SELECT 1 FROM tellus_brand_members WHERE id = $1 AND brand_id = $2 AND can_manage_inbox = TRUE",
                body.member_id, thread["brand_id"],
            )
            if not ok:
                raise HTTPException(status_code=404, detail="Inbox member not found")
        row = await conn.fetchrow(
            "UPDATE tellus_dm_threads SET assigned_member_id = $2 WHERE id = $1 AND status <> 'closed' RETURNING id",
            thread_id, body.member_id,
        )
        if row is None:
            raise HTTPException(status_code=409, detail="Conversation is closed")
        if body.member_id is not None:
            recipient = await conn.fetchrow(
                "SELECT m.account_id, a.email, a.display_name FROM tellus_brand_members m JOIN tellus_accounts a ON a.id = m.account_id WHERE m.id = $1",
                body.member_id,
            )
            if recipient:
                await notify_account(
                    conn, recipient["account_id"], "dm_assignment", "Comms conversation assigned",
                    "A conversation was assigned to you.", reference_type="dm_thread", reference_id=str(thread_id),
                )
                if recipient["email"]:
                    brand_name = await conn.fetchval("SELECT name FROM tellus_brands WHERE id = $1", thread["brand_id"])
                    background.add_task(send_tellus_dm_email, recipient["email"], recipient["display_name"], brand_name or "A business", "/brand/messages")
        model, _, _ = await _thread_response(conn, thread_id, account)
    return model


@router.patch("/comms/team/{member_id}/inbox")
async def toggle_inbox_member(
    member_id: UUID, body: TellusInboxToggle,
    account: TellusAccount = Depends(require_tellus_account),
):
    if account.account_type != "brand" or account.brand_id is None:
        raise HTTPException(status_code=403, detail="Only the business owner can manage Comms access")
    async with get_connection() as conn:
        brand = await conn.fetchrow("SELECT * FROM tellus_brands WHERE id = $1 AND owner_account_id = $2", account.brand_id, account.id)
        if brand is None:
            raise HTTPException(status_code=404, detail="Business not found")
        if body.enabled and brand["plan_status"] != "active":
            raise HTTPException(status_code=402, detail="An active plan is required for inbox agents")
        row = await conn.fetchrow(
            "UPDATE tellus_brand_members SET can_manage_inbox = $3 WHERE id = $1 AND brand_id = $2 AND role <> 'owner' RETURNING id, can_manage_inbox",
            member_id, brand["id"], body.enabled,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Team member not found")
    return {"member_id": row["id"], "can_manage_inbox": row["can_manage_inbox"]}


@router.patch("/comms/brand/messaging")
async def toggle_brand_comms(
    body: TellusInboxToggle,
    account: TellusAccount = Depends(require_tellus_account),
):
    if account.account_type != "brand" or account.brand_id is None:
        raise HTTPException(status_code=403, detail="Only a business owner can manage Comms")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "UPDATE tellus_brands SET messaging_enabled = $2 WHERE id = $1 AND owner_account_id = $3 RETURNING messaging_enabled",
            account.brand_id, body.enabled, account.id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Business not found")
    return {"messaging_enabled": row["messaging_enabled"]}


@router.post("/comms/threads/{thread_id}/close", response_model=TellusDmThread)
async def close_comms_thread(thread_id: UUID, account: TellusAccount = Depends(require_tellus_account)):
    async with get_connection() as conn:
        _, role = await get_thread_access(conn, thread_id, account)
        row = await conn.fetchrow("UPDATE tellus_dm_threads SET status = 'closed', closed_at = NOW(), closed_by_account_id = $2 WHERE id = $1 AND status <> 'closed' RETURNING id", thread_id, account.id)
        if row is None: raise HTTPException(status_code=409, detail="Conversation is already closed")
        model, _, _ = await _thread_response(conn, thread_id, account)
    return model


@router.post("/comms/threads/{thread_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def block_comms_thread(thread_id: UUID, account: TellusAccount = Depends(require_verified_consumer)):
    async with get_connection() as conn:
        thread, role = await get_thread_access(conn, thread_id, account)
        if role != "consumer": raise HTTPException(status_code=403, detail="Consumer access required")
        result = await conn.execute("UPDATE tellus_dm_threads SET blocked_at = COALESCE(blocked_at, NOW()) WHERE id = $1 AND consumer_account_id = $2", thread_id, account.id)
        if result == "UPDATE 0": raise HTTPException(status_code=404, detail="Conversation not found")


@router.delete("/comms/threads/{thread_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_comms_thread(thread_id: UUID, account: TellusAccount = Depends(require_verified_consumer)):
    async with get_connection() as conn:
        result = await conn.execute("UPDATE tellus_dm_threads SET blocked_at = NULL WHERE id = $1 AND consumer_account_id = $2", thread_id, account.id)
        if result == "UPDATE 0": raise HTTPException(status_code=404, detail="Conversation not found")
