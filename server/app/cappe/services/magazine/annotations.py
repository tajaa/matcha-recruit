"""Account-private, immutable annotations. PUT retries reuse a client UUID.

Quotes keep text and context, never HTML. Re-anchoring is a reader concern:
when a publisher changes words, the saved quote survives without guessing at
another passage. Every operation rechecks the live story and paid access.
"""
import json
from uuid import UUID

from fastapi import HTTPException

from app.cappe.models.reader import ReaderAnnotationCreate
from app.cappe.services.magazine import reader, shelf
from app.cappe.services.magazine.access import has_paid_access

LIMIT = 250


async def readable_post(conn, account_id: UUID, slug: str, story_slug: str) -> UUID:
    email = await shelf.confirmed_email(conn, account_id)
    site, _ = await shelf.published_magazine(conn, slug)
    post = await reader.live_story(conn, site["id"], slug=story_slug)
    if not post:
        raise HTTPException(404, "Story not found")
    if post.get("access") == "paid":
        shopper = await shelf.shopper_for(conn, site["id"], email)
        if not shopper or not await has_paid_access(conn, site["id"], shopper["id"]):
            raise HTTPException(403, "Subscribe to save and read annotations on this story")
    return post["id"]


def annotation(row) -> dict:
    body = row["body"]
    return {**(json.loads(body) if isinstance(body, str) else body), "id": str(row["id"])}


async def listing(conn, account_id: UUID, post_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, body FROM cappe_reader_annotations WHERE account_id = $1 AND post_id = $2 "
        "ORDER BY created_at, id LIMIT $3", account_id, post_id, LIMIT,
    )
    return [annotation(row) for row in rows]


async def save(conn, account_id: UUID, post_id: UUID, annotation_id: UUID,
               body: ReaderAnnotationCreate) -> dict:
    async with conn.transaction():
        # Serialize cap checks across tabs. No network work in the transaction.
        await conn.fetchval("SELECT id FROM cappe_accounts WHERE id = $1 FOR UPDATE", account_id)
        existing = await conn.fetchrow(
            "SELECT id, body FROM cappe_reader_annotations "
            "WHERE account_id = $1 AND post_id = $2 AND id = $3", account_id, post_id, annotation_id,
        )
        if existing:
            return annotation(existing)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM cappe_reader_annotations WHERE account_id = $1 AND post_id = $2",
            account_id, post_id,
        )
        if count >= LIMIT:
            raise HTTPException(409, f"You have {LIMIT} annotations on this story. Delete one to add another.")
        row = await conn.fetchrow(
            "INSERT INTO cappe_reader_annotations (account_id, post_id, id, body) "
            "VALUES ($1, $2, $3, $4::jsonb) RETURNING id, body",
            account_id, post_id, annotation_id, json.dumps(body.model_dump(), ensure_ascii=True),
        )
        return annotation(row)


async def remove(conn, account_id: UUID, post_id: UUID, annotation_id: UUID) -> None:
    await conn.execute(
        "DELETE FROM cappe_reader_annotations WHERE account_id = $1 AND post_id = $2 AND id = $3",
        account_id, post_id, annotation_id,
    )
