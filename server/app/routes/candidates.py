import hashlib
import os
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pydantic import BaseModel

from ..database import get_connection
from ..dependencies import get_current_user, require_candidate
from ..models.auth import CurrentUser
from ..models.candidate import CandidateResponse, CandidateDetail
from ..services.resume_parser import ResumeParser
from ..services.storage import get_storage


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file contents."""
    return hashlib.sha256(file_bytes).hexdigest()

router = APIRouter()

# Directory to store uploaded resumes (local fallback)
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class BulkUploadResult(BaseModel):
    success_count: int
    error_count: int
    errors: list[dict]
    imported_ids: list[str]


class UpdateCandidateProfile(BaseModel):
    """Request model for manual profile update."""
    name: Optional[str] = None
    phone: Optional[str] = None
    skills: Optional[str] = None  # Comma-separated
    summary: Optional[str] = None


@router.post("/upload", response_model=CandidateResponse)
async def upload_resume(file: UploadFile = File(...)):
    """Upload and parse a resume (PDF or DOCX)."""
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".doc"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    # Read file content
    file_bytes = await file.read()

    # Compute hash for duplicate detection
    file_hash = compute_file_hash(file_bytes)

    # Check for duplicate
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id, name FROM candidates WHERE resume_hash = $1",
            file_hash,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Duplicate resume - already exists as '{existing['name'] or 'Unknown'}'"
            )

    # Parse resume
    parser = ResumeParser()
    parsed = parser.parse_resume_file(file_bytes, file.filename)

    # Extract fields
    name = parsed.get("name")
    email = parsed.get("email")
    phone = parsed.get("phone")
    skills = parsed.get("skills", [])
    experience_years = parsed.get("experience_years")
    education = parsed.get("education", [])
    resume_text = parsed.pop("_resume_text", "")

    # Save to database
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO candidates (name, email, phone, resume_text, resume_hash, skills, experience_years, education, parsed_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id, name, email, phone, skills, experience_years, education, created_at
            """,
            name,
            email,
            phone,
            resume_text,
            file_hash,
            json.dumps(skills),
            experience_years,
            json.dumps(education),
            json.dumps(parsed),
        )

        # Optionally save the file
        candidate_id = row["id"]
        file_path = os.path.join(UPLOAD_DIR, f"{candidate_id}{ext}")
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Update file path
        await conn.execute(
            "UPDATE candidates SET resume_file_path = $1 WHERE id = $2",
            file_path,
            candidate_id,
        )

        skills_data = json.loads(row["skills"]) if row["skills"] else []
        education_data = json.loads(row["education"]) if row["education"] else []

        return CandidateResponse(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            phone=row["phone"],
            skills=skills_data,
            experience_years=row["experience_years"],
            education=education_data,
            created_at=row["created_at"],
        )


@router.post("/bulk-upload", response_model=BulkUploadResult)
async def bulk_upload_resumes(files: list[UploadFile] = File(...)):
    """Upload and parse multiple resumes (PDF or DOCX).

    Files are stored in S3 (or locally as fallback) and parsed using AI.
    """
    storage = get_storage()
    parser = ResumeParser()

    success_count = 0
    errors = []
    imported_ids = []

    for i, file in enumerate(files):
        try:
            # Validate file type
            if not file.filename:
                errors.append({
                    "file": f"File {i + 1}",
                    "error": "No filename provided",
                })
                continue

            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in [".pdf", ".docx", ".doc"]:
                errors.append({
                    "file": file.filename,
                    "error": "Only PDF and DOCX files are supported",
                })
                continue

            # Read file content
            file_bytes = await file.read()

            # Compute hash for duplicate detection
            file_hash = compute_file_hash(file_bytes)

            # Check for duplicate
            async with get_connection() as conn:
                existing = await conn.fetchrow(
                    "SELECT id, name FROM candidates WHERE resume_hash = $1",
                    file_hash,
                )
                if existing:
                    errors.append({
                        "file": file.filename,
                        "error": f"Duplicate resume - already exists as '{existing['name'] or 'Unknown'}'",
                    })
                    continue

            # Store file in S3/local storage
            file_path = await storage.upload_file(
                file_bytes,
                file.filename,
                prefix="resumes",
            )

            # Parse resume
            try:
                parsed = parser.parse_resume_file(file_bytes, file.filename)
            except Exception as parse_error:
                # Still save the file even if parsing fails
                parsed = {"_parse_error": str(parse_error)}

            # Extract fields
            name = parsed.get("name")
            email = parsed.get("email")
            phone = parsed.get("phone")
            skills = parsed.get("skills", [])
            experience_years = parsed.get("experience_years")
            education = parsed.get("education", [])
            resume_text = parsed.pop("_resume_text", "")

            # Save to database
            async with get_connection() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO candidates (name, email, phone, resume_text, resume_file_path, resume_hash, skills, experience_years, education, parsed_data)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING id
                    """,
                    name,
                    email,
                    phone,
                    resume_text,
                    file_path,
                    file_hash,
                    json.dumps(skills) if skills else None,
                    experience_years,
                    json.dumps(education) if education else None,
                    json.dumps(parsed),
                )

                imported_ids.append(str(row["id"]))
                success_count += 1

        except Exception as e:
            errors.append({
                "file": file.filename if file.filename else f"File {i + 1}",
                "error": str(e),
            })

    return BulkUploadResult(
        success_count=success_count,
        error_count=len(errors),
        errors=errors,
        imported_ids=imported_ids,
    )


@router.get("", response_model=list[CandidateResponse])
async def list_candidates(
    search: Optional[str] = None,
    skills: Optional[str] = None,  # Comma-separated
    min_experience: Optional[int] = None,
    max_experience: Optional[int] = None,
    education: Optional[str] = None,  # e.g., "bachelor", "master", "phd"
):
    """List candidates with optional filters."""
    async with get_connection() as conn:
        # Build dynamic query
        conditions = []
        params = []
        param_idx = 1

        if search:
            conditions.append(f"(name ILIKE ${param_idx} OR email ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        if skills:
            # Filter by any of the provided skills
            skill_list = [s.strip().lower() for s in skills.split(",") if s.strip()]
            if skill_list:
                # Check if skills JSONB contains any of the requested skills (case-insensitive)
                skill_conditions = []
                for skill in skill_list:
                    skill_conditions.append(f"LOWER(skills::text) LIKE ${param_idx}")
                    params.append(f"%{skill}%")
                    param_idx += 1
                conditions.append(f"({' OR '.join(skill_conditions)})")

        if min_experience is not None:
            conditions.append(f"experience_years >= ${param_idx}")
            params.append(min_experience)
            param_idx += 1

        if max_experience is not None:
            conditions.append(f"experience_years <= ${param_idx}")
            params.append(max_experience)
            param_idx += 1

        if education:
            # Search in education JSONB for degree type
            conditions.append(f"LOWER(education::text) LIKE ${param_idx}")
            params.append(f"%{education.lower()}%")
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT id, name, email, phone, skills, experience_years, education, created_at
            FROM candidates
            {where_clause}
            ORDER BY created_at DESC
        """

        rows = await conn.fetch(query, *params)

        results = []
        for row in rows:
            skills_data = json.loads(row["skills"]) if row["skills"] else []
            education_data = json.loads(row["education"]) if row["education"] else []
            results.append(CandidateResponse(
                id=row["id"],
                name=row["name"],
                email=row["email"],
                phone=row["phone"],
                skills=skills_data,
                experience_years=row["experience_years"],
                education=education_data,
                created_at=row["created_at"],
            ))
        return results


# ===========================================
# Candidate Self-Service Endpoints
# IMPORTANT: These must be before /{candidate_id} routes
# ===========================================

@router.post("/me/resume", response_model=CandidateResponse)
async def update_my_resume(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_candidate)
):
    """Upload/update resume for the currently logged-in candidate."""
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".doc"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    # Read file content
    file_bytes = await file.read()

    # Get existing candidate record
    async with get_connection() as conn:
        candidate = await conn.fetchrow(
            "SELECT id FROM candidates WHERE user_id = $1",
            current_user.id
        )
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate profile not found")

        candidate_id = candidate["id"]

        # Compute hash
        file_hash = compute_file_hash(file_bytes)

        # Parse resume
        parser = ResumeParser()
        parsed = parser.parse_resume_file(file_bytes, file.filename)

        # Extract fields
        name = parsed.get("name")
        email = parsed.get("email")
        phone = parsed.get("phone")
        skills = parsed.get("skills", [])
        experience_years = parsed.get("experience_years")
        education = parsed.get("education", [])
        resume_text = parsed.pop("_resume_text", "")

        # Save file
        file_path = os.path.join(UPLOAD_DIR, f"{candidate_id}{ext}")
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # UPDATE existing record (not INSERT)
        row = await conn.fetchrow(
            """
            UPDATE candidates
            SET name = COALESCE($1, name),
                email = COALESCE($2, email),
                phone = COALESCE($3, phone),
                resume_text = $4,
                resume_hash = $5,
                resume_file_path = $6,
                skills = $7,
                experience_years = COALESCE($8, experience_years),
                education = $9,
                parsed_data = $10
            WHERE id = $11
            RETURNING id, name, email, phone, skills, experience_years, education, created_at
            """,
            name,
            email,
            phone,
            resume_text,
            file_hash,
            file_path,
            json.dumps(skills) if skills else None,
            experience_years,
            json.dumps(education) if education else None,
            json.dumps(parsed),
            candidate_id,
        )

        skills_data = json.loads(row["skills"]) if row["skills"] else []
        education_data = json.loads(row["education"]) if row["education"] else []

        return CandidateResponse(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            phone=row["phone"],
            skills=skills_data,
            experience_years=row["experience_years"],
            education=education_data,
            created_at=row["created_at"],
        )


@router.put("/me/profile", response_model=CandidateResponse)
async def update_my_profile(
    request: UpdateCandidateProfile,
    current_user: CurrentUser = Depends(require_candidate)
):
    """Update profile for logged-in candidate (manual entry without resume)."""
    async with get_connection() as conn:
        # Get existing candidate record
        candidate = await conn.fetchrow(
            "SELECT id FROM candidates WHERE user_id = $1",
            current_user.id
        )
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate profile not found")

        candidate_id = candidate["id"]

        # Parse skills from comma-separated string
        skills_list = []
        if request.skills:
            skills_list = [s.strip() for s in request.skills.split(",") if s.strip()]

        # Build parsed_data with summary
        parsed_data = {}
        if request.summary:
            parsed_data["summary"] = request.summary

        # Update record
        row = await conn.fetchrow(
            """
            UPDATE candidates
            SET name = COALESCE(NULLIF($1, ''), name),
                phone = COALESCE(NULLIF($2, ''), phone),
                skills = COALESCE($3, skills),
                parsed_data = COALESCE($4, parsed_data)
            WHERE id = $5
            RETURNING id, name, email, phone, skills, experience_years, education, created_at
            """,
            request.name,
            request.phone,
            json.dumps(skills_list) if skills_list else None,
            json.dumps(parsed_data) if parsed_data else None,
            candidate_id,
        )

        skills_data = json.loads(row["skills"]) if row["skills"] else []
        education_data = json.loads(row["education"]) if row["education"] else []

        return CandidateResponse(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            phone=row["phone"],
            skills=skills_data,
            experience_years=row["experience_years"],
            education=education_data,
            created_at=row["created_at"],
        )


# ===========================================
# Admin/Client Candidate Management Endpoints
# ===========================================

@router.get("/{candidate_id}", response_model=CandidateDetail)
async def get_candidate(candidate_id: UUID):
    """Get a candidate's full details."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, email, phone, resume_text, skills, experience_years, education, parsed_data, created_at
            FROM candidates
            WHERE id = $1
            """,
            candidate_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Candidate not found")

        skills_data = json.loads(row["skills"]) if row["skills"] else []
        education_data = json.loads(row["education"]) if row["education"] else []
        parsed_data = json.loads(row["parsed_data"]) if row["parsed_data"] else {}

        return CandidateDetail(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            phone=row["phone"],
            resume_text=row["resume_text"],
            skills=skills_data,
            experience_years=row["experience_years"],
            education=education_data,
            parsed_data=parsed_data,
            created_at=row["created_at"],
        )


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: UUID):
    """Delete a candidate."""
    async with get_connection() as conn:
        # Get file path first
        row = await conn.fetchrow(
            "SELECT resume_file_path FROM candidates WHERE id = $1",
            candidate_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Candidate not found")

        # Delete file if exists
        if row["resume_file_path"] and os.path.exists(row["resume_file_path"]):
            os.unlink(row["resume_file_path"])

        # Delete from database
        await conn.execute("DELETE FROM candidates WHERE id = $1", candidate_id)

        return {"status": "deleted"}
