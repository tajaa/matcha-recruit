"""Espresso Tasks: one phase per task (`services/matcha_work/agent_tasks/orchestrator.py`)."""

from uuid import UUID

from app.workers.celery_app import celery_app

from ..utils import run_with_chat_fanout


@celery_app.task(
    name="app.workers.tasks.agent_tasks.run_agent_task_phase",
    soft_time_limit=500,
    time_limit=560,
)
def run_agent_task_phase(task_id, token):
    from app.matcha.services.matcha_work.agent_tasks import orchestrator

    # A phase that ends the task posts its card and bell through the socket
    # fan-out, which needs the worker's own Redis client (`run_with_chat_fanout`).
    run_with_chat_fanout(orchestrator.run_phase(UUID(task_id), UUID(token)))


@celery_app.task(
    name="app.workers.tasks.agent_tasks.reconcile_agent_tasks",
    soft_time_limit=90,
    time_limit=120,
)
def reconcile_agent_tasks():
    from app.matcha.services.matcha_work.agent_tasks import orchestrator

    run_with_chat_fanout(orchestrator.reconcile())
