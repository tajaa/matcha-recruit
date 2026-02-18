"""Public project routes — no authentication required.

Provides:
- Public project info for the apply page
- Public application submission with resume upload
"""

import hashlib
import json
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import EmailStr

from ...database import get_connection
from ..models.project import PublicProjectInfo

router = APIRouter()

# Upload directory for resumes (same as public_jobs.py)
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads"
)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


@router.get("/{project_id}", response_model=PublicProjectInfo)
async def get_public_project(project_id: UUID):
    """Get public-facing project info for the apply page.

    Only returns projects that have is_public=true and status='active'.
    Salary is omitted if salary_hidden=true.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, company_name, position_title, description, location,
                   salary_min, salary_max, salary_hidden, currency,
                   requirements, benefits, closing_date
            FROM projects
            WHERE id = $1 AND is_public = true AND status = 'active'
            """,
            project_id,
        )
        if not row:
            raise HTTPException(
                status_code=404,
                detail="Project not found or not accepting applications",
            )

        return PublicProjectInfo(
            id=row["id"],
            company_name=row["company_name"],
            position_title=row["position_title"],
            description=row["description"],
            location=row["location"],
            salary_min=None if row["salary_hidden"] else row["salary_min"],
            salary_max=None if row["salary_hidden"] else row["salary_max"],
            salary_hidden=row["salary_hidden"] or False,
            currency=row["currency"] or "USD",
            requirements=row["requirements"],
            benefits=row["benefits"],
            closing_date=row["closing_date"],
        )


@router.post("/{project_id}/apply", status_code=201)
async def apply_to_project(
    project_id: UUID,
    name: str = Form(...),
    email: EmailStr = Form(...),
    phone: Optional[str] = Form(None),
    cover_letter: Optional[str] = Form(None),
    source: str = Form("direct"),
    resume: UploadFile = File(...),
):
    """Submit a public application for a project.

    Parses the resume, deduplicates candidates by email/hash, creates a
    project_applications record, and queues AI resume screening.
    """
    from ...matcha.services.resume_parser import ResumeParser
    from ...workers.tasks.resume_screening import screen_resume_async

    # Validate file type
    if not resume.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(resume.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".doc"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    async with get_connection() as conn:
        # Verify project is public and active
        project = await conn.fetchrow(
            """
            SELECT id, requirements, description
            FROM projects
            WHERE id = $1 AND is_public = true AND status = 'active'
            """,
            project_id,
        )
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found or not accepting applications",
            )

        # Read and hash resume
        file_bytes = await resume.read()
        file_hash = _compute_file_hash(file_bytes)

        # Find or create candidate (deduplicate by email or resume hash)
        existing_candidate = await conn.fetchrow(
            "SELECT id FROM candidates WHERE email = $1 OR resume_hash = $2",
            email,
            file_hash,
        )

        resume_text = ""

        if existing_candidate:
            candidate_id = existing_candidate["id"]

            # Check for duplicate application
            existing_app = await conn.fetchval(
                "SELECT id FROM project_applications WHERE project_id = $1 AND candidate_id = $2",
                project_id,
                candidate_id,
            )
            if existing_app:
                raise HTTPException(
                    status_code=409,
                    detail="You have already applied to this position",
                )

            # Parse the newly uploaded resume regardless of what's stored —
            # the stored resume_text may be stale or empty for older/manual records.
            parser = ResumeParser()
            parsed_fresh = parser.parse_resume_file(file_bytes, resume.filename)
            resume_text = parsed_fresh.pop("_resume_text", "")

            # Fall back to stored text only if the fresh parse produced nothing.
            if not resume_text:
                resume_row = await conn.fetchrow(
                    "SELECT resume_text FROM candidates WHERE id = $1",
                    candidate_id,
                )
                resume_text = (resume_row["resume_text"] or "") if resume_row else ""
        else:
            # Parse resume
            parser = ResumeParser()
            parsed = parser.parse_resume_file(file_bytes, resume.filename)

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
                file_path,
                candidate_id,
            )

        # Create project application
        app_row = await conn.fetchrow(
            """
            INSERT INTO project_applications (project_id, candidate_id, source, cover_letter, status)
            VALUES ($1, $2, $3, $4, 'new')
            RETURNING id
            """,
            project_id,
            candidate_id,
            source,
            cover_letter,
        )
        application_id = str(app_row["id"])

    # Queue AI resume screening (after connection is released)
    screen_resume_async.delay(
        str(project_id),
        application_id,
        str(candidate_id),
        resume_text,
        project["requirements"],
        project["description"],
    )

    return {
        "success": True,
        "message": "Your application has been submitted successfully. We'll review it shortly.",
        "application_id": application_id,
    }
