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

from ..common import loads_list

logger = logging.getLogger(__name__)

# MESSAGES (not turns — a turn is a user+assistant pair) replayed into the
# prompt. Mirrors _MAX_HISTORY_MESSAGES in merlin/turn.py / merlin/agent.py — the
# transcript can be long now that it persists, but the prompt window can't
# grow with it. Was named HISTORY_TURNS at 10 (5 actual exchanges) while the
# two prompt-builders' own "_MAX_HISTORY_TURNS" slice was also 10 messages —
# same number, same wrong unit, so the slice looked like a second guard but
# was a no-op against this query's own LIMIT. 20 messages ≈ the 10 exchanges
# the naming always intended.
HISTORY_MESSAGES = 20
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
    """A page's conversations, most-recently-used first.

    `kind` is not filtered on here — it doesn't need to be. Setup-kind rows
    always carry `page_id IS NULL` (enforced by `ck_cappe_merlin_convo_scope`),
    so `WHERE page_id = $1` already excludes them from every page's list."""
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


async def list_site_setup_conversations(conn, site_id: UUID, account_id: UUID) -> list[dict[str, Any]]:
    """A site's setup-concierge conversations, most-recently-used first."""
    rows = await conn.fetch(
        """
        SELECT id, title, created_at, updated_at
        FROM cappe_merlin_conversations
        WHERE site_id = $1 AND account_id = $2 AND kind = 'setup'
        ORDER BY updated_at DESC
        """,
        site_id,
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
        SELECT id, account_id, site_id, page_id, kind, staged_actions, title, created_at, updated_at
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
    d = dict(row)
    d["staged_actions"] = loads_list(d["staged_actions"]) if d["staged_actions"] is not None else None
    return d


async def create_conversation(
    conn,
    *,
    account_id: UUID,
    site_id: UUID,
    page_id: Optional[UUID],
    kind: str = "page",
    title: Optional[str] = None,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO cappe_merlin_conversations (account_id, site_id, page_id, kind, title)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, title, created_at, updated_at
        """,
        account_id,
        site_id,
        page_id,
        kind,
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
            SELECT id, role, content, results, steps, attachments, ops, tier, created_at
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
        for key in ("results", "steps", "attachments", "ops"):
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
        HISTORY_MESSAGES,
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
    ops: Optional[list[dict[str, Any]]] = None,
    tier: Optional[str] = None,
) -> dict[str, Any]:
    """`ops` (migration zzzzcappe24) is the validated op log for an ASSISTANT
    message — what the client would apply if it never got the chance to. It
    is what makes an agent turn recoverable after a disconnect: the route
    persists it on the message even when the SSE stream never delivered a
    `result` frame, and a reopened conversation with `ops` set but no
    `results` yet is a turn the panel can offer to apply retroactively."""
    row = await conn.fetchrow(
        """
        INSERT INTO cappe_merlin_messages
            (conversation_id, role, content, results, steps, attachments, ops, tier)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, role, content, results, steps, attachments, ops, tier, created_at
        """,
        conversation_id,
        role,
        content or "",
        json.dumps(results) if results is not None else None,
        json.dumps(steps) if steps is not None else None,
        json.dumps(attachments) if attachments is not None else None,
        json.dumps(ops) if ops is not None else None,
        tier,
    )
    await conn.execute(
        "UPDATE cappe_merlin_conversations SET updated_at = NOW() WHERE id = $1",
        conversation_id,
    )
    m = dict(row)
    for key in ("results", "steps", "attachments", "ops"):
        m[key] = loads_list(m[key]) if m[key] is not None else None
    return m


# Cap on PENDING (status='proposed') staged actions per setup conversation.
# A concierge chat that never gets confirmed shouldn't grow this column
# without bound — the oldest proposed entry is pruned, not the newest, since
# the user is more likely to be about to act on something just staged.
MAX_PENDING_STAGED_ACTIONS = 10

# Cap on the TOTAL entry count (any status) per conversation. Without this,
# executed/dismissed/blocked entries — never touched by the pending cap above
# — accumulate in the JSONB column forever: re-serialized on every mutate,
# re-decoded on every setup request, all rendered by the panel. Pruned oldest
# settled (non-'proposed') first, applied after the pending prune, so a
# 'proposed' entry is never dropped to make room for a settled one.
MAX_STAGED_ACTIONS = 40


async def lock_conversation_actions(conn, conversation_id: UUID) -> list[dict[str, Any]]:
    """`SELECT staged_actions ... FOR UPDATE`, decoded, with NO transaction of
    its own — unlike `mutate_staged_actions`, the caller must already be
    inside `conn.transaction()` and must keep it open across its own
    `execute_setup_action` write and a following `mutate_staged_actions` call,
    so the two-phase "is this still proposed / run the write / flip the
    status" sequence is one atomic unit. Without this, two concurrent
    confirmations (a REST Approve click racing a chat "yes, go ahead") can
    both pass the proposed-status check and both perform the underlying
    write — `mutate_staged_actions`'s own lock only serializes the STATUS
    flip, not the row it's a status for."""
    row = await conn.fetchrow(
        "SELECT staged_actions FROM cappe_merlin_conversations WHERE id = $1 FOR UPDATE",
        conversation_id,
    )
    if row is None:
        return []
    return loads_list(row["staged_actions"]) if row["staged_actions"] is not None else []


async def mutate_staged_actions(
    conn, conversation_id: UUID, fn
) -> list[dict[str, Any]]:
    """Row-locked read-modify-write of a setup conversation's staged-action
    queue. `fn(list[dict]) -> list[dict]` is pure — it receives the current
    entries and returns the next state; this function owns the lock, the
    JSONB (de)serialization, and the pending-count cap.

    The lock is a `SELECT ... FOR UPDATE` inside this function's own
    transaction (nested transactions are savepoints in asyncpg, so calling
    this from within an already-open transaction is safe) — it exists so a
    chat-driven `stage_action`/`execute_staged_action` call and a REST
    approve/dismiss click for the same conversation can't race and clobber
    each other's view of the queue, mirroring matcha Huume's
    `store.execute_plan_locked` advisory-lock pattern (reimplemented here,
    not imported — cappe does not depend on matcha code).
    """
    async with conn.transaction():
        row = await conn.fetchrow(
            "SELECT staged_actions FROM cappe_merlin_conversations WHERE id = $1 FOR UPDATE",
            conversation_id,
        )
        current = loads_list(row["staged_actions"]) if row and row["staged_actions"] is not None else []
        next_state = fn(current)

        proposed = [e for e in next_state if isinstance(e, dict) and e.get("status") == "proposed"]
        if len(proposed) > MAX_PENDING_STAGED_ACTIONS:
            drop_ids = {
                e.get("id")
                for e in sorted(proposed, key=lambda e: e.get("created_at") or "")[
                    : len(proposed) - MAX_PENDING_STAGED_ACTIONS
                ]
            }
            next_state = [e for e in next_state if e.get("id") not in drop_ids]

        if len(next_state) > MAX_STAGED_ACTIONS:
            settled = [e for e in next_state if isinstance(e, dict) and e.get("status") != "proposed"]
            overflow = len(next_state) - MAX_STAGED_ACTIONS
            drop_ids = {
                e.get("id")
                for e in sorted(settled, key=lambda e: e.get("created_at") or "")[: overflow]
            }
            next_state = [e for e in next_state if e.get("id") not in drop_ids]

        await conn.execute(
            "UPDATE cappe_merlin_conversations SET staged_actions = $2, updated_at = NOW() WHERE id = $1",
            conversation_id,
            json.dumps(next_state),
        )
        return next_state
