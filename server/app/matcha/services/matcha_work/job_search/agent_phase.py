"""One model phase of a job search, as an ordinary agent-runtime run.

The search is a third caller of `agent_runtime.runner` (after the chat
assistant and agent cards): there is still one loop. Each call writes its own
`mw_project_agent_runs` row (kind `job_search`, pointing at the search) so
steps, tokens and failures are audited like any other run.

Runs are not stored by the provider: the ask and, when the person chose to,
their résumé are in the input.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence
from uuid import UUID

from app.core.services import agent_surfaces, anthropic_messages
from app.database import connection_or_direct
from app.matcha.services.huume.luna_client import text_item
from app.matcha.services.huume.routing import LUNA
from app.matcha.services.matcha_work.agent_runtime import models, runner
from app.matcha.services.matcha_work.agent_runtime.context import RunContext, RunLimits
from app.matcha.services.matcha_work.agent_runtime.registry import Ability
from app.matcha.services.matcha_work.project_agent import store

logger = logging.getLogger(__name__)

USAGE_FEATURE = "matcha.espresso.job_search"
_NOTE_SECONDS = 1.5


async def default_model() -> str:
    """The model a new search uses: the admin's choice for Job search, else Luna."""
    return await anthropic_messages.claude_override(agent_surfaces.ESPRESSO_JOB_SEARCH) or LUNA


def model_for(search: dict) -> str:
    """The search's model, if this server still offers it."""
    model = search.get("model")
    return model if model in models.offered() else LUNA


def default_client(model: str) -> Any:
    from app.matcha.services.huume.claude_client import get_claude_client
    from app.matcha.services.huume.luna_client import get_luna_client

    return get_claude_client() if models.is_claude(model) else get_luna_client()


@dataclass
class SearchProgress:
    """Progress notes on the search row, throttled; steps stay on the run row."""

    note_fn: Callable[[str], Any]
    _last: float = 0.0

    async def note(self, text: str, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last < _NOTE_SECONDS:
            return
        self._last = now
        try:
            await self.note_fn(text)
        except Exception:
            logger.debug("job search progress note failed", exc_info=True)

    async def step(self, seq: int, kind: str, label: str, status: str) -> None:
        return None


async def _insert_run(search: dict, phase: str, model: str, abilities: list[str]) -> UUID:
    async with connection_or_direct() as conn:
        return await conn.fetchval(
            """INSERT INTO mw_project_agent_runs
                   (company_id, requested_by, agent_key, kind, prompt, status, started_at,
                    model, surface, abilities, job_search_id)
               VALUES ($1, $2, 'espresso', 'job_search', $3, 'running', NOW(), $4, 'job_search', $5, $6)
               RETURNING id""",
            search["company_id"], search["user_id"], f"{phase}:{search['id']}", model, abilities, search["id"],
        )


async def _account(search: dict, stats: dict) -> None:
    """Count the run on the search and charge the workspace's token budget.
    Accounting never turns a finished phase into a failed one."""
    total = int((stats.get("token_usage") or {}).get("total_tokens") or 0)
    try:
        async with connection_or_direct() as conn:
            await conn.execute(
                "UPDATE mw_job_searches SET model_runs = model_runs + 1, tokens = tokens + $2 WHERE id = $1",
                search["id"], total,
            )
        if total > 0:
            from app.matcha.services.billing import token_budget_service

            async with connection_or_direct() as conn, conn.transaction():
                await token_budget_service.deduct_tokens(conn, search["company_id"], total)
    except Exception:
        logger.warning("job search token accounting failed search=%s", search["id"], exc_info=True)


async def run_model_phase(
    search: dict,
    *,
    phase: str,
    abilities: Sequence[Ability],
    contract: runner.ResultContract,
    instructions: str,
    user_text: str,
    limits: RunLimits,
    progress: SearchProgress,
    reasoning_effort: str = "low",
    client_factory: Callable[[str], Any] = default_client,
    first_note: str | None = None,
) -> runner.RunOutcome:
    """Run one bounded loop. Raises `runner.AgentRunError` when no usable result came."""
    model = model_for(search)
    run_id = await _insert_run(search, phase, model, [a.key for a in abilities])
    ctx = RunContext(
        run_id=run_id,
        user_id=search["user_id"],
        company_id=search["company_id"],
        role="client",
        surface="job_search",
        ask=user_text[:12_000],
        storage_prefix=f"matcha-work/{search['company_id']}/job-search/{search['id']}",
        progress=progress,
        limits=limits,
        usage_feature=USAGE_FEATURE,
        model=model,
        reasoning_effort=reasoning_effort,
        store_responses=False,
    )
    stats: dict = {}
    try:
        outcome = await runner.run_agent(
            ctx,
            client=client_factory(model),
            abilities=abilities,
            contract=contract,
            instructions=instructions,
            first_input=[text_item("user", user_text)],
            first_note=first_note,
            stats=stats,
        )
    except Exception as exc:
        await store.mark_run(
            run_id, status="failed", error=str(exc)[:500] or type(exc).__name__,
            model_calls=int(stats.get("model_calls") or 0),
            token_usage=stats.get("token_usage") or {},
            search_calls=int(stats.get("search_calls") or 0),
        )
        await _account(search, stats)
        raise
    await store.mark_run(
        run_id, status="done", result={"phase": phase, "result": outcome.result,
                                       "warnings": outcome.warnings[:20]},
        model_calls=outcome.model_calls, token_usage=outcome.token_usage,
        search_calls=outcome.search_calls,
    )
    await _account(search, {"token_usage": outcome.token_usage})
    return outcome
