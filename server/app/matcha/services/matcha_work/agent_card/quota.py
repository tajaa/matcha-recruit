"""Agent-card runs, counted in runs: a view of the shared monthly task
allowance (`agent_tasks/allowance.py`), where a card run costs one unit."""
from __future__ import annotations

from uuid import UUID

from ..agent_tasks import allowance

# Kept for callers that build a payload in the old shape.
usage_payload = allowance.usage_payload


async def card_agent_usage(user_id: UUID | str, *, plan: str | None = None) -> dict:
    """`{limit, used, remaining, resets_at}` in card runs for the current UTC month."""
    return allowance.as_count(
        await allowance.task_usage(user_id, plan=plan), allowance.WEIGHTS["agent_card"],
    )
