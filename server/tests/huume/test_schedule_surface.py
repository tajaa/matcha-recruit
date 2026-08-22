from datetime import date
from uuid import uuid4

from app.matcha.services.huume.prompt import build_state_block, build_system_prompt
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
    )


def test_schedule_surface_declarations_are_scoped():
    names = {declaration.name for declaration in tool_declarations(allowed_names=SCHEDULE_TOOLS)}
    assert names == set(SCHEDULE_TOOLS)
    assert "send_offer" not in names
    assert "draft_discipline" not in names


def test_schedule_prompt_is_conversational_and_does_not_expose_global_huume_tools():
    # Exercise the REAL empty-state text build_state_block produces for this
    # surface, not a literal — the generic empty-state used to name
    # send_offer/build_onboarding_plan/execute_approved_steps even on the
    # schedule surface, which none of those tools are declared to.
    state_block = build_state_block({}, schedule_surface=True)
    prompt = build_system_prompt(
        company_name="Team Wilshire",
        today="2026-08-21",
        state_block=state_block,
        surface_context=_schedule_context(),
    )
    assert "real multi-turn conversation" in prompt
    assert "what needs attention" in prompt
    assert "send_offer" not in prompt
    assert "draft_discipline" not in prompt
    assert "build_onboarding_plan" not in prompt
    assert "execute_approved_steps" not in prompt
    assert "get_schedule_overview" in prompt
    assert "propose_schedule_change" in prompt
