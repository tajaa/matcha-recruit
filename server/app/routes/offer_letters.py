from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ..database import get_connection
from ..models.offer_letter import OfferLetter, OfferLetterCreate, OfferLetterUpdate

router = APIRouter()


@router.get("", response_model=List[OfferLetter])
async def list_offer_letters():
    """List all offer letters."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM offer_letters
            ORDER BY created_at DESC
            """
        )
        return [OfferLetter(**dict(row)) for row in rows]


@router.post("", response_model=OfferLetter)
async def create_offer_letter(offer: OfferLetterCreate):
    """Create a new offer letter draft."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO offer_letters (
                candidate_name, position_title, company_name, salary, bonus, 
                stock_options, start_date, employment_type, location, benefits, 
                manager_name, manager_title, expiration_date
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING *
            """,
            offer.candidate_name,
            offer.position_title,
            offer.company_name,
            offer.salary,
            offer.bonus,
            offer.stock_options,
            offer.start_date,
            offer.employment_type,
            offer.location,
            offer.benefits,
            offer.manager_name,
            offer.manager_title,
            offer.expiration_date,
        )
        return OfferLetter(**dict(row))


@router.get("/{offer_id}", response_model=OfferLetter)
async def get_offer_letter(offer_id: UUID):
    """Get details of a specific offer letter."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM offer_letters WHERE id = $1",
            offer_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Offer letter not found")
        return OfferLetter(**dict(row))


@router.patch("/{offer_id}", response_model=OfferLetter)
async def update_offer_letter(offer_id: UUID, update: OfferLetterUpdate):
    """Update an offer letter."""
    async with get_connection() as conn:
        # Check if exists
        exists = await conn.fetchval("SELECT 1 FROM offer_letters WHERE id = $1", offer_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Offer letter not found")

        # Build query dynamically
        update_data = update.dict(exclude_unset=True)
        if not update_data:
            # Nothing to update, return current state
            row = await conn.fetchrow("SELECT * FROM offer_letters WHERE id = $1", offer_id)
            return OfferLetter(**dict(row))

        set_clauses = []
        values = []
        idx = 1
        for key, value in update_data.items():
            set_clauses.append(f"{key} = ${idx}")
            values.append(value)
            idx += 1
        
        values.append(offer_id)
        query = f"""
            UPDATE offer_letters
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = ${idx}
            RETURNING *
        """
        
        row = await conn.fetchrow(query, *values)
        return OfferLetter(**dict(row))
