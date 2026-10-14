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
actually did on the web, with flights and in a browser, written from the run's
own audit rows (`run_record`). Without it the next run only has the earlier
answer's wording to go on, and has "corrected" a page load that did happen.
Only the server writes a record: the same marker anywhere in a replayed
message is defused first, so a page cannot get a model to forge one.

`earlier_links` is the other half: the URLs recent runs in this conversation
verified, which the next run's result may cite again ("send me those links").
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.database import decode_jsonb
from app.matcha.services.huume.luna_client import text_item

from ..agent_card.schema import verified_links
from .result import read_result

DEFAULT_LIMIT = 20
DEFAULT_MAX_CHARS = 8000
_PER_MESSAGE_CHARS = 2000
# The run record: page loads, searches (web and flights) and browser steps.
# Mail and calendar reads stay out of it; the answer says what it needed to.
_RECORD_KINDS = ("fetch", "search", "browse")
RECORD_MARKER = "[System record of the run behind this answer:"
_FORGED_MARKER = re.compile(r"\[(\s*system\s+record)", re.IGNORECASE)
_RECORD_STEPS = 6
_RECORD_RUNS = 5
_RECORD_CHARS = 600  # per answer, within the replay's max_chars
_URL_CHARS = 120
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
        # A record is the server's to write: defuse the marker in what anyone
        # (a person, or a model a page talked into it) wrote.
        text = _FORGED_MARKER.sub(r"(\1", content[:_PER_MESSAGE_CHARS])
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
    # Records count toward max_chars too: drop the oldest messages until all fits.
    used += sum(len(records[run]) + 2 for _, _, run in kept if run in records)
    while kept and used > max_chars:
        _, text, run = kept.pop()
        used -= len(text) + (len(records.pop(run)) + 2 if run in records else 0)
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


_STATUS_SUFFIX = {
    "error": ", which failed",
    "skipped": ", skipped and never tried (the run's budget or time ran out)",
    "claimed": ", outcome unknown",
    "unknown": ", outcome unknown",
}


def _step_line(row) -> str:
    """One step, as the server saw it. A skipped step was never tried, which is
    not the same as a page that failed to load."""
    args = decode_jsonb(row["args"], {}) or {}
    out = decode_jsonb(row["result"], {}) or {}
    status = row["status"]
    if row["tool"] == "fetch_page":
        url = str(out.get("url") or args.get("url") or "").strip()[:_URL_CHARS] or "a page"
        if status == "ok" and not out.get("error"):
            return f"loaded {url}"
        if status == "skipped":
            return f"did not try {url} (the run's page budget or time ran out)"
        return f"tried to load {url}, which failed"
    if row["tool"] == "web_search":
        query = " ".join(str(args.get("query") or "").split())[:100]
        said = f'searched the web for "{query}"' if query else "searched the web"
        return said if out.get("status") in (None, "completed") else f"{said}, which did not complete"
    # Flights, the booking browser and any later tool: the server's own label.
    label = " ".join(str(row["label"] or row["tool"]).split())[:_URL_CHARS]
    return label + ("" if status == "ok" else _STATUS_SUFFIX.get(status, f" ({status})"))


async def run_record(conn, run_ids: list) -> dict[str, str]:
    """Run id -> one line saying what that run did on the web, with flights and
    in a browser, from its steps.

    Written by the server from `mw_project_agent_steps`, never by a model.
    Bounded: the first steps, then a count of the rest, at most
    `_RECORD_CHARS`."""
    ids = [u for u in (_uuid(r) for r in run_ids) if u is not None]
    if not ids:
        return {}
    rows = await conn.fetch(
        """SELECT run_id, tool, kind, label, status, args, result
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
            said = "no page loads, searches or browser steps"
        else:
            said = "; ".join(done[:_RECORD_STEPS])
            if len(done) > _RECORD_STEPS:
                said += f"; and {len(done) - _RECORD_STEPS} more steps"
        record = f"{RECORD_MARKER} {said}.]"
        if len(record) > _RECORD_CHARS:
            record = record[: _RECORD_CHARS - 5] + "….]"
        records[run] = record
    return records


async def earlier_links(conn, *, channel_id: UUID, exclude_run: UUID | None = None,
                        runs: int = EARLIER_RUNS) -> frozenset[str]:
    """Links recent finished runs in this conversation verified: what their
    stored results cite (`verified_links`, plus the pages their photos and
    screenshots came from) and the pages they loaded or viewed. Newest
    run first, so the cap drops the oldest.

    Every run in the conversation counts, not only the requester's: in a shared
    chat a coworker's answer is already on everyone's screen, and citing its
    links again shows nobody anything new. They are for the result only
    (`RunState.earlier_links`); nothing that acts reads them."""
    rows = await conn.fetch(
        """SELECT id, result FROM mw_project_agent_runs
           WHERE channel_id = $1 AND kind = 'assistant'
             AND status = 'done' AND id IS DISTINCT FROM $2
           ORDER BY created_at DESC
           LIMIT $3""",
        channel_id, exclude_run, runs,
    )
    loaded: dict[str, list[str]] = {}
    ids = [row["id"] for row in rows]
    if ids:
        for step in await conn.fetch(
            """SELECT run_id, result FROM mw_project_agent_steps
               WHERE run_id = ANY($1::uuid[]) AND tool IN ('fetch_page', 'view_page') AND status = 'ok'
               ORDER BY seq""",
            ids,
        ):
            out = decode_jsonb(step["result"], {}) or {}
            url = out.get("url")
            if isinstance(url, str) and url.startswith(("https://", "http://")) and not out.get("error"):
                loaded.setdefault(str(step["run_id"]), []).append(url)
    found: dict[str, None] = {}
    for row in rows:
        stored = read_result(decode_jsonb(row["result"], {})) or {}
        for block in stored.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") in ("sources", "picks"):
                found.update(dict.fromkeys(verified_links(block)))
            elif block.get("type") in ("photos", "screenshots"):
                # The page each picture came from, never the picture (our CDN copy).
                for image in block.get(block["type"]) or []:
                    page = image.get("page_url") if isinstance(image, dict) else None
                    if isinstance(page, str) and page.startswith(("https://", "http://")):
                        found[page] = None
        found.update(dict.fromkeys(loaded.get(str(row["id"]), [])))
    return frozenset(list(found)[:_MAX_EARLIER_LINKS])
