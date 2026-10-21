"""A site's magazine settings (`cappe_magazines`, cappemag02) — owner side,
and a writer's magazine site (cappemag04).

Turning the magazine on is the owner's switch; whether its pages render also
depends on the plan (`services/magazine/magazines.live_magazine`). The
response says both, so the editor can tell an owner "your plan doesn't include
a magazine" instead of showing a switch that does nothing.

A writer account gets its magazine from `POST /magazine/sites`: a
magazine-only site at exactly the handle they chose (`services/magazine/
writers.py`), created under the same account lock and site limit as any site.

Paid subscriptions (cappemag05) are turned on here too: that needs a plan
with `magazine_paid`, a Stripe account that can take charges, and a price.
Turning them off stamps `lapsed_at`; the hourly lapse sweep
(`services/magazine/lapse.py`) then ends each reader's subscription with the
month they paid for. A new price is for new subscribers; readers keep theirs.
"""
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

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
from ..services.magazine import writers
from ..services.magazine.billing import fee_bps
from ..services.magazine.magazines import MASTHEADS, get_magazine, save_magazine
from ..services.magazine.topics import TOPICS, normalize_topic
from ._shared import get_owned_site, site_row_to_dict
from .render import invalidate_render_cache
from .sites import _SITE_COLS, _enforce_site_limit, _lock_account_for_site_creation

router = APIRouter()


async def _view(conn, site, mag: dict | None, plan: str | None) -> dict[str, Any]:
    ent = await resolve_entitlements(plan, conn=conn)
    base = mag or {"site_id": site["id"], "name": site["name"]}
    return {**base, "plan_includes_magazine": ent.has("magazine"),
            "live": bool(mag and mag["enabled"] and ent.has("magazine")),
            "plan_includes_paid": ent.has("magazine_paid"),
            "stripe_ready": await _stripe_ready(conn, site["account_id"]),
            "fee_bps": await fee_bps(conn)}


async def _stripe_ready(conn, account_id) -> bool:
    row = await conn.fetchrow(
        "SELECT stripe_account_id, stripe_charges_enabled FROM cappe_accounts WHERE id = $1", account_id,
    )
    return bool(row and row["stripe_account_id"] and row["stripe_charges_enabled"])


async def _paid_fields(conn, site, fields: dict[str, Any], plan: str | None) -> None:
    """Check and complete the paid-subscription part of an update, in place."""
    current = await get_magazine(conn, site["id"]) or {}
    if isinstance(fields.get("paid_pitch"), str):
        fields["paid_pitch"] = fields["paid_pitch"].strip() or None
    turning_on = fields.get("paid_enabled") is True and not current.get("paid_enabled")
    turning_off = fields.get("paid_enabled") is False and current.get("paid_enabled")
    paid_after = fields.get("paid_enabled", current.get("paid_enabled"))
    if paid_after and not fields.get("price_cents", current.get("price_cents")):
        raise HTTPException(status_code=422, detail="Set a monthly price for paid subscriptions.")
    if turning_on:
        ent = await resolve_entitlements(plan, conn=conn)
        if not ent.has("magazine_paid"):
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail={
                "code": "plan_required", "plan": "writer",
                "message": "Paid subscriptions need the Writer plan (or Creator, Business or Pro)."})
        if not await _stripe_ready(conn, site["account_id"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
                "code": "stripe_required",
                "message": "Connect Stripe and finish its setup first: readers pay into your Stripe account."})
        fields["lapsed_at"] = None
    elif turning_off:
        fields["lapsed_at"] = datetime.now(timezone.utc)


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
    for key in ("enabled", "name", "masthead_style", "topics", "front_at_root", "nav_label", "follow_enabled",
                "paid_enabled", "preview_blocks"):
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
        if fields.keys() & {"paid_enabled", "price_cents", "paid_pitch", "preview_blocks"}:
            await _paid_fields(conn, site, fields, account.plan)
        mag = await save_magazine(conn, site_id, fields, default_name=site["name"])
        view = await _view(conn, site, mag, account.plan)
    await invalidate_render_cache(site_id)
    return view


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
