"""Pure authorization checks for event-to-channel assignments."""

from uuid import uuid4

from app.matcha.services.ems.event_assignments import (
    assignment_channel_scope_allowed,
    may_complete_event_assignment,
)
from app.matcha.services.ops.permissions import OpsCapability, OpsAccess


def test_assignee_can_complete_without_sensitive_event_access():
    assignee = uuid4()
    access = OpsAccess(
        company_id=uuid4(),
        user_id=assignee,
        level="member",
        capabilities=frozenset({OpsCapability.EVENT_CONFIRM_OWN}),
        source="explicit",
    )
    assert may_complete_event_assignment(
        assignee_user_id=assignee,
        actor_user_id=assignee,
        access=access,
    )


def test_event_manager_can_complete_for_assignee():
    manager = uuid4()
    access = OpsAccess(
        company_id=uuid4(),
        user_id=manager,
        level="reviewer",
        capabilities=frozenset({OpsCapability.EVENT_ASSIGN}),
        source="explicit",
    )
    assert may_complete_event_assignment(
        assignee_user_id=uuid4(),
        actor_user_id=manager,
        access=access,
    )


def test_unrelated_member_cannot_complete_assignment():
    access = OpsAccess(
        company_id=uuid4(),
        user_id=uuid4(),
        level="member",
        capabilities=frozenset({OpsCapability.EVENT_CONFIRM_OWN}),
        source="explicit",
    )
    assert not may_complete_event_assignment(
        assignee_user_id=uuid4(),
        actor_user_id=access.user_id,
        access=access,
    )


def test_assignments_only_target_operations_channels():
    assert assignment_channel_scope_allowed(None)
    assert assignment_channel_scope_allowed("operations")
    assert not assignment_channel_scope_allowed("project_discussion")
    assert not assignment_channel_scope_allowed("community")
