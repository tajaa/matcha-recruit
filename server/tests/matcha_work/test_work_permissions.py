"""Pure and fake-connection tests for company-scoped Work access."""

from uuid import uuid4

import pytest

from app.core.models.auth import CurrentUser
from app.matcha.services.matcha_work.work_permissions import (
    WorkCapability,
    WorkPermissionDenied,
    access_from_capabilities,
    assert_work_capability,
    default_access_for_membership,
    effective_access,
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
async def test_terminated_employee_does_not_get_employee_default():
    company_id = uuid4()

    class TerminatedEmployeeConn(FakeConn):
        async def fetchval(self, query, *args):
            if "FROM employees" in query:
                assert "termination_date IS NULL" in query
                return None
            return await super().fetchval(query, *args)

    access = await resolve_work_access(
        TerminatedEmployeeConn(),
        user=user("employee"),
        company_id=company_id,
    )

    assert access.level == "guest"
    assert access.source == "external_default"


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
async def test_explicit_grant_short_circuits_membership_lookups():
    class ExplicitOnlyConn(FakeConn):
        async def fetchval(self, query, *args):
            if "FROM clients" in query or "FROM employees" in query:
                raise AssertionError("membership lookup should be skipped")
            return await super().fetchval(query, *args)

    actor = user("employee")
    access = await resolve_work_access(
        ExplicitOnlyConn(explicit="operator"),
        user=actor,
        company_id=uuid4(),
    )

    assert access.level == "operator"
    assert access.source == "explicit"


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


@pytest.mark.parametrize(
    ("owner", "client", "employee", "expected_level", "expected_source"),
    [
        (True, False, False, "admin", "company_owner"),
        (False, True, False, "operator", "client_default"),
        (False, False, True, "member", "employee_default"),
        (False, False, False, "guest", "external_default"),
    ],
)
def test_default_access_for_membership(owner, client, employee, expected_level, expected_source):
    assert default_access_for_membership(
        is_company_owner=owner,
        is_company_client=client,
        is_company_employee=employee,
    ) == (expected_level, expected_source)


def test_effective_explicit_grant_overrides_membership_default():
    access = effective_access(
        company_id=uuid4(),
        user_id=uuid4(),
        user_role="employee",
        explicit_level="reviewer",
        is_company_employee=True,
    )
    assert access.level == "reviewer"
    assert access.source == "explicit"
    assert access.allows(WorkCapability.SENSITIVE_RECORD_READ)
    assert not access.allows(WorkCapability.ACTION_EXECUTE)


def test_owner_outranks_explicit_grant():
    access = effective_access(
        company_id=uuid4(),
        user_id=uuid4(),
        user_role="client",
        explicit_level="member",
        is_company_owner=True,
    )

    assert access.level == "admin"
    assert access.source == "company_owner"


def test_platform_admin_is_immutable_admin_access():
    access = effective_access(
        company_id=uuid4(),
        user_id=uuid4(),
        user_role="admin",
        explicit_level=None,
        is_platform_admin=True,
    )
    assert access.level == "admin"
    assert access.source == "platform_admin"
    assert access.allows(WorkCapability.PERMISSIONS_MANAGE)
