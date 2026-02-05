"""Gummfit (Creator Agency) domain-specific dependencies."""
from typing import Optional

from fastapi import Depends, HTTPException, status

from ..dependencies import get_current_user, require_roles
from ..database import get_connection

# Gummfit role dependencies
require_creator = require_roles("creator")
require_agency = require_roles("agency")
require_gumfit_admin = require_roles("gumfit_admin")
require_creator_or_agency = require_roles("creator", "agency")
require_admin_or_creator = require_roles("admin", "creator")
require_admin_or_agency = require_roles("admin", "agency")


async def get_creator_info(
    current_user=Depends(get_current_user)
) -> Optional[dict]:
    """Get the creator record for a creator user. Returns None for non-creators."""
    if current_user.role != "creator":
        return None

    async with get_connection() as conn:
        creator = await conn.fetchrow(
            """SELECT id, user_id, display_name, bio, profile_image_url,
                      niches, social_handles, audience_demographics, metrics,
                      is_verified, is_public, created_at, updated_at
               FROM creators WHERE user_id = $1""",
            current_user.id
        )
        if creator:
            return dict(creator)
        return None


async def require_creator_record(
    current_user=Depends(require_creator)
) -> dict:
    """Require the current user to be a creator with a valid creator record."""
    async with get_connection() as conn:
        creator = await conn.fetchrow(
            """SELECT id, user_id, display_name, bio, profile_image_url,
                      niches, social_handles, audience_demographics, metrics,
                      is_verified, is_public, created_at, updated_at
               FROM creators WHERE user_id = $1""",
            current_user.id
        )
        if not creator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Creator record not found"
            )
        return dict(creator)


async def get_agency_info(
    current_user=Depends(get_current_user)
) -> Optional[dict]:
    """Get the agency and membership info for an agency user. Returns None for non-agency users."""
    if current_user.role != "agency":
        return None

    async with get_connection() as conn:
        # Get agency membership for this user
        membership = await conn.fetchrow(
            """SELECT am.*, a.id as agency_id, a.name as agency_name, a.slug,
                      a.agency_type, a.description, a.logo_url, a.website_url,
                      a.is_verified, a.contact_email, a.industries
               FROM agency_members am
               JOIN agencies a ON am.agency_id = a.id
               WHERE am.user_id = $1 AND am.is_active = true""",
            current_user.id
        )
        if membership:
            return dict(membership)
        return None


async def require_agency_membership(
    current_user=Depends(require_agency)
) -> dict:
    """Require the current user to be an agency member with an active membership."""
    async with get_connection() as conn:
        membership = await conn.fetchrow(
            """SELECT am.*, a.id as agency_id, a.name as agency_name, a.slug,
                      a.agency_type, a.description, a.logo_url, a.website_url,
                      a.is_verified, a.contact_email, a.industries
               FROM agency_members am
               JOIN agencies a ON am.agency_id = a.id
               WHERE am.user_id = $1 AND am.is_active = true""",
            current_user.id
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agency membership not found"
            )
        return dict(membership)


async def require_agency_admin(
    current_user=Depends(require_agency)
) -> dict:
    """Require the current user to be an agency owner or admin."""
    async with get_connection() as conn:
        membership = await conn.fetchrow(
            """SELECT am.*, a.id as agency_id, a.name as agency_name, a.slug,
                      a.agency_type, a.description, a.logo_url, a.website_url,
                      a.is_verified, a.contact_email, a.industries
               FROM agency_members am
               JOIN agencies a ON am.agency_id = a.id
               WHERE am.user_id = $1 AND am.is_active = true
               AND am.role IN ('owner', 'admin')""",
            current_user.id
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be an agency owner or admin to perform this action"
            )
        return dict(membership)
