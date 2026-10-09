"""Anthropic Claude: the shared client, the per-app "AI models" switch, and
a one-shot text/JSON call.

Claude is an opt-in alternative for the workloads that run on OpenAI Luna or
on Gemini's one-shot JSON calls. Which model runs is decided in ONE place —
`claude_override(surface)` — from the admin setting `agent_models` (Admin →
Settings → AI models): one choice per app, overridable per product, keyed by
the surfaces in `agent_surfaces.py`. "default" keeps a surface on the
provider it was built on; a Claude id routes it to that model. The schedule
assistant's own dropdown is the one per-turn override on top of it.

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


async def claude_override(surface: str) -> Optional[str]:
    """The Claude model the admin "AI models" setting routes this surface to
    (an `agent_surfaces` key), or None to keep it on its own provider.

    Never raises: a missing key, an unreadable setting or a non-Claude value
    all mean "default", so a settings outage can never take a surface down.
    """
    if not anthropic_configured():
        return None
    try:
        from app.core.services.platform_settings import get_agent_model

        choice = await get_agent_model(surface)
    except Exception:
        logger.warning("agent model setting unreadable; using %s's default", surface, exc_info=True)
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


async def _create(params: dict[str, Any], *, timeout_seconds: float, deadline: float | None = None) -> Any:
    """One Messages call plus its ledger row, success or not. Raises
    RuntimeError on an API failure or a refusal; with `deadline`, raises
    asyncio.TimeoutError once it passes (SDK retries included), after
    writing a status='timeout' row so the slowest calls are still counted."""
    model = params["model"]
    started = time.monotonic()
    request = get_async_client().with_options(timeout=timeout_seconds).beta.messages.create(**params)
    try:
        message = await (asyncio.wait_for(request, timeout=deadline) if deadline else request)
    except asyncio.TimeoutError:
        await record_anthropic_response(
            model=model, latency_ms=int((time.monotonic() - started) * 1000),
            error=f"deadline of {deadline}s passed", status="timeout",
        )
        raise
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
    return message


def _reply_text(message: Any) -> str:
    return "\n".join(block.text for block in message.content if block.type == "text").strip()


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
    return _reply_text(await _create(params, timeout_seconds=timeout_seconds))


def gemini_contents_to_messages(contents: Any) -> list[dict[str, Any]]:
    """Gemini `contents` → Messages turns. THE translator: the matcha-work
    skill engine (`matcha_work_ai._claude.to_messages`) and
    `generate_content_routed` both use it.

    `contents` is a string, or a list of strings / Parts / Contents. Roles
    carry over ("model" → assistant; a bare string or Part is a user turn);
    text maps one to one; inline PDFs and images become `pdf_block` /
    `image_block` in user turns (assistant turns can't carry them, and image
    types Messages rejects are dropped); empty text is dropped; adjacent
    same-role turns merge. A thread that opens or ends on the assistant is
    padded so it opens and ends on the user (assistant prefill is a 400 on
    these models).
    """
    messages: list[dict[str, Any]] = []

    def blocks_of(part: Any, role: str) -> list[dict[str, Any]]:
        if isinstance(part, str):
            return [{"type": "text", "text": part}] if part.strip() else []
        text = getattr(part, "text", None)
        if isinstance(text, str):
            return [{"type": "text", "text": text}] if text.strip() else []
        inline = getattr(part, "inline_data", None)
        if inline is None or role != "user":
            return []
        data = getattr(inline, "data", None) or b""
        mime = (getattr(inline, "mime_type", None) or "").lower()
        block = pdf_block(data) if mime == "application/pdf" and data else image_block(data, mime)
        return [block] if block else []

    for item in contents if isinstance(contents, (list, tuple)) else [contents]:
        if item is None:
            continue
        parts = getattr(item, "parts", None)
        if parts is not None:  # a types.Content
            role = "assistant" if getattr(item, "role", "user") == "model" else "user"
            blocks = [b for part in parts for b in blocks_of(part, role)]
        else:
            role = "user"
            blocks = blocks_of(item, role)
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


class RoutedClaudeError(RuntimeError):
    """A call `generate_content_routed` sent to Claude failed (API error,
    refusal, or a reply cut off at max_tokens). Its own type so a Gemini
    model-fallback loop re-raises it instead of retrying the same Claude call
    under a different Gemini model name."""


# Any JSON value, not only an object: some sites ask for a list.
_JSON_ANY_INSTRUCTION = (
    "Respond with only the JSON the request asks for (an object or an array) "
    "and nothing else: no prose before or after it, and no Markdown code fences."
)
# Messages limits for what a routed call carries (build-with-claude/vision,
# PDF support): 32 MB per request, 600 PDF pages on these 1M-context models.
_MAX_ROUTED_ATTACHMENT_B64 = 30 * 1024 * 1024
_MAX_PDF_PAGES = 600


def _extract_json(text: str) -> str | None:
    """The first JSON value (object or array) in a reply, re-serialized; None
    when there is none. Tolerates fences and prose around it."""
    raw = (text or "").strip()
    fenced = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", raw, re.S)
    if fenced:
        raw = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for start, char in enumerate(raw):
        if char in "{[":
            try:
                value, _ = decoder.raw_decode(raw, start)
            except json.JSONDecodeError:
                continue
            return json.dumps(value)
    return None


def _claude_can_carry(contents: Any) -> bool:
    """False when an inline attachment would break a Messages request: over
    the request size budget, or a PDF past the page limit. A PDF pypdf can't
    read is left for the API to judge."""
    items = contents if isinstance(contents, (list, tuple)) else [contents]
    parts = [p for item in items for p in (getattr(item, "parts", None) or [item])]
    total = 0
    for part in parts:
        inline = getattr(part, "inline_data", None)
        data = getattr(inline, "data", None) if inline is not None else None
        if not data:
            continue
        total += 4 * ((len(data) + 2) // 3)
        if (getattr(inline, "mime_type", "") or "").lower() == "application/pdf":
            try:
                import io

                from pypdf import PdfReader

                if len(PdfReader(io.BytesIO(data)).pages) > _MAX_PDF_PAGES:
                    return False
            except Exception:
                pass
    return total <= _MAX_ROUTED_ATTACHMENT_B64


async def _anthropic_bucket_allows(service: str, endpoint: str) -> bool:
    """Check the anthropic rate-limit bucket and count this call in it. A
    full bucket → False (the caller runs on Gemini). A limiter outage lets the
    call through rather than taking the surface down."""
    from app.core.services.rate_limiter import RateLimitExceeded, get_rate_limiter

    limiter = get_rate_limiter("anthropic")
    try:
        await limiter.check_limit(service, endpoint)
    except RateLimitExceeded as exc:
        logger.warning("routed %s/%s: %s; running on Gemini", service, endpoint, exc)
        return False
    except Exception:
        logger.warning("routed %s/%s: anthropic rate-limit check failed; allowing", service, endpoint, exc_info=True)
        return True
    try:
        await limiter.record_call(service, endpoint)
    except Exception:
        logger.warning("routed %s/%s: could not record an anthropic call", service, endpoint, exc_info=True)
    return True


def ran_on_claude(response: Any) -> bool:
    """Whether `generate_content_routed` answered on Claude. A caller that
    counts its own calls in the Gemini bucket skips the count when it did."""
    return getattr(response, "provider", None) == "anthropic"


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
    surface: str | None,
    rate_label: tuple[str, str] = ("agent_model", "routed"),
) -> Any:
    """`client.aio.models.generate_content`, unless the admin AI-model setting
    routes `surface` to Claude, in which case the same request runs there.

    Returns the Gemini response, or an object with the same `.text` the call
    sites read (and `provider="anthropic"`, see `ran_on_claude`). Raises like
    Gemini does — `asyncio.TimeoutError` past the timeout — so each site's
    error handling stays as is; a Claude failure is a `RoutedClaudeError`.
    Claude gets the SAME `timeout_seconds`, retries included: a chat turn
    budgeted at 20s stays 20s.

    The call runs on Gemini instead when the `anthropic` rate-limit bucket is
    full (`rate_label` names it there) or an attachment is past Claude's
    limits. `surface` is the `agent_surfaces` key whose setting decides; None
    pins Gemini, for a caller that shares this path with a surface the
    setting doesn't route.

    `json_output` defaults to the config's `response_mime_type`; pass True
    where the prompt asks for JSON in prose. The reply is then reduced to the
    bare JSON value (object or array), so a site that `json.loads` it
    strictly keeps working, and a reply cut off at `max_tokens` (thinking
    shares the cap) is an error rather than broken JSON. Gemini-only knobs
    (temperature, safety settings) are dropped on the Claude path.
    """
    claude_model = await claude_override(surface) if surface else None
    if claude_model and not _claude_can_carry(contents):
        logger.info("routed %s/%s: attachments past Claude's limits; running on Gemini", *rate_label)
        claude_model = None
    if claude_model and not await _anthropic_bucket_allows(*rate_label):
        claude_model = None
    if not claude_model:
        return await asyncio.wait_for(
            client.aio.models.generate_content(model=model, contents=contents, config=config),
            timeout=timeout_seconds,
        )

    if json_output is None:
        json_output = getattr(config, "response_mime_type", None) == "application/json"
    system = getattr(config, "system_instruction", None)
    system_text = "\n\n".join(
        part for part in (system if isinstance(system, str) else None, _JSON_ANY_INSTRUCTION if json_output else None)
        if part
    )
    params: dict[str, Any] = {
        "model": claude_model,
        "max_tokens": max(max_tokens, 4_096),
        "messages": gemini_contents_to_messages(contents),
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort},
        **request_extras(claude_model),
    }
    if system_text:
        params["system"] = system_text
    try:
        message = await _create(params, timeout_seconds=timeout_seconds, deadline=timeout_seconds)
    except RuntimeError as exc:
        raise RoutedClaudeError(str(exc)) from exc
    if message.stop_reason == "max_tokens":
        raise RoutedClaudeError(f"Claude reply cut off at max_tokens={params['max_tokens']}")
    text = _reply_text(message)
    if json_output:
        text = _extract_json(text) or text  # no JSON: the site's own parser reports it
    return SimpleNamespace(text=text, usage_metadata=None, provider="anthropic")
