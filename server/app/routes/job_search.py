"""Job search routes using SearchAPI (Google Jobs)."""

import httpx
from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..models.job_search import (
    JobSearchRequest,
    JobSearchResponse,
    JobListing,
    JobApplyLink,
    JobDetectedExtensions,
    JobHighlightSection,
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
