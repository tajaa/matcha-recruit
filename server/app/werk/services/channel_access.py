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
    # One person's private conversation with Espresso (the assistant). Exactly
    # one member, its owner; nobody else can be added.
    ASSISTANT = "assistant"


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
    user_id: UUID | None = None
    assistant_user_id: UUID | None = None
    is_personal: bool = False


def capability_allowed(
    *,
    scope: ChannelScope,
    features: Mapping[str, bool],
    capability: ChannelCapability,
    is_platform_admin: bool = False,
    user_id: UUID | None = None,
    assistant_user_id: UUID | None = None,
    is_personal: bool = False,
) -> bool:
    if scope is ChannelScope.ASSISTANT:
        from app.matcha.services.matcha_work.agent_runtime.eligibility import assistant_available

        # Decided BEFORE the platform-admin bypass, on purpose: this
        # conversation can hold a person's email and calendar, so it is its
        # owner's alone. Chat only, no calls, no automation, no managing.
        return (
            capability is ChannelCapability.CHAT
            and user_id is not None
            and user_id == assistant_user_id
            and assistant_available(is_personal=is_personal, features=features)
        )
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
               COALESCE(comp.is_personal, false) AS is_personal,
               ch.assistant_user_id,
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
        user_id=user_id,
        assistant_user_id=row.get("assistant_user_id"),
        is_personal=bool(row.get("is_personal")),
    )


class ChannelIsPrivateConversation(PermissionError):
    pass


def refuse_membership_change(access: ChannelAccess) -> None:
    """A private conversation with Espresso has one member and stays that way:
    no joining, inviting, renaming, archiving, deleting, handing over or
    charging for it."""
    if access.scope is ChannelScope.ASSISTANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your conversation with Espresso is private and can't be changed.",
        )


def assert_channel_capability(access: ChannelAccess, capability: ChannelCapability) -> None:
    if not capability_allowed(
        scope=access.scope,
        features=access.features,
        capability=capability,
        is_platform_admin=access.is_platform_admin,
        user_id=access.user_id,
        assistant_user_id=access.assistant_user_id,
        is_personal=access.is_personal,
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
