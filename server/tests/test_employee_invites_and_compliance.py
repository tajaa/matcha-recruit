import asyncio
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

multipart_module = types.ModuleType("multipart")
multipart_module.__version__ = "0.0"
multipart_submodule = types.ModuleType("multipart.multipart")
multipart_submodule.parse_options_header = lambda value: (value, {})
sys.modules.setdefault("multipart", multipart_module)
sys.modules.setdefault("multipart.multipart", multipart_submodule)

from app.core.models.auth import CurrentUser

compliance_service_module = types.ModuleType("app.core.services.compliance_service")


async def _noop_ensure_location_for_employee(
    conn,
    company_id,
    work_city,
    work_state,
    background_tasks=None,
    work_zip=None,
):
    return None


compliance_service_module.ensure_location_for_employee = _noop_ensure_location_for_employee
sys.modules.setdefault("app.core.services.compliance_service", compliance_service_module)

onboarding_orchestrator_module = types.ModuleType("app.matcha.services.onboarding_orchestrator")
onboarding_orchestrator_module.PROVIDER_GOOGLE_WORKSPACE = "google_workspace"
onboarding_orchestrator_module.PROVIDER_SLACK = "slack"


async def _noop_google_workspace_onboarding(*args, **kwargs):
    return None


async def _noop_slack_onboarding(*args, **kwargs):
    return None


onboarding_orchestrator_module.start_google_workspace_onboarding = _noop_google_workspace_onboarding
onboarding_orchestrator_module.start_slack_onboarding = _noop_slack_onboarding
sys.modules.setdefault("app.matcha.services.onboarding_orchestrator", onboarding_orchestrator_module)

routes_package = types.ModuleType("app.matcha.routes")
routes_package.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "matcha" / "routes")]
sys.modules.setdefault("app.matcha.routes", routes_package)

employees_spec = importlib.util.spec_from_file_location(
    "app.matcha.routes.employees",
    Path(__file__).resolve().parents[1] / "app" / "matcha" / "routes" / "employees.py",
)
employees_routes = importlib.util.module_from_spec(employees_spec)
sys.modules["app.matcha.routes.employees"] = employees_routes
assert employees_spec.loader is not None
employees_spec.loader.exec_module(employees_routes)


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _InviteConn:
    def __init__(self):
        self.employee_id = uuid4()
        self.invitation_id = uuid4()
        self.execute_calls: list[tuple[str, tuple]] = []

    def transaction(self):
        return _FakeTransaction()

    async def fetchrow(self, query, *args):
        if "SELECT * FROM employees" in query:
            return {
                "id": self.employee_id,
                "email": "invitee@itsmatcha.net",
                "first_name": "Casey",
                "last_name": "Jones",
                "work_state": "CA",
                "work_city": "Los Angeles",
                "user_id": None,
            }
        if "INSERT INTO employee_invitations" in query:
            return {
                "id": self.invitation_id,
                "employee_id": self.employee_id,
                "token": "invite-token",
                "status": "pending",
                "expires_at": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
            }
        if "SELECT name FROM companies" in query:
            return {"name": "Matcha"}
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "UPDATE 1"


class _CreateConn:
    def __init__(self):
        self.employee_id = uuid4()
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    async def fetchval(self, query, *args):
        if "SELECT id FROM employees WHERE org_id = $1 AND email = $2" in query:
            return None
        raise AssertionError(f"Unexpected fetchval query: {query}")

    async def fetchrow(self, query, *args):
        if "INSERT INTO employees" in query:
            return {
                "id": self.employee_id,
                "org_id": args[0],
                "email": args[1],
                "personal_email": args[2],
                "first_name": args[3],
                "last_name": args[4],
                "work_state": args[5],
                "employment_type": args[6],
                "start_date": args[7],
                "address": args[8],
                "manager_id": args[9],
                "pay_classification": args[10],
                "pay_rate": args[11],
                "work_city": args[12],
                "termination_date": None,
                "user_id": None,
                "phone": None,
                "emergency_contact": None,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        if "SELECT auto_send_invitation" in query:
            return None
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def fetch(self, query, *args):
        if "FROM onboarding_tasks" in query:
            return []
        if "FROM integration_connections" in query:
            return []
        raise AssertionError(f"Unexpected fetch query: {query}")


class _FakeConnContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _FakeEmailService:
    def __init__(self, *, sent: bool):
        self.sent = sent

    async def send_employee_invitation_email(self, **kwargs):
        return self.sent


def test_send_single_invitation_cancels_pending_invitation_when_email_send_fails(monkeypatch):
    conn = _InviteConn()
    company_id = uuid4()
    invited_by = uuid4()

    monkeypatch.setattr(
        employees_routes,
        "_sync_employee_location_for_compliance",
        lambda *args, **kwargs: asyncio.sleep(0, result=None),
    )
    monkeypatch.setattr(
        employees_routes,
        "get_email_service",
        lambda: _FakeEmailService(sent=False),
    )

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            employees_routes.send_single_invitation(
                conn.employee_id,
                company_id,
                invited_by,
                conn,
            )
        )

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail == employees_routes.INVITATION_SEND_FAILED_DETAIL
    assert len(conn.execute_calls) == 2
    assert "WHERE employee_id = $1 AND status = 'pending'" in conn.execute_calls[0][0]
    assert conn.execute_calls[0][1] == (conn.employee_id,)
    assert "WHERE id = $1" in conn.execute_calls[1][0]
    assert conn.execute_calls[1][1] == (conn.invitation_id,)


def test_sync_employee_location_for_compliance_normalizes_location(monkeypatch):
    calls = {}
    expected_location_id = uuid4()

    async def _fake_ensure_location_for_employee(
        conn,
        company_id,
        work_city,
        work_state,
        background_tasks=None,
        work_zip=None,
    ):
        calls["company_id"] = company_id
        calls["work_city"] = work_city
        calls["work_state"] = work_state
        calls["background_tasks"] = background_tasks
        return expected_location_id

    monkeypatch.setattr(
        employees_routes,
        "ensure_location_for_employee",
        _fake_ensure_location_for_employee,
    )

    background_tasks = BackgroundTasks()
    company_id = uuid4()
    employee_id = uuid4()

    result = asyncio.run(
        employees_routes._sync_employee_location_for_compliance(
            object(),
            company_id=company_id,
            employee_id=employee_id,
            work_state=" ca ",
            work_city=" San Francisco ",
            background_tasks=background_tasks,
        )
    )

    assert result == expected_location_id
    assert calls == {
        "company_id": company_id,
        "work_city": "San Francisco",
        "work_state": "CA",
        "background_tasks": background_tasks,
    }


def test_create_employee_syncs_compliance_location(monkeypatch):
    conn = _CreateConn()
    company_id = uuid4()
    current_user = CurrentUser(id=uuid4(), email="hr-admin@itsmatcha.net", role="client")
    background_tasks = BackgroundTasks()
    sync_calls: list[dict] = []

    async def _fake_get_client_company_id(_current_user):
        return company_id

    async def _fake_comp_fields(_conn):
        return True

    async def _fake_org_fields(_conn):
        return False

    async def _fake_sync_employee_location_for_compliance(
        conn,
        *,
        company_id,
        employee_id,
        work_state,
        work_city,
        background_tasks=None,
    ):
        sync_calls.append(
            {
                "company_id": company_id,
                "employee_id": employee_id,
                "work_state": work_state,
                "work_city": work_city,
                "background_tasks": background_tasks,
            }
        )
        return uuid4()

    monkeypatch.setattr(employees_routes, "get_connection", lambda: _FakeConnContext(conn))
    monkeypatch.setattr(employees_routes, "get_client_company_id", _fake_get_client_company_id)
    monkeypatch.setattr(employees_routes, "_employee_compensation_fields_available", _fake_comp_fields)
    monkeypatch.setattr(employees_routes, "_employee_org_fields_available", _fake_org_fields)
    monkeypatch.setattr(
        employees_routes,
        "_sync_employee_location_for_compliance",
        _fake_sync_employee_location_for_compliance,
    )

    request = employees_routes.EmployeeCreateRequest(
        work_email="new.hire@itsmatcha.net",
        personal_email="new.hire@gmail.com",
        first_name="New",
        last_name="Hire",
        work_state="CA",
        work_city="San Francisco",
        employment_type="full_time",
        start_date="2026-03-08",
    )

    response = asyncio.run(employees_routes.create_employee(request, background_tasks, current_user))

    assert response.id == conn.employee_id
    assert sync_calls == [
        {
            "company_id": company_id,
            "employee_id": conn.employee_id,
            "work_state": "CA",
            "work_city": "San Francisco",
            "background_tasks": background_tasks,
        }
    ]
