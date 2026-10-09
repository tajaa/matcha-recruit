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
import logging
import time
from typing import Any

import anthropic
from google.genai import types
from PIL import Image, ImageOps

from app.core.services.ai_usage import record_anthropic_response
from app.core.services.anthropic_messages import gemini_contents_to_messages, get_async_client, request_extras
from app.core.services.rate_limiter import RateLimitExceeded, get_rate_limiter

logger = logging.getLogger(__name__)

# Document turns (a handbook, a deck) can be long. Non-streaming, but the
# explicit timeout below is what bounds the call.
_MAX_TOKENS = 32_000
_EFFORT = {"none": "low", "low": "medium", "high": "high"}
_JSON_ONLY = (
    "Respond with exactly one JSON object in the shape described above and "
    "nothing else: no prose before or after it, and no Markdown code fences."
)


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
