"""Job search routes using SearchAPI (Google Jobs)."""

import json
from typing import List

import httpx
from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..database import get_connection
from ..models.job_search import (
    JobSearchRequest,
    JobSearchResponse,
    JobListing,
    JobApplyLink,
    JobDetectedExtensions,
    JobHighlightSection,
    SavedJob,
    SavedJobCreate,
)

router = APIRouter()


@router.post("/search", response_model=JobSearchResponse)
async def search_jobs(payload: JobSearchRequest):
    """
    Search for jobs using Google Jobs API via SearchAPI.

    Returns job listings with titles, companies, locations, descriptions,
    and application links. Supports filtering by date posted and employment type.
    """
    settings = get_settings()

    if not settings.search_api_key:
        raise HTTPException(
            status_code=400,
            detail="SearchAPI key not configured. Set SEARCH_API_KEY environment variable."
        )

    # Build search params
    params = {
        "engine": "google_jobs",
        "q": payload.query,
        "api_key": settings.search_api_key,
    }

    if payload.location:
        params["location"] = payload.location

    if payload.next_page_token:
        params["next_page_token"] = payload.next_page_token

    # Build chips parameter for filters
    chips = []
    if payload.date_posted:
        chips.append(f"date_posted:{payload.date_posted}")
    if payload.employment_type:
        chips.append(f"employment_type:{payload.employment_type}")
    if chips:
        params["chips"] = ",".join(chips)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://www.searchapi.io/api/v1/search",
                params=params
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"SearchAPI request failed: {str(e)}"
        )

    # Parse job listings
    jobs = []
    for job in data.get("jobs", []):
        apply_links = [
            JobApplyLink(link=link.get("link", ""), source=link.get("source", ""))
            for link in job.get("apply_links", [])
        ]

        # Parse detected_extensions into structured format
        raw_extensions = job.get("detected_extensions", {}) or {}
        detected_extensions = JobDetectedExtensions(
            posted_at=raw_extensions.get("posted_at"),
            schedule_type=raw_extensions.get("schedule_type"),
            salary=raw_extensions.get("salary"),
            work_from_home=raw_extensions.get("work_from_home"),
            health_insurance=raw_extensions.get("health_insurance"),
            dental_coverage=raw_extensions.get("dental_coverage"),
            paid_time_off=raw_extensions.get("paid_time_off"),
        ) if raw_extensions else None

        # Parse job_highlights into structured format
        raw_highlights = job.get("job_highlights", []) or []
        job_highlights = [
            JobHighlightSection(title=h.get("title", ""), items=h.get("items", []))
            for h in raw_highlights
            if isinstance(h, dict)
        ] if raw_highlights else None

        jobs.append(JobListing(
            title=job.get("title", ""),
            company_name=job.get("company_name", ""),
            location=job.get("location", ""),
            description=job.get("description", ""),
            detected_extensions=detected_extensions,
            extensions=job.get("extensions"),
            job_highlights=job_highlights,
            apply_links=apply_links,
            thumbnail=job.get("thumbnail"),
            job_id=job.get("job_id"),
            sharing_link=job.get("sharing_link"),
        ))

    # Get pagination token
    pagination = data.get("pagination", {})
    next_token = pagination.get("next_page_token")

    return JobSearchResponse(
        jobs=jobs,
        next_page_token=next_token,
        query=payload.query,
        location=payload.location,
    )


# Saved Jobs endpoints

@router.post("/saved", response_model=SavedJob)
async def save_job(payload: SavedJobCreate):
    """Save a job listing to the database for later reference."""
    async with get_connection() as conn:
        # Check if job already saved (by job_id if available)
        if payload.job_id:
            existing = await conn.fetchrow(
                "SELECT id FROM saved_jobs WHERE job_id = $1",
                payload.job_id
            )
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Job already saved"
                )

        row = await conn.fetchrow(
            """
            INSERT INTO saved_jobs (
                job_id, title, company_name, location, description,
                salary, schedule_type, work_from_home, posted_at,
                apply_link, thumbnail, extensions, job_highlights, apply_links, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            RETURNING *
            """,
            payload.job_id,
            payload.title,
            payload.company_name,
            payload.location,
            payload.description,
            payload.salary,
            payload.schedule_type,
            payload.work_from_home,
            payload.posted_at,
            payload.apply_link,
            payload.thumbnail,
            json.dumps(payload.extensions) if payload.extensions else None,
            json.dumps([h.model_dump() for h in payload.job_highlights]) if payload.job_highlights else None,
            json.dumps([l.model_dump() for l in payload.apply_links]) if payload.apply_links else None,
            payload.notes,
        )

        return _row_to_saved_job(row)


@router.get("/saved", response_model=List[SavedJob])
async def list_saved_jobs():
    """Get all saved job listings."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM saved_jobs ORDER BY created_at DESC"
        )
        return [_row_to_saved_job(row) for row in rows]


@router.get("/saved/ids", response_model=List[str])
async def list_saved_job_ids():
    """Get just the job_ids of all saved jobs (for quick lookup)."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT job_id FROM saved_jobs WHERE job_id IS NOT NULL"
        )
        return [row["job_id"] for row in rows]


@router.get("/saved/{job_id}", response_model=SavedJob)
async def get_saved_job(job_id: str):
    """Get a specific saved job by its ID (UUID) or job_id."""
    async with get_connection() as conn:
        # Try by UUID first
        row = await conn.fetchrow(
            "SELECT * FROM saved_jobs WHERE id::text = $1 OR job_id = $1",
            job_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Saved job not found")
        return _row_to_saved_job(row)


@router.delete("/saved/{job_id}")
async def delete_saved_job(job_id: str):
    """Delete a saved job by its ID (UUID) or job_id."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM saved_jobs WHERE id::text = $1 OR job_id = $1",
            job_id
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Saved job not found")
        return {"status": "deleted"}


def _row_to_saved_job(row) -> SavedJob:
    """Convert a database row to a SavedJob model."""
    extensions = None
    if row["extensions"]:
        extensions = json.loads(row["extensions"]) if isinstance(row["extensions"], str) else row["extensions"]

    job_highlights = None
    if row["job_highlights"]:
        raw = json.loads(row["job_highlights"]) if isinstance(row["job_highlights"], str) else row["job_highlights"]
        job_highlights = [JobHighlightSection(**h) for h in raw]

    apply_links = None
    if row["apply_links"]:
        raw = json.loads(row["apply_links"]) if isinstance(row["apply_links"], str) else row["apply_links"]
        apply_links = [JobApplyLink(**l) for l in raw]

    return SavedJob(
        id=str(row["id"]),
        job_id=row["job_id"],
        title=row["title"],
        company_name=row["company_name"],
        location=row["location"],
        description=row["description"],
        salary=row["salary"],
        schedule_type=row["schedule_type"],
        work_from_home=row["work_from_home"] or False,
        posted_at=row["posted_at"],
        apply_link=row["apply_link"],
        thumbnail=row["thumbnail"],
        extensions=extensions,
        job_highlights=job_highlights,
        apply_links=apply_links,
        notes=row["notes"],
        created_at=row["created_at"],
    )
