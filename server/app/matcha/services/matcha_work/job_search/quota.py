"""Job searches, counted in searches: a view of the shared monthly task
allowance (`agent_tasks/allowance.py`), where a whole search costs five units.

A search costs real money (Google Jobs calls, page loads, model runs), so the
allowance counts whole searches, not re-ranks or redrafts. Only a search the
system failed is free. A cancelled search counts, and so does a deleted one:
deleting leaves a blanked row behind for exactly this reason.
"""
from __future__ import annotations

from uuid import UUID

from ..agent_tasks import allowance


async def job_search_usage(user_id: UUID | str, *, plan: str | None = None) -> dict:
    """`{limit, used, remaining, resets_at}` in searches for the current UTC month."""
    return allowance.as_count(
        await allowance.task_usage(user_id, plan=plan), allowance.WEIGHTS["job_search"],
    )
