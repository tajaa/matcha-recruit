from datetime import date
from uuid import uuid4

from app.matcha.services.huume.prompt import build_system_prompt
from app.matcha.services.huume.scope import (
    HuumeSurfaceContext,
    SCHEDULE_LOOKUP_TOPICS,
    SCHEDULE_TOOLS,
)
from app.matcha.services.huume.tools import tool_declarations


def _schedule_context() -> HuumeSurfaceContext:
    return HuumeSurfaceContext(
        surface="schedule_assistant",
        location_id=uuid4(),
        week_start=date(2026, 8, 23),
        week_end=date(2026, 8, 30),
        allowed_tools=SCHEDULE_TOOLS,
        allowed_lookup_topics=SCHEDULE_LOOKUP_TOPICS,
        write_mode="draft",
    )


def test_schedule_surface_declarations_are_scoped():
    names = {declaration.name for declaration in tool_declarations(allowed_names=SCHEDULE_TOOLS)}
    assert names == set(SCHEDULE_TOOLS)
    assert "send_offer" not in names
    assert "draft_discipline" not in names


def test_schedule_prompt_is_conversational_and_does_not_expose_global_huume_tools():
    prompt = build_system_prompt(
        company_name="Team Wilshire",
        today="2026-08-21",
        state_block="Nothing is currently staged.",
        surface_context=_schedule_context(),
    )
    assert "real multi-turn conversation" in prompt
    assert "what needs attention" in prompt
    assert "send_offer" not in prompt
    assert "draft_discipline" not in prompt
    assert "get_schedule_overview" in prompt
