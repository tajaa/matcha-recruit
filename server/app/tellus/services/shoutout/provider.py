"""Gemini Google Search provider behind the radar's future-provider seam."""
import asyncio
import json
from dataclasses import dataclass
from typing import Protocol

import httpx
from google.genai import types

from ....core.services.genai_client import get_genai_client
from ....core.services.model_catalog import GEMINI_FLASH
from ....core.services.rate_limiter import get_rate_limiter


@dataclass(frozen=True)
class SearchResult:
    mentions: list[dict]
    grounding_uris: list[str]
    grounding_resolved: int


class MentionProvider(Protocol):
    async def search(self, prompt: str) -> SearchResult: ...


def _json_object(text: str) -> dict:
    value = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def resolve_grounding_uris(uris: list[str]) -> tuple[list[str], int]:
    """Resolve exactly one redirect hop without fetching social pages themselves."""
    resolved: list[str] = []
    successful = 0
    async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
        for uri in uris:
            try:
                response = await client.head(uri)
                resolved.append(response.headers.get("location") or uri)
                successful += 1
            except httpx.HTTPError:
                resolved.append(uri)
    return resolved, successful


class GeminiGroundingProvider:
    async def search(self, prompt: str) -> SearchResult:
        limiter = get_rate_limiter()
        await limiter.check_limit("gemini_compliance", "tellus_shoutout_radar")
        try:
            response = await asyncio.wait_for(
                get_genai_client().aio.models.generate_content(
                    model=GEMINI_FLASH,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                    ),
                ),
                timeout=90,
            )
        finally:
            # A timeout may still have reached Gemini, so it still consumes the budget.
            await limiter.record_call("gemini_compliance", "tellus_shoutout_radar")
        data = _json_object(getattr(response, "text", "") or "")
        mentions = data.get("mentions") if isinstance(data.get("mentions"), list) else []
        candidates_response = getattr(response, "candidates", None) or []
        first_candidate = candidates_response[0] if candidates_response else None
        metadata = getattr(first_candidate, "grounding_metadata", None)
        chunks = getattr(metadata, "grounding_chunks", None) or []
        uris = [uri for uri in (getattr(getattr(chunk, "web", None), "uri", None) for chunk in chunks) if uri]
        resolved, resolved_count = await resolve_grounding_uris(uris)
        return SearchResult(
            mentions=[item for item in mentions if isinstance(item, dict)],
            grounding_uris=resolved,
            grounding_resolved=resolved_count,
        )
