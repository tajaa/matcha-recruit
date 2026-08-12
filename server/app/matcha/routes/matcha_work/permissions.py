"""Company-scoped Matcha Work permission management."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import resolve_accessible_company_scope
from app.matcha.services.matcha_work.work_permissions import (
    WorkCapability,
    WorkPermissionDenied,
    assert_work_capability,
    effective_access,
    resolve_work_access,
)

router = APIRouter()


class WorkPermissionUpdate(BaseModel):
    level: Literal["member", "reviewer", "operator", "admin"]


async def _target_company(current_user: CurrentUser, requested_company_id: UUID | None):
    scope = await resolve_accessible_company_scope(current_user, requested_company_id)
    company_id = scope.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    return company_id


async def _assert_manager(conn, *, current_user: CurrentUser, company_id: UUID) -> None:
    access = await resolve_work_access(conn, user=current_user, company_id=company_id)
    try:
        assert_work_capability(access, WorkCapability.PERMISSIONS_MANAGE)
    except WorkPermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


async def _company_owner_id(conn, *, company_id: UUID) -> UUID | None:
    return await conn.fetchval(
        "SELECT owner_id FROM companies WHERE id = $1",
        company_id,
    )


@router.get("/permissions")
async def list_work_permissions(
    company_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    target_company_id = await _target_company(current_user, company_id)
    async with get_connection() as conn:
        await _assert_manager(conn, current_user=current_user, company_id=target_company_id)
        company_name = await conn.fetchval(
            "SELECT name FROM companies WHERE id = $1",
            target_company_id,
        )
        rows = await conn.fetch(
            """
            WITH eligible AS (
                SELECT c.user_id, 'company_client'::text AS source
                  FROM clients c
                 WHERE c.company_id = $1
                UNION
                SELECT e.user_id, 'company_employee'::text
                  FROM employees e
                 WHERE e.org_id = $1
                   AND e.user_id IS NOT NULL
                   AND e.termination_date IS NULL
                UNION
                SELECT cm.user_id, 'channel_member'::text
                  FROM channel_members cm
                  JOIN channels ch ON ch.id = cm.channel_id
                 WHERE ch.company_id = $1
                   AND cm.removed_for_inactivity IS NOT TRUE
                UNION
                SELECT tc.user_id, 'thread_collaborator'::text
                  FROM mw_thread_collaborators tc
                  JOIN mw_threads t ON t.id = tc.thread_id
                 WHERE t.company_id = $1
                UNION
                SELECT pc.user_id, 'project_collaborator'::text
                  FROM mw_project_collaborators pc
                  JOIN mw_projects p ON p.id = pc.project_id
                 WHERE p.company_id = $1 AND pc.status = 'active'
                UNION
                SELECT owner_id, 'company_owner'::text
                  FROM companies
                 WHERE id = $1 AND owner_id IS NOT NULL
                UNION
                SELECT p.user_id, 'explicit_grant'::text
                  FROM mw_work_permissions p
                 WHERE p.company_id = $1
            ), grouped AS (
                SELECT user_id, array_agg(DISTINCT source ORDER BY source) AS eligible_via
                  FROM eligible
                 GROUP BY user_id
            )
            SELECT g.user_id, u.email, u.role, u.avatar_url,
                   COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name,
                   g.eligible_via,
                   p.level AS explicit_level, p.granted_by, p.created_at, p.updated_at,
                   (c.owner_id = g.user_id) AS is_company_owner
              FROM grouped g
              JOIN users u ON u.id = g.user_id
              LEFT JOIN clients cl ON cl.user_id = g.user_id AND cl.company_id = $1
              LEFT JOIN employees e ON e.user_id = g.user_id AND e.org_id = $1
              LEFT JOIN admins a ON a.user_id = g.user_id
              LEFT JOIN mw_work_permissions p
                ON p.company_id = $1 AND p.user_id = g.user_id
              JOIN companies c ON c.id = $1
             WHERE u.is_active IS NOT FALSE
             ORDER BY name, u.email
            """,
            target_company_id,
        )
        permissions = []
        for row in rows:
            access = effective_access(
                company_id=target_company_id,
                user_id=row["user_id"],
                user_role=row["role"],
                explicit_level=row["explicit_level"],
                is_platform_admin=(row["role"] == "admin"),
                is_company_owner=bool(row["is_company_owner"]),
                is_company_client="company_client" in row["eligible_via"],
                is_company_employee="company_employee" in row["eligible_via"],
            )
            permissions.append({
                "user_id": str(row["user_id"]),
                "email": row["email"],
                "name": row["name"],
                "role": row["role"],
                "avatar_url": row["avatar_url"],
                "eligible_via": list(row["eligible_via"]),
                "explicit_level": row["explicit_level"],
                "effective_level": access.level,
                "effective_source": access.source,
                "capabilities": sorted(capability.value for capability in access.capabilities),
                "granted_by": str(row["granted_by"]) if row["granted_by"] else None,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "immutable": bool(row["is_company_owner"]) or row["role"] == "admin",
            })
    return {
        "company_id": target_company_id,
        "company_name": company_name,
        "permissions": permissions,
    }


@router.put("/permissions/{user_id}")
async def set_work_permission(
    user_id: UUID,
    body: WorkPermissionUpdate,
    company_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    target_company_id = await _target_company(current_user, company_id)
    async with get_connection() as conn:
        await _assert_manager(conn, current_user=current_user, company_id=target_company_id)
        if await _company_owner_id(conn, company_id=target_company_id) == user_id:
            raise HTTPException(
                status_code=400,
                detail="The company owner's access cannot be changed",
            )
        eligible = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM clients WHERE user_id = $1 AND company_id = $2
                UNION ALL
                SELECT 1
                  FROM employees
                 WHERE user_id = $1
                   AND org_id = $2
                   AND termination_date IS NULL
                UNION ALL
                SELECT 1
                  FROM channel_members cm
                  JOIN channels ch ON ch.id = cm.channel_id
                 WHERE cm.user_id = $1
                   AND ch.company_id = $2
                   AND cm.removed_for_inactivity IS NOT TRUE
                UNION ALL
                SELECT 1
                  FROM mw_thread_collaborators tc
                  JOIN mw_threads t ON t.id = tc.thread_id
                 WHERE tc.user_id = $1 AND t.company_id = $2
                UNION ALL
                SELECT 1
                  FROM mw_project_collaborators pc
                  JOIN mw_projects p ON p.id = pc.project_id
                 WHERE pc.user_id = $1
                   AND p.company_id = $2
                   AND pc.status = 'active'
            )
            """,
            user_id,
            target_company_id,
        )
        if not eligible:
            raise HTTPException(
                status_code=400,
                detail="User must be a company member or active shared-resource collaborator",
            )
        async with conn.transaction():
            previous_level = await conn.fetchval(
                "SELECT level FROM mw_work_permissions WHERE company_id = $1 AND user_id = $2",
                target_company_id,
                user_id,
            )
            row = await conn.fetchrow(
                """
                INSERT INTO mw_work_permissions (company_id, user_id, level, granted_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (company_id, user_id) DO UPDATE
                    SET level = EXCLUDED.level,
                        granted_by = EXCLUDED.granted_by,
                        updated_at = NOW()
                RETURNING company_id, user_id, level, granted_by, created_at, updated_at
                """,
                target_company_id,
                user_id,
                body.level,
                current_user.id,
            )
            await conn.execute(
                """
                INSERT INTO mw_work_permission_audit_log
                    (company_id, user_id, actor_user_id, action, old_level, new_level)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                target_company_id,
                user_id,
                current_user.id,
                "updated" if previous_level else "granted",
                previous_level,
                body.level,
            )
    return dict(row)


@router.delete("/permissions/{user_id}")
async def delete_work_permission(
    user_id: UUID,
    company_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    target_company_id = await _target_company(current_user, company_id)
    async with get_connection() as conn:
        await _assert_manager(conn, current_user=current_user, company_id=target_company_id)
        if await _company_owner_id(conn, company_id=target_company_id) == user_id:
            raise HTTPException(
                status_code=400,
                detail="The company owner's access cannot be changed",
            )
        async with conn.transaction():
            deleted = await conn.fetchval(
                """
                DELETE FROM mw_work_permissions
                 WHERE company_id = $1 AND user_id = $2
                RETURNING level
                """,
                target_company_id,
                user_id,
            )
            if deleted is not None:
                await conn.execute(
                    """
                    INSERT INTO mw_work_permission_audit_log
                        (company_id, user_id, actor_user_id, action, old_level, new_level)
                    VALUES ($1, $2, $3, 'revoked', $4, NULL)
                    """,
                    target_company_id,
                    user_id,
                    current_user.id,
                    deleted,
                )
    return {"ok": True}
