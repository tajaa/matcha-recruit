"""Company-scoped Matcha Work authorization.

Work permissions are deliberately resolved against the company that owns the
resource being accessed. A user may be a collaborator on another company's
channel or workspace, but their home-company role must not grant access to the
target company's records or actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Collection, Literal
from uuid import UUID

from app.core.models.auth import CurrentUser


WorkAccessLevel = Literal["guest", "member", "reviewer", "operator", "admin"]
WorkAccessSource = Literal[
    "platform_admin",
    "explicit",
    "company_owner",
    "client_default",
    "employee_default",
    "external_default",
]


class WorkCapability(str, Enum):
    """Capabilities used by both REST and Huume execution paths."""

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


class WorkPermissionDenied(PermissionError):
    """Raised by the pure authorization helpers when a capability is absent."""

    def __init__(self, capability: WorkCapability):
        self.capability = capability
        super().__init__(f"Matcha Work capability required: {capability.value}")


@dataclass(frozen=True)
class WorkAccess:
    company_id: UUID
    user_id: UUID
    level: WorkAccessLevel
    capabilities: frozenset[WorkCapability]
    source: WorkAccessSource

    def allows(self, capability: WorkCapability) -> bool:
        return capability in self.capabilities


_LEVEL_CAPABILITIES: dict[WorkAccessLevel, frozenset[WorkCapability]] = {
    "guest": frozenset(),
    "member": frozenset(
        {
            WorkCapability.EVENT_CONFIRM_OWN,
            WorkCapability.ACTION_PROPOSE,
        }
    ),
    "reviewer": frozenset(
        {
            WorkCapability.EVENT_CONFIRM_OWN,
            WorkCapability.EVENT_REVIEW,
            WorkCapability.EVENT_RESOLVE,
            WorkCapability.EVENT_ASSIGN,
            WorkCapability.SENSITIVE_RECORD_READ,
            WorkCapability.ACTION_PROPOSE,
        }
    ),
    "operator": frozenset(
        {
            WorkCapability.EVENT_CONFIRM_OWN,
            WorkCapability.EVENT_REVIEW,
            WorkCapability.EVENT_RESOLVE,
            WorkCapability.EVENT_PROMOTE,
            WorkCapability.EVENT_ASSIGN,
            WorkCapability.SENSITIVE_RECORD_READ,
            WorkCapability.ACTION_PROPOSE,
            WorkCapability.ACTION_APPROVE,
            WorkCapability.ACTION_EXECUTE,
        }
    ),
    "admin": frozenset(WorkCapability),
}


def capabilities_for_level(level: WorkAccessLevel) -> frozenset[WorkCapability]:
    """Return an immutable capability set for a Work access level."""

    return _LEVEL_CAPABILITIES[level]


def capability_allowed(
    access: WorkAccess,
    capability: WorkCapability,
) -> bool:
    return access.allows(capability)


def assert_work_capability(
    access: WorkAccess,
    capability: WorkCapability,
) -> None:
    if not capability_allowed(access, capability):
        raise WorkPermissionDenied(capability)


async def resolve_work_access(
    conn,
    *,
    user: CurrentUser,
    company_id: UUID,
) -> WorkAccess:
    """Resolve effective Work access for ``user`` in ``company_id``.

    Explicit grants win over defaults. Platform admins are an override. A
    collaborator who belongs to another company receives guest access unless
    the target company has explicitly granted a Work level.
    """

    if user.role == "admin":
        level: WorkAccessLevel = "admin"
        source: WorkAccessSource = "platform_admin"
    else:
        explicit_level = await conn.fetchval(
            """
            SELECT level
              FROM mw_work_permissions
             WHERE company_id = $1 AND user_id = $2
            """,
            company_id,
            user.id,
        )
        if explicit_level in _LEVEL_CAPABILITIES and explicit_level != "guest":
            level = explicit_level
            source = "explicit"
        else:
            owner_id = await conn.fetchval(
                "SELECT owner_id FROM companies WHERE id = $1",
                company_id,
            )
            if owner_id == user.id:
                level = "admin"
                source = "company_owner"
            else:
                client_company_id = await conn.fetchval(
                    "SELECT company_id FROM clients WHERE user_id = $1",
                    user.id,
                )
                employee_company_id = await conn.fetchval(
                    "SELECT org_id FROM employees WHERE user_id = $1",
                    user.id,
                )
                if client_company_id == company_id:
                    level = "operator"
                    source = "client_default"
                elif employee_company_id == company_id:
                    level = "member"
                    source = "employee_default"
                else:
                    level = "guest"
                    source = "external_default"

    return WorkAccess(
        company_id=company_id,
        user_id=user.id,
        level=level,
        capabilities=capabilities_for_level(level),
        source=source,
    )


def access_from_capabilities(
    *,
    company_id: UUID,
    user_id: UUID,
    level: WorkAccessLevel,
    capabilities: Collection[WorkCapability],
    source: WorkAccessSource = "explicit",
) -> WorkAccess:
    """Build access for pure service tests and non-DB authorization paths."""

    return WorkAccess(
        company_id=company_id,
        user_id=user_id,
        level=level,
        capabilities=frozenset(capabilities),
        source=source,
    )
