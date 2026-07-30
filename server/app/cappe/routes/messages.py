"""Cappe messages — owner side of the creator↔client inbox.

Threads group messages with one client (by email). The creator lists threads,
opens one (which marks it read), starts new conversations, and replies. Each
owner message emails the client a token link to the public thread page
(public read/reply lives in public.py). Client directory lives in clients.py.
"""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeMessage,
    CappeMessageCreate,
    CappeThread,
    CappeThreadCreate,
    CappeThreadDetail,
)
from ..services.email import send_cappe_message_email, thread_url
from ._shared import get_owned_site

router = APIRouter()

_THREAD_COLS = (
    "id, site_id, client_email, client_name, subject, status, booking_id, order_id, "
    "owner_unread, last_message_at, created_at"
)


async def _owner_msg_request_ok(account_id) -> None:
    """Per-account budget on the request itself — an owner blasting this
    endpoint is their own account's abuse, so it 429s the request (unlike the
    per-recipient budget below, which only ever skips the email)."""
    await check_rate_limit(str(account_id), "cappe_owner_msg", 60, 3600)


async def _recipient_send_ok(email: str) -> bool:
    """Per-recipient send budget. Never blocks the thread/message write —
    only the email — so a chatty owner still gets their message recorded even
    past this cap; mirrors services/commerce.check_recipient_send_ok."""
    try:
        await check_rate_limit(email.lower(), "cappe_owner_msg_to", 20, 3600)
        return True
    except HTTPException:
        return False


async def _notify_recipient(to_email, to_name, site_name, body, link, from_label) -> None:
    """Background-task entry point: gate on the recipient's own send budget
    before ever calling the email service."""
    if await _recipient_send_ok(to_email):
        await send_cappe_message_email(to_email, to_name, site_name, body, link, from_label)


@router.get("/sites/{site_id}/threads", response_model=list[CappeThread])
async def list_threads(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"""SELECT {_THREAD_COLS},
                   (SELECT body FROM cappe_messages m WHERE m.thread_id = t.id
                    ORDER BY created_at DESC LIMIT 1) AS last_snippet
                FROM cappe_threads t
                WHERE site_id = $1 ORDER BY last_message_at DESC""",
            site_id,
        )
    return [dict(r) for r in rows]


@router.get("/sites/{site_id}/threads/{thread_id}", response_model=CappeThreadDetail)
async def get_thread(
    site_id: UUID, thread_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        thread = await conn.fetchrow(
            f"SELECT {_THREAD_COLS}, access_token FROM cappe_threads WHERE id = $1 AND site_id = $2",
            thread_id, site_id,
        )
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        # Opening the thread clears the owner's unread count.
        await conn.execute("UPDATE cappe_threads SET owner_unread = 0 WHERE id = $1", thread_id)
        msgs = await conn.fetch(
            "SELECT id, thread_id, sender, body, created_at FROM cappe_messages "
            "WHERE thread_id = $1 ORDER BY created_at",
            thread_id,
        )
    d = dict(thread)
    d["owner_unread"] = 0
    d["messages"] = [dict(m) for m in msgs]
    return d


@router.post("/sites/{site_id}/threads", response_model=CappeThreadDetail, status_code=status.HTTP_201_CREATED)
async def start_thread(
    site_id: UUID, body: CappeThreadCreate, background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Start (or continue) a conversation with a client and send the first
    message. Reuses an existing open thread for the same client email."""
    await _owner_msg_request_ok(account.id)
    email = body.client_email.strip().lower()
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            thread = await conn.fetchrow(
                "SELECT id FROM cappe_threads WHERE site_id = $1 AND lower(client_email) = $2 AND status = 'open'",
                site_id, email,
            )
            if thread is None:
                thread = await conn.fetchrow(
                    """INSERT INTO cappe_threads
                           (site_id, client_email, client_name, subject, booking_id, order_id,
                            client_unread, last_message_at)
                       VALUES ($1, $2, $3, $4, $5, $6, 1, NOW())
                       RETURNING id""",
                    site_id, email, body.client_name, body.subject, body.booking_id, body.order_id,
                )
            else:
                await conn.execute(
                    "UPDATE cappe_threads SET client_unread = client_unread + 1, last_message_at = NOW() "
                    "WHERE id = $1", thread["id"],
                )
            await conn.execute(
                "INSERT INTO cappe_messages (thread_id, site_id, sender, body) VALUES ($1, $2, 'owner', $3)",
                thread["id"], site_id, body.body,
            )
            full = await conn.fetchrow(
                f"SELECT {_THREAD_COLS}, access_token FROM cappe_threads WHERE id = $1", thread["id"],
            )
            msgs = await conn.fetch(
                "SELECT id, thread_id, sender, body, created_at FROM cappe_messages "
                "WHERE thread_id = $1 ORDER BY created_at", thread["id"],
            )
    background.add_task(
        _notify_recipient, email, body.client_name, site["name"], body.body,
        thread_url(full["access_token"]), site["name"],
    )
    d = dict(full)
    d["messages"] = [dict(m) for m in msgs]
    return d


@router.post("/sites/{site_id}/threads/{thread_id}/messages", response_model=CappeMessage, status_code=status.HTTP_201_CREATED)
async def reply_thread(
    site_id: UUID, thread_id: UUID, body: CappeMessageCreate, background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    await _owner_msg_request_ok(account.id)
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        thread = await conn.fetchrow(
            "SELECT id, client_email, client_name, access_token FROM cappe_threads "
            "WHERE id = $1 AND site_id = $2", thread_id, site_id,
        )
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        async with conn.transaction():
            msg = await conn.fetchrow(
                "INSERT INTO cappe_messages (thread_id, site_id, sender, body) "
                "VALUES ($1, $2, 'owner', $3) RETURNING id, thread_id, sender, body, created_at",
                thread_id, site_id, body.body,
            )
            await conn.execute(
                "UPDATE cappe_threads SET client_unread = client_unread + 1, status = 'open', "
                "last_message_at = NOW() WHERE id = $1", thread_id,
            )
    background.add_task(
        _notify_recipient, thread["client_email"], thread["client_name"], site["name"],
        body.body, thread_url(thread["access_token"]), site["name"],
    )
    return dict(msg)


@router.post("/sites/{site_id}/threads/{thread_id}/close", response_model=CappeThread)
async def close_thread(
    site_id: UUID, thread_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"UPDATE cappe_threads SET status = 'closed' WHERE id = $1 AND site_id = $2 RETURNING {_THREAD_COLS}",
            thread_id, site_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return dict(row)
