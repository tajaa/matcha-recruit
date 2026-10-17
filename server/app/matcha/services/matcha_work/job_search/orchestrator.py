"""Runs a job search as a chain of short worker tasks, one phase each.

The engine (the dispatch token and lease, attempts, retries, restarts,
reconcile) is `agent_runtime/chain.py`; see its docstring for how the chain
holds together. This module is job search's specialisation of it: the phases
in the order a search goes through them, how a search that cannot go on ends
(`_ending`), and `JOB_CHAIN`, the spec the engine runs on. `claim`, `advance`,
`run_phase`, `nudge` and `reconcile` are the engine's, bound to that spec.
"""
from __future__ import annotations

from uuid import UUID

from app.database import connection_or_direct
from app.matcha.services.matcha_work.agent_runtime import chain

from . import model_phases, phases
from .agent_phase import USAGE_FEATURE
from .enqueue import dispatch
from .phases import Deps, PhaseOutcome
from .service import LIVE, STALE_INTERVAL, release_drafts, rerank, resting_status

# Under the task's 500s soft limit (`workers/tasks/job_search.py`), with room
# to write the outcome.
PHASE_SECONDS = 420
# Longer than the task's 560s hard limit: a lease never runs out while its
# task can still be running, so a restart cannot start a second copy.
LEASE_INTERVAL = "10 minutes"
MAX_ATTEMPTS = 3
RETRY_COUNTDOWN = 30
# A live search with no lease that has not moved in this long lost its task.
IDLE_INTERVAL = "2 minutes"

# The order a search goes through: each status names the phase that runs in it.
PHASES = {
    "planning": model_phases.plan,
    "discovering": phases.discover,
    "screening": model_phases.screen,
    "enriching": phases.enrich,
    "approaching": model_phases.approach,
}


async def _ending(search: dict, message: str) -> PhaseOutcome:
    """A search that cannot go on: `done` (counted) if it has ranked jobs to
    show, else `failed` (free). A cancelled search that was drafting a
    requested approach goes back to `cancelled`."""
    if resting_status(search) == "cancelled":
        return PhaseOutcome(status="cancelled", progress={"note": f"Cancelled. Couldn't draft the approach: {message}"})
    async with connection_or_direct() as conn:
        leads = int(await conn.fetchval(
            "SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1", search["id"],
        ) or 0)
        if leads:
            fresh = await conn.fetchrow("SELECT * FROM mw_job_searches WHERE id = $1", search["id"])
            await rerank(conn, fresh)
    if leads:
        return PhaseOutcome(status="done", progress={"note": f"Stopped early: {message}", "ranked": True})
    return PhaseOutcome(status="failed", progress={"note": message})


async def _stopped(conn, search_id: UUID) -> None:
    """Whatever ends a search (finished early, cancelled, stalled) drafts
    nothing more; and the person hears it finished, once, through Tasks."""
    from app.matcha.services.matcha_work.agent_tasks import job_tasks

    await release_drafts(conn, search_id)
    await job_tasks.search_stopped(conn, search_id)


JOB_CHAIN = chain.ChainSpec(
    table="mw_job_searches",
    live=LIVE,
    start=("queued", "planning"),
    phases=PHASES,
    dispatch=dispatch,
    ending=_ending,
    on_terminal=_stopped,
    budget_columns=phases.BUDGET_COLUMNS,
    # Listing searches cost against the same label as the search's model runs.
    usage_feature=lambda _search: USAGE_FEATURE,
    name="job search",
    noun="search",
    phase_seconds=PHASE_SECONDS,
    lease_interval=LEASE_INTERVAL,
    max_attempts=MAX_ATTEMPTS,
    retry_countdown=RETRY_COUNTDOWN,
    idle_interval=IDLE_INTERVAL,
    stale_interval=STALE_INTERVAL,
)


async def claim(search_id: UUID, token: UUID) -> dict | None:
    return await chain.claim(JOB_CHAIN, search_id, token)


async def advance(search_id: UUID, token: UUID, outcome: PhaseOutcome, *,
                  retry: bool = False, error: str | None = None) -> tuple[bool, UUID | None]:
    return await chain.advance(JOB_CHAIN, search_id, token, outcome, retry=retry, error=error)


async def run_phase(search_id: UUID, token: UUID, *, deps: Deps | None = None) -> None:
    await chain.run_phase(JOB_CHAIN, search_id, token, deps=deps or Deps())


async def nudge(search_id: UUID) -> bool:
    """Restart this search's chain if it has stalled. Cheap when it hasn't."""
    return await chain.nudge(JOB_CHAIN, search_id)


async def reconcile() -> dict:
    """Main-worker start: end searches dead for hours, restart idle ones."""
    return await chain.reconcile(JOB_CHAIN)
