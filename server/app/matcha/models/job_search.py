"""Schemas for external job search via SearchAPI."""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel


class JobSearchRequest(BaseModel):
    """Request schema for job search."""
    query: str
    location: Optional[str] = None
    next_page_token: Optional[str] = None
    date_posted: Optional[Literal["today", "3days", "week", "month"]] = None
    employment_type: Optional[Literal["FULLTIME", "PARTTIME", "CONTRACTOR", "INTERN"]] = None


class JobApplyLink(BaseModel):
    """Apply link for a job listing."""
    link: str
    source: str


class JobDetectedExtensions(BaseModel):
    """Parsed metadata from job listing."""
    posted_at: Optional[str] = None
    schedule_type: Optional[str] = None
    salary: Optional[str] = None
    work_from_home: Optional[bool] = None
    health_insurance: Optional[bool] = None
    dental_coverage: Optional[bool] = None
    paid_time_off: Optional[bool] = None


class JobHighlightSection(BaseModel):
    """A section of job highlights (e.g., Qualifications, Responsibilities)."""
    title: str
    items: List[str] = []


class JobListing(BaseModel):
    """Individual job listing from search results."""
    title: str
    company_name: str
    location: str
    description: str
    detected_extensions: Optional[JobDetectedExtensions] = None
    extensions: Optional[List[str]] = None
    job_highlights: Optional[List[JobHighlightSection]] = None
    apply_links: List[JobApplyLink] = []
    thumbnail: Optional[str] = None
    job_id: Optional[str] = None
    sharing_link: Optional[str] = None


class JobSearchResponse(BaseModel):
    """Response schema for job search."""
    jobs: List[JobListing]
    next_page_token: Optional[str] = None
    query: str
    location: Optional[str] = None


# Saved Jobs models
class SavedJobCreate(BaseModel):
    """Request to save a job listing."""
    job_id: Optional[str] = None
    title: str
    company_name: str
    location: Optional[str] = None
    description: Optional[str] = None
    salary: Optional[str] = None
    schedule_type: Optional[str] = None
    work_from_home: bool = False
    posted_at: Optional[str] = None
    apply_link: Optional[str] = None
    thumbnail: Optional[str] = None
    extensions: Optional[List[str]] = None
    job_highlights: Optional[List[JobHighlightSection]] = None
    apply_links: Optional[List[JobApplyLink]] = None
    notes: Optional[str] = None


class SavedJob(BaseModel):
    """Saved job listing stored in database."""
    id: str
    job_id: Optional[str] = None
    title: str
    company_name: str
    location: Optional[str] = None
    description: Optional[str] = None
    salary: Optional[str] = None
    schedule_type: Optional[str] = None
    work_from_home: bool = False
    posted_at: Optional[str] = None
    apply_link: Optional[str] = None
    thumbnail: Optional[str] = None
    extensions: Optional[List[str]] = None
    job_highlights: Optional[List[JobHighlightSection]] = None
    apply_links: Optional[List[JobApplyLink]] = None
    notes: Optional[str] = None
    created_at: datetime
