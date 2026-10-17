"""Celery entry points for Espresso assistant runs (`mw_project_agent_runs.kind='assistant'`)
and the page views a run sends to the browser worker.

Lifecycle: claim the queued run → run the agent → post the answer, a question
or a confirmation card in the chat it was asked in. A failure closes the
progress card and says so; the run's spend is recorded either way.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from ..celery_app import celery_app
from ..utils import run_with_chat_fanout

logger = logging.getLogger(__name__)

# Backstop over the whole run. The loop bounds itself, but a stuck await
# anywhere would otherwise sit until Celery's 540s soft / 600s hard kill, which
# leaves the row live and the progress card spinning.
RUN_DEADLINE_SECONDS = 450.0


@celery_app.task(name="app.workers.tasks.assistant.run_assistant")
def run_assistant(run_id: str) -> None:
    run_with_chat_fanout(_run(UUID(run_id)))


# One page view for a run on another worker (`abilities/screenshots.py`): sent
# to AGENT_BROWSER_QUEUE, its result read back by the run. The view bounds
# itself (VIEW_SECONDS + STORE_SECONDS); these limits are the backstop.
@celery_app.task(name="app.workers.tasks.assistant.view_page", soft_time_limit=90, time_limit=120)
def view_page(url: str, prefix: str, recap_run_id: str | None = None) -> dict:
    from app.matcha.services.matcha_work.agent_runtime.abilities.screenshots import view_and_store

    from app.matcha.services.matcha_work.recaps.scope import current_run
    token = current_run.set(UUID(recap_run_id) if recap_run_id else None)
    try:
        return asyncio.run(view_and_store(url, prefix))
    finally:
        current_run.reset(token)


async def _run(run_id: UUID) -> None:
    from app.database import connection_or_direct
    from app.matcha.services.matcha_work.agent_runtime import assistant, runner
    from app.matcha.services.matcha_work.project_agent import store

    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """UPDATE mw_project_agent_runs
               SET status = 'running', started_at = NOW()
               WHERE id = $1 AND status = 'queued' AND kind = 'assistant'
               RETURNING id, company_id, project_id, channel_id, requested_by,
                         trigger_message_id, prompt, surface, abilities, resume_prompt_id, model,
                         (SELECT role FROM users WHERE id = requested_by) AS requester_role,
                         (SELECT email FROM users WHERE id = requested_by) AS requester_email""",
            run_id,
        )
    if not row:
        return
    run = dict(row)
    stats: dict = {}
    try:
        await asyncio.wait_for(assistant.run_assistant(run, stats=stats), timeout=RUN_DEADLINE_SECONDS)
    except Exception as exc:
        logger.exception("assistant run failed run=%s", run_id)
        if isinstance(exc, runner.AgentRunError):
            reason = str(exc)
        elif isinstance(exc, TimeoutError):
            reason = "It took too long."
        else:
            reason = "Something went wrong on my side."
        await store.mark_run(
            run_id,
            status="failed",
            error=str(exc)[:1000],
            model_calls=stats.get("model_calls", 0),
            token_usage=stats.get("token_usage") or {},
            search_calls=stats.get("search_calls", 0),
        )
        await assistant.report_failure(run, reason)
    finally:
        await _deduct_tokens(run, stats)


async def _deduct_tokens(run: dict, stats: dict) -> None:
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
        logger.warning("Failed to deduct assistant tokens company=%s", run["company_id"], exc_info=True)
