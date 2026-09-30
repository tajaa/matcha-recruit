"""Live airline fares through Duffel (`agent_card/flights.py`).

One read tool, `search_flights`, over a per-run `FlightSession`. The session
keeps every offer the run's searches returned, and the `flights` result block
is rebuilt from it by offer id (`schema.gate_flights`): the model picks offers
and says why, it never states a price. Read-only; nothing is booked.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from app.matcha.services.matcha_work.agent_card import flights as duffel

from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, ToolOutput

logger = logging.getLogger(__name__)

KEY = "flights"

SEARCH_FLIGHTS_DESCRIPTION = (
    "Search live airline fares (Duffel). One call also tries the flexible dates and nearby "
    "airports you allow, prices a round trip as two one-way tickets too, and adds the listed "
    "fees for the bags you ask for. Returns the cheapest options, each with an offer_id."
)
SEARCH_FLIGHTS_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "origin": {"type": "string", "description": "IATA airport or city code, e.g. SFO or NYC"},
        "destination": {"type": "string", "description": "IATA airport or city code"},
        "depart_date": {"type": "string", "description": "YYYY-MM-DD"},
        "return_date": {"type": ["string", "null"], "description": "YYYY-MM-DD for a round trip, null for one-way"},
        "adults": {"type": "integer", "description": "Default 1"},
        "children": {"type": "integer", "description": "Ages 2-11"},
        "infants": {"type": "integer", "description": "Under 2, on a lap"},
        "cabin": {"type": "string", "enum": list(duffel.CABINS)},
        "max_connections": {"type": "integer", "description": "0 = nonstop only. Default 1"},
        "flexible_days": {"type": "integer", "description": "0-2: also search this many days either side"},
        "nearby_airports": {"type": "boolean", "description": "Also search airports within ~100 miles"},
        "checked_bags": {"type": "integer", "description": "Checked bags per passenger to price in (0-3)"},
        "carry_on_bags": {"type": "integer", "description": "Carry-on bags per passenger to price in (0-1)"},
    },
    "required": ["origin", "destination", "depart_date"],
}

# Held back from the search's own budget, so it stops and keeps what finished
# before the runner's backstop fires.
_MARGIN_SECONDS = 5.0


def session_of(state: RunState) -> Any:
    return state.sessions.get(KEY)


def search_tool(*, max_searches: int, search_seconds: float, min_seconds: float) -> AgentTool:
    async def handler(ctx: RunContext, state: RunState, args: dict, left: float) -> ToolOutput:
        session = session_of(state)
        seconds = min(search_seconds, left - _MARGIN_SECONDS)
        await ctx.progress.note("Searching flights…")
        try:
            out = await session.search(args, seconds=seconds)
        except TimeoutError:
            raise  # the runner answers with timeout_message
        except Exception as exc:
            logger.warning("agent flight search failed", exc_info=True)
            out = {"error": f"The flight search failed: {type(exc).__name__}"}
        options = out.get("options") or []
        if options:
            await ctx.progress.note(f"Comparing {len(options)} flight options…")
        return ToolOutput(
            payload=out,
            label=f"Searched flights: {out.get('searched') or 'failed'}"[:200],
            audit={"options": len(options), "offer_requests": out.get("offer_requests"),
                   "error": out.get("error")},
        )

    return AgentTool(
        name="search_flights",
        effect="read",
        description=SEARCH_FLIGHTS_DESCRIPTION,
        parameters=SEARCH_FLIGHTS_PARAMETERS,
        step_kind="search",  # no new step kind, so no migration
        handler=handler,
        max_calls=max_searches,
        # The search stops at its own budget; this is only the backstop.
        timeout_seconds=search_seconds + 10.0,
        min_seconds_left=min_seconds + _MARGIN_SECONDS,
        exhausted_label="Flight search limit reached",
        exhausted_message="Flight search limit reached; finish with the offers you have.",
        timeout_message="The flight search took too long. Try fewer options, or finish.",
        too_late_message="Not enough time left for another flight search; finish with the offers you have.",
    )


_PROMPT = """Flights:
- Use search_flights for fares: web pages don't show live prices. Pass IATA codes (an airport like \
SFO or a city like NYC), dates as YYYY-MM-DD, and what the person asked for: passengers, cabin, \
bags, how flexible they are. For "cheapest", set flexible_days 1 unless they gave fixed dates, and \
nearby_airports true unless they said only one airport will do.
- A round trip is also priced as two one-way tickets (ticketing "separate"); weigh the saving \
against the risk the tool's warnings describe. When bags are needed, compare total_with_bags, and \
never compare amounts in different currencies.
- To show offers, add a `flights` block: up to 5 options by offer_id, each with a label (Cheapest, \
Best value, Fastest, Fewest stops, Most flexible) and 1-3 short reasons. The prices and times shown \
come from the search, so quote numbers only as the tool gave them and never invent an offer_id.
- Say plainly when a saving comes from another airport, another date or separate tickets. Never \
suggest hidden-city tickets. You cannot book: say how to book the chosen offer on the airline's site."""


def flights_block_schema() -> dict[str, Any]:
    """The card result's `flights` fields (`query_summary`, `options`), as a block."""
    from app.matcha.services.matcha_work.agent_card.schema import RESULT_SCHEMA

    return {
        "type": "object",
        "description": "Flight offers you chose from search_flights, by offer_id (up to 5).",
        "properties": RESULT_SCHEMA["properties"]["flights"]["properties"],
    }


def gate_block(block_type: str, raw: Any, state: RunState) -> tuple[dict | None, list[str]]:
    from app.matcha.services.matcha_work.agent_card import schema

    session = session_of(state)
    gate = schema.Gate(state.provenance)
    if session is None:
        return None, ["Dropped a flights block: no flight search ran"]
    block = schema.gate_flights(raw, session, gate)
    return ({"type": "flights", "flights": block} if block else None), gate.warnings


def build(
    *,
    token: Callable[[], str | None] = lambda: duffel.token(),
    session: Callable[[str], Any] = lambda tok: duffel.FlightSession(tok),
    max_searches: int = 3,
    search_seconds: float = 100.0,
    min_seconds: float = 30.0,
) -> Ability:
    """`token` and `session` are called when a run starts, so a caller's
    patches (and the env) are read then, not at import."""
    return Ability(
        key=KEY,
        label="Flights",
        tools=(search_tool(max_searches=max_searches, search_seconds=search_seconds,
                           min_seconds=min_seconds),),
        prompt_block=lambda _ctx: _PROMPT,
        env_ready=lambda: bool(token()),
        session_factory=lambda _ctx: session(token()),
        block_schemas={"flights": flights_block_schema()},
        gate=gate_block,
    )
