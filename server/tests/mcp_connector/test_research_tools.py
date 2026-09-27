"""The connector's research-card tools: access, claim/attach rules, report contract."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.matcha.routes.matcha_work import _shared
from app.matcha.routes.mcp_connector import research
from app.matcha.services.matcha_work import project_file_service, project_task_service
from tests._helpers.routes import QueryConn

TASK = uuid.UUID("aaaaaaaa-1111-4111-8111-111111111111")
PROJECT = uuid.UUID("bbbbbbbb-2222-4222-8222-222222222222")
USER = SimpleNamespace(id=uuid.UUID("cccccccc-3333-4333-8333-333333333333"), role="client")

GOOD_REPORT = """### Summary
Short answer.

### Findings
- A fact [1]

### Recommendation
Buy the 14-inch.

### Sources
1. Apple — https://www.apple.com/macbook-pro/
"""


def _card(**over):
    row = {
        "id": TASK, "project_id": PROJECT, "title": "Which MacBook Pro?",
        "description": "Compare 14 vs 16", "category": "research",
        "board_column": "todo", "status": "pending", "priority": "medium",
        "progress_note": None, "review_note": None,
        "updated_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "autopr_run_requested_at": None, "project_title": "Errands",
    }
    row.update(over)
    return row


@pytest.fixture
def env(monkeypatch):
    """Card lookup via a QueryConn, access via a stubbed guard, writes recorded."""
    state = SimpleNamespace(
        conn=QueryConn(fetchrow={"FROM mw_tasks t": _card()}),
        role="owner", access_error=None, updates=[], notes=[], stored=[], files=[],
    )
    monkeypatch.setattr(research, "get_connection", lambda *a, **k: state.conn)

    async def verify(project_id, user):
        if state.access_error:
            raise state.access_error
        return {"id": project_id, "title": "Errands", "company_id": uuid.uuid4()}, state.role

    async def update(project_id, task_id, patch, **kw):
        state.updates.append(patch)
        return {"id": str(task_id)}

    async def log(**kw):
        state.notes.append(kw)
        return {"id": "note"}

    async def list_files(project_id, task_id):
        return state.files

    async def store(content, **kw):
        state.stored.append((content, kw))
        return {"id": uuid.uuid4(), "filename": kw["filename"]}

    monkeypatch.setattr(_shared, "_verify_project_access", verify)
    monkeypatch.setattr(project_task_service, "update_project_task", update)
    monkeypatch.setattr(project_task_service, "log_task_activity", log)
    monkeypatch.setattr(project_file_service, "list_task_files", list_files)
    monkeypatch.setattr(project_file_service, "store_project_file_bytes", store)
    return state


# ── report contract ──────────────────────────────────────────────────────────


def test_validate_report_accepts_the_contract_and_collapses_the_note():
    report, note = research.validate_report(GOOD_REPORT, "  Buy the\n14-inch  ")
    assert report.startswith("### Summary")
    assert note == "Buy the 14-inch"


@pytest.mark.parametrize("report, message", [
    ("", "empty"),
    (GOOD_REPORT.replace("### Sources", "### Links"), "### Sources"),
    ("### Findings\nx\n### Summary\nx\n### Recommendation\nx\n### Sources\nx", "out of order"),
    (GOOD_REPORT + "x" * research.REPORT_MAX_BYTES, "KB"),
])
def test_validate_report_rejects(report, message):
    with pytest.raises(research.ConnectorError, match=message):
        research.validate_report(report, "note")


@pytest.mark.parametrize("note", ["", "x" * (research.CARD_NOTE_MAX + 1)])
def test_validate_report_rejects_bad_card_note(note):
    with pytest.raises(research.ConnectorError, match="card_note"):
        research.validate_report(GOOD_REPORT, note)


def test_report_filename_counts_prior_reports():
    assert research.report_filename(TASK, []) == "research-report-aaaaaaaa-r1.md"
    names = ["research-report-aaaaaaaa-r1.md", "notes.md", "research-report-aaaaaaaa-r2.md"]
    assert research.report_filename(TASK, names) == "research-report-aaaaaaaa-r3.md"


# ── access ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_card_reads_as_not_visible(env):
    env.conn.set("fetchrow", "FROM mw_tasks t", None)
    with pytest.raises(research.ConnectorError) as err:
        await research.get_research_card(USER, task_id=str(TASK))
    assert err.value.status_code == 404


@pytest.mark.asyncio
async def test_other_tenants_card_reads_as_not_visible(env):
    env.access_error = HTTPException(status_code=404, detail="Project not found")
    with pytest.raises(research.ConnectorError, match="visible") as err:
        await research.get_research_card(USER, task_id=str(TASK))
    assert err.value.status_code == 404


@pytest.mark.asyncio
async def test_non_research_card_is_refused(env):
    env.conn.set("fetchrow", "FROM mw_tasks t", _card(category="bug"))
    with pytest.raises(research.ConnectorError, match="not a research card"):
        await research.get_research_card(USER, task_id=str(TASK))


@pytest.mark.asyncio
async def test_bad_uuid_is_explained(env):
    with pytest.raises(research.ConnectorError, match="UUID"):
        await research.get_research_card(USER, task_id="card-7")


# ── list ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_scopes_to_company_or_collaborator(monkeypatch):
    conn = QueryConn(fetch={"FROM mw_tasks t": [{
        "id": TASK, "project_id": PROJECT, "project_title": "Errands", "title": "Q",
        "board_column": "todo", "priority": "low", "updated_at": None,
        "autopr_run_requested_at": datetime.now(timezone.utc),
    }]})
    monkeypatch.setattr(research, "get_connection", lambda *a, **k: conn)
    company = uuid.uuid4()

    async def company_id(user):
        return company

    import app.matcha.dependencies as deps
    monkeypatch.setattr(deps, "get_client_company_id", company_id)

    out = await research.list_research_cards(USER, limit=500)
    assert out["count"] == 1 and out["cards"][0]["queued_for_autopr"] is True
    sql = conn.sql_for("fetch")[0]
    assert "p.company_id = $1" in sql and "mw_project_collaborators" in sql
    assert "project_type" not in sql  # only employees get the sensitive-type filter
    args = conn.args_for("FROM mw_tasks t")
    assert args[0] == company and args[1] == USER.id and args[-1] == 50  # limit clamped


@pytest.mark.asyncio
async def test_list_hides_sensitive_boards_from_employees(monkeypatch):
    conn = QueryConn(fetch={"FROM mw_tasks t": []})
    monkeypatch.setattr(research, "get_connection", lambda *a, **k: conn)

    async def company_id(user):
        return uuid.uuid4()

    import app.matcha.dependencies as deps
    monkeypatch.setattr(deps, "get_client_company_id", company_id)
    employee = SimpleNamespace(id=uuid.uuid4(), role="employee")
    await research.list_research_cards(employee, project_id=str(PROJECT))
    sql = conn.sql_for("fetch")[0]
    assert "project_type" in sql and "t.project_id" in sql
    assert ["discipline", "recruiting"] in list(conn.args_for("FROM mw_tasks t"))


# ── get ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_inlines_text_and_separates_the_previous_report(env, monkeypatch):
    now = datetime.now(timezone.utc)
    env.files = [
        {"id": 1, "filename": "brief.md", "storage_url": "s3://b/brief.md", "file_size": 20, "created_at": now},
        {"id": 2, "filename": "photo.png", "storage_url": "s3://b/p.png", "file_size": 999, "created_at": now},
        {"id": 3, "filename": "research-report-aaaaaaaa-r1.md", "storage_url": "s3://b/r1.md",
         "file_size": 40, "created_at": now - timedelta(days=1)},
    ]

    class Storage:
        async def download_file(self, path):
            return {"s3://b/brief.md": b"budget $2.5k", "s3://b/r1.md": b"### Summary\nold"}[path]

    import app.core.services.storage as storage_mod
    monkeypatch.setattr(storage_mod, "get_storage", lambda: Storage())
    env.conn.set("fetchrow", "FROM mw_tasks t", _card(board_column="changes_requested", review_note="Add prices"))

    out = await research.get_research_card(USER, task_id=str(TASK))
    assert out["review_note"] == "Add prices"
    assert [a["filename"] for a in out["attachments"]] == ["brief.md", "photo.png"]
    assert out["attachments"][0]["text"] == "budget $2.5k"
    assert "text" not in out["attachments"][1]
    assert out["previous_report"]["text"] == "### Summary\nold"
    assert out["report_contract"]["required_headings_in_order"][0] == "### Summary"
    assert "claim_research_card" in out["next_step"]


# ── claim ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_moves_to_in_progress_and_notes_it(env):
    out = await research.claim_research_card(USER, task_id=str(TASK), client_name="Claude")
    assert out == {"claimed": True, "already_in_progress": False, "task_id": str(TASK)}
    assert env.updates == [{"board_column": "in_progress"}]
    assert "Claude" in env.notes[0]["body"] and env.notes[0]["kind"] == "note"


@pytest.mark.asyncio
async def test_claim_is_idempotent_on_in_progress(env):
    env.conn.set("fetchrow", "FROM mw_tasks t", _card(board_column="in_progress"))
    out = await research.claim_research_card(USER, task_id=str(TASK), client_name="Claude")
    assert out["already_in_progress"] is True and env.updates == []


@pytest.mark.asyncio
@pytest.mark.parametrize("card, role, message", [
    ({}, "viewer", "not move"),
    ({"board_column": "done"}, "owner", "not waiting"),
    ({"autopr_run_requested_at": datetime.now(timezone.utc)}, "owner", "AutoPR"),
])
async def test_claim_refusals(env, card, role, message):
    env.role = role
    env.conn.set("fetchrow", "FROM mw_tasks t", _card(**card))
    with pytest.raises(research.ConnectorError, match=message):
        await research.claim_research_card(USER, task_id=str(TASK), client_name="Claude")
    assert env.updates == []


# ── attach ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_attach_publishes_like_the_autopr_lane(env):
    env.conn.set("fetchrow", "FROM mw_tasks t", _card(board_column="in_progress"))
    env.files = [{"filename": "research-report-aaaaaaaa-r1.md"}]
    out = await research.attach_research_report(
        USER, task_id=str(TASK), report_markdown=GOOD_REPORT,
        card_note="Get the 14-inch M5 Pro", client_name="ChatGPT",
    )
    assert out["filename"] == "research-report-aaaaaaaa-r2.md" and out["column"] == "review"

    content, kw = env.stored[0]
    body = content.decode()
    assert body.startswith("_Research via ChatGPT on the requester's own plan")
    assert "### Recommendation" in body
    assert kw["task_id"] == TASK and kw["content_type"] == "text/markdown"
    assert kw["prefix"].endswith(f"/{PROJECT}/tasks/{TASK}/files")

    assert env.notes[0]["body"] == "Get the 14-inch M5 Pro\n\nReport attached: research-report-aaaaaaaa-r2.md"
    assert env.notes[0]["attachment_ids"]
    assert env.updates == [{
        "board_column": "review",
        "progress_note": "🧠 CONNECTOR · ChatGPT · READY FOR REVIEW · note: Get the 14-inch M5 Pro",
    }]


@pytest.mark.asyncio
async def test_attach_refuses_closed_cards_and_bad_reports(env):
    env.conn.set("fetchrow", "FROM mw_tasks t", _card(board_column="review"))
    with pytest.raises(research.ConnectorError, match="not waiting"):
        await research.attach_research_report(
            USER, task_id=str(TASK), report_markdown=GOOD_REPORT, card_note="n", client_name="C",
        )
    env.conn.set("fetchrow", "FROM mw_tasks t", _card())
    with pytest.raises(research.ConnectorError, match="### Findings"):
        await research.attach_research_report(
            USER, task_id=str(TASK), report_markdown="### Summary\nx", card_note="n", client_name="C",
        )
    assert env.stored == [] and env.updates == []


@pytest.mark.asyncio
async def test_attach_maps_upload_policy_errors(env, monkeypatch):
    async def reject(content, **kw):
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    monkeypatch.setattr(project_file_service, "store_project_file_bytes", reject)
    with pytest.raises(research.ConnectorError, match="10 MB"):
        await research.attach_research_report(
            USER, task_id=str(TASK), report_markdown=GOOD_REPORT, card_note="n", client_name="C",
        )


def test_launch_prompt_names_the_card_and_tools():
    prompt = research.launch_prompt(TASK, "Which\nMacBook  Pro?")
    assert str(TASK) in prompt and '"Which MacBook Pro?"' in prompt
    for tool in ("get_research_card", "claim_research_card", "attach_research_report"):
        assert tool in prompt


@pytest.mark.asyncio
async def test_card_lookup_derives_pending_run_from_history(env):
    await research._load_card(TASK)
    sql = env.conn.sql_for("fetchrow")[0]
    assert "t.autopr_run_requested_at" not in sql
    assert project_task_service.AUTOPR_PENDING_REQUEST_QUERY in sql
    assert "autopr_run.created_at AS autopr_run_requested_at" in sql


@pytest.mark.asyncio
async def test_list_derives_pending_run_from_history(monkeypatch):
    conn = QueryConn(fetch={"FROM mw_tasks t": []})
    monkeypatch.setattr(research, "get_connection", lambda: conn)
    await research.list_research_cards(SimpleNamespace(id=USER.id, role="admin"))
    sql = conn.sql_for("fetch")[0]
    assert "t.autopr_run_requested_at" not in sql
    assert project_task_service.AUTOPR_PENDING_REQUEST_QUERY in sql
    query = project_task_service.AUTOPR_PENDING_REQUEST_QUERY
    assert "mw_task_history" in query
    assert "autopr_run_request" in query and "autopr_run_claim" in query and "autopr_run_cancel" in query
    assert project_task_service._AUTOPR_RUN_REQUEST_TTL in query


# ── release (local Codex run ended without a report) ─────────────────────────

GRANT_ISSUED = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def _claim(**over):
    row = {"created_at": GRANT_ISSUED + timedelta(seconds=30), "from_value": "todo",
           "to_value": "in_progress", "actor_user_id": USER.id}
    row.update(over)
    return row


def _release_env(env, *, claim=None, touched=False, column="in_progress"):
    env.conn = QueryConn(
        fetchrow={"FROM mw_tasks t": _card(board_column=column),
                  "event_type = 'column_change'": claim},
        fetchval={"mw_project_files": touched},
    )
    return env


async def _release(project=PROJECT):
    return await research.release_unfinished_claim(USER, project_id=project, task_id=TASK, since=GRANT_ISSUED)


@pytest.mark.asyncio
@pytest.mark.parametrize("from_value", ["todo", "changes_requested"])
async def test_release_returns_an_untouched_claim_to_its_column(env, monkeypatch, from_value):
    state = _release_env(env, claim=_claim(from_value=from_value))
    monkeypatch.setattr(research, "get_connection", lambda *a, **k: state.conn)
    assert await _release() == {"released": True, "column": from_value}
    assert state.updates == [{"board_column": from_value}]
    assert "went back to the queue" in state.notes[0]["body"]
    touched_sql, touched_args = state.conn.sql_for("fetchval")[0], state.conn.calls[-1][2]
    assert "IS DISTINCT FROM $3" in touched_sql and "research-report-%" in touched_sql
    assert touched_args[2] == USER.id


@pytest.mark.asyncio
@pytest.mark.parametrize("claim,touched,column,reason", [
    (_claim(), False, "review", "not_in_progress"),
    (None, False, "in_progress", "claim_not_owned"),
    (_claim(actor_user_id=uuid.uuid4()), False, "in_progress", "claim_not_owned"),
    (_claim(created_at=GRANT_ISSUED - timedelta(minutes=5)), False, "in_progress", "claim_not_owned"),
    (_claim(to_value="review"), False, "in_progress", "claim_not_owned"),
    (_claim(from_value="review"), False, "in_progress", "claim_not_owned"),
    (_claim(), True, "in_progress", "changed_since_claim"),
])
async def test_release_leaves_anything_it_does_not_own(env, monkeypatch, claim, touched, column, reason):
    state = _release_env(env, claim=claim, touched=touched, column=column)
    monkeypatch.setattr(research, "get_connection", lambda *a, **k: state.conn)
    assert await _release() == {"released": False, "reason": reason}
    assert state.updates == [] and state.notes == []


@pytest.mark.asyncio
async def test_release_refuses_viewers_and_other_projects(env, monkeypatch):
    state = _release_env(env, claim=_claim())
    monkeypatch.setattr(research, "get_connection", lambda *a, **k: state.conn)
    with pytest.raises(research.ConnectorError) as wrong_project:
        await _release(project=uuid.uuid4())
    assert wrong_project.value.status_code == 404
    state.role = "viewer"
    with pytest.raises(research.ConnectorError) as viewer:
        await _release()
    assert viewer.value.status_code == 403
    assert state.updates == []


@pytest.mark.asyncio
async def test_release_surfaces_a_rejected_move(env, monkeypatch):
    state = _release_env(env, claim=_claim())
    monkeypatch.setattr(research, "get_connection", lambda *a, **k: state.conn)

    async def reject(*a, **k):
        raise ValueError("Invalid board_column: todo")

    monkeypatch.setattr(project_task_service, "update_project_task", reject)
    with pytest.raises(research.ConnectorError, match="Invalid board_column"):
        await _release()
