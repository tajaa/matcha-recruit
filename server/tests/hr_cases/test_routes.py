"""Route table + gating for /matcha-work/hr-cases. No app boot, no DB.

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_routes.py -q
"""
import importlib.util
import inspect
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests._helpers.routes import QueryConn, iter_api_routes, route_client

SERVER = Path(__file__).resolve().parents[2]
NAME = "app.matcha.routes.matcha_work.hr_cases"


@pytest.fixture(scope="module")
def mod():
    if "app.matcha.routes" not in sys.modules:
        pkg = types.ModuleType("app.matcha.routes")
        pkg.__path__ = [str(SERVER / "app/matcha/routes")]
        sys.modules["app.matcha.routes"] = pkg
    if NAME in sys.modules:
        return sys.modules[NAME]
    spec = importlib.util.spec_from_file_location(NAME, SERVER / "app/matcha/routes/matcha_work/hr_cases.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[NAME] = module
    spec.loader.exec_module(module)
    return module


def _feature_of(dependant) -> set[str]:
    found = set()
    for sub in dependant.dependencies:
        closure = inspect.getclosurevars(sub.call).nonlocals if inspect.isfunction(sub.call) else {}
        if closure.get("feature_name"):
            found.add(closure["feature_name"])
        found |= _feature_of(sub)
    return found


def _uses(dependant, call) -> bool:
    return any(sub.call is call or _uses(sub, call) for sub in dependant.dependencies)


def test_surface_order_and_gating(mod):
    routes = list(iter_api_routes(mod.router))
    order = [r.path for r in routes]
    param = order.index("/hr-cases/{case_id}")
    assert order.index("/hr-cases/access") < param and order.index("/hr-cases/settings") < param
    for route in routes:
        label = f"{sorted(route.methods)} {route.path}"
        assert "hr_cases" in _feature_of(route.dependant), label
        assert _uses(route.dependant, mod.require_admin_or_client), label
        src = inspect.getsource(route.endpoint)
        assert "await _business_company(current_user)" in src, label
        if route.path != "/hr-cases/access":
            assert "await _require_hr(conn, current_user, company_id)" in src, label


def _client(mod, user):
    gate = mod.router.dependencies[0].dependency
    return route_client(mod.router, overrides={mod.require_admin_or_client: user, gate: user})


@pytest.fixture
def scope(monkeypatch, mod):
    company = uuid4()
    state = {"personal": False, "hr": True, "conn": QueryConn(fetchval={"is_personal": False})}

    async def resolve(user, requested=None):
        return {"company_id": company}

    async def hr(conn, *, user, company_id):
        return state["hr"]

    monkeypatch.setattr(mod, "resolve_accessible_company_scope", resolve)
    monkeypatch.setattr(mod, "has_hr_access", hr)
    monkeypatch.setattr(mod, "get_connection", lambda *a, **k: state["conn"])
    state["company"] = company
    return state


USER = SimpleNamespace(id=uuid4(), role="client")


def test_personal_workspace_refused(mod, scope):
    scope["conn"] = QueryConn(fetchval={"is_personal": True})
    with _client(mod, USER) as client:
        assert client.get("/hr-cases").status_code == 403


def test_non_hr_gets_404_and_access_false(mod, scope):
    scope["hr"] = False
    with _client(mod, USER) as client:
        assert client.get("/hr-cases/access").json() == {"hr_access": False}
        assert client.get("/hr-cases").status_code == 404
        assert client.get(f"/hr-cases/{uuid4()}").status_code == 404
        assert client.post(f"/hr-cases/{uuid4()}/dismiss", json={"reason": "not a policy issue"}).status_code == 404


def test_list_returns_columns_and_cases(mod, scope, monkeypatch):
    async def list_cases(conn, *, company_id, include_closed):
        assert company_id == scope["company"] and include_closed is True
        return [{"id": "c1"}]
    monkeypatch.setattr(mod.case_service, "list_cases", list_cases)
    with _client(mod, USER) as client:
        body = client.get("/hr-cases?include_closed=true").json()
    assert [c["key"] for c in body["columns"]] == ["new", "review", "delivery", "signed", "done"]
    assert body["cases"] == [{"id": "c1"}]


def test_dismiss_maps_errors_and_validates(mod, scope, monkeypatch):
    async def dismiss(conn, **kw):
        raise mod.CaseError(409, "Can't dismiss a case that is approved to deliver.")
    monkeypatch.setattr(mod.case_service, "dismiss_case", dismiss)
    with _client(mod, USER) as client:
        assert client.post(f"/hr-cases/{uuid4()}/dismiss", json={"reason": "short"}).status_code == 422
        assert client.post(f"/hr-cases/{uuid4()}/dismiss", json={"reason": "handled informally"}).status_code == 409


def test_open_case_by_hand(mod, scope, monkeypatch):
    incident_id = uuid4()
    gm = uuid4()
    scope["conn"] = QueryConn(
        fetchval={"is_personal": False},
        fetchrow={"FROM ir_incidents": {"id": incident_id, "created_by": gm, "reported_by_email": None, "involved_employee_ids": []}},
    )
    from app.matcha.services.hr_cases import notifications

    async def resolve_gm(conn, *, company_id, incident):
        return gm

    seen = {}

    async def open_case(conn, **kw):
        seen.update(kw)
        return {"id": "c1"}, True
    monkeypatch.setattr(notifications, "resolve_gm_user_id", resolve_gm)
    monkeypatch.setattr(mod.case_service, "open_case", open_case)
    with _client(mod, USER) as client:
        body = client.post("/hr-cases", json={"incident_id": str(incident_id)}).json()
    assert body == {"case": {"id": "c1"}, "created": True}
    assert seen["origin"] == "manual" and seen["gm_user_id"] == gm and seen["opened_by"] == USER.id


def test_open_case_unknown_incident(mod, scope):
    scope["conn"] = QueryConn(fetchval={"is_personal": False}, fetchrow={"FROM ir_incidents": None})
    with _client(mod, USER) as client:
        assert client.post("/hr-cases", json={"incident_id": str(uuid4())}).status_code == 404


def test_get_case_and_settings(mod, scope, monkeypatch):
    async def get_case(conn, *, company_id, case_id, with_events):
        assert with_events is True
        return {"id": str(case_id)}

    async def settings(conn, company_id):
        return {"triage_min_confidence": 0.6, "filename_template": "{last_name}"}
    monkeypatch.setattr(mod.case_service, "get_case", get_case)
    monkeypatch.setattr(mod.case_service, "get_settings", settings)
    cid = uuid4()
    with _client(mod, USER) as client:
        assert client.get(f"/hr-cases/{cid}").json() == {"id": str(cid)}
        assert client.get("/hr-cases/settings").json()["triage_min_confidence"] == 0.6
        assert client.put("/hr-cases/settings", json={"triage_min_confidence": 0.1}).status_code == 422
        resp = client.put("/hr-cases/settings", json={"triage_min_confidence": 0.7})
    assert resp.status_code == 200
    assert scope["conn"].args_for("INSERT INTO hr_case_settings")[1] == 0.7


def test_flag_registered():
    from app.core.feature_flags import DEFAULT_COMPANY_FEATURES, FEATURE_REQUIRES

    assert DEFAULT_COMPANY_FEATURES["hr_cases"] is False
    assert FEATURE_REQUIRES["hr_cases"] == ("matcha_work", "matcha_drive")
