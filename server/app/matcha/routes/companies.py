from typing import Optional
from uuid import UUID
import json

from fastapi import APIRouter, HTTPException

from ...database import get_connection
from ..models.company import CompanyCreate, CompanyResponse

router = APIRouter()


@router.post("", response_model=CompanyResponse)
async def create_company(company: CompanyCreate):
    """Create a new company."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO companies (name, industry, size)
            VALUES ($1, $2, $3)
            RETURNING id, name, industry, size, created_at
            """,
            company.name,
            company.industry,
            company.size,
        )
        return CompanyResponse(
            id=row["id"],
            name=row["name"],
            industry=row["industry"],
            size=row["size"],
            created_at=row["created_at"],
            interview_count=0,
        )


@router.get("", response_model=list[CompanyResponse])
async def list_companies():
    """List all companies with interview counts."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT c.*, COUNT(i.id) as interview_count
            FROM companies c
            LEFT JOIN interviews i ON c.id = i.company_id
            GROUP BY c.id
            ORDER BY c.created_at DESC
            """
        )
        return [
            CompanyResponse(
                id=row["id"],
                name=row["name"],
                industry=row["industry"],
                size=row["size"],
                created_at=row["created_at"],
                interview_count=row["interview_count"],
            )
            for row in rows
        ]


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: UUID):
    """Get a company by ID with its culture profile."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.*, COUNT(i.id) as interview_count
            FROM companies c
            LEFT JOIN interviews i ON c.id = i.company_id
            WHERE c.id = $1
            GROUP BY c.id
            """,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get culture profile if exists
        profile_row = await conn.fetchrow(
            "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
            company_id,
        )
        culture_profile = None
        if profile_row and profile_row["profile_data"]:
            culture_profile = json.loads(profile_row["profile_data"]) if isinstance(profile_row["profile_data"], str) else profile_row["profile_data"]

        return CompanyResponse(
            id=row["id"],
            name=row["name"],
            industry=row["industry"],
            size=row["size"],
            created_at=row["created_at"],
            culture_profile=culture_profile,
            interview_count=row["interview_count"],
        )


@router.delete("/{company_id}")
async def delete_company(company_id: UUID):
    """Delete a company and all related data."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM companies WHERE id = $1",
            company_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Company not found")
        return {"status": "deleted"}
