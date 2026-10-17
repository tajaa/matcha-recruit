"""One model phase of a job search, as an ordinary agent-runtime run.

The search is a third caller of `agent_runtime.runner` (after the chat
assistant and agent cards): there is still one loop. The run itself (its
`mw_project_agent_runs` row, the runner, `mark_run`, the token charge) is
`agent_runtime/phase_run.py`; this module says whose run it is: kind
`job_search`, pointing at the search, counted on the search row.

Runs are not stored by the provider: the ask and, when the person chose to,
their résumé are in the input.
"""
from __future__ import annotations

from functools import partial
from typing import Any, Callable, Sequence
from uuid import UUID

from app.core.services import agent_surfaces, anthropic_messages
from app.database import connection_or_direct
from app.matcha.services.matcha_work.agent_runtime import models, phase_run, runner
from app.matcha.services.matcha_work.agent_runtime.context import RunLimits
from app.matcha.services.matcha_work.agent_runtime.phase_run import NoteProgress, default_client
from app.matcha.services.matcha_work.agent_runtime.registry import Ability

USAGE_FEATURE = "matcha.espresso.job_search"

# Progress notes on the search row, throttled (`phase_run.NoteProgress`).
SearchProgress = NoteProgress


async def default_model() -> str:
    """The model a new search uses: the admin's choice for Job search, else Claude Haiku."""
    return await anthropic_messages.surface_model(agent_surfaces.ESPRESSO_JOB_SEARCH)


async def model_for(search: dict) -> str:
    """The search's model while this server still offers it. Otherwise what a
    new search would get, the admin's choice included, stamped on the row so it
    says what runs."""
    model = search.get("model")
    if model in models.offered():
        return model
    model = await default_model()
    async with connection_or_direct() as conn:
        await conn.execute("UPDATE mw_job_searches SET model = $2 WHERE id = $1", search["id"], model)
    return model


async def _count_run(search_id: UUID, stats: dict) -> None:
    """The run on the search's own counters. `phase_run` charges the workspace."""
    async with connection_or_direct() as conn:
        await conn.execute(
            "UPDATE mw_job_searches SET model_runs = model_runs + 1, tokens = tokens + $2 WHERE id = $1",
            search_id, phase_run.total_tokens(stats),
        )


async def run_owner(search: dict) -> phase_run.RunOwner:
    """The search as the owner of its model runs."""
    return phase_run.RunOwner(
        kind="job_search",
        fk_column="job_search_id",
        owner_id=search["id"],
        user_id=search["user_id"],
        company_id=search["company_id"],
        model=await model_for(search),
        usage_feature=USAGE_FEATURE,
        storage_prefix=f"matcha-work/{search['company_id']}/job-search/{search['id']}",
        surface="job_search",
        account=partial(_count_run, search["id"]),
    )


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
    return await phase_run.run_model_phase(
        await run_owner(search),
        phase=phase,
        abilities=abilities,
        contract=contract,
        instructions=instructions,
        user_text=user_text,
        limits=limits,
        progress=progress,
        reasoning_effort=reasoning_effort,
        client_factory=client_factory,
        first_note=first_note,
    )
