"""Responses tools for the agent-card loop.

One hosted tool (OpenAI `web_search`, run on the provider's side) and the
function tools we execute: `fetch_page` (SSRF-guarded GET + structured page
extraction), `search_flights` (Duffel, only for travel requests when a token is
configured; see `flights.py`) and `finish` (the structured result, validated by
`schema.normalize_result`). There are no write tools — the only effect a run
has is the result shown to the person who asked.

The tools themselves are declared in the agent runtime's registry
(`agent_runtime/abilities/web.py`); this module holds the card's `finish` and
renders the list the card loop offers.
"""
from __future__ import annotations

from typing import Any

from app.matcha.services.matcha_work.agent_runtime import registry
from app.matcha.services.matcha_work.agent_runtime.abilities import flights as flights_ability
from app.matcha.services.matcha_work.agent_runtime.abilities import web

from .schema import RESULT_SCHEMA

WEB_SEARCH_TOOL: dict[str, Any] = web.WEB_SEARCH_TOOL
RESPONSE_INCLUDE = list(web.RESPONSE_INCLUDE)

FINISH_TOOL = registry.AgentTool(
    name="finish",
    effect="finish",
    description=(
        "Finish with the structured result page. Every URL in it (buy links, "
        "review/rating/price sources, sources) must be one web search returned "
        "or fetch_page loaded; anything else is removed."
    ),
    parameters={
        "type": "object",
        "properties": {"result": RESULT_SCHEMA},
        "required": ["result"],
    },
    step_kind="finish",
)


async def _unused_fetch(_url: str) -> tuple[dict, set[str]]:  # pragma: no cover - declarations only
    raise RuntimeError("declarations() renders tools; it does not run them")


def declarations(*, flights: bool = False) -> list[dict[str, Any]]:
    """The card's tools as the loop offers them: hosted search first, then
    `search_flights` when offered, then `fetch_page`, then `finish`."""
    ability = web.build(fetch_page=_unused_fetch, max_fetches=0, fetch_seconds=0)
    tools = list(ability.tools)
    if flights:
        tools.insert(1, flights_ability.search_tool(max_searches=0, search_seconds=0, min_seconds=0))
    return registry.declarations([*tools, FINISH_TOOL])
