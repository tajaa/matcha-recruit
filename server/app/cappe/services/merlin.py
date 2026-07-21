"""Merlin — AI chat editing for the Cappe page builder.

The user chats ("make the hero darker and add an FAQ"); Gemini returns a short
JSON envelope `{message, ops}` where each op is one of a small, whitelisted
set (the `MERLIN_OPS` registry in `merlin_ops.py`; catalog data in
`merlin_catalog.py`). The client applies ops to its own in-memory editor state
(auto-apply + undo — nothing persists here); this module's job is to build the
prompt and run the Gemini turn, delegating op validation to `merlin_ops`.

Validation philosophy — skip-and-report, never reject a whole turn: one bad
op (stale block id, hallucinated field) drops that op into `rejected` with a
reason; every other valid op in the same turn still applies. This mirrors the
`_call_with_retry` pattern in `ir_analysis.py` but is deliberately softer,
since a partially-useful edit is better than none for a chat UI.

Never raises for "the model said something weird" — only `RateLimitExceeded`
propagates (the route turns that into 429). Anything else degrades to a
message-only response with empty ops.
"""
import asyncio
import json
import logging
import re
from typing import Any, Optional

from google.genai import types

from ...config import get_settings
from ...core.services.genai_client import get_genai_client
from ...core.services.rate_limiter import GeminiRateLimiter
from .design_gate import is_premium_plan
from .merlin_catalog import (
    BLOCK_FIELDS,
    BLOCK_LABELS,
    BLOCK_TYPES,
    DEFAULT_MODEL_TIER,
    DESIGN_GROUPS,
    FREE_PLAN_TIERS,
    MODEL_TIERS,
    SELECT_OPTIONS,
)
# Op validation lives in the registry module now; re-exported here so existing
# importers (routes, tests) keep resolving `merlin.validate_ops`.
from .merlin_ops import MERLIN_OPS, OP_NAMES, validate_ops  # noqa: F401

logger = logging.getLogger(__name__)

# Per-turn call timeout now lives on ModelTier (merlin_catalog.py) — a
# thinking tier is slower than a non-thinking one, so it isn't one flat
# constant anymore. Same order of magnitude as ir_analysis.GEMINI_CALL_TIMEOUT.
# A theme swap replaces brand/fonts/radius/mode site-wide, so it only fires when
# the user actually asked for one. Without this the model reached for `preset`
# on a request that never mentioned themes and nuked the site's look.
_THEME_INTENT_RE = re.compile(r"\b(theme|preset|palette|colou?r scheme|restyle|redesign)\b", re.I)
_MAX_HISTORY_TURNS = 10

_rate_limiter: Optional[GeminiRateLimiter] = None


def _get_rate_limiter() -> GeminiRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GeminiRateLimiter()
    return _rate_limiter


def resolve_model_tier(requested: Any, plan: Any) -> str:
    """Pick the model tier for this turn, clamped to what the plan allows.

    Clamps rather than raises (same call as matcha_work_ai._get_model): an
    unknown tier or one above the caller's plan quietly degrades to `lite`, so
    a stale client or a hand-rolled request can't 403 the whole turn. The panel
    already hides the locked tiers, so a clamp here means something odd
    happened, not that the user did something wrong.
    """
    tier = requested if isinstance(requested, str) and requested in MODEL_TIERS else DEFAULT_MODEL_TIER
    if not is_premium_plan(plan) and tier not in FREE_PLAN_TIERS:
        return DEFAULT_MODEL_TIER
    return tier


def _parse_json_response(text: str) -> dict[str, Any]:
    """Strip markdown fences (Gemini sometimes wraps JSON in ```json) and parse."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _catalog_text() -> str:
    """Per-type field listing with kinds + select options, so the model knows
    both what it may set and what shape the value must take."""
    lines = []
    for btype in sorted(BLOCK_TYPES):
        fields = BLOCK_FIELDS[btype]
        if not fields:
            lines.append(f"- {btype} ({BLOCK_LABELS.get(btype, btype)}): (structural — use canvas_* ops, not set_field)")
            continue
        opts = SELECT_OPTIONS.get(btype, {})
        rendered = []
        for name in sorted(fields):
            kind = fields[name]
            allowed = opts.get(name)
            rendered.append(f"{name}:{kind}({'|'.join(sorted(allowed))})" if allowed else f"{name}:{kind}")
        lines.append(f"- {btype} ({BLOCK_LABELS.get(btype, btype)}): {', '.join(rendered)}")
    return "\n".join(lines)


_SYSTEM_PROMPT = """You are Merlin, an AI that edits a website page by emitting a strict JSON \
plan. You do not write prose explanations of code — you output ONLY a JSON object shaped exactly:

{"message": "<one short sentence for the user, plain language>", "ops": [<op>, ...]}"""
# NOTE: _SYSTEM_PROMPT (and every generated fragment below) is full of literal
# JSON braces — never run str.format() or an f-string over any of them
# (`{"message"...}` parses as a replacement field and raises KeyError). They are
# concatenated in _build_prompt.

# General rules that apply regardless of which op is used. The op-SPECIFIC rules
# (animation lives in set_design, preset-swap gating, canvas grid geometry, mode
# values) are carried on the MERLIN_OPS registry entries and generated by
# `_rules_text` — a rule can't drift from the op it governs.
_GENERAL_RULES: tuple[str, ...] = (
    'NEVER substitute a different change for the one you were asked to make. If you cannot accomplish the request with the ops above, return an empty "ops" array and say plainly what you can\'t do. Doing something the user did not ask for is far worse than doing nothing.',
    'Your "message" must describe ONLY the ops you actually emitted. Never describe an effect you did not produce.',
    "Change only what was asked. Do not rewrite the user's copy, switch their theme, or restyle sections as a side effect of an unrelated request.",
    'When the user says "this section", "here", or "it", they mean the SELECTED SECTION named below. If nothing is selected and the target is ambiguous, ask which section rather than guessing.',
    'Address blocks and canvas elements ONLY by the "id" values given to you below — never by position/index guessing.',
    "At most 20 ops per turn. Prefer editing an existing block over removing and recreating it.",
    "Never invent a block type or field name outside the catalog below.",
    'If the request is unclear or nothing needs to change, return an empty "ops" array with a clarifying "message".',
    "Output ONLY the JSON object. No markdown fences, no commentary.",
)


def _op_shapes_text() -> str:
    """The "Each op is one of:" block, generated from the MERLIN_OPS registry so
    an op's documented shape can't drift from its validator."""
    return "Each op is one of:\n" + "\n".join(op.prompt_shape for op in MERLIN_OPS if op.prompt_shape)


def _rules_text() -> str:
    """General rules + the op-specific rules carried on the registry entries."""
    lines = list(_GENERAL_RULES)
    for op in MERLIN_OPS:
        lines.extend(op.prompt_rules)
    return "Rules:\n" + "\n".join(f"- {r}" for r in lines)


def _design_catalog_text() -> str:
    """The `_design` surface, so the model knows animation/styling is expressible
    at all. Without this it reaches for whatever it *can* emit — which is how an
    "animate this text" request became a site-wide theme swap."""
    lines = []
    for group in sorted(DESIGN_GROUPS):
        rendered = []
        for key in sorted(DESIGN_GROUPS[group]):
            spec = DESIGN_GROUPS[group][key]
            if isinstance(spec, frozenset):
                rendered.append(f"{key}({'|'.join(sorted(spec))})")
            elif isinstance(spec, tuple):
                rendered.append(f"{key}({spec[0]}-{spec[1]})")
            elif spec == "gradient":
                rendered.append(f'{key}({{"angle":0-360,"stops":["#hex","#hex"(,3rd)]}})')
            else:
                rendered.append(f"{key}:{spec}")
        lines.append(f"- {group}: {', '.join(rendered)}")
    return "\n".join(lines)


def _strip_prompt_noise(block: dict[str, Any]) -> dict[str, Any]:
    """A prompt-only view of one block: drops null/empty-string field values
    and empty `_design` groups — noise that costs tokens on every turn without
    helping the model (an absent key already reads as unset/default, same as
    an explicit null). Pure — returns a new dict; the caller's original block
    (which validate_ops still needs at full fidelity, from the same request
    payload) is untouched."""
    cleaned: dict[str, Any] = {}
    for k, v in block.items():
        if v is None or v == "":
            continue
        if k == "_design" and isinstance(v, dict):
            design = {g: keys for g, keys in v.items() if isinstance(keys, dict) and keys}
            if design:
                cleaned[k] = design
            continue
        cleaned[k] = v
    return cleaned


def _build_prompt(
    *, message: str, history: list[dict[str, Any]], blocks: list[dict[str, Any]],
    theme: dict[str, Any], business_name: Optional[str], business_type: Optional[str],
    feedback: Optional[str], selected_block: Optional[str] = None,
) -> str:
    parts = [
        _SYSTEM_PROMPT,
        _op_shapes_text(),
        _rules_text(),
        "Block catalog (type: allowed fields):\n" + _catalog_text(),
        "Section design catalog for set_design (group: settings):\n" + _design_catalog_text(),
    ]

    if business_name or business_type:
        parts.append(f"Site: {business_name or '(unnamed)'} — {business_type or 'general business'}")

    compact_blocks = [_strip_prompt_noise(b) if isinstance(b, dict) else b for b in blocks]
    parts.append("Current blocks (JSON):\n" + json.dumps(compact_blocks, separators=(",", ":")))
    parts.append("Current theme (JSON):\n" + json.dumps(theme, separators=(",", ":")))

    if selected_block:
        parts.append(
            f"SELECTED SECTION: id={selected_block}. "
            'Resolve "this section" / "here" / "it" to this block.'
        )
    else:
        parts.append(
            "SELECTED SECTION: none. If the user refers to \"this section\" and it is "
            "ambiguous which they mean, ask instead of guessing."
        )

    trimmed = history[-_MAX_HISTORY_TURNS:]
    if trimmed:
        convo = []
        for turn in trimmed:
            if turn.get("role") == "assistant" and turn.get("ops_summary"):
                convo.append(f"assistant: {turn.get('content', '')} [{turn['ops_summary']}]")
            else:
                convo.append(f"{turn.get('role')}: {turn.get('content', '')}")
        parts.append("Conversation so far:\n" + "\n".join(convo))

    if feedback:
        parts.append(f"PREVIOUS ATTEMPT FAILED VALIDATION: {feedback}\nFix and return valid JSON only.")

    parts.append(f"User: {message}")
    return "\n\n".join(parts)


def _rejection_feedback(rejected: list[dict[str, Any]]) -> str:
    reasons = "; ".join(f"{r['op'].get('op', '?')}: {r['reason']}" for r in rejected[:8])
    return f"{len(rejected)} op(s) were invalid — {reasons}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_merlin_turn(
    *, message: str, history: list[dict[str, Any]], blocks: list[dict[str, Any]],
    theme: dict[str, Any], business_name: Optional[str] = None, business_type: Optional[str] = None,
    model_tier: str = DEFAULT_MODEL_TIER, plan: Any = None, selected_block: Optional[str] = None,
) -> dict[str, Any]:
    """Run one Merlin chat turn. Returns `{"message", "ops", "rejected", "tier"}`.

    `model_tier` must already be clamped to the caller's plan (see
    `resolve_model_tier`) — this function trusts it and only falls back to the
    default if it's not a known tier.

    Raises RateLimitExceeded (from core.services.rate_limiter) if the global
    Gemini cost guard is tripped — the caller (route) turns that into a 429.
    Every other failure mode (timeout, bad JSON, Gemini error) is soft-failed
    into a message-only response with no ops, never raised.
    """
    rate_limiter = _get_rate_limiter()
    await rate_limiter.check_limit("cappe_merlin", "chat")  # fail fast, before any Gemini call

    tier = model_tier if model_tier in MODEL_TIERS else DEFAULT_MODEL_TIER
    client = get_genai_client()
    tier_cfg = MODEL_TIERS[tier]
    model = tier_cfg.model
    thinking_cfg = (
        types.ThinkingConfig(thinking_level=tier_cfg.thinking_level)
        if tier_cfg.thinking_level else types.ThinkingConfig(thinking_budget=0)
    )
    premium = is_premium_plan(plan)
    # Did the user actually ask about themes this turn? Gates the site-wide
    # preset swap so it can't ride along on an unrelated request.
    theme_intent = bool(_THEME_INTENT_RE.search(message or ""))

    last_feedback: Optional[str] = None
    final_message = "Sorry, I couldn't process that — try again."
    final_valid: list[dict[str, Any]] = []
    final_rejected: list[dict[str, Any]] = []

    for attempt in range(2):  # one initial attempt + one validation-feedback retry
        if attempt > 0:
            await rate_limiter.check_limit("cappe_merlin", "chat")

        prompt = _build_prompt(
            message=message, history=history, blocks=blocks, theme=theme,
            business_name=business_name, business_type=business_type, feedback=last_feedback,
            selected_block=selected_block,
        )
        # Everything from the API call through op validation sits inside the
        # try: a hallucinated payload shape must degrade to a retry or an
        # empty-ops response, never escape as a 500 (the never-raises contract).
        try:
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json", thinking_config=thinking_cfg,
                        ),
                    ),
                    timeout=tier_cfg.timeout,
                )
            finally:
                # Record even on timeout — the request was issued and billed, so
                # skipping it here lets a slow model burn quota invisibly.
                await rate_limiter.record_call("cappe_merlin", tier)
            payload = _parse_json_response(getattr(response, "text", None) or "")
            if not isinstance(payload, dict):
                # Valid JSON, wrong shape (a bare array or string) — `.get` on it
                # would be an AttributeError.
                raise ValueError("payload was not a JSON object")

            raw_message = str(payload.get("message") or "").strip() or "Done."
            raw_ops = payload.get("ops")
            raw_ops = raw_ops if isinstance(raw_ops, list) else []
            valid, rejected = validate_ops(
                raw_ops, blocks, premium=premium, theme_intent=theme_intent,
            )
        except asyncio.TimeoutError:
            logger.warning("Merlin call timed out (attempt %d/2)", attempt + 1)
            last_feedback = f"the previous attempt timed out after {tier_cfg.timeout}s — respond more concisely"
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Merlin returned unusable JSON (attempt %d/2): %s", attempt + 1, exc)
            last_feedback = "the previous attempt was not valid JSON — return ONLY the JSON object, no markdown"
            continue
        except Exception as exc:  # noqa: BLE001 — never-raises contract past rate limiting
            logger.warning("Merlin call failed (attempt %d/2): %s", attempt + 1, exc)
            break

        final_message, final_valid, final_rejected = raw_message, valid, rejected

        if raw_ops and not valid and rejected and attempt == 0:
            # Every op failed validation — worth one retry with the reasons.
            last_feedback = _rejection_feedback(rejected)
            continue
        break

    return {"message": final_message, "ops": final_valid, "rejected": final_rejected, "tier": tier}
