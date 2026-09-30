"""Route table + gating for /matcha-work/drive. No app boot, no DB.

Loaded by path under a stub `app.matcha.routes` package so the router zoo's
`__init__` never runs — same trick as tests/sym_chat/test_routes_smoke.py.
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
NAME = "app.matcha.routes.matcha_work.drive"


@pytest.fixture(scope="module")
def mod():
    if "app.matcha.routes" not in sys.modules:
        pkg = types.ModuleType("app.matcha.routes")
        pkg.__path__ = [str(SERVER / "app/matcha/routes")]
        sys.modules["app.matcha.routes"] = pkg
    if NAME in sys.modules:
        return sys.modules[NAME]
    spec = importlib.util.spec_from_file_location(NAME, SERVER / "app/matcha/routes/matcha_work/drive.py")
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


def test_static_paths_declared_before_params(mod):
    order = [r.path for r in iter_api_routes(mod.router)]
    first_param = min(i for i, p in enumerate(order) if "{" in p)
    assert order.index("/drive/tree") < first_param
    assert order.index("/drive/search") < first_param


def test_every_route_is_flag_gated_authenticated_and_business_scoped(mod):
    for route in iter_api_routes(mod.router):
        label = f"{sorted(route.methods)} {route.path}"
        assert "matcha_drive" in _feature_of(route.dependant), f"{label} not behind matcha_drive"
        assert _uses(route.dependant, mod.require_company_member), f"{label} has no auth dependency"
        assert "await _business_company(current_user)" in inspect.getsource(route.endpoint), label


def _client(mod, user):
    feature_gate = mod.router.dependencies[0].dependency
    return route_client(mod.router, overrides={mod.require_company_member: user, feature_gate: user})


def _patch_scope(monkeypatch, mod, *, is_personal):
    company = uuid4()

    async def scope(user, requested=None):
        return {"company_id": company}

    monkeypatch.setattr(mod, "resolve_accessible_company_scope", scope)
    monkeypatch.setattr(mod, "get_connection", lambda *a, **k: QueryConn(fetchval={"is_personal": is_personal}))
    return company


def test_personal_workspace_refused(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=True)
    user = SimpleNamespace(id=uuid4(), role="client")
    with _client(mod, user) as client:
        assert client.get("/drive/tree").status_code == 403


def test_service_errors_map_to_status(monkeypatch, mod):
    company = _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")
    seen = {}

    async def load_actor(conn, *, user, company_id):
        seen["company"] = company_id
        return SimpleNamespace(user_id=user.id, work_level="operator")

    async def list_folder(conn, *, company_id, folder_id, actor):
        raise mod.DriveError(404, "That folder doesn't exist.")

    monkeypatch.setattr(mod.svc, "load_actor", load_actor)
    monkeypatch.setattr(mod.svc, "list_folder", list_folder)
    with _client(mod, user) as client:
        resp = client.get(f"/drive/folders/{uuid4()}")
    assert resp.status_code == 404
    assert seen["company"] == company


def test_upload_checks_permission_before_reading_the_file(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace(user_id=user.id, work_level="member")

    async def deny(conn, *, company_id, folder_id, actor):
        raise mod.DriveError(404, "That folder doesn't exist.")

    async def prepare(*a, **k):
        raise AssertionError("must not parse the file before the permission check")
    monkeypatch.setattr(mod.svc, "load_actor", load_actor)
    monkeypatch.setattr(mod.svc, "assert_can_add", deny)
    monkeypatch.setattr(mod.svc, "prepare_file", prepare)
    with _client(mod, user) as client:
        resp = client.post("/drive/files", data={"folder_id": str(uuid4())},
                           files={"file": ("big.pdf", b"%PDF-1.7", "application/pdf")})
    assert resp.status_code == 404


def test_upload_bad_file_after_permission_is_400(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace(user_id=user.id, work_level="operator")

    async def allow(conn, **kw):
        return {}
    monkeypatch.setattr(mod.svc, "load_actor", load_actor)
    monkeypatch.setattr(mod.svc, "assert_can_add", allow)
    with _client(mod, user) as client:
        resp = client.post("/drive/files", data={"folder_id": str(uuid4())},
                           files={"file": ("malware.exe", b"MZ", "application/octet-stream")})
    assert resp.status_code == 400


def test_platform_admin_is_refused(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    with _client(mod, SimpleNamespace(id=uuid4(), role="admin")) as client:
        assert client.get("/drive/tree").status_code == 403


def test_employees_reach_drive(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace(user_id=user.id, work_level="member")

    async def tree(conn, *, company_id, actor):
        return {"spaces": {}}
    monkeypatch.setattr(mod.svc, "load_actor", load_actor)
    monkeypatch.setattr(mod.svc, "get_tree", tree)
    with _client(mod, SimpleNamespace(id=uuid4(), role="employee")) as client:
        assert client.get("/drive/tree").status_code == 200


def test_grant_permission_enum_validated(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")
    with _client(mod, user) as client:
        resp = client.put(f"/drive/folders/{uuid4()}/grants", json={"user_id": str(uuid4()), "permission": "owner"})
    assert resp.status_code == 422


def test_flag_registered_default_off_and_requires_matcha_work():
    from app.core.feature_flags import DEFAULT_COMPANY_FEATURES, FEATURE_REQUIRES

    assert DEFAULT_COMPANY_FEATURES["matcha_drive"] is False
    assert FEATURE_REQUIRES["matcha_drive"] == ("matcha_work",)
