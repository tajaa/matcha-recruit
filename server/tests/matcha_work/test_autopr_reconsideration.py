"""Decision-bound AutoPR reconsideration regression tests."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


class _AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        return False


class _ReconsiderationConn:
    def __init__(self, progress_note, *, board_column="todo", status="pending"):
        self.progress_note = progress_note
        self.board_column = board_column
        self.status = status
        self.insert_args = None
        self.activity_id = uuid4()
        self.created_at = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)

    def transaction(self):
        return _AsyncContext()

    async def fetchrow(self, query, *args):
        if "SELECT id, progress_note" in query:
            if self.progress_note is None:
                return None
            return {
                "id": args[0],
                "progress_note": self.progress_note,
                "board_column": self.board_column,
                "status": self.status,
            }
        if "INSERT INTO mw_task_history" in query:
            self.insert_args = args
            return {"id": self.activity_id, "created_at": self.created_at}
        raise AssertionError(f"Unexpected query: {query}")


def _connection_context(conn):
    return _AsyncContext(conn)


def test_operator_directives_accept_clear_work_commands_in_bound_context():
    from app.matcha.services.matcha_work import project_task_service as svc

    directives, route = svc._parse_autopr_directives(
        "It still fails.\n"
        "--you need to draft this PR\n"
        "--you need to trust me that it's still not working\n"
        "--test-route=/app/jobs\n"
    )

    assert directives == ["draft_pr", "trust_still_broken"]
    assert route == "/app/jobs"
    assert svc._parse_autopr_directives("you need to draft this PR") == (["draft_pr"], None)
    assert svc._parse_autopr_directives("you can work on this.") == (["draft_pr"], None)
    assert svc._parse_autopr_directives("Please go ahead and work on this ticket") == (
        ["draft_pr"],
        None,
    )
    assert svc._parse_autopr_directives("just go ahead and do it anyways") == (
        ["draft_pr"],
        None,
    )
    assert svc._parse_autopr_directives("--test-route=https://evil.example/x") == ([], None)
    assert svc._parse_autopr_directives(
        "--do not draft a PR yet, ask questions first"
    ) == ([], None)
    assert svc._parse_autopr_directives("Do not work on this yet") == ([], None)
    assert svc._parse_autopr_directives("You can not work on this yet") == ([], None)
    assert svc._parse_autopr_directives("The expected behavior is to create a PR") == (
        [],
        None,
    )
    assert svc._parse_autopr_directives("--no draft PR yet") == ([], None)
    assert svc._parse_autopr_directives("--draft prevention notes") == ([], None)


def test_operator_directives_accept_ordinary_override_phrasing():
    """A refusal is overridden the way an owner actually types it.

    Every phrasing here was rejected by the first-generation parser, so a
    ticket the owner had explicitly unblocked kept publishing the same
    "no safe action" note.
    """
    from app.matcha.services.matcha_work import project_task_service as svc

    for phrasing in (
        "do it anyway",
        "work on it either way",
        "you can absolutely draft a PR with migration scripts",
        "draft the migration",
        "write the migration file",
        "i need you to implement this",
        "handle the migration",
        "proceed",
    ):
        assert svc._parse_autopr_directives(phrasing) == (["draft_pr"], None), phrasing

    # Prose that merely mentions the same verbs stays untrusted.
    assert svc._parse_autopr_directives("the dropdown should fix hospitality accounts") == (
        [],
        None,
    )
    assert svc._parse_autopr_directives("no need to draft a PR for this") == ([], None)
    assert svc._parse_autopr_directives("do not draft the migration") == ([], None)


@pytest.mark.asyncio
async def test_reconsideration_is_bound_to_exact_no_spec_note(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    note = (
        "🤖 AUTO SETUP · NO PR: ALREADY FIXED · build 858 · prod 1065b28 · "
        "🟡 C98 · [autopr:no-spec 2026-08-28T22:37:56Z] already_fixed"
    )
    conn = _ReconsiderationConn(note)
    notify = AsyncMock()
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    monkeypatch.setattr(svc, "_notify_task_comment", notify)
    project_id, task_id, actor_id, attachment_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )

    result = await svc.request_autopr_reconsideration(
        project_id=project_id,
        task_id=task_id,
        actor_user_id=actor_id,
        expected_progress_note=note,
        body="The existing credential selector only covers employees, not jobs.",
        attachment_ids=[attachment_id],
    )

    assert result["autopr_reconsideration_pending"] is True
    assert result["activity_id"] == str(conn.activity_id)
    metadata = json.loads(conn.insert_args[4])
    assert metadata["kind"] == "autopr_additional_context"
    assert metadata["autopr_reconsideration_of"] == note
    assert metadata["attachment_ids"] == [str(attachment_id)]
    assert metadata["reply_to_name"] == "AUTO SETUP"
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconsideration_rejects_stale_decision(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = (
        "🤖 AUTO SETUP · NO PR: ALREADY FIXED · "
        "[autopr:no-spec 2026-08-30T20:00:00Z] already_fixed"
    )
    conn = _ReconsiderationConn(current)
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    with pytest.raises(svc.AutoPRReconsiderationConflict, match="decision changed"):
        await svc.request_autopr_reconsideration(
            project_id=uuid4(),
            task_id=uuid4(),
            actor_user_id=uuid4(),
            expected_progress_note=current + " stale",
            body="New evidence",
        )
    assert conn.insert_args is None


@pytest.mark.asyncio
async def test_reconsideration_rejects_non_no_spec_task(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = "🤖 AUTO SETUP · READY FOR REVIEW · PR #401"
    conn = _ReconsiderationConn(current)
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    with pytest.raises(svc.AutoPRReconsiderationConflict, match="no longer"):
        await svc.request_autopr_reconsideration(
            project_id=uuid4(),
            task_id=uuid4(),
            actor_user_id=uuid4(),
            expected_progress_note=current,
            body="New evidence",
        )


@pytest.mark.asyncio
async def test_awaiting_answers_accepts_chat_or_ticket_context(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = (
        "🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · build 900 · "
        "prod abc1234 · PR #501 · note: Which jobs screen is affected?"
    )
    conn = _ReconsiderationConn(current, board_column="changes_requested")
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    monkeypatch.setattr(svc, "_notify_task_comment", AsyncMock())

    result = await svc.request_autopr_reconsideration(
        project_id=uuid4(),
        task_id=uuid4(),
        actor_user_id=uuid4(),
        expected_progress_note=current,
        body="The jobs editor at /work/jobs is the affected screen.",
    )

    assert result["autopr_reconsideration_pending"] is True
    assert json.loads(conn.insert_args[4])["kind"] == "autopr_additional_context"


@pytest.mark.asyncio
async def test_reconsideration_persists_trusted_directive_policy(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = (
        "🤖 AUTO SETUP · NO PR: ALREADY FIXED · "
        "[autopr:no-spec 2026-08-30T20:00:00Z] already_fixed"
    )
    conn = _ReconsiderationConn(current)
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    monkeypatch.setattr(svc, "_notify_task_comment", AsyncMock())

    result = await svc.request_autopr_reconsideration(
        project_id=uuid4(),
        task_id=uuid4(),
        actor_user_id=uuid4(),
        expected_progress_note=current,
        body="you can work on this.\n--trust-still-broken\n--test-route=/app/jobs",
    )

    metadata = json.loads(conn.insert_args[4])
    assert metadata["autopr_directives"] == "draft_pr,trust_still_broken"
    assert metadata["autopr_test_route"] == "/app/jobs"
    assert result["autopr_directives"] == ["draft_pr", "trust_still_broken"]
    assert result["autopr_test_route"] == "/app/jobs"


@pytest.mark.asyncio
async def test_legacy_answers_needed_note_matches_desktop_eligibility(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = "from auto setup · build 849 · answers needed · Which screen is affected?"
    conn = _ReconsiderationConn(current, board_column="changes_requested")
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    monkeypatch.setattr(svc, "_notify_task_comment", AsyncMock())

    result = await svc.request_autopr_reconsideration(
        project_id=uuid4(),
        task_id=uuid4(),
        actor_user_id=uuid4(),
        expected_progress_note=current,
        body="The jobs editor is affected.",
    )

    assert result["autopr_reconsideration_pending"] is True


@pytest.mark.asyncio
async def test_force_directive_survives_a_screenshot_question_round(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = (
        "🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · PR #501 · 🟡 C55 · "
        "[autopr:directives draft_pr,trust_still_broken] · note: Attach the screen"
    )
    conn = _ReconsiderationConn(current, board_column="changes_requested")
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    monkeypatch.setattr(svc, "_notify_task_comment", AsyncMock())

    result = await svc.request_autopr_reconsideration(
        project_id=uuid4(),
        task_id=uuid4(),
        actor_user_id=uuid4(),
        expected_progress_note=current,
        body="Here is the requested screenshot and exact role.",
        attachment_ids=[uuid4()],
    )

    metadata = json.loads(conn.insert_args[4])
    assert metadata["autopr_directives"] == "draft_pr,trust_still_broken"
    assert result["autopr_directives"] == ["draft_pr", "trust_still_broken"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("board_column", "status"),
    [
        ("in_progress", "pending"),
        ("review", "pending"),
        ("done", "completed"),
        ("todo", "cancelled"),
    ],
)
async def test_reconsideration_rejects_ineligible_task_state(
    monkeypatch, board_column, status
):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = (
        "🤖 AUTO SETUP · NO PR: ALREADY FIXED · "
        "[autopr:no-spec 2026-08-30T20:00:00Z] already_fixed"
    )
    conn = _ReconsiderationConn(
        current, board_column=board_column, status=status
    )
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    with pytest.raises(svc.AutoPRReconsiderationConflict, match="Todo or Changes"):
        await svc.request_autopr_reconsideration(
            project_id=uuid4(),
            task_id=uuid4(),
            actor_user_id=uuid4(),
            expected_progress_note=current,
            body="New evidence",
        )
    assert conn.insert_args is None


@pytest.mark.asyncio
async def test_reconsideration_requires_text_or_attachment():
    from app.matcha.services.matcha_work import project_task_service as svc

    with pytest.raises(ValueError, match="requires text or an attachment"):
        await svc.request_autopr_reconsideration(
            project_id=uuid4(),
            task_id=uuid4(),
            actor_user_id=uuid4(),
            expected_progress_note="unused",
            body="   ",
        )


def test_task_shape_serializes_reconsideration_fields():
    from app.matcha.services.matcha_work import project_task_service as svc

    event_id = uuid4()
    now = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
    shaped = svc._row_to_task(
        {
            "id": uuid4(),
            "autopr_reconsideration_pending": True,
            "autopr_reconsideration_event_id": event_id,
            "autopr_reconsideration_at": now,
        }
    )
    assert shaped["autopr_reconsideration_event_id"] == str(event_id)
    assert shaped["autopr_reconsideration_at"] == now.isoformat()
