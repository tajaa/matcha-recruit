"""Design-token system + the bespoke per-block `_design` designer layer + the
base stylesheet. Consumes `..design_registry` for the color-token/keys-by-group
whitelists that keep `_design` values closed (no raw user string reaches
CSS)."""
import re
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
