"""Token-driven Cappe public-site renderer (Tailwind, server-rendered).

Turns a published site's design tokens (`theme_config`) + a page's content
blocks into a standalone, polished HTML document. Styling is Tailwind via the
Play CDN (`cdn.tailwindcss.com`) — zero build; the per-site palette + font
pairing are injected into `tailwind.config` so the same markup yields visibly
distinct designs per template. (Play CDN is fine for MVP; swap to a compiled
build before real launch.)

Design is expressed entirely through tokens, so one renderer serves every
template and still looks bespoke:

  theme_config = {
    "colors": {bg, surface, text, muted, border, brand, brandText, accent},
    "fonts":  {"heading": "Playfair Display", "body": "Lora"},
    "radius": "none|sm|md|lg|xl|2xl|full",
    "heroStyle": "centered|split|image|minimal",
    "navStyle":  "simple|centered",
    "mode": "light|dark",
  }

Back-compat: the old `{primaryColor, font, mode}` shape still resolves.

Block types: hero, features, gallery, pricing, testimonial, cta, menu, posts,
text, contact. Unknown blocks degrade to a text section. All user content is
HTML-escaped.
"""
import html
from typing import Any
from urllib.parse import quote

# ── tokens ────────────────────────────────────────────────────────────────

_SERIF = {
    "playfair display", "lora", "fraunces", "source serif pro", "source serif 4",
    "merriweather", "georgia", "pt serif", "cormorant garamond", "libre baskerville",
}

_RADIUS = {
    "none": "0px", "sm": "0.375rem", "md": "0.5rem", "lg": "0.75rem",
    "xl": "1rem", "2xl": "1.5rem", "full": "9999px",
}

_LIGHT = {
    "bg": "#ffffff", "surface": "#f8fafc", "text": "#18181b", "muted": "#64748b",
    "border": "#e5e7eb", "brand": "#10b981", "brandText": "#ffffff", "accent": "#10b981",
}
_DARK = {
    "bg": "#0a0a0a", "surface": "#161616", "text": "#fafafa", "muted": "#a1a1aa",
    "border": "#272727", "brand": "#a3e635", "brandText": "#0a0a0a", "accent": "#a3e635",
}


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _font_stack(name: str) -> str:
    generic = "serif" if (name or "").strip().lower() in _SERIF else "sans-serif"
    return f"'{name}', {'ui-serif, Georgia,' if generic == 'serif' else 'ui-sans-serif, system-ui,'} {generic}"


def _tokens(theme: dict | None) -> dict:
    theme = theme or {}
    mode = (theme.get("mode") or "light").lower()
    base = dict(_DARK if mode == "dark" else _LIGHT)

    # Back-compat: old single-color shape.
    if theme.get("primaryColor"):
        base["brand"] = theme["primaryColor"]
        base["accent"] = theme["primaryColor"]

    colors = theme.get("colors") or {}
    base.update({k: v for k, v in colors.items() if v})

    fonts = theme.get("fonts") or {}
    legacy_font = theme.get("font")
    heading = fonts.get("heading") or legacy_font or "Inter"
    body = fonts.get("body") or legacy_font or "Inter"

    radius = _RADIUS.get((theme.get("radius") or "lg").lower(), _RADIUS["lg"])

    return {
        "colors": base,
        "heading": heading,
        "body": body,
        "radius": radius,
        "heroStyle": (theme.get("heroStyle") or "centered").lower(),
        "navStyle": (theme.get("navStyle") or "simple").lower(),
        "dark": mode == "dark",
    }


def _gfonts_link(heading: str, body: str) -> str:
    fams = []
    for f in (heading, body):
        if f and f not in fams and f.lower() not in ("inter",):
            fams.append(f)
    # Inter is so common we still want it crisp; always include it.
    if "Inter" not in fams and heading != "Inter" and body != "Inter":
        pass
    families = list(dict.fromkeys([heading, body, "Inter"]))
    parts = [f"family={quote(f)}:wght@400;500;600;700;800" for f in families if f]
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{"&".join(parts)}&display=swap">'
    )


# ── blocks ────────────────────────────────────────────────────────────────

def _btn(label: str, href: str, t: dict, *, solid: bool = True) -> str:
    if not label:
        return ""
    if solid:
        cls = "bg-brand text-brand-fg hover:opacity-90"
    else:
        cls = "border border-line text-ink hover:bg-surface"
    return (
        f'<a href="{_esc(href or "#")}" class="inline-flex items-center justify-center '
        f'rounded-theme px-6 py-3 text-sm font-semibold transition {cls}">{_esc(label)}</a>'
    )


def _hero(b: dict, t: dict) -> str:
    eyebrow = b.get("eyebrow")
    heading = b.get("heading")
    sub = b.get("subheading")
    cta = b.get("cta")
    cta2 = b.get("cta2")
    image = b.get("image")
    style = (b.get("style") or t["heroStyle"]).lower()

    eyebrow_html = (
        f'<p class="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-brand">{_esc(eyebrow)}</p>'
        if eyebrow else ""
    )
    buttons = (
        f'<div class="mt-8 flex flex-wrap items-center gap-3 {"justify-center" if style in ("centered","image") else ""}">'
        f'{_btn(cta, b.get("ctaHref"), t)}{_btn(cta2, b.get("cta2Href"), t, solid=False)}</div>'
        if (cta or cta2) else ""
    )

    if style == "image":
        bg = (
            f"background-image:linear-gradient(rgba(0,0,0,.55),rgba(0,0,0,.55)),url('{_esc(image)}');"
            if image else "background:linear-gradient(135deg,var(--brand),color-mix(in srgb,var(--brand) 55%, #000));"
        )
        return f"""
        <section class="relative isolate flex min-h-[70vh] items-center justify-center bg-cover bg-center px-6 text-center text-white" style="{bg}">
          <div class="max-w-3xl">
            {eyebrow_html.replace('text-brand','text-white/80')}
            <h1 class="font-heading text-4xl font-bold leading-tight sm:text-6xl">{_esc(heading)}</h1>
            <p class="mx-auto mt-5 max-w-xl text-lg text-white/85">{_esc(sub)}</p>
            {buttons}
          </div>
        </section>"""

    if style == "split":
        side = (
            f'<img src="{_esc(image)}" alt="" class="h-full w-full rounded-theme object-cover" />'
            if image else
            '<div class="h-full w-full rounded-theme bg-gradient-to-br from-brand to-accent opacity-90"></div>'
        )
        return f"""
        <section class="mx-auto grid max-w-6xl items-center gap-10 px-6 py-20 md:grid-cols-2 md:py-28">
          <div>
            {eyebrow_html}
            <h1 class="font-heading text-4xl font-bold leading-tight text-ink sm:text-5xl">{_esc(heading)}</h1>
            <p class="mt-5 max-w-md text-lg text-muted">{_esc(sub)}</p>
            {buttons}
          </div>
          <div class="aspect-[4/3] md:aspect-auto md:h-80">{side}</div>
        </section>"""

    if style == "minimal":
        return f"""
        <section class="mx-auto max-w-3xl px-6 py-24 md:py-32">
          {eyebrow_html}
          <h1 class="font-heading text-4xl font-bold leading-tight text-ink sm:text-6xl">{_esc(heading)}</h1>
          <p class="mt-5 max-w-xl text-lg text-muted">{_esc(sub)}</p>
          {buttons}
        </section>"""

    # centered (default)
    return f"""
    <section class="bg-gradient-to-b from-surface to-canvas px-6 py-24 text-center md:py-32">
      <div class="mx-auto max-w-3xl">
        {eyebrow_html}
        <h1 class="font-heading text-4xl font-bold leading-tight text-ink sm:text-6xl">{_esc(heading)}</h1>
        <p class="mx-auto mt-5 max-w-xl text-lg text-muted">{_esc(sub)}</p>
        {buttons}
      </div>
    </section>"""


def _section_head(b: dict) -> str:
    heading = b.get("heading")
    sub = b.get("subheading")
    if not heading and not sub:
        return ""
    h = f'<h2 class="font-heading text-3xl font-bold text-ink sm:text-4xl">{_esc(heading)}</h2>' if heading else ""
    s = f'<p class="mx-auto mt-3 max-w-2xl text-muted">{_esc(sub)}</p>' if sub else ""
    return f'<div class="mb-12 text-center">{h}{s}</div>'


def _features(b: dict, t: dict) -> str:
    items = [i for i in (b.get("items") or []) if isinstance(i, dict)]
    cards = "".join(
        f"""
        <div class="rounded-theme border border-line bg-surface p-7">
          <div class="mb-4 flex h-11 w-11 items-center justify-center rounded-theme bg-brand/10 text-lg font-bold text-brand">{_esc(i.get("icon") or (i.get("title") or "•")[:1])}</div>
          <h3 class="font-heading text-lg font-semibold text-ink">{_esc(i.get("title"))}</h3>
          <p class="mt-2 text-sm leading-relaxed text-muted">{_esc(i.get("body"))}</p>
        </div>"""
        for i in items
    )
    return f"""
    <section class="mx-auto max-w-6xl px-6 py-20">
      {_section_head(b)}
      <div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{cards}</div>
    </section>"""


def _gallery(b: dict, t: dict) -> str:
    imgs = [i for i in (b.get("images") or []) if isinstance(i, dict) and i.get("url")]
    tiles = "".join(
        f"""
        <figure class="group relative overflow-hidden rounded-theme">
          <img src="{_esc(i.get("url"))}" alt="{_esc(i.get("caption"))}" class="aspect-square w-full object-cover transition duration-500 group-hover:scale-105" />
          {f'<figcaption class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent p-3 text-sm text-white">{_esc(i.get("caption"))}</figcaption>' if i.get("caption") else ""}
        </figure>"""
        for i in imgs
    )
    return f"""
    <section class="mx-auto max-w-6xl px-6 py-20">
      {_section_head(b)}
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:gap-4">{tiles}</div>
    </section>"""


def _pricing(b: dict, t: dict) -> str:
    plans = [p for p in (b.get("plans") or []) if isinstance(p, dict)]
    cards = ""
    for p in plans:
        hot = bool(p.get("highlighted"))
        feats = "".join(
            f'<li class="flex items-start gap-2 text-sm text-muted"><span class="mt-0.5 text-brand">✓</span><span>{_esc(f)}</span></li>'
            for f in (p.get("features") or [])
        )
        ring = "ring-2 ring-brand shadow-xl" if hot else "border border-line"
        badge = '<span class="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand px-3 py-1 text-xs font-semibold text-brand-fg">Popular</span>' if hot else ""
        cards += f"""
        <div class="relative flex flex-col rounded-theme bg-surface p-8 {ring}">
          {badge}
          <h3 class="font-heading text-lg font-semibold text-ink">{_esc(p.get("name"))}</h3>
          <div class="mt-3 flex items-baseline gap-1">
            <span class="text-4xl font-bold text-ink">{_esc(p.get("price"))}</span>
            <span class="text-sm text-muted">{_esc(p.get("period") or "")}</span>
          </div>
          <ul class="mt-6 flex-1 space-y-3">{feats}</ul>
          <div class="mt-8">{_btn(p.get("cta") or "Choose", p.get("ctaHref"), t, solid=hot)}</div>
        </div>"""
    return f"""
    <section class="mx-auto max-w-5xl px-6 py-20">
      {_section_head(b)}
      <div class="grid gap-6 md:grid-cols-3">{cards}</div>
    </section>"""


def _testimonial(b: dict, t: dict) -> str:
    items = b.get("items")
    if not items and b.get("quote"):
        items = [{"quote": b.get("quote"), "author": b.get("author"), "role": b.get("role")}]
    items = [i for i in (items or []) if isinstance(i, dict)]
    cards = "".join(
        f"""
        <figure class="rounded-theme border border-line bg-surface p-8">
          <blockquote class="font-heading text-lg leading-relaxed text-ink">“{_esc(i.get("quote"))}”</blockquote>
          <figcaption class="mt-5 text-sm"><span class="font-semibold text-ink">{_esc(i.get("author"))}</span>{f'<span class="text-muted"> · {_esc(i.get("role"))}</span>' if i.get("role") else ""}</figcaption>
        </figure>"""
        for i in items
    )
    return f"""
    <section class="mx-auto max-w-5xl px-6 py-20">
      {_section_head(b)}
      <div class="grid gap-6 md:grid-cols-2">{cards}</div>
    </section>"""


def _cta(b: dict, t: dict) -> str:
    return f"""
    <section class="bg-brand px-6 py-20 text-center text-brand-fg">
      <div class="mx-auto max-w-2xl">
        <h2 class="font-heading text-3xl font-bold sm:text-4xl">{_esc(b.get("heading"))}</h2>
        {f'<p class="mx-auto mt-3 max-w-xl opacity-90">{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""}
        <div class="mt-8 flex justify-center">
          <a href="{_esc(b.get("ctaHref") or "#")}" class="inline-flex items-center rounded-theme bg-white/15 px-6 py-3 text-sm font-semibold backdrop-blur transition hover:bg-white/25">{_esc(b.get("cta") or "Get started")}</a>
        </div>
      </div>
    </section>"""


def _menu(b: dict, t: dict) -> str:
    sections = [s for s in (b.get("sections") or []) if isinstance(s, dict)]
    cols = ""
    for s in sections:
        rows = ""
        for it in (s.get("items") or []):
            if not isinstance(it, dict):
                continue
            rows += f"""
            <li class="flex items-baseline gap-3 py-2">
              <span class="font-medium text-ink">{_esc(it.get("name"))}</span>
              <span class="h-px flex-1 translate-y-1 border-b border-dotted border-line"></span>
              <span class="font-semibold text-brand">{_esc(it.get("price"))}</span>
            </li>
            {f'<li class="-mt-1 pb-2 text-sm text-muted">{_esc(it.get("description"))}</li>' if it.get("description") else ""}"""
        cols += f"""
        <div>
          <h3 class="mb-2 font-heading text-xl font-semibold text-ink">{_esc(s.get("name"))}</h3>
          <ul class="divide-y divide-line/60">{rows}</ul>
        </div>"""
    return f"""
    <section class="mx-auto max-w-4xl px-6 py-20">
      {_section_head(b)}
      <div class="grid gap-12 md:grid-cols-2">{cols}</div>
    </section>"""


def _posts(b: dict, t: dict) -> str:
    items = [i for i in (b.get("items") or []) if isinstance(i, dict)]
    rows = "".join(
        f"""
        <article class="group border-b border-line py-8">
          {f'<p class="mb-2 text-xs font-medium uppercase tracking-wider text-muted">{_esc(i.get("date"))}</p>' if i.get("date") else ""}
          <h3 class="font-heading text-2xl font-semibold text-ink transition group-hover:text-brand"><a href="{_esc("/p/" + i.get("slug")) if i.get("slug") else "#"}">{_esc(i.get("title"))}</a></h3>
          <p class="mt-2 max-w-2xl leading-relaxed text-muted">{_esc(i.get("excerpt"))}</p>
        </article>"""
        for i in items
    )
    return f"""
    <section class="mx-auto max-w-3xl px-6 py-16">
      {_section_head(b)}
      <div>{rows}</div>
    </section>"""


def _text(b: dict, t: dict) -> str:
    body = b.get("body")
    paras = body if isinstance(body, list) else [body]
    inner = "".join(f"<p>{_esc(p)}</p>" for p in paras if p)
    head = f'<h2 class="mb-4 font-heading text-3xl font-bold text-ink">{_esc(b.get("heading"))}</h2>' if b.get("heading") else ""
    return f"""
    <section class="mx-auto max-w-3xl px-6 py-16">
      {head}
      <div class="space-y-4 text-lg leading-relaxed text-muted">{inner}</div>
    </section>"""


def _contact(b: dict, t: dict) -> str:
    fields = b.get("fields") or ["name", "email", "message"]
    inputs = "".join(
        (f'<textarea rows="4" placeholder="{_esc(f.capitalize())}" class="rounded-theme border border-line bg-canvas px-4 py-3 text-ink outline-none focus:border-brand"></textarea>'
         if f == "message" else
         f'<input placeholder="{_esc(f.capitalize())}" class="rounded-theme border border-line bg-canvas px-4 py-3 text-ink outline-none focus:border-brand" />')
        for f in fields
    )
    return f"""
    <section class="mx-auto max-w-xl px-6 py-20">
      <div class="mb-8 text-center">
        <h2 class="font-heading text-3xl font-bold text-ink">{_esc(b.get("heading") or "Get in touch")}</h2>
        {f'<p class="mt-2 text-muted">{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""}
      </div>
      <form onsubmit="return false" class="flex flex-col gap-3">
        {inputs}
        <button class="rounded-theme bg-brand py-3 font-semibold text-brand-fg transition hover:opacity-90">Send</button>
      </form>
    </section>"""


_RENDERERS = {
    "hero": _hero, "features": _features, "gallery": _gallery, "pricing": _pricing,
    "testimonial": _testimonial, "cta": _cta, "menu": _menu, "posts": _posts,
    "text": _text, "contact": _contact,
}


def _render_block(block: dict, t: dict) -> str:
    if not isinstance(block, dict):
        return ""
    fn = _RENDERERS.get(block.get("type"))
    if fn:
        return fn(block, t)
    body = block.get("body") or block.get("heading")
    return _text({"body": body}, t) if body else ""


# ── document ──────────────────────────────────────────────────────────────

def render_site_html(site: dict, page: dict, nav_pages: list[dict]) -> str:
    """Full HTML document for one page of a site."""
    t = _tokens(site.get("theme_config"))
    c = t["colors"]
    home_slug = nav_pages[0]["slug"] if nav_pages else "home"

    meta = site.get("meta_config") or {}
    logo_url = meta.get("logo_url") if isinstance(meta, dict) else None
    brand = (
        f'<img src="{_esc(logo_url)}" alt="{_esc(site.get("name"))}" class="h-8 w-auto" />'
        if logo_url
        else f'<span class="font-heading text-lg font-bold text-ink">{_esc(site.get("name"))}</span>'
    )

    content = page.get("content") or {}
    blocks = content.get("blocks") if isinstance(content, dict) else None
    blocks = blocks if isinstance(blocks, list) else []
    body_html = "".join(_render_block(b, t) for b in blocks)
    if not body_html:
        body_html = _text({"body": page.get("title")}, t)

    nav_links = "".join(
        f'<a href="{"/" if p["slug"] in ("home", home_slug) else "/p/" + _esc(p["slug"])}" '
        f'class="text-sm font-medium text-muted transition hover:text-brand">{_esc(p["title"])}</a>'
        for p in nav_pages
    )
    nav_center = "justify-center" if t["navStyle"] == "centered" else "justify-between"

    config = (
        "tailwind.config={theme:{extend:{"
        f"colors:{{canvas:'{c['bg']}',surface:'{c['surface']}',ink:'{c['text']}',"
        f"muted:'{c['muted']}',line:'{c['border']}',brand:'{c['brand']}',"
        f"'brand-fg':'{c['brandText']}',accent:'{c['accent']}'}},"
        f"fontFamily:{{heading:[{_font_stack(t['heading'])!r}],body:[{_font_stack(t['body'])!r}]}},"
        "borderRadius:{theme:'%s'}}}}" % t["radius"]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(site.get('name'))} — {_esc(page.get('title'))}</title>
  {_gfonts_link(t['heading'], t['body'])}
  <script src="https://cdn.tailwindcss.com"></script>
  <script>{config}</script>
  <style>
    :root {{ --brand: {c['brand']}; }}
    body {{ font-family: {_font_stack(t['body'])}; }}
    .font-heading {{ font-family: {_font_stack(t['heading'])}; }}
  </style>
</head>
<body class="bg-canvas text-ink antialiased">
  <header class="sticky top-0 z-20 border-b border-line bg-canvas/80 backdrop-blur">
    <div class="mx-auto flex max-w-6xl items-center {nav_center} gap-6 px-6 py-4">
      <a href="/" class="flex items-center">{brand}</a>
      <nav class="hidden items-center gap-6 sm:flex">{nav_links}</nav>
    </div>
  </header>
  <main>{body_html}</main>
  <footer class="border-t border-line py-10 text-center text-sm text-muted">
    <p>© {_esc(site.get('name'))}</p>
    <p class="mt-1 text-xs opacity-70">Built with Cappe</p>
  </footer>
</body>
</html>"""
