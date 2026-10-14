"""Espresso job search: one phase per task (`job_search/orchestrator.py`)."""

import asyncio
from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(
    name="app.workers.tasks.job_search.run_job_search_phase",
    soft_time_limit=500,
    time_limit=560,
)
def run_job_search_phase(search_id, token):
    from app.matcha.services.matcha_work.job_search import orchestrator

    asyncio.run(orchestrator.run_phase(UUID(search_id), UUID(token)))


@celery_app.task(
    name="app.workers.tasks.job_search.reconcile_job_searches",
    soft_time_limit=90,
    time_limit=120,
)
def reconcile_job_searches():
    from app.matcha.services.matcha_work.job_search import orchestrator

    asyncio.run(orchestrator.reconcile())
