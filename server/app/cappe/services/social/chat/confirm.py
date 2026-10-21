"""A confirmed plan becomes posts — the same posts and targets the form
composer makes, so the queue, the publisher and the retries don't know or
care where they came from.

Each network's own copy goes on its target (`content`: the text and the
link with that network's UTM tags), and the post keeps the Instagram caption
for the queue. The owner's edits on the card (`apply_edits`) are applied and
checked before anything is written; the caller runs `create_posts` inside one
transaction with the plan's row locked, so a double click can't post twice.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from ...common import loads_list
from .. import assets as asset_store
from .. import posts as post_store
from .plan import compose_caption, with_utm

MAX_AHEAD = timedelta(days=365)


class PlanError(ValueError):
    """The plan (as edited) can't be posted; the message says why."""


class AlreadyPosted(PlanError):
    """Something in the plan already went out from this chat."""


def _key(item: dict[str, Any]) -> Optional[str]:
    key = item.get("asset_id") or item.get("url")
    return str(key) if key else None


async def posted_from_chat(conn, site_id: UUID, conversation_id: UUID) -> set[str]:
    """What this chat has posted (photo URLs, video asset ids), read from the
    posts themselves — not the conversation's plan history, which is pruned
    and can be a step behind a confirm made during a turn."""
    rows = await conn.fetch(
        """SELECT media FROM cappe_social_posts
           WHERE site_id = $1 AND ai_meta->'chat'->>'conversation_id' = $2 AND status <> 'cancelled'""",
        site_id, str(conversation_id),
    )
    return {k for r in rows for item in loads_list(r["media"]) if isinstance(item, dict) for k in [_key(item)] if k}


async def check_media(conn, site_id: UUID, conversation_id: UUID, plan: dict[str, Any]) -> None:
    """Before writing: nothing in the plan went out from this chat already,
    and every video is still usable (not failed, deleted or someone else's).
    Runs under the plan's lock, so a second confirm sees the first's posts."""
    keys = {k for post in plan.get("posts") or [] for item in post.get("media") or [] for k in [_key(item)] if k}
    if keys & await posted_from_chat(conn, site_id, conversation_id):
        raise AlreadyPosted("Some of this was already posted from this chat — check the Queue")
    videos = {str(item["asset_id"]) for post in plan.get("posts") or [] for item in post.get("media") or []
              if item.get("kind") == "video" and item.get("asset_id")}
    if videos:
        found = await asset_store.load_many(conn, list(videos))
        for asset_id in videos:
            asset = found.get(asset_id)
            if asset is None or asset["site_id"] != site_id or asset["status"] not in ("rendering", "ready"):
                raise PlanError((asset or {}).get("error") or "A video in this plan failed or is gone — drop it again")


def apply_edits(plan: dict[str, Any], edits: Optional[list[dict[str, Any]]], *, keep_link: bool) -> dict[str, Any]:
    """The plan with the owner's own words in place of the model's."""
    out = {**plan, "posts": [dict(p) for p in plan.get("posts") or []]}
    if edits is not None:
        if len(edits) != len(out["posts"]):
            raise PlanError("The plan changed — reload it and try again")
        for post, edit in zip(out["posts"], edits):
            post["instagram"] = {"caption": edit["instagram"]["caption"], "hashtags": edit["instagram"]["hashtags"]}
            post["facebook"] = {"text": edit["facebook"]["text"]}
            post["alt_text"] = edit.get("alt_text")
    if not keep_link:
        out["link"] = {"kind": "none", "product_id": None, "product_name": None, "url": None}
    return out


def schedule(mode: str, when_local: Optional[str], tz, now: Optional[datetime] = None) -> Optional[datetime]:
    """The first post's time (UTC), None for a draft. `now` posts at once."""
    now = now or datetime.now(timezone.utc)
    if mode == "draft":
        return None
    if mode == "now":
        return now
    try:
        local = datetime.fromisoformat(str(when_local or ""))
    except ValueError:
        raise PlanError("Pick a time for this") from None
    at = (local if local.tzinfo else local.replace(tzinfo=tz)).astimezone(timezone.utc)
    if at < now - timedelta(minutes=1):
        raise PlanError("That time has already passed — pick another")
    if at > now + MAX_AHEAD:
        raise PlanError("Schedule within the next year")
    return at


def _media(post: dict[str, Any]) -> list[dict[str, Any]]:
    alt = post.get("alt_text")
    out = []
    for item in post.get("media") or []:
        if item.get("kind") == "video":
            out.append({"kind": "video", "asset_id": str(item["asset_id"]), "alt": alt})
        else:
            out.append({"kind": "image", "url": item["url"], "alt": alt})
    return out


def check(plan: dict[str, Any], platforms: list[str], *, mode: str) -> None:
    """Every post must be postable where it's going (drafts may be anything)."""
    if not plan.get("posts"):
        raise PlanError("There's nothing to post yet — drop a photo or a video, or say what to post")
    if mode == "draft":
        return
    if not platforms:
        raise PlanError("Pick at least one account to post to")
    for n, post in enumerate(plan["posts"], start=1):
        caption = compose_caption(post.get("instagram") or {}) or (post.get("facebook") or {}).get("text") or ""
        reason = post_store.validate_for_targets(caption, _media(post), platforms)
        if reason:
            raise PlanError(f"Post {n}: {reason}" if len(plan["posts"]) > 1 else reason)


async def create_posts(
    conn, *, site_id: UUID, plan: dict[str, Any], accounts: list[dict[str, Any]], first_at: Optional[datetime],
    publish_now: bool, provenance: dict[str, Any], tz=None,
) -> list[dict[str, Any]]:
    """Write one post per planned post. Returns `[{id, publish_now}]`; the
    caller dispatches publishing for those once the transaction commits."""
    link = (plan.get("link") or {}).get("url")
    product_id = (plan.get("link") or {}).get("product_id")
    created = []
    for post in plan["posts"]:
        offset = timedelta(days=int(post.get("offset_days") or 0))
        # Days are added on the store's wall clock, so a post spread across a
        # clock change still goes out at the hour picked.
        at = ((first_at.astimezone(tz) + offset).astimezone(timezone.utc) if tz else first_at + offset) \
            if first_at else None
        now_post = publish_now and not offset
        instagram = compose_caption(post.get("instagram") or {})
        facebook = ((post.get("facebook") or {}).get("text") or "").strip() or instagram
        row = await post_store.create_post(
            conn, site_id=site_id, caption=instagram or facebook, media=_media(post), link_url=link,
            product_id=UUID(product_id) if product_id else None, scheduled_at=None if now_post else at,
            ai_meta={"alt_text": post.get("alt_text"), "chat": provenance} if post.get("alt_text") else {"chat": provenance},
        )
        await post_store.set_targets(conn, row["id"], [UUID(a["connection_id"]) for a in accounts],
                                     due_at=None if now_post else at)
        await post_store.set_content(conn, row["id"], {
            "instagram": {"text": instagram, "link_url": with_utm(link, "instagram")},
            "facebook": {"text": facebook, "link_url": with_utm(link, "facebook")},
        })
        if now_post:
            await post_store.publish_now(conn, site_id, row["id"])
        created.append({"id": row["id"], "publish_now": now_post})
    return created


__all__ = ["PlanError", "AlreadyPosted", "posted_from_chat", "check_media", "apply_edits", "schedule", "check", "create_posts"]
