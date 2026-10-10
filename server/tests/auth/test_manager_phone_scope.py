"""A business admin's Matcha Schedule token reaches the schedule, nothing else."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.services import auth, mobile_scope, session_tokens


def _settings():
    return SimpleNamespace(
        jwt_secret_key="test-secret",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=15,
        jwt_refresh_token_expire_days=7,
        jwt_refresh_idle_expire_minutes=30,
        jwt_session_absolute_expire_hours=12,
    )


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    for module in (auth, session_tokens):
        monkeypatch.setattr(module, "get_settings", _settings)


def _token(role, *, phone=True):
    claims = {"sid": str(uuid4()), "cl": "ios_schedule"} if phone else None
    return "Bearer " + auth.create_access_token(uuid4(), "x@example.com", role, extra_claims=claims)


THREAD = str(uuid4())


@pytest.mark.parametrize(("method", "path", "allowed"), [
    ("GET", "/api/auth/me", True),
    ("POST", "/api/auth/logout", False),
    ("POST", "/api/push/register", True),
    ("POST", "/api/push/unregister", True),
    ("GET", "/api/locations", True),
    ("GET", "/api/employee-schedule/week", True),
    ("POST", "/api/employee-schedule/requests/abc/review", True),
    ("DELETE", "/api/employee-schedule/shifts/abc", True),
    ("GET", "/api/employee-schedule", False),
    ("GET", "/api/inbox/conversations", True),
    ("GET", "/api/matcha-work/notifications/unread-count", True),
    ("POST", f"/api/matcha-work/threads/{THREAD}/messages/stream", True),
    ("POST", f"/api/matcha-work/threads/{THREAD}/messages", False),
    ("GET", f"/api/matcha-work/threads/{THREAD}", False),
    ("GET", "/api/employees/pto/requests", True),
    ("PATCH", f"/api/employees/pto/requests/{THREAD}", True),
    ("DELETE", f"/api/employees/pto/requests/{THREAD}", False),
    ("GET", "/api/employees", False),
    ("GET", "/api/employees/pto/summary", False),
    ("GET", "/api/ir/incidents", False),
    ("POST", "/api/checkout", False),
])
def test_allowlist(method, path, allowed):
    assert mobile_scope.manager_phone_path_allowed(method, path) is allowed


def test_only_a_business_phone_token_is_held():
    assert mobile_scope.is_business_phone_token(_token("client"))
    assert not mobile_scope.is_business_phone_token(_token("employee"))
    assert not mobile_scope.is_business_phone_token(_token("client", phone=False))
    assert not mobile_scope.is_business_phone_token("Bearer not-a-jwt")
    assert not mobile_scope.is_business_phone_token("Basic abc")
    assert not mobile_scope.is_business_phone_token(None)


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(mobile_scope.ManagerPhoneScopeMiddleware)

    @app.get("/api/employees")
    async def employees():
        return {"ok": True}

    @app.get("/api/employee-schedule/week")
    async def week():
        return {"ok": True}

    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(("authorization", "path", "status"), [
    (lambda: _token("client"), "/api/employees", 403),
    (lambda: _token("client"), "/api/employee-schedule/week", 200),
    (lambda: _token("employee"), "/api/employees", 200),
    (lambda: _token("client", phone=False), "/api/employees", 200),
    (lambda: None, "/api/employees", 200),
])
def test_middleware(client, authorization, path, status):
    value = authorization()
    headers = {"Authorization": value} if value else {}
    response = client.get(path, headers=headers)
    assert response.status_code == status
    if status == 403:
        assert response.json() == {"detail": mobile_scope.REFUSAL}


def test_preflight_is_never_held(client):
    response = client.options("/api/employees", headers={"Authorization": _token("client")})
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_a_phone_session_only_streams_to_the_schedule_assistant(monkeypatch):
    from app.matcha.models.matcha_work.matcha_work import SendMessageRequest
    from app.matcha.routes.matcha_work import messaging

    company_id = uuid4()
    monkeypatch.setattr(messaging, "get_client_company_id", AsyncMock(return_value=company_id))
    monkeypatch.setattr(messaging.doc_svc, "get_thread", AsyncMock(return_value={
        "surface": None, "status": "active", "company_id": company_id,
    }))
    user = SimpleNamespace(id=uuid4(), role="client", device_session_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        await messaging.send_message_stream(uuid4(), SendMessageRequest(content="hi"), user)
    assert exc.value.status_code == 403
    assert "schedule assistant" in exc.value.detail
