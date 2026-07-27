"""Design-token system + the bespoke per-block `_design` designer layer + the
base stylesheet. Consumes `..design_registry` for the color-token/keys-by-group
whitelists that keep `_design` values closed (no raw user string reaches
CSS)."""
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..design_registry import DESIGN_COLOR_TOKENS, DESIGN_KEYS_BY_GROUP
from .sanitize import _anchor_id, _clampi, _clean_css, _esc, _hexonly, _safe_image, _safe_url_css


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


_SECTION_RE = re.compile(r"<section\b([^>]*)>")


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


def _apply_design(
    html_str: str, design: Any, *, block_index: Any = None, editable: bool = False, anchors: bool = False,
) -> str:
    """Post-process a block's HTML: merge designer classes/attrs/style into its
    first <section> tag and inject background media layers. When `editable`, also
    tag the section with `data-cz-block` for the canvas selection runtime — and
    same tag, independently, when `anchors` (the Merlin agent loop's screenshot
    target: it needs `data-cz-block` to scroll a section into view, but must NOT
    get the rest of the editable-mode output — the canvas editor runtime and
    `data-cz-field` tags — which `editable` alone would carry along). No-op on
    published output (no design + not editable + not anchors)."""
    has_design = isinstance(design, dict) and bool(design)
    tag_block = (editable or anchors) and block_index is not None
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


_ASSETS = Path(__file__).parent / "assets"
_BASE_CSS = (_ASSETS / "base.css").read_text(encoding="utf-8")
