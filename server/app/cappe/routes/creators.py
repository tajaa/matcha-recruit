"""Cappe creator self-service — profile (media kit), socials, portfolio, rates,
review submission, media upload, earnings. The public directory lives in
routes/public/creators.py; offers live in routes/collab.py."""
import asyncio
import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ...core.services.redis_cache import check_rate_limit
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount
from ..models.uploads import CappeUploadResponse
from ..models.creators import (
    CreatorPortfolioItem,
    CreatorPortfolioUpsert,
    CreatorProfileCreate,
    CreatorProfileMe,
    CreatorProfileUpdate,
    CreatorRate,
    CreatorRateUpsert,
    CreatorSocial,
    CreatorSocialUpsert,
)
from ..models.collab import EarningsRow
from ..services import upload_guard
from ._shared import build_patch, read_capped
from ..services.common import loads

logger = logging.getLogger("cappe.creators")

router = APIRouter()

_MAX_IMAGE_SOURCE_BYTES = 25 * 1024 * 1024
_MAX_IMAGE_STORED_BYTES = 5 * 1024 * 1024
_MAX_VIDEO_BYTES = 50 * 1024 * 1024


def _require_creator(account: CappeAccount) -> None:
    if account.account_type != "creator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Creator account required")


_PROFILE_COLS = (
    "id, handle, display_name, avatar_url, cover_url, bio, location, niches, languages, "
    "open_to_offers, status, review_note, submitted_at, published_at, "
    "reach_verified, reach_audited_at"
)


async def _load_me(conn, account_id: UUID) -> dict:
    prof = await conn.fetchrow(
        f"SELECT {_PROFILE_COLS} FROM cappe_creator_profiles WHERE account_id = $1", account_id
    )
    if prof is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No creator profile yet")
    d = dict(prof)
    d["socials"] = [
        dict(r)
        for r in await conn.fetch(
            "SELECT id, platform, handle, url, follower_count, engagement_rate, audit_status, "
            "verified_follower_count, audited_at, sort_order FROM cappe_creator_socials "
            "WHERE profile_id = $1 ORDER BY sort_order, created_at",
            prof["id"],
        )
    ]
    portfolio_rows = await conn.fetch(
        "SELECT id, title, description, media_url, media_type, external_url, brand_name, "
        "metrics, sort_order, created_at FROM cappe_creator_portfolio_items "
        "WHERE profile_id = $1 ORDER BY sort_order, created_at",
        prof["id"],
    )
    d["portfolio"] = [{**dict(r), "metrics": loads(r["metrics"]) or {}} for r in portfolio_rows]
    d["rates"] = [
        dict(r)
        for r in await conn.fetch(
            "SELECT id, deliverable_type, platform, price_cents, negotiable, notes, sort_order "
            "FROM cappe_creator_rate_cards WHERE profile_id = $1 ORDER BY sort_order, created_at",
            prof["id"],
        )
    ]
    return d


async def _recompute_reach_verified(conn, profile_id: UUID) -> None:
    """Only safe to call right after every social row for this profile was
    just deleted and reinserted (replace_my_socials' pattern below) — it
    checks audit_status on whatever rows currently exist, so on a path that
    edits socials WITHOUT wiping prior audits first it would incorrectly
    treat a still-flagged social as verified.

    Deliberately does NOT touch reach_audited_at (that's the admin's actual
    last-review timestamp, set only by the per-social audit endpoint) — see
    admin_list_creators' reaudit_due for how a post-audit social edit still
    surfaces in the re-audit queue despite the stale timestamp."""
    verified = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM cappe_creator_socials WHERE profile_id = $1 AND audit_status = 'verified')",
        profile_id,
    )
    await conn.execute(
        "UPDATE cappe_creator_profiles SET reach_verified = $2, updated_at = NOW() WHERE id = $1",
        profile_id, bool(verified),
    )


@router.get("/creators/me", response_model=CreatorProfileMe)
async def get_my_profile(account: CappeAccount = Depends(require_cappe_account)):
    _require_creator(account)
    async with get_connection() as conn:
        return CreatorProfileMe(**await _load_me(conn, account.id))


@router.post("/creators/me", status_code=status.HTTP_201_CREATED, response_model=CreatorProfileMe)
async def create_my_profile(
    body: CreatorProfileCreate, account: CappeAccount = Depends(require_cappe_account)
):
    _require_creator(account)
    async with get_connection() as conn:
        try:
            await conn.execute(
                "INSERT INTO cappe_creator_profiles (account_id, handle, display_name) "
                "VALUES ($1, $2, $3)",
                account.id, body.handle, body.display_name,
            )
        except asyncpg.UniqueViolationError as exc:
            constraint = getattr(exc, "constraint_name", "") or ""
            if "handle" in constraint:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Handle is taken")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile already exists")
        return CreatorProfileMe(**await _load_me(conn, account.id))


@router.patch("/creators/me", response_model=CreatorProfileMe)
async def update_my_profile(
    body: CreatorProfileUpdate, account: CappeAccount = Depends(require_cappe_account)
):
    _require_creator(account)
    async with get_connection() as conn:
        sets, args = build_patch(
            body,
            ["display_name", "avatar_url", "cover_url", "bio", "location",
             "niches", "languages", "open_to_offers"],
            nullable={"avatar_url", "cover_url", "bio", "location"},
        )
        if sets:
            sets.append("updated_at = NOW()")
            args.append(account.id)
            await conn.execute(
                f"UPDATE cappe_creator_profiles SET {', '.join(sets)} WHERE account_id = ${len(args)}",
                *args,
            )
        return CreatorProfileMe(**await _load_me(conn, account.id))


@router.post("/creators/me/submit", response_model=CreatorProfileMe)
async def submit_my_profile(account: CappeAccount = Depends(require_cappe_account)):
    _require_creator(account)
    async with get_connection() as conn:
        prof = await conn.fetchrow(
            "SELECT id, status, bio FROM cappe_creator_profiles WHERE account_id = $1", account.id
        )
        if prof is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No creator profile yet")
        if prof["status"] not in ("draft", "rejected"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Profile is not in a submittable state")
        social_count = await conn.fetchval(
            "SELECT COUNT(*) FROM cappe_creator_socials WHERE profile_id = $1", prof["id"]
        )
        portfolio_count = await conn.fetchval(
            "SELECT COUNT(*) FROM cappe_creator_portfolio_items WHERE profile_id = $1", prof["id"]
        )
        if social_count < 1 or not ((prof["bio"] or "").strip() or portfolio_count >= 1):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Add at least one social account and a bio or portfolio item first",
            )
        await conn.execute(
            "UPDATE cappe_creator_profiles SET status='pending_review', submitted_at=NOW(), "
            "review_note=NULL, updated_at=NOW() WHERE id = $1",
            prof["id"],
        )
        return CreatorProfileMe(**await _load_me(conn, account.id))


@router.put("/creators/me/socials", response_model=list[CreatorSocial])
async def replace_my_socials(
    body: list[CreatorSocialUpsert], account: CappeAccount = Depends(require_cappe_account)
):
    _require_creator(account)
    if len(body) > 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Max 12 socials")
    async with get_connection() as conn:
        prof = await conn.fetchrow("SELECT id FROM cappe_creator_profiles WHERE account_id = $1", account.id)
        if prof is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No creator profile yet")
        try:
            async with conn.transaction():
                await conn.execute("DELETE FROM cappe_creator_socials WHERE profile_id = $1", prof["id"])
                for s in body:
                    await conn.execute(
                        "INSERT INTO cappe_creator_socials "
                        "(profile_id, platform, handle, url, follower_count, engagement_rate, sort_order) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                        prof["id"], s.platform, s.handle, s.url, s.follower_count, s.engagement_rate, s.sort_order,
                    )
                # Any social edit resets audits — simplest correct rule. After a
                # replace-all every row is fresh/unverified, so reach_verified
                # always goes false here.
                await _recompute_reach_verified(conn, prof["id"])
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Duplicate social URL")
        rows = await conn.fetch(
            "SELECT id, platform, handle, url, follower_count, engagement_rate, audit_status, "
            "verified_follower_count, audited_at, sort_order FROM cappe_creator_socials "
            "WHERE profile_id = $1 ORDER BY sort_order, created_at",
            prof["id"],
        )
        return [CreatorSocial(**dict(r)) for r in rows]


@router.put("/creators/me/portfolio", response_model=list[CreatorPortfolioItem])
async def replace_my_portfolio(
    body: list[CreatorPortfolioUpsert], account: CappeAccount = Depends(require_cappe_account)
):
    _require_creator(account)
    if len(body) > 24:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Max 24 portfolio items")
    for item in body:
        if not (item.media_url or item.external_url):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Each portfolio item needs media_url or external_url")
    async with get_connection() as conn:
        prof = await conn.fetchrow("SELECT id FROM cappe_creator_profiles WHERE account_id = $1", account.id)
        if prof is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No creator profile yet")
        async with conn.transaction():
            await conn.execute("DELETE FROM cappe_creator_portfolio_items WHERE profile_id = $1", prof["id"])
            for it in body:
                await conn.execute(
                    "INSERT INTO cappe_creator_portfolio_items "
                    "(profile_id, title, description, media_url, media_type, external_url, "
                    "brand_name, metrics, sort_order) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                    prof["id"], it.title, it.description, it.media_url, it.media_type,
                    it.external_url, it.brand_name, json.dumps(it.metrics), it.sort_order,
                )
        rows = await conn.fetch(
            "SELECT id, title, description, media_url, media_type, external_url, brand_name, "
            "metrics, sort_order, created_at FROM cappe_creator_portfolio_items "
            "WHERE profile_id = $1 ORDER BY sort_order, created_at",
            prof["id"],
        )
        return [CreatorPortfolioItem(**{**dict(r), "metrics": loads(r["metrics"]) or {}}) for r in rows]


@router.put("/creators/me/rates", response_model=list[CreatorRate])
async def replace_my_rates(
    body: list[CreatorRateUpsert], account: CappeAccount = Depends(require_cappe_account)
):
    _require_creator(account)
    if len(body) > 20:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Max 20 rates")
    async with get_connection() as conn:
        prof = await conn.fetchrow("SELECT id FROM cappe_creator_profiles WHERE account_id = $1", account.id)
        if prof is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No creator profile yet")
        try:
            async with conn.transaction():
                await conn.execute("DELETE FROM cappe_creator_rate_cards WHERE profile_id = $1", prof["id"])
                for r in body:
                    await conn.execute(
                        "INSERT INTO cappe_creator_rate_cards "
                        "(profile_id, deliverable_type, platform, price_cents, negotiable, notes, sort_order) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                        prof["id"], r.deliverable_type, r.platform, r.price_cents,
                        r.negotiable, r.notes, r.sort_order,
                    )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Duplicate rate for the same deliverable and platform")
        rows = await conn.fetch(
            "SELECT id, deliverable_type, platform, price_cents, negotiable, notes, sort_order "
            "FROM cappe_creator_rate_cards WHERE profile_id = $1 ORDER BY sort_order, created_at",
            prof["id"],
        )
        return [CreatorRate(**dict(r)) for r in rows]


@router.post("/creators/me/upload", response_model=CappeUploadResponse)
async def upload_creator_media(
    file: UploadFile = File(...), account: CappeAccount = Depends(require_cappe_account)
):
    """Used for avatar, cover, portfolio media, deliverable proof. No
    `cappe_assets` record — that catalog is site-scoped and creators have no
    site."""
    _require_creator(account)
    # No S3 storage quota on this path (unlike site assets, a creator has no
    # site to cap by) — a per-account request rate limit is the only backstop
    # against unbounded upload volume/cost.
    await check_rate_limit(str(account.id), "cappe_creator_upload", 30, 3600)
    if file.content_type in upload_guard.ALLOWED_IMAGE:
        allowed = upload_guard.ALLOWED_IMAGE
        data = await read_capped(file, _MAX_IMAGE_SOURCE_BYTES, "Image too large (max 25 MB)")
    elif file.content_type in upload_guard.ALLOWED_VIDEO:
        allowed = upload_guard.ALLOWED_VIDEO
        data = await read_capped(file, _MAX_VIDEO_BYTES, "Video too large (max 50 MB)")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    content_type = upload_guard.verify_upload(data, file.content_type, allowed)
    filename = file.filename or "upload"
    if content_type in upload_guard.ALLOWED_IMAGE:
        data, content_type, filename = await asyncio.to_thread(
            upload_guard.compress_image_for_storage,
            data,
            content_type,
            filename,
            max_bytes=_MAX_IMAGE_STORED_BYTES,
        )
    url = await get_storage().upload_file(
        file_bytes=data, filename=filename, prefix="cappe", content_type=content_type,
    )
    return CappeUploadResponse(url=url)


@router.get("/creators/me/earnings", response_model=list[EarningsRow])
async def my_earnings(account: CappeAccount = Depends(require_cappe_account)):
    _require_creator(account)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT p.offer_id, o.title AS offer_title, ba.name AS brand_name, p.label,
                      p.amount_cents, p.fee_cents, p.status, p.paid_at
                 FROM cappe_collab_payments p
                 JOIN cappe_collab_offers o ON o.id = p.offer_id
                 JOIN cappe_creator_profiles cp ON cp.id = o.creator_profile_id
                 JOIN cappe_accounts ba ON ba.id = o.brand_account_id
                WHERE cp.account_id = $1
                ORDER BY COALESCE(p.paid_at, p.due_at, p.created_at) DESC""",
            account.id,
        )
        return [EarningsRow(**dict(r)) for r in rows]
