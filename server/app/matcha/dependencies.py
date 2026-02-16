"""Matcha (HR/Recruiting) domain-specific dependencies."""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status

from ..core.feature_flags import merge_company_features
from ..core.dependencies import get_current_user, require_roles
from ..database import get_connection

# Matcha role dependencies
require_client = require_roles("client")
require_employee = require_roles("employee")
require_admin_or_client = require_roles("admin", "client")
require_admin_or_employee = require_roles("admin", "employee")


async def get_client_company_id(
    current_user=Depends(get_current_user)
) -> Optional[UUID]:
    """Get the company_id for a client user. For admins, returns the first company."""
    async with get_connection() as conn:
        if current_user.role == "admin":
            # Admin users: default to first company
            # TODO: Add company selector for admins to switch between companies
            company_id = await conn.fetchval("SELECT id FROM companies ORDER BY created_at LIMIT 1")
            return company_id

        if current_user.role == "client":
            # Get company with status check
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
                return None

            # Check company approval status
            company_status = company["status"] or "approved"

            if company_status == "pending":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your business registration is pending approval. You will be notified once it's reviewed."
                )

            if company_status == "rejected":
                reason = company["rejection_reason"] or "No reason provided"
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Your business registration was not approved. Reason: {reason}"
                )

            return company["company_id"]

        return None


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

        async with get_connection() as conn:
            company_row = None

            if current_user.role == "client":
                company_row = await conn.fetchrow(
                    """
                    SELECT comp.id, comp.status, comp.rejection_reason,
                           COALESCE(comp.enabled_features, '{"offer_letters": true}'::jsonb) as enabled_features
                    FROM clients c
                    JOIN companies comp ON c.company_id = comp.id
                    WHERE c.user_id = $1
                    """,
                    current_user.id
                )
            elif current_user.role == "employee":
                company_row = await conn.fetchrow(
                    """
                    SELECT comp.id, comp.status, comp.rejection_reason,
                           COALESCE(comp.enabled_features, '{"offer_letters": true}'::jsonb) as enabled_features
                    FROM employees e
                    JOIN companies comp ON e.org_id = comp.id
                    WHERE e.user_id = $1
                    """,
                    current_user.id
                )

            if not company_row:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No company associated with this account"
                )

            # Check company approval status
            company_status = company_row["status"] or "approved"
            if company_status == "pending":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your business registration is pending approval."
                )
            if company_status == "rejected":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your business registration was not approved."
                )

            features = merge_company_features(company_row["enabled_features"])

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
