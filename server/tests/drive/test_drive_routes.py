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

    from app.matcha import dependencies

    # The business-workspace guard is shared (matcha/dependencies.py).
    monkeypatch.setattr(dependencies, "resolve_accessible_company_scope", scope)
    monkeypatch.setattr(dependencies, "get_connection", lambda *a, **k: QueryConn(fetchval={"is_personal": is_personal}))
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


def test_people_route_passes_query_and_maps_refusal(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")
    seen = {}

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace(user_id=user.id, work_level="operator")

    async def search_members(conn, *, company_id, q, actor):
        seen["q"] = q
        raise mod.DriveError(403, "Only a workspace admin can manage folder access.")

    monkeypatch.setattr(mod.svc, "load_actor", load_actor)
    monkeypatch.setattr(mod.svc, "search_members", search_members)
    with _client(mod, user) as client:
        resp = client.get("/drive/people?q=jan")
    assert resp.status_code == 403
    assert seen["q"] == "jan"


def test_people_declared_before_params(mod):
    order = [r.path for r in iter_api_routes(mod.router)]
    first_param = min(i for i, p in enumerate(order) if "{" in p)
    assert order.index("/drive/people") < first_param


# ── Google import routes ────────────────────────────────────────────────

GOOGLE_URL = "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUv/edit"


@pytest.fixture(autouse=True)
def _settings(monkeypatch, mod):
    monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(app_base_url="https://app.test"))


def _no_rate_limit(monkeypatch, mod):
    async def ok(*a, **k):
        return None
    monkeypatch.setattr(mod, "check_rate_limit", ok)


def test_import_rejects_non_google_link_before_anything(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")
    with _client(mod, user) as client:
        resp = client.post("/drive/google/import", json={"url": "https://example.com/doc/123456789012", "folder_id": str(uuid4())})
    assert resp.status_code == 400


def test_import_checks_destination_before_calling_google(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    _no_rate_limit(monkeypatch, mod)
    user = SimpleNamespace(id=uuid4(), role="client")

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace(user_id=user.id, work_level="member")

    async def deny(conn, *, company_id, folder_id, actor):
        raise mod.DriveError(404, "That folder doesn't exist.")

    async def fetch(self, file_id):
        raise AssertionError("Google must not be called")
    monkeypatch.setattr(mod.svc, "load_actor", load_actor)
    monkeypatch.setattr(mod.svc, "assert_can_add", deny)
    monkeypatch.setattr(mod.GoogleDriveService, "fetch_file", fetch)
    with _client(mod, user) as client:
        resp = client.post("/drive/google/import", json={"url": GOOGLE_URL, "folder_id": str(uuid4())})
    assert resp.status_code == 404


def test_import_stores_snapshot_with_google_source(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    _no_rate_limit(monkeypatch, mod)
    user = SimpleNamespace(id=uuid4(), role="client")
    folder_id = uuid4()
    stored = {}

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace(user_id=user.id, work_level="admin")

    async def allow(conn, **kwargs):
        return {}

    async def fetch(self, file_id):
        return mod.gdrive.GoogleFile(file_id=file_id, name="Write-up.docx", mime_type="x", data=b"PK\x03\x04")

    async def prepare(name, data):
        return SimpleNamespace(filename=name)

    async def store(conn, **kwargs):
        stored.update(kwargs)
        return {"id": str(uuid4()), "filename": "Write-up.docx"}

    monkeypatch.setattr(mod.svc, "load_actor", load_actor)
    monkeypatch.setattr(mod.svc, "assert_can_add", allow)
    monkeypatch.setattr(mod.GoogleDriveService, "fetch_file", fetch)
    monkeypatch.setattr(mod.svc, "prepare_file", prepare)
    monkeypatch.setattr(mod.svc, "store_file", store)
    with _client(mod, user) as client:
        resp = client.post("/drive/google/import", json={"url": GOOGLE_URL, "folder_id": str(folder_id)})
    assert resp.status_code == 201
    assert stored["source"] == "google_drive"
    assert stored["source_ref"] == "1AbCdEfGhIjKlMnOpQrStUv"
    assert stored["folder_id"] == folder_id


def test_import_maps_google_errors(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    _no_rate_limit(monkeypatch, mod)
    user = SimpleNamespace(id=uuid4(), role="client")

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace(user_id=user.id, work_level="admin")

    async def allow(conn, **kwargs):
        return {}

    async def fetch(self, file_id):
        raise mod.GoogleDriveError(409, "Connect your Google account first.")
    monkeypatch.setattr(mod.svc, "load_actor", load_actor)
    monkeypatch.setattr(mod.svc, "assert_can_add", allow)
    monkeypatch.setattr(mod.GoogleDriveService, "fetch_file", fetch)
    with _client(mod, user) as client:
        resp = client.post("/drive/google/import", json={"url": GOOGLE_URL, "folder_id": str(uuid4())})
    assert resp.status_code == 409


def test_connect_builds_offline_readonly_url(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")
    monkeypatch.setattr(mod.gdrive, "_client_credentials", lambda: {"client_id": "cid", "client_secret": "s"})

    bindings = []

    async def issue(prefix, user_id, ttl_seconds=0, *, binding=None):
        assert prefix == "gdrive_oauth_state"
        bindings.append(binding)
        return "S" * 43
    monkeypatch.setattr(mod.oauth_state, "issue_state", issue)
    with _client(mod, user) as client:
        resp = client.post("/drive/google/connect")
    url = resp.json()["auth_url"]
    assert "drive.readonly" in url and "access_type=offline" in url and "state=" + "S" * 43 in url
    assert "client_secret" not in url
    # The handle is bound to a nonce only this browser holds, in a cookie
    # scoped to the callback.
    cookie = resp.headers["set-cookie"]
    nonce = resp.cookies[mod.GDRIVE_BIND_COOKIE]
    assert bindings == [mod.oauth_state.binding_hash(nonce)]
    assert "HttpOnly" in cookie and "Path=/api/matcha-work/drive/google/callback" in cookie
    assert "samesite=lax" in cookie.lower() and "Secure" in cookie


def test_connect_503_when_state_store_down(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")
    monkeypatch.setattr(mod.gdrive, "_client_credentials", lambda: {"client_id": "cid", "client_secret": "s"})

    async def issue(prefix, user_id, ttl_seconds=0, *, binding=None):
        raise mod.oauth_state.OAuthStateUnavailable("down")
    monkeypatch.setattr(mod.oauth_state, "issue_state", issue)
    with _client(mod, user) as client:
        assert client.post("/drive/google/connect").status_code == 503


def test_status_and_disconnect(monkeypatch, mod):
    _patch_scope(monkeypatch, mod, is_personal=False)
    user = SimpleNamespace(id=uuid4(), role="client")

    async def status(self):
        return {"connected": True, "email": "gm@example.com"}

    async def disconnect(self):
        return None
    monkeypatch.setattr(mod.GoogleDriveService, "get_status", status)
    monkeypatch.setattr(mod.GoogleDriveService, "disconnect", disconnect)
    with _client(mod, user) as client:
        assert client.get("/drive/google/status").json()["email"] == "gm@example.com"
        assert client.delete("/drive/google/disconnect").json() == {"connected": False}


def _callback(mod, monkeypatch, *, consume, exchange=None):
    monkeypatch.setattr(mod.oauth_state, "consume_state", consume)
    if exchange:
        monkeypatch.setattr(mod.GoogleDriveService, "exchange_code", exchange)
    return route_client(mod.oauth_callback_router)


def test_callback_success_and_errors(monkeypatch, mod):
    user_id = uuid4()
    calls = []

    async def consume(prefix, state, *, binding=None):
        if state == "replayed" + "x" * 35:
            raise ValueError("Invalid or expired OAuth state")
        return user_id

    async def exchange(self, code, redirect_uri):
        calls.append((self.user_id, code, redirect_uri))
        if code == "bad":
            raise mod.GoogleDriveError(400, "Google didn't accept the sign-in. Please try again.")

    with _callback(mod, monkeypatch, consume=consume, exchange=exchange) as client:
        ok = client.get("/drive/google/callback", params={"state": "s" * 43, "code": "good"})
        assert ok.status_code == 200 and "gdrive-connected" in ok.text
        assert calls[0][0] == user_id and calls[0][2].endswith("/api/matcha-work/drive/google/callback")
        denied = client.get("/drive/google/callback", params={"state": "s" * 43, "error": "access_denied"})
        assert "gdrive-cancelled" in denied.text
        missing = client.get("/drive/google/callback", params={"state": "s" * 43})
        assert missing.status_code == 400 and "gdrive-error" in missing.text
        bad = client.get("/drive/google/callback", params={"state": "s" * 43, "code": "bad"})
        assert bad.status_code == 400 and "gdrive-error" in bad.text
        replay = client.get("/drive/google/callback", params={"state": "replayed" + "x" * 35, "code": "good"})
        # Still the popup page, so the dialog hears about it.
        assert replay.status_code == 400 and "gdrive-error" in replay.text
        # The result only ever goes to our own origin.
        assert "'*'" not in ok.text and '"https://app.test"' in ok.text


def test_callback_503_when_state_store_down(monkeypatch, mod):
    async def consume(prefix, state, *, binding=None):
        raise mod.oauth_state.OAuthStateUnavailable("down")
    with _callback(mod, monkeypatch, consume=consume) as client:
        resp = client.get("/drive/google/callback", params={"state": "s" * 43, "code": "c"})
        assert resp.status_code == 503 and "gdrive-error" in resp.text


def test_callback_passes_the_browser_binding(monkeypatch, mod):
    seen = []

    async def consume(prefix, state, *, binding=None):
        seen.append(binding)
        if binding != mod.oauth_state.binding_hash("nonce-1"):
            raise ValueError("OAuth state was started in another browser")
        return uuid4()

    async def exchange(self, code, redirect_uri):
        return None

    with _callback(mod, monkeypatch, consume=consume, exchange=exchange) as client:
        # A victim opening the sender's auth URL has no cookie (or another one).
        stranger = client.get("/drive/google/callback", params={"state": "s" * 43, "code": "c"})
        assert stranger.status_code == 400 and "another browser" in stranger.text
        client.cookies.set(mod.GDRIVE_BIND_COOKIE, "nonce-1")
        own = client.get("/drive/google/callback", params={"state": "s" * 43, "code": "c"})
        assert own.status_code == 200 and "gdrive-connected" in own.text
    assert seen == [None, mod.oauth_state.binding_hash("nonce-1")]
