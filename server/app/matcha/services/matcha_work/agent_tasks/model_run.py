"""One model phase of a task, as an ordinary agent-runtime run.

A task is another caller of `agent_runtime.runner` (after the chat assistant,
agent cards and job search): there is still one loop. The run itself (its
`mw_project_agent_runs` row, the runner, the token charge) is
`agent_runtime/phase_run.py`; this module says whose run it is: kind
`agent_task`, pointing at the task, counted on the task row.

Runs are not stored by the provider: a task's input can carry what the person
gave it (files, the brief).
"""
from __future__ import annotations

from functools import partial
from uuid import UUID

from app.core.services import agent_surfaces, anthropic_messages
from app.database import connection_or_direct
from app.matcha.services.matcha_work.agent_runtime import models, phase_run, runner

USAGE_PREFIX = "matcha.espresso.tasks"


async def default_model() -> str:
    """The model a new task uses: the admin's choice for Tasks, else Claude Haiku."""
    return await anthropic_messages.surface_model(agent_surfaces.ESPRESSO_TASKS)


async def model_for(task: dict) -> str:
    """The task's model while this server still offers it. Otherwise (a Luna
    task once the server has an Anthropic key) what a new task would get, the
    admin's choice included, stamped on the row so it says what runs."""
    model = task.get("model")
    if model in models.offered():
        return model
    model = await default_model()
    async with connection_or_direct() as conn:
        await conn.execute("UPDATE mw_agent_tasks SET model = $2 WHERE id = $1", task["id"], model)
    return model


async def _count_run(task_id: UUID, stats: dict) -> None:
    """The run on the task's own counters. `phase_run` charges the workspace."""
    async with connection_or_direct() as conn:
        await conn.execute(
            "UPDATE mw_agent_tasks SET model_runs = model_runs + 1, tokens = tokens + $2 WHERE id = $1",
            task_id, phase_run.total_tokens(stats),
        )


async def run_owner(task: dict) -> phase_run.RunOwner:
    """The task as the owner of its model runs."""
    return phase_run.RunOwner(
        kind="agent_task",
        fk_column="agent_task_id",
        owner_id=task["id"],
        user_id=task["user_id"],
        company_id=task["company_id"],
        model=await model_for(task),
        # Per playbook, so a research round's cost reads on its own in ai_usage.
        usage_feature=f"{USAGE_PREFIX}.{task['playbook']}",
        storage_prefix=f"matcha-work/{task['company_id']}/agent-tasks/{task['id']}",
        surface="agent_task",
        account=partial(_count_run, task["id"]),
        dispatch_token=task.get("dispatch_token"),
        recap_round=task.get("current_round"),
    )


async def run_model_phase(task: dict, **kwargs) -> runner.RunOutcome:
    """Run one bounded loop for this task (`phase_run.run_model_phase`'s
    arguments). Raises `runner.AgentRunError` when no usable result came."""
    return await phase_run.run_model_phase(await run_owner(task), **kwargs)
