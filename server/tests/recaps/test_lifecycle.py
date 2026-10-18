from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.matcha_work.recaps import Event
from app.matcha.services.matcha_work.recaps import observe, reconcile, scope, service, settings

NOW = datetime.now(timezone.utc)
USER, COMPANY, RECAP, SOURCE, RUN = [uuid4() for _ in range(5)]


class Conn:
    def __init__(self):
        self.execute = AsyncMock()
        self.fetchval = AsyncMock()
        self.fetchrow = AsyncMock()
        self.fetch = AsyncMock()

    @asynccontextmanager
    async def transaction(self, **_):
        yield self


def wire(monkeypatch, module, conn):
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setattr(module, "connection_or_direct", connection)


def source(**over):
    return {"id": SOURCE, "recap_id": RECAP, "kind": "run", "run_id": RUN,
            "owner_user_id": USER, "company_id": COMPANY, "state": "collecting", "semantic_state": "live", "role": "root", **over}


def row(**over):
    return {"id": RECAP, "company_id": COMPANY, "owner_user_id": USER, "state": "collecting", "title": "Apartment task",
            "outcome": "observed", "created_at": NOW, "ready_at": None, "expires_at": None,
            "last_error_code": None, "manual_retry_request_id": None, "render_attempts": 0,
            "source_completed_at": None, "finalize_after": None, "output_manifest": None, "manifest": None, **over}


@pytest.mark.asyncio
async def test_feature_off_registration_is_zero_db_work(monkeypatch):
    monkeypatch.setattr(settings, "enabled", lambda: False)
    conn = Conn()
    assert await scope.register(conn, kind="run", source_id=RUN, user_id=USER, company_id=COMPANY, title="Task") is None
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_registration_owner_check_and_child_failure_fences_root(monkeypatch):
    monkeypatch.setattr(settings, "enabled", lambda: True)
    conn = Conn()
    monkeypatch.setattr(scope, "source_for_run", AsyncMock(return_value=source()))
    monkeypatch.setattr(settings, "available", lambda _: True)
    conn.fetchrow.side_effect = RuntimeError("snapshot store unavailable")
    assert await scope.register(conn, kind="research", source_id=uuid4(), user_id=USER, company_id=COMPANY,
                                title="Child", parent_run_id=RUN) is None
    assert "source_binding_failed" in conn.execute.await_args.args[0]
    conn.execute.reset_mock()
    assert await scope.register(conn, kind="run", source_id=uuid4(), user_id=uuid4(), company_id=COMPANY,
                                title="Other", parent_run_id=RUN) is None
    # The legitimate parent's generation is fenced even after a malformed
    # internal lineage attempt. No foreign data can be attached.
    assert "source_binding_failed" in conn.execute.await_args.args[0]


@pytest.mark.asyncio
async def test_root_enrollment_reserves_cap_and_mail_before_dispatch(monkeypatch):
    monkeypatch.setattr(settings, "enabled", lambda: True)
    monkeypatch.setattr(settings, "available", lambda _: True)
    conn = Conn()
    conn.fetchrow.return_value = {"enabled": True, "email_enabled": True}
    conn.fetchval.side_effect = [True, 0, RECAP]
    assert await scope.register(conn, kind="jobs", source_id=uuid4(), user_id=USER, company_id=COMPANY, title="Jobs", generation=1) == RECAP
    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert "advisory_xact_lock" in statements[0]
    assert any("completion_mail_owner" in sql for sql in statements)
    assert any("mw_agent_recap_deliveries" in sql for sql in statements)


@pytest.mark.asyncio
@pytest.mark.parametrize("pref,personal,count", [(None, True, 0), ({"enabled": False}, True, 0), ({"enabled": True}, False, 0), ({"enabled": True}, True, 10)])
async def test_enrollment_respects_preferences_personal_scope_and_cap(monkeypatch, pref, personal, count):
    monkeypatch.setattr(settings, "enabled", lambda: True)
    monkeypatch.setattr(settings, "available", lambda _: True)
    conn = Conn(); conn.fetchrow.return_value = pref; conn.fetchval.side_effect = [personal, count]
    assert await scope.register(conn, kind="run", source_id=RUN, user_id=USER, company_id=COMPANY, title="Task") is None


@pytest.mark.asyncio
async def test_event_idempotency_and_reserved_final_budget(monkeypatch):
    conn = Conn(); conn.fetchrow.return_value = {"state": "collecting", "event_count": 120}
    snap = Event(title="Final", kind="result", occurred_at=NOW)
    assert await scope.event(conn, source(), "final", snap) is None
    conn.fetchval.return_value = uuid4()
    assert await scope.event(conn, source(), "final", snap, reserve_final=True)
    conn.fetchval.return_value = None
    conn.execute.reset_mock()
    assert await scope.event(conn, source(), "final", snap, reserve_final=True) is None
    conn.execute.assert_not_awaited()
    conn.fetchrow.return_value = {"state": "ready", "event_count": 5}
    assert await scope.event(conn, source(), "late", snap) is None


@pytest.mark.asyncio
async def test_prompt_gap_and_continuation_do_not_close_prematurely(monkeypatch):
    conn = Conn(); conn.fetch.return_value = []
    monkeypatch.setattr(scope, "event", AsyncMock())
    conn.fetchrow.side_effect = [{"status": "done", "result": {"question": {"question": "Which city?"}}}, None]
    conn.fetchval.return_value = None
    assert await observe.refresh_source(conn, source()) == "waiting"
    conn.fetchrow.side_effect = [{"status": "done", "result": {"held": {}}}, None]
    # An explicit nonempty held payload is how actual runs persist it.
    yes = {"kind": "confirm_action", "status": "answered", "answer": "yes", "answered_at": NOW, "expires_at": NOW + timedelta(hours=1)}
    conn.fetchrow.side_effect = [{"status": "done", "result": {"held": {"tool": "send_email"}}}, yes]
    assert await observe.refresh_source(conn, source()) == "waiting"
    conn.fetchval.return_value = 1
    conn.fetchrow.side_effect = [{"status": "done", "result": {"held": {"tool": "send_email"}}}, yes]
    assert await observe.refresh_source(conn, source()) == "terminal"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,answer,expiry,outcome", [("answered", "no", NOW + timedelta(hours=1), "declined"),
                                                           ("open", None, NOW - timedelta(hours=1), "partial")])
async def test_decline_and_expiry_are_visible(monkeypatch, status, answer, expiry, outcome):
    conn = Conn(); conn.fetch.return_value = []; conn.fetchval.return_value = None
    conn.fetchrow.side_effect = [{"status": "done", "result": {"held": {"tool": "send_email"}}},
                                 {"kind": "confirm_action", "status": status, "answer": answer, "answered_at": NOW, "expires_at": expiry}]
    record = AsyncMock(); monkeypatch.setattr(scope, "event", record)
    assert await observe.refresh_source(conn, source()) == "terminal"
    assert record.await_args_list[0].args[3].outcome == outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,status,answer,answered,state,title,outcome", [
    # A new message lapses a confirmation: nothing was done, and no expiry is invented.
    ("confirm_action", "superseded", None, None, "terminal", "Action not confirmed", "cancelled"),
    # A new message answers a question in a run of its own.
    ("ask_user", "answered", "text", timedelta(minutes=10), "terminal", "Answered in a new request", "observed"),
    # Just answered: its continuation is still being started.
    ("ask_user", "answered", "text", timedelta(seconds=5), "waiting", None, None),
    ("ask_user", "open", None, None, "waiting", None, None),
])
async def test_a_question_closed_by_a_new_message_ends_the_wait(monkeypatch, kind, status, answer, answered, state, title, outcome):
    conn = Conn(); conn.fetch.return_value = []; conn.fetchval.return_value = None
    conn.fetchrow.side_effect = [{"status": "done", "result": {"question": {"question": "Which city?"}}},
                                 {"kind": kind, "status": status, "answer": answer, "expires_at": NOW + timedelta(days=2),
                                  "answered_at": NOW - answered if answered else None}]
    record = AsyncMock(); monkeypatch.setattr(scope, "event", record)
    assert await observe.refresh_source(conn, source()) == state
    if title:
        ended = record.await_args_list[0].args[3]
        assert (ended.title, ended.outcome) == (title, outcome) and "expired" not in ended.title


@pytest.mark.asyncio
async def test_old_generations_never_read_new_mutable_results():
    conn = Conn(); conn.fetchrow.return_value = {"recap_generation": 2}
    assert await observe.refresh_source(conn, source(kind="jobs", generation=1, job_search_id=uuid4())) == "deleted"
    assert await observe.refresh_source(conn, source(kind="jobs", generation=1, semantic_state="terminal")) == "terminal"


@pytest.mark.asyncio
async def test_collect_waits_for_every_child_then_freezes_once(monkeypatch):
    conn = Conn(); conn.fetch.return_value = [source(), source(id=uuid4(), kind="jobs")]
    refresh = AsyncMock(side_effect=["terminal", "live"]); monkeypatch.setattr(observe, "refresh_source", refresh)
    await reconcile.collect(conn, row())
    assert not any("manifest=" in c.args[0] for c in conn.execute.await_args_list)
    refresh.side_effect = ["terminal", "terminal"]
    await reconcile.collect(conn, row())
    assert any("finalize_after" in c.args[0] for c in conn.execute.await_args_list)


@pytest.mark.asyncio
async def test_source_deletion_revokes_entire_multisource_recap(monkeypatch):
    conn = Conn(); conn.fetch.return_value = [source()]
    monkeypatch.setattr(observe, "refresh_source", AsyncMock(return_value="deleted"))
    revoke = AsyncMock(); monkeypatch.setattr(reconcile, "tombstone", revoke)
    await reconcile.collect(conn, row())
    revoke.assert_awaited_once_with(conn, RECAP)


@pytest.mark.asyncio
async def test_owner_scoping_and_feature_off_before_migration(monkeypatch):
    monkeypatch.setattr(settings, "enabled", lambda: True)
    conn = Conn(); conn.fetchrow.return_value = None
    with pytest.raises(HTTPException) as exc:
        await service.owned(conn, RECAP, USER, COMPANY)
    assert exc.value.status_code == 404
    sql, *args = conn.fetchrow.await_args.args
    assert "owner_user_id=$2" in sql and "company_id=$3" in sql and "deleted_at IS NOT NULL" in sql
    assert args == [RECAP, USER, COMPANY]
    monkeypatch.setattr(settings, "enabled", lambda: False)
    conn.fetchval.return_value = None
    wire(monkeypatch, service, conn)
    assert await service.listing(USER, COMPANY) == {"recaps": [], "next_cursor": None}


@pytest.mark.asyncio
async def test_retry_grant_is_idempotent_and_lifetime_bounded(monkeypatch):
    conn = Conn(); wire(monkeypatch, service, conn)
    monkeypatch.setattr(settings, "available", lambda _: True)
    key = uuid4()
    owned = AsyncMock(return_value=row(state="queued", manual_retry_request_id=key))
    monkeypatch.setattr(service, "owned", owned)
    assert (await service.retry(USER, COMPANY, RECAP, key))["state"] == "queued"
    conn.fetchrow.assert_not_awaited()
    with pytest.raises(HTTPException) as exc:
        await service.retry(USER, COMPANY, RECAP, uuid4())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_tombstone_persists_independent_cleanup_and_fences_publish(monkeypatch):
    conn = Conn(); conn.fetchrow.return_value = {"company_id": COMPANY, "owner_user_id": USER}
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(s3_private_bucket="private"))
    await service.tombstone(conn, RECAP)
    assert "render_token=NULL" in conn.fetchrow.await_args_list[0].args[0]
    assert "manifest=NULL" in conn.fetchrow.await_args_list[0].args[0]
    assert "FOR UPDATE" in conn.fetchrow.await_args_list[1].args[0]
    assert any("cleanup_jobs" in c.args[0] for c in conn.execute.await_args_list)
    assert any("state='suppressed'" in c.args[0] for c in conn.execute.await_args_list)
    assert any("result-'recap'" in c.args[0] for c in conn.execute.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("handed", [True, False])
async def test_deleting_a_video_keeps_a_task_email_already_handed_to_it(monkeypatch, handed):
    conn = Conn()
    conn.fetchrow.side_effect = [{"company_id": COMPANY, "owner_user_id": USER}, {"state": "pending"}]
    conn.fetchval.return_value = 1 if handed else None
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(s3_private_bucket="private"))
    await service.tombstone(conn, RECAP, keep_mail=True)
    sql = [c.args[0] for c in conn.execute.await_args_list]
    assert any("state='suppressed'" in q for q in sql) is not handed
    assert any("SET mail_payload=NULL" in q for q in sql) is not handed
    assert any("not_before=NOW()" in q for q in sql) is handed


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,email,owner", [("research", False, "legacy"), ("jobs", False, "legacy"), ("run", False, "none"),
                                              ("research", True, "recap"), ("jobs", True, "recap"), ("run", True, "recap")])
async def test_a_task_email_changes_hands_only_when_recap_email_is_on(monkeypatch, kind, email, owner):
    # Recaps on, recap email off: every task email goes exactly as it always has.
    monkeypatch.setattr(settings, "enabled", lambda: True); monkeypatch.setattr(settings, "available", lambda _: True)
    monkeypatch.setattr(scope, "source_for_run", AsyncMock(return_value=None))
    conn = Conn(); conn.fetchrow.return_value = {"enabled": True, "email_enabled": email}
    conn.fetchval.side_effect = [True, 0, RECAP]  # personal, today's count, the new recap
    assert await scope.register(conn, kind=kind, source_id=uuid4(), user_id=USER, company_id=COMPANY, title="Task") == RECAP
    insert = next(c for c in conn.execute.await_args_list if "INSERT INTO mw_agent_recap_sources" in c.args[0])
    assert insert.args[6] == owner
    assert any("mw_agent_recap_deliveries" in c.args[0] for c in conn.execute.await_args_list) is (owner == "recap")


@pytest.mark.asyncio
async def test_a_failing_recap_hook_never_fails_the_operation_it_observes(monkeypatch):
    monkeypatch.setattr(settings, "enabled", lambda: True)
    conn = Conn(); conn.fetchrow.side_effect = RuntimeError("unexpected row shape")
    await scope.before_job_restart(conn, uuid4())
    # Unfrozen, the resting generation's recap is skipped rather than shown the newer search.
    fence = conn.execute.await_args.args[0]
    assert "source_hook_failed" in fence and "j.recap_generation=s.generation" in fence
    await scope.supersede_round(conn, {"id": uuid4(), "current_round": 2})
    conn.fetch.side_effect = RuntimeError("recap table unavailable")
    await scope.revoke_source(conn, "research", uuid4())
    conn.fetchval.side_effect = RuntimeError("no recap_generation column")
    assert await scope.register_job(conn, {"id": uuid4(), "user_id": USER, "company_id": COMPANY, "title": "Jobs"}) is None
    assert await scope.register_task(conn, {"id": uuid4(), "current_round": 1, "user_id": USER, "company_id": COMPANY}) is None


@pytest.mark.asyncio
async def test_enrollment_check_is_free_when_off(monkeypatch):
    conn = Conn(); wire(monkeypatch, scope, conn)
    monkeypatch.setattr(settings, "enabled", lambda: False)
    assert not await scope.enrolled(RUN)
    conn.fetchval.assert_not_awaited()
    monkeypatch.setattr(settings, "enabled", lambda: True); conn.fetchval.return_value = 1
    assert await scope.enrolled(RUN)
    assert "r.state IN ('collecting','waiting')" in conn.fetchval.await_args.args[0]
    conn.fetchval.side_effect = OSError("pool closed")
    assert not await scope.enrolled(RUN)
