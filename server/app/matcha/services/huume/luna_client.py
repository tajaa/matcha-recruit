"""OpenAI Responses client for the bounded Luna tool loops.

The only provider boundary for Huume's agent loop and Espresso's project
agents. It speaks the Responses API directly: callers hand over Responses
input items and JSON Schema tools, and get a `LunaResponse` back.

It used to impersonate a google-genai client — Gemini-shaped `Content`/`Part`
objects in, a faked `candidates[0].content.parts` out — so a provider swap
could land without touching the loop or its tests. That shim is gone; what
remains here is request POLICY, which is genuinely this layer's job: retry and
back-off for transient 429s, one whole-request deadline across attempts, the
caller's rate-limit hooks, and usage accounting on every exit path.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import get_settings
from app.core.services.ai_usage import record_openai_response
from app.core.services.openai_responses import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    RESPONSES_URL,
    function_calls as _function_call_items,
    http_error_detail as _http_error_detail,
    response_text as _response_text,
)


_MAX_RATE_LIMIT_RETRIES = 2
_DEFAULT_TOTAL_TIMEOUT_SECONDS = DEFAULT_REQUEST_TIMEOUT_SECONDS
_MIN_RETRY_ATTEMPT_SECONDS = 1.0
_MAX_FALLBACK_DELAY_SECONDS = 30.0
_RETRY_JITTER_SECONDS = 0.5
_DURATION_PART_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)(ms|[smhd])", re.IGNORECASE)
_RETRY_MESSAGE_RE = re.compile(
    r"try again in\s+((?:[0-9]+(?:\.[0-9]+)?(?:ms|[smhd])\s*)+)",
    re.IGNORECASE,
)
_RESET_HEADERS = (
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "x-ratelimit-reset-project-tokens",
)

_RequestHook = Callable[[], Awaitable[None]]







def _duration_seconds(value: Any) -> float | None:
    """Parse OpenAI reset durations such as ``100ms`` or ``6m0s``."""
    matches = list(_DURATION_PART_RE.finditer(str(value or "")))
    if not matches:
        return None
    multipliers = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
    return sum(
        float(match.group(1)) * multipliers[match.group(2).lower()]
        for match in matches
    )


def _rate_limit_delay(response: httpx.Response, retry_number: int) -> float:
    """Return a provider-safe delay with jitter for a transient 429."""
    jitter = random.uniform(0.0, _RETRY_JITTER_SECONDS)
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            delay = float(retry_after)
            if math.isfinite(delay) and delay >= 0:
                # Retry-After is a minimum. Never cap or shorten it; the total
                # request budget below decides whether a retry can fit.
                return delay + jitter
        except ValueError:
            pass

    retry_message_delay = None
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message_match = _RETRY_MESSAGE_RE.search(str(error.get("message") or ""))
            if message_match:
                retry_message_delay = _duration_seconds(message_match.group(1))
    except (TypeError, ValueError):
        pass
    if retry_message_delay is not None:
        # The error message describes when this specific request can fit again;
        # reset headers describe when an entire bucket returns to its initial
        # state, which can be much later (for example 9.675s vs. 6m0s).
        return retry_message_delay + jitter

    candidates = [response.headers.get(name) for name in _RESET_HEADERS]
    parsed = [delay for candidate in candidates if (delay := _duration_seconds(candidate)) is not None]
    if parsed:
        # A 429 may be constrained by requests, organization tokens, or
        # project tokens. Waiting for the longest advertised reset is the safe
        # choice when the response does not identify a single dimension.
        return max(parsed) + jitter
    fallback = min(10.0 * (2 ** retry_number), _MAX_FALLBACK_DELAY_SECONDS)
    return fallback + jitter


def _is_retryable_rate_limit(exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code != 429:
        return False
    try:
        payload = exc.response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        return not (
            isinstance(error, dict)
            and "insufficient_quota" in (error.get("code"), error.get("type"))
        )
    except (TypeError, ValueError):
        return True


@dataclass(frozen=True)
class LunaResponse:
    """One Responses reply, read straight off the provider payload."""

    response_id: str | None
    text: str
    # `[{"call_id", "name", "arguments"}]`, in provider order. `call_id` is what
    # a result is paired back to; the retired Gemini shim had no id to carry and
    # re-paired on the tool NAME, which mispairs two concurrent calls to the
    # same tool with no warning.
    function_calls: list[dict[str, Any]] = field(default_factory=list)
    # Every output item verbatim — including `reasoning` — because the loop
    # feeds the assistant turn back as history and dropping items there lost
    # text that accompanied a tool call.
    output_items: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    status: str | None = None
    incomplete_details: dict[str, Any] | None = None

    @property
    def truncated(self) -> bool:
        """Whether the provider stopped early rather than finishing.

        Worth asking separately: a truncated or filtered reply otherwise looks
        exactly like a reply with no text and no tool calls, and the loop's
        fallback copy then blames the wrong thing.
        """
        return bool(self.incomplete_details) or self.status == "incomplete"


def tool_output_item(call_id: str, payload: Any) -> dict[str, Any]:
    """A `function_call_output` for one call, keyed by its own `call_id`."""
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps(payload if payload is not None else {}, default=str, separators=(",", ":")),
    }


def text_item(role: str, text: str) -> dict[str, Any]:
    """One text input item.

    The content type is load-bearing and is not a style choice: assistant
    history sent as `input_text` is a hard HTTP 400.
    """
    content_type = "output_text" if role == "assistant" else "input_text"
    return {"role": role, "content": [{"type": content_type, "text": text}]}


def image_item(data: bytes, mime_type: str | None) -> dict[str, Any]:
    """One user image input item. Assistant images are not valid as input."""
    encoded = base64.b64encode(data).decode("ascii")
    mime = mime_type or "application/octet-stream"
    return {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"}


class LunaSession:
    """A single turn's conversation with the Responses API.

    Instantiated per turn on purpose: `previous_response_id` chains the calls
    WITHIN one turn (the follow-ups then carry only tool outputs), and the
    chain must not leak into the next turn, which rebuilds its own history and
    system prompt.
    """

    def __init__(self) -> None:
        self._previous_response_id: str | None = None

    @property
    def previous_response_id(self) -> str | None:
        return self._previous_response_id

    async def create_response(
        self,
        *,
        model: str,
        input: list[dict[str, Any]],
        instructions: str,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format_json: bool = False,
        reasoning_effort: str = "high",
        store: bool = True,
        timeout_seconds: float = _DEFAULT_TOTAL_TIMEOUT_SECONDS,
        before_request: _RequestHook | None = None,
        after_request: _RequestHook | None = None,
    ) -> LunaResponse:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for Huume Luna")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        payload: dict[str, Any] = {
            "model": model,
            "input": input,
            # Responses does not carry request-level instructions forward with
            # previous_response_id, so the safety prompt is repeated on every
            # tool follow-up rather than sent once.
            "instructions": instructions or "",
            "tools": list(tools or []),
            "parallel_tool_calls": True,
            "reasoning": {"effort": reasoning_effort},
            # Pin the published standard-rate tier so per-call cost attribution
            # cannot silently drift to a differently priced service tier.
            "service_tier": "default",
            # The follow-up path reads server-side state through
            # previous_response_id. That depended on the API default until it
            # was stated here.
            "store": store,
        }
        # "required" is only valid alongside a non-empty tool array.
        if tool_choice and (tool_choice != "required" or payload["tools"]):
            payload["tool_choice"] = tool_choice
        if self._previous_response_id:
            payload["previous_response_id"] = self._previous_response_id
        # Structured-output switch for tool-less callers that parse the reply
        # as JSON. Without it the model may wrap the object in prose and the
        # caller's json.loads silently yields nothing.
        if response_format_json:
            payload["text"] = {"format": {"type": "json_object"}}

        data, attempt_started = await self._post(
            payload, model=model, api_key=settings.openai_api_key,
            timeout_seconds=timeout_seconds,
            before_request=before_request, after_request=after_request,
        )

        # An id-less response keeps the existing chain rather than resetting it.
        self._previous_response_id = data.get("id") or self._previous_response_id
        calls = []
        for item in _function_call_items(data):
            call_id = str(item.get("call_id") or "")
            name = str(item.get("name") or "")
            if not call_id or not name:
                # Unpairable: a result for it could never be attributed, and
                # the shim used to let it through and fail a round later on a
                # different turn's watch.
                raise RuntimeError(
                    "OpenAI Responses returned a function call without a name and call_id"
                )
            raw = item.get("arguments") or "{}"
            try:
                arguments = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:
                # Not silently `{}`: an argument-less call reads to the loop as
                # a deliberate no-arg invocation.
                raise RuntimeError(
                    f"OpenAI Responses returned unparsable arguments for {name}: {exc}"
                ) from exc
            calls.append({"call_id": call_id, "name": name, "arguments": arguments})

        await record_openai_response(
            model=model,
            latency_ms=int((time.monotonic() - attempt_started) * 1000),
            response=data,
        )
        return LunaResponse(
            response_id=data.get("id"),
            text=_response_text(data),
            function_calls=calls,
            output_items=[item for item in data.get("output", []) or [] if isinstance(item, dict)],
            usage=data.get("usage") or {},
            status=data.get("status"),
            incomplete_details=data.get("incomplete_details"),
        )

    async def _post(
        self, payload: dict[str, Any], *, model: str, api_key: str,
        timeout_seconds: float,
        before_request: _RequestHook | None, after_request: _RequestHook | None,
    ) -> tuple[dict[str, Any], float]:
        """POST with retry, under ONE deadline shared across attempts."""
        started = time.monotonic()
        deadline = started + timeout_seconds
        attempt_started = started
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            for retry_number in range(_MAX_RATE_LIMIT_RETRIES + 1):
                if time.monotonic() >= deadline:
                    raise RuntimeError("OpenAI Responses request deadline elapsed before an API attempt")
                if before_request is not None:
                    await before_request()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("OpenAI Responses request deadline elapsed before an API attempt")

                attempt_started = time.monotonic()
                try:
                    async with asyncio.timeout(remaining):
                        response = await client.post(
                            RESPONSES_URL,
                            headers={"Authorization": f"Bearer {api_key}"},
                            json=payload,
                        )
                except asyncio.CancelledError:
                    await record_openai_response(
                        model=model,
                        latency_ms=int((time.monotonic() - attempt_started) * 1000),
                        error="OpenAI Responses request cancelled",
                        status="timeout",
                    )
                    raise
                except TimeoutError as exc:
                    error_detail = f"request exceeded {timeout_seconds:g}s total deadline"
                    await record_openai_response(
                        model=model,
                        latency_ms=int((time.monotonic() - attempt_started) * 1000),
                        error=error_detail,
                        status="timeout",
                    )
                    raise RuntimeError(f"OpenAI Responses request failed: {error_detail}") from exc
                except httpx.HTTPError as exc:
                    error_detail = _http_error_detail(exc)
                    await record_openai_response(
                        model=model,
                        latency_ms=int((time.monotonic() - attempt_started) * 1000),
                        error=error_detail,
                        status="timeout" if isinstance(exc, httpx.TimeoutException) else "error",
                    )
                    raise RuntimeError(f"OpenAI Responses request failed: {error_detail}") from exc
                finally:
                    if after_request is not None:
                        await after_request()

                try:
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as exc:
                    error_detail = _http_error_detail(exc)
                    await record_openai_response(
                        model=model,
                        latency_ms=int((time.monotonic() - attempt_started) * 1000),
                        error=error_detail,
                        status="error",
                    )
                    if (
                        retry_number >= _MAX_RATE_LIMIT_RETRIES
                        or not _is_retryable_rate_limit(exc)
                    ):
                        raise RuntimeError(f"OpenAI Responses request failed: {error_detail}") from exc
                    delay = _rate_limit_delay(response, retry_number)
                    remaining = deadline - time.monotonic()
                    if delay + _MIN_RETRY_ATTEMPT_SECONDS > remaining:
                        raise RuntimeError(
                            "OpenAI Responses request failed: "
                            f"{error_detail} (retry delay {delay:.3f}s exceeds the remaining "
                            f"{max(remaining, 0.0):.3f}s request budget)"
                        ) from exc
                    await asyncio.sleep(delay)
        try:
            data = response.json()
        except (TypeError, ValueError) as exc:
            await record_openai_response(
                model=model,
                latency_ms=int((time.monotonic() - attempt_started) * 1000),
                error=f"Invalid Responses JSON: {exc}",
                status="error",
            )
            raise RuntimeError("OpenAI Responses returned invalid JSON") from exc
        if not isinstance(data, dict):
            await record_openai_response(
                model=model,
                latency_ms=int((time.monotonic() - attempt_started) * 1000),
                error="OpenAI Responses payload must be an object",
                status="error",
            )
            raise RuntimeError("OpenAI Responses payload must be an object")
        return data, attempt_started


def get_luna_client() -> LunaSession:
    """A fresh per-turn session. Tests monkeypatch this seam."""
    return LunaSession()
