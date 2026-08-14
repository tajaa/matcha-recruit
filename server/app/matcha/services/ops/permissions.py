"""Company-scoped Ops permissions.

Ops permissions intentionally have their own table and capability enum. This
prevents an Ops-only tenant from depending on Matcha Work's permission routes
while preserving the same role defaults used by the existing Work system.

The capability values deliberately match the Work enum's string values so the
frontend's capability checks and the EMS domain helpers that read
``access.allows(...)`` keep working during the migration — but the enum type,
storage, and resolver are Ops-owned.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal
from uuid import UUID

from app.core.models.auth import CurrentUser


OpsAccessLevel = Literal["guest", "member", "reviewer", "operator", "admin"]
OpsAccessSource = Literal[
    "platform_admin",
    "explicit",
    "company_owner",
    "client_default",
    "employee_default",
    "external_default",
]


class OpsCapability(str, Enum):
    """Capabilities granted by Ops permission levels.

    Values mirror ``WorkCapability`` so any remaining frontend capability
    string checks continue to resolve, but Ops authorization is independent of
    Matcha Work permission rows.
    """

    EVENT_CONFIRM_OWN = "events.confirm_own"
    EVENT_REVIEW = "events.review"
    EVENT_RESOLVE = "events.resolve"
    EVENT_PROMOTE = "events.promote"
    EVENT_ASSIGN = "events.assign"
    SENSITIVE_RECORD_READ = "records.view_sensitive"
    ACTION_PROPOSE = "actions.propose"
    ACTION_APPROVE = "actions.approve"
    ACTION_EXECUTE = "actions.execute"
    PERMISSIONS_MANAGE = "permissions.manage"


class OpsPermissionDenied(PermissionError):
    """Raised by the pure authorization helpers when a capability is absent."""

    def __init__(self, capability: OpsCapability):
        self.capability = capability
        super().__init__(f"Matcha Ops capability required: {capability.value}")


def can_revoke_ops_permission(*, actor_user_id: UUID, target_user_id: UUID, source: str) -> bool:
    """Prevent non-platform managers from revoking their own grant."""
    return actor_user_id != target_user_id or source == "platform_admin"


@dataclass(frozen=True)
class OpsAccess:
    company_id: UUID
    user_id: UUID
    level: OpsAccessLevel
    capabilities: frozenset[OpsCapability]
    source: OpsAccessSource

    def allows(self, capability: OpsCapability) -> bool:
        return capability in self.capabilities


_LEVEL_CAPABILITIES: dict[OpsAccessLevel, frozenset[OpsCapability]] = {
    "guest": frozenset(),
    "member": frozenset({OpsCapability.EVENT_CONFIRM_OWN, OpsCapability.ACTION_PROPOSE}),
    "reviewer": frozenset({
        OpsCapability.EVENT_CONFIRM_OWN,
        OpsCapability.EVENT_REVIEW,
        OpsCapability.EVENT_RESOLVE,
        OpsCapability.EVENT_ASSIGN,
        OpsCapability.SENSITIVE_RECORD_READ,
        OpsCapability.ACTION_PROPOSE,
    }),
    "operator": frozenset({
        OpsCapability.EVENT_CONFIRM_OWN,
        OpsCapability.EVENT_REVIEW,
        OpsCapability.EVENT_RESOLVE,
        OpsCapability.EVENT_PROMOTE,
        OpsCapability.EVENT_ASSIGN,
        OpsCapability.SENSITIVE_RECORD_READ,
        OpsCapability.ACTION_PROPOSE,
        OpsCapability.ACTION_APPROVE,
        OpsCapability.ACTION_EXECUTE,
    }),
    "admin": frozenset(OpsCapability),
}


def capabilities_for_level(level: OpsAccessLevel) -> frozenset[OpsCapability]:
    return _LEVEL_CAPABILITIES[level]


def assert_ops_capability(access: OpsAccess, capability: OpsCapability) -> None:
    if not access.allows(capability):
        raise OpsPermissionDenied(capability)


async def resolve_ops_access(
    conn,
    *,
    user: CurrentUser,
    company_id: UUID,
) -> OpsAccess:
    """Resolve effective Ops access for ``user`` in ``company_id``.

    Reads only ``ops_permissions`` — never ``mw_work_permissions``. The
    migration backfill (matchaops02) is the one-time bridge that copies
    existing Work grants into Ops; after that the two systems are independent.
    """
    if user.role == "admin":
        return OpsAccess(company_id, user.id, "admin", _LEVEL_CAPABILITIES["admin"], "platform_admin")

    owner_id = await conn.fetchval("SELECT owner_id FROM companies WHERE id = $1", company_id)
    if owner_id == user.id:
        return OpsAccess(company_id, user.id, "admin", _LEVEL_CAPABILITIES["admin"], "company_owner")

    explicit = await conn.fetchval(
        "SELECT level FROM ops_permissions WHERE company_id = $1 AND user_id = $2",
        company_id,
        user.id,
    )
    if explicit in _LEVEL_CAPABILITIES and explicit != "guest":
        level = explicit
        return OpsAccess(company_id, user.id, level, _LEVEL_CAPABILITIES[level], "explicit")

    client_company_id = await conn.fetchval("SELECT company_id FROM clients WHERE user_id = $1", user.id)
    employee_company_id = await conn.fetchval(
        "SELECT org_id FROM employees WHERE user_id = $1 AND termination_date IS NULL",
        user.id,
    )
    if client_company_id == company_id:
        level, source = "operator", "client_default"
    elif employee_company_id == company_id:
        level, source = "member", "employee_default"
    else:
        level, source = "guest", "external_default"
    return OpsAccess(company_id, user.id, level, _LEVEL_CAPABILITIES[level], source)


@dataclass(frozen=True)
class OpsPermissionGrant:
    company_id: UUID
    user_id: UUID
    level: OpsAccessLevel
    granted_by: UUID | None
    created_at: object
    updated_at: object
    name: str
    email: str


async def list_ops_permissions(conn, *, company_id: UUID) -> list[OpsPermissionGrant]:
    rows = await conn.fetch(
        """
        SELECT op.company_id, op.user_id, op.level, op.granted_by, op.created_at, op.updated_at,
               COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name,
               u.email
          FROM ops_permissions op
          JOIN users u ON u.id = op.user_id
          LEFT JOIN clients c ON c.user_id = u.id
          LEFT JOIN employees e ON e.user_id = u.id
          LEFT JOIN admins a ON a.user_id = u.id
         WHERE op.company_id = $1
         ORDER BY op.created_at ASC
        """,
        company_id,
    )
    return [OpsPermissionGrant(**dict(r)) for r in rows]


async def upsert_ops_permission(
    conn,
    *,
    company_id: UUID,
    user_id: UUID,
    level: OpsAccessLevel,
    actor_user_id: UUID,
) -> OpsPermissionGrant:
    old = await conn.fetchval(
        "SELECT level FROM ops_permissions WHERE company_id = $1 AND user_id = $2",
        company_id,
        user_id,
    )
    row = await conn.fetchrow(
        """
        INSERT INTO ops_permissions (company_id, user_id, level, granted_by)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (company_id, user_id)
        DO UPDATE SET level = EXCLUDED.level, granted_by = EXCLUDED.granted_by, updated_at = NOW()
        RETURNING company_id, user_id, level, granted_by, created_at, updated_at
        """,
        company_id,
        user_id,
        level,
        actor_user_id,
    )
    action = "updated" if old is not None else "granted"
    await conn.execute(
        """
        INSERT INTO ops_permission_audit_log (company_id, user_id, actor_user_id, action, old_level, new_level)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        company_id,
        user_id,
        actor_user_id,
        action,
        old,
        level,
    )
    detail = await conn.fetchrow(
        """
        SELECT u.email, COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
          FROM users u
          LEFT JOIN clients c ON c.user_id = u.id
          LEFT JOIN employees e ON e.user_id = u.id
          LEFT JOIN admins a ON a.user_id = u.id
         WHERE u.id = $1
        """,
        user_id,
    )
    return OpsPermissionGrant(
        company_id=company_id,
        user_id=user_id,
        level=level,
        granted_by=actor_user_id,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        name=detail["name"],
        email=detail["email"],
    )


async def revoke_ops_permission(
    conn,
    *,
    company_id: UUID,
    user_id: UUID,
    actor_user_id: UUID,
) -> None:
    old = await conn.fetchval(
        "SELECT level FROM ops_permissions WHERE company_id = $1 AND user_id = $2",
        company_id,
        user_id,
    )
    if old is None:
        return
    await conn.execute(
        "DELETE FROM ops_permissions WHERE company_id = $1 AND user_id = $2",
        company_id,
        user_id,
    )
    await conn.execute(
        """
        INSERT INTO ops_permission_audit_log (company_id, user_id, actor_user_id, action, old_level, new_level)
        VALUES ($1, $2, $3, 'revoked', $4, NULL)
        """,
        company_id,
        user_id,
        actor_user_id,
        old,
    )
