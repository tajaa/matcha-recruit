"""Pure and fake-connection tests for company-scoped Work access."""

from uuid import uuid4

import pytest

from app.core.models.auth import CurrentUser
from app.matcha.services.matcha_work.work_permissions import (
    WorkCapability,
    WorkPermissionDenied,
    access_from_capabilities,
    assert_work_capability,
    resolve_work_access,
)


class FakeConn:
    def __init__(self, *, explicit=None, owner_id=None, client_company_id=None, employee_company_id=None):
        self.explicit = explicit
        self.owner_id = owner_id
        self.client_company_id = client_company_id
        self.employee_company_id = employee_company_id

    async def fetchval(self, query, *args):
        if "FROM mw_work_permissions" in query:
            return self.explicit
        if "SELECT owner_id" in query:
            return self.owner_id
        if "FROM clients" in query:
            return self.client_company_id
        if "FROM employees" in query:
            return self.employee_company_id
        raise AssertionError(f"Unexpected query: {query}")


def user(role="employee"):
    return CurrentUser(id=uuid4(), email="person@example.com", role=role)


@pytest.mark.asyncio
async def test_owner_resolves_to_admin():
    actor = user("employee")
    company_id = uuid4()
    access = await resolve_work_access(
        FakeConn(owner_id=actor.id), user=actor, company_id=company_id
    )
    assert access.level == "admin"
    assert access.source == "company_owner"
    assert access.allows(WorkCapability.ACTION_EXECUTE)


@pytest.mark.asyncio
async def test_same_company_client_defaults_to_operator():
    actor = user("client")
    company_id = uuid4()
    access = await resolve_work_access(
        FakeConn(client_company_id=company_id), user=actor, company_id=company_id
    )
    assert access.level == "operator"
    assert access.allows(WorkCapability.ACTION_EXECUTE)


@pytest.mark.asyncio
async def test_same_company_employee_defaults_to_member():
    actor = user("employee")
    company_id = uuid4()
    access = await resolve_work_access(
        FakeConn(employee_company_id=company_id), user=actor, company_id=company_id
    )
    assert access.level == "member"
    assert access.allows(WorkCapability.ACTION_PROPOSE)
    assert not access.allows(WorkCapability.ACTION_EXECUTE)


@pytest.mark.asyncio
async def test_explicit_grant_overrides_home_company_role():
    actor = user("employee")
    company_id = uuid4()
    access = await resolve_work_access(
        FakeConn(explicit="reviewer", employee_company_id=company_id),
        user=actor,
        company_id=company_id,
    )
    assert access.level == "reviewer"
    assert access.source == "explicit"
    assert access.allows(WorkCapability.EVENT_RESOLVE)
    assert access.allows(WorkCapability.EVENT_ASSIGN)
    assert not access.allows(WorkCapability.ACTION_EXECUTE)


@pytest.mark.asyncio
async def test_external_collaborator_is_guest_even_if_global_client():
    actor = user("client")
    access = await resolve_work_access(
        FakeConn(), user=actor, company_id=uuid4()
    )
    assert access.level == "guest"
    assert not access.capabilities


def test_assert_work_capability_raises_for_member_execution():
    access = access_from_capabilities(
        company_id=uuid4(),
        user_id=uuid4(),
        level="member",
        capabilities={WorkCapability.ACTION_PROPOSE},
    )
    with pytest.raises(WorkPermissionDenied) as exc:
        assert_work_capability(access, WorkCapability.ACTION_EXECUTE)
    assert exc.value.capability is WorkCapability.ACTION_EXECUTE


def test_member_cannot_assign_events():
    access = access_from_capabilities(
        company_id=uuid4(),
        user_id=uuid4(),
        level="member",
        capabilities={WorkCapability.EVENT_CONFIRM_OWN},
    )
    with pytest.raises(WorkPermissionDenied) as exc:
        assert_work_capability(access, WorkCapability.EVENT_ASSIGN)
    assert exc.value.capability is WorkCapability.EVENT_ASSIGN
