"""Block renderers + their interactive-widget JS, the freeform canvas block,
and `_render_block` (the per-block dispatch + `_apply_design` wrapper)."""
import re
from pathlib import Path
from urllib.parse import quote

from .design import _apply_design, _font_stack
from .sanitize import _clampi, _clean_css, _cv_safe_id, _esc, _hexonly, _num, _safe_href, _safe_image, _uid

_ASSETS = Path(__file__).parent / "assets"


# ── blocks ──────────────────────────────────────────────────────────────────

def _btn(label, href, *, solid=True, field=None, editable=False):
    if not label:
        return ""
    cls = "cz-btn--solid" if solid else "cz-btn--ghost"
    attrs = _fattr(field, editable, "button") if field else ""
    return f'<a class="cz-btn {cls}"{attrs} href="{_esc(_safe_href(href))}">{_esc(label)}</a>'


def _fattr(field: str, editable: bool, kind: str = "text") -> str:
    """`data-cz-field` tag for canvas inline-text editing + Merlin's unified
    selection contract — only in editor mode. `kind` ("text"|"image"|"button")
    rides as `data-cz-kind` (omitted for the "text" default) so the editor
    runtime's click handler (canvas.js:postSelection) can report what kind of
    element was highlighted without guessing from tag name."""
    if not editable:
        return ""
    attrs = f' data-cz-field="{field}"'
    if kind != "text":
        attrs += f' data-cz-kind="{kind}"'
    return attrs


def _head(b, editable=False, sub=True):
    # `sub` gates the subheading tag for block types whose BLOCK_FIELDS entry
    # (server/app/cappe/services/merlin/catalog.py) has no "subheading" field —
    # gallery/pricing/testimonial/menu/posts/map. Without it these types still
    # got a `data-cz-field="subheading"` tag whenever legacy content happened
    # to carry that key, advertising a set_field path the op layer rejects.
    h = f'<h2{_fattr("heading", editable)}>{_esc(b.get("heading"))}</h2>' if b.get("heading") else ""
    s = f'<p{_fattr("subheading", editable)}>{_esc(b.get("subheading"))}</p>' if (sub and b.get("subheading")) else ""
    return f'<div class="cz-head">{h}{s}</div>' if (h or s) else ""


def _hero(b, t, editable=False):
    style = (b.get("style") or t["heroStyle"]).lower()
    eyebrow = f'<p class="cz-eyebrow cz-hero__eyebrow"{_fattr("eyebrow", editable)}>{_esc(b.get("eyebrow"))}</p>' if b.get("eyebrow") else ""
    title = f'<h1 class="cz-hero__title"{_fattr("heading", editable)}>{_esc(b.get("heading"))}</h1>'
    lead = f'<p class="cz-hero__lead"{_fattr("subheading", editable)}>{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    cta = (f'<div class="cz-cta-row">{_btn(b.get("cta"), b.get("ctaHref"), field="cta", editable=editable)}'
           f'{_btn(b.get("cta2"), b.get("cta2Href"), solid=False, field="cta2", editable=editable)}</div>') if (b.get("cta") or b.get("cta2")) else ""
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
        art = (f'<img src="{_esc(img)}" alt=""{_fattr("image", editable, "image")} />' if img else "")
        return (f'<section class="cz-hero cz-hero--split"><div class="cz-wrap cz-grid">'
                f'<div>{eyebrow}{title}{lead}{cta}</div><div class="cz-art">{art}</div></div></section>')
    mod = "cz-hero--minimal" if style == "minimal" else "cz-hero--centered"
    return f'<section class="cz-hero {mod}"><div class="cz-wrap">{eyebrow}{title}{lead}{cta}</div></section>'


def _features(b, t, editable=False):
    cards = "".join(
        f'<div class="cz-card"><div class="cz-feat__icon">{_esc(i.get("icon") or (i.get("title") or "•")[:1])}</div>'
        f'<h3{_fattr(f"items.{idx}.title", editable)}>{_esc(i.get("title"))}</h3>'
        f'<p{_fattr(f"items.{idx}.body", editable)}>{_esc(i.get("body"))}</p></div>'
        for idx, i in enumerate(b.get("items") or []) if isinstance(i, dict))
    return f'<section class="cz-features"><div class="cz-wrap">{_head(b, editable)}<div class="cz-cards">{cards}</div></div></section>'


def _gallery(b, t, editable=False):
    tiles = ""
    for idx, i in enumerate(b.get("images") or []):
        if not isinstance(i, dict):
            continue
        u = _safe_image(i.get("url"))
        if not u:
            continue
        cap = f'<figcaption{_fattr(f"images.{idx}.caption", editable)}>{_esc(i.get("caption"))}</figcaption>' if i.get("caption") else ""
        tiles += (f'<figure class="cz-tile"><img src="{_esc(u)}" alt="{_esc(i.get("caption"))}"'
                  f'{_fattr(f"images.{idx}.url", editable, "image")} />{cap}</figure>')
    return f'<section class="cz-gallery"><div class="cz-wrap">{_head(b, editable, sub=False)}<div class="cz-grid-img">{tiles}</div></div></section>'


def _pricing(b, t, editable=False):
    cards = ""
    for idx, p in enumerate(b.get("plans") or []):
        if not isinstance(p, dict):
            continue
        hot = bool(p.get("highlighted"))
        feats = "".join(f'<li>{_esc(f)}</li>' for f in (p.get("features") or []))
        badge = '<span class="cz-plan__badge">Popular</span>' if hot else ""
        # `price` is wrapped in its own <span> (not the whole .cz-plan__price div)
        # so the tagged element's textContent is exactly the price value — the
        # sibling period <span> would otherwise get folded into a highlighted
        # range's reported text and break the server's exact-match anchor check.
        cards += (f'<div class="cz-plan {"cz-plan--hot" if hot else ""}">{badge}'
                  f'<h3{_fattr(f"plans.{idx}.name", editable)}>{_esc(p.get("name"))}</h3>'
                  f'<div class="cz-plan__price"><span{_fattr(f"plans.{idx}.price", editable)}>{_esc(p.get("price"))}</span>'
                  f'<span>{_esc(p.get("period") or "")}</span></div>'
                  f'<ul>{feats}</ul>{_btn(p.get("cta") or "Choose", p.get("ctaHref"), solid=hot, field=f"plans.{idx}.cta", editable=editable)}</div>')
    return f'<section class="cz-pricing"><div class="cz-wrap">{_head(b, editable, sub=False)}<div class="cz-plans">{cards}</div></div></section>'


def _testimonial(b, t, editable=False):
    real_items = b.get("items")
    items = real_items or ([{"quote": b.get("quote"), "author": b.get("author"), "role": b.get("role")}] if b.get("quote") else [])
    # The legacy scalar shape (no `items` array — old single-quote content)
    # has no array for a "items.N.*" set_field path to descend into, so
    # tagging it that way advertised a path deepSet always refuses. Only tag
    # when `items` genuinely exists on the block.
    tag = editable and bool(real_items)
    cards = ""
    for idx, i in enumerate(items):
        if not isinstance(i, dict):
            continue
        # Quote text is wrapped in an inner <span> so the curly quote marks
        # around it stay outside the tagged element's textContent (same
        # exact-match reasoning as the pricing price/period split above).
        role = f' · <span{_fattr(f"items.{idx}.role", tag)}>{_esc(i.get("role"))}</span>' if i.get("role") else ""
        cards += (f'<figure class="cz-quote"><blockquote>“<span{_fattr(f"items.{idx}.quote", tag)}>{_esc(i.get("quote"))}</span>”</blockquote>'
                  f'<figcaption><b{_fattr(f"items.{idx}.author", tag)}>{_esc(i.get("author"))}</b>{role}</figcaption></figure>')
    return f'<section class="cz-quotes"><div class="cz-wrap">{_head(b, editable, sub=False)}<div class="cz-quote-grid">{cards}</div></div></section>'


def _cta(b, t, editable=False):
    sub = f'<p{_fattr("subheading", editable)}>{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    return (f'<section class="cz-band"><div class="cz-wrap"><h2{_fattr("heading", editable)}>{_esc(b.get("heading"))}</h2>{sub}'
            f'<a class="cz-btn"{_fattr("cta", editable, "button")} href="{_esc(_safe_href(b.get("ctaHref")))}">{_esc(b.get("cta") or "Get started")}</a></div></section>')


def _menu(b, t, editable=False):
    cols = ""
    for sidx, s in enumerate(b.get("sections") or []):
        if not isinstance(s, dict):
            continue
        rows = ""
        for iidx, it in enumerate(s.get("items") or []):
            if not isinstance(it, dict):
                continue
            base = f"sections.{sidx}.items.{iidx}"
            rows += (f'<div class="cz-menu-row"><span class="name"{_fattr(f"{base}.name", editable)}>{_esc(it.get("name"))}</span>'
                     f'<span class="dots"></span><span class="price"{_fattr(f"{base}.price", editable)}>{_esc(it.get("price"))}</span></div>')
            if it.get("description"):
                rows += f'<div class="desc"{_fattr(f"{base}.description", editable)}>{_esc(it.get("description"))}</div>'
        cols += f'<div><h3{_fattr(f"sections.{sidx}.name", editable)}>{_esc(s.get("name"))}</h3>{rows}</div>'
    return f'<section class="cz-menu"><div class="cz-wrap">{_head(b, editable, sub=False)}<div class="cz-menu-grid">{cols}</div></div></section>'


def _posts(b, t, editable=False):
    rows = ""
    for idx, i in enumerate(b.get("items") or []):
        if not isinstance(i, dict):
            continue
        date = f'<div class="date"{_fattr(f"items.{idx}.date", editable)}>{_esc(i.get("date"))}</div>' if i.get("date") else ""
        href = _safe_href("/p/" + i.get("slug")) if i.get("slug") else "#"
        rows += (f'<article class="cz-post">{date}<h3><a href="{_esc(href)}"{_fattr(f"items.{idx}.title", editable)}>{_esc(i.get("title"))}</a></h3>'
                 f'<p{_fattr(f"items.{idx}.excerpt", editable)}>{_esc(i.get("excerpt"))}</p></article>')
    return f'<section class="cz-posts"><div class="cz-narrow">{_head(b, editable, sub=False)}{rows}</div></section>'


def _stats(b, t, editable=False):
    cells = "".join(
        f'<div class="cz-stat"><div class="cz-stat__num"{_fattr(f"items.{idx}.value", editable)}>{_esc(i.get("value"))}</div>'
        f'<div class="cz-stat__label"{_fattr(f"items.{idx}.label", editable)}>{_esc(i.get("label"))}</div></div>'
        for idx, i in enumerate(b.get("items") or []) if isinstance(i, dict))
    return f'<section class="cz-stats"><div class="cz-wrap">{_head(b, editable)}<div class="cz-stats-grid">{cells}</div></div></section>'


def _logos(b, t, editable=False):
    title = f'<p class="cz-logos__title"{_fattr("heading", editable)}>{_esc(b.get("heading") or "Trusted by")}</p>'
    items = ""
    for idx, i in enumerate(b.get("items") or []):
        if not isinstance(i, dict):
            continue
        u = _safe_image(i.get("image"))
        if u:
            items += f'<img src="{_esc(u)}" alt="{_esc(i.get("name"))}"{_fattr(f"items.{idx}.image", editable, "image")} />'
        elif i.get("name"):
            items += f'<span class="cz-logos__name"{_fattr(f"items.{idx}.name", editable)}>{_esc(i.get("name"))}</span>'
    return f'<section class="cz-logos"><div class="cz-wrap">{title}<div class="cz-logos__row">{items}</div></div></section>'


def _faq(b, t, editable=False):
    rows = ""
    for idx, i in enumerate(b.get("items") or []):
        if not isinstance(i, dict) or not i.get("q"):
            continue
        rows += (f'<details class="cz-faq__item"><summary{_fattr(f"items.{idx}.q", editable)}>{_esc(i.get("q"))}</summary>'
                 f'<p{_fattr(f"items.{idx}.a", editable)}>{_esc(i.get("a"))}</p></details>')
    return f'<section class="cz-faq"><div class="cz-wrap">{_head(b, editable)}<div class="cz-faq__list">{rows}</div></div></section>'


def _bento(b, t, editable=False):
    cells = ""
    for idx, i in enumerate(b.get("items") or []):
        if not isinstance(i, dict):
            continue
        span = str(i.get("span") or "").lower()
        mod = " cz-bento-cell--wide" if span == "wide" else (" cz-bento-cell--tall" if span == "tall" else "")
        icon = f'<div class="cz-bento-cell__icon">{_esc(i.get("icon"))}</div>' if i.get("icon") else ""
        head = f'<h3{_fattr(f"items.{idx}.title", editable)}>{_esc(i.get("title"))}</h3>' if i.get("title") else ""
        body = f'<p{_fattr(f"items.{idx}.body", editable)}>{_esc(i.get("body"))}</p>' if i.get("body") else ""
        u = _safe_image(i.get("image"))
        if u:
            # Defense-in-depth: _safe_image already rejects quotes/parens, but
            # encode locally too so the CSS url() literal can't be closed even
            # if that guard ever changes (HTML-attr escape + CSS-quote encode).
            safe_u = _esc(u).replace("'", "%27").replace("(", "%28").replace(")", "%29")
            cells += (f'<div class="cz-bento-cell cz-bento-cell--img{mod}"{_fattr(f"items.{idx}.image", editable, "image")} '
                      f'style="background-image:url(\'{safe_u}\')">{icon}{head}{body}</div>')
        else:
            cells += f'<div class="cz-bento-cell{mod}">{icon}{head}{body}</div>'
    return f'<section class="cz-bento"><div class="cz-wrap">{_head(b, editable)}<div class="cz-bento-grid">{cells}</div></div></section>'


def _split(b, t, editable=False):
    img = _safe_image(b.get("image"))
    art = f'<img src="{_esc(img)}" alt=""{_fattr("image", editable, "image")} />' if img else ""
    eyebrow = f'<p class="cz-eyebrow"{_fattr("eyebrow", editable)}>{_esc(b.get("eyebrow"))}</p>' if b.get("eyebrow") else ""
    head = f'<h2{_fattr("heading", editable)}>{_esc(b.get("heading"))}</h2>' if b.get("heading") else ""
    body = f'<p{_fattr("body", editable)}>{_esc(b.get("body"))}</p>' if b.get("body") else ""
    # Tagged by RAW index into `bullets` (not the filtered `bl` position) so the
    # emitted path always matches the array `set_field`/`_resolve_field_text`
    # actually index into.
    bullets_html = "".join(
        f'<li{_fattr(f"bullets.{idx}", editable)}>{_esc(x)}</li>'
        for idx, x in enumerate(b.get("bullets") or []) if x)
    bullets = f'<ul class="cz-split__bullets">{bullets_html}</ul>' if bullets_html else ""
    cta = _btn(b.get("cta"), b.get("ctaHref"), field="cta", editable=editable) if b.get("cta") else ""
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


def _credentials(b, t, editable=False):
    cards = ""
    for idx, i in enumerate(b.get("items") or []):
        if not isinstance(i, dict):
            continue
        meta = " · ".join(x for x in (_esc(i.get("issuer")), _esc(i.get("year"))) if x)
        meta_html = f'<div class="cz-cred__meta">{meta}</div>' if meta else ""
        detail = f'<p class="cz-cred__detail"{_fattr(f"items.{idx}.detail", editable)}>{_esc(i.get("detail"))}</p>' if i.get("detail") else ""
        cards += (f'<div class="cz-cred"><div class="cz-cred__badge">✓</div>'
                  f'<div><h3{_fattr(f"items.{idx}.title", editable)}>{_esc(i.get("title"))}</h3>{meta_html}{detail}</div></div>')
    return f'<section class="cz-creds"><div class="cz-wrap">{_head(b, editable)}<div class="cz-creds-grid">{cards}</div></div></section>'


# ── interactive widgets (same-origin /api/cappe/public, no styling deps) ─────

_RUNTIME_JS = (_ASSETS / "runtime.js").read_text(encoding="utf-8")


def _widget_runtime():
    return "<script>" + _RUNTIME_JS + "</script>"


# Motion runtime. Adds `cz-js` (so hide-state CSS only applies when JS is
# available — no-JS shows everything), reveals each <section> on scroll-in
# (covers both the legacy premium full-section reveal and per-section .cz-rv
# designer motion), wires stagger child indices, and runs rAF parallax. No-op
# without IntersectionObserver; parallax is skipped under reduced-motion / mobile.
_STAGGER_SEL = (".cz-cards>*,.cz-plans>*,.cz-bento>*,.cz-gallery>*,"
                ".cz-creds>*,.cz-quotes>*,.cz-stats>*,.cz-reviews-box>*")
_MOTION_JS_TEMPLATE = (_ASSETS / "motion.js").read_text(encoding="utf-8")
_MOTION_JS = "<script>" + _MOTION_JS_TEMPLATE.replace("__STAGGER_SEL__", _STAGGER_SEL) + "</script>"


# Canvas editor runtime — emitted ONLY when `editable` (editor preview), never on
# published pages. Lets the parent app click-select sections, inline-edit tagged
# text, and drag-reorder, via postMessage. Vanilla, inline, no user strings.
_CANVAS_JS = (
    "<style>" + (_ASSETS / "canvas.css").read_text(encoding="utf-8") + "</style>\n"
    "<script>" + (_ASSETS / "canvas.js").read_text(encoding="utf-8") + "</script>"
)


_STORE_JS = (_ASSETS / "store.js").read_text(encoding="utf-8")


_BOOKING_JS = (_ASSETS / "booking.js").read_text(encoding="utf-8")
_BOOKING_ACCESS_JS = (_ASSETS / "booking_suggestion_access.js").read_text(encoding="utf-8")


_NEWSLETTER_JS = (_ASSETS / "newsletter.js").read_text(encoding="utf-8")


_CONTACT_JS = (_ASSETS / "contact.js").read_text(encoding="utf-8")


_REVIEWS_JS = (_ASSETS / "reviews.js").read_text(encoding="utf-8")


def _reviews(b, t, editable=False):
    wid = "rv" + str(_uid())
    show_form = b.get("allowSubmissions") is not False  # default on
    return (f'<section class="cz-reviews"><div class="cz-wrap">{_head(b, editable)}'
            f'<div id="{wid}" class="cz-reviews-box" data-form="{"1" if show_form else "0"}">'
            f'<p style="color:var(--muted)">Loading reviews…</p></div></div></section>'
            f'<script>{_REVIEWS_JS.replace("__ID__", wid)}</script>')


def _store(b, t, editable=False):
    # `id="shop"` is a stable anchor any CTA/nav can link to (#shop) regardless
    # of the seller's vocation — the generalizable "go buy" destination.
    wid = "st" + str(_uid())
    return (f'<section id="shop" class="cz-store"><div class="cz-wrap">{_head(b, editable)}'
            f'<div id="{wid}" class="cz-store-box"><p style="color:var(--muted)">Loading products...</p></div></div></section>'
            f'<script>{_STORE_JS.replace("__ID__", wid)}</script>')


def _booking(b, t, editable=False):
    wid = "bk" + str(_uid())
    return (f'<section id="book" class="cz-form-sec"><div class="cz-wrap">{_head(b, editable)}'
            f'<div id="{wid}" class="cz-form"><p style="color:var(--muted)">Loading...</p></div></div></section>'
            f'<script>{_BOOKING_JS.replace("__ID__", wid)}</script>'
            f'<script>{_BOOKING_ACCESS_JS.replace("__ID__", wid)}</script>')


def _newsletter(b, t, editable=False):
    wid = "nl" + str(_uid())
    return (f'<section class="cz-form-sec"><div class="cz-narrow" style="text-align:center">{_head(b, editable)}'
            f'<div id="{wid}" class="cz-form"></div></div></section>'
            f'<script>{_NEWSLETTER_JS.replace("__ID__", wid)}</script>')


def _contact(b, t, editable=False):
    wid = "cf" + str(_uid())
    fields = b.get("fields") or ["name", "email", "message"]
    form_slug = b.get("formSlug") or b.get("form_slug") or ""
    sub = f'<p{_fattr("subheading", editable)}>{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    inputs = "".join(
        (f'<textarea class="cz-field" data-k="{_esc(f)}" rows="4" placeholder="{_esc(f.capitalize())}"></textarea>'
         if f == "message" else
         f'<input class="cz-field" data-k="{_esc(f)}" placeholder="{_esc(f.capitalize())}" />')
        for f in fields if isinstance(f, str))
    return (f'<section class="cz-form-sec"><div class="cz-narrow">'
            f'<div class="cz-head"><h2{_fattr("heading", editable)}>{_esc(b.get("heading") or "Get in touch")}</h2>{sub}</div>'
            f'<div id="{wid}" data-form="{_esc(form_slug)}" class="cz-form">{inputs}'
            f'<button class="cz-btn cz-btn--solid cz-btn--block">Send</button><p class="cz-msg"></p></div></div></section>'
            f'<script>{_CONTACT_JS.replace("__ID__", wid)}</script>')


# --- local presence: map + hours --------------------------------------------

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


def _map(b, t, editable=False):
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
        addr_html = f'<p class="cz-map__addr"{_fattr("address", editable)}>{_esc(addr)}</p>' if addr else ""
        apple = (f'<a class="cz-btn cz-btn--ghost" href="https://maps.apple.com/?q={query}" '
                 f'target="_blank" rel="noopener noreferrer">Apple Maps</a>') if addr else ""
        actions = (f'{addr_html}<div class="cz-map__actions">'
                   f'<a class="cz-btn cz-btn--solid" href="{_esc(g)}" target="_blank" rel="noopener noreferrer">Get directions</a>'
                   f'{apple}</div>')
    return f'<section class="cz-map"><div class="cz-wrap">{_head(b, editable, sub=False)}{embed}{actions}</div></section>'


_OPENNOW_JS = "<script>" + (_ASSETS / "opennow.js").read_text(encoding="utf-8") + "</script>"

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _hours(b, t, editable=False):
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
    return (f'<section class="cz-hours"><div class="cz-narrow" style="text-align:center">{_head(b, editable)}'
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
            els_html.append(f'<div class="cz-el cz-el--img"{dataattr}{_fattr(eid, editable, "image")}{style_attr}>{inner}</div>')
        elif kind == "button":
            btncls = "cz-btn--ghost" if style.get("variant") == "outline" else "cz-btn--solid"
            href = _esc(_safe_href(el.get("href")))
            # data-cz-field tags the label for inline editing; the click runtime
            # already preventDefaults <a> navigation in the editor.
            els_html.append(
                f'<a class="cz-el cz-el--btn cz-btn {btncls}"{dataattr}{_fattr(eid, editable, "button")} '
                f'href="{href}"{style_attr}>{_esc(el.get("text"))}</a>'
            )
        else:
            tag = "h2" if kind == "heading" else "p"
            # Image elements ALSO get data-cz-field (above) — kept out of
            # contenteditable purely by canvas.js's dblclick handler checking
            # data-cz-kind==="image" and bailing before it ever sets
            # contenteditable. That client-side check is the only thing
            # stopping a cz-edit for an image field; useCanvasBridge.ts's
            # cz-edit receiver re-checks kind too, so a bypass there doesn't
            # overwrite an image URL with typed text.
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

def _render_block(block, t, index=None, editable=False, anchors=False):
    if not isinstance(block, dict):
        return ""
    btype = block.get("type")
    # Canvas needs the block index (for per-block CSS scoping) + editable, so it's
    # dispatched here rather than through _RENDERERS' (block, t, editable) shape.
    if btype == "canvas":
        raw = _canvas(block, t, editable, index if index is not None else 0)
        return _apply_design(
            raw, block.get("_design"), block_index=index, editable=editable, anchors=anchors,
        ) if raw else raw
    fn = _RENDERERS.get(btype)
    if fn:
        raw = fn(block, t, editable)
    else:
        body = block.get("body") or block.get("heading")
        raw = _text({"body": body}, t) if body else ""
    if not raw:
        return raw
    return _apply_design(raw, block.get("_design"), block_index=index, editable=editable, anchors=anchors)
