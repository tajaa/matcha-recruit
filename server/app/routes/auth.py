import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status

from ..database import get_connection
from uuid import UUID

from ..models.auth import (
    LoginRequest, TokenResponse, RefreshTokenRequest, UserResponse,
    AdminRegister, ClientRegister, CandidateRegister,
    AdminProfile, ClientProfile, CandidateProfile, CurrentUser,
    ChangePasswordRequest, ChangeEmailRequest, UpdateProfileRequest,
    CandidateBetaInfo, CandidateBetaListResponse, BetaToggleRequest,
    TokenAwardRequest, AllowedRolesRequest, CandidateSessionSummary
)
from ..services.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token
)
from ..dependencies import get_current_user, require_admin
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
            payload.sub
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


@router.post("/register/admin", response_model=TokenResponse, dependencies=[Depends(require_admin)])
async def register_admin(request: AdminRegister):
    """Register a new admin (admin only)."""
    async with get_connection() as conn:
        # Check if email exists
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'admin')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Create admin profile
        await conn.execute(
            "INSERT INTO admins (user_id, name) VALUES ($1, $2)",
            user["id"], request.name
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


@router.post("/register/client", response_model=TokenResponse)
async def register_client(request: ClientRegister):
    """Register a new client linked to a company."""
    async with get_connection() as conn:
        # Check if email exists
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Verify company exists
        company = await conn.fetchrow("SELECT id FROM companies WHERE id = $1", request.company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'client')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Create client profile
        await conn.execute(
            """
            INSERT INTO clients (user_id, company_id, name, phone, job_title)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user["id"], request.company_id, request.name, request.phone, request.job_title
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


@router.post("/register/employee", response_model=TokenResponse)
async def register_employee(request: EmployeeRegister):
    """Register a new employee."""
    async with get_connection() as conn:
        # Check if email exists
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Verify company exists
        company = await conn.fetchrow("SELECT id FROM companies WHERE id = $1", request.company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'employee')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Create employee profile
        await conn.execute(
            """
            INSERT INTO employees (user_id, org_id, email, first_name, last_name, work_state, employment_type, start_date)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            user["id"], request.company_id, request.email, request.first_name, request.last_name,
            request.work_state, request.employment_type, request.start_date
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


@router.post("/register/candidate", response_model=TokenResponse)
async def register_candidate(request: CandidateRegister):
    """Register a new candidate."""
    async with get_connection() as conn:
        # Check if email exists in users
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'candidate')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Check if candidate record exists with this email (from resume upload)
        candidate = await conn.fetchrow(
            "SELECT id FROM candidates WHERE email = $1",
            request.email
        )

        if candidate:
            # Link existing candidate to user
            await conn.execute(
                "UPDATE candidates SET user_id = $1, name = COALESCE(name, $2), phone = COALESCE(phone, $3) WHERE id = $4",
                user["id"], request.name, request.phone, candidate["id"]
            )
        else:
            # Create new candidate record
            await conn.execute(
                "INSERT INTO candidates (user_id, name, email, phone) VALUES ($1, $2, $3, $4)",
                user["id"], request.name, request.email, request.phone
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
        if current_user.role == "admin":
            profile = await conn.fetchrow(
                "SELECT id, user_id, name, created_at FROM admins WHERE user_id = $1",
                current_user.id
            )
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "name": profile["name"],
                    "email": current_user.email,
                    "created_at": profile["created_at"].isoformat()
                } if profile else None
            }

        elif current_user.role == "client":
            profile = await conn.fetchrow(
                """
                SELECT c.id, c.user_id, c.company_id, comp.name as company_name,
                       c.name, c.phone, c.job_title, c.created_at
                FROM clients c
                JOIN companies comp ON c.company_id = comp.id
                WHERE c.user_id = $1
                """,
                current_user.id
            )
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "company_id": str(profile["company_id"]),
                    "company_name": profile["company_name"],
                    "name": profile["name"],
                    "phone": profile["phone"],
                    "job_title": profile["job_title"],
                    "email": current_user.email,
                    "created_at": profile["created_at"].isoformat()
                } if profile else None
            }

        elif current_user.role == "candidate":
            profile = await conn.fetchrow(
                """
                SELECT id, user_id, name, email, phone, skills, experience_years, created_at
                FROM candidates WHERE user_id = $1
                """,
                current_user.id
            )
            skills_data = json.loads(profile["skills"]) if profile and profile["skills"] else []
            return {
                "user": {
                    "id": str(current_user.id),
                    "email": current_user.email,
                    "role": current_user.role,
                    "beta_features": current_user.beta_features,
                    "interview_prep_tokens": current_user.interview_prep_tokens,
                    "allowed_interview_roles": current_user.allowed_interview_roles
                },
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]) if profile["user_id"] else None,
                    "name": profile["name"],
                    "email": profile["email"],
                    "phone": profile["phone"],
                    "skills": skills_data,
                    "experience_years": profile["experience_years"],
                    "created_at": profile["created_at"].isoformat()
                } if profile else None
            }

        elif current_user.role == "employee":
            profile = await conn.fetchrow(
                """
                SELECT e.id, e.user_id, e.org_id, c.name as company_name,
                       e.first_name, e.last_name, e.email, e.work_state,
                       e.employment_type, e.start_date, e.manager_id, e.created_at
                FROM employees e
                JOIN companies c ON e.org_id = c.id
                WHERE e.user_id = $1
                """,
                current_user.id
            )
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "company_id": str(profile["org_id"]),
                    "company_name": profile["company_name"],
                    "first_name": profile["first_name"],
                    "last_name": profile["last_name"],
                    "email": profile["email"],
                    "work_state": profile["work_state"],
                    "employment_type": profile["employment_type"],
                    "start_date": profile["start_date"].isoformat() if profile["start_date"] else None,
                    "manager_id": str(profile["manager_id"]) if profile["manager_id"] else None,
                    "created_at": profile["created_at"].isoformat()
                } if profile else None
            }

    return {"user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role}, "profile": None}


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Logout endpoint (for audit/future token blacklist)."""
    return {"status": "logged_out"}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Change password for current user."""
    async with get_connection() as conn:
        # Get current password hash
        user = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1",
            current_user.id
        )

        if not user or not verify_password(request.current_password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        # Validate new password
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters"
            )

        # Update password
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
        # Verify password
        user = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1",
            current_user.id
        )

        if not user or not verify_password(request.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is incorrect"
            )

        # Check if new email is already taken
        existing = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1 AND id != $2",
            request.new_email, current_user.id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use"
            )

        # Update email in users table
        await conn.execute(
            "UPDATE users SET email = $1 WHERE id = $2",
            request.new_email, current_user.id
        )

        # Also update email in role-specific table if applicable
        if current_user.role == "candidate":
            await conn.execute(
                "UPDATE candidates SET email = $1 WHERE user_id = $2",
                request.new_email, current_user.id
            )

        # Generate new tokens with updated email
        settings = get_settings()
        access_token = create_access_token(current_user.id, request.new_email, current_user.role)
        refresh_token = create_refresh_token(current_user.id, request.new_email, current_user.role)

        return {
            "status": "email_changed",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.jwt_access_token_expire_minutes * 60
        }


@router.put("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update profile information for current user."""
    async with get_connection() as conn:
        if current_user.role == "admin":
            if request.name:
                await conn.execute(
                    "UPDATE admins SET name = $1 WHERE user_id = $2",
                    request.name, current_user.id
                )
        elif current_user.role == "client":
            updates = []
            values = []
            if request.name:
                updates.append("name = $" + str(len(values) + 1))
                values.append(request.name)
            if request.phone:
                updates.append("phone = $" + str(len(values) + 1))
                values.append(request.phone)
            if updates:
                values.append(current_user.id)
                await conn.execute(
                    f"UPDATE clients SET {', '.join(updates)} WHERE user_id = ${len(values)}",
                    *values
                )
        elif current_user.role == "candidate":
            updates = []
            values = []
            if request.name:
                updates.append("name = $" + str(len(values) + 1))
                values.append(request.name)
            if request.phone:
                updates.append("phone = $" + str(len(values) + 1))
                values.append(request.phone)
            if updates:
                values.append(current_user.id)
                await conn.execute(
                    f"UPDATE candidates SET {', '.join(updates)} WHERE user_id = ${len(values)}",
                    *values
                )

        return {"status": "profile_updated"}


# ===========================================
# Admin Beta Access Management
# ===========================================

@router.get("/admin/candidates/beta", response_model=CandidateBetaListResponse, dependencies=[Depends(require_admin)])
async def list_candidates_beta():
    """List all candidates with beta access info and interview prep stats."""
    async with get_connection() as conn:
        # Get all candidates with their user info and interview prep stats
        rows = await conn.fetch("""
            SELECT
                u.id as user_id,
                u.email,
                c.name,
                COALESCE(u.beta_features, '{}'::jsonb) as beta_features,
                COALESCE(u.interview_prep_tokens, 0) as interview_prep_tokens,
                COALESCE(u.allowed_interview_roles, '[]'::jsonb) as allowed_interview_roles,
                COUNT(i.id) FILTER (WHERE i.interview_type = 'tutor_interview') as total_sessions,
                AVG(
                    CASE
                        WHEN i.tutor_analysis IS NOT NULL
                        AND i.tutor_analysis->'interview'->>'response_quality_score' IS NOT NULL
                        THEN (i.tutor_analysis->'interview'->>'response_quality_score')::float
                        ELSE NULL
                    END
                ) as avg_score,
                MAX(i.created_at) FILTER (WHERE i.interview_type = 'tutor_interview') as last_session_at
            FROM users u
            JOIN candidates c ON c.user_id = u.id
            LEFT JOIN interviews i ON i.interviewer_name = u.email AND i.interview_type = 'tutor_interview'
            WHERE u.role = 'candidate'
            GROUP BY u.id, u.email, c.name, u.beta_features, u.interview_prep_tokens, u.allowed_interview_roles
            ORDER BY c.name
        """)

        candidates = []
        for row in rows:
            beta_features = row["beta_features"] if row["beta_features"] else {}
            if isinstance(beta_features, str):
                beta_features = json.loads(beta_features)

            allowed_roles = row["allowed_interview_roles"] if row["allowed_interview_roles"] else []
            if isinstance(allowed_roles, str):
                allowed_roles = json.loads(allowed_roles)

            candidates.append(CandidateBetaInfo(
                user_id=row["user_id"],
                email=row["email"],
                name=row["name"],
                beta_features=beta_features,
                interview_prep_tokens=row["interview_prep_tokens"],
                allowed_interview_roles=allowed_roles,
                total_sessions=row["total_sessions"] or 0,
                avg_score=round(row["avg_score"], 1) if row["avg_score"] else None,
                last_session_at=row["last_session_at"]
            ))

        return CandidateBetaListResponse(candidates=candidates, total=len(candidates))


@router.patch("/admin/candidates/{user_id}/beta", dependencies=[Depends(require_admin)])
async def toggle_candidate_beta(user_id: UUID, request: BetaToggleRequest):
    """Toggle a beta feature for a candidate."""
    async with get_connection() as conn:
        # Verify user exists and is a candidate
        user = await conn.fetchrow(
            "SELECT id, role, beta_features FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] != "candidate":
            raise HTTPException(status_code=400, detail="User is not a candidate")

        # Update beta features
        current_features = user["beta_features"] if user["beta_features"] else {}
        if isinstance(current_features, str):
            current_features = json.loads(current_features)

        if request.enabled:
            current_features[request.feature] = True
        else:
            current_features.pop(request.feature, None)

        await conn.execute(
            "UPDATE users SET beta_features = $1::jsonb WHERE id = $2",
            json.dumps(current_features), user_id
        )

        return {"status": "updated", "beta_features": current_features}


@router.post("/admin/candidates/{user_id}/tokens", dependencies=[Depends(require_admin)])
async def award_tokens(user_id: UUID, request: TokenAwardRequest):
    """Award interview prep tokens to a candidate."""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    async with get_connection() as conn:
        # Verify user exists and is a candidate
        user = await conn.fetchrow(
            "SELECT id, role, interview_prep_tokens FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] != "candidate":
            raise HTTPException(status_code=400, detail="User is not a candidate")

        new_total = (user["interview_prep_tokens"] or 0) + request.amount
        await conn.execute(
            "UPDATE users SET interview_prep_tokens = $1 WHERE id = $2",
            new_total, user_id
        )

        return {"status": "awarded", "new_total": new_total}


@router.put("/admin/candidates/{user_id}/roles", dependencies=[Depends(require_admin)])
async def update_allowed_roles(user_id: UUID, request: AllowedRolesRequest):
    """Update allowed interview roles for a candidate."""
    async with get_connection() as conn:
        # Verify user exists and is a candidate
        user = await conn.fetchrow(
            "SELECT id, role FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] != "candidate":
            raise HTTPException(status_code=400, detail="User is not a candidate")

        await conn.execute(
            "UPDATE users SET allowed_interview_roles = $1::jsonb WHERE id = $2",
            json.dumps(request.roles), user_id
        )

        return {"status": "updated", "allowed_interview_roles": request.roles}


@router.get("/admin/candidates/{user_id}/sessions", response_model=list[CandidateSessionSummary], dependencies=[Depends(require_admin)])
async def get_candidate_sessions(user_id: UUID):
    """Get interview prep sessions for a specific candidate."""
    async with get_connection() as conn:
        # Get user email
        user = await conn.fetchrow("SELECT email FROM users WHERE id = $1", user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get interview prep sessions (using interviewer_name = email pattern from tutor)
        rows = await conn.fetch("""
            SELECT
                id as session_id,
                interviewer_role as interview_role,
                EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - created_at)) / 60 as duration_minutes,
                status,
                created_at,
                tutor_analysis
            FROM interviews
            WHERE interviewer_name = $1
            AND interview_type = 'tutor_interview'
            ORDER BY created_at DESC
            LIMIT 50
        """, user["email"])

        sessions = []
        for row in rows:
            analysis = row["tutor_analysis"]
            response_score = None
            communication_score = None

            if analysis:
                if isinstance(analysis, str):
                    analysis = json.loads(analysis)
                interview_data = analysis.get("interview", {})
                response_score = interview_data.get("response_quality_score")
                communication_score = interview_data.get("communication_score")

            sessions.append(CandidateSessionSummary(
                session_id=row["session_id"],
                interview_role=row["interview_role"],
                duration_minutes=int(row["duration_minutes"] or 0),
                status=row["status"],
                created_at=row["created_at"],
                response_quality_score=response_score,
                communication_score=communication_score
            ))

        return sessions
