from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .services.auth import decode_token
from .models.auth import CurrentUser, UserRole
from .database import get_connection

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CurrentUser:
    """Dependency to get the current authenticated user."""
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = UUID(payload.sub)

    async with get_connection() as conn:
        # Verify user exists and is active
        user_row = await conn.fetchrow(
            """SELECT id, email, role, is_active,
                      COALESCE(beta_features, '{}'::jsonb) as beta_features,
                      COALESCE(interview_prep_tokens, 0) as interview_prep_tokens,
                      COALESCE(allowed_interview_roles, '[]'::jsonb) as allowed_interview_roles
               FROM users WHERE id = $1""",
            user_id
        )

        if not user_row or not user_row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        beta_features = user_row["beta_features"] if user_row["beta_features"] else {}
        if isinstance(beta_features, str):
            import json
            beta_features = json.loads(beta_features)

        allowed_roles = user_row["allowed_interview_roles"] if user_row["allowed_interview_roles"] else []
        if isinstance(allowed_roles, str):
            import json
            allowed_roles = json.loads(allowed_roles)

        return CurrentUser(
            id=user_row["id"],
            email=user_row["email"],
            role=user_row["role"],
            profile=None,  # Profile loaded on demand
            beta_features=beta_features,
            interview_prep_tokens=user_row["interview_prep_tokens"],
            allowed_interview_roles=allowed_roles
        )


def require_roles(*roles: UserRole):
    """Dependency factory for role-based access control."""
    async def role_checker(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(roles)}"
            )
        return current_user
    return role_checker


# Convenience dependencies
require_admin = require_roles("admin")
require_client = require_roles("client")
require_candidate = require_roles("candidate")
require_employee = require_roles("employee")
require_creator = require_roles("creator")
require_agency = require_roles("agency")
require_admin_or_client = require_roles("admin", "client")
require_admin_or_employee = require_roles("admin", "employee")
require_creator_or_agency = require_roles("creator", "agency")
require_admin_or_creator = require_roles("admin", "creator")
require_admin_or_agency = require_roles("admin", "agency")


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[CurrentUser]:
    """Optional auth - returns None if no valid token."""
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


async def get_client_company_id(
    current_user: CurrentUser = Depends(get_current_user)
) -> Optional[UUID]:
    """Get the company_id for a client user. For admins, returns the first company."""
    async with get_connection() as conn:
        if current_user.role == "admin":
            # Admin users: default to first company
            # TODO: Add company selector for admins to switch between companies
            company_id = await conn.fetchval("SELECT id FROM companies ORDER BY created_at LIMIT 1")
            return company_id

        if current_user.role == "client":
            company_id = await conn.fetchval(
                "SELECT company_id FROM clients WHERE user_id = $1",
                current_user.id
            )
            return company_id

        return None


async def get_employee_info(
    current_user: CurrentUser = Depends(get_current_user)
) -> Optional[dict]:
    """Get the employee record for an employee user. Returns None for non-employees."""
    if current_user.role != "employee":
        return None

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            """SELECT id, org_id, email, first_name, last_name, work_state,
                      employment_type, start_date, termination_date, manager_id,
                      phone, address, emergency_contact, created_at, updated_at
               FROM employees WHERE user_id = $1""",
            current_user.id
        )
        if employee:
            return dict(employee)
        return None


async def require_employee_record(
    current_user: CurrentUser = Depends(require_employee)
) -> dict:
    """Require the current user to be an employee with a valid employee record."""
    async with get_connection() as conn:
        employee = await conn.fetchrow(
            """SELECT id, org_id, email, first_name, last_name, work_state,
                      employment_type, start_date, termination_date, manager_id,
                      phone, address, emergency_contact, created_at, updated_at
               FROM employees WHERE user_id = $1""",
            current_user.id
        )
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee record not found"
            )
        return dict(employee)


async def require_interview_prep_access(
    current_user: CurrentUser = Depends(get_current_user)
) -> CurrentUser:
    """
    Dependency for interview prep access control.
    - Admins: always allowed
    - Candidates: need beta access + at least 1 token
    """
    # Admins always have access
    if current_user.role == "admin":
        return current_user

    # Candidates need beta access
    if current_user.role == "candidate":
        has_beta = current_user.beta_features.get("interview_prep", False)
        if not has_beta:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to Interview Prep. Contact support for beta access."
            )
        if current_user.interview_prep_tokens <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You have no interview prep tokens remaining."
            )
        return current_user

    # Other roles (client) don't have access
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Interview prep is not available for your account type."
    )


async def get_creator_info(
    current_user: CurrentUser = Depends(get_current_user)
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
    current_user: CurrentUser = Depends(require_creator)
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
    current_user: CurrentUser = Depends(get_current_user)
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
    current_user: CurrentUser = Depends(require_agency)
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
    current_user: CurrentUser = Depends(require_agency)
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
