"""Tell-Us promo campaigns — brand CRUD, scanner device mgmt, consumer card
reads. Public claim + scan-redeem endpoints live in promo_public.py (token
auth, no bearer)."""
import contextlib
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_consumer, require_paid_brand
from ..models.promo import (
    CampaignCreate,
    CampaignOut,
    CampaignPatch,
    CancelOut,
    CardOut,
    DesignPut,
    RedeemIn,
    RedeemOut,
    ScannerCreate,
    ScannerOut,
)
from ..models.tellus import TellusAccount
from ..services import promo_service
from ..services.promo_service import PromoError
from ._shared import get_owned_store

router = APIRouter()

_DESIGN_MAX_BYTES = 256 * 1024
_FLYER_MAX_BYTES = 5 * 1024 * 1024
_FLYER_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def _raise(e: PromoError):
    raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message, **e.extra})


# ── brand: campaigns ─────────────────────────────────────────────────────────

@router.post("/promo/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignCreate, account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        return await promo_service.create_campaign(conn, account.brand_id, body)


@router.get("/promo/campaigns", response_model=list[CampaignOut])
async def list_campaigns(account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        return await promo_service.list_campaigns(conn, account.brand_id)


@router.get("/promo/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: UUID, account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        try:
            return await promo_service.get_campaign_owned(conn, account.brand_id, campaign_id)
        except PromoError as e:
            _raise(e)


@router.get("/promo/campaigns/{campaign_id}/design")
async def get_campaign_design(campaign_id: UUID, account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        try:
            design = await promo_service.get_campaign_design(conn, account.brand_id, campaign_id)
        except PromoError as e:
            _raise(e)
    return {"design_json": design}


@router.patch("/promo/campaigns/{campaign_id}", response_model=CampaignOut)
async def patch_campaign(campaign_id: UUID, body: CampaignPatch, account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        try:
            return await promo_service.update_campaign(conn, account.brand_id, campaign_id, body)
        except PromoError as e:
            _raise(e)


@router.post("/promo/campaigns/{campaign_id}/cancel", response_model=CancelOut)
async def cancel_campaign(campaign_id: UUID, account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        try:
            count = await promo_service.cancel_campaign(conn, account.brand_id, campaign_id)
        except PromoError as e:
            _raise(e)
    return CancelOut(invalidated_count=count)


@router.put("/promo/campaigns/{campaign_id}/design", status_code=status.HTTP_204_NO_CONTENT)
async def put_campaign_design(campaign_id: UUID, body: DesignPut, account: TellusAccount = Depends(require_paid_brand)):
    if len(json.dumps(body.design_json)) > _DESIGN_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Design is too large.")
    async with get_connection() as conn:
        try:
            await promo_service.save_design(conn, account.brand_id, campaign_id, body.design_json)
        except PromoError as e:
            _raise(e)


def _is_managed_flyer(url: Optional[str]) -> bool:
    return bool(url) and "/tellus/promo/" in url


async def _delete_flyer_object(url: str) -> None:
    with contextlib.suppress(Exception):
        await get_storage().delete_file(url)


@router.post("/promo/campaigns/{campaign_id}/flyer")
async def upload_flyer(
    campaign_id: UUID,
    file: UploadFile = File(...),
    account: TellusAccount = Depends(require_paid_brand),
):
    """Public bucket on purpose — renders on the unauthenticated /p/{token}
    claim page, so a presigned/private URL (like report media) would rot.
    Mirrors links.py:upload_brand_logo."""
    ext = _FLYER_TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="Flyer must be a PNG, JPEG, or WebP image.")
    data = await file.read()
    if len(data) > _FLYER_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Flyer must be 5MB or smaller.")

    storage = get_storage()
    if not (storage.s3_client and storage.bucket):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Image uploads are not configured.")
    url = await storage.upload_file(
        data, f"flyer.{ext}", prefix=f"tellus/promo/{account.brand_id}/{campaign_id}",
        content_type=file.content_type,
    )

    async with get_connection() as conn:
        try:
            old = await promo_service.set_flyer_url(conn, account.brand_id, campaign_id, url)
        except PromoError as e:
            _raise(e)
    if old and old != url and _is_managed_flyer(old):
        await _delete_flyer_object(old)
    return {"flyer_image_url": url}


# ── brand: scanners ───────────────────────────────────────────────────────────

@router.post("/promo/scanners", response_model=ScannerOut, status_code=status.HTTP_201_CREATED)
async def create_scanner(body: ScannerCreate, account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        await get_owned_store(conn, body.store_id, account.brand_id)
        return await promo_service.create_scanner(conn, account.brand_id, body.store_id, body.label)


@router.get("/promo/scanners", response_model=list[ScannerOut])
async def list_scanners(account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        return await promo_service.list_scanners(conn, account.brand_id)


@router.post("/promo/scanners/{scanner_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_scanner(scanner_id: UUID, account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        try:
            await promo_service.revoke_scanner(conn, account.brand_id, scanner_id)
        except PromoError as e:
            _raise(e)


@router.post("/promo/redeem", response_model=RedeemOut)
async def redeem_as_brand(body: RedeemIn, account: TellusAccount = Depends(require_paid_brand)):
    """iOS/web brand-app path: the brand owner's own device is the scanner,
    no per-store device token involved."""
    scanner = {"id": None, "brand_id": account.brand_id, "store_id": None}
    async with get_connection() as conn:
        try:
            result = await promo_service.redeem_card(conn, scanner, body.card_token)
        except PromoError as e:
            _raise(e)
    return RedeemOut(**result)


# ── consumer: my cards ────────────────────────────────────────────────────────

@router.get("/me/promo-cards", response_model=list[CardOut])
async def my_promo_cards(account: TellusAccount = Depends(require_consumer)):
    async with get_connection() as conn:
        return await promo_service.list_my_cards(conn, account.id)


@router.get("/me/promo-cards/{card_token}", response_model=CardOut)
async def my_promo_card(card_token: str, account: TellusAccount = Depends(require_consumer)):
    async with get_connection() as conn:
        try:
            return await promo_service.get_my_card(conn, account.id, card_token)
        except PromoError as e:
            _raise(e)
