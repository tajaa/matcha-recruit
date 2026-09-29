"""`project_service.resolve_project_access` is the one project-access rule:
the REST routes' `_verify_project_access` and the agent-card chat answers
both go through it, so the two can't drift apart."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.routes.matcha_work import _shared
from app.matcha.services.matcha_work import project_service


def _user(role):
    return SimpleNamespace(id=uuid4(), role=role, email="person@example.com")


@pytest.fixture
def svc(monkeypatch):
    mocks = {"company": AsyncMock(return_value=None), "collab": AsyncMock(return_value=None)}
    monkeypatch.setattr(project_service, "get_project", mocks["company"])
    monkeypatch.setattr(project_service, "get_project_as_collaborator", mocks["collab"])
    return mocks


@pytest.mark.asyncio
async def test_admins_reach_a_project_only_as_a_collaborator(svc):
    assert await project_service.resolve_project_access(uuid4(), _user("admin"), company_id=uuid4()) is None
    svc["company"].assert_not_awaited()
    svc["collab"].return_value = ({"id": 1}, "editor")
    assert await project_service.resolve_project_access(uuid4(), _user("admin"), company_id=None) == ({"id": 1}, "editor")


@pytest.mark.asyncio
async def test_company_project_defaults_to_owner(svc):
    svc["company"].return_value = {"project_type": "general"}
    project, role = await project_service.resolve_project_access(uuid4(), _user("client"), company_id=uuid4())
    assert role == "owner" and project["collaborator_role"] == "owner"


@pytest.mark.asyncio
async def test_no_company_skips_the_company_lookup(svc):
    svc["collab"].return_value = ({"project_type": "general"}, "viewer")
    assert (await project_service.resolve_project_access(uuid4(), _user("client"), company_id=None))[1] == "viewer"
    svc["company"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("project_type", ["discipline", "recruiting"])
@pytest.mark.parametrize("path", ["company", "collab"])
async def test_employees_never_reach_hr_sensitive_projects(svc, project_type, path):
    svc[path].return_value = {"project_type": project_type} if path == "company" else ({"project_type": project_type}, "viewer")
    assert await project_service.resolve_project_access(uuid4(), _user("employee"), company_id=uuid4()) is None
    # A client of the same company still can.
    assert await project_service.resolve_project_access(uuid4(), _user("client"), company_id=uuid4()) is not None


@pytest.mark.asyncio
async def test_rest_route_raises_404_through_the_same_rule(monkeypatch):
    seen = {}

    async def resolve(project_id, user, *, company_id):
        seen["company_id"] = company_id
        return None

    company = uuid4()
    monkeypatch.setattr(project_service, "resolve_project_access", resolve)
    monkeypatch.setattr(_shared, "get_client_company_id", AsyncMock(return_value=company))
    with pytest.raises(HTTPException) as exc:
        await _shared._verify_project_access(uuid4(), _user("client"))
    assert exc.value.status_code == 404 and seen["company_id"] == company
    with pytest.raises(HTTPException):
        await _shared._verify_project_access(uuid4(), _user("admin"))
    assert seen["company_id"] is None


def test_guard_still_hides_sensitive_projects_from_employees():
    with pytest.raises(HTTPException) as exc:
        _shared._guard_sensitive_project_type({"project_type": "discipline"}, _user("employee"))
    assert exc.value.status_code == 404
    _shared._guard_sensitive_project_type({"project_type": "discipline"}, _user("client"))
