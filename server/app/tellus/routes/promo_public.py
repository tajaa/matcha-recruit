"""Tell-Us public promo surfaces — no bearer auth except the claim POST
(which requires a consumer JWT so the FE can bounce to signup/login on 401).
Token is the auth for preview + scanner; rate limits mirror
public_intake.py's layering."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..dependencies import optional_consumer_account_id, require_consumer
from ..models.promo import ClaimOut, ClaimPreviewOut, RedeemIn, RedeemOut, ScanBootstrapOut
from ..models.tellus import TellusAccount
from ..services import promo_service
from ..services.promo_service import PromoError

router = APIRouter()


def _raise(e: PromoError):
    raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message, **e.extra})


# ── claim ─────────────────────────────────────────────────────────────────────

@router.get("/p/{claim_token}", response_model=ClaimPreviewOut)
async def claim_preview(claim_token: str, request: Request, authorization: Optional[str] = Header(default=None)):
    await check_rate_limit(client_ip(request), "tellus_promo_preview", 60, 3600)
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
    await check_rate_limit(ip, "tellus_promo_claim_burst", 5, 60)
    await check_rate_limit(ip, "tellus_promo_claim", 20, 3600)
    await check_rate_limit(claim_token, "tellus_promo_claim_token", 120, 3600)

    async with get_connection() as conn:
        try:
            card, created = await promo_service.claim_card(conn, claim_token, account.id)
        except PromoError as e:
            _raise(e)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return ClaimOut(**card, created=created)


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
