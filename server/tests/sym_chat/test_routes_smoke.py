"""Route table + gating for /matcha-work/sym-chats. No app boot, no DB.

The module is loaded by path under a stub `app.matcha.routes` package so the
router zoo's `__init__` (WeasyPrint et al.) never runs — same trick as
tests/symlink/test_routes_smoke.py.
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
NAME = "app.matcha.routes.matcha_work.sym_chat"


@pytest.fixture(scope="module")
def mod():
    if "app.matcha.routes" not in sys.modules:
        pkg = types.ModuleType("app.matcha.routes")
        pkg.__path__ = [str(SERVER / "app/matcha/routes")]
        sys.modules["app.matcha.routes"] = pkg
    if NAME in sys.modules:
        return sys.modules[NAME]
    spec = importlib.util.spec_from_file_location(NAME, SERVER / "app/matcha/routes/matcha_work/sym_chat.py")
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


def test_surface(mod):
    paths = {(r.path, tuple(sorted(r.methods))) for r in iter_api_routes(mod.router)}
    assert paths == {
        ("/sym-chats/kinds", ("GET",)),
        ("/sym-chats", ("GET",)),
        ("/sym-chats", ("POST",)),
        ("/sym-chats/people", ("GET",)),
        ("/sym-chats/{chat_id}", ("GET",)),
        ("/sym-chats/{chat_id}/messages", ("POST",)),
        ("/sym-chats/{chat_id}/cancel", ("POST",)),
    }
    order = [r.path for r in iter_api_routes(mod.router)]
    assert order.index("/sym-chats/people") < order.index("/sym-chats/{chat_id}")


def test_every_route_is_flag_gated_and_authenticated(mod):
    for route in iter_api_routes(mod.router):
        label = f"{sorted(route.methods)} {route.path}"
        assert "sym_chat" in _feature_of(route.dependant), f"{label} is not behind require_feature('sym_chat')"
        assert _uses(route.dependant, mod.require_admin_or_client), f"{label} has no auth dependency"


def test_every_handler_resolves_business_scope(mod):
    for route in iter_api_routes(mod.router):
        assert "await _business_scope(current_user)" in inspect.getsource(route.endpoint), route.path


def _client(mod, user):
    feature_gate = mod.router.dependencies[0].dependency
    return route_client(mod.router, overrides={mod.require_admin_or_client: user, feature_gate: user})


def _patch_scope(monkeypatch, mod, *, is_personal):
    company = uuid4()

    async def scope(user, requested=None):
        return {"company_id": company}

    monkeypatch.setattr(mod, "resolve_accessible_company_scope", scope)
    monkeypatch.setattr(mod, "get_connection", lambda *a, **k: QueryConn(fetchval={"is_personal": is_personal}))
    return company


def test_personal_workspace_is_refused(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=True)
    user = SimpleNamespace(id=uuid4(), role="client")
    with _client(mod, user) as client:
        assert client.get("/sym-chats").status_code == 403


def test_individual_role_is_refused(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="individual")
    with _client(mod, user) as client:
        assert client.get("/sym-chats").status_code == 403


def test_business_user_lists_and_service_errors_map_to_status(monkeypatch, mod):
    company = _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")
    seen = {}

    async def list_for_user(company_id, user_id):
        seen["args"] = (company_id, user_id)
        return []

    async def get_detail(chat_id, company_id, user_id):
        raise mod.service.SymChatError(404, "Sym-chat not found")

    monkeypatch.setattr(mod.service, "list_for_user", list_for_user)
    monkeypatch.setattr(mod.service, "get_detail", get_detail)
    with _client(mod, user) as client:
        assert client.get("/sym-chats").json() == {"sym_chats": []}
        assert seen["args"] == (company, user.id)
        assert client.get(f"/sym-chats/{uuid4()}").status_code == 404
        # Body validation: participants are required.
        assert client.post("/sym-chats", json={"kind": "decide", "title": "x", "participant_ids": []}).status_code == 422


def test_turn_charges_both_budgets(monkeypatch, mod):
    company = _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")
    charged = []

    async def rate(key, action, limit, window):
        charged.append((key, action, limit, window))

    async def run_turn(chat_id, company_id, user_id, content):
        return {"reply": "ok"}

    monkeypatch.setattr(mod, "check_rate_limit", rate)
    monkeypatch.setattr(mod.service, "run_turn", run_turn)
    chat_id = uuid4()
    with _client(mod, user) as client:
        assert client.post(f"/sym-chats/{chat_id}/messages", json={"content": "hi"}).status_code == 200
    assert charged == [
        (str(chat_id), "sym_chat_turn", 200, 3600),
        (str(company), "sym_chat_turn_company", 1000, 3600),
    ]


def test_flag_registered_default_off_and_requires_matcha_work():
    from app.core.feature_flags import DEFAULT_COMPANY_FEATURES, FEATURE_REQUIRES

    assert DEFAULT_COMPANY_FEATURES["sym_chat"] is False
    assert FEATURE_REQUIRES["sym_chat"] == ("matcha_work",)
