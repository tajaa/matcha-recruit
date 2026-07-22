"""Picks Merlin's model tier per request, so the user doesn't have to.

The three tiers are a real trade: `lite` (flash-lite, no thinking, single-shot)
answers a copy tweak in a second or two; `max` (flash, high thinking, the agent
loop with screenshots) is what a "make this look designed" ask actually needs
and costs an order of magnitude more. Asking a small-business owner to pick is
asking them to guess at model economics, and the default (`lite`) is wrong for
exactly the requests that made them reach for AI.

So `auto` is the default and this module resolves it: a heuristic handles the
obvious cases for free, and anything ambiguous costs one flash-lite
classification call (~6s ceiling, minimal thinking) before the real turn.

Two rules keep it honest:
  - **Free plans never reach the classifier.** `auto` clamps to `lite` on the
    plan gate first, so a free turn adds no call it can't use the answer for.
  - **Failure routes UP, not down.** A classifier timeout falling back to
    `lite` would silently give the cheap answer to the request that needed the
    expensive one — the exact failure `auto` exists to prevent.
"""
import asyncio
import json
import logging
import re
from typing import Any, Optional

from google.genai import types

from ...core.services.genai_client import get_genai_client
from ...core.services.rate_limiter import GeminiRateLimiter, RateLimitExceeded
from .design_gate import is_premium_plan
from .merlin_catalog import DEFAULT_MODEL_TIER, MODEL_TIERS

logger = logging.getLogger(__name__)

AUTO_TIER = "auto"
# What a complexity verdict maps to.
_COMPLEXITY_TIERS = {"trivial": "lite", "standard": "regular", "complex": "max"}
_FALLBACK_TIER = "regular"

_CLASSIFIER_MODEL = "gemini-3.5-flash-lite"
_CLASSIFIER_TIMEOUT = 6.0

# Heuristic pre-filter. A short, imperative edit against a section the user has
# already selected is a copy/field tweak — "change this to Book Now", "make it
# say 8am". Those don't need a classifier call OR a screenshot loop.
_TRIVIAL_WORD_MAX = 6
_TRIVIAL_HINTS = re.compile(
    r"\b(typo|spelling|rename|capitali[sz]e|shorter|longer|delete|remove)\b", re.I
)
# Words that reliably mean "judge this visually" — worth `max` without asking.
_COMPLEX_HINTS = re.compile(
    r"\b(redesign|restyle|revamp|overhaul|professional|premium|polished?|designed|"
    r"modern|beautiful|stunning|cohesive|rework|whole page|entire (page|site))\b",
    re.I,
)

_CLASSIFIER_PROMPT = """Classify how much work a website-editing request needs. Answer ONLY with JSON:
{"complexity": "trivial" | "standard" | "complex"}

- trivial: changing words, a single field, one obvious setting. No judgment about how it looks.
- standard: a concrete structural or styling change — add a section, change a color, adjust spacing.
- complex: anything requiring visual judgment or coordinated changes across a section or page — \
"make it look professional", "this feels cramped", "match the vibe of the rest of the site", \
a redesign, or a request that names a problem rather than a fix.

When unsure, answer "complex" — an overworked answer is recoverable, an underworked one is not."""


def _heuristic(message: str, has_selected_block: bool) -> Optional[str]:
    """A free verdict where one is obvious, else None (ask the classifier)."""
    text = (message or "").strip()
    if not text:
        return DEFAULT_MODEL_TIER
    if _COMPLEX_HINTS.search(text):
        return "max"
    words = text.split()
    if len(words) <= _TRIVIAL_WORD_MAX and (has_selected_block or _TRIVIAL_HINTS.search(text)):
        return "lite"
    return None


async def _classify(message: str, history_tail: Optional[str]) -> Optional[str]:
    """One flash-lite call. None on any failure — the caller decides the
    fallback (which is deliberately not the cheap tier)."""
    prompt = _CLASSIFIER_PROMPT
    if history_tail:
        prompt += f"\n\nEarlier in this conversation:\n{history_tail}"
    prompt += f"\n\nRequest: {message}"

    limiter = GeminiRateLimiter()
    try:
        await limiter.check_limit("cappe_merlin", "route")
    except RateLimitExceeded:
        # The budget is spent; don't burn the turn's own headroom on routing.
        return None

    try:
        client = get_genai_client()
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=_CLASSIFIER_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                ),
            ),
            timeout=_CLASSIFIER_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 — routing must never fail a turn
        logger.info("Merlin tier classification failed: %s", exc)
        return None
    finally:
        try:
            await limiter.record_call("cappe_merlin", "lite")
        except Exception:  # noqa: BLE001
            pass

    try:
        payload = json.loads((getattr(response, "text", None) or "").strip())
        verdict = payload.get("complexity") if isinstance(payload, dict) else None
    except (json.JSONDecodeError, AttributeError):
        return None
    return _COMPLEXITY_TIERS.get(verdict)


async def route_tier(
    requested: Any,
    plan: Any,
    *,
    message: str = "",
    has_selected_block: bool = False,
    history_tail: Optional[str] = None,
) -> tuple[str, bool]:
    """Resolve the tier for one turn. Returns `(tier, was_routed)`.

    `was_routed` drives the panel's "Auto → Max" badge — without it the user
    can't tell whether Auto is working or silently pinning one tier.

    A pinned (non-auto) tier is clamped exactly as before, so this is safe to
    put in front of every request.
    """
    from .merlin import resolve_model_tier

    if requested != AUTO_TIER:
        return resolve_model_tier(requested, plan), False

    # Free plans get lite regardless, so don't pay for a verdict we'd discard.
    if not is_premium_plan(plan):
        return DEFAULT_MODEL_TIER, False

    heuristic = _heuristic(message, has_selected_block)
    if heuristic is not None:
        return heuristic, True

    classified = await _classify(message, history_tail)
    tier = classified or _FALLBACK_TIER
    return (tier if tier in MODEL_TIERS else _FALLBACK_TIER), True
