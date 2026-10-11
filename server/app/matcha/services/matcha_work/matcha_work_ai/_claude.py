"""Claude for the skill engine's one structured-JSON call — what a Claude
pick (Matcha Work, Espresso) and the admin's Claude model run on.

The request is laid out by `_claude_thread` for prompt caching (instructions,
thread context and the conversation are cached; the per-turn document and
date ride a trailing system message). The output is the same reply text the
provider's shared parser reads, plus a `token_usage` dict.

Where Gemini needs differ:

- **Caching.** Gemini creates a server-side cache object per company and
  prompt hash; Messages caches by prefix — see `_claude_thread`.
- **Structured output.** `output_config.format` holds the engine's reply
  schema (`ENGINE_SCHEMA`), so the reply is always one parseable object.
  `updates` travels as a JSON string and is turned back into an object
  before the shared parser sees it. A model that rejects the schema is
  remembered and gets the prose JSON instruction instead.
- **Thinking.** Adaptive thinking (Sonnet 5.5 rejects `disabled`) at one
  effort per thread (`_claude_thread.thread_effort`): an effort change
  invalidates the cached conversation.
- **Stop reasons.** A refusal becomes a short plain reply (Sonnet also has
  the server-side fallback); a reply cut off at `max_tokens` keeps what was
  written, decoded from the partial JSON.
- **Images.** Messages takes JPEG/PNG/GIF/WebP only, at most 10 MB base64
  each, 32 MB per request, and 2000 px a side once a request holds more than
  20 images; Gemini took HEIC/BMP/TIFF and bigger files. `claude_turn_contents`
  re-encodes what Pillow can read and sends the turn to Gemini when it can't,
  so an image is never silently dropped and never 400s every later turn.
- **Spend.** Each turn checks and records the `anthropic` rate-limit bucket
  (`ANTHROPIC_HOURLY_LIMIT` / `ANTHROPIC_DAILY_LIMIT`). A full bucket runs the
  turn on Gemini instead of failing it.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import anthropic
from google.genai import types
from PIL import Image, ImageOps

from app.core.services.ai_usage import record_anthropic_response
from app.core.services.anthropic_messages import gemini_contents_to_messages, get_async_client, request_extras
from app.core.services.rate_limiter import RateLimitExceeded, get_rate_limiter
from app.matcha.services.billing.model_pricing import claude_turn_cost

from ._claude_thread import ENGINE_SCHEMA, ThreadRequest, engine_reply_text
from ._stream import partial_reply

logger = logging.getLogger(__name__)

# Document turns (a handbook, a deck) can be long. Non-streaming, but the
# explicit timeout below is what bounds the call.
_MAX_TOKENS = 32_000
REFUSAL_REPLY = "I can't help with that one."
CUT_OFF_NOTE = "\n\n(This answer was cut off before it finished. Ask me to continue.)"

# Models this process found to reject the trailing `role: "system"` message,
# or the reply schema. The next call skips that feature instead of failing
# twice; a restart tries again.
_NO_SYSTEM_ROLE: set[str] = set()
_NO_SCHEMA: set[str] = set()


_RATE_SERVICE = "matcha_work"
_RATE_ENDPOINT = "skill_engine"

# Image limits on the Claude API (build-with-claude/vision). Haiku/Sonnet 5.5
# downscale past 2576 px on the long edge anyway, so resizing there loses
# nothing; past 20 images a request must stay under 2000 px a side.
_SUPPORTED_IMAGE_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif", "WEBP": "image/webp"}
_LONG_EDGE = 2576
_MANY_IMAGES = 20
_MANY_IMAGES_LONG_EDGE = 2000
# Re-encode anything over 5 MB base64 (the documented cap is 10 MB), and keep
# the whole request's images well under the 32 MB request limit.
_MAX_IMAGE_B64 = 5 * 1024 * 1024
_MAX_TOTAL_IMAGE_B64 = 24 * 1024 * 1024
_EXIF_ORIENTATION = 0x0112


def _b64_len(n: int) -> int:
    return 4 * ((n + 2) // 3)


def normalize_image(data: bytes, long_edge: int = _LONG_EDGE) -> tuple[bytes, str] | None:
    """Image bytes → (bytes, media type) Messages accepts, or None when Pillow
    can't read them (HEIC without a codec, corrupt data).

    A supported format already within size and dimensions, and with no EXIF
    rotation (Claude ignores metadata, so a phone photo would arrive
    sideways), passes through untouched, with the media type taken from the
    bytes rather than the declared one (a mismatch is a 400). Anything else
    is EXIF-rotated,
    shrunk to `long_edge`, and re-encoded: PNG when it has transparency and
    stays under the size cap, JPEG otherwise.
    """
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            width, height = probe.size
            rotated = probe.getexif().get(_EXIF_ORIENTATION, 1) != 1
    except Exception:
        return None
    mime = _SUPPORTED_IMAGE_TYPES.get(fmt)
    if mime and not rotated and max(width, height) <= long_edge and _b64_len(len(data)) <= _MAX_IMAGE_B64:
        return data, mime
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.seek(0)  # first frame of an animation, as Claude would use
            img = ImageOps.exif_transpose(img)
            img.thumbnail((long_edge, long_edge))
            has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
            if has_alpha:
                out = io.BytesIO()
                img.convert("RGBA").save(out, format="PNG", optimize=True)
                if _b64_len(out.tell()) <= _MAX_IMAGE_B64:
                    return out.getvalue(), "image/png"
                flat = Image.new("RGB", img.size, (255, 255, 255))
                flat.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
                img = flat
            out = io.BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=85)
            if _b64_len(out.tell()) > _MAX_IMAGE_B64:
                return None
            return out.getvalue(), "image/jpeg"
    except Exception:
        return None


def _normalize_contents(contents: list[Any]) -> list[Any] | None:
    """The turn's Gemini `contents` with every user image made Claude-ready,
    or None when one can't be (the turn then runs on Gemini). Model-turn
    images are left alone: `to_messages` drops them anyway."""
    images = sum(
        1
        for content in contents
        if getattr(content, "role", "user") != "model"
        for part in getattr(content, "parts", None) or []
        if getattr(getattr(part, "inline_data", None), "data", None)
    )
    if not images:
        return contents
    long_edge = _MANY_IMAGES_LONG_EDGE if images > _MANY_IMAGES else _LONG_EDGE
    total = 0
    normalized: list[Any] = []
    for content in contents:
        if getattr(content, "role", "user") == "model":
            normalized.append(content)
            continue
        parts: list[Any] = []
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            if not data:
                parts.append(part)
                continue
            fixed = normalize_image(data, long_edge)
            if fixed is None:
                logger.info("skill engine: unreadable %s image for Claude; turn runs on Gemini",
                            getattr(inline, "mime_type", None))
                return None
            total += _b64_len(len(fixed[0]))
            if total > _MAX_TOTAL_IMAGE_B64:
                logger.info("skill engine: %s images exceed Claude's request budget; turn runs on Gemini", images)
                return None
            parts.append(types.Part.from_bytes(data=fixed[0], mime_type=fixed[1]))
        normalized.append(types.Content(role=getattr(content, "role", "user"), parts=parts))
    return normalized


async def claude_turn_contents(contents: list[Any]) -> list[Any] | None:
    """The contents a Claude turn should send, or None to run this turn on
    Gemini: the `anthropic` rate-limit bucket is full, or an image can't be
    made Claude-ready. Never raises — a limiter outage lets the turn through
    rather than taking chat down."""
    try:
        await get_rate_limiter("anthropic").check_limit(_RATE_SERVICE, _RATE_ENDPOINT)
    except RateLimitExceeded as exc:
        logger.warning("skill engine: %s; turn runs on Gemini", exc)
        return None
    except Exception:
        logger.warning("skill engine: anthropic rate-limit check failed; allowing the turn", exc_info=True)
    return await asyncio.to_thread(_normalize_contents, contents)


async def record_claude_call() -> None:
    """Count one skill-engine call in the `anthropic` bucket. Never raises."""
    try:
        await get_rate_limiter("anthropic").record_call(_RATE_SERVICE, _RATE_ENDPOINT)
    except Exception:
        logger.warning("skill engine: could not record an anthropic call", exc_info=True)


def to_messages(contents: list[Any]) -> list[dict[str, Any]]:
    """The provider's Gemini `contents` → Messages turns, via the one shared
    translator (`anthropic_messages.gemini_contents_to_messages`)."""
    return gemini_contents_to_messages(contents)


def _usage(message: Any, model: str) -> dict[str, Any] | None:
    """Token usage in the engine's shape. Cache reads are left out of
    `prompt_tokens` and `total_tokens`, so they don't count against a
    tenant's quota or budget (Gemini's cached tokens don't either); they are
    in `cached_tokens`. `cost_dollars` is the turn's real price
    (`claude_turn_cost`: reads at the cached rate, writes at 1.25x / 2x)."""
    usage = getattr(message, "usage", None)
    if usage is None:
        return None
    uncached = getattr(usage, "input_tokens", None) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", None) or 0
    by_ttl = getattr(usage, "cache_creation", None)
    cache_write_1h = (getattr(by_ttl, "ephemeral_1h_input_tokens", None) or 0) if by_ttl is not None else 0
    completion = getattr(usage, "output_tokens", None) or 0
    prompt = uncached + cache_write
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "cached_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "cache_write_1h_tokens": cache_write_1h,
        "cost_dollars": float(claude_turn_cost(
            model, input_tokens=uncached, cache_read_tokens=cache_read, cache_write_tokens=cache_write,
            cache_write_1h_tokens=cache_write_1h, output_tokens=completion,
        )),
        "estimated": False,
        "model": model,
    }


class ClaudeCallFailed(RuntimeError):
    """The Anthropic call did not produce a reply (after its ledger row)."""


@dataclass
class ClaudeResult:
    text: str  # the engine reply JSON for `provider._parse_engine_reply`
    usage: dict[str, Any] | None
    stop_reason: str | None
    structured: bool


def request_params(request: ThreadRequest, *, model: str, effort: str, system_role: bool,
                   structured: bool) -> dict[str, Any]:
    """The Messages request for one thread turn."""
    output_config: dict[str, Any] = {"effort": effort}
    if structured:
        output_config["format"] = {"type": "json_schema", "schema": ENGINE_SCHEMA}
    return {
        "model": model,
        "max_tokens": _MAX_TOKENS,
        "system": request.system(structured=structured),
        "messages": request.messages(system_role=system_role),
        "thinking": {"type": "adaptive"},
        "output_config": output_config,
        **request_extras(model),
    }


def _rejected_feature(exc: anthropic.BadRequestError, *, system_role: bool, structured: bool) -> str | None:
    """Which optional feature a 400 is about, if it is about one."""
    detail = str(exc).lower()
    if system_role and "role" in detail and "system" in detail:
        return "system_role"
    if structured and any(word in detail for word in ("output_config", "json_schema", "schema", "format")):
        return "schema"
    return None


def reply_text(raw: str, *, stop_reason: str | None, structured: bool, stop_details: Any = None) -> str:
    """The model's text → the engine reply JSON, by why it stopped."""
    if stop_reason == "refusal":
        logger.info("skill engine: Claude declined (%s)", getattr(stop_details, "category", None))
        return json.dumps({"mode": "refuse", "skill": "none", "operation": "none", "reply": REFUSAL_REPLY})
    text = engine_reply_text(raw) if structured else raw
    if stop_reason == "max_tokens":
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("reply"), str):
            parsed["reply"] = parsed["reply"].rstrip() + CUT_OFF_NOTE
            return json.dumps(parsed)
        written = partial_reply(raw) or ""
        return json.dumps({"mode": "general", "reply": written.rstrip() + CUT_OFF_NOTE})

    return text


async def call_claude_thread(
    request: ThreadRequest, *, model: str, effort: str, timeout_seconds: float,
) -> ClaudeResult:
    """One thread turn on Claude → ClaudeResult.

    Raises ClaudeCallFailed on an API failure, after writing the ledger row;
    the provider then runs the turn on Gemini. A 400 naming the trailing
    system message or the schema is retried once without it, and the model
    is remembered."""
    system_role = model not in _NO_SYSTEM_ROLE
    structured = model not in _NO_SCHEMA
    client = get_async_client().with_options(timeout=timeout_seconds)
    for _attempt in range(3):
        params = request_params(request, model=model, effort=effort, system_role=system_role, structured=structured)
        started = time.monotonic()
        try:
            message = await client.beta.messages.create(**params)
        except anthropic.BadRequestError as exc:
            await record_anthropic_response(
                model=model, latency_ms=int((time.monotonic() - started) * 1000), error=str(exc)[:500], status="error",
            )
            feature = _rejected_feature(exc, system_role=system_role, structured=structured)
            if feature == "system_role":
                logger.warning("skill engine: %s rejects a mid-conversation system message; using a user block", model)
                _NO_SYSTEM_ROLE.add(model)
                system_role = False
                continue
            if feature == "schema":
                logger.warning("skill engine: %s rejects the reply schema; using the JSON instruction", model)
                _NO_SCHEMA.add(model)
                structured = False
                continue
            raise ClaudeCallFailed(f"Anthropic Messages request failed: {exc}") from exc
        except anthropic.APIError as exc:
            await record_anthropic_response(
                model=model, latency_ms=int((time.monotonic() - started) * 1000), error=str(exc)[:500],
                status="timeout" if isinstance(exc, anthropic.APITimeoutError) else "error",
            )
            raise ClaudeCallFailed(f"Anthropic Messages request failed: {exc}") from exc
        await record_anthropic_response(
            model=model, latency_ms=int((time.monotonic() - started) * 1000),
            message=message.model_dump(mode="json"),
        )
        raw = "\n".join(block.text for block in message.content if block.type == "text").strip()
        return ClaudeResult(
            text=reply_text(raw, stop_reason=message.stop_reason, structured=structured,
                            stop_details=getattr(message, "stop_details", None)),
            usage=_usage(message, model),
            stop_reason=message.stop_reason,
            structured=structured,
        )
    raise ClaudeCallFailed("Anthropic Messages request kept rejecting the request")


@dataclass
class ClaudeTurnRef:
    """What a finished Claude turn ran with, so the compaction that follows
    can re-send its exact prefix and read it from cache."""

    request: ThreadRequest
    model: str
    effort: str
    structured: bool


SUMMARY_INSTRUCTION = (
    "Write a new conversation summary to replace the one in THREAD CONTEXT (if any): what this "
    "conversation has established so far, for continuity in later turns. Include key decisions, the "
    "document or task being worked on, specific values, names and dates, the user's stated preferences, "
    "and where the work stands. No greetings or filler, at most 250 words. Put it in `reply`, with mode "
    "\"general\", skill \"none\", operation \"none\" and updates_json \"{}\"."
)
_SUMMARY_MAX_TOKENS = 8_000


async def summarize_thread(
    turn: ClaudeTurnRef, assistant_reply: str, *, timeout_seconds: float = 60,
) -> tuple[str | None, dict[str, Any] | None]:
    """The compaction summary for a Claude thread, written by the same model
    on the turn's own request: same system, history up to the latest user
    turn (its breakpoint), same thinking, effort and format, so everything up
    to there is a cache read. Then the reply the turn produced and the
    summary request. Returns (summary, token_usage); (None, ...) when nothing
    usable came back. Never raises."""
    output_config: dict[str, Any] = {"effort": turn.effort}
    if turn.structured:
        output_config["format"] = {"type": "json_schema", "schema": ENGINE_SCHEMA}
    params = {
        "model": turn.model,
        "max_tokens": _SUMMARY_MAX_TOKENS,
        "system": turn.request.system(structured=turn.structured),
        "messages": [
            *turn.request.history,
            {"role": "assistant", "content": [{"type": "text", "text": (assistant_reply or "").strip() or "(no reply)"}]},
            {"role": "user", "content": [{"type": "text", "text": SUMMARY_INSTRUCTION}]},
        ],
        "thinking": {"type": "adaptive"},
        "output_config": output_config,
        **request_extras(turn.model),
    }
    await record_claude_call()
    started = time.monotonic()
    try:
        message = await get_async_client().with_options(timeout=timeout_seconds).beta.messages.create(**params)
    except anthropic.APIError as exc:
        await record_anthropic_response(
            model=turn.model, latency_ms=int((time.monotonic() - started) * 1000), error=str(exc)[:500],
            status="timeout" if isinstance(exc, anthropic.APITimeoutError) else "error",
        )
        logger.warning("thread compaction on Claude failed: %s", exc)
        return None, None
    except Exception:
        logger.warning("thread compaction on Claude failed", exc_info=True)
        return None, None
    await record_anthropic_response(
        model=turn.model, latency_ms=int((time.monotonic() - started) * 1000),
        message=message.model_dump(mode="json"),
    )
    usage = _usage(message, turn.model)
    if message.stop_reason == "refusal":
        return None, usage
    raw = "\n".join(block.text for block in message.content if block.type == "text").strip()
    summary = None
    try:
        parsed = json.loads(engine_reply_text(raw) if turn.structured else raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("reply"), str):
            summary = parsed["reply"]
    except ValueError:
        summary = partial_reply(raw)
    summary = (summary or "").strip()
    return (summary or None), usage
