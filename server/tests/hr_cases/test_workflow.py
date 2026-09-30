"""Write-up workflow: who may act, submitted vs held, HR decisions (with the
approval-time leave recheck), delivery dates, and the manager's redacted view.

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_workflow.py -q
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.services.hr_cases import case_service, draft_review, notifications, workflow
from app.matcha.services.hr_cases.case_service import CaseError
from tests._helpers.routes import QueryConn

COMPANY = uuid4()
GM = uuid4()
OTHER = uuid4()
EMPLOYEE = uuid4()


def case(**kw):
    base = {
        "id": uuid4(), "company_id": COMPANY, "case_number": "HRC-2026-0001", "stage": "flagged",
        "stage_label": "Flagged", "checklist": [], "gm_user_id": GM, "source_incident_id": uuid4(),
        "incident_number": "IR-1", "incident_title": "Late", "employee_id": None, "employee_name": None,
        "action_type": None, "triage": {"violations": [{"policy_title": "Attendance policy"}]},
        "review": None, "decision": None, "decision_reason": None, "decided_at": None,
        "delivered_at": None, "draft_file_id": None, "updated_at": None,
    }
    base.update(kw)
    return base


def prepared(status="ok", text="letter text"):
    return SimpleNamespace(text_status=status, extracted_text=text if status == "ok" else None, filename="w.pdf")


@pytest.fixture
def env(monkeypatch):
    state = {"case": case(), "review": {"blocks": [], "advisories": [], "compliance": {}}, "steps": [],
             "events": [], "sets": [], "opened": []}

    async def get_case(conn, *, company_id, case_id, with_events=False):
        return state["case"]

    async def find_open(conn, *, company_id, incident_id):
        return state.get("existing")

    async def open_case(conn, **kw):
        state["opened"].append(kw)
        return state["case"], True

    async def set_fields(conn, **kw):
        state["sets"].append(kw)

    async def apply_event(conn, *, company_id, case_id, event, actor_user_id, sets=None, details=None):
        state["events"].append((event, sets or {}))
        return {**state["case"], "stage": {"draft_submitted": "hr_review", "approve": "approved",
                                            "request_changes": "changes_requested", "delivered": "delivered",
                                            "signed_uploaded": "verifying", "acknowledge": "closed"}[event]}

    async def review(conn, **kw):
        state["review_kw"] = kw
        return dict(state["review"])

    async def store(conn, **kw):
        return {"id": uuid4()}

    async def notify(conn, *, case, step, actor_user_id, reason=None):
        state["steps"].append((step, reason))

    monkeypatch.setattr(case_service, "get_case", get_case)
    monkeypatch.setattr(case_service, "find_open_case_for_incident", find_open)
    monkeypatch.setattr(case_service, "open_case", open_case)
    monkeypatch.setattr(case_service, "set_fields", set_fields)
    monkeypatch.setattr(case_service, "apply_event", apply_event)
    monkeypatch.setattr(draft_review, "review_draft", review)
    monkeypatch.setattr(workflow, "store_draft_file", store)
    monkeypatch.setattr(notifications, "notify_step", notify)
    return state


def conn_for(employee=True, incident=True):
    return QueryConn(
        fetchrow={"FROM employees": {"id": EMPLOYEE, "name": "Jane Doe"} if employee else None},
        fetchval={"FROM ir_incidents WHERE id = $1 AND company_id": 1 if incident else None,
                  "SELECT description FROM ir_incidents": "account"},
    )


async def submit(conn, **overrides):
    kw = dict(company_id=COMPANY, actor_user_id=GM, actor_is_hr=False, prepared=prepared(),
              employee_id=EMPLOYEE, action_type="written_warning", infraction_type="attendance",
              occurrence_dates=[date(2026, 9, 3)], case_id=uuid4())
    kw.update(overrides)
    return await workflow.submit_draft(conn, **kw)


@pytest.mark.asyncio
async def test_submit_passes_to_hr(env):
    out = await submit(conn_for())
    assert out["status"] == "submitted"
    event, sets = env["events"][0]
    assert event == "draft_submitted" and sets["employee_id"] == EMPLOYEE and sets["action_type"] == "written_warning"
    assert sets["review"]["input"]["occurrence_dates"] == ["2026-09-03"]
    assert env["steps"] == [("draft_submitted", None)]
    assert env["review_kw"]["policy_titles"] == ["Attendance policy"]
    assert env["review_kw"]["incident_account"] == "account"


@pytest.mark.asyncio
async def test_blocked_draft_is_held_without_stage_change(env):
    env["review"] = {"blocks": [{"code": "protected_leave_overlap", "detail": "x"}], "advisories": []}
    out = await submit(conn_for())
    assert out["status"] == "held"
    assert env["events"] == []
    assert env["sets"][0]["event"] == "draft_held"
    assert env["steps"] == [("draft_held", None)]


@pytest.mark.asyncio
async def test_other_manager_cannot_submit_on_someone_elses_case(env):
    with pytest.raises(CaseError) as exc:
        await submit(conn_for(), actor_user_id=OTHER)
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_hr_can_submit_on_any_case(env):
    assert (await submit(conn_for(), actor_user_id=OTHER, actor_is_hr=True))["status"] == "submitted"


@pytest.mark.asyncio
@pytest.mark.parametrize("override,status", [
    ({"action_type": "firing"}, 400),
    ({"infraction_type": "vibes"}, 400),
    ({"prepared": prepared(status="empty")}, 400),
])
async def test_submit_input_errors(env, override, status):
    with pytest.raises(CaseError) as exc:
        await submit(conn_for(), **override)
    assert exc.value.status == status


@pytest.mark.asyncio
async def test_submit_unknown_employee(env):
    with pytest.raises(CaseError) as exc:
        await submit(conn_for(employee=False))
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_submit_refused_once_with_hr(env):
    env["case"] = case(stage="hr_review", stage_label="HR review")
    with pytest.raises(CaseError) as exc:
        await submit(conn_for())
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_new_draft_opens_case_with_sender_as_manager(env):
    await submit(conn_for(), case_id=None, incident_id=uuid4())
    assert env["opened"][0]["gm_user_id"] == GM and env["opened"][0]["origin"] == "gm_draft"


@pytest.mark.asyncio
async def test_draft_for_flagged_case_without_manager_claims_it(env):
    env["existing"] = case(gm_user_id=None)
    await submit(conn_for(), case_id=None, incident_id=uuid4(), actor_user_id=OTHER)
    assert env["sets"][0]["sets"] == {"gm_user_id": OTHER}


@pytest.mark.asyncio
async def test_draft_for_unknown_incident(env):
    with pytest.raises(CaseError) as exc:
        await submit(conn_for(incident=False), case_id=None, incident_id=uuid4())
    assert exc.value.status == 404


# ── Decisions ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_changes_needs_a_real_reason(env):
    with pytest.raises(CaseError):
        await workflow.decide(QueryConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER,
                              decision="request_changes", reason="fix it")
    await workflow.decide(QueryConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER,
                          decision="request_changes", reason="Add the dates of each late arrival.")
    assert env["events"][0][0] == "request_changes"
    assert env["steps"] == [("changes_requested", "Add the dates of each late arrival.")]


@pytest.mark.asyncio
async def test_approve_rechecks_leave(env, monkeypatch):
    from app.matcha.services.discipline import discipline_compliance

    env["case"] = case(stage="hr_review", employee_id=EMPLOYEE,
                       review={"input": {"infraction_type": "attendance", "occurrence_dates": ["2026-09-03"]}})
    seen = {}

    async def gate(conn, **kw):
        seen.update(kw)
        return {"blocks": [{"code": "protected_leave_overlap"}]}
    monkeypatch.setattr(discipline_compliance, "check_discipline_compliance", gate)
    with pytest.raises(CaseError) as exc:
        await workflow.decide(QueryConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER,
                              decision="approve", reason=None)
    assert exc.value.status == 409
    assert seen["occurrence_dates"] == [date(2026, 9, 3)]
    assert env["events"] == []

    async def clean(conn, **kw):
        return {"blocks": []}
    monkeypatch.setattr(discipline_compliance, "check_discipline_compliance", clean)
    out = await workflow.decide(QueryConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER,
                                decision="approve", reason="Looks right")
    assert out["stage"] == "approved"
    assert env["events"][0][1]["decision"] == "approved"
    assert env["steps"] == [("approved", None)]


@pytest.mark.asyncio
async def test_unknown_decision(env):
    with pytest.raises(CaseError):
        await workflow.decide(QueryConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER,
                              decision="shrug", reason=None)


# ── Delivery ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manager_marks_delivered(env):
    env["case"] = case(stage="approved", decided_at=datetime.now(timezone.utc) - timedelta(days=2))
    out = await workflow.mark_delivered(QueryConn(), company_id=COMPANY, case_id=uuid4(),
                                        actor_user_id=GM, actor_is_hr=False,
                                        delivered_on=date.today() - timedelta(days=1))
    assert out["stage"] == "delivered"
    assert env["events"][0][1]["delivered_at"].hour == 12
    assert env["steps"] == [("delivered", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize("delivered_on", [date.today() + timedelta(days=1), date.today() - timedelta(days=10)])
async def test_delivery_date_bounds(env, delivered_on):
    env["case"] = case(stage="approved", decided_at=datetime.now(timezone.utc) - timedelta(days=2))
    with pytest.raises(CaseError):
        await workflow.mark_delivered(QueryConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=GM,
                                      actor_is_hr=False, delivered_on=delivered_on)


@pytest.mark.asyncio
async def test_stranger_cannot_mark_delivered(env):
    with pytest.raises(CaseError) as exc:
        await workflow.mark_delivered(QueryConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER,
                                      actor_is_hr=False)
    assert exc.value.status == 404


# ── Manager view + helpers ──────────────────────────────────────────────


def test_manager_view_redacts_hr_internals():
    view = workflow.manager_view(case(
        stage="changes_requested", decision="changes_requested", decision_reason="Add dates",
        triage={"violations": [{"policy_title": "secret"}]},
        review={"blocks": [], "advisories": [{"source": "compliance", "code": "x", "detail": "FMLA"}]},
    ))
    assert "triage" not in view and "FMLA" not in str(view) and "secret" not in str(view)
    assert view["decision_reason"] == "Add dates" and view["can_submit_draft"] is True
    approved = workflow.manager_view(case(stage="approved", decision="approved", decision_reason="internal note"))
    assert approved["decision_reason"] is None and approved["can_mark_delivered"] is True


def test_parse_occurrence_dates():
    assert workflow.parse_occurrence_dates(["2026-09-03", " ", "2026-09-01", "2026-09-03"]) == [date(2026, 9, 1), date(2026, 9, 3)]
    for bad in (["9/3"], [(date.today() + timedelta(days=1)).isoformat()], ["2026-01-01"] * 0 + [f"2026-01-{d:02d}" for d in range(1, 32)]):
        with pytest.raises(CaseError):
            workflow.parse_occurrence_dates(bad)


@pytest.mark.asyncio
async def test_list_for_manager_scopes_to_self():
    conn = QueryConn(fetch={"FROM hr_cases c": []})
    assert await workflow.list_for_manager(conn, company_id=COMPANY, user_id=GM) == []
    assert conn.args_for("FROM hr_cases c") == (COMPANY, GM)


@pytest.mark.asyncio
async def test_store_draft_file_goes_to_hr_drafts_via_system_path(monkeypatch):
    from app.matcha.services.drive import drive_service

    drafts = uuid4()

    async def seeded(conn, company_id):
        return {"hr_discipline_drafts": drafts}
    seen = {}

    async def store(conn, **kw):
        seen.update(kw)
        return {"id": uuid4()}
    monkeypatch.setattr(drive_service, "ensure_system_folders", seeded)
    monkeypatch.setattr(drive_service, "store_file", store)
    await workflow.store_draft_file(QueryConn(), company_id=COMPANY, case_number="HRC-2026-0002",
                                    prepared=prepared(), uploaded_by=GM)
    assert seen["folder_id"] == drafts and seen["actor"] is None
    assert seen["filename"] == "HRC-2026-0002 - draft - w.pdf"


# ── Signed copy ─────────────────────────────────────────────────────────


@pytest.fixture
def signed_env(env, monkeypatch):
    from app.matcha.services.drive import drive_service
    from app.matcha.services.hr_cases import verification

    env["case"] = case(stage="delivered", stage_label="Delivered", allowed_events=["signed_uploaded"],
                       employee_id=EMPLOYEE, action_type="written_warning",
                       delivered_at=datetime(2026, 9, 28, tzinfo=timezone.utc))
    folder = uuid4()

    async def ensure(conn, **kw):
        return folder

    async def prepare(name, data):
        return SimpleNamespace(filename=name)

    async def store(conn, **kw):
        env["stored"] = kw
        return {"id": uuid4()}

    async def settings(conn, company_id):
        return {"filename_template": "{last_name}_{case_number}"}
    monkeypatch.setattr(verification, "ensure_employee_folder", ensure)
    monkeypatch.setattr(drive_service, "prepare_file", prepare)
    monkeypatch.setattr(drive_service, "store_file", store)
    monkeypatch.setattr(case_service, "get_settings", settings)
    env["folder"] = folder
    return env


def signed_conn():
    return QueryConn(fetchrow={"FROM employees": {"first_name": "Jane", "last_name": "Doe"}})


@pytest.mark.asyncio
async def test_upload_signed_files_under_template(signed_env):
    out = await workflow.upload_signed(signed_conn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=GM,
                                       actor_is_hr=False, filename="IMG_0042.JPG", data=b"jpeg")
    assert out["mime_type"] == "image/jpeg"
    stored = signed_env["stored"]
    assert stored["filename"] == "Doe_HRC-2026-0001.jpg"
    assert stored["folder_id"] == signed_env["folder"] and stored["actor"] is None
    assert stored["linked_type"] == "hr_case"
    assert signed_env["events"][0][0] == "signed_uploaded"


@pytest.mark.asyncio
async def test_upload_signed_refusals(signed_env):
    with pytest.raises(CaseError) as exc:
        await workflow.upload_signed(signed_conn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=GM,
                                     actor_is_hr=False, filename="letter.docx", data=b"x")
    assert exc.value.status == 400
    with pytest.raises(CaseError) as exc:
        await workflow.upload_signed(signed_conn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER,
                                     actor_is_hr=False, filename="s.pdf", data=b"%PDF")
    assert exc.value.status == 404
    signed_env["case"] = case(stage="approved", stage_label="Approved to deliver", allowed_events=["delivered"])
    with pytest.raises(CaseError) as exc:
        await workflow.upload_signed(signed_conn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=GM,
                                     actor_is_hr=False, filename="s.pdf", data=b"%PDF")
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_upload_signed_maps_drive_errors(signed_env, monkeypatch):
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.drive_service import DriveError

    async def boom(conn, **kw):
        raise DriveError(503, "File storage isn't configured.")
    monkeypatch.setattr(drive_service, "store_file", boom)
    with pytest.raises(CaseError) as exc:
        await workflow.upload_signed(signed_conn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=GM,
                                     actor_is_hr=True, filename="s.pdf", data=b"%PDF")
    assert exc.value.status == 503


@pytest.mark.asyncio
async def test_check_signed_and_notify_never_raises(monkeypatch):
    from contextlib import asynccontextmanager

    from app import database
    from app.matcha.services.hr_cases import verification

    @asynccontextmanager
    async def get_connection(*a, **k):
        yield QueryConn()
    monkeypatch.setattr(database, "get_connection", get_connection)
    seen = []

    async def run_check(conn, **kw):
        return {"id": "c1", "stage": "closed"}

    async def notify(conn, *, case, actor_user_id):
        seen.append(case["stage"])
    monkeypatch.setattr(verification, "run_check", run_check)
    monkeypatch.setattr(notifications, "notify_signed", notify)
    await workflow.check_signed_and_notify(company_id=COMPANY, case_id=uuid4(), data=b"x",
                                           mime_type="application/pdf", actor_user_id=GM)
    assert seen == ["closed"]

    async def broken(conn, **kw):
        raise RuntimeError("model down")
    monkeypatch.setattr(verification, "run_check", broken)
    await workflow.check_signed_and_notify(company_id=COMPANY, case_id=uuid4(), data=b"x",
                                           mime_type="application/pdf", actor_user_id=GM)


@pytest.mark.asyncio
async def test_recheck_and_acknowledge(env, monkeypatch):
    from app.core.services import storage
    from app.matcha.services.hr_cases import verification

    async def download(path):
        return b"%PDF"
    monkeypatch.setattr(storage, "get_storage", lambda: SimpleNamespace(download_file=download))

    async def run_check(conn, **kw):
        env["check_kw"] = kw
        return {"id": "c1", "stage": "closed"}

    async def notify(conn, **kw):
        env["notified"] = True
    monkeypatch.setattr(verification, "run_check", run_check)
    monkeypatch.setattr(notifications, "notify_signed", notify)

    env["case"] = case(stage="delivered")
    with pytest.raises(CaseError):
        await workflow.recheck_signed(QueryConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER)
    env["case"] = case(stage="needs_attention", signed_file_id=uuid4())
    with pytest.raises(CaseError) as exc:
        await workflow.recheck_signed(QueryConn(fetchrow={"FROM drive_files": None}), company_id=COMPANY,
                                      case_id=uuid4(), actor_user_id=OTHER)
    assert exc.value.status == 404
    conn = QueryConn(fetchrow={"FROM drive_files": {"filename": "s.png", "storage_path": "s3://b/k", "content_type": "image/png"}})
    out = await workflow.recheck_signed(conn, company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER)
    assert out["stage"] == "closed" and env["check_kw"]["mime_type"] == "image/png" and env["notified"]
    assert env["events"][-1][0] == "signed_uploaded"

    await workflow.acknowledge(QueryConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=OTHER)
    assert env["events"][-1][0] == "acknowledge" and "attention_acknowledged_at" in env["events"][-1][1]


def test_manager_signed_check_only_shows_fixable_problems():
    assert workflow.manager_signed_check(case()) is None
    view = workflow.manager_signed_check(case(verification={"outcome": "needs_attention",
                                                            "reasons": ["employee_signature_missing", "employee_comments"]}))
    assert view == {"outcome": "fix_needed", "problems": ["There's no employee signature on it."]}
    view = workflow.manager_signed_check(case(verification={"outcome": "needs_attention", "reasons": ["employee_comments"]}))
    assert view == {"outcome": "with_hr", "problems": []}
    assert workflow.manager_signed_check(case(verification={"outcome": "verified", "reasons": []}))["outcome"] == "verified"
    assert "signed_check" in workflow.manager_view(case())
