"""A site's magazine settings (`cappe_magazines`, cappemag02) — owner side,
and a writer's magazine site (cappemag04).

Turning the magazine on is the owner's switch; whether its pages render also
depends on the plan (`services/magazine/magazines.live_magazine`). The
response says both, so the editor can tell an owner "your plan doesn't include
a magazine" instead of showing a switch that does nothing.

A writer account gets its magazine from `POST /magazine/sites`: a
magazine-only site at exactly the handle they chose (`services/magazine/
writers.py`), created under the same account lock and site limit as any site.
"""
import json
from typing import Any, Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeHandleCheck,
    CappeMagazine,
    CappeMagazineSiteCreate,
    CappeMagazineUpdate,
    CappeSite,
)
from ..services.entitlements import resolve_entitlements
from ..services.magazine import pages as mag_pages, reader as mag_reader
from ..services.magazine import writers
from ..services.magazine.magazines import MASTHEADS, get_magazine, save_magazine
from ..services.magazine.stories import POST_COLS, post_row
from ..services.magazine.topics import TOPICS, normalize_topic
from ._shared import get_owned_site, site_row_to_dict
from .render import _front_html, _nav, _site_dict, invalidate_render_cache, tenant_security_headers
from .sites import _SITE_COLS, _enforce_site_limit, _lock_account_for_site_creation

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


# --- A writer's magazine site -------------------------------------------------

@router.get("/magazine/options")
async def magazine_options(account: CappeAccount = Depends(require_cappe_account)):
    """What a new magazine can be: its topics and masthead styles (with the
    fonts each sets), for the writer's onboarding before any site exists."""
    return {
        "topics": [{"key": k, "label": v} for k, v in TOPICS.items()],
        "mastheads": [{"key": k, "heading": h, "body": b} for k, (h, b) in MASTHEADS.items()],
    }


@router.get("/magazine/handle-available", response_model=CappeHandleCheck)
async def handle_available(handle: str = Query(..., max_length=60),
                           account: CappeAccount = Depends(require_cappe_account)):
    """Whether a handle can be a magazine's address, and why not."""
    await check_rate_limit(str(account.id), "cappe_mag_handle", 30, 60)
    wanted = writers.normalize_handle(handle)
    problem = writers.handle_problem(wanted)
    if problem is None:
        async with get_connection() as conn:
            if await writers.handle_taken(conn, wanted):
                problem = writers.TAKEN
    return {"handle": wanted, "available": problem is None, "reason": problem}


@router.post("/magazine/sites", response_model=CappeSite, status_code=status.HTTP_201_CREATED)
async def create_magazine_site(body: CappeMagazineSiteCreate, account: CappeAccount = Depends(require_cappe_account)):
    """A writer's magazine: a site at `<handle>.gummfit.com` whose front page
    is the magazine, with a draft About page. Business accounts turn on a
    magazine from their own site instead."""
    if account.account_type != "writer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Magazine sites are for writer accounts. Turn on a magazine from your site.")
    handle = writers.normalize_handle(body.handle)
    problem = writers.handle_problem(handle)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    topics = [normalize_topic(t) for t in body.topics]
    if any(t is None for t in topics):
        raise HTTPException(status_code=422, detail="Pick the magazine's topics from the list.")
    heading, text = MASTHEADS[body.masthead_style]
    name = body.name.strip()
    async with get_connection() as conn:
        try:
            async with conn.transaction():
                await _lock_account_for_site_creation(conn, account.id)
                await _enforce_site_limit(conn, account)
                if await writers.handle_taken(conn, handle):
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=writers.TAKEN)
                row = await conn.fetchrow(
                    f"""INSERT INTO cappe_sites (account_id, name, slug, subdomain, source_type, theme_config)
                        VALUES ($1, $2, $3, $3, 'magazine', $4::jsonb)
                        RETURNING {_SITE_COLS}""",
                    account.id, name, handle, json.dumps({"fonts": {"heading": heading, "body": text}}),
                )
                await save_magazine(conn, row["id"], {
                    "enabled": True, "name": name, "tagline": (body.tagline or "").strip() or None,
                    "masthead_style": body.masthead_style, "accent": body.accent,
                    "topics": list(dict.fromkeys(topics)), "front_at_root": True,
                }, default_name=name)
                await conn.execute(
                    """INSERT INTO cappe_pages (site_id, title, slug, content, sort_order, status)
                       VALUES ($1, 'About', 'about', '{}', 1, 'draft')""",
                    row["id"],
                )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=writers.TAKEN) from exc
    return site_row_to_dict(row, page_count=1)
