"""Tell-Us public feedback intake (no auth — resolved by link token).

The consumer-facing QR/link flow: fetch the form config, presign media straight
to the private S3 bucket, then submit. A logged-in consumer's bearer token (if
present) links `reporter_account_id` so the feedback can earn points; anonymous
submissions still land (0 points). Honeypot + layered rate limits, mirroring
`matcha/routes/inbound_email.py`.
"""
import logging
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...core.services.storage import get_storage
from ...database import get_connection
from ..models.tellus import (
    TellusFeedbackSubmit,
    TellusFeedbackSubmitResponse,
    TellusIntakeConfig,
    TellusMediaPresignRequest,
    TellusMediaPresignResponse,
)
from ..services.auth import decode_tellus_token
from ..services.email import send_tellus_feedback_alert_email
from ..services.feedback_service import create_report

logger = logging.getLogger(__name__)

router = APIRouter()

_CATEGORIES = ["service", "cleanliness", "facilities", "safety", "compliment", "other"]

_ALLOWED_PHOTO = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif"}
_ALLOWED_VIDEO = {"video/mp4", "video/webm", "video/quicktime"}
_MAX_PHOTO_BYTES = 10 * 1024 * 1024      # 10 MB
_MAX_VIDEO_BYTES = 200 * 1024 * 1024     # 200 MB (direct-to-S3, bypasses nginx)
_MAX_MEDIA_PER_REPORT = 6


async def _optional_account_id(authorization: Optional[str]) -> Optional[UUID]:
    """Resolve a consumer account_id from a bearer token if one is present and
    valid; otherwise None (anonymous). Never raises — auth is optional here."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    payload = decode_tellus_token(authorization.split(" ", 1)[1].strip(), expected_type="access")
    if payload is None:
        return None
    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    async with get_connection() as conn:
        ok = await conn.fetchval(
            "SELECT 1 FROM tellus_accounts WHERE id = $1 AND status = 'active' AND account_type = 'consumer'",
            account_id,
        )
    return account_id if ok else None


async def _resolve_link(conn, token: str) -> dict:
    """Look up a link + brand/store, 404/410 on invalid/inactive/exhausted.
    Does NOT increment use_count (read-only)."""
    row = await conn.fetchrow(
        """SELECT l.id, l.brand_id, l.store_id, l.is_active, l.expires_at,
                  l.max_uses, l.use_count, b.name AS brand_name, b.logo_url,
                  s.name AS store_name
           FROM tellus_links l
           JOIN tellus_brands b ON b.id = l.brand_id
           LEFT JOIN tellus_stores s ON s.id = l.store_id
           WHERE l.token = $1""",
        token,
    )
    if row is None or not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This feedback link is not available.")
    if row["expires_at"] is not None:
        expired = await conn.fetchval("SELECT $1::timestamptz < NOW()", row["expires_at"])
        if expired:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This feedback link has expired.")
    if row["max_uses"] is not None and (row["use_count"] or 0) >= row["max_uses"]:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This feedback link is no longer accepting responses.")
    return dict(row)


@router.get("/i/{token}", response_model=TellusIntakeConfig)
async def intake_config(token: str, request: Request):
    """Form config for a QR/link feedback page (brand, store, categories)."""
    await check_rate_limit(client_ip(request), "tellus_intake_get", 60, 3600)
    async with get_connection() as conn:
        link = await _resolve_link(conn, token)
    return TellusIntakeConfig(
        brand_name=link["brand_name"],
        brand_logo_url=link["logo_url"],
        store_name=link["store_name"],
        categories=_CATEGORIES,
    )


@router.post("/i/{token}/media/presign", response_model=TellusMediaPresignResponse)
async def presign_media(token: str, body: TellusMediaPresignRequest, request: Request):
    """Presign a direct-to-S3 PUT for a photo/video. The browser uploads the
    bytes straight to the private bucket (bypassing nginx's body limit)."""
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_presign_burst", 10, 60)
    await check_rate_limit(ip, "tellus_presign_hr", 60, 3600)
    await check_rate_limit(token, "tellus_presign_link", 200, 3600)

    async with get_connection() as conn:
        await _resolve_link(conn, token)

    if body.media_type == "photo":
        if body.mime_type not in _ALLOWED_PHOTO:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image type")
        if body.file_size > _MAX_PHOTO_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large (max 10 MB)")
    else:
        if body.mime_type not in _ALLOWED_VIDEO:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported video type (use MP4, WebM, or MOV)")
        if body.file_size > _MAX_VIDEO_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Video too large (max 200 MB)")

    result = get_storage().get_presigned_upload_url(
        filename=body.original_filename or "upload",
        prefix="tellus",
        content_type=body.mime_type,
        expires_in=900,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Media uploads are not configured.")
    upload_url, storage_path = result
    return TellusMediaPresignResponse(upload_url=upload_url, storage_path=storage_path, expires_in=900)


@router.post("/i/{token}", response_model=TellusFeedbackSubmitResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    token: str,
    body: TellusFeedbackSubmit,
    request: Request,
    background: BackgroundTasks,
    authorization: Optional[str] = Header(default=None),
):
    """Submit feedback against a link. Anonymous by default; a valid consumer
    bearer token attaches `reporter_account_id` so it can earn points."""
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_submit_burst", 5, 60)
    await check_rate_limit(ip, "tellus_submit_hr", 40, 3600)
    await check_rate_limit(token, "tellus_submit_link", 60, 3600)

    # Honeypot: a filled hidden field means a bot. Accept-and-drop — return a
    # synthetic success (indistinguishable from a real one) without writing.
    if body.website:
        logger.info("Tell-Us honeypot tripped on link %s from %s", token, ip)
        return TellusFeedbackSubmitResponse(
            report_id=uuid4(), report_number=None, points_awarded=0, earned=False,
        )

    # Cap media count + REJECT any storage path outside our tellus/ upload
    # prefix. The client echoes back the presigned storage_path; without this
    # check a hostile submitter could reference arbitrary private-bucket keys
    # (e.g. other tenants' documents) and the brand dashboard would mint
    # presigned GET URLs for them.
    media = list(body.media_keys or [])[:_MAX_MEDIA_PER_REPORT]
    storage = get_storage()
    bucket = storage.private_bucket or storage.bucket
    allowed_prefix = f"s3://{bucket}/tellus/" if bucket else None
    for m in media:
        if allowed_prefix is None or not m.storage_path.startswith(allowed_prefix):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid media reference.",
            )

    reporter_account_id = await _optional_account_id(authorization)

    async with get_connection() as conn:
        async with conn.transaction():
            # Atomic reserve-a-use: validates active/expiry/max_uses AND increments
            # in one statement so concurrent submits can't overshoot the cap.
            link = await conn.fetchrow(
                """UPDATE tellus_links
                   SET use_count = use_count + 1
                   WHERE token = $1 AND is_active
                     AND (expires_at IS NULL OR expires_at > NOW())
                     AND (max_uses IS NULL OR use_count < max_uses)
                   RETURNING id, brand_id, store_id""",
                token,
            )
            if link is None:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="This feedback link is not available.",
                )

            outcome = await create_report(
                conn,
                brand_id=link["brand_id"],
                store_id=link["store_id"],
                link_id=link["id"],
                category=body.category,
                sentiment=body.sentiment,
                title=body.title,
                description=body.description,
                occurred_at=body.occurred_at,
                reporter_account_id=reporter_account_id,
                reporter_contact=body.reporter_contact,
                media=media,
            )

    # Alert the brand owner by email (best-effort, after the response).
    owner_id = outcome.get("brand_owner_account_id")
    if owner_id:
        async with get_connection() as conn:
            owner = await conn.fetchrow(
                "SELECT email, display_name FROM tellus_accounts WHERE id = $1", owner_id
            )
        if owner:
            background.add_task(
                send_tellus_feedback_alert_email,
                owner["email"], owner["display_name"], outcome["brand_name"],
                outcome["store_name"], body.sentiment,
            )

    report = outcome["report"]
    return TellusFeedbackSubmitResponse(
        report_id=report["id"],
        report_number=report["report_number"],
        points_awarded=outcome["points_awarded"],
        earned=outcome["earned"],
    )
