"""Merlin conversation persistence (tables from migration zzzzcappe22).

Merlin was stateless until now: the transcript lived in the browser and died
with the tab. This module owns the two tables that back it — a page can hold
several named conversations, each an ordered list of user/assistant messages.

What is persisted is the CONVERSATION, not the page. Client-state-is-truth is
unchanged: ops still round-trip to the editor and nothing here writes
`cappe_pages`/`cappe_sites`.

Every read is account-scoped. `get_owned_conversation` is the one gate — it
joins through to `account_id` and 404s (never 403s) on a foreign id, matching
`get_owned_site`'s missing-vs-forbidden indistinguishability.
"""
import json
import logging
from typing import Any, Optional
from uuid import UUID

from ..routes._shared import loads_list

logger = logging.getLogger(__name__)

# Turns replayed into the prompt. Mirrors _MAX_HISTORY_TURNS in merlin.py — the
# transcript can be long now that it persists, but the prompt window can't grow
# with it.
HISTORY_TURNS = 10
# Hard ceiling on what `get_conversation` returns to the panel. A conversation
# that outgrows this is still usable; the panel just shows the recent tail.
MAX_MESSAGES_RETURNED = 200
_TITLE_MAX = 120


def title_from_message(message: str) -> str:
    """Derive a conversation title from its opening message.

    Trimmed to a single line so a pasted multi-line brief doesn't become a
    120-char title with newlines in it.
    """
    text = " ".join((message or "").split()).strip()
    if not text:
        return "New conversation"
    return text[:60] if len(text) > 60 else text


async def list_conversations(conn, page_id: UUID, account_id: UUID) -> list[dict[str, Any]]:
    """A page's conversations, most-recently-used first."""
    rows = await conn.fetch(
        """
        SELECT id, title, created_at, updated_at
        FROM cappe_merlin_conversations
        WHERE page_id = $1 AND account_id = $2
        ORDER BY updated_at DESC
        """,
        page_id,
        account_id,
    )
    return [dict(r) for r in rows]


async def get_owned_conversation(conn, conversation_id: UUID, account_id: UUID) -> dict[str, Any]:
    """Fetch a conversation row or raise 404 — the ownership gate for every
    conversation-addressed route. Imported lazily-safe (HTTPException here
    rather than in the route) so no caller can forget the check."""
    from fastapi import HTTPException, status

    row = await conn.fetchrow(
        """
        SELECT id, account_id, site_id, page_id, title, created_at, updated_at
        FROM cappe_merlin_conversations
        WHERE id = $1 AND account_id = $2
        """,
        conversation_id,
        account_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return dict(row)


async def create_conversation(
    conn, *, account_id: UUID, site_id: UUID, page_id: UUID, title: Optional[str] = None
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO cappe_merlin_conversations (account_id, site_id, page_id, title)
        VALUES ($1, $2, $3, $4)
        RETURNING id, title, created_at, updated_at
        """,
        account_id,
        site_id,
        page_id,
        (title or "New conversation")[:_TITLE_MAX],
    )
    return dict(row)


async def rename_conversation(conn, conversation_id: UUID, title: str) -> None:
    await conn.execute(
        "UPDATE cappe_merlin_conversations SET title = $2, updated_at = NOW() WHERE id = $1",
        conversation_id,
        title[:_TITLE_MAX],
    )


async def delete_conversation(conn, conversation_id: UUID) -> None:
    # Messages cascade (FK ON DELETE CASCADE).
    await conn.execute("DELETE FROM cappe_merlin_conversations WHERE id = $1", conversation_id)


async def get_messages(conn, conversation_id: UUID) -> list[dict[str, Any]]:
    """The conversation's messages oldest-first, capped at the recent tail.

    The ORDER BY/LIMIT dance selects the LAST N rows then re-sorts them
    ascending — a plain `ORDER BY created_at LIMIT n` would return the oldest
    messages, which is the opposite of what a chat panel wants.
    """
    rows = await conn.fetch(
        """
        SELECT * FROM (
            SELECT id, role, content, results, steps, attachments, tier, created_at
            FROM cappe_merlin_messages
            WHERE conversation_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
        ) recent
        ORDER BY created_at ASC, id ASC
        """,
        conversation_id,
        MAX_MESSAGES_RETURNED,
    )
    out = []
    for r in rows:
        m = dict(r)
        # JSONB columns come back as text (no global codec) and are nullable
        # here — an absent trace must stay None, not become [].
        for key in ("results", "steps", "attachments"):
            m[key] = loads_list(m[key]) if m[key] is not None else None
        out.append(m)
    return out


async def load_history(conn, conversation_id: UUID) -> list[dict[str, Any]]:
    """The prompt-shaped transcript tail: `[{role, content, ops_summary}]`,
    matching what the client used to resend. `ops_summary` is rebuilt from the
    stored result chips so the model still sees what each past turn changed."""
    rows = await conn.fetch(
        """
        SELECT * FROM (
            SELECT role, content, results, created_at, id
            FROM cappe_merlin_messages
            WHERE conversation_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
        ) recent
        ORDER BY created_at ASC, id ASC
        """,
        conversation_id,
        HISTORY_TURNS,
    )
    history: list[dict[str, Any]] = []
    for r in rows:
        turn: dict[str, Any] = {"role": r["role"], "content": r["content"] or ""}
        results = loads_list(r["results"]) if r["results"] is not None else []
        summaries = [
            str(item.get("summary"))
            for item in results
            if isinstance(item, dict) and item.get("summary")
        ]
        if summaries:
            turn["ops_summary"] = "; ".join(summaries)
        history.append(turn)
    return history


async def add_message(
    conn,
    conversation_id: UUID,
    *,
    role: str,
    content: str,
    results: Optional[list[dict[str, Any]]] = None,
    steps: Optional[list[dict[str, Any]]] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
    tier: Optional[str] = None,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO cappe_merlin_messages
            (conversation_id, role, content, results, steps, attachments, tier)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, role, content, results, steps, attachments, tier, created_at
        """,
        conversation_id,
        role,
        content or "",
        json.dumps(results) if results is not None else None,
        json.dumps(steps) if steps is not None else None,
        json.dumps(attachments) if attachments is not None else None,
        tier,
    )
    await conn.execute(
        "UPDATE cappe_merlin_conversations SET updated_at = NOW() WHERE id = $1",
        conversation_id,
    )
    m = dict(row)
    for key in ("results", "steps", "attachments"):
        m[key] = loads_list(m[key]) if m[key] is not None else None
    return m
