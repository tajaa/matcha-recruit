from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.work_permissions import WorkCapability
from app.matcha.services.ops.permissions import (
    OpsAccess,
    OpsCapability,
    OpsPermissionDenied,
    assert_ops_capability,
    can_revoke_ops_permission,
)


def _access(level: str) -> OpsAccess:
    from app.matcha.services.ops.permissions import _LEVEL_CAPABILITIES

    return OpsAccess(
        company_id=uuid4(),
        user_id=uuid4(),
        level=level,
        capabilities=_LEVEL_CAPABILITIES[level],
        source="explicit",
    )


def test_ops_capabilities_are_not_work_enum_members():
    assert OpsCapability.EVENT_REVIEW.value == WorkCapability.EVENT_REVIEW.value
    assert OpsCapability.EVENT_REVIEW is not WorkCapability.EVENT_REVIEW


def test_reviewer_can_review_but_not_promote():
    access = _access("reviewer")
    assert access.allows(OpsCapability.EVENT_REVIEW)
    assert not access.allows(OpsCapability.EVENT_PROMOTE)


def test_ops_permission_denied_is_independent():
    with pytest.raises(OpsPermissionDenied):
        assert_ops_capability(_access("member"), OpsCapability.EVENT_REVIEW)


def test_ops_admin_can_manage_permissions():
    assert _access("admin").allows(OpsCapability.PERMISSIONS_MANAGE)


def test_non_platform_admin_cannot_revoke_own_permission():
    user_id = uuid4()
    assert not can_revoke_ops_permission(
        actor_user_id=user_id,
        target_user_id=user_id,
        source="explicit",
    )


def test_platform_admin_can_revoke_own_permission():
    user_id = uuid4()
    assert can_revoke_ops_permission(
        actor_user_id=user_id,
        target_user_id=user_id,
        source="platform_admin",
    )
