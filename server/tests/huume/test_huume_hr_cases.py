"""Huume HR-case skill: registry wiring, confirm-turn validators, state block,
stage-time resolution, read tools and the executor.

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_hr_cases.py -q
"""
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.services.huume import actions, assets, hr_case_skill as skill
from app.matcha.services.huume.agent import _HR_OPS_TOOL_SPECS
from app.matcha.services.huume.prompt import build_state_block
from app.matcha.services.huume.tools import TOOLS_BY_NAME
from tests._helpers.routes import QueryConn

COMPANY = uuid4()
USER = uuid4()
EMP = str(uuid4())
FEATURES = {"huume": True, "matcha_work": True, "hr_cases": True, "matcha_drive": True}

STAGED_TOOLS = ("submit_write_up", "decide_write_up", "mark_write_up_delivered", "file_signed_write_up")
READ_TOOLS = ("list_write_ups", "search_drive", "read_drive_file")


def test_tools_declared_and_wired():
    for name in STAGED_TOOLS:
        assert TOOLS_BY_NAME[name].kind == "staged"
        spec = _HR_OPS_TOOL_SPECS[name]
        assert actions._HUUME_ACTION_REQUIRED_FEATURE[spec["action_type"]] == "hr_cases"
        assert spec["action_type"] in assets._NO_ASSET_TYPES
    for name in READ_TOOLS:
        assert TOOLS_BY_NAME[name].kind == "read"
    assert "attachment_index" in _HR_OPS_TOOL_SPECS["submit_write_up"]["fields"]


def draft(**kw):
    base = {"type": "hr_case_draft", "status": "proposed", "confirm_id": "abc12345", "source": "drive",
            "drive_file_id": str(uuid4()), "employee_id": EMP, "action_type": "written_warning",
            "infraction_type": "attendance", "occurrence_dates": ["2026-09-03"]}
    base.update(kw)
    return base


def evaluate(staged, features=FEATURES):
    return actions.evaluate_huume_action(staged_action=staged, features=features, role="client",
                                         thread_huume_mode=True, this_turn_staged_new=False)


def test_draft_validator_happy_path():
    v = evaluate(draft())
    assert v.ok and v.action["type"] == "hr_case_draft" and v.action["occurrence_dates"] == ["2026-09-03"]


@pytest.mark.parametrize("override,fragment", [
    ({"source": "email"}, "lost track"),
    ({"drive_file_id": None}, "lost track"),
    ({"employee_id": "jane"}, "Who is"),
    ({"action_type": "firing"}, "What kind"),
    ({"infraction_type": "vibes"}, "What's it about"),
    ({"occurrence_dates": ["9/3"]}, "couldn't read"),
    ({"occurrence_dates": [f"2026-01-{d:02d}" for d in range(1, 32)]}, "lot of dates"),
    ({"case_id": "nope"}, "case id"),
])
def test_draft_validator_refusals(override, fragment):
    v = evaluate(draft(**override))
    assert not v.ok and fragment in v.message


def test_action_needs_hr_cases_flag():
    v = evaluate(draft(), features={**FEATURES, "hr_cases": False})
    assert not v.ok and "hr_cases" in v.message


def test_decision_and_delivered_validators():
    cid = str(uuid4())
    assert evaluate({"type": "hr_case_decision", "status": "proposed", "case_id": cid, "decision": "approve"}).ok
    short = evaluate({"type": "hr_case_decision", "status": "proposed", "case_id": cid,
                      "decision": "request_changes", "reason": "fix"})
    assert not short.ok
    assert not evaluate({"type": "hr_case_decision", "status": "proposed", "case_id": cid, "decision": "deny"}).ok
    ok = evaluate({"type": "hr_case_delivered", "status": "proposed", "case_id": cid, "delivered_on": "2026-09-28"})
    assert ok.ok and ok.action["delivered_on"] == "2026-09-28"
    assert not evaluate({"type": "hr_case_delivered", "status": "proposed", "case_id": cid, "delivered_on": "soon"}).ok
    assert not evaluate({"type": "hr_case_delivered", "status": "proposed", "case_id": "x"}).ok


def test_state_block_echoes_ids():
    block = build_state_block({"huume_action": draft(source="attachment", attachment_url="https://x/y",
                                                     filename="w.pdf", employee_name="Jane Doe")})
    assert "confirm_id=abc12345" in block and "Jane Doe" in block and "w.pdf" in block
    assert "https://x/y" not in block
    cid = str(uuid4())
    block = build_state_block({"huume_action": {"type": "hr_case_decision", "status": "proposed",
                                                "case_id": cid, "decision": "request_changes"}})
    assert f"case_id={cid}" in block and "send back" in block
    block = build_state_block({"huume_action": {"type": "hr_case_delivered", "status": "proposed", "case_id": cid}})
    assert f"case_id={cid}" in block and "today" in block


# ── Stage-time resolution ───────────────────────────────────────────────


@pytest.fixture
def conn(monkeypatch):
    holder = {"conn": QueryConn()}

    @asynccontextmanager
    async def get_connection(*a, **k):
        yield holder["conn"]
    from app import database
    monkeypatch.setattr(database, "get_connection", get_connection)
    return holder


REFS = [{"url": "https://cdn/old.pdf", "filename": "old.pdf"}, {"url": "https://cdn/new.pdf", "filename": "new.pdf"}]


@pytest.mark.asyncio
async def test_resolve_needs_exactly_one_source(conn):
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"employee_name": "Jane"}, attachment_refs=REFS)
    assert out["status"] == "refused"
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"attachment_index": 0, "drive_file_id": "x"}, attachment_refs=REFS)
    assert out["status"] == "refused"


@pytest.mark.asyncio
async def test_resolve_attachment_is_newest_first_and_employee_by_name(conn):
    conn["conn"] = QueryConn(fetch={"FROM employees": [{"id": EMP, "name": "Jane Doe"}]})
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"attachment_index": 0, "employee_name": "jane_",
                                                                   "occurrence_dates": ["2026-09-03", "2026-09-01"]},
                                         attachment_refs=REFS)
    assert out == {"status": "ok", "source": "attachment", "attachment_url": "https://cdn/new.pdf",
                   "filename": "new.pdf", "employee_id": EMP, "employee_name": "Jane Doe",
                   "occurrence_dates": ["2026-09-01", "2026-09-03"]}
    assert conn["conn"].args_for("FROM employees")[1] == "%jane\\_%"


@pytest.mark.asyncio
async def test_resolve_bad_attachment_index_and_google(conn):
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"attachment_index": 5}, attachment_refs=REFS)
    assert out["status"] == "refused"
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"attachment_index": "x"}, attachment_refs=REFS)
    assert out["status"] == "refused"
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"google_url": "https://evil.test/d/1234567890"}, attachment_refs=[])
    assert out["status"] == "refused"


DATES = {"occurrence_dates": ["2026-09-03"]}


@pytest.mark.asyncio
async def test_resolve_needs_occurrence_dates(conn):
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"drive_file_id": "d", "employee_name": "Jane"},
                                         attachment_refs=[])
    assert out["status"] == "refused" and "date" in out["message"]
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"drive_file_id": "d", "occurrence_dates": ["9/3"]},
                                         attachment_refs=[])
    assert out["status"] == "refused" and "YYYY-MM-DD" in out["message"]
    assert conn["conn"].calls == []  # refused before any lookup


@pytest.mark.asyncio
async def test_resolve_employee_ambiguous_missing_and_by_id(conn):
    doe, roe = uuid4(), uuid4()
    conn["conn"] = QueryConn(fetch={"FROM employees": [{"id": doe, "name": "Jane Doe", "job_title": "Barista"},
                                                       {"id": roe, "name": "Jane Roe", "job_title": None}]})
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"drive_file_id": "d", "employee_name": "Jane", **DATES},
                                         attachment_refs=[])
    assert out["status"] == "refused" and "Jane Doe (Barista); Jane Roe" in out["message"] and "employee_id" in out["message"]
    assert out["candidates"] == [{"employee_id": str(doe), "name": "Jane Doe", "job_title": "Barista"},
                                 {"employee_id": str(roe), "name": "Jane Roe", "job_title": None}]
    conn["conn"] = QueryConn(fetch={"FROM employees": []})
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"drive_file_id": "d", "employee_name": "Zed", **DATES},
                                         attachment_refs=[])
    assert out["status"] == "refused"
    conn["conn"] = QueryConn(fetchrow={"FROM employees": {"id": EMP, "name": "Jane Doe"}})
    out = await skill.resolve_draft_args(
        company_id=COMPANY, args={"google_url": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUv/edit",
                                  "employee_id": EMP, **DATES},
        attachment_refs=[],
    )
    assert out["status"] == "ok" and out["google_file_id"] == "1AbCdEfGhIjKlMnOpQrStUv"
    assert await skill.resolve_draft_args(company_id=COMPANY, args={"drive_file_id": "d", **DATES}, attachment_refs=[]) == {
        "status": "refused", "message": "Who is the write-up for? I couldn't find that employee on the roster."}


@pytest.mark.asyncio
async def test_resolve_prefers_a_name_typed_in_full(conn):
    lee = uuid4()
    conn["conn"] = QueryConn(fetch={"FROM employees": [{"id": lee, "name": "Sam Lee", "job_title": None},
                                                       {"id": uuid4(), "name": "Sam Leeds", "job_title": None}]})
    out = await skill.resolve_draft_args(company_id=COMPANY, args={"drive_file_id": "d", "employee_name": "sam lee", **DATES},
                                         attachment_refs=[])
    assert out["status"] == "ok" and out["employee_id"] == str(lee)


# ── Read tools ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_tools_respect_flags():
    assert (await skill.list_write_ups(company_id=COMPANY, user_id=USER, features={}))["status"] == "module_off"
    assert (await skill.search_drive(company_id=COMPANY, user_id=USER, features={}, query="x"))["status"] == "module_off"
    assert (await skill.read_drive_file(company_id=COMPANY, user_id=USER, features={}, file_id="x"))["status"] == "module_off"


@pytest.mark.asyncio
async def test_list_write_ups_hr_vs_manager(conn, monkeypatch):
    from app.matcha.services.hr_cases import case_service, workflow

    async def cases(conn, *, company_id):
        return [{"id": uuid4(), "case_number": "HRC-1", "stage_label": "HR review", "incident_number": "IR-1",
                 "employee_name": "Jane Doe", "action_type": "written_warning", "gm_name": "Sam",
                 "allowed_events": ["approve"]}]

    async def mine(conn, *, company_id, user_id):
        return [{"id": uuid4(), "case_number": "HRC-2", "stage_label": "Flagged", "incident_number": None,
                 "employee_name": None, "review": {"held_for_hr": True}, "decision_reason": None,
                 "can_submit_draft": True, "can_mark_delivered": False}]
    monkeypatch.setattr(case_service, "list_cases", cases)
    monkeypatch.setattr(workflow, "list_for_manager", mine)

    async def hr(conn, **kw):
        return True
    monkeypatch.setattr(skill, "_is_hr", hr)
    out = await skill.list_write_ups(company_id=COMPANY, user_id=USER, features=FEATURES)
    assert out["view"] == "hr" and out["cases"][0]["manager"] == "Sam"

    async def not_hr(conn, **kw):
        return False
    monkeypatch.setattr(skill, "_is_hr", not_hr)
    out = await skill.list_write_ups(company_id=COMPANY, user_id=USER, features=FEATURES)
    assert out["view"] == "manager" and out["cases"][0]["held_for_hr"] is True


@pytest.fixture
def drive_actor(monkeypatch):
    from app.matcha.services.drive import drive_service

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace(user_id=user.id, work_level="operator")
    monkeypatch.setattr(drive_service, "load_actor", load_actor)
    return drive_service


@pytest.mark.asyncio
async def test_search_and_read_drive(conn, drive_actor, monkeypatch):
    from app.matcha.services.drive.drive_service import DriveError

    conn["conn"] = QueryConn(fetchval={"SELECT role FROM users": "client"})
    fid = uuid4()

    async def search(conn, **kw):
        return [{"id": fid, "filename": "Handbook.pdf", "folder_name": "Company", "space": "general", "text_status": "ok"}]
    monkeypatch.setattr(drive_actor, "search", search)
    out = await skill.search_drive(company_id=COMPANY, user_id=USER, features=FEATURES, query="leave")
    assert out["files"][0] == {"drive_file_id": str(fid), "filename": "Handbook.pdf", "folder": "Company",
                               "space": "general", "readable_text": True}

    async def search_fail(conn, **kw):
        raise DriveError(400, "Unknown space.")
    monkeypatch.setattr(drive_actor, "search", search_fail)
    assert (await skill.search_drive(company_id=COMPANY, user_id=USER, features=FEATURES, query="leave"))["status"] == "error"

    async def read_text(conn, **kw):
        return {"id": fid, "filename": "Handbook.pdf", "text_status": "ok", "text": "policy", "truncated": False}
    monkeypatch.setattr(drive_actor, "read_file_text", read_text)
    out = await skill.read_drive_file(company_id=COMPANY, user_id=USER, features=FEATURES, file_id=str(fid))
    assert out["text"] == "policy"
    assert (await skill.read_drive_file(company_id=COMPANY, user_id=USER, features=FEATURES, file_id="bad"))["status"] == "error"

    async def scan(conn, **kw):
        return {"id": fid, "filename": "scan.pdf", "text_status": "empty", "text": "", "truncated": False}
    monkeypatch.setattr(drive_actor, "read_file_text", scan)
    assert (await skill.read_drive_file(company_id=COMPANY, user_id=USER, features=FEATURES, file_id=str(fid)))["status"] == "no_text"

    async def denied(conn, **kw):
        raise DriveError(404, "That file doesn't exist.")
    monkeypatch.setattr(drive_actor, "read_file_text", denied)
    assert (await skill.read_drive_file(company_id=COMPANY, user_id=USER, features=FEATURES, file_id=str(fid)))["status"] == "error"


# ── Executor ────────────────────────────────────────────────────────────


@pytest.fixture
def exec_env(conn, monkeypatch):
    from app.matcha.services.hr_cases import workflow

    state = {"hr": False, "submit": {"status": "submitted"}}

    async def is_hr(conn, **kw):
        return state["hr"]

    async def fetch_source(conn, **kw):
        return SimpleNamespace(filename="w.pdf"), "huume", None

    async def submit(connect, **kw):
        state["submit_kw"] = {**kw, "connect": connect}
        case = {"id": uuid4(), "case_number": "HRC-3",
                "review": {"blocks": [{"detail": "Protected sick leave on 9/3."}]}}
        view = {"review": {"notes": [{"detail": "No signature line."}]}}
        return {"status": state["submit"]["status"], "case": case, "manager_view": view}

    async def decide(conn, **kw):
        state["decide_kw"] = kw
        return {"id": uuid4(), "case_number": "HRC-3"}

    async def deliver(conn, **kw):
        state["deliver_kw"] = kw
        return {"id": uuid4(), "case_number": "HRC-3"}
    monkeypatch.setattr(skill, "_is_hr", is_hr)
    monkeypatch.setattr(skill, "_fetch_source", fetch_source)
    monkeypatch.setattr(workflow, "submit_draft", submit)
    monkeypatch.setattr(workflow, "decide", decide)
    monkeypatch.setattr(workflow, "mark_delivered", deliver)
    return state


@pytest.mark.asyncio
async def test_execute_draft_submitted(exec_env):
    out = await skill.execute(company_id=COMPANY, actor_user_id=USER, action=evaluate(draft()).action)
    assert out["status"] == "created" and "sent to HR" in out["message"] and "No signature line." in out["message"]
    assert exec_env["submit_kw"]["origin"] == "huume"
    assert exec_env["submit_kw"]["occurrence_dates"] == [date(2026, 9, 3)]
    from app import database
    assert exec_env["submit_kw"]["connect"] is database.get_connection  # not a held connection


@pytest.mark.asyncio
async def test_execute_draft_storage_and_drive_errors_are_refusals(exec_env, monkeypatch):
    from app.matcha.services.drive.drive_service import DriveError

    async def unreadable(conn, **kw):
        raise DriveError(502, "I couldn't read that attachment again.")
    monkeypatch.setattr(skill, "_fetch_source", unreadable)
    out = await skill.execute(company_id=COMPANY, actor_user_id=USER, action=evaluate(draft()).action)
    assert out == {"status": "refused", "message": "I couldn't read that attachment again."}


@pytest.mark.asyncio
async def test_execute_held_hides_leave_detail_from_manager(exec_env):
    exec_env["submit"] = {"status": "held"}
    out = await skill.execute(company_id=COMPANY, actor_user_id=USER, action=evaluate(draft()).action)
    assert "can't go forward" in out["message"] and "sick leave" not in out["message"]
    exec_env["hr"] = True
    out = await skill.execute(company_id=COMPANY, actor_user_id=USER, action=evaluate(draft()).action)
    assert "sick leave" in out["message"]


@pytest.mark.asyncio
async def test_execute_decision_is_hr_only(exec_env):
    action = {"type": "hr_case_decision", "case_id": str(uuid4()), "decision": "approve", "reason": None}
    out = await skill.execute(company_id=COMPANY, actor_user_id=USER, action=action)
    assert out["status"] == "refused" and "decide_kw" not in exec_env
    exec_env["hr"] = True
    out = await skill.execute(company_id=COMPANY, actor_user_id=USER, action=action)
    assert out["status"] == "created" and "approved to deliver" in out["message"]


@pytest.mark.asyncio
async def test_execute_delivered_and_errors(exec_env, monkeypatch):
    from app.matcha.services.hr_cases import workflow
    from app.matcha.services.hr_cases.case_service import CaseError

    action = {"type": "hr_case_delivered", "case_id": str(uuid4()), "delivered_on": "2026-09-28"}
    out = await skill.execute(company_id=COMPANY, actor_user_id=USER, action=action)
    assert out["status"] == "created" and exec_env["deliver_kw"]["delivered_on"] == date(2026, 9, 28)

    async def refuse(conn, **kw):
        raise CaseError(409, "Can't delivered a case that is flagged.")
    monkeypatch.setattr(workflow, "mark_delivered", refuse)
    out = await skill.execute(company_id=COMPANY, actor_user_id=USER, action=action)
    assert out == {"status": "refused", "message": "Can't delivered a case that is flagged."}
    assert (await skill.execute(company_id=COMPANY, actor_user_id=USER, action={"type": "nope"}))["status"] == "error"


@pytest.mark.asyncio
async def test_fetch_source_each_kind(monkeypatch):
    from app.core.services import storage
    from app.matcha.services.drive import drive_service, google_drive_service

    async def prepare(name, data):
        return SimpleNamespace(filename=name, data=data)
    monkeypatch.setattr(drive_service, "prepare_file", prepare)

    async def download(path):
        return b"bytes"
    monkeypatch.setattr(storage, "get_storage", lambda: SimpleNamespace(download_file=download))
    prepared, source, ref = await skill._fetch_source(QueryConn(), company_id=COMPANY, user_id=USER,
                                                      action={"source": "attachment", "attachment_url": "u", "filename": "w.pdf"})
    assert (prepared.filename, source, ref) == ("w.pdf", "huume", None)

    async def load_actor(conn, *, user, company_id):
        return SimpleNamespace()

    async def read_bytes(conn, **kw):
        return {"filename": "d.docx"}, b"PK"
    monkeypatch.setattr(drive_service, "load_actor", load_actor)
    monkeypatch.setattr(drive_service, "read_file_bytes", read_bytes)
    fid = str(uuid4())
    _, source, ref = await skill._fetch_source(QueryConn(fetchval={"SELECT role": "client"}), company_id=COMPANY,
                                               user_id=USER, action={"source": "drive", "drive_file_id": fid})
    assert ref == f"drive:{fid}"

    async def fetch(self, file_id):
        return google_drive_service.GoogleFile(file_id=file_id, name="g.docx", mime_type="x", data=b"PK")
    monkeypatch.setattr(google_drive_service.GoogleDriveService, "fetch_file", fetch)
    _, source, ref = await skill._fetch_source(QueryConn(), company_id=COMPANY, user_id=USER,
                                               action={"source": "google", "google_file_id": "1AbCdEfGhIjKlMnOpQrStUv"})
    assert (source, ref) == ("google_drive", "1AbCdEfGhIjKlMnOpQrStUv")


@pytest.mark.asyncio
async def test_fetch_source_unreadable_attachment_is_a_drive_error(monkeypatch):
    from app.core.services import storage
    from app.matcha.services.drive.drive_service import DriveError

    async def download(path):
        raise RuntimeError("Failed to download from S3: NoSuchKey")
    monkeypatch.setattr(storage, "get_storage", lambda: SimpleNamespace(download_file=download))
    with pytest.raises(DriveError) as exc:
        await skill._fetch_source(QueryConn(), company_id=COMPANY, user_id=USER,
                                  action={"source": "attachment", "attachment_url": "u", "filename": "w.pdf"})
    assert exc.value.status == 502 and "attachment" in exc.value.detail


# ── Through the loop ────────────────────────────────────────────────────

from unittest.mock import AsyncMock, MagicMock

from app.matcha.services.huume import agent
from app.matcha.services.huume.luna_client import LunaResponse


class _NoopRateLimiter:
    def __init__(self, *a, **k):
        pass

    async def check_limit(self, *a, **k):
        return None

    async def record_call(self, *a, **k):
        return None


def _response(calls=None, text=None):
    return LunaResponse(
        response_id="resp", text=text,
        function_calls=[{"call_id": f"c{i}", "name": n, "arguments": a} for i, (n, a) in enumerate(calls or [])],
        usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    )


async def _turn(monkeypatch, calls, *, current_state=None, attachment_refs=None, client_out=None):
    client = MagicMock()
    if client_out is not None:
        client_out.append(client)
    client.create_response = AsyncMock(side_effect=[_response(calls=calls), _response(text="Done.")])
    monkeypatch.setattr(agent, "get_luna_client", lambda: client)
    monkeypatch.setattr(agent, "ApiRateLimiter", _NoopRateLimiter)
    frames = [f async for f in agent.run_huume_turn(
        thread_id=uuid4(), company_id=COMPANY, user_id=USER, user_role="client",
        history=[{"role": "user", "content": "here's the write-up for Jane"}],
        company_name="Po Coffee", current_state=current_state or {}, features=FEATURES, integrations={},
        attachment_refs=attachment_refs,
    )]
    return next(f["data"] for f in frames if f["type"] == "huume_result")


@pytest.mark.asyncio
async def test_loop_stages_write_up_with_pinned_source(monkeypatch):
    seen = {}

    async def resolve(*, company_id, args, attachment_refs):
        seen["refs"] = attachment_refs
        return {"status": "ok", "source": "attachment", "attachment_url": "https://cdn/w.pdf",
                "filename": "w.pdf", "employee_id": EMP, "employee_name": "Jane Doe"}
    monkeypatch.setattr(skill, "resolve_draft_args", resolve)
    result = await _turn(monkeypatch, [("submit_write_up", {
        "employee_name": "Jane", "action_type": "written_warning", "infraction_type": "attendance",
        "occurrence_dates": ["2026-09-03"], "attachment_index": 0,
    })], attachment_refs=REFS)
    staged = result["state_updates"]["huume_action"]
    assert staged["type"] == "hr_case_draft" and staged["status"] == "proposed"
    assert staged["attachment_url"] == "https://cdn/w.pdf" and staged["confirm_id"]
    assert seen["refs"] == REFS


@pytest.mark.asyncio
async def test_loop_refuses_unresolvable_write_up(monkeypatch):
    async def resolve(**kw):
        return {"status": "refused", "message": "Who is the write-up for?"}
    monkeypatch.setattr(skill, "resolve_draft_args", resolve)
    result = await _turn(monkeypatch, [("submit_write_up", {"action_type": "written_warning", "infraction_type": "attendance"})])
    assert ("submit_write_up", "rejected") in [(s["tool"], s["status"]) for s in result["steps"]]
    assert "huume_action" not in result["state_updates"]


@pytest.mark.asyncio
async def test_loop_hands_the_model_candidate_ids_on_an_ambiguous_name(monkeypatch):
    pick = str(uuid4())

    async def resolve(**kw):
        return {"status": "refused", "message": "More than one employee matches.",
                "candidates": [{"employee_id": pick, "name": "Sam Lee", "job_title": None}]}
    monkeypatch.setattr(skill, "resolve_draft_args", resolve)
    clients = []
    await _turn(monkeypatch, [("submit_write_up", {"employee_name": "Sam", "action_type": "written_warning",
                                                   "infraction_type": "attendance", "occurrence_dates": ["2026-09-03"]})],
                client_out=clients)
    follow_up = clients[0].create_response.await_args_list[1]
    assert pick in str(follow_up)


@pytest.mark.asyncio
async def test_loop_refuses_decision_from_non_hr(monkeypatch, conn):
    async def not_hr(conn, **kw):
        return False
    monkeypatch.setattr(skill, "_is_hr", not_hr)
    result = await _turn(monkeypatch, [("decide_write_up", {"case_id": str(uuid4()), "decision": "approve"})])
    assert ("decide_write_up", "rejected") in [(s["tool"], s["status"]) for s in result["steps"]]


@pytest.mark.asyncio
async def test_loop_read_tools(monkeypatch):
    async def listing(**kw):
        return {"status": "ok", "view": "manager", "cases": []}

    async def search(**kw):
        return {"status": "module_off", "message": "Matcha Drive isn't enabled for this company."}

    async def read(**kw):
        return {"status": "ok", "text": "t"}
    monkeypatch.setattr(skill, "list_write_ups", listing)
    monkeypatch.setattr(skill, "search_drive", search)
    monkeypatch.setattr(skill, "read_drive_file", read)
    result = await _turn(monkeypatch, [
        ("list_write_ups", {}), ("search_drive", {"query": "policy"}), ("read_drive_file", {"drive_file_id": "x"}),
    ])
    statuses = [(s["tool"], s["status"]) for s in result["steps"]]
    assert ("list_write_ups", "ok") in statuses
    assert ("search_drive", "rejected") in statuses
    assert ("read_drive_file", "ok") in statuses


# ── Signed copy ─────────────────────────────────────────────────────────


def test_resolve_signed_args():
    cid = str(uuid4())
    assert skill.resolve_signed_args(args={"case_id": "x"}, attachment_refs=REFS)["status"] == "refused"
    assert skill.resolve_signed_args(args={"case_id": cid}, attachment_refs=REFS)["status"] == "refused"
    assert skill.resolve_signed_args(args={"case_id": cid, "attachment_index": 3}, attachment_refs=REFS)["status"] == "refused"
    assert skill.resolve_signed_args(args={"case_id": cid, "attachment_index": "a"}, attachment_refs=REFS)["status"] == "refused"
    assert skill.resolve_signed_args(args={"case_id": cid, "attachment_index": 1}, attachment_refs=REFS) == {
        "status": "ok", "source": "attachment", "attachment_url": "https://cdn/old.pdf", "filename": "old.pdf"}
    assert skill.resolve_signed_args(args={"case_id": cid, "drive_file_id": "d"}, attachment_refs=[]) == {
        "status": "ok", "source": "drive", "drive_file_id": "d"}


def test_signed_validator_and_state_block():
    cid = str(uuid4())
    staged = {"type": "hr_case_signed", "status": "proposed", "case_id": cid, "source": "attachment",
              "attachment_url": "https://cdn/s.pdf", "filename": "s.pdf", "confirm_id": "zz"}
    ok = evaluate(staged)
    assert ok.ok and ok.action["attachment_url"] == "https://cdn/s.pdf"
    assert not evaluate({**staged, "source": "google", "google_file_id": "g"}).ok
    assert not evaluate({**staged, "case_id": "x"}).ok
    block = build_state_block({"huume_action": staged})
    assert "confirm_id=zz" in block and f"case_id={cid}" in block and "s.pdf" in block


@pytest.mark.asyncio
async def test_execute_signed_files_and_queues_check(exec_env, monkeypatch):
    from app.matcha.services.hr_cases import workflow

    async def fetch_bytes(conn, **kw):
        return "s.pdf", b"%PDF", "huume", None

    async def upload(conn, **kw):
        exec_env["upload_kw"] = kw
        return {"case": {"id": uuid4(), "case_number": "HRC-3"}, "mime_type": "application/pdf"}
    spawned = {}

    def spawn(**kw):
        spawned.update(kw)
    monkeypatch.setattr(skill, "_fetch_bytes", fetch_bytes)
    monkeypatch.setattr(workflow, "upload_signed", upload)
    monkeypatch.setattr(workflow, "spawn_signed_check", spawn)
    action = {"type": "hr_case_signed", "case_id": str(uuid4()), "source": "attachment", "attachment_url": "u"}
    out = await skill.execute(company_id=COMPANY, actor_user_id=USER, action=action)
    assert out["status"] == "created" and "checking it now" in out["message"]
    # Detached, so the reply doesn't wait out the model read (bg_tasks run inline).
    assert "bg_tasks" not in out
    assert spawned["data"] == b"%PDF" and spawned["mime_type"] == "application/pdf"
    assert exec_env["upload_kw"]["filename"] == "s.pdf"


@pytest.mark.asyncio
async def test_loop_stages_signed_copy(monkeypatch):
    cid = str(uuid4())
    result = await _turn(monkeypatch, [("file_signed_write_up", {"case_id": cid, "attachment_index": 0})],
                         attachment_refs=REFS)
    staged = result["state_updates"]["huume_action"]
    assert staged["type"] == "hr_case_signed" and staged["attachment_url"] == "https://cdn/new.pdf"
    result = await _turn(monkeypatch, [("file_signed_write_up", {"case_id": cid})], attachment_refs=[])
    assert ("file_signed_write_up", "rejected") in [(s["tool"], s["status"]) for s in result["steps"]]
