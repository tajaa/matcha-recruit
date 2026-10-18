"""A task's card in the conversation it came from.

When a task starts from chat (a submitted form, or `start_task`), Espresso
posts a card saying so; when it finishes, stops or needs the person, another
card follows in the same conversation with the headline and the top
findings. Both are ordinary Espresso messages (metadata kind `agent_task`),
so apps that don't know the card show the text.

Everything in a card is read from the task's own rows. Pool-free: the
finished card is posted from the worker.
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.database import decode_jsonb

from . import items as items_mod
from .research.model_phases import SUMMARY_TOP, TOP_PICKS

logger = logging.getLogger(__name__)

METADATA_KIND = "agent_task"
# The summary's top picks ("find 5" shows five), in its order, chosen from the
# best SUMMARY_TOP by rank.
TOP_ITEMS = TOP_PICKS
PICKED_FROM = SUMMARY_TOP


def card_view(task: dict, *, summary: dict | None = None, top: list[dict] | None = None,
              event: str = "update", limit: int = TOP_ITEMS) -> dict:
    """The bounded card both apps render: status, the note or headline, and
    up to TOP_ITEMS findings."""
    progress = task.get("progress") if isinstance(task.get("progress"), dict) else decode_jsonb(task.get("progress"), {}) or {}
    return {
        "event": event,
        "task_id": str(task["id"]),
        "playbook": task.get("playbook"),
        "title": (task.get("title") or task.get("directive") or "")[:120],
        "status": task.get("status"),
        "note": str(progress.get("note") or "")[:200],
        "headline": str((summary or {}).get("headline") or "")[:200] or None,
        "counts": (summary or {}).get("counts"),
        "items": [
            {"id": item["id"], "title": item["title"][:120], "subtitle": item.get("subtitle", "")[:120],
             "url": item.get("url"), "fields": {k: v.get("display") for k, v in (item.get("fields") or {}).items()},
             "image": (item.get("images") or [{}])[0].get("url") if item.get("images") else None}
            for item in (top or [])[:limit]
        ],
    }


def card_text(card: dict) -> str:
    title = card["title"] or "your task"
    if card["event"] == "started":
        return f"On it: {title}. I'll let you know here when it's done."
    if card["status"] == "done":
        return f"Done: {title}. {card['headline'] or card['note']}".strip()
    if card["status"] == "failed":
        return f"Stopped: {title}. {card['note']}".strip()
    if card["status"] == "waiting":
        return f"{title} needs you to go on."
    return f"{title}: {card['note']}".strip()


async def post_card(conn, task: dict, *, company_id: UUID, channel_id: UUID, event: str = "update",
                    summary: dict | None = None, top: list[dict] | None = None) -> dict | None:
    """Insert the card on the caller's transaction; returns the message to
    broadcast once it has committed."""
    from app.matcha.services.matcha_work.project_agent.chat import persist_espresso_message

    card = card_view(task, summary=summary, top=top, event=event)
    return await persist_espresso_message(
        conn, company_id, channel_id, card_text(card),
        metadata={"kind": METADATA_KIND, "task_id": card["task_id"], "task": card},
    )


async def picked_from(conn, task_id: UUID, summary: dict) -> list:
    """The findings a round's picks come from: the batch it released, when it
    released one (`research/batches.py`), else the best ranked."""
    batch = summary.get("batch")
    if isinstance(batch, list):
        return list(await conn.fetch(
            """SELECT * FROM mw_agent_task_items WHERE task_id = $1 AND id::text = ANY($2::text[])
               ORDER BY rank NULLS LAST""",
            task_id, [str(i) for i in batch],
        ))
    return list(await conn.fetch(
        f"""SELECT * FROM mw_agent_task_items WHERE task_id = $1 AND rank_band < 9
            ORDER BY rank LIMIT {PICKED_FROM}""",
        task_id,
    ))


def picks(ranked: list[dict], summary: dict) -> list[dict]:
    """The summary's top picks first, in its order, then the ranking's best."""
    order = {str(p.get("item_id")): n for n, p in enumerate(summary.get("top") or []) if isinstance(p, dict)}
    return sorted(ranked, key=lambda item: order.get(str(item["id"]), len(order)))[:TOP_ITEMS]


async def post_stopped(conn, task_id: UUID) -> dict | None:
    """The finished (or stopped, or waiting) card in the task's conversation,
    if it came from one. Returns the message to broadcast."""
    row = await conn.fetchrow(
        """SELECT id, user_id, company_id, playbook, title, directive, status, progress, origin_channel_id,
                  current_round
           FROM mw_agent_tasks WHERE id = $1 AND deleted_at IS NULL""",
        task_id,
    )
    if row is None or row["origin_channel_id"] is None or row["status"] not in ("done", "failed", "waiting"):
        return None
    summary = decode_jsonb(await conn.fetchval(
        "SELECT summary FROM mw_agent_task_rounds WHERE task_id = $1 AND n = $2", task_id, row["current_round"],
    ), {}) or {}
    top = picks([items_mod.item_summary(r) for r in await picked_from(conn, task_id, summary)],
                summary) if row["status"] == "done" else []
    return await post_card(conn, dict(row), company_id=row["company_id"], channel_id=row["origin_channel_id"],
                           summary=summary, top=top)
