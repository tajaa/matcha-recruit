from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.work_permissions import WorkCapability
from app.matcha.services.ops.permissions import (
    OpsAccess,
    OpsCapability,
    OpsPermissionDenied,
    assert_ops_capability,
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
