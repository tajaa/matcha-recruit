"""Anthropic Claude: the shared client, the platform "Agent model" switch, and
a one-shot text/JSON call.

Claude is an opt-in alternative for the workloads that run on OpenAI Luna or
on Gemini's one-shot JSON calls. Which model runs is decided in ONE place —
`claude_override()` — from the admin setting `platform_settings.agent_model`
(Admin → Settings). "default" keeps every surface on the provider it was
built on; a Claude id routes them all to that model. The schedule assistant's
own dropdown is the one per-turn override on top of it.

The multi-turn tool loops use `services/huume/claude_client.ClaudeSession`;
this module is the single-shot half plus the pieces both share.
`generate_content_routed` lets a plain Gemini `generate_content` call site
follow the switch without being rewritten.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from types import SimpleNamespace
from typing import Any, Optional

import anthropic

from app.config import get_settings
from app.core.services.ai_usage import record_anthropic_response

logger = logging.getLogger(__name__)

CLAUDE_HAIKU = "claude-haiku-5-5"
CLAUDE_SONNET = "claude-sonnet-5-5"
CLAUDE_MODELS: tuple[str, ...] = (CLAUDE_HAIKU, CLAUDE_SONNET)
CLAUDE_LABELS: dict[str, str] = {CLAUDE_HAIKU: "Claude Haiku 5.5", CLAUDE_SONNET: "Claude Sonnet 5.5"}

# Server-side refusal fallback (Claude API only). Sonnet 5.5 accepts the
# `"default"` form; Haiku 5.5 has no server-side fallback.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
_JSON_INSTRUCTION = (
    "Respond with exactly one JSON object and nothing else: no prose before or "
    "after it, and no Markdown code fences."
)

_client: Optional[anthropic.AsyncAnthropic] = None


def anthropic_configured() -> bool:
    try:
        return bool(get_settings().anthropic_api_key)
    except RuntimeError:  # settings not loaded (a bare test process)
        return False


def get_async_client() -> anthropic.AsyncAnthropic:
    """Module-cached async client. Raises when no key is configured."""
    global _client
    if _client is None:
        api_key = get_settings().anthropic_api_key
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for Claude")
        _client = anthropic.AsyncAnthropic(api_key=api_key)
    return _client


def request_extras(model: str) -> dict[str, Any]:
    """Per-model request fields every Claude call sends."""
    if model == CLAUDE_SONNET:
        return {"fallbacks": "default", "betas": [_FALLBACK_BETA]}
    return {}


async def claude_override() -> Optional[str]:
    """The Claude model the platform "Agent model" setting routes agent and
    one-shot workloads to, or None to keep each surface on its own provider.

    Never raises: a missing key, an unreadable setting or an unknown value all
    mean "default", so a settings outage can never take a surface down.
    """
    if not anthropic_configured():
        return None
    try:
        from app.core.services.platform_settings import get_agent_model

        choice = await get_agent_model()
    except Exception:
        logger.warning("agent model setting unreadable; using each surface's default", exc_info=True)
        return None
    return choice if choice in CLAUDE_MODELS else None


def image_block(data: bytes, mime_type: str | None) -> dict[str, Any] | None:
    """Image bytes as a Messages block, or None for a type Messages rejects."""
    mime = (mime_type or "").lower()
    if mime not in _IMAGE_TYPES or not data:
        return None
    return {"type": "image", "source": {
        "type": "base64", "media_type": mime, "data": base64.b64encode(data).decode("ascii"),
    }}


def pdf_block(data: bytes) -> dict[str, Any]:
    return {"type": "document", "source": {
        "type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode("ascii"),
    }}


def parse_json_object(text: str) -> dict:
    """The JSON object in a reply: tolerates code fences and stray prose
    around it. Raises ValueError when there is none."""
    raw = (text or "").strip()
    fenced = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", raw, re.S)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object in the reply") from None
        parsed = json.loads(raw[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("reply JSON is not an object")
    return parsed


async def generate_text(
    prompt: str,
    *,
    model: str,
    system: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    json_output: bool = False,
    max_tokens: int = 8_000,
    effort: str = "low",
    timeout_seconds: float = 60.0,
) -> str:
    """One Messages call; returns the reply text. Raises RuntimeError on any
    API failure, after writing the ledger row.

    `attachments` are Messages content blocks (`image_block`/`pdf_block`)
    placed before the prompt. `json_output` adds a JSON-only instruction —
    callers still parse with `parse_json_object`, which tolerates fences.
    `max_tokens` covers thinking too, so it is floored at 4096: a small cap
    with adaptive thinking on can spend it all before the answer.
    """
    system_text = "\n\n".join(part for part in (system, _JSON_INSTRUCTION if json_output else None) if part)
    content: list[dict[str, Any]] = [*(attachments or []), {"type": "text", "text": prompt}]
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": max(max_tokens, 4_096),
        "messages": [{"role": "user", "content": content}],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort},
        **request_extras(model),
    }
    if system_text:
        params["system"] = system_text
    started = time.monotonic()
    try:
        message = await get_async_client().with_options(timeout=timeout_seconds).beta.messages.create(**params)
    except anthropic.APIError as exc:
        status = "timeout" if isinstance(exc, anthropic.APITimeoutError) else "error"
        await record_anthropic_response(
            model=model, latency_ms=int((time.monotonic() - started) * 1000),
            error=str(exc)[:500], status=status,
        )
        raise RuntimeError(f"Anthropic Messages request failed: {exc}") from exc
    await record_anthropic_response(
        model=model, latency_ms=int((time.monotonic() - started) * 1000),
        message=message.model_dump(mode="json"),
    )
    if message.stop_reason == "refusal":
        raise RuntimeError("Anthropic Messages declined the request")
    return "\n".join(block.text for block in message.content if block.type == "text").strip()


def _gemini_contents_to_claude(contents: Any) -> tuple[str, list[dict[str, Any]]]:
    """Gemini `contents` (a string, or a list of strings / Parts / Contents)
    → (prompt text, attachment blocks). Text joins in order; inline PDFs and
    images become `pdf_block` / `image_block`. These call sites send one user
    turn, so roles are not preserved."""
    texts: list[str] = []
    attachments: list[dict[str, Any]] = []

    def take(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, str):
            if item.strip():
                texts.append(item)
            return
        parts = getattr(item, "parts", None)
        if parts is not None:  # a types.Content
            for part in parts:
                take(part)
            return
        text = getattr(item, "text", None)
        if isinstance(text, str):
            if text.strip():
                texts.append(text)
            return
        inline = getattr(item, "inline_data", None)
        if inline is not None:
            data = getattr(inline, "data", None) or b""
            mime = (getattr(inline, "mime_type", None) or "").lower()
            block = pdf_block(data) if mime == "application/pdf" and data else image_block(data, mime)
            if block:
                attachments.append(block)

    for item in contents if isinstance(contents, (list, tuple)) else [contents]:
        take(item)
    return "\n\n".join(texts), attachments


async def generate_content_routed(
    client: Any,
    *,
    model: str,
    contents: Any,
    config: Any = None,
    timeout_seconds: float,
    json_output: bool | None = None,
    max_tokens: int = 16_000,
    effort: str = "low",
) -> Any:
    """`client.aio.models.generate_content`, unless the admin Agent model names
    a Claude model, in which case the same request runs there.

    Returns the Gemini response, or an object with the same `.text` the call
    sites read. Raises like Gemini does (`asyncio.TimeoutError` past the
    timeout, `RuntimeError` on an API failure), so each site's existing
    error handling stays as is. Claude gets the SAME `timeout_seconds` as
    Gemini, retries included: a chat turn budgeted at 20s stays 20s, and a
    slower model surfaces as that site's usual timeout reply rather than a
    longer wait. `json_output` defaults to the config's
    `response_mime_type`; pass True where the prompt asks for JSON in prose.
    In JSON mode the reply is normalized to the bare object, so a site that
    `json.loads` the text strictly keeps working. Gemini-only knobs
    (temperature, safety settings) are dropped on the Claude path.
    """
    claude_model = await claude_override()
    if not claude_model:
        return await asyncio.wait_for(
            client.aio.models.generate_content(model=model, contents=contents, config=config),
            timeout=timeout_seconds,
        )
    if json_output is None:
        json_output = getattr(config, "response_mime_type", None) == "application/json"
    system = getattr(config, "system_instruction", None)
    prompt, attachments = _gemini_contents_to_claude(contents)
    text = await asyncio.wait_for(
        generate_text(
            prompt,
            model=claude_model,
            system=system if isinstance(system, str) else None,
            attachments=attachments,
            json_output=json_output,
            max_tokens=max_tokens,
            effort=effort,
            timeout_seconds=timeout_seconds,
        ),
        timeout=timeout_seconds,
    )
    if json_output:
        try:
            text = json.dumps(parse_json_object(text))
        except ValueError:
            pass  # the site's own parser reports it
    return SimpleNamespace(text=text, usage_metadata=None)
