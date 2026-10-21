"""One turn of the Social chat: what's been dropped, one Claude call, the
plan card.

The conversation lives in Merlin's tables (`cappe_merlin_conversations` with
`kind='social'`, no page) so the transcript and the confirm-first card reuse
`merlin/store.py`: messages carry what was dropped (`attachments`), and the
plan is a staged action (`kind='social_plan'`, proposed → executed /
dismissed / replaced) whose `revision` the confirm must match.

Everything dropped in the conversation and not yet posted is one numbered
list (`items_from`), so "put the first two together" means the same thing on
every turn, and a chat that goes on after a confirm plans only what's new.
Videos are looked up fresh each turn: the model sees a poster frame once the
cut has one. A video made into download files by a confirmed plan counts as
used too, so the next turn doesn't offer it again.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.core.services import anthropic_messages
from app.core.services.storage import get_storage

from ..ai import AiUnavailable, model_for
from ..assets import poster
from . import plan as planner

logger = logging.getLogger(__name__)

KIND = "social"
ACTION_KIND = "social_plan"
MAX_ITEMS = 20
FALLBACK_REPLY = "Here's a plan — check it and confirm."


def own_image(url: Optional[str]) -> bool:
    """A photo uploaded through the Social page (our CDN, our prefix). Only
    those are handed to the model, which fetches them by URL."""
    domain = get_storage().cloudfront_domain
    return bool(url and domain and url.startswith(f"https://{domain}/cappe/social/"))


def _shape(asset: dict[str, Any]) -> Optional[str]:
    w, h = asset.get("width"), asset.get("height")
    if not (w and h):
        return None
    ratio = w / h
    return "vertical" if ratio < 0.9 else "landscape" if ratio > 1.1 else "square"


def posted_keys(actions: list[dict[str, Any]]) -> set[str]:
    """What the conversation's confirmed plans already posted (photo URLs,
    video asset ids)."""
    keys: set[str] = set()
    for action in actions:
        if action.get("kind") != ACTION_KIND or action.get("status") != "executed":
            continue
        plan = action.get("plan") or {}
        # A files-only confirm posted nothing: its videos are used (made into
        # files), its photos are still there to post.
        posted = bool(action.get("post_ids"))
        exported = set((plan.get("exports") or {}).get("items") or []) if action.get("export_ids") else set()
        for post in plan.get("posts") or []:
            for n, item in zip(post.get("items") or [], post.get("media") or []):
                key = item.get("asset_id") or item.get("url")
                if key and (posted or (item.get("kind") == "video" and n in exported)):
                    keys.add(str(key))
    return keys


def items_from(messages: list[dict[str, Any]], assets: dict[str, dict[str, Any]],
               exclude: set[str] | frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Everything the owner has dropped in this conversation, in order, once
    each, minus what's already posted (`exclude`). A video that failed or is
    gone is left out."""
    seen: set[str] = set(exclude)
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        for att in message.get("attachments") or []:
            if not isinstance(att, dict):
                continue
            key = str(att.get("asset_id") or att.get("url") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            if att.get("kind") == "video":
                asset = assets.get(key)
                if asset is None or asset.get("status") in ("failed", "deleted"):
                    continue
                out.append({"kind": "video", "asset_id": key, "poster": poster(asset), "name": att.get("name"),
                            "duration_ms": asset.get("duration_ms"), "shape": _shape(asset),
                            "status": asset.get("status")})
            else:
                out.append({"kind": "image", "url": att.get("url"), "name": att.get("name")})
    return out[:MAX_ITEMS]


def pictures(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[int]]:
    """Image blocks for the model (photos, and video posters), and which item
    number each one is."""
    blocks, numbers = [], []
    for n, item in enumerate(items, start=1):
        url = item.get("url") if item.get("kind") == "image" else item.get("poster")
        if url and len(blocks) < planner.MAX_PICTURES:
            blocks.append({"type": "image", "source": {"type": "url", "url": url}})
            numbers.append(n)
    return blocks, numbers


def latest(actions: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    plans = [a for a in actions if isinstance(a, dict) and a.get("kind") == ACTION_KIND]
    return plans[-1] if plans else None


def proposed(actions: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    current = latest(actions)
    return current if current and current.get("status") == "proposed" else None


def staged(plan: dict[str, Any], *, revision: int, model: str) -> dict[str, Any]:
    return {"id": uuid4().hex, "kind": ACTION_KIND, "status": "proposed", "revision": revision, "plan": plan,
            "post_ids": [], "export_ids": [], "model": model, "created_at": datetime.now(timezone.utc).isoformat()}


def replace_proposed(new: dict[str, Any]):
    """For `mutate_staged_actions`: the new plan supersedes any still open."""
    def apply(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = [{**a, "status": "replaced"} if a.get("kind") == ACTION_KIND and a.get("status") == "proposed" else a
               for a in actions]
        return [*out, new]
    return apply


def next_revision(actions: list[dict[str, Any]]) -> int:
    return max([int(a.get("revision") or 0) for a in actions if a.get("kind") == ACTION_KIND] or [0]) + 1


async def think(
    *, site: dict[str, Any], settings: dict[str, Any], accounts: list[dict[str, Any]],
    products: list[dict[str, Any]], items: list[dict[str, Any]], history: list[dict[str, Any]],
    current_plan: Optional[dict[str, Any]], message: str, now_local: datetime, tz_name: str,
    origin: Optional[str],
) -> tuple[str, Optional[dict[str, Any]], str]:
    """(reply, plan or None, model). Raises AiUnavailable without a model,
    RuntimeError/ValueError on a failed call."""
    model = await model_for("chat")
    if not model:
        raise AiUnavailable("The social assistant needs Claude; ask your admin to set ANTHROPIC_API_KEY")
    blocks, numbers = pictures(items)
    files_for = planner.export_hint(message, items, accounts, current_plan)
    prompt = planner.build_prompt(
        site=site, settings=settings, accounts=accounts, products=products, items=items, pictures=numbers,
        history=history, current_plan=current_plan, message=message, now_local=now_local,
        export_platforms=files_for,
    )
    raw = await anthropic_messages.generate_text(
        prompt, model=model, system=planner.SYSTEM, attachments=blocks, json_output=True,
        # TikTok and YouTube words for each video post need the room.
        max_tokens=8_000 if files_for else 6_000, effort="low", timeout_seconds=60.0,
    )
    out = planner.parse_reply(raw)
    plan = planner.resolve(out, message=message, items=items, accounts=accounts, products=products,
                           origin=origin, now_local=now_local, tz_name=tz_name, current=current_plan)
    reply = str(out.get("reply") or "").strip()[:1000] or (FALLBACK_REPLY if plan else "What would you like to post?")
    return reply, plan, model


__all__ = [
    "KIND", "ACTION_KIND", "own_image", "posted_keys", "items_from", "pictures", "latest", "proposed", "staged",
    "replace_proposed", "next_revision", "think",
]
