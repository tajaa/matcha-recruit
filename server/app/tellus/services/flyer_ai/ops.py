"""Flyer op registry — the whitelist of everything the assistant may do.

One `FlyerOp` entry per capability, carrying the three things that used to drift
apart when they lived in three files: the validator, the JSON shape shown to the
model, and the op-specific prose rules. `validate_ops` is a generic loop over
`OPS_BY_NAME`, so adding a capability is adding an entry here (plus its arm in
`apply.py`). Mirrors `cappe/services/merlin/ops.py`.

Validation philosophy, also borrowed: **skip and report, never raise.** A
validator returns a reason string (dropping that one op into `rejected`) or
None. A model saying something strange must cost one op, not the whole turn.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .catalog import (
    ADDABLE_LAYER_KINDS,
    ARTBOARD_PRESETS,
    DESIGN_MAX_BYTES,
    FIELDS_BY_KIND,
    MAX_OPS_PER_TURN,
    MAX_TEXT_LEN,
    MIN_QR_CONTRAST,
    PALETTE_TOKENS,
    contrast_ratio,
    is_color,
    resolve_color,
)
from .layouts import LAYOUTS_BY_KEY
from .palettes import PALETTES_BY_KEY

# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _sid(value: Any) -> Optional[str]:
    """Model-supplied ids are used as dict keys, and a hallucinated dict or list
    there raises `TypeError: unhashable type` — which would escape the
    never-raises contract and 500 the whole turn over one bad op. Everything
    that gets looked up goes through here first."""
    return value if isinstance(value, str) else None


def _num(value: Any) -> Optional[float]:
    """A real number. `bool` is excluded explicitly — `True` is an `int` in
    Python, so `{"x": true}` would otherwise validate as a coordinate."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int(value: Any) -> Optional[int]:
    n = _num(value)
    return None if n is None else int(round(n))


def layer_box(layer: dict[str, Any]) -> tuple[float, float]:
    """The layer's occupied box in artboard units. Mirrors
    utils/designer.ts:layerBox — a text layer's height is derived, not stored."""
    kind = layer.get("type")
    if kind == "qr":
        size = _num(layer.get("size")) or 0
        return size, size
    if kind == "text":
        return (
            _num(layer.get("width")) or 0,
            (_num(layer.get("fontSize")) or 0) * (_num(layer.get("lineHeight")) or 1),
        )
    return _num(layer.get("width")) or 0, _num(layer.get("height")) or 0


def _in_bounds(x: float, y: float, box: tuple[float, float], artboard: dict[str, Any]) -> bool:
    """Both axes, both edges. The renderer clips to the artboard, so a layer
    placed outside it is invisible and recoverable only by undo — the model gets
    no feedback that its edit did nothing."""
    w = _num(artboard.get("w")) or 0
    h = _num(artboard.get("h")) or 0
    return x >= 0 and y >= 0 and x + box[0] <= w and y + box[1] <= h


def _check_value(field_name: str, value: Any, spec: Any) -> Optional[str]:
    if spec == "color":
        return None if is_color(value) else f"{field_name} must be a palette token or a hex colour"
    if spec == "bool":
        return None if isinstance(value, bool) else f"{field_name} must be true or false"
    if spec == "text":
        if not isinstance(value, str):
            return f"{field_name} must be text"
        if len(value) > MAX_TEXT_LEN:
            return f"{field_name} is longer than {MAX_TEXT_LEN} characters"
        return None
    if isinstance(spec, frozenset):
        return None if value in spec else f"{field_name} must be one of: {', '.join(sorted(spec))}"
    if isinstance(spec, tuple):
        n = _num(value)
        if n is None:
            return f"{field_name} must be a number"
        if not (spec[0] <= n <= spec[1]):
            return f"{field_name} must be between {spec[0]} and {spec[1]}"
        return None
    return f"{field_name} has no known value spec"


def _qr_contrast_reason(fg: Any, bg: Any, palette: Optional[dict[str, Any]]) -> Optional[str]:
    """A QR whose modules don't contrast with their quiet zone is a flyer that
    looks finished and scans as nothing. This is the one place where a colour
    choice is a correctness question rather than a taste one."""
    try:
        ratio = contrast_ratio(resolve_color(palette, str(fg)), resolve_color(palette, str(bg)))
    except (ValueError, TypeError):
        return "QR colours could not be read"
    if ratio < MIN_QR_CONTRAST:
        return (
            f"QR foreground and background contrast is too low ({ratio:.1f}:1); "
            f"a printed code needs at least {MIN_QR_CONTRAST}:1 to scan"
        )
    return None


# ---------------------------------------------------------------------------
# Validation context
# ---------------------------------------------------------------------------


@dataclass
class OpContext:
    """Threaded through every validator. `layers` is a LIVE projection of the
    document as the turn's ops would leave it — an op that adds a layer registers
    it here so a later op in the same turn can address it, and one that removes a
    layer unregisters it so a later op can't. Without that, a perfectly coherent
    two-op sequence ("add a headline, then colour it") half-fails."""
    design: dict[str, Any]
    layers: dict[str, dict[str, Any]]
    order: list[str]
    campaign: Optional[dict[str, Any]] = None

    @property
    def artboard(self) -> dict[str, Any]:
        got = self.design.get("artboard")
        return got if isinstance(got, dict) else {"w": 0, "h": 0}

    @property
    def palette(self) -> Optional[dict[str, Any]]:
        got = self.design.get("palette")
        return got if isinstance(got, dict) else None

    def qr_ids(self) -> list[str]:
        return [lid for lid in self.order if self.layers.get(lid, {}).get("type") == "qr"]


# ---------------------------------------------------------------------------
# Per-op validators
# ---------------------------------------------------------------------------


def _v_set_layer(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    lid = _sid(raw.get("layer"))
    layer = ctx.layers.get(lid) if lid else None
    if layer is None:
        return "no layer with that id"
    kind = layer.get("type")
    path = raw.get("path")
    if not isinstance(path, str):
        return "path must be a field name"
    spec = FIELDS_BY_KIND.get(kind, {}).get(path)
    if spec is None:
        return f"{kind} layers have no '{path}' field"
    reason = _check_value(path, raw.get("value"), spec)
    if reason:
        return reason
    if kind == "qr" and path in ("fg", "bg"):
        other = "bg" if path == "fg" else "fg"
        pair = {path: raw.get("value"), other: layer.get(other)}
        return _qr_contrast_reason(pair["fg"], pair["bg"], ctx.palette)
    return None


def _v_move_layer(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    lid = _sid(raw.get("layer"))
    layer = ctx.layers.get(lid) if lid else None
    if layer is None:
        return "no layer with that id"
    x, y = _int(raw.get("x")), _int(raw.get("y"))
    if x is None or y is None:
        return "x and y must be numbers"
    if not _in_bounds(x, y, layer_box(layer), ctx.artboard):
        return "that position puts the layer outside the page"
    raw["x"], raw["y"] = x, y
    return None


def _v_resize_layer(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    lid = _sid(raw.get("layer"))
    layer = ctx.layers.get(lid) if lid else None
    if layer is None:
        return "no layer with that id"
    kind = layer.get("type")
    w = _int(raw.get("width"))
    h = _int(raw.get("height"))
    if w is None and h is None:
        return "width or height must be given"
    if kind == "qr":
        size = w or h or 0
        reason = _check_value("size", size, FIELDS_BY_KIND["qr"]["size"])
        if reason:
            return reason
        box = (float(size), float(size))
    else:
        w = w if w is not None else int(layer_box(layer)[0])
        h = h if h is not None else int(layer_box(layer)[1])
        for name, value in (("width", w), ("height", h)):
            spec = FIELDS_BY_KIND.get(kind, {}).get(name)
            if spec is not None:
                reason = _check_value(name, value, spec)
                if reason:
                    return reason
        box = (float(w), float(h))
    x = _num(layer.get("x")) or 0
    y = _num(layer.get("y")) or 0
    if not _in_bounds(x, y, box, ctx.artboard):
        return "that size pushes the layer off the page"
    return None


def _v_add_layer(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    kind = raw.get("kind")
    if kind not in ADDABLE_LAYER_KINDS:
        return f"kind must be one of: {', '.join(sorted(ADDABLE_LAYER_KINDS))}"
    specs = FIELDS_BY_KIND[kind]
    layer: dict[str, Any] = {"type": kind}
    for name, value in list(raw.items()):
        if name in ("op", "kind", "id"):
            continue
        spec = specs.get(name)
        if spec is None:
            # Strip rather than reject: an extra key is the model being
            # verbose, not the edit being wrong.
            raw.pop(name, None)
            continue
        reason = _check_value(name, value, spec)
        if reason:
            return reason
        layer[name] = value
    for required in _REQUIRED_ON_ADD.get(kind, ()):
        if required not in layer:
            return f"a new {kind} layer needs {required}"
    x, y = _int(raw.get("x")), _int(raw.get("y"))
    if x is None or y is None:
        return "x and y must be numbers"
    layer.setdefault("lineHeight", 1.2)
    if not _in_bounds(x, y, layer_box(layer), ctx.artboard):
        return "that position puts the new layer outside the page"
    if kind == "qr":
        reason = _qr_contrast_reason(layer.get("fg", "#17140f"), layer.get("bg", "#ffffff"), ctx.palette)
        if reason:
            return reason
    temp = _sid(raw.get("id"))
    if temp:
        # Register under the model's temp id so a later op this turn resolves.
        ctx.layers[temp] = {**layer, "x": x, "y": y, "id": temp}
        ctx.order.append(temp)
    return None


_REQUIRED_ON_ADD: dict[str, tuple[str, ...]] = {
    "text": ("text", "fontSize", "width"),
    "shape": ("shape", "width", "height", "fill"),
    "sticker": ("assetId", "width", "height"),
    "qr": ("size",),
}


def _v_remove_layer(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    lid = _sid(raw.get("layer"))
    layer = ctx.layers.get(lid) if lid else None
    if layer is None or lid is None:
        return "no layer with that id"
    # The domain's one hard invariant. Everything else on a flyer is taste; the
    # claim QR is the only reason the flyer exists, and a printed run without it
    # is unrecoverable in a way an ugly headline is not.
    if layer.get("type") == "qr" and len(ctx.qr_ids()) <= 1:
        return "this is the flyer's only claim QR — removing it would leave nothing to scan"
    ctx.layers.pop(lid, None)
    if lid in ctx.order:
        ctx.order.remove(lid)
    return None


def _v_reorder_layer(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    lid = _sid(raw.get("layer"))
    if not lid or lid not in ctx.layers:
        return "no layer with that id"
    to = _int(raw.get("to"))
    if to is None or to < 0 or to >= max(1, len(ctx.order)):
        return f"'to' must be between 0 and {max(0, len(ctx.order) - 1)}"
    raw["to"] = to
    return None


def _v_set_background(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    return None if is_color(raw.get("value")) else "value must be a palette token or a hex colour"


def _v_set_palette(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    """Rewritten in place into `set_palette_values`, the same trick
    `merlin.ops._v_apply_style_recipe` uses: the applier only ever sees the
    concrete form, so the preset library never has to exist downstream."""
    preset = PALETTES_BY_KEY.get(_sid(raw.get("preset")) or "")
    if preset is None:
        return f"unknown palette; choose one of: {', '.join(sorted(PALETTES_BY_KEY))}"
    raw.clear()
    raw["op"] = "set_palette_values"
    raw["palette"] = dict(preset.colors)
    return None


def _v_set_palette_values(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    palette = raw.get("palette")
    if not isinstance(palette, dict):
        return "palette must be an object of token -> colour"
    if set(palette) != set(PALETTE_TOKENS):
        return f"palette must define exactly: {', '.join(PALETTE_TOKENS)}"
    for token, value in palette.items():
        if not (isinstance(value, str) and value.startswith("#") and is_color(value)):
            return f"{token} must be a hex colour"
    return None


def _v_apply_layout(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    """Rewritten into `set_document` — same expansion trick as set_palette."""
    layout = LAYOUTS_BY_KEY.get(_sid(raw.get("layout")) or "")
    if layout is None:
        return f"unknown layout; choose one of: {', '.join(sorted(LAYOUTS_BY_KEY))}"
    if not ctx.campaign:
        return "layouts are unavailable in this context"
    palette_key = _sid(raw.get("palette")) or ""
    preset = PALETTES_BY_KEY.get(palette_key)
    colors = dict(preset.colors) if preset else (ctx.palette or dict(PALETTES_BY_KEY["warm-paper"].colors))
    document = layout.build(ctx.campaign, colors)
    raw.clear()
    raw["op"] = "set_document"
    raw["design"] = document
    return _v_set_document(raw, ctx)


def _v_set_document(raw: dict[str, Any], ctx: OpContext) -> Optional[str]:
    document = raw.get("design")
    reason = validate_document(document)
    if reason:
        return reason
    # Rebase the context onto the new document: ops after a whole-document
    # replacement must be checked against what it contains, not what it replaced.
    ctx.design = document
    ctx.layers = {layer["id"]: layer for layer in document["layers"]}
    ctx.order = [layer["id"] for layer in document["layers"]]
    return None


def validate_document(document: Any) -> Optional[str]:
    """Full-document check, used by `set_document` and by the layout drift-gate.

    The byte cap is deliberately re-applied here rather than only at the route:
    the human PUT path enforces it, so a model output that skipped it would make
    the assistant the way around a limit the save path imposes."""
    import json

    if not isinstance(document, dict):
        return "design must be an object"
    artboard = document.get("artboard")
    if not isinstance(artboard, dict) or artboard.get("preset") not in ARTBOARD_PRESETS:
        return f"artboard.preset must be one of: {', '.join(sorted(ARTBOARD_PRESETS))}"
    w, h = ARTBOARD_PRESETS[artboard["preset"]]
    if _int(artboard.get("w")) != w or _int(artboard.get("h")) != h:
        return f"artboard size must be {w}x{h} for preset {artboard['preset']}"
    background = document.get("background")
    if not isinstance(background, dict) or background.get("kind") != "color" or not is_color(background.get("color")):
        return "background must be a colour"
    palette = document.get("palette")
    if palette is not None:
        holder = {"op": "set_palette_values", "palette": palette}
        reason = _v_set_palette_values(holder, OpContext(design={}, layers={}, order=[]))
        if reason:
            return reason
    layers = document.get("layers")
    if not isinstance(layers, list):
        return "layers must be a list"
    seen: set[str] = set()
    for layer in layers:
        if not isinstance(layer, dict):
            return "every layer must be an object"
        lid = _sid(layer.get("id"))
        if not lid or lid in seen:
            return "every layer needs a unique id"
        seen.add(lid)
        kind = layer.get("type")
        specs = FIELDS_BY_KIND.get(kind)
        if specs is None:
            return f"unknown layer type '{kind}'"
        for name, value in layer.items():
            if name in ("id", "type", "src", "slot", "assetId"):
                continue
            spec = specs.get(name)
            if spec is None:
                continue
            reason = _check_value(name, value, spec)
            if reason:
                return reason
        x = _num(layer.get("x"))
        y = _num(layer.get("y"))
        if x is None or y is None:
            return "every layer needs numeric x and y"
        if not _in_bounds(x, y, layer_box(layer), artboard):
            return f"a {kind} layer sits outside the page"
        if kind == "qr":
            reason = _qr_contrast_reason(layer.get("fg"), layer.get("bg"), palette)
            if reason:
                return reason
    if not any(layer.get("type") == "qr" for layer in layers):
        return "the design must include a claim QR"
    if len(json.dumps(document).encode()) > DESIGN_MAX_BYTES:
        return "the design is too large to save"
    return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlyerOp:
    name: str
    validate: Callable[[dict[str, Any], OpContext], Optional[str]]
    prompt_shape: str
    prompt_rules: tuple[str, ...] = field(default_factory=tuple)


FLYER_OPS: tuple[FlyerOp, ...] = (
    FlyerOp(
        "set_layer", _v_set_layer,
        '{"op":"set_layer","layer":"<id>","path":"<field>","value":<value>}',
        ("set_layer changes ONE field of ONE layer — use it for copy, colour, size, alignment. "
         "The field must exist on that layer's kind (see the layer catalog).",),
    ),
    FlyerOp(
        "move_layer", _v_move_layer,
        '{"op":"move_layer","layer":"<id>","x":<int>,"y":<int>}',
        ("Coordinates are the layer's TOP-LEFT corner in artboard units, and the whole layer must "
         "stay on the page — an off-page layer is invisible, not subtle.",),
    ),
    FlyerOp(
        "resize_layer", _v_resize_layer,
        '{"op":"resize_layer","layer":"<id>","width":<int>,"height":<int>}',
        ("For a QR layer pass width only — it is always square. To make TEXT bigger set its "
         "fontSize with set_layer instead; resizing a text layer only changes its wrap width.",),
    ),
    FlyerOp(
        "add_layer", _v_add_layer,
        '{"op":"add_layer","kind":"text|shape|sticker|qr","id":"new-1","x":<int>,"y":<int>,...fields}',
        ('"id" is a temporary name you choose (e.g. "new-1") so a LATER op in this same turn can '
         "target the layer you just added. You cannot add an image layer — the brand's logo is "
         "placed by the person, not by you.",),
    ),
    FlyerOp(
        "remove_layer", _v_remove_layer,
        '{"op":"remove_layer","layer":"<id>"}',
        ("You may never remove the flyer's only claim QR. If the person asks you to, refuse and "
         "explain that the QR is the only thing on the page a customer can act on.",),
    ),
    FlyerOp(
        "reorder_layer", _v_reorder_layer,
        '{"op":"reorder_layer","layer":"<id>","to":<index>}',
        ("Index 0 is the BACK of the stack; the last index is the front. Use this to put a "
         "background shape behind text rather than moving the text.",),
    ),
    FlyerOp(
        "set_background", _v_set_background,
        '{"op":"set_background","value":"<token|#hex>"}',
        (),
    ),
    FlyerOp(
        "set_palette", _v_set_palette,
        '{"op":"set_palette","preset":"<palette key>"}',
        ('This is the right answer to "make it warmer / darker / calmer / bolder" — one op '
         "restyles every layer that named a token, coherently. Prefer it over recolouring "
         "layers one at a time.",),
    ),
    FlyerOp(
        "set_palette_values", _v_set_palette_values,
        '{"op":"set_palette_values","palette":{"ink":"#hex","paper":"#hex","brand":"#hex","brandSoft":"#hex","accent":"#hex","muted":"#hex"}}',
        ("Only use this when the person asks for a specific colour no preset covers. A preset is "
         "almost always the better answer.",),
    ),
    FlyerOp(
        "apply_layout", _v_apply_layout,
        '{"op":"apply_layout","layout":"<layout key>","palette":"<palette key>"}',
        ("This REPLACES the whole page with a professionally-composed one, keeping the campaign's "
         'own words. Use it for "design me something" or "start over", never for a small edit.',),
    ),
    FlyerOp("set_document", _v_set_document, "", ()),
)

OPS_BY_NAME: dict[str, FlyerOp] = {op.name: op for op in FLYER_OPS}


def op_shapes_text() -> str:
    return "Each op is one of:\n" + "\n".join(op.prompt_shape for op in FLYER_OPS if op.prompt_shape)


def op_rules_text() -> list[str]:
    rules: list[str] = []
    for op in FLYER_OPS:
        rules.extend(op.prompt_rules)
    return rules


def validate_ops(
    raw_ops: Any,
    design: dict[str, Any],
    campaign: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """-> (valid, rejected). Never raises."""
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if not isinstance(raw_ops, list):
        return valid, rejected

    layers = {
        layer["id"]: layer
        for layer in (design.get("layers") or [])
        if isinstance(layer, dict) and isinstance(layer.get("id"), str)
    }
    ctx = OpContext(
        design=design,
        layers=deepcopy(layers),
        order=list(layers.keys()),
        campaign=campaign,
    )

    for entry in raw_ops:
        if len(valid) >= MAX_OPS_PER_TURN:
            # Reported, never silent: a truncated turn that says nothing reads
            # as "everything applied".
            rejected.append({"op": entry if isinstance(entry, dict) else {"op": "?"},
                             "reason": f"more than {MAX_OPS_PER_TURN} changes in one turn"})
            continue
        if not isinstance(entry, dict):
            rejected.append({"op": {"op": "?"}, "reason": "each op must be an object"})
            continue
        name = entry.get("op")
        spec = OPS_BY_NAME.get(name) if isinstance(name, str) else None
        if spec is None:
            rejected.append({"op": entry, "reason": f"unknown op '{name}'"})
            continue
        raw = deepcopy(entry)
        try:
            reason = spec.validate(raw, ctx)
        except Exception as exc:  # noqa: BLE001 — never-raises contract
            reason = f"could not be applied ({type(exc).__name__})"
        if reason:
            rejected.append({"op": entry, "reason": reason})
            continue
        valid.append(raw)
    return valid, rejected
