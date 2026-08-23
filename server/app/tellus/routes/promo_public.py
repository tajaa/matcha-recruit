"""Tell-Us public promo surfaces — no bearer auth except the claim POST
(which requires a consumer JWT so the FE can bounce to signup/login on 401).
Token is the auth for preview + scanner; rate limits mirror
public_intake.py's layering."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..dependencies import optional_consumer_account_id, require_consumer
from ..models.promo import ClaimOut, ClaimPreviewOut, RedeemIn, RedeemOut, ScanBootstrapOut
from ..models.shoutout_offers import ShoutoutOfferClaimOut, ShoutoutOfferPreviewOut
from ..models.tellus import TellusAccount
from ..services import promo_service
from ..services.promo_service import PromoError
from ..services.shoutout import offers_service

router = APIRouter()


def _raise(e: PromoError):
    # jsonable_encoder because Starlette serializes detail with json.dumps, not
    # jsonable_encoder — see PromoError's docstring on .extra being primitives.
    raise HTTPException(
        status_code=e.http_status,
        detail=jsonable_encoder({"code": e.code, "message": e.message, **e.extra}),
    )


def _raise_offer(e: offers_service.OfferError):
    raise HTTPException(
        status_code=e.status,
        detail=jsonable_encoder({"code": e.code, "message": e.message, **e.extra}),
    )


# ── claim ─────────────────────────────────────────────────────────────────────

@router.get("/p/{claim_token}", response_model=ClaimPreviewOut)
async def claim_preview(claim_token: str, request: Request, authorization: Optional[str] = Header(default=None)):
    # Must stay >= the claim POST's per-IP budget below: one claim costs 2-3
    # previews (first load, the post-login bounce-back to ?claim=1, the 410
    # re-fetch), and the whole point of a flyer is a shared-WiFi/CGNAT crowd
    # on one egress IP. A token-scoped burst catches per-campaign hammering
    # without punishing the crowd.
    await check_rate_limit(client_ip(request), "tellus_promo_preview", 300, 3600)
    await check_rate_limit(claim_token, "tellus_promo_preview_token_burst", 120, 60)
    viewer = await optional_consumer_account_id(authorization)
    async with get_connection() as conn:
        try:
            return await promo_service.resolve_claim_preview(conn, claim_token, viewer)
        except PromoError as e:
            _raise(e)


@router.post("/p/{claim_token}/claim", response_model=ClaimOut)
async def claim(
    claim_token: str,
    request: Request,
    response: Response,
    account: TellusAccount = Depends(require_consumer),
):
    ip = client_ip(request)
    # max_claims (up to 10,000) + the one-card-per-account unique index are
    # the real ceilings on a campaign — these limits only need to stop a
    # stampede, not approximate the cap. A raised per-IP limit is deliberate:
    # the flyer's whole point is a shared-WiFi/CGNAT crowd (a cafe, an event)
    # claiming from the same egress IP.
    await check_rate_limit(ip, "tellus_promo_claim_burst", 5, 60)
    await check_rate_limit(ip, "tellus_promo_claim", 100, 3600)
    await check_rate_limit(claim_token, "tellus_promo_claim_token_burst", 60, 60)

    async with get_connection() as conn:
        try:
            card, created = await promo_service.claim_card(conn, claim_token, account.id)
        except PromoError as e:
            _raise(e)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return ClaimOut(**card, created=created)


@router.get("/o/{offer_token}", response_model=ShoutoutOfferPreviewOut)
async def shoutout_offer_preview(
    offer_token: str, request: Request, authorization: Optional[str] = Header(default=None),
):
    await check_rate_limit(client_ip(request), "tellus_shoutout_offer_preview", 120, 60)
    viewer = await optional_consumer_account_id(authorization)
    async with get_connection() as conn:
        try:
            return await offers_service.preview_offer(conn, token=offer_token, account_id=viewer)
        except offers_service.OfferError as error:
            _raise_offer(error)


@router.post("/o/{offer_token}/claim", response_model=ShoutoutOfferClaimOut)
async def shoutout_offer_claim(
    offer_token: str, request: Request, account: TellusAccount = Depends(require_consumer),
):
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_shoutout_offer_claim_burst", 5, 60)
    await check_rate_limit(ip, "tellus_shoutout_offer_claim", 30, 3600)
    async with get_connection() as conn:
        try:
            return await offers_service.claim_offer(conn, token=offer_token, account_id=account.id)
        except offers_service.OfferError as error:
            _raise_offer(error)


@router.get("/o/code/{short_code}", response_model=ShoutoutOfferPreviewOut)
async def shoutout_offer_code_preview(
    short_code: str, request: Request, authorization: Optional[str] = Header(default=None),
):
    await check_rate_limit(client_ip(request), "tellus_shoutout_code_preview", 120, 60)
    viewer = await optional_consumer_account_id(authorization)
    async with get_connection() as conn:
        try:
            return await offers_service.preview_offer(conn, short_code=short_code, account_id=viewer)
        except offers_service.OfferError as error:
            _raise_offer(error)


@router.post("/o/code/{short_code}/claim", response_model=ShoutoutOfferClaimOut)
async def shoutout_offer_code_claim(
    short_code: str, request: Request, account: TellusAccount = Depends(require_consumer),
):
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_shoutout_code_claim_burst", 3, 60)
    await check_rate_limit(ip, "tellus_shoutout_code_claim", 20, 3600)
    async with get_connection() as conn:
        try:
            return await offers_service.claim_offer(conn, short_code=short_code, account_id=account.id)
        except offers_service.OfferError as error:
            _raise_offer(error)


# ── scanner ───────────────────────────────────────────────────────────────────

@router.get("/scan/{device_token}", response_model=ScanBootstrapOut)
async def scan_bootstrap(device_token: str, request: Request):
    await check_rate_limit(client_ip(request), "tellus_scan_boot", 120, 3600)
    async with get_connection() as conn:
        try:
            scanner = await promo_service.resolve_scanner(conn, device_token)
        except PromoError as e:
            _raise(e)
    return ScanBootstrapOut(
        store_name=scanner["store_name"], brand_name=scanner["brand_name"],
        brand_logo_url=scanner["brand_logo_url"],
    )


@router.post("/scan/{device_token}/redeem", response_model=RedeemOut)
async def scan_redeem(device_token: str, body: RedeemIn, request: Request):
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_scan_redeem_burst", 30, 60)
    await check_rate_limit(device_token, "tellus_scan_redeem", 600, 3600)

    async with get_connection() as conn:
        try:
            scanner = await promo_service.resolve_scanner(conn, device_token)
            result = await promo_service.redeem_card(conn, scanner, body.card_token)
        except PromoError as e:
            _raise(e)
    return RedeemOut(**result)
