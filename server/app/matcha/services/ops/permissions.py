"""Company-scoped Ops permissions.

Ops permissions intentionally have their own table and capability enum. This
prevents an Ops-only tenant from depending on Matcha Work's permission routes
while preserving the same role defaults used by the existing Work system.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal
from uuid import UUID

import asyncpg

from app.core.models.auth import CurrentUser
from app.matcha.services.matcha_work.work_permissions import WorkCapability


OpsAccessLevel = Literal["guest", "member", "reviewer", "operator", "admin"]
OpsAccessSource = Literal[
    "platform_admin",
    "explicit",
    "company_owner",
    "client_default",
    "employee_default",
    "external_default",
]


# Capability values remain compatible with the existing EMS service helpers
# during the migration. The storage and access resolver are Ops-owned; this
# alias lets old event domain functions accept the same capability enum while
# their imports are moved incrementally.
OpsCapability = WorkCapability


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


async def resolve_ops_access(
    conn,
    *,
    user: CurrentUser,
    company_id: UUID,
) -> OpsAccess:
    if user.role == "admin":
        return OpsAccess(company_id, user.id, "admin", _LEVEL_CAPABILITIES["admin"], "platform_admin")

    owner_id = await conn.fetchval("SELECT owner_id FROM companies WHERE id = $1", company_id)
    if owner_id == user.id:
        return OpsAccess(company_id, user.id, "admin", _LEVEL_CAPABILITIES["admin"], "company_owner")

    try:
        explicit = await conn.fetchval(
            "SELECT level FROM ops_permissions WHERE company_id = $1 AND user_id = $2",
            company_id,
            user.id,
        )
    except asyncpg.UndefinedTableError:
        # Backend deploys may precede the additive migration. The old table
        # carries the same levels, so preserve access during the rollout.
        explicit = await conn.fetchval(
            "SELECT level FROM mw_work_permissions WHERE company_id = $1 AND user_id = $2",
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
