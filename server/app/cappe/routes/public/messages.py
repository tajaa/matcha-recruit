"""Cappe public surface — messages (client side, token-gated)."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import CappeMessageCreate, CappePublicThread
from ...services.email import dashboard_url, send_cappe_message_email

router = APIRouter()


@router.get("/public/threads/{token}", response_model=CappePublicThread)
async def public_thread(token: str, request: Request):
    """A client reads their conversation via the unguessable thread token."""
    await check_rate_limit(client_ip(request), "cappe_thread", 30, 60)
    try:
        tok = UUID(token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    async with get_connection() as conn:
        thread = await conn.fetchrow(
            """SELECT t.id, t.subject, s.name AS site_name
               FROM cappe_threads t JOIN cappe_sites s ON s.id = t.site_id
               WHERE t.access_token = $1""",
            tok,
        )
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        await conn.execute("UPDATE cappe_threads SET client_unread = 0 WHERE id = $1", thread["id"])
        msgs = await conn.fetch(
            "SELECT id, thread_id, sender, body, created_at FROM cappe_messages "
            "WHERE thread_id = $1 ORDER BY created_at",
            thread["id"],
        )
    return {"site_name": thread["site_name"], "subject": thread["subject"], "messages": [dict(m) for m in msgs]}


@router.post("/public/threads/{token}/messages", status_code=status.HTTP_201_CREATED)
async def public_thread_reply(token: str, body: CappeMessageCreate, request: Request, background: BackgroundTasks):
    """A client replies to their conversation."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_thread_reply", 5, 60)
    await check_rate_limit(ip, "cappe_thread_reply_hr", 30, 3600)
    try:
        tok = UUID(token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    async with get_connection() as conn:
        thread = await conn.fetchrow(
            """SELECT t.id, t.site_id, t.client_name, s.name AS site_name, a.email AS owner_email,
                      a.name AS owner_name
               FROM cappe_threads t
               JOIN cappe_sites s ON s.id = t.site_id
               JOIN cappe_accounts a ON a.id = s.account_id
               WHERE t.access_token = $1""",
            tok,
        )
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO cappe_messages (thread_id, site_id, sender, body) VALUES ($1, $2, 'client', $3)",
                thread["id"], thread["site_id"], body.body,
            )
            await conn.execute(
                "UPDATE cappe_threads SET owner_unread = owner_unread + 1, status = 'open', "
                "last_message_at = NOW() WHERE id = $1", thread["id"],
            )
    background.add_task(
        send_cappe_message_email, thread["owner_email"], thread["owner_name"], thread["site_name"],
        body.body, dashboard_url(f"/sites/{thread['site_id']}/messages"), thread["client_name"] or "a client",
    )
    return {"status": "ok"}
