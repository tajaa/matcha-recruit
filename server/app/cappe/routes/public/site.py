"""Cappe public surface — site render data."""
from fastapi import APIRouter, Request

from ....database import get_connection
from ...models.cappe import CappePublicSite
from .._shared import loads, page_row_to_dict
from ._common import _published_site, _read_rate_limit

router = APIRouter()


@router.get("/public/sites/{slug}", response_model=CappePublicSite)
async def get_public_site(slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        pages = await conn.fetch(
            "SELECT id, site_id, title, slug, content, sort_order, status, created_at, updated_at "
            "FROM cappe_pages WHERE site_id = $1 AND status = 'published' ORDER BY sort_order, created_at",
            site["id"],
        )
    return CappePublicSite(
        name=site["name"],
        slug=site["slug"],
        theme_config=loads(site["theme_config"]),
        meta_config=loads(site["meta_config"]),
        pages=[page_row_to_dict(p) for p in pages],
    )
