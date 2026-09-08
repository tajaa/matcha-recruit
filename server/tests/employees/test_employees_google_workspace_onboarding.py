import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import BackgroundTasks

from app.core.models.auth import CurrentUser

# Patch the module that DEFINES create_employee, not the package facade that
# re-exports it: after the 2026-05-16 employees package split, `get_connection`
# and `get_client_company_id` are resolved in crud.py's globals, so a patch on
# `routes.employees` is never seen by the code under test.
from app.matcha.routes.employees import crud as employees_crud


class _FakeConn:
    """Minimal asyncpg stand-in for the create_employee path.

    Only the queries this test actually cares about are answered; everything
    else returns an empty/None default so the surrounding best-effort blocks
    (credential templates, training rules, onboarding templates) no-op.
    """

    def __init__(self, *, integration_rows=None):
        self.integration_rows = integration_rows or []
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.employee_id = uuid4()

    async def fetchval(self, query, *args):
        # Duplicate-email guard: no existing employee.
        if "SELECT id FROM employees WHERE org_id = $1 AND email = $2" in query:
            return None
        # _column_exists() — report the optional columns as absent so the
        # INSERT takes its narrow, schema-independent shape.
        if "information_schema.columns" in query:
            return False
        return None

    async def fetch(self, query, *args):
        # _employee_compensation_fields_available / _employee_org_fields_available
        if "information_schema.columns" in query:
            return []
        if "FROM integration_connections" in query:
            return self.integration_rows
        return []

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
                address,
                manager_id,
                is_supervisor,
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
                "is_supervisor": is_supervisor,
                "user_id": None,
                "phone": None,
                "address": address,
                "emergency_contact": None,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        return None

    async def execute(self, query, *args):
        return None


class _FakeConnContext:
    def __init__(self, conn: _FakeConn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _google_row(auto_provision: bool):
    return {
        "provider": employees_crud.PROVIDER_GOOGLE_WORKSPACE,
        "config": {"auto_provision_on_employee_create": auto_provision},
    }


def _install_fakes(monkeypatch, conn: _FakeConn, company_id):
    monkeypatch.setattr(employees_crud, "get_connection", lambda: _FakeConnContext(conn))

    async def _fake_get_client_company_id(_current_user):
        return company_id

    monkeypatch.setattr(employees_crud, "get_client_company_id", _fake_get_client_company_id)

    # Compliance-location sync would reach for real location/geocode data; it is
    # not what these tests are pinning.
    async def _fake_sync(conn, **kwargs):
        return None

    monkeypatch.setattr(employees_crud, "_sync_employee_location_for_compliance", _fake_sync)


def _provisioning_tasks(background_tasks: BackgroundTasks):
    return [
        t for t in background_tasks.tasks
        if t.func is employees_crud._run_provisioning_and_notify
    ]


def test_create_employee_queues_google_onboarding_when_connected_and_enabled(monkeypatch):
    company_id = uuid4()
    hr_user_id = uuid4()
    conn = _FakeConn(integration_rows=[_google_row(True)])
    _install_fakes(monkeypatch, conn, company_id)

    request = employees_crud.EmployeeCreateRequest(
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

    response = asyncio.run(
        employees_crud.create_employee(request, background_tasks, current_user)
    )

    assert response.id == conn.employee_id
    assert response.email == "new.hire@itsmatcha.net"
    assert response.work_email == "new.hire@itsmatcha.net"
    assert response.personal_email == "new.hire@gmail.com"

    # Filter rather than count: create_employee also queues unrelated
    # best-effort work (jurisdiction drift, OIG screening).
    tasks = _provisioning_tasks(background_tasks)
    assert len(tasks) == 1
    kwargs = tasks[0].kwargs
    assert kwargs["run_google"] is True
    assert kwargs["run_slack"] is False
    assert kwargs["company_id"] == company_id
    assert kwargs["employee_id"] == conn.employee_id
    assert kwargs["triggered_by"] == hr_user_id
    assert kwargs["work_email"] == "new.hire@itsmatcha.net"
    assert kwargs["personal_email"] == "new.hire@gmail.com"


def test_create_employee_does_not_queue_google_onboarding_when_auto_provision_disabled(monkeypatch):
    company_id = uuid4()
    conn = _FakeConn(integration_rows=[_google_row(False)])
    _install_fakes(monkeypatch, conn, company_id)

    request = employees_crud.EmployeeCreateRequest(
        email="manual.only@itsmatcha.net",
        first_name="Manual",
        last_name="Only",
        start_date="2026-02-17",
    )
    background_tasks = BackgroundTasks()
    current_user = CurrentUser(id=uuid4(), email="hr-admin@itsmatcha.net", role="client")

    response = asyncio.run(
        employees_crud.create_employee(request, background_tasks, current_user)
    )

    assert response.id == conn.employee_id
    assert _provisioning_tasks(background_tasks) == []
