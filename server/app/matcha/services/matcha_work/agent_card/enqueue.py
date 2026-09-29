"""Gate and queue one agent-card run.

`preflight` is every refusal a caller can know about up front — plan, monthly
cap, token budget, rate limit. Card creation and send-back run it BEFORE
touching the card (a refusal must not leave a dead card, or a rejected card
whose note is lost), then pass `skip_preflight=True` here.

What `enqueue_card_agent` always re-checks, because it must be atomic: the
monthly cap, under a per-user advisory lock, and the one-live-run-per-card
guard, after sweeping runs whose worker died.
"""
from __future__ import annotations

import logging
import os
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.database import get_connection
from app.matcha.services.billing.entitlements_service import PLAN_PRO, require_plan

from .agent import CARD_AGENT_MODEL
from .chat_flow import close_open_prompts
from .quota import card_agent_usage, limit_for_plan, usage_payload, used_this_month

logger = logging.getLogger(__name__)

AGENT_CATEGORY = "agent"
# Leave unset to use Celery's default queue; set to route agent runs to a
# dedicated worker (`-Q agent_cards`) once one is deployed, so a multi-minute
# web run never blocks the single-concurrency main worker.
_QUEUE_ENV = "AGENT_CARD_QUEUE"
_RUNNABLE_COLUMNS = {"todo", "in_progress", "changes_requested"}
# Celery's hard task limit is 600s, so a run still queued/running well past
# that has lost its worker. Older than this it stops blocking a rerun.
_STALE_RUN_INTERVAL = "11 minutes"


def _is_admin(user) -> bool:
    return (getattr(user, "role", "") or "").lower() == "admin"


def _limit_error(usage: dict) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "agent_run_limit",
            "message": "You've used this month's agent runs.",
            **usage,
        },
    )


async def preflight(user, company_id: UUID) -> None:
    """Plan, monthly cap, workspace token budget and rate limit. Raises
    HTTPException. Advisory for the cap (enqueue re-checks it atomically)."""
    if _is_admin(user):
        return
    plan = await require_plan(user.id, PLAN_PRO, "agent_cards")
    usage = await card_agent_usage(user.id, plan=plan)
    if usage["remaining"] <= 0:
        raise _limit_error(usage)
    from app.matcha.services.billing import token_budget_service

    await token_budget_service.check_token_budget(company_id)

    from app.core.services.redis_cache import check_rate_limit

    await check_rate_limit(str(user.id), "espresso_agent_card_user", 20, 3600)


async def enqueue_card_agent(
    *,
    task: dict,
    user,
    reason: Literal["created", "redirect", "rerun"],
    skip_preflight: bool = False,
) -> dict:
    """Insert a queued `card_agent` run for `task` and dispatch it.

    `task` needs id, project_id, company_id, category, board_column.
    Returns `{run_id, round, status}`.
    """
    if task.get("category") != AGENT_CATEGORY:
        raise HTTPException(status_code=400, detail="Only agent cards run the agent")
    if task.get("board_column") not in _RUNNABLE_COLUMNS:
        raise HTTPException(
            status_code=409,
            detail="Move the card back to To do or Changes requested to run the agent again.",
        )
    task_id = UUID(str(task["id"]))
    project_id = UUID(str(task["project_id"]))
    company_id = UUID(str(task["company_id"]))
    if not skip_preflight:
        await preflight(user, company_id)

    # Plan is cached (60s), so re-resolving it here is cheap and keeps the
    # atomic cap below correct even for callers that skipped preflight.
    limit: int | None = None
    if not _is_admin(user):
        limit = limit_for_plan(await require_plan(user.id, PLAN_PRO, "agent_cards"))

    async with get_connection() as conn:
        async with conn.transaction():
            # User lock first, then card lock — every caller takes them in this
            # order, so two enqueues can't deadlock. The user lock makes
            # count-then-insert atomic per person: two cards created at once
            # can't both slip under the cap.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"{user.id}:card_agent_cap",
            )
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"{task_id}:card_agent",
            )
            # A worker killed mid-run leaves its row live, and the one-live-run
            # index would 409 every retry until the reconciler happened to run.
            await conn.execute(
                f"""UPDATE mw_project_agent_runs
                    SET status = 'failed', completed_at = NOW(),
                        error = COALESCE(error, 'Interrupted before completion.')
                    WHERE task_id = $1 AND kind = 'card_agent'
                      AND status IN ('queued', 'running')
                      AND COALESCE(started_at, created_at) < NOW() - INTERVAL '{_STALE_RUN_INTERVAL}'""",
                task_id,
            )
            if limit is not None:
                used = await used_this_month(conn, user.id)
                if used >= limit:
                    raise _limit_error(usage_payload(limit, used))
            done_round = await conn.fetchval(
                """SELECT COALESCE(MAX(round), 0) FROM mw_project_agent_runs
                   WHERE task_id = $1 AND kind = 'card_agent' AND status = 'done'""",
                task_id,
            )
            # A redirect always starts the next round; a rerun of a failed pass
            # (or the first run) retries the round that never finished.
            round_no = int(done_round or 0) + 1
            prompt = task.get("title") or ""
            if task.get("description"):
                prompt = f"{prompt}\n\n{task['description']}"
            try:
                run_id = await conn.fetchval(
                    """INSERT INTO mw_project_agent_runs
                       (company_id, project_id, requested_by, agent_key, kind, prompt,
                        status, model, task_id, round)
                       VALUES ($1, $2, $3, 'espresso', 'card_agent', $4, 'queued', $5, $6, $7)
                       RETURNING id""",
                    company_id, project_id, user.id, prompt[:12_000],
                    CARD_AGENT_MODEL, task_id, round_no,
                )
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=409, detail="The agent is already working on this card.")
            # Questions about the previous pass (see / buy it) are stale now.
            await close_open_prompts(conn, task_id)

    from app.workers.tasks.agent_card import run_card_agent

    queue = os.getenv(_QUEUE_ENV) or None
    try:
        run_card_agent.apply_async(args=[str(run_id)], queue=queue)
    except Exception:
        # Broker down. Don't leave a queued row that holds the live-run index
        # (and would count against the cap) with nothing ever going to run it.
        logger.exception("agent card dispatch failed run=%s", run_id)
        async with get_connection() as conn:
            await conn.execute(
                """UPDATE mw_project_agent_runs
                   SET status = 'failed', completed_at = NOW(),
                       error = 'Could not be queued.'
                   WHERE id = $1 AND status = 'queued'""",
                run_id,
            )
        raise HTTPException(
            status_code=503,
            detail="Couldn't start the agent right now. Try again in a moment.",
        )
    logger.info("agent card run queued run=%s task=%s round=%s reason=%s", run_id, task_id, round_no, reason)
    return {"run_id": str(run_id), "round": round_no, "status": "queued"}
