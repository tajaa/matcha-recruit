"""Matcha (HR/Recruiting) domain-specific dependencies."""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status

from ..core.feature_flags import default_company_features_json, merge_company_features
from ..core.dependencies import get_current_user, require_roles
from ..database import get_connection

# Matcha role dependencies
require_client = require_roles("client")
require_employee = require_roles("employee")
require_admin_or_client = require_roles("admin", "client")
require_admin_or_client_or_broker = require_roles("admin", "client", "broker")
require_admin_or_employee = require_roles("admin", "employee")
require_broker = require_roles("broker")

BROKER_ACTIVE_LINK_STATUSES = ("active", "grace")


def _ensure_company_is_accessible(company_status: Optional[str], rejection_reason: Optional[str]) -> None:
    """Raise an HTTP 403 if a company status blocks access."""
    status_value = company_status or "approved"
    if status_value == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your business registration is pending approval. You will be notified once it's reviewed."
        )
    if status_value == "rejected":
        reason = rejection_reason or "No reason provided"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your business registration was not approved. Reason: {reason}"
        )


async def resolve_accessible_company_scope(
    current_user,
    requested_company_id: Optional[UUID] = None,
) -> dict:
    """
    Centralized tenant access resolver.

    Returns scope metadata used by company-scoped routes and dependencies.
    """
    async with get_connection() as conn:
        if current_user.role == "admin":
            selected_company_id = requested_company_id
            if selected_company_id is not None:
                exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1)", selected_company_id)
                if not exists:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
            else:
                selected_company_id = await conn.fetchval("SELECT id FROM companies ORDER BY created_at LIMIT 1")

            company_ids = [selected_company_id] if selected_company_id else []
            return {
                "company_id": selected_company_id,
                "company_ids": company_ids,
                "actor_role": "admin",
                "broker_id": None,
                "broker_member_role": None,
                "link_permissions": {},
                "terms_accepted": True,
            }

        if current_user.role == "client":
            company = await conn.fetchrow(
                """
                SELECT c.company_id, comp.status, comp.rejection_reason
                FROM clients c
                JOIN companies comp ON c.company_id = comp.id
                WHERE c.user_id = $1
                """,
                current_user.id
            )
            if not company:
                return {
                    "company_id": None,
                    "company_ids": [],
                    "actor_role": "client",
                    "broker_id": None,
                    "broker_member_role": None,
                    "link_permissions": {},
                    "terms_accepted": True,
                }

            _ensure_company_is_accessible(company["status"], company["rejection_reason"])
            company_id = company["company_id"]
            if requested_company_id and requested_company_id != company_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for requested company")

            return {
                "company_id": company_id,
                "company_ids": [company_id],
                "actor_role": "client",
                "broker_id": None,
                "broker_member_role": None,
                "link_permissions": {},
                "terms_accepted": True,
            }

        if current_user.role == "employee":
            company = await conn.fetchrow(
                """
                SELECT e.org_id as company_id, comp.status, comp.rejection_reason
                FROM employees e
                JOIN companies comp ON e.org_id = comp.id
                WHERE e.user_id = $1
                """,
                current_user.id
            )
            if not company:
                return {
                    "company_id": None,
                    "company_ids": [],
                    "actor_role": "employee",
                    "broker_id": None,
                    "broker_member_role": None,
                    "link_permissions": {},
                    "terms_accepted": True,
                }

            _ensure_company_is_accessible(company["status"], company["rejection_reason"])
            company_id = company["company_id"]
            if requested_company_id and requested_company_id != company_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for requested company")

            return {
                "company_id": company_id,
                "company_ids": [company_id],
                "actor_role": "employee",
                "broker_id": None,
                "broker_member_role": None,
                "link_permissions": {},
                "terms_accepted": True,
            }

        if current_user.role == "broker":
            membership = await conn.fetchrow(
                """
                SELECT
                    bm.broker_id,
                    bm.role as member_role,
                    bm.is_active as member_active,
                    b.status as broker_status,
                    COALESCE(b.terms_required_version, 'v1') as terms_required_version
                FROM broker_members bm
                JOIN brokers b ON b.id = bm.broker_id
                WHERE bm.user_id = $1
                ORDER BY bm.created_at ASC
                LIMIT 1
                """,
                current_user.id,
            )
            if not membership or not membership["member_active"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No active broker membership found for this account",
                )

            if membership["broker_status"] != "active":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Broker account is not active",
                )

            required_terms = membership["terms_required_version"]
            terms_accepted = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM broker_terms_acceptances
                    WHERE broker_id = $1
                      AND user_id = $2
                      AND terms_version = $3
                )
                """,
                membership["broker_id"],
                current_user.id,
                required_terms,
            )
            if not terms_accepted:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Broker partner terms must be accepted before accessing client companies",
                )

            if requested_company_id:
                row = await conn.fetchrow(
                    """
                    SELECT
                        l.company_id,
                        l.permissions,
                        comp.status as company_status,
                        comp.rejection_reason
                    FROM broker_company_links l
                    JOIN companies comp ON comp.id = l.company_id
                    WHERE l.broker_id = $1
                      AND l.company_id = $2
                      AND l.status = ANY($3::text[])
                    """,
                    membership["broker_id"],
                    requested_company_id,
                    list(BROKER_ACTIVE_LINK_STATUSES),
                )
                if not row:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Broker does not have access to the requested company",
                    )
                _ensure_company_is_accessible(row["company_status"], row["rejection_reason"])
                link_permissions = row["permissions"] if isinstance(row["permissions"], dict) else {}
                return {
                    "company_id": row["company_id"],
                    "company_ids": [row["company_id"]],
                    "actor_role": "broker",
                    "broker_id": membership["broker_id"],
                    "broker_member_role": membership["member_role"],
                    "link_permissions": link_permissions,
                    "terms_accepted": True,
                }

            rows = await conn.fetch(
                """
                SELECT
                    l.company_id,
                    l.permissions,
                    comp.status as company_status,
                    comp.rejection_reason
                FROM broker_company_links l
                JOIN companies comp ON comp.id = l.company_id
                WHERE l.broker_id = $1
                  AND l.status = ANY($2::text[])
                ORDER BY l.activated_at NULLS LAST, l.created_at
                """,
                membership["broker_id"],
                list(BROKER_ACTIVE_LINK_STATUSES),
            )

            valid_company_ids: list[UUID] = []
            selected_permissions: dict = {}
            for row in rows:
                # Pending/rejected client registrations are not accessible
                if (row["company_status"] or "approved") in {"pending", "rejected"}:
                    continue
                valid_company_ids.append(row["company_id"])
                if not selected_permissions:
                    selected_permissions = row["permissions"] if isinstance(row["permissions"], dict) else {}

            selected_company_id = valid_company_ids[0] if valid_company_ids else None
            return {
                "company_id": selected_company_id,
                "company_ids": valid_company_ids,
                "actor_role": "broker",
                "broker_id": membership["broker_id"],
                "broker_member_role": membership["member_role"],
                "link_permissions": selected_permissions,
                "terms_accepted": True,
            }

    return {
        "company_id": None,
        "company_ids": [],
        "actor_role": current_user.role,
        "broker_id": None,
        "broker_member_role": None,
        "link_permissions": {},
        "terms_accepted": True,
    }


async def get_accessible_company_scope(
    current_user=Depends(get_current_user),
) -> dict:
    """Dependency that returns centralized company access scope."""
    return await resolve_accessible_company_scope(current_user)


async def get_client_company_id(
    current_user=Depends(get_current_user)
) -> Optional[UUID]:
    """
    Backwards-compatible accessor for legacy company-scoped routes.

    This now delegates to the centralized resolver.
    """
    scope = await resolve_accessible_company_scope(current_user)
    return scope.get("company_id")


async def get_employee_info(
    current_user=Depends(get_current_user)
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
    current_user=Depends(require_employee)
) -> dict:
    """Require the current user to be an employee with a valid employee record."""
    async with get_connection() as conn:
        employee = await conn.fetchrow(
            """SELECT id, org_id, user_id, email, first_name, last_name, work_state,
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
    current_user=Depends(get_current_user)
):
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


def require_feature(feature_name: str):
    """Factory that returns a dependency checking if a company feature is enabled.

    Also verifies the company is approved (pending/rejected companies are blocked).
    Admin users bypass all checks.
    """
    async def checker(current_user=Depends(get_current_user)):
        # Admin bypasses all feature checks
        if current_user.role == "admin":
            return current_user

        scope = await resolve_accessible_company_scope(current_user)
        company_id = scope.get("company_id")
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No company associated with this account"
            )

        async with get_connection() as conn:
            enabled_features = await conn.fetchval(
                """
                SELECT COALESCE(enabled_features, $2::jsonb)
                FROM companies
                WHERE id = $1
                """,
                company_id,
                default_company_features_json(),
            )
            if enabled_features is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Company not found",
                )

            features = merge_company_features(enabled_features)

            if not features.get(feature_name, False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"The '{feature_name}' feature is not enabled for your company"
                )

        return current_user
    return checker


async def verify_manager_access(
    current_user,
    target_employee_id: UUID
) -> bool:
    """
    Check if current user is manager of target employee or has admin/client role.

    Args:
        current_user: Current authenticated user
        target_employee_id: UUID of the employee to check access for

    Returns:
        bool: True if user has access, False otherwise
    """
    # Admins and clients have access to all employees in their org
    if current_user.role in ["admin", "client"]:
        return True

    # For employees, check if they're the manager
    async with get_connection() as conn:
        # Get current user's employee record
        current_emp = await conn.fetchrow(
            "SELECT id FROM employees WHERE user_id = $1",
            current_user.id
        )

        if not current_emp:
            return False

        # Check if target employee reports to current user
        is_manager = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM employees WHERE id = $1 AND manager_id = $2)",
            target_employee_id, current_emp["id"]
        )

        return bool(is_manager)
