"""Cappe template catalog — public, read-only."""
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from ...database import get_connection
from ..models.cappe import CappeTemplateDetail, CappeTemplateSummary
from ..services.render import render_site_html
from ._shared import loads

router = APIRouter()

_SUMMARY_COLS = "id, name, slug, category, description, preview_image_url, is_premium, price_cents"


@router.get("/templates", response_model=list[CappeTemplateSummary])
async def list_templates(category: str | None = Query(default=None)):
    """List active templates, optionally filtered by category."""
    async with get_connection() as conn:
        if category:
            rows = await conn.fetch(
                f"SELECT {_SUMMARY_COLS} FROM cappe_templates "
                "WHERE is_active = true AND category = $1 ORDER BY name",
                category,
            )
        else:
            rows = await conn.fetch(
                f"SELECT {_SUMMARY_COLS} FROM cappe_templates WHERE is_active = true ORDER BY category, name"
            )
    return [dict(r) for r in rows]


@router.get("/templates/{slug}", response_model=CappeTemplateDetail)
async def get_template(slug: str):
    """Get one active template by slug, including its full structure."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT {_SUMMARY_COLS}, structure FROM cappe_templates "
            "WHERE slug = $1 AND is_active = true",
            slug,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    d = dict(row)
    d["structure"] = loads(row["structure"])
    return d


@router.get("/templates/{slug}/preview", response_class=HTMLResponse)
async def preview_template(slug: str):
    """Render a template's first page to standalone HTML (for gallery previews).

    Public, no auth — drives the live iframe thumbnail in the template gallery.
    Builds the same inputs `render_site_html` gets for a real published site.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT name, structure FROM cappe_templates WHERE slug = $1 AND is_active = true",
            slug,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    structure = loads(row["structure"])
    pages = structure.get("pages") or []
    if not pages:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template has no pages")

    site = {"name": row["name"], "theme_config": structure.get("theme") or {}}
    nav = [{"slug": p.get("slug"), "title": p.get("title")} for p in pages]
    home = next((p for p in pages if p.get("slug") == "home"), pages[0])
    page = {"title": home.get("title"), "slug": home.get("slug"), "content": home.get("content") or {}}
    return HTMLResponse(render_site_html(site, page, nav))
