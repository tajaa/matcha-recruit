"""Unauthenticated public loyalty and scanner routes."""
from fastapi import APIRouter, HTTPException, Request

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..models.loyalty import LoyaltyVisitIn
from ..services import loyalty_service, promo_service


router = APIRouter()


def _raise(error: loyalty_service.LoyaltyError) -> None:
    raise HTTPException(
        status_code=error.http_status,
        detail={"code": error.code, "message": error.message, **error.extra},
    )


@router.get("/b/{slug}/loyalty")
async def public_loyalty(slug: str, request: Request):
    await check_rate_limit(client_ip(request), "tellus_public_loyalty", 120, 3600)
    async with get_connection() as conn:
        try:
            return await loyalty_service.get_public_program(conn, slug)
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.post("/scan/{device_token}/loyalty/visit")
async def scanner_visit(device_token: str, body: LoyaltyVisitIn, request: Request):
    await check_rate_limit(client_ip(request), "tellus_loyalty_scan_ip", 60, 60)
    await check_rate_limit(device_token, "tellus_loyalty_scan_device", 120, 60)
    async with get_connection() as conn:
        try:
            scanner = await promo_service.resolve_scanner(conn, device_token)
            return await loyalty_service.record_visit(
                conn, scanner=scanner, raw_member_token=body.member_token
            )
        except (promo_service.PromoError, loyalty_service.LoyaltyError) as error:
            if isinstance(error, promo_service.PromoError):
                raise HTTPException(
                    status_code=error.http_status,
                    detail={"code": error.code, "message": error.message, **error.extra},
                )
            _raise(error)
