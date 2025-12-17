import os
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, File

from ..database import get_connection
from ..models.candidate import CandidateResponse, CandidateDetail
from ..services.resume_parser import ResumeParser
from ..config import get_settings

router = APIRouter()

# Directory to store uploaded resumes
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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

    # Parse resume
    settings = get_settings()
    parser = ResumeParser(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    parsed = await parser.parse_resume_file(file_bytes, file.filename)

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
            INSERT INTO candidates (name, email, phone, resume_text, skills, experience_years, education, parsed_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, name, email, phone, skills, experience_years, education, created_at
            """,
            name,
            email,
            phone,
            resume_text,
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


@router.get("", response_model=list[CandidateResponse])
async def list_candidates():
    """List all candidates."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, email, phone, skills, experience_years, education, created_at
            FROM candidates
            ORDER BY created_at DESC
            """
        )
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
