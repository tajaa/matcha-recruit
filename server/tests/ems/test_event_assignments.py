"""Pure authorization checks for event-to-channel assignments."""

from uuid import uuid4

from app.matcha.services.ems.event_assignments import may_complete_event_assignment
from app.matcha.services.matcha_work.work_permissions import access_from_capabilities, WorkCapability


def test_assignee_can_complete_without_sensitive_event_access():
    assignee = uuid4()
    access = access_from_capabilities(
        company_id=uuid4(),
        user_id=assignee,
        level="member",
        capabilities={WorkCapability.EVENT_CONFIRM_OWN},
    )
    assert may_complete_event_assignment(
        assignee_user_id=assignee,
        actor_user_id=assignee,
        access=access,
    )


def test_event_manager_can_complete_for_assignee():
    manager = uuid4()
    access = access_from_capabilities(
        company_id=uuid4(),
        user_id=manager,
        level="reviewer",
        capabilities={WorkCapability.EVENT_ASSIGN},
    )
    assert may_complete_event_assignment(
        assignee_user_id=uuid4(),
        actor_user_id=manager,
        access=access,
    )


def test_unrelated_member_cannot_complete_assignment():
    access = access_from_capabilities(
        company_id=uuid4(),
        user_id=uuid4(),
        level="member",
        capabilities={WorkCapability.EVENT_CONFIRM_OWN},
    )
    assert not may_complete_event_assignment(
        assignee_user_id=uuid4(),
        actor_user_id=access.user_id,
        access=access,
    )
