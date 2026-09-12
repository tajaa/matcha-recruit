"""Decision-bound AutoPR reconsideration regression tests."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

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
    assert svc._parse_autopr_directives("--extend-runtime") == (["extend_runtime"], None)
    assert svc._parse_autopr_directives("please extend the runtime") == ([], None)


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
async def test_runtime_pause_accepts_ten_minute_continuation(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    current = (
        "🤖 AUTO SETUP · PAUSED: APPROVE 10 MORE MINUTES · checkpoint 123\n"
        "Why more time: The first 20-minute investigation ended before AutoPR produced a publishable result.\n"
        "Done so far: Saved a partial report and run transcript."
    )
    conn = _ReconsiderationConn(current, board_column="changes_requested")
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    monkeypatch.setattr(svc, "_notify_task_comment", AsyncMock())

    result = await svc.request_autopr_reconsideration(
        project_id=uuid4(),
        task_id=uuid4(),
        actor_user_id=uuid4(),
        expected_progress_note=current,
        body="--extend-runtime",
    )

    metadata = json.loads(conn.insert_args[4])
    assert metadata["autopr_directives"] == "extend_runtime"
    assert result["autopr_directives"] == ["extend_runtime"]


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
            "autopr_claimed_at": now,
        }
    )
    assert shaped["autopr_reconsideration_event_id"] == str(event_id)
    assert shaped["autopr_reconsideration_at"] == now.isoformat()
    assert shaped["autopr_claimed_at"] == now.isoformat()


class _RunRequestConn:
    """Stub for the run-now queue: one task row, one pending-request lookup."""

    def __init__(self, *, board_column="todo", status="pending", pending_at=None,
                 active_claimed_at=None, exists=True):
        self.board_column = board_column
        self.status = status
        self.pending_at = pending_at
        self.active_claimed_at = active_claimed_at
        self.exists = exists
        self.insert_args = None
        self.update_args = None
        self.history_events = []
        self.activity_id = uuid4()
        self.created_at = datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc)

    def transaction(self):
        return _AsyncContext()

    async def fetchrow(self, query, *args):
        if "SELECT id, board_column" in query:
            if not self.exists:
                return None
            return {"id": args[0], "board_column": self.board_column, "status": self.status,
                    "progress_note": getattr(self, "progress_note", None)}
        if "UPDATE mw_tasks SET" in query:
            self.update_args = args
            self.board_column = "in_progress"
            self.status = "pending"
            return {
                "id": args[0], "project_id": args[1], "company_id": uuid4(),
                "created_by": uuid4(), "title": "Queued task", "description": None,
                "due_date": None, "priority": "medium", "status": "pending",
                "board_column": "in_progress", "pipeline_column": "lead",
                "assigned_to": None, "completed_at": None,
                "created_at": self.created_at, "updated_at": self.created_at,
                "progress_note": getattr(self, "progress_note", None),
                "category": "engineering", "element_id": None, "review_note": None,
                "deal_value": None, "probability": None, "contact_name": None,
                "contact_company": None, "contact_email": None, "contact_phone": None,
                "outcome": None, "loss_reason": None, "next_action_at": None,
                "expected_close": None, "pr_url": None, "pr_number": None,
            }
        if "INSERT INTO mw_task_history" in query:
            self.insert_args = args
            return {"id": self.activity_id, "created_at": self.created_at}
        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query, *args):
        if "INSERT INTO mw_task_history" in query:
            self.history_events.append(args)
            return "INSERT 0 1"
        raise AssertionError(f"Unexpected query: {query}")

    async def fetchval(self, query, *args):
        if "AS paused" in query:
            return getattr(self, "held", False)
        if "metadata->>'kind' = 'autopr_run_claim'" in query:
            return self.active_claimed_at
        if "autopr_run_request" in query:
            return self.pending_at
        if "SELECT 1 FROM mw_tasks" in query:
            return 1 if self.exists else None
        raise AssertionError(f"Unexpected query: {query}")


def _watched_project_id():
    """A board the kanban-autopr harness actually polls.

    "Run AutoPR now" is rejected anywhere else: nothing would ever claim the
    request, so the card would sit queued with no run coming.
    """
    from app.matcha.services.matcha_work import project_task_service as svc

    return UUID(next(iter(svc.KANBAN_AUTOPR_PROJECT_IDS)))


def _autopr_bot_id():
    from app.matcha.services.matcha_work import project_task_service as svc

    return UUID(svc.KANBAN_AUTOPR_BOT_USER_ID)


@pytest.mark.asyncio
async def test_run_now_queues_one_pending_request(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    conn = _RunRequestConn()
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    result = await svc.request_autopr_run(
        project_id=_watched_project_id(), task_id=uuid4(), actor_user_id=uuid4()
    )

    assert result["already_pending"] is False
    assert result["autopr_run_requested_at"] == conn.created_at.isoformat()
    metadata = json.loads(conn.insert_args[4])
    assert metadata == {"kind": "autopr_run_request"}


@pytest.mark.asyncio
async def test_run_now_is_idempotent_while_a_request_is_unclaimed(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    pending_at = datetime(2026, 9, 2, 2, 55, tzinfo=timezone.utc)
    conn = _RunRequestConn(pending_at=pending_at)
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    result = await svc.request_autopr_run(
        project_id=_watched_project_id(), task_id=uuid4(), actor_user_id=uuid4()
    )

    assert result["already_pending"] is True
    assert result["autopr_run_requested_at"] == pending_at.isoformat()
    # Pressing the button twice must not stack a second history event.
    assert conn.insert_args is None


@pytest.mark.asyncio
async def test_run_now_rejects_lanes_autopr_never_picks_from(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    conn = _RunRequestConn(board_column="review")
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    with pytest.raises(svc.AutoPRReconsiderationConflict):
        await svc.request_autopr_run(
            project_id=_watched_project_id(), task_id=uuid4(), actor_user_id=uuid4()
        )
    assert conn.insert_args is None


@pytest.mark.asyncio
async def test_run_claim_consumes_the_request(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    conn = _RunRequestConn()
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    result = await svc.claim_autopr_run(
        project_id=_watched_project_id(),
        task_id=uuid4(),
        actor_user_id=_autopr_bot_id(),
    )

    assert result["claimed_at"] == conn.created_at.isoformat()
    assert result["task"]["board_column"] == "in_progress"
    assert result["task"]["autopr_claimed_at"] == conn.created_at.isoformat()
    assert conn.update_args is not None
    assert conn.history_events[0][4:7] == ("column_change", "todo", "in_progress")
    assert json.loads(conn.history_events[0][-1]) == {"kind": "autopr_run_claim_move"}
    assert json.loads(conn.insert_args[4]) == {"kind": "autopr_run_claim"}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["claim", "defer"])
async def test_machine_run_mutations_require_watched_board_and_bot_actor(
    monkeypatch, operation
):
    from app.matcha.services.matcha_work import project_task_service as svc

    connection_factory = AsyncMock()
    monkeypatch.setattr(svc, "get_connection", connection_factory)
    fn = svc.claim_autopr_run if operation == "claim" else svc.defer_autopr_run

    with pytest.raises(svc.AutoPRReconsiderationConflict, match="does not watch"):
        await fn(
            project_id=uuid4(), task_id=uuid4(), actor_user_id=_autopr_bot_id()
        )
    with pytest.raises(svc.AutoPRActorNotPermitted, match="service account"):
        await fn(
            project_id=_watched_project_id(), task_id=uuid4(), actor_user_id=uuid4()
        )
    connection_factory.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_now_rejects_a_board_autopr_does_not_watch(monkeypatch):
    """The harness polls four fixed Espresso projects. A request anywhere else
    could never be claimed, so it would pin the card at "Queued for AutoPR"
    while the local watcher forced a dispatch that ignored it."""
    from app.matcha.services.matcha_work import project_task_service as svc

    conn = _RunRequestConn()
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    unwatched = uuid4()
    assert str(unwatched) not in svc.KANBAN_AUTOPR_PROJECT_IDS
    with pytest.raises(svc.AutoPRReconsiderationConflict):
        await svc.request_autopr_run(
            project_id=unwatched, task_id=uuid4(), actor_user_id=uuid4()
        )
    assert conn.insert_args is None


@pytest.mark.asyncio
@pytest.mark.parametrize("exists,column,status,active_claim", [
    (True, "todo", "pending", False),
    (True, "changes_requested", "pending", False),
    (False, "todo", "pending", False),
    (True, "in_progress", "pending", False),
    (True, "in_progress", "pending", True),
    (True, "todo", "cancelled", False),
])
async def test_unqueue_preserves_card_and_records_hold(
    monkeypatch, exists, column, status, active_claim
):
    from app.matcha.services.matcha_work import project_task_service as svc

    conn = _RunRequestConn(exists=exists, board_column=column, status=status)
    if active_claim:
        conn.active_claimed_at = conn.created_at
    conn.execute = AsyncMock()
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    if exists and ((column == "in_progress" and not active_claim) or status == "cancelled"):
        with pytest.raises(svc.AutoPRReconsiderationConflict):
            await svc.cancel_autopr_run(project_id=uuid4(), task_id=uuid4(), actor_user_id=uuid4())
        conn.execute.assert_not_called()
        return
    result = await svc.cancel_autopr_run(project_id=uuid4(), task_id=uuid4(), actor_user_id=uuid4())
    if not exists:
        assert result is None
        conn.execute.assert_not_called()
    else:
        assert result == {"ok": True, "autopr_paused": True, "autopr_hold_reason": None}
        args = conn.execute.call_args.args
        assert "INSERT INTO mw_task_history" in args[0]
        assert "clock_timestamp()" in args[0]
        assert json.loads(args[-1]) == {"kind": "autopr_run_cancel"}


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,stored", [
    ("docs allowlist", "docs allowlist"),
    ("  padded  ", "padded"),
    ("", None),
    ("x" * 300, "x" * 200),
])
async def test_unqueue_records_the_operator_reason_on_the_hold_row(monkeypatch, reason, stored):
    # The reason rides on the same autopr_run_cancel row the hold query
    # resolves, so a card can say why it is parked; blank means no key at all.
    from app.matcha.services.matcha_work import project_task_service as svc

    conn = _RunRequestConn()
    conn.execute = AsyncMock()
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    result = await svc.cancel_autopr_run(
        project_id=uuid4(), task_id=uuid4(), actor_user_id=uuid4(), reason=reason,
    )
    assert result == {"ok": True, "autopr_paused": True, "autopr_hold_reason": stored}
    metadata = json.loads(conn.execute.call_args.args[-1])
    if stored is None:
        assert metadata == {"kind": "autopr_run_cancel"}
    else:
        assert metadata == {"kind": "autopr_run_cancel", "reason": stored}


@pytest.mark.asyncio
async def test_selector_deferral_consumes_request_without_pausing_or_moving(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    conn = _RunRequestConn()
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    result = await svc.defer_autopr_run(
        project_id=_watched_project_id(),
        task_id=uuid4(),
        actor_user_id=_autopr_bot_id(),
    )

    assert result == {"ok": True, "autopr_paused": False}
    assert conn.board_column == "todo"
    assert conn.update_args is None
    assert json.loads(conn.history_events[0][-1]) == {
        "kind": "autopr_run_cancel", "pause": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("held,column,status,exists", [
    (True, "todo", "pending", True), (False, "in_progress", "pending", True),
    (False, "todo", "cancelled", True), (False, "todo", "pending", False),
])
async def test_stale_investigation_cannot_claim_unqueued_card(monkeypatch, held, column, status, exists):
    from app.matcha.services.matcha_work import project_task_service as svc

    conn = _RunRequestConn(exists=exists, board_column=column, status=status)
    conn.held = held
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    result = await svc.claim_autopr_run(
        project_id=_watched_project_id(),
        task_id=uuid4(),
        actor_user_id=_autopr_bot_id(),
    )
    assert result is None if not exists else result["ok"] is False
    assert conn.insert_args is None


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,code", [(None, 404), ({"ok": True}, None), ("conflict", 409), ("forbidden", 403)])
async def test_unqueue_route_checks_access_and_results(monkeypatch, outcome, code):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.matcha.routes.matcha_work import task_history as route
    from app.matcha.services.matcha_work import project_task_service as svc

    access = AsyncMock()
    if outcome == "forbidden":
        access.side_effect = HTTPException(status_code=403, detail="Forbidden")
    monkeypatch.setattr(route, "_verify_project_access", access)
    cancel = AsyncMock(return_value=outcome)
    if outcome == "conflict":
        cancel.side_effect = svc.AutoPRReconsiderationConflict("Already started")
    monkeypatch.setattr(svc, "cancel_autopr_run", cancel)
    if code:
        with pytest.raises(HTTPException) as exc:
            await route.cancel_autopr_run_endpoint(uuid4(), uuid4(), SimpleNamespace(id=uuid4()))
        assert exc.value.status_code == code
    else:
        assert await route.cancel_autopr_run_endpoint(uuid4(), uuid4(), SimpleNamespace(id=uuid4())) == outcome
        assert cancel.call_args.kwargs["reason"] is None
    if outcome == "forbidden":
        cancel.assert_not_called()


@pytest.mark.asyncio
async def test_unqueue_route_forwards_an_optional_reason_body(monkeypatch):
    # Espresso's Unqueue posts nothing; the CLI and the failure budget post
    # {"reason": ...}. Both reach the same service call.
    from types import SimpleNamespace

    from app.matcha.models.matcha_work.matcha_work import AutoPRHoldRequest
    from app.matcha.routes.matcha_work import task_history as route
    from app.matcha.services.matcha_work import project_task_service as svc

    monkeypatch.setattr(route, "_verify_project_access", AsyncMock())
    cancel = AsyncMock(return_value={"ok": True, "autopr_paused": True, "autopr_hold_reason": "docs"})
    monkeypatch.setattr(svc, "cancel_autopr_run", cancel)
    result = await route.cancel_autopr_run_endpoint(
        uuid4(), uuid4(), SimpleNamespace(id=uuid4()), body=AutoPRHoldRequest(reason="docs"),
    )
    assert result["autopr_hold_reason"] == "docs"
    assert cancel.call_args.kwargs["reason"] == "docs"
    with pytest.raises(ValueError):
        AutoPRHoldRequest(reason="x" * 201)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint_name,service_name", [
    ("claim_autopr_run_endpoint", "claim_autopr_run"),
    ("defer_autopr_run_endpoint", "defer_autopr_run"),
])
@pytest.mark.parametrize("error_type,status_code", [
    ("conflict", 409),
    ("actor", 403),
])
async def test_machine_run_routes_map_service_guards(
    monkeypatch, endpoint_name, service_name, error_type, status_code
):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.matcha.routes.matcha_work import task_history as route
    from app.matcha.services.matcha_work import project_task_service as svc

    monkeypatch.setattr(route, "_verify_project_access", AsyncMock())
    error = (
        svc.AutoPRReconsiderationConflict("unwatched")
        if error_type == "conflict"
        else svc.AutoPRActorNotPermitted("wrong actor")
    )
    monkeypatch.setattr(svc, service_name, AsyncMock(side_effect=error))

    with pytest.raises(HTTPException) as exc:
        await getattr(route, endpoint_name)(uuid4(), uuid4(), SimpleNamespace(id=uuid4()))
    assert exc.value.status_code == status_code


@pytest.mark.asyncio
@pytest.mark.parametrize("note,held,status,allowed", [
    ("🤖 AUTO SETUP · ALREADY SCOPED · PR #42", False, "pending", True),
    ("🤖 AUTO SETUP · ALREADY SCOPED · PR #42", True, "pending", False),
    ("🤖 AUTO SETUP · ALREADY SCOPED · PR #42", False, "cancelled", False),
    ("Ordinary manual work", False, "pending", False),
    (None, False, "pending", False),
])
async def test_claim_preserves_scoped_recovery_lane(monkeypatch, note, held, status, allowed):
    from app.matcha.services.matcha_work import project_task_service as svc

    conn = _RunRequestConn(board_column="in_progress", status=status)
    conn.progress_note = note
    conn.held = held
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))
    result = await svc.claim_autopr_run(
        project_id=_watched_project_id(),
        task_id=uuid4(),
        actor_user_id=_autopr_bot_id(),
    )
    assert result["ok"] is allowed
    assert (conn.insert_args is not None) is allowed


@pytest.mark.asyncio
async def test_claim_resumes_an_unsettled_in_progress_pickup(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service as svc

    active_at = datetime(2026, 9, 2, 2, 45, tzinfo=timezone.utc)
    conn = _RunRequestConn(board_column="in_progress", active_claimed_at=active_at)
    conn.progress_note = "Ordinary brief state"
    monkeypatch.setattr(svc, "get_connection", lambda: _connection_context(conn))

    result = await svc.claim_autopr_run(
        project_id=_watched_project_id(),
        task_id=uuid4(),
        actor_user_id=_autopr_bot_id(),
    )

    assert result["ok"] is True
    assert result["task"]["board_column"] == "in_progress"
    assert conn.history_events == []


def test_hold_sql_releases_only_for_new_work_or_review_round():
    # Execute the production state query against an isolated in-memory SQL
    # fixture. No application database, migrations, or external connections.
    import sqlite3
    from app.matcha.services.matcha_work import project_task_service as svc

    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE mw_tasks (id TEXT)")
        db.execute("CREATE TABLE mw_task_history (task_id TEXT, event_type TEXT, metadata TEXT, created_at INTEGER)")
        db.execute("INSERT INTO mw_tasks VALUES ('ticket')")
        query = f"SELECT {svc._AUTOPR_HOLD_SQL} FROM mw_tasks t WHERE t.id = 'ticket'"

        def add(at, kind=None, event="activity", pause=None):
            metadata = {"kind": kind} if kind else {}
            if pause is not None:
                metadata["pause"] = pause
            db.execute("INSERT INTO mw_task_history VALUES (?, ?, ?, ?)",
                       ("ticket", event, json.dumps(metadata), at))

        def paused():
            return bool(db.execute(query).fetchone()[0])

        assert not paused()
        add(1, "autopr_run_request")
        add(2, "autopr_run_claim")
        add(3, "autopr_run_cancel")
        assert paused()
        add(4, "autopr_run_cancel", pause=False)
        assert not paused()
        add(5, "autopr_run_cancel")
        add(6, event="column_change")  # publish -> review does not resume
        add(7, "autopr_run_claim")     # stale worker does not resume
        assert paused()
        add(8, event="review_rejected")
        assert not paused()
        add(9, "autopr_run_cancel")
        add(10, event="round_started")
        assert not paused()
        add(11, "autopr_run_cancel")
        add(12, "autopr_additional_context")
        assert not paused()
        add(13, "autopr_run_cancel")
        add(14, "autopr_run_request")
        assert not paused()
        add(14, "autopr_run_cancel")  # conservative equal-time ordering
        add(14, event="review_rejected")
        assert paused()


def test_hold_lookup_is_joined_once_per_task():
    import inspect
    from app.matcha.services.matcha_work import project_task_service as svc

    query_source = inspect.getsource(svc.list_project_tasks)
    assert query_source.count("{_AUTOPR_HOLD_QUERY}") == 1
    assert query_source.count("{_AUTOPR_HOLD_REASON_QUERY}") == 1
    assert "{_AUTOPR_HOLD_SQL}" not in query_source
    assert "COALESCE(autopr_hold.paused, FALSE) AS autopr_paused" in query_source
    assert "autopr_hold_reason.reason AS autopr_hold_reason" in query_source


def test_hold_reason_follows_the_same_row_as_the_hold():
    # Same isolated SQL fixture as the hold test: the reason must come from
    # exactly the row that decides "paused", read null once the hold lifts,
    # and ignore a machine deferral (pause:false) even when it carries text.
    import sqlite3
    from app.matcha.services.matcha_work import project_task_service as svc

    assert svc._AUTOPR_HOLD_ROW in svc._AUTOPR_HOLD_QUERY
    assert svc._AUTOPR_HOLD_ROW in svc._AUTOPR_HOLD_REASON_QUERY
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE mw_tasks (id TEXT)")
        db.execute("CREATE TABLE mw_task_history (task_id TEXT, event_type TEXT, metadata TEXT, created_at INTEGER)")
        db.execute("INSERT INTO mw_tasks VALUES ('ticket')")
        paused_query = f"SELECT {svc._AUTOPR_HOLD_SQL} FROM mw_tasks t WHERE t.id = 'ticket'"
        reason_query = f"SELECT ({svc._AUTOPR_HOLD_REASON_QUERY}) FROM mw_tasks t WHERE t.id = 'ticket'"

        def add(at, kind=None, event="activity", **metadata):
            if kind:
                metadata["kind"] = kind
            db.execute("INSERT INTO mw_task_history VALUES (?, ?, ?, ?)",
                       ("ticket", event, json.dumps(metadata), at))

        def state():
            return (bool(db.execute(paused_query).fetchone()[0]),
                    db.execute(reason_query).fetchone()[0])

        assert state() == (False, None)
        add(1, "autopr_run_cancel")
        assert state() == (True, None)
        add(2, "autopr_run_cancel", reason="docs allowlist")
        assert state() == (True, "docs allowlist")
        add(3, "autopr_run_cancel", pause=False, reason="machine deferral")
        assert state() == (False, None)
        add(4, "autopr_run_cancel", reason="parked: 3x disallowed_paths")
        add(5, event="column_change")
        assert state() == (True, "parked: 3x disallowed_paths")
        add(6, "autopr_run_request")
        assert state() == (False, None)


def test_active_claim_survives_comments_but_settles_on_run_mutation():
    import sqlite3
    from app.matcha.services.matcha_work import project_task_service as svc

    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE mw_tasks (id TEXT, board_column TEXT)")
        db.execute(
            "CREATE TABLE mw_task_history "
            "(task_id TEXT, event_type TEXT, metadata TEXT, created_at INTEGER)"
        )
        db.execute("INSERT INTO mw_tasks VALUES ('ticket', 'in_progress')")
        sqlite_claim_query = svc._AUTOPR_ACTIVE_CLAIM_QUERY.replace(
            f"AND h.created_at > now() - interval '{svc._AUTOPR_ACTIVE_CLAIM_TTL}'",
            "",
        )
        query = f"SELECT ({sqlite_claim_query}) FROM mw_tasks t WHERE t.id = 'ticket'"

        def add(at, event="activity", kind=None):
            db.execute(
                "INSERT INTO mw_task_history VALUES (?, ?, ?, ?)",
                ("ticket", event, json.dumps({"kind": kind} if kind else {}), at),
            )

        add(1, kind="autopr_run_claim")
        assert db.execute(query).fetchone()[0] == 1
        add(2, kind="note")
        assert db.execute(query).fetchone()[0] == 1
        add(3, event="progress_note_change")
        assert db.execute(query).fetchone()[0] is None
        add(4, kind="autopr_run_claim")
        assert db.execute(query).fetchone()[0] == 4
        add(5, event="column_change")
        assert db.execute(query).fetchone()[0] is None


def test_active_claim_is_bounded_and_column_gated_in_list_query():
    import inspect
    from app.matcha.services.matcha_work import project_task_service as svc

    assert "t.board_column = 'in_progress'" in svc._AUTOPR_ACTIVE_CLAIM_QUERY
    assert svc._AUTOPR_ACTIVE_CLAIM_TTL in svc._AUTOPR_ACTIVE_CLAIM_QUERY
    query_source = inspect.getsource(svc.list_project_tasks)
    assert "autopr_claim ON TRUE" in query_source


def test_hold_index_upgrade_and_downgrade_are_concurrent(monkeypatch):
    import importlib.util
    from pathlib import Path
    from unittest.mock import MagicMock

    path = Path(__file__).resolve().parents[2] / "alembic/versions/autoprrun02_autopr_hold_state_index.py"
    spec = importlib.util.spec_from_file_location("autopr_hold_index", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    op = MagicMock()
    monkeypatch.setattr(migration, "op", op)
    migration.upgrade()
    statements = [call.args[0] for call in op.execute.call_args_list]
    assert "DROP INDEX CONCURRENTLY" in statements[0]
    assert "CREATE INDEX CONCURRENTLY" in statements[1]
    assert "(task_id, created_at DESC)" in statements[1]
    for kind in ("autopr_run_request", "autopr_run_claim", "autopr_run_cancel",
                 "autopr_additional_context", "review_rejected", "round_started"):
        assert f"'{kind}'" in statements[1]
    assert migration.down_revision == "autoprrun01"
    op.reset_mock()
    migration.downgrade()
    assert "DROP INDEX CONCURRENTLY" in op.execute.call_args.args[0]
    op.get_context.return_value.autocommit_block.assert_called_once()
