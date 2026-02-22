"""
Employee Self-Service Portal Routes

Provides API endpoints for employees to:
- View their profile and dashboard
- View and sign documents
- Manage PTO requests
- Search company policies
- Update personal information
"""
import json
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, status, Request, BackgroundTasks
from pydantic import BaseModel

from ...database import get_connection
from ...config import get_settings
from ...core.models.auth import CurrentUser
from ...core.services.policy_service import SignatureService
from ..models.employee import (
    EmployeeResponse, EmployeeUpdate, ProfileUpdateRequest,
    PTOBalanceResponse, PTORequestCreate, PTORequestResponse, PTORequestListResponse,
    PTOSummary,
    EmployeeDocumentResponse, EmployeeDocumentListResponse, SignDocumentRequest,
    PortalDashboard, PortalTasks, PendingTask,
    LeaveRequestCreate, LeaveRequestResponse, LeaveRequestListResponse,
)
from ..models.xp import (
    VibeCheckSubmit, VibeCheckResponse, VibeCheckListResponse,
    ENPSSubmit, ENPSSurveyResponse,
    SelfAssessmentSubmit, ManagerReviewSubmit,
    PerformanceReviewResponse
)
from ..models.internal_mobility import (
    EmployeeCareerProfileResponse,
    EmployeeCareerProfileUpdateRequest,
    MobilityFeedItem,
    MobilityFeedResponse,
    MobilityOpportunityActionResponse,
    MobilityApplicationCreateRequest,
    MobilityApplicationResponse,
)
from ...core.dependencies import get_current_user
from ..dependencies import require_employee, require_employee_record, require_feature

router = APIRouter()

# Per-feature dependencies for portal routes
_pto_dep = [Depends(require_feature("time_off"))]
_policies_dep = [Depends(require_feature("policies"))]
_vibe_dep = [Depends(require_feature("vibe_checks"))]
_enps_dep = [Depends(require_feature("enps"))]
_reviews_dep = [Depends(require_feature("performance_reviews"))]
_mobility_dep = [Depends(require_feature("internal_mobility"))]


def _parse_json_array(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []

    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            trimmed = item.strip()
            if trimmed:
                result.append(trimmed)
    return result


def _normalize_string_list(values: Optional[list[str]]) -> list[str]:
    if not values:
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed:
            continue
        key = trimmed.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(trimmed)
    return deduped


def _row_to_career_profile(row: Any) -> EmployeeCareerProfileResponse:
    return EmployeeCareerProfileResponse(
        id=row["id"],
        employee_id=row["employee_id"],
        org_id=row["org_id"],
        target_roles=_parse_json_array(row["target_roles"]),
        target_departments=_parse_json_array(row["target_departments"]),
        skills=_parse_json_array(row["skills"]),
        interests=_parse_json_array(row["interests"]),
        mobility_opt_in=bool(row["mobility_opt_in"]),
        visibility=row["visibility"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _get_or_create_career_profile(conn: Any, employee: dict) -> EmployeeCareerProfileResponse:
    row = await conn.fetchrow(
        """
        SELECT id, employee_id, org_id, target_roles, target_departments, skills, interests,
               mobility_opt_in, visibility, created_at, updated_at
        FROM employee_career_profiles
        WHERE employee_id = $1 AND org_id = $2
        """,
        employee["id"],
        employee["org_id"],
    )

    if not row:
        # Atomic upsert prevents race conditions when profile + feed endpoints initialize concurrently.
        row = await conn.fetchrow(
            """
            INSERT INTO employee_career_profiles (
                employee_id, org_id, target_roles, target_departments, skills, interests, mobility_opt_in, visibility
            )
            VALUES ($1, $2, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, true, 'private')
            ON CONFLICT (employee_id)
            DO UPDATE SET
                org_id = EXCLUDED.org_id
            RETURNING id, employee_id, org_id, target_roles, target_departments, skills, interests,
                      mobility_opt_in, visibility, created_at, updated_at
            """,
            employee["id"],
            employee["org_id"],
        )
    return _row_to_career_profile(row)


def _ratio(count: int, total: int, empty_default: float = 1.0) -> float:
    if total <= 0:
        return empty_default
    return max(0.0, min(1.0, count / total))


def _infer_target_years_from_title(title: str) -> float:
    normalized = title.lower()
    if any(keyword in normalized for keyword in ("director", "head", "principal")):
        return 8.0
    if any(keyword in normalized for keyword in ("manager", "lead", "senior", " sr ")):
        return 5.0
    if any(keyword in normalized for keyword in ("junior", " jr ", "associate", "intern")):
        return 1.0
    return 3.0


def _compute_level_fit(start_date_value: Optional[date], title: str) -> float:
    if not start_date_value:
        return 0.6
    tenure_years = max((date.today() - start_date_value).days / 365.25, 0.0)
    target_years = _infer_target_years_from_title(title)
    delta = abs(tenure_years - target_years)
    return max(0.0, 1.0 - (delta / max(target_years, 1.0)))


def _compute_mobility_match(
    *,
    profile: EmployeeCareerProfileResponse,
    employee_start_date: Optional[date],
    title: str,
    department: Optional[str],
    description: Optional[str],
    required_skills_raw: Any,
    preferred_skills_raw: Any,
) -> tuple[float, dict[str, Any]]:
    profile_skills = {skill.lower() for skill in profile.skills}
    profile_roles = {role.lower() for role in profile.target_roles}
    profile_departments = {dept.lower() for dept in profile.target_departments}
    profile_interests = {interest.lower() for interest in profile.interests}

    required_skills = _parse_json_array(required_skills_raw)
    preferred_skills = _parse_json_array(preferred_skills_raw)
    required_lower = [skill.lower() for skill in required_skills]
    preferred_lower = [skill.lower() for skill in preferred_skills]

    matched_required = [skill for skill in required_skills if skill.lower() in profile_skills]
    matched_preferred = [skill for skill in preferred_skills if skill.lower() in profile_skills]
    missing_required = [skill for skill in required_skills if skill.lower() not in profile_skills]

    required_fit = _ratio(len(matched_required), len(required_skills), empty_default=1.0)
    preferred_fit = _ratio(len(matched_preferred), len(preferred_skills), empty_default=1.0)

    alignment_signals: list[str] = []
    alignment_score = 0.0
    alignment_slots = 0

    normalized_title = title.lower()
    normalized_department = (department or "").strip().lower()
    normalized_description = (description or "").strip().lower()

    if profile_roles:
        alignment_slots += 1
        if any(role in normalized_title for role in profile_roles):
            alignment_score += 1
            alignment_signals.append("target_role_match")

    if profile_departments:
        alignment_slots += 1
        if normalized_department and normalized_department in profile_departments:
            alignment_score += 1
            alignment_signals.append("target_department_match")

    if profile_interests:
        alignment_slots += 1
        if any(interest in normalized_description for interest in profile_interests):
            alignment_score += 1
            alignment_signals.append("interest_match")

    interest_alignment = (
        alignment_score / alignment_slots if alignment_slots > 0 else 0.5
    )
    level_fit = _compute_level_fit(employee_start_date, title)

    score = round(
        (
            required_fit * 0.50
            + preferred_fit * 0.20
            + interest_alignment * 0.20
            + level_fit * 0.10
        )
        * 100.0,
        1,
    )

    reasons = {
        "matched_skills": matched_required,
        "missing_skills": missing_required,
        "preferred_matched_skills": matched_preferred,
        "alignment_signals": alignment_signals,
        "component_scores": {
            "required_skill_fit": round(required_fit * 100.0, 1),
            "preferred_skill_fit": round(preferred_fit * 100.0, 1),
            "interest_alignment": round(interest_alignment * 100.0, 1),
            "level_fit": round(level_fit * 100.0, 1),
        },
    }
    return score, reasons


async def _get_employee_opportunity(
    conn: Any,
    employee: dict,
    opportunity_id: UUID,
    *,
    require_active: bool = True,
) -> Any:
    row = await conn.fetchrow(
        """
        SELECT id, org_id, type, title, department, description, required_skills, preferred_skills, status
        FROM internal_opportunities
        WHERE id = $1 AND org_id = $2
        """,
        opportunity_id,
        employee["org_id"],
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    if require_active and row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active opportunities can be actioned",
        )
    return row


async def _ensure_match_for_opportunity(
    conn: Any,
    employee: dict,
    profile: EmployeeCareerProfileResponse,
    opportunity_row: Any,
) -> tuple[float, dict[str, Any]]:
    existing = await conn.fetchrow(
        """
        SELECT match_score, reasons
        FROM internal_opportunity_matches
        WHERE employee_id = $1 AND opportunity_id = $2
        """,
        employee["id"],
        opportunity_row["id"],
    )

    existing_reasons = None
    existing_score = None
    if existing:
        existing_score = existing["match_score"]
        existing_reasons = existing["reasons"]
        if isinstance(existing_reasons, str):
            try:
                existing_reasons = json.loads(existing_reasons)
            except json.JSONDecodeError:
                existing_reasons = None

    if existing_score is not None and isinstance(existing_reasons, dict):
        return float(existing_score), existing_reasons

    computed_score, computed_reasons = _compute_mobility_match(
        profile=profile,
        employee_start_date=employee.get("start_date"),
        title=opportunity_row["title"],
        department=opportunity_row["department"],
        description=opportunity_row["description"],
        required_skills_raw=opportunity_row["required_skills"],
        preferred_skills_raw=opportunity_row["preferred_skills"],
    )

    await conn.execute(
        """
        INSERT INTO internal_opportunity_matches (
            employee_id, opportunity_id, match_score, reasons, status
        )
        VALUES ($1, $2, $3, $4::jsonb, 'suggested')
        ON CONFLICT (employee_id, opportunity_id)
        DO UPDATE SET
            match_score = $3,
            reasons = $4::jsonb,
            updated_at = NOW()
        """,
        employee["id"],
        opportunity_row["id"],
        computed_score,
        json.dumps(computed_reasons),
    )

    return computed_score, computed_reasons


# ================================
# Portal Dashboard
# ================================

@router.get("/me", response_model=PortalDashboard)
async def get_portal_dashboard(
    employee: dict = Depends(require_employee_record)
):
    """Get employee portal dashboard with summary stats."""
    async with get_connection() as conn:
        # Get PTO balance for current year
        current_year = datetime.now().year
        pto_balance = await conn.fetchrow(
            """SELECT id, employee_id, year, balance_hours, accrued_hours,
                      used_hours, carryover_hours, updated_at
               FROM pto_balances
               WHERE employee_id = $1 AND year = $2""",
            employee["id"], current_year
        )

        # Count pending documents
        pending_docs = await conn.fetchval(
            """SELECT COUNT(*) FROM employee_documents
               WHERE employee_id = $1 AND status = 'pending_signature'""",
            employee["id"]
        )

        # Count pending PTO requests
        pending_pto = await conn.fetchval(
            """SELECT COUNT(*) FROM pto_requests
               WHERE employee_id = $1 AND status = 'pending'""",
            employee["id"]
        )

        # Total pending tasks
        pending_tasks = pending_docs + pending_pto

        return PortalDashboard(
            employee=EmployeeResponse(
                id=employee["id"],
                org_id=employee["org_id"],
                user_id=None,  # Don't expose user_id
                email=employee["email"],
                first_name=employee["first_name"],
                last_name=employee["last_name"],
                work_state=employee["work_state"],
                employment_type=employee["employment_type"],
                start_date=employee["start_date"],
                termination_date=employee["termination_date"],
                manager_id=employee["manager_id"],
                phone=employee["phone"],
                address=employee["address"],
                emergency_contact=employee["emergency_contact"],
                created_at=employee["created_at"],
                updated_at=employee["updated_at"]
            ),
            pto_balance=PTOBalanceResponse(
                id=pto_balance["id"],
                employee_id=pto_balance["employee_id"],
                year=pto_balance["year"],
                balance_hours=Decimal(str(pto_balance["balance_hours"])),
                accrued_hours=Decimal(str(pto_balance["accrued_hours"])),
                used_hours=Decimal(str(pto_balance["used_hours"])),
                carryover_hours=Decimal(str(pto_balance["carryover_hours"])),
                updated_at=pto_balance["updated_at"]
            ) if pto_balance else None,
            pending_tasks_count=pending_tasks,
            pending_documents_count=pending_docs,
            pending_pto_requests_count=pending_pto
        )


@router.patch("/me", response_model=EmployeeResponse)
async def update_my_profile(
    request: ProfileUpdateRequest,
    employee: dict = Depends(require_employee_record)
):
    """Update employee's own profile (phone, address, emergency contact)."""
    async with get_connection() as conn:
        updates = []
        values = []
        param_idx = 1

        if request.phone is not None:
            updates.append(f"phone = ${param_idx}")
            values.append(request.phone)
            param_idx += 1

        if request.address is not None:
            updates.append(f"address = ${param_idx}")
            values.append(request.address)
            param_idx += 1

        if request.emergency_contact is not None:
            updates.append(f"emergency_contact = ${param_idx}::jsonb")
            import json
            values.append(json.dumps(request.emergency_contact))
            param_idx += 1

        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )

        updates.append(f"updated_at = NOW()")
        values.append(employee["id"])

        query = f"""
            UPDATE employees
            SET {', '.join(updates)}
            WHERE id = ${param_idx}
            RETURNING id, org_id, email, first_name, last_name, work_state,
                      employment_type, start_date, termination_date, manager_id,
                      phone, address, emergency_contact, created_at, updated_at
        """

        updated = await conn.fetchrow(query, *values)

        return EmployeeResponse(
            id=updated["id"],
            org_id=updated["org_id"],
            user_id=None,
            email=updated["email"],
            first_name=updated["first_name"],
            last_name=updated["last_name"],
            work_state=updated["work_state"],
            employment_type=updated["employment_type"],
            start_date=updated["start_date"],
            termination_date=updated["termination_date"],
            manager_id=updated["manager_id"],
            phone=updated["phone"],
            address=updated["address"],
            emergency_contact=updated["emergency_contact"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"]
        )


@router.get("/me/mobility/profile", response_model=EmployeeCareerProfileResponse, dependencies=_mobility_dep)
async def get_my_mobility_profile(
    employee: dict = Depends(require_employee_record),
):
    """Get (or initialize) employee career profile used for internal mobility matching."""
    async with get_connection() as conn:
        return await _get_or_create_career_profile(conn, employee)


@router.put("/me/mobility/profile", response_model=EmployeeCareerProfileResponse, dependencies=_mobility_dep)
async def update_my_mobility_profile(
    request: EmployeeCareerProfileUpdateRequest,
    employee: dict = Depends(require_employee_record),
):
    """Update employee career interests/profile for internal mobility."""
    payload = request.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    async with get_connection() as conn:
        # Ensure row exists before applying partial updates.
        await _get_or_create_career_profile(conn, employee)

        updates: list[str] = []
        values: list[Any] = []
        param_idx = 1

        if "target_roles" in payload:
            updates.append(f"target_roles = ${param_idx}::jsonb")
            values.append(json.dumps(_normalize_string_list(payload["target_roles"])))
            param_idx += 1

        if "target_departments" in payload:
            updates.append(f"target_departments = ${param_idx}::jsonb")
            values.append(json.dumps(_normalize_string_list(payload["target_departments"])))
            param_idx += 1

        if "skills" in payload:
            updates.append(f"skills = ${param_idx}::jsonb")
            values.append(json.dumps(_normalize_string_list(payload["skills"])))
            param_idx += 1

        if "interests" in payload:
            updates.append(f"interests = ${param_idx}::jsonb")
            values.append(json.dumps(_normalize_string_list(payload["interests"])))
            param_idx += 1

        if "mobility_opt_in" in payload:
            updates.append(f"mobility_opt_in = ${param_idx}")
            values.append(bool(payload["mobility_opt_in"]))
            param_idx += 1

        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No supported fields to update",
            )

        updates.append("updated_at = NOW()")
        values.extend([employee["id"], employee["org_id"]])

        updated = await conn.fetchrow(
            f"""
            UPDATE employee_career_profiles
            SET {', '.join(updates)}
            WHERE employee_id = ${param_idx} AND org_id = ${param_idx + 1}
            RETURNING id, employee_id, org_id, target_roles, target_departments, skills, interests,
                      mobility_opt_in, visibility, created_at, updated_at
            """,
            *values,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update mobility profile",
            )

        return _row_to_career_profile(updated)


@router.get("/me/mobility/feed", response_model=MobilityFeedResponse, dependencies=_mobility_dep)
async def get_my_mobility_feed(
    status_filter: str = "active",
    employee: dict = Depends(require_employee_record),
):
    """Return internal opportunities for the employee, with deterministic match scores."""
    if status_filter not in {"active", "draft", "closed"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status_filter must be one of: active, draft, closed",
        )

    async with get_connection() as conn:
        profile = await _get_or_create_career_profile(conn, employee)

        rows = await conn.fetch(
            """
            SELECT
                io.id as opportunity_id,
                io.type,
                io.title,
                io.department,
                io.description,
                io.required_skills,
                io.preferred_skills,
                iom.match_score,
                iom.status as match_status,
                iom.reasons
            FROM internal_opportunities io
            LEFT JOIN internal_opportunity_matches iom
                ON iom.opportunity_id = io.id
               AND iom.employee_id = $1
            WHERE io.org_id = $2
              AND io.status = $3
            ORDER BY COALESCE(iom.match_score, -1) DESC, io.created_at DESC
            """,
            employee["id"],
            employee["org_id"],
            status_filter,
        )

        items: list[MobilityFeedItem] = []
        for row in rows:
            reasons = row["reasons"]
            if isinstance(reasons, str):
                try:
                    reasons = json.loads(reasons)
                except json.JSONDecodeError:
                    reasons = None

            match_score = row["match_score"]
            match_status = row["match_status"] or "suggested"

            # Compute and persist v1 deterministic score if missing.
            if match_score is None or reasons is None:
                computed_score, computed_reasons = _compute_mobility_match(
                    profile=profile,
                    employee_start_date=employee.get("start_date"),
                    title=row["title"],
                    department=row["department"],
                    description=row["description"],
                    required_skills_raw=row["required_skills"],
                    preferred_skills_raw=row["preferred_skills"],
                )

                upserted = await conn.fetchrow(
                    """
                    INSERT INTO internal_opportunity_matches (
                        employee_id, opportunity_id, match_score, reasons, status
                    )
                    VALUES ($1, $2, $3, $4::jsonb, 'suggested')
                    ON CONFLICT (employee_id, opportunity_id)
                    DO UPDATE SET
                        match_score = $3,
                        reasons = $4::jsonb,
                        updated_at = NOW()
                    RETURNING status
                    """,
                    employee["id"],
                    row["opportunity_id"],
                    computed_score,
                    json.dumps(computed_reasons),
                )
                match_score = computed_score
                reasons = computed_reasons
                match_status = upserted["status"] if upserted and upserted["status"] else match_status

            items.append(
                MobilityFeedItem(
                    opportunity_id=row["opportunity_id"],
                    type=row["type"],
                    title=row["title"],
                    department=row["department"],
                    description=row["description"],
                    match_score=float(match_score) if match_score is not None else None,
                    status=match_status,
                    reasons=reasons if isinstance(reasons, dict) else None,
                )
            )

        return MobilityFeedResponse(items=items, total=len(items))


@router.post(
    "/me/mobility/opportunities/{opportunity_id}/save",
    response_model=MobilityOpportunityActionResponse,
    dependencies=_mobility_dep,
)
async def save_mobility_opportunity(
    opportunity_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Mark an opportunity as saved for the current employee."""
    async with get_connection() as conn:
        profile = await _get_or_create_career_profile(conn, employee)
        opportunity = await _get_employee_opportunity(conn, employee, opportunity_id, require_active=True)
        score, reasons = await _ensure_match_for_opportunity(conn, employee, profile, opportunity)

        row = await conn.fetchrow(
            """
            INSERT INTO internal_opportunity_matches (
                employee_id, opportunity_id, match_score, reasons, status
            )
            VALUES ($1, $2, $3, $4::jsonb, 'saved')
            ON CONFLICT (employee_id, opportunity_id)
            DO UPDATE SET
                match_score = $3,
                reasons = $4::jsonb,
                status = 'saved',
                updated_at = NOW()
            RETURNING status
            """,
            employee["id"],
            opportunity_id,
            score,
            json.dumps(reasons),
        )

    return MobilityOpportunityActionResponse(opportunity_id=opportunity_id, status=row["status"])


@router.delete(
    "/me/mobility/opportunities/{opportunity_id}/save",
    response_model=MobilityOpportunityActionResponse,
    dependencies=_mobility_dep,
)
async def unsave_mobility_opportunity(
    opportunity_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Remove saved state and return the opportunity to suggested state."""
    async with get_connection() as conn:
        await _get_employee_opportunity(conn, employee, opportunity_id, require_active=False)

        row = await conn.fetchrow(
            """
            INSERT INTO internal_opportunity_matches (employee_id, opportunity_id, status)
            VALUES ($1, $2, 'suggested')
            ON CONFLICT (employee_id, opportunity_id)
            DO UPDATE SET
                status = 'suggested',
                updated_at = NOW()
            RETURNING status
            """,
            employee["id"],
            opportunity_id,
        )

    return MobilityOpportunityActionResponse(opportunity_id=opportunity_id, status=row["status"])


@router.post(
    "/me/mobility/opportunities/{opportunity_id}/dismiss",
    response_model=MobilityOpportunityActionResponse,
    dependencies=_mobility_dep,
)
async def dismiss_mobility_opportunity(
    opportunity_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Mark an opportunity as dismissed for the current employee."""
    async with get_connection() as conn:
        profile = await _get_or_create_career_profile(conn, employee)
        opportunity = await _get_employee_opportunity(conn, employee, opportunity_id, require_active=False)
        score, reasons = await _ensure_match_for_opportunity(conn, employee, profile, opportunity)

        row = await conn.fetchrow(
            """
            INSERT INTO internal_opportunity_matches (
                employee_id, opportunity_id, match_score, reasons, status
            )
            VALUES ($1, $2, $3, $4::jsonb, 'dismissed')
            ON CONFLICT (employee_id, opportunity_id)
            DO UPDATE SET
                match_score = $3,
                reasons = $4::jsonb,
                status = 'dismissed',
                updated_at = NOW()
            RETURNING status
            """,
            employee["id"],
            opportunity_id,
            score,
            json.dumps(reasons),
        )

    return MobilityOpportunityActionResponse(opportunity_id=opportunity_id, status=row["status"])


@router.post(
    "/me/mobility/opportunities/{opportunity_id}/apply",
    response_model=MobilityApplicationResponse,
    dependencies=_mobility_dep,
)
async def apply_to_mobility_opportunity(
    opportunity_id: UUID,
    request: MobilityApplicationCreateRequest,
    employee: dict = Depends(require_employee_record),
):
    """Create or refresh an internal mobility application for an opportunity."""
    async with get_connection() as conn:
        profile = await _get_or_create_career_profile(conn, employee)
        opportunity = await _get_employee_opportunity(conn, employee, opportunity_id, require_active=True)
        score, reasons = await _ensure_match_for_opportunity(conn, employee, profile, opportunity)

        app_row = await conn.fetchrow(
            """
            INSERT INTO internal_opportunity_applications (
                employee_id, opportunity_id, status, employee_notes, submitted_at
            )
            VALUES ($1, $2, 'new', $3, NOW())
            ON CONFLICT (employee_id, opportunity_id)
            DO UPDATE SET
                status = 'new',
                employee_notes = $3,
                submitted_at = NOW(),
                updated_at = NOW()
            RETURNING id, status, submitted_at, manager_notified_at
            """,
            employee["id"],
            opportunity_id,
            request.employee_notes,
        )

        await conn.execute(
            """
            INSERT INTO internal_opportunity_matches (
                employee_id, opportunity_id, match_score, reasons, status
            )
            VALUES ($1, $2, $3, $4::jsonb, 'applied')
            ON CONFLICT (employee_id, opportunity_id)
            DO UPDATE SET
                match_score = $3,
                reasons = $4::jsonb,
                status = 'applied',
                updated_at = NOW()
            """,
            employee["id"],
            opportunity_id,
            score,
            json.dumps(reasons),
        )

    return MobilityApplicationResponse(
        application_id=app_row["id"],
        status=app_row["status"],
        submitted_at=app_row["submitted_at"],
        manager_notified=app_row["manager_notified_at"] is not None,
    )


@router.get("/me/tasks", response_model=PortalTasks)
async def get_pending_tasks(
    employee: dict = Depends(require_employee_record)
):
    """Get all pending tasks for the employee."""
    import json as _json
    tasks = []

    async with get_connection() as conn:
        # Get pending documents to sign
        docs = await conn.fetch(
            """SELECT id, title, description, expires_at, created_at
               FROM employee_documents
               WHERE employee_id = $1 AND status = 'pending_signature'
               ORDER BY expires_at ASC NULLS LAST, created_at DESC""",
            employee["id"]
        )

        for doc in docs:
            tasks.append(PendingTask(
                id=doc["id"],
                task_type="document_signature",
                title=f"Sign: {doc['title']}",
                description=doc["description"],
                due_date=doc["expires_at"],
                created_at=doc["created_at"]
            ))

        # Include pending onboarding / return-to-work tasks assigned to the employee
        onboarding_rows = await conn.fetch(
            """SELECT id, title, description, category, due_date, created_at
               FROM employee_onboarding_tasks
               WHERE employee_id = $1
                 AND status = 'pending'
                 AND is_employee_task = true
               ORDER BY due_date ASC NULLS LAST, created_at DESC""",
            employee["id"],
        )

        for task in onboarding_rows:
            task_type = "return_to_work_task" if task["category"] == "return_to_work" else "onboarding_task"
            tasks.append(PendingTask(
                id=task["id"],
                task_type=task_type,
                title=task["title"],
                description=task["description"],
                due_date=task["due_date"],
                created_at=task["created_at"],
            ))

        # Only show PTO approval tasks if time_off feature is enabled
        features_row = await conn.fetchval(
            """SELECT COALESCE(comp.enabled_features, '{"offer_letters": true}'::jsonb)
               FROM companies comp WHERE comp.id = $1""",
            employee["org_id"]
        )
        features = _json.loads(features_row) if isinstance(features_row, str) else (features_row or {})

        if features.get("time_off", False):
            # Get pending PTO requests awaiting manager approval (for managers)
            subordinate_requests = await conn.fetch(
                """SELECT pr.id, pr.start_date, pr.end_date, pr.hours,
                          e.first_name, e.last_name, pr.created_at
                   FROM pto_requests pr
                   JOIN employees e ON pr.employee_id = e.id
                   WHERE e.manager_id = $1 AND pr.status = 'pending'
                   ORDER BY pr.start_date ASC""",
                employee["id"]
            )

            for req in subordinate_requests:
                tasks.append(PendingTask(
                    id=req["id"],
                    task_type="pto_approval",
                    title=f"Review PTO: {req['first_name']} {req['last_name']}",
                    description=f"{req['hours']} hours from {req['start_date']} to {req['end_date']}",
                    due_date=req["start_date"],
                    created_at=req["created_at"]
                ))

    return PortalTasks(tasks=tasks, total=len(tasks))


# ================================
# PTO Management
# ================================

@router.get("/me/pto", response_model=PTOSummary, dependencies=_pto_dep)
async def get_pto_summary(
    employee: dict = Depends(require_employee_record)
):
    """Get PTO balance and recent requests."""
    async with get_connection() as conn:
        current_year = datetime.now().year

        # Get or create PTO balance for current year
        pto_balance = await conn.fetchrow(
            """SELECT id, employee_id, year, balance_hours, accrued_hours,
                      used_hours, carryover_hours, updated_at
               FROM pto_balances
               WHERE employee_id = $1 AND year = $2""",
            employee["id"], current_year
        )

        if not pto_balance:
            # Create initial PTO balance
            pto_balance = await conn.fetchrow(
                """INSERT INTO pto_balances (employee_id, year, balance_hours, accrued_hours, used_hours, carryover_hours)
                   VALUES ($1, $2, 0, 0, 0, 0)
                   RETURNING id, employee_id, year, balance_hours, accrued_hours, used_hours, carryover_hours, updated_at""",
                employee["id"], current_year
            )

        # Get pending requests
        pending = await conn.fetch(
            """SELECT id, employee_id, start_date, end_date, hours, reason,
                      request_type, status, approved_by, approved_at, denial_reason,
                      created_at, updated_at
               FROM pto_requests
               WHERE employee_id = $1 AND status = 'pending'
               ORDER BY start_date ASC""",
            employee["id"]
        )

        # Get approved requests for current year
        approved = await conn.fetch(
            """SELECT id, employee_id, start_date, end_date, hours, reason,
                      request_type, status, approved_by, approved_at, denial_reason,
                      created_at, updated_at
               FROM pto_requests
               WHERE employee_id = $1
               AND status = 'approved'
               AND EXTRACT(YEAR FROM start_date) = $2
               ORDER BY start_date DESC""",
            employee["id"], current_year
        )

        return PTOSummary(
            balance=PTOBalanceResponse(
                id=pto_balance["id"],
                employee_id=pto_balance["employee_id"],
                year=pto_balance["year"],
                balance_hours=Decimal(str(pto_balance["balance_hours"])),
                accrued_hours=Decimal(str(pto_balance["accrued_hours"])),
                used_hours=Decimal(str(pto_balance["used_hours"])),
                carryover_hours=Decimal(str(pto_balance["carryover_hours"])),
                updated_at=pto_balance["updated_at"]
            ),
            pending_requests=[
                PTORequestResponse(
                    id=r["id"],
                    employee_id=r["employee_id"],
                    start_date=r["start_date"],
                    end_date=r["end_date"],
                    hours=Decimal(str(r["hours"])),
                    reason=r["reason"],
                    request_type=r["request_type"],
                    status=r["status"],
                    approved_by=r["approved_by"],
                    approved_at=r["approved_at"],
                    denial_reason=r["denial_reason"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                ) for r in pending
            ],
            approved_requests=[
                PTORequestResponse(
                    id=r["id"],
                    employee_id=r["employee_id"],
                    start_date=r["start_date"],
                    end_date=r["end_date"],
                    hours=Decimal(str(r["hours"])),
                    reason=r["reason"],
                    request_type=r["request_type"],
                    status=r["status"],
                    approved_by=r["approved_by"],
                    approved_at=r["approved_at"],
                    denial_reason=r["denial_reason"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                ) for r in approved
            ]
        )


@router.post("/me/pto/request", response_model=PTORequestResponse, dependencies=_pto_dep)
async def submit_pto_request(
    request: PTORequestCreate,
    employee: dict = Depends(require_employee_record)
):
    """Submit a new PTO request."""
    # Validate dates
    if request.start_date > request.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date must be before or equal to end date"
        )

    if request.start_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot request PTO for past dates"
        )

    if request.hours <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hours must be greater than 0"
        )

    async with get_connection() as conn:
        # Check for overlapping requests
        overlap = await conn.fetchval(
            """SELECT COUNT(*) FROM pto_requests
               WHERE employee_id = $1
               AND status IN ('pending', 'approved')
               AND (
                   (start_date <= $2 AND end_date >= $2) OR
                   (start_date <= $3 AND end_date >= $3) OR
                   (start_date >= $2 AND end_date <= $3)
               )""",
            employee["id"], request.start_date, request.end_date
        )

        if overlap > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request overlaps with existing PTO request"
            )

        # Create the request
        pto_request = await conn.fetchrow(
            """INSERT INTO pto_requests
               (employee_id, start_date, end_date, hours, reason, request_type, status)
               VALUES ($1, $2, $3, $4, $5, $6, 'pending')
               RETURNING id, employee_id, start_date, end_date, hours, reason,
                         request_type, status, approved_by, approved_at, denial_reason,
                         created_at, updated_at""",
            employee["id"], request.start_date, request.end_date,
            request.hours, request.reason, request.request_type
        )

        # TODO: Send notification to manager

        return PTORequestResponse(
            id=pto_request["id"],
            employee_id=pto_request["employee_id"],
            start_date=pto_request["start_date"],
            end_date=pto_request["end_date"],
            hours=Decimal(str(pto_request["hours"])),
            reason=pto_request["reason"],
            request_type=pto_request["request_type"],
            status=pto_request["status"],
            approved_by=pto_request["approved_by"],
            approved_at=pto_request["approved_at"],
            denial_reason=pto_request["denial_reason"],
            created_at=pto_request["created_at"],
            updated_at=pto_request["updated_at"]
        )


@router.delete("/me/pto/request/{request_id}", dependencies=_pto_dep)
async def cancel_pto_request(
    request_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Cancel a pending PTO request."""
    async with get_connection() as conn:
        # Verify the request belongs to this employee and is pending
        request = await conn.fetchrow(
            """SELECT id, status FROM pto_requests
               WHERE id = $1 AND employee_id = $2""",
            request_id, employee["id"]
        )

        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PTO request not found"
            )

        if request["status"] != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only cancel pending requests"
            )

        await conn.execute(
            """UPDATE pto_requests SET status = 'cancelled', updated_at = NOW()
               WHERE id = $1""",
            request_id
        )

        return {"status": "cancelled", "request_id": str(request_id)}


# ================================
# Leave Requests (Extended Leave)
# ================================

LEAVE_TYPES = {"fmla", "state_pfml", "parental", "bereavement", "jury_duty", "medical", "military", "unpaid_loa"}

_compliance_plus_dep = [Depends(require_feature("compliance_plus"))]


@router.get("/me/leave", response_model=LeaveRequestListResponse, dependencies=_pto_dep)
async def get_my_leave_requests(
    status_filter: Optional[str] = None,
    employee: dict = Depends(require_employee_record),
):
    """List the current employee's extended leave requests."""
    async with get_connection() as conn:
        if status_filter:
            rows = await conn.fetch(
                """SELECT * FROM leave_requests
                   WHERE employee_id = $1 AND status = $2
                   ORDER BY created_at DESC""",
                employee["id"], status_filter,
            )
        else:
            rows = await conn.fetch(
                """SELECT * FROM leave_requests
                   WHERE employee_id = $1
                   ORDER BY created_at DESC""",
                employee["id"],
            )
        return LeaveRequestListResponse(
            requests=[LeaveRequestResponse(**dict(r)) for r in rows],
            total=len(rows),
        )


@router.get("/me/leave/eligibility", dependencies=_compliance_plus_dep)
async def get_my_leave_eligibility(
    employee: dict = Depends(require_employee_record),
):
    """Check what leave programs the employee may qualify for.

    Requires the ``compliance_plus`` feature flag.
    Returns FMLA eligibility and applicable state programs.
    """
    from ..services.leave_eligibility_service import LeaveEligibilityService

    service = LeaveEligibilityService()
    return await service.get_eligibility_summary(employee["id"])


@router.get("/me/leave/{leave_id}", response_model=LeaveRequestResponse, dependencies=_pto_dep)
async def get_my_leave_request(
    leave_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Get a specific leave request belonging to the current employee."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM leave_requests WHERE id = $1 AND employee_id = $2",
            leave_id, employee["id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found")
        return LeaveRequestResponse(**dict(row))


@router.post("/me/leave/request", response_model=LeaveRequestResponse, dependencies=_pto_dep)
async def submit_leave_request(
    request: LeaveRequestCreate,
    background_tasks: BackgroundTasks,
    employee: dict = Depends(require_employee_record),
):
    """Submit an extended leave request."""
    if request.leave_type not in LEAVE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid leave type: {request.leave_type}")

    if request.start_date < date.today():
        raise HTTPException(status_code=400, detail="Start date cannot be in the past")

    if request.end_date and request.end_date < request.start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO leave_requests
               (employee_id, org_id, leave_type, start_date, end_date,
                expected_return_date, reason, intermittent, intermittent_schedule, status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'requested')
               RETURNING *""",
            employee["id"], employee["org_id"],
            request.leave_type, request.start_date, request.end_date,
            request.expected_return_date, request.reason,
            request.intermittent, request.intermittent_schedule,
        )
        from ..services.leave_agent import get_leave_agent

        background_tasks.add_task(get_leave_agent().on_leave_request_created, row["id"])
        return LeaveRequestResponse(**dict(row))


@router.delete("/me/leave/{leave_id}", dependencies=_pto_dep)
async def cancel_leave_request(
    leave_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    """Cancel a pending leave request."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, status FROM leave_requests WHERE id = $1 AND employee_id = $2",
            leave_id, employee["id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found")
        if row["status"] != "requested":
            raise HTTPException(status_code=400, detail="Can only cancel requests in 'requested' status")

        await conn.execute(
            "UPDATE leave_requests SET status = 'cancelled', updated_at = NOW() WHERE id = $1",
            leave_id,
        )
        return {"status": "cancelled", "leave_id": str(leave_id)}


# ================================
# Documents
# ================================

@router.get("/me/documents", response_model=EmployeeDocumentListResponse)
async def get_my_documents(
    status_filter: Optional[str] = None,
    employee: dict = Depends(require_employee_record)
):
    """Get documents assigned to the employee."""
    async with get_connection() as conn:
        if status_filter:
            docs = await conn.fetch(
                """SELECT id, org_id, employee_id, doc_type, title, description,
                          storage_path, status, expires_at, signed_at, assigned_by,
                          created_at, updated_at
                   FROM employee_documents
                   WHERE employee_id = $1 AND status = $2
                   ORDER BY created_at DESC""",
                employee["id"], status_filter
            )
        else:
            docs = await conn.fetch(
                """SELECT id, org_id, employee_id, doc_type, title, description,
                          storage_path, status, expires_at, signed_at, assigned_by,
                          created_at, updated_at
                   FROM employee_documents
                   WHERE employee_id = $1
                   ORDER BY
                       CASE WHEN status = 'pending_signature' THEN 0 ELSE 1 END,
                       created_at DESC""",
                employee["id"]
            )

        return EmployeeDocumentListResponse(
            documents=[
                EmployeeDocumentResponse(
                    id=d["id"],
                    org_id=d["org_id"],
                    employee_id=d["employee_id"],
                    doc_type=d["doc_type"],
                    title=d["title"],
                    description=d["description"],
                    storage_path=d["storage_path"],
                    status=d["status"],
                    expires_at=d["expires_at"],
                    signed_at=d["signed_at"],
                    assigned_by=d["assigned_by"],
                    created_at=d["created_at"],
                    updated_at=d["updated_at"]
                ) for d in docs
            ],
            total=len(docs)
        )


@router.get("/me/documents/{document_id}", response_model=EmployeeDocumentResponse)
async def get_document(
    document_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Get a specific document."""
    async with get_connection() as conn:
        doc = await conn.fetchrow(
            """SELECT id, org_id, employee_id, doc_type, title, description,
                      storage_path, status, expires_at, signed_at, assigned_by,
                      created_at, updated_at
               FROM employee_documents
               WHERE id = $1 AND employee_id = $2""",
            document_id, employee["id"]
        )

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        return EmployeeDocumentResponse(
            id=doc["id"],
            org_id=doc["org_id"],
            employee_id=doc["employee_id"],
            doc_type=doc["doc_type"],
            title=doc["title"],
            description=doc["description"],
            storage_path=doc["storage_path"],
            status=doc["status"],
            expires_at=doc["expires_at"],
            signed_at=doc["signed_at"],
            assigned_by=doc["assigned_by"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"]
        )


@router.post("/me/documents/{document_id}/sign", response_model=EmployeeDocumentResponse)
async def sign_document(
    document_id: UUID,
    request: SignDocumentRequest,
    http_request: Request,
    employee: dict = Depends(require_employee_record)
):
    """Sign a document."""
    async with get_connection() as conn:
        # Verify the document belongs to this employee and is pending signature
        doc = await conn.fetchrow(
            """SELECT id, status FROM employee_documents
               WHERE id = $1 AND employee_id = $2""",
            document_id, employee["id"]
        )

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        if doc["status"] != "pending_signature":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document is not pending signature"
            )

        # Get client IP
        client_ip = http_request.client.host if http_request.client else None

        # Update the document as signed
        updated = await conn.fetchrow(
            """UPDATE employee_documents
               SET status = 'signed',
                   signed_at = NOW(),
                   signature_data = $1,
                   signature_ip = $2,
                   updated_at = NOW()
               WHERE id = $3
               RETURNING id, org_id, employee_id, doc_type, title, description,
                         storage_path, status, expires_at, signed_at, assigned_by,
                         created_at, updated_at""",
            request.signature_data, client_ip, document_id
        )

        # Keep admin policy-signature tracking in sync for employee policy docs.
        try:
            await SignatureService.sync_employee_document_signature(
                company_id=str(updated["org_id"]),
                employee_id=str(employee["id"]),
                employee_name=f"{employee['first_name']} {employee['last_name']}".strip(),
                employee_email=employee["email"],
                document_title=updated["title"],
                document_type=updated["doc_type"],
                signature_data=request.signature_data,
                ip_address=client_ip,
            )
        except Exception as exc:
            print(f"[Policy] Failed to sync employee policy signature for admin tracking: {exc}")

        return EmployeeDocumentResponse(
            id=updated["id"],
            org_id=updated["org_id"],
            employee_id=updated["employee_id"],
            doc_type=updated["doc_type"],
            title=updated["title"],
            description=updated["description"],
            storage_path=updated["storage_path"],
            status=updated["status"],
            expires_at=updated["expires_at"],
            signed_at=updated["signed_at"],
            assigned_by=updated["assigned_by"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"]
        )


# ================================
# Policy Search
# ================================

@router.get("/policies", dependencies=_policies_dep)
async def search_policies(
    q: Optional[str] = None,
    employee: dict = Depends(require_employee_record)
):
    """Search company policies."""
    async with get_connection() as conn:
        if q:
            # Search by title or content
            policies = await conn.fetch(
                """SELECT id, title, description, content, version, status, created_at
                   FROM policies
                   WHERE company_id = $1
                   AND status = 'active'
                   AND (
                       title ILIKE $2 OR
                       description ILIKE $2 OR
                       content ILIKE $2
                   )
                   ORDER BY title ASC""",
                employee["org_id"], f"%{q}%"
            )
        else:
            # List all active policies
            policies = await conn.fetch(
                """SELECT id, title, description, content, version, status, created_at
                   FROM policies
                   WHERE company_id = $1 AND status = 'active'
                   ORDER BY title ASC""",
                employee["org_id"]
            )

        return {
            "policies": [
                {
                    "id": str(p["id"]),
                    "title": p["title"],
                    "description": p["description"],
                    "content": p["content"][:500] + "..." if p["content"] and len(p["content"]) > 500 else p["content"],
                    "version": p["version"],
                    "created_at": p["created_at"].isoformat() if p["created_at"] else None
                } for p in policies
            ],
            "total": len(policies)
        }


@router.get("/policies/{policy_id}", dependencies=_policies_dep)
async def get_policy(
    policy_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Get a specific policy."""
    async with get_connection() as conn:
        policy = await conn.fetchrow(
            """SELECT id, title, description, content, file_url, version, status, created_at
               FROM policies
               WHERE id = $1 AND company_id = $2 AND status = 'active'""",
            policy_id, employee["org_id"]
        )

        if not policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found"
            )

        return {
            "id": str(policy["id"]),
            "title": policy["title"],
            "description": policy["description"],
            "content": policy["content"],
            "file_url": policy["file_url"],
            "version": policy["version"],
            "created_at": policy["created_at"].isoformat() if policy["created_at"] else None
        }


# ================================
# Onboarding
# ================================

class OnboardingTaskResponse(BaseModel):
    id: UUID
    leave_request_id: Optional[UUID] = None
    title: str
    description: Optional[str]
    category: str
    is_employee_task: bool
    due_date: Optional[date]
    status: str
    completed_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class OnboardingProgress(BaseModel):
    total: int
    completed: int
    pending: int
    tasks: list


class CompleteTaskRequest(BaseModel):
    notes: Optional[str] = None


@router.get("/onboarding", response_model=OnboardingProgress)
async def get_my_onboarding_tasks(
    employee: dict = Depends(require_employee_record)
):
    """Get all onboarding tasks for the current employee."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM employee_onboarding_tasks
            WHERE employee_id = $1
            ORDER BY
                CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                category, due_date, created_at
            """,
            employee["id"]
        )

        tasks = [
            {
                "id": str(row["id"]),
                "leave_request_id": str(row["leave_request_id"]) if row["leave_request_id"] else None,
                "title": row["title"],
                "description": row["description"],
                "category": row["category"],
                "is_employee_task": row["is_employee_task"],
                "due_date": row["due_date"].isoformat() if row["due_date"] else None,
                "status": row["status"],
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "notes": row["notes"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]

        completed = sum(1 for t in tasks if t["status"] == "completed")
        pending = sum(1 for t in tasks if t["status"] == "pending")

        return OnboardingProgress(
            total=len(tasks),
            completed=completed,
            pending=pending,
            tasks=tasks
        )


@router.patch("/onboarding/{task_id}")
async def complete_onboarding_task(
    task_id: UUID,
    request: CompleteTaskRequest,
    employee: dict = Depends(require_employee_record)
):
    """Mark an onboarding task as complete (employee can only complete their own tasks)."""
    async with get_connection() as conn:
        # Get the task
        task = await conn.fetchrow(
            """
            SELECT * FROM employee_onboarding_tasks
            WHERE id = $1 AND employee_id = $2
            """,
            task_id, employee["id"]
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Onboarding task not found"
            )

        # Employee can only complete tasks assigned to them (is_employee_task = true)
        if not task["is_employee_task"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This task must be completed by HR/manager"
            )

        if task["status"] == "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task is already completed"
            )

        # Get user_id from employee record
        user_id = employee.get("user_id")

        # Update the task
        notes = request.notes if request.notes else None
        await conn.execute(
            """
            UPDATE employee_onboarding_tasks
            SET status = 'completed', completed_at = NOW(), completed_by = $1, notes = $2, updated_at = NOW()
            WHERE id = $3
            """,
            user_id, notes, task_id
        )

        return {
            "message": "Task marked as complete",
            "task_id": str(task_id),
            "status": "completed"
        }


# ================================
# XP Features - Vibe Checks
# ================================


def get_current_week_start() -> datetime:
    """Get the start of the current vibe check week (Monday 7 AM)."""
    now = datetime.now(timezone.utc)
    # Calculate days since Monday (Monday = 0)
    days_since_monday = now.weekday()
    # Get this Monday at 7 AM
    monday_7am = now.replace(hour=7, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
    # If we're before Monday 7 AM, use last week's Monday
    if now < monday_7am:
        monday_7am -= timedelta(days=7)
    return monday_7am


def get_next_week_start() -> datetime:
    """Get the start of the next vibe check week (next Monday 7 AM)."""
    return get_current_week_start() + timedelta(days=7)


@router.get("/vibe-checks/status", dependencies=_vibe_dep)
async def get_vibe_check_status(
    employee: dict = Depends(require_employee_record)
):
    """Check if employee can submit a vibe check this week."""
    async with get_connection() as conn:
        # Check if vibe checks are enabled
        config = await conn.fetchrow(
            "SELECT * FROM vibe_check_configs WHERE org_id = $1 AND enabled = true",
            employee["org_id"]
        )

        if not config:
            return {
                "enabled": False,
                "can_submit": False,
                "message": "Vibe checks are not enabled for your organization"
            }

        # Check if already submitted this week
        week_start = get_current_week_start()
        existing = await conn.fetchval(
            """
            SELECT COUNT(*) FROM vibe_check_responses
            WHERE employee_id = $1 AND created_at >= $2
            """,
            employee["id"], week_start
        )

        if existing > 0:
            next_week = get_next_week_start()
            return {
                "enabled": True,
                "can_submit": False,
                "already_submitted": True,
                "next_available": next_week.isoformat(),
                "message": f"You've already submitted this week. Next submission opens Monday at 7 AM."
            }

        return {
            "enabled": True,
            "can_submit": True,
            "week_start": week_start.isoformat(),
            "message": "Ready to submit your vibe check"
        }


@router.post("/vibe-checks", response_model=VibeCheckResponse, dependencies=_vibe_dep)
async def submit_vibe_check(
    submission: VibeCheckSubmit,
    employee: dict = Depends(require_employee_record)
):
    """Submit a vibe check response with real-time AI analysis."""
    import json
    from ..services.vibe_analyzer import VibeAnalyzer

    async with get_connection() as conn:
        # Check if vibe checks are enabled
        config = await conn.fetchrow(
            "SELECT * FROM vibe_check_configs WHERE org_id = $1 AND enabled = true",
            employee["org_id"]
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vibe checks are not enabled for your organization"
            )

        # Check if already submitted this week
        week_start = get_current_week_start()
        existing = await conn.fetchval(
            """
            SELECT COUNT(*) FROM vibe_check_responses
            WHERE employee_id = $1 AND created_at >= $2
            """,
            employee["id"], week_start
        )

        if existing > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You've already submitted a vibe check this week. Next submission opens Monday at 7 AM."
            )

        # Real-time sentiment analysis (if comment provided)
        sentiment_result = None
        if submission.comment:
            try:
                settings = get_settings()
                analyzer = VibeAnalyzer(api_key=settings.gemini_api_key)
                sentiment_result = await analyzer.analyze_sentiment(submission.comment)
            except Exception as e:
                print(f"[VibeCheck] Sentiment analysis failed: {e}")
                # Continue without sentiment analysis

        # Always store employee_id for tracking (anonymity is enforced at display layer)
        result = await conn.fetchrow(
            """
            INSERT INTO vibe_check_responses
            (org_id, employee_id, mood_rating, comment, custom_responses, sentiment_analysis)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            employee["org_id"],
            employee["id"],
            submission.mood_rating,
            submission.comment,
            json.dumps(submission.custom_responses or {}),
            json.dumps(sentiment_result) if sentiment_result else None
        )

        return VibeCheckResponse(**dict(result))


@router.get("/vibe-checks/history", response_model=VibeCheckListResponse, dependencies=_vibe_dep)
async def get_my_vibe_history(
    limit: int = 30,
    offset: int = 0,
    employee: dict = Depends(require_employee_record)
):
    """Get employee's own vibe check history."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM vibe_check_responses
            WHERE employee_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            employee["id"], limit, offset
        )

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM vibe_check_responses WHERE employee_id = $1",
            employee["id"]
        )

        return VibeCheckListResponse(
            responses=[VibeCheckResponse(**r) for r in rows],
            total=total
        )


# ================================
# XP Features - eNPS Surveys
# ================================


@router.get("/enps/surveys/active", response_model=list[ENPSSurveyResponse], dependencies=_enps_dep)
async def get_active_enps_surveys(
    employee: dict = Depends(require_employee_record)
):
    """Get active eNPS surveys for employee to respond to."""
    async with get_connection() as conn:
        today = date.today()

        rows = await conn.fetch(
            """
            SELECT s.* FROM enps_surveys s
            WHERE s.org_id = $1
            AND s.status = 'active'
            AND s.start_date <= $2
            AND s.end_date >= $2
            AND NOT EXISTS (
                SELECT 1
                FROM enps_responses r
                WHERE r.survey_id = s.id
                AND r.employee_id = $3
            )
            AND NOT EXISTS (
                SELECT 1
                FROM enps_anonymous_response_guards g
                WHERE g.survey_id = s.id
                AND g.employee_id = $3
            )
            ORDER BY s.start_date DESC
            """,
            employee["org_id"], today, employee["id"]
        )

        return [ENPSSurveyResponse(**r) for r in rows]


@router.post("/enps/surveys/{survey_id}/respond", dependencies=_enps_dep)
async def submit_enps_response(
    survey_id: UUID,
    submission: ENPSSubmit,
    employee: dict = Depends(require_employee_record)
):
    """Submit eNPS response with real-time theme extraction."""
    import json
    from ..services.enps_analyzer import ENPSAnalyzer

    async with get_connection() as conn:
        today = date.today()

        # Get survey
        survey = await conn.fetchrow(
            """
            SELECT * FROM enps_surveys
            WHERE id = $1
            AND org_id = $2
            AND status = 'active'
            AND start_date <= $3
            AND end_date >= $3
            """,
            survey_id,
            employee["org_id"],
            today,
        )

        if not survey:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Survey not found or is not active for your organization"
            )

        # Determine category
        if submission.score >= 9:
            category = "promoter"
        elif submission.score <= 6:
            category = "detractor"
        else:
            category = "passive"

        # Real-time AI theme extraction (if reason provided)
        sentiment_result = None
        if submission.reason:
            try:
                settings = get_settings()
                analyzer = ENPSAnalyzer(api_key=settings.gemini_api_key)
                sentiment_result = await analyzer.extract_themes_from_reason(
                    submission.reason, submission.score, category
                )
            except Exception as e:
                print(f"[eNPS] Theme extraction failed: {e}")
                # Continue without theme analysis

        # Store response:
        # - Named surveys use employee_id on enps_responses unique constraint.
        # - Anonymous surveys reserve a separate one-response guard, keeping
        #   analytics rows unlinked from employee identity.
        async with conn.transaction():
            if survey["is_anonymous"]:
                guard_id = await conn.fetchval(
                    """
                    INSERT INTO enps_anonymous_response_guards (survey_id, employee_id)
                    VALUES ($1, $2)
                    ON CONFLICT (survey_id, employee_id) DO NOTHING
                    RETURNING id
                    """,
                    survey_id,
                    employee["id"],
                )
                if not guard_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="You have already responded to this survey"
                    )
                response_employee_id = None
            else:
                response_employee_id = employee["id"]

            response_id = await conn.fetchval(
                """
                INSERT INTO enps_responses (survey_id, employee_id, score, reason, category, sentiment_analysis)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (survey_id, employee_id) DO NOTHING
                RETURNING id
                """,
                survey_id,
                response_employee_id,
                submission.score,
                submission.reason,
                category,
                json.dumps(sentiment_result) if sentiment_result else None
            )
            if not response_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You have already responded to this survey"
                )

        return {"message": "Response submitted successfully", "status": "submitted"}


# ================================
# XP Features - Performance Reviews
# ================================


@router.get("/reviews/pending", response_model=list[PerformanceReviewResponse], dependencies=_reviews_dep)
async def get_pending_reviews(
    employee: dict = Depends(require_employee_record)
):
    """Get pending performance reviews for employee (either as reviewee or reviewer)."""
    async with get_connection() as conn:
        # Get reviews where employee is the reviewee or the manager
        rows = await conn.fetch(
            """
            SELECT * FROM performance_reviews
            WHERE (employee_id = $1 OR manager_id = $1)
            AND status IN ('pending', 'self_submitted')
            ORDER BY created_at DESC
            """,
            employee["id"]
        )

        return [PerformanceReviewResponse(**r) for r in rows]


@router.get("/reviews/{review_id}", response_model=PerformanceReviewResponse, dependencies=_reviews_dep)
async def get_review(
    review_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Get a specific performance review (employee must be reviewee or manager)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM performance_reviews
            WHERE id = $1 AND (employee_id = $2 OR manager_id = $2)
            """,
            review_id, employee["id"]
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found or access denied"
            )

        return PerformanceReviewResponse(**row)


@router.post("/reviews/{review_id}/self-assessment", dependencies=_reviews_dep)
async def submit_self_assessment(
    review_id: UUID,
    submission: SelfAssessmentSubmit,
    employee: dict = Depends(require_employee_record)
):
    """Employee submits self-assessment for a performance review."""
    import json

    async with get_connection() as conn:
        # Get review
        review = await conn.fetchrow(
            "SELECT * FROM performance_reviews WHERE id = $1 AND employee_id = $2",
            review_id, employee["id"]
        )

        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found"
            )

        if review["status"] not in ["pending"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Self-assessment already submitted"
            )

        # Update review
        await conn.execute(
            """
            UPDATE performance_reviews
            SET self_ratings = $1, self_comments = $2, self_submitted_at = NOW(), status = 'self_submitted'
            WHERE id = $3
            """,
            json.dumps(submission.self_ratings),
            submission.self_comments,
            review_id
        )

        return {"message": "Self-assessment submitted successfully"}


@router.post("/reviews/{review_id}/manager-review", dependencies=_reviews_dep)
async def submit_manager_review(
    review_id: UUID,
    submission: ManagerReviewSubmit,
    employee: dict = Depends(require_employee_record)
):
    """Manager submits review for a direct report with AI analysis."""
    import json
    from ..services.review_analyzer import ReviewAnalyzer

    async with get_connection() as conn:
        # Get review - must be manager
        review = await conn.fetchrow(
            "SELECT * FROM performance_reviews WHERE id = $1 AND manager_id = $2",
            review_id, employee["id"]
        )

        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found or you are not the manager"
            )

        if review["status"] not in ["self_submitted"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Self-assessment must be submitted first"
            )

        # Get template categories for AI analysis
        cycle = await conn.fetchrow(
            "SELECT template_id FROM review_cycles WHERE id = $1",
            review["cycle_id"]
        )

        template_categories = []
        if cycle and cycle["template_id"]:
            template = await conn.fetchrow(
                "SELECT categories FROM review_templates WHERE id = $1",
                cycle["template_id"]
            )
            if template:
                template_categories = json.loads(template["categories"]) if isinstance(template["categories"], str) else template["categories"]

        # Run AI analysis
        ai_analysis = None
        if review["self_ratings"] and submission.manager_ratings:
            try:
                settings = get_settings()
                analyzer = ReviewAnalyzer(api_key=settings.gemini_api_key)

                self_ratings = json.loads(review["self_ratings"]) if isinstance(review["self_ratings"], str) else review["self_ratings"]

                ai_analysis = await analyzer.analyze_review_alignment(
                    self_ratings=self_ratings,
                    manager_ratings=submission.manager_ratings,
                    template_categories=template_categories,
                    self_comments=review["self_comments"],
                    manager_comments=submission.manager_comments
                )
            except Exception as e:
                print(f"[Review] AI analysis failed: {e}")
                # Continue without AI analysis

        # Update review
        await conn.execute(
            """
            UPDATE performance_reviews
            SET manager_ratings = $1,
                manager_comments = $2,
                manager_overall_rating = $3,
                manager_submitted_at = NOW(),
                ai_analysis = $4,
                status = 'completed',
                completed_at = NOW()
            WHERE id = $5
            """,
            json.dumps(submission.manager_ratings),
            submission.manager_comments,
            submission.manager_overall_rating,
            json.dumps(ai_analysis) if ai_analysis else None,
            review_id
        )

        return {"message": "Manager review submitted successfully"}
