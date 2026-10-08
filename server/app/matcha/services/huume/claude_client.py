"""Anthropic Messages session for the Huume loop — the schedule assistant's
opt-in alternative to Luna (`routing.SCHEDULE_MODEL_CHOICES`).

It speaks the loop's existing contract on purpose: `create_response(...)`
takes the same Responses-shaped input items and function tools `agent.py`
already builds, and returns the same `LunaResponse`. So the loop, its tool
pairing by `call_id`, its bounds and its tests do not branch on provider —
only the session object does.

The one real difference is state. Responses chains a turn's follow-up calls
server-side through `previous_response_id`; Messages is stateless, so this
session keeps the turn's conversation itself and resends it on every call.
The history is append-only — each reply goes back exactly as returned
(`to_param()`, thinking blocks included), never edited — which is what the
current models' preserved-thinking check requires.

Request policy differs from `luna_client` in one deliberate way: the SDK's own
retry (429 / 5xx / connection, honoring `retry-after`) runs inside ONE
caller-supplied deadline, rather than a hand-rolled ladder. The rate-limit
hooks therefore fire once per call, not once per SDK retry.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import anthropic

from app.config import get_settings
from app.core.services.ai_usage import record_anthropic_response

from .luna_client import LunaResponse
from .routing import CLAUDE_SONNET

_RequestHook = Callable[[], Awaitable[None]]

# Comfortably above any tool-call turn; the per-call deadline is the real
# bound. Non-streaming, so it stays well inside the SDK's long-request guard.
_MAX_TOKENS = 16_000
# Explicit, because the two models default differently (Haiku 5.5 `medium`,
# Sonnet 5.5 `high`). `medium` is the documented starting point for multistep
# tool use; the loop's state block and tool refusals carry the hard parts.
_DEFAULT_EFFORT = "medium"
# Server-side refusal fallback (Claude API only). Sonnet 5.5 accepts the
# `"default"` form; Haiku 5.5 has no server-side fallback.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})


def _tool(spec: dict[str, Any]) -> dict[str, Any]:
    """A Responses function tool as a Messages tool."""
    return {
        "name": spec["name"],
        "description": spec.get("description") or "",
        "input_schema": spec.get("parameters") or {"type": "object", "properties": {}},
    }


def _image_block(data_url: str) -> dict[str, Any] | None:
    """`data:<mime>;base64,<data>` → a Messages image block, or None for a
    type Messages does not accept (a PDF that rode in as an image part)."""
    header, _, data = str(data_url or "").partition(",")
    if not header.startswith("data:") or ";base64" not in header or not data:
        return None
    mime = header[len("data:"):].split(";", 1)[0].lower()
    if mime not in _IMAGE_TYPES:
        return None
    return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}


def to_messages(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Responses input items → Messages `messages`.

    Text and images map one to one; every `function_call_output` in the batch
    becomes a `tool_result` in ONE user message (splitting them teaches the
    model to stop calling tools in parallel). Empty text is dropped — Messages
    rejects an empty text block — and adjacent same-role messages are merged.
    """
    messages: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if not blocks:
            return
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": blocks})

    tool_results: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") == "function_call_output":
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": item["call_id"],
                "content": str(item.get("output") or "{}"),
            })
            continue
        if tool_results:
            push("user", tool_results)
            tool_results = []
        role = "assistant" if item.get("role") == "assistant" else "user"
        blocks: list[dict[str, Any]] = []
        for part in item.get("content") or []:
            kind = part.get("type")
            if kind in ("input_text", "output_text", "text"):
                text = str(part.get("text") or "")
                if text.strip():
                    blocks.append({"type": "text", "text": text})
            elif kind == "input_image" and role == "user":
                block = _image_block(part.get("image_url") or "")
                if block:
                    blocks.append(block)
        push(role, blocks)
    if tool_results:
        push("user", tool_results)
    return messages


def _usage(message: Any) -> dict[str, Any]:
    """Messages usage in the Responses shape `agent._accumulate_usage` reads.

    Messages' `input_tokens` excludes cache reads and writes; Responses'
    includes them. Summed here so the loop's prompt-token bound and the
    per-turn cost see the whole prompt, as they do for Luna.
    """
    usage = getattr(message, "usage", None)
    if usage is None:
        return {}
    cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", None) or 0
    input_total = (getattr(usage, "input_tokens", None) or 0) + cache_read + cache_write
    output = getattr(usage, "output_tokens", None) or 0
    return {
        "input_tokens": input_total,
        "output_tokens": output,
        "total_tokens": input_total + output,
        "input_tokens_details": {"cached_tokens": cache_read},
        "output_tokens_details": {},
    }


class ClaudeSession:
    """One turn's conversation with the Messages API. Per turn, like
    `LunaSession`: the next turn rebuilds its own history and system prompt."""

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client
        self._messages: list[dict[str, Any]] = []
        self._last_id: str | None = None

    @property
    def previous_response_id(self) -> str | None:
        return self._last_id

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            api_key = get_settings().anthropic_api_key
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is required for Claude in Huume")
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        return self._client

    async def create_response(
        self,
        *,
        model: str,
        input: list[dict[str, Any]],
        instructions: str,
        tools: list[dict[str, Any]] | None = None,
        timeout_seconds: float = 60.0,
        before_request: _RequestHook | None = None,
        after_request: _RequestHook | None = None,
        effort: str = _DEFAULT_EFFORT,
    ) -> LunaResponse:
        """One model call. The first call sends the conversation; later calls
        send only tool outputs, appended to the turn's history kept here."""
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        client = self._get_client()
        appended = to_messages(input)
        candidate = [*self._messages, *appended]
        if not candidate or candidate[0]["role"] != "user":
            candidate.insert(0, {"role": "user", "content": [{"type": "text", "text": "Hello."}]})
        if candidate[-1]["role"] != "user":
            # Prefill is a 400 on these models; the turn must end on the user.
            candidate.append({"role": "user", "content": [{"type": "text", "text": "Continue."}]})

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "system": instructions or "",
            "messages": candidate,
            "tools": [_tool(spec) for spec in tools or []],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
            # Follow-ups resend the whole turn; cache the prefix each time.
            "cache_control": {"type": "ephemeral"},
        }
        if model == CLAUDE_SONNET:
            params["fallbacks"] = "default"
            params["betas"] = [_FALLBACK_BETA]

        if before_request is not None:
            await before_request()
        started = time.monotonic()
        try:
            message = await client.with_options(timeout=timeout_seconds).beta.messages.create(**params)
        except asyncio.CancelledError:
            # The loop's own wait_for deadline cancels a call that is still
            # inside an SDK retry; it must still leave a ledger row.
            await record_anthropic_response(
                model=model, latency_ms=int((time.monotonic() - started) * 1000),
                error="Anthropic Messages request cancelled", status="timeout",
            )
            raise
        except anthropic.APITimeoutError as exc:
            await record_anthropic_response(
                model=model, latency_ms=int((time.monotonic() - started) * 1000),
                error=f"request exceeded {timeout_seconds:g}s", status="timeout",
            )
            raise RuntimeError(f"Anthropic Messages request timed out after {timeout_seconds:g}s") from exc
        except anthropic.APIStatusError as exc:
            detail = f"{exc.status_code}: {exc.message}"
            await record_anthropic_response(
                model=model, latency_ms=int((time.monotonic() - started) * 1000),
                error=detail, status="error",
            )
            raise RuntimeError(f"Anthropic Messages request failed: {detail}") from exc
        except anthropic.APIConnectionError as exc:
            await record_anthropic_response(
                model=model, latency_ms=int((time.monotonic() - started) * 1000),
                error=str(exc), status="error",
            )
            raise RuntimeError(f"Anthropic Messages request failed: {exc}") from exc
        finally:
            if after_request is not None:
                await after_request()

        # Record first, as luna_client does: the call is billed now, and the
        # parsing below can raise.
        await record_anthropic_response(
            model=model, latency_ms=int((time.monotonic() - started) * 1000),
            message=message.model_dump(mode="json"),
        )
        self._messages = [*candidate, message.to_param()]
        self._last_id = message.id

        texts: list[str] = []
        calls: list[dict[str, Any]] = []
        for block in message.content:
            if block.type == "text":
                texts.append(block.text)
            elif block.type == "tool_use":
                # The SDK already validated `input` as an object.
                calls.append({"call_id": block.id, "name": block.name, "arguments": block.input})

        stop_reason = message.stop_reason
        text = "\n".join(t for t in texts if t).strip()
        incomplete = None
        if stop_reason in ("max_tokens", "refusal", "model_context_window_exceeded"):
            incomplete = {"reason": stop_reason}
            if stop_reason == "refusal" and not text and not calls:
                text = "I can't help with that request."
        return LunaResponse(
            response_id=message.id,
            text=text,
            function_calls=calls,
            usage=_usage(message),
            status="incomplete" if incomplete else "completed",
            incomplete_details=incomplete,
        )


def get_claude_client() -> ClaudeSession:
    """A fresh per-turn session. Tests monkeypatch this seam."""
    return ClaudeSession()
