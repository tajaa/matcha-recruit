"""Self-contained Cappe public-site renderer.

Renders a published site's design tokens (`theme_config`) + a page's content
blocks into a standalone HTML document styled by ONE inline `<style>` — no
external CSS framework, no runtime CDN. The page is always styled (no flash, no
dependency on a third party). Per-site palette + fonts are injected as CSS
custom properties; a static, designed stylesheet (`_BASE_CSS`) consumes them, so
every template looks bespoke from the same engine.

Interactive widgets (store / booking / newsletter / contact) ship a tiny vanilla
JS runtime that talks to the same-origin public API. All user content is escaped;
URLs are scheme-checked.

Block types: hero, features, gallery, pricing, testimonial, cta, menu, posts,
stats, logos, faq, bento, split, credentials, reviews, map, hours, text,
contact, store, booking, newsletter.
"""
import html
import itertools
import json
import re
from typing import Any
from urllib.parse import quote

from .design_registry import DESIGN_COLOR_TOKENS, DESIGN_KEYS_BY_GROUP

_uid_counter = itertools.count(1)


def _uid() -> int:
    return next(_uid_counter)


# ── tokens ──────────────────────────────────────────────────────────────────

_SERIF = {
    "playfair display", "lora", "fraunces", "source serif pro", "source serif 4",
    "merriweather", "georgia", "pt serif", "cormorant garamond", "libre baskerville",
    "dm serif display", "instrument serif", "newsreader", "spectral",
    "eb garamond", "crimson pro", "bitter", "frank ruhl libre", "bodoni moda",
    "marcellus", "gloock", "caprasimo",
}
_RADIUS = {"none": "0px", "sm": "6px", "md": "10px", "lg": "14px", "xl": "18px", "2xl": "24px", "full": "9999px"}
_LIGHT = {"bg": "#ffffff", "surface": "#f6f7f9", "text": "#16181d", "muted": "#5b6470",
          "border": "#e6e8ec", "brand": "#10b981", "brandText": "#ffffff", "accent": "#10b981"}
_DARK = {"bg": "#0b0b0f", "surface": "#15151d", "text": "#f5f6f7", "muted": "#a0a4ad",
         "border": "#262630", "brand": "#a3e635", "brandText": "#0b0b0f", "accent": "#a3e635"}


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _safe_href(href: Any) -> str:
    if not href:
        return "#"
    s = str(href).strip()
    if s.startswith(("/", "#")):
        return s
    if s.lower().startswith(("http://", "https://", "mailto:", "tel:")):
        return s
    return "#"


def _safe_image(url: Any) -> str | None:
    if not url:
        return None
    s = str(url).strip()
    if any(c in s for c in ("'", '"', ")", "(", ";", "<", ">", "\\", "\n", "\r")):
        return None
    return s if s.lower().startswith(("http://", "https://", "/")) else None


def _js_obj(obj: Any) -> str:
    return (json.dumps(obj).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace(chr(0x2028), "\\u2028").replace(chr(0x2029), "\\u2029"))


def _clean_css(v: Any) -> str:
    return str(v if v is not None else "").replace("<", "").replace(">", "").replace("}", "")


# ── bespoke designer layer (per-block `_design`) ────────────────────────────
# Every value below is an enum lookup, a clamped number, a hex-only color, or a
# scheme-checked URL — no raw user string ever reaches a class/style/attr. A
# block with no (or empty) `_design` renders byte-identical to before.

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_SECTION_RE = re.compile(r"<section\b([^>]*)>")


def _hexonly(v: Any) -> str:
    s = str(v or "").strip()
    return s if _HEX_RE.match(s) else ""


def _design_color(v: Any) -> str:
    """A `_design` color value: a hex literal OR a semantic theme token,
    resolved to the SAME var()/color-mix CSS the hand-authored classes use
    (DESIGN_COLOR_TOKENS is a closed whitelist — nothing free-form reaches the
    stylesheet through it). Merlin's `_design_value_error` already restricts
    what a request can carry to one of these two forms; this is where it
    becomes CSS. Anything else (a token name that was retired, a non-string)
    falls through to `_hexonly`, so a stale value degrades to "no color" —
    never a raw pass-through string."""
    if isinstance(v, str) and v in DESIGN_COLOR_TOKENS:
        return DESIGN_COLOR_TOKENS[v]
    return _hexonly(v)


def _clampi(v: Any, lo: int, hi: int, default: int = 0) -> int:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


_ANCHOR_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def _anchor_id(v: Any) -> str:
    """Strict slug for a section `id=` attribute. Only [a-z0-9-] with no leading/
    trailing dash — no space/quote/`>` can appear, so no attribute breakout."""
    s = str(v or "").strip().lower()
    return s if _ANCHOR_RE.match(s) else ""


_PAD_SCALE = {"none": "0rem", "sm": "2rem", "lg": "6rem", "xl": "9rem"}
_MAXW = {"narrow": "44rem", "wide": "84rem", "full": "100%"}
_MINH = {"tall": "70vh", "screen": "100vh"}
_MOTION_FX = {"fade", "slide-up", "slide-down", "slide-left", "slide-right", "zoom", "blur-in",
              "flip", "rotate", "mask-up", "bounce",
              "fade-up", "fade-down", "scale-up", "blur-up"}
_HOVER_FX = {"lift", "tilt", "glow", "grow", "sink"}
_LOOP_FX = {"float", "pulse", "sway", "breathe"}
_HEADING_FX = {"rise", "shimmer"}
# Reveal easing (motion.easing → the transition timing-function on .cz-rv).
# `smooth` == the historical hardcoded default, so setting it is a no-op and an
# unset section keeps `var(--cz-ease, cubic-bezier(.2,.7,.2,1))`'s fallback.
_EASING = {
    "smooth": "cubic-bezier(.2,.7,.2,1)",
    "gentle": "cubic-bezier(.16,1,.3,1)",
    "spring": "cubic-bezier(.34,1.56,.64,1)",
    "snappy": "cubic-bezier(.65,0,.35,1)",
    "linear": "linear",
}
_OVERLAYS = {"light", "medium", "dark"}
# Decorative lane (Phase 5). Filters/patterns are class-toggled CSS; dividers
# are enum-keyed inline-SVG paths injected like bg_media (all values enum/clamp/
# hex — nothing user-authored reaches the SVG sink).
_IMG_FILTER_FX = {"mono", "warm", "cool", "soft", "punch"}
_BG_PATTERNS = {"dots", "grid", "diagonal"}
# Paths are authored for a TOP divider (shape hangs from the top edge, filled
# with the neighbouring/page background); the bottom variant is scaleY-flipped
# in CSS. viewBox is 0 0 1440 96, preserveAspectRatio=none stretches to fit.
_DIVIDER_PATHS = {
    "wave": "M0,0 L1440,0 L1440,40 C1200,88 960,8 720,48 C480,88 240,16 0,56 Z",
    "slant": "M0,0 L1440,0 L1440,8 L0,88 Z",
    "curve": "M0,0 L1440,0 L1440,48 Q720,120 0,48 Z",
    "peaks": "M0,0 L1440,0 L1440,56 L1200,24 L960,64 L720,20 L480,60 L240,28 L0,56 Z",
}

# ── global style system (theme_config.style → extra :root vars) ─────────────
# Each value is an enum-dict constant or a `_clampi` int emitted with a unit —
# no raw user string reaches the sink. Every enum default equals today's literal
# in `_BASE_CSS`, and a token is only emitted when the editor sets the key, so an
# unset `style` renders byte-identical.
_CONTAINER = {"compact": "64rem", "default": "72rem", "wide": "80rem", "xwide": "88rem"}
_GUTTER = {"tight": "1rem", "default": "1.5rem", "roomy": "2rem"}
_LINEHEIGHT = {"tight": "1.45", "normal": "1.6", "relaxed": "1.75"}
_SEC_PAD = {"compact": "clamp(2rem,5vw,3.5rem)", "cozy": "clamp(2.5rem,6vw,4.25rem)",
            "default": "clamp(3rem,7vw,5rem)", "roomy": "clamp(4rem,8vw,6.5rem)"}
_CARD_BORDER = {"none": "0", "hairline": "1px", "bold": "2px"}
_GRID_GAP = {"tight": "0.75rem", "default": "1.25rem", "roomy": "2rem"}


def _style_vars(style: Any) -> list[str]:
    """Build the optional `--token:value` list from `theme_config.style`. Absent /
    unrecognized keys are omitted so the `_BASE_CSS` `var(--token, <literal>)`
    fallbacks apply (byte-identical to today)."""
    if not isinstance(style, dict) or not style:
        return []
    out: list[str] = []

    def _enum(key: str, table: dict, var: str) -> None:
        v = table.get(str(style.get(key) or ""))
        if v is not None:
            out.append(f"{var}:{v}")

    def _px(key: str, lo: int, hi: int, var: str) -> None:
        n = _clampi(style.get(key), lo, hi, 0)
        if n:
            out.append(f"{var}:{n}px")

    _px("baseFont", 14, 20, "--base-fs")
    _enum("lineHeight", _LINEHEIGHT, "--base-lh")
    _enum("container", _CONTAINER, "--container")
    _enum("gutter", _GUTTER, "--gutter")
    _enum("sectionPad", _SEC_PAD, "--sec-pad")
    _enum("gap", _GRID_GAP, "--grid-gap")
    _px("cardPad", 8, 48, "--card-pad")
    _enum("cardBorder", _CARD_BORDER, "--card-bd")
    _px("headerPad", 8, 28, "--hdr-pad")
    _px("brandSize", 14, 32, "--brand-fs")
    _px("footerPad", 16, 80, "--ftr-pad")
    _px("buttonPadX", 4, 40, "--btn-px")
    _px("buttonPadY", 4, 30, "--btn-py")
    return out


def _design_motion(d: dict) -> bool:
    m = d.get("motion") if isinstance(d.get("motion"), dict) else {}
    return bool(
        (m.get("effect") in _MOTION_FX) or m.get("parallax") or m.get("kenburns") or m.get("stagger")
    )


def _block_has_motion(b: Any) -> bool:
    return isinstance(b, dict) and isinstance(b.get("_design"), dict) and _design_motion(b["_design"])


def _safe_url_css(url: Any) -> str:
    """Sanitized URL for a CSS url('...') — reuses the hero re-encode."""
    u = _safe_image(url)
    if not u:
        return ""
    return _esc(u).replace("'", "%27").replace("(", "%28").replace(")", "%29")


def _emit_design_group(group: str, values: dict, classes: list, cssvars: list) -> None:
    """Registry-driven emission for a self-contained design group (colors/type).

    Executes each key's declarative `RenderRule` (from `design_registry`) with
    this module's own sanitizers (`_hexonly`/`_clampi`) — byte-identical to the
    former inline blocks, so an unset key emits nothing and the `_BASE_CSS`
    var-fallback applies. New self-contained tokens become one registry entry
    rather than a hand-added branch here."""
    for dk in DESIGN_KEYS_BY_GROUP.get(group, ()):
        rule = dk.render
        if rule is None:
            continue
        raw = values.get(dk.key)
        if rule.kind == "hex":
            v = _design_color(raw)
            if v:
                cssvars.append(f"{rule.var}:{v}")
                for ev in rule.extra_vars:
                    cssvars.append(f"{ev}:{v}")
                if rule.css_class:
                    classes.append(rule.css_class)
        elif rule.kind == "int_px":
            if rule.allow_zero:
                # A token where 0 is a real value: an absent/null/non-numeric key
                # is "unset" (skip → var-fallback), an explicit clamped value —
                # including 0 — emits. The sentinel default (lo-1) is below the
                # range, so `_clampi` returning it means the input wasn't numeric.
                if raw is None:
                    continue
                n = _clampi(raw, rule.lo, rule.hi, rule.lo - 1)
                if n < rule.lo:
                    continue
            else:
                # Legacy skip-on-zero (byte-identical to the former inline
                # blocks): a value that clamps to 0 means "unset" for tokens
                # whose min is > 0, so a present 0 clamps up to lo and survives.
                n = _clampi(raw, rule.lo, rule.hi, 0)
                if not n:
                    continue
            cssvars.append(f"{rule.var}:{n}px")
            if rule.css_class:
                classes.append(rule.css_class)


# Responsive layout: per-breakpoint overrides of the layout keys. `md` (tablet)
# then `sm` (mobile) — sm is authored last so it wins where both max-widths match.
_RESP_BREAKPOINTS = (("Md", "1024px"), ("Sm", "640px"))


def _responsive_layout_style(layout: dict, cls: str) -> str:
    """Per-breakpoint layout overrides as a scoped ``<style>`` — the responsive
    layer over the base (desktop) layout emission.

    The base layout emits inline CSS vars, and a stylesheet rule cannot override
    an inline custom property, so every breakpoint declaration is ``!important``
    and scoped to the section's own class ``cls`` (no global bleed). Section-level
    keys (padding/align) are set as direct properties; ``columns`` is a
    ``--cz-cols`` var override because it is consumed by the section's child grid.
    Returns ``""`` when no ``*Md``/``*Sm`` key is present, so a non-responsive
    section renders byte-identically to before this feature existed."""
    blocks: list[str] = []
    for suffix, mq in _RESP_BREAKPOINTS:
        decls: list[str] = []
        pt = _PAD_SCALE.get(layout.get("padTop" + suffix))
        if pt is not None:
            decls.append(f"padding-top:{pt}!important")
        pb = _PAD_SCALE.get(layout.get("padBottom" + suffix))
        if pb is not None:
            decls.append(f"padding-bottom:{pb}!important")
        al = layout.get("align" + suffix)
        if al in ("left", "center"):
            decls.append(f"text-align:{al}!important")
        cols = _clampi(layout.get("columns" + suffix), 1, 6, 0)
        if cols:
            decls.append(f"--cz-cols:repeat({cols},minmax(0,1fr))!important")
        if decls:
            blocks.append(f"@media(max-width:{mq}){{.{cls}{{{';'.join(decls)}}}}}")
    return f"<style>{''.join(blocks)}</style>" if blocks else ""


def _apply_design(html_str: str, design: Any, *, block_index: Any = None, editable: bool = False) -> str:
    """Post-process a block's HTML: merge designer classes/attrs/style into its
    first <section> tag and inject background media layers. When `editable`, also
    tag the section with `data-cz-block` for the canvas selection runtime. No-op
    on published output (no design + not editable)."""
    has_design = isinstance(design, dict) and bool(design)
    tag_block = editable and block_index is not None
    if not has_design and not tag_block:
        return html_str
    m = _SECTION_RE.search(html_str)
    if not m:
        return html_str

    classes: list[str] = []
    attrs: list[str] = []
    cssvars: list[str] = []
    bg_media = ""
    resp_style = ""  # scoped <style> for per-breakpoint layout overrides
    divider_html = ""  # injected SVG shape dividers (Phase 5c)

    if has_design:
        motion = design.get("motion") if isinstance(design.get("motion"), dict) else {}
        bg = design.get("bg") if isinstance(design.get("bg"), dict) else {}
        layout = design.get("layout") if isinstance(design.get("layout"), dict) else {}
        colors = design.get("colors") if isinstance(design.get("colors"), dict) else {}
        typ = design.get("type") if isinstance(design.get("type"), dict) else {}
        border = design.get("border") if isinstance(design.get("border"), dict) else {}
        anchor = design.get("anchor") if isinstance(design.get("anchor"), dict) else {}
        image = design.get("image") if isinstance(design.get("image"), dict) else {}
        divider = design.get("divider") if isinstance(design.get("divider"), dict) else {}
        classes.append("cz-design")

        # ── motion ──────────────────────────────────────────────────────────
        effect = motion.get("effect")
        if effect in _MOTION_FX:
            classes += ["cz-rv", f"cz-rv--{effect}"]
            attrs.append(f'data-cz-delay="{_clampi(motion.get("delay"), 0, 2000)}"')
            attrs.append(f'data-cz-dur="{_clampi(motion.get("duration"), 100, 2000, 700)}"')
            if motion.get("stagger"):
                classes.append("cz-rv--stagger")
            # Reveal easing — a static inline var the .cz-rv transition consumes.
            # Unset → the CSS `var(--cz-ease, <default>)` fallback keeps today's curve.
            ease = _EASING.get(motion.get("easing"))
            if ease:
                cssvars.append(f"--cz-ease:{ease}")
        if motion.get("parallax"):
            classes.append("cz-parallax")
            attrs.append(f'data-cz-parallax="{_clampi(motion.get("parallaxStrength"), 0, 80, 20)}"')
        if motion.get("kenburns"):
            classes.append("cz-kenburns")
        # hover / continuous-loop / per-heading animation (each CSS-only, ungated)
        if motion.get("hover") in _HOVER_FX:
            classes.append(f"cz-hover-{motion['hover']}")
        if motion.get("loop") in _LOOP_FX:
            classes.append(f"cz-loop-{motion['loop']}")
        if motion.get("heading") in _HEADING_FX:
            classes.append(f"cz-bh-{motion['heading']}")

        # ── background ──────────────────────────────────────────────────────
        bg_type = bg.get("type")
        if bg_type == "color":
            col = _design_color(bg.get("color"))
            if col:
                classes.append("cz-bg--color")
                cssvars.append(f"--cz-bg-color:{col}")
        elif bg_type == "gradient":
            grad = _design_gradient(bg.get("gradient"))
            if grad:
                classes.append("cz-bg--gradient")
                cssvars.append(f"--cz-grad:{grad}")
        elif bg_type == "image":
            u = _safe_url_css(bg.get("image"))
            if u:
                classes += ["cz-bg", "cz-bg--image"]
                bg_media = f"<div class=\"cz-bg-media\" style=\"background-image:url('{u}')\"></div>"
        elif bg_type == "video":
            u = _safe_image(bg.get("video"))
            if u:
                classes += ["cz-bg", "cz-bg--video"]
                bg_media = ('<div class="cz-bg-media"><video autoplay muted loop playsinline '
                            f'preload="metadata"><source src="{_esc(u)}"></video></div>')
        if bg_media:
            overlay = bg.get("overlay")
            ov_cls = f"cz-ov-{overlay}" if overlay in _OVERLAYS else ""
            op = bg.get("overlayOpacity")
            ov_style = ""
            if op is not None and str(op) != "":
                ov_style = f' style="background:rgba(0,0,0,{_clampi(op, 0, 100) / 100})"'
            bg_media += f'<div class="cz-bg-ov {ov_cls}"{ov_style}></div>'
            blur = _clampi(bg.get("blur"), 0, 40)
            if blur:
                cssvars.append(f"--cz-blur:{blur}px")
                classes.append("cz-bg--blur")
        # decorative pattern — independent of bg type (background-image layers
        # over background-color, so it combines with a solid bg fill).
        if bg.get("pattern") in _BG_PATTERNS:
            classes.append(f"cz-pat-{bg['pattern']}")
            pcol = _design_color(bg.get("patternColor"))
            if pcol:
                cssvars.append(f"--cz-pat-col:{pcol}")

        # ── layout ──────────────────────────────────────────────────────────
        # Numeric px override wins over the enum step; -1 default distinguishes
        # "unset" from a deliberate 0 so `padTopPx:0` can zero the padding.
        pt_px = _clampi(layout.get("padTopPx"), 0, 400, -1)
        pt = f"{pt_px}px" if pt_px >= 0 else _PAD_SCALE.get(layout.get("padTop"))
        if pt is not None:
            cssvars.append(f"--cz-pad-t:{pt}")
            classes.append("cz-has-pt")
        pb_px = _clampi(layout.get("padBottomPx"), 0, 400, -1)
        pb = f"{pb_px}px" if pb_px >= 0 else _PAD_SCALE.get(layout.get("padBottom"))
        if pb is not None:
            cssvars.append(f"--cz-pad-b:{pb}")
            classes.append("cz-has-pb")
        cols = _clampi(layout.get("columns"), 1, 6, 0)
        if cols:
            cssvars.append(f"--cz-cols:repeat({cols},minmax(0,1fr))")
            classes.append("cz-has-cols")
        gap_px = _clampi(layout.get("gap"), 0, 80, -1)
        if gap_px >= 0:
            cssvars.append(f"--cz-gap:{gap_px}px")
            classes.append("cz-has-gap")
        mw = _MAXW.get(layout.get("maxWidth"))
        if mw:
            cssvars.append(f"--cz-maxw:{mw}")
            classes.append("cz-has-maxw")
        mh = _MINH.get(layout.get("minHeight"))
        if mh:
            cssvars.append(f"--cz-minh:{mh}")
            classes.append("cz-has-minh")
        align = layout.get("align")
        if align in ("left", "center"):
            classes.append(f"cz-al-{align}")
        # ── responsive layout (opt-in per breakpoint; scoped <style>) ───────
        # Base emission above is unchanged, so a section with no *Md/*Sm key is
        # byte-identical; a responsive one gains a stable per-block scope class
        # + an injected media-query style block. Needs the block index for the
        # deterministic class, so skip if it wasn't provided.
        if block_index is not None:
            _rcls = f"cz-rb{int(block_index)}"
            _resp = _responsive_layout_style(layout, _rcls)
            if _resp:
                classes.append(_rcls)
                resp_style = _resp

        # ── per-section color overrides + type sizes (registry-driven) ──────
        # These two groups are self-contained (each key → a css-var, no coupling
        # to siblings), so their emission is declared in `design_registry` and
        # executed by `_emit_design_group`. The coupled groups (motion effects,
        # background media, layout px-override, border) stay bespoke below/above.
        _emit_design_group("colors", colors, classes, cssvars)
        _emit_design_group("type", typ, classes, cssvars)

        # ── image filter preset (curated CSS filter chains) ─────────────────
        if image.get("filter") in _IMG_FILTER_FX:
            classes.append(f"cz-imgf-{image['filter']}")

        # ── shape dividers (enum-keyed inline SVG, injected like bg_media) ──
        if divider.get("top") in _DIVIDER_PATHS or divider.get("bottom") in _DIVIDER_PATHS:
            dh = _clampi(divider.get("height"), 20, 160, 64)
            dcol = _design_color(divider.get("color")) or "var(--bg)"
            for edge in ("top", "bottom"):
                shape = divider.get(edge)
                if shape in _DIVIDER_PATHS:
                    divider_html += (
                        f'<div class="cz-div cz-div--{edge}" style="height:{dh}px" aria-hidden="true">'
                        f'<svg viewBox="0 0 1440 96" preserveAspectRatio="none">'
                        f'<path d="{_DIVIDER_PATHS[shape]}" style="fill:{dcol}"/></svg></div>'
                    )

        # ── per-section border / divider ────────────────────────────────────
        if border.get("top") or border.get("bottom"):
            bw = _clampi(border.get("width"), 1, 8, 1)
            bcol = _design_color(border.get("color"))
            cssvars.append(f"--cz-bd-w:{bw}px")
            if bcol:
                cssvars.append(f"--cz-bd-col:{bcol}")
            if border.get("top"):
                classes.append("cz-bd-t")
            if border.get("bottom"):
                classes.append("cz-bd-b")

        # ── section anchor id (new attr sink; strict slug prevents breakout) ─
        # Skip if the block renderer already put an id on the section (store→
        # #shop, booking→#book): a second id= would be invalid HTML and the
        # browser would keep the first, silently ignoring the user's anchor.
        aid = _anchor_id(anchor.get("id"))
        if aid and "id=" not in m.group(1):
            attrs.append(f'id="{aid}"')

    if tag_block:
        attrs.append(f'data-cz-block="{int(block_index)}"')

    # ── merge into the existing <section ...> tag ───────────────────────────
    existing = m.group(1)  # attributes already on the tag (may include class/style)
    new_attrs = existing
    if classes:
        cls_str = " ".join(classes)
        cm = re.search(r'\sclass="([^"]*)"', new_attrs)
        if cm:
            new_attrs = new_attrs.replace(cm.group(0), f' class="{cm.group(1)} {cls_str}"', 1)
        else:
            new_attrs += f' class="{cls_str}"'
    if cssvars:
        style_str = _clean_css(";".join(cssvars))
        sm = re.search(r'\sstyle="([^"]*)"', new_attrs)
        if sm:
            new_attrs = new_attrs.replace(sm.group(0), f' style="{sm.group(1)};{style_str}"', 1)
        else:
            new_attrs += f' style="{style_str}"'
    if attrs:
        new_attrs += " " + " ".join(attrs)
    open_tag = f"<section{new_attrs}>"
    # Inject the responsive scoped <style> + bg media + shape dividers as the
    # section's first children (content .cz-wrap follows). Each is "" unless its
    # keys were set, so untouched output is unchanged.
    return html_str[:m.start()] + open_tag + resp_style + bg_media + divider_html + html_str[m.end():]


def _design_gradient(g: Any) -> str:
    if not isinstance(g, dict):
        return ""
    stops = [s for s in (_design_color(x) for x in (g.get("stops") or [])) if s]
    if len(stops) < 2:
        return ""
    angle = _clampi(g.get("angle"), 0, 360, 135)
    return f"linear-gradient({angle}deg,{','.join(stops[:3])})"


def _font_stack(name: str) -> str:
    generic = "serif" if (name or "").strip().lower() in _SERIF else "sans-serif"
    fallback = "ui-serif, Georgia," if generic == "serif" else "ui-sans-serif, system-ui, -apple-system,"
    # Strip quotes from the font name: it is wrapped in single quotes below and
    # then inlined into a double-quoted style="..." attribute (canvas elements) or
    # a single-quoted CSS string (<style> theme vars). A raw " or ' in the name
    # would break out of the attribute/string and inject markup — this is the one
    # unvalidated free-text field that reaches a style sink. <, >, } are already
    # dropped by _clean_css; also drop both quote styles here.
    safe = _clean_css(name).replace('"', "").replace("'", "")
    return f"'{safe}', {fallback} {generic}"


def _tokens(theme: dict | None) -> dict:
    theme = theme or {}
    mode = (theme.get("mode") or "light").lower()
    base = dict(_DARK if mode == "dark" else _LIGHT)
    if theme.get("primaryColor"):
        base["brand"] = theme["primaryColor"]
        base["accent"] = theme["primaryColor"]
    colors = theme.get("colors") or {}
    base.update({k: v for k, v in colors.items() if v})
    fonts = theme.get("fonts") or {}
    legacy = theme.get("font")
    return {
        "colors": base,
        "heading": fonts.get("heading") or legacy or "Inter",
        "body": fonts.get("body") or legacy or "Inter",
        "radius": _RADIUS.get((theme.get("radius") or "lg").lower(), _RADIUS["lg"]),
        "heroStyle": (theme.get("heroStyle") or "centered").lower(),
        "navStyle": (theme.get("navStyle") or "simple").lower(),
        "dark": mode == "dark",
        # Premium effects layer (mesh + glow, big display type, hover-lift glass
        # cards, scroll-reveal) — opt-in via theme_config.
        "premium": bool(theme.get("premium") or theme.get("fancy")),
    }


def _gfonts_link(heading: str, body: str) -> str:
    families = list(dict.fromkeys([heading, body, "Inter"]))
    parts = [f"family={quote(f)}:wght@400;500;600;700;800" for f in families if f]
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{"&".join(parts)}&display=swap">')


# ── stylesheet (real CSS; consumes the per-site CSS variables) ───────────────

_BASE_CSS = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-b);
  line-height:var(--base-lh,1.6);-webkit-font-smoothing:antialiased;font-size:var(--base-fs,17px)}
img{max-width:100%;display:block}
a{color:inherit}
h1,h2,h3{font-family:var(--font-h);font-weight:700;line-height:1.05;letter-spacing:-0.02em;margin:0}
p{margin:0}
.cz-wrap{max-width:var(--container,72rem);margin:0 auto;padding:0 var(--gutter,1.5rem)}
.cz-narrow{max-width:44rem;margin:0 auto;padding:0 1.5rem}

/* header */
.cz-header{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--bg) 82%,transparent);
  backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.cz-header .cz-bar{display:flex;align-items:center;gap:1.5rem;padding:var(--hdr-pad,1.05rem) 0}
.cz-header.center .cz-bar{justify-content:center}
.cz-header:not(.center) .cz-bar{justify-content:space-between}
.cz-brand{font-family:var(--font-h);font-weight:700;font-size:var(--brand-fs,1.2rem);text-decoration:none;color:var(--ink)}
.cz-brand img{height:30px;width:auto}
.cz-nav{display:flex;gap:1.5rem;flex-wrap:wrap}
.cz-nav a{color:var(--muted);text-decoration:none;font-size:.95rem;font-weight:500;transition:color .2s}
.cz-nav a:hover{color:var(--brand)}

/* buttons */
.cz-btn{display:inline-flex;align-items:center;justify-content:center;gap:.5rem;
  padding:var(--btn-py,.8rem) var(--btn-px,1.5rem);border-radius:var(--radius);font-weight:600;font-size:.95rem;
  text-decoration:none;cursor:pointer;border:1px solid transparent;transition:transform .15s,opacity .2s,background .2s;font-family:var(--font-b)}
.cz-btn:active{transform:translateY(1px)}
.cz-btn--solid{background:var(--brand);color:var(--brand-fg)}
.cz-btn--solid:hover{opacity:.92}
.cz-btn--ghost{background:transparent;color:var(--ink);border-color:var(--line)}
.cz-btn--ghost:hover{background:var(--surface)}
.cz-btn--block{width:100%}

/* sections + section headings */
section{position:relative}
.cz-head{text-align:center;max-width:42rem;margin:0 auto 3rem}
.cz-head h2{font-size:calc(var(--cz-h-scale,100)/100*clamp(1.8rem,4vw,2.6rem))}
.cz-head p{margin-top:.75rem;color:var(--muted)}
.cz-eyebrow{font-size:.72rem;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:var(--brand)}

/* hero */
.cz-hero{padding:clamp(3.5rem,9vw,7rem) 0}
.cz-hero--centered{text-align:center;background:linear-gradient(180deg,var(--surface),var(--bg))}
.cz-hero__title{font-size:calc(var(--cz-h-scale,100)/100*clamp(2.4rem,6vw,4.4rem))}
.cz-hero--centered .cz-hero__title,.cz-hero--centered .cz-hero__lead{margin-left:auto;margin-right:auto}
.cz-hero__title{max-width:18ch}
.cz-hero__eyebrow{margin-bottom:1rem}
.cz-hero__lead{margin-top:1.25rem;font-size:1.2rem;color:var(--muted);max-width:38rem}
.cz-cta-row{display:flex;flex-wrap:wrap;gap:.75rem;margin-top:2rem}
.cz-hero--centered .cz-cta-row,.cz-hero--image .cz-cta-row{justify-content:center}
.cz-hero--split .cz-grid{display:grid;gap:2.5rem;align-items:center}
.cz-hero--split .cz-art{aspect-ratio:4/3;border-radius:var(--radius);overflow:hidden;
  background:linear-gradient(135deg,var(--brand),var(--accent))}
.cz-hero--split .cz-art img{width:100%;height:100%;object-fit:cover}
.cz-hero--minimal{padding:clamp(4rem,11vw,9rem) 0}
.cz-hero--minimal .cz-hero__title{max-width:20ch}
.cz-hero--image{min-height:74vh;display:flex;align-items:center;text-align:center;color:#fff;
  background-size:cover;background-position:center;position:relative}
.cz-hero--image::before{content:"";position:absolute;inset:0;
  background:linear-gradient(180deg,rgba(0,0,0,.28),rgba(0,0,0,.5) 55%,rgba(0,0,0,.72))}
.cz-ov-light::before{background:linear-gradient(180deg,rgba(0,0,0,.1),rgba(0,0,0,.3) 60%,rgba(0,0,0,.5))}
.cz-ov-dark::before{background:linear-gradient(180deg,rgba(0,0,0,.46),rgba(0,0,0,.62) 55%,rgba(0,0,0,.78))}
.cz-hero--full{min-height:100vh}
.cz-hero--video{overflow:hidden}
.cz-hero--video .cz-hero__video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:0;border:0}
.cz-hero--video::before{z-index:1}
.cz-hero--video .cz-wrap{z-index:2}
.cz-hero--image .cz-wrap{position:relative;z-index:1}
.cz-hero--image .cz-hero__title{margin:0 auto;max-width:20ch;text-shadow:0 2px 24px rgba(0,0,0,.35)}
.cz-hero--image .cz-hero__lead{color:rgba(255,255,255,.88);margin:1.25rem auto 0}
.cz-hero--image .cz-eyebrow{color:rgba(255,255,255,.85)}
.cz-hero--left{text-align:left}
.cz-hero--left .cz-hero__title,.cz-hero--left .cz-hero__lead{margin-left:0;margin-right:0}
.cz-hero--left .cz-cta-row{justify-content:flex-start}

/* features */
.cz-features{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-cards{display:grid;gap:var(--cz-gap,var(--grid-gap,1.25rem));grid-template-columns:var(--cz-cols,repeat(auto-fit,minmax(220px,1fr)))}
.cz-card{border:var(--card-bd,1px) solid var(--line);background:var(--surface);border-radius:var(--radius);padding:var(--card-pad,1.6rem)}
.cz-feat__icon{width:44px;height:44px;display:flex;align-items:center;justify-content:center;
  border-radius:var(--radius);background:color-mix(in srgb,var(--brand) 14%,transparent);
  color:var(--brand);font-weight:700;font-size:1.15rem;margin-bottom:1rem}
.cz-card h3{font-size:1.15rem;margin-bottom:.4rem}
.cz-card p{color:var(--muted);font-size:.95rem}

/* gallery */
.cz-gallery{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-grid-img{display:grid;gap:var(--cz-gap,var(--grid-gap,.85rem));grid-template-columns:var(--cz-cols,repeat(auto-fit,minmax(220px,1fr)))}
.cz-tile{position:relative;border-radius:var(--radius);overflow:hidden}
.cz-tile img{aspect-ratio:1;width:100%;object-fit:cover;transition:transform .5s}
.cz-tile:hover img{transform:scale(1.05)}
.cz-tile figcaption{position:absolute;inset:auto 0 0 0;padding:.7rem .9rem;color:#fff;font-size:.85rem;
  background:linear-gradient(transparent,rgba(0,0,0,.6))}

/* pricing */
.cz-pricing{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-plans{display:grid;gap:var(--cz-gap,var(--grid-gap,1.25rem));grid-template-columns:var(--cz-cols,repeat(auto-fit,minmax(240px,1fr)));max-width:60rem;margin:0 auto}
.cz-plan{position:relative;border:var(--card-bd,1px) solid var(--line);background:var(--surface);border-radius:var(--radius);
  padding:var(--card-pad,2rem);display:flex;flex-direction:column}
.cz-plan--hot{outline:2px solid var(--brand);outline-offset:-1px;box-shadow:0 20px 40px -24px rgba(0,0,0,.4)}
.cz-plan__badge{position:absolute;top:-.7rem;left:50%;transform:translateX(-50%);background:var(--brand);
  color:var(--brand-fg);font-size:.7rem;font-weight:700;padding:.25rem .7rem;border-radius:999px}
.cz-plan__price{font-size:2.4rem;font-weight:700;font-family:var(--font-h);margin:.5rem 0}
.cz-plan__price span{font-size:.9rem;color:var(--muted);font-weight:400}
.cz-plan ul{list-style:none;padding:0;margin:0 0 1.5rem;display:flex;flex-direction:column;gap:.6rem;flex:1}
.cz-plan li{color:var(--muted);font-size:.93rem;display:flex;gap:.5rem}
.cz-plan li::before{content:"✓";color:var(--brand);font-weight:700}

/* testimonial */
.cz-quotes{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-quote-grid{display:grid;gap:var(--cz-gap,var(--grid-gap,1.25rem));grid-template-columns:var(--cz-cols,repeat(auto-fit,minmax(280px,1fr)));max-width:60rem;margin:0 auto}
.cz-quote{border:var(--card-bd,1px) solid var(--line);background:var(--surface);border-radius:var(--radius);padding:var(--card-pad,2rem)}
.cz-quote blockquote{font-family:var(--font-h);font-size:1.15rem;line-height:1.5;margin:0}
.cz-quote figcaption{margin-top:1.25rem;font-size:.9rem}
.cz-quote figcaption b{color:var(--ink)}
.cz-quote figcaption span{color:var(--muted)}

/* cta band */
.cz-band{background:var(--brand);color:var(--brand-fg);text-align:center;padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-band h2{font-size:calc(var(--cz-h-scale,100)/100*clamp(1.8rem,4vw,2.6rem))}
.cz-band p{margin:.75rem auto 0;max-width:34rem;opacity:.9}
.cz-band .cz-btn{margin-top:1.75rem;background:rgba(255,255,255,.16);color:#fff}
.cz-band .cz-btn:hover{background:rgba(255,255,255,.26)}

/* menu */
.cz-menu{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-menu-grid{display:grid;gap:var(--cz-gap,var(--grid-gap,2.5rem));grid-template-columns:var(--cz-cols,repeat(auto-fit,minmax(280px,1fr)));max-width:54rem;margin:0 auto}
.cz-menu h3{font-size:1.3rem;margin-bottom:.5rem}
.cz-menu-row{display:flex;align-items:baseline;gap:.75rem;padding:.55rem 0;border-top:1px solid var(--line)}
.cz-menu-row .name{font-weight:600}
.cz-menu-row .dots{flex:1;border-bottom:1px dotted var(--line);transform:translateY(-3px)}
.cz-menu-row .price{color:var(--brand);font-weight:600}
.cz-menu .desc{color:var(--muted);font-size:.88rem;padding-bottom:.4rem}

/* posts */
.cz-posts{padding:clamp(2.5rem,6vw,4rem) 0}
.cz-post{border-bottom:1px solid var(--line);padding:2rem 0}
.cz-post .date{font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:.4rem}
.cz-post h3{font-size:1.7rem}
.cz-post h3 a{text-decoration:none}
.cz-post:hover h3{color:var(--brand)}
.cz-post p{margin-top:.5rem;color:var(--muted);max-width:42rem}

/* text */
.cz-text{padding:clamp(2.5rem,6vw,4rem) 0}
.cz-text .cz-narrow>*+*{margin-top:1rem}
.cz-text h2{font-size:calc(var(--cz-h-scale,100)/100*clamp(1.6rem,3.5vw,2.2rem));margin-bottom:1rem}
.cz-text p{font-size:1.12rem;color:var(--muted);line-height:1.75}

/* forms / widgets */
.cz-form-sec{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-field{width:100%;padding:.7rem .9rem;border:1px solid var(--line);background:var(--bg);color:var(--ink);
  border-radius:var(--radius);font:inherit;font-size:.95rem;outline:none;transition:border-color .2s}
.cz-field:focus{border-color:var(--brand)}
.cz-form{display:flex;flex-direction:column;gap:.7rem;max-width:32rem;margin:0 auto}
.cz-label{font-size:.78rem;font-weight:600;color:var(--muted);display:block;margin-bottom:.3rem}
.cz-msg{font-size:.9rem}
.cz-msg.err{color:#ef4444}.cz-msg.ok{color:var(--brand)}
.cz-inline{display:flex;gap:.6rem}.cz-inline .cz-field{flex:1}

/* store */
.cz-store{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-store-grid{display:grid;gap:1.1rem;grid-template-columns:repeat(2,1fr)}
.cz-product{border:1px solid var(--line);background:var(--surface);border-radius:var(--radius);overflow:hidden;
  display:flex;flex-direction:column;text-align:left;cursor:pointer;font:inherit;color:inherit;width:100%;padding:0;
  transition:transform .25s cubic-bezier(.2,.7,.2,1),border-color .25s,box-shadow .25s}
.cz-product:hover{transform:translateY(-3px);border-color:color-mix(in srgb,var(--brand) 40%,var(--line));
  box-shadow:0 20px 38px -26px rgba(0,0,0,.4)}
.cz-product__img{aspect-ratio:1;width:100%;object-fit:cover;display:block;background:color-mix(in srgb,var(--ink) 6%,transparent)}
.cz-product__body{padding:.85rem .9rem 1rem;display:flex;flex-direction:column;gap:.35rem}
.cz-product h3{font-size:1rem;line-height:1.25}
.cz-product__foot{display:flex;align-items:center;justify-content:space-between;gap:.5rem;margin-top:.15rem}
.cz-product__opts{font-size:.7rem;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:.08rem .5rem;white-space:nowrap}
.cz-price{font-weight:700;font-family:var(--font-h)}
.cz-store-cat{font-family:var(--font-h);font-size:1.5rem;margin:2rem 0 1.1rem}
.cz-store-cat:first-child{margin-top:0}
@media(min-width:600px){.cz-store-grid{grid-template-columns:repeat(3,1fr)}}
@media(min-width:980px){.cz-store-grid{grid-template-columns:repeat(4,1fr);gap:1.4rem}}

/* option chips (product detail) */
.cz-opt-group{margin:.2rem 0 .5rem}
.cz-opt-group>.cz-label{display:block;margin-bottom:.35rem}
.cz-opts{display:flex;flex-wrap:wrap;gap:.4rem}
.cz-opt{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:var(--radius);
  padding:.45rem .8rem;font:inherit;font-size:.9rem;cursor:pointer;transition:border-color .15s,background .15s}
.cz-opt:hover{border-color:var(--brand)}
.cz-opt--on{background:var(--brand);color:var(--brand-fg);border-color:var(--brand)}

/* product detail overlay (acts like a product page; back-button closes it) */
.cz-pd{position:fixed;inset:0;z-index:50;display:flex;align-items:flex-start;justify-content:center;overflow-y:auto;
  padding:clamp(1rem,4vw,3rem) 1rem;background:rgba(10,10,9,.55);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px)}
.cz-pd[hidden]{display:none}
.cz-pd__panel{position:relative;width:100%;max-width:60rem;background:var(--bg);color:var(--ink);border:1px solid var(--line);
  border-radius:calc(var(--radius) + 6px);overflow:hidden;box-shadow:0 40px 100px -30px rgba(0,0,0,.6)}
.cz-pd__x{position:absolute;top:.8rem;right:.8rem;z-index:2;width:34px;height:34px;border:0;border-radius:999px;
  background:color-mix(in srgb,var(--ink) 10%,var(--bg));color:var(--ink);font-size:1.3rem;line-height:1;cursor:pointer}
.cz-pd__x:hover{background:color-mix(in srgb,var(--ink) 18%,var(--bg))}
.cz-pd__grid{display:grid;grid-template-columns:1fr}
.cz-pd__media{display:flex;background:color-mix(in srgb,var(--ink) 6%,transparent)}
.cz-pd__media img,.cz-pd__noimg{width:100%;aspect-ratio:1;object-fit:cover;display:block}
.cz-pd__info{padding:clamp(1.4rem,4vw,2.4rem);display:flex;flex-direction:column;gap:.45rem}
.cz-pd__name{font-size:calc(var(--cz-h-scale,100)/100*clamp(1.6rem,3.4vw,2.2rem));line-height:1.05;margin:.1rem 0 0}
.cz-pd__price{font-family:var(--font-h);font-weight:700;font-size:1.5rem;margin:.15rem 0 .4rem}
.cz-pd__was{text-decoration:line-through;opacity:.5;margin-right:.4rem;font-weight:400}
.cz-pd__off{color:var(--brand);font-size:.62em;margin-left:.3rem}
.cz-pd__desc{color:var(--muted);font-size:1rem;line-height:1.6}
.cz-pd__buy{margin-top:.7rem;display:flex;flex-direction:column;gap:.55rem}
.cz-pd__qty{max-width:6.5rem}
.cz-pd__reviews{padding:0 clamp(1.4rem,4vw,2.4rem) clamp(1.6rem,4vw,2.4rem)}
.cz-pd__rtitle{font-family:var(--font-h);font-size:1.2rem;display:flex;align-items:center;gap:.5rem;
  margin:0 0 1rem;padding-top:1.2rem;border-top:1px solid var(--line)}
.cz-pd__rstars{color:#f5b301;letter-spacing:1px}
.cz-pd__rn{color:var(--muted);font-size:.85rem;font-weight:400}
.cz-pd__rlist{display:grid;gap:.9rem;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
@media(min-width:760px){
  .cz-pd__grid{grid-template-columns:1.05fr 1fr}
  .cz-pd__media img,.cz-pd__noimg{height:100%;aspect-ratio:auto;min-height:24rem}
}

/* footer */
.cz-footer{border-top:1px solid var(--line);text-align:center;color:var(--muted);
  font-size:.85rem;padding:var(--ftr-pad,2.5rem) 0}
.cz-footer .small{font-size:.75rem;opacity:.7;margin-top:.35rem}
.cz-foot-social{display:flex;flex-wrap:wrap;justify-content:center;gap:1.1rem;margin-bottom:1rem}
.cz-foot-social a{color:var(--ink);text-decoration:none;font-size:.82rem;font-weight:600;letter-spacing:.02em}
.cz-foot-social a:hover{color:var(--brand)}
.cz-foot-contact{display:flex;flex-wrap:wrap;justify-content:center;gap:.4rem 1.2rem;margin-bottom:1rem}
.cz-foot-contact a,.cz-foot-contact span{color:var(--muted);text-decoration:none;font-size:.9rem}
.cz-foot-contact a:hover{color:var(--brand)}

/* stats band */
.cz-stats{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-stats-grid{display:grid;gap:var(--cz-gap,var(--grid-gap,1.5rem));grid-template-columns:var(--cz-cols,repeat(auto-fit,minmax(150px,1fr)));max-width:62rem;margin:0 auto;text-align:center}
.cz-stat{padding:1rem .5rem;position:relative}
.cz-stat+.cz-stat::before{content:"";position:absolute;left:0;top:18%;bottom:18%;width:1px;background:var(--line)}
.cz-stat__num{font-family:var(--font-h);font-weight:700;font-size:calc(var(--cz-h-scale,100)/100*clamp(2.4rem,5vw,3.4rem));line-height:1;
  background:linear-gradient(135deg,var(--brand),var(--accent));-webkit-background-clip:text;background-clip:text;color:transparent}
.cz-stat__label{margin-top:.55rem;color:var(--muted);font-size:.92rem;letter-spacing:.01em}

/* logo cloud */
.cz-logos{padding:clamp(2.25rem,5vw,3.5rem) 0}
.cz-logos__title{text-align:center;color:var(--muted);font-size:.74rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase;margin:0 0 1.75rem}
.cz-logos__row{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:1.5rem 3rem}
.cz-logos__row img{height:28px;width:auto;filter:grayscale(1);opacity:.65;transition:opacity .2s,filter .2s}
.cz-logos__row img:hover{filter:grayscale(0);opacity:1}
.cz-logos__name{font-family:var(--font-h);font-weight:700;font-size:1.15rem;color:var(--muted);opacity:.8}

/* faq (native accordion) */
.cz-faq{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-faq__list{max-width:46rem;margin:0 auto;border-top:1px solid var(--line)}
.cz-faq__item{border-bottom:1px solid var(--line)}
.cz-faq__item summary{display:flex;justify-content:space-between;align-items:center;gap:1rem;cursor:pointer;
  padding:1.3rem .25rem;font-family:var(--font-h);font-weight:600;font-size:1.12rem;color:var(--ink);list-style:none}
.cz-faq__item summary::-webkit-details-marker{display:none}
.cz-faq__item summary::after{content:"+";color:var(--brand);font-size:1.5rem;font-weight:300;line-height:1;transition:transform .25s}
.cz-faq__item[open] summary::after{transform:rotate(45deg)}
.cz-faq__item p{color:var(--muted);font-size:1.02rem;line-height:1.75;margin:0;padding:0 .25rem 1.4rem;max-width:42rem}

/* bento grid */
.cz-bento{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-bento-grid{display:grid;gap:1.1rem;grid-template-columns:repeat(2,1fr)}
.cz-bento-cell{border:var(--card-bd,1px) solid var(--line);background:var(--surface);border-radius:var(--radius);padding:var(--card-pad,1.7rem);
  display:flex;flex-direction:column;justify-content:flex-end;min-height:190px;position:relative;overflow:hidden;
  transition:transform .2s,border-color .2s}
.cz-bento-cell:hover{transform:translateY(-3px);border-color:color-mix(in srgb,var(--brand) 40%,var(--line))}
.cz-bento-cell--img{color:#fff;background-size:cover;background-position:center}
.cz-bento-cell--img::before{content:"";position:absolute;inset:0;background:linear-gradient(transparent 30%,rgba(0,0,0,.72))}
.cz-bento-cell--img>*{position:relative;z-index:1}
.cz-bento-cell__icon{font-size:1.5rem;margin-bottom:auto}
.cz-bento-cell h3{font-size:1.22rem;margin-bottom:.4rem}
.cz-bento-cell p{color:var(--muted);font-size:.94rem;line-height:1.55}
.cz-bento-cell--img p{color:rgba(255,255,255,.86)}

/* split feature */
.cz-split{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-split__grid{display:grid;gap:2.5rem;align-items:center}
.cz-split__art{aspect-ratio:4/3;border-radius:var(--radius);overflow:hidden;background:linear-gradient(135deg,var(--brand),var(--accent))}
.cz-split__art img{width:100%;height:100%;object-fit:cover}
.cz-split__body h2{font-size:calc(var(--cz-h-scale,100)/100*clamp(1.6rem,3.5vw,2.4rem));margin-bottom:1rem}
.cz-split__body>.cz-eyebrow{margin-bottom:.9rem}
.cz-split__body p{color:var(--muted);font-size:1.08rem;line-height:1.7}
.cz-split__bullets{list-style:none;padding:0;margin:1.25rem 0 0;display:flex;flex-direction:column;gap:.7rem}
.cz-split__bullets li{display:flex;gap:.6rem;color:var(--ink);font-size:1rem}
.cz-split__bullets li::before{content:"✓";color:var(--brand);font-weight:700}
.cz-split .cz-btn{margin-top:1.6rem}

/* credentials / qualifications */
.cz-creds{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-creds-grid{display:grid;gap:var(--cz-gap,var(--grid-gap,1rem));grid-template-columns:var(--cz-cols,repeat(auto-fit,minmax(260px,1fr)));max-width:62rem;margin:0 auto}
.cz-cred{display:flex;gap:.95rem;align-items:flex-start;border:var(--card-bd,1px) solid var(--line);background:var(--surface);
  border-radius:var(--radius);padding:1.25rem 1.4rem}
.cz-cred__badge{flex:0 0 auto;width:34px;height:34px;display:flex;align-items:center;justify-content:center;
  border-radius:999px;background:color-mix(in srgb,var(--brand) 16%,transparent);color:var(--brand);font-weight:700}
.cz-cred h3{font-size:1.08rem;line-height:1.3}
.cz-cred__meta{color:var(--brand);font-size:.84rem;font-weight:600;margin-top:.2rem}
.cz-cred__detail{color:var(--muted);font-size:.9rem;margin-top:.45rem;line-height:1.55}

/* booking slot picker */
.cz-daystrip{display:flex;gap:.5rem;overflow-x:auto;padding:.1rem 0 .55rem;margin-bottom:.7rem}
.cz-day{flex:0 0 auto;display:flex;flex-direction:column;align-items:flex-start;gap:.1rem;border:1px solid var(--line);
  background:var(--surface);color:var(--ink);border-radius:var(--radius);padding:.5rem .8rem;font:inherit;
  font-size:.9rem;font-weight:600;cursor:pointer;transition:border-color .15s,background .15s}
.cz-day span{font-size:.71rem;font-weight:500;color:var(--muted)}
.cz-day--on{border-color:var(--brand);background:color-mix(in srgb,var(--brand) 12%,var(--surface))}
.cz-day--on span{color:var(--brand)}
.cz-times{display:flex;flex-wrap:wrap;gap:.45rem}
.cz-slot{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:var(--radius);
  padding:.5rem .8rem;font:inherit;font-size:.88rem;cursor:pointer;transition:border-color .15s,background .15s}
.cz-slot:hover{border-color:var(--brand)}
.cz-slot--on{background:var(--brand);color:var(--brand-fg);border-color:var(--brand)}
.cz-staffrow{display:flex;flex-wrap:wrap;gap:.45rem}
.cz-staff{display:inline-flex;align-items:center;gap:.4rem;border:1px solid var(--line);background:var(--surface);
  color:var(--ink);border-radius:var(--radius);padding:.35rem .7rem;font:inherit;font-size:.88rem;cursor:pointer;
  transition:border-color .15s,background .15s}
.cz-staff img{width:22px;height:22px;border-radius:50%;object-fit:cover}
.cz-staff:hover{border-color:var(--brand)}
.cz-staff--on{background:var(--brand);color:var(--brand-fg);border-color:var(--brand)}

/* reviews */
.cz-reviews{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-reviews-grid{display:grid;gap:var(--cz-gap,var(--grid-gap,1.25rem));grid-template-columns:var(--cz-cols,repeat(auto-fit,minmax(260px,1fr)));max-width:60rem;margin:0 auto}
.cz-review{border:var(--card-bd,1px) solid var(--line);background:var(--surface);border-radius:var(--radius);padding:var(--card-pad,1.6rem)}
.cz-review__stars{color:#f5b301;letter-spacing:2px;margin-bottom:.55rem}
.cz-review blockquote{margin:0;font-size:1.02rem;line-height:1.6;color:var(--ink)}
.cz-review figcaption{margin-top:.9rem;font-weight:600;color:var(--muted);font-size:.9rem}
.cz-rv-form{max-width:34rem;margin:2rem auto 0;display:flex;flex-direction:column;gap:.6rem;
  border-top:1px solid var(--line);padding-top:1.6rem}
.cz-rv-form__t{font-weight:700;font-family:var(--font-h);text-align:center}

/* map + hours */
.cz-map{padding:var(--sec-pad,clamp(3rem,7vw,5rem)) 0}
.cz-map__embed{border-radius:var(--radius);overflow:hidden;border:1px solid var(--line);aspect-ratio:16/9;margin-bottom:1.25rem}
.cz-map__embed iframe{width:100%;height:100%;border:0;display:block}
.cz-map__addr{font-size:1.05rem;margin-bottom:.9rem}
.cz-map__actions{display:flex;flex-wrap:wrap;gap:.6rem}
.cz-hours{padding:clamp(2.5rem,6vw,4rem) 0}
.cz-hours__list{max-width:30rem;margin:1.1rem auto 0;border-top:1px solid var(--line)}
.cz-hours__row{display:flex;justify-content:space-between;gap:1rem;padding:.7rem .2rem;border-bottom:1px solid var(--line);font-size:.98rem}
.cz-hours__closed{color:var(--muted)}
.cz-badge{display:inline-block;padding:.35rem .85rem;border-radius:999px;font-size:.82rem;font-weight:700}
.cz-badge--open{background:color-mix(in srgb,#22c55e 20%,transparent);color:#15803d}
.cz-badge--closed{background:color-mix(in srgb,var(--ink) 9%,transparent);color:var(--muted)}

@media(min-width:768px){
  .cz-hero--split .cz-grid{grid-template-columns:1.1fr .9fr}
  .cz-hero--split{padding:clamp(4rem,8vw,7rem) 0}
  .cz-bento-grid{grid-template-columns:repeat(4,1fr);grid-auto-rows:11rem}
  .cz-bento-cell{grid-column:span 2}
  .cz-bento-cell--wide{grid-column:span 4}
  .cz-bento-cell--tall{grid-row:span 2}
  .cz-split__grid{grid-template-columns:1fr 1fr}
  .cz-split--reverse .cz-split__art{order:2}
}
@media(max-width:560px){.cz-nav{display:none}}

/* ── premium effects layer (body.cz-premium) ─────────────────────────────── */
/* fixed grid mesh + a soft brand-tinted glow behind the top of the page */
.cz-premium::before{content:"";position:fixed;inset:0;z-index:-2;pointer-events:none;
  background-image:linear-gradient(color-mix(in srgb,var(--ink) 5%,transparent) 1px,transparent 1px),
    linear-gradient(90deg,color-mix(in srgb,var(--ink) 5%,transparent) 1px,transparent 1px);
  background-size:60px 60px;
  -webkit-mask-image:radial-gradient(ellipse 75% 55% at 50% 0%,#000,transparent);
          mask-image:radial-gradient(ellipse 75% 55% at 50% 0%,#000,transparent)}
.cz-premium::after{content:"";position:fixed;left:50%;top:-20%;z-index:-1;pointer-events:none;
  width:64rem;height:44rem;max-width:120vw;transform:translateX(-50%);border-radius:50%;
  filter:blur(150px);opacity:.5;animation:czGlow 9s ease-in-out infinite;
  background:radial-gradient(closest-side,color-mix(in srgb,var(--brand) 36%,transparent),transparent)}
@keyframes czGlow{0%,100%{opacity:.42;transform:translateX(-50%) scale(1)}50%{opacity:.66;transform:translateX(-50%) scale(1.07)}}

/* display type + eyebrow pill */
.cz-premium .cz-hero__title{font-size:clamp(2.8rem,7.2vw,6rem);line-height:.98;letter-spacing:-.02em}
.cz-premium .cz-hero__lead{font-size:1.26rem}
.cz-premium .cz-hero--centered{background:transparent}
.cz-premium .cz-head h2,.cz-premium .cz-split__body h2,.cz-premium .cz-band h2,
.cz-premium .cz-stat__num{letter-spacing:-.015em}
.cz-premium .cz-head h2,.cz-premium .cz-split__body h2{font-size:clamp(2rem,4.8vw,3.6rem);line-height:1.02}
.cz-premium .cz-eyebrow{display:inline-block;padding:.42rem .95rem;border-radius:999px;
  border:1px solid color-mix(in srgb,var(--brand) 35%,transparent);
  background:color-mix(in srgb,var(--brand) 8%,transparent);letter-spacing:.24em;font-size:.66rem}

/* glass cards with hover-lift + brand glow */
.cz-premium .cz-card,.cz-premium .cz-plan,.cz-premium .cz-quote,.cz-premium .cz-cred,
.cz-premium .cz-review,.cz-premium .cz-product,.cz-premium .cz-tile{
  transition:transform .5s cubic-bezier(.2,.7,.2,1),border-color .5s,box-shadow .5s,background .5s}
.cz-premium .cz-card:hover,.cz-premium .cz-plan:hover,.cz-premium .cz-quote:hover,
.cz-premium .cz-cred:hover,.cz-premium .cz-review:hover,.cz-premium .cz-product:hover{
  transform:translateY(-5px);border-color:color-mix(in srgb,var(--brand) 45%,var(--line));
  box-shadow:0 30px 60px -34px color-mix(in srgb,var(--brand) 55%,transparent)}
.cz-premium .cz-feat__icon{background:linear-gradient(135deg,var(--brand),var(--accent));color:var(--brand-fg)}
.cz-premium .cz-tile:hover{box-shadow:0 30px 60px -34px color-mix(in srgb,var(--brand) 50%,transparent)}

/* scroll-reveal — only active once JS adds .cz-js (no-JS shows everything).
   Per-section designer motion (.cz-rv) opts out so the two don't double-hide. */
.cz-premium.cz-js main>section:not(.cz-rv){opacity:0;transform:translateY(26px);
  transition:opacity .9s cubic-bezier(.2,.7,.2,1),transform .9s cubic-bezier(.2,.7,.2,1)}
.cz-premium.cz-js main>section:not(.cz-rv).cz-in{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){
  .cz-premium.cz-js main>section:not(.cz-rv){opacity:1;transform:none;transition:none}
  .cz-premium::after{animation:none}}

/* ── bespoke designer layer (per-section; independent of cz-premium) ──────── */
/* layout: consume vars only when the matching cz-has-* class is present, so
   unset sections keep today's exact spacing/width. */
.cz-has-pt{padding-top:var(--cz-pad-t)}
.cz-has-pb{padding-bottom:var(--cz-pad-b)}
.cz-has-minh{min-height:var(--cz-minh);display:flex;flex-direction:column;justify-content:center}
.cz-has-maxw>.cz-wrap,.cz-has-maxw>.cz-narrow{max-width:var(--cz-maxw)}
.cz-al-left{text-align:left}
.cz-al-center{text-align:center}
/* per-section color overrides (scoped to the section) */
.cz-design{color:var(--cz-text,inherit)}
.cz-design h1,.cz-design h2,.cz-design h3{color:var(--cz-heading,inherit)}
.cz-acc{--brand:var(--cz-brand);--accent:var(--cz-accent)}
/* per-section type sizes + borders (scoped to the section; unset = today) */
.cz-design.cz-has-hsize .cz-head h2,.cz-design.cz-has-hsize .cz-hero__title,
.cz-design.cz-has-hsize .cz-split__body h2,.cz-design.cz-has-hsize .cz-band h2{font-size:var(--cz-h-size)}
.cz-design.cz-has-psize p{font-size:var(--cz-p-size)}
.cz-bd-t{border-top:var(--cz-bd-w,1px) solid var(--cz-bd-col,var(--line))}
.cz-bd-b{border-bottom:var(--cz-bd-w,1px) solid var(--cz-bd-col,var(--line))}
/* backgrounds: solid/gradient paint the section; image/video ride a media layer */
.cz-bg--color{background:var(--cz-bg-color)}
.cz-bg--gradient{background:var(--cz-grad)}
.cz-bg{position:relative;overflow:hidden}
.cz-bg>.cz-bg-media{position:absolute;inset:0;z-index:0}
.cz-bg--image>.cz-bg-media{background-size:cover;background-position:center}
.cz-bg--video>.cz-bg-media video{width:100%;height:100%;object-fit:cover;border:0}
.cz-bg>.cz-bg-ov{position:absolute;inset:0;z-index:1;pointer-events:none}
.cz-bg>.cz-bg-ov.cz-ov-light{background:linear-gradient(180deg,rgba(0,0,0,.1),rgba(0,0,0,.3) 60%,rgba(0,0,0,.5))}
.cz-bg>.cz-bg-ov.cz-ov-medium{background:linear-gradient(180deg,rgba(0,0,0,.28),rgba(0,0,0,.5) 55%,rgba(0,0,0,.72))}
.cz-bg>.cz-bg-ov.cz-ov-dark{background:linear-gradient(180deg,rgba(0,0,0,.46),rgba(0,0,0,.62) 55%,rgba(0,0,0,.78))}
.cz-bg>.cz-wrap,.cz-bg>.cz-narrow,.cz-bg>*:not(.cz-bg-media):not(.cz-bg-ov):not(.cz-div){position:relative;z-index:2}
.cz-bg--blur>.cz-bg-media{filter:blur(var(--cz-blur))}
/* ── decorative lane (Phase 5): patterns, image filters, shape dividers ──── */
/* patterns: background-image layers over background-color, so they combine
   with a solid bg fill; placed after .cz-bg--* so the image layer wins. */
.cz-pat-dots{background-image:radial-gradient(var(--cz-pat-col,color-mix(in srgb,var(--ink) 14%,transparent)) 1px,transparent 1.5px);background-size:22px 22px}
.cz-pat-grid{background-image:linear-gradient(var(--cz-pat-col,color-mix(in srgb,var(--ink) 10%,transparent)) 1px,transparent 1px),linear-gradient(90deg,var(--cz-pat-col,color-mix(in srgb,var(--ink) 10%,transparent)) 1px,transparent 1px);background-size:44px 44px}
.cz-pat-diagonal{background-image:repeating-linear-gradient(45deg,var(--cz-pat-col,color-mix(in srgb,var(--ink) 9%,transparent)) 0 1px,transparent 1px 16px)}
/* image filter presets: applied to the section's bg media + content images */
.cz-imgf-mono .cz-bg-media,.cz-imgf-mono img{filter:grayscale(1)}
.cz-imgf-warm .cz-bg-media,.cz-imgf-warm img{filter:sepia(.28) saturate(1.18) contrast(1.02)}
.cz-imgf-cool .cz-bg-media,.cz-imgf-cool img{filter:saturate(.85) hue-rotate(-12deg) brightness(1.03)}
.cz-imgf-soft .cz-bg-media,.cz-imgf-soft img{filter:contrast(.92) brightness(1.06) saturate(.88)}
.cz-imgf-punch .cz-bg-media,.cz-imgf-punch img{filter:contrast(1.12) saturate(1.28)}
/* shape dividers: inline SVG anchored inside the section's own box, filled
   with the neighbouring/page background (default var(--bg)); bottom flips. */
.cz-div{position:absolute;left:0;right:0;z-index:1;pointer-events:none;line-height:0}
.cz-div svg{display:block;width:100%;height:100%}
.cz-div--top{top:0}
.cz-div--bottom{bottom:0;transform:scaleY(-1)}
.cz-kenburns>.cz-bg-media{animation:czKen 18s ease-in-out infinite alternate}
@keyframes czKen{from{transform:scale(1)}to{transform:scale(1.12)}}
/* motion reveal — gated by body.cz-motion.cz-js (runtime present + JS available) */
.cz-motion.cz-js .cz-rv{opacity:0;
  transition:opacity var(--cz-dur,700ms) var(--cz-ease,cubic-bezier(.2,.7,.2,1)),
    transform var(--cz-dur,700ms) var(--cz-ease,cubic-bezier(.2,.7,.2,1)),
    filter var(--cz-dur,700ms) var(--cz-ease,cubic-bezier(.2,.7,.2,1));
  transition-delay:var(--cz-delay,0ms)}
.cz-motion.cz-js .cz-rv--slide-up{transform:translateY(28px)}
.cz-motion.cz-js .cz-rv--slide-left{transform:translateX(28px)}
.cz-motion.cz-js .cz-rv--slide-right{transform:translateX(-28px)}
.cz-motion.cz-js .cz-rv--zoom{transform:scale(.94)}
.cz-motion.cz-js .cz-rv--blur-in{filter:blur(12px)}
.cz-motion.cz-js .cz-rv.cz-in{opacity:1;transform:none;filter:none}
/* stagger: direct grid children cascade via --i set by the runtime */
.cz-motion.cz-js .cz-rv--stagger .cz-cards>*,.cz-motion.cz-js .cz-rv--stagger .cz-plans>*,
.cz-motion.cz-js .cz-rv--stagger .cz-bento>*,.cz-motion.cz-js .cz-rv--stagger .cz-gallery>*,
.cz-motion.cz-js .cz-rv--stagger .cz-creds>*,.cz-motion.cz-js .cz-rv--stagger .cz-quotes>*,
.cz-motion.cz-js .cz-rv--stagger .cz-stats>*,.cz-motion.cz-js .cz-rv--stagger .cz-reviews-box>*{
  opacity:0;transform:translateY(20px);
  transition:opacity .6s cubic-bezier(.2,.7,.2,1),transform .6s cubic-bezier(.2,.7,.2,1);
  transition-delay:calc(var(--i,0)*90ms)}
.cz-motion.cz-js .cz-rv--stagger.cz-in .cz-cards>*,.cz-motion.cz-js .cz-rv--stagger.cz-in .cz-plans>*,
.cz-motion.cz-js .cz-rv--stagger.cz-in .cz-bento>*,.cz-motion.cz-js .cz-rv--stagger.cz-in .cz-gallery>*,
.cz-motion.cz-js .cz-rv--stagger.cz-in .cz-creds>*,.cz-motion.cz-js .cz-rv--stagger.cz-in .cz-quotes>*,
.cz-motion.cz-js .cz-rv--stagger.cz-in .cz-stats>*,.cz-motion.cz-js .cz-rv--stagger.cz-in .cz-reviews-box>*{
  opacity:1;transform:none}
/* animated hero headline (theme.type.heroAnim) */
.cz-h-rise .cz-hero__title{animation:czRise .9s cubic-bezier(.2,.7,.2,1) both}
@keyframes czRise{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}
.cz-h-shimmer .cz-hero__title{background:linear-gradient(100deg,var(--ink) 30%,var(--brand) 50%,var(--ink) 70%);
  background-size:200% auto;-webkit-background-clip:text;background-clip:text;color:transparent;
  animation:czShim 4.5s linear infinite}
@keyframes czShim{to{background-position:200% center}}
/* typography tokens (consumed only when the editor set them) */
.cz-typw h1,.cz-typw h2,.cz-typw h3,.cz-typw .cz-hero__title{font-weight:var(--font-h-wght)}
.cz-hero__title,.cz-head h2,.cz-split__body h2{letter-spacing:var(--ls-h,normal)}
/* brand gradient (falls back to solid brand — no-op when unset) */
.cz-btn--solid{background:var(--brand-grad,var(--brand))}
.cz-band{background:var(--brand-grad,var(--brand))}
@media(max-width:768px){.cz-parallax>.cz-bg-media{transform:none!important}}
/* extra reveal effects (cz-rv variants — reset by .cz-rv.cz-in) */
.cz-motion.cz-js .cz-rv--slide-down{transform:translateY(-28px)}
.cz-motion.cz-js .cz-rv--flip{transform:perspective(800px) rotateX(26deg);transform-origin:top center}
.cz-motion.cz-js .cz-rv--rotate{transform:rotate(-4deg) scale(.95)}
.cz-motion.cz-js .cz-rv--bounce{transform:translateY(34px)}
.cz-motion.cz-js .cz-rv--bounce.cz-in{animation:czBounce .8s cubic-bezier(.2,1.3,.4,1) both}
@keyframes czBounce{from{transform:translateY(34px)}60%{transform:translateY(-8px)}to{transform:none}}
.cz-motion.cz-js .cz-rv--mask-up{clip-path:inset(100% 0 0 0);opacity:1;
  transition:clip-path var(--cz-dur,700ms) var(--cz-ease,cubic-bezier(.2,.7,.2,1));transition-delay:var(--cz-delay,0ms)}
.cz-motion.cz-js .cz-rv--mask-up.cz-in{clip-path:inset(0 0 0 0)}
/* softer reveals (all reset by .cz-rv.cz-in's transform:none;filter:none) */
.cz-motion.cz-js .cz-rv--fade-up{transform:translateY(14px)}
.cz-motion.cz-js .cz-rv--fade-down{transform:translateY(-14px)}
.cz-motion.cz-js .cz-rv--scale-up{transform:scale(.98)}
.cz-motion.cz-js .cz-rv--blur-up{filter:blur(8px);transform:translateY(16px)}
/* hover effects (whole-section, CSS-only) */
.cz-hover-lift{transition:transform .35s cubic-bezier(.2,.7,.2,1),box-shadow .35s}
.cz-hover-lift:hover{transform:translateY(-6px);box-shadow:0 30px 60px -34px color-mix(in srgb,var(--brand) 50%,transparent)}
.cz-hover-tilt{transition:transform .35s cubic-bezier(.2,.7,.2,1)}
.cz-hover-tilt:hover{transform:perspective(900px) rotateX(3deg) rotateY(-3deg) scale(1.01)}
.cz-hover-glow{transition:box-shadow .4s}
.cz-hover-glow:hover{box-shadow:0 0 0 1px color-mix(in srgb,var(--brand) 40%,transparent),0 24px 60px -30px color-mix(in srgb,var(--brand) 55%,transparent)}
.cz-hover-grow{transition:transform .35s cubic-bezier(.2,.7,.2,1)}
.cz-hover-grow:hover{transform:scale(1.02)}
.cz-hover-sink{transition:transform .3s cubic-bezier(.2,.7,.2,1)}
.cz-hover-sink:hover{transform:translateY(4px) scale(.99)}
/* continuous loops */
.cz-loop-float{animation:czFloat 6s ease-in-out infinite}
@keyframes czFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
.cz-loop-pulse{animation:czPulse 4s ease-in-out infinite}
@keyframes czPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.015)}}
.cz-loop-sway{animation:czSway 5s ease-in-out infinite}
@keyframes czSway{0%,100%{transform:rotate(-1.2deg)}50%{transform:rotate(1.2deg)}}
.cz-loop-breathe{animation:czBreathe 4.5s ease-in-out infinite}
@keyframes czBreathe{0%,100%{opacity:.82}50%{opacity:1}}
/* per-block heading animation (reuses czRise/czShim keyframes) */
.cz-bh-rise h1,.cz-bh-rise h2{animation:czRise .9s cubic-bezier(.2,.7,.2,1) both}
.cz-bh-shimmer h1,.cz-bh-shimmer h2{background:linear-gradient(100deg,var(--ink) 30%,var(--brand) 50%,var(--ink) 70%);
  background-size:200% auto;-webkit-background-clip:text;background-clip:text;color:transparent;animation:czShim 4.5s linear infinite}

/* ── promos: announcement bar + pop-up modal (meta_config.promos) ────────── */
.cz-promobar{background:var(--czbar-bg,var(--brand));color:var(--czbar-fg,var(--brand-fg));
  font-size:.92rem;font-weight:600;position:relative;z-index:60}
.cz-promobar[hidden]{display:none}
.cz-promobar--bottom{position:fixed;left:0;right:0;bottom:0}
.cz-promobar__in{max-width:84rem;margin:0 auto;padding:.6rem 2.4rem;display:flex;align-items:center;
  justify-content:center;gap:.9rem;flex-wrap:wrap;text-align:center}
.cz-promobar__cta{color:inherit;text-decoration:underline;text-underline-offset:3px;font-weight:800;white-space:nowrap}
.cz-promobar__x{position:absolute;right:.7rem;top:50%;transform:translateY(-50%);background:none;border:0;
  color:inherit;opacity:.7;cursor:pointer;font-size:1.25rem;line-height:1;padding:.1rem .35rem}
.cz-promobar__x:hover{opacity:1}
.cz-modal{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;padding:1.2rem}
.cz-modal[hidden]{display:none}
.cz-modal__scrim{position:absolute;inset:0;background:rgba(8,10,14,.62);opacity:0;transition:opacity .3s}
.cz-modal.cz-in .cz-modal__scrim{opacity:1}
.cz-modal__card{position:relative;z-index:1;width:100%;max-width:30rem;background:var(--czpop-bg,var(--surface));
  color:var(--ink);border:1px solid var(--line);border-radius:calc(var(--radius) + 4px);padding:1.9rem;
  box-shadow:0 40px 80px -30px rgba(0,0,0,.55);text-align:center;
  transform:translateY(14px) scale(.97);opacity:0;
  transition:transform .35s cubic-bezier(.2,.7,.2,1),opacity .35s}
.cz-modal.cz-in .cz-modal__card{transform:none;opacity:1}
.cz-modal__x{position:absolute;right:.85rem;top:.65rem;background:none;border:0;color:var(--muted);
  font-size:1.5rem;line-height:1;cursor:pointer}
.cz-modal__x:hover{color:var(--ink)}
.cz-modal__img{width:100%;height:9rem;object-fit:cover;border-radius:var(--radius);margin-bottom:1rem}
.cz-modal__card h3{font-family:var(--font-h);font-size:1.5rem;margin:0 0 .55rem}
.cz-modal__card p{color:var(--muted);margin:0 0 1.15rem;font-size:.98rem}
.cz-modal__code{display:flex;align-items:center;justify-content:center;gap:.6rem;
  border:1px dashed var(--brand);border-radius:var(--radius);padding:.7rem 1rem;margin-bottom:.7rem}
.cz-modal__code b{font-family:var(--font-h);font-size:1.2rem;letter-spacing:.06em}
.cz-modal__copy{background:none;border:0;color:var(--brand);font-weight:700;cursor:pointer;font-size:.85rem}
.cz-modal .cz-inline{display:flex;gap:.5rem}
@media(max-width:520px){.cz-modal .cz-inline{flex-direction:column}}
@media(prefers-reduced-motion:reduce){
  .cz-motion.cz-js .cz-rv,.cz-motion.cz-js .cz-rv--stagger .cz-cards>*,
  .cz-motion.cz-js .cz-rv--stagger .cz-plans>*{opacity:1!important;transform:none!important;filter:none!important;transition:none}
  .cz-rv--mask-up{clip-path:none!important}
  .cz-kenburns>.cz-bg-media,.cz-parallax>.cz-bg-media,.cz-h-rise .cz-hero__title,.cz-h-shimmer .cz-hero__title,
  .cz-loop-float,.cz-loop-pulse,.cz-loop-sway,.cz-loop-breathe,
  .cz-bh-rise h1,.cz-bh-rise h2,.cz-bh-shimmer h1,.cz-bh-shimmer h2{animation:none!important}
  .cz-h-shimmer .cz-hero__title,.cz-bh-shimmer h1,.cz-bh-shimmer h2{color:var(--ink);-webkit-text-fill-color:var(--ink)}
  .cz-modal__scrim,.cz-modal__card{transition:none}}
"""


# ── blocks ──────────────────────────────────────────────────────────────────

def _btn(label, href, *, solid=True):
    if not label:
        return ""
    cls = "cz-btn--solid" if solid else "cz-btn--ghost"
    return f'<a class="cz-btn {cls}" href="{_esc(_safe_href(href))}">{_esc(label)}</a>'


def _fattr(field: str, editable: bool) -> str:
    """`data-cz-field` tag for canvas inline-text editing — only in editor mode."""
    return f' data-cz-field="{field}"' if editable else ""


def _head(b, editable=False):
    h = f'<h2{_fattr("heading", editable)}>{_esc(b.get("heading"))}</h2>' if b.get("heading") else ""
    s = f'<p{_fattr("subheading", editable)}>{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    return f'<div class="cz-head">{h}{s}</div>' if (h or s) else ""


def _hero(b, t, editable=False):
    style = (b.get("style") or t["heroStyle"]).lower()
    eyebrow = f'<p class="cz-eyebrow cz-hero__eyebrow"{_fattr("eyebrow", editable)}>{_esc(b.get("eyebrow"))}</p>' if b.get("eyebrow") else ""
    title = f'<h1 class="cz-hero__title"{_fattr("heading", editable)}>{_esc(b.get("heading"))}</h1>'
    lead = f'<p class="cz-hero__lead"{_fattr("subheading", editable)}>{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    cta = (f'<div class="cz-cta-row">{_btn(b.get("cta"), b.get("ctaHref"))}'
           f'{_btn(b.get("cta2"), b.get("cta2Href"), solid=False)}</div>') if (b.get("cta") or b.get("cta2")) else ""
    img = _safe_image(b.get("image"))
    vid = _safe_image(b.get("video"))  # same URL sanitizer (scheme + breakout chars)

    # A centered hero that has media (photo/video) becomes a full-bleed overlay
    # hero — the intuitive result of "add a hero image/video". split/minimal stay
    # explicit. A video always forces the full-bleed treatment.
    if (img or vid) and style == "centered":
        style = "image"

    if vid or style == "image":
        overlay = (b.get("overlay") or "medium").lower()
        overlay = overlay if overlay in ("light", "medium", "dark") else "medium"
        cls = f"cz-hero--image cz-ov-{overlay}"
        if (b.get("align") or "center").lower() == "left":
            cls += " cz-hero--left"
        if (b.get("height") or "tall").lower() == "full":
            cls += " cz-hero--full"
        if vid:
            # Full-bleed autoplay background video (premium). The still image,
            # when present, serves as the poster while the video buffers.
            cls += " cz-hero--video"
            poster = f' poster="{_esc(img)}"' if img else ""
            media = (f'<video class="cz-hero__video" autoplay muted loop playsinline preload="auto"{poster}>'
                     f'<source src="{_esc(vid)}"></video>')
            return (f'<section class="cz-hero {cls}">{media}<div class="cz-wrap">'
                    f'{eyebrow}{title}{lead}{cta}</div></section>')
        # _safe_image already rejects quotes/parens; re-encode so the url() is
        # self-evidently un-breakoutable without trusting the sibling sanitizer.
        safe_u = _esc(img).replace("'", "%27").replace("(", "%28").replace(")", "%29") if img else ""
        bgstyle = f"background-image:url('{safe_u}')" if safe_u else ""
        return (f'<section class="cz-hero {cls}" style="{bgstyle}"><div class="cz-wrap">'
                f'{eyebrow}{title}{lead}{cta}</div></section>')
    if style == "split":
        art = (f'<img src="{_esc(img)}" alt="" />' if img else "")
        return (f'<section class="cz-hero cz-hero--split"><div class="cz-wrap cz-grid">'
                f'<div>{eyebrow}{title}{lead}{cta}</div><div class="cz-art">{art}</div></div></section>')
    mod = "cz-hero--minimal" if style == "minimal" else "cz-hero--centered"
    return f'<section class="cz-hero {mod}"><div class="cz-wrap">{eyebrow}{title}{lead}{cta}</div></section>'


def _features(b, t, editable=False):
    cards = "".join(
        f'<div class="cz-card"><div class="cz-feat__icon">{_esc(i.get("icon") or (i.get("title") or "•")[:1])}</div>'
        f'<h3>{_esc(i.get("title"))}</h3><p>{_esc(i.get("body"))}</p></div>'
        for i in (b.get("items") or []) if isinstance(i, dict))
    return f'<section class="cz-features"><div class="cz-wrap">{_head(b, editable)}<div class="cz-cards">{cards}</div></div></section>'


def _gallery(b, t):
    tiles = ""
    for i in (b.get("images") or []):
        if not isinstance(i, dict):
            continue
        u = _safe_image(i.get("url"))
        if not u:
            continue
        cap = f'<figcaption>{_esc(i.get("caption"))}</figcaption>' if i.get("caption") else ""
        tiles += f'<figure class="cz-tile"><img src="{_esc(u)}" alt="{_esc(i.get("caption"))}" />{cap}</figure>'
    return f'<section class="cz-gallery"><div class="cz-wrap">{_head(b)}<div class="cz-grid-img">{tiles}</div></div></section>'


def _pricing(b, t):
    cards = ""
    for p in (b.get("plans") or []):
        if not isinstance(p, dict):
            continue
        hot = bool(p.get("highlighted"))
        feats = "".join(f'<li>{_esc(f)}</li>' for f in (p.get("features") or []))
        badge = '<span class="cz-plan__badge">Popular</span>' if hot else ""
        cards += (f'<div class="cz-plan {"cz-plan--hot" if hot else ""}">{badge}<h3>{_esc(p.get("name"))}</h3>'
                  f'<div class="cz-plan__price">{_esc(p.get("price"))}<span>{_esc(p.get("period") or "")}</span></div>'
                  f'<ul>{feats}</ul>{_btn(p.get("cta") or "Choose", p.get("ctaHref"), solid=hot)}</div>')
    return f'<section class="cz-pricing"><div class="cz-wrap">{_head(b)}<div class="cz-plans">{cards}</div></div></section>'


def _testimonial(b, t):
    items = b.get("items") or ([{"quote": b.get("quote"), "author": b.get("author"), "role": b.get("role")}] if b.get("quote") else [])
    cards = ""
    for i in items:
        if not isinstance(i, dict):
            continue
        role = f' · <span>{_esc(i.get("role"))}</span>' if i.get("role") else ""
        cards += (f'<figure class="cz-quote"><blockquote>“{_esc(i.get("quote"))}”</blockquote>'
                  f'<figcaption><b>{_esc(i.get("author"))}</b>{role}</figcaption></figure>')
    return f'<section class="cz-quotes"><div class="cz-wrap">{_head(b)}<div class="cz-quote-grid">{cards}</div></div></section>'


def _cta(b, t, editable=False):
    sub = f'<p{_fattr("subheading", editable)}>{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    return (f'<section class="cz-band"><div class="cz-wrap"><h2{_fattr("heading", editable)}>{_esc(b.get("heading"))}</h2>{sub}'
            f'<a class="cz-btn" href="{_esc(_safe_href(b.get("ctaHref")))}">{_esc(b.get("cta") or "Get started")}</a></div></section>')


def _menu(b, t):
    cols = ""
    for s in (b.get("sections") or []):
        if not isinstance(s, dict):
            continue
        rows = ""
        for it in (s.get("items") or []):
            if not isinstance(it, dict):
                continue
            rows += (f'<div class="cz-menu-row"><span class="name">{_esc(it.get("name"))}</span>'
                     f'<span class="dots"></span><span class="price">{_esc(it.get("price"))}</span></div>')
            if it.get("description"):
                rows += f'<div class="desc">{_esc(it.get("description"))}</div>'
        cols += f'<div><h3>{_esc(s.get("name"))}</h3>{rows}</div>'
    return f'<section class="cz-menu"><div class="cz-wrap">{_head(b)}<div class="cz-menu-grid">{cols}</div></div></section>'


def _posts(b, t):
    rows = ""
    for i in (b.get("items") or []):
        if not isinstance(i, dict):
            continue
        date = f'<div class="date">{_esc(i.get("date"))}</div>' if i.get("date") else ""
        href = _safe_href("/p/" + i.get("slug")) if i.get("slug") else "#"
        rows += (f'<article class="cz-post">{date}<h3><a href="{_esc(href)}">{_esc(i.get("title"))}</a></h3>'
                 f'<p>{_esc(i.get("excerpt"))}</p></article>')
    return f'<section class="cz-posts"><div class="cz-narrow">{_head(b)}{rows}</div></section>'


def _stats(b, t):
    cells = "".join(
        f'<div class="cz-stat"><div class="cz-stat__num">{_esc(i.get("value"))}</div>'
        f'<div class="cz-stat__label">{_esc(i.get("label"))}</div></div>'
        for i in (b.get("items") or []) if isinstance(i, dict))
    return f'<section class="cz-stats"><div class="cz-wrap">{_head(b)}<div class="cz-stats-grid">{cells}</div></div></section>'


def _logos(b, t):
    title = f'<p class="cz-logos__title">{_esc(b.get("heading") or "Trusted by")}</p>'
    items = ""
    for i in (b.get("items") or []):
        if not isinstance(i, dict):
            continue
        u = _safe_image(i.get("image"))
        if u:
            items += f'<img src="{_esc(u)}" alt="{_esc(i.get("name"))}" />'
        elif i.get("name"):
            items += f'<span class="cz-logos__name">{_esc(i.get("name"))}</span>'
    return f'<section class="cz-logos"><div class="cz-wrap">{title}<div class="cz-logos__row">{items}</div></div></section>'


def _faq(b, t):
    rows = ""
    for i in (b.get("items") or []):
        if not isinstance(i, dict) or not i.get("q"):
            continue
        rows += (f'<details class="cz-faq__item"><summary>{_esc(i.get("q"))}</summary>'
                 f'<p>{_esc(i.get("a"))}</p></details>')
    return f'<section class="cz-faq"><div class="cz-wrap">{_head(b)}<div class="cz-faq__list">{rows}</div></div></section>'


def _bento(b, t):
    cells = ""
    for i in (b.get("items") or []):
        if not isinstance(i, dict):
            continue
        span = str(i.get("span") or "").lower()
        mod = " cz-bento-cell--wide" if span == "wide" else (" cz-bento-cell--tall" if span == "tall" else "")
        icon = f'<div class="cz-bento-cell__icon">{_esc(i.get("icon"))}</div>' if i.get("icon") else ""
        head = f'<h3>{_esc(i.get("title"))}</h3>' if i.get("title") else ""
        body = f'<p>{_esc(i.get("body"))}</p>' if i.get("body") else ""
        u = _safe_image(i.get("image"))
        if u:
            # Defense-in-depth: _safe_image already rejects quotes/parens, but
            # encode locally too so the CSS url() literal can't be closed even
            # if that guard ever changes (HTML-attr escape + CSS-quote encode).
            safe_u = _esc(u).replace("'", "%27").replace("(", "%28").replace(")", "%29")
            cells += (f'<div class="cz-bento-cell cz-bento-cell--img{mod}" '
                      f'style="background-image:url(\'{safe_u}\')">{icon}{head}{body}</div>')
        else:
            cells += f'<div class="cz-bento-cell{mod}">{icon}{head}{body}</div>'
    return f'<section class="cz-bento"><div class="cz-wrap">{_head(b)}<div class="cz-bento-grid">{cells}</div></div></section>'


def _split(b, t, editable=False):
    img = _safe_image(b.get("image"))
    art = f'<img src="{_esc(img)}" alt="" />' if img else ""
    eyebrow = f'<p class="cz-eyebrow"{_fattr("eyebrow", editable)}>{_esc(b.get("eyebrow"))}</p>' if b.get("eyebrow") else ""
    head = f'<h2{_fattr("heading", editable)}>{_esc(b.get("heading"))}</h2>' if b.get("heading") else ""
    body = f'<p{_fattr("body", editable)}>{_esc(b.get("body"))}</p>' if b.get("body") else ""
    bl = [x for x in (b.get("bullets") or []) if x]
    bullets = ('<ul class="cz-split__bullets">' + "".join(f'<li>{_esc(x)}</li>' for x in bl) + "</ul>") if bl else ""
    cta = _btn(b.get("cta"), b.get("ctaHref")) if b.get("cta") else ""
    mod = " cz-split--reverse" if b.get("reverse") else ""
    return (f'<section class="cz-split{mod}"><div class="cz-wrap"><div class="cz-split__grid">'
            f'<div class="cz-split__art">{art}</div>'
            f'<div class="cz-split__body">{eyebrow}{head}{body}{bullets}{cta}</div>'
            f'</div></div></section>')


def _text(b, t, editable=False):
    body = b.get("body")
    # Single-paragraph (scalar) body is inline-editable as `body`; a list of
    # paragraphs stays panel-only (no dotted-path inline edit in v1).
    if isinstance(body, list):
        inner = "".join(f"<p>{_esc(p)}</p>" for p in body if p)
    else:
        inner = f'<p{_fattr("body", editable)}>{_esc(body)}</p>' if body else ""
    head = f'<h2{_fattr("heading", editable)}>{_esc(b.get("heading"))}</h2>' if b.get("heading") else ""
    return f'<section class="cz-text"><div class="cz-narrow">{head}{inner}</div></section>'


def _credentials(b, t):
    cards = ""
    for i in (b.get("items") or []):
        if not isinstance(i, dict):
            continue
        meta = " · ".join(x for x in (_esc(i.get("issuer")), _esc(i.get("year"))) if x)
        meta_html = f'<div class="cz-cred__meta">{meta}</div>' if meta else ""
        detail = f'<p class="cz-cred__detail">{_esc(i.get("detail"))}</p>' if i.get("detail") else ""
        cards += (f'<div class="cz-cred"><div class="cz-cred__badge">✓</div>'
                  f'<div><h3>{_esc(i.get("title"))}</h3>{meta_html}{detail}</div></div>')
    return f'<section class="cz-creds"><div class="cz-wrap">{_head(b)}<div class="cz-creds-grid">{cards}</div></div></section>'


# ── interactive widgets (same-origin /api/cappe/public, no styling deps) ─────

def _widget_runtime():
    return (
        "<script>window.__CAPPE_RT__=window.__CAPPE_RT__||(function(){"
        "var C=window.__CAPPE__||{api:''};"
        "function esc(s){return (s==null?'':String(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;')"
        ".replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');}"
        "function url(s){s=(s==null?'':String(s)).trim();var l=s.toLowerCase();"
        "return (l.indexOf('http://')===0||l.indexOf('https://')===0||s.charAt(0)==='/')?s:'';}"
        "function money(c,cur){try{return new Intl.NumberFormat('en-US',{style:'currency',currency:cur||'USD'})"
        ".format((c||0)/100);}catch(e){return '$'+(((c||0)/100).toFixed(2));}}"
        "function get(p){return fetch(C.api+p).then(function(r){if(!r.ok)throw new Error('load');return r.json();});}"
        "function post(p,b){return fetch(C.api+p,{method:'POST',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify(b)}).then(function(r){return r.json().catch(function(){return null;})"
        ".then(function(d){if(!r.ok)throw new Error((d&&d.detail)||'Request failed');return d;});});}"
        "return {api:C.api,slug:C.slug,preview:!!C.preview,esc:esc,url:url,money:money,get:get,post:post};})();</script>"
    )


# Motion runtime. Adds `cz-js` (so hide-state CSS only applies when JS is
# available — no-JS shows everything), reveals each <section> on scroll-in
# (covers both the legacy premium full-section reveal and per-section .cz-rv
# designer motion), wires stagger child indices, and runs rAF parallax. No-op
# without IntersectionObserver; parallax is skipped under reduced-motion / mobile.
_STAGGER_SEL = (".cz-cards>*,.cz-plans>*,.cz-bento>*,.cz-gallery>*,"
                ".cz-creds>*,.cz-quotes>*,.cz-stats>*,.cz-reviews-box>*")
_MOTION_JS = (
    "<script>(function(){var b=document.body;"
    "if(!b||!('IntersectionObserver' in window))return;b.classList.add('cz-js');"
    "var rm=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;"
    "document.querySelectorAll('.cz-rv').forEach(function(s){"
    "var d=s.getAttribute('data-cz-delay');if(d)s.style.setProperty('--cz-delay',d+'ms');"
    "var u=s.getAttribute('data-cz-dur');if(u)s.style.setProperty('--cz-dur',u+'ms');"
    "if(s.className.indexOf('cz-rv--stagger')>=0){var k=s.querySelectorAll('" + _STAGGER_SEL + "');"
    "for(var i=0;i<k.length;i++)k[i].style.setProperty('--i',i);}});"
    "var io=new IntersectionObserver(function(es){es.forEach(function(e){"
    "if(e.isIntersecting){e.target.classList.add('cz-in');io.unobserve(e.target);}});},{threshold:.12});"
    "document.querySelectorAll('main>section').forEach(function(s){io.observe(s);});"
    "var small=window.matchMedia&&window.matchMedia('(max-width:768px)').matches;"
    "if(!rm&&!small){var px=[].slice.call(document.querySelectorAll('.cz-parallax'));"
    "if(px.length){var tk=false;var upd=function(){tk=false;"
    "px.forEach(function(s){var st=parseFloat(s.getAttribute('data-cz-parallax'))||0;"
    "var m=s.querySelector('.cz-bg-media');if(!m)return;var r=s.getBoundingClientRect();"
    "var off=r.top+r.height/2-window.innerHeight/2;"
    "m.style.transform='translateY('+(off*st/-1000)+'px) scale(1.16)';});};"
    "window.addEventListener('scroll',function(){if(!tk){tk=true;requestAnimationFrame(upd);}},{passive:true});"
    "upd();}}})();</script>"
)


# Canvas editor runtime — emitted ONLY when `editable` (editor preview), never on
# published pages. Lets the parent app click-select sections, inline-edit tagged
# text, and drag-reorder, via postMessage. Vanilla, inline, no user strings.
_CANVAS_JS = """<style>
.cz-editable [data-cz-block]{cursor:pointer}
.cz-editable [data-cz-block].cz-hover{outline:2px dashed rgba(16,185,129,.55);outline-offset:-2px}
.cz-editable [data-cz-block].cz-selected{outline:2px solid #10b981;outline-offset:-2px}
.cz-editable [data-cz-field]{cursor:text}
.cz-editable [data-cz-field].cz-editing{outline:2px solid #10b981;outline-offset:3px;background:rgba(16,185,129,.07);border-radius:3px}
.cz-editable .cz-drop{height:0;border-top:3px solid #10b981;position:relative;z-index:9999}
.cz-editable.cz-dragging *{cursor:grabbing !important;user-select:none !important}
.cz-editable .cz-el{cursor:move}
.cz-editable .cz-el.cz-editing{cursor:text}
.cz-editable .cz-el.cz-el-sel{outline:2px solid #10b981;outline-offset:1px}
.cz-cv-h{position:absolute;width:11px;height:11px;background:#10b981;border:2px solid #fff;border-radius:50%;z-index:10000;box-shadow:0 0 0 1px rgba(0,0,0,.15)}
.cz-cv-h[data-dir=nw]{top:-6px;left:-6px;cursor:nwse-resize}
.cz-cv-h[data-dir=ne]{top:-6px;right:-6px;cursor:nesw-resize}
.cz-cv-h[data-dir=sw]{bottom:-6px;left:-6px;cursor:nesw-resize}
.cz-cv-h[data-dir=se]{bottom:-6px;right:-6px;cursor:nwse-resize}
.cz-cv-h[data-dir=n]{top:-6px;left:50%;margin-left:-5.5px;cursor:ns-resize}
.cz-cv-h[data-dir=s]{bottom:-6px;left:50%;margin-left:-5.5px;cursor:ns-resize}
.cz-cv-h[data-dir=w]{left:-6px;top:50%;margin-top:-5.5px;cursor:ew-resize}
.cz-cv-h[data-dir=e]{right:-6px;top:50%;margin-top:-5.5px;cursor:ew-resize}
.cz-cv-grabbing *{user-select:none !important}
.cz-editable .cz-canvas .cz-cv-wrap{min-height:96px}
.cz-editable a.cz-el,.cz-editable .cz-el img{-webkit-user-drag:none;user-drag:none}
.cz-theme-hl{outline:2px solid #10b981 !important;outline-offset:2px !important;transition:outline-color .15s}
</style>
<script>(function(){
var editing=null,origText='',cancelEdit=false,dragging=false,dragFrom=-1,downY=0,downIdx=-1,moved=false,dropLine=null;
var elDrag=null,elResize=null,rdir='',selEl=null,curBp='d',gx=0,gy=0,sx=0,sy=0,sw=0,sh=0,gg=null,pid=0;
var themeMode=false; // theme drawer open (Form mode only) — clicks probe a region instead of selecting
var restrictMode=false; // Form mode: keep hover+click-select for the form<->preview sync, but
                         // suppress canvas-only affordances (inline edit, drag-reorder, element drag/resize)
// Region -> selector map for theme highlight-sync. Kept in lockstep with the
// ThemeRegion union in useThemeBridge.ts.
var THEME_REGION_SEL={
  brand:'.cz-btn--solid,.cz-brand',
  accent:'.cz-btn--solid,.cz-brand,.cz-stat__num',
  headingFont:'h1,h2,h3',
  bodyFont:'body',
  radius:'.cz-btn,.cz-card,.cz-plan,.cz-quote,.cz-bento-cell',
  mode:'body',
  container:'.cz-wrap',
  gutter:'.cz-wrap',
  sectionPad:'main>section:first-of-type,main>[data-cz-block]:first-of-type',
  gap:'.cz-cards,.cz-plans,.cz-grid-img,.cz-quote-grid',
  cardPad:'.cz-card,.cz-plan,.cz-quote,.cz-bento-cell',
  cardBorder:'.cz-card,.cz-plan,.cz-quote,.cz-bento-cell',
  headerPad:'.cz-header',
  brandSize:'.cz-header',
  footerPad:'.cz-footer'
};
var THEME_HL_MAX=6;
function clearThemeHl(){var hs=document.querySelectorAll('.cz-theme-hl');for(var i=0;i<hs.length;i++)hs[i].classList.remove('cz-theme-hl');}
function highlightTheme(region){
  clearThemeHl();
  var sel=THEME_REGION_SEL[region];if(!sel)return;
  var els=[].slice.call(document.querySelectorAll(sel)).slice(0,THEME_HL_MAX);
  for(var i=0;i<els.length;i++)els[i].classList.add('cz-theme-hl');
  // Scroll the first match into view — but never for whole-page targets (body),
  // where "scrolling into view" would just yank the preview to the top.
  if(els[0]&&els[0]!==document.body&&els[0].scrollIntoView)els[0].scrollIntoView({block:'center',behavior:'smooth'});
}
// Reverse direction: clicking a page element while the theme drawer is open
// probes which region governs it, so the parent can jump the drawer there.
// Checked most-specific first — broad containers (body) would match everything.
var THEME_PROBE_ORDER=['brand','headingFont','cardPad','headerPad','footerPad','gap'];
function probeThemeRegion(el){
  for(var k=0;k<THEME_PROBE_ORDER.length;k++){
    var region=THEME_PROBE_ORDER[k];
    var matches=document.querySelectorAll(THEME_REGION_SEL[region]);
    for(var i=0;i<matches.length;i++){if(matches[i]===el||matches[i].contains(el)){post({type:'cz-theme-probe',region:region});return;}}
  }
  var inSection=el.closest&&el.closest('[data-cz-block]');
  post({type:'cz-theme-probe',region:inSection?'sectionPad':'bodyFont'});
}
function post(m){try{window.parent.postMessage(m,'*');}catch(e){}}
function blocks(){return [].slice.call(document.querySelectorAll('main>[data-cz-block]'));}
function blockEl(i){return document.querySelector('[data-cz-block="'+i+'"]');}
function idxOf(el){var b=el&&el.closest?el.closest('[data-cz-block]'):null;return b?parseInt(b.getAttribute('data-cz-block'),10):-1;}
function clearHandles(){var hs=document.querySelectorAll('.cz-cv-h');for(var i=0;i<hs.length;i++)hs[i].parentNode.removeChild(hs[i]);}
function addHandles(el){clearHandles();var ds=['nw','n','ne','e','se','s','sw','w'];for(var i=0;i<ds.length;i++){var h=document.createElement('div');h.className='cz-cv-h';h.setAttribute('data-dir',ds[i]);el.appendChild(h);}}
function clearSel(){var s=document.querySelectorAll('.cz-selected,.cz-el-sel');for(var i=0;i<s.length;i++)s[i].classList.remove('cz-selected','cz-el-sel');clearHandles();selEl=null;}
function highlight(i){clearSel();var el=blockEl(i);if(el)el.classList.add('cz-selected');}
function selectEl(el){clearSel();el.classList.add('cz-el-sel');selEl=el;addHandles(el);}
function postSelectEl(el){var r=el.getBoundingClientRect();post({type:'cz-select',block:idxOf(el),field:el.getAttribute('data-cz-id'),rect:{top:r.top,left:r.left,width:r.width,height:r.height}});}
function clamp(v,lo,hi){return Math.max(lo,Math.min(hi,v));}
function gridInfo(el){var w=el.closest&&el.closest('.cz-cv-wrap');if(!w)return null;var cs=getComputedStyle(w);var cols=parseInt(cs.getPropertyValue('--cv-cols'),10)||12;var rh=parseFloat(cs.getPropertyValue('--cv-rowh'))||24;return {cols:cols,rowH:rh,cellW:(w.clientWidth/cols)||1};}
function pos(el){var p=(curBp==='m')?'m':'d';return {x:parseInt(el.getAttribute('data-'+p+'x'),10)||0,y:parseInt(el.getAttribute('data-'+p+'y'),10)||0,w:parseInt(el.getAttribute('data-'+p+'w'),10)||1,h:parseInt(el.getAttribute('data-'+p+'h'),10)||1};}
function setPos(el,x,y,w,h){el.style.gridColumn=(x+1)+'/span '+w;el.style.gridRow=(y+1)+'/span '+h;var p=(curBp==='m')?'m':'d';el.setAttribute('data-'+p+'x',x);el.setAttribute('data-'+p+'y',y);el.setAttribute('data-'+p+'w',w);el.setAttribute('data-'+p+'h',h);}
document.addEventListener('mouseover',function(e){if(themeMode||editing||dragging||elDrag||elResize)return;var b=e.target.closest&&e.target.closest('[data-cz-block]');if(b)b.classList.add('cz-hover');});
document.addEventListener('mouseout',function(e){var b=e.target.closest&&e.target.closest('[data-cz-block]');if(b)b.classList.remove('cz-hover');});
document.addEventListener('click',function(e){
  var a=e.target.closest&&e.target.closest('a');if(a)e.preventDefault();
  if(editing&&editing.contains(e.target))return;
  if(moved){moved=false;return;}
  if(themeMode){probeThemeRegion(e.target);return;}
  var ce=e.target.closest&&e.target.closest('.cz-el');
  var b=e.target.closest&&e.target.closest('[data-cz-block]');if(!b)return;
  var i=parseInt(b.getAttribute('data-cz-block'),10);
  if(ce){if(ce!==selEl){selectEl(ce);postSelectEl(ce);}return;}
  var f=e.target.closest&&e.target.closest('[data-cz-field]');
  var r=b.getBoundingClientRect();
  highlight(i);
  post({type:'cz-select',block:i,field:f?f.getAttribute('data-cz-field'):undefined,rect:{top:r.top,left:r.left,width:r.width,height:r.height}});
},true);
document.addEventListener('dblclick',function(e){
  if(themeMode||restrictMode)return;
  var f=e.target.closest&&e.target.closest('[data-cz-field]');if(!f)return;
  e.preventDefault();
  if(editing&&editing!==f)editing.blur();
  clearHandles();
  editing=f;origText=f.innerText;cancelEdit=false;
  f.setAttribute('contenteditable','true');f.classList.add('cz-editing');
  post({type:'cz-editing-start'});f.focus();
});
document.addEventListener('keydown',function(e){
  if(!editing)return;
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();editing.blur();}
  else if(e.key==='Escape'){cancelEdit=true;editing.blur();}
});
document.addEventListener('blur',function(e){
  if(!editing||e.target!==editing)return;
  var f=editing;editing=null;
  f.removeAttribute('contenteditable');f.classList.remove('cz-editing');
  var i=idxOf(f),field=f.getAttribute('data-cz-field');
  if(cancelEdit){f.innerText=origText;cancelEdit=false;}
  else{var v=f.innerText.replace(/\\s+$/,'');if(v!==origText)post({type:'cz-edit',block:i,field:field,value:v});}
  if(selEl===f)addHandles(f);
  post({type:'cz-editing-end'});
},true);
document.addEventListener('pointerdown',function(e){
  if(editing||themeMode||restrictMode)return;
  var h=e.target.closest&&e.target.closest('.cz-cv-h');
  if(h&&selEl){e.preventDefault();gg=gridInfo(selEl);if(!gg)return;elResize=selEl;rdir=h.getAttribute('data-dir');var p=pos(selEl);sx=p.x;sy=p.y;sw=p.w;sh=p.h;gx=e.clientX;gy=e.clientY;moved=false;downIdx=-1;dragging=false;pid=e.pointerId;try{selEl.setPointerCapture(pid);}catch(_){}return;}
  var ce=e.target.closest&&e.target.closest('.cz-el');
  if(ce){gg=gridInfo(ce);if(!gg)return;if(ce!==selEl){selectEl(ce);postSelectEl(ce);}elDrag=ce;var q=pos(ce);sx=q.x;sy=q.y;sw=q.w;sh=q.h;gx=e.clientX;gy=e.clientY;moved=false;downIdx=-1;dragging=false;pid=e.pointerId;try{ce.setPointerCapture(pid);}catch(_){}return;}
  var b=e.target.closest&&e.target.closest('[data-cz-block]');if(!b)return;
  downIdx=parseInt(b.getAttribute('data-cz-block'),10);downY=e.clientY;moved=false;dragFrom=downIdx;dragging=false;
});
function startedMove(e){if(moved)return true;if(Math.abs(e.clientX-gx)<4&&Math.abs(e.clientY-gy)<4)return false;moved=true;document.body.classList.add('cz-cv-grabbing');post({type:'cz-editing-start'});return true;}
document.addEventListener('pointermove',function(e){
  if(elDrag){
    if(!startedMove(e))return;
    var dx=Math.round((e.clientX-gx)/gg.cellW),dy=Math.round((e.clientY-gy)/gg.rowH);
    setPos(elDrag,clamp(sx+dx,0,gg.cols-sw),Math.max(0,sy+dy),sw,sh);e.preventDefault();return;
  }
  if(elResize){
    if(!startedMove(e))return;
    var cx=Math.round((e.clientX-gx)/gg.cellW),cy=Math.round((e.clientY-gy)/gg.rowH);
    var x=sx,y=sy,w=sw,h=sh;
    if(rdir.indexOf('e')>=0)w=clamp(sw+cx,1,gg.cols-sx);
    if(rdir.indexOf('s')>=0)h=Math.max(1,sh+cy);
    if(rdir.indexOf('w')>=0){var nx=clamp(sx+cx,0,sx+sw-1);w=sw+(sx-nx);x=nx;}
    if(rdir.indexOf('n')>=0){var ny=clamp(sy+cy,0,sy+sh-1);h=sh+(sy-ny);y=ny;}
    setPos(elResize,x,y,w,h);e.preventDefault();return;
  }
  if(downIdx<0||editing)return;
  if(!dragging){if(Math.abs(e.clientY-downY)<6)return;dragging=true;moved=true;document.body.classList.add('cz-dragging');post({type:'cz-editing-start'});}
  showDrop(targetIdx(e.clientY));e.preventDefault();
},{passive:false});
function targetIdx(y){var bs=blocks(),to=bs.length;for(var k=0;k<bs.length;k++){var r=bs[k].getBoundingClientRect();if(y<r.top+r.height/2){to=k;break;}}return to;}
function showDrop(to){removeDrop();var bs=blocks();dropLine=document.createElement('div');dropLine.className='cz-drop';var main=document.querySelector('main');if(to>=bs.length)main.appendChild(dropLine);else main.insertBefore(dropLine,bs[to]);}
function removeDrop(){if(dropLine&&dropLine.parentNode)dropLine.parentNode.removeChild(dropLine);dropLine=null;}
document.addEventListener('pointerup',function(e){
  var el=elDrag||elResize;
  if(el){
    try{el.releasePointerCapture(pid);}catch(_){}
    if(moved){var p=pos(el);post({type:elDrag?'cz-elem-move':'cz-elem-resize',block:idxOf(el),id:el.getAttribute('data-cz-id'),bp:curBp,pos:p});document.body.classList.remove('cz-cv-grabbing');post({type:'cz-editing-end'});}
    elDrag=null;elResize=null;setTimeout(function(){moved=false;},0);return;
  }
  if(dragging){
    var to=targetIdx(e.clientY);removeDrop();document.body.classList.remove('cz-dragging');
    var dest=to>dragFrom?to-1:to;
    if(dest!==dragFrom)post({type:'cz-reorder',from:dragFrom,to:dest});
    post({type:'cz-editing-end'});dragging=false;setTimeout(function(){moved=false;},0);
  }
  downIdx=-1;
});
window.addEventListener('message',function(e){
  var d=e.data||{};
  if(d.type==='cz-highlight'){highlight(d.block);if(d.scroll){var _hb=blockEl(d.block);if(_hb&&_hb.scrollIntoView)_hb.scrollIntoView({block:'center',behavior:'smooth'});}}
  else if(d.type==='cz-clear')clearSel();
  else if(d.type==='cz-bp')curBp=(d.bp==='m')?'m':'d';
  else if(d.type==='cz-elem-highlight'){var el=document.querySelector('.cz-el[data-cz-id="'+d.id+'"]');if(el)selectEl(el);}
  else if(d.type==='cz-theme-highlight')highlightTheme(d.region);
  else if(d.type==='cz-theme-clear')clearThemeHl();
  else if(d.type==='cz-theme-open')themeMode=true;
  else if(d.type==='cz-theme-close'){themeMode=false;clearThemeHl();}
  else if(d.type==='cz-mode')restrictMode=(d.mode==='form');
});
post({type:'cz-ready'});
})();</script>"""


_STORE_JS = r"""(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
if(RT.preview){box.innerHTML='<p style="color:var(--muted)">Your products appear here once your site is live.</p>';return;}
function field(f){var req=f.required?' required':'';var l='<label class="cz-label">'+RT.esc(f.label||f.key)+'</label>';
if(f.type==='textarea')return '<div>'+l+'<textarea class="cz-field" data-k="'+RT.esc(f.key)+'"'+req+'></textarea></div>';
if(f.type==='select'){var o=(f.options||[]).map(function(x){return '<option>'+RT.esc(x)+'</option>';}).join('');return '<div>'+l+'<select class="cz-field" data-k="'+RT.esc(f.key)+'"'+req+'>'+o+'</select></div>';}
var ty=(['email','number','tel','date'].indexOf(f.type)>=0)?f.type:'text';return '<div>'+l+'<input class="cz-field" type="'+ty+'" data-k="'+RT.esc(f.key)+'"'+req+' /></div>';}
function optsHtml(p){return (p.option_groups||[]).map(function(g){
return '<div class="cz-opt-group" data-group="'+RT.esc(g.id)+'" data-single="'+(g.select_type==='single'?'1':'')+'" data-required="'+(g.required?'1':'')+'"><label class="cz-label">'+RT.esc(g.name)+(g.required?' *':'')+'</label><div class="cz-opts">'+
(g.options||[]).map(function(o){var dc=o.price_delta_cents||0;var d=dc?(' '+(dc>0?'+':'−')+RT.money(Math.abs(dc),p.currency)):'';
return '<button type="button" class="cz-opt" data-opt="'+RT.esc(o.id)+'" data-delta="'+dc+'">'+RT.esc(o.name)+d+'</button>';}).join('')+'</div></div>';}).join('');}
function stars(n){n=Math.round(n||0);var s='';for(var i=1;i<=5;i++)s+=(i<=n?'★':'☆');return s;}
var REVIEWS=[];
// One shared product-detail overlay (acts like a product page).
var ov=document.createElement('div');ov.className='cz-pd';ov.hidden=true;
ov.innerHTML='<div class="cz-pd__panel"><button class="cz-pd__x" aria-label="Close">×</button><div class="cz-pd__grid"><div class="cz-pd__media" data-media></div><div class="cz-pd__info" data-info></div></div><div class="cz-pd__reviews" data-reviews></div></div>';
document.body.appendChild(ov);
function hideDetail(){ov.hidden=true;document.body.style.overflow='';}
function dismiss(){if(history.state&&history.state.czpd)history.back();else hideDetail();}
ov.querySelector('.cz-pd__x').addEventListener('click',dismiss);
ov.addEventListener('click',function(e){if(e.target===ov)dismiss();});
window.addEventListener('popstate',function(){if(!ov.hidden)hideDetail();});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!ov.hidden)dismiss();});
function reviewsHtml(){if(!REVIEWS.length)return '';
var avg=REVIEWS.reduce(function(a,r){return a+(r.rating||0);},0)/REVIEWS.length;
return '<h3 class="cz-pd__rtitle">What clients say <span class="cz-pd__rstars">'+stars(avg)+'</span><span class="cz-pd__rn">'+REVIEWS.length+' review'+(REVIEWS.length>1?'s':'')+'</span></h3>'+
'<div class="cz-pd__rlist">'+REVIEWS.map(function(r){return '<figure class="cz-review"><div class="cz-review__stars">'+stars(r.rating)+'</div><blockquote>'+RT.esc(r.body)+'</blockquote><figcaption>'+RT.esc(r.author_name)+'</figcaption></figure>';}).join('')+'</div>';}
function openDetail(p){
var iu=RT.url(p.image_url);
ov.querySelector('[data-media]').innerHTML=iu?'<img src="'+RT.esc(iu)+'" alt="" />':'<div class="cz-pd__noimg"></div>';
var priceHtml;if(p.discount_percent&&p.discounted_price_cents!=null){priceHtml='<span class="cz-pd__was">'+RT.money(p.price_cents,p.currency)+'</span>'+RT.money(p.discounted_price_cents,p.currency)+'<span class="cz-pd__off">'+p.discount_percent+'% off</span>';}else{priceHtml=p.price_cents?RT.money(p.price_cents,p.currency):'Free';}
var booking=p.fulfillment==='booking';
var info=ov.querySelector('[data-info]');
info.innerHTML=(p.category?'<div class="cz-eyebrow">'+RT.esc(p.category)+'</div>':'')+
'<h2 class="cz-pd__name">'+RT.esc(p.name)+'</h2>'+
'<div class="cz-pd__price">'+priceHtml+'</div>'+
(p.description?'<p class="cz-pd__desc">'+RT.esc(p.description)+'</p>':'')+
optsHtml(p)+(p.intake_fields||[]).map(field).join('')+
(booking?'<div><label class="cz-label">Preferred time</label><input class="cz-field" type="datetime-local" data-when /></div>':'')+
'<div class="cz-pd__buy"><label class="cz-label">Quantity</label><input class="cz-field cz-pd__qty" type="number" min="1" value="1" data-qty />'+
'<input class="cz-field" type="email" data-email placeholder="Your email" /><input class="cz-field" type="text" data-name placeholder="Your name" />'+
'<button class="cz-btn cz-btn--solid cz-btn--block" data-go></button><p class="cz-msg"></p></div>';
var sb=info.querySelector('[data-go]'),msg=info.querySelector('.cz-msg');
function unit(){var s=p.price_cents||0;info.querySelectorAll('.cz-opt--on').forEach(function(b){s+=parseInt(b.getAttribute('data-delta'),10)||0;});s=Math.max(0,s);if(p.discount_percent)s=Math.round(s*(100-p.discount_percent)/100);return s;}
function qn(){return Math.max(1,parseInt(info.querySelector('[data-qty]').value,10)||1);}
function refresh(){sb.textContent=(booking?'Request — ':'Add to bag — ')+RT.money(unit()*qn(),p.currency);}
info.querySelectorAll('.cz-opt-group').forEach(function(g){var single=g.getAttribute('data-single')==='1';g.querySelectorAll('.cz-opt').forEach(function(o){o.addEventListener('click',function(){if(single){g.querySelectorAll('.cz-opt').forEach(function(x){x.classList.remove('cz-opt--on');});o.classList.add('cz-opt--on');}else o.classList.toggle('cz-opt--on');refresh();});});});
info.querySelector('[data-qty]').addEventListener('input',refresh);refresh();
sb.addEventListener('click',function(){var email=info.querySelector('[data-email]').value.trim();
if(!email){msg.textContent='Email required';msg.className='cz-msg err';return;}
var ok=true;info.querySelectorAll('.cz-opt-group').forEach(function(g){if(g.getAttribute('data-required')==='1'&&!g.querySelector('.cz-opt--on'))ok=false;});
if(!ok){msg.textContent='Please choose the required options';msg.className='cz-msg err';return;}
var optIds=[];info.querySelectorAll('.cz-opt--on').forEach(function(b){optIds.push(b.getAttribute('data-opt'));});
var ans={};(p.intake_fields||[]).forEach(function(f){var el=info.querySelector('[data-k="'+f.key+'"]');if(el)ans[f.key]=el.value;});
var item={product_id:p.id,quantity:qn(),intake_answers:ans,selected_option_ids:optIds};
if(booking){var w=info.querySelector('[data-when]').value;if(!w){msg.textContent='Pick a time';msg.className='cz-msg err';return;}item.starts_at=w;}
sb.disabled=true;msg.textContent='Placing order…';msg.className='cz-msg';
RT.post('/orders',{customer_email:email,customer_name:info.querySelector('[data-name]').value.trim(),items:[item],success_url:location.href,cancel_url:location.href}).then(function(res){if(res&&res.checkout_url){msg.textContent='Redirecting to secure checkout…';window.location=res.checkout_url;return;}info.querySelector('.cz-pd__buy').innerHTML='<p class="cz-msg ok">Order placed. We will email you'+(p.fulfillment==='digital'?' your download once confirmed':'')+'.</p>';
}).catch(function(e){sb.disabled=false;refresh();msg.textContent=e.message;msg.className='cz-msg err';});});
ov.querySelector('[data-reviews]').innerHTML=reviewsHtml();
ov.querySelector('.cz-pd__panel').scrollTop=0;ov.hidden=false;document.body.style.overflow='hidden';
if(!(history.state&&history.state.czpd))history.pushState({czpd:1},'');
}
function card(p){var c=document.createElement('button');c.type='button';c.className='cz-product';
var iu=RT.url(p.image_url);var img=iu?'<img class="cz-product__img" src="'+RT.esc(iu)+'" alt="" />':'<div class="cz-product__img"></div>';
var price;if(p.discount_percent&&p.discounted_price_cents!=null){price='<span class="cz-pd__was">'+RT.money(p.price_cents,p.currency)+'</span>'+RT.money(p.discounted_price_cents,p.currency);}else{price=p.price_cents?RT.money(p.price_cents,p.currency):'Free';}
c.innerHTML=img+'<div class="cz-product__body"><h3>'+RT.esc(p.name)+'</h3><div class="cz-product__foot"><span class="cz-price">'+price+'</span>'+((p.option_groups||[]).length?'<span class="cz-product__opts">Options</span>':'')+'</div></div>';
c.addEventListener('click',function(){openDetail(p);});return c;}
function grid(list){var g=document.createElement('div');g.className='cz-store-grid';list.forEach(function(p){g.appendChild(card(p));});return g;}
Promise.all([RT.get('/products'),RT.get('/reviews').catch(function(){return [];})]).then(function(r){
var items=r[0]||[];REVIEWS=r[1]||[];
if(!items.length){box.innerHTML='<p style="color:var(--muted)">No products yet.</p>';return;}box.innerHTML='';
var cats=[],byCat={};items.forEach(function(p){var k=(p.category||'').trim();if(!(k in byCat)){byCat[k]=[];cats.push(k);}byCat[k].push(p);});
if(cats.filter(function(k){return k;}).length===0){box.appendChild(grid(items));return;}
cats.sort(function(a,b){if(!a)return 1;if(!b)return -1;return 0;});
cats.forEach(function(k){if(k){var h=document.createElement('h3');h.className='cz-store-cat';h.textContent=k;box.appendChild(h);}box.appendChild(grid(byCat[k]));});
}).catch(function(){box.innerHTML='<p style="color:var(--muted)">Unable to load products.</p>';});})();"""


_BOOKING_JS = r"""(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
if(RT.preview){box.innerHTML='<p style="color:var(--muted)">Visitors pick from your open times here once your site is live.</p>';return;}
var selLoc='';
function locP(){return selLoc?('location_id='+encodeURIComponent(selLoc)):'';}
function qjoin(){var p=[];for(var i=0;i<arguments.length;i++){if(arguments[i])p.push(arguments[i]);}return p.length?('?'+p.join('&')):'';}
RT.get('/locations').catch(function(){return [];}).then(function(locs){locs=locs||[];
if(locs.length>1){box.innerHTML='<p class="cz-label">Choose a location</p><div class="cz-staffrow">'+
locs.map(function(l){return '<button type="button" class="cz-staff" data-loc-id="'+RT.esc(l.id)+'">'+RT.esc(l.name)+(l.address?'<span style="display:block;font-size:.75em;color:var(--muted)">'+RT.esc(l.address)+'</span>':'')+'</button>';}).join('')+'</div>';
box.querySelectorAll('[data-loc-id]').forEach(function(b){b.addEventListener('click',function(){selLoc=b.getAttribute('data-loc-id');start();});});}
else{selLoc=locs.length===1?locs[0].id:'';start();}});
function start(){
Promise.all([RT.get('/booking-types'+qjoin(locP())),RT.get('/rider').catch(function(){return {items:[]};}),RT.get('/staff'+qjoin(locP())).catch(function(){return [];})]).then(function(r){
var types=r[0],rider=(r[1]&&r[1].items)||[],staffList=r[2]||[];
if(!types.length){box.innerHTML='<p style="color:var(--muted)">No appointments available.</p>';return;}
var byId={};types.forEach(function(t){byId[t.id]=t;});
var staffById={};staffList.forEach(function(s){staffById[s.id]=s;});
var selStaff=null;
function priceLabel(t){if(!t.price_cents)return 'Free';var m=RT.money(t.price_cents,'USD');return t.pricing_mode==='hourly'?m+'/hr':m;}
var reqRider=rider.filter(function(i){return i.is_required;});
var riderHtml='';
if(rider.length){riderHtml='<div class="cz-rider" style="border:1px solid var(--line);border-radius:var(--radius);padding:.85rem 1rem;margin:.5rem 0;font-size:.9rem">'+
'<div style="font-weight:600;margin-bottom:.4rem">Booking requirements</div><ul style="margin:0 0 .5rem;padding-left:1.1rem;color:var(--muted)">'+
rider.map(function(i){return '<li>'+RT.esc(i.label)+(i.detail?' — '+RT.esc(i.detail):'')+(i.is_required?'':' (optional)')+'</li>';}).join('')+'</ul>'+
(reqRider.length?'<label style="display:flex;gap:.5rem;align-items:flex-start"><input type="checkbox" data-ack /> <span>I have read and agree to these requirements.</span></label>':'')+'</div>';}
box.innerHTML='<select class="cz-field" data-bt>'+types.map(function(t){return '<option value="'+RT.esc(t.id)+'">'+RT.esc(t.name)+' ('+t.duration_minutes+' min) · '+priceLabel(t)+'</option>';}).join('')+'</select>'+
'<div data-staff style="margin:.45rem 0"></div>'+
'<div data-slots style="margin:.5rem 0"><p style="color:var(--muted)">Loading times…</p></div>'+
'<input class="cz-field" type="email" data-email placeholder="Your email" /><input class="cz-field" type="text" data-name placeholder="Your name" />'+
riderHtml+
'<button class="cz-btn cz-btn--solid cz-btn--block" data-go disabled>Select a time</button><p class="cz-msg"></p>';
var sb=box.querySelector('[data-go]'),msg=box.querySelector('.cz-msg'),btSel=box.querySelector('[data-bt]'),slotWrap=box.querySelector('[data-slots]'),staffWrap=box.querySelector('[data-staff]'),sel=null;
function cur(){return byId[btSel.value];}
function renderStaff(t){selStaff=null;var ids=(t&&t.staff_ids)||[];if(!ids.length){staffWrap.innerHTML='';return;}
staffWrap.innerHTML='<p class="cz-label">With</p><div class="cz-staffrow"><button type="button" class="cz-staff cz-staff--on" data-staff-id="">Any available</button>'+
ids.map(function(id){var s=staffById[id];if(!s)return '';var iu=RT.url(s.image_url);return '<button type="button" class="cz-staff" data-staff-id="'+RT.esc(id)+'">'+(iu?'<img src="'+RT.esc(iu)+'" alt="" />':'')+RT.esc(s.name)+'</button>';}).join('')+'</div>';
staffWrap.querySelectorAll('.cz-staff').forEach(function(b){b.addEventListener('click',function(){staffWrap.querySelectorAll('.cz-staff').forEach(function(x){x.classList.remove('cz-staff--on');});b.classList.add('cz-staff--on');selStaff=b.getAttribute('data-staff-id')||null;loadSlots();});});}
function loadSlots(){sel=null;sb.disabled=true;sb.textContent='Select a time';slotWrap.innerHTML='<p style="color:var(--muted)">Loading times…</p>';
var t=cur();if(!t)return;
RT.get('/booking-types/'+encodeURIComponent(t.id)+'/slots'+qjoin(locP(),selStaff?('staff_id='+encodeURIComponent(selStaff)):'')).then(function(d){var slots=(d&&d.slots)||[];
if(!slots.length){slotWrap.innerHTML='<p style="color:var(--muted)">No open times in the next few weeks. Please check back soon.</p>';return;}
var days=[],byDay={};slots.forEach(function(s){if(!byDay[s.date]){byDay[s.date]=[];days.push(s.date);}byDay[s.date].push(s);});
// One price line when every slot costs the same; otherwise show price per time.
var uniform=slots.every(function(s){return s.price_cents===slots[0].price_cents;});
var priceNote=(uniform&&slots[0].price_cents)?(' · '+RT.money(slots[0].price_cents,'USD')+(t.pricing_mode==='hourly'?'/hr':'')):'';
var tzNote=d.timezone?(' · times in '+RT.esc(d.timezone)):'';
var discNote=d.discount_percent?(' · <span style="color:var(--brand)">'+d.discount_percent+'% off</span>'):'';
slotWrap.innerHTML='<p class="cz-label">Pick a day'+tzNote+priceNote+discNote+'</p>'+
'<div class="cz-daystrip">'+days.map(function(dt,i){return '<button type="button" class="cz-day" data-day="'+i+'">'+RT.esc(byDay[dt][0].day_label)+'<span>'+byDay[dt].length+' open</span></button>';}).join('')+'</div>'+
'<div class="cz-times" data-times></div>';
var timesWrap=slotWrap.querySelector('[data-times]'),dayBtns=slotWrap.querySelectorAll('.cz-day');
function showDay(i){sel=null;sb.disabled=true;sb.textContent='Select a time';
dayBtns.forEach(function(b,j){b.classList.toggle('cz-day--on',j===i);});
timesWrap.innerHTML=byDay[days[i]].map(function(s){var pl=(!uniform&&s.price_cents)?(' · '+RT.money(s.price_cents,'USD')):'';
return '<button type="button" class="cz-slot" data-start="'+RT.esc(s.start)+'" data-end="'+RT.esc(s.end)+'">'+RT.esc(s.time_label)+pl+'</button>';}).join('');
timesWrap.querySelectorAll('.cz-slot').forEach(function(btn){btn.addEventListener('click',function(){
timesWrap.querySelectorAll('.cz-slot').forEach(function(b){b.classList.remove('cz-slot--on');});
btn.classList.add('cz-slot--on');
sel={start:btn.getAttribute('data-start'),end:btn.getAttribute('data-end')};sb.disabled=false;sb.textContent='Request booking';});});}
dayBtns.forEach(function(b,i){b.addEventListener('click',function(){showDay(i);});});showDay(0);
}).catch(function(){slotWrap.innerHTML='<p style="color:var(--muted)">Could not load times.</p>';});}
function onType(){renderStaff(cur());loadSlots();}
btSel.addEventListener('change',onType);onType();
sb.addEventListener('click',function(){var t=cur(),email=box.querySelector('[data-email]').value.trim();
if(!sel){msg.textContent='Pick a time';msg.className='cz-msg err';return;}
if(!email){msg.textContent='Email required';msg.className='cz-msg err';return;}
var ackEl=box.querySelector('[data-ack]');if(ackEl&&!ackEl.checked){msg.textContent='Please agree to the requirements';msg.className='cz-msg err';return;}
var body={booking_type_id:t.id,starts_at:sel.start,customer_email:email,customer_name:box.querySelector('[data-name]').value.trim(),rider_acknowledged:ackEl?ackEl.checked:false};
if(t.pricing_mode==='hourly'&&sel.end)body.ends_at=sel.end;
if(selStaff)body.staff_id=selStaff;
if(selLoc)body.location_id=selLoc;
sb.disabled=true;msg.textContent='Requesting…';msg.className='cz-msg';
RT.post('/bookings',body).then(function(res){var price=res.quoted_price_cents?(' — '+RT.money(res.quoted_price_cents,'USD')):'';
var note=res.requires_approval?'Request sent for '+RT.esc(new Date(res.starts_at).toLocaleString())+price+'. The host will review and confirm by email.':'Booked for '+RT.esc(new Date(res.starts_at).toLocaleString())+price+'. A confirmation is on its way.';
box.innerHTML='<p class="cz-msg ok">'+note+'</p>';
}).catch(function(e){sb.disabled=false;sb.textContent='Request booking';msg.textContent=e.message;msg.className='cz-msg err';});});
}).catch(function(){box.innerHTML='<p style="color:var(--muted)">Unable to load.</p>';});}})();"""


_NEWSLETTER_JS = r"""(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
box.innerHTML='<div class="cz-inline"><input class="cz-field" type="email" data-email placeholder="you@example.com" /><button class="cz-btn cz-btn--solid">Subscribe</button></div><p class="cz-msg"></p>';
var sb=box.querySelector('button'),msg=box.querySelector('.cz-msg');
sb.addEventListener('click',function(){var email=box.querySelector('[data-email]').value.trim();
if(!email){msg.textContent='Email required';msg.className='cz-msg err';return;}
sb.disabled=true;RT.post('/subscribe',{email:email}).then(function(){box.innerHTML='<p class="cz-msg ok">You are subscribed.</p>';
}).catch(function(e){sb.disabled=false;msg.textContent=e.message;msg.className='cz-msg err';});});})();"""


_CONTACT_JS = r"""(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
var slug=box.getAttribute('data-form')||'';var sb=box.querySelector('button'),msg=box.querySelector('.cz-msg');
sb.addEventListener('click',function(){if(!slug){msg.textContent='Form not configured yet';msg.className='cz-msg err';return;}
var data={};box.querySelectorAll('[data-k]').forEach(function(el){data[el.getAttribute('data-k')]=el.value;});
sb.disabled=true;msg.textContent='Sending...';msg.className='cz-msg';
RT.post('/forms/'+encodeURIComponent(slug),{data:data,submitter_email:data.email||null}).then(function(){
box.innerHTML='<p class="cz-msg ok" style="text-align:center">Thanks - your message was sent.</p>';
}).catch(function(e){sb.disabled=false;msg.textContent=e.message;msg.className='cz-msg err';});});})();"""


_REVIEWS_JS = r"""(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
var wantForm=box.getAttribute('data-form')==='1';
function stars(n){n=n||0;var s='';for(var i=1;i<=5;i++){s+=i<=n?'★':'☆';}return s;}
function formHtml(){return wantForm?'<div class="cz-rv-form"><div class="cz-rv-form__t">Leave a review</div>'+
'<input class="cz-field" data-name placeholder="Your name" />'+
'<select class="cz-field" data-rating><option value="5">★★★★★</option><option value="4">★★★★</option><option value="3">★★★</option><option value="2">★★</option><option value="1">★</option></select>'+
'<textarea class="cz-field" data-body rows="3" placeholder="Share your experience"></textarea>'+
'<button class="cz-btn cz-btn--solid cz-btn--block" data-go>Submit review</button><p class="cz-msg"></p></div>':'';}
function render(list){
var grid=list.length?('<div class="cz-reviews-grid">'+list.map(function(r){return '<figure class="cz-review"><div class="cz-review__stars">'+stars(r.rating)+'</div><blockquote>'+RT.esc(r.body)+'</blockquote><figcaption>'+RT.esc(r.author_name)+'</figcaption></figure>';}).join('')+'</div>'):(wantForm?'':'<p style="color:var(--muted)">No reviews yet.</p>');
box.innerHTML=grid+formHtml();
if(!wantForm)return;
var go=box.querySelector('[data-go]'),msg=box.querySelector('.cz-msg');
go.addEventListener('click',function(){var name=box.querySelector('[data-name]').value.trim(),body=box.querySelector('[data-body]').value.trim(),rating=parseInt(box.querySelector('[data-rating]').value,10);
if(!name||!body){msg.textContent='Name and review are required';msg.className='cz-msg err';return;}
go.disabled=true;msg.textContent='Submitting…';msg.className='cz-msg';
RT.post('/reviews',{author_name:name,rating:rating,body:body}).then(function(){box.querySelector('.cz-rv-form').innerHTML='<p class="cz-msg ok" style="text-align:center">Thanks! Your review will appear once approved.</p>';
}).catch(function(e){go.disabled=false;msg.textContent=e.message;msg.className='cz-msg err';});});}
if(RT.preview){render([{author_name:'Sample Customer',rating:5,body:'Approved reviews from your customers show here.'}]);return;}
RT.get('/reviews').then(function(list){render(list||[]);}).catch(function(){box.innerHTML='<p style="color:var(--muted)">Unable to load reviews.</p>';});
})();"""


def _reviews(b, t):
    wid = "rv" + str(_uid())
    show_form = b.get("allowSubmissions") is not False  # default on
    return (f'<section class="cz-reviews"><div class="cz-wrap">{_head(b)}'
            f'<div id="{wid}" class="cz-reviews-box" data-form="{"1" if show_form else "0"}">'
            f'<p style="color:var(--muted)">Loading reviews…</p></div></div></section>'
            f'<script>{_REVIEWS_JS.replace("__ID__", wid)}</script>')


def _store(b, t):
    # `id="shop"` is a stable anchor any CTA/nav can link to (#shop) regardless
    # of the seller's vocation — the generalizable "go buy" destination.
    wid = "st" + str(_uid())
    return (f'<section id="shop" class="cz-store"><div class="cz-wrap">{_head(b)}'
            f'<div id="{wid}" class="cz-store-box"><p style="color:var(--muted)">Loading products...</p></div></div></section>'
            f'<script>{_STORE_JS.replace("__ID__", wid)}</script>')


def _booking(b, t):
    wid = "bk" + str(_uid())
    return (f'<section id="book" class="cz-form-sec"><div class="cz-wrap">{_head(b)}'
            f'<div id="{wid}" class="cz-form"><p style="color:var(--muted)">Loading...</p></div></div></section>'
            f'<script>{_BOOKING_JS.replace("__ID__", wid)}</script>')


def _newsletter(b, t):
    wid = "nl" + str(_uid())
    return (f'<section class="cz-form-sec"><div class="cz-narrow" style="text-align:center">{_head(b)}'
            f'<div id="{wid}" class="cz-form"></div></div></section>'
            f'<script>{_NEWSLETTER_JS.replace("__ID__", wid)}</script>')


def _contact(b, t):
    wid = "cf" + str(_uid())
    fields = b.get("fields") or ["name", "email", "message"]
    form_slug = b.get("formSlug") or b.get("form_slug") or ""
    sub = f'<p>{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    inputs = "".join(
        (f'<textarea class="cz-field" data-k="{_esc(f)}" rows="4" placeholder="{_esc(f.capitalize())}"></textarea>'
         if f == "message" else
         f'<input class="cz-field" data-k="{_esc(f)}" placeholder="{_esc(f.capitalize())}" />')
        for f in fields if isinstance(f, str))
    return (f'<section class="cz-form-sec"><div class="cz-narrow">'
            f'<div class="cz-head"><h2>{_esc(b.get("heading") or "Get in touch")}</h2>{sub}</div>'
            f'<div id="{wid}" data-form="{_esc(form_slug)}" class="cz-form">{inputs}'
            f'<button class="cz-btn cz-btn--solid cz-btn--block">Send</button><p class="cz-msg"></p></div></div></section>'
            f'<script>{_CONTACT_JS.replace("__ID__", wid)}</script>')


# --- local presence: map + hours --------------------------------------------

def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _resolve_loc(t, b):
    """The location a map/hours block displays: the block's `location` id if it
    matches one, else the default (first, default-ordered) location, else None.
    Falls back to meta_config for single-location sites (no locations)."""
    locs = t.get("locations") or []
    if not locs:
        return None
    want = str(b.get("location") or "").strip() if isinstance(b, dict) else ""
    if want:
        for l in locs:
            if str(l.get("id")) == want:
                return l
    return locs[0]


def _map(b, t):
    """A "find us" block: address + directions deep links (no API key), plus an
    OpenStreetMap embed when the owner supplied lat/lng. Per-location when the
    site has locations."""
    loc = _resolve_loc(t, b) or {}
    meta = t.get("meta") or {}
    geo = meta.get("geo") if isinstance(meta.get("geo"), dict) else {}
    addr = (b.get("address") or loc.get("address") or meta.get("contact_address") or "").strip()
    bl_lat = b.get("lat") if b.get("lat") not in (None, "") else (loc.get("lat") if loc.get("lat") is not None else geo.get("lat"))
    bl_lng = b.get("lng") if b.get("lng") not in (None, "") else (loc.get("lng") if loc.get("lng") is not None else geo.get("lng"))
    lat = _num(bl_lat)
    lng = _num(bl_lng)
    if not addr and lat is None:
        return ""

    embed = ""
    if lat is not None and lng is not None:
        d = 0.012
        src = (f"https://www.openstreetmap.org/export/embed.html?"
               f"bbox={lng - d},{lat - d},{lng + d},{lat + d}&layer=mapnik&marker={lat},{lng}")
        embed = f'<div class="cz-map__embed"><iframe loading="lazy" title="Map" src="{_esc(src)}"></iframe></div>'

    query = quote(addr) if addr else (f"{lat},{lng}" if lat is not None else "")
    actions = ""
    if query:
        g = f"https://www.google.com/maps/search/?api=1&query={query}"
        addr_html = f'<p class="cz-map__addr">{_esc(addr)}</p>' if addr else ""
        apple = (f'<a class="cz-btn cz-btn--ghost" href="https://maps.apple.com/?q={query}" '
                 f'target="_blank" rel="noopener noreferrer">Apple Maps</a>') if addr else ""
        actions = (f'{addr_html}<div class="cz-map__actions">'
                   f'<a class="cz-btn cz-btn--solid" href="{_esc(g)}" target="_blank" rel="noopener noreferrer">Get directions</a>'
                   f'{apple}</div>')
    return f'<section class="cz-map"><div class="cz-wrap">{_head(b)}{embed}{actions}</div></section>'


_OPENNOW_JS = (
    "<script>(function(){var C=window.__CAPPE__||{};var hours=C.hours||[];"
    "var el=document.querySelector('[data-opennow]');if(!el||!hours.length)return;"
    "function hm(s){var p=(s||'').split(':');return p.length===2?(parseInt(p[0],10)*60+parseInt(p[1],10)):null;}"
    "function localNow(tz){try{var f=new Intl.DateTimeFormat('en-US',{timeZone:tz||'UTC',hour12:false,weekday:'short',hour:'2-digit',minute:'2-digit'});"
    "var parts={};f.formatToParts(new Date()).forEach(function(p){parts[p.type]=p.value;});"
    "var wm={Mon:0,Tue:1,Wed:2,Thu:3,Fri:4,Sat:5,Sun:6};"
    "return {wd:wm[parts.weekday],mins:(parseInt(parts.hour,10)%24)*60+parseInt(parts.minute,10)};}catch(e){return null;}}"
    "var n=localNow(C.tz);if(!n||n.wd==null)return;"
    "function entry(d){for(var i=0;i<hours.length;i++){if(parseInt(hours[i].day,10)===d)return hours[i];}return null;}"
    "function openIn(e,mins){if(!e||e.closed)return false;var o=hm(e.open),c=hm(e.close);if(o==null||c==null)return false;return c>o?(o<=mins&&mins<c):(mins>=o);}"
    "var open=openIn(entry(n.wd),n.mins);"
    "if(!open){var y=entry((n.wd+6)%7);if(y&&!y.closed){var o=hm(y.open),c=hm(y.close);if(o!=null&&c!=null&&c<=o&&n.mins<c)open=true;}}"
    "el.textContent=open?'Open now':'Closed';el.className='cz-badge '+(open?'cz-badge--open':'cz-badge--closed');})();</script>"
)

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _hours(b, t):
    """Structured weekly hours table + a client-computed "Open now" badge (the
    badge is computed in-browser from injected hours+tz, so it's cache-safe)."""
    loc = _resolve_loc(t, b) or {}
    meta = t.get("meta") or {}
    hours = loc.get("hours") if (isinstance(loc.get("hours"), list) and loc.get("hours")) \
        else (meta.get("hours") if isinstance(meta.get("hours"), list) else [])
    if not hours:
        return ""
    rows = ""
    for i, name in enumerate(_DAY_NAMES):
        e = next((h for h in hours if isinstance(h, dict) and int(h.get("day", -1)) == i), None)
        if e and not e.get("closed") and e.get("open") and e.get("close"):
            val = f'{_esc(e["open"])} – {_esc(e["close"])}'
        else:
            val = '<span class="cz-hours__closed">Closed</span>'
        rows += f'<div class="cz-hours__row"><span>{name}</span><span>{val}</span></div>'
    return (f'<section class="cz-hours"><div class="cz-narrow" style="text-align:center">{_head(b)}'
            f'<span class="cz-badge" data-opennow></span>'
            f'<div class="cz-hours__list">{rows}</div></div></section>'
            f'{_OPENNOW_JS}')


# ── freeform grid-snap canvas block ─────────────────────────────────────────
# A `canvas` block lays its child elements (heading / text / image) on a CSS
# grid at explicit per-breakpoint coordinates (Squarespace "Fluid Engine" style).
# Stored opaquely in page content (no migration). Every value below is clamped /
# enum / hex / scheme-checked / id-regex'd — no raw user string reaches CSS/HTML.
_CV_COLS_MAX = 48
_CV_SPAN_MAX = 48
_CV_ROWS_MAX = 400
_CV_WEIGHTS = {"300", "400", "500", "600", "700", "800", "900"}
_CV_ALIGN = {"left", "center", "right", "justify"}
_CV_FIT = {"cover", "contain", "fill", "none"}
_CV_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_CV_SPACING_RE = re.compile(r"^-?[0-9]*\.?[0-9]+(em|px)$")

_CANVAS_CSS = (
    ".cz-canvas{padding:3rem 1.25rem}"
    ".cz-canvas .cz-cv-wrap{display:grid;grid-template-columns:repeat(var(--cv-cols,12),1fr);"
    "grid-auto-rows:var(--cv-rowh,24px);gap:0;max-width:72rem;margin:0 auto;position:relative}"
    ".cz-el{min-width:0;min-height:1em;overflow-wrap:break-word}"
    ".cz-canvas h2.cz-el,.cz-canvas p.cz-el{margin:0}"
    ".cz-el--img{overflow:hidden}"
    ".cz-el--img img{width:100%;height:100%;object-fit:var(--cv-fit,cover);"
    "border-radius:var(--cv-rad,0);display:block}"
    ".cz-canvas a.cz-el--btn{width:100%;height:100%}"
)


def _cv_safe_id(v: Any) -> str:
    s = str(v or "")
    return s if _CV_ID_RE.match(s) else ""


def _canvas(b, t, editable=False, index=0):
    grid = b.get("grid") if isinstance(b.get("grid"), dict) else {}
    mob = b.get("mobile") if isinstance(b.get("mobile"), dict) else {}
    cols = _clampi(grid.get("cols"), 1, _CV_COLS_MAX, 24)
    rowH = _clampi(grid.get("rowH"), 4, 200, 24)
    mcols = _clampi(mob.get("cols"), 1, _CV_COLS_MAX, 8)
    mrowH = _clampi(mob.get("rowH"), 4, 200, rowH)

    # Parse + clamp every element first (so we can derive a mobile stack order).
    parsed = []
    for el in (b.get("elements") if isinstance(b.get("elements"), list) else []):
        if not isinstance(el, dict):
            continue
        eid = _cv_safe_id(el.get("id"))
        kind = el.get("kind")
        if not eid or kind not in ("heading", "text", "image", "button"):
            continue
        d = el.get("d") if isinstance(el.get("d"), dict) else {}
        dx = _clampi(d.get("x"), 0, _CV_COLS_MAX, 0)
        dy = _clampi(d.get("y"), 0, _CV_ROWS_MAX, 0)
        dw = _clampi(d.get("w"), 1, _CV_SPAN_MAX, max(1, cols // 2))
        dh = _clampi(d.get("h"), 1, _CV_SPAN_MAX, 2)
        parsed.append((el, eid, kind, dx, dy, dw, dh))

    # Auto-derive mobile placement (full-width stack by desktop reading order)
    # for elements that have no explicit `m`. Mirrored client-side.
    derived = {}
    running = 0
    for k in sorted(range(len(parsed)), key=lambda j: (parsed[j][4], parsed[j][3])):
        dh = parsed[k][6]
        derived[k] = (0, running, mcols, max(1, dh))
        running += max(1, dh)

    # Placement (grid-column/row) + the wrap's grid vars go into a scoped <style>
    # — NOT inline — so the mobile @media rules can override them (inline styles
    # beat media queries). The JS engine reads coords from data-d*/data-m* attrs,
    # not the CSS, so live-drag still works. Only breakpoint-invariant visual
    # styling (font/color/fit/radius) is inlined on the element.
    els_html = []
    desk_rules = [f'.cz-cv-{index} .cz-cv-wrap{{--cv-cols:{cols};--cv-rowh:{rowH}px}}']
    mob_rules = [f'.cz-cv-{index} .cz-cv-wrap{{--cv-cols:{mcols};--cv-rowh:{mrowH}px}}']
    for k, (el, eid, kind, dx, dy, dw, dh) in enumerate(parsed):
        style = el.get("style") if isinstance(el.get("style"), dict) else {}
        parts = []
        if kind == "image":
            if style.get("fit") in _CV_FIT:
                parts.append(f"--cv-fit:{style['fit']}")
            rad = _clampi(style.get("radius"), 0, 200, 0)
            if rad:
                parts.append(f"--cv-rad:{rad}px")
        elif kind == "button":
            # Typography + button colors; variant (solid/outline) rides on a class.
            if style.get("font"):
                parts.append(f"font-family:{_font_stack(style['font'])}")
            sz = _clampi(style.get("size"), 8, 200, 0)
            if sz:
                parts.append(f"font-size:{sz}px")
            wt = str(style.get("weight") or "")
            if wt in _CV_WEIGHTS:
                parts.append(f"font-weight:{wt}")
            bg = _hexonly(style.get("bg"))
            if bg:
                parts.append(f"background:{bg}")
            col = _hexonly(style.get("color"))
            if col:
                parts.append(f"color:{col}")
            rad = _clampi(style.get("radius"), 0, 200, 0)
            if rad:
                parts.append(f"border-radius:{rad}px")
        else:
            if style.get("font"):
                parts.append(f"font-family:{_font_stack(style['font'])}")
            sz = _clampi(style.get("size"), 8, 200, 0)
            if sz:
                parts.append(f"font-size:{sz}px")
            wt = str(style.get("weight") or "")
            if wt in _CV_WEIGHTS:
                parts.append(f"font-weight:{wt}")
            sp = str(style.get("spacing") or "").strip()
            if _CV_SPACING_RE.match(sp):
                parts.append(f"letter-spacing:{sp}")
            try:
                lh = float(style.get("lineHeight"))
                if 0.8 <= lh <= 3.0:
                    parts.append(f"line-height:{lh}")
            except (TypeError, ValueError):
                pass
            col = _hexonly(style.get("color"))
            if col:
                parts.append(f"color:{col}")
            if style.get("align") in _CV_ALIGN:
                parts.append(f"text-align:{style['align']}")
        style_attr = f' style="{_clean_css(";".join(parts))}"' if parts else ""

        m = el.get("m") if isinstance(el.get("m"), dict) else None
        if m:
            mx = _clampi(m.get("x"), 0, _CV_COLS_MAX, 0)
            my = _clampi(m.get("y"), 0, _CV_ROWS_MAX, 0)
            mw = _clampi(m.get("w"), 1, _CV_SPAN_MAX, mcols)
            mh = _clampi(m.get("h"), 1, _CV_SPAN_MAX, dh)
        else:
            mx, my, mw, mh = derived[k]
        # Both breakpoints' coords ride on the element so the canvas runtime can
        # read the active set on drag (data attrs, not the rendered CSS).
        dataattr = (f' data-cz-id="{eid}" data-dx="{dx}" data-dy="{dy}" data-dw="{dw}" data-dh="{dh}"'
                    f' data-mx="{mx}" data-my="{my}" data-mw="{mw}" data-mh="{mh}"')
        desk_rules.append(f'.cz-cv-{index} [data-cz-id="{eid}"]{{grid-column:{dx + 1}/span {dw};grid-row:{dy + 1}/span {dh}}}')
        mob_rules.append(f'.cz-cv-{index} [data-cz-id="{eid}"]{{grid-column:{mx + 1}/span {mw};grid-row:{my + 1}/span {mh}}}')

        if kind == "image":
            src = _safe_image(el.get("src"))
            inner = f'<img src="{_esc(src)}" alt="{_esc(el.get("alt"))}" loading="lazy" />' if src else ""
            els_html.append(f'<div class="cz-el cz-el--img"{dataattr}{style_attr}>{inner}</div>')
        elif kind == "button":
            btncls = "cz-btn--ghost" if style.get("variant") == "outline" else "cz-btn--solid"
            href = _esc(_safe_href(el.get("href")))
            # data-cz-field tags the label for inline editing; the click runtime
            # already preventDefaults <a> navigation in the editor.
            els_html.append(
                f'<a class="cz-el cz-el--btn cz-btn {btncls}"{dataattr}{_fattr(eid, editable)} '
                f'href="{href}"{style_attr}>{_esc(el.get("text"))}</a>'
            )
        else:
            tag = "h2" if kind == "heading" else "p"
            # Only text/buttons get data-cz-field, so the inline-text editor
            # (dblclick → contenteditable) targets a label, never an image wrapper.
            els_html.append(
                f'<{tag} class="cz-el cz-el--{kind}"{dataattr}{_fattr(eid, editable)}{style_attr}>'
                f'{_esc(el.get("text"))}</{tag}>'
            )

    style_block = (f'<style>{"".join(desk_rules)}'
                   f'@media(max-width:767px){{{"".join(mob_rules)}}}</style>')
    wrap = f'<div class="cz-cv-wrap">{"".join(els_html)}</div>'
    return f'<section class="cz-canvas cz-cv-{index}">{style_block}{wrap}</section>'


_RENDERERS = {
    "hero": _hero, "features": _features, "gallery": _gallery, "pricing": _pricing,
    "testimonial": _testimonial, "cta": _cta, "menu": _menu, "posts": _posts,
    "stats": _stats, "logos": _logos, "faq": _faq, "bento": _bento, "split": _split,
    "credentials": _credentials, "reviews": _reviews, "map": _map, "hours": _hours,
    "text": _text, "contact": _contact, "store": _store, "booking": _booking, "newsletter": _newsletter,
}

# Renderers that accept a 3rd `editable` arg to emit `data-cz-field` tags for the
# canvas inline-text editor. Populated when those renderers are made editable-aware.
_EDITABLE_AWARE: frozenset[str] = frozenset({"hero", "cta", "text", "split", "features"})


def _render_block(block, t, index=None, editable=False):
    if not isinstance(block, dict):
        return ""
    btype = block.get("type")
    # Canvas needs the block index (for per-block CSS scoping) + editable, so it's
    # dispatched here rather than through _RENDERERS' (block, t[, editable]) shape.
    if btype == "canvas":
        raw = _canvas(block, t, editable, index if index is not None else 0)
        return _apply_design(raw, block.get("_design"), block_index=index, editable=editable) if raw else raw
    fn = _RENDERERS.get(btype)
    if fn:
        raw = fn(block, t, editable) if btype in _EDITABLE_AWARE else fn(block, t)
    else:
        body = block.get("body") or block.get("heading")
        raw = _text({"body": body}, t) if body else ""
    if not raw:
        return raw
    return _apply_design(raw, block.get("_design"), block_index=index, editable=editable)


# ── head / footer (business identity + SEO from meta_config) ────────────────

# Footer social links — text labels (no icon-font dep on the published site).
_SOCIAL_LABELS = [
    ("instagram", "Instagram"), ("x", "X"), ("tiktok", "TikTok"),
    ("youtube", "YouTube"), ("facebook", "Facebook"), ("linkedin", "LinkedIn"),
    ("website", "Website"),
]


def _head_seo(site: dict, page: dict, meta: dict) -> tuple[str, str]:
    """Return (title_text, extra_head_html) from meta_config.seo + favicon_url.
    Falls back to "{site} — {page}" when no SEO title is set."""
    seo = meta.get("seo") if isinstance(meta.get("seo"), dict) else {}
    title = (seo.get("title") or "").strip() or f"{site.get('name')} — {page.get('title')}"
    desc = (seo.get("description") or "").strip()
    og_img = _safe_image(seo.get("og_image"))
    favicon = _safe_image(meta.get("favicon_url"))
    parts = []
    if desc:
        parts.append(f'<meta name="description" content="{_esc(desc)}" />')
    parts.append(f'<meta property="og:title" content="{_esc((seo.get("title") or site.get("name")))}" />')
    if desc:
        parts.append(f'<meta property="og:description" content="{_esc(desc)}" />')
    if og_img:
        parts.append(f'<meta property="og:image" content="{_esc(og_img)}" />')
    parts.append('<meta property="og:type" content="website" />')
    if favicon:
        parts.append(f'<link rel="icon" href="{_esc(favicon)}" />')

    ld = _local_business_ld(site, meta)
    if ld:
        parts.append(ld)
    return _esc(title), "".join(parts)


_SCHEMA_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _local_business_ld(site: dict, meta: dict) -> str:
    """schema.org LocalBusiness JSON-LD for local SEO (static — crawler metadata,
    not a live 'open now')."""
    addr = (meta.get("contact_address") or "").strip()
    phone = (meta.get("contact_phone") or "").strip()
    hours = meta.get("hours") if isinstance(meta.get("hours"), list) else []
    geo = meta.get("geo") if isinstance(meta.get("geo"), dict) else {}
    if not (addr or phone or hours):
        return ""
    data: dict = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": site.get("name") or ""}
    if addr:
        data["address"] = addr
    if phone:
        data["telephone"] = phone
    logo = _safe_image(meta.get("logo_url"))
    if logo:
        data["image"] = logo
    lat, lng = _num(geo.get("lat")), _num(geo.get("lng"))
    if lat is not None and lng is not None:
        data["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lng}
    spec = []
    for h in hours:
        if not isinstance(h, dict) or h.get("closed") or not (h.get("open") and h.get("close")):
            continue
        try:
            day = _SCHEMA_DAYS[int(h["day"])]
        except (KeyError, ValueError, IndexError):
            continue
        spec.append({"@type": "OpeningHoursSpecification", "dayOfWeek": f"https://schema.org/{day}",
                     "opens": h["open"], "closes": h["close"]})
    if spec:
        data["openingHoursSpecification"] = spec
    # Neutralize any "</script>" inside owner-controlled strings.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">{payload}</script>'


def _footer(site: dict, meta: dict) -> str:
    """Footer with optional business contact info + social links from meta_config."""
    name = _esc(site.get("name"))
    contact = []
    ce = (meta.get("contact_email") or "").strip()
    cp = (meta.get("contact_phone") or "").strip()
    ca = (meta.get("contact_address") or "").strip()
    ch = (meta.get("business_hours") or "").strip()
    if ce:
        contact.append(f'<a href="mailto:{_esc(ce)}">{_esc(ce)}</a>')
    if cp:
        contact.append(f'<a href="tel:{_esc(cp.replace(" ", ""))}">{_esc(cp)}</a>')
    if ca:
        contact.append(f"<span>{_esc(ca)}</span>")
    if ch:
        contact.append(f"<span>{_esc(ch)}</span>")
    contact_html = f'<div class="cz-foot-contact">{"".join(contact)}</div>' if contact else ""

    social = meta.get("social") if isinstance(meta.get("social"), dict) else {}
    links = []
    for key, label in _SOCIAL_LABELS:
        u = (social.get(key) or "").strip() if isinstance(social, dict) else ""
        if u:
            links.append(
                f'<a href="{_esc(_safe_href(u))}" target="_blank" rel="noopener noreferrer nofollow">{label}</a>'
            )
    social_html = f'<div class="cz-foot-social">{"".join(links)}</div>' if links else ""

    return (f'<footer class="cz-footer"><div class="cz-wrap">{social_html}{contact_html}'
            f'<p>© {name}</p><p class="small">Built with Cappe</p></div></footer>')


# ── document ──────────────────────────────────────────────────────────────

# ── site-wide promos (announcement bar + pop-up modal) ──────────────────────
# Driven entirely by the DOM (data-* attrs + #czbar / #czpop ids) so this is a
# static constant — no per-render interpolation, no user strings in JS. Newsletter
# mode reuses the public /subscribe endpoint via the widget runtime (__CAPPE_RT__).
_PROMO_JS = r"""(function(){
var RT=window.__CAPPE_RT__,pv=RT&&RT.preview,edit=document.body.classList.contains('cz-editable');
var slug=((window.__CAPPE__||{}).slug)||'';
function k(s){return 'czp:'+slug+':'+s;}
var bar=document.getElementById('czbar');
if(bar){var bx=bar.querySelector('[data-czclose]');
  if(bx){if(!pv){try{if(localStorage.getItem(k('bar'))==='1')bar.setAttribute('hidden','');}catch(e){}}
    bx.addEventListener('click',function(){bar.setAttribute('hidden','');try{localStorage.setItem(k('bar'),'1');}catch(e){}});}}
var pop=document.getElementById('czpop');
if(pop){
  var trig=pop.getAttribute('data-trigger')||'load',
      delay=parseInt(pop.getAttribute('data-delay'),10)||0,
      freq=pop.getAttribute('data-freq')||'session',shown=false;
  function seen(){try{return (freq==='once'?localStorage:sessionStorage).getItem(k('pop'))==='1';}catch(e){return false;}}
  function mark(){try{(freq==='once'?localStorage:sessionStorage).setItem(k('pop'),'1');}catch(e){}}
  function open(){if(shown)return;if(!pv&&freq!=='always'&&seen())return;shown=true;
    pop.removeAttribute('hidden');requestAnimationFrame(function(){pop.classList.add('cz-in');});if(!pv)mark();}
  function close(){pop.classList.remove('cz-in');setTimeout(function(){pop.setAttribute('hidden','');},300);}
  [].slice.call(pop.querySelectorAll('[data-czclose]')).forEach(function(el){el.addEventListener('click',close);});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!pop.hasAttribute('hidden'))close();});
  if(pv){if(!edit)open();}
  else if(trig==='delay'){setTimeout(open,Math.max(0,delay)*1000);}
  else if(trig==='exit'){var armed=false;setTimeout(function(){armed=true;},2000);
    document.addEventListener('mouseout',function(e){if(armed&&!e.relatedTarget&&e.clientY<=0)open();});
    setTimeout(open,25000);}
  else{setTimeout(open,500);}
  var nf=pop.querySelector('[data-cznews]');
  if(nf&&RT){var inp=nf.querySelector('input'),btn=nf.querySelector('button'),msg=pop.querySelector('[data-czmsg]');
    btn.addEventListener('click',function(){var email=(inp.value||'').trim();
      if(!email){if(msg){msg.textContent='Email required';msg.className='cz-msg err';}return;}
      btn.disabled=true;RT.post('/subscribe',{email:email}).then(function(){
        nf.innerHTML='<p class="cz-msg ok">You are subscribed!</p>';
      }).catch(function(e){btn.disabled=false;if(msg){msg.textContent=e.message;msg.className='cz-msg err';}});});}
  var cp=pop.querySelector('[data-czcopy]');
  if(cp){cp.addEventListener('click',function(){var code=cp.getAttribute('data-code')||'';
    try{navigator.clipboard.writeText(code);cp.textContent='Copied!';setTimeout(function(){cp.textContent='Copy';},1500);}catch(e){}});}
}})();"""


def _promo_link(label: Any, href: Any, cls: str) -> str:
    if not label:
        return ""
    return f'<a class="{cls}" href="{_esc(_safe_href(href))}">{_esc(label)}</a>'


def _promos(meta: dict, t: dict) -> tuple[str, str, str]:
    """Site-wide promos from meta_config.promos → (bar_html, popup_html, js).
    All-empty when promos absent/disabled. Colors hex-only, text escaped; the
    pop-up newsletter mode reuses /subscribe via the widget runtime."""
    promos = meta.get("promos") if isinstance(meta.get("promos"), dict) else {}
    bar_html = popup_html = ""
    need_js = False

    bar = promos.get("bar") if isinstance(promos.get("bar"), dict) else {}
    if bar.get("enabled") and (bar.get("text") or bar.get("ctaLabel")):
        pos = "bottom" if bar.get("position") == "bottom" else "top"
        styles = []
        if _hexonly(bar.get("bg")):
            styles.append(f"--czbar-bg:{_hexonly(bar.get('bg'))}")
        if _hexonly(bar.get("color")):
            styles.append(f"--czbar-fg:{_hexonly(bar.get('color'))}")
        style_attr = f' style="{";".join(styles)}"' if styles else ""
        cta = _promo_link(bar.get("ctaLabel"), bar.get("ctaHref"), "cz-promobar__cta")
        dismiss = ('<button class="cz-promobar__x" data-czclose aria-label="Dismiss">&times;</button>'
                   if bar.get("dismissible") else "")
        bar_html = (f'<div class="cz-promobar cz-promobar--{pos}" id="czbar"{style_attr}>'
                    f'<div class="cz-promobar__in"><span class="cz-promobar__txt">{_esc(bar.get("text"))}</span>'
                    f'{cta}</div>{dismiss}</div>')
        if bar.get("dismissible"):
            need_js = True

    popup = promos.get("popup") if isinstance(promos.get("popup"), dict) else {}
    if popup.get("enabled") and (popup.get("heading") or popup.get("body")):
        trigger = popup.get("trigger") if popup.get("trigger") in ("load", "delay", "exit") else "load"
        delay = _clampi(popup.get("delaySec"), 0, 120, 5)
        freq = popup.get("frequency") if popup.get("frequency") in ("session", "always", "once") else "session"
        mode = popup.get("mode") if popup.get("mode") in ("newsletter", "cta", "code") else "newsletter"
        style_attr = f' style="--czpop-bg:{_hexonly(popup.get("bg"))}"' if _hexonly(popup.get("bg")) else ""
        img_u = _safe_image(popup.get("image"))
        img = f'<img class="cz-modal__img" src="{_esc(img_u)}" alt="" />' if img_u else ""
        heading = f'<h3>{_esc(popup.get("heading"))}</h3>' if popup.get("heading") else ""
        body = f'<p>{_esc(popup.get("body"))}</p>' if popup.get("body") else ""
        if mode == "newsletter":
            inner = ('<div data-cznews><div class="cz-inline">'
                     '<input class="cz-field" type="email" placeholder="you@example.com" />'
                     f'<button class="cz-btn cz-btn--solid">{_esc(popup.get("ctaLabel") or "Subscribe")}</button>'
                     '</div><p class="cz-msg" data-czmsg></p></div>')
        elif mode == "code":
            code = _esc(popup.get("code") or "")
            inner = (f'<div class="cz-modal__code"><b>{code}</b>'
                     f'<button class="cz-modal__copy" data-czcopy data-code="{code}">Copy</button></div>'
                     + _promo_link(popup.get("ctaLabel"), popup.get("ctaHref"), "cz-btn cz-btn--solid cz-btn--block"))
        else:  # cta
            inner = _promo_link(popup.get("ctaLabel") or "Learn more", popup.get("ctaHref"),
                                "cz-btn cz-btn--solid cz-btn--block")
        popup_html = (f'<div class="cz-modal" id="czpop" data-trigger="{trigger}" data-delay="{delay}" '
                      f'data-freq="{freq}" hidden><div class="cz-modal__scrim" data-czclose></div>'
                      f'<div class="cz-modal__card"{style_attr}>'
                      f'<button class="cz-modal__x" data-czclose aria-label="Close">&times;</button>'
                      f'{img}{heading}{body}{inner}</div></div>')
        need_js = True

    return bar_html, popup_html, (f'<script>{_PROMO_JS}</script>' if need_js else "")


def render_site_html(site: dict, page: dict, nav_pages: list[dict], preview: bool = False, editable: bool = False,
                     locations: list[dict] | None = None) -> str:
    t = _tokens(site.get("theme_config"))
    c = t["colors"]
    slug = site.get("slug") or ""
    home_slug = nav_pages[0]["slug"] if nav_pages else "home"
    locations = locations or []
    # Default location (default-first ordered) drives the global hours/tz badge;
    # the booking widget fetches /locations itself for the per-location picker.
    _def_loc = locations[0] if locations else {}
    # `preview` flags the editor's sandboxed iframe (no same-origin = no live API
    # fetch). Widgets read it to show a static placeholder instead of failing.
    _meta_ctx = site.get("meta_config") if isinstance(site.get("meta_config"), dict) else {}
    _ctx_hours = _def_loc.get("hours") if (isinstance(_def_loc.get("hours"), list) and _def_loc.get("hours")) \
        else (_meta_ctx.get("hours") if isinstance(_meta_ctx.get("hours"), list) else [])
    cappe_ctx = _js_obj({
        "slug": slug, "api": f"/api/cappe/public/sites/{slug}", "preview": bool(preview),
        "tz": _def_loc.get("timezone") or site.get("timezone") or "UTC",
        "hours": _ctx_hours,
    })

    meta = site.get("meta_config") or {}
    logo = _safe_image(meta.get("logo_url")) if isinstance(meta, dict) else None
    brand_inner = f'<img src="{_esc(logo)}" alt="{_esc(site.get("name"))}" />' if logo else _esc(site.get("name"))

    # Give block renderers access to site context (used by map/hours blocks).
    t["meta"] = meta if isinstance(meta, dict) else {}
    t["locations"] = locations
    t["site_name"] = site.get("name") or ""

    content = page.get("content") or {}
    blocks = content.get("blocks") if isinstance(content, dict) else None
    blocks = blocks if isinstance(blocks, list) else []
    body_html = "".join(_render_block(b, t, i, editable) for i, b in enumerate(blocks)) or _text({"body": page.get("title")}, t)

    nav_links = "".join(
        f'<a href="{"/" if p["slug"] in ("home", home_slug) else "/p/" + _esc(p["slug"])}">{_esc(p["title"])}</a>'
        for p in nav_pages)
    header_cls = "cz-header center" if t["navStyle"] == "centered" else "cz-header"

    theme_vars = (
        f":root{{--bg:{_clean_css(c['bg'])};--surface:{_clean_css(c['surface'])};"
        f"--ink:{_clean_css(c['text'])};--muted:{_clean_css(c['muted'])};--line:{_clean_css(c['border'])};"
        f"--brand:{_clean_css(c['brand'])};--brand-fg:{_clean_css(c['brandText'])};--accent:{_clean_css(c['accent'])};"
        f"--radius:{_clean_css(t['radius'])};--font-h:{_font_stack(t['heading'])};--font-b:{_font_stack(t['body'])}}}"
    )

    # Designer typography + brand-gradient tokens (all optional; absent = today).
    tc = site.get("theme_config") if isinstance(site.get("theme_config"), dict) else {}
    typ = tc.get("type") if isinstance(tc.get("type"), dict) else {}
    tc_colors = tc.get("colors") if isinstance(tc.get("colors"), dict) else {}
    _extra = []
    _hw = _clampi(typ.get("headingWeight"), 300, 900, 0)
    if _hw:
        _extra.append(f"--font-h-wght:{_hw}")
    _ls = str(typ.get("headingSpacing") or "").strip()
    if re.match(r"^-?[0-9]*\.?[0-9]+(em|px)$", _ls):
        _extra.append(f"--ls-h:{_ls}")
    # Global heading-size scale (percent, 70-140). Consumed by the heading rules
    # as `calc(var(--cz-h-scale,100)/100*<clamp>)`, so unset (or 100) computes to
    # the original clamp — identical to today. Emitted only when it actually
    # differs from the 100 default. Divide-in-CSS keeps the token a clean int.
    _hscale = _clampi(typ.get("headingScale"), 70, 140, 0)
    if _hscale and _hscale != 100:
        _extra.append(f"--cz-h-scale:{_hscale}")
    _grad = _design_gradient(tc_colors.get("brandGradient"))
    if _grad:
        _extra.append(f"--brand-grad:{_grad}")
    _extra += _style_vars(tc.get("style"))
    extra_vars = f":root{{{';'.join(_extra)}}}" if _extra else ""
    _hero_anim = typ.get("heroAnim")
    _anim_cls = f"cz-h-{_hero_anim}" if _hero_anim in ("rise", "shimmer") else ""

    meta_dict = meta if isinstance(meta, dict) else {}
    head_title, head_seo = _head_seo(site, page, meta_dict)
    needs_motion = t["premium"] or any(_block_has_motion(b) for b in blocks)
    body_cls = " ".join(filter(None, [
        "cz-premium" if t["premium"] else "",
        "cz-motion" if needs_motion else "",
        "cz-typw" if _hw else "",
        _anim_cls,
        "cz-editable" if editable else "",
    ]))
    premium_js = _MOTION_JS if needs_motion else ""
    canvas_js = _CANVAS_JS if editable else ""
    promo_bar, promo_popup, promo_js = _promos(meta_dict, t)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{head_title}</title>
  {head_seo}
  {_gfonts_link(t['heading'], t['body'])}
  <style>{theme_vars}{extra_vars}{_BASE_CSS}{_CANVAS_CSS}</style>
  <script>window.__CAPPE__={cappe_ctx};</script>
  {_widget_runtime()}
</head>
<body class="{body_cls}">
  {promo_bar}
  <header class="{header_cls}"><div class="cz-wrap cz-bar">
    <a class="cz-brand" href="/">{brand_inner}</a>
    <nav class="cz-nav">{nav_links}</nav>
  </div></header>
  <main>{body_html}</main>
  {_footer(site, meta_dict)}
  {promo_popup}
  {promo_js}
  {premium_js}
  {canvas_js}
</body>
</html>"""
