"""The `/assistant/sessions` route must refuse before creating a session when
`huume`/`matcha_work` are off — the mount only gates `employee_schedule`, and a
turn later fails deep inside the Huume dispatch with no session-create signal
at all (2026-08-26 incident: PO Coffee got a working session and a chat panel
that failed on every message)."""

import asyncio
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.routes.employee_schedule import assistant


def _run(coro):
    return asyncio.run(coro)


def _user():
    return SimpleNamespace(id=uuid4(), role="client")


@pytest.mark.parametrize("missing", ["huume", "matcha_work"])
def test_session_create_refuses_when_a_required_flag_is_off(monkeypatch, missing):
    company_id = uuid4()
    features = {"huume": True, "matcha_work": True, "employee_schedule": True}
    features[missing] = False

    async def fake_require_company_id(_user):
        return company_id

    async def fake_get_company_features(_company_id):
        return features

    async def fake_get_or_create(**_kwargs):
        raise AssertionError("session must not be created when a required flag is off")

    monkeypatch.setattr(assistant, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(assistant, "get_company_features", fake_get_company_features)
    monkeypatch.setattr(assistant, "get_or_create_schedule_assistant_session", fake_get_or_create)

    with pytest.raises(HTTPException) as exc:
        _run(assistant.create_schedule_assistant_session(
            assistant.ScheduleAssistantSessionRequest(location_id=uuid4(), week_start=date(2026, 8, 24)),
            current_user=_user(),
        ))
    assert exc.value.status_code == 403
    assert missing in exc.value.detail


def test_session_create_proceeds_when_both_flags_are_on(monkeypatch):
    company_id = uuid4()
    created = {}

    async def fake_require_company_id(_user):
        return company_id

    async def fake_get_company_features(_company_id):
        return {"huume": True, "matcha_work": True, "employee_schedule": True}

    async def fake_get_or_create(**kwargs):
        created.update(kwargs)
        return {"session_id": str(uuid4())}

    monkeypatch.setattr(assistant, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(assistant, "get_company_features", fake_get_company_features)
    monkeypatch.setattr(assistant, "get_or_create_schedule_assistant_session", fake_get_or_create)

    result = _run(assistant.create_schedule_assistant_session(
        assistant.ScheduleAssistantSessionRequest(location_id=uuid4(), week_start=date(2026, 8, 24)),
        current_user=_user(),
    ))
    assert "session_id" in result
    assert created["company_id"] == company_id


def test_adopt_proposal_route_requires_huume_and_hands_the_scope_to_the_service(monkeypatch):
    company_id, user = uuid4(), _user()
    session_id, proposal_id = uuid4(), uuid4()
    adopted = {}

    async def fake_require_company_id(_user):
        return company_id

    async def fake_get_company_features(_company_id):
        return {"huume": True, "matcha_work": True, "employee_schedule": True}

    async def fake_adopt(**kwargs):
        adopted.update(kwargs)
        return {"current_state": {"huume_action": {"type": "schedule_change"}}, "version": 2, "confirm_id": "ab12cd34"}

    monkeypatch.setattr(assistant, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(assistant, "get_company_features", fake_get_company_features)
    monkeypatch.setattr(assistant, "adopt_editor_proposal", fake_adopt)

    result = _run(assistant.adopt_schedule_proposal(
        session_id, assistant.AdoptProposalRequest(proposal_id=proposal_id), current_user=user,
    ))
    assert result["confirm_id"] == "ab12cd34"
    assert adopted == {"company_id": company_id, "user_id": user.id, "actor_role": "client",
                       "session_id": session_id, "proposal_id": proposal_id}


def test_adopt_proposal_route_refuses_when_huume_is_off(monkeypatch):
    async def fake_require_company_id(_user):
        return uuid4()

    async def fake_get_company_features(_company_id):
        return {"huume": False, "matcha_work": True}

    async def must_not_run(**_kwargs):
        raise AssertionError("service must not run without huume")

    monkeypatch.setattr(assistant, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(assistant, "get_company_features", fake_get_company_features)
    monkeypatch.setattr(assistant, "adopt_editor_proposal", must_not_run)
    with pytest.raises(HTTPException) as exc:
        _run(assistant.adopt_schedule_proposal(uuid4(), assistant.AdoptProposalRequest(proposal_id=uuid4()), current_user=_user()))
    assert exc.value.status_code == 403
