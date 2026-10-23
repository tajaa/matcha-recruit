"""Following magazines from a Gummfit account (cappemag08).

A follow is a signed-in reader's one tap on their dashboard: a row in
`cappe_magazine_follows`. It sends no email (the magazine's email followers
are `cappe_subscribers`, double opt-in, and stay separate). It gives the
reader a Following list and a feed of new stories from the magazines they
follow, newest first. The owner sees only the count.

Only a live magazine can be followed. A followed magazine that goes down
stays in the list (`live` false) so it can be unfollowed, and its stories
leave the feed until it is back.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from ..common import site_public_origin
from .magazines import live_magazines
from .reader import LIVE, covers
from .shelf import story_card
from .stories import POST_COLS, post_row

# How many magazines one account may follow, and how many the feed and the
# list read. A cap keeps the feed one bounded query.
FOLLOW_LIMIT = 500
FEED_PAGE = 12
# The feed goes back this many pages (600 stories); the route refuses later
# ones, so the last says there is no more.
FEED_MAX_PAGE = 50

_SITE_COLS = "s.id, s.slug, s.name, s.subdomain, s.custom_domain, s.account_id, s.status"


async def follow(conn, account_id: UUID, site: dict) -> None:
    """Follow a live magazine (the caller has checked it is). Following again
    changes nothing. The count and the insert hold the account's lock, so two
    follows at once can't both pass the limit."""
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"cappe_follow:{account_id}")
        count = await conn.fetchval("SELECT COUNT(*) FROM cappe_magazine_follows WHERE account_id = $1", account_id)
        if count >= FOLLOW_LIMIT:
            exists = await conn.fetchval(
                "SELECT 1 FROM cappe_magazine_follows WHERE account_id = $1 AND site_id = $2", account_id, site["id"])
            if not exists:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
                    "code": "follow_limit", "message": f"You can follow up to {FOLLOW_LIMIT} magazines."})
        await conn.execute(
            "INSERT INTO cappe_magazine_follows (account_id, site_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            account_id, site["id"],
        )


async def unfollow(conn, account_id: UUID, site_id: UUID) -> None:
    await conn.execute("DELETE FROM cappe_magazine_follows WHERE account_id = $1 AND site_id = $2",
                       account_id, site_id)


async def is_following(conn, account_id: UUID, site_id: UUID) -> bool:
    return bool(await conn.fetchval(
        "SELECT 1 FROM cappe_magazine_follows WHERE account_id = $1 AND site_id = $2", account_id, site_id))


async def follower_count(conn, site_id: UUID) -> int:
    return int(await conn.fetchval("SELECT COUNT(*) FROM cappe_magazine_follows WHERE site_id = $1", site_id) or 0)


async def _followed_sites(conn, account_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"""SELECT {_SITE_COLS}, f.created_at AS followed_at
              FROM cappe_magazine_follows f JOIN cappe_sites s ON s.id = f.site_id
             WHERE f.account_id = $1
             ORDER BY f.created_at DESC LIMIT $2""",
        account_id, FOLLOW_LIMIT,
    )
    return [dict(r) for r in rows]


async def following(conn, account_id: UUID) -> list[dict[str, Any]]:
    """The magazines this account follows, most recently followed first."""
    sites = await _followed_sites(conn, account_id)
    live = await live_magazines(conn, [s for s in sites if s["status"] == "published"])
    out = []
    for s in sites:
        mag = live.get(s["id"])
        out.append({"site_id": s["id"], "slug": s["slug"], "name": (mag or {}).get("name") or s["name"],
                    "tagline": (mag or {}).get("tagline"), "accent": (mag or {}).get("accent"),
                    "origin": site_public_origin(s), "live": bool(mag), "followed_at": s["followed_at"]})
    return out


async def feed(conn, account_id: UUID, *, page: int = 1) -> dict[str, Any]:
    """New stories from the live magazines this account follows, newest first."""
    sites = await _followed_sites(conn, account_id)
    live = await live_magazines(conn, [s for s in sites if s["status"] == "published"])
    if not live:
        return {"stories": [], "has_more": False, "page": page}
    rows = await conn.fetch(
        f"SELECT {POST_COLS} FROM cappe_posts WHERE site_id = ANY($1::uuid[]) AND {LIVE} "
        "ORDER BY published_at DESC NULLS LAST, created_at DESC, id LIMIT $2 OFFSET $3",
        list(live), FEED_PAGE + 1, (page - 1) * FEED_PAGE,
    )
    posts = [post_row(r) for r in rows]
    shown = posts[:FEED_PAGE]
    by_site: dict[UUID, list[dict]] = {}
    for p in shown:
        by_site.setdefault(p["site_id"], []).append(p)
    found: dict[str, dict] = {}
    for site_id, group in by_site.items():
        found.update(await covers(conn, site_id, group))
    site_of = {s["id"]: s for s in sites}
    stories = []
    for p in shown:
        site, mag = site_of[p["site_id"]], live[p["site_id"]]
        stories.append({**story_card(p, found.get(str(p["id"]))),
                        "magazine": {"slug": site["slug"], "name": mag.get("name") or site["name"],
                                     "accent": mag.get("accent")}})
    return {"stories": stories, "has_more": len(posts) > FEED_PAGE and page < FEED_MAX_PAGE, "page": page}
