"""HR actions, human classification, suggestions and stale/revoked writes.

All collaborators use fake connections; no database or model is called.
"""
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.matcha.models.hr_cases import PolicyViolationReview
from app.matcha.services.hr_cases import case_service, draft_review, incident_review as svc, notifications, workflow
from app.matcha.services.hr_cases.case_service import CaseError
from tests._helpers.routes import QueryConn

COMPANY, CASE, EMPLOYEE, INCIDENT = (uuid4() for _ in range(4))
USER = SimpleNamespace(id=uuid4(), role="client", email="hr@example.test")
WHEN = datetime(2026, 9, 29, tzinfo=timezone.utc)


def body(**kw):
    return PolicyViolationReview.model_validate({
        "classification": "policy_violation", "employee_id": EMPLOYEE,
        "action_type": "written_warning", "infraction_type": "attendance",
        "occurrence_dates": ["2026-09-03"], **kw,
    })


class Conn(QueryConn):
    def transaction(self):
        return self


@pytest.fixture
def env(monkeypatch):
    state = {
        "case": {"id": CASE, "company_id": COMPANY, "case_number": "HRC-2026-0001",
                 "source_incident_id": INCIDENT, "stage": "flagged", "stage_label": "Flagged",
                 "gm_user_id": uuid4(), "draft_file_id": None, "review": None,
                 "triage": {"violations": [{"policy_title": "Attendance"}]}, "updated_at": WHEN},
        "employee": {"id": EMPLOYEE, "first_name": "Test", "last_name": "Employee", "name": "Test Employee"},
        "incident": {"id": INCIDENT, "incident_number": "IR-1", "title": "Attendance report",
                     "description": "Reported conduct", "updated_at": WHEN},
        "hr": True, "open": 0, "events": [], "writes": [], "gates": 0, "models": 0,
    }
    conn = Conn(
        fetchrow={"SELECT id FROM hr_cases": {"id": CASE}},
        fetchval={"SELECT description FROM ir_incidents": "Reported conduct"},
        fetch={"UPDATE drive_files f": []},
    )
    original_fetchrow = conn.fetchrow

    async def fetchrow(sql, *args):
        if "FROM employees" in sql:
            assert args == (EMPLOYEE, COMPANY)
            return state["employee"]
        if "FROM ir_incidents" in sql:
            assert args == (INCIDENT, COMPANY)
            return dict(state["incident"]) if state["incident"] else None
        return await original_fetchrow(sql, *args)

    conn.fetchrow = fetchrow

    @asynccontextmanager
    async def connect():
        state["open"] += 1
        try:
            yield conn
        finally:
            state["open"] -= 1

    async def hr(*a, **kw):
        return state["hr"]

    async def get_case(conn, **kw):
        assert kw["company_id"] == COMPANY and kw["case_id"] == CASE
        return dict(state["case"])

    async def sets(conn, **kw):
        state["writes"].append(kw)
        state["case"].update(kw["sets"])
        state["case"]["updated_at"] += timedelta(seconds=1)
        if kw.get("event"):
            state["events"].append(kw["event"])

    async def apply(conn, **kw):
        from app.matcha.services.hr_cases.stages import next_stage
        state["case"]["stage"] = next_stage(state["case"]["stage"], kw["event"])
        state["case"].update(kw.get("sets") or {})
        state["events"].append(kw["event"])
        return dict(state["case"])

    async def gate(conn, **kw):
        state["gates"] += 1
        assert kw["employee_id"] == EMPLOYEE and kw["company_id"] == COMPANY
        assert kw["occurrence_dates"] == [date(2026, 9, 3)]
        blocked = state.get("block") or state.get("block_at") == state["gates"]
        return {"checked_at": WHEN.isoformat(), "blocks": [{"detail": "Protected sick leave (CA 246.5)."}] if blocked else [],
                "advisories": [{"code": "timing", "detail": "Check timing", "source": "ir_incident"}]}

    async def letter(**kw):
        assert state["open"] == 0
        state["models"] += 1
        if state.get("during_model"):
            state["during_model"]()
        return "Test Employee, 2026-09-03. Reported conduct. Expected improvement. Acknowledgment and signature."

    monkeypatch.setattr(svc, "has_hr_access", hr)
    monkeypatch.setattr(svc, "check_discipline_compliance", gate)
    monkeypatch.setattr(svc, "draft_letter", letter)
    monkeypatch.setattr(case_service, "get_case", get_case)
    monkeypatch.setattr(case_service, "set_fields", sets)
    monkeypatch.setattr(case_service, "apply_event", apply)
    monkeypatch.setattr(notifications, "send_step", AsyncMock())
    state.update(connect=connect, conn=conn)
    return state


async def suggest(env, **kw):
    return await svc.suggest(env["connect"], company_id=COMPANY, case_id=CASE, user=USER, body=body(**kw))


@pytest.mark.asyncio
async def test_confirmed_violation_drafts_without_issuing(env):
    case = await suggest(env)
    assert case["stage"] == "drafting" and not case["draft_file_id"]
    assert env["events"] == ["policy_violation_confirmed", "start_draft"]
    assert env["gates"] == 2 and env["models"] == 1
    assert case["review"]["suggestion"]["input"]["classification"] == "policy_violation"
    assert case["review"]["advisories"][0]["source"] == "compliance"
    assert env["writes"][0]["require_stages"] == ("flagged", "drafting")


@pytest.mark.parametrize("classification", [None, "not_a_violation", "likely_violation", "clean"])
def test_non_violation_cannot_trigger_a_draft(classification):
    with pytest.raises(ValidationError):
        body(classification=classification)


@pytest.mark.asyncio
async def test_duplicate_returns_same_suggestion_and_different_basis_refuses(env):
    first = await suggest(env)
    second = await suggest(env)
    assert first["review"]["suggestion"]["id"] == second["review"]["suggestion"]["id"]
    assert env["models"] == 1
    with pytest.raises(CaseError, match="Dismiss the current suggestion"):
        await suggest(env, action_type="suspension")


@pytest.mark.asyncio
@pytest.mark.parametrize("at,models", [(1, 0), (2, 1)])
async def test_gate_blocks_before_generation_and_before_persistence(env, at, models):
    env["block_at"] = at
    with pytest.raises(CaseError) as exc:
        await suggest(env)
    assert exc.value.status == 422 and "CA 246.5" in exc.value.detail
    assert env["writes"] == [] and env["events"] == [] and env["models"] == models


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,status", [("case", 409), ("incident", 409), ("access", 404)])
async def test_changed_inputs_or_revoked_access_during_model_cannot_write(env, kind, status):
    def change():
        if kind == "access":
            env["hr"] = False
        else:
            env[kind]["updated_at"] += timedelta(seconds=1)
    env["during_model"] = change
    with pytest.raises(CaseError) as exc:
        await suggest(env)
    assert exc.value.status == status and env["writes"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,status", [("employee", 404), ("incident", 404), ("hr", 404)])
async def test_missing_tenant_data_or_access(env, kind, status):
    env[kind] = None
    with pytest.raises(CaseError) as exc:
        await suggest(env)
    assert exc.value.status == status and env["models"] == 0


@pytest.mark.asyncio
async def test_terminal_or_already_submitted_cases_and_future_dates_refuse(env):
    env["case"]["stage"] = "dismissed"
    with pytest.raises(CaseError) as exc:
        await suggest(env)
    assert exc.value.status == 409
    env["case"]["stage"] = "flagged"
    with pytest.raises(CaseError) as exc:
        await suggest(env, occurrence_dates=["2099-01-01"])
    assert exc.value.status == 400 and env["models"] == 0


@pytest.mark.asyncio
async def test_start_uses_existing_transition_and_notifies_after_releasing_connection(env, monkeypatch):
    async def send(**kw):
        assert env["open"] == 0 and kw["step"] == "start_draft"
    monkeypatch.setattr(notifications, "send_step", send)
    out = await svc.start_draft(env["connect"], company_id=COMPANY, case_id=CASE, user=USER)
    assert out["stage"] == "drafting" and env["events"] == ["start_draft"]
    env["case"]["gm_user_id"] = None
    with pytest.raises(CaseError, match="No manager"):
        await svc.start_draft(env["connect"], company_id=COMPANY, case_id=CASE, user=USER)


@pytest.mark.asyncio
async def test_dismiss_only_suggestion_preserves_case_and_records_reason(env):
    case = await suggest(env)
    sid = case["review"]["suggestion"]["id"]
    out = await svc.dismiss_suggestion(env["connect"], company_id=COMPANY, case_id=CASE, user=USER,
                                       suggestion_id=sid, reason="Prefer a manager-written letter.")
    assert out["stage"] == "drafting" and "suggestion" not in out["review"]
    assert out["review"]["advisories"] and env["events"][-1] == "suggestion_dismissed"
    with pytest.raises(CaseError) as exc:
        await svc.dismiss_suggestion(env["connect"], company_id=COMPANY, case_id=CASE, user=USER,
                                     suggestion_id=sid, reason="Prefer a manager-written letter.")
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_accept_edited_letter_uses_full_existing_review_and_separate_approval(env, monkeypatch):
    from app.matcha.services.drive import drive_service

    case = await suggest(env)
    sid = case["review"]["suggestion"]["id"]
    monkeypatch.setattr(workflow, "store_draft_file", AsyncMock(return_value={"id": uuid4()}))
    monkeypatch.setattr(draft_review, "review_draft", AsyncMock(return_value={"blocks": [], "advisories": []}))
    monkeypatch.setattr(draft_review, "ai_wording_review", AsyncMock(return_value=[]))
    monkeypatch.setattr(notifications, "step_recipients", AsyncMock(return_value=[]))
    monkeypatch.setattr(drive_service, "prepare_file", AsyncMock(return_value=SimpleNamespace(
        text_status="ok", extracted_text="Edited letter", filename="write-up.txt",
    )))
    out = await svc.accept_suggestion(env["connect"], company_id=COMPANY, case_id=CASE, user=USER,
                                     suggestion_id=sid, letter="Edited letter")
    assert out["stage"] == "hr_review" and out["draft_file_id"]
    assert env["events"][-1] == "draft_submitted" and "approve" not in env["events"]
    assert env["gates"] == 4  # generation + persistence + each submit connection
    assert draft_review.review_draft.await_args.kwargs["infraction_type"] == "attendance"
    assert draft_review.review_draft.await_args.kwargs["text"] == "Edited letter"
    assert workflow.store_draft_file.await_args.kwargs["source"] == "system"


@pytest.mark.asyncio
async def test_accept_rechecks_gate_and_rejects_stale_suggestion(env):
    case = await suggest(env)
    sid = case["review"]["suggestion"]["id"]
    env["block"] = True
    with pytest.raises(CaseError) as exc:
        await svc.accept_suggestion(env["connect"], company_id=COMPANY, case_id=CASE, user=USER,
                                    suggestion_id=sid, letter="Edited letter")
    assert exc.value.status == 422 and env["case"]["stage"] == "drafting"
    with pytest.raises(CaseError) as exc:
        await svc.accept_suggestion(env["connect"], company_id=COMPANY, case_id=CASE, user=USER,
                                    suggestion_id=uuid4(), letter="Edited letter")
    assert exc.value.status == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("change,status", [("access", 404), ("dismiss", 409), ("incident", 409), ("leave", 422)])
async def test_accept_race_cannot_write_and_cleans_up_only_attempt_file(env, monkeypatch, change, status):
    from app.matcha.services.drive import drive_service

    case = await suggest(env)
    sid = case["review"]["suggestion"]["id"]
    file_id, folder_id = uuid4(), uuid4()
    env["conn"].set("fetch", "UPDATE drive_files f", [{"id": file_id, "folder_id": folder_id}])
    monkeypatch.setattr(drive_service, "write_audit", AsyncMock())
    monkeypatch.setattr(workflow, "store_draft_file", AsyncMock(return_value={"id": file_id}))
    monkeypatch.setattr(draft_review, "review_draft", AsyncMock(return_value={"blocks": [], "advisories": []}))

    async def ai(**kw):
        assert env["open"] == 0
        if change == "access":
            env["hr"] = False
        elif change == "dismiss":
            env["case"]["review"] = None
        elif change == "incident":
            env["incident"]["updated_at"] += timedelta(seconds=1)
        else:
            env["block"] = True
        return []
    monkeypatch.setattr(draft_review, "ai_wording_review", ai)
    with pytest.raises(CaseError) as exc:
        await svc.accept_suggestion(env["connect"], company_id=COMPANY, case_id=CASE, user=USER,
                                    suggestion_id=sid, letter="Test Employee edited letter")
    assert exc.value.status == status and env["case"]["stage"] == "drafting"
    assert "draft_submitted" not in env["events"]
    cleanup_sql = env["conn"].sql_for("fetch")[-1]
    assert "NOT EXISTS (SELECT 1 FROM hr_cases c WHERE c.draft_file_id = f.id)" in cleanup_sql
    cleanup_args = env["conn"].args_for("UPDATE drive_files f")
    assert cleanup_args[0] == COMPANY and cleanup_args[1].startswith(f"hr_suggestion:{sid}:")
    assert drive_service.write_audit.await_args.kwargs["file_id"] == file_id


@pytest.mark.asyncio
async def test_cleanup_failure_never_masks_original_error(env, monkeypatch):
    from app.matcha.services.drive import drive_service
    env["conn"].set("fetch", "UPDATE drive_files f", [{"id": uuid4(), "folder_id": uuid4()}])
    monkeypatch.setattr(drive_service, "write_audit", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    # Best effort: the original failed acceptance remains actionable.
    await svc._discard_failed_file(env["connect"], company_id=COMPANY, attempt_ref="test-attempt", user=USER)


@pytest.mark.asyncio
async def test_storage_failure_returns_actionable_status_and_no_transition(env, monkeypatch):
    from app.matcha.services.drive.drive_service import DriveError
    case = await suggest(env)
    monkeypatch.setattr(workflow, "store_draft_file", AsyncMock(side_effect=DriveError(503, "File storage unavailable")))
    with pytest.raises(CaseError) as exc:
        await svc.accept_suggestion(env["connect"], company_id=COMPANY, case_id=CASE, user=USER,
                                    suggestion_id=case["review"]["suggestion"]["id"], letter="Edited letter")
    assert exc.value.status == 503 and "storage" in exc.value.detail
    assert env["case"]["stage"] == "drafting"


@pytest.mark.asyncio
@pytest.mark.parametrize("response", ['{"letter": "An editable letter ✓"}', '{"letter": 4}', '{}', 'not json'])
async def test_real_drafting_parser_and_provider_failures(monkeypatch, response):
    from app.matcha.services._shared import gemini

    generate = AsyncMock(return_value=SimpleNamespace(text=response))
    monkeypatch.setattr(gemini, "_genai", lambda: SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    args = dict(incident={"incident_number": "IR-1", "title": "Report", "description": "Reported account"},
                employee_name="Test Employee", inputs=body().model_dump(mode="json"), policy_titles=["Attendance"])
    if "editable" in response:
        assert await svc.draft_letter(**args) == "An editable letter ✓"
        assert "not you" in generate.await_args.kwargs["config"]["system_instruction"]
    else:
        with pytest.raises(CaseError) as exc:
            await svc.draft_letter(**args)
        assert exc.value.status == 503
    generate.side_effect = TimeoutError()
    with pytest.raises(CaseError) as exc:
        await svc.draft_letter(**args)
    assert exc.value.status == 503
