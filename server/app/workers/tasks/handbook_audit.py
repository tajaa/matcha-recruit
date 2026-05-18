"""Deprecation shim — handbook audit moved to FastAPI BackgroundTasks.

The implementation now lives in
``app/core/services/handbook_audit_service.py`` and is dispatched inline
from the ``/resources/handbook-gap-analyzer/analyze`` route. The Celery
task name is preserved here ONLY so any Redis-queued jobs that were
enqueued by the pre-migration backend don't crash the worker on dequeue.

Delete this file once the prod Redis queue has drained (typically within
an hour of the deploy that swaps the route to BackgroundTasks).
"""

import asyncio
import logging

from ..celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.workers.tasks.handbook_audit.analyze_handbook_audit",
)
def analyze_handbook_audit(self, report_id: str):
    """Backwards-compatible Celery entry point — forwards to the new
    BackgroundTasks-resident service. Will be removed after the Redis
    queue drains.
    """
    logger.warning(
        "DEPRECATED: handbook_audit Celery dispatch hit for report_id=%s. "
        "New invocations should run inline via BackgroundTasks. "
        "This shim exists to drain stuck Redis-queued jobs.",
        report_id,
    )
    try:
        from app.core.services.handbook_audit_service import run_handbook_audit
        asyncio.run(run_handbook_audit(report_id))
    except Exception as exc:
        logger.exception("shim run_handbook_audit failed report_id=%s: %s", report_id, exc)
        # Don't retry — the BackgroundTasks path is the canonical one now.
