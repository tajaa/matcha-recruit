"""Diagnostic-only Celery task — deliberately raises so the task_failure
signal (celery_app.py:_on_task_failure) has something to report.

Not scheduler-gated, not dispatched by on_worker_ready — call it by hand to
verify the worker error-reporting path end to end:

    celery -A app.workers.celery_app call app.workers.tasks.debug_error.raise_test_error

A resulting row should appear in server_error_reports with source='celery'.
"""

from ..celery_app import celery_app


@celery_app.task(name="app.workers.tasks.debug_error.raise_test_error")
def raise_test_error(message: str = "diagnostics: manual worker error-reporting test"):
    raise RuntimeError(message)
