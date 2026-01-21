"""Matcha (HR/Recruiting) domain-specific dependencies."""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status

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
            company_id = await conn.fetchval(
                "SELECT company_id FROM clients WHERE user_id = $1",
                current_user.id
            )
            return company_id

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
