"""Merlin's server-side mirror of the page-builder catalog.

Merlin (AI chat editing, see `services/merlin.py`) needs to know what block
types exist, what fields each accepts, and what theme keys are legal — the
same knowledge the frontend already encodes in
`client/src/cappe/pages/site/PageEditor/blockSchemas.ts`. There is no shared
schema between server and client (Python/TS), so this is a hand-maintained
mirror: keep it in sync with `BLOCK_SCHEMAS` and `BLOCK_ORDER` there whenever
a block type or field is added/renamed/removed on the frontend.

Kept as plain dicts/sets (not Pydantic) — this is read-only reference data
consumed by prompt-building and validation, not request/response shapes.
"""
from typing import Any

# type -> {field name: field kind}, for the block's top-level content fields
# (excluding `type` itself and the structural `_design`/`_k`). Kinds use the
# same vocabulary as `Field.kind` in the frontend's PageEditor/types.ts:
# text | textarea | select | bool | image | video | strlist | list.
#
# The kind is load-bearing, not documentation: `validate_ops` type-checks the
# op's value against it, and refuses a non-integer path segment after a
# list/strlist field. Without that, `set_field path="items.title"` replaced a
# whole list of cards with a single object and reported success.
BLOCK_FIELDS: dict[str, dict[str, str]] = {
    "hero": {
        "eyebrow": "text", "heading": "text", "subheading": "textarea",
        "style": "select", "image": "image", "video": "video",
        "align": "select", "overlay": "select", "height": "select",
        "cta": "text", "ctaHref": "text", "cta2": "text", "cta2Href": "text",
    },
    "features": {"heading": "text", "subheading": "textarea", "items": "list"},
    "gallery": {"heading": "text", "images": "list"},
    "pricing": {"heading": "text", "plans": "list"},
    "testimonial": {"heading": "text", "items": "list"},
    "cta": {"heading": "text", "subheading": "textarea", "cta": "text", "ctaHref": "text"},
    "menu": {"heading": "text", "sections": "list"},
    "posts": {"heading": "text", "items": "list"},
    "stats": {"heading": "text", "subheading": "textarea", "items": "list"},
    "logos": {"heading": "text", "items": "list"},
    "faq": {"heading": "text", "subheading": "textarea", "items": "list"},
    "bento": {"heading": "text", "subheading": "textarea", "items": "list"},
    "split": {
        "eyebrow": "text", "heading": "text", "body": "textarea", "image": "image",
        "bullets": "strlist", "cta": "text", "ctaHref": "text", "reverse": "bool",
    },
    "credentials": {"heading": "text", "subheading": "textarea", "items": "list"},
    "reviews": {"heading": "text", "subheading": "textarea", "allowSubmissions": "bool"},
    "map": {"heading": "text", "address": "text", "lat": "text", "lng": "text"},
    "hours": {"heading": "text", "subheading": "textarea"},
    "text": {"heading": "text", "body": "textarea"},
    "contact": {"heading": "text", "subheading": "textarea", "fields": "strlist", "formSlug": "text"},
    "store": {"heading": "text", "subheading": "textarea"},
    "booking": {"heading": "text", "subheading": "textarea"},
    "newsletter": {"heading": "text", "subheading": "textarea"},
    # canvas is structural (grid/elements), not field-based — handled by the
    # canvas_add/canvas_update/canvas_remove ops instead of set_field.
    "canvas": {},
}

# Allowed values for `select`-kind fields, so the model can't invent an enum
# member the renderer will silently ignore ("overlay": "darker").
SELECT_OPTIONS: dict[str, dict[str, frozenset[str]]] = {
    "hero": {
        "style": frozenset({"centered", "split", "image", "minimal"}),
        "align": frozenset({"center", "left"}),
        "overlay": frozenset({"light", "medium", "dark"}),
        "height": frozenset({"tall", "full"}),
    },
}

# Kinds whose value is a JSON array — a path segment after one of these must
# be a list index, never a key name.
LIST_KINDS: frozenset[str] = frozenset({"list", "strlist"})
# Kinds whose value is a plain string.
TEXT_KINDS: frozenset[str] = frozenset({"text", "textarea", "select", "image", "video"})

BLOCK_TYPES: frozenset[str] = frozenset(BLOCK_FIELDS.keys())

# Human labels, for the prompt only (mirrors BLOCK_SCHEMAS[type].label).
BLOCK_LABELS: dict[str, str] = {
    "hero": "Hero", "features": "Features", "gallery": "Gallery", "pricing": "Pricing",
    "testimonial": "Testimonials", "cta": "Call to action", "menu": "Menu",
    "posts": "Post list", "stats": "Stats band", "logos": "Logo cloud", "faq": "FAQ",
    "bento": "Bento grid", "split": "Split feature", "credentials": "Certifications",
    "reviews": "Reviews", "map": "Map / Find us", "hours": "Opening hours", "text": "Text",
    "contact": "Contact form", "store": "Store (products)", "booking": "Booking widget",
    "newsletter": "Newsletter signup", "canvas": "Blank / Freeform",
}

# theme_config top-level keys Merlin may set. `type`/`style`/`premium` and
# `colors.brandGradient` are premium-only (see design_gate.py) but Merlin is
# already premium-gated end to end, so no separate whitelist tier here.
THEME_KEYS: frozenset[str] = frozenset({
    "preset", "colors.brand", "colors.accent", "fonts.heading", "fonts.body",
    "radius", "mode", "premium", "colors.brandGradient",
})
# `type.*` / `style.*` are open-ended sub-key bags (Designer typography / global
# style system) — validated by prefix instead of an exact set.
THEME_KEY_PREFIXES: tuple[str, ...] = ("type.", "style.")

THEME_MODE_VALUES = frozenset({"light", "dark"})

# Canvas element constraints (mirrors client/src/cappe/pages/site/PageEditor/canvasHelpers.ts).
CANVAS_ELEMENT_KINDS: frozenset[str] = frozenset({"heading", "text", "image", "button"})
CANVAS_MAX_ELEMENTS = 200
CANVAS_GRID_COLS = 24  # desktop grid width elements are placed against
CANVAS_MOBILE_GRID_COLS = 8  # mobile breakpoint width (`mobile.cols`)
# Upper bound on rows, mirroring the renderer's own clamp (`_CV_ROWS_MAX`).
# Used when a block declares no `grid.rows`, so an element can't be placed at
# y=999999 where the editor canvas can never scroll to it.
CANVAS_GRID_ROWS_MAX = 400
CANVAS_STYLE_KEYS: frozenset[str] = frozenset({
    "font", "size", "weight", "spacing", "lineHeight", "color", "align",
    "fit", "radius", "variant", "bg",
})
# Keys a `canvas_update` patch may carry. Deliberately excludes `id` (spreading
# a new id over an element can collide two of them, and a renderer-rejected id
# silently drops the element from the published page) and `kind` (an
# unrecognized kind is skipped by the renderer but still shows in the editor).
CANVAS_PATCH_KEYS: frozenset[str] = frozenset({"text", "src", "alt", "href", "d", "m", "style"})

MAX_OPS_PER_TURN = 20

# AI image-generation aspect ratios Merlin's generate_image op may request.
# Mirror of `core/services/image_gen.py:ASPECT_RATIOS` — kept here (pure, no
# google SDK) so op validation/prompt/schema don't drag the SDK into merlin_ops
# (which the whole pure-test suite imports). The service re-normalizes anyway,
# so drift degrades to "defaulted", never a crash.
AI_ASPECT_RATIOS: frozenset[str] = frozenset({"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"})
AI_IMAGE_PROMPT_MAX = 1000  # matches CappeImageGenRequest.prompt max_length

# --- Per-block design bag (`_design`) -----------------------------------------
# The per-section inspector's vocabulary (motion/bg/layout/colors/type/border/
# anchor) — where ALL motion and animation lives, so without it Merlin can't
# honor "animate this" and substitutes destructive ops it *can* emit instead.
#
# This is now DERIVED from the single-source-of-truth `design_registry` (the AI
# gets the `merlin_settable` subset of the renderer's full vocabulary); the
# derivation is asserted byte-equal to the historical hand-written dict in
# tests/cappe/test_design_registry.py. Value spec per key: a frozenset is a
# closed enum; "bool"/"color"/"text"/(min, max) int ranges are checked by kind
# in merlin_ops.py.
from .design_registry import build_design_groups

DESIGN_GROUPS: dict[str, dict[str, Any]] = build_design_groups()

# `_design` is a Pro/Business feature — `gate_content` strips it on save for
# non-premium plans. Merlin lite is open to free plans, so a design op from a
# free account must be refused with a reason, not applied in-editor and then
# silently dropped the moment the user hits Save.
DESIGN_REQUIRES_PREMIUM = True

# --- Model tiers -------------------------------------------------------------
# Restated locally rather than imported from a heavy service module (the
# matcha_work_ai.py:695 precedent). NOTE: this ladder is deliberately AHEAD of
# core/services/gemini_compliance.py:37-38, which still names the 3.1/3-preview
# generation — Merlin moved to the 2026-07-21 GA models first. Don't "resync"
# them by reverting this; the rest of the codebase is the side that's stale.
#
# `lite` is the default and is available on every plan — it's cheap enough to
# absorb as a funnel into upgrades. `regular` needs a paid plan; the server
# CLAMPS rather than 403s (mirroring matcha_work_ai._get_model), so a stale
# client asking for a tier it can't have silently gets what it's entitled to
# instead of an error. A pro/heavy tier is deliberately NOT offered — page
# editing is a structured-op task that flash handles well, and the cost is not
# metered yet (no token wallet), so the expensive model has no guard rail.
#
# Cost of the 2026-07-21 bump, per 1M tokens (in → out):
#   lite     3.1-flash-lite $0.25/$1.50  →  3.5-flash-lite $0.30/$2.50
#   regular  3-flash-preview $0.50/$3.00 →  3.6-flash      $1.50/$7.50
# Both went UP against what we were running: Google prices 3.6 Flash as the
# cheaper successor to 3.5 Flash ($9.00 out), but Merlin was never on 3.5 Flash
# — it sat a rung lower on a *preview* model. Bought with it: both tiers are now
# GA rather than preview, and flash-lite's agentic score (the op-emission task
# Merlin actually does) jumps Terminal-Bench 2.1 31% → 54%. 3.6 Flash also emits
# ~17% fewer output tokens than 3.5 Flash, which claws back part of the `regular`
# increase. Revisit if the token wallet lands and per-account cost gets metered.
MODEL_TIERS: dict[str, str] = {
    "lite": "gemini-3.5-flash-lite",
    "regular": "gemini-3.6-flash",
}
DEFAULT_MODEL_TIER = "lite"
# Tiers a non-premium (free / hosting) plan may use.
FREE_PLAN_TIERS: frozenset[str] = frozenset({"lite"})
