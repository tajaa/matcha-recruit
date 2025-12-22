"""Openings routes - scrape job listings from company career pages by industry."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import get_settings
from ..services.career_scraper import (
    INDUSTRIES,
    OpeningsSearchResult,
    ScrapedJob,
    search_openings,
)

router = APIRouter()


class OpeningsSearchRequest(BaseModel):
    """Request to search for job openings by industry."""
    industry: str
    query: Optional[str] = None
    max_sources: int = 10


class IndustriesResponse(BaseModel):
    """Available industries for searching."""
    industries: list[str]


@router.get("/industries", response_model=IndustriesResponse)
async def get_industries():
    """Get list of available industries for searching."""
    return IndustriesResponse(industries=INDUSTRIES)


@router.post("/search", response_model=OpeningsSearchResult)
async def search_job_openings(payload: OpeningsSearchRequest):
    """
    Search for job openings by industry.

    This endpoint:
    1. Uses SearchAPI to find company career pages in the specified industry
    2. Scrapes each career page to extract individual job listings
    3. Returns aggregated job listings from multiple sources

    Note: This can take 10-30 seconds depending on the number of sources.
    """
    settings = get_settings()

    if not settings.search_api_key:
        raise HTTPException(
            status_code=400,
            detail="SearchAPI key not configured. Set SEARCH_API_KEY environment variable."
        )

    # Validate industry
    if payload.industry not in INDUSTRIES:
        # Allow custom industries but warn
        pass

    try:
        result = await search_openings(
            industry=payload.industry,
            api_key=settings.search_api_key,
            query=payload.query,
            max_sources=min(payload.max_sources, 20),  # Cap at 20 sources
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to search openings: {str(e)}"
        )
