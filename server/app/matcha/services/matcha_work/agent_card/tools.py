"""Responses tools for the agent-card loop.

One hosted tool (OpenAI `web_search`, run on the provider's side) and the
function tools we execute: `fetch_page` (SSRF-guarded GET + structured page
extraction), `search_flights` (Duffel, only for travel requests when a token is
configured; see `flights.py`) and `finish` (the structured result, validated by
`schema.normalize_result`). There are no write tools — the only effect a run
has is the result shown to the person who asked.
"""
from __future__ import annotations

from typing import Any

from .flights import CABINS
from .schema import RESULT_SCHEMA

WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search", "search_context_size": "medium"}
# Asks the provider to return each search's source list, which feeds the
# provenance gate alongside the url_citation annotations.
RESPONSE_INCLUDE = ["web_search_call.action.sources"]


SEARCH_FLIGHTS_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "search_flights",
    "description": (
        "Search live airline fares (Duffel). One call also tries the flexible dates and nearby "
        "airports you allow, prices a round trip as two one-way tickets too, and adds the listed "
        "fees for the bags you ask for. Returns the cheapest options, each with an offer_id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "IATA airport or city code, e.g. SFO or NYC"},
            "destination": {"type": "string", "description": "IATA airport or city code"},
            "depart_date": {"type": "string", "description": "YYYY-MM-DD"},
            "return_date": {"type": ["string", "null"], "description": "YYYY-MM-DD for a round trip, null for one-way"},
            "adults": {"type": "integer", "description": "Default 1"},
            "children": {"type": "integer", "description": "Ages 2-11"},
            "infants": {"type": "integer", "description": "Under 2, on a lap"},
            "cabin": {"type": "string", "enum": list(CABINS)},
            "max_connections": {"type": "integer", "description": "0 = nonstop only. Default 1"},
            "flexible_days": {"type": "integer", "description": "0-2: also search this many days either side"},
            "nearby_airports": {"type": "boolean", "description": "Also search airports within ~100 miles"},
            "checked_bags": {"type": "integer", "description": "Checked bags per passenger to price in (0-3)"},
            "carry_on_bags": {"type": "integer", "description": "Carry-on bags per passenger to price in (0-1)"},
        },
        "required": ["origin", "destination", "depart_date"],
    },
}


def declarations(*, flights: bool = False) -> list[dict[str, Any]]:
    """The run's tools. Web search stays first: the loop drops index 0 once
    the search budget is spent."""
    tools = _base_declarations()
    if flights:
        tools.insert(1, SEARCH_FLIGHTS_TOOL)
    return tools


def _base_declarations() -> list[dict[str, Any]]:
    return [
        WEB_SEARCH_TOOL,
        {
            "type": "function",
            "name": "fetch_page",
            "description": (
                "Load one public web page and return its title, Open Graph image, "
                "schema.org Product data (price, offers with buy URLs, rating, review "
                "snippets, images) and a slice of visible text. Use it on retailer, "
                "brand and review pages you found with web search."
            ),
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "An http(s) URL"}},
                "required": ["url"],
            },
        },
        {
            "type": "function",
            "name": "finish",
            "description": (
                "Finish with the structured result page. Every URL in it (buy links, "
                "review/rating/price sources, sources) must be one web search returned "
                "or fetch_page loaded; anything else is removed."
            ),
            "parameters": {
                "type": "object",
                "properties": {"result": RESULT_SCHEMA},
                "required": ["result"],
            },
        },
    ]
