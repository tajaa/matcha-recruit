"""Cappe public render data — a published site by slug, for anonymous viewers."""
from fastapi import APIRouter, HTTPException, status

from ...database import get_connection
from ..models.cappe import CappePublicSite
from ._shared import loads, page_row_to_dict

router = APIRouter()


@router.get("/public/sites/{slug}", response_model=CappePublicSite)
async def get_public_site(slug: str):
    """Return a published site's render data (published pages only)."""
    async with get_connection() as conn:
        site = await conn.fetchrow(
            "SELECT id, name, slug, theme_config, meta_config, status "
            "FROM cappe_sites WHERE slug = $1",
            slug,
        )
        if site is None or site["status"] != "published":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
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
