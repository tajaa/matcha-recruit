"""The REST layer: personal-only, owner-scoped, thin over the service."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.models.auth import CurrentUser
from app.matcha.models.matcha_work.job_search import JobSearchCreate, JobWeights, LeadPatch
from app.matcha.routes.matcha_work import job_search as routes
from app.matcha.routes.matcha_work.assistant import require_personal_workspace

USER = CurrentUser(id=uuid4(), email="owner@example.test", role="client")
SID, LID, CID = uuid4(), uuid4(), uuid4()


@pytest.mark.asyncio
async def test_routes_pass_the_caller(monkeypatch):
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=CID))
    for name in ("list_searches", "get_search", "status_view", "get_lead", "patch_lead",
                 "update_weights", "cancel_search", "delete_search"):
        monkeypatch.setattr(routes.service, name, AsyncMock(return_value={"ok": name}))
    monkeypatch.setattr(routes.enqueue, "create_search", AsyncMock(return_value={"id": "new"}))
    monkeypatch.setattr(routes.enqueue, "consent_granted", AsyncMock(return_value=False))
    monkeypatch.setattr(routes.quota, "job_search_usage", AsyncMock(return_value={"limit": 4}))

    listed = await routes.list_job_searches(USER)
    assert listed["usage"] == {"limit": 4} and listed["available"] is True
    assert listed["consent"]["granted"] is False and listed["consent"]["disclosure"]["version"] == "jobs-2"
    routes.service.list_searches.assert_awaited_once_with(USER.id, CID)

    body = JobSearchCreate(request_id=uuid4(), ask="COO roles across the US")
    assert await routes.create_job_search(body, USER) == {"id": "new"}
    assert routes.enqueue.create_search.await_args.args == (USER, CID, body)

    await routes.get_job_search(SID, USER)
    await routes.job_search_status(SID, USER)
    await routes.get_job_lead(SID, LID, USER)
    await routes.update_job_lead(SID, LID, LeadPatch(user_state="saved"), USER)
    await routes.rerank_job_search(SID, JobWeights(), USER)
    await routes.cancel_job_search(SID, USER)
    await routes.delete_job_search(SID, USER)
    for name in ("get_search", "status_view", "cancel_search", "delete_search"):
        assert getattr(routes.service, name).await_args.args == (SID, USER.id)
    assert routes.service.get_lead.await_args.args == (SID, LID, USER.id)
    assert routes.service.patch_lead.await_args.args[:3] == (SID, LID, USER.id)


@pytest.mark.asyncio
async def test_errors_and_gates(monkeypatch):
    async def missing():
        raise routes.service.JobSearchError("Job search not found.", 404)

    with pytest.raises(HTTPException) as exc:
        await routes._call(missing())
    assert exc.value.status_code == 404
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await routes.list_job_searches(USER)
    assert exc.value.status_code == 400
    assert any(d.dependency is require_personal_workspace for d in routes.router.dependencies)
    assert routes.router.prefix == "/job-searches"


def test_request_bodies_are_bounded():
    from pydantic import ValidationError

    from app.matcha.models.matcha_work.job_search import JobCriteria

    criteria = JobCriteria(titles=[" COO ", "coo", "Chief Operating Officer"], currency="usd",
                           exclude_companies=["Acme"], deal_breakers=["no travel"])
    assert criteria.titles == ["COO", "Chief Operating Officer"] and criteria.currency == "USD"
    for bad in (dict(currency="U$D"), dict(titles=["x"] * 9), dict(remote="sometimes"), dict(base_floor=-1)):
        with pytest.raises(ValidationError):
            JobCriteria(**bad)
    with pytest.raises(ValidationError):
        JobWeights(base=0, bonus=0, equity=0, fit=0)
    with pytest.raises(ValidationError):
        JobSearchCreate(request_id=uuid4(), ask="x")
    with pytest.raises(ValidationError):
        JobSearchCreate(request_id=uuid4(), ask="COO roles", surprise=True)


@pytest.mark.asyncio
async def test_form_setup_does_not_load_search_history(monkeypatch):
    history = AsyncMock()
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=CID))
    monkeypatch.setattr(routes.service, "list_searches", history)
    monkeypatch.setattr(routes.quota, "job_search_usage", AsyncMock(return_value={"remaining": 3}))
    monkeypatch.setattr(routes.enqueue, "consent_granted", AsyncMock(return_value=False))
    result = await routes.job_search_setup(USER)
    assert result["usage"] == {"remaining": 3} and result["consent"]["granted"] is False
    assert "searches" not in result and result["available"] is True
    history.assert_not_awaited()


@pytest.mark.asyncio
async def test_tailoring_passes_the_caller_and_maps_refusals(monkeypatch):
    from app.matcha.services.matcha_work.job_search.service import JobSearchError

    monkeypatch.setattr(routes.tailor, "request", AsyncMock(return_value={"resume_status": "queued"}))
    assert await routes.tailor_job_resume(SID, LID, USER) == {"resume_status": "queued"}
    assert routes.tailor.request.await_args.args == (USER, SID, LID)
    refusal = {"code": "resume_required", "message": "Add your résumé first."}
    monkeypatch.setattr(routes.tailor, "request", AsyncMock(side_effect=JobSearchError("x", 422, refusal)))
    with pytest.raises(HTTPException) as err:
        await routes.tailor_job_resume(SID, LID, USER)
    assert err.value.status_code == 422 and err.value.detail == refusal
