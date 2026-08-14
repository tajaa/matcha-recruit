"""Channel scope and entitlement checks shared by REST and WebSocket paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping
from uuid import UUID

from fastapi import HTTPException, status

from app.core.feature_flags import merge_company_features


class ChannelScope(StrEnum):
    OPERATIONS = "operations"
    PROJECT_DISCUSSION = "project_discussion"
    COMMUNITY = "community"


class ChannelCapability(StrEnum):
    CHAT = "chat"
    CALL = "call"
    AUTOMATION = "automation"
    MANAGE = "manage"


class ChannelAccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class ChannelAccess:
    channel_id: UUID
    company_id: UUID
    scope: ChannelScope
    features: Mapping[str, bool]
    is_member: bool
    member_role: str | None
    is_platform_admin: bool


def capability_allowed(
    *,
    scope: ChannelScope,
    features: Mapping[str, bool],
    capability: ChannelCapability,
    is_platform_admin: bool = False,
) -> bool:
    if is_platform_admin:
        return True
    if scope is ChannelScope.PROJECT_DISCUSSION:
        return bool(features.get("matcha_work")) if capability is ChannelCapability.CHAT else False
    if scope is ChannelScope.OPERATIONS:
        return bool(features.get("matcha_ops"))
    # Community channels retain the personal/paid channel path and never run
    # company Ops automation.
    return capability is not ChannelCapability.AUTOMATION


async def load_channel_access(
    conn,
    *,
    channel_id: UUID,
    user_id: UUID,
    user_role: str,
) -> ChannelAccess:
    row = await conn.fetchrow(
        """
        SELECT ch.id, ch.company_id, COALESCE(ch.channel_scope, 'operations') AS channel_scope,
               comp.enabled_features, comp.signup_source,
               cm.role AS member_role,
               cm.removed_for_inactivity IS NOT TRUE AS is_member
          FROM channels ch
          JOIN companies comp ON comp.id = ch.company_id
          LEFT JOIN channel_members cm ON cm.channel_id = ch.id AND cm.user_id = $2
         WHERE ch.id = $1
        """,
        channel_id,
        user_id,
    )
    if row is None:
        raise ChannelAccessDenied("Channel not found")
    try:
        scope = ChannelScope(row["channel_scope"])
    except ValueError:
        scope = ChannelScope.OPERATIONS
    return ChannelAccess(
        channel_id=row["id"],
        company_id=row["company_id"],
        scope=scope,
        features=merge_company_features(row["enabled_features"], row["signup_source"]),
        is_member=bool(row["is_member"]),
        member_role=row["member_role"],
        is_platform_admin=user_role == "admin",
    )


def assert_channel_capability(access: ChannelAccess, capability: ChannelCapability) -> None:
    if not capability_allowed(
        scope=access.scope,
        features=access.features,
        capability=capability,
        is_platform_admin=access.is_platform_admin,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"The {access.scope.value} channel is not available for this account",
        )


def ops_automation_allowed(access: ChannelAccess, feature: str) -> bool:
    return (
        access.scope is ChannelScope.OPERATIONS
        and bool(access.features.get("matcha_ops"))
        and bool(access.features.get(feature))
    )


async def channel_ops_automation_enabled(
    conn,
    *,
    channel_id: UUID,
    feature: str,
) -> bool:
    """Background-safe automation gate.

    Re-resolves the channel's scope and the OWNING company's features at reply
    time, so a reply to an already-created automation pill is refused once the
    channel is reclassified (e.g. legacy collab → ``project_discussion``) or the
    tenant's ``matcha_ops``/domain flag is revoked. Never runs Ops automation
    in a project-discussion or community channel.
    """
    row = await conn.fetchrow(
        """
        SELECT COALESCE(ch.channel_scope, 'operations') AS channel_scope,
               comp.enabled_features, comp.signup_source
          FROM channels ch
          JOIN companies comp ON comp.id = ch.company_id
         WHERE ch.id = $1
        """,
        channel_id,
    )
    if not row:
        return False
    try:
        scope = ChannelScope(row["channel_scope"])
    except ValueError:
        scope = ChannelScope.OPERATIONS
    if scope is not ChannelScope.OPERATIONS:
        return False
    features = merge_company_features(row["enabled_features"], row["signup_source"])
    return bool(features.get("matcha_ops")) and bool(features.get(feature))
