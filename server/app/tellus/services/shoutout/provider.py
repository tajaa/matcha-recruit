"""OpenAI web-search provider behind the radar's future-provider seam."""
import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from ....config import get_settings


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
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end < start:
            return {}
        try:
            parsed = json.loads(value[start:end + 1])
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


def _response_text_and_sources(payload: dict) -> tuple[str, list[str]]:
    text, citations = [], []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "web_search_call":
            action = item.get("action")
            sources = action.get("sources", []) if isinstance(action, dict) else []
            for source in sources:
                if isinstance(source, dict) and isinstance(source.get("url"), str):
                    citations.append(source["url"])
            continue
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict) or content.get("type") != "output_text":
                continue
            if isinstance(content.get("text"), str):
                text.append(content["text"])
            for annotation in content.get("annotations", []):
                if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                    continue
                url = annotation.get("url")
                if isinstance(url, str):
                    citations.append(url)
    return "\n".join(text), list(dict.fromkeys(citations))


class OpenAIWebSearchProvider:
    async def search(self, prompt: str) -> SearchResult:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for shoutout scans.")
        if not settings.openai_luna_model:
            raise RuntimeError("OPENAI_LUNA_MODEL is required for shoutout scans.")
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_luna_model,
                    "input": prompt,
                    "tools": [{"type": "web_search_preview"}],
                    "tool_choice": "required",
                    "include": ["web_search_call.action.sources"],
                },
            )
            response.raise_for_status()
        text, citations = _response_text_and_sources(response.json())
        data = _json_object(text)
        mentions = data.get("mentions") if isinstance(data.get("mentions"), list) else []
        resolved, resolved_count = await resolve_grounding_uris(citations)
        return SearchResult(
            mentions=[item for item in mentions if isinstance(item, dict)],
            grounding_uris=resolved,
            grounding_resolved=resolved_count,
        )
