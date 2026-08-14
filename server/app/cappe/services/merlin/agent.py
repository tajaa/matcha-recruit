"""Merlin's agent loop — the version of Merlin that can SEE its own work.

The single-shot path (`services/merlin/turn.py`) asks Gemini for an op plan and
returns it. That model has never looked at the page: it reasons over a JSON
block tree and a theme dict, which is exactly how the 2026-07-21 incidents
happened (a dark-on-dark gradient that rendered invisible; a "make it look
designed" request that painted a bright wireframe grid over a section). Both
were defensible in JSON and obviously wrong on screen.

This module closes that loop. Gemini gets five tools and iterates:

    apply_ops        → validate + fold onto a WORKING COPY of the snapshot
    render_screenshot→ render that copy to HTML, screenshot it, hand back the PNG
    inspect_block    → full-fidelity JSON for one block (the prompt is compacted)
    generate_image   → generate (optionally from a user attachment), fold as a
                        set_field (or, for a section background, the
                        set_design bg.type/bg.image pair), hand back the PNG
                        so the model can judge it
    finish           → stop, with the message shown to the user

Nothing here writes a page. The working copy is throwaway; what returns to the
client is the ordered list of validated ops, which the client applies to live
editor state exactly as it always has (one undo step, saved on Save). The
client remains the source of truth — the server only borrows a copy to look at.

Bounds are per tier and hard (`_BOUNDS`): model calls, screenshots, and wall
clock. Hitting one force-finishes with whatever ops validated so far rather
than failing — a partial improvement beats an error, same philosophy as
`validate_ops`' skip-and-report.

Contract with the route: this is an async generator of SSE-shaped dicts. It
raises only `RateLimitExceeded` (the route turns that into a 429 frame); every
other failure degrades to an `error` frame followed by a `result` frame
carrying whatever was accomplished.
"""
import asyncio
import json
import logging
import secrets
import time
from typing import Any, AsyncIterator, Optional

from fastapi import HTTPException
from google.genai import types

from ....core.services.ai_usage import feature_scope
from ....core.services.genai_client import get_genai_client
from ....core.services.rate_limiter import GeminiRateLimiter, RateLimitExceeded
from ....core.services.storage import get_storage
from ..browser_pool import SHOT_EXT, SHOT_MIME
from ..design_gate import is_premium_plan
from .. import image_quota
from .turn import (
    DEFAULT_MODEL_TIER,
    build_selection_prompt_line,
    build_shared_prompt_sections,
    has_theme_intent,
    strip_prompt_noise,
)
from .apply import apply_ops
from .attachments import caption_lines
from .catalog import (
    AI_ASPECT_RATIOS,
    AI_IMAGE_PROMPT_MAX,
    AI_IMAGE_SIZE_COST_ESTIMATE,
    AI_IMAGE_SIZES,
    BLOCK_LABELS,
    DEFAULT_AI_IMAGE_SIZE,
    MODEL_TIERS,
)
from .loop_control import NoProgressGuard, ToolObservation, TurnTokenBudget, estimate_prompt_tokens
from .ops import image_field_error, image_fields, validate_ops

logger = logging.getLogger(__name__)

# Tiers that get the loop at all. Lite stays single-shot: the loop costs several
# model calls plus screenshots per turn, which is not a free-plan taste.
AGENT_TIERS: frozenset[str] = frozenset({"regular", "max"})


class _Bounds:
    __slots__ = ("model_calls", "screenshots", "wall_clock", "prompt_tokens", "total_tokens")

    def __init__(
        self,
        model_calls: int,
        screenshots: int,
        wall_clock: float,
        prompt_tokens: int,
        total_tokens: int,
    ):
        self.model_calls = model_calls
        self.screenshots = screenshots
        self.wall_clock = wall_clock
        self.prompt_tokens = prompt_tokens
        self.total_tokens = total_tokens


# `max` buys depth, not a different model (see MODEL_TIERS — both are
# gemini-3.7-flash; max thinks harder). Wall clock is the real ceiling: the user
# is watching an SSE stream.
_BOUNDS: dict[str, _Bounds] = {
    "regular": _Bounds(model_calls=6, screenshots=3, wall_clock=120.0, prompt_tokens=300_000, total_tokens=375_000),
    "max": _Bounds(model_calls=10, screenshots=5, wall_clock=240.0, prompt_tokens=500_000, total_tokens=625_000),
}

# One model call's ceiling. Below the wall-clock bound so a single hung call
# can't consume the whole turn.
_CALL_TIMEOUT = 75.0

# MESSAGES, not turns — matches merlin/store.py's HISTORY_MESSAGES / merlin/turn.py's
# own constant of the same corrected name (see that file's comment: named
# _MAX_HISTORY_TURNS at 10 while already meaning messages, this slice never
# actually trimmed anything since the store query already capped there first).
_MAX_HISTORY_MESSAGES = 20

# `MERLIN_OPS`' MAX_OPS_PER_TURN (merlin/ops.py) caps a single apply_ops CALL —
# the single-shot path's only call. The agent loop can call apply_ops several
# times in one turn (fix, screenshot, fix again), and op_log accumulates
# across all of them uncapped — a `max` turn could legitimately reach ~180 ops
# in one client-side undo step while the prompt tells the model "at most 20".
# This is the actual per-TURN ceiling; comfortably above one call's cap so a
# normal multi-fix turn never bumps it, but low enough that a runaway turn
# still force-finishes instead of handing the client a page-sized diff.
_MAX_TURN_OPS = 60

# Screenshots pile up as image Parts in `contents` and are re-sent whole on
# EVERY later model call — a `max` turn's 5th shot means the 6th-10th calls
# each pay for 5 images even though only the newest one is relevant to what
# the model is judging right now. Keep just the most recent.
_KEEP_RECENT_SHOTS = 1
_STALE_SHOT_NOTE = "[an earlier screenshot was here — judge from the most recent one below]"
_STALE_ATTACHMENT_NOTE = "[the user's reference images were available for planning; use attachment_index to reference them for image generation]"


# ---------------------------------------------------------------------------
# Tool declarations
# ---------------------------------------------------------------------------

def _tool_declarations() -> list[types.FunctionDeclaration]:
    """The loop's vocabulary. `apply_ops` deliberately takes the ops array as a
    JSON STRING rather than a typed array: the op union is wide and
    heterogeneous (13 shapes, arbitrary `value` types), and forcing it through a
    function-calling schema would flatten exactly the fields `validate_ops`
    exists to check. The prompt carries the real op shapes, same as single-shot.
    """
    return [
        types.FunctionDeclaration(
            name="apply_ops",
            description=(
                "Apply a batch of edit ops to the page and get back, per op, whether it "
                "was valid and what it changed. Ops that fail validation are reported "
                "with a reason and simply not applied — fix and retry those. Call this "
                "before render_screenshot; the screenshot shows the result of every op "
                "applied so far this turn."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "ops": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "A JSON array of op objects, using exactly the op shapes "
                            "given in the instructions. Example: "
                            '[{"op":"set_design","block":"b1","group":"bg","key":"color","value":"surface"}]'
                        ),
                    ),
                },
                required=["ops"],
            ),
        ),
        types.FunctionDeclaration(
            name="render_screenshot",
            description=(
                "Render the page AS IT NOW STANDS (original content plus every op you "
                "have applied this turn) and return a screenshot. Use it to CHECK YOUR "
                "OWN WORK: is the section actually visible, does the text read against "
                "its background, does it look designed or does it look like a debug "
                "overlay? If something is wrong, fix it with more ops. "
                "ALWAYS pass block_id for the section you changed — without it you get "
                "only the top fold, which shows nothing if you edited a section further "
                "down the page."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "viewport": types.Schema(
                        type=types.Type.STRING,
                        enum=["desktop", "mobile"],
                        description="Which viewport to render. Defaults to desktop.",
                    ),
                    "block_id": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Scroll to and center this block's section before shooting — "
                            "the id of the section you just changed. Omit only when "
                            "judging the page as a whole (e.g. after a theme swap)."
                        ),
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="inspect_block",
            description=(
                "Full, uncompacted JSON for one block by id. The block list in the "
                "instructions has empty fields stripped to save space — use this when "
                "you need to see a section's exact current content or design bag."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "block_id": types.Schema(type=types.Type.STRING),
                },
                required=["block_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="generate_image",
            description=(
                "Generate an AI image and place it into an existing block — either a "
                "content image field, or the section's background. "
                "Expand the user's request into a full photographic brief before calling "
                "this — subject, setting, framing/composition, and lighting — rather than "
                "forwarding their bare phrase; a one-line prompt tends to produce a "
                "generic, low-quality result. "
                "If the user attached photo(s), pass attachment_index (1-based, matching "
                "the numbered attachments in the instructions) to use it as a reference — "
                "for a variation, a background change, or restyling their own photo. "
                "The generated image is shown to you afterward so you can judge it and "
                "retry with a better prompt if it's wrong."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "block_id": types.Schema(type=types.Type.STRING),
                    "field": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "The content image field to set, e.g. 'image'. Defaults to "
                            "'image'. Only valid on blocks that HAVE an image field (e.g. "
                            "hero, split) — for a section background on any other block "
                            "type, use background instead."
                        ),
                    ),
                    "background": types.Schema(
                        type=types.Type.BOOLEAN,
                        description=(
                            "true = use the generated image as the SECTION'S BACKGROUND "
                            "(works on every block type; sets the bg.type/bg.image design "
                            "keys for you). Omit/false = fill the content image field named "
                            "by field. After a background placement, render_screenshot and "
                            "check the text still reads; add bg.overlay / bg.overlayOpacity "
                            "via apply_ops if it doesn't."
                        ),
                    ),
                    "prompt": types.Schema(type=types.Type.STRING),
                    "aspect": types.Schema(
                        type=types.Type.STRING,
                        enum=sorted(AI_ASPECT_RATIOS),
                    ),
                    "image_size": types.Schema(
                        type=types.Type.STRING,
                        enum=list(AI_IMAGE_SIZES),
                        description=(
                            "Output resolution. Defaults to 2K, which is sharp enough for a "
                            "full-bleed section background. Use 4K only if the user explicitly "
                            "asks for maximum quality — it costs about 1.5x more. Use 1K only "
                            "for a small element where a section background's sharpness doesn't matter."
                        ),
                    ),
                    "attachment_index": types.Schema(
                        type=types.Type.INTEGER,
                        description="1-based index into the numbered attachments, to condition on one of them. Omit for a fresh generation.",
                    ),
                },
                required=["block_id", "prompt"],
            ),
        ),
        types.FunctionDeclaration(
            name="finish",
            description=(
                "End the turn. Call this once you are satisfied with what the page "
                "looks like, or to explain why you could not do what was asked."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "message": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "One or two plain-language sentences for the user, "
                            "describing ONLY changes you actually applied."
                        ),
                    ),
                },
                required=["message"],
            ),
        ),
    ]


_AGENT_INSTRUCTIONS = """You are Merlin, an AI that edits a website page for its owner.

Unlike a one-shot editor, you can SEE the page. Work in a loop:

1. Decide what the request means in DESIGN terms, given the section's current \
content and the site's theme (mode, colors, existing design).
2. Call apply_ops with the ops that express it.
3. Call render_screenshot WITH block_id SET TO THE SECTION YOU CHANGED, and LOOK at the \
result. Judge it as a designer would: is the change visible at all? Does text read against \
its background? Do cards still sit apart from the section behind them? Does it look \
intentional, or does it look like a debug overlay?
4. If it is wrong, fix it with more ops and screenshot again. If it is right, call finish.

Checking your work is the point of this loop — a change you never looked at is a guess, and a \
screenshot that isn't scrolled to the section you edited shows nothing (a page has several \
sections; only the one you named with block_id is guaranteed to be in frame). For any visual/ \
design request, screenshot at least once before finishing, always with block_id set to what you \
changed. For a pure copy edit (changing words only) a screenshot is optional; omit block_id only \
when judging the WHOLE page (e.g. after a theme swap).

When the user says a change didn't apply or looks wrong — often with a screenshot of the page \
attached — treat their evidence as ground truth over the conversation history: a prior turn may \
have claimed a change that never rendered. Diagnose from the CURRENT blocks JSON, their \
screenshot, and a fresh render_screenshot of the section in question; apply the fix; then \
screenshot the fixed section before finishing.

Never claim in `finish` that you did something you did not actually apply. If you could not \
do what was asked, apply nothing and say so plainly — that is far better than substituting \
a different change."""


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

def _history_text(history: list[dict[str, Any]]) -> Optional[str]:
    trimmed = history[-_MAX_HISTORY_MESSAGES:]
    if not trimmed:
        return None
    lines = []
    for turn in trimmed:
        if turn.get("role") == "assistant" and turn.get("ops_summary"):
            lines.append(f"assistant: {turn.get('content', '')} [{turn['ops_summary']}]")
        else:
            lines.append(f"{turn.get('role')}: {turn.get('content', '')}")
    return "Conversation so far:\n" + "\n".join(lines)


def _build_system_prompt(
    *,
    blocks: list[dict[str, Any]],
    theme: dict[str, Any],
    business_name: Optional[str],
    selected_block: Optional[str],
    selection: Optional[dict[str, Any]] = None,
    history: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
) -> str:
    parts = [_AGENT_INSTRUCTIONS, *build_shared_prompt_sections()]
    if business_name:
        parts.append(f"Site: {business_name}")

    compact = [strip_prompt_noise(b) if isinstance(b, dict) else b for b in blocks]
    parts.append("Current blocks (JSON):\n" + json.dumps(compact, separators=(",", ":")))
    parts.append("Current theme (JSON):\n" + json.dumps(theme, separators=(",", ":")))

    parts.append(build_selection_prompt_line(selection, blocks, selected_block))

    caption = caption_lines(attachments)
    if caption:
        parts.append(caption)

    convo = _history_text(history)
    if convo:
        parts.append(convo)
    return "\n\n".join(parts)


def _has_inline_image(part: types.Part) -> bool:
    return getattr(part, "inline_data", None) is not None


def _strip_stale_images(content: types.Content) -> types.Content:
    """Replace a past turn's image Part(s) with one text placeholder.

    Every OTHER part is kept verbatim — in particular `function_response`
    parts, which the API requires one-per-call for the call they answer;
    dropping one breaks every model call after it, not just the image
    bookkeeping. A no-op (returns the same object) when there's nothing to
    strip, so re-running this over an already-stripped turn is harmless.
    """
    parts = list(content.parts or [])
    kept = [p for p in parts if not _has_inline_image(p)]
    if len(kept) == len(parts):
        return content
    kept.append(types.Part(text=_STALE_SHOT_NOTE))
    return types.Content(role=content.role, parts=kept)


def _strip_initial_attachments(content: types.Content) -> types.Content:
    """Drop original user image bytes after the planning call.

    They are useful for the first interpretation of the request, but resending
    them on every follow-up is wasted input spend. `atts` remains intact for a
    later `generate_image(attachment_index=...)` call.
    """
    parts = list(content.parts or [])
    kept = [part for part in parts if not _has_inline_image(part)]
    if len(kept) == len(parts):
        return content
    kept.append(types.Part(text=_STALE_ATTACHMENT_NOTE))
    return types.Content(role=content.role, parts=kept)


def _agent_observation(*, name: str, args: dict[str, Any], payload: dict[str, Any]) -> ToolObservation:
    if name == "apply_ops":
        return ToolObservation(
            tool=name,
            status="changed" if payload.get("applied") else "failed",
            args=args,
            reason=payload.get("error") or next(
                (item.get("reason") for item in payload.get("rejected") or [] if isinstance(item, dict)),
                None,
            ),
        )
    if name == "inspect_block":
        return ToolObservation(
            tool=name,
            status="informed" if payload.get("block") is not None else "failed",
            args=args,
            reason=payload.get("error"),
        )
    if name == "render_screenshot":
        return ToolObservation(
            tool=name,
            status="informed" if payload.get("rendered") is True else "failed",
            args=args,
            reason=payload.get("error"),
        )
    if name == "generate_image":
        return ToolObservation(
            tool=name,
            status="changed" if payload.get("placed") is True else "failed",
            args=args,
            reason=payload.get("error"),
        )
    return ToolObservation(tool=name, status="failed", args=args, reason=payload.get("error"))


async def run_merlin_agent(
    *,
    message: str,
    history: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    theme: dict[str, Any],
    render_html,
    business_name: Optional[str] = None,
    model_tier: str = "regular",
    plan: Any = None,
    account_id: Optional[str] = None,
    selected_block: Optional[str] = None,
    selection: Optional[dict[str, Any]] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run one agent turn, yielding SSE-shaped frames.

    `render_html(blocks, theme) -> str` is injected by the route: rendering
    needs the site row, nav pages and the plan's design gating, none of which
    belong in this module.

    Frames: `{"type": "status"|"step"|"error"|"result", ...}`. Exactly one
    `result` frame is always emitted last, carrying the validated op log even
    when the loop failed partway.
    """
    tier = model_tier if model_tier in MODEL_TIERS else DEFAULT_MODEL_TIER
    bounds = _BOUNDS.get(tier, _BOUNDS["regular"])
    tier_cfg = MODEL_TIERS[tier]
    premium = is_premium_plan(plan)
    theme_intent = has_theme_intent(message)
    rate_limiter = GeminiRateLimiter()
    atts = attachments or []

    # The working copy. Ops fold onto this so a screenshot shows the cumulative
    # result; the client's real state is untouched until it applies `op_log`.
    work_blocks = [dict(b) for b in blocks if isinstance(b, dict)]
    work_theme = dict(theme)

    op_log: list[dict[str, Any]] = []
    rejected_log: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    final_message: Optional[str] = None

    model_calls = 0
    screenshots = 0
    # Deterministic (not model-dependent) honesty guard: whether the model
    # ever actually SAW a render this turn, vs. only tried and failed. Used at
    # result assembly below to caveat a claimed success it never verified —
    # the second half of the 2026-08-01 incident (a false "it worked" message
    # is a prompt-following failure the model can repeat; this can't be forgotten).
    screenshot_ok = False
    screenshot_failed = False
    no_progress = NoProgressGuard()
    token_budget = TurnTokenBudget(bounds.prompt_tokens, bounds.total_tokens)
    started = time.monotonic()

    def elapsed() -> float:
        return time.monotonic() - started

    def time_left() -> float:
        return bounds.wall_clock - elapsed()

    def record_step(step: dict[str, Any]) -> dict[str, Any]:
        steps.append(step)
        return {"type": "step", **step}

    client = get_genai_client()
    system_instruction = _build_system_prompt(
        blocks=blocks, theme=theme, business_name=business_name,
        selected_block=selected_block, selection=selection, history=history, attachments=atts,
    )
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=_tool_declarations())],
        thinking_config=types.ThinkingConfig(thinking_level=tier_cfg.thinking_level),
        system_instruction=system_instruction,
    )
    first_parts: list[types.Part] = [
        types.Part.from_bytes(data=a["data"], mime_type=a["mime"]) for a in atts
    ]
    first_parts.append(types.Part(text=message))
    contents: list[types.Content] = [types.Content(role="user", parts=first_parts)]
    # Indices into `contents` of past turns still carrying an image Part —
    # user-attached photos are NOT tracked here (they're the request itself,
    # not a screenshot to prune) — only entries appended after a tool-call
    # batch below. See _strip_stale_images / _KEEP_RECENT_SHOTS.
    image_bearing_indices: list[int] = []

    # --- tool implementations ------------------------------------------------

    def do_apply_ops(args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """(function_response payload, step frame). Validates against the CURRENT
        working copy, not the original snapshot — so an op may legitimately
        target a block an earlier tool call in this same turn created."""
        nonlocal work_blocks, work_theme
        raw = args.get("ops")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return {"error": "ops was not valid JSON — send a JSON array of op objects"}, {}
        if not isinstance(parsed, list):
            return {"error": "ops must be a JSON array"}, {}

        # `validate_ops`' own MAX_OPS_PER_TURN caps a single CALL. The agent
        # loop can call apply_ops several times in one turn, and op_log
        # accumulates across all of them — this is the actual per-TURN
        # ceiling, which no single call's own limit can see.
        remaining = _MAX_TURN_OPS - len(op_log)
        if remaining <= 0:
            return (
                {"error": f"op budget for this turn is spent ({_MAX_TURN_OPS}) — call finish with what you have"},
                {},
            )
        overflow_rejections: list[dict[str, Any]] = []
        if len(parsed) > remaining:
            overflow, parsed = parsed[remaining:], parsed[:remaining]
            overflow_rejections = [
                {
                    "op": o if isinstance(o, dict) else {"op": str(o)},
                    "reason": f"turn exceeded the {_MAX_TURN_OPS}-op budget for this turn",
                }
                for o in overflow
            ]

        valid, rejections = validate_ops(
            parsed, work_blocks, premium=premium, theme_intent=theme_intent
        )
        rejections = [*rejections, *overflow_rejections]
        applied = apply_ops(work_blocks, work_theme, valid)
        work_blocks, work_theme = applied.blocks, applied.theme

        # The op log is what the CLIENT will replay. Every validated op goes in
        # — a valid op whose target has since vanished degrades to a "Skipped"
        # chip when the client re-applies it, same as `applied.results` shows
        # here; it's still worth sending (the client's state may differ from
        # this working copy by the time it applies).
        op_log.extend(valid)
        rejected_log.extend(rejections)

        payload = {
            "applied": [r["summary"] for r in applied.results if r["ok"]],
            "skipped": [r["summary"] for r in applied.results if not r["ok"]],
            "rejected": [
                {"op": r["op"].get("op"), "reason": r["reason"]} for r in rejections
            ],
        }
        n_ok = sum(1 for r in applied.results if r["ok"])
        step = {
            "kind": "ops",
            "label": f"Applied {n_ok} change{'' if n_ok == 1 else 's'}"
            + (f", {len(rejections)} rejected" if rejections else ""),
            "results": applied.results,
        }
        return payload, step

    def do_inspect_block(args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        block_id = args.get("block_id")
        found = next((b for b in work_blocks if b.get("id") == block_id), None)
        if found is None:
            return {"error": f"no block with id '{block_id}'"}, {}
        return {"block": found}, {"kind": "inspect", "label": f"Inspected {found.get('type')}"}

    async def do_screenshot(args: dict[str, Any]):
        """Returns (function_response payload, step frame, png bytes | None)."""
        nonlocal screenshots, screenshot_ok, screenshot_failed
        from ..browser_pool import ScreenshotUnavailable, screenshot_html

        viewport = args.get("viewport") or "desktop"
        if screenshots >= bounds.screenshots:
            return (
                {"error": f"screenshot budget spent ({bounds.screenshots}) — finish with what you have"},
                {},
                None,
            )
        if time_left() <= 0:
            # The wall-clock bound is only re-checked between loop iterations —
            # without this, a call that legally started with time left can
            # still spend up to the shot's own ~20s timeout AFTER the bound is
            # already gone, doubling the overrun on top of the model call's own.
            return (
                {"error": "time budget spent — finish with what you have"},
                {"kind": "screenshot", "label": "Skipped — out of time"},
                None,
            )
        # Resolve block_id to its render index — render_html enumerates
        # work_blocks in the same order screenshot_html's focus_block indexes
        # into (see render_site_html's block_anchors). A stale/unknown id
        # degrades to None (top-fold shot), never an error — the model asking
        # to look is more important than it naming the id exactly right.
        block_id = args.get("block_id")
        focus_index = next(
            (i for i, b in enumerate(work_blocks) if isinstance(b, dict) and b.get("id") == block_id),
            None,
        ) if isinstance(block_id, str) and block_id else None
        focus_label = BLOCK_LABELS.get(
            next((b.get("type") for b in work_blocks if isinstance(b, dict) and b.get("id") == block_id), None)
        ) if focus_index is not None else None

        try:
            # render_html is a sync HTML build (WeasyPrint-adjacent string work,
            # not I/O) — off the event loop so it doesn't stall every other
            # request while a Max turn takes up to 5 shots.
            html = await asyncio.to_thread(render_html, work_blocks, work_theme)
            png, blocked_hosts = await screenshot_html(html, viewport, focus_block=focus_index)
        except ScreenshotUnavailable as exc:
            # Chromium missing or crashed. The turn continues blind rather than
            # failing — that's still today's behavior, not a regression.
            logger.warning("Merlin screenshot unavailable: %s", exc)
            screenshot_failed = True
            return (
                {"error": "screenshot unavailable on this server — proceed without it"},
                {"kind": "screenshot", "label": "Preview unavailable"},
                None,
            )
        except Exception as exc:  # noqa: BLE001 — never-raises contract
            logger.warning("Merlin render failed: %s", exc)
            screenshot_failed = True
            return (
                {"error": "could not render the page — proceed without a screenshot"},
                {"kind": "screenshot", "label": "Render failed"},
                None,
            )
        screenshots += 1
        screenshot_ok = True
        step = {
            "kind": "screenshot",
            "label": f"Rendered {viewport} preview — {focus_label}" if focus_label
            else f"Rendered {viewport} preview",
        }
        # Store the shot so the transcript can show what Merlin actually looked
        # at — the difference between "it says it checked" and seeing the frame
        # it checked. Best-effort: no storage configured just means no thumbnail.
        try:
            step["image_url"] = await get_storage().upload_file(
                png, f"shot_{secrets.token_hex(8)}.{SHOT_EXT}",
                prefix="cappe/merlin-shots", content_type=SHOT_MIME,
            )
        except Exception as exc:  # noqa: BLE001 — cosmetic, never fails the turn
            logger.info("Merlin screenshot upload skipped: %s", exc)
        note = "The image attached to this response is the page as it now stands."
        if blocked_hosts:
            # Tell the model explicitly rather than let it infer a rendering
            # bug from a blank area — those hosts are blocked for SSRF safety
            # (see browser_pool._route_guard), not broken on the real site.
            note += (
                f" Fetches to these external hosts were blocked for this preview and will "
                f"render blank or missing here even though they load fine for real visitors: "
                f"{', '.join(blocked_hosts)}. Do not 'fix' a section for that reason alone."
            )
        return (
            {"rendered": True, "viewport": viewport, "note": note},
            step,
            png,
        )

    async def do_generate_image(args: dict[str, Any]):
        """Generate, fold the result as a `set_field` onto the working copy, and
        hand the bytes back so the model can judge and retry. Executed inline
        (not deferred to the client like the single-shot path's generate_image
        op) — the whole point of the tool is that the model sees what it made.
        """
        nonlocal work_blocks, work_theme
        from ....core.services.image_gen import IMAGE_MODEL, ImageGenError, generate_image
        from ..image_prompting import build_image_prompt

        if time_left() <= 0:
            # Same reasoning as do_screenshot's check: generation has its own
            # ~60s internal timeout, the single biggest contributor to a turn
            # overrunning its advertised wall-clock bound if allowed to start
            # after the budget is already gone.
            return (
                {"error": "time budget spent — finish with what you have"},
                {"kind": "image", "label": "Skipped — out of time"},
                None,
            )

        block_id = args.get("block_id")
        prompt = str(args.get("prompt") or "").strip()
        field_given = args.get("field")
        field = str(field_given or "image")
        aspect = args.get("aspect") if args.get("aspect") in AI_ASPECT_RATIOS else None
        image_size = args.get("image_size") if args.get("image_size") in AI_IMAGE_SIZES else DEFAULT_AI_IMAGE_SIZE

        target = next((b for b in work_blocks if b.get("id") == block_id), None)
        if target is None:
            return {"error": f"no block with id '{block_id}'"}, {}, None
        if not prompt:
            return {"error": "prompt is required"}, {}, None
        if len(prompt) > AI_IMAGE_PROMPT_MAX:
            return {"error": f"prompt too long (max {AI_IMAGE_PROMPT_MAX} chars)"}, {}, None

        # Resolve WHERE this lands before spending any quota/$ generating it —
        # the 2026-08-01 incident was a claimed background write landing in a
        # dead `image` key on a `text` block (no image field at all), because
        # this tool folded a raw set_field without ever checking the target
        # was valid. Mirrors _v_generate_image's single-shot check (ops.py).
        btype = target.get("type")
        background = args.get("background") is True
        reroute_note: Optional[str] = None
        if not background:
            target_err = image_field_error(btype, field)
            if target_err is not None:
                if field_given is None and not image_fields(btype):
                    # Default placement on a block with no image field at all
                    # — the section background is the only target that can
                    # render it, so route there instead of burning a turn on
                    # an error round-trip. ("make this text section look like
                    # handcrafted paper" is exactly this case.)
                    background = True
                    reroute_note = (
                        f"{btype} blocks have no image field — placed as the "
                        "section background (bg.type + bg.image) instead"
                    )
                else:
                    # No premium check needed here: the agent loop only runs
                    # on AGENT_TIERS (regular/max), which the route clamps to
                    # premium plans — a free account never reaches this tool.
                    return (
                        {"error": target_err + " — pass background: true to place it as the section background"},
                        {"kind": "image", "label": "Skipped — invalid image target"},
                        None,
                    )

        reference: Optional[list[tuple[bytes, str]]] = None
        idx = args.get("attachment_index")
        if isinstance(idx, (int, float)) and 1 <= int(idx) <= len(atts):
            att = atts[int(idx) - 1]
            reference = [(att["data"], att["mime"])]

        if account_id is not None:
            try:
                await image_quota.check_and_record(account_id, premium=premium)
            except HTTPException:
                # `check_and_record` is `redis_cache.check_rate_limit`, which
                # raises HTTPException(429) — not RateLimitExceeded (that type
                # is GeminiRateLimiter's, a different budget). Catch the real
                # one so quota exhaustion degrades this ONE tool call rather
                # than escaping to the loop's outer handler and killing the
                # whole turn (including ops already applied this turn).
                return (
                    {"error": "image generation quota reached for today"},
                    {"kind": "image", "label": "Image quota reached"},
                    None,
                )

        try:
            # Separates agent-driven image spend from the editor's plain
            # Generate button, which keeps the stack-derived "core.image_gen"
            # label — both call the same `generate_image`, so without this
            # override the by-feature rollup couldn't tell them apart. The
            # scope survives `generate_image`'s internal `asyncio.to_thread`
            # (contextvars.Context is copied into the worker thread).
            with feature_scope("cappe.merlin_agent.image"):
                # The model already wrote a detailed brief (tool description
                # asks for one); build_image_prompt still adds the baseline
                # quality/no-text/no-watermark clause every generation here
                # gets, same as the wizard's direct path.
                url, png = await generate_image(
                    build_image_prompt(prompt), prefix="cappe/gen", aspect_ratio=aspect or "16:9",
                    reference_images=reference, return_bytes=True,
                    image_size=image_size,
                )
        except ImageGenError as exc:
            return (
                {"error": f"generation failed: {exc}"},
                {"kind": "image", "label": "Image generation failed"},
                None,
            )

        if background:
            fold = [
                {"op": "set_design", "block": block_id, "group": "bg", "key": "type", "value": "image"},
                {"op": "set_design", "block": block_id, "group": "bg", "key": "image", "value": url},
            ]
        else:
            fold = [{"op": "set_field", "block": block_id, "path": field, "value": url}]
        cost = AI_IMAGE_SIZE_COST_ESTIMATE.get(image_size, "")
        applied = apply_ops(work_blocks, work_theme, fold)
        if not all(r.get("ok") for r in applied.results):
            # Reachable only via a same-turn race (e.g. the block was removed
            # by an earlier op this turn). The step still carries image_url so
            # the panel's "Apply to…" menu can rescue the paid generation.
            reason = next(r["summary"] for r in applied.results if not r.get("ok"))
            return (
                {"error": f"image generated but not placed: {reason}", "url": url},
                {
                    "kind": "image",
                    "label": f"Generated image ({image_size}, {IMAGE_MODEL}, {cost}) — placement failed",
                    "image_url": url, "prompt": prompt, "aspect": aspect or "16:9", "image_size": image_size,
                },
                png,
            )
        work_blocks, work_theme = applied.blocks, applied.theme
        op_log.extend(fold)

        placed_note = "The image attached to this response is what was generated and placed."
        if reroute_note:
            placed_note = reroute_note + ". " + placed_note
        elif background:
            placed_note += " Screenshot to verify the text still reads against it — bg.overlay / bg.overlayOpacity are available via apply_ops if not."
        target_label = "background" if background else field
        return (
            {"placed": True, "url": url, "note": placed_note},
            # image_url lets the panel show what was generated (same field the
            # screenshot step already uses for its thumbnail) — and now also
            # drives the panel's "Apply to…" menu, so the user can re-target
            # the SAME generated image onto a different field/background than
            # wherever the model happened to place it. prompt/aspect/image_size
            # ride along so the route can catalog this generation into
            # cappe_assets without re-deriving them from the tool-call args.
            # model/cost are folded into the label — the only thing the panel
            # actually renders — so "which model, roughly what did that cost"
            # is visible in the transcript itself, not just on /admin/ai-usage.
            {
                "kind": "image", "label": f"Generated image ({image_size}, {IMAGE_MODEL}, {cost}) → {target_label}",
                "image_url": url,
                "prompt": prompt, "aspect": aspect or "16:9", "image_size": image_size,
            },
            png,
        )

    # --- the loop ------------------------------------------------------------

    try:
        while True:
            if model_calls >= bounds.model_calls or elapsed() >= bounds.wall_clock:
                reason = "step" if model_calls >= bounds.model_calls else "time"
                logger.info("Merlin agent hit its %s bound (tier=%s)", reason, tier)
                yield {"type": "status", "message": "Wrapping up…"}
                break
            budget_reason = token_budget.reason_before_next_call(
                estimated_next_prompt_tokens=estimate_prompt_tokens(system_instruction, contents)
            )
            if budget_reason:
                logger.info("Merlin agent hit token bound (tier=%s calls=%s)", tier, model_calls)
                final_message = budget_reason
                break

            await rate_limiter.check_limit("cappe_merlin", "agent")
            model_calls += 1
            # Capped to whatever's left of the wall clock, not the flat
            # per-call ceiling: a call that legally started at t=119s of a
            # 120s bound must not still be allowed to run the full 75s —
            # the loop-top bound check only fires BETWEEN iterations, so the
            # call's own timeout is what keeps one iteration from blowing
            # past the tier's advertised ceiling.
            call_timeout = min(_CALL_TIMEOUT, max(1.0, bounds.wall_clock - elapsed()))
            try:
                # Labeled separately from the stack-derived "cappe.merlin_agent"
                # (and split by tier): this is the call whose cost actually
                # grows turn over turn, since `contents` accumulates every
                # screenshot as image input tokens — the by-feature rollup at
                # /admin/ai-usage needs to isolate it from the one-off
                # generate_image tool call below to answer "which part of an
                # agentic turn costs the most".
                with feature_scope(f"cappe.merlin_agent.loop.{tier}"):
                    response = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=tier_cfg.model, contents=contents, config=config
                        ),
                        timeout=call_timeout,
                    )
            finally:
                # Record even on timeout: the request was issued and billed.
                await rate_limiter.record_call("cappe_merlin", tier)
            token_budget.record_response(
                response,
                fallback_prompt_tokens=estimate_prompt_tokens(system_instruction, contents),
            )
            if model_calls == 1:
                contents[0] = _strip_initial_attachments(contents[0])

            # Keep the ORIGINAL parts, not just their `.function_call` — a
            # thinking model (gemini-3.x) attaches a `thought_signature` to
            # each function-call part, and the API requires it echoed back on
            # the next turn or every call past the first 400s with
            # "Function call is missing a thought_signature". Rebuilding a
            # bare `Part(function_call=c)` below used to drop it silently.
            call_parts = [
                part
                for candidate in (response.candidates or [])
                for part in (candidate.content.parts or [] if candidate.content else [])
                if getattr(part, "function_call", None)
            ]
            calls = [p.function_call for p in call_parts]

            if not calls:
                # No tool call — the model answered in prose. Treat it as the
                # finishing message rather than looping on nothing.
                final_message = (getattr(response, "text", None) or "").strip() or None
                break

            # Echo the model's own parts back verbatim (thought_signature and
            # all) before the responses, or the next call loses the tool-call
            # context.
            contents.append(
                types.Content(
                    role="model",
                    parts=call_parts,
                )
            )

            response_parts: list[types.Part] = []
            image_parts: list[types.Part] = []
            finished = False
            observations: list[ToolObservation] = []

            # Gemini's parallel function calling makes no ordering promise
            # within one batch — `[finish(...), apply_ops(...)]` is a real
            # shape, not a hypothetical. Breaking on `finish` mid-iteration
            # used to drop every call after it unexecuted, so a turn could
            # report "darkened the hero" with an empty op log. Run every
            # OTHER call in the batch first; honor `finish` only once they've
            # all executed, so the message it returns describes ops that
            # actually landed.
            finish_message: Optional[str] = None
            for call in calls:
                name = call.name
                args = dict(call.args or {})

                if name == "finish":
                    finish_message = str(args.get("message") or "").strip() or None
                    finished = True
                    continue

                if name == "apply_ops":
                    payload, step = do_apply_ops(args)
                elif name == "inspect_block":
                    payload, step = do_inspect_block(args)
                elif name == "render_screenshot":
                    yield {"type": "status", "message": "Rendering the page…"}
                    payload, step, png = await do_screenshot(args)
                    if png is not None:
                        image_parts.append(types.Part.from_bytes(data=png, mime_type=SHOT_MIME))
                elif name == "generate_image":
                    from ....core.services.image_gen import IMAGE_MODEL as _IMG_MODEL

                    _size = args.get("image_size") if args.get("image_size") in AI_IMAGE_SIZES else DEFAULT_AI_IMAGE_SIZE
                    _cost = AI_IMAGE_SIZE_COST_ESTIMATE.get(_size, "")
                    yield {
                        "type": "status",
                        "message": f"Generating image — {_IMG_MODEL} · {_size} ({_cost})…",
                    }
                    payload, step, png = await do_generate_image(args)
                    if png is not None:
                        image_parts.append(types.Part.from_bytes(data=png, mime_type="image/png"))
                else:
                    payload, step = {"error": f"unknown tool '{name}'"}, {}

                observations.append(_agent_observation(name=name, args=args, payload=payload))
                if step:
                    yield record_step(step)
                response_parts.append(
                    types.Part.from_function_response(name=name, response=payload)
                )

            decision = no_progress.observe_batch(observations)
            if decision.stop:
                final_message = (
                    "I need a detail corrected before I can make that change: "
                    f"{decision.reason or 'the edit was rejected.'}"
                )
                break
            if finished and not any(observation.status == "failed" for observation in observations):
                final_message = finish_message
                break

            if finished:
                response_parts.append(types.Part.from_function_response(
                    name="finish",
                    response={
                        "status": "deferred",
                        "reason": "One or more tool calls failed; review their results before finishing.",
                    },
                ))

            if image_parts:
                # This batch is about to become the newest image-bearing turn —
                # prune every earlier one down past the keep count BEFORE
                # appending it, so "most recent" always means "as of the turn
                # that's about to be sent", not last call's newest.
                keep_existing = max(_KEEP_RECENT_SHOTS - 1, 0)
                stale = image_bearing_indices[: len(image_bearing_indices) - keep_existing] \
                    if keep_existing else image_bearing_indices
                for i in stale:
                    contents[i] = _strip_stale_images(contents[i])
                image_bearing_indices = image_bearing_indices[len(stale):]

            contents.append(types.Content(role="user", parts=[*response_parts, *image_parts]))
            if image_parts:
                image_bearing_indices.append(len(contents) - 1)

    except RateLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 — never-raises past rate limiting
        logger.warning("Merlin agent turn failed: %s", exc, exc_info=True)
        yield {"type": "error", "message": "Merlin hit a problem mid-edit — keeping what worked."}

    if not final_message:
        final_message = (
            "Here's what I changed." if op_log else "I couldn't complete that — nothing was changed."
        )
    if op_log and screenshot_failed and not screenshot_ok:
        # The incident's second half: the model finished claiming success it
        # never actually SAW (every render_screenshot attempt this turn
        # degraded — no Chromium, or a render error). Deterministic, not a
        # prompt instruction the model can forget under a different tier/turn.
        final_message = final_message.rstrip() + (
            " (Note: I couldn't render a preview to verify these changes visually — "
            "please double-check the page.)"
        )

    yield {
        "type": "result",
        "data": {
            "message": final_message,
            "ops": op_log,
            "rejected": rejected_log,
            "tier": tier,
            "steps": steps,
        },
    }
