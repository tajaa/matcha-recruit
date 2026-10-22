"""What a magazine's public pages read: its live stories and their covers.

"Live" is `status = 'published' AND hidden_at IS NULL` everywhere a reader can
reach — the front, topic pages, a story, the feed, the sitemap, the public
JSON. A hidden story (an admin took it down) is a 404, not a page.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from .stories import POST_COLS, cover_asset, post_row, site_assets
from .story_schema import referenced_asset_ids

LIVE = "status = 'published' AND hidden_at IS NULL"


async def live_stories(conn, site_id: UUID, *, topic: Optional[str] = None, exclude: Optional[UUID] = None,
                       limit: int = 12, offset: int = 0) -> list[dict]:
    clauses, args = [f"site_id = $1 AND {LIVE}"], [site_id]
    if topic:
        args.append(topic)
        clauses.append(f"topic = ${len(args)}")
    if exclude:
        args.append(exclude)
        clauses.append(f"id <> ${len(args)}")
    args += [limit, offset]
    rows = await conn.fetch(
        f"SELECT {POST_COLS} FROM cappe_posts WHERE {' AND '.join(clauses)} "
        f"ORDER BY published_at DESC NULLS LAST, created_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}",
        *args,
    )
    return [post_row(r) for r in rows]


async def live_story(conn, site_id: UUID, *, slug: Optional[str] = None, post_id: Optional[UUID] = None) -> Optional[dict]:
    if slug is not None:
        row = await conn.fetchrow(f"SELECT {POST_COLS} FROM cappe_posts WHERE site_id = $1 AND slug = $2 AND {LIVE}",
                                  site_id, slug)
    else:
        row = await conn.fetchrow(f"SELECT {POST_COLS} FROM cappe_posts WHERE site_id = $1 AND id = $2 AND {LIVE}",
                                  site_id, post_id)
    return post_row(row) if row else None


async def covers(conn, site_id: UUID, posts: list[dict]) -> dict[str, dict]:
    """Each story's cover picture, keyed by the story's id."""
    wanted = {str(p["id"]): cover_asset(p.get("content") or {}, p.get("cover_asset_id")) for p in posts}
    assets = await site_assets(conn, site_id, [a for a in wanted.values() if a])
    return {pid: assets[aid] for pid, aid in wanted.items() if aid and aid in assets}


async def story_assets(conn, site_id: UUID, post: dict) -> dict[str, dict]:
    return await site_assets(conn, site_id, referenced_asset_ids(post.get("content") or {}, post.get("cover_asset_id")))


async def topics_in_use(conn, site_id: UUID, preferred: list[str]) -> list[str]:
    """The topics that have live stories, the magazine's own list first."""
    rows = await conn.fetch(
        f"SELECT DISTINCT topic FROM cappe_posts WHERE site_id = $1 AND {LIVE} AND topic IS NOT NULL", site_id,
    )
    used = {r["topic"] for r in rows}
    ordered = [t for t in preferred if t in used]
    return ordered + sorted(used - set(ordered))
