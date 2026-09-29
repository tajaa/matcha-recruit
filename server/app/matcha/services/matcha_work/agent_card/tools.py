"""Responses tools for the agent-card loop.

One hosted tool (OpenAI `web_search`, run on the provider's side) and two
function tools we execute: `fetch_page` (SSRF-guarded GET + structured page
extraction) and `finish` (the structured result, validated by
`schema.normalize_result`). There are no write tools — the only effect a run
has is the result shown to the person who asked.
"""
from __future__ import annotations

from typing import Any

from .schema import RESULT_SCHEMA

WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search", "search_context_size": "medium"}
# Asks the provider to return each search's source list, which feeds the
# provenance gate alongside the url_citation annotations.
RESPONSE_INCLUDE = ["web_search_call.action.sources"]


def declarations() -> list[dict[str, Any]]:
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
