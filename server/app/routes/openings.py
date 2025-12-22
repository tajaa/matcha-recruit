"""Openings routes - scrape job listings from company career pages and niche job boards."""

import asyncio
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import get_settings
from ..database import get_connection
from ..services.job_sources import (
    DirectCompanyScraper,
    ScrapedJob as SourceScrapedJob,
    AVAILABLE_SOURCES,
)

router = APIRouter()

# Initialize the direct company scraper
direct_scraper = DirectCompanyScraper()


# =============================================================================
# TRACKED COMPANIES (Company Watchlist)
# =============================================================================

class TrackedCompanyCreate(BaseModel):
    """Request to add a company to track."""
    name: str
    career_url: str
    industry: Optional[str] = None


class TrackedCompany(BaseModel):
    """A tracked company."""
    id: str
    name: str
    career_url: str
    industry: Optional[str] = None
    last_scraped_at: Optional[datetime] = None
    job_count: int = 0
    new_job_count: int = 0
    created_at: datetime


class TrackedCompanyJob(BaseModel):
    """A job from a tracked company."""
    id: str
    company_id: str
    company_name: str
    title: str
    location: Optional[str] = None
    department: Optional[str] = None
    apply_url: str
    is_new: bool
    first_seen_at: datetime


class RefreshResult(BaseModel):
    """Result of refreshing tracked companies."""
    companies_refreshed: int
    new_jobs_found: int
    total_jobs: int


@router.post("/companies", response_model=TrackedCompany)
async def add_tracked_company(payload: TrackedCompanyCreate):
    """Add a company to the watchlist."""
    async with get_connection() as conn:
        # Check if already tracked
        existing = await conn.fetchrow(
            "SELECT id FROM tracked_companies WHERE career_url = $1",
            payload.career_url
        )
        if existing:
            raise HTTPException(status_code=400, detail="Company already being tracked")

        row = await conn.fetchrow(
            """
            INSERT INTO tracked_companies (name, career_url, industry)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            payload.name,
            payload.career_url,
            payload.industry,
        )

        return TrackedCompany(
            id=str(row["id"]),
            name=row["name"],
            career_url=row["career_url"],
            industry=row["industry"],
            last_scraped_at=row["last_scraped_at"],
            job_count=0,
            new_job_count=0,
            created_at=row["created_at"],
        )


@router.get("/companies", response_model=List[TrackedCompany])
async def list_tracked_companies():
    """Get all tracked companies with job counts."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT
                tc.*,
                COUNT(tcj.id) as job_count,
                COUNT(tcj.id) FILTER (WHERE tcj.is_new = true) as new_job_count
            FROM tracked_companies tc
            LEFT JOIN tracked_company_jobs tcj ON tc.id = tcj.company_id
            GROUP BY tc.id
            ORDER BY tc.created_at DESC
        """)

        return [
            TrackedCompany(
                id=str(row["id"]),
                name=row["name"],
                career_url=row["career_url"],
                industry=row["industry"],
                last_scraped_at=row["last_scraped_at"],
                job_count=row["job_count"],
                new_job_count=row["new_job_count"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.delete("/companies/{company_id}")
async def delete_tracked_company(company_id: str):
    """Remove a company from tracking."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM tracked_companies WHERE id::text = $1",
            company_id
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Company not found")
        return {"status": "deleted"}


@router.get("/companies/{company_id}/jobs", response_model=List[TrackedCompanyJob])
async def get_tracked_company_jobs(company_id: str):
    """Get jobs from a specific tracked company."""
    async with get_connection() as conn:
        # Get company info
        company = await conn.fetchrow(
            "SELECT name FROM tracked_companies WHERE id::text = $1",
            company_id
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        rows = await conn.fetch(
            """
            SELECT * FROM tracked_company_jobs
            WHERE company_id::text = $1
            ORDER BY is_new DESC, first_seen_at DESC
            """,
            company_id
        )

        return [
            TrackedCompanyJob(
                id=str(row["id"]),
                company_id=str(row["company_id"]),
                company_name=company["name"],
                title=row["title"],
                location=row["location"],
                department=row["department"],
                apply_url=row["apply_url"],
                is_new=row["is_new"],
                first_seen_at=row["first_seen_at"],
            )
            for row in rows
        ]


@router.post("/companies/refresh", response_model=RefreshResult)
async def refresh_tracked_companies():
    """Scrape all tracked companies for new job listings."""
    async with get_connection() as conn:
        companies = await conn.fetch("SELECT * FROM tracked_companies")

        if not companies:
            return RefreshResult(companies_refreshed=0, new_jobs_found=0, total_jobs=0)

        total_new_jobs = 0
        total_jobs = 0

        for company in companies:
            try:
                # Scrape the company's career page
                jobs = await direct_scraper.scrape_url(
                    url=company["career_url"],
                    company_name=company["name"],
                )

                for job in jobs:
                    # Try to insert new job (ignore if already exists)
                    result = await conn.fetchrow(
                        """
                        INSERT INTO tracked_company_jobs
                            (company_id, title, location, department, apply_url)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (apply_url) DO NOTHING
                        RETURNING id
                        """,
                        company["id"],
                        job.title,
                        job.location,
                        job.department,
                        job.apply_url,
                    )
                    if result:
                        total_new_jobs += 1

                total_jobs += len(jobs)

                # Update last scraped timestamp
                await conn.execute(
                    "UPDATE tracked_companies SET last_scraped_at = NOW() WHERE id = $1",
                    company["id"]
                )

            except Exception as e:
                print(f"[Refresh] Failed to scrape {company['name']}: {e}")
                continue

        return RefreshResult(
            companies_refreshed=len(companies),
            new_jobs_found=total_new_jobs,
            total_jobs=total_jobs,
        )


@router.post("/companies/{company_id}/mark-seen")
async def mark_company_jobs_seen(company_id: str):
    """Mark all jobs from a company as seen (not new)."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE tracked_company_jobs SET is_new = false WHERE company_id::text = $1",
            company_id
        )
        return {"status": "marked_seen"}


# =============================================================================
# NICHE JOB SOURCES (Poached, Wellfound, etc.)
# =============================================================================

class SourceInfo(BaseModel):
    """Information about a job source."""
    id: str
    name: str
    description: str
    industries: List[str]


class SourceSearchRequest(BaseModel):
    """Request to search niche job sources."""
    sources: List[str]  # List of source IDs to search
    query: Optional[str] = None
    location: Optional[str] = None
    limit: int = 50


class SourceSearchResult(BaseModel):
    """Result from searching niche sources."""
    jobs: List[dict]  # ScrapedJob as dict
    sources_searched: int
    sources_failed: int


@router.get("/sources", response_model=List[SourceInfo])
async def list_job_sources():
    """Get list of available niche job sources."""
    sources = []
    for source_id, source_class in AVAILABLE_SOURCES.items():
        source = source_class()
        info = source.get_info()
        sources.append(SourceInfo(
            id=info.id,
            name=info.name,
            description=info.description,
            industries=info.industries,
        ))
    return sources


@router.post("/sources/search", response_model=SourceSearchResult)
async def search_job_sources(payload: SourceSearchRequest):
    """Search selected niche job sources for jobs."""
    if not payload.sources:
        raise HTTPException(status_code=400, detail="No sources selected")

    settings = get_settings()
    if not settings.search_api_key:
        raise HTTPException(
            status_code=400,
            detail="SearchAPI key not configured. Set SEARCH_API_KEY environment variable."
        )

    all_jobs = []
    sources_searched = 0
    sources_failed = 0

    # Run searches concurrently
    async def search_source(source_id: str):
        if source_id not in AVAILABLE_SOURCES:
            return None, f"Unknown source: {source_id}"

        try:
            # Pass API key to the source
            source = AVAILABLE_SOURCES[source_id](api_key=settings.search_api_key)
            jobs = await source.search(
                query=payload.query,
                location=payload.location,
                limit=payload.limit,
            )
            return jobs, None
        except Exception as e:
            print(f"[Sources] Error searching {source_id}: {e}")
            return None, str(e)

    tasks = [search_source(sid) for sid in payload.sources]
    results = await asyncio.gather(*tasks)

    for jobs, error in results:
        if error:
            sources_failed += 1
        elif jobs is not None:
            sources_searched += 1
            all_jobs.extend([job.model_dump() for job in jobs])

    # Deduplicate by apply_url
    seen_urls = set()
    unique_jobs = []
    for job in all_jobs:
        if job["apply_url"] and job["apply_url"] not in seen_urls:
            seen_urls.add(job["apply_url"])
            unique_jobs.append(job)

    return SourceSearchResult(
        jobs=unique_jobs[:payload.limit],
        sources_searched=sources_searched,
        sources_failed=sources_failed,
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
