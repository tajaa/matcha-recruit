"""Cappe public surface — blog posts / magazine stories as JSON.

Only live posts (published and not hidden by an admin). A paid story's body
and blocks are never returned here: its words are for subscribers, and this
endpoint is anonymous.
"""
from fastapi import HTTPException, Request, status

from ....database import get_connection
from ...models.cappe import CappePost
from ...services.magazine.reader import LIVE
from ...services.magazine.stories import POST_COLS, post_row
from ._common import _published_site, _read_rate_limit

from ._body_limit import limited_public_router

router = limited_public_router()


def _public(row) -> dict:
    d = post_row(row)
    d["hidden"] = False
    d.pop("hidden_at", None)
    if d.get("access") == "paid":
        d["body"] = None
        d["content"] = None
    return d


@router.get("/public/sites/{slug}/posts", response_model=list[CappePost])
async def public_posts(slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            f"SELECT {POST_COLS} FROM cappe_posts WHERE site_id = $1 AND {LIVE} "
            "ORDER BY published_at DESC NULLS LAST, created_at DESC",
            site["id"],
        )
    return [_public(r) for r in rows]


@router.get("/public/sites/{slug}/posts/{post_slug}", response_model=CappePost)
async def public_post(slug: str, post_slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        row = await conn.fetchrow(
            f"SELECT {POST_COLS} FROM cappe_posts WHERE site_id = $1 AND slug = $2 AND {LIVE}",
            site["id"], post_slug,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return _public(row)
