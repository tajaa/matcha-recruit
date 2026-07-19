"""Design-vocabulary registry — single source of truth for the `_design` bag.

One `DesignKey` per per-section design setting. An entry has two facets that
used to live in two files and drift:

  - `merlin_spec` — the value-spec the AI (`merlin_ops`) is allowed to emit for
    this key (a frozenset enum / (min,max) int range / "bool"/"color"/"text"),
    or `None` if the key is renderer-only and not AI-settable. `DESIGN_GROUPS`
    (the catalog Merlin validates + prompts against) is DERIVED from these, so
    the AI surface can't drift from the registry.

  - `render` — a *declarative* rule for how the key becomes CSS in the public
    renderer (`render._apply_design`). Data, not a callable, so this module has
    no dependency on `render.py` (which imports it) — no circular import. The
    renderer executes the rule with its own sanitizers (`_hexonly`/`_clampi`).
    `render=None` means the key's emission is bespoke/coupled (motion effects,
    background media, the padTop px-override sentinel, …) and stays hand-written
    in `_apply_design`; the registry still records the key so the vocabulary is
    complete and the parity test can assert every AI key is honored.

Deliberate subset vs superset: the renderer honors MORE than the AI may set
(e.g. `type.headingSize`, `layout.columns`, `bg.gradient`). Those carry
`merlin_spec=None`. This asymmetry is intentional — a human in DesignInspector
has the full surface; the AI gets a curated, conservative slice.

Adding a design capability is adding a `DesignKey` here (+ a client applier in
merlinOps.ts, which is behavior). Mirrors the `ThreadMode` /`MerlinOp`
registries elsewhere in this codebase.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

# --- value-spec constants (shared by the AI subset) --------------------------
# Transcribed to match the historical merlin_catalog.DESIGN_GROUPS exactly; the
# derivation test asserts byte-equality, so these are the AI-facing specs (which
# are intentionally looser/tighter than the renderer's own clamps in places).
_MOTION_EFFECT = frozenset({
    "none", "fade", "slide-up", "slide-down", "slide-left", "slide-right",
    "zoom", "blur-in", "flip", "rotate", "mask-up", "bounce",
    "fade-up", "fade-down", "scale-up", "blur-up",
})
_MOTION_HEADING = frozenset({"none", "rise", "shimmer"})
_MOTION_HOVER = frozenset({"none", "lift", "tilt", "glow", "grow", "sink"})
_MOTION_LOOP = frozenset({"none", "float", "pulse", "sway", "breathe"})
# Reveal-transition easing (motion.easing → --cz-ease). No "none" — clearing is
# value=null; unset falls back to the renderer's default curve.
_MOTION_EASING = frozenset({"smooth", "gentle", "spring", "snappy", "linear"})
_BG_TYPE = frozenset({"none", "color", "gradient", "image", "video"})
_BG_OVERLAY = frozenset({"none", "light", "medium", "dark"})
_LAYOUT_ALIGN = frozenset({"default", "left", "center"})
_LAYOUT_MAXW = frozenset({"default", "narrow", "wide", "full"})
_LAYOUT_MINH = frozenset({"default", "tall", "screen"})


@dataclass(frozen=True)
class RenderRule:
    """Declarative emission for a self-contained design key. `_apply_design`
    interprets it; the rule references css-var names / classes only, never code.

      - kind "hex"    : sanitize value as a hex color; if non-empty emit
                        `{var}:{value}` (+ each of `extra_vars`) and, if set,
                        add `css_class`.
      - kind "int_px" : clamp value to [lo, hi]; emit `{var}:{n}px` (+ optional
                        `css_class`). By default a value that clamps to 0 is
                        treated as "unset" and emits nothing (safe only for
                        tokens whose `lo` > 0 — a present 0 clamps up to `lo`,
                        so 0 never survives to mean "off"). Set `allow_zero=True`
                        for a token where 0 is a real value (e.g. a spacing/gap
                        token with `lo=0`): then an absent/non-numeric key is
                        "unset" (skipped) but an explicit 0 emits `0px`.

    Both emit nothing on an unset/empty result — the `_BASE_CSS` `var(--x, …)`
    fallback then applies, so an unset key renders byte-identically to before.
    """
    kind: str
    var: str
    css_class: Optional[str] = None
    extra_vars: tuple[str, ...] = ()
    lo: int = 0
    hi: int = 0
    # int_px only: distinguish an explicit 0 from "unset" (see class docstring).
    allow_zero: bool = False


@dataclass(frozen=True)
class DesignKey:
    group: str
    key: str
    # AI value-spec, or None if renderer-only (not offered to Merlin).
    merlin_spec: Any = None
    # Declarative renderer emission, or None if bespoke/coupled in _apply_design.
    render: Optional[RenderRule] = None
    note: str = ""

    @property
    def merlin_settable(self) -> bool:
        return self.merlin_spec is not None


# --- the registry ------------------------------------------------------------
# Order within a group is the emission order the renderer uses (load-bearing for
# byte-identical output where `render` is set).

DESIGN_KEYS: tuple[DesignKey, ...] = (
    # ── motion (all bespoke: effects couple to delay/dur/stagger attrs) ──
    DesignKey("motion", "effect", _MOTION_EFFECT, note="cz-rv--{effect} + data-cz-delay/dur"),
    DesignKey("motion", "heading", _MOTION_HEADING, note="cz-bh-{heading}"),
    DesignKey("motion", "hover", _MOTION_HOVER, note="cz-hover-{hover}"),
    DesignKey("motion", "loop", _MOTION_LOOP, note="cz-loop-{loop}"),
    DesignKey("motion", "delay", (0, 2000), note="data-cz-delay (with effect)"),
    DesignKey("motion", "duration", (100, 2000), note="data-cz-dur (with effect)"),
    DesignKey("motion", "parallaxStrength", (0, 80), note="data-cz-parallax (with parallax)"),
    DesignKey("motion", "stagger", "bool", note="cz-rv--stagger"),
    DesignKey("motion", "parallax", "bool", note="cz-parallax"),
    DesignKey("motion", "kenburns", "bool", note="cz-kenburns"),
    DesignKey("motion", "easing", _MOTION_EASING, note="--cz-ease reveal timing-function"),
    # ── background (bespoke: type-dispatched media injection + overlay) ──
    DesignKey("bg", "type", _BG_TYPE),
    DesignKey("bg", "overlay", _BG_OVERLAY),
    DesignKey("bg", "color", "color"),
    DesignKey("bg", "image", "text"),
    DesignKey("bg", "video", "text"),
    DesignKey("bg", "blur", "bool", note="AI sees bool; renderer clamps 0-40"),
    # ── layout (bespoke: px-override sentinel, columns→repeat template) ──
    DesignKey("layout", "align", _LAYOUT_ALIGN, note="cz-al-{left|center}"),
    DesignKey("layout", "maxWidth", _LAYOUT_MAXW, note="--cz-maxw + cz-has-maxw"),
    DesignKey("layout", "minHeight", _LAYOUT_MINH, note="--cz-minh + cz-has-minh"),
    DesignKey("layout", "padTop", "text", note="_PAD_SCALE enum or padTopPx override"),
    DesignKey("layout", "padBottom", "text", note="_PAD_SCALE enum or padBottomPx override"),
    # ── colors (self-contained: registry-driven emission) ──
    DesignKey("colors", "text", "color", render=RenderRule("hex", "--cz-text")),
    DesignKey("colors", "heading", "color", render=RenderRule("hex", "--cz-heading")),
    DesignKey("colors", "accent", "color",
              render=RenderRule("hex", "--cz-brand", css_class="cz-acc", extra_vars=("--cz-accent",))),
    # ── type (renderer-only, not AI-settable; registry-driven emission) ──
    DesignKey("type", "headingSize", None,
              render=RenderRule("int_px", "--cz-h-size", css_class="cz-has-hsize", lo=16, hi=96)),
    DesignKey("type", "bodySize", None,
              render=RenderRule("int_px", "--cz-p-size", css_class="cz-has-psize", lo=12, hi=28)),
    # ── border (bespoke: top/bottom/width/color coupling) ──
    DesignKey("border", "top", "bool"),
    DesignKey("border", "bottom", "bool"),
    DesignKey("border", "width", (0, 20)),
    DesignKey("border", "color", "color"),
    # ── anchor (bespoke: id-collision guard on the section tag) ──
    DesignKey("anchor", "id", "text"),
)

# Groups whose emission `_apply_design` delegates to the registry (all keys in
# the group are self-contained). Other groups stay bespoke.
REGISTRY_DRIVEN_GROUPS: frozenset[str] = frozenset({"colors", "type"})

# Emission order per group (only meaningful for REGISTRY_DRIVEN_GROUPS).
def _group_design_keys() -> dict[str, tuple[DesignKey, ...]]:
    """Group DESIGN_KEYS by `group`, preserving declaration order (= renderer
    emission order). A function so the loop variable doesn't leak into the
    module namespace."""
    grouped: dict[str, tuple[DesignKey, ...]] = {}
    for dk in DESIGN_KEYS:
        grouped[dk.group] = grouped.get(dk.group, ()) + (dk,)
    return grouped


DESIGN_KEYS_BY_GROUP: dict[str, tuple[DesignKey, ...]] = _group_design_keys()


def build_design_groups() -> dict[str, dict[str, Any]]:
    """Derive the AI-facing `DESIGN_GROUPS` catalog (merlin_catalog imports this).

    Only `merlin_settable` keys, grouped, mapping key→merlin_spec — byte-equal
    to the historical hand-written dict (guarded by test)."""
    groups: dict[str, dict[str, Any]] = {}
    for dk in DESIGN_KEYS:
        if dk.merlin_settable:
            groups.setdefault(dk.group, {})[dk.key] = dk.merlin_spec
    return groups
