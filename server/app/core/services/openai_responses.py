"""Shared pieces of the OpenAI Responses API edge.

Every OpenAI call in this repo is hand-rolled `httpx` against
`POST /v1/responses` — there is no `openai` SDK dependency, deliberately. What
those call sites share is small but was copied rather than shared: three
byte-identical `_response_text` walkers (`huume/luna_client.py`,
`inventory/waste/agent.py`, `core/services/credential_template_service.py`),
with `inventory/insight.py` importing the private copy out of `waste/agent.py`.

This module owns the pieces that are genuinely common — the endpoint, the
default budget, the payload readers and the bounded error detail. It does NOT
own request policy: retries, deadlines and rate-limit hooks live in
`huume/luna_client.py`, which is the only caller that needs them.
"""

from __future__ import annotations

from typing import Any

import httpx


RESPONSES_URL = "https://api.openai.com/v1/responses"

# A whole-request budget, not a per-attempt one — a caller that retries counts
# its attempts against this same deadline.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 55.0

# Provider error text reaches logs and the `ai_usage_log` ledger, so it is
# bounded here rather than at each call site (`_build_row` truncates to 500).
_MAX_ERROR_DETAIL_CHARS = 1000


def response_text(payload: dict[str, Any]) -> str:
    """Assistant text from a Responses payload, without trusting its shape.

    Prefers the `output_text` convenience field and otherwise walks
    `output[] -> content[]` for `output_text` parts, which is what a response
    carrying reasoning or tool-call items looks like.
    """
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()
    parts: list[str] = []
    for output in payload.get("output", []) or []:
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for content in output.get("content", []) or []:
            if (
                isinstance(content, dict)
                and content.get("type") == "output_text"
                and isinstance(content.get("text"), str)
            ):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def function_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The `function_call` items of a Responses payload, in provider order.

    `call_id` is carried through deliberately: it is what pairs a result back
    to its call. Matching on the tool NAME instead — which the retired Gemini
    adapter did — mispairs two concurrent calls to the same tool.
    """
    return [
        output
        for output in payload.get("output", []) or []
        if isinstance(output, dict) and output.get("type") == "function_call"
    ]


def web_search_calls(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The hosted `web_search_call` items among a response's `output[]`."""
    return [
        item for item in output or []
        if isinstance(item, dict) and item.get("type") == "web_search_call"
    ]


def cited_urls(output: list[dict[str, Any]]) -> list[str]:
    """Every URL the provider says it actually saw: `url_citation` annotations
    on message text plus the sources a `web_search_call` returned (present only
    when the request asked for `include=["web_search_call.action.sources"]`).
    """
    urls: list[str] = []
    for item in output or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "web_search_call":
            action = item.get("action") or {}
            for source in action.get("sources") or []:
                if isinstance(source, dict) and isinstance(source.get("url"), str):
                    urls.append(source["url"])
            continue
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            for annotation in content.get("annotations", []) or []:
                if (
                    isinstance(annotation, dict)
                    and annotation.get("type") == "url_citation"
                    and isinstance(annotation.get("url"), str)
                ):
                    urls.append(annotation["url"])
    return urls


def http_error_detail(exc: httpx.HTTPError) -> str:
    """The provider's own error detail, bounded, for logs and the usage audit.

    Never the raw httpx repr — that can carry the request URL and headers.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc)
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            code = error.get("code") or error.get("type")
            message = error.get("message")
            detail = ": ".join(str(value) for value in (code, message) if value)
            if detail:
                return detail[:_MAX_ERROR_DETAIL_CHARS]
    except (TypeError, ValueError):
        pass
    return f"HTTP {response.status_code}: {response.text[:_MAX_ERROR_DETAIL_CHARS]}"
