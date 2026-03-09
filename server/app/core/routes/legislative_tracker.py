"""Legislative tracker routes — admin-only, stateless live API calls via Gemini grounding."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_admin
from ..services.legislative_tracker import (
    scan_bills,
    ALL_STATES,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scan", dependencies=[Depends(require_admin)])
async def scan_bills_endpoint(
    keywords: Optional[str] = Query(None, description="Comma-separated keywords"),
    states: Optional[str] = Query(None, description="Comma-separated state codes or ALL"),
):
    """
    Run a live legislative scan using Gemini Google Search grounding + Polymarket.

    Searches for pending HR/employment bills, matches against Polymarket prediction
    markets, and uses Gemini to estimate passage probability for unmatched bills.
    May take 15-30s on first run.
    """
    kw_list = None
    if keywords:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]

    state_list = None
    if states:
        raw = [s.strip().upper() for s in states.split(",") if s.strip()]
        if "ALL" in raw:
            state_list = ALL_STATES
        else:
            state_list = [s for s in raw if s in set(ALL_STATES)]
            if not state_list:
                raise HTTPException(status_code=400, detail="No valid state codes provided")

    try:
        return await scan_bills(keywords=kw_list, states=state_list)
    except Exception as e:
        logger.error(f"Legislative scan failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")
