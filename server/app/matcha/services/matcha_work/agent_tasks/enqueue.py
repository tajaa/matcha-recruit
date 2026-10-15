"""Gate, create and dispatch a task, and start its follow-up rounds.

`preflight` is every refusal knowable up front: Tasks switched on, the kind
of workspace, the playbook's own needs, the plan, consent, the token budget
and a daily rate limit. `create_task` then counts and inserts under the
shared allowance lock (`allowance.lock`): the monthly units, and at most
`MAX_LIVE` tasks running at once (a waiting task holds no worker, so it
doesn't count).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.database import connection_or_direct
from app.matcha.services.billing.entitlements_service import PLAN_PRO, require_plan

from . import allowance, document, job_tasks, model_run, playbooks, service
from .playbook import Playbook

logger = logging.getLogger(__name__)

ENTITLEMENT = "agent_tasks"
MAX_LIVE = 2
DAILY_CREATES = 10
# A refine is free but can run a whole new search, so follow-ups are rate limited too.
DAILY_ROUNDS = 30
MAX_BRIEF_BYTES = 8_000
# Unset: Celery's default queue. A task is a chain of short worker tasks, so
# on the single-slot main worker it interleaves with everything else.
_QUEUE_ENVS = ("AGENT_TASKS_QUEUE", "AGENT_CARD_QUEUE")


def queue_for() -> str | None:
    for name in _QUEUE_ENVS:
        if os.getenv(name):
            return os.getenv(name)
    return None


def _is_admin(user) -> bool:
    return (getattr(user, "role", "") or "").lower() == "admin"


def tasks_enabled(user) -> bool:
    """Tasks is off until the Mac tab ships (`ESPRESSO_TASKS_ENABLED`); admins
    can use it either way."""
    from app.config import get_settings

    return _is_admin(user) or bool(getattr(get_settings(), "espresso_tasks_enabled", False))


def _limit_error(usage: dict, cost: int) -> HTTPException:
    return HTTPException(status_code=429, detail={
        "code": "task_limit",
        "message": "You've used this month's tasks." if usage["remaining"] <= 0
        else f"That needs {cost} units and you have {usage['remaining']} left this month.",
        "cost": cost,
        **usage,
    })


async def _daily(user_id: str, action: str, limit: int, what: str) -> None:
    """The per-day cap, refused in words the person (and Espresso, which
    relays it) can act on, not a bare "Too many requests"."""
    from app.core.services.redis_cache import check_rate_limit

    try:
        await check_rate_limit(user_id, action, limit, 86400)
    except HTTPException as exc:
        if exc.status_code != 429:
            raise
        raise HTTPException(status_code=429, detail={
            "code": "daily_limit",
            "message": f"That's {limit} {what} today, the most in a day. Try again tomorrow.",
        }) from exc


def _live_error() -> HTTPException:
    return HTTPException(status_code=409, detail={
        "code": "task_running",
        "message": f"{MAX_LIVE} tasks are already running. Wait for one to finish or cancel it.",
    })


async def dispatch(task_id: UUID, token: UUID, *, countdown: int = 0) -> None:
    """Queue the task's next phase. Raises when the broker refuses it."""
    from app.workers.tasks.agent_tasks import run_agent_task_phase

    run_agent_task_phase.apply_async(
        args=[str(task_id), str(token)], queue=queue_for(), countdown=max(0, int(countdown)),
    )


async def _consent(user, company_id: UUID, playbook: Playbook, consent_version: str | None) -> None:
    if playbook.consent is None:
        return
    from app.matcha.services.matcha_work.agent_runtime import grants

    rows = await grants.list_rows(user.id)
    if not grants.is_active(rows.get(playbook.consent), playbook.consent):
        # Raises 409 consent_required (with the disclosure) unless they just agreed.
        await grants.enable(user.id, company_id, playbook.consent, consent_version=consent_version)


async def preflight(user, company_id: UUID, playbook: Playbook, *, consent_version: str | None = None) -> str | None:
    """Raises HTTPException. Returns the plan (None for an admin)."""
    if not tasks_enabled(user):
        raise HTTPException(status_code=403, detail={"code": "feature_disabled",
                                                     "message": "Tasks aren't available yet."})
    if playbook.personal_only:
        from app.matcha.services.matcha_work.agent_runtime.enqueue import workspace_enabled

        if not await workspace_enabled(company_id):
            raise HTTPException(status_code=403, detail={
                "code": "feature_disabled",
                "message": "Espresso tasks come with a personal Espresso account.",
            })
    if playbook.engine != "chain":
        raise HTTPException(status_code=400, detail=f"{playbook.label} tasks are started from their own screen.")
    if not playbook.env_ready():
        raise HTTPException(status_code=503, detail=f"{playbook.label} isn't available right now.")
    plan = None
    if not _is_admin(user):
        plan = await require_plan(user.id, PLAN_PRO, ENTITLEMENT)
    await _consent(user, company_id, playbook, consent_version)
    if not _is_admin(user):
        from app.matcha.services.billing import token_budget_service

        await token_budget_service.check_token_budget(company_id)
        await _daily(str(user.id), "espresso_agent_task_user", DAILY_CREATES, "tasks started")
    return plan


async def _live_count(conn, user_id: UUID, *, besides: UUID | None = None) -> int:
    return int(await conn.fetchval(
        f"""SELECT COUNT(*) FROM mw_agent_tasks
            WHERE user_id = $1 AND engine = 'chain' AND deleted_at IS NULL
              AND status IN ({service._LIVE_SQL}) AND ($2::uuid IS NULL OR id <> $2)""",
        user_id, besides,
    ) or 0)


async def _owned_inputs(conn, user_id: UUID, company_id: UUID, ids: list[UUID]) -> list[UUID]:
    if not ids:
        return []
    found = {row["id"] for row in await conn.fetch(
        "SELECT id FROM mw_agent_inputs WHERE id = ANY($1::uuid[]) AND user_id = $2 AND company_id = $3",
        ids, user_id, company_id,
    )}
    if set(ids) - found:
        raise HTTPException(status_code=404, detail="One of those files wasn't found.")
    return list(dict.fromkeys(ids))


def _brief(playbook: Playbook, raw: dict) -> dict:
    if len(json.dumps(raw or {}, default=str)) > MAX_BRIEF_BYTES:
        raise HTTPException(status_code=422, detail="That's too much detail for one task.")
    try:
        return playbook.validate_brief(raw or {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def create_task(user, company_id: UUID, body, *,
                      origin: tuple[UUID | None, UUID | None] | None = None) -> dict:
    """Start a task. `body`: `AgentTaskCreate`. `origin`: the conversation (and
    message) it was started from, where its cards are posted; only server
    code passes one."""
    # A retried create (the first answer was lost) gets the task it already
    # started, before any limit could refuse it.
    existing = await service.find_by_request(user.id, body.request_id)
    if existing is not None:
        return existing
    playbook = playbooks.get(body.playbook)
    if playbook is None:
        raise HTTPException(status_code=400, detail="Espresso doesn't know that kind of task.")
    brief = _brief(playbook, body.brief)
    if playbook.engine == job_tasks.ENGINE:
        # A job search runs on its own engine, with its own gates (plan,
        # allowance, consent, one at a time); Tasks only has to be on.
        if not tasks_enabled(user):
            raise HTTPException(status_code=403, detail={"code": "feature_disabled",
                                                         "message": "Tasks aren't available yet."})
        return await job_tasks.start(user, company_id, body, brief, origin=origin)
    plan = await preflight(user, company_id, playbook, consent_version=body.consent_version)
    limit = allowance.limit_for_plan(plan) if plan is not None else None
    cost = allowance.WEIGHTS[playbook.key]
    # Settled now, like the assistant's: a later admin change applies to new tasks.
    model = await model_run.default_model()
    token = uuid4()
    async with connection_or_direct() as conn:
        async with conn.transaction():
            await allowance.lock(conn, user.id)
            row = await conn.fetchrow(
                "SELECT * FROM mw_agent_tasks WHERE user_id = $1 AND request_id = $2", user.id, body.request_id,
            )
            if row is not None:  # a retried create
                return service.task_view(row)
            input_ids = await _owned_inputs(conn, user.id, company_id, list(body.input_ids or []))
            # A chain that died long ago would hold a live slot forever.
            await service.end_stale(conn, user.id)
            if await _live_count(conn, user.id) >= MAX_LIVE:
                raise _live_error()
            used = await allowance.used_units(conn, user.id) if limit is not None else 0
            if allowance.over(limit, used, cost):
                raise _limit_error(allowance.usage_payload(limit, used), cost)
            row = await conn.fetchrow(
                """INSERT INTO mw_agent_tasks
                       (request_id, user_id, company_id, source, playbook, engine, title, directive, brief,
                        input_ids, status, phase, dispatch_token, progress, model, current_round,
                        origin_channel_id, origin_message_id)
                   VALUES ($1, $2, $3, 'espresso', $4, 'chain', $5, $6, $7::jsonb, $8::uuid[], 'queued', $9,
                           $10, '{"note": "Queued."}'::jsonb, $11, 1, $12, $13)
                   RETURNING *""",
                body.request_id, user.id, company_id, playbook.key, (body.title or "")[:120],
                body.directive, json.dumps(brief), input_ids, playbook.phase_key(playbook.first_phase),
                token, model, *(origin or (None, None)),
            )
            await conn.execute(
                """INSERT INTO mw_agent_task_rounds (task_id, user_id, n, kind, directive, units, status)
                   VALUES ($1, $2, 1, 'initial', $3, $4, 'running')""",
                row["id"], user.id, body.directive, cost,
            )
    try:
        await dispatch(row["id"], token)
    except Exception:
        # Broker down: a queued row with nothing to run it would hold a live
        # slot. Failed tasks are free.
        logger.exception("agent task dispatch failed task=%s", row["id"])
        async with connection_or_direct() as conn, conn.transaction():
            await conn.execute(
                """UPDATE mw_agent_tasks
                   SET status = 'failed', error = 'Could not be queued.', dispatch_token = NULL,
                       completed_at = NOW(), updated_at = NOW()
                   WHERE id = $1 AND status = 'queued'""",
                row["id"],
            )
            await service.close_round(conn, row["id"])
        raise HTTPException(status_code=503, detail="Couldn't start the task right now. Try again in a moment.")
    logger.info("agent task queued task=%s playbook=%s user=%s", row["id"], playbook.key, user.id)
    return service.task_view(row)


ROUND_NOTES = {
    "refine": "Reading your change…",
    "more": "Looking for more…",
}


async def start_round(user, task_id: UUID, body) -> dict:
    """A follow-up on a finished (or waiting) task: refine, search more, or a
    document. `body`: `RoundCreate`. Idempotent per `request_id`."""
    if not tasks_enabled(user):
        raise HTTPException(status_code=403, detail={"code": "feature_disabled",
                                                     "message": "Tasks aren't available yet."})
    kind = body.kind
    directive = " ".join((body.directive or "").split())
    if kind == "refine" and len(directive) < 3:
        raise HTTPException(status_code=422, detail="Say what to change.")
    plan = None if _is_admin(user) else await require_plan(user.id, PLAN_PRO, ENTITLEMENT)
    limit = allowance.limit_for_plan(plan) if plan is not None else None
    if plan is not None and kind != "document":
        from app.matcha.services.billing import token_budget_service

        async with connection_or_direct() as conn:
            company_id = await conn.fetchval(
                "SELECT company_id FROM mw_agent_tasks WHERE id = $1 AND user_id = $2", task_id, user.id,
            )
        if company_id is not None:
            await token_budget_service.check_token_budget(company_id)
        await _daily(str(user.id), "espresso_agent_task_round", DAILY_ROUNDS, "follow-ups")
    token = uuid4()
    async with connection_or_direct() as conn:
        async with conn.transaction():
            await allowance.lock(conn, user.id)
            task = dict(await service.owned_task(conn, task_id, user.id, lock=True))
            if task["engine"] == job_tasks.ENGINE:
                raise HTTPException(status_code=409, detail=(
                    "A job search is changed on its own page: re-rank it with What matters, or redraft a job."
                ))
            if body.request_id is not None and await conn.fetchval(
                "SELECT 1 FROM mw_agent_task_rounds WHERE task_id = $1 AND request_id = $2",
                task_id, body.request_id,
            ):
                dispatch_now = False
            else:
                dispatch_now = await _new_round(conn, user, task, kind=kind, directive=directive,
                                                item_ids=list(body.item_ids or []), request_id=body.request_id,
                                                limit=limit, token=token)
    if dispatch_now:
        try:
            await dispatch(task_id, token)
        except Exception:
            # The task stays queued; a status poll restarts it.
            logger.exception("agent task round dispatch failed task=%s", task_id)
    return await service.get_task(task_id, user.id, mark_seen=False)


async def _new_round(conn, user, task: dict, *, kind: str, directive: str, item_ids: list[UUID],
                     request_id: UUID | None, limit: int | None, token: UUID) -> bool:
    """Insert the round and set the task going. True when there is a phase to dispatch."""
    playbook = playbooks.get(task["playbook"])
    if task["engine"] != "chain" or playbook is None or kind not in playbook.round_phases:
        raise HTTPException(status_code=400, detail="This task can't do that.")
    if task["status"] in service.LIVE:
        raise HTTPException(status_code=409, detail="It's still working. Try again when it finishes.")
    allowed = ("done", "waiting", "cancelled") if kind == "document" else ("done", "waiting")
    if task["status"] not in allowed:
        raise HTTPException(status_code=409, detail="Only a finished task can do that.")
    n = int(task["current_round"] or 0) + 1
    if n > playbook.max_rounds:
        raise HTTPException(status_code=429, detail="This task has had all its follow-ups. Start a new one.")
    if item_ids:
        owned = await conn.fetchval(
            "SELECT COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND id = ANY($2::uuid[])",
            task["id"], item_ids,
        )
        if int(owned or 0) != len(set(item_ids)):
            raise HTTPException(status_code=404, detail="One of those findings wasn't found.")
    cost = allowance.ROUND_UNITS.get(kind, 0)
    if kind != "document":
        if await _live_count(conn, user.id, besides=task["id"]) >= MAX_LIVE:
            raise _live_error()
        if cost:
            used = await allowance.used_units(conn, user.id) if limit is not None else 0
            if allowance.over(limit, used, cost):
                raise _limit_error(allowance.usage_payload(limit, used), cost)
    await conn.execute(
        """INSERT INTO mw_agent_task_rounds (task_id, user_id, n, kind, request_id, directive, scope, units, status)
           VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, 'running')""",
        task["id"], user.id, n, kind, request_id, directive,
        json.dumps({"item_ids": [str(i) for i in item_ids]}), cost,
    )
    if kind == "document":
        made = await document.write(conn, task, item_ids=item_ids, today=date.today())
        await conn.execute(
            """UPDATE mw_agent_task_rounds SET status = 'done', document = $3::jsonb, completed_at = NOW()
               WHERE task_id = $1 AND n = $2""",
            task["id"], n, json.dumps(made),
        )
        await conn.execute(
            "UPDATE mw_agent_tasks SET current_round = $2, updated_at = NOW() WHERE id = $1", task["id"], n,
        )
        return False
    more_rounds = int(await conn.fetchval(
        "SELECT COUNT(*) FROM mw_agent_task_rounds WHERE task_id = $1 AND kind = 'more'", task["id"],
    ) or 0)
    cursor = ({"more": True, "provider_page": more_rounds + 1, "web_runs": 0,
               "like": [str(i) for i in item_ids]} if kind == "more" else {})
    await conn.execute(
        """UPDATE mw_agent_tasks
           SET status = 'queued', phase = $2, dispatch_token = $3, lease_until = NULL, attempts = 0,
               current_round = $4, phase_cursor = $5::jsonb, provider_calls = 0, fetch_calls = 0,
               browser_views = 0, completed_at = NULL, waiting_since = NULL, needs = NULL, error = NULL,
               progress = progress || $6::jsonb, updated_at = NOW()
           WHERE id = $1""",
        task["id"], playbook.phase_key(playbook.round_phases[kind]), token, n, json.dumps(cursor),
        json.dumps({"note": ROUND_NOTES.get(kind, "Working…")}),
    )
    return True
