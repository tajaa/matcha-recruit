# Import all tasks for Celery autodiscovery
from .interview_analysis import analyze_interview_async
from .matching import match_candidates_async, match_position_candidates_async
from .culture_aggregation import aggregate_culture_async

__all__ = [
    "analyze_interview_async",
    "match_candidates_async",
    "match_position_candidates_async",
    "aggregate_culture_async",
]
