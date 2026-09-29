"""Who may reach a matcha-work project: the one rule behind the REST routes'
`_verify_project_access` and every non-HTTP surface (the agent-card chat
answers). Keep it here so the two can't drift apart.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

# HR-sensitive project types are mw_projects under the same company, but
# employees (werk-lite whole-company access) must not reach them.
EMPLOYEE_HIDDEN_PROJECT_TYPES = ("discipline", "recruiting")


def role_can_edit(role: Optional[str]) -> bool:
    """Write gate: only the explicit read-only roles are blocked (the owner can
    come back as role None or 'owner' depending on the access path)."""
    return role not in ("viewer", "commenter")


def hidden_from_user(project: dict, user) -> bool:
    return user.role == "employee" and project.get("project_type") in EMPLOYEE_HIDDEN_PROJECT_TYPES


async def resolve_project_access(project_id: UUID, user, *, company_id: Optional[UUID]) -> Optional[tuple[dict, str]]:
    """(project, role), or None when this user can't reach the project.

    `company_id` is the caller's resolved company (`get_client_company_id`);
    admins are not scoped by company and reach a project only as a collaborator.
    """
    # Through the package so tests that patch project_service.* keep working.
    from app.matcha.services.matcha_work import project_service as proj_svc

    if user.role == "admin":
        return await proj_svc.get_project_as_collaborator(project_id, user.id)
    project = await proj_svc.get_project(project_id, company_id, user_id=user.id) if company_id else None
    if not project:
        result = await proj_svc.get_project_as_collaborator(project_id, user.id)
        if result and hidden_from_user(result[0], user):
            return None
        return result
    if hidden_from_user(project, user):
        return None
    if not project.get("collaborator_role"):
        project["collaborator_role"] = "owner"
    return project, project["collaborator_role"]
