from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import types
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.models.auth import CurrentUser
from app.matcha.models.er_case import ERCaseCreate, ERCaseUpdate

multipart_module = types.ModuleType("multipart")
multipart_module.__version__ = "0.0"
multipart_submodule = types.ModuleType("multipart.multipart")
multipart_submodule.parse_options_header = lambda value: (value, {})
sys.modules.setdefault("multipart", multipart_module)
sys.modules.setdefault("multipart.multipart", multipart_submodule)

auth_service_module = types.ModuleType("app.core.services.auth")
auth_service_module.hash_password = lambda value: f"hashed:{value}"

async def _fake_verify_password_async(plain, hashed):
    return True

auth_service_module.verify_password_async = _fake_verify_password_async
sys.modules.setdefault("app.core.services.auth", auth_service_module)

employees_routes_module = types.ModuleType("app.matcha.routes.employees")

async def _fake_refresh_risk_assessment(company_id):
    return None

employees_routes_module._refresh_risk_assessment = _fake_refresh_risk_assessment
sys.modules.setdefault("app.matcha.routes.employees", employees_routes_module)

routes_package = types.ModuleType("app.matcha.routes")
routes_package.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "matcha" / "routes")]
sys.modules.setdefault("app.matcha.routes", routes_package)

er_spec = importlib.util.spec_from_file_location(
    "app.matcha.routes.er_copilot",
    Path(__file__).resolve().parents[1] / "app" / "matcha" / "routes" / "er_copilot.py",
)
er_copilot_routes = importlib.util.module_from_spec(er_spec)
sys.modules["app.matcha.routes.er_copilot"] = er_copilot_routes
assert er_spec.loader is not None
er_spec.loader.exec_module(er_copilot_routes)


class _ConnContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _CreateCaseConn:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, query, *args):
        if "INSERT INTO er_cases" in query:
            return self.row
        raise AssertionError(f"Unexpected fetchrow query: {query}")


class _UpdateCaseConn:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, query, *args):
        if "UPDATE er_cases" in query:
            return self.row
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def fetchval(self, query, *args):
        if "SELECT COUNT(*) FROM er_case_documents" in query:
            return 0
        raise AssertionError(f"Unexpected fetchval query: {query}")


def _request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))


def _user() -> CurrentUser:
    return CurrentUser(id=uuid4(), email="client@example.com", role="client")


@pytest.mark.asyncio
async def test_create_case_queues_risk_refresh(monkeypatch: pytest.MonkeyPatch):
    company_id = uuid4()
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(),
        "case_number": "ER-2026-03-ABCD",
        "title": "Policy issue",
        "description": "Details",
        "intake_context": None,
        "status": "open",
        "company_id": company_id,
        "created_by": uuid4(),
        "assigned_to": None,
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "category": None,
        "outcome": None,
        "involved_employees": [],
    }

    monkeypatch.setattr(er_copilot_routes, "get_connection", lambda: _ConnContext(_CreateCaseConn(row)))
    async def _fake_company_id(current_user):
        return company_id

    monkeypatch.setattr(er_copilot_routes, "get_client_company_id", _fake_company_id)

    async def _noop_log_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(er_copilot_routes, "log_audit", _noop_log_audit)

    background_tasks = BackgroundTasks()
    response = await er_copilot_routes.create_case(
        ERCaseCreate(title="Policy issue", description="Details"),
        _request(),
        background_tasks,
        _user(),
    )

    assert response.company_id == company_id
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].args == (company_id,)


@pytest.mark.asyncio
async def test_update_case_queues_risk_refresh_for_non_closed_status_change(monkeypatch: pytest.MonkeyPatch):
    company_id = uuid4()
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(),
        "case_number": "ER-2026-03-ABCD",
        "title": "Policy issue",
        "description": "Details",
        "intake_context": None,
        "status": "in_review",
        "company_id": company_id,
        "created_by": uuid4(),
        "assigned_to": None,
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "category": None,
        "outcome": None,
        "involved_employees": [],
    }

    monkeypatch.setattr(er_copilot_routes, "get_connection", lambda: _ConnContext(_UpdateCaseConn(row)))
    async def _fake_company_id(current_user):
        return company_id

    monkeypatch.setattr(er_copilot_routes, "get_client_company_id", _fake_company_id)

    async def _noop_verify_case_company(*args, **kwargs):
        return None

    async def _noop_log_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(er_copilot_routes, "_verify_case_company", _noop_verify_case_company)
    monkeypatch.setattr(er_copilot_routes, "log_audit", _noop_log_audit)

    background_tasks = BackgroundTasks()
    response = await er_copilot_routes.update_case(
        row["id"],
        ERCaseUpdate(status="in_review"),
        _request(),
        background_tasks,
        _user(),
    )

    assert response.status == "in_review"
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].args == (company_id,)
