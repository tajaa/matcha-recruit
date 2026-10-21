"""A site's magazine settings (`cappe_magazines`, cappemag02) — owner side.

Turning the magazine on is the owner's switch; whether its pages render also
depends on the plan (`services/magazine/magazines.live_magazine`). The
response says both, so the editor can tell an owner "your plan doesn't include
a magazine" instead of showing a switch that does nothing.
"""
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeMagazine, CappeMagazineUpdate
from ..services.entitlements import resolve_entitlements
from ..services.magazine.magazines import get_magazine, save_magazine
from ..services.magazine.topics import normalize_topic
from ..services.magazine import pages as mag_pages, reader as mag_reader
from ..services.magazine.stories import POST_COLS, post_row
from ._shared import get_owned_site
from .render import _front_html, _nav, _site_dict, invalidate_render_cache, tenant_security_headers

router = APIRouter()


async def _view(conn, site, mag: dict | None, plan: str | None) -> dict[str, Any]:
    ent = await resolve_entitlements(plan, conn=conn)
    base = mag or {"site_id": site["id"], "name": site["name"]}
    return {**base, "plan_includes_magazine": ent.has("magazine"),
            "live": bool(mag and mag["enabled"] and ent.has("magazine"))}


@router.get("/sites/{site_id}/magazine", response_model=CappeMagazine)
async def get_site_magazine(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """The site's magazine, or its defaults when it has none yet."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        return await _view(conn, site, await get_magazine(conn, site_id), account.plan)


@router.put("/sites/{site_id}/magazine", response_model=CappeMagazine)
async def update_site_magazine(site_id: UUID, body: CappeMagazineUpdate,
                               account: CappeAccount = Depends(require_cappe_account)):
    fields = body.model_dump(exclude_unset=True)
    for key in ("enabled", "name", "masthead_style", "topics", "front_at_root", "nav_label", "follow_enabled"):
        if key in fields and fields[key] is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{key} can't be empty")
    if "topics" in fields:
        topics = [normalize_topic(t) for t in fields["topics"]]
        if any(t is None for t in topics):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Pick the magazine's topics from the list.")
        fields["topics"] = list(dict.fromkeys(topics))
    for key in ("name", "tagline", "about", "nav_label"):
        if isinstance(fields.get(key), str):
            fields[key] = fields[key].strip() or (None if key in ("tagline", "about") else fields[key])
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        if fields.get("cover_post_id"):
            owned = await conn.fetchval("SELECT 1 FROM cappe_posts WHERE id = $1 AND site_id = $2",
                                        fields["cover_post_id"], site_id)
            if not owned:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail="The cover story has to be one of this site's stories.")
        mag = await save_magazine(conn, site_id, fields, default_name=site["name"])
        view = await _view(conn, site, mag, account.plan)
    await invalidate_render_cache(site_id)
    return view


class CappeReaderView(BaseModel):
    """A story by `story_id` or `slug` (a link clicked inside the view); neither
    for the magazine's front."""
    story_id: Optional[UUID] = None
    slug: Optional[str] = Field(default=None, max_length=160)


@router.post("/sites/{site_id}/magazine/view", response_class=HTMLResponse)
async def reader_view(site_id: UUID, body: CappeReaderView, account: CappeAccount = Depends(require_cappe_account)):
    """The magazine as a reader will see it, for its owner: the front, or a
    saved story, rendered by the same code as the public pages. Unlike them it
    shows a site that isn't published, a magazine that's off or not on the
    plan yet, and a story that is still a draft. Nothing here is public: it is
    the owner's own request, never cached. A paid story shows what a reader
    without a subscription sees."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        mag = await get_magazine(conn, site_id) or {"site_id": site_id, "name": site["name"],
                                                    "masthead_style": "classic", "front_at_root": False}
        if body.story_id is None and not body.slug:
            html = await _front_html(conn, site, mag, page=1, host=None)
        else:
            row = await conn.fetchrow(
                f"SELECT {POST_COLS} FROM cappe_posts WHERE site_id = $1 AND "
                + ("id = $2" if body.story_id else "slug = $2"),
                site_id, body.story_id or body.slug,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
            post = post_row(row)
            assets = await mag_reader.story_assets(conn, site_id, post)
            more = await mag_reader.live_stories(conn, site_id, exclude=post["id"], limit=3)
            more_covers = await mag_reader.covers(conn, site_id, more)
            nav = await _nav(conn, site_id)
            html = mag_pages.render_story(_site_dict(site, magazine=mag), nav, mag, post, assets, more=more,
                                          more_covers=more_covers, origin="",
                                          preview_blocks=int(mag.get("preview_blocks") or 3))
    return HTMLResponse(html, headers={**tenant_security_headers(), "Cache-Control": "no-store"})
