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


@router.get("/permissions")
async def list_work_permissions(
    company_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    target_company_id = await _target_company(current_user, company_id)
    async with get_connection() as conn:
        await _assert_manager(conn, current_user=current_user, company_id=target_company_id)
        rows = await conn.fetch(
            """
            SELECT p.user_id, u.email, u.role, p.level, p.granted_by,
                   p.created_at, p.updated_at
              FROM mw_work_permissions p
              JOIN users u ON u.id = p.user_id
             WHERE p.company_id = $1
             ORDER BY u.email
            """,
            target_company_id,
        )
    return {
        "company_id": target_company_id,
        "permissions": [dict(row) for row in rows],
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
        eligible = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM clients WHERE user_id = $1 AND company_id = $2
                UNION ALL
                SELECT 1 FROM employees WHERE user_id = $1 AND org_id = $2
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
