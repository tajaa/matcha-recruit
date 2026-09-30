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


MANAGER_ROUTES = {
    "/hr-cases/mine", "/hr-cases/employees", "/hr-cases/incidents", "/hr-cases/drafts",
    "/hr-cases/{case_id}/delivered", "/hr-cases/{case_id}/draft", "/hr-cases/{case_id}/signed",
}


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
        if route.path in MANAGER_ROUTES:
            # Authorized per-case in workflow.py (HR or the case's manager).
            assert "_require_hr(" not in src, label
        elif route.path != "/hr-cases/access":
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

    from app.matcha import dependencies

    async def manage(conn, *, user, company_id):
        return state.get("manage", True)

    # The business-workspace guard is shared (matcha/dependencies.py).
    monkeypatch.setattr(dependencies, "resolve_accessible_company_scope", resolve)
    monkeypatch.setattr(dependencies, "get_connection", lambda *a, **k: state["conn"])
    monkeypatch.setattr(mod, "has_hr_access", hr)
    monkeypatch.setattr(mod, "can_change_hr_settings", manage)
    monkeypatch.setattr(mod, "get_connection", lambda *a, **k: state["conn"])
    state["company"] = company
    return state


USER = SimpleNamespace(id=uuid4(), role="client", email="gm@example.com")


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


# ── Manager + decision routes ───────────────────────────────────────────


def _no_limit(monkeypatch, mod):
    async def ok(*a, **k):
        return None
    monkeypatch.setattr(mod, "check_rate_limit", ok)


def test_mine_lists_managers_own_cases(mod, scope, monkeypatch):
    async def mine(conn, *, company_id, user_id):
        assert user_id == USER.id
        return [{"id": "c1"}]
    monkeypatch.setattr(mod.workflow, "list_for_manager", mine)
    scope["hr"] = False  # managers don't need HR access for their own cases
    with _client(mod, USER) as client:
        assert client.get("/hr-cases/mine").json() == {"cases": [{"id": "c1"}]}


def test_employee_and_incident_pickers(mod, scope):
    scope["conn"] = QueryConn(
        fetchval={"is_personal": False},
        fetch={"FROM employees": [{"id": "e1", "name": "Jane Doe", "job_title": "Barista"}],
               "FROM ir_incidents": [{"id": "i1", "incident_number": "IR-1", "title": "Late", "occurred_at": None,
                                      "created_by": None, "reported_by_email": "x@example.com"}]},
    )
    with _client(mod, USER) as client:
        assert client.get("/hr-cases/employees?q=ja_").json()["employees"][0]["name"] == "Jane Doe"
        incidents = client.get("/hr-cases/incidents").json()["incidents"]
    assert incidents == [{"id": "i1", "incident_number": "IR-1", "title": "Late", "occurred_at": None}]
    assert scope["conn"].args_for("FROM employees")[2] == "%ja\\_%"
    assert scope["conn"].args_for("FROM ir_incidents")[3] is True  # HR sees every incident


def test_a_manager_only_sees_incidents_they_reported(mod, scope, monkeypatch):
    from app.matcha.services.hr_cases import notifications

    mine, theirs = uuid4(), uuid4()
    scope["hr"] = False
    scope["conn"] = QueryConn(
        fetchval={"is_personal": False},
        fetch={"FROM ir_incidents": [
            {"id": mine, "incident_number": "IR-1", "title": "a", "occurred_at": None, "created_by": USER.id, "reported_by_email": None},
            # Reported by the same address, but credited to another active member.
            {"id": theirs, "incident_number": "IR-2", "title": "b", "occurred_at": None, "created_by": uuid4(), "reported_by_email": USER.email},
        ]},
    )

    async def reporter(conn, *, company_id, incident):
        return incident["created_by"]
    monkeypatch.setattr(notifications, "resolve_gm_user_id", reporter)
    with _client(mod, USER) as client:
        incidents = client.get("/hr-cases/incidents").json()["incidents"]
    assert [i["id"] for i in incidents] == [str(mine)]
    args = scope["conn"].args_for("FROM ir_incidents")
    assert args[3:] == (False, USER.id, USER.email)


DRAFT_FORM = {"employee_id": str(uuid4()), "action_type": "written_warning", "infraction_type": "attendance",
              "occurrence_dates": "2026-09-03"}


def test_draft_needs_exactly_one_source(mod, scope, monkeypatch):
    _no_limit(monkeypatch, mod)
    with _client(mod, USER) as client:
        assert client.post("/hr-cases/drafts", data=DRAFT_FORM).status_code == 400
        both = client.post("/hr-cases/drafts", data={**DRAFT_FORM, "google_url": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUv"},
                           files={"file": ("w.pdf", b"%PDF-1.7", "application/pdf")})
        assert both.status_code == 400


def test_draft_upload_submits_and_returns_manager_view(mod, scope, monkeypatch):
    _no_limit(monkeypatch, mod)
    from app.matcha.services.drive import drive_service

    async def prepare(name, data):
        return SimpleNamespace(filename=name, text_status="ok", extracted_text="t")
    seen = {}

    async def submit(connect, **kw):
        seen.update(kw, connect=connect)
        return {"status": "submitted", "case": {"id": "c1"}, "manager_view": {"id": "c1", "stage": "hr_review"}}
    monkeypatch.setattr(drive_service, "prepare_file", prepare)
    monkeypatch.setattr(mod.workflow, "submit_draft", submit)
    scope["hr"] = False
    with _client(mod, USER) as client:
        resp = client.post("/hr-cases/drafts", data=DRAFT_FORM, files={"file": ("w.pdf", b"%PDF-1.7", "application/pdf")})
    assert resp.status_code == 201
    assert resp.json() == {"status": "submitted", "case": {"id": "c1", "stage": "hr_review"}}
    assert seen["actor_is_hr"] is False and seen["occurrence_dates"][0].isoformat() == "2026-09-03"
    assert seen["connect"] is mod.get_connection  # a factory, not a held connection


def test_draft_drive_errors_while_filing_map_to_their_status(mod, scope, monkeypatch):
    _no_limit(monkeypatch, mod)
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.drive_service import DriveError

    async def prepare(name, data):
        return SimpleNamespace(filename=name, text_status="ok", extracted_text="t")

    async def submit(connect, **kw):
        raise DriveError(503, "Storage is unavailable.")
    monkeypatch.setattr(drive_service, "prepare_file", prepare)
    monkeypatch.setattr(mod.workflow, "submit_draft", submit)
    with _client(mod, USER) as client:
        resp = client.post("/hr-cases/drafts", data=DRAFT_FORM, files={"file": ("w.pdf", b"%PDF-1.7", "application/pdf")})
    assert resp.status_code == 503 and resp.json()["detail"] == "Storage is unavailable."


def test_draft_from_google_link(mod, scope, monkeypatch):
    _no_limit(monkeypatch, mod)
    from app.matcha.services.drive import drive_service, google_drive_service

    async def fetch(self, file_id):
        return google_drive_service.GoogleFile(file_id=file_id, name="w.docx", mime_type="x", data=b"PK")

    async def prepare(name, data):
        return SimpleNamespace(filename=name, text_status="ok", extracted_text="t")
    seen = {}

    async def submit(connect, **kw):
        seen.update(kw)
        return {"status": "held", "case": {}, "manager_view": {"id": "c1"}}
    monkeypatch.setattr(google_drive_service.GoogleDriveService, "fetch_file", fetch)
    monkeypatch.setattr(drive_service, "prepare_file", prepare)
    monkeypatch.setattr(mod.workflow, "submit_draft", submit)
    with _client(mod, USER) as client:
        resp = client.post("/hr-cases/drafts", data={**DRAFT_FORM, "google_url": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUv/edit"})
        bad = client.post("/hr-cases/drafts", data={**DRAFT_FORM, "google_url": "https://example.com/x"})
    assert resp.status_code == 201 and resp.json()["status"] == "held"
    assert seen["source"] == "google_drive" and seen["source_ref"] == "1AbCdEfGhIjKlMnOpQrStUv"
    assert bad.status_code == 400


def test_draft_from_drive_file_uses_senders_drive_access(mod, scope, monkeypatch):
    _no_limit(monkeypatch, mod)
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.drive_service import DriveError

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace(user_id=user.id, work_level="member")

    async def read_bytes(conn, *, company_id, file_id, actor):
        raise DriveError(404, "That file doesn't exist.")
    monkeypatch.setattr(drive_service, "load_actor", load_actor)
    monkeypatch.setattr(drive_service, "read_file_bytes", read_bytes)
    with _client(mod, USER) as client:
        resp = client.post("/hr-cases/drafts", data={**DRAFT_FORM, "drive_file_id": str(uuid4())})
    assert resp.status_code == 404


def test_draft_bad_dates(mod, scope, monkeypatch):
    _no_limit(monkeypatch, mod)
    with _client(mod, USER) as client:
        resp = client.post("/hr-cases/drafts", data={**DRAFT_FORM, "occurrence_dates": "yesterday"},
                           files={"file": ("w.pdf", b"%PDF-1.7", "application/pdf")})
    assert resp.status_code == 400


def test_decision_is_hr_only_and_maps_errors(mod, scope, monkeypatch):
    async def decide(conn, **kw):
        raise mod.CaseError(409, "Leave records changed")
    monkeypatch.setattr(mod.workflow, "decide", decide)
    with _client(mod, USER) as client:
        assert client.post(f"/hr-cases/{uuid4()}/decision", json={"decision": "approve"}).status_code == 409
        assert client.post(f"/hr-cases/{uuid4()}/decision", json={"decision": "maybe"}).status_code == 422
    scope["hr"] = False
    with _client(mod, USER) as client:
        assert client.post(f"/hr-cases/{uuid4()}/decision", json={"decision": "approve"}).status_code == 404


def test_delivered_returns_manager_view_for_managers(mod, scope, monkeypatch):
    full = {"id": "c1", "case_number": "HRC-1", "stage": "delivered", "triage": {"secret": 1}}

    async def deliver(conn, **kw):
        return full
    monkeypatch.setattr(mod.workflow, "mark_delivered", deliver)
    scope["hr"] = False
    with _client(mod, USER) as client:
        body = client.post(f"/hr-cases/{uuid4()}/delivered", json={}).json()
    assert "triage" not in body and body["stage"] == "delivered"
    scope["hr"] = True
    with _client(mod, USER) as client:
        assert "triage" in client.post(f"/hr-cases/{uuid4()}/delivered", json={}).json()


def test_draft_download_goes_through_drive_and_is_audited(mod, scope, monkeypatch):
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.drive_service import DriveError

    draft, case_id = uuid4(), uuid4()

    async def load(conn, **kw):
        return {"draft_file_id": draft}
    seen = {}

    async def presign(conn, **kw):
        seen.update(kw)
        return {"url": "https://s3/x", "filename": "d.pdf", "expires_in": 300}
    monkeypatch.setattr(mod.workflow, "load_for_actor", load)
    monkeypatch.setattr(drive_service, "presign_download", presign)
    with _client(mod, USER) as client:
        assert client.get(f"/hr-cases/{case_id}/draft").json()["url"] == "https://s3/x"
    assert seen["file_id"] == draft and seen["actor"] is None and seen["on_behalf_of"] == USER.id
    assert seen["audit_details"] == {"via": "hr_case", "case_id": str(case_id)}

    async def gone(conn, **kw):
        raise DriveError(404, "That file doesn't exist.")
    monkeypatch.setattr(drive_service, "presign_download", gone)
    with _client(mod, USER) as client:
        resp = client.get(f"/hr-cases/{case_id}/draft")
    assert resp.status_code == 404 and resp.json()["detail"] == "The draft file is no longer available."

    async def no_draft(conn, **kw):
        return {"draft_file_id": None}
    monkeypatch.setattr(mod.workflow, "load_for_actor", no_draft)
    with _client(mod, USER) as client:
        assert client.get(f"/hr-cases/{uuid4()}/draft").status_code == 404


# ── Signed copy + template ──────────────────────────────────────────────


def test_signed_upload_schedules_check_and_redacts_for_manager(mod, scope, monkeypatch):
    queued = []

    async def upload(conn, **kw):
        return {"case": {"id": "c1", "case_number": "HRC-1", "stage": "verifying", "triage": {"x": 1}},
                "mime_type": "application/pdf"}

    async def check(**kw):
        queued.append(kw)
    monkeypatch.setattr(mod.workflow, "upload_signed", upload)
    monkeypatch.setattr(mod.workflow, "check_signed_and_notify", check)
    scope["hr"] = False
    with _client(mod, USER) as client:
        body = client.post(f"/hr-cases/{uuid4()}/signed", files={"file": ("s.pdf", b"%PDF", "application/pdf")}).json()
    assert "triage" not in body and body["stage"] == "verifying"
    assert queued and queued[0]["mime_type"] == "application/pdf"


def test_signed_upload_error_maps(mod, scope, monkeypatch):
    async def upload(conn, **kw):
        raise mod.CaseError(409, "Can't add a signed copy now.")
    monkeypatch.setattr(mod.workflow, "upload_signed", upload)
    with _client(mod, USER) as client:
        assert client.post(f"/hr-cases/{uuid4()}/signed", files={"file": ("s.pdf", b"%PDF", "application/pdf")}).status_code == 409


def test_signed_download_goes_through_drive_and_is_audited(mod, scope, monkeypatch):
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.drive_service import DriveError

    signed, case_id = uuid4(), uuid4()

    async def load(conn, **kw):
        return {"signed_file_id": signed}
    seen = {}

    async def presign(conn, **kw):
        seen.update(kw)
        return {"url": "https://s3/signed", "filename": "Doe.pdf", "expires_in": 300}
    monkeypatch.setattr(mod.workflow, "load_for_actor", load)
    monkeypatch.setattr(drive_service, "presign_download", presign)
    with _client(mod, USER) as client:
        assert client.get(f"/hr-cases/{case_id}/signed").json()["filename"] == "Doe.pdf"
    assert seen["file_id"] == signed and seen["actor"] is None and seen["on_behalf_of"] == USER.id

    async def gone(conn, **kw):
        raise DriveError(404, "That file doesn't exist.")
    monkeypatch.setattr(drive_service, "presign_download", gone)
    with _client(mod, USER) as client:
        assert client.get(f"/hr-cases/{case_id}/signed").status_code == 404

    async def none(conn, **kw):
        return {"signed_file_id": None}
    monkeypatch.setattr(mod.workflow, "load_for_actor", none)
    with _client(mod, USER) as client:
        assert client.get(f"/hr-cases/{uuid4()}/signed").status_code == 404


def test_acknowledge_and_recheck_are_hr_only(mod, scope, monkeypatch):
    async def ok(conn, **kw):
        return {"id": "c1", "stage": "closed"}
    seen = {}

    async def recheck(connect, **kw):
        seen["connect"] = connect
        return {"id": "c1", "stage": "closed"}
    monkeypatch.setattr(mod.workflow, "acknowledge", ok)
    monkeypatch.setattr(mod.workflow, "recheck_signed", recheck)
    with _client(mod, USER) as client:
        assert client.post(f"/hr-cases/{uuid4()}/acknowledge").json()["stage"] == "closed"
        assert client.post(f"/hr-cases/{uuid4()}/recheck").json()["stage"] == "closed"
    assert seen["connect"] is mod.get_connection  # a factory: no connection across the model read

    async def still_checking(connect, **kw):
        raise mod.CaseError(409, "That signed copy is still being checked.")
    monkeypatch.setattr(mod.workflow, "recheck_signed", still_checking)
    with _client(mod, USER) as client:
        assert client.post(f"/hr-cases/{uuid4()}/recheck").status_code == 409
    scope["hr"] = False
    with _client(mod, USER) as client:
        assert client.post(f"/hr-cases/{uuid4()}/acknowledge").status_code == 404
        assert client.post(f"/hr-cases/{uuid4()}/recheck").status_code == 404


def test_filename_template_setting(mod, scope, monkeypatch):
    async def settings(conn, company_id):
        return {"triage_min_confidence": 0.6, "filename_template": "{last_name}_{case_number}"}
    monkeypatch.setattr(mod.case_service, "get_settings", settings)
    with _client(mod, USER) as client:
        assert "case_number" in client.get("/hr-cases/settings").json()["filename_tokens"]
        assert client.put("/hr-cases/settings", json={"filename_template": "{ssn}"}).status_code == 400
        assert client.put("/hr-cases/settings", json={"filename_template": "{last_name}_{case_number}"}).status_code == 200
    assert scope["conn"].args_for("filename_template = EXCLUDED")[1] == "{last_name}_{case_number}"


def test_platform_admin_is_refused(mod, scope):
    with _client(mod, SimpleNamespace(id=uuid4(), role="admin")) as client:
        assert client.get("/hr-cases").status_code == 403
        assert client.get("/hr-cases/access").status_code == 403


def test_a_read_only_hr_grant_cannot_change_settings(mod, scope):
    scope["manage"] = False
    with _client(mod, USER) as client:
        resp = client.put("/hr-cases/settings", json={"triage_min_confidence": 0.9})
    assert resp.status_code == 403
    assert not any("hr_case_settings" in sql for sql in scope["conn"].sql_for("execute"))
