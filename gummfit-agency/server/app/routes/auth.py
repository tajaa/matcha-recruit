import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status
from uuid import UUID

from ..models.auth import (
    LoginRequest, TokenResponse, RefreshTokenRequest, UserResponse,
    CreatorRegister, AgencyRegister,
    CreatorProfile, AgencyProfile, CurrentUser,
    ChangePasswordRequest, ChangeEmailRequest,
)
from ..services.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token
)
from ..dependencies import get_current_user
from ..database import get_connection
from ..config import get_settings

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate user and return tokens."""
    async with get_connection() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, password_hash, role, is_active, created_at, last_login FROM users WHERE email = $1",
            request.email
        )

        if not user or not verify_password(request.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        if not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled"
            )

        # Update last login
        await conn.execute(
            "UPDATE users SET last_login = NOW() WHERE id = $1",
            user["id"]
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=user["last_login"]
            )
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    payload = decode_token(request.refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    async with get_connection() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, role, is_active, created_at, last_login FROM users WHERE id = $1",
            UUID(payload.sub)
        )

        if not user or not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        new_refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=user["last_login"]
            )
        )


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    import re
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text


@router.post("/register/creator", response_model=TokenResponse)
async def register_creator(request: CreatorRegister):
    """Register a new creator."""
    async with get_connection() as conn:
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'creator')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        await conn.execute(
            """
            INSERT INTO creators (user_id, display_name, bio, niches, social_handles)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user["id"],
            request.display_name,
            request.bio,
            json.dumps(request.niches) if request.niches else "[]",
            json.dumps(request.social_handles) if request.social_handles else "{}"
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=None
            )
        )


@router.post("/register/agency", response_model=TokenResponse)
async def register_agency(request: AgencyRegister):
    """Register a new agency and its owner."""
    async with get_connection() as conn:
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        base_slug = slugify(request.agency_name)
        slug = base_slug
        counter = 1
        while await conn.fetchval("SELECT id FROM agencies WHERE slug = $1", slug):
            slug = f"{base_slug}-{counter}"
            counter += 1

        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'agency')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        agency = await conn.fetchrow(
            """
            INSERT INTO agencies (name, slug, agency_type, description, website_url, industries)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            request.agency_name,
            slug,
            request.agency_type,
            request.description,
            request.website_url,
            json.dumps(request.industries) if request.industries else "[]"
        )

        await conn.execute(
            """
            INSERT INTO agency_members (agency_id, user_id, role, joined_at)
            VALUES ($1, $2, 'owner', NOW())
            """,
            agency["id"],
            user["id"]
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=None
            )
        )


@router.get("/me")
async def get_current_user_profile(current_user: CurrentUser = Depends(get_current_user)):
    """Get current user with full profile."""
    async with get_connection() as conn:
        if current_user.role == "creator":
            profile = await conn.fetchrow(
                """
                SELECT id, user_id, display_name, bio, profile_image_url,
                       niches, social_handles, audience_demographics, metrics,
                       is_verified, is_public, created_at
                FROM creators WHERE user_id = $1
                """,
                current_user.id
            )
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "display_name": profile["display_name"],
                    "bio": profile["bio"],
                    "profile_image_url": profile["profile_image_url"],
                    "niches": json.loads(profile["niches"]) if isinstance(profile["niches"], str) else (profile["niches"] or []),
                    "social_handles": json.loads(profile["social_handles"]) if isinstance(profile["social_handles"], str) else (profile["social_handles"] or {}),
                    "audience_demographics": json.loads(profile["audience_demographics"]) if isinstance(profile["audience_demographics"], str) else (profile["audience_demographics"] or {}),
                    "metrics": json.loads(profile["metrics"]) if isinstance(profile["metrics"], str) else (profile["metrics"] or {}),
                    "is_verified": profile["is_verified"],
                    "is_public": profile["is_public"],
                    "email": current_user.email,
                    "created_at": profile["created_at"].isoformat()
                } if profile else None
            }

        elif current_user.role == "agency":
            membership = await conn.fetchrow(
                """
                SELECT am.id, am.agency_id, am.user_id, am.role as member_role,
                       am.title, am.is_active, am.invited_at, am.joined_at,
                       a.name as agency_name, a.slug, a.agency_type, a.description,
                       a.logo_url, a.website_url, a.is_verified, a.contact_email,
                       a.industries, a.created_at
                FROM agency_members am
                JOIN agencies a ON am.agency_id = a.id
                WHERE am.user_id = $1 AND am.is_active = true
                """,
                current_user.id
            )
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": {
                    "id": str(membership["agency_id"]),
                    "user_id": str(membership["user_id"]),
                    "agency_name": membership["agency_name"],
                    "slug": membership["slug"],
                    "agency_type": membership["agency_type"],
                    "description": membership["description"],
                    "logo_url": membership["logo_url"],
                    "website_url": membership["website_url"],
                    "is_verified": membership["is_verified"],
                    "contact_email": membership["contact_email"],
                    "industries": json.loads(membership["industries"]) if isinstance(membership["industries"], str) else (membership["industries"] or []),
                    "member_role": membership["member_role"],
                    "email": current_user.email,
                    "created_at": membership["created_at"].isoformat()
                } if membership else None
            }

        elif current_user.role == "gumfit_admin":
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": None
            }

    return {"user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role}, "profile": None}


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Logout endpoint."""
    return {"status": "logged_out"}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Change password for current user."""
    async with get_connection() as conn:
        user = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1",
            current_user.id
        )

        if not user or not verify_password(request.current_password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters"
            )

        new_hash = hash_password(request.new_password)
        await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2",
            new_hash, current_user.id
        )

        return {"status": "password_changed"}


@router.post("/change-email")
async def change_email(
    request: ChangeEmailRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Change email for current user."""
    async with get_connection() as conn:
        user = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1",
            current_user.id
        )

        if not user or not verify_password(request.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is incorrect"
            )

        existing = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1 AND id != $2",
            request.new_email, current_user.id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use"
            )

        await conn.execute(
            "UPDATE users SET email = $1 WHERE id = $2",
            request.new_email, current_user.id
        )

        settings = get_settings()
        access_token = create_access_token(current_user.id, request.new_email, current_user.role)
        refresh_token = create_refresh_token(current_user.id, request.new_email, current_user.role)

        return {
            "status": "email_changed",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.jwt_access_token_expire_minutes * 60
        }
