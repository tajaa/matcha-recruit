"""Public job board routes - no authentication required.

Provides:
- Job listings with JSON-LD for Google Jobs
- Job application form
- Indeed XML feed for job aggregators
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr

from ..config import get_settings
from ..database import get_connection
from ..services.resume_parser import ResumeParser


router = APIRouter()

# Upload directory for resumes
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# =============================================================================
# Response Models
# =============================================================================

class PublicJobListing(BaseModel):
    """Public job listing (minimal info for list view)."""
    id: str
    title: str
    company_name: str
    location: Optional[str] = None
    employment_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    remote_policy: Optional[str] = None
    created_at: datetime


class PublicJobDetail(BaseModel):
    """Full public job details."""
    id: str
    title: str
    company_name: str
    company_id: str
    location: Optional[str] = None
    employment_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    requirements: Optional[list[str]] = None
    responsibilities: Optional[list[str]] = None
    required_skills: Optional[list[str]] = None
    preferred_skills: Optional[list[str]] = None
    experience_level: Optional[str] = None
    benefits: Optional[list[str]] = None
    department: Optional[str] = None
    remote_policy: Optional[str] = None
    visa_sponsorship: bool = False
    created_at: datetime
    # JSON-LD for Google Jobs
    json_ld: dict


class JobListResponse(BaseModel):
    """Response for job listings."""
    jobs: list[PublicJobListing]
    total: int


class ApplicationSubmitResponse(BaseModel):
    """Response after submitting application."""
    success: bool
    message: str
    application_id: str


# =============================================================================
# Helper Functions
# =============================================================================

def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file contents."""
    return hashlib.sha256(file_bytes).hexdigest()


def generate_json_ld(job: dict, base_url: str) -> dict:
    """Generate JSON-LD structured data for Google Jobs."""
    settings = get_settings()

    # Map employment type to schema.org values
    employment_type_map = {
        "full-time": "FULL_TIME",
        "part-time": "PART_TIME",
        "contract": "CONTRACTOR",
        "internship": "INTERN",
        "temporary": "TEMPORARY",
    }

    # Build description from requirements and responsibilities
    description_parts = []
    if job.get("responsibilities"):
        responsibilities = job["responsibilities"]
        if isinstance(responsibilities, str):
            responsibilities = json.loads(responsibilities)
        if responsibilities:
            description_parts.append("<h3>Responsibilities</h3><ul>")
            for r in responsibilities:
                description_parts.append(f"<li>{r}</li>")
            description_parts.append("</ul>")

    if job.get("requirements"):
        requirements = job["requirements"]
        if isinstance(requirements, str):
            requirements = json.loads(requirements)
        if requirements:
            description_parts.append("<h3>Requirements</h3><ul>")
            for r in requirements:
                description_parts.append(f"<li>{r}</li>")
            description_parts.append("</ul>")

    if job.get("benefits"):
        benefits = job["benefits"]
        if isinstance(benefits, str):
            benefits = json.loads(benefits)
        if benefits:
            description_parts.append("<h3>Benefits</h3><ul>")
            for b in benefits:
                description_parts.append(f"<li>{b}</li>")
            description_parts.append("</ul>")

    description = "".join(description_parts) if description_parts else f"Join {job['company_name']} as a {job['title']}."

    # Build JSON-LD
    json_ld = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job["title"],
        "description": description,
        "identifier": {
            "@type": "PropertyValue",
            "name": job["company_name"],
            "value": str(job["id"])
        },
        "datePosted": job["created_at"].strftime("%Y-%m-%d") if isinstance(job["created_at"], datetime) else job["created_at"][:10],
        "validThrough": (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%dT23:59"),
        "hiringOrganization": {
            "@type": "Organization",
            "name": job["company_name"],
            "sameAs": base_url,
        },
        "directApply": True,
    }

    # Employment type
    if job.get("employment_type"):
        mapped_type = employment_type_map.get(job["employment_type"], "FULL_TIME")
        json_ld["employmentType"] = mapped_type

    # Location
    if job.get("location"):
        location_parts = job["location"].split(",")
        address = {"@type": "PostalAddress"}
        if len(location_parts) >= 1:
            address["addressLocality"] = location_parts[0].strip()
        if len(location_parts) >= 2:
            address["addressRegion"] = location_parts[1].strip()
        address["addressCountry"] = "US"  # Default

        json_ld["jobLocation"] = {
            "@type": "Place",
            "address": address
        }

    # Remote work
    if job.get("remote_policy") == "remote":
        json_ld["jobLocationType"] = "TELECOMMUTE"
        json_ld["applicantLocationRequirements"] = {
            "@type": "Country",
            "name": "USA"
        }

    # Salary
    if job.get("salary_min") or job.get("salary_max"):
        salary = {
            "@type": "MonetaryAmount",
            "currency": job.get("salary_currency", "USD"),
            "value": {
                "@type": "QuantitativeValue",
                "unitText": "YEAR"
            }
        }
        if job.get("salary_min"):
            salary["value"]["minValue"] = job["salary_min"]
        if job.get("salary_max"):
            salary["value"]["maxValue"] = job["salary_max"]
        json_ld["baseSalary"] = salary

    return json_ld


def generate_indeed_xml(jobs: list[dict], base_url: str) -> str:
    """Generate Indeed XML feed."""
    root = Element("source")

    publisher = SubElement(root, "publisher")
    publisher.text = "Matcha Recruit"

    publisherurl = SubElement(root, "publisherurl")
    publisherurl.text = base_url

    for job in jobs:
        job_elem = SubElement(root, "job")

        title = SubElement(job_elem, "title")
        title.text = job["title"]

        date = SubElement(job_elem, "date")
        if isinstance(job["created_at"], datetime):
            date.text = job["created_at"].strftime("%Y-%m-%d")
        else:
            date.text = job["created_at"][:10]

        referencenumber = SubElement(job_elem, "referencenumber")
        referencenumber.text = str(job["id"])

        url = SubElement(job_elem, "url")
        url.text = f"{base_url}/jobs/{job['id']}/apply"

        company = SubElement(job_elem, "company")
        company.text = job["company_name"]

        if job.get("location"):
            location_parts = job["location"].split(",")
            if len(location_parts) >= 1:
                city = SubElement(job_elem, "city")
                city.text = location_parts[0].strip()
            if len(location_parts) >= 2:
                state = SubElement(job_elem, "state")
                state.text = location_parts[1].strip()

        country = SubElement(job_elem, "country")
        country.text = "US"

        # Build description
        desc_parts = []
        if job.get("responsibilities"):
            responsibilities = job["responsibilities"]
            if isinstance(responsibilities, str):
                responsibilities = json.loads(responsibilities)
            if responsibilities:
                desc_parts.append("Responsibilities: " + "; ".join(responsibilities))
        if job.get("requirements"):
            requirements = job["requirements"]
            if isinstance(requirements, str):
                requirements = json.loads(requirements)
            if requirements:
                desc_parts.append("Requirements: " + "; ".join(requirements))

        description = SubElement(job_elem, "description")
        description.text = " | ".join(desc_parts) if desc_parts else f"Join {job['company_name']} as a {job['title']}."

        if job.get("salary_min") or job.get("salary_max"):
            salary = SubElement(job_elem, "salary")
            if job.get("salary_min") and job.get("salary_max"):
                salary.text = f"${job['salary_min']:,} - ${job['salary_max']:,}"
            elif job.get("salary_min"):
                salary.text = f"${job['salary_min']:,}+"
            else:
                salary.text = f"Up to ${job['salary_max']:,}"

        jobtype = SubElement(job_elem, "jobtype")
        type_map = {
            "full-time": "fulltime",
            "part-time": "parttime",
            "contract": "contract",
            "internship": "internship",
            "temporary": "temporary",
        }
        jobtype.text = type_map.get(job.get("employment_type"), "fulltime")

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="unicode")


# =============================================================================
# Public Endpoints (No Auth Required)
# =============================================================================

@router.get("", response_model=JobListResponse)
async def list_jobs(
    location: Optional[str] = Query(None, description="Filter by location"),
    department: Optional[str] = Query(None, description="Filter by department"),
    remote: Optional[bool] = Query(None, description="Filter remote-only jobs"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    """List all active job postings."""
    async with get_connection() as conn:
        # Build query with filters
        conditions = ["p.status = 'active'", "p.show_on_job_board = true"]
        params = []
        param_idx = 1

        if location:
            conditions.append(f"p.location ILIKE ${param_idx}")
            params.append(f"%{location}%")
            param_idx += 1

        if department:
            conditions.append(f"p.department ILIKE ${param_idx}")
            params.append(f"%{department}%")
            param_idx += 1

        if remote:
            conditions.append("p.remote_policy = 'remote'")

        where_clause = " AND ".join(conditions)

        # Get total count
        count_query = f"""
            SELECT COUNT(*) FROM positions p
            JOIN companies c ON p.company_id = c.id
            WHERE {where_clause}
        """
        total = await conn.fetchval(count_query, *params)

        # Get jobs
        query = f"""
            SELECT
                p.id, p.title, c.name as company_name, p.location,
                p.employment_type, p.salary_min, p.salary_max,
                p.salary_currency, p.remote_policy, p.created_at
            FROM positions p
            JOIN companies c ON p.company_id = c.id
            WHERE {where_clause}
            ORDER BY p.created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

        jobs = [
            PublicJobListing(
                id=str(row["id"]),
                title=row["title"],
                company_name=row["company_name"],
                location=row["location"],
                employment_type=row["employment_type"],
                salary_min=row["salary_min"],
                salary_max=row["salary_max"],
                salary_currency=row["salary_currency"] or "USD",
                remote_policy=row["remote_policy"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return JobListResponse(jobs=jobs, total=total)


@router.get("/feed.xml")
async def get_indeed_xml_feed():
    """Get Indeed-compatible XML feed of all active jobs."""
    settings = get_settings()
    base_url = settings.app_base_url

    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT
                p.id, p.title, c.name as company_name, p.location,
                p.employment_type, p.salary_min, p.salary_max,
                p.salary_currency, p.requirements, p.responsibilities,
                p.created_at
            FROM positions p
            JOIN companies c ON p.company_id = c.id
            WHERE p.status = 'active' AND p.show_on_job_board = true
            ORDER BY p.created_at DESC
            LIMIT 500
        """)

        jobs = [dict(row) for row in rows]
        xml_content = generate_indeed_xml(jobs, base_url)

        return Response(
            content=xml_content,
            media_type="application/xml",
        )


@router.get("/{position_id}", response_model=PublicJobDetail)
async def get_job_detail(position_id: str):
    """Get full details for a specific job posting."""
    settings = get_settings()
    base_url = settings.app_base_url

    async with get_connection() as conn:
        row = await conn.fetchrow("""
            SELECT
                p.*, c.name as company_name
            FROM positions p
            JOIN companies c ON p.company_id = c.id
            WHERE p.id::text = $1 AND p.status = 'active' AND p.show_on_job_board = true
        """, position_id)

        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        job_dict = dict(row)
        json_ld = generate_json_ld(job_dict, base_url)

        # Parse JSONB fields
        def parse_json_field(val):
            if val is None:
                return None
            if isinstance(val, str):
                return json.loads(val)
            return val

        return PublicJobDetail(
            id=str(row["id"]),
            title=row["title"],
            company_name=row["company_name"],
            company_id=str(row["company_id"]),
            location=row["location"],
            employment_type=row["employment_type"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            salary_currency=row["salary_currency"] or "USD",
            requirements=parse_json_field(row["requirements"]),
            responsibilities=parse_json_field(row["responsibilities"]),
            required_skills=parse_json_field(row["required_skills"]),
            preferred_skills=parse_json_field(row["preferred_skills"]),
            experience_level=row["experience_level"],
            benefits=parse_json_field(row["benefits"]),
            department=row["department"],
            remote_policy=row["remote_policy"],
            visa_sponsorship=row["visa_sponsorship"],
            created_at=row["created_at"],
            json_ld=json_ld,
        )


@router.post("/{position_id}/apply", response_model=ApplicationSubmitResponse)
async def apply_to_job(
    position_id: str,
    name: str = Form(...),
    email: EmailStr = Form(...),
    phone: Optional[str] = Form(None),
    cover_letter: Optional[str] = Form(None),
    source: str = Form("direct"),
    resume: UploadFile = File(...),
):
    """Submit a job application with resume."""
    # Validate file type
    if not resume.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(resume.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".doc"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    async with get_connection() as conn:
        # Check if position exists and is active
        position = await conn.fetchrow(
            "SELECT id, title FROM positions WHERE id::text = $1 AND status = 'active'",
            position_id
        )
        if not position:
            raise HTTPException(status_code=404, detail="Job not found or no longer accepting applications")

        # Read and hash file
        file_bytes = await resume.read()
        file_hash = compute_file_hash(file_bytes)

        # Check if candidate already exists (by email or resume hash)
        existing_candidate = await conn.fetchrow(
            "SELECT id FROM candidates WHERE email = $1 OR resume_hash = $2",
            email, file_hash
        )

        if existing_candidate:
            candidate_id = existing_candidate["id"]

            # Check if already applied to this position
            existing_app = await conn.fetchrow(
                "SELECT id FROM job_applications WHERE position_id::text = $1 AND candidate_id = $2",
                position_id, candidate_id
            )
            if existing_app:
                raise HTTPException(
                    status_code=409,
                    detail="You have already applied to this position"
                )
        else:
            # Parse resume
            parser = ResumeParser()
            parsed = parser.parse_resume_file(file_bytes, resume.filename)

            # Extract fields (use form data if resume parsing misses them)
            parsed_name = parsed.get("name") or name
            parsed_email = parsed.get("email") or email
            parsed_phone = parsed.get("phone") or phone
            skills = parsed.get("skills", [])
            experience_years = parsed.get("experience_years")
            education = parsed.get("education", [])
            resume_text = parsed.pop("_resume_text", "")

            # Create candidate
            candidate_row = await conn.fetchrow(
                """
                INSERT INTO candidates (name, email, phone, resume_text, resume_hash, skills, experience_years, education, parsed_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                parsed_name,
                parsed_email,
                parsed_phone,
                resume_text,
                file_hash,
                json.dumps(skills),
                experience_years,
                json.dumps(education),
                json.dumps(parsed),
            )
            candidate_id = candidate_row["id"]

            # Save resume file
            file_path = os.path.join(UPLOAD_DIR, f"{candidate_id}{ext}")
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            await conn.execute(
                "UPDATE candidates SET resume_file_path = $1 WHERE id = $2",
                file_path, candidate_id
            )

        # Create job application
        app_row = await conn.fetchrow(
            """
            INSERT INTO job_applications (position_id, candidate_id, source, cover_letter)
            VALUES ($1::uuid, $2, $3, $4)
            RETURNING id
            """,
            position_id,
            candidate_id,
            source,
            cover_letter,
        )

        return ApplicationSubmitResponse(
            success=True,
            message=f"Your application for {position['title']} has been submitted successfully!",
            application_id=str(app_row["id"]),
        )


# =============================================================================
# Admin Endpoints (for viewing applications)
# =============================================================================

class ApplicationListItem(BaseModel):
    """Application in list view."""
    id: str
    candidate_name: str
    candidate_email: str
    source: Optional[str]
    status: str
    created_at: datetime


class ApplicationListResponse(BaseModel):
    """Response for application list."""
    applications: list[ApplicationListItem]
    total: int


@router.get("/{position_id}/applications", response_model=ApplicationListResponse)
async def list_applications(
    position_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    """List applications for a position (requires auth in production)."""
    async with get_connection() as conn:
        # Verify position exists
        position = await conn.fetchrow(
            "SELECT id FROM positions WHERE id::text = $1",
            position_id
        )
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Build query
        conditions = ["ja.position_id::text = $1"]
        params = [position_id]
        param_idx = 2

        if status:
            conditions.append(f"ja.status = ${param_idx}")
            params.append(status)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        # Get total
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM job_applications ja WHERE {where_clause}",
            *params
        )

        # Get applications
        query = f"""
            SELECT
                ja.id, ja.source, ja.status, ja.created_at,
                c.name as candidate_name, c.email as candidate_email
            FROM job_applications ja
            JOIN candidates c ON ja.candidate_id = c.id
            WHERE {where_clause}
            ORDER BY ja.created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

        applications = [
            ApplicationListItem(
                id=str(row["id"]),
                candidate_name=row["candidate_name"] or "Unknown",
                candidate_email=row["candidate_email"] or "Unknown",
                source=row["source"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return ApplicationListResponse(applications=applications, total=total)
