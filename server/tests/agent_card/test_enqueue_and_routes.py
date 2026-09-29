from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

from app.core.services import redis_cache
from app.matcha.services.billing import entitlements_service, token_budget_service
from app.matcha.services.matcha_work.agent_card import enqueue, quota


def _user(role="client"):
    return SimpleNamespace(id=uuid4(), role=role)


def _task(**over):
    task = {"id": uuid4(), "project_id": uuid4(), "company_id": uuid4(), "title": "Find me a balm",
            "description": "Vegan", "category": "agent", "board_column": "todo"}
    task.update(over)
    return task


# ── preflight ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_preflight_requires_pro(monkeypatch):
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", AsyncMock(return_value="lite"))
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(_user(), uuid4())
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "plan_required" and exc.value.detail["feature"] == "agent_cards"


@pytest.mark.asyncio
async def test_preflight_enforces_monthly_cap(monkeypatch):
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", AsyncMock(return_value="pro"))
    monkeypatch.setattr(enqueue, "card_agent_usage", AsyncMock(return_value={
        "limit": 40, "used": 40, "remaining": 0, "resets_at": "2026-10-01T00:00:00+00:00"}))
    budget = AsyncMock()
    monkeypatch.setattr(token_budget_service, "check_token_budget", budget)
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(_user(), uuid4())
    assert exc.value.status_code == 429 and exc.value.detail["code"] == "agent_run_limit"
    budget.assert_not_awaited()


@pytest.mark.asyncio
async def test_preflight_passes_then_checks_token_budget_and_rate_limit(monkeypatch):
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", AsyncMock(return_value="business"))
    monkeypatch.setattr(enqueue, "card_agent_usage", AsyncMock(return_value={"limit": 100, "used": 3, "remaining": 97}))
    order = []
    budget = AsyncMock(side_effect=lambda *_a: order.append("budget"))
    monkeypatch.setattr(token_budget_service, "check_token_budget", budget)
    limiter = AsyncMock(side_effect=lambda *_a: order.append("rate"))
    monkeypatch.setattr(redis_cache, "check_rate_limit", limiter)
    company, user = uuid4(), _user()
    await enqueue.preflight(user, company)
    budget.assert_awaited_once_with(company)
    limiter.assert_awaited_once_with(str(user.id), "espresso_agent_card_user", 20, 3600)
    assert order == ["budget", "rate"]


@pytest.mark.asyncio
async def test_preflight_rate_limit_refuses_before_any_insert(monkeypatch):
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", AsyncMock(return_value="pro"))
    monkeypatch.setattr(enqueue, "card_agent_usage", AsyncMock(return_value={"limit": 40, "used": 0, "remaining": 40}))
    monkeypatch.setattr(token_budget_service, "check_token_budget", AsyncMock())
    monkeypatch.setattr(redis_cache, "check_rate_limit", AsyncMock(side_effect=HTTPException(429, "slow down")))
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(_user(), uuid4())
    assert exc.value.detail == "slow down"


@pytest.mark.asyncio
async def test_admin_skips_every_gate(monkeypatch):
    plan = AsyncMock()
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", plan)
    await enqueue.preflight(_user("admin"), uuid4())
    plan.assert_not_awaited()


# ── enqueue ────────────────────────────────────────────────────────────────

class _Conn:
    def __init__(self, done_round=0, insert_error=None, used=0):
        self.done_round = done_round
        self.insert_error = insert_error
        self.used = used
        self.run_id = uuid4()
        self.inserted = None
        self.executed = []
        self.updates = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, query, *args):
        if "pg_advisory_xact_lock" in query:
            self.executed.append(("lock", args[0]))
        elif "SET status = 'failed'" in query:
            self.executed.append(("sweep" if "INTERVAL" in query else "fail", args))
            self.updates.append((query, args))
        elif "UPDATE mw_agent_card_prompts SET status = 'superseded'" in query:
            self.executed.append(("close_prompts", args))
        else:
            raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "COUNT(*)" in query:
            self.executed.append(("count", args))
            return self.used
        if "MAX(round)" in query:
            return self.done_round
        if "INSERT INTO mw_project_agent_runs" in query:
            self.executed.append(("insert", args))
            if self.insert_error:
                raise self.insert_error
            self.inserted = args
            return self.run_id
        raise AssertionError(query)


@pytest.fixture
def wired(monkeypatch):
    holder = {"conn": _Conn()}

    @asynccontextmanager
    async def get_connection():
        yield holder["conn"]

    monkeypatch.setattr(enqueue, "get_connection", get_connection)
    monkeypatch.setattr(enqueue, "preflight", AsyncMock())
    monkeypatch.setattr(enqueue, "require_plan", AsyncMock(return_value="pro"))
    from app.workers.tasks import agent_card as worker

    dispatch = Mock()
    monkeypatch.setattr(worker.run_card_agent, "apply_async", dispatch)
    holder["dispatch"] = dispatch
    return holder


@pytest.mark.asyncio
async def test_first_run_is_round_one_and_dispatches(wired, monkeypatch):
    monkeypatch.delenv("AGENT_CARD_QUEUE", raising=False)
    out = await enqueue.enqueue_card_agent(task=_task(), user=_user(), reason="created")
    assert out["round"] == 1 and out["status"] == "queued"
    args = wired["conn"].inserted
    assert args[3] == "Find me a balm\n\nVegan"
    assert args[6] == 1
    assert wired["dispatch"].call_args.kwargs == {"args": [out["run_id"]], "queue": None}
    enqueue.preflight.assert_awaited_once()


@pytest.mark.asyncio
async def test_locks_are_user_then_card_then_stale_sweep_then_count_then_insert(wired):
    task, user = _task(), _user()
    await enqueue.enqueue_card_agent(task=task, user=user, reason="rerun", skip_preflight=True)
    steps = [step[0] if step[0] != "lock" else f"lock:{step[1].split(':', 1)[1]}" for step in wired["conn"].executed]
    assert steps == ["lock:card_agent_cap", "lock:card_agent", "sweep", "count", "insert", "close_prompts"]
    locks = [step[1] for step in wired["conn"].executed if step[0] == "lock"]
    assert locks[0].startswith(str(user.id)) and locks[1].startswith(str(task["id"]))


@pytest.mark.asyncio
async def test_stale_live_runs_are_swept_so_a_dead_worker_cannot_block_reruns(wired):
    task = _task()
    await enqueue.enqueue_card_agent(task=task, user=_user(), reason="rerun", skip_preflight=True)
    query, args = wired["conn"].updates[0]
    assert "status IN ('queued', 'running')" in query
    assert "INTERVAL '11 minutes'" in query
    assert "COALESCE(started_at, created_at)" in query
    assert args == (task["id"],)


@pytest.mark.asyncio
async def test_redirect_starts_next_round_on_configured_queue(wired, monkeypatch):
    monkeypatch.setenv("AGENT_CARD_QUEUE", "agent_cards")
    wired["conn"].done_round = 2
    out = await enqueue.enqueue_card_agent(
        task=_task(board_column="changes_requested"), user=_user(), reason="redirect", skip_preflight=True,
    )
    assert out["round"] == 3
    assert wired["dispatch"].call_args.kwargs["queue"] == "agent_cards"
    enqueue.preflight.assert_not_awaited()


@pytest.mark.asyncio
async def test_cap_is_enforced_atomically_even_when_preflight_was_skipped(wired):
    wired["conn"].used = 40  # two cards created at once both passed the advisory preflight
    with pytest.raises(HTTPException) as exc:
        await enqueue.enqueue_card_agent(task=_task(), user=_user(), reason="created", skip_preflight=True)
    assert exc.value.status_code == 429 and exc.value.detail["code"] == "agent_run_limit"
    assert exc.value.detail["limit"] == 40 and exc.value.detail["used"] == 40
    assert wired["conn"].inserted is None
    wired["dispatch"].assert_not_called()


@pytest.mark.asyncio
async def test_plan_below_pro_is_refused_even_when_preflight_was_skipped(wired, monkeypatch):
    monkeypatch.setattr(enqueue, "require_plan", AsyncMock(side_effect=HTTPException(403, {"code": "plan_required"})))
    with pytest.raises(HTTPException) as exc:
        await enqueue.enqueue_card_agent(task=_task(), user=_user(), reason="created", skip_preflight=True)
    assert exc.value.status_code == 403 and wired["conn"].inserted is None


@pytest.mark.asyncio
async def test_admin_is_never_capped(wired):
    wired["conn"].used = 10_000
    out = await enqueue.enqueue_card_agent(task=_task(), user=_user("admin"), reason="rerun")
    assert out["status"] == "queued"
    assert not any(step[0] == "count" for step in wired["conn"].executed)
    enqueue.require_plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_run_conflict_is_409(wired):
    wired["conn"].insert_error = asyncpg.UniqueViolationError("dup")
    with pytest.raises(HTTPException) as exc:
        await enqueue.enqueue_card_agent(task=_task(), user=_user(), reason="rerun")
    assert exc.value.status_code == 409
    wired["dispatch"].assert_not_called()


@pytest.mark.asyncio
async def test_broker_down_fails_the_row_so_it_cannot_hold_the_live_run_slot(wired):
    wired["dispatch"].side_effect = ConnectionError("redis down")
    with pytest.raises(HTTPException) as exc:
        await enqueue.enqueue_card_agent(task=_task(), user=_user(), reason="created")
    assert exc.value.status_code == 503
    fail = [u for u in wired["conn"].updates if "AND status = 'queued'" in u[0]]
    assert len(fail) == 1 and "Could not be queued" in fail[0][0]
    assert fail[0][1] == (wired["conn"].run_id,)
    # The current result's chat questions stay open: nothing replaced it.
    assert "close_prompts" not in [step[0] for step in wired["conn"].executed]


@pytest.mark.asyncio
async def test_open_questions_close_only_after_the_new_run_is_dispatched(wired):
    order = []
    wired["dispatch"].side_effect = lambda *a, **k: order.append("dispatch")
    original = wired["conn"].execute

    async def execute(query, *args):
        if "mw_agent_card_prompts" in query:
            order.append("close_prompts")
        return await original(query, *args)

    wired["conn"].execute = execute
    await enqueue.enqueue_card_agent(task=_task(), user=_user(), reason="redirect", skip_preflight=True)
    assert order == ["dispatch", "close_prompts"]


@pytest.mark.asyncio
async def test_a_failure_closing_questions_never_fails_the_enqueue(wired):
    original = wired["conn"].execute

    async def execute(query, *args):
        if "mw_agent_card_prompts" in query:
            raise RuntimeError("db blip")
        return await original(query, *args)

    wired["conn"].execute = execute
    out = await enqueue.enqueue_card_agent(task=_task(), user=_user(), reason="rerun", skip_preflight=True)
    assert out["status"] == "queued"


@pytest.mark.asyncio
@pytest.mark.parametrize("task,code", [
    (_task(category="research"), 400),
    (_task(board_column="review"), 409),
    (_task(board_column="done"), 409),
])
async def test_only_open_agent_cards_run(wired, task, code):
    with pytest.raises(HTTPException) as exc:
        await enqueue.enqueue_card_agent(task=task, user=_user(), reason="rerun")
    assert exc.value.status_code == code


# ── quota + entitlements ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_counts_against_plan_limit(monkeypatch):
    class _C:
        async def fetchval(self, query, *args):
            assert "status IN ('queued', 'running', 'done')" in query
            return 7

    @asynccontextmanager
    async def cod():
        yield _C()

    monkeypatch.setattr(quota, "connection_or_direct", cod)
    usage = await quota.card_agent_usage(uuid4(), plan="pro")
    assert usage["limit"] == 40 and usage["used"] == 7 and usage["remaining"] == 33
    free = await quota.card_agent_usage(uuid4(), plan="free")
    assert free["limit"] == 0 and free["remaining"] == 0


def test_next_month_rollover():
    assert quota._next_month_start(datetime(2026, 12, 15, tzinfo=timezone.utc)) == datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert quota._next_month_start(datetime(2026, 9, 28, tzinfo=timezone.utc)) == datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_agent_cards_feature_is_pro_and_up():
    assert entitlements_service.features_for_plan("pro")["agent_cards"]
    assert entitlements_service.features_for_plan("business")["agent_cards"]
    assert not entitlements_service.features_for_plan("lite")["agent_cards"]
    assert not entitlements_service.features_for_plan("free")["agent_cards"]


@pytest.mark.asyncio
async def test_entitlements_payload_reports_agent_runs(monkeypatch):
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", AsyncMock(return_value="pro"))
    monkeypatch.setattr(quota, "card_agent_usage", AsyncMock(return_value={"limit": 40, "used": 1, "remaining": 39}))
    from app.matcha.services.matcha_work import matcha_work_document as doc_svc

    monkeypatch.setattr(doc_svc, "check_token_quota", AsyncMock(side_effect=RuntimeError("no db")))
    payload = await entitlements_service.resolve_entitlements(uuid4())
    assert payload["quotas"]["agent_runs"]["remaining"] == 39


# ── route hooks ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_route_gates_before_insert_and_queues_after(monkeypatch):
    from app.matcha.routes.matcha_work import tasks as tasks_routes
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    project = {"company_id": uuid4(), "title": "Board"}
    monkeypatch.setattr(tasks_routes, "_verify_project_access", AsyncMock(return_value=(project, "owner")))
    order = []
    monkeypatch.setattr(enqueue, "preflight", AsyncMock(side_effect=lambda *_a: order.append("preflight")))

    async def create(**kwargs):
        order.append(("create", kwargs["board_column"], kwargs["category"]))
        return {"id": str(uuid4()), "project_id": str(uuid4()), "company_id": project["company_id"],
                "category": "agent", "board_column": "todo", "title": kwargs["title"]}

    monkeypatch.setattr(pt_svc, "create_project_task", create)
    queued = AsyncMock(return_value={"run_id": "r", "round": 1, "status": "queued"})
    monkeypatch.setattr(enqueue, "enqueue_card_agent", queued)

    result = await tasks_routes.create_project_task_endpoint(
        uuid4(), {"title": "Find me a balm", "category": "agent", "board_column": "review"}, _user(),
    )
    assert order == ["preflight", ("create", "todo", "agent")]
    assert result["agent_run"]["status"] == "queued"
    assert queued.await_args.kwargs["skip_preflight"] is True


@pytest.mark.asyncio
async def test_create_route_refuses_without_plan_and_creates_nothing(monkeypatch):
    from app.matcha.routes.matcha_work import tasks as tasks_routes
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    monkeypatch.setattr(tasks_routes, "_verify_project_access", AsyncMock(return_value=({"company_id": uuid4()}, "owner")))
    monkeypatch.setattr(enqueue, "preflight", AsyncMock(side_effect=HTTPException(403, {"code": "plan_required"})))
    create = AsyncMock()
    monkeypatch.setattr(pt_svc, "create_project_task", create)
    with pytest.raises(HTTPException):
        await tasks_routes.create_project_task_endpoint(uuid4(), {"title": "x", "category": "agent"}, _user())
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_route_reports_a_queue_failure_without_failing_create(monkeypatch):
    from app.matcha.routes.matcha_work import tasks as tasks_routes
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    monkeypatch.setattr(tasks_routes, "_verify_project_access", AsyncMock(return_value=({"company_id": uuid4()}, "owner")))
    monkeypatch.setattr(enqueue, "preflight", AsyncMock())
    monkeypatch.setattr(pt_svc, "create_project_task", AsyncMock(return_value={"id": str(uuid4()), "category": "agent"}))
    monkeypatch.setattr(enqueue, "enqueue_card_agent", AsyncMock(side_effect=HTTPException(429, "slow down")))
    result = await tasks_routes.create_project_task_endpoint(uuid4(), {"title": "x", "category": "agent"}, _user())
    assert result["agent_run_error"] == "slow down"


@pytest.mark.asyncio
async def test_create_route_leaves_other_cards_alone(monkeypatch):
    from app.matcha.routes.matcha_work import tasks as tasks_routes
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    monkeypatch.setattr(tasks_routes, "_verify_project_access", AsyncMock(return_value=({"company_id": uuid4()}, "owner")))
    preflight = AsyncMock()
    monkeypatch.setattr(enqueue, "preflight", preflight)
    monkeypatch.setattr(pt_svc, "create_project_task", AsyncMock(return_value={"id": str(uuid4()), "category": "bug"}))
    result = await tasks_routes.create_project_task_endpoint(uuid4(), {"title": "x", "category": "bug"}, _user())
    preflight.assert_not_awaited()
    assert "agent_run" not in result


@pytest.mark.asyncio
async def test_create_route_blocks_read_only_collaborators(monkeypatch):
    from app.matcha.routes.matcha_work import tasks as tasks_routes

    monkeypatch.setattr(tasks_routes, "_verify_project_access", AsyncMock(return_value=({"company_id": uuid4()}, "viewer")))
    with pytest.raises(HTTPException) as exc:
        await tasks_routes.create_project_task_endpoint(uuid4(), {"title": "x", "category": "agent"}, _user())
    assert exc.value.status_code == 403


def _reject_env(monkeypatch, *, category, role="owner", reject_result=None):
    """Wire the reject endpoint; returns the ordered call log."""
    from app.matcha.routes.matcha_work import tasks as tasks_routes
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    log = []

    class _C:
        async def fetchval(self, query, *args):
            assert "SELECT category FROM mw_tasks" in query
            return category

    @asynccontextmanager
    async def gc():
        yield _C()

    monkeypatch.setattr(tasks_routes, "get_connection", gc)
    monkeypatch.setattr(tasks_routes, "_verify_project_access", AsyncMock(
        return_value=({"title": "B", "company_id": uuid4()}, role)))

    async def reject(*_a, **_k):
        log.append("reject")
        return reject_result or {"id": str(uuid4()), "category": category, "board_column": "changes_requested"}

    monkeypatch.setattr(pt_svc, "reject_project_task", reject)
    monkeypatch.setattr(enqueue, "preflight", AsyncMock(side_effect=lambda *_a: log.append("preflight")))
    queued = AsyncMock(side_effect=lambda **_k: log.append("enqueue") or {"run_id": "r", "round": 2, "status": "queued"})
    monkeypatch.setattr(enqueue, "enqueue_card_agent", queued)
    return tasks_routes, log, queued


@pytest.mark.asyncio
async def test_reject_gates_before_the_card_moves_then_redirects(monkeypatch):
    tasks_routes, log, queued = _reject_env(monkeypatch, category="agent")
    result = await tasks_routes.reject_project_task_endpoint(uuid4(), uuid4(), {"note": "Only vegan"}, _user())
    assert log == ["preflight", "reject", "enqueue"]
    assert queued.await_args.kwargs["reason"] == "redirect" and queued.await_args.kwargs["skip_preflight"] is True
    assert result["agent_run"]["round"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status,detail", [
    (403, {"code": "plan_required"}), (429, {"code": "agent_run_limit"}), (409, "busy"),
])
async def test_refused_redirect_leaves_the_card_in_review_with_its_note_unspent(monkeypatch, status, detail):
    tasks_routes, log, queued = _reject_env(monkeypatch, category="agent")
    enqueue.preflight.side_effect = HTTPException(status, detail)
    with pytest.raises(HTTPException) as exc:
        await tasks_routes.reject_project_task_endpoint(uuid4(), uuid4(), {"note": "Only vegan"}, _user())
    assert exc.value.status_code == status
    assert log == []  # reject never ran: the card is still in Review


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["viewer", "commenter"])
async def test_read_only_collaborators_cannot_spend_a_run_by_rejecting(monkeypatch, role):
    tasks_routes, log, queued = _reject_env(monkeypatch, category="agent", role=role)
    with pytest.raises(HTTPException) as exc:
        await tasks_routes.reject_project_task_endpoint(uuid4(), uuid4(), {"note": "x"}, _user())
    assert exc.value.status_code == 403
    assert log == []


@pytest.mark.asyncio
async def test_queue_refusal_after_reject_is_reported_and_note_is_kept(monkeypatch):
    tasks_routes, log, queued = _reject_env(monkeypatch, category="agent")
    queued.side_effect = HTTPException(503, "Couldn't start the agent right now.")
    result = await tasks_routes.reject_project_task_endpoint(uuid4(), uuid4(), {"note": "x"}, _user())
    assert log == ["preflight", "reject"]
    assert result["agent_run_error"] == "Couldn't start the agent right now."
    assert result["board_column"] == "changes_requested"


@pytest.mark.asyncio
async def test_reject_leaves_other_cards_alone(monkeypatch):
    tasks_routes, log, queued = _reject_env(monkeypatch, category="research", role="viewer")
    await tasks_routes.reject_project_task_endpoint(uuid4(), uuid4(), {"note": "x"}, _user())
    assert log == ["reject"]
    queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_runs_list_and_rerun_endpoints(monkeypatch):
    from app.matcha.routes.matcha_work import agent_cards

    run_id = uuid4()
    now = datetime.now(timezone.utc)

    class _C:
        async def fetchrow(self, query, *args):
            return {"id": args[0], "project_id": args[1], "company_id": uuid4(), "title": "t",
                    "description": None, "category": "agent", "board_column": "todo"}

        async def fetch(self, query, *args):
            if "mw_project_agent_steps" in query:
                return [{"run_id": run_id, "seq": 1, "kind": "search", "label": "Searched", "status": "ok"}]
            if "mw_agent_purchase_requests" in query:
                assert "user_id = $2" in query  # only the caller's own handoffs
                return [{"id": uuid4(), "run_id": run_id, "item_name": "Balm", "retailer": "Shop",
                         "checkout_url": "https://shop.example.com/b", "amount": Decimal("7.50"),
                         "currency": "USD", "card_last4": "4242", "status": "handoff", "created_at": now}]
            return [{"id": run_id, "round": 1, "status": "done", "result": '{"headline": "h"}', "error": None,
                     "search_calls": 2, "model_calls": 3, "created_at": now, "started_at": now, "completed_at": now}]

    @asynccontextmanager
    async def gc():
        yield _C()

    monkeypatch.setattr(agent_cards, "get_connection", gc)
    monkeypatch.setattr(agent_cards, "_verify_project_access", AsyncMock(return_value=({}, "owner")))
    out = await agent_cards.list_agent_runs_endpoint(uuid4(), uuid4(), _user())
    assert out["runs"][0]["result"] == {"headline": "h"}
    assert out["runs"][0]["steps"][0]["kind"] == "search"
    assert out["purchases"][0]["amount"] == 7.5 and out["purchases"][0]["card_last4"] == "4242"

    queued = AsyncMock(return_value={"run_id": "r", "round": 1, "status": "queued"})
    monkeypatch.setattr(enqueue, "enqueue_card_agent", queued)
    assert (await agent_cards.rerun_agent_endpoint(uuid4(), uuid4(), _user()))["status"] == "queued"
    assert queued.await_args.kwargs["reason"] == "rerun"

    monkeypatch.setattr(agent_cards, "_verify_project_access", AsyncMock(return_value=({}, "viewer")))
    with pytest.raises(HTTPException):
        await agent_cards.rerun_agent_endpoint(uuid4(), uuid4(), _user())
