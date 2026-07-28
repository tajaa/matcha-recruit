"""Shared datetime helpers. Leaf module: imports nothing from services/ or routes/.

Exists so services that only need "now, as a naive UTC datetime" don't have to
lazily import it from ``routes/ir_incidents/_shared`` — that import runs the IR
router package's ``__init__.py``, pulling ~2,200 modules and ~2s of cold import
into callers that never touch a route (``broker/risk_index``,
``broker/submission_readiness``, and the ``broker_risk_alerts`` /
``broker_milestones`` Celery tasks, which re-pay it every 5 tasks under
``--max-tasks-per-child=5``).
"""
from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """Return current UTC time as naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime) -> datetime:
    """Normalize a datetime to naive UTC for TIMESTAMP (without time zone) columns."""
    if value.tzinfo:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
