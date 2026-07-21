"""Merlin op registry — the single source of truth for the whitelisted ops.

Every Merlin capability (`set_field`, `set_design`, `add_block`, …) is one
`MerlinOp` entry below. An entry carries everything the three surfaces that
used to hand-sync per op now read from one place:

  - `validate`     — the per-op safety check (was a branch in `_validate_one`)
  - `prompt_shape` — the op's JSON-shape line for the model (was a literal in
                     `_SYSTEM_PROMPT`)
  - `prompt_rules` — op-specific guidance appended after the general rules

`validate_ops` is a generic loop over `OPS_BY_NAME`; adding an op is adding a
registry entry (+ its client-side applier in `merlinOps.ts`, which is behavior
and stays in TS). This mirrors the `ThreadMode` registry in
`app/matcha/services/matcha_work_modes.py`.

Validation philosophy is unchanged — skip-and-report, never raise for "the
model said something weird": each validator returns a reason string (dropping
that one op into `rejected`) or `None`. A validator may mutate `raw` in place
to strip unknown/structural keys; the caller still appends the cleaned `raw`.
"""
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .merlin_catalog import (
    AI_ASPECT_RATIOS,
    AI_IMAGE_PROMPT_MAX,
    BLOCK_FIELDS,
    BLOCK_TYPES,
    CANVAS_ELEMENT_KINDS,
    CANVAS_GRID_COLS,
    CANVAS_GRID_ROWS_MAX,
    CANVAS_MAX_ELEMENTS,
    CANVAS_MOBILE_GRID_COLS,
    CANVAS_PATCH_KEYS,
    CANVAS_STYLE_KEYS,
    COLUMN_BLOCK_TYPES,
    DESIGN_COLOR_TOKENS,
    DESIGN_GROUPS,
    LIST_KINDS,
    MAX_OPS_PER_TURN,
    SELECT_OPTIONS,
    TEXT_KINDS,
    THEME_KEY_PREFIXES,
    THEME_KEYS,
    THEME_MODE_VALUES,
)

from .section_presets import PRESETS_BY_KEY, SECTION_PRESETS
from .style_recipes import RECIPES_BY_KEY, STYLE_RECIPES
from .theme_presets import PRESET_IDS, THEME_PRESETS, font_pairings_text, preset_catalog_text

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# `layout.columns`/`columnsMd`/`columnsSm` only reach CSS on grid-shaped block
# types (see COLUMN_BLOCK_TYPES) — set_design/add_block/set_design_bulk all
# gate on this so "make the hero three columns" doesn't validate and report
# success while `--cz-cols` goes unread.
_COLUMN_DESIGN_KEYS = frozenset({"columns", "columnsMd", "columnsSm"})

# ---------------------------------------------------------------------------
# Low-level value helpers (moved verbatim from merlin.py — behavior-preserving)
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
        # A synthetic same-turn block (see _v_add_block) has no schema
        # defaults, so a real list field reads as length 0 here even though
        # the client will construct it with defaults — skip the bound for it;
        # the client still refuses an actual out-of-range index when it
        # applies the op for real.
        if idx > length and not block.get("_synthetic"):
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


def _is_valid_color(value: Any) -> bool:
    """A hex string OR a semantic theme token (DESIGN_COLOR_TOKENS) — tokens
    resolve through the theme's own var()/color-mix relationship, so they
    stay coherent on every theme by construction; a literal hex is a blind
    guess the model has no way to check against the theme it's editing."""
    return isinstance(value, str) and (bool(_HEX_COLOR_RE.match(value)) or value in DESIGN_COLOR_TOKENS)


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
        if not _is_valid_color(value):
            return f"'{key}' must be a hex color like #1a2b3c or a theme token ({', '.join(sorted(DESIGN_COLOR_TOKENS))})"
    elif spec == "text":
        if not isinstance(value, str):
            return f"'{key}' must be text"
    elif spec == "gradient":
        if not isinstance(value, dict):
            return f"'{key}' must be an object like {{\"angle\":135,\"stops\":[\"#111\",\"#eee\"]}}"
        stops = value.get("stops")
        if not isinstance(stops, list) or not (2 <= len(stops) <= 3) or not all(
            _is_valid_color(s) for s in stops
        ):
            return f"'{key}.stops' must be 2-3 hex colors or theme tokens like #1a2b3c or 'brand-soft'"
        angle = value.get("angle")
        if angle is not None:
            num = _num(angle)
            if num is None or not (0 <= num <= 360):
                return f"'{key}.angle' must be a number between 0 and 360"
    return None


def _filter_style(style: Any) -> dict[str, Any]:
    return {k: v for k, v in style.items() if k in CANVAS_STYLE_KEYS} if isinstance(style, dict) else {}


# ---------------------------------------------------------------------------
# Per-op validators
# ---------------------------------------------------------------------------
# Each takes (raw, ctx) and returns None (valid) or a rejection reason. Bodies
# are the exact branches that lived in merlin._validate_one — same order, same
# reason strings — so validate_ops behavior is byte-for-byte unchanged.

@dataclass
class ValidationCtx:
    """Everything a per-op validator reads beyond the op dict itself. Bundled so
    a new lane can add a field without re-threading every validator signature."""
    by_id: dict[str, dict[str, Any]]
    pending_canvas_count: dict[str, int]
    premium: bool = True
    theme_intent: bool = True


def _v_set_field(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    block = ctx.by_id.get(_sid(raw.get("block")))
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


def _v_set_design(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    block = ctx.by_id.get(_sid(raw.get("block")))
    if block is None:
        return "block id not found"
    if not ctx.premium:
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
    if group == "layout" and key in _COLUMN_DESIGN_KEYS and block.get("type") not in COLUMN_BLOCK_TYPES:
        return f"'{key}' has no effect on a {block.get('type')} block — only grid-shaped sections support columns"
    return _design_value_error(raw.get("value"), spec[key], group, key)


def _v_set_design_bulk(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    """Style many sections in one op — same premium gate and per-key cleaning
    as set_design, but targets a list of ids (or literal "all") instead of
    one block. Exists so "make everything dark and moody" costs 1 op instead
    of N × groups-changed, comfortably inside MAX_OPS_PER_TURN."""
    if not ctx.premium:
        return "section design and animation are a Pro feature — upgrade to use them"
    targets_raw = raw.get("blocks")
    if targets_raw == "all":
        target_ids = sorted(ctx.by_id)
    elif isinstance(targets_raw, list) and targets_raw:
        ids = [_sid(x) for x in targets_raw]
        if any(i is None for i in ids):
            return "'blocks' must be a list of block ids, or the literal \"all\""
        unknown = sorted({i for i in ids if i not in ctx.by_id})
        if unknown:
            return f"unknown block id(s): {', '.join(unknown)}"
        target_ids = ids
    else:
        return "'blocks' must be a non-empty list of block ids, or the literal \"all\""
    cleaned = _clean_design_bag(raw.get("design"))
    if not cleaned:
        return "'design' has no valid group/key/value entries"
    # Targets can be mixed block types, so (unlike add_block, which knows its
    # one block's type up front) this can't drop the columns keys per-target
    # inside _clean_design_bag — reject explicit instead of silently applying
    # to some targets and not others, same "don't silently drop" stance as
    # the unknown-id check above.
    if cleaned.get("layout", {}).keys() & _COLUMN_DESIGN_KEYS:
        non_grid = sorted(
            tid for tid in target_ids if ctx.by_id.get(tid, {}).get("type") not in COLUMN_BLOCK_TYPES
        )
        if non_grid:
            return f"columns has no effect on: {', '.join(non_grid)} — only grid-shaped sections support columns"
    raw["blocks"] = target_ids
    raw["design"] = cleaned
    return None


def _v_apply_style_recipe(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    """Expand a curated style recipe into a `set_design_bulk` op IN PLACE, then
    delegate to the real validator (same target-resolution, premium gate, and
    columns/mixed-type guard) — the `apply_section_preset` → `add_block` trick,
    for restyling instead of new-block content. The client only ever sees the
    expanded `set_design_bulk`; the recipe library never needs a TS mirror.
    deepcopy so downstream mutation of the op can't corrupt the shared recipe
    data. The original `recipe` key is kept as provenance."""
    recipe = RECIPES_BY_KEY.get(_sid(raw.get("recipe")))
    if recipe is None:
        return f"unknown style recipe '{raw.get('recipe')}' — expected one of: {', '.join(sorted(RECIPES_BY_KEY))}"
    raw["op"] = "set_design_bulk"
    raw["design"] = deepcopy(recipe.design)
    return _v_set_design_bulk(raw, ctx)


def _clean_design_bag(design: Any, btype: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Filter a raw `{group: {key: value}}` design bag down to entries valid
    against DESIGN_GROUPS — an invalid group/key/value is dropped rather than
    failing the whole op (a partially-styled result beats none). The caller
    decides whether an empty result should reject the op. Shared by add_block
    (a fresh block's optional `design`) and set_design_bulk (many sections at
    once) — same cleaning rules either way.

    `btype` additionally drops `layout.columns`/`columnsMd`/`columnsSm` when
    the (single, known-up-front) block type can't render them — same gate
    `_v_set_design` enforces by rejecting outright. Only add_block passes it;
    set_design_bulk's targets can be mixed types, so it gates separately."""
    if not isinstance(design, dict):
        return {}
    cleaned: dict[str, dict[str, Any]] = {}
    for group, keys in design.items():
        sg = _sid(group)
        spec = DESIGN_GROUPS.get(sg) if sg else None
        if spec is None or not isinstance(keys, dict):
            continue
        kept = {}
        for k, v in keys.items():
            sk = _sid(k)
            if not sk or sk not in spec or v is None or _design_value_error(v, spec[sk], sg, sk) is not None:
                continue  # nulls dropped too — nothing to clear on a brand-new block/target
            if sg == "layout" and sk in _COLUMN_DESIGN_KEYS and btype is not None and btype not in COLUMN_BLOCK_TYPES:
                continue
            kept[sk] = v
        if kept:
            cleaned[sg] = kept
    return cleaned


def _v_add_block(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
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
    design = raw.get("design")
    if design is not None:
        if not isinstance(design, dict) or not ctx.premium:
            # Non-premium: `_design` is stripped on save (gate_content), so
            # applying it in-editor would look styled and then silently vanish.
            # Drop the bag but keep the block — an unstyled section is more
            # useful than refusing the whole add (same philosophy as dropping
            # bad content entries above).
            raw.pop("design", None)
        else:
            cleaned = _clean_design_bag(design, btype)
            if cleaned:
                raw["design"] = cleaned
            else:
                raw.pop("design", None)
    raw_id = raw.get("id")
    if raw_id is not None:
        temp_id = _sid(raw_id)
        if temp_id is None:
            return "'id' must be a string"
        if temp_id in ctx.by_id:
            return f"id '{raw_id}' collides with an existing or already-added block"
        # Register a synthetic block so LATER ops in this same turn (set_field,
        # set_design, generate_image, move_block, canvas_*, duplicate_block,
        # remove_block) can resolve it before it's actually created client-side.
        # ctx.by_id is shared across the whole validate_ops loop, so this is
        # visible to every op validated after this one (not before — ops are
        # validated in order, same as the client applies them).
        # `_synthetic` marks this for `_validate_field_value`: unlike a real
        # snapshot block, this dict has only the explicit `content` fields —
        # no schema defaults — so a real list field (e.g. faq's `items`)
        # reads as length 0 even though the client will construct it with
        # defaults. Bound-checking a list index against that phantom length
        # rejected the flagship same-turn case ("add a section and fill it
        # in"); the marker tells that check to skip the bound here.
        synthetic: dict[str, Any] = {"id": temp_id, "type": btype, **(raw.get("content") or {}), "_synthetic": True}
        ctx.by_id[temp_id] = synthetic
        if btype == "canvas":
            ctx.pending_canvas_count[temp_id] = 0
    return None


def _v_apply_section_preset(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    """Expand a preset reference into a fully-populated add_block IN PLACE, then
    run it through the real add_block validator (same content filtering + the
    non-premium design strip). The client only ever sees the expanded add_block
    — the preset library never needs a TS mirror. deepcopy so downstream
    mutation of the op can't corrupt the shared library data. The original
    `preset` key is kept as provenance (client uses it in the apply summary)."""
    preset = PRESETS_BY_KEY.get(_sid(raw.get("preset")))
    if preset is None:
        return f"unknown preset '{raw.get('preset')}' — expected one of: {', '.join(sorted(PRESETS_BY_KEY))}"
    at = raw.get("at")
    if not isinstance(at, int) or isinstance(at, bool):
        return "missing/invalid 'at' index"
    raw["op"] = "add_block"
    raw["type"] = preset.block_type
    raw["content"] = deepcopy(preset.content)
    raw["design"] = deepcopy(preset.design)
    return _v_add_block(raw, ctx)


def _v_generate_image(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    """AI image generation targeting an existing block's image field. Validated
    server-side (block/field/prompt/aspect) but EXECUTED CLIENT-SIDE: generation
    is a slow async round-trip, and applyMerlinOps is a synchronous pure fold, so
    the client generates via POST /sites/{id}/generate-image then applies the URL
    as a follow-up set_field. Not premium-gated here — the endpoint's daily quota
    (free taste + paid headroom) is the cost guard, same as the editor button.

    Targets a block in `ctx.by_id`, which holds both real snapshot blocks and
    any synthetic same-turn adds `_v_add_block` registered under their model-
    given `id` — so a same-turn `add_block(id="new-1")` + `generate_image` on
    "new-1" resolves normally. An id no earlier op registered still degrades
    to 'block id not found'."""
    block = ctx.by_id.get(_sid(raw.get("block")))
    if block is None:
        return "block id not found"
    btype = block.get("type")
    fields = BLOCK_FIELDS.get(btype) if isinstance(btype, str) else None
    if fields is None:
        return f"unknown block type '{btype}'"
    field = _sid(raw.get("field")) or "image"
    if fields.get(field) != "image":
        return f"'{field}' is not an image field on a {btype} block"
    raw["field"] = field  # normalize the default so the client sees an explicit target
    prompt = raw.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return "missing image prompt"
    if len(prompt) > AI_IMAGE_PROMPT_MAX:
        return f"image prompt too long (max {AI_IMAGE_PROMPT_MAX} chars)"
    # Drop any present-but-invalid aspect (a non-string hallucination — 16, {} —
    # or an unknown ratio) so the service defaults it. Checking `_sid` alone
    # missed non-strings: they'd survive and 422 the client's typed request.
    aspect = raw.get("aspect")
    if aspect is not None and not (isinstance(aspect, str) and aspect in AI_ASPECT_RATIOS):
        raw.pop("aspect", None)
    return None


def _v_duplicate_block(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    if _sid(raw.get("block")) not in ctx.by_id:
        return "block id not found"
    at = raw.get("at")
    if at is not None and (not isinstance(at, int) or isinstance(at, bool)):
        return "invalid 'at' index"
    return None


def _v_remove_block(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    if _sid(raw.get("block")) not in ctx.by_id:
        return "block id not found"
    return None


def _v_move_block(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    if _sid(raw.get("block")) not in ctx.by_id:
        return "block id not found"
    to = raw.get("to")
    if not isinstance(to, int) or isinstance(to, bool):
        return "missing/invalid 'to' index"
    return None


def _v_set_theme(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    key = _sid(raw.get("key"))
    if not key:
        return "missing key"
    if key not in THEME_KEYS and not key.startswith(THEME_KEY_PREFIXES):
        return f"unknown theme key '{key}'"
    if key == "mode" and _sid(raw.get("value")) not in THEME_MODE_VALUES:
        return "mode must be 'light' or 'dark'"
    if key == "preset":
        if not ctx.theme_intent:
            # Switching preset replaces brand, fonts, radius and mode site-wide.
            # Firing that off a request that never mentioned themes is how a
            # "animate this text" turn silently restyled the whole site.
            return "won't switch the site theme unless you ask for a theme change directly"
        if _sid(raw.get("value")) not in PRESET_IDS:
            return f"unknown theme preset '{raw.get('value')}' — expected one of: {', '.join(sorted(PRESET_IDS))}"
    return None


def _resolve_canvas(raw: dict[str, Any], ctx: ValidationCtx) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Shared canvas-op preamble: the target block must exist and be a canvas.
    Returns (block, None) or (None, reason)."""
    block = ctx.by_id.get(_sid(raw.get("block")))
    if block is None:
        return None, "block id not found"
    if block.get("type") != "canvas":
        return None, "target block is not a canvas block"
    return block, None


def _v_canvas_add(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    block, reason = _resolve_canvas(raw, ctx)
    if reason:
        return reason
    bid = _sid(raw.get("block"))
    grid = _canvas_grid(block)
    mobile_grid = _canvas_grid(block, "mobile")
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
    if ctx.pending_canvas_count.get(bid, 0) >= CANVAS_MAX_ELEMENTS:
        return f"canvas already has the max of {CANVAS_MAX_ELEMENTS} elements"
    ctx.pending_canvas_count[bid] = ctx.pending_canvas_count.get(bid, 0) + 1
    return None


def _v_canvas_update(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    block, reason = _resolve_canvas(raw, ctx)
    if reason:
        return reason
    grid = _canvas_grid(block)
    mobile_grid = _canvas_grid(block, "mobile")
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


def _v_canvas_remove(raw: dict[str, Any], ctx: ValidationCtx) -> Optional[str]:
    block, reason = _resolve_canvas(raw, ctx)
    if reason:
        return reason
    els = {_sid(e.get("id")) for e in _canvas_elements(block)}
    if _sid(raw.get("el")) not in els:
        return "element id not found"
    return None


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MerlinOp:
    name: str                                            # op string + client applier key
    validate: Callable[[dict[str, Any], ValidationCtx], Optional[str]]
    # The op's JSON-shape line the model is shown (consumed by _build_prompt in
    # Phase 0.3). Kept as data here so the prompt can't drift from the validator.
    prompt_shape: str = ""
    # Op-specific guidance appended after the general rules block.
    prompt_rules: tuple[str, ...] = field(default_factory=tuple)


MERLIN_OPS: tuple[MerlinOp, ...] = (
    MerlinOp(
        name="set_field",
        validate=_v_set_field,
        prompt_shape='{"op":"set_field","block":"<id>","path":"<fieldName>","value":<any>}',
    ),
    MerlinOp(
        name="set_design",
        validate=_v_set_design,
        prompt_shape=(
            # Group order is the registry's declaration order (motion first — the
            # most-requested), NOT alphabetical, so the shape leads the model with
            # the common case. DESIGN_GROUPS preserves that insertion order.
            '{"op":"set_design","block":"<id>","group":"'
            + '"|"'.join(DESIGN_GROUPS)
            + '","key":"<setting>","value":<any>}'
        ),
        prompt_rules=(
            'Animation and per-section styling live in set_design, NOT in the theme. '
            '"Animate the heading" is {"op":"set_design","group":"motion","key":"heading","value":"shimmer"|"rise"}. '
            'Reveal-on-scroll is motion.effect. Never switch the site theme to satisfy an animation or styling request.',
            'bg.gradient only renders when bg.type is also "gradient" — set both in the same turn. '
            'bg.overlayOpacity only affects a bg.type of image or video (it needs bg-media to sit over).',
            'layout.columns/columnsMd/columnsSm only affect grid-shaped sections: '
            + ", ".join(sorted(COLUMN_BLOCK_TYPES))
            + ". Setting it on any other block type is rejected.",
        ),
    ),
    MerlinOp(
        name="set_design_bulk",
        validate=_v_set_design_bulk,
        prompt_shape=(
            '{"op":"set_design_bulk","blocks":["<id>",...]|"all","design":{"<group>":{"<key>":<value>}}}'
        ),
        prompt_rules=(
            'When styling 3+ sections the same way (e.g. "make everything dark and moody"), use ONE '
            'set_design_bulk instead of many set_design ops — "design" takes a whole bag of groups/keys '
            'applied to every section in "blocks" (or "all"). Same group/key/value rules as set_design. '
            'It can only SET values, not clear them (no null-clearing across many sections) — use set_design '
            'for that on a single section.',
        ),
    ),
    MerlinOp(
        name="apply_style_recipe",
        validate=_v_apply_style_recipe,
        prompt_shape='{"op":"apply_style_recipe","blocks":["<id>",...]|"all","recipe":"<recipeKey>"}',
        prompt_rules=(
            'For "make this look designed / polished / professional / premium", PREFER apply_style_recipe '
            'over hand-picking set_design values — a recipe is a professionally-authored, theme-portable '
            '(token-based) multi-key restyle in one op; freehand set_design values risk picking colors with '
            'no relationship to the theme (this is how a dark-on-dark gradient went invisible, and how a '
            'literal pattern color rendered as a bright wireframe-grid overlay). '
            'Available recipes: '
            + "; ".join(f"{r.key} — {r.blurb}" for r in STYLE_RECIPES)
            + ".",
        ),
    ),
    MerlinOp(
        name="add_block",
        validate=_v_add_block,
        prompt_shape='{"op":"add_block","type":"<blockType>","at":<index>,"content":{...fields...},"design":{...optional set_design groups/keys...},"id":"<optional short id, e.g. new-1>"}',
        prompt_rules=(
            'Give a new block an "id" (e.g. "new-1") when a LATER op in this same turn needs to target it — '
            'set_field, set_design, generate_image, move_block, canvas_add/update/remove, duplicate_block and '
            'remove_block can all address it by that id. The op giving it the id must come BEFORE any op using it.',
        ),
    ),
    MerlinOp(
        name="apply_section_preset",
        validate=_v_apply_section_preset,
        prompt_shape='{"op":"apply_section_preset","preset":"<presetName>","at":<index>,"id":"<optional short id, see add_block>"}',
        prompt_rules=(
            "Prefer apply_section_preset over hand-building add_block when the user asks for a new "
            "section without specifying detailed content — presets are professionally designed. "
            "Available presets: "
            + "; ".join(f"{p.key} ({p.block_type}) — {p.blurb}" for p in SECTION_PRESETS)
            + ".",
        ),
    ),
    MerlinOp(
        name="duplicate_block",
        validate=_v_duplicate_block,
        prompt_shape='{"op":"duplicate_block","block":"<id>","at":<index optional, default right after the source>}',
        prompt_rules=(
            "Use duplicate_block for \"copy/duplicate this section\" instead of hand-rebuilding it with "
            "add_block — it copies content AND design in one op.",
        ),
    ),
    MerlinOp(
        name="generate_image",
        validate=_v_generate_image,
        prompt_shape='{"op":"generate_image","block":"<id>","field":"<imageField>","prompt":"<what to depict>","aspect":"16:9"}',
        prompt_rules=(
            "generate_image creates an AI image and places it in a block's image field "
            "(field defaults to \"image\"; on a hero that's the full-bleed background). Use it when the "
            "user asks to generate/create/imagine a photo or background — NOT for stock the user will "
            "supply. Can target a block added earlier in this same turn if that add_block gave it an \"id\". "
            "aspect is one of: " + ", ".join(sorted(AI_ASPECT_RATIOS)) + ".",
        ),
    ),
    MerlinOp(
        name="remove_block",
        validate=_v_remove_block,
        prompt_shape='{"op":"remove_block","block":"<id>"}',
    ),
    MerlinOp(
        name="move_block",
        validate=_v_move_block,
        prompt_shape='{"op":"move_block","block":"<id>","to":<index>}',
    ),
    MerlinOp(
        name="set_theme",
        validate=_v_set_theme,
        prompt_shape=(
            '{"op":"set_theme","key":"colors.brand"|"colors.accent"|"fonts.heading"'
            '|"fonts.body"|"radius"|"mode"|"preset","value":<any>}'
        ),
        prompt_rules=(
            'Only use set_theme with key "preset" when the user explicitly asks to change their theme — '
            'it replaces their brand color, fonts, corners and light/dark mode site-wide.',
            '"value" for set_theme "mode" must be "light" or "dark".',
            "Available theme presets (id — description):\n" + preset_catalog_text(),
            "Good heading/body font pairings for fonts.heading + fonts.body: " + font_pairings_text() + ".",
        ),
    ),
    MerlinOp(
        name="canvas_add",
        validate=_v_canvas_add,
        prompt_shape=(
            '{"op":"canvas_add","block":"<id>","element":{"kind":"heading"|"text"|"image"|"button",'
            '"text"?,"src"?,"href"?,"d":{"x","y","w","h"},"style"?}}'
        ),
        prompt_rules=(
            'Canvas blocks are a 24-column grid (desktop); place elements with x+w <= 24, y increasing downward. '
            'A hero-like layout: eyebrow text near y=3 (small), a heading around y=5 (h=3), '
            'supporting text around y=9, one or two buttons around y=12.',
        ),
    ),
    MerlinOp(
        name="canvas_update",
        validate=_v_canvas_update,
        prompt_shape='{"op":"canvas_update","block":"<id>","el":"<elementId>","patch":{...any of text/src/alt/href/d/style...}}',
    ),
    MerlinOp(
        name="canvas_remove",
        validate=_v_canvas_remove,
        prompt_shape='{"op":"canvas_remove","block":"<id>","el":"<elementId>"}',
    ),
)

OPS_BY_NAME: dict[str, MerlinOp] = {op.name: op for op in MERLIN_OPS}
OP_NAMES: frozenset[str] = frozenset(OPS_BY_NAME)


# ---------------------------------------------------------------------------
# Machine-readable schema export
# ---------------------------------------------------------------------------
# One JSON view of the whole registry-derived surface, so a consumer (the editor,
# tooling, a drift test) can read the op/block/design/theme vocabulary from the
# server's single source of truth instead of hand-mirroring it. This is the
# mechanism that retires merlin_catalog.py's "hand-maintained mirror" role;
# wiring the frontend to consume it is a separate (client) stage.

def _spec_json(spec: Any) -> Any:
    """JSON-safe rendering of a value-spec: enum→sorted list, range→[lo,hi],
    kind-name→itself."""
    if isinstance(spec, frozenset):
        return {"enum": sorted(spec)}
    if isinstance(spec, tuple):
        return {"min": spec[0], "max": spec[1]}
    if spec == "gradient":
        return {
            "kind": "gradient", "stops": {"min": 2, "max": 3, "tokens": sorted(DESIGN_COLOR_TOKENS)},
            "angle": {"min": 0, "max": 360},
        }
    if spec == "color":
        return {"kind": "color", "tokens": sorted(DESIGN_COLOR_TOKENS)}
    return {"kind": spec}


def build_merlin_schema() -> dict[str, Any]:
    """Assemble the full Merlin schema from the registries + catalog. Pure and
    JSON-serializable."""
    from .merlin_catalog import (
        BLOCK_LABELS,
        CANVAS_ELEMENT_KINDS,
        CANVAS_GRID_COLS,
        CANVAS_MAX_ELEMENTS,
        CANVAS_MOBILE_GRID_COLS,
        THEME_KEY_PREFIXES,
        THEME_KEYS,
        THEME_MODE_VALUES,
    )

    blocks: dict[str, Any] = {}
    for btype in sorted(BLOCK_TYPES):
        fields = BLOCK_FIELDS.get(btype, {})
        opts = SELECT_OPTIONS.get(btype, {})
        blocks[btype] = {
            "label": BLOCK_LABELS.get(btype, btype),
            "fields": {
                name: {"kind": kind, **({"options": sorted(opts[name])} if name in opts else {})}
                for name, kind in sorted(fields.items())
            },
        }

    return {
        "ops": [{"name": op.name, "shape": op.prompt_shape} for op in MERLIN_OPS],
        "blocks": blocks,
        "design": {
            group: {key: _spec_json(spec) for key, spec in sorted(keys.items())}
            for group, keys in sorted(DESIGN_GROUPS.items())
        },
        "theme": {
            "keys": sorted(THEME_KEYS),
            "prefixes": list(THEME_KEY_PREFIXES),
            "modes": sorted(THEME_MODE_VALUES),
        },
        "sectionPresets": [
            {"name": p.key, "label": p.label, "blurb": p.blurb, "blockType": p.block_type}
            for p in SECTION_PRESETS
        ],
        "themePresets": [
            {"id": p.id, "name": p.name, "blurb": p.blurb, "premium": p.premium, "mode": p.mode}
            for p in THEME_PRESETS
        ],
        "styleRecipes": [
            {"key": r.key, "label": r.label, "blurb": r.blurb} for r in STYLE_RECIPES
        ],
        "imageGen": {
            "aspectRatios": sorted(AI_ASPECT_RATIOS),
            "promptMax": AI_IMAGE_PROMPT_MAX,
        },
        "limits": {
            "maxOpsPerTurn": MAX_OPS_PER_TURN,
            "canvas": {
                "elementKinds": sorted(CANVAS_ELEMENT_KINDS),
                "maxElements": CANVAS_MAX_ELEMENTS,
                "gridCols": CANVAS_GRID_COLS,
                "mobileGridCols": CANVAS_MOBILE_GRID_COLS,
            },
        },
    }


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
    ctx = ValidationCtx(
        by_id=by_id, pending_canvas_count=pending_canvas_count,
        premium=premium, theme_intent=theme_intent,
    )

    for raw in raw_ops:
        if not isinstance(raw, dict):
            rejected.append({"op": {"op": str(raw)}, "reason": "op was not a JSON object"})
            continue
        op = OPS_BY_NAME.get(raw.get("op"))
        if op is None:
            rejected.append({"op": raw, "reason": f"unknown op '{raw.get('op')}'"})
            continue

        reason = op.validate(raw, ctx)
        if reason:
            rejected.append({"op": raw, "reason": reason})
        else:
            valid.append(raw)

    return valid, rejected
