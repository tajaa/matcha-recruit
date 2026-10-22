"""Cappe social growth — the owner's side.

Everything under `/sites/{site_id}/social/*`, each route on
`require_cappe_account` + site ownership. Plan gates: `social` for posting and
scheduling, `social_video` for dropped videos, `social_autoreply` for the AI
inbox (turning the mode on, asking for a draft). The Meta OAuth callback and
the webhook are public routes in `routes/public/social_meta.py`.

A video is uploaded by the browser straight to S3 (`assets/presign`, then
`assets/{id}/complete`), cut to size on the worker, and named in a post's
media by its `asset_id`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from ...core.services.redis_cache import check_rate_limit
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeSocialAsset,
    CappeSocialAssetPresign,
    CappeSocialAssetUpload,
    CappeSocialCaptionRequest,
    CappeSocialCaptions,
    CappeSocialConnection,
    CappeSocialConnections,
    CappeSocialConnectStart,
    CappeSocialInboxItem,
    CappeSocialOverview,
    CappeSocialPost,
    CappeSocialPostInput,
    CappeSocialPostUpdate,
    CappeSocialReplyInput,
    CappeSocialSettings,
    CappeSocialSettingsUpdate,
    CappeSocialUpload,
)
from ..services.common import site_public_origin
from ..services.email import app_origin
from ..services.entitlements import resolve_entitlements
from ..services import cappe_assets, upload_guard
from ..services.social import ai as social_ai
from ..services.social import assets as asset_store
from ..services.social import autoreply, captions, oauth
from ..services.social import connections as conn_store
from ..services.social import inbox as inbox_store
from ..services.social import media as social_media
from ..services.social import outbound
from ..services.social import posts as post_store
from ..services.social.providers import meta
from ..services.social.providers.base import ProviderError
from ._shared import get_owned_site, read_capped

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sites/{site_id}/social")

# Schedules further out than this are a typo, not a plan.
MAX_SCHEDULE_AHEAD = timedelta(days=365)
# Phone photos run large; the stored JPEG is bounded by services/social/media.py.
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# Caption drafting is a real model call per click.
_CAPTIONS_PER_HOUR = 30
_DRAFTS_PER_HOUR = 60
_VIDEO_UPLOADS_PER_HOUR = 30


def _social_gate(ent) -> None:
    if not ent.has("social"):
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail="Social posting isn't included in your plan.")


def _video_gate(ent) -> None:
    if not ent.has("social_video"):
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail="Video posts are part of the Business, Pro and Creator plans.")


def _autoreply_gate(ent) -> None:
    if not ent.has("social_autoreply"):
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail="AI replies are part of the Business and Creator plans.")


def _meta_config() -> meta.MetaConfig:
    cfg = meta.MetaConfig.from_settings()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Instagram and Facebook aren't set up on this server yet.")
    return cfg


def oauth_redirect_uri() -> str:
    """Where Meta sends the browser back; must match the app's allowed list."""
    return f"{app_origin()}/api/cappe/public/social/meta/callback"


def site_zone(site) -> ZoneInfo:
    try:
        return ZoneInfo(str((site or {}).get("timezone") or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def check_schedule(when: Optional[datetime], tz: ZoneInfo | timezone = timezone.utc) -> Optional[datetime]:
    """A schedule must be in the future (a minute's grace for clock skew)
    and within a year. A time with no zone is the site's wall-clock time
    (`tz`). Returns it as an aware UTC datetime."""
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    now = datetime.now(timezone.utc)
    if when < now - timedelta(minutes=1):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="That time has already passed")
    if when > now + MAX_SCHEDULE_AHEAD:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Schedule within the next year")
    return when.astimezone(timezone.utc)


async def _checked_media(conn, site_id: UUID, items, ent) -> list[dict]:
    """The post's media as stored: a photo by its URL, a video by its asset
    (this site's, uploaded, not failed — and the plan must include video)."""
    media: list[dict] = []
    for item in items:
        if item.kind == "video":
            media.append({"kind": "video", "asset_id": str(item.asset_id), "alt": item.alt})
        else:
            media.append({"kind": "image", "url": item.url, "alt": item.alt})
    video_ids = [m["asset_id"] for m in media if m["kind"] == "video"]
    if not video_ids:
        return media
    _video_gate(ent)
    found = await asset_store.load_many(conn, video_ids)
    for asset_id in video_ids:
        asset = found.get(asset_id)
        if asset is None or asset["site_id"] != site_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
        if asset["status"] in ("failed", "deleted"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=asset["error"] or "That video couldn't be prepared — upload it again")
        if asset["status"] == "uploading":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="That video hasn't finished uploading")
    return media


async def _own_connections(conn, site_id: UUID, connection_ids: list[UUID]) -> list[dict]:
    """The site's connections for these ids, 404 if any isn't the site's."""
    if not connection_ids:
        return []
    rows = await conn_store.list_connections(conn, site_id)
    by_id = {r["id"]: r for r in rows}
    missing = [c for c in connection_ids if c not in by_id]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return [by_id[c] for c in connection_ids]


# ── overview / accounts ─────────────────────────────────────────────────────

@router.get("/overview", response_model=CappeSocialOverview)
async def overview(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        connections = await conn_store.list_connections(conn, site_id)
        row = await conn.fetchrow(
            """SELECT count(*) FILTER (WHERE status = 'scheduled') AS scheduled,
                      count(*) FILTER (WHERE status IN ('published', 'partial')
                                         AND published_at > NOW() - INTERVAL '30 days') AS published_30d
               FROM cappe_social_posts WHERE site_id = $1""",
            site_id,
        )
        inbox_counts = await inbox_store.counts(conn, site_id)
        settings = await inbox_store.get_settings(conn, site_id)
    return CappeSocialOverview(
        connections=len(connections),
        scheduled=int(row["scheduled"] or 0) if row else 0,
        published_30d=int(row["published_30d"] or 0) if row else 0,
        inbox_new=inbox_counts["new"],
        drafts_waiting=inbox_counts["waiting"],
        followers=[{"platform": c["platform"], "handle": c["handle"] or c["display_name"],
                    "followers_count": c["followers_count"]} for c in connections],
        autoreply_mode=settings["autoreply_mode"],
        meta_configured=meta.configured(),
        ai_available=await social_ai.available(),
    )


@router.get("/connections", response_model=CappeSocialConnections)
async def list_connections(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn_store.list_connections(conn, site_id)
    return CappeSocialConnections(configured=meta.configured(),
                                  connections=[CappeSocialConnection(**r) for r in rows])


@router.post("/connections/meta/start", response_model=CappeSocialConnectStart)
async def start_meta_connect(
    site_id: UUID, response: Response, account: CappeAccount = Depends(require_cappe_account),
):
    """The Facebook Login URL for this site. The signed state brings the
    browser back to the right site on the public callback, and the nonce
    cookie set here makes sure it is this browser (see services/social/oauth)."""
    cfg = _meta_config()
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
    _social_gate(ent)
    nonce = oauth.new_nonce()
    # Lax, not Strict: the callback is a top-level navigation back from
    # facebook.com, which Strict would strip the cookie from.
    response.set_cookie(
        oauth.NONCE_COOKIE, nonce, max_age=oauth.STATE_TTL_SECONDS, path=oauth.NONCE_COOKIE_PATH,
        httponly=True, secure=True, samesite="lax",
    )
    state = oauth.make_state(site_id, account.id, nonce)
    return CappeSocialConnectStart(authorize_url=meta.authorize_url(cfg, redirect_uri=oauth_redirect_uri(), state=state))


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(site_id: UUID, connection_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Forget the account and its token. Scheduled targets on it go with it
    (cascade); the inbox rows do too."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        if not await conn_store.delete_connection(conn, site_id, connection_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")


# ── settings ────────────────────────────────────────────────────────────────

async def _settings_view(conn, site_id: UUID, ent) -> CappeSocialSettings:
    row = await inbox_store.get_settings(conn, site_id)
    return CappeSocialSettings(**row, autoreply_available=ent.has("social_autoreply"),
                               video_available=ent.has("social_video"), ai_available=await social_ai.available())


@router.get("/settings", response_model=CappeSocialSettings)
async def get_settings(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        return await _settings_view(conn, site_id, ent)


@router.put("/settings", response_model=CappeSocialSettings)
async def update_settings(
    site_id: UUID, body: CappeSocialSettingsUpdate, account: CappeAccount = Depends(require_cappe_account),
):
    fields = body.model_dump(exclude_unset=True)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        # Gate only a change of mode: a downgraded owner whose stored mode is
        # still review/auto can save tone, notes and hashtags (the form sends
        # the stored mode back), and the worker re-checks the plan anyway.
        if fields.get("autoreply_mode") in ("review", "auto"):
            stored = await inbox_store.get_settings(conn, site_id)
            if fields["autoreply_mode"] != (stored or {}).get("autoreply_mode"):
                _autoreply_gate(ent)
        if fields:
            await inbox_store.upsert_settings(conn, site_id, fields)
        return await _settings_view(conn, site_id, ent)


# ── posts ───────────────────────────────────────────────────────────────────

def _post_view(post: dict) -> CappeSocialPost:
    return CappeSocialPost(**post)


@router.get("/posts", response_model=list[CappeSocialPost])
async def list_posts(
    site_id: UUID,
    status_filter: Optional[str] = Query(default=None, alias="status",
                                         pattern="^(draft|scheduled|rendering|publishing|published|partial|failed|cancelled)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        posts = await post_store.list_posts(conn, site_id, status=status_filter, limit=limit, offset=offset)
    return [_post_view(p) for p in posts]


@router.post("/posts", response_model=CappeSocialPost, status_code=status.HTTP_201_CREATED)
async def create_post(site_id: UUID, body: CappeSocialPostInput, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        when = check_schedule(body.scheduled_at, site_zone(site))
        ent = await resolve_entitlements(account.plan, conn=conn)
        _social_gate(ent)
        media = await _checked_media(conn, site_id, body.media, ent)
        targets = await _own_connections(conn, site_id, body.connection_ids)
        if when and not targets:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Pick at least one account to post to")
        reason = post_store.validate_for_targets(body.caption, media, [t["platform"] for t in targets]) if targets else None
        if when and reason:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=reason)
        async with conn.transaction():
            post = await post_store.create_post(
                conn, site_id=site_id, caption=body.caption, media=media, link_url=body.link_url,
                product_id=body.product_id, scheduled_at=when,
                ai_meta={"alt_text": body.alt_text} if body.alt_text else {},
            )
            await post_store.set_targets(conn, post["id"], [t["id"] for t in targets], due_at=when)
        post = await post_store.get_post(conn, site_id, post["id"])
    return _post_view(post)


@router.get("/posts/{post_id}", response_model=CappeSocialPost)
async def get_post(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        post = await post_store.get_post(conn, site_id, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return _post_view(post)


@router.patch("/posts/{post_id}", response_model=CappeSocialPost)
async def update_post(
    site_id: UUID, post_id: UUID, body: CappeSocialPostUpdate, account: CappeAccount = Depends(require_cappe_account),
):
    """Edit a draft, a scheduled post or a failed one. Sending `scheduled_at`
    reschedules; sending it as null returns the post to drafts."""
    fields = body.model_dump(exclude_unset=True)
    connection_ids = fields.pop("connection_ids", None)
    reschedule = "scheduled_at" in fields
    scheduled_at = fields.pop("scheduled_at", None)
    alt_text = fields.pop("alt_text", None)
    if "caption" in fields and fields["caption"] is None:
        fields["caption"] = ""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        when = check_schedule(scheduled_at, site_zone(site)) if reschedule else None
        if "media" in fields:
            ent = await resolve_entitlements(account.plan, conn=conn)
            fields["media"] = await _checked_media(conn, site_id, body.media or [], ent)
        current = await post_store.get_post(conn, site_id, post_id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        if current["status"] not in post_store.OPEN_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"A {current['status']} post can't be edited")
        if alt_text is not None:
            fields["ai_meta"] = {**current["ai_meta"], "alt_text": alt_text}
        targets = (await _own_connections(conn, site_id, connection_ids)
                   if connection_ids is not None else [{"id": t["connection_id"], "platform": t["platform"]}
                                                       for t in current["targets"]])
        caption = fields.get("caption", current["caption"])
        media = fields.get("media", current["media"])
        effective_when = when if reschedule else current["scheduled_at"]
        if effective_when:
            if not targets:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail="Pick at least one account to post to")
            reason = post_store.validate_for_targets(caption, media, [t["platform"] for t in targets])
            if reason:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=reason)
        async with conn.transaction():
            await post_store.update_post(conn, site_id, post_id, fields)
            if connection_ids is not None:
                await post_store.set_targets(conn, post_id, [t["id"] for t in targets], due_at=effective_when)
            if reschedule:
                await post_store.set_schedule(conn, site_id, post_id, when)
        post = await post_store.get_post(conn, site_id, post_id)
    return _post_view(post)


@router.post("/posts/{post_id}/publish", response_model=CappeSocialPost)
async def publish_post(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Post now. The targets are due immediately and the publisher runs for
    this post; the row comes back `publishing` until it reports."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        _social_gate(ent)
        current = await post_store.get_post(conn, site_id, post_id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        # `partial` is a retry: only the targets that didn't go out are re-tried.
        if current["status"] not in (*post_store.OPEN_STATUSES, "partial"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Post is already {current['status']}")
        if not current["targets"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Pick at least one account to post to")
        reason = post_store.validate_for_targets(current["caption"], current["media"],
                                                 [t["platform"] for t in current["targets"] if t["status"] != "published"])
        if reason:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=reason)
        _meta_config()
        await post_store.publish_now(conn, site_id, post_id)
        post = await post_store.get_post(conn, site_id, post_id)
    try:
        from app.workers.tasks.cappe_social_publisher import run_cappe_social_publish_post

        run_cappe_social_publish_post.delay(str(post_id))
    except Exception:  # noqa: BLE001 — the minute sweep picks it up when the broker is down
        logger.warning("cappe social: could not dispatch publish for %s; the sweep will", post_id, exc_info=True)
    return _post_view(post)


@router.post("/posts/{post_id}/cancel", response_model=CappeSocialPost)
async def cancel_post(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        if not await post_store.cancel_post(conn, site_id, post_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Only a post that hasn't gone out can be cancelled")
        post = await post_store.get_post(conn, site_id, post_id)
    return _post_view(post)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        if not await post_store.delete_post(conn, site_id, post_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="A published post stays as the record of what went out")


@router.post("/media", response_model=CappeSocialUpload)
async def upload_media(
    site_id: UUID, file: UploadFile = File(...), account: CappeAccount = Depends(require_cappe_account),
):
    """One dropped photo, normalized for every network (JPEG, ≤1440 px,
    padded into Instagram's ratio range — see services/social/media.py) and
    added to the site's asset library."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
    _social_gate(ent)
    if file.content_type not in upload_guard.ALLOWED_IMAGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Photos only (JPG, PNG, WebP or GIF)")
    data = await read_capped(file, _MAX_UPLOAD_BYTES, "Photo too large (max 20 MB)")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    upload_guard.verify_upload(data, file.content_type, upload_guard.ALLOWED_IMAGE)
    prepared = await asyncio.to_thread(social_media.prepare_image, data)
    stem = (file.filename or "photo").rsplit(".", 1)[0] or "photo"
    url = await get_storage().upload_file(
        file_bytes=prepared.data, filename=f"{stem}.jpg", prefix="cappe/social", content_type="image/jpeg",
    )
    try:
        async with get_connection() as conn:
            await cappe_assets.record(conn, account_id=account.id, site_id=site["id"], kind="upload", url=url)
    except Exception as exc:  # noqa: BLE001 — catalog bookkeeping never fails the upload
        logger.warning("cappe asset catalog insert failed (social): %s", exc)
    return CappeSocialUpload(url=url, width=prepared.width, height=prepared.height, padded=prepared.padded)


# ── videos ──────────────────────────────────────────────────────────────────

def _asset_view(asset: dict) -> CappeSocialAsset:
    return CappeSocialAsset(**asset_store.public_view(asset))


@router.post("/assets/presign", response_model=CappeSocialAssetUpload, status_code=status.HTTP_201_CREATED)
async def presign_video(site_id: UUID, body: CappeSocialAssetPresign, account: CappeAccount = Depends(require_cappe_account)):
    """Start a video upload. The browser posts the file straight to storage
    (pinned to the size given here), then calls `…/complete`."""
    await check_rate_limit(str(account.id), "cappe_social_video_upload", _VIDEO_UPLOADS_PER_HOUR, 3600)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        _social_gate(ent)
        _video_gate(ent)
        try:
            upload = asset_store.presign_upload(site_id, body.filename, body.content_type, body.size)
        except asset_store.AssetStorageUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        asset = await asset_store.create(conn, site_id=site_id, account_id=account.id, filename=body.filename,
                                         path=upload["path"], content_type=body.content_type, size=body.size)
    return CappeSocialAssetUpload(asset_id=asset["id"], upload_url=upload["upload_url"], fields=upload["fields"],
                                  max_bytes=asset_store.MAX_VIDEO_BYTES)


@router.post("/assets/{asset_id}/complete", response_model=CappeSocialAsset)
async def complete_video(site_id: UUID, asset_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """The upload finished: check what landed, then queue the cut. Storage
    is checked with no pooled connection held."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        asset = await asset_store.get(conn, site_id, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if asset["status"] != "uploading":
        return _asset_view(asset)
    try:
        problem = await asset_store.verify_upload(asset)
    except asset_store.AssetStorageUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    async with get_connection() as conn:
        if problem:
            await asset_store.mark_failed(conn, asset_id, problem)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)
        await asset_store.mark_rendering(conn, asset_id)
        asset = await asset_store.get(conn, site_id, asset_id)
    try:
        from app.workers.tasks.cappe_social_media import render_cappe_social_video

        render_cappe_social_video.delay(str(asset_id))
    except Exception:  # noqa: BLE001 — the media sweep re-queues a render that never started
        logger.warning("cappe social: could not queue the render for %s; the sweep will", asset_id, exc_info=True)
    return _asset_view(asset)


@router.get("/assets/{asset_id}", response_model=CappeSocialAsset)
async def get_video(site_id: UUID, asset_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        asset = await asset_store.get(conn, site_id, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return _asset_view(asset)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(site_id: UUID, asset_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Drop a video no post uses (removed from the composer)."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        deleted = await asset_store.delete(conn, site_id, asset_id)
        if deleted is None:
            exists = await asset_store.get(conn, site_id, asset_id)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT if exists else status.HTTP_404_NOT_FOUND,
                                detail="A post uses this video" if exists else "Video not found")
    await asset_store.delete_files(deleted)


@router.post("/captions", response_model=CappeSocialCaptions)
async def draft_captions(site_id: UUID, body: CappeSocialCaptionRequest, account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_social_captions", _CAPTIONS_PER_HOUR, 3600)
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        _social_gate(ent)
        settings = await inbox_store.get_settings(conn, site_id)
        product = None
        if body.product_id:
            row = await conn.fetchrow(
                "SELECT name, description, price_cents, currency FROM cappe_products WHERE id = $1 AND site_id = $2",
                body.product_id, site_id,
            )
            product = dict(row) if row else None
    try:
        result = await captions.draft_captions(
            site_name=site["name"], media_urls=[m.url for m in body.media], product=product, brief=body.brief,
            tone=body.tone or settings["tone"], default_hashtags=settings["default_hashtags"],
            store_url=site_public_origin(site),
        )
    except social_ai.AiUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except (RuntimeError, ValueError) as exc:
        logger.warning("cappe social captions failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Couldn't write captions just now — try again in a moment.")
    return CappeSocialCaptions(**result)


# ── inbox ───────────────────────────────────────────────────────────────────

def _item_view(item: dict) -> CappeSocialInboxItem:
    return CappeSocialInboxItem(**item)


@router.get("/inbox", response_model=list[CappeSocialInboxItem])
async def list_inbox(
    site_id: UUID,
    status_filter: Optional[str] = Query(default=None, alias="status",
                                         pattern="^(new|drafted|replied|skipped|escalated)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        items = await inbox_store.list_inbox(conn, site_id, status=status_filter, limit=limit, offset=offset)
    return [_item_view(i) for i in items]


@router.post("/inbox/{inbox_id}/draft", response_model=CappeSocialInboxItem)
async def draft_for_item(site_id: UUID, inbox_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Ask for a draft reply on demand. Never sends. The model call runs with
    no pooled connection held."""
    await check_rate_limit(str(account.id), "cappe_social_drafts", _DRAFTS_PER_HOUR, 3600)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        _autoreply_gate(ent)
        item = await inbox_store.get_item(conn, site_id, inbox_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        settings = await inbox_store.get_settings(conn, site_id)
        grounding = await autoreply.load_grounding(conn, site_id)
    model = await social_ai.model_for("reply")
    if not model:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Reply drafting needs Claude; ask your admin to set ANTHROPIC_API_KEY")
    try:
        draft = await autoreply.draft_reply(item, grounding, settings, model=model)
    except (RuntimeError, ValueError) as exc:
        logger.warning("cappe social draft failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Couldn't draft a reply just now — try again in a moment.")
    classification = {"intent": draft.intent, "sentiment": draft.sentiment, "confidence": draft.confidence,
                      "needs_human": draft.needs_human, "model": model}
    next_status = "drafted" if draft.reply and not draft.needs_human else "escalated"
    async with get_connection() as conn:
        if draft.reply:
            await inbox_store.create_reply(conn, inbox_id=inbox_id, site_id=site_id, body=draft.reply, mode="approved",
                                           status="draft", model=model,
                                           grounding={"facts_used": draft.facts_used, "decision": "draft"})
        if item["status"] in ("new", "drafted", "escalated"):
            await inbox_store.set_item_status(conn, inbox_id, next_status, classification)
        item = await inbox_store.get_item(conn, site_id, inbox_id)
    return _item_view(item)


@router.post("/inbox/{inbox_id}/reply", response_model=CappeSocialInboxItem)
async def reply_to_item(
    site_id: UUID, inbox_id: UUID, body: CappeSocialReplyInput, account: CappeAccount = Depends(require_cappe_account),
):
    """Send a reply now: the owner's words, or an approved draft (edited or
    not). The reply row is written `sending` before the network call, which
    runs with no pooled connection held."""
    cfg = _meta_config()
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        item = await inbox_store.get_item(conn, site_id, inbox_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        try:
            cred = await outbound.reply_credentials(conn, item)
        except ProviderError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        # One row per thing sent. An unedited draft carries its own send; an
        # edited one is rejected and the edit is a new 'approved' row; the
        # owner's own words are 'manual'.
        reply = None
        mode = "manual"
        if body.reply_id:
            draft = await inbox_store.get_reply(conn, site_id, body.reply_id)
            if draft is None or draft["inbox_id"] != inbox_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
            if draft["status"] == "draft":
                mode = "approved"
                if draft["body"] == body.body:
                    if not await inbox_store.claim_draft(conn, draft["id"]):
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                            detail="That reply is already being sent")
                    reply = draft
                else:
                    await inbox_store.mark_reply(conn, draft["id"], status="rejected")
        if reply is None:
            reply = await inbox_store.create_reply(conn, inbox_id=inbox_id, site_id=site_id, body=body.body, mode=mode,
                                                   status="sending", model=None, grounding={"by": "owner"})
    try:
        sent_id = await outbound.send_with(cfg, cred, item, body.body)
    except ProviderError as exc:
        async with get_connection() as conn:
            await inbox_store.mark_reply(conn, reply["id"], status="failed", error=str(exc)[:500])
            await outbound.note_send_failure(conn, cred, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Couldn't send: {exc}")
    async with get_connection() as conn:
        await inbox_store.mark_reply(conn, reply["id"], status="sent", external_reply_id=sent_id)
        await inbox_store.set_item_status(conn, inbox_id, "replied")
        item = await inbox_store.get_item(conn, site_id, inbox_id)
    return _item_view(item)


@router.post("/inbox/{inbox_id}/skip", response_model=CappeSocialInboxItem)
async def skip_item(site_id: UUID, inbox_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        item = await inbox_store.get_item(conn, site_id, inbox_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        for reply in item["replies"]:
            if reply["status"] == "draft":
                await inbox_store.mark_reply(conn, reply["id"], status="rejected")
        await inbox_store.set_item_status(conn, inbox_id, "skipped", {"skipped_by": "owner"})
        item = await inbox_store.get_item(conn, site_id, inbox_id)
    return _item_view(item)


__all__ = ["router", "oauth_redirect_uri", "check_schedule", "site_zone", "MAX_SCHEDULE_AHEAD"]
