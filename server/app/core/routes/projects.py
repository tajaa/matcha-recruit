import json
import secrets
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ...database import get_connection
from ..models.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectCandidateAdd,
    ProjectCandidateBulkAdd,
    ProjectCandidateUpdate,
    ProjectCandidateResponse,
    ApplicationResponse,
    BulkAcceptResponse,
    ProjectStatus,
    CandidateStage,
)

router = APIRouter()


def _project_response(row, candidate_count: int = 0, application_count: int = 0) -> ProjectResponse:
    return ProjectResponse(
        id=row["id"],
        company_name=row["company_name"],
        name=row["name"],
        company_id=row["company_id"],
        position_title=row["position_title"],
        location=row["location"],
        salary_min=row["salary_min"],
        salary_max=row["salary_max"],
        salary_hidden=row["salary_hidden"] or False,
        is_public=row["is_public"] or False,
        description=row["description"],
        currency=row["currency"] or "USD",
        benefits=row["benefits"],
        requirements=row["requirements"],
        closing_date=row["closing_date"],
        status=row["status"],
        notes=row["notes"],
        candidate_count=candidate_count,
        application_count=application_count,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("", response_model=ProjectResponse)
async def create_project(project: ProjectCreate):
    """Create a new project."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO projects (
                company_name, name, company_id, position_title, location,
                salary_min, salary_max, salary_hidden, is_public, description,
                currency, benefits, requirements, closing_date, status, notes
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            RETURNING id, company_name, name, company_id, position_title, location,
                      salary_min, salary_max, salary_hidden, is_public, description,
                      currency, benefits, requirements, closing_date, status, notes,
                      created_at, updated_at
            """,
            project.company_name,
            project.name,
            project.company_id,
            project.position_title,
            project.location,
            project.salary_min,
            project.salary_max,
            project.salary_hidden,
            project.is_public,
            project.description,
            project.currency,
            project.benefits,
            project.requirements,
            project.closing_date,
            project.status.value,
            project.notes,
        )

        return _project_response(row, 0, 0)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(status: Optional[str] = None):
    """List projects with optional status filter."""
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT p.*,
                       COUNT(DISTINCT pc.id) as candidate_count,
                       COUNT(DISTINCT pa.id) as application_count
                FROM projects p
                LEFT JOIN project_candidates pc ON p.id = pc.project_id
                LEFT JOIN project_applications pa ON p.id = pa.project_id
                WHERE p.status = $1
                GROUP BY p.id
                ORDER BY p.updated_at DESC
                """,
                status,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT p.*,
                       COUNT(DISTINCT pc.id) as candidate_count,
                       COUNT(DISTINCT pa.id) as application_count
                FROM projects p
                LEFT JOIN project_candidates pc ON p.id = pc.project_id
                LEFT JOIN project_applications pa ON p.id = pa.project_id
                GROUP BY p.id
                ORDER BY p.updated_at DESC
                """
            )

        return [_project_response(row, row["candidate_count"], row["application_count"]) for row in rows]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID):
    """Get a project by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.*,
                   COUNT(DISTINCT pc.id) as candidate_count,
                   COUNT(DISTINCT pa.id) as application_count
            FROM projects p
            LEFT JOIN project_candidates pc ON p.id = pc.project_id
            LEFT JOIN project_applications pa ON p.id = pa.project_id
            WHERE p.id = $1
            GROUP BY p.id
            """,
            project_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        return _project_response(row, row["candidate_count"], row["application_count"])


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: UUID, project: ProjectUpdate):
    """Update a project."""
    async with get_connection() as conn:
        # Build dynamic update query
        updates = []
        params = []
        param_idx = 1

        if project.company_name is not None:
            updates.append(f"company_name = ${param_idx}")
            params.append(project.company_name)
            param_idx += 1

        if project.name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(project.name)
            param_idx += 1

        if project.company_id is not None:
            updates.append(f"company_id = ${param_idx}")
            params.append(project.company_id)
            param_idx += 1

        if project.position_title is not None:
            updates.append(f"position_title = ${param_idx}")
            params.append(project.position_title)
            param_idx += 1

        if project.location is not None:
            updates.append(f"location = ${param_idx}")
            params.append(project.location)
            param_idx += 1

        if project.salary_min is not None:
            updates.append(f"salary_min = ${param_idx}")
            params.append(project.salary_min)
            param_idx += 1

        if project.salary_max is not None:
            updates.append(f"salary_max = ${param_idx}")
            params.append(project.salary_max)
            param_idx += 1

        if project.benefits is not None:
            updates.append(f"benefits = ${param_idx}")
            params.append(project.benefits)
            param_idx += 1

        if project.requirements is not None:
            updates.append(f"requirements = ${param_idx}")
            params.append(project.requirements)
            param_idx += 1

        if project.status is not None:
            updates.append(f"status = ${param_idx}")
            params.append(project.status.value)
            param_idx += 1

        if project.salary_hidden is not None:
            updates.append(f"salary_hidden = ${param_idx}")
            params.append(project.salary_hidden)
            param_idx += 1

        if project.is_public is not None:
            updates.append(f"is_public = ${param_idx}")
            params.append(project.is_public)
            param_idx += 1

        if project.description is not None:
            updates.append(f"description = ${param_idx}")
            params.append(project.description)
            param_idx += 1

        if project.currency is not None:
            updates.append(f"currency = ${param_idx}")
            params.append(project.currency)
            param_idx += 1

        if project.closing_date is not None:
            updates.append(f"closing_date = ${param_idx}")
            params.append(project.closing_date)
            param_idx += 1

        if project.notes is not None:
            updates.append(f"notes = ${param_idx}")
            params.append(project.notes)
            param_idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        params.append(project_id)

        query = f"""
            UPDATE projects
            SET {', '.join(updates)}
            WHERE id = ${param_idx}
            RETURNING id, company_name, name, company_id, position_title, location,
                      salary_min, salary_max, salary_hidden, is_public, description,
                      currency, benefits, requirements, closing_date, status, notes,
                      created_at, updated_at
        """

        row = await conn.fetchrow(query, *params)

        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        candidate_count = await conn.fetchval(
            "SELECT COUNT(*) FROM project_candidates WHERE project_id = $1",
            project_id,
        )
        application_count = await conn.fetchval(
            "SELECT COUNT(*) FROM project_applications WHERE project_id = $1",
            project_id,
        )

        return _project_response(row, candidate_count, application_count)


@router.delete("/{project_id}")
async def delete_project(project_id: UUID):
    """Delete a project."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM projects WHERE id = $1",
            project_id,
        )

        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Project not found")

        return {"status": "deleted"}


# Project Candidates endpoints

@router.post("/{project_id}/candidates", response_model=ProjectCandidateResponse)
async def add_candidate_to_project(project_id: UUID, data: ProjectCandidateAdd):
    """Add a candidate to a project."""
    async with get_connection() as conn:
        # Check project exists
        project = await conn.fetchval(
            "SELECT id FROM projects WHERE id = $1",
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Check candidate exists
        candidate = await conn.fetchrow(
            "SELECT id, name, email, phone, skills, experience_years FROM candidates WHERE id = $1",
            data.candidate_id,
        )
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        # Check if already added
        existing = await conn.fetchval(
            "SELECT id FROM project_candidates WHERE project_id = $1 AND candidate_id = $2",
            project_id,
            data.candidate_id,
        )
        if existing:
            raise HTTPException(status_code=409, detail="Candidate already in project")

        # Add candidate
        row = await conn.fetchrow(
            """
            INSERT INTO project_candidates (project_id, candidate_id, stage, notes)
            VALUES ($1, $2, $3, $4)
            RETURNING id, project_id, candidate_id, stage, notes, created_at, updated_at
            """,
            project_id,
            data.candidate_id,
            data.stage.value,
            data.notes,
        )

        skills = json.loads(candidate["skills"]) if candidate["skills"] else []

        return ProjectCandidateResponse(
            id=row["id"],
            project_id=row["project_id"],
            candidate_id=row["candidate_id"],
            candidate_name=candidate["name"],
            candidate_email=candidate["email"],
            candidate_phone=candidate["phone"],
            candidate_skills=skills,
            candidate_experience_years=candidate["experience_years"],
            stage=row["stage"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.post("/{project_id}/candidates/bulk", response_model=dict)
async def bulk_add_candidates_to_project(project_id: UUID, data: ProjectCandidateBulkAdd):
    """Add multiple candidates to a project at once."""
    async with get_connection() as conn:
        # Check project exists
        project = await conn.fetchval(
            "SELECT id FROM projects WHERE id = $1",
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        added = 0
        skipped = 0

        for candidate_id in data.candidate_ids:
            # Check candidate exists
            candidate = await conn.fetchval(
                "SELECT id FROM candidates WHERE id = $1",
                candidate_id,
            )
            if not candidate:
                skipped += 1
                continue

            # Check if already added
            existing = await conn.fetchval(
                "SELECT id FROM project_candidates WHERE project_id = $1 AND candidate_id = $2",
                project_id,
                candidate_id,
            )
            if existing:
                skipped += 1
                continue

            # Add candidate
            await conn.execute(
                """
                INSERT INTO project_candidates (project_id, candidate_id, stage)
                VALUES ($1, $2, $3)
                """,
                project_id,
                candidate_id,
                data.stage.value,
            )
            added += 1

        return {"added": added, "skipped": skipped}


@router.get("/{project_id}/candidates", response_model=list[ProjectCandidateResponse])
async def list_project_candidates(
    project_id: UUID,
    stage: Optional[str] = None,
):
    """List candidates in a project with optional stage filter."""
    async with get_connection() as conn:
        # Check project exists
        project = await conn.fetchval(
            "SELECT id FROM projects WHERE id = $1",
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if stage:
            query = """
                SELECT pc.*, c.name as candidate_name, c.email as candidate_email,
                       c.phone as candidate_phone, c.skills as candidate_skills,
                       c.experience_years as candidate_experience_years
                FROM project_candidates pc
                JOIN candidates c ON pc.candidate_id = c.id
                WHERE pc.project_id = $1 AND pc.stage = $2
                ORDER BY pc.updated_at DESC
            """
            rows = await conn.fetch(query, project_id, stage)
        else:
            query = """
                SELECT pc.*, c.name as candidate_name, c.email as candidate_email,
                       c.phone as candidate_phone, c.skills as candidate_skills,
                       c.experience_years as candidate_experience_years
                FROM project_candidates pc
                JOIN candidates c ON pc.candidate_id = c.id
                WHERE pc.project_id = $1
                ORDER BY pc.updated_at DESC
            """
            rows = await conn.fetch(query, project_id)

        return [
            ProjectCandidateResponse(
                id=row["id"],
                project_id=row["project_id"],
                candidate_id=row["candidate_id"],
                candidate_name=row["candidate_name"],
                candidate_email=row["candidate_email"],
                candidate_phone=row["candidate_phone"],
                candidate_skills=json.loads(row["candidate_skills"]) if row["candidate_skills"] else [],
                candidate_experience_years=row["candidate_experience_years"],
                stage=row["stage"],
                notes=row["notes"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.put("/{project_id}/candidates/{candidate_id}", response_model=ProjectCandidateResponse)
async def update_project_candidate(
    project_id: UUID,
    candidate_id: UUID,
    data: ProjectCandidateUpdate,
):
    """Update a candidate's stage or notes in a project."""
    async with get_connection() as conn:
        # Build dynamic update
        updates = []
        params = []
        param_idx = 1

        if data.stage is not None:
            updates.append(f"stage = ${param_idx}")
            params.append(data.stage.value)
            param_idx += 1

        if data.notes is not None:
            updates.append(f"notes = ${param_idx}")
            params.append(data.notes)
            param_idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        params.extend([project_id, candidate_id])

        query = f"""
            UPDATE project_candidates
            SET {', '.join(updates)}
            WHERE project_id = ${param_idx} AND candidate_id = ${param_idx + 1}
            RETURNING id, project_id, candidate_id, stage, notes, created_at, updated_at
        """

        row = await conn.fetchrow(query, *params)

        if not row:
            raise HTTPException(status_code=404, detail="Candidate not in project")

        # Get candidate details
        candidate = await conn.fetchrow(
            "SELECT name, email, phone, skills, experience_years FROM candidates WHERE id = $1",
            candidate_id,
        )

        skills = json.loads(candidate["skills"]) if candidate["skills"] else []

        return ProjectCandidateResponse(
            id=row["id"],
            project_id=row["project_id"],
            candidate_id=row["candidate_id"],
            candidate_name=candidate["name"],
            candidate_email=candidate["email"],
            candidate_phone=candidate["phone"],
            candidate_skills=skills,
            candidate_experience_years=candidate["experience_years"],
            stage=row["stage"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.delete("/{project_id}/candidates/{candidate_id}")
async def remove_candidate_from_project(project_id: UUID, candidate_id: UUID):
    """Remove a candidate from a project."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM project_candidates WHERE project_id = $1 AND candidate_id = $2",
            project_id,
            candidate_id,
        )

        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Candidate not in project")

        return {"status": "removed"}


@router.get("/{project_id}/stats")
async def get_project_stats(project_id: UUID):
    """Get candidate counts per stage for a project."""
    async with get_connection() as conn:
        # Check project exists
        project = await conn.fetchval(
            "SELECT id FROM projects WHERE id = $1",
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        rows = await conn.fetch(
            """
            SELECT stage, COUNT(*) as count
            FROM project_candidates
            WHERE project_id = $1
            GROUP BY stage
            """,
            project_id,
        )

        stats = {stage.value: 0 for stage in CandidateStage}
        for row in rows:
            stats[row["stage"]] = row["count"]

        stats["total"] = sum(stats.values())

        return stats


# ============================================================================
# Application management endpoints
# NOTE: bulk-accept-recommended MUST be declared before /{application_id}/accept
# to avoid FastAPI parsing the literal string as a UUID.
# ============================================================================

@router.get("/{project_id}/applications", response_model=list[ApplicationResponse])
async def list_project_applications(
    project_id: UUID,
    status: Optional[str] = None,
):
    """List public applications for a project with AI screening results."""
    async with get_connection() as conn:
        project = await conn.fetchval("SELECT id FROM projects WHERE id = $1", project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if status:
            rows = await conn.fetch(
                """
                SELECT pa.*, c.name as candidate_name, c.email as candidate_email,
                       c.skills as candidate_skills
                FROM project_applications pa
                JOIN candidates c ON pa.candidate_id = c.id
                WHERE pa.project_id = $1 AND pa.status = $2
                ORDER BY pa.ai_score DESC NULLS LAST, pa.created_at DESC
                """,
                project_id,
                status,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT pa.*, c.name as candidate_name, c.email as candidate_email,
                       c.skills as candidate_skills
                FROM project_applications pa
                JOIN candidates c ON pa.candidate_id = c.id
                WHERE pa.project_id = $1
                ORDER BY pa.ai_score DESC NULLS LAST, pa.created_at DESC
                """,
                project_id,
            )

        return [
            ApplicationResponse(
                id=row["id"],
                project_id=row["project_id"],
                candidate_id=row["candidate_id"],
                candidate_name=row["candidate_name"],
                candidate_email=row["candidate_email"],
                candidate_skills=json.loads(row["candidate_skills"]) if row["candidate_skills"] else [],
                status=row["status"],
                ai_score=row["ai_score"],
                ai_recommendation=row["ai_recommendation"],
                ai_notes=row["ai_notes"],
                source=row["source"] or "direct",
                cover_letter=row["cover_letter"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.post("/{project_id}/applications/bulk-accept-recommended", response_model=BulkAcceptResponse)
async def bulk_accept_recommended_applications(project_id: UUID):
    """Accept all AI-recommended applications, add to pipeline, and send screening invites."""
    from ..services.email import get_email_service
    from ...config import get_settings

    email_service = get_email_service()
    settings = get_settings()

    async with get_connection() as conn:
        project = await conn.fetchrow(
            "SELECT company_name, name, position_title, location, salary_min, salary_max FROM projects WHERE id = $1",
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get all recommended applications not yet accepted/rejected
        apps = await conn.fetch(
            """
            SELECT pa.id, pa.candidate_id, c.name, c.email
            FROM project_applications pa
            JOIN candidates c ON pa.candidate_id = c.id
            WHERE pa.project_id = $1 AND pa.ai_recommendation = 'recommended'
              AND pa.status = 'recommended'
            """,
            project_id,
        )

        accepted = 0
        skipped = 0
        errors = []

        salary_range = _format_salary_range(project["salary_min"], project["salary_max"])

        for app in apps:
            candidate_id = app["candidate_id"]

            # Update application status
            await conn.execute(
                "UPDATE project_applications SET status = 'accepted', updated_at = NOW() WHERE id = $1",
                app["id"],
            )

            # Upsert into project_candidates
            await conn.execute(
                """
                INSERT INTO project_candidates (project_id, candidate_id, stage)
                VALUES ($1, $2, 'initial')
                ON CONFLICT (project_id, candidate_id) DO NOTHING
                """,
                project_id,
                candidate_id,
            )

            # Check if outreach already exists
            existing_outreach = await conn.fetchval(
                "SELECT id FROM project_outreach WHERE project_id = $1 AND candidate_id = $2",
                project_id,
                candidate_id,
            )
            if existing_outreach:
                skipped += 1
                continue

            # Create outreach record and send screening invite
            token = secrets.token_urlsafe(32)
            await conn.execute(
                """
                INSERT INTO project_outreach (project_id, candidate_id, token, status, email_sent_at)
                VALUES ($1, $2, $3, 'screening_invited', NOW())
                """,
                project_id,
                candidate_id,
                token,
            )

            success = await email_service.send_screening_invite_email(
                to_email=app["email"],
                to_name=app["name"],
                company_name=project["company_name"],
                position_title=project["position_title"] or project["name"],
                location=project["location"],
                salary_range=salary_range,
                screening_token=token,
            )

            if success:
                accepted += 1
            else:
                await conn.execute(
                    "UPDATE project_outreach SET status = 'email_failed' WHERE token = $1",
                    token,
                )
                errors.append(f"Email failed for candidate {candidate_id}")
                accepted += 1  # Still counted as accepted (pipeline entry created)

        return BulkAcceptResponse(accepted=accepted, skipped=skipped, errors=errors)


@router.post("/{project_id}/applications/{application_id}/accept")
async def accept_application(project_id: UUID, application_id: UUID):
    """Accept a single applicant: add to pipeline and send screening invite."""
    from ..services.email import get_email_service

    email_service = get_email_service()

    async with get_connection() as conn:
        project = await conn.fetchrow(
            "SELECT company_name, name, position_title, location, salary_min, salary_max FROM projects WHERE id = $1",
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        app = await conn.fetchrow(
            """
            SELECT pa.*, c.name as candidate_name, c.email as candidate_email
            FROM project_applications pa
            JOIN candidates c ON pa.candidate_id = c.id
            WHERE pa.id = $1 AND pa.project_id = $2
            """,
            application_id,
            project_id,
        )
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        # Update status
        await conn.execute(
            "UPDATE project_applications SET status = 'accepted', updated_at = NOW() WHERE id = $1",
            application_id,
        )

        # Upsert into project_candidates
        await conn.execute(
            """
            INSERT INTO project_candidates (project_id, candidate_id, stage)
            VALUES ($1, $2, 'initial')
            ON CONFLICT (project_id, candidate_id) DO NOTHING
            """,
            project_id,
            app["candidate_id"],
        )

        # Check if outreach already exists
        existing_outreach = await conn.fetchval(
            "SELECT id FROM project_outreach WHERE project_id = $1 AND candidate_id = $2",
            project_id,
            app["candidate_id"],
        )

        email_sent = False
        if not existing_outreach and app["candidate_email"]:
            token = secrets.token_urlsafe(32)
            await conn.execute(
                """
                INSERT INTO project_outreach (project_id, candidate_id, token, status, email_sent_at)
                VALUES ($1, $2, $3, 'screening_invited', NOW())
                """,
                project_id,
                app["candidate_id"],
                token,
            )
            salary_range = _format_salary_range(project["salary_min"], project["salary_max"])
            email_sent = await email_service.send_screening_invite_email(
                to_email=app["candidate_email"],
                to_name=app["candidate_name"],
                company_name=project["company_name"],
                position_title=project["position_title"] or project["name"],
                location=project["location"],
                salary_range=salary_range,
                screening_token=token,
            )
            if not email_sent:
                await conn.execute(
                    "UPDATE project_outreach SET status = 'email_failed' WHERE token = $1",
                    token,
                )

        return {"status": "accepted", "screening_invite_sent": email_sent}


@router.post("/{project_id}/applications/{application_id}/reject")
async def reject_application(project_id: UUID, application_id: UUID):
    """Reject an applicant."""
    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE project_applications
            SET status = 'rejected', updated_at = NOW()
            WHERE id = $1 AND project_id = $2
            """,
            application_id,
            project_id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Application not found")

        return {"status": "rejected"}


@router.post("/{project_id}/close")
async def close_project(project_id: UUID):
    """Trigger project close workflow: analyze remaining interviews, rank, notify top 3."""
    async with get_connection() as conn:
        # Atomically transition active -> closing to prevent duplicate enqueues.
        # Any concurrent call (second admin, scheduler overlap, retry) will see
        # status='closing' and get a 409 instead of spawning a second worker.
        result = await conn.execute(
            """
            UPDATE projects SET status = 'closing', updated_at = NOW()
            WHERE id = $1 AND status NOT IN ('completed', 'closing')
            """,
            project_id,
        )
        if result == "UPDATE 0":
            existing = await conn.fetchval(
                "SELECT status FROM projects WHERE id = $1", project_id
            )
            if existing is None:
                raise HTTPException(status_code=404, detail="Project not found")
            if existing == 'closing':
                return {"status": "already_queued", "message": "Close workflow is already running."}
            raise HTTPException(status_code=409, detail=f"Cannot close project with status '{existing}'")

    from ...workers.tasks.project_close import close_project_async
    close_project_async.delay(str(project_id))

    return {"status": "queued", "message": "Project close workflow started. Rankings will be processed shortly."}


def _format_salary_range(salary_min, salary_max):
    """Format salary range for display."""
    if not salary_min and not salary_max:
        return None
    fmt = lambda n: f"${n:,}"
    if salary_min and salary_max:
        return f"{fmt(salary_min)} - {fmt(salary_max)}"
    if salary_min:
        return f"{fmt(salary_min)}+"
    return f"Up to {fmt(salary_max)}"
