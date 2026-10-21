"""A site's magazine settings (`cappe_magazines`, cappemag02) — owner side.

Turning the magazine on is the owner's switch; whether its pages render also
depends on the plan (`services/magazine/magazines.live_magazine`). The
response says both, so the editor can tell an owner "your plan doesn't include
a magazine" instead of showing a switch that does nothing.
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeMagazine, CappeMagazineUpdate
from ..services.entitlements import resolve_entitlements
from ..services.magazine.magazines import get_magazine, save_magazine
from ..services.magazine.topics import normalize_topic
from ._shared import get_owned_site
from .render import invalidate_render_cache

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
