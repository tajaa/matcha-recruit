"""GumFit Admin routes for managing creators, agencies, users, and invites."""

from datetime import datetime, timedelta
from typing import Optional, Literal
from uuid import UUID, uuid4
import secrets
import json

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, EmailStr

from ..database import get_connection
from ..models.auth import CurrentUser
from ..dependencies import require_gumfit_admin

router = APIRouter()


def parse_json_field(value) -> list:
    """Parse a JSON field that might be a string or already a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


# ============================================================================
# Response Models
# ============================================================================

class GumFitStats(BaseModel):
    total_creators: int
    total_agencies: int
    total_users: int
    pending_invites: int
    active_campaigns: int
    recent_signups: int


class GumFitCreator(BaseModel):
    id: UUID
    display_name: str
    email: str
    profile_image_url: Optional[str]
    is_verified: bool
    is_public: bool
    niches: list[str]
    total_followers: int
    created_at: datetime


class GumFitCreatorList(BaseModel):
    creators: list[GumFitCreator]
    total: int


class GumFitAgency(BaseModel):
    id: UUID
    agency_name: str
    slug: str
    email: str
    logo_url: Optional[str]
    agency_type: str
    is_verified: bool
    industries: list[str]
    member_count: int
    created_at: datetime


class GumFitAgencyList(BaseModel):
    agencies: list[GumFitAgency]
    total: int


class GumFitUser(BaseModel):
    id: UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]
    profile_name: Optional[str]


class GumFitUserList(BaseModel):
    users: list[GumFitUser]
    total: int


class GumFitInvite(BaseModel):
    id: UUID
    email: str
    invite_type: Literal["creator", "agency"]
    status: Literal["pending", "accepted", "expired"]
    message: Optional[str]
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]


class GumFitInviteList(BaseModel):
    invites: list[GumFitInvite]
    total: int


class InviteCreate(BaseModel):
    email: EmailStr
    invite_type: Literal["creator", "agency"]
    message: Optional[str] = None


class InviteResponse(BaseModel):
    id: UUID
    email: str
    invite_type: str
    status: str
    created_at: datetime
    expires_at: datetime


# ============================================================================
# Stats Endpoint
# ============================================================================

@router.get("/stats", response_model=GumFitStats)
async def get_gumfit_stats(
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """Get platform statistics for GumFit admin dashboard."""
    async with get_connection() as conn:
        # Count creators
        total_creators = await conn.fetchval(
            "SELECT COUNT(*) FROM creators"
        ) or 0

        # Count agencies
        total_agencies = await conn.fetchval(
            "SELECT COUNT(*) FROM agencies"
        ) or 0

        # Count users (creators and agencies only)
        total_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE role IN ('creator', 'agency')"
        ) or 0

        # Count pending invites
        pending_invites = await conn.fetchval(
            """SELECT COUNT(*) FROM gumfit_invites
               WHERE status = 'pending' AND expires_at > NOW()"""
        ) or 0

        # Count active campaigns (if table exists)
        try:
            active_campaigns = await conn.fetchval(
                "SELECT COUNT(*) FROM campaigns WHERE status = 'active'"
            ) or 0
        except Exception:
            active_campaigns = 0

        # Count recent signups (last 7 days)
        recent_signups = await conn.fetchval(
            """SELECT COUNT(*) FROM users
               WHERE role IN ('creator', 'agency')
               AND created_at > NOW() - INTERVAL '7 days'"""
        ) or 0

        return GumFitStats(
            total_creators=total_creators,
            total_agencies=total_agencies,
            total_users=total_users,
            pending_invites=pending_invites,
            active_campaigns=active_campaigns,
            recent_signups=recent_signups,
        )


# ============================================================================
# Creators Endpoints
# ============================================================================

@router.get("/creators", response_model=GumFitCreatorList)
async def list_creators(
    search: Optional[str] = None,
    verified: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """List all creators with optional filtering."""
    async with get_connection() as conn:
        # Build query
        where_clauses = []
        params = []
        param_idx = 1

        if search:
            where_clauses.append(
                f"(c.display_name ILIKE ${param_idx} OR u.email ILIKE ${param_idx})"
            )
            params.append(f"%{search}%")
            param_idx += 1

        if verified is not None:
            where_clauses.append(f"c.is_verified = ${param_idx}")
            params.append(verified)
            param_idx += 1

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Get total count
        total = await conn.fetchval(
            f"""SELECT COUNT(*) FROM creators c
                JOIN users u ON c.user_id = u.id
                {where_sql}""",
            *params
        )

        # Get creators
        rows = await conn.fetch(
            f"""SELECT c.id, c.display_name, u.email, c.profile_image_url,
                       c.is_verified, c.is_public, c.niches,
                       COALESCE((c.metrics->>'total_followers')::int, 0) as total_followers,
                       c.created_at
                FROM creators c
                JOIN users u ON c.user_id = u.id
                {where_sql}
                ORDER BY c.created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
            *params, limit, skip
        )

        creators = [
            GumFitCreator(
                id=row["id"],
                display_name=row["display_name"],
                email=row["email"],
                profile_image_url=row["profile_image_url"],
                is_verified=row["is_verified"],
                is_public=row["is_public"],
                niches=parse_json_field(row["niches"]),
                total_followers=row["total_followers"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return GumFitCreatorList(creators=creators, total=total or 0)


@router.patch("/creators/{creator_id}/verify")
async def toggle_creator_verification(
    creator_id: UUID,
    verified: bool,
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """Toggle creator verification status."""
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE creators SET is_verified = $1, updated_at = NOW()
               WHERE id = $2""",
            verified, creator_id
        )
        if result == "UPDATE 0":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Creator not found"
            )
        return {"success": True, "is_verified": verified}


# ============================================================================
# Agencies Endpoints
# ============================================================================

@router.get("/agencies", response_model=GumFitAgencyList)
async def list_agencies(
    search: Optional[str] = None,
    verified: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """List all agencies with optional filtering."""
    async with get_connection() as conn:
        # Build query
        where_clauses = []
        params = []
        param_idx = 1

        if search:
            where_clauses.append(
                f"(a.name ILIKE ${param_idx} OR a.contact_email ILIKE ${param_idx})"
            )
            params.append(f"%{search}%")
            param_idx += 1

        if verified is not None:
            where_clauses.append(f"a.is_verified = ${param_idx}")
            params.append(verified)
            param_idx += 1

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Get total count
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM agencies a {where_sql}",
            *params
        )

        # Get agencies with member count
        rows = await conn.fetch(
            f"""SELECT a.id, a.name as agency_name, a.slug,
                       COALESCE(a.contact_email, '') as email,
                       a.logo_url, a.agency_type, a.is_verified, a.industries,
                       a.created_at,
                       (SELECT COUNT(*) FROM agency_members am WHERE am.agency_id = a.id AND am.is_active = true) as member_count
                FROM agencies a
                {where_sql}
                ORDER BY a.created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
            *params, limit, skip
        )

        agencies = [
            GumFitAgency(
                id=row["id"],
                agency_name=row["agency_name"],
                slug=row["slug"],
                email=row["email"],
                logo_url=row["logo_url"],
                agency_type=row["agency_type"],
                is_verified=row["is_verified"],
                industries=parse_json_field(row["industries"]),
                member_count=row["member_count"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return GumFitAgencyList(agencies=agencies, total=total or 0)


@router.patch("/agencies/{agency_id}/verify")
async def toggle_agency_verification(
    agency_id: UUID,
    verified: bool,
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """Toggle agency verification status."""
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE agencies SET is_verified = $1, updated_at = NOW()
               WHERE id = $2""",
            verified, agency_id
        )
        if result == "UPDATE 0":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agency not found"
            )
        return {"success": True, "is_verified": verified}


# ============================================================================
# Users Endpoints
# ============================================================================

@router.get("/users", response_model=GumFitUserList)
async def list_users(
    search: Optional[str] = None,
    role: Optional[Literal["creator", "agency"]] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """List all platform users (creators and agencies) with optional filtering."""
    async with get_connection() as conn:
        # Build query
        where_clauses = ["u.role IN ('creator', 'agency')"]
        params = []
        param_idx = 1

        if search:
            where_clauses.append(f"u.email ILIKE ${param_idx}")
            params.append(f"%{search}%")
            param_idx += 1

        if role:
            where_clauses.append(f"u.role = ${param_idx}")
            params.append(role)
            param_idx += 1

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        # Get total count
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM users u {where_sql}",
            *params
        )

        # Get users with profile names
        rows = await conn.fetch(
            f"""SELECT u.id, u.email, u.role, u.is_active, u.created_at, u.last_login,
                       CASE
                           WHEN u.role = 'creator' THEN (SELECT display_name FROM creators WHERE user_id = u.id)
                           WHEN u.role = 'agency' THEN (SELECT a.name FROM agencies a JOIN agency_members am ON am.agency_id = a.id WHERE am.user_id = u.id LIMIT 1)
                       END as profile_name
                FROM users u
                {where_sql}
                ORDER BY u.created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
            *params, limit, skip
        )

        users = [
            GumFitUser(
                id=row["id"],
                email=row["email"],
                role=row["role"],
                is_active=row["is_active"],
                created_at=row["created_at"],
                last_login=row["last_login"],
                profile_name=row["profile_name"],
            )
            for row in rows
        ]

        return GumFitUserList(users=users, total=total or 0)


@router.patch("/users/{user_id}/active")
async def toggle_user_active(
    user_id: UUID,
    is_active: bool,
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """Toggle user active status."""
    async with get_connection() as conn:
        # Verify user is a creator or agency
        user = await conn.fetchrow(
            "SELECT role FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        if user["role"] not in ("creator", "agency"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only manage creator and agency users"
            )

        await conn.execute(
            "UPDATE users SET is_active = $1 WHERE id = $2",
            is_active, user_id
        )
        return {"success": True, "is_active": is_active}


# ============================================================================
# Invites Endpoints
# ============================================================================

@router.get("/invites", response_model=GumFitInviteList)
async def list_invites(
    search: Optional[str] = None,
    invite_status: Optional[Literal["pending", "accepted", "expired"]] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """List all invites with optional filtering."""
    async with get_connection() as conn:
        # Build query
        where_clauses = []
        params = []
        param_idx = 1

        if search:
            where_clauses.append(f"email ILIKE ${param_idx}")
            params.append(f"%{search}%")
            param_idx += 1

        if invite_status:
            if invite_status == "expired":
                where_clauses.append("status = 'pending' AND expires_at <= NOW()")
            elif invite_status == "pending":
                where_clauses.append("status = 'pending' AND expires_at > NOW()")
            else:
                where_clauses.append(f"status = ${param_idx}")
                params.append(invite_status)
                param_idx += 1

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Get total count
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM gumfit_invites {where_sql}",
            *params
        )

        # Get invites
        rows = await conn.fetch(
            f"""SELECT id, email, invite_type, status, message, created_at,
                       expires_at, accepted_at,
                       CASE WHEN status = 'pending' AND expires_at <= NOW() THEN 'expired' ELSE status END as computed_status
                FROM gumfit_invites
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
            *params, limit, skip
        )

        invites = [
            GumFitInvite(
                id=row["id"],
                email=row["email"],
                invite_type=row["invite_type"],
                status=row["computed_status"],
                message=row["message"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                accepted_at=row["accepted_at"],
            )
            for row in rows
        ]

        return GumFitInviteList(invites=invites, total=total or 0)


@router.post("/invites", response_model=InviteResponse)
async def send_invite(
    invite: InviteCreate,
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """Send an invite to a creator or agency."""
    async with get_connection() as conn:
        # Check if email already has a pending invite
        existing = await conn.fetchrow(
            """SELECT id FROM gumfit_invites
               WHERE email = $1 AND status = 'pending' AND expires_at > NOW()""",
            invite.email
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An invite is already pending for this email"
            )

        # Check if user already exists
        existing_user = await conn.fetchrow(
            "SELECT id FROM users WHERE email = $1",
            invite.email
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists"
            )

        # Create invite
        invite_id = uuid4()
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)

        await conn.execute(
            """INSERT INTO gumfit_invites
               (id, email, invite_type, token, message, status, created_at, expires_at, created_by)
               VALUES ($1, $2, $3, $4, $5, 'pending', NOW(), $6, $7)""",
            invite_id, invite.email, invite.invite_type, token,
            invite.message, expires_at, current_user.id
        )

        # TODO: Send email with invite link
        # await send_invite_email(invite.email, token, invite.invite_type, invite.message)

        return InviteResponse(
            id=invite_id,
            email=invite.email,
            invite_type=invite.invite_type,
            status="pending",
            created_at=datetime.utcnow(),
            expires_at=expires_at,
        )


@router.post("/invites/{invite_id}/resend")
async def resend_invite(
    invite_id: UUID,
    current_user: CurrentUser = Depends(require_gumfit_admin)
):
    """Resend an invite (extends expiration)."""
    async with get_connection() as conn:
        invite = await conn.fetchrow(
            "SELECT * FROM gumfit_invites WHERE id = $1",
            invite_id
        )
        if not invite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invite not found"
            )
        if invite["status"] == "accepted":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invite has already been accepted"
            )

        # Generate new token and extend expiration
        new_token = secrets.token_urlsafe(32)
        new_expires = datetime.utcnow() + timedelta(days=7)

        await conn.execute(
            """UPDATE gumfit_invites
               SET token = $1, expires_at = $2, status = 'pending'
               WHERE id = $3""",
            new_token, new_expires, invite_id
        )

        # TODO: Send email with new invite link
        # await send_invite_email(invite["email"], new_token, invite["invite_type"], invite["message"])

        return {"success": True, "expires_at": new_expires.isoformat()}
