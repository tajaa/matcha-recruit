"""Runs a task as a chain of short worker tasks, one phase each.

The engine (the dispatch token and lease, attempts, retries, restarts,
reconcile) is `agent_runtime/chain.py`; see its docstring for how the chain
holds together. This module is Tasks' specialisation of it: every chain
playbook's phases (stored on the row as `<playbook>.<phase>`), how a task that
cannot go on ends (`_ending`), what happens once it stops (`_stopped`), and
`TASK_CHAIN`, the spec the engine runs on.
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.database import connection_or_direct
from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.agent_runtime.chain import PhaseOutcome

from . import chat, mail, notify, playbooks, service
from .enqueue import dispatch
from .model_run import USAGE_PREFIX
from .research.phases import Deps

logger = logging.getLogger(__name__)

# Under the task's 500s soft limit (`workers/tasks/agent_tasks.py`), with room
# to write the outcome.
PHASE_SECONDS = 420
# Longer than the task's 560s hard limit: a lease never runs out while its
# task can still be running, so a restart cannot start a second copy.
LEASE_INTERVAL = "10 minutes"
MAX_ATTEMPTS = 3
RETRY_COUNTDOWN = 30
# A live task with no lease that has not moved in this long lost its worker task.
IDLE_INTERVAL = "2 minutes"
BUDGET_COLUMNS = frozenset({"provider_calls", "fetch_calls", "browser_views"})


async def _ending(task: dict, message: str) -> PhaseOutcome:
    """A task that cannot go on: `done` if it has findings to show (ranked),
    else `failed` (free)."""
    async with connection_or_direct() as conn:
        found = int(await conn.fetchval(
            "SELECT COUNT(*) FROM mw_agent_task_items WHERE task_id = $1", task["id"],
        ) or 0)
        if found:
            playbook = playbooks.get(task.get("playbook"))
            fresh = await conn.fetchrow("SELECT * FROM mw_agent_tasks WHERE id = $1", task["id"])
            if playbook is not None and fresh is not None:
                await playbook.rerank(conn, dict(fresh))
    if found:
        return PhaseOutcome(status="done", progress={"note": f"Stopped early: {message}"})
    return PhaseOutcome(status="failed", progress={"note": message})


async def _stopped(conn, task_id: UUID) -> None:
    """Once a task stops (done, failed, waiting): settle its round, tell the
    person, post the card in the conversation it came from, and email what
    it found (once a round, so only when this call settled it)."""
    settled = await service.close_round(conn, task_id)
    await notify.task_stopped(conn, task_id)
    try:
        message = await chat.post_stopped(conn, task_id)
        if message is not None:
            from app.matcha.services.matcha_work.project_agent.chat import broadcast_espresso_message

            await broadcast_espresso_message(message)
    except Exception:
        logger.warning("task card could not be posted task=%s", task_id, exc_info=True)
    if settled:
        await mail.round_finished(conn, task_id)


TASK_CHAIN = chain.ChainSpec(
    table="mw_agent_tasks",
    live=service.LIVE,
    start=("queued", "running"),
    phases=playbooks.chain_phases(),
    dispatch=dispatch,
    ending=_ending,
    on_terminal=_stopped,
    phase_column="phase",
    budget_columns=BUDGET_COLUMNS,
    # A round's searches cost against the same label as its model runs.
    usage_feature=lambda task: f"{USAGE_PREFIX}.{task.get('playbook') or 'research'}",
    name="agent task",
    noun="task",
    phase_seconds=PHASE_SECONDS,
    lease_interval=LEASE_INTERVAL,
    max_attempts=MAX_ATTEMPTS,
    retry_countdown=RETRY_COUNTDOWN,
    idle_interval=IDLE_INTERVAL,
    stale_interval=service.STALE_INTERVAL,
)


async def run_phase(task_id: UUID, token: UUID, *, deps: Deps | None = None) -> None:
    await chain.run_phase(TASK_CHAIN, task_id, token, deps=deps or Deps())


async def nudge(task_id: UUID) -> bool:
    """Restart this task's chain if it has stalled. Cheap when it hasn't."""
    return await chain.nudge(TASK_CHAIN, task_id)


async def reconcile() -> dict:
    """Main-worker start: end tasks dead for hours, restart idle ones, and
    cancel tasks nobody answered for a week."""
    out = await chain.reconcile(TASK_CHAIN)
    out["expired"] = await service.expire_waiting()
    return out
