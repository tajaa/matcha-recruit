"""Openings routes - scrape job listings from company career pages by industry."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import get_settings
from ..database import get_connection
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


# Saved Openings Models
class SavedOpeningCreate(BaseModel):
    """Request to save an opening."""
    title: str
    company_name: str
    location: Optional[str] = None
    department: Optional[str] = None
    apply_url: str
    source_url: Optional[str] = None
    industry: Optional[str] = None
    notes: Optional[str] = None


class SavedOpening(BaseModel):
    """A saved opening."""
    id: str
    title: str
    company_name: str
    location: Optional[str] = None
    department: Optional[str] = None
    apply_url: str
    source_url: Optional[str] = None
    industry: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


# Saved Openings Endpoints
@router.post("/saved", response_model=SavedOpening)
async def save_opening(payload: SavedOpeningCreate):
    """Save an opening for later."""
    async with get_connection() as conn:
        # Check if already saved
        existing = await conn.fetchrow(
            "SELECT id FROM saved_openings WHERE apply_url = $1",
            payload.apply_url
        )
        if existing:
            raise HTTPException(status_code=400, detail="Opening already saved")

        row = await conn.fetchrow(
            """
            INSERT INTO saved_openings (title, company_name, location, department, apply_url, source_url, industry, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            payload.title,
            payload.company_name,
            payload.location,
            payload.department,
            payload.apply_url,
            payload.source_url,
            payload.industry,
            payload.notes,
        )
        return _row_to_saved_opening(row)


@router.get("/saved", response_model=List[SavedOpening])
async def list_saved_openings():
    """Get all saved openings."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM saved_openings ORDER BY created_at DESC"
        )
        return [_row_to_saved_opening(row) for row in rows]


@router.get("/saved/urls", response_model=List[str])
async def list_saved_opening_urls():
    """Get just the apply_urls of saved openings (for quick lookup)."""
    async with get_connection() as conn:
        rows = await conn.fetch("SELECT apply_url FROM saved_openings")
        return [row["apply_url"] for row in rows]


@router.delete("/saved/{opening_id}")
async def delete_saved_opening(opening_id: str):
    """Delete a saved opening."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM saved_openings WHERE id::text = $1 OR apply_url = $1",
            opening_id
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Saved opening not found")
        return {"status": "deleted"}


def _row_to_saved_opening(row) -> SavedOpening:
    """Convert database row to SavedOpening model."""
    return SavedOpening(
        id=str(row["id"]),
        title=row["title"],
        company_name=row["company_name"],
        location=row["location"],
        department=row["department"],
        apply_url=row["apply_url"],
        source_url=row["source_url"],
        industry=row["industry"],
        notes=row["notes"],
        created_at=row["created_at"],
    )
