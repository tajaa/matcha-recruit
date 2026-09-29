"""Gate and queue one agent-card run.

`preflight` is split out so card creation can refuse BEFORE inserting the card
(a plan or cap failure should not leave a dead agent card on the board);
`enqueue_card_agent` runs it again unless told the caller just did.
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
from .quota import card_agent_usage

logger = logging.getLogger(__name__)

AGENT_CATEGORY = "agent"
# Leave unset to use Celery's default queue; set to route agent runs to a
# dedicated worker (`-Q agent_cards`) once one is deployed, so a multi-minute
# web run never blocks the single-concurrency main worker.
_QUEUE_ENV = "AGENT_CARD_QUEUE"
_RUNNABLE_COLUMNS = {"todo", "in_progress", "changes_requested"}


def _is_admin(user) -> bool:
    return (getattr(user, "role", "") or "").lower() == "admin"


async def preflight(user, company_id: UUID) -> None:
    """Plan, monthly cap and workspace token budget. Raises HTTPException."""
    if _is_admin(user):
        return
    plan = await require_plan(user.id, PLAN_PRO, "agent_cards")
    usage = await card_agent_usage(user.id, plan=plan)
    if usage["remaining"] <= 0:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "agent_run_limit",
                "message": "You've used this month's agent runs.",
                **usage,
            },
        )
    from app.matcha.services.billing import token_budget_service

    await token_budget_service.check_token_budget(company_id)


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

    from app.core.services.redis_cache import check_rate_limit

    await check_rate_limit(str(user.id), "espresso_agent_card_user", 20, 3600)

    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"{task_id}:card_agent",
            )
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

    from app.workers.tasks.agent_card import run_card_agent

    queue = os.getenv(_QUEUE_ENV) or None
    run_card_agent.apply_async(args=[str(run_id)], queue=queue)
    logger.info("agent card run queued run=%s task=%s round=%s reason=%s", run_id, task_id, round_no, reason)
    return {"run_id": str(run_id), "round": round_no, "status": "queued"}
