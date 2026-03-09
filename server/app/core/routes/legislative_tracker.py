"""Legislative tracker routes — admin-only, stateless live API calls."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_admin
from ..services.legislative_tracker import (
    get_legiscan_bill_detail,
    search_polymarket_match,
    estimate_probability_gemini,
    _build_bill_summary,
    _stage_heuristic,
    scan_bills,
    HR_KEYWORDS,
    ALL_STATES,
)
from ...config import get_settings

import httpx

router = APIRouter()


@router.get("/scan", dependencies=[Depends(require_admin)])
async def scan_bills_endpoint(
    keywords: Optional[str] = Query(None, description="Comma-separated keywords"),
    states: Optional[str] = Query(None, description="Comma-separated state codes or ALL"),
):
    """
    Run a live legislative scan.

    Searches LegiScan for pending HR/employment bills, matches against
    Polymarket prediction markets, and uses Gemini for bills with no market.
    May take 10-30s depending on API response times.
    """
    settings = get_settings()
    if not settings.legiscan_api_key:
        raise HTTPException(
            status_code=400,
            detail="LEGISCAN_API_KEY not configured. Register free at legiscan.com.",
        )

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

    return await scan_bills(keywords=kw_list, states=state_list)


@router.get("/bill/{bill_id}", dependencies=[Depends(require_admin)])
async def get_bill_detail(bill_id: int):
    """
    Get detailed info for a single bill: LegiScan detail + Polymarket match + Gemini estimate.
    """
    settings = get_settings()
    if not settings.legiscan_api_key:
        raise HTTPException(
            status_code=400,
            detail="LEGISCAN_API_KEY not configured.",
        )

    async with httpx.AsyncClient() as client:
        detail = await get_legiscan_bill_detail(bill_id, client)
        if not detail:
            raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")

        title = detail.get("title", "")
        poly = await search_polymarket_match(title, client)

        # Build a search-result-compatible dict from the detail
        search_like = {
            "bill_id": bill_id,
            "state": detail.get("state", ""),
            "bill_number": detail.get("bill_number", ""),
            "title": title,
            "description": detail.get("description", ""),
            "status": detail.get("status", 0),
            "last_action": detail.get("last_action", ""),
            "last_action_date": detail.get("last_action_date", ""),
            "url": detail.get("url", ""),
        }
        bill = _build_bill_summary(search_like, detail)

        if poly:
            bill["probability"] = poly["probability"]
            bill["probability_source"] = "polymarket"
            bill["polymarket_url"] = poly["url"]
            bill["polymarket_volume"] = poly["volume"]
        else:
            bill["probability"] = _stage_heuristic(bill["status"])
            bill["probability_source"] = "heuristic"
            gemini_res = await estimate_probability_gemini(bill)
            if gemini_res:
                bill["probability"] = gemini_res["probability"]
                bill["probability_source"] = "gemini"
                bill["probability_reasoning"] = gemini_res["reasoning"]

    return bill
