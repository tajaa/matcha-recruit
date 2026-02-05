"""
Agency routes for the Creator/Influencer Management Platform.
Handles agency profiles, team management, and creator discovery.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...database import get_connection
from ...core.dependencies import get_current_user
from ..dependencies import (
    require_agency,
    require_agency_membership,
    require_agency_admin,
)
from ...core.models.auth import CurrentUser
from ..models.agency import (
    AgencyCreate,
    AgencyUpdate,
    AgencyResponse,
    AgencyPublicResponse,
    AgencyMemberInvite,
    AgencyMemberUpdate,
    AgencyMemberResponse,
    AgencyWithMembership,
)
from ..models.creator import CreatorPublicResponse

router = APIRouter()


def parse_jsonb(value):
    """Parse JSONB value from database."""
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return value


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text


def row_to_agency_response(row) -> AgencyResponse:
    """Convert database row to AgencyResponse."""
    return AgencyResponse(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        agency_type=row["agency_type"],
        description=row["description"],
        logo_url=row["logo_url"],
        website_url=row["website_url"],
        is_verified=row["is_verified"],
        verification_status=row["verification_status"],
        contact_email=row["contact_email"],
        industries=parse_jsonb(row["industries"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# =============================================================================
# Agency Profile Endpoints
# =============================================================================

@router.get("/me", response_model=AgencyWithMembership)
async def get_my_agency(
    membership: dict = Depends(require_agency_membership)
):
    """Get the current user's agency with membership context."""
    async with get_connection() as conn:
        agency_row = await conn.fetchrow(
            "SELECT * FROM agencies WHERE id = $1",
            membership["agency_id"]
        )

        member_count = await conn.fetchval(
            "SELECT COUNT(*) FROM agency_members WHERE agency_id = $1 AND is_active = true",
            membership["agency_id"]
        )

        active_deals = await conn.fetchval(
            "SELECT COUNT(*) FROM brand_deals WHERE agency_id = $1 AND status IN ('open', 'draft')",
            membership["agency_id"]
        )

        user_row = await conn.fetchrow(
            "SELECT email FROM users WHERE id = $1",
            membership["user_id"]
        )

        return AgencyWithMembership(
            agency=row_to_agency_response(agency_row),
            membership=AgencyMemberResponse(
                id=membership["id"],
                agency_id=membership["agency_id"],
                user_id=membership["user_id"],
                email=user_row["email"],
                role=membership["role"],
                title=membership["title"],
                is_active=membership["is_active"],
                invited_at=membership["invited_at"],
                joined_at=membership["joined_at"],
            ),
            member_count=member_count,
            active_deals_count=active_deals,
        )


@router.put("/me", response_model=AgencyResponse)
async def update_my_agency(
    update: AgencyUpdate,
    membership: dict = Depends(require_agency_admin),
):
    """Update the agency profile. Requires admin/owner role."""
    async with get_connection() as conn:
        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Convert lists to JSON
        if "industries" in update_data and update_data["industries"] is not None:
            update_data["industries"] = json.dumps(update_data["industries"])

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]
        set_clauses.append("updated_at = NOW()")

        row = await conn.fetchrow(
            f"""
            UPDATE agencies
            SET {", ".join(set_clauses)}
            WHERE id = ${len(update_data) + 1}
            RETURNING *
            """,
            *update_data.values(),
            membership["agency_id"],
        )

        return row_to_agency_response(row)


@router.get("/public/{slug}", response_model=AgencyPublicResponse)
async def get_public_agency(slug: str):
    """Get a public agency profile."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM agencies WHERE slug = $1",
            slug,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Agency not found")

        return AgencyPublicResponse(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            agency_type=row["agency_type"],
            description=row["description"],
            logo_url=row["logo_url"],
            website_url=row["website_url"],
            is_verified=row["is_verified"],
            industries=parse_jsonb(row["industries"]),
        )


# =============================================================================
# Team Management Endpoints
# =============================================================================

@router.get("/me/members", response_model=list[AgencyMemberResponse])
async def list_agency_members(
    membership: dict = Depends(require_agency_membership)
):
    """List all members of the current agency."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT am.*, u.email
               FROM agency_members am
               JOIN users u ON am.user_id = u.id
               WHERE am.agency_id = $1
               ORDER BY am.role, am.joined_at""",
            membership["agency_id"],
        )

        return [
            AgencyMemberResponse(
                id=row["id"],
                agency_id=row["agency_id"],
                user_id=row["user_id"],
                email=row["email"],
                role=row["role"],
                title=row["title"],
                is_active=row["is_active"],
                invited_at=row["invited_at"],
                joined_at=row["joined_at"],
            )
            for row in rows
        ]


@router.post("/me/members", response_model=AgencyMemberResponse)
async def invite_agency_member(
    invite: AgencyMemberInvite,
    membership: dict = Depends(require_agency_admin),
):
    """Invite a new member to the agency. Requires admin/owner role."""
    async with get_connection() as conn:
        # Check if user exists
        user_row = await conn.fetchrow(
            "SELECT id, role FROM users WHERE email = $1",
            invite.email,
        )

        if not user_row:
            raise HTTPException(
                status_code=404,
                detail="User not found. They need to register first."
            )

        if user_row["role"] != "agency":
            raise HTTPException(
                status_code=400,
                detail="User must have an agency role to join an agency."
            )

        # Check if already a member
        existing = await conn.fetchrow(
            """SELECT * FROM agency_members
               WHERE agency_id = $1 AND user_id = $2""",
            membership["agency_id"],
            user_row["id"],
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="User is already a member of this agency."
            )

        # Create membership
        row = await conn.fetchrow(
            """INSERT INTO agency_members
               (agency_id, user_id, role, title, joined_at)
               VALUES ($1, $2, $3, $4, NOW())
               RETURNING *""",
            membership["agency_id"],
            user_row["id"],
            invite.role,
            invite.title,
        )

        return AgencyMemberResponse(
            id=row["id"],
            agency_id=row["agency_id"],
            user_id=row["user_id"],
            email=invite.email,
            role=row["role"],
            title=row["title"],
            is_active=row["is_active"],
            invited_at=row["invited_at"],
            joined_at=row["joined_at"],
        )


@router.put("/me/members/{member_id}", response_model=AgencyMemberResponse)
async def update_agency_member(
    member_id: UUID,
    update: AgencyMemberUpdate,
    membership: dict = Depends(require_agency_admin),
):
    """Update a member's role or status. Requires admin/owner role."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """SELECT am.*, u.email
               FROM agency_members am
               JOIN users u ON am.user_id = u.id
               WHERE am.id = $1 AND am.agency_id = $2""",
            member_id,
            membership["agency_id"],
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Member not found")

        # Prevent demoting the owner
        if existing["role"] == "owner" and update.role and update.role != "owner":
            raise HTTPException(
                status_code=400,
                detail="Cannot change the owner's role. Transfer ownership first."
            )

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]

        row = await conn.fetchrow(
            f"""UPDATE agency_members
                SET {", ".join(set_clauses)}
                WHERE id = ${len(update_data) + 1}
                RETURNING *""",
            *update_data.values(),
            member_id,
        )

        return AgencyMemberResponse(
            id=row["id"],
            agency_id=row["agency_id"],
            user_id=row["user_id"],
            email=existing["email"],
            role=row["role"],
            title=row["title"],
            is_active=row["is_active"],
            invited_at=row["invited_at"],
            joined_at=row["joined_at"],
        )


@router.delete("/me/members/{member_id}")
async def remove_agency_member(
    member_id: UUID,
    membership: dict = Depends(require_agency_admin),
):
    """Remove a member from the agency. Requires admin/owner role."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM agency_members WHERE id = $1 AND agency_id = $2",
            member_id,
            membership["agency_id"],
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Member not found")

        if existing["role"] == "owner":
            raise HTTPException(
                status_code=400,
                detail="Cannot remove the owner. Transfer ownership first."
            )

        await conn.execute(
            "DELETE FROM agency_members WHERE id = $1",
            member_id,
        )

        return {"status": "removed"}


# =============================================================================
# Creator Discovery Endpoints
# =============================================================================

@router.get("/creators/search", response_model=list[CreatorPublicResponse])
async def search_creators(
    query: Optional[str] = None,
    niches: Optional[str] = Query(None, description="Comma-separated niches"),
    min_followers: Optional[int] = None,
    verified_only: bool = False,
    limit: int = Query(20, le=100),
    offset: int = 0,
    membership: dict = Depends(require_agency_membership),
):
    """Search for creators to discover for potential deals."""
    async with get_connection() as conn:
        sql = "SELECT * FROM creators WHERE is_public = true"
        params = []
        param_count = 0

        if query:
            param_count += 1
            sql += f" AND (display_name ILIKE ${param_count} OR bio ILIKE ${param_count})"
            params.append(f"%{query}%")

        if niches:
            niche_list = [n.strip() for n in niches.split(",")]
            param_count += 1
            sql += f" AND niches ?| ${param_count}"
            params.append(niche_list)

        if verified_only:
            sql += " AND is_verified = true"

        sql += " ORDER BY is_verified DESC, created_at DESC"
        sql += f" LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
        params.extend([limit, offset])

        rows = await conn.fetch(sql, *params)

        return [
            CreatorPublicResponse(
                id=row["id"],
                display_name=row["display_name"],
                bio=row["bio"],
                profile_image_url=row["profile_image_url"],
                niches=parse_jsonb(row["niches"]),
                audience_demographics=parse_jsonb(row["audience_demographics"]) or {},
                metrics=parse_jsonb(row["metrics"]) or {},
                is_verified=row["is_verified"],
            )
            for row in rows
        ]


@router.get("/creators/{creator_id}", response_model=CreatorPublicResponse)
async def get_creator_profile(
    creator_id: UUID,
    membership: dict = Depends(require_agency_membership),
):
    """Get a creator's public profile for review."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM creators WHERE id = $1 AND is_public = true",
            creator_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Creator not found")

        return CreatorPublicResponse(
            id=row["id"],
            display_name=row["display_name"],
            bio=row["bio"],
            profile_image_url=row["profile_image_url"],
            niches=parse_jsonb(row["niches"]),
            audience_demographics=parse_jsonb(row["audience_demographics"]) or {},
            metrics=parse_jsonb(row["metrics"]) or {},
            is_verified=row["is_verified"],
        )
