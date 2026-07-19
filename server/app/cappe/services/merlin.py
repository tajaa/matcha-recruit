"""Merlin — AI chat editing for the Cappe page builder.

The user chats ("make the hero darker and add an FAQ"); Gemini returns a short
JSON envelope `{message, ops}` where each op is one of a small, whitelisted
set (see `merlin_catalog.py` and `_OP_NAMES` below). The client applies ops to
its own in-memory editor state (auto-apply + undo — nothing persists here);
this module's job is to produce *safe* ops, not to touch the database.

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
    CANVAS_ELEMENT_KINDS,
    CANVAS_GRID_COLS,
    CANVAS_GRID_ROWS_MAX,
    CANVAS_MAX_ELEMENTS,
    CANVAS_MOBILE_GRID_COLS,
    CANVAS_PATCH_KEYS,
    CANVAS_STYLE_KEYS,
    DEFAULT_MODEL_TIER,
    DESIGN_GROUPS,
    FREE_PLAN_TIERS,
    LIST_KINDS,
    MAX_OPS_PER_TURN,
    MODEL_TIERS,
    SELECT_OPTIONS,
    TEXT_KINDS,
    THEME_KEY_PREFIXES,
    THEME_KEYS,
    THEME_MODE_VALUES,
)

logger = logging.getLogger(__name__)

MERLIN_CALL_TIMEOUT = 45  # seconds — same order as ir_analysis.GEMINI_CALL_TIMEOUT
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
# A theme swap replaces brand/fonts/radius/mode site-wide, so it only fires when
# the user actually asked for one. Without this the model reached for `preset`
# on a request that never mentioned themes and nuked the site's look.
_THEME_INTENT_RE = re.compile(r"\b(theme|preset|palette|colou?r scheme|restyle|redesign)\b", re.I)
_OP_NAMES = frozenset({
    "set_field", "set_design", "add_block", "remove_block", "move_block",
    "set_theme", "canvas_add", "canvas_update", "canvas_remove",
})
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
# Validation
# ---------------------------------------------------------------------------

def _sid(value: Any) -> Optional[str]:
    """Model-supplied ids/keys are used as dict/set lookup keys, and a
    hallucinated dict or list there raises `TypeError: unhashable type` —
    which would escape the never-raises contract and 500 the whole turn over
    one bad op. Everything that gets looked up goes through here first."""
    return value if isinstance(value, str) else None


def _index_blocks(blocks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {b["id"]: b for b in blocks if isinstance(b, dict) and isinstance(b.get("id"), str)}


def _num(value: Any) -> Optional[float]:
    """A real number. `bool` is excluded explicitly — `True` is an `int` in
    Python, so `{"x": true}` would otherwise validate as a grid coordinate."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _canvas_grid(block: dict[str, Any], key: str = "grid") -> tuple[int, int]:
    """(cols, rows) for a canvas block's desktop (`grid`) or mobile (`mobile`)
    breakpoint, falling back to the editor defaults."""
    grid = block.get(key)
    default_cols = CANVAS_GRID_COLS if key == "grid" else CANVAS_MOBILE_GRID_COLS
    cols, rows = default_cols, CANVAS_GRID_ROWS_MAX
    if isinstance(grid, dict):
        c, r = _num(grid.get("cols")), _num(grid.get("rows"))
        if c and c > 0:
            cols = int(c)
        if r and r > 0:
            rows = min(int(r), CANVAS_GRID_ROWS_MAX)
    return cols, rows


def _check_positions(payload: dict[str, Any], grid: tuple[int, int], mobile_grid: tuple[int, int]) -> Optional[str]:
    """Bounds-check whichever placements are present. `m` (mobile) gets the same
    treatment as `d` — it is spread onto the element client-side just the same,
    so leaving it unchecked reopens the unreachable-element hole on the mobile
    breakpoint."""
    if "d" in payload and not _valid_pos(payload.get("d"), grid):
        return "element position is out of bounds"
    if "m" in payload and not _valid_pos(payload.get("m"), mobile_grid):
        return "mobile element position is out of bounds"
    return None


def _canvas_elements(block: dict[str, Any]) -> list[dict[str, Any]]:
    els = block.get("elements")
    return [e for e in els if isinstance(e, dict)] if isinstance(els, list) else []


def _valid_pos(d: Any, grid: tuple[int, int]) -> bool:
    """Bounds an element to the grid on BOTH axes. The renderer clamps y at
    publish time, but the editor canvas does not — an unbounded y puts the
    element somewhere the user can't scroll to and can only undo."""
    if not isinstance(d, dict):
        return False
    cols, rows = grid
    x, y, w, h = (_num(d.get(k)) for k in ("x", "y", "w", "h"))
    if any(v is None for v in (x, y, w, h)):
        return False
    if w <= 0 or h <= 0 or x < 0 or y < 0:
        return False
    return x + w <= cols and y + h <= rows


def _validate_field_value(
    raw: dict[str, Any], block: dict[str, Any], head: str, kind: str,
    rest: list[str], btype: str,
) -> Optional[str]:
    """Path + value checking for `set_field`, keyed on the field's declared
    kind. Two things this must catch, both of which silently destroyed content
    before: a non-integer segment after a list field (the client's deepSet
    replaced the whole array with an object), and a value of the wrong JSON
    type for the field (a list field set to a bare string)."""
    value = raw.get("value")

    if rest:
        if kind not in LIST_KINDS:
            # Scalar field with a sub-path — nothing legal addresses into a string.
            return f"'{head}' on a {btype} block is a {kind} field and has no sub-fields"
        idx_seg = rest[0]
        if not idx_seg.isdigit():
            return f"'{head}' is a list — '{idx_seg}' must be a list index, not a key"
        idx = int(idx_seg)
        current = block.get(head)
        length = len(current) if isinstance(current, list) else 0
        # `== length` is an append; anything past that would leave undefined holes.
        if idx > length:
            return f"index {idx} is past the end of '{head}' (length {length})"
        if kind == "strlist" and len(rest) > 1:
            return f"'{head}' holds plain strings — '{rest[1]}' is not addressable"
        if kind == "strlist" and not isinstance(value, str):
            return f"'{head}' entries must be strings"
        return None

    # Whole-field assignment — the value must match the field's kind.
    return _field_value_error(value, kind, btype, head)


def _field_value_error(value: Any, kind: str, btype: str, head: str) -> Optional[str]:
    """Type-check a whole-field value against its declared kind. Shared by
    `set_field` and `add_block.content` so the two can't drift — an unchecked
    add_block was letting through exactly what set_field rejects."""
    if kind == "bool":
        if not isinstance(value, bool):
            return f"'{head}' must be true or false"
    elif kind == "strlist":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return f"'{head}' must be a list of strings"
    elif kind == "list":
        if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
            return f"'{head}' must be a list of objects"
    elif kind in TEXT_KINDS:
        if value is not None and not isinstance(value, str):
            return f"'{head}' must be text"
        if kind == "select" and value:
            allowed = SELECT_OPTIONS.get(btype, {}).get(head)
            if allowed and value not in allowed:
                return f"'{head}' must be one of: {', '.join(sorted(allowed))}"
    return None


def _valid_field_value(value: Any, kind: str, btype: str, head: str) -> bool:
    return _field_value_error(value, kind, btype, head) is None


def _design_value_error(value: Any, spec: Any, group: str, key: str) -> Optional[str]:
    """Check a `_design` value against its spec from DESIGN_GROUPS: a frozenset
    is a closed enum, a (min, max) tuple an int range, else a kind name.
    `None` always passes — it clears the key, mirroring DesignInspector's
    `patch(group, key, '')` behavior."""
    if value is None:
        return None
    if isinstance(spec, frozenset):
        if value not in spec:
            return f"'{key}' must be one of: {', '.join(sorted(spec))}"
    elif isinstance(spec, tuple):
        num = _num(value)
        if num is None or not (spec[0] <= num <= spec[1]):
            return f"'{key}' must be a number between {spec[0]} and {spec[1]}"
    elif spec == "bool":
        if not isinstance(value, bool):
            return f"'{key}' must be true or false"
    elif spec == "color":
        if not isinstance(value, str) or not _HEX_COLOR_RE.match(value):
            return f"'{key}' must be a hex color like #1a2b3c"
    elif spec == "text":
        if not isinstance(value, str):
            return f"'{key}' must be text"
    return None


def _filter_style(style: Any) -> dict[str, Any]:
    return {k: v for k, v in style.items() if k in CANVAS_STYLE_KEYS} if isinstance(style, dict) else {}


def validate_ops(
    raw_ops: list[Any], blocks: list[dict[str, Any]], *,
    premium: bool = True, theme_intent: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter a model-produced ops array down to ones that are safe to hand to
    the client. Returns (valid_ops, rejections) where each rejection is
    `{"op": <original>, "reason": <str>}`. Truncates to MAX_OPS_PER_TURN before
    validating anything past it (rejected with a shared reason, not silently
    dropped) — a runaway op count is a prompt/model failure, not routine.

    `premium` gates the `_design` bag (stripped on save for free plans, so
    applying it would be a lie). `theme_intent` is whether the user's message
    actually asked about themes — a whole-site preset swap is too destructive
    to fire off a request that never mentioned one.

    Validates against the snapshot the client sent, not against effects of
    earlier ops in the same batch: an op that targets something an earlier op
    in this same turn would have created (e.g. canvas_update on a canvas_add's
    new element) will not resolve and is rejected — acceptable for v1, since
    the client applies ops in order and a follow-up chat turn can adjust it.
    """
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    if len(raw_ops) > MAX_OPS_PER_TURN:
        for extra in raw_ops[MAX_OPS_PER_TURN:]:
            rejected.append({"op": extra if isinstance(extra, dict) else {"op": str(extra)},
                              "reason": f"turn exceeded the {MAX_OPS_PER_TURN}-op limit"})
        raw_ops = raw_ops[:MAX_OPS_PER_TURN]

    by_id = _index_blocks(blocks)
    # Track canvas element counts as adds are validated, so a burst of
    # canvas_add ops in one turn can't blow past CANVAS_MAX_ELEMENTS even
    # though each individual op looks fine against the original snapshot.
    pending_canvas_count = {
        bid: len(_canvas_elements(b)) for bid, b in by_id.items() if b.get("type") == "canvas"
    }

    for raw in raw_ops:
        if not isinstance(raw, dict):
            rejected.append({"op": {"op": str(raw)}, "reason": "op was not a JSON object"})
            continue
        op = raw.get("op")
        if op not in _OP_NAMES:
            rejected.append({"op": raw, "reason": f"unknown op '{op}'"})
            continue

        reason = _validate_one(raw, op, by_id, pending_canvas_count, premium, theme_intent)
        if reason:
            rejected.append({"op": raw, "reason": reason})
        else:
            valid.append(raw)

    return valid, rejected


def _validate_one(
    raw: dict[str, Any], op: str, by_id: dict[str, dict[str, Any]],
    pending_canvas_count: dict[str, int], premium: bool = True, theme_intent: bool = True,
) -> Optional[str]:
    """Returns None if valid, else a rejection reason. May mutate `raw` in
    place to strip unknown/structural keys (e.g. add_block.content, canvas
    style bags) — the caller still appends the (now-cleaned) `raw` to `valid`."""

    if op == "set_field":
        block = by_id.get(_sid(raw.get("block")))
        if block is None:
            return "block id not found"
        path = raw.get("path")
        if not isinstance(path, str) or not path:
            return "missing path"
        btype = block.get("type")
        fields = BLOCK_FIELDS.get(btype) if isinstance(btype, str) else None
        if fields is None:
            return f"unknown block type '{btype}'"
        parts = path.split(".")
        head = parts[0]
        kind = fields.get(head)
        if kind is None:
            return f"field '{head}' is not valid on a {btype} block"
        return _validate_field_value(raw, block, head, kind, parts[1:], btype)

    if op == "set_design":
        block = by_id.get(_sid(raw.get("block")))
        if block is None:
            return "block id not found"
        if not premium:
            # `_design` is stripped on save for non-premium plans, so applying
            # it in-editor would look like it worked and then vanish.
            return "section design and animation are a Pro feature — upgrade to use them"
        group = _sid(raw.get("group"))
        spec = DESIGN_GROUPS.get(group) if group else None
        if spec is None:
            return f"unknown design group '{raw.get('group')}' — expected one of: {', '.join(sorted(DESIGN_GROUPS))}"
        key = _sid(raw.get("key"))
        if key is None or key not in spec:
            return f"'{raw.get('key')}' is not a {group} setting — expected one of: {', '.join(sorted(spec))}"
        return _design_value_error(raw.get("value"), spec[key], group, key)

    if op == "add_block":
        btype = _sid(raw.get("type"))
        if btype not in BLOCK_TYPES:
            return f"unknown block type '{raw.get('type')}'"
        at = raw.get("at")
        if not isinstance(at, int) or isinstance(at, bool):
            return "missing/invalid 'at' index"
        content = raw.get("content")
        if content is not None:
            if not isinstance(content, dict):
                return "'content' must be an object"
            allowed = BLOCK_FIELDS.get(btype, {})
            # Filter on field name AND value kind — `set_field` type-checks, so
            # without this the same bad value (e.g. a list field set to a
            # string) just walks in through add_block instead. Bad entries are
            # dropped rather than failing the op: the block still gets built
            # from schema defaults, which is more useful than no block at all.
            raw["content"] = {
                k: v for k, v in content.items()
                if k in allowed and _valid_field_value(v, allowed[k], btype, k)
            }
        return None

    if op == "remove_block":
        if _sid(raw.get("block")) not in by_id:
            return "block id not found"
        return None

    if op == "move_block":
        if _sid(raw.get("block")) not in by_id:
            return "block id not found"
        to = raw.get("to")
        if not isinstance(to, int) or isinstance(to, bool):
            return "missing/invalid 'to' index"
        return None

    if op == "set_theme":
        key = _sid(raw.get("key"))
        if not key:
            return "missing key"
        if key not in THEME_KEYS and not key.startswith(THEME_KEY_PREFIXES):
            return f"unknown theme key '{key}'"
        if key == "mode" and _sid(raw.get("value")) not in THEME_MODE_VALUES:
            return "mode must be 'light' or 'dark'"
        if key == "preset" and not theme_intent:
            # Switching preset replaces brand, fonts, radius and mode site-wide.
            # Firing that off a request that never mentioned themes is how a
            # "animate this text" turn silently restyled the whole site.
            return "won't switch the site theme unless you ask for a theme change directly"
        return None

    # Canvas ops all require the target block to exist and be a canvas block.
    bid = _sid(raw.get("block"))
    block = by_id.get(bid)
    if block is None:
        return "block id not found"
    if block.get("type") != "canvas":
        return "target block is not a canvas block"
    grid = _canvas_grid(block)
    mobile_grid = _canvas_grid(block, "mobile")

    if op == "canvas_add":
        element = raw.get("element")
        if not isinstance(element, dict):
            return "missing element"
        if _sid(element.get("kind")) not in CANVAS_ELEMENT_KINDS:
            return f"unknown element kind '{element.get('kind')}'"
        bad_pos = _check_positions(element, grid, mobile_grid)
        if bad_pos:
            return bad_pos
        if "style" in element:
            element["style"] = _filter_style(element.get("style"))
        if pending_canvas_count.get(bid, 0) >= CANVAS_MAX_ELEMENTS:
            return f"canvas already has the max of {CANVAS_MAX_ELEMENTS} elements"
        pending_canvas_count[bid] = pending_canvas_count.get(bid, 0) + 1
        return None

    if op == "canvas_update":
        els = {_sid(e.get("id")) for e in _canvas_elements(block)}
        if _sid(raw.get("el")) not in els:
            return "element id not found"
        patch = raw.get("patch")
        if not isinstance(patch, dict):
            return "missing patch"
        bad_pos = _check_positions(patch, grid, mobile_grid)
        if bad_pos:
            return bad_pos
        if "style" in patch:
            patch["style"] = _filter_style(patch.get("style"))
        # Whitelist patch keys: the client spreads this over the element, so an
        # `id` here can collide two elements (later ops then hit the wrong one)
        # and a `kind` the renderer doesn't whitelist drops the element from the
        # published page while it still shows in the editor.
        raw["patch"] = {k: v for k, v in patch.items() if k in CANVAS_PATCH_KEYS}
        return None

    if op == "canvas_remove":
        els = {_sid(e.get("id")) for e in _canvas_elements(block)}
        if _sid(raw.get("el")) not in els:
            return "element id not found"
        return None

    return f"unhandled op '{op}'"  # unreachable — op already checked against _OP_NAMES


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

{"message": "<one short sentence for the user, plain language>", "ops": [<op>, ...]}

Each op is one of:
{"op":"set_field","block":"<id>","path":"<fieldName>","value":<any>}
{"op":"set_design","block":"<id>","group":"motion"|"bg"|"layout"|"colors"|"border"|"anchor","key":"<setting>","value":<any>}
{"op":"add_block","type":"<blockType>","at":<index>,"content":{...fields...}}
{"op":"remove_block","block":"<id>"}
{"op":"move_block","block":"<id>","to":<index>}
{"op":"set_theme","key":"colors.brand"|"colors.accent"|"fonts.heading"|"fonts.body"|"radius"|"mode"|"preset","value":<any>}
{"op":"canvas_add","block":"<id>","element":{"kind":"heading"|"text"|"image"|"button","text"?,"src"?,"href"?,"d":{"x","y","w","h"},"style"?}}
{"op":"canvas_update","block":"<id>","el":"<elementId>","patch":{...any of text/src/alt/href/d/style...}}
{"op":"canvas_remove","block":"<id>","el":"<elementId>"}

Rules:
- NEVER substitute a different change for the one you were asked to make. If you cannot accomplish the request with the ops above, return an empty "ops" array and say plainly what you can't do. Doing something the user did not ask for is far worse than doing nothing.
- Your "message" must describe ONLY the ops you actually emitted. Never describe an effect you did not produce.
- Change only what was asked. Do not rewrite the user's copy, switch their theme, or restyle sections as a side effect of an unrelated request.
- Animation and per-section styling live in set_design, NOT in the theme. "Animate the heading" is {"op":"set_design","group":"motion","key":"heading","value":"shimmer"|"rise"}. Reveal-on-scroll is motion.effect. Never switch the site theme to satisfy an animation or styling request.
- Only use set_theme with key "preset" when the user explicitly asks to change their theme — it replaces their brand color, fonts, corners and light/dark mode site-wide.
- When the user says "this section", "here", or "it", they mean the SELECTED SECTION named below. If nothing is selected and the target is ambiguous, ask which section rather than guessing.
- Address blocks and canvas elements ONLY by the "id" values given to you below — never by position/index guessing.
- At most 20 ops per turn. Prefer editing an existing block over removing and recreating it.
- Never invent a block type or field name outside the catalog below.
- Canvas blocks are a 24-column grid (desktop); place elements with x+w <= 24, y increasing downward. A hero-like layout: eyebrow text near y=3 (small), a heading around y=5 (h=3), supporting text around y=9, one or two buttons around y=12.
- "value" for set_theme "mode" must be "light" or "dark".
- If the request is unclear or nothing needs to change, return an empty "ops" array with a clarifying "message".
- Output ONLY the JSON object. No markdown fences, no commentary.
"""
# NOTE: _SYSTEM_PROMPT is full of literal JSON braces — never run str.format()
# or an f-string over it (`{"message"...}` parses as a replacement field and
# raises KeyError). The catalog is concatenated below instead.


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
            else:
                rendered.append(f"{key}:{spec}")
        lines.append(f"- {group}: {', '.join(rendered)}")
    return "\n".join(lines)


def _build_prompt(
    *, message: str, history: list[dict[str, Any]], blocks: list[dict[str, Any]],
    theme: dict[str, Any], business_name: Optional[str], business_type: Optional[str],
    feedback: Optional[str], selected_block: Optional[str] = None,
) -> str:
    parts = [
        _SYSTEM_PROMPT,
        "Block catalog (type: allowed fields):\n" + _catalog_text(),
        "Section design catalog for set_design (group: settings):\n" + _design_catalog_text(),
    ]

    if business_name or business_type:
        parts.append(f"Site: {business_name or '(unnamed)'} — {business_type or 'general business'}")

    parts.append("Current blocks (JSON):\n" + json.dumps(blocks))
    parts.append("Current theme (JSON):\n" + json.dumps(theme))

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
    model = MODEL_TIERS[tier]
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
                        config=types.GenerateContentConfig(response_mime_type="application/json"),
                    ),
                    timeout=MERLIN_CALL_TIMEOUT,
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
            last_feedback = f"the previous attempt timed out after {MERLIN_CALL_TIMEOUT}s — respond more concisely"
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
