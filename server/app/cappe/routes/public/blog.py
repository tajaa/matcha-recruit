"""Cappe public surface — blog."""
from fastapi import APIRouter, HTTPException, Request, status

from ....database import get_connection
from ...models.cappe import CappePost
from ._common import _published_site, _read_rate_limit

router = APIRouter()


@router.get("/public/sites/{slug}/posts", response_model=list[CappePost])
async def public_posts(slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            "SELECT id, site_id, title, slug, excerpt, body, cover_image_url, status, "
            "published_at, created_at, updated_at "
            "FROM cappe_posts WHERE site_id = $1 AND status = 'published' "
            "ORDER BY published_at DESC NULLS LAST, created_at DESC",
            site["id"],
        )
    return [dict(r) for r in rows]


@router.get("/public/sites/{slug}/posts/{post_slug}", response_model=CappePost)
async def public_post(slug: str, post_slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        row = await conn.fetchrow(
            "SELECT id, site_id, title, slug, excerpt, body, cover_image_url, status, "
            "published_at, created_at, updated_at "
            "FROM cappe_posts WHERE site_id = $1 AND slug = $2 AND status = 'published'",
            site["id"], post_slug,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return dict(row)
