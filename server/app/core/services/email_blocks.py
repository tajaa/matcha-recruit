"""Email-safe newsletter block renderer.

Turns a structured ``design_json`` (an ordered list of content blocks) into
bulletproof, "website-in-the-inbox" HTML: everything is table-based with
``role="presentation"``, styles are inlined, buttons are bulletproof (VML for
Outlook), and multi-column rows use the fluid-hybrid ("spongy") technique so
they render side-by-side in Outlook *and* stack on mobile with no reliance on
media queries.

This is the counterpart to the freeform ``content_html`` path — a block design
renders down to the same content slot that ``newsletter_service._render_email``
wraps in branded chrome, so the send / preview / tracking pipeline is unchanged.

Design contract (the block ``type`` + field names below MUST stay in sync with
the client-side schema in ``client/src/pages/admin/Newsletter/blocks/schema.ts``):

    hero      { image, eyebrow?, heading?, subheading?, ctaLabel?, ctaHref?,
                layout?('overlay'|'stacked'), overlay?('light'|'medium'|'dark'),
                align?('center'|'left') }
    heading   { heading, subheading?, align?('left'|'center') }
    text      { html?, body?, align? }
    button    { label, href, align?, variant?('solid'|'outline'), fullWidth? }
    image     { url, href?, alt?, caption?, width?('full'|'inset'), radius? }
    imageText { image, heading?, body?, ctaLabel?, ctaHref?, imageSide?('left'|'right') }
    columns   { columns: [ { image?, heading?, body?, ctaLabel?, ctaHref? } ] }
    features  { heading?, subheading?, items: [ { icon?, title?, body? } ] }
    articles  { heading?, items: [ { image?, title?, excerpt?, href?, label? } ] }
    quote     { quote, author?, role? }
    stats     { heading?, items: [ { value, label } ] }
    divider   { }
    spacer    { size?('sm'|'md'|'lg') }
    video     { url, poster?, caption? }
    footer    { brandName?, tagline?, socials?: [ { label, href } ], showAddress? }

All user content is HTML-escaped; all URLs are scheme-checked.
"""

from __future__ import annotations

import html as _html
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Palettes
#
# Email clients strip <head>/<style> layout rules and give no reliable CSS
# variable support, so every colour is resolved to a concrete value here and
# inlined at render time. Keys prefixed like the legacy EMAIL_THEMES are kept
# so the freeform content_html path (and the video-poster fallback) can share
# one palette dict.
# ---------------------------------------------------------------------------

PALETTES: dict[str, dict[str, str]] = {
    "light": {
        # legacy keys (kept for back-compat with _render_email / poster fallback)
        "wrapper_bg": "#ffffff",
        "wrapper_fg": "#3f3f46",
        "heading_fg": "#18181b",
        "accent": "#059669",
        "link": "#047857",
        "muted": "#71717a",
        "rule": "#e4e4e7",
        # rich block-renderer keys
        "page_bg": "#f4f4f5",
        "card_bg": "#ffffff",
        "text": "#3f3f46",
        "heading": "#18181b",
        "border": "#e4e4e7",
        "subtle_bg": "#f7f7f8",
        "brand": "#059669",
        "brand_text": "#ffffff",
        "eyebrow": "#059669",
        "shadow": "#00000014",
    },
    "dark": {
        "wrapper_bg": "#161616",
        "wrapper_fg": "#d4d4d8",
        "heading_fg": "#fafafa",
        "accent": "#34d399",
        "link": "#6ee7b7",
        "muted": "#a1a1aa",
        "rule": "#2a2a2a",
        "page_bg": "#0a0a0a",
        "card_bg": "#161616",
        "text": "#d4d4d8",
        "heading": "#fafafa",
        "border": "#2a2a2a",
        "subtle_bg": "#202022",
        "brand": "#10b981",
        "brand_text": "#04140d",
        "eyebrow": "#34d399",
        "shadow": "#00000040",
    },
}

FONT_STACK = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

# Content column width (the classic email-safe 600px card, minus the chrome's
# 32px side padding on each edge). Column math keys off this, so it must match
# the padding used by newsletter_service._render_email's content <td>.
CARD_WIDTH = 600
CONTENT_WIDTH = 536  # CARD_WIDTH - 2*32 gutter


def resolve_palette(theme: str, overrides: Optional[dict[str, Any]] = None) -> dict[str, str]:
    """Return a concrete palette for ``theme`` with optional design overrides.

    ``overrides`` (from ``design_json.theme``) may set ``brandColor`` and
    ``bg``; unknown keys are ignored. A bad hex value is dropped rather than
    injected, since these land unescaped inside ``style="..."`` attributes.
    """
    palette = dict(PALETTES.get(theme, PALETTES["light"]))
    overrides = overrides or {}
    brand = _safe_color(overrides.get("brandColor"))
    if brand:
        palette["brand"] = brand
        palette["accent"] = brand
        palette["eyebrow"] = brand
        palette["link"] = brand
    bg = _safe_color(overrides.get("bg"))
    if bg:
        palette["page_bg"] = bg
    return palette


# ---------------------------------------------------------------------------
# Escaping / safety helpers (mirror cappe/services/render.py conventions)
# ---------------------------------------------------------------------------


def _esc(v: Any) -> str:
    return _html.escape(str(v if v is not None else ""))


def _safe_href(href: Any) -> str:
    if not href:
        return "#"
    s = str(href).strip()
    if s.startswith(("/", "#")):
        return s
    if s.lower().startswith(("http://", "https://", "mailto:", "tel:")):
        return s
    return "#"


def _safe_image(url: Any) -> Optional[str]:
    """Return a URL only if it is a clean http(s)/relative image ref.

    Rejects anything with quotes/parens/brackets so it can be dropped straight
    into an ``src="..."`` attribute without breaking out of it.
    """
    if not url:
        return None
    s = str(url).strip()
    if any(c in s for c in ("'", '"', ")", "(", ";", "<", ">", "\\", "\n", "\r")):
        return None
    return s if s.lower().startswith(("http://", "https://", "/")) else None


_HEX = set("0123456789abcdefABCDEF")


def _safe_color(v: Any) -> Optional[str]:
    """Accept only ``#rgb`` / ``#rrggbb`` hex colours — these are inlined raw."""
    if not v:
        return None
    s = str(v).strip()
    if s.startswith("#") and len(s) in (4, 7) and all(c in _HEX for c in s[1:]):
        return s
    return None


def _str(block: dict, key: str, default: str = "") -> str:
    v = block.get(key)
    return str(v).strip() if v is not None else default


def _paragraphs(text: str, palette: dict, *, align: str = "left", size: int = 16) -> str:
    """Render a plain-text body into escaped <p> paragraphs (blank line splits,
    single newline → <br>)."""
    out = []
    for para in (text or "").split("\n\n"):
        para = para.strip()
        if not para:
            continue
        inner = "<br/>".join(_esc(line) for line in para.split("\n"))
        out.append(
            f'<p style="margin:0 0 14px 0;font-size:{size}px;line-height:1.65;'
            f'color:{palette["text"]};text-align:{align};">{inner}</p>'
        )
    return "".join(out)


# ---------------------------------------------------------------------------
# Reusable primitives
# ---------------------------------------------------------------------------


def _button(
    label: str,
    href: str,
    palette: dict,
    *,
    align: str = "center",
    variant: str = "solid",
    full_width: bool = False,
) -> str:
    """Bulletproof CTA button — a bgcolor <td> with a padded <a>, plus a VML
    roundrect so Outlook (which ignores padding/border-radius) still shows a
    real filled button."""
    if not label:
        return ""
    href = _safe_href(href)
    label_e = _esc(label)
    solid = variant != "outline"
    bg = palette["brand"] if solid else palette["card_bg"]
    fg = palette["brand_text"] if solid else palette["brand"]
    border = palette["brand"]
    width_attr = ' width="100%"' if full_width else ""
    align_attr = "center" if align == "center" else ("right" if align == "right" else "left")

    vml = (
        f'<!--[if mso]>'
        f'<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" '
        f'xmlns:w="urn:schemas-microsoft-com:office:word" '
        f'href="{href}" style="height:44px;v-text-anchor:middle;width:220px;" '
        f'arcsize="14%" strokecolor="{border}" fillcolor="{bg}">'
        f'<w:anchorlock/><center style="color:{fg};font-family:{FONT_STACK};'
        f'font-size:15px;font-weight:600;">{label_e}</center>'
        f'</v:roundrect><![endif]-->'
    )
    btn = (
        f'<!--[if !mso]><!-- -->'
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0"{width_attr} '
        f'style="{"width:100%;" if full_width else ""}">'
        f'<tr><td align="center" bgcolor="{bg}" '
        f'style="border-radius:8px;border:1px solid {border};">'
        f'<a href="{href}" target="_blank" '
        f'style="display:inline-block;{"width:100%;" if full_width else ""}'
        f'padding:13px 30px;font-family:{FONT_STACK};font-size:15px;font-weight:600;'
        f'line-height:1.1;color:{fg};text-decoration:none;border-radius:8px;">'
        f'{label_e}</a></td></tr></table>'
        f'<!--<![endif]-->'
    )
    return (
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">'
        f'<tr><td align="{align_attr}" style="padding:6px 0;">{vml}{btn}</td></tr></table>'
    )


def _img(url: str, palette: dict, *, alt: str = "", radius: bool = True, width: int = CONTENT_WIDTH) -> str:
    src = _safe_image(url)
    if not src:
        return ""
    r = "border-radius:10px;" if radius else ""
    return (
        f'<img src="{_esc(src)}" alt="{_esc(alt)}" width="{width}" '
        f'style="display:block;width:100%;max-width:{width}px;height:auto;'
        f'border:0;outline:none;text-decoration:none;{r}" />'
    )


def _responsive_row(cells: list[str], palette: dict, *, valign: str = "top") -> str:
    """Fluid-hybrid ("spongy") multi-column row.

    Each cell is an inline-block div constrained by ``max-width`` so it flows
    side-by-side when there's room and stacks on narrow screens — with no media
    query. An MSO ghost table forces the same side-by-side layout in Outlook,
    which ignores ``display:inline-block``.
    """
    cells = [c for c in cells if c]
    if not cells:
        return ""
    n = len(cells)
    gutter = 12
    # Per-cell max width so n cells + gutters fit the content column.
    cell_w = int((CONTENT_WIDTH - gutter * (n - 1)) / n)

    # An MSO ghost table forces side-by-side in Outlook (which ignores
    # inline-block); the real inline-block divs handle every other client and
    # stack on mobile with no media query.
    parts = [
        '<div style="font-size:0;text-align:center;">',
        f'<!--[if mso]><table role="presentation" border="0" cellpadding="0" cellspacing="0" width="{CONTENT_WIDTH}"><tr><![endif]-->',
    ]
    for cell in cells:
        parts.append(
            f'<!--[if mso]><td width="{cell_w}" valign="{valign}" style="vertical-align:{valign};padding:0 {gutter // 2}px;"><![endif]-->'
            f'<div style="display:inline-block;width:100%;max-width:{cell_w}px;'
            f'vertical-align:{valign};font-size:16px;text-align:left;padding:0 {gutter // 2}px;'
            f'box-sizing:border-box;">{cell}</div>'
            f'<!--[if mso]></td><![endif]-->'
        )
    parts.append('<!--[if mso]></tr></table><![endif]--></div>')
    return "".join(parts)


def _section(inner: str, *, pad_top: int = 10, pad_bottom: int = 10) -> str:
    """Wrap a block's content in a full-width row with vertical padding."""
    if not inner:
        return ""
    return (
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">'
        f'<tr><td style="padding:{pad_top}px 0 {pad_bottom}px 0;">{inner}</td></tr></table>'
    )


# ---------------------------------------------------------------------------
# Per-block renderers — each returns the block's inner HTML (already padded).
# ---------------------------------------------------------------------------


def _render_hero(b: dict, palette: dict, ctx: dict) -> str:
    image = _safe_image(b.get("image"))
    eyebrow = _str(b, "eyebrow")
    heading = _str(b, "heading")
    subheading = _str(b, "subheading")
    cta_label = _str(b, "ctaLabel")
    cta_href = _str(b, "ctaHref")
    layout = _str(b, "layout", "stacked")
    align = _str(b, "align", "center")
    text_align = "center" if align == "center" else "left"

    def _text_stack(on_image: bool) -> str:
        fg_heading = "#ffffff" if on_image else palette["heading"]
        fg_text = "#f4f4f5" if on_image else palette["text"]
        fg_eyebrow = "#ffffff" if on_image else palette["eyebrow"]
        parts = []
        if eyebrow:
            parts.append(
                f'<div style="font-size:12px;font-weight:700;letter-spacing:1.5px;'
                f'text-transform:uppercase;color:{fg_eyebrow};margin:0 0 10px 0;'
                f'text-align:{text_align};opacity:{"0.9" if on_image else "1"};">{_esc(eyebrow)}</div>'
            )
        if heading:
            parts.append(
                f'<h1 style="margin:0 0 12px 0;font-size:30px;line-height:1.2;'
                f'font-weight:800;color:{fg_heading};text-align:{text_align};'
                f'letter-spacing:-0.5px;">{_esc(heading)}</h1>'
            )
        if subheading:
            parts.append(
                f'<p style="margin:0 0 18px 0;font-size:17px;line-height:1.55;'
                f'color:{fg_text};text-align:{text_align};">{_esc(subheading)}</p>'
            )
        if cta_label:
            btn_align = align if align in ("left", "center", "right") else "center"
            # On an image overlay, force a solid brand button for contrast.
            parts.append(_button(cta_label, cta_href, palette, align=btn_align, variant="solid"))
        return "".join(parts)

    if image and layout == "overlay":
        overlay = _str(b, "overlay", "dark")
        scrim = {"light": "rgba(0,0,0,0.25)", "medium": "rgba(0,0,0,0.45)", "dark": "rgba(0,0,0,0.62)"}.get(overlay, "rgba(0,0,0,0.55)")
        # background-image on a td; VML fill for Outlook.
        vml = (
            f'<!--[if gte mso 9]>'
            f'<v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false" '
            f'style="width:{CARD_WIDTH}px;height:340px;">'
            f'<v:fill type="frame" src="{_esc(image)}" color="#111111" />'
            f'<v:textbox inset="0,0,0,0"><![endif]-->'
        )
        vml_end = "<!--[if gte mso 9]></v:textbox></v:rect><![endif]-->"
        return (
            f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
            f'style="border-radius:12px;overflow:hidden;">'
            f'<tr><td background="{_esc(image)}" bgcolor="#111111" valign="middle" '
            f'style="background-image:url(\'{_esc(image)}\');background-size:cover;'
            f'background-position:center;border-radius:12px;">'
            f'{vml}'
            f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">'
            f'<tr><td style="padding:48px 32px;background:{scrim};border-radius:12px;">'
            f'{_text_stack(on_image=True)}'
            f'</td></tr></table>'
            f'{vml_end}'
            f'</td></tr></table>'
        )

    # Stacked: image on top (if any), text below.
    stack = []
    if image:
        stack.append(f'<div style="margin:0 0 20px 0;">{_img(image, palette, alt=heading, radius=True)}</div>')
    stack.append(_text_stack(on_image=False))
    return "".join(stack)


def _render_heading(b: dict, palette: dict, ctx: dict) -> str:
    heading = _str(b, "heading")
    subheading = _str(b, "subheading")
    align = _str(b, "align", "left")
    parts = []
    if heading:
        parts.append(
            f'<h2 style="margin:0 0 6px 0;font-size:23px;line-height:1.3;font-weight:700;'
            f'color:{palette["heading"]};text-align:{align};letter-spacing:-0.3px;">{_esc(heading)}</h2>'
        )
    if subheading:
        parts.append(
            f'<p style="margin:0;font-size:16px;line-height:1.55;color:{palette["muted"]};'
            f'text-align:{align};">{_esc(subheading)}</p>'
        )
    return "".join(parts)


def _render_text(b: dict, palette: dict, ctx: dict) -> str:
    align = _str(b, "align", "left")
    raw_html = b.get("html")
    if raw_html:
        # Already-sanitized rich HTML from the inline editor. Wrap so base
        # typography (colour/size/line-height) is inherited by bare tags.
        sanitize = ctx.get("sanitize")
        safe = sanitize(str(raw_html)) if sanitize else _esc(raw_html)
        return (
            f'<div style="font-size:16px;line-height:1.65;color:{palette["text"]};'
            f'text-align:{align};">{safe}</div>'
        )
    return _paragraphs(_str(b, "body"), palette, align=align)


def _render_button(b: dict, palette: dict, ctx: dict) -> str:
    return _button(
        _str(b, "label"),
        _str(b, "href"),
        palette,
        align=_str(b, "align", "center"),
        variant=_str(b, "variant", "solid"),
        full_width=bool(b.get("fullWidth")),
    )


def _render_image(b: dict, palette: dict, ctx: dict) -> str:
    url = _safe_image(b.get("url"))
    if not url:
        return ""
    width = CONTENT_WIDTH if _str(b, "width", "full") == "full" else 400
    radius = b.get("radius", True) is not False
    img = _img(url, palette, alt=_str(b, "alt"), radius=radius, width=width)
    href = _str(b, "href")
    if href:
        img = f'<a href="{_safe_href(href)}" target="_blank" style="text-decoration:none;">{img}</a>'
    caption = _str(b, "caption")
    inner = f'<div style="text-align:center;">{img}</div>'
    if caption:
        inner += (
            f'<p style="margin:8px 0 0 0;font-size:13px;line-height:1.5;color:{palette["muted"]};'
            f'text-align:center;">{_esc(caption)}</p>'
        )
    return inner


def _render_image_text(b: dict, palette: dict, ctx: dict) -> str:
    image = _safe_image(b.get("image"))
    heading = _str(b, "heading")
    body = _str(b, "body")
    cta_label = _str(b, "ctaLabel")
    cta_href = _str(b, "ctaHref")
    side = _str(b, "imageSide", "left")

    text_col = []
    if heading:
        text_col.append(
            f'<h3 style="margin:0 0 8px 0;font-size:19px;line-height:1.3;font-weight:700;'
            f'color:{palette["heading"]};">{_esc(heading)}</h3>'
        )
    if body:
        text_col.append(_paragraphs(body, palette))
    if cta_label:
        text_col.append(
            f'<a href="{_safe_href(cta_href)}" target="_blank" '
            f'style="font-size:15px;font-weight:600;color:{palette["brand"]};text-decoration:none;">'
            f'{_esc(cta_label)} &rarr;</a>'
        )
    text_html = "".join(text_col)
    img_html = _img(image, palette, alt=heading) if image else ""
    if not img_html:
        return text_html
    cells = [img_html, text_html] if side == "left" else [text_html, img_html]
    return _responsive_row(cells, palette, valign="middle")


def _render_columns(b: dict, palette: dict, ctx: dict) -> str:
    cols = b.get("columns") or []
    cells = []
    for col in cols[:3]:
        if not isinstance(col, dict):
            continue
        parts = []
        image = _safe_image(col.get("image"))
        if image:
            cw = int((CONTENT_WIDTH - 12 * (min(len(cols), 3) - 1)) / max(min(len(cols), 3), 1))
            parts.append(f'<div style="margin:0 0 12px 0;">{_img(image, palette, alt=_str(col, "heading"), width=cw)}</div>')
        h = _str(col, "heading")
        if h:
            parts.append(
                f'<h3 style="margin:0 0 6px 0;font-size:17px;line-height:1.3;font-weight:700;'
                f'color:{palette["heading"]};">{_esc(h)}</h3>'
            )
        body = _str(col, "body")
        if body:
            parts.append(_paragraphs(body, palette, size=15))
        cl = _str(col, "ctaLabel")
        if cl:
            parts.append(
                f'<a href="{_safe_href(_str(col, "ctaHref"))}" target="_blank" '
                f'style="font-size:14px;font-weight:600;color:{palette["brand"]};text-decoration:none;">'
                f'{_esc(cl)} &rarr;</a>'
            )
        cells.append("".join(parts))
    return _responsive_row(cells, palette)


def _render_features(b: dict, palette: dict, ctx: dict) -> str:
    head = _render_heading({"heading": b.get("heading"), "subheading": b.get("subheading"), "align": "center"}, palette, ctx)
    items = b.get("items") or []
    heading_c = palette["heading"]
    text_c = palette["text"]
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        icon = _str(item, "icon")
        title = _str(item, "title")
        body = _str(item, "body")
        parts = ['<div style="margin:0 0 12px 0;">']
        if icon:
            parts.append(f'<div style="font-size:22px;line-height:1;margin:0 0 4px 0;">{_esc(icon)}</div>')
        if title:
            parts.append(f'<div style="font-size:16px;font-weight:700;color:{heading_c};margin:0 0 3px 0;">{_esc(title)}</div>')
        if body:
            parts.append(f'<div style="font-size:14px;line-height:1.55;color:{text_c};">{_esc(body)}</div>')
        parts.append("</div>")
        rows.append("".join(parts))
    # Two-up grid of feature cells (each pair is one spongy row).
    grid = "".join(_responsive_row(rows[i:i + 2], palette) for i in range(0, len(rows), 2))
    top = f'<div style="margin:0 0 16px 0;">{head}</div>' if head else ""
    return top + grid


def _render_articles(b: dict, palette: dict, ctx: dict) -> str:
    head = _render_heading({"heading": b.get("heading"), "subheading": b.get("subheading")}, palette, ctx)
    items = b.get("items") or []
    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        image = _safe_image(item.get("image"))
        title = _str(item, "title")
        excerpt = _str(item, "excerpt")
        href = _str(item, "href")
        label = _str(item, "label") or "Read more"
        img_html = (
            f'<div style="margin:0 0 12px 0;">{_img(image, palette, alt=title)}</div>' if image else ""
        )
        title_html = ""
        if title:
            t = _esc(title)
            if href:
                t = f'<a href="{_safe_href(href)}" target="_blank" style="color:{palette["heading"]};text-decoration:none;">{t}</a>'
            title_html = f'<h3 style="margin:0 0 6px 0;font-size:19px;line-height:1.35;font-weight:700;color:{palette["heading"]};">{t}</h3>'
        excerpt_html = (
            f'<p style="margin:0 0 10px 0;font-size:15px;line-height:1.6;color:{palette["text"]};">{_esc(excerpt)}</p>'
            if excerpt else ""
        )
        link_html = (
            f'<a href="{_safe_href(href)}" target="_blank" style="font-size:14px;font-weight:600;'
            f'color:{palette["brand"]};text-decoration:none;">{_esc(label)} &rarr;</a>'
            if href else ""
        )
        cards.append(
            f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
            f'style="margin:0 0 12px 0;background:{palette["subtle_bg"]};border:1px solid {palette["border"]};'
            f'border-radius:12px;">'
            f'<tr><td style="padding:18px 20px;">{img_html}{title_html}{excerpt_html}{link_html}</td></tr></table>'
        )
    top = f'<div style="margin:0 0 14px 0;">{head}</div>' if head else ""
    return top + "".join(cards)


def _render_quote(b: dict, palette: dict, ctx: dict) -> str:
    quote = _str(b, "quote")
    if not quote:
        return ""
    author = _str(b, "author")
    role = _str(b, "role")
    attribution = ""
    if author or role:
        who = _esc(author)
        if role:
            who += f'<span style="color:{palette["muted"]};font-weight:400;"> — {_esc(role)}</span>' if who else f'<span style="color:{palette["muted"]};">{_esc(role)}</span>'
        attribution = f'<div style="margin:12px 0 0 0;font-size:14px;font-weight:600;color:{palette["heading"]};">{who}</div>'
    return (
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">'
        f'<tr>'
        f'<td width="4" style="background:{palette["brand"]};border-radius:4px;"></td>'
        f'<td style="padding:2px 0 2px 18px;">'
        f'<div style="font-size:19px;line-height:1.5;font-style:italic;color:{palette["heading"]};font-weight:500;">'
        f'&ldquo;{_esc(quote)}&rdquo;</div>{attribution}'
        f'</td></tr></table>'
    )


def _render_stats(b: dict, palette: dict, ctx: dict) -> str:
    head = _render_heading({"heading": b.get("heading"), "align": "center"}, palette, ctx)
    items = b.get("items") or []
    cells = []
    for item in items[:4]:
        if not isinstance(item, dict):
            continue
        value = _str(item, "value")
        label = _str(item, "label")
        cells.append(
            f'<div style="text-align:center;">'
            f'<div style="font-size:30px;line-height:1;font-weight:800;color:{palette["brand"]};margin:0 0 4px 0;">{_esc(value)}</div>'
            f'<div style="font-size:13px;line-height:1.4;color:{palette["muted"]};text-transform:uppercase;letter-spacing:0.5px;">{_esc(label)}</div>'
            f'</div>'
        )
    top = f'<div style="margin:0 0 16px 0;">{head}</div>' if head else ""
    return top + _responsive_row(cells, palette)


def _render_divider(b: dict, palette: dict, ctx: dict) -> str:
    return (
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">'
        f'<tr><td style="padding:6px 0;"><div style="height:1px;line-height:1px;font-size:1px;'
        f'background:{palette["border"]};">&nbsp;</div></td></tr></table>'
    )


_SPACER_H = {"sm": 12, "md": 28, "lg": 48}


def _render_spacer(b: dict, palette: dict, ctx: dict) -> str:
    h = _SPACER_H.get(_str(b, "size", "md"), 28)
    return f'<div style="height:{h}px;line-height:{h}px;font-size:1px;">&nbsp;</div>'


def _render_video(b: dict, palette: dict, ctx: dict) -> str:
    url = _safe_href(b.get("url"))
    poster = _safe_image(b.get("poster"))
    caption = _str(b, "caption")
    if poster:
        card = (
            f'<div style="position:relative;">{_img(poster, palette, alt="Watch video")}</div>'
            f'<div style="text-align:center;margin-top:-38px;position:relative;">'
            f'<span style="display:inline-block;width:52px;height:52px;line-height:52px;border-radius:50%;'
            f'background:{palette["brand"]};color:{palette["brand_text"]};font-size:20px;text-align:center;'
            f'box-shadow:0 4px 14px {palette["shadow"]};">&#9654;</span></div>'
        )
    else:
        card = (
            f'<div style="padding:44px 16px;text-align:center;background:{palette["subtle_bg"]};'
            f'border:1px solid {palette["border"]};border-radius:12px;">'
            f'<div style="font-size:30px;color:{palette["brand"]};line-height:1;">&#9654;</div>'
            f'<div style="margin-top:8px;color:{palette["heading"]};font-size:15px;font-weight:600;">Watch video</div>'
            f'</div>'
        )
    inner = f'<a href="{url}" target="_blank" rel="noopener" style="text-decoration:none;display:block;">{card}</a>'
    if caption:
        inner += (
            f'<p style="margin:10px 0 0 0;font-size:13px;line-height:1.5;color:{palette["muted"]};'
            f'text-align:center;">{_esc(caption)}</p>'
        )
    return inner


def _render_footer(b: dict, palette: dict, ctx: dict) -> str:
    brand_name = _str(b, "brandName")
    tagline = _str(b, "tagline")
    socials = b.get("socials") or []
    parts = ['<div style="text-align:center;">']
    if brand_name:
        parts.append(
            f'<div style="font-size:16px;font-weight:700;color:{palette["heading"]};margin:0 0 4px 0;">{_esc(brand_name)}</div>'
        )
    if tagline:
        parts.append(
            f'<div style="font-size:13px;line-height:1.5;color:{palette["muted"]};margin:0 0 10px 0;">{_esc(tagline)}</div>'
        )
    links = []
    for s in socials:
        if not isinstance(s, dict):
            continue
        label = _str(s, "label")
        href = _str(s, "href")
        if label and href:
            links.append(
                f'<a href="{_safe_href(href)}" target="_blank" '
                f'style="font-size:13px;font-weight:600;color:{palette["brand"]};text-decoration:none;margin:0 8px;">{_esc(label)}</a>'
            )
    if links:
        parts.append(f'<div style="margin:6px 0 0 0;">{"&nbsp;&middot;&nbsp;".join(links)}</div>')
    parts.append("</div>")
    return "".join(parts)


_RENDERERS = {
    "hero": _render_hero,
    "heading": _render_heading,
    "text": _render_text,
    "button": _render_button,
    "image": _render_image,
    "imageText": _render_image_text,
    "columns": _render_columns,
    "features": _render_features,
    "articles": _render_articles,
    "quote": _render_quote,
    "stats": _render_stats,
    "divider": _render_divider,
    "spacer": _render_spacer,
    "video": _render_video,
    "footer": _render_footer,
}

# Spacers/dividers bring their own spacing, so they skip the section wrapper.
_TIGHT_BLOCKS = {"spacer", "divider"}


def block_is_media(block: dict) -> bool:
    """Whether a block contributes a visual (used by the mandatory-media gate)."""
    t = block.get("type")
    if t in ("image", "video", "hero", "imageText"):
        return bool(_safe_image(block.get("image")) or _safe_image(block.get("url")) or _safe_image(block.get("poster")))
    if t == "columns":
        return any(isinstance(c, dict) and _safe_image(c.get("image")) for c in (block.get("columns") or []))
    if t == "articles":
        return any(isinstance(c, dict) and _safe_image(c.get("image")) for c in (block.get("items") or []))
    return False


def design_has_media(design: Optional[dict]) -> bool:
    """True when a design contains at least one real visual — the requirement
    the idea→newsletter export and the builder's send-readiness check enforce."""
    if not design or not isinstance(design, dict):
        return False
    return any(block_is_media(b) for b in (design.get("blocks") or []) if isinstance(b, dict))


def render_blocks(
    design: Optional[dict],
    palette: dict,
    *,
    base_url: str = "",
    sanitize=None,
) -> str:
    """Render a design's ``blocks`` into the email content HTML slot.

    ``sanitize`` is the ``newsletter_service.sanitize_html`` callable, threaded
    in for the rich-text ``text`` block (passing it as an argument avoids a
    circular import).
    """
    if not design or not isinstance(design, dict):
        return ""
    ctx = {"base_url": base_url, "sanitize": sanitize}
    out = []
    for block in design.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        renderer = _RENDERERS.get(block.get("type"))
        if not renderer:
            continue
        try:
            inner = renderer(block, palette, ctx)
        except Exception:
            # A single malformed block must never take down the whole render.
            inner = ""
        if not inner:
            continue
        if block.get("type") in _TIGHT_BLOCKS:
            out.append(inner)
        else:
            out.append(_section(inner))
    return "".join(out)
