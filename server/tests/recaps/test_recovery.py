from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.matcha.models.matcha_work.recaps import Event, Fact, Manifest
from app.matcha.services.matcha_work.recaps import capture, media_job, observe, reconcile, scope, settings
from .test_lifecycle import NOW, RECAP, RUN, USER, Conn, row, source, wire


@pytest.mark.asyncio
async def test_dead_phase_cannot_block_completed_owner(monkeypatch):
    conn = Conn(); conn.fetchrow.return_value = {"status": "running", "result": {}}; conn.fetch.return_value = []
    monkeypatch.setattr(scope, "capture_current", AsyncMock(return_value=False))
    record = AsyncMock(); monkeypatch.setattr(scope, "event", record)
    assert await observe.refresh_source(conn, source(role="phase")) == "terminal"
    record.assert_not_awaited()
    scope.capture_current.return_value = True
    assert await observe.refresh_source(conn, source(role="phase")) == "live"


@pytest.mark.asyncio
async def test_superseded_round_recovery_does_not_copy_new_results(monkeypatch):
    conn = Conn(); conn.fetchrow.return_value = {"status":"running", "n":1, "current_round":2, "deleted_at":None}
    record = AsyncMock(); monkeypatch.setattr(scope, "event", record)
    assert await observe.refresh_source(conn, source(kind="research", task_round_id=uuid4())) == "terminal"
    assert record.await_args.args[3].outcome == "partial"
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_action_aggregation_preserves_recorded_subject(monkeypatch):
    conn = Conn(); monkeypatch.setattr(observe, "refresh_source", AsyncMock(return_value="terminal"))
    monkeypatch.setattr(settings, "available", lambda _: True)
    event = Event(title="Sent email", kind="action_resolved", outcome="unknown", occurred_at=NOW,
                  facts=[Fact(label="Subject", value="Selected message")])
    conn.fetch.side_effect = [[source()], [{"snapshot":event.model_dump(mode="json"), "asset":None}],
        [{"tool":"send_email", "kind":"commit", "status":"unknown", "mode":"live", "queued":None, "count":3, "created_at":NOW}]]
    await reconcile.collect(conn, row(source_completed_at=NOW, finalize_after=NOW-timedelta(seconds=1)))
    freeze = next(call for call in conn.execute.await_args_list if "manifest=$2" in call.args[0])
    manifest = Manifest.model_validate_json(freeze.args[2])
    assert any(f.value == "Selected message" for e in manifest.transcript for f in e.facts)
    assert any(f.label == "Additional actions with this outcome" and f.value == "2"
               for e in manifest.transcript for f in e.facts)


@pytest.mark.asyncio
async def test_recovery_repairs_lost_jobs_and_revokes_expired_artifacts(monkeypatch):
    from app.workers.tasks import recaps as tasks
    conn = Conn(); wire(monkeypatch, reconcile, conn); conn.fetchval.side_effect = [True, True]
    candidate, invalid, expired, render, delivery, cleanup = [uuid4() for _ in range(6)]
    conn.fetch.side_effect = [[{"id":candidate}], [{"id":invalid}], [{"id":expired}],
                             [{"id":render}], [{"id":delivery}], [{"id":cleanup}]]
    conn.fetchrow.return_value = row(id=candidate)
    collect = AsyncMock(); monkeypatch.setattr(reconcile, "collect", collect)
    revoke = AsyncMock(); monkeypatch.setattr(reconcile, "tombstone", revoke)
    published = []
    for name in ("render_recap", "deliver_recap", "cleanup_recap"):
        monkeypatch.setattr(tasks, name, SimpleNamespace(apply_async=lambda **kwargs: published.append(kwargs)))
    assert await reconcile.sweep()
    collect.assert_awaited_once()
    assert {call.kwargs["state"] for call in revoke.await_args_list} == {"deleted", "expired"}
    assert published == [{"args":[str(render)],"queue":settings.RENDER_QUEUE},
                         {"args":[str(delivery)],"queue":"celery"},
                         {"args":[str(cleanup)],"queue":settings.RENDER_QUEUE}]
    sql = " ".join(call.args[0] for call in conn.execute.await_args_list)
    assert "send_lease_expired" in sql and "render_lease_expired" in sql and "render_queue_timeout" in sql


@pytest.mark.asyncio
async def test_sweep_stops_without_schema_or_dispatch_claim(monkeypatch):
    conn = Conn(); wire(monkeypatch, reconcile, conn); conn.fetchval.return_value = False
    assert not await reconcile.sweep()
    conn.fetch.assert_not_awaited()
    conn.fetchval.side_effect = [True, False]
    assert not await reconcile.sweep()
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_completion_is_persisted_and_partial_work_requeues(monkeypatch):
    from app.matcha.services.matcha_work.recaps import storage
    conn = Conn(); wire(monkeypatch, reconcile, conn); conn.fetchrow.return_value = {"bucket":"private", "prefix":"generated/"}
    remove = AsyncMock(return_value=False); monkeypatch.setattr(storage, "cleanup", remove)
    await reconcile.cleanup_job(RECAP)
    assert conn.execute.await_args.args[2] == "pending"
    remove.return_value = True
    await reconcile.cleanup_job(RECAP)
    assert conn.execute.await_args.args[2] == "done"
    conn.fetchrow.return_value = None
    await reconcile.cleanup_job(RECAP)
    assert remove.await_count == 2


@pytest.mark.asyncio
async def test_cdp_failure_uses_only_enrolled_checkpoint(monkeypatch):
    conn = Conn(); wire(monkeypatch, capture, conn); conn.fetchval.return_value = True
    monkeypatch.setattr(settings, "enabled", lambda: True); monkeypatch.setattr(settings, "available", lambda _: True)
    monkeypatch.setattr(capture, "get_settings", lambda: SimpleNamespace(espresso_recaps_capture_enabled=True))
    monkeypatch.setattr(scope, "source_for_run", AsyncMock(return_value=source()))
    page = SimpleNamespace(context=SimpleNamespace(new_cdp_session=AsyncMock(side_effect=RuntimeError())), screenshot=AsyncMock(return_value=b"jpeg"))
    store = AsyncMock(); monkeypatch.setattr(capture, "_store", store)
    token = scope.current_run.set(RUN)
    try:
        async with capture.window(page) as window: window.accepted = True
    finally: scope.current_run.reset(token)
    assert store.await_args.args[1] == [(0.0, b"jpeg")]
    assert "capture_windows_reserved<8" in conn.fetchval.await_args.args[0]


def test_media_entrypoint_accepts_only_fixed_operation_and_uuid(monkeypatch):
    bootstrap = Mock(); monkeypatch.setattr(media_job, "load_recap_worker_settings", bootstrap)
    operation = AsyncMock(); monkeypatch.setattr(media_job, "render_job", operation)
    monkeypatch.setattr(media_job.sys, "argv", ["media_job", "render", str(RECAP)])
    media_job.main()
    operation.assert_awaited_once_with(RECAP); bootstrap.assert_called_once()
    monkeypatch.setattr(media_job.sys, "argv", ["media_job", "render", "bad-id"])
    with pytest.raises(ValueError): media_job.main()


def test_availability_requires_explicit_owner_and_private_bucket(monkeypatch):
    config = SimpleNamespace(espresso_recaps_enabled=True, espresso_recaps_allowed_users=f" {USER}, {uuid4()}", s3_private_bucket="private")
    monkeypatch.setattr(settings, "get_settings", lambda: config)
    assert settings.available(USER)
    assert not settings.available(uuid4())
    config.s3_private_bucket = ""
    assert not settings.available(USER)
    config.espresso_recaps_enabled = False
    assert not settings.enabled()
