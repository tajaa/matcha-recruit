"""Saving a story: the stored shape, the text the iOS app sees, reading time,
and the record of which library pictures a story uses.

A story (`format='blocks'`) keeps its words in `content`. Its `body` — the
plain-text field the iOS app shows and edits — is DERIVED from the blocks on
every save, so the app always has something to show; an app edit that changes
`body` is refused with 409 `edit_on_web` (the route), because writing it back
would lose the layout. A legacy post (`format='markdown'`) keeps its Markdown
`body` and renders as one text block.
"""
from __future__ import annotations

import json
import math
from typing import Any, Iterable, Optional
from uuid import UUID

from ..cappe_assets import COLUMNS as ASSET_COLUMNS, row as asset_row
from .richtext import md_to_text
from .story_schema import StoryError, count_words, referenced_asset_ids

POST_COLS = (
    "id, site_id, title, slug, excerpt, body, cover_image_url, status, published_at, created_at, updated_at, "
    "format, content, kicker, topic, layout, access, cover_asset_id, byline, word_count, reading_minutes, "
    "hidden_at"
)

WORDS_PER_MINUTE = 230


def post_row(r) -> dict[str, Any]:
    d = dict(r)
    content = d.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            content = {}
    d["content"] = content if isinstance(content, dict) else {}
    return d


def story_text(content: dict) -> str:
    """The story's words in reading order, as plain text: what `body` holds for
    a block story, what is counted, and what a feed or search reads."""
    parts: list[str] = []
    for b in content.get("blocks") or []:
        kind = b.get("type")
        if kind == "text":
            parts.append(md_to_text(b.get("md")))
        elif kind == "quote" and b.get("text"):
            who = f" — {b['attribution']}" if b.get("attribution") else ""
            parts.append(f"“{b['text']}”{who}")
        elif kind == "sidebar":
            parts.append("\n".join(filter(None, [b.get("title"), md_to_text(b.get("md"))])))
        elif kind == "qa":
            for item in b.get("items") or []:
                parts.append("\n".join(filter(None, [item.get("q"), md_to_text(item.get("a_md"))])))
        elif kind == "photo":
            # Words set on the picture are part of the story too.
            parts += [o["text"] for o in b.get("overlays") or [] if (o.get("text") or "").strip()]
            if b.get("caption"):
                parts.append(b["caption"])
    return "\n\n".join(p for p in parts if p.strip())


def reading_stats(text: str) -> tuple[int, int]:
    """(words, minutes): a minute per 230 words, at least one for any text."""
    words = count_words(text)
    return words, (math.ceil(words / WORDS_PER_MINUTE) if words else 0)


async def site_assets(conn, site_id: UUID, ids: Iterable[str]) -> dict[str, dict]:
    """The site's own library rows for `ids`, keyed by id string."""
    wanted = sorted(set(ids))
    if not wanted:
        return {}
    rows = await conn.fetch(
        f"SELECT {ASSET_COLUMNS} FROM cappe_assets WHERE site_id = $1 AND id = ANY($2::uuid[])",
        site_id, wanted,
    )
    return {str(r["id"]): asset_row(r) for r in rows}


async def check_assets(conn, site_id: UUID, content: dict, cover_asset_id: Optional[str]) -> dict[str, dict]:
    """Every picture the story uses must be in this site's library."""
    ids = referenced_asset_ids(content, cover_asset_id)
    found = await site_assets(conn, site_id, ids)
    if len(found) != len(ids):
        raise StoryError("A picture in this story isn't in your library any more. Choose another.")
    return found


async def sync_post_assets(conn, post_id: UUID, site_id: UUID, ids: Iterable[str]) -> None:
    """Record exactly the pictures a story uses now."""
    await conn.execute("DELETE FROM cappe_post_assets WHERE post_id = $1", post_id)
    wanted = sorted(set(ids))
    if wanted:
        await conn.execute(
            "INSERT INTO cappe_post_assets (post_id, asset_id, site_id) "
            "SELECT $1, unnest($2::uuid[]), $3 ON CONFLICT DO NOTHING",
            post_id, wanted, site_id,
        )


def cover_asset(content: dict, cover_asset_id: Optional[str]) -> Optional[str]:
    """The picture on the cover: the cover block's, else the story's own."""
    blocks = content.get("blocks") or []
    if blocks and blocks[0].get("type") == "cover" and blocks[0].get("asset_id"):
        return blocks[0]["asset_id"]
    return str(cover_asset_id) if cover_asset_id else None


async def stories_using(conn, site_id: UUID, asset_id: UUID) -> list[str]:
    """Titles of the stories that show a picture (to refuse deleting it)."""
    rows = await conn.fetch(
        "SELECT p.title FROM cappe_post_assets pa JOIN cappe_posts p ON p.id = pa.post_id "
        "WHERE pa.site_id = $1 AND pa.asset_id = $2 ORDER BY p.updated_at DESC LIMIT 5",
        site_id, asset_id,
    )
    return [r["title"] for r in rows]
