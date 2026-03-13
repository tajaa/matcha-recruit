# Import all tasks for Celery autodiscovery
from .interview_analysis import analyze_interview_async
from .compliance_checks import (
    run_compliance_check_task,
    enqueue_scheduled_compliance_checks,
    run_deadline_escalation,
)
from .onboarding_reminders import run_onboarding_reminders
from .risk_assessment import (
    run_risk_assessment_task,
    enqueue_scheduled_risk_assessments,
)
from .healthcare_research import run_healthcare_research
from .oncology_research import run_oncology_research

__all__ = [
    "analyze_interview_async",
    "run_compliance_check_task",
    "enqueue_scheduled_compliance_checks",
    "run_deadline_escalation",
    "run_onboarding_reminders",
    "run_risk_assessment_task",
    "enqueue_scheduled_risk_assessments",
    "run_healthcare_research",
    "run_oncology_research",
]
