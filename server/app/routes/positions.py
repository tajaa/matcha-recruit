from typing import Optional
from uuid import UUID
import json

from fastapi import APIRouter, HTTPException, Query

from ..database import get_connection
from ..models.position import (
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    PositionStatus,
    ExperienceLevel,
    RemotePolicy,
)

router = APIRouter()


def parse_jsonb(value):
    """Parse JSONB value from database."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def row_to_position_response(row, company_name: Optional[str] = None) -> PositionResponse:
    """Convert database row to PositionResponse."""
    return PositionResponse(
        id=row["id"],
        company_id=row["company_id"],
        title=row["title"],
        salary_min=row["salary_min"],
        salary_max=row["salary_max"],
        salary_currency=row["salary_currency"],
        location=row["location"],
        employment_type=row["employment_type"],
        requirements=parse_jsonb(row["requirements"]),
        responsibilities=parse_jsonb(row["responsibilities"]),
        required_skills=parse_jsonb(row["required_skills"]),
        preferred_skills=parse_jsonb(row["preferred_skills"]),
        experience_level=row["experience_level"],
        benefits=parse_jsonb(row["benefits"]),
        department=row["department"],
        reporting_to=row["reporting_to"],
        remote_policy=row["remote_policy"],
        visa_sponsorship=row["visa_sponsorship"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        company_name=company_name,
    )


@router.post("", response_model=PositionResponse)
async def create_position(position: PositionCreate):
    """Create a new position."""
    async with get_connection() as conn:
        # Verify company exists
        company_row = await conn.fetchrow(
            "SELECT id, name FROM companies WHERE id = $1",
            position.company_id,
        )
        if not company_row:
            raise HTTPException(status_code=404, detail="Company not found")

        row = await conn.fetchrow(
            """
            INSERT INTO positions (
                company_id, title, salary_min, salary_max, salary_currency,
                location, employment_type, requirements, responsibilities,
                required_skills, preferred_skills, experience_level, benefits,
                department, reporting_to, remote_policy, visa_sponsorship
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            RETURNING *
            """,
            position.company_id,
            position.title,
            position.salary_min,
            position.salary_max,
            position.salary_currency,
            position.location,
            position.employment_type.value if position.employment_type else None,
            json.dumps(position.requirements) if position.requirements else None,
            json.dumps(position.responsibilities) if position.responsibilities else None,
            json.dumps(position.required_skills) if position.required_skills else None,
            json.dumps(position.preferred_skills) if position.preferred_skills else None,
            position.experience_level.value if position.experience_level else None,
            json.dumps(position.benefits) if position.benefits else None,
            position.department,
            position.reporting_to,
            position.remote_policy.value if position.remote_policy else None,
            position.visa_sponsorship,
        )
        return row_to_position_response(row, company_row["name"])


@router.get("", response_model=list[PositionResponse])
async def list_positions(
    status: Optional[PositionStatus] = None,
    experience_level: Optional[ExperienceLevel] = None,
    remote_policy: Optional[RemotePolicy] = None,
    search: Optional[str] = Query(None, description="Search in title and skills"),
):
    """List all positions with optional filters."""
    async with get_connection() as conn:
        query = """
            SELECT p.*, c.name as company_name
            FROM positions p
            JOIN companies c ON p.company_id = c.id
            WHERE 1=1
        """
        params = []
        param_count = 0

        if status:
            param_count += 1
            query += f" AND p.status = ${param_count}"
            params.append(status.value)

        if experience_level:
            param_count += 1
            query += f" AND p.experience_level = ${param_count}"
            params.append(experience_level.value)

        if remote_policy:
            param_count += 1
            query += f" AND p.remote_policy = ${param_count}"
            params.append(remote_policy.value)

        if search:
            param_count += 1
            query += f"""
                AND (
                    p.title ILIKE ${param_count}
                    OR p.required_skills::text ILIKE ${param_count}
                    OR p.preferred_skills::text ILIKE ${param_count}
                )
            """
            params.append(f"%{search}%")

        query += " ORDER BY p.created_at DESC"

        rows = await conn.fetch(query, *params)
        return [row_to_position_response(row, row["company_name"]) for row in rows]


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(position_id: UUID):
    """Get a position by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.*, c.name as company_name
            FROM positions p
            JOIN companies c ON p.company_id = c.id
            WHERE p.id = $1
            """,
            position_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Position not found")

        return row_to_position_response(row, row["company_name"])


@router.put("/{position_id}", response_model=PositionResponse)
async def update_position(position_id: UUID, update: PositionUpdate):
    """Update a position."""
    async with get_connection() as conn:
        # Get existing position
        existing = await conn.fetchrow(
            "SELECT * FROM positions WHERE id = $1",
            position_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Position not found")

        # Build update query dynamically
        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Convert enums and lists to proper format
        if "employment_type" in update_data and update_data["employment_type"]:
            update_data["employment_type"] = update_data["employment_type"].value
        if "experience_level" in update_data and update_data["experience_level"]:
            update_data["experience_level"] = update_data["experience_level"].value
        if "remote_policy" in update_data and update_data["remote_policy"]:
            update_data["remote_policy"] = update_data["remote_policy"].value
        if "status" in update_data and update_data["status"]:
            update_data["status"] = update_data["status"].value

        # Convert lists to JSON
        for field in ["requirements", "responsibilities", "required_skills", "preferred_skills", "benefits"]:
            if field in update_data and update_data[field] is not None:
                update_data[field] = json.dumps(update_data[field])

        set_clauses = []
        params = []
        for i, (key, value) in enumerate(update_data.items(), start=1):
            set_clauses.append(f"{key} = ${i}")
            params.append(value)

        # Add updated_at
        params.append("NOW()")
        set_clauses.append(f"updated_at = NOW()")

        # Add position_id
        params.append(position_id)

        query = f"""
            UPDATE positions
            SET {", ".join(set_clauses)}
            WHERE id = ${len(params)}
            RETURNING *
        """

        # Execute with proper NOW() handling
        row = await conn.fetchrow(
            f"""
            UPDATE positions
            SET {", ".join(f"{k} = ${i+1}" for i, k in enumerate(update_data.keys()))}, updated_at = NOW()
            WHERE id = ${len(update_data) + 1}
            RETURNING *
            """,
            *update_data.values(),
            position_id,
        )

        # Get company name
        company_row = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1",
            row["company_id"],
        )

        return row_to_position_response(row, company_row["name"] if company_row else None)


@router.delete("/{position_id}")
async def delete_position(position_id: UUID):
    """Delete a position."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM positions WHERE id = $1",
            position_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Position not found")
        return {"status": "deleted"}


@router.get("/company/{company_id}", response_model=list[PositionResponse])
async def list_company_positions(
    company_id: UUID,
    status: Optional[PositionStatus] = None,
):
    """List all positions for a specific company."""
    async with get_connection() as conn:
        # Verify company exists
        company_row = await conn.fetchrow(
            "SELECT id, name FROM companies WHERE id = $1",
            company_id,
        )
        if not company_row:
            raise HTTPException(status_code=404, detail="Company not found")

        query = """
            SELECT p.*
            FROM positions p
            WHERE p.company_id = $1
        """
        params = [company_id]

        if status:
            query += " AND p.status = $2"
            params.append(status.value)

        query += " ORDER BY p.created_at DESC"

        rows = await conn.fetch(query, *params)
        return [row_to_position_response(row, company_row["name"]) for row in rows]
