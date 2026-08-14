"""Matcha Ops permission management.

Company-scoped grant listing and mutation, gated on the
``permissions.manage`` Ops capability (company owner or platform admin, or an
explicit ``admin`` grant). Kept separate from Matcha Work permissions so an
Ops-only tenant never depends on the Work permission surface.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import resolve_accessible_company_scope
from app.matcha.services.ops.permissions import (
    OpsAccessLevel,
    OpsCapability,
    OpsPermissionGrant,
    assert_ops_capability,
    can_revoke_ops_permission,
    list_ops_permissions,
    resolve_ops_access,
    revoke_ops_permission,
    upsert_ops_permission,
)

router = APIRouter()


class UpsertPermissionRequest(BaseModel):
    level: OpsAccessLevel

    def model_post_init(self, __context) -> None:
        if self.level == "guest":
            raise ValueError("guest is not a grantable level — revoke instead")


class OpsPermissionGrantOut(BaseModel):
    user_id: UUID
    level: str
    granted_by: UUID | None
    name: str
    email: str


def _grant_payload(grant: OpsPermissionGrant) -> dict:
    return {
        "user_id": str(grant.user_id),
        "level": grant.level,
        "granted_by": str(grant.granted_by) if grant.granted_by else None,
        "name": grant.name,
        "email": grant.email,
    }


async def _manager_access(conn, current_user: CurrentUser):
    scope = await resolve_accessible_company_scope(current_user)
    company_id = scope.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No company associated with your account")
    access = await resolve_ops_access(conn, user=current_user, company_id=company_id)
    try:
        assert_ops_capability(access, OpsCapability.PERMISSIONS_MANAGE)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return company_id, access


@router.get("/me")
async def my_ops_access(current_user: CurrentUser = Depends(get_current_user)):
    scope = await resolve_accessible_company_scope(current_user)
    company_id = scope.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No company associated with your account")
    async with get_connection() as conn:
        access = await resolve_ops_access(conn, user=current_user, company_id=company_id)
    return {
        "level": access.level,
        "capabilities": sorted(capability.value for capability in access.capabilities),
        "source": access.source,
        "can_manage": access.allows(OpsCapability.PERMISSIONS_MANAGE),
    }


@router.get("", response_model=list[OpsPermissionGrantOut])
async def list_permissions(current_user: CurrentUser = Depends(get_current_user)):
    async with get_connection() as conn:
        company_id, _access = await _manager_access(conn, current_user)
        grants = await list_ops_permissions(conn, company_id=company_id)
    return [_grant_payload(g) for g in grants]


@router.put("/{user_id}", response_model=OpsPermissionGrantOut)
async def upsert_permission(
    user_id: UUID,
    body: UpsertPermissionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    async with get_connection() as conn:
        company_id, access = await _manager_access(conn, current_user)
        # A manager may not demote or promote themselves into a dead end; the
        # owner/platform-admin source is immutable anyway (resolved, not stored).
        if not can_revoke_ops_permission(
            actor_user_id=current_user.id,
            target_user_id=user_id,
            source=access.source,
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot change your own permission level")
        grant = await upsert_ops_permission(
            conn,
            company_id=company_id,
            user_id=user_id,
            level=body.level,
            actor_user_id=current_user.id,
        )
    return _grant_payload(grant)


@router.delete("/{user_id}")
async def delete_permission(
    user_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    async with get_connection() as conn:
        company_id, access = await _manager_access(conn, current_user)
        if user_id == current_user.id and access.source != "platform_admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot revoke your own permission level",
            )
        await revoke_ops_permission(
            conn,
            company_id=company_id,
            user_id=user_id,
            actor_user_id=current_user.id,
        )
    return {"ok": True}
