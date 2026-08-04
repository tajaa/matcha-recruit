"""Tell-Us brand <-> reviewer DMs.

One thread per report (a brand addresses a bad experience directly with the
person who reported it). The brand opens the thread; the consumer replies or
blocks. Brand-side views only ever see the consumer's display_name — never
their email — mirroring the redaction already enforced on TellusReport.

Mixed roles on one router (like rewards.py's shared notification endpoints) —
each endpoint declares its own dependency rather than splitting into two
near-identical files.
"""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_consumer, require_paid_brand, require_tellus_account
from ..models.tellus import TellusAccount, TellusDmMessage, TellusDmSend, TellusDmThread
from ..services.email import send_tellus_dm_email
from ..services.points_service import _notify
from ._shared import get_owned_report

router = APIRouter()


def _thread_to_model(row) -> TellusDmThread:
    return TellusDmThread(
        id=row["id"],
        report_id=row["report_id"],
        counterparty_name=row["counterparty_name"],
        report_title=row["report_title"],
        report_number=row["report_number"],
        blocked=row["blocked_at"] is not None,
        unread_count=row["unread_count"],
        last_message_at=row["last_message_at"],
        created_at=row["created_at"],
    )


async def _get_thread_for_account(conn, thread_id: UUID, account: TellusAccount) -> tuple[dict, str]:
    """Ownership-scoped thread fetch — 404s rather than leaking existence to
    the wrong party. Returns the raw row plus the caller's role."""
    if account.account_type == "brand":
        row = await conn.fetchrow(
            "SELECT * FROM tellus_dm_threads WHERE id = $1 AND brand_id = $2",
            thread_id, account.brand_id,
        )
        role = "brand"
    else:
        row = await conn.fetchrow(
            "SELECT * FROM tellus_dm_threads WHERE id = $1 AND consumer_account_id = $2",
            thread_id, account.id,
        )
        role = "consumer"
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return dict(row), role


@router.post("/feedback/{report_id}/dm", response_model=TellusDmThread)
async def open_thread(
    report_id: UUID, body: TellusDmSend, background: BackgroundTasks,
    account: TellusAccount = Depends(require_paid_brand),
):
    """Brand opens (or reopens) the one thread for this report, sending its
    first message in the same call — an empty thread with nobody's opening
    line isn't a meaningful state to create."""
    await check_rate_limit(str(account.id), "tellus_dm_send", 30, 3600)

    async with get_connection() as conn:
        async with conn.transaction():
            report = await get_owned_report(conn, report_id, account.brand_id)
            if report["reporter_account_id"] is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This reporter is anonymous — there's no one to message.",
                )
            if report["review_state"] is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="DMs are only available for public reviews.",
                )
            # ON CONFLICT makes reopening idempotent: a brand messaging again
            # about the same report reuses the existing thread instead of
            # erroring on the UNIQUE(report_id).
            thread = await conn.fetchrow(
                """INSERT INTO tellus_dm_threads (report_id, brand_id, consumer_account_id)
                       VALUES ($1, $2, $3)
                   ON CONFLICT (report_id) DO UPDATE SET last_message_at = tellus_dm_threads.last_message_at
                   RETURNING *""",
                report_id, account.brand_id, report["reporter_account_id"],
            )
            if thread["blocked_at"] is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This reviewer has ended the conversation.",
                )

            await conn.execute(
                """INSERT INTO tellus_dm_messages (thread_id, sender_role, sender_account_id, body)
                   VALUES ($1, 'brand', $2, $3)""",
                thread["id"], account.id, body.body,
            )
            await conn.execute(
                "UPDATE tellus_dm_threads SET last_message_at = NOW() WHERE id = $1", thread["id"],
            )
            await _notify(
                conn, report["reporter_account_id"], "dm_message", "New message about your feedback",
                "A brand sent you a message.", reference_type="dm_thread", reference_id=str(thread["id"]),
            )

            consumer = await conn.fetchrow(
                "SELECT email, display_name FROM tellus_accounts WHERE id = $1",
                report["reporter_account_id"],
            )
            brand = await conn.fetchrow("SELECT name FROM tellus_brands WHERE id = $1", account.brand_id)

        row = await conn.fetchrow(
            """SELECT t.id, t.report_id, t.blocked_at, t.last_message_at, t.created_at,
                      COALESCE(a.display_name, 'Reviewer') AS counterparty_name,
                      r.title AS report_title, r.report_number,
                      0 AS unread_count
               FROM tellus_dm_threads t
               JOIN tellus_reports r ON r.id = t.report_id
               JOIN tellus_accounts a ON a.id = t.consumer_account_id
               WHERE t.id = $1""",
            thread["id"],
        )

    if consumer:
        background.add_task(send_tellus_dm_email, consumer["email"], consumer["display_name"], brand["name"] if brand else "A brand")

    return _thread_to_model(row)


@router.get("/dm/threads", response_model=list[TellusDmThread])
async def list_threads(account: TellusAccount = Depends(require_tellus_account)):
    async with get_connection() as conn:
        if account.account_type == "brand":
            rows = await conn.fetch(
                """SELECT t.id, t.report_id, t.blocked_at, t.last_message_at, t.created_at,
                          COALESCE(a.display_name, 'Reviewer') AS counterparty_name,
                          r.title AS report_title, r.report_number,
                          (SELECT COUNT(*) FROM tellus_dm_messages m
                             WHERE m.thread_id = t.id AND m.read_at IS NULL AND m.sender_role <> 'brand') AS unread_count
                   FROM tellus_dm_threads t
                   JOIN tellus_reports r ON r.id = t.report_id
                   JOIN tellus_accounts a ON a.id = t.consumer_account_id
                   WHERE t.brand_id = $1
                   ORDER BY t.last_message_at DESC""",
                account.brand_id,
            )
            role = "brand"
        else:
            rows = await conn.fetch(
                """SELECT t.id, t.report_id, t.blocked_at, t.last_message_at, t.created_at,
                          b.name AS counterparty_name,
                          r.title AS report_title, r.report_number,
                          (SELECT COUNT(*) FROM tellus_dm_messages m
                             WHERE m.thread_id = t.id AND m.read_at IS NULL AND m.sender_role <> 'consumer') AS unread_count
                   FROM tellus_dm_threads t
                   JOIN tellus_reports r ON r.id = t.report_id
                   JOIN tellus_brands b ON b.id = t.brand_id
                   WHERE t.consumer_account_id = $1
                   ORDER BY t.last_message_at DESC""",
                account.id,
            )
            role = "consumer"
    return [_thread_to_model(r) for r in rows]


@router.get("/dm/threads/{thread_id}/messages", response_model=list[TellusDmMessage])
async def get_messages(thread_id: UUID, account: TellusAccount = Depends(require_tellus_account)):
    async with get_connection() as conn:
        _, my_role = await _get_thread_for_account(conn, thread_id, account)
        # Read-on-fetch: the OTHER party's unread messages are marked read the
        # moment I open this thread.
        await conn.execute(
            "UPDATE tellus_dm_messages SET read_at = NOW() "
            "WHERE thread_id = $1 AND sender_role <> $2 AND read_at IS NULL",
            thread_id, my_role,
        )
        rows = await conn.fetch(
            """SELECT * FROM (
                   SELECT * FROM tellus_dm_messages WHERE thread_id = $1
                   ORDER BY created_at DESC LIMIT 200
               ) recent ORDER BY created_at ASC""",
            thread_id,
        )
    return [
        TellusDmMessage(
            id=r["id"], thread_id=r["thread_id"], sender_role=r["sender_role"],
            body=r["body"], created_at=r["created_at"], is_mine=(r["sender_role"] == my_role),
        )
        for r in rows
    ]


@router.post("/dm/threads/{thread_id}/messages", response_model=TellusDmMessage)
async def send_message(
    thread_id: UUID, body: TellusDmSend, background: BackgroundTasks,
    account: TellusAccount = Depends(require_tellus_account),
):
    await check_rate_limit(str(account.id), "tellus_dm_send_burst", 10, 60)
    await check_rate_limit(str(account.id), "tellus_dm_send", 30, 3600)

    async with get_connection() as conn:
        async with conn.transaction():
            thread, my_role = await _get_thread_for_account(conn, thread_id, account)
            if thread["blocked_at"] is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This conversation has been ended.",
                )
            row = await conn.fetchrow(
                """INSERT INTO tellus_dm_messages (thread_id, sender_role, sender_account_id, body)
                       VALUES ($1, $2, $3, $4) RETURNING *""",
                thread_id, my_role, account.id, body.body,
            )
            await conn.execute(
                "UPDATE tellus_dm_threads SET last_message_at = NOW() WHERE id = $1", thread_id,
            )

            # Notifications key off tellus_accounts: the consumer side is
            # already an account id, but the brand side needs its owner's.
            if my_role == "consumer":
                counterparty_id = await conn.fetchval(
                    "SELECT owner_account_id FROM tellus_brands WHERE id = $1", thread["brand_id"]
                )
            else:
                counterparty_id = thread["consumer_account_id"]
            await _notify(
                conn, counterparty_id, "dm_message", "New message about a review",
                "You have a new message.", reference_type="dm_thread", reference_id=str(thread_id),
            )

            recipient_email = None
            recipient_name = None
            from_label = "A brand"
            if my_role == "brand":
                consumer = await conn.fetchrow(
                    "SELECT email, display_name FROM tellus_accounts WHERE id = $1",
                    thread["consumer_account_id"],
                )
                if consumer:
                    recipient_email, recipient_name = consumer["email"], consumer["display_name"]
                brand = await conn.fetchrow("SELECT name FROM tellus_brands WHERE id = $1", thread["brand_id"])
                from_label = brand["name"] if brand else "A brand"
            else:
                owner = await conn.fetchrow(
                    """SELECT a.email, a.display_name FROM tellus_accounts a
                       JOIN tellus_brands b ON b.owner_account_id = a.id
                       WHERE b.id = $1""",
                    thread["brand_id"],
                )
                if owner:
                    recipient_email, recipient_name = owner["email"], owner["display_name"]
                reviewer = await conn.fetchrow(
                    "SELECT display_name FROM tellus_accounts WHERE id = $1", account.id
                )
                from_label = (reviewer["display_name"] if reviewer else None) or "A reviewer"

    if recipient_email:
        background.add_task(send_tellus_dm_email, recipient_email, recipient_name, from_label)

    return TellusDmMessage(
        id=row["id"], thread_id=row["thread_id"], sender_role=row["sender_role"],
        body=row["body"], created_at=row["created_at"], is_mine=True,
    )


@router.post("/dm/threads/{thread_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def block_thread(thread_id: UUID, account: TellusAccount = Depends(require_consumer)):
    """Silent by design — no brand notification when a consumer blocks."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE tellus_dm_threads SET blocked_at = COALESCE(blocked_at, NOW()) "
            "WHERE id = $1 AND consumer_account_id = $2",
            thread_id, account.id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.delete("/dm/threads/{thread_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_thread(thread_id: UUID, account: TellusAccount = Depends(require_consumer)):
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE tellus_dm_threads SET blocked_at = NULL WHERE id = $1 AND consumer_account_id = $2",
            thread_id, account.id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
