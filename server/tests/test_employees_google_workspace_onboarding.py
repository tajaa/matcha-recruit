import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import BackgroundTasks

from app.core.models.auth import CurrentUser
from app.matcha.routes import employees as employees_routes


class _FakeConn:
    def __init__(self, *, integration_row=None):
        self.integration_row = integration_row
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.employee_id = uuid4()

    async def fetchval(self, query, *args):
        if "SELECT id FROM employees WHERE org_id = $1 AND email = $2" in query:
            return None
        return None

    async def fetchrow(self, query, *args):
        if "INSERT INTO employees" in query:
            (
                company_id,
                email,
                personal_email,
                first_name,
                last_name,
                work_state,
                employment_type,
                start_date,
                manager_id,
            ) = args
            return {
                "id": self.employee_id,
                "org_id": company_id,
                "email": email,
                "personal_email": personal_email,
                "first_name": first_name,
                "last_name": last_name,
                "work_state": work_state,
                "employment_type": employment_type,
                "start_date": start_date,
                "termination_date": None,
                "manager_id": manager_id,
                "user_id": None,
                "phone": None,
                "address": None,
                "emergency_contact": None,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        if "FROM integration_connections" in query:
            return self.integration_row
        return None


class _FakeConnContext:
    def __init__(self, conn: _FakeConn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _set_fake_connection(monkeypatch, conn: _FakeConn):
    monkeypatch.setattr(employees_routes, "get_connection", lambda: _FakeConnContext(conn))


def test_create_employee_queues_google_onboarding_when_connected_and_enabled(monkeypatch):
    company_id = uuid4()
    hr_user_id = uuid4()
    conn = _FakeConn(
        integration_row={
            "config": {
                "auto_provision_on_employee_create": True,
            }
        }
    )
    _set_fake_connection(monkeypatch, conn)

    async def _fake_get_client_company_id(_current_user):
        return company_id

    monkeypatch.setattr(employees_routes, "get_client_company_id", _fake_get_client_company_id)

    request = employees_routes.EmployeeCreateRequest(
        work_email="new.hire@itsmatcha.net",
        personal_email="new.hire@gmail.com",
        first_name="New",
        last_name="Hire",
        work_state="CA",
        employment_type="full_time",
        start_date="2026-02-17",
    )
    background_tasks = BackgroundTasks()
    current_user = CurrentUser(id=hr_user_id, email="hr-admin@itsmatcha.net", role="client")

    response = asyncio.run(employees_routes.create_employee(request, background_tasks, current_user))

    assert response.id == conn.employee_id
    assert response.email == "new.hire@itsmatcha.net"
    assert response.work_email == "new.hire@itsmatcha.net"
    assert response.personal_email == "new.hire@gmail.com"
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func == employees_routes._run_google_workspace_auto_provisioning
    assert task.kwargs["company_id"] == company_id
    assert task.kwargs["employee_id"] == conn.employee_id
    assert task.kwargs["triggered_by"] == hr_user_id


def test_create_employee_does_not_queue_google_onboarding_when_auto_provision_disabled(monkeypatch):
    company_id = uuid4()
    conn = _FakeConn(
        integration_row={
            "config": {
                "auto_provision_on_employee_create": False,
            }
        }
    )
    _set_fake_connection(monkeypatch, conn)

    async def _fake_get_client_company_id(_current_user):
        return company_id

    monkeypatch.setattr(employees_routes, "get_client_company_id", _fake_get_client_company_id)

    request = employees_routes.EmployeeCreateRequest(
        email="manual.only@itsmatcha.net",
        first_name="Manual",
        last_name="Only",
        start_date="2026-02-17",
    )
    background_tasks = BackgroundTasks()
    current_user = CurrentUser(id=uuid4(), email="hr-admin@itsmatcha.net", role="client")

    response = asyncio.run(employees_routes.create_employee(request, background_tasks, current_user))

    assert response.id == conn.employee_id
    assert len(background_tasks.tasks) == 0
