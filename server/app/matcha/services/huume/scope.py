"""Surface-scoped context for Huume's tool registry."""

from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class HuumeSurfaceContext:
    surface: Literal["workspace", "schedule_assistant"] = "workspace"
    location_id: UUID | None = None
    week_start: date | None = None
    week_end: date | None = None
    allowed_tools: frozenset[str] | None = None
    allowed_lookup_topics: frozenset[str] | None = None

    @property
    def is_schedule(self) -> bool:
        return self.surface == "schedule_assistant"


SCHEDULE_TOOLS = frozenset({
    "get_schedule_overview",
    "get_week_build_readiness",
    "build_week_schedule",
    "list_schedule_eligibility_cases",
    "find_shift_coverage",
    "propose_schedule_change",
    "propose_assignment_note",
    "propose_meal_break_waiver",
    "propose_work_permit",
    "propose_eligibility_case_decision",
    "lookup_context",
    "cancel_staged",
    "finish",
})

SCHEDULE_LOOKUP_TOPICS = frozenset({
    "roster", "employee", "schedule", "credentials", "training_status", "locations",
})
