"""Anthropic Messages session for the agent loops — the Claude twin of
`luna_client.LunaSession`.

It speaks the loops' existing contract on purpose: `create_response(...)`
takes the same Responses-shaped input items and tools every Luna caller
already builds (function tools, the hosted `web_search` tool, `tool_choice`,
JSON mode, `reasoning_effort`) and returns the same `LunaResponse`. So the
Huume loop, Espresso's project agents and the agent runtime do not branch on
provider — only the session object does. Which session a caller gets is
decided by `core/services/anthropic_messages.claude_override()` (the platform
"Agent model" setting) or, on the schedule assistant, by its dropdown.

Differences from Responses, and how each is absorbed here:

- **State.** Responses chains a turn's calls server-side
  (`previous_response_id`); Messages is stateless, so this session keeps the
  turn's conversation and resends it on every call (`keeps_history`). The
  history is append-only — each reply goes back exactly as returned,
  thinking blocks included — because the current models reject a thinking
  block whose earlier conversation changed.
- **Tools are fixed for the session.** For the same reason a change to
  `tools` mid-turn is a 400 once a thinking block is in the history. The
  first call's tool list is kept; a later call that offers fewer tools gets
  a note in its user turn naming the ones no longer available (callers
  re-check every tool call server-side anyway).
- **Forced tool calls.** Haiku 5.5 accepts `any` / a named tool; Sonnet 5.5
  rejects both, so there the request stays `auto`, the user turn says which
  tool to call, and one retry nudges a reply that called none.
- **Hosted web search** maps to Anthropic's server `web_search` tool, and
  its blocks are translated back into Responses `web_search_call` / message
  `url_citation` items in `output_items`, which is what the agent runtime's
  provenance gate reads.
- **Request policy.** The SDK's own retry (429 / 5xx / connection, honoring
  `retry-after`) runs inside ONE caller-supplied deadline; the rate-limit
  hooks fire once per call, not once per SDK retry.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import anthropic

from app.core.services.ai_usage import record_anthropic_response
from app.core.services.anthropic_messages import (
    CLAUDE_HAIKU,
    CLAUDE_SONNET,
    get_async_client,
    parse_json_object,
    request_extras,
)

from .luna_client import LunaResponse

_RequestHook = Callable[[], Awaitable[None]]

# Comfortably above any tool-call turn; the per-call deadline is the real
# bound. Non-streaming, so it stays well inside the SDK's long-request guard.
_MAX_TOKENS = 16_000
# Explicit, because the two models default differently (Haiku 5.5 `medium`,
# Sonnet 5.5 `high`). `medium` is the documented starting point for
# multistep tool use.
_DEFAULT_EFFORT = "medium"
_EFFORT_FROM_REASONING = {"minimal": "low", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"}
# The basic search tool for Haiku; the dynamic-filtering variant needs Sonnet.
_WEB_SEARCH_TYPE = {CLAUDE_HAIKU: "web_search_20250305", CLAUDE_SONNET: "web_search_20260209"}
# A server-tool loop can pause (`pause_turn`); each continuation is one more call.
_MAX_PAUSE_CONTINUATIONS = 3
_JSON_NOTE = (
    "Respond with exactly one JSON object and nothing else: no prose before or "
    "after it, and no Markdown code fences."
)


def _image_block(data_url: str) -> dict[str, Any] | None:
    """`data:<mime>;base64,<data>` → a Messages image block, or None for a
    type Messages does not accept (a PDF that rode in as an image part)."""
    header, _, data = str(data_url or "").partition(",")
    if not header.startswith("data:") or ";base64" not in header or not data:
        return None
    mime = header[len("data:"):].split(";", 1)[0].lower()
    if mime not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
        return None
    return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}


def to_messages(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Responses input items → Messages `messages`.

    Text and images map one to one; every `function_call_output` in the batch
    becomes a `tool_result` in ONE user message (splitting them teaches the
    model to stop calling tools in parallel). Empty text is dropped — Messages
    rejects an empty text block — adjacent same-role messages are merged, and
    Responses output items (reasoning, hosted calls) have no Messages
    equivalent and are skipped.
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
        kind = item.get("type")
        if kind == "function_call_output":
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": item["call_id"],
                "content": str(item.get("output") or "{}"),
            })
            continue
        if tool_results:
            push("user", tool_results)
            tool_results = []
        if kind not in (None, "message") or "role" not in item:
            continue
        role = "assistant" if item.get("role") == "assistant" else "user"
        blocks: list[dict[str, Any]] = []
        for part in item.get("content") or []:
            part_kind = part.get("type")
            if part_kind in ("input_text", "output_text", "text"):
                text = str(part.get("text") or "")
                if text.strip():
                    blocks.append({"type": "text", "text": text})
            elif part_kind == "input_image" and role == "user":
                block = _image_block(part.get("image_url") or "")
                if block:
                    blocks.append(block)
        push(role, blocks)
    if tool_results:
        push("user", tool_results)
    return messages


def _tools(specs: list[dict[str, Any]] | None, *, model: str, max_tool_calls: int | None) -> list[dict[str, Any]]:
    """Responses tools → Messages tools. Function tools keep their schema;
    the hosted `web_search` becomes Anthropic's server search tool."""
    out: list[dict[str, Any]] = []
    for spec in specs or []:
        kind = spec.get("type")
        if kind == "function" or (kind is None and spec.get("name")):
            out.append({
                "name": spec["name"],
                "description": spec.get("description") or "",
                "input_schema": spec.get("parameters") or {"type": "object", "properties": {}},
            })
        elif kind == "web_search":
            tool: dict[str, Any] = {"type": _WEB_SEARCH_TYPE.get(model, "web_search_20250305"), "name": "web_search"}
            if max_tool_calls:
                tool["max_uses"] = max_tool_calls
            out.append(tool)
    return out


def _usage(message: Any) -> dict[str, Any]:
    """Messages usage in the Responses shape the loops' accumulators read.

    Messages' `input_tokens` excludes cache reads and writes; Responses'
    includes them. Summed here so the loops' prompt-token bounds and the
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


def _sum_usage(total: dict[str, Any], add: dict[str, Any]) -> dict[str, Any]:
    if not total:
        return add
    if not add:
        return total
    return {
        "input_tokens": total["input_tokens"] + add["input_tokens"],
        "output_tokens": total["output_tokens"] + add["output_tokens"],
        "total_tokens": total["total_tokens"] + add["total_tokens"],
        "input_tokens_details": {"cached_tokens": total["input_tokens_details"]["cached_tokens"]
                                 + add["input_tokens_details"]["cached_tokens"]},
        "output_tokens_details": {},
    }


def output_items(blocks: list[Any]) -> list[dict[str, Any]]:
    """Server web-search blocks and cited text, as the Responses output items
    `openai_responses.web_search_calls` / `cited_urls` read: one
    `web_search_call` per search (its results as `action.sources`) and one
    `message` per text block, its citations as `url_citation` annotations."""
    results: dict[str, Any] = {}
    for block in blocks:
        if getattr(block, "type", None) == "web_search_tool_result":
            results[block.tool_use_id] = block.content
    items: list[dict[str, Any]] = []
    for block in blocks:
        kind = getattr(block, "type", None)
        if kind == "server_tool_use" and getattr(block, "name", None) == "web_search":
            found = results.get(block.id)
            ok = isinstance(found, list)
            sources = [{"type": "url", "url": r.url} for r in found if getattr(r, "url", None)] if ok else []
            query = block.input.get("query") if isinstance(block.input, dict) else None
            items.append({
                "type": "web_search_call", "id": block.id,
                "status": "completed" if ok else "failed",
                "action": {"type": "search", "query": query or "", "sources": sources},
            })
        elif kind == "text":
            annotations = [
                {"type": "url_citation", "url": c.url, "title": getattr(c, "title", None)}
                for c in (getattr(block, "citations", None) or [])
                if getattr(c, "url", None)
            ]
            items.append({"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": block.text, "annotations": annotations},
            ]})
    return items


def _forced_name(tool_choice: Any) -> str | None:
    if isinstance(tool_choice, dict) and tool_choice.get("name"):
        return str(tool_choice["name"])
    return None


class ClaudeSession:
    """One turn's conversation with the Messages API. Per turn, like
    `LunaSession`: the next turn rebuilds its own history and system prompt."""

    # The agent runtime reads this: a session that keeps its own history is
    # sent only what is new, never a replayed Responses transcript.
    keeps_history = True

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client
        self._messages: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] | None = None
        self._last_id: str | None = None

    @property
    def previous_response_id(self) -> str | None:
        return self._last_id

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = get_async_client()
        return self._client

    async def create_response(
        self,
        *,
        model: str,
        input: list[dict[str, Any]],
        instructions: str,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        response_format_json: bool = False,
        reasoning_effort: str | None = None,
        store: bool = True,
        timeout_seconds: float = 60.0,
        before_request: _RequestHook | None = None,
        after_request: _RequestHook | None = None,
        max_tool_calls: int | None = None,
        include: list[str] | None = None,
        chain: bool = True,
        effort: str | None = None,
    ) -> LunaResponse:
        """One model call (plus any `pause_turn` continuations and, for a
        forced tool on Sonnet, one nudge). `store` and `include` are Responses
        concepts with nothing to do here; `chain=False` means `input` is the
        whole conversation."""
        del store, include
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        client = self._get_client()
        offered = _tools(tools, model=model, max_tool_calls=max_tool_calls)
        if self._tools is None or not chain:
            self._tools = offered
        pinned = self._tools
        offered_names = {tool["name"] for tool in offered}
        withdrawn = [tool["name"] for tool in pinned if tool["name"] not in offered_names]

        notes: list[str] = []
        api_choice: dict[str, Any] | None = None
        forced = tool_choice == "required" or _forced_name(tool_choice) is not None
        if tool_choice == "none" or (pinned and not offered):
            api_choice = {"type": "none"}
        else:
            if withdrawn:
                notes.append(
                    "These tools are no longer available for this step; do not call them: "
                    + ", ".join(withdrawn) + "."
                )
            if forced and model != CLAUDE_SONNET:
                name = _forced_name(tool_choice)
                api_choice = {"type": "tool", "name": name} if name else {"type": "any"}
            elif forced:
                name = _forced_name(tool_choice)
                notes.append(f"Call the `{name}` tool now." if name else "Respond by calling one of the available tools.")
        if response_format_json:
            notes.append(_JSON_NOTE)

        history = self._messages if chain else []
        candidate = [*history, *to_messages(input)]
        if not candidate or candidate[0]["role"] != "user":
            candidate.insert(0, {"role": "user", "content": [{"type": "text", "text": "Hello."}]})
        if candidate[-1]["role"] != "user":
            # Prefill is a 400 on these models; the turn must end on the user.
            candidate.append({"role": "user", "content": []})
        tail = list(candidate[-1]["content"]) + [{"type": "text", "text": note} for note in notes]
        candidate[-1] = {**candidate[-1], "content": tail or [{"type": "text", "text": "Continue."}]}

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "system": instructions or "",
            "tools": pinned,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort or _EFFORT_FROM_REASONING.get(reasoning_effort or "", _DEFAULT_EFFORT)},
            # Follow-ups resend the whole turn; cache the prefix each time.
            "cache_control": {"type": "ephemeral"},
            **request_extras(model),
        }
        if api_choice is not None:
            params["tool_choice"] = api_choice

        if before_request is not None:
            await before_request()
        deadline = time.monotonic() + timeout_seconds
        try:
            content, message, usage = await self._call(client, params, candidate, deadline)
            nudge = (
                forced and model == CLAUDE_SONNET and message.stop_reason == "end_turn"
                and not any(block.type == "tool_use" for block in content)
            )
            if nudge:
                retry_from = [*candidate, {"role": "assistant", "content": list(content)}, {
                    "role": "user", "content": [{"type": "text", "text": "You must call a tool now."}],
                }]
                more, message, more_usage = await self._call(client, params, retry_from, deadline)
                candidate, content, usage = retry_from, more, _sum_usage(usage, more_usage)
        finally:
            if after_request is not None:
                await after_request()

        self._messages = [*candidate, {"role": "assistant", "content": list(content)}]
        self._last_id = message.id

        text = "\n".join(block.text for block in content if block.type == "text" and block.text).strip()
        # The SDK already validated each tool_use `input` as an object.
        calls = [
            {"call_id": block.id, "name": block.name, "arguments": block.input}
            for block in content if block.type == "tool_use"
        ]
        if response_format_json and text:
            try:
                text = json.dumps(parse_json_object(text))
            except ValueError:
                pass  # the caller's own parse reports it
        stop_reason = message.stop_reason
        incomplete = None
        if stop_reason in ("max_tokens", "refusal", "model_context_window_exceeded", "pause_turn"):
            incomplete = {"reason": stop_reason}
            if stop_reason == "refusal" and not text and not calls:
                text = "I can't help with that request."
        return LunaResponse(
            response_id=message.id,
            text=text,
            function_calls=calls,
            usage=usage,
            status="incomplete" if incomplete else "completed",
            incomplete_details=incomplete,
            output_items=output_items(content),
        )

    async def _call(
        self, client: anthropic.AsyncAnthropic, params: dict[str, Any],
        messages: list[dict[str, Any]], deadline: float,
    ) -> tuple[list[Any], Any, dict[str, Any]]:
        """One request plus its `pause_turn` continuations, all inside
        `deadline`. Returns the reply's blocks (continuations merged), the
        last message, and the summed usage. Every attempt writes a ledger row."""
        content: list[Any] = []
        usage: dict[str, Any] = {}
        sent = messages
        message = None
        for _ in range(_MAX_PAUSE_CONTINUATIONS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Anthropic Messages request deadline elapsed")
            message = await self._post(client, {**params, "messages": sent}, remaining)
            content.extend(message.content)
            usage = _sum_usage(usage, _usage(message))
            if message.stop_reason != "pause_turn":
                break
            # A paused server-tool loop resumes from the assistant turn as is.
            sent = [*messages, {"role": "assistant", "content": list(content)}]
        return content, message, usage

    async def _post(self, client: anthropic.AsyncAnthropic, params: dict[str, Any], timeout: float) -> Any:
        model = params["model"]
        started = time.monotonic()
        try:
            message = await client.with_options(timeout=timeout).beta.messages.create(**params)
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
                error=f"request exceeded {timeout:g}s", status="timeout",
            )
            raise RuntimeError(f"Anthropic Messages request timed out after {timeout:g}s") from exc
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
        # Record first, as luna_client does: the call is billed now, and the
        # parsing after it can raise.
        await record_anthropic_response(
            model=model, latency_ms=int((time.monotonic() - started) * 1000),
            message=message.model_dump(mode="json"),
        )
        return message


def get_claude_client() -> ClaudeSession:
    """A fresh per-turn session. Tests monkeypatch this seam."""
    return ClaudeSession()
