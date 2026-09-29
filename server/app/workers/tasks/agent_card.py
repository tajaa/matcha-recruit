"""Celery entry point for agent-card runs (`mw_project_agent_runs.kind='card_agent'`).

Lifecycle: claim the queued run → move the card todo → in_progress (round 1;
revision rounds stay in changes_requested) → run the web agent → move the card
to review → ask in the project chat whether to show the result. Failure
leaves the card where it is with a "Run again" status line.
"""
from __future__ import annotations

import asyncio
import logging
import os
from uuid import UUID

from ..celery_app import celery_app

logger = logging.getLogger(__name__)

FAILED_NOTE = "Agent stopped: {reason} Use Run again to retry."
# Backstop over the whole run. The loop bounds itself (300s of model turns, 25s
# per page, 60s of photos) but a stuck await anywhere would otherwise sit until
# Celery's 540s soft / 600s hard kill — which leaves the row live and the card
# in In progress. Failing cleanly here lets the run record its spend and the
# card offer "Run again".
RUN_DEADLINE_SECONDS = 420.0


@celery_app.task(name="app.workers.tasks.agent_card.run_card_agent")
def run_card_agent(run_id: str) -> None:
    asyncio.run(_run(UUID(run_id)))


async def _run(run_id: UUID) -> None:
    from app.database import connection_or_direct
    from app.matcha.services.matcha_work.agent_card import agent, board
    from app.matcha.services.matcha_work.project_agent import store

    async with connection_or_direct() as conn:
        run = await conn.fetchrow(
            """UPDATE mw_project_agent_runs
               SET status = 'running', started_at = NOW()
               WHERE id = $1 AND status = 'queued' AND kind = 'card_agent'
               RETURNING company_id, project_id, task_id, round, requested_by,
                         (SELECT role FROM users WHERE id = requested_by) AS requester_role""",
            run_id,
        )
        if not run:
            return
        task = await conn.fetchrow(
            """SELECT title, description, review_note, category
               FROM mw_tasks WHERE id = $1 AND project_id = $2""",
            run["task_id"], run["project_id"],
        )
        previous = None
        if run["round"] > 1:
            previous = await conn.fetchval(
                """SELECT result FROM mw_project_agent_runs
                   WHERE task_id = $1 AND kind = 'card_agent' AND status = 'done'
                   ORDER BY round DESC, completed_at DESC LIMIT 1""",
                run["task_id"],
            )

    if not task or task["category"] != "agent":
        await store.mark_run(run_id, status="failed", error="The card was deleted or is no longer an agent card.")
        return

    if isinstance(previous, str):
        import json

        try:
            previous = json.loads(previous)
        except ValueError:
            previous = None

    project_id, task_id = run["project_id"], run["task_id"]
    moved = await board.claim_column(task_id, run_id=run_id)
    if moved:
        await board.publish_task_updated(project_id, moved)

    ask = task["title"] or ""
    if task["description"]:
        ask = f"{ask}\n\n{task['description']}"
    stats: dict = {}
    try:
        await asyncio.wait_for(
            agent.run_card_agent(
                run_id=run_id,
                company_id=run["company_id"],
                project_id=project_id,
                task_id=task_id,
                round=run["round"],
                ask=ask,
                review_note=task["review_note"] if run["round"] > 1 else None,
                previous_result=previous if isinstance(previous, dict) else None,
                stats=stats,
            ),
            timeout=RUN_DEADLINE_SECONDS,
        )
    except Exception as exc:
        logger.exception("agent card run failed run=%s", run_id)
        if isinstance(exc, agent.CardAgentError):
            reason = str(exc)
        elif isinstance(exc, TimeoutError):
            reason = "the run took too long."
        else:
            reason = "something went wrong while researching."
        await store.mark_run(
            run_id,
            status="failed",
            error=str(exc)[:1000],
            model_calls=stats.get("model_calls", 0),
            token_usage=stats.get("token_usage") or {},
            search_calls=stats.get("search_calls", 0),
        )
        row = await board.set_progress(task_id, FAILED_NOTE.format(reason=reason), force=True)
        if row:
            await board.publish_task_updated(project_id, row)
    else:
        row = await board.finish_column(task_id, run_id=run_id)
        note_row = await board.set_progress(task_id, "Result ready for review.", force=True)
        latest = note_row or row
        if latest:
            await board.publish_task_updated(project_id, latest)
        await _offer_in_chat(run_id)
    finally:
        await _deduct_tokens(run, stats)


async def _offer_in_chat(run_id: UUID) -> None:
    """Ask in the project chat whether to show the result. Best-effort: the
    result is already on the card, so a chat failure never fails the run.

    The chat fanout publishes through the shared Redis client, which only the
    API opens (in its lifespan). A Celery task has none, so without one the
    question was saved but reached open chats only on their next reload. It is
    opened here, on this task's own event loop, and closed after."""
    from app.core.services import redis_cache

    opened = False
    try:
        from app.matcha.services.matcha_work.agent_card import chat_flow

        if redis_cache.get_redis_cache() is None:
            await redis_cache.init_redis_cache(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            opened = True
        await chat_flow.offer_result(run_id)
    except Exception:
        logger.warning("agent card chat offer failed run=%s", run_id, exc_info=True)
    finally:
        if opened:
            await redis_cache.close_redis_cache()


async def _deduct_tokens(run, stats: dict) -> None:
    """Charge the workspace token budget, like the other project agents.
    Accounting failure never turns a finished run into a failed one."""
    if run["requester_role"] == "admin":
        return
    total = int((stats.get("token_usage") or {}).get("total_tokens") or 0)
    if total <= 0:
        return
    try:
        from app.database import connection_or_direct
        from app.matcha.services.billing import token_budget_service

        async with connection_or_direct() as conn, conn.transaction():
            await token_budget_service.deduct_tokens(conn, run["company_id"], total)
    except Exception:
        logger.warning("Failed to deduct agent-card tokens company=%s", run["company_id"], exc_info=True)
