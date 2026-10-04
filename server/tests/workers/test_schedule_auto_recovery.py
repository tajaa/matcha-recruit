"""Durable auto-schedule recovery seams; all database/broker calls are fake."""

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.workers.tasks import schedule_auto_generation as worker


NOW = datetime(2026, 10, 1, 16, tzinfo=timezone.utc)


def _rule(**changes):
    rule = {
        "id": uuid4(), "company_id": uuid4(), "location_id": uuid4(),
        "week_template_id": uuid4(), "enabled": True, "cadence": "weekly",
        "run_weekday": 4, "run_time": time(9), "target_weeks_ahead": 1,
        "target_week_start": None, "next_run_at": NOW, "schedule_version": 1,
        "timezone": "America/Los_Angeles", "company_status": "approved",
        "enabled_features": {"employee_schedule": True, "huume": True, "matcha_work": True},
        "signup_source": None, "last_status": None, "updated_at": NOW,
    }
    rule.update(changes)
    return rule


class _RunConn:
    def __init__(self, rule, *, locked=True, completion_failures=0, after_read=None):
        self.rule = rule
        self.locked = locked
        self.completion_failures = completion_failures
        self.after_read = after_read
        self.closed = False
        self.queries = []

    async def fetchval(self, query, *_args):
        return self.locked if "pg_try_advisory_lock" in query else None

    async def fetchrow(self, _query, *_args):
        snapshot = self.rule.copy()
        if self.after_read:
            self.after_read(self.rule)
        return snapshot

    async def execute(self, query, *args):
        self.queries.append((query, args))
        assert "schedule_version=" in query and "enabled=true" in query and "next_run_at=" in query
        if "last_status='feature_disabled'" in query:
            assert "WHERE id=$1 AND schedule_version=$2 AND enabled=true AND next_run_at=$3" in query
            key, version, occurrence = args
            update = {"enabled": False, "next_run_at": None, "last_status": "feature_disabled"}
        elif "last_status='retrying'" in query:
            message, key, version, occurrence = args
            update = {"last_status": "retrying", "last_message": message}
        elif "last_completed_at" in query:
            if self.completion_failures:
                self.completion_failures -= 1
                raise ConnectionError("completion write interrupted")
            status, message, generation_id, key, version, following, enabled, occurrence = args
            update = {"last_status": status, "last_message": message,
                      "last_generation_run_id": generation_id, "next_run_at": following, "enabled": enabled}
        else:
            key, version, occurrence, first_attempt_at = args
            # An in-flight claim must leave its only durable occurrence intact.
            setters = query.split("WHERE")[0]
            assert "SET next_run_at" not in setters and "enabled=" not in setters
            update = {"last_status": "running", "last_attempt_at": first_attempt_at}
        if (key, version, occurrence) != (self.rule["id"], self.rule["schedule_version"], self.rule["next_run_at"]):
            return "UPDATE 0"
        self.rule.update(update)
        return "UPDATE 1"

    async def close(self):
        self.closed = True


def _wire_run(monkeypatch, conn, generate):
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(worker, "generate_review_suggestion", generate)
    monkeypatch.setattr(worker, "_utcnow", lambda: NOW)


@pytest.mark.asyncio
async def test_planner_failure_keeps_occurrence_for_retry(monkeypatch):
    rule = _rule()
    conn = _RunConn(rule)

    async def first_attempt(**_kwargs):
        assert rule["last_status"] == "running"
        assert rule["enabled"] and rule["next_run_at"] == NOW
        raise ConnectionError("temporary planner dependency outage")

    generate = AsyncMock(side_effect=first_attempt)
    _wire_run(monkeypatch, conn, generate)
    with pytest.raises(ConnectionError):
        await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert conn.closed and rule["last_status"] == "retrying"
    # The cause is logged; the manager sees a plain status, not exception text.
    assert "temporary planner" not in rule["last_message"]
    assert rule["enabled"] and rule["next_run_at"] == NOW
    generate.side_effect = None
    generate.return_value = {"status": "generated", "generation_run_id": str(uuid4())}
    result = await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert result["status"] == "generated"
    assert rule["next_run_at"] == datetime(2026, 10, 8, 16, tzinfo=timezone.utc)
    assert generate.await_count == 2


@pytest.mark.asyncio
async def test_retries_share_one_window_and_then_fail_and_advance(monkeypatch):
    rule = _rule()
    conn = _RunConn(rule)
    generate = AsyncMock(side_effect=ValueError("deterministic planner bug"))
    _wire_run(monkeypatch, conn, generate)
    with pytest.raises(ValueError):
        await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert rule["last_attempt_at"] == NOW
    # A lease recovery inside the window retries and keeps the first attempt time.
    later = NOW + timedelta(seconds=worker.RETRY_WINDOW_SECONDS - 1)
    monkeypatch.setattr(worker, "_utcnow", lambda: later)
    with pytest.raises(ValueError):
        await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert rule["last_attempt_at"] == NOW and rule["last_status"] == "retrying"
    # Past the window the failure is terminal: no raise, so no Celery retry,
    # and the weekly rule moves to its next occurrence.
    monkeypatch.setattr(worker, "_utcnow", lambda: NOW + timedelta(seconds=worker.RETRY_WINDOW_SECONDS))
    result = await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert result["status"] == "failed" and "deterministic" not in result["message"]
    assert rule["last_status"] == "failed" and rule["enabled"]
    assert rule["next_run_at"] == datetime(2026, 10, 8, 16, tzinfo=timezone.utc)
    assert generate.await_count == 3


@pytest.mark.asyncio
async def test_repeated_worker_deaths_abandon_the_occurrence_without_planning(monkeypatch):
    # 'running' with an old first attempt: every earlier attempt was killed.
    age = worker.RETRY_WINDOW_SECONDS + worker.DISPATCH_LEASE_SECONDS
    rule = _rule(cadence="once", target_weeks_ahead=None, target_week_start=date(2026, 10, 4),
                 last_status="running", last_attempt_at=NOW)
    conn = _RunConn(rule)
    generate = AsyncMock()
    _wire_run(monkeypatch, conn, generate)
    monkeypatch.setattr(worker, "_utcnow", lambda: NOW + timedelta(seconds=age))
    result = await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert result["status"] == "failed"
    assert rule["last_status"] == "failed" and rule["next_run_at"] is None and rule["enabled"] is False
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_previous_occurrences_attempt_does_not_shorten_the_window(monkeypatch):
    rule = _rule(last_attempt_at=NOW - timedelta(days=7))
    conn = _RunConn(rule)
    generate = AsyncMock(side_effect=ConnectionError("outage"))
    _wire_run(monkeypatch, conn, generate)
    with pytest.raises(ConnectionError):
        await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert rule["last_attempt_at"] == NOW and rule["last_status"] == "retrying"


@pytest.mark.asyncio
async def test_completion_failure_replays_already_persisted_proposal(monkeypatch):
    rule = _rule(cadence="once", target_weeks_ahead=None, target_week_start=date(2026, 10, 4))
    conn = _RunConn(rule, completion_failures=1)
    generation_id = str(uuid4())
    generate = AsyncMock(side_effect=[
        {"status": "generated", "generation_run_id": generation_id},
        {"status": "already_present", "generation_run_id": generation_id},
    ])
    _wire_run(monkeypatch, conn, generate)
    with pytest.raises(ConnectionError, match="completion write interrupted"):
        await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert rule["enabled"] and rule["next_run_at"] == NOW
    result = await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert result["generation_run_id"] == generation_id
    assert rule["last_generation_run_id"] is not None
    assert rule["next_run_at"] is None and rule["enabled"] is False


@pytest.mark.asyncio
async def test_lock_contention_does_not_mark_rule_terminal(monkeypatch):
    rule = _rule(last_status="running")
    conn = _RunConn(rule, locked=False)
    generate = AsyncMock()
    _wire_run(monkeypatch, conn, generate)
    assert await worker._run(str(rule["id"]), 1, NOW.isoformat()) == {"skipped": True, "reason": "already_running"}
    assert conn.queries == [] and conn.closed
    assert rule["last_status"] == "running" and rule["next_run_at"] == NOW
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_obsolete_feature_disable_cannot_clobber_new_rule(monkeypatch):
    rule = _rule(enabled_features={"employee_schedule": True, "huume": False, "matcha_work": True})

    def manager_saves(current):
        current.update(schedule_version=2, enabled_features={"employee_schedule": True, "huume": True, "matcha_work": True})

    conn = _RunConn(rule, after_read=manager_saves)
    generate = AsyncMock()
    _wire_run(monkeypatch, conn, generate)
    result = await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert result["reason"] == "stale_or_disabled_rule"
    assert rule["enabled"] and rule["next_run_at"] == NOW and rule["schedule_version"] == 2
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_cannot_advance_a_newly_saved_version(monkeypatch):
    rule = _rule()
    conn = _RunConn(rule)
    new_occurrence = NOW + timedelta(days=2)

    async def generate(**_kwargs):
        rule.update(schedule_version=2, next_run_at=new_occurrence)
        return {"status": "generated"}

    _wire_run(monkeypatch, conn, AsyncMock(side_effect=generate))
    result = await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert result["reason"] == "stale_or_disabled_rule"
    assert rule["enabled"] and rule["next_run_at"] == new_occurrence


@pytest.mark.asyncio
async def test_long_outage_advances_directly_to_future_cadence(monkeypatch):
    rule = _rule()
    conn = _RunConn(rule)
    generate = AsyncMock()
    _wire_run(monkeypatch, conn, generate)
    now = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)
    monkeypatch.setattr(worker, "_utcnow", lambda: now)
    result = await worker._run(str(rule["id"]), 1, NOW.isoformat())
    assert result["status"] == "not_ready" and "already passed" in result["message"]
    assert rule["next_run_at"] == datetime(2026, 11, 5, 17, tzinfo=timezone.utc)
    assert rule["next_run_at"] > now
    generate.assert_not_awaited()


@pytest.mark.parametrize("delay,published", [(0, True), (120, True), (121, False), (7 * 86400, False)])
def test_only_short_etas_are_published(monkeypatch, delay, published):
    monkeypatch.setattr(worker, "_utcnow", lambda: NOW)
    publish = Mock()
    monkeypatch.setattr(worker.run_schedule_auto_generation, "apply_async", publish)
    occurrence = NOW + timedelta(seconds=delay)
    assert worker.enqueue_schedule_automation(uuid4(), 1, occurrence) is published
    assert publish.call_count == int(published)
    if published:
        assert publish.call_args.kwargs["eta"] == occurrence


class _DispatchConn:
    def __init__(self, rules, *, enabled=True, claimed=True, cycle_limit=100):
        self.rules = rules
        self.settings = {"enabled": enabled, "max_per_cycle": cycle_limit}
        self.claimed = claimed
        self.closed = False
        self.fetch_args = None
        self.writes = []

    async def fetchrow(self, _query, *_args):
        return self.settings

    async def fetchval(self, query, *_args):
        assert "last_run_at" in query and "enabled=true" in query
        return self.claimed

    async def fetch(self, query, horizon, lease, limit):
        self.fetch_args = (query, horizon, lease, limit)
        assert "LIMIT $3" in query and "r.updated_at < NOW()" in query
        candidates = [r.copy() for r in self.rules if r["enabled"] and r["next_run_at"] <= horizon
                      and (r["last_status"] not in {"queued", "running", "retrying"}
                           or r["updated_at"] < NOW - timedelta(seconds=lease))]
        return candidates[:limit]

    async def execute(self, query, *args):
        self.writes.append((query, args))
        if "INSERT INTO scheduler_settings" in query:
            assert "ON CONFLICT (task_key) DO NOTHING" in query
            return "INSERT 0 0"
        if "last_status='dispatch_failed'" in query:
            message, key, version, occurrence = args
            expected_status = "queued"
            update = {"last_status": "dispatch_failed", "last_message": message}
        else:
            key, version, occurrence, _lease = args
            expected_status = None
            update = {"last_status": "queued"}
        rule = next(r for r in self.rules if r["id"] == key)
        if rule["schedule_version"] != version or rule["next_run_at"] != occurrence or not rule["enabled"]:
            return "UPDATE 0"
        if expected_status and rule["last_status"] != expected_status:
            return "UPDATE 0"
        rule.update(**update, updated_at=NOW)
        return "UPDATE 1"

    async def close(self):
        self.closed = True


def _wire_dispatch(monkeypatch, conn, publish=None):
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(worker, "_utcnow", lambda: NOW)
    publish = publish or Mock(return_value=True)
    monkeypatch.setattr(worker, "enqueue_schedule_automation", publish)
    return publish


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,claimed,reason", [(False, True, "disabled"), (True, False, "another_chain")])
async def test_dispatcher_respects_operator_disable_and_duplicate_chain(monkeypatch, enabled, claimed, reason):
    conn = _DispatchConn([_rule()], enabled=enabled, claimed=claimed)
    publish = _wire_dispatch(monkeypatch, conn)
    assert await worker._dispatch() == {"skipped": True, "reason": reason, "reschedule": False}
    assert conn.closed and conn.fetch_args is None
    publish.assert_not_called()


@pytest.mark.asyncio
async def test_partial_publication_failure_releases_claim_for_next_sweep(monkeypatch):
    first, second = _rule(), _rule()
    conn = _DispatchConn([first, second])
    publish = _wire_dispatch(monkeypatch, conn, Mock(side_effect=[ConnectionError("Redis down"), True]))
    assert await worker._dispatch() == {"queued": 1, "failed": 1, "reschedule": True}
    assert first["next_run_at"] == NOW and first["last_status"] == "dispatch_failed"
    assert second["last_status"] == "queued"
    publish.side_effect = None
    assert await worker._dispatch() == {"queued": 1, "failed": 0, "reschedule": True}
    assert publish.call_count == 3


@pytest.mark.asyncio
async def test_publication_timeout_cannot_overwrite_task_that_already_started(monkeypatch):
    rule = _rule()
    conn = _DispatchConn([rule])

    def publish(*_args):
        rule["last_status"] = "running"
        raise ConnectionError("broker acknowledgement timed out")

    _wire_dispatch(monkeypatch, conn, Mock(side_effect=publish))
    assert (await worker._dispatch())["failed"] == 1
    assert rule["last_status"] == "running" and rule["next_run_at"] == NOW


@pytest.mark.asyncio
async def test_deferred_publication_releases_queue_lease_and_reports_truthfully(monkeypatch):
    rule = _rule()
    conn = _DispatchConn([rule])
    _wire_dispatch(monkeypatch, conn, Mock(return_value=False))
    assert await worker._dispatch() == {"queued": 0, "failed": 1, "reschedule": True}
    assert rule["last_status"] == "dispatch_failed" and rule["next_run_at"] == NOW
    assert "beyond the short dispatch horizon" in rule["last_message"]


@pytest.mark.asyncio
async def test_stale_running_and_queued_leases_recover_without_starving_new_work(monkeypatch):
    active = [_rule(last_status="running") for _ in range(100)]
    stale = [_rule(last_status=status, updated_at=NOW - timedelta(seconds=661))
             for status in ("running", "queued", "retrying")]
    new = _rule()
    conn = _DispatchConn(active + stale + [new])
    publish = _wire_dispatch(monkeypatch, conn)
    result = await worker._dispatch()
    assert result["queued"] == 4 and publish.call_count == 4
    assert all(r["last_status"] == "running" for r in active)
    assert all(r["last_status"] == "queued" for r in stale + [new])


@pytest.mark.asyncio
@pytest.mark.parametrize("configured,limit", [(0, 100), (-10, 1), (1000000, 1000)])
async def test_dispatch_cycle_and_horizon_are_bounded(monkeypatch, configured, limit):
    conn = _DispatchConn([], cycle_limit=configured)
    _wire_dispatch(monkeypatch, conn)
    assert (await worker._dispatch())["queued"] == 0
    assert conn.fetch_args[1:] == (NOW + timedelta(seconds=120), 660, limit)


def test_dispatcher_requeues_after_exception(monkeypatch):
    monkeypatch.setattr(worker, "_dispatch", AsyncMock(side_effect=ConnectionError("DB down")))
    reschedule = Mock()
    monkeypatch.setattr(worker, "_reschedule_dispatch", reschedule)
    with pytest.raises(ConnectionError):
        worker.dispatch_schedule_automation.run()
    reschedule.assert_called_once()


@pytest.mark.parametrize("reschedule", [False, True])
def test_only_winning_dispatch_chain_reschedules(monkeypatch, reschedule):
    monkeypatch.setattr(worker, "_dispatch", AsyncMock(return_value={"queued": 0, "reschedule": reschedule}))
    publish = Mock()
    monkeypatch.setattr(worker, "_reschedule_dispatch", publish)
    assert worker.dispatch_schedule_automation.run() == {"queued": 0}
    assert publish.call_count == int(reschedule)


@pytest.mark.parametrize("resume", [False, True])
def test_startup_dispatch_that_loses_the_claim_follows_up_once(monkeypatch, resume):
    skipped = {"skipped": True, "reason": "another_chain", "reschedule": False}
    monkeypatch.setattr(worker, "_dispatch", AsyncMock(return_value=skipped))
    publish = Mock()
    monkeypatch.setattr(worker, "_reschedule_dispatch", publish)
    worker.dispatch_schedule_automation.run(resume=resume)
    # The follow-up is a plain dispatch, so a live chain ends it after one hop.
    assert publish.call_count == int(resume)


def test_dispatch_chain_publication_failure_is_logged_for_startup_recovery(monkeypatch, caplog):
    monkeypatch.setattr(worker.dispatch_schedule_automation, "apply_async", Mock(side_effect=ConnectionError("Redis down")))
    worker._reschedule_dispatch()
    assert "worker startup resumes recovery" in caplog.text
