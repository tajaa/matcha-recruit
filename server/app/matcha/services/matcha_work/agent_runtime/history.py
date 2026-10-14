"""The conversation so far, replayed as context for one run.

A run has no memory of its own: each message starts a fresh one, and what came
before is read back from the channel. Two things come out of that read and
they are deliberately separate:

  * the replay: every recent message, so the model follows the conversation;
  * the requester's own texts: the only words that can ground an outward
    action (see `policy`).

In a shared project chat a coworker's message is context. It is never
grounding: someone else naming an address does not make it one the requester
asked to write to.

Each earlier answer of Espresso's is replayed with a record of what its run
actually did on the web, written from the run's own audit rows (`run_record`).
Without it the next run only has the earlier answer's wording to go on, and
has "corrected" a page load that did happen. `earlier_links` is the other half:
the URLs the requester's recent runs here already verified, seeded into the
next run's provenance so "send me those links" can be answered.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.database import decode_jsonb
from app.matcha.services.huume.luna_client import text_item

DEFAULT_LIMIT = 20
DEFAULT_MAX_CHARS = 8000
_PER_MESSAGE_CHARS = 2000
# The run record: web steps only (`fetch`, `search`). Mail and calendar reads
# stay out of it; the earlier answer already says what it needed to of them.
_RECORD_KINDS = ("fetch", "search")
_RECORD_STEPS = 8
_RECORD_RUNS = 5
_URL_CHARS = 200
EARLIER_RUNS = 5
_MAX_EARLIER_LINKS = 60


async def build_history(
    conn,
    *,
    channel_id: UUID,
    requester_id: UUID,
    trigger_message_id: UUID | None = None,
    limit: int = DEFAULT_LIMIT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[list[dict], tuple[str, ...]]:
    """(replay items oldest first, the requester's own texts).

    The trigger message itself is left out of the replay (the caller sends it
    as the run's request) but counts among the requester's texts.
    """
    rows = await conn.fetch(
        """SELECT m.id, m.sender_id, m.content,
                  m.metadata->>'kind' AS metadata_kind, m.metadata->>'run_id' AS run_id,
                  (u.email LIKE 'espresso@%.invalid') AS from_espresso,
                  COALESCE(c.name, NULLIF(BTRIM(CONCAT(e.first_name, ' ', e.last_name)), ''), 'Someone') AS sender_name
           FROM channel_messages m
           LEFT JOIN users u ON u.id = m.sender_id
           LEFT JOIN clients c ON c.user_id = m.sender_id
           LEFT JOIN employees e ON e.user_id = m.sender_id
           WHERE m.channel_id = $1 AND m.deleted_at IS NULL
             -- The column holds 'user' or 'system' (ems01); anything that is
             -- not a system notice is part of the conversation.
             AND m.message_type IS DISTINCT FROM 'system'
             -- "On it." is a progress card, not something that was said.
             AND COALESCE(m.metadata->>'kind', '') <> 'agent_progress'
           ORDER BY m.created_at DESC
           LIMIT $2""",
        channel_id, limit + 1,
    )
    kept: list[tuple[str, str, str | None]] = []  # (role, text, run id), newest first
    own: list[str] = []
    used = 0
    full = False
    for row in rows:  # newest first: the budget keeps the most recent
        content = (row["content"] or "").strip()
        if not content:
            continue
        mine = row["sender_id"] == requester_id
        if mine:
            own.append(content)
        if trigger_message_id is not None and row["id"] == trigger_message_id:
            continue
        text = content[:_PER_MESSAGE_CHARS]
        if full or len(kept) >= limit or used + len(text) > max_chars:
            # Stop at the first message that does not fit, so the replay is an
            # unbroken run of the latest messages rather than whichever fit.
            full = True
            continue
        used += len(text)
        if row["from_espresso"]:
            answered = row.get("metadata_kind") == "agent_result" and row.get("run_id")
            kept.append(("assistant", text, row["run_id"] if answered else None))
        elif mine:
            kept.append(("user", text, None))
        else:
            kept.append(("user", f"[{row['sender_name']}, another person in this chat]: {text}", None))
    runs = [run for _, _, run in kept if run][:_RECORD_RUNS]
    records = await run_record(conn, runs)
    items = [
        text_item(role, f"{text}\n\n{records[run]}" if run in records else text)
        for role, text, run in reversed(kept)
    ]
    own.reverse()
    return items, tuple(own)


def _uuid(value: Any) -> UUID | None:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


def _step_line(row) -> str:
    args = decode_jsonb(row["args"], {}) or {}
    out = decode_jsonb(row["result"], {}) or {}
    if row["kind"] == "search":
        query = " ".join(str(args.get("query") or "").split())[:120]
        return f'searched "{query}"' if query else "searched the web"
    url = str(out.get("url") or args.get("url") or "").strip()[:_URL_CHARS] or "a page"
    if row["status"] == "ok" and not out.get("error"):
        return f"loaded {url}"
    return f"tried to load {url}, which failed"


async def run_record(conn, run_ids: list) -> dict[str, str]:
    """Run id -> one line saying what that run did on the web, from its steps.

    Written by the server from `mw_project_agent_steps`, never by a model, so
    a later run can rely on it over the earlier answer's own account."""
    ids = [u for u in (_uuid(r) for r in run_ids) if u is not None]
    if not ids:
        return {}
    rows = await conn.fetch(
        """SELECT run_id, kind, status, args, result
           FROM mw_project_agent_steps
           WHERE run_id = ANY($1::uuid[]) AND kind = ANY($2::text[])
           ORDER BY run_id, seq""",
        ids, list(_RECORD_KINDS),
    )
    lines: dict[str, list[str]] = {str(u): [] for u in ids}
    for row in rows:
        lines[str(row["run_id"])].append(_step_line(row))
    records = {}
    for run, done in lines.items():
        if not done:
            said = "it did not load or search any web page"
        else:
            said = "; ".join(done[:_RECORD_STEPS])
            if len(done) > _RECORD_STEPS:
                said += f"; and {len(done) - _RECORD_STEPS} more"
        records[run] = f"[System record of the run behind this answer: {said}.]"
    return records


def _urls(value: Any, found: set[str]) -> None:
    """Every http(s) `url` / `page_url` in a stored result, which the result
    gate already let through when it was stored."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("url", "page_url") and isinstance(item, str) and item.startswith(("https://", "http://")):
                found.add(item)
            else:
                _urls(item, found)
    elif isinstance(value, list):
        for item in value:
            _urls(item, found)


async def earlier_links(conn, *, channel_id: UUID, requester_id: UUID,
                        exclude_run: UUID | None = None, runs: int = EARLIER_RUNS) -> frozenset[str]:
    """URLs the requester's recent finished runs in this conversation
    verified: pages they loaded, and links their stored results carry.

    Only the requester's own runs: in a shared chat a coworker's run is
    context, and it vouches for nothing in this one."""
    rows = await conn.fetch(
        """SELECT id, result FROM mw_project_agent_runs
           WHERE channel_id = $1 AND requested_by = $2 AND kind = 'assistant'
             AND status = 'done' AND id IS DISTINCT FROM $3
           ORDER BY created_at DESC
           LIMIT $4""",
        channel_id, requester_id, exclude_run, runs,
    )
    found: set[str] = set()
    for row in rows:
        _urls(decode_jsonb(row["result"], {}), found)
    ids = [row["id"] for row in rows]
    if ids:
        for step in await conn.fetch(
            """SELECT result FROM mw_project_agent_steps
               WHERE run_id = ANY($1::uuid[]) AND kind = 'fetch' AND status = 'ok'""",
            ids,
        ):
            out = decode_jsonb(step["result"], {}) or {}
            url = out.get("url")
            if isinstance(url, str) and url.startswith(("https://", "http://")) and not out.get("error"):
                found.add(url)
    return frozenset(sorted(found)[:_MAX_EARLIER_LINKS])
