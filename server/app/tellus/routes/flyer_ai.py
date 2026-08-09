"""Tell-Us flyer design assistant — brand-authenticated AI editing of a promo
campaign's flyer document.

A separate module from promo.py on purpose: `tests/tellus/test_promo_cards.py`
sweeps that router and pins its route count, and these endpoints have their own
gate sweep besides.
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.services.rate_limiter import RateLimitExceeded
from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_paid_brand
from ..models.flyer_ai import (
    FlyerAiSchemaResponse,
    FlyerAssistRequest,
    FlyerAssistResponse,
    FlyerIdeasResponse,
)
from ..models.tellus import TellusAccount
from ..services import promo_service
from ..services.flyer_ai import catalog, layouts, palettes, turn
from ..services.flyer_ai.ops import OPS_BY_NAME
from ..services.promo_service import PromoError

router = APIRouter()

# Same ceiling routes/promo.py puts on a human PUT — an assistant that accepted
# a bigger document than the save path would just move the failure to save time.
_DESIGN_MAX_BYTES = catalog.DESIGN_MAX_BYTES

_BUSY_DETAIL = "The design assistant is busy right now — try again in a moment."


def _raise(e: PromoError):
    raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message, **e.extra})


async def _campaign_for(brand_id, campaign_id: UUID) -> dict:
    """Ownership check plus the campaign copy the prompt grounds on, in ONE
    short connection that is closed before any Gemini call. Holding a pool
    connection across a network round-trip is the rule the flyer-upload fix
    established, and a model turn is an order of magnitude slower than S3.
    """
    async with get_connection() as conn:
        try:
            await promo_service.assert_campaign_owned(conn, brand_id, campaign_id)
            return await promo_service.get_campaign_owned(conn, brand_id, campaign_id)
        except PromoError as e:
            _raise(e)


@router.post("/promo/campaigns/{campaign_id}/design/assist", response_model=FlyerAssistResponse)
async def assist_design(
    campaign_id: UUID,
    body: FlyerAssistRequest,
    account: TellusAccount = Depends(require_paid_brand),
):
    if len(json.dumps(body.design).encode()) > _DESIGN_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Design is too large.",
        )
    await check_rate_limit(str(account.id), "tellus_flyer_ai_burst", 5, 60)
    await check_rate_limit(str(account.id), "tellus_flyer_ai", 60, 3600)

    campaign = await _campaign_for(account.brand_id, campaign_id)
    try:
        return await turn.run_flyer_turn(
            message=body.message,
            design=body.design,
            campaign=campaign,
            history=[h.model_dump() for h in body.history],
            selection=body.selection.model_dump() if body.selection else None,
        )
    except RateLimitExceeded:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_BUSY_DETAIL)


@router.post("/promo/campaigns/{campaign_id}/design/ideas", response_model=FlyerIdeasResponse)
async def design_ideas(
    campaign_id: UUID,
    account: TellusAccount = Depends(require_paid_brand),
):
    await check_rate_limit(str(account.id), "tellus_flyer_ideas_burst", 3, 60)
    await check_rate_limit(str(account.id), "tellus_flyer_ideas", 30, 3600)

    campaign = await _campaign_for(account.brand_id, campaign_id)
    try:
        return {"ideas": await turn.generate_ideas(campaign=campaign)}
    except RateLimitExceeded:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_BUSY_DETAIL)


@router.get("/promo/design/schema", response_model=FlyerAiSchemaResponse)
async def design_schema(account: TellusAccount = Depends(require_paid_brand)):
    """The vocabulary the validators enforce, so a client picker can't offer
    something the server would reject."""
    return {
        "palette_tokens": list(catalog.PALETTE_TOKENS),
        "palettes": [
            {"key": p.key, "label": p.label, "blurb": p.blurb, "colors": p.colors}
            for p in palettes.PALETTES
        ],
        "layouts": [
            {"key": layout.key, "label": layout.label, "blurb": layout.blurb, "preset": layout.preset}
            for layout in layouts.LAYOUTS
        ],
        "fonts": sorted(catalog.FONT_FAMILIES),
        "layer_kinds": sorted(catalog.LAYER_KINDS),
        "addable_layer_kinds": sorted(catalog.ADDABLE_LAYER_KINDS),
        "ops": list(OPS_BY_NAME),
        "max_ops_per_turn": catalog.MAX_OPS_PER_TURN,
    }
