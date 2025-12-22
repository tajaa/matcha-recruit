import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ..database import get_connection
from ..models.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectCandidateAdd,
    ProjectCandidateBulkAdd,
    ProjectCandidateUpdate,
    ProjectCandidateResponse,
    ProjectStatus,
    CandidateStage,
)

router = APIRouter()


@router.post("", response_model=ProjectResponse)
async def create_project(project: ProjectCreate):
    """Create a new project."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO projects (company_name, name, position_title, location, salary_min, salary_max, benefits, requirements, status, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id, company_name, name, position_title, location, salary_min, salary_max, benefits, requirements, status, notes, created_at, updated_at
            """,
            project.company_name,
            project.name,
            project.position_title,
            project.location,
            project.salary_min,
            project.salary_max,
            project.benefits,
            project.requirements,
            project.status.value,
            project.notes,
        )

        return ProjectResponse(
            id=row["id"],
            company_name=row["company_name"],
            name=row["name"],
            position_title=row["position_title"],
            location=row["location"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            benefits=row["benefits"],
            requirements=row["requirements"],
            status=row["status"],
            notes=row["notes"],
            candidate_count=0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(status: Optional[str] = None):
    """List projects with optional status filter."""
    async with get_connection() as conn:
        if status:
            query = """
                SELECT p.*, COUNT(pc.id) as candidate_count
                FROM projects p
                LEFT JOIN project_candidates pc ON p.id = pc.project_id
                WHERE p.status = $1
                GROUP BY p.id
                ORDER BY p.updated_at DESC
            """
            rows = await conn.fetch(query, status)
        else:
            query = """
                SELECT p.*, COUNT(pc.id) as candidate_count
                FROM projects p
                LEFT JOIN project_candidates pc ON p.id = pc.project_id
                GROUP BY p.id
                ORDER BY p.updated_at DESC
            """
            rows = await conn.fetch(query)

        return [
            ProjectResponse(
                id=row["id"],
                company_name=row["company_name"],
                name=row["name"],
                position_title=row["position_title"],
                location=row["location"],
                salary_min=row["salary_min"],
                salary_max=row["salary_max"],
                benefits=row["benefits"],
                requirements=row["requirements"],
                status=row["status"],
                notes=row["notes"],
                candidate_count=row["candidate_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID):
    """Get a project by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.*, COUNT(pc.id) as candidate_count
            FROM projects p
            LEFT JOIN project_candidates pc ON p.id = pc.project_id
            WHERE p.id = $1
            GROUP BY p.id
            """,
            project_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        return ProjectResponse(
            id=row["id"],
            company_name=row["company_name"],
            name=row["name"],
            position_title=row["position_title"],
            location=row["location"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            benefits=row["benefits"],
            requirements=row["requirements"],
            status=row["status"],
            notes=row["notes"],
            candidate_count=row["candidate_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


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
            RETURNING id, company_name, name, position_title, location, salary_min, salary_max, benefits, requirements, status, notes, created_at, updated_at
        """

        row = await conn.fetchrow(query, *params)

        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get candidate count
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM project_candidates WHERE project_id = $1",
            project_id,
        )

        return ProjectResponse(
            id=row["id"],
            company_name=row["company_name"],
            name=row["name"],
            position_title=row["position_title"],
            location=row["location"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            benefits=row["benefits"],
            requirements=row["requirements"],
            status=row["status"],
            notes=row["notes"],
            candidate_count=count,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


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
