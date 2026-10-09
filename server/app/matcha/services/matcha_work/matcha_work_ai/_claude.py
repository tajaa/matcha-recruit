"""Claude for the skill engine's one structured-JSON call — what a Claude
pick in Espresso's model picker runs on.

Same inputs as `GeminiProvider._call_gemini`: the static prompt (instructions
+ company context) and the dynamic prompt (per-message state) become two
system blocks, and the Gemini `contents` the provider already built are
translated to Messages turns, images included. Same output: the reply text
the provider's shared parser reads, plus a `token_usage` dict.

Where Gemini needs differ:

- **Caching.** Gemini creates a server-side cache object per company and
  prompt hash; Messages caches by prefix. The static block carries
  `cache_control`, so a company's next turn reads it from cache.
- **JSON mode.** There is no schema-less JSON switch, so the system prompt
  closes with a JSON-only instruction and the reply goes through the
  provider's existing `_clean_json_text` + parse, which already tolerates
  fences.
- **Thinking.** The engine's thinking level maps onto effort (adaptive
  thinking stays on: Sonnet 5.5 rejects `disabled`).
"""

from __future__ import annotations

import time
from typing import Any

import anthropic

from app.core.services.ai_usage import record_anthropic_response
from app.core.services.anthropic_messages import get_async_client, image_block, request_extras

# Document turns (a handbook, a deck) can be long. Non-streaming, but the
# explicit timeout below is what bounds the call.
_MAX_TOKENS = 32_000
_EFFORT = {"none": "low", "low": "medium", "high": "high"}
_JSON_ONLY = (
    "Respond with exactly one JSON object in the shape described above and "
    "nothing else: no prose before or after it, and no Markdown code fences."
)


def to_messages(contents: list[Any]) -> list[dict[str, Any]]:
    """The provider's Gemini `contents` → Messages turns.

    Text parts and inline images map one to one; empty text and image types
    Messages rejects are dropped; adjacent same-role turns merge. A thread
    that opens or ends on the assistant is padded so it opens and ends on
    the user (assistant prefill is a 400 on these models).
    """
    messages: list[dict[str, Any]] = []
    for content in contents:
        role = "assistant" if getattr(content, "role", "user") == "model" else "user"
        blocks: list[dict[str, Any]] = []
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            inline = getattr(part, "inline_data", None)
            if text and text.strip():
                blocks.append({"type": "text", "text": text})
            elif inline is not None and role == "user":
                block = image_block(getattr(inline, "data", None) or b"", getattr(inline, "mime_type", None))
                if block:
                    blocks.append(block)
        if not blocks:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": blocks})
    if not messages or messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": [{"type": "text", "text": "(conversation start)"}]})
    if messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": [{"type": "text", "text": "Continue."}]})
    return messages


def _usage(message: Any, model: str) -> dict[str, Any] | None:
    """Token usage in the engine's shape. `prompt_tokens` is the WHOLE
    prompt (Messages reports cache reads and writes apart from
    `input_tokens`), with cache reads also in `cached_tokens` — the split
    `model_pricing.calculate_call_cost` prices."""
    usage = getattr(message, "usage", None)
    if usage is None:
        return None
    cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", None) or 0
    prompt = (getattr(usage, "input_tokens", None) or 0) + cache_read + cache_write
    completion = getattr(usage, "output_tokens", None) or 0
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "cached_tokens": cache_read,
        "estimated": False,
        "model": model,
    }


async def call_claude(
    *,
    static_prompt: str,
    dynamic_prompt: str,
    contents: list[Any],
    model: str,
    thinking_level: str,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any] | None]:
    """One skill-engine call on Claude → (reply text, token_usage).

    Raises RuntimeError on an API failure (after writing the ledger row);
    the provider turns that into the same "try again" reply a Gemini failure
    gets. A refusal comes back as text the parser cannot read, so the
    provider's salvage path shows a generic reply rather than nothing.
    """
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": _MAX_TOKENS,
        "system": [
            {"type": "text", "text": static_prompt, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"{dynamic_prompt}\n\n{_JSON_ONLY}"},
        ],
        "messages": to_messages(contents),
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": _EFFORT.get(thinking_level, "medium")},
        **request_extras(model),
    }
    started = time.monotonic()
    try:
        message = await get_async_client().with_options(timeout=timeout_seconds).beta.messages.create(**params)
    except anthropic.APIError as exc:
        await record_anthropic_response(
            model=model, latency_ms=int((time.monotonic() - started) * 1000), error=str(exc)[:500],
            status="timeout" if isinstance(exc, anthropic.APITimeoutError) else "error",
        )
        raise RuntimeError(f"Anthropic Messages request failed: {exc}") from exc
    await record_anthropic_response(
        model=model, latency_ms=int((time.monotonic() - started) * 1000),
        message=message.model_dump(mode="json"),
    )
    text = "\n".join(block.text for block in message.content if block.type == "text").strip()
    return text, _usage(message, model)
