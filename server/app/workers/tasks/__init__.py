# Import all tasks for Celery autodiscovery
from .interview_analysis import analyze_interview_async
from .matching import match_candidates_async, match_position_candidates_async
from .culture_aggregation import aggregate_culture_async
from .compliance_checks import (
    run_compliance_check_task,
    enqueue_scheduled_compliance_checks,
    run_deadline_escalation,
)
from .onboarding_reminders import run_onboarding_reminders

__all__ = [
    "analyze_interview_async",
    "match_candidates_async",
    "match_position_candidates_async",
    "aggregate_culture_async",
    "run_compliance_check_task",
    "enqueue_scheduled_compliance_checks",
    "run_deadline_escalation",
    "run_onboarding_reminders",
]
