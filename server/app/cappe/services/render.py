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
import itertools
import json
from typing import Any
from urllib.parse import quote

# Per-element id source for interactive widgets (unique within a document).
_uid_counter = itertools.count(1)


def _uid() -> int:
    return next(_uid_counter)

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


def _safe_href(href: Any) -> str:
    """Scheme-allowlist a user-supplied URL before it goes into an href.

    HTML-escaping alone doesn't stop `javascript:`/`data:` (no escapable chars),
    so reject anything that isn't an absolute http(s)/mailto/tel URL or a
    same-site path/fragment.
    """
    if not href:
        return "#"
    s = str(href).strip()
    if s.startswith(("/", "#")):
        return s
    if s.lower().startswith(("http://", "https://", "mailto:", "tel:")):
        return s
    return "#"


def _js_obj(obj: Any) -> str:
    """JSON for embedding inside an inline <script>. Escapes the sequences that
    could terminate/break out of the script element (`</script>`, `<!--`) and the
    JS line separators that aren't valid in string literals."""
    return (
        json.dumps(obj)
        .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        .replace(chr(0x2028), "\\u2028").replace(chr(0x2029), "\\u2029")
    )


def _clean_css(v: Any) -> str:
    """Strip HTML-breakout chars from a value emitted into a <style> block (so a
    hostile color/font token can't close </style> and inject markup)."""
    return str(v if v is not None else "").replace("<", "").replace(">", "")


def _safe_image(url: Any) -> str | None:
    """Validate a URL for use inside a CSS `url('…')` (style attribute).

    HTML-escaping is the wrong layer for CSS: an escaped quote is decoded before
    the CSS parser runs and can break out of url(). Reject any char that could
    escape the literal or the attribute, and allow only http(s) or site-root.
    """
    if not url:
        return None
    s = str(url).strip()
    if any(c in s for c in ("'", '"', ")", "(", ";", "<", ">", "\\", "\n", "\r")):
        return None
    return s if s.lower().startswith(("http://", "https://", "/")) else None


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
        f'<a href="{_esc(_safe_href(href))}" class="inline-flex items-center justify-center '
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
        safe_img = _safe_image(image)
        bg = (
            f"background-image:linear-gradient(rgba(0,0,0,.55),rgba(0,0,0,.55)),url('{safe_img}');"
            if safe_img else "background:linear-gradient(135deg,var(--brand),color-mix(in srgb,var(--brand) 55%, #000));"
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
          <a href="{_esc(_safe_href(b.get("ctaHref")))}" class="inline-flex items-center rounded-theme bg-white/15 px-6 py-3 text-sm font-semibold backdrop-blur transition hover:bg-white/25">{_esc(b.get("cta") or "Get started")}</a>
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
          <h3 class="font-heading text-2xl font-semibold text-ink transition group-hover:text-brand"><a href="{_esc(_safe_href("/p/" + i.get("slug"))) if i.get("slug") else "#"}">{_esc(i.get("title"))}</a></h3>
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


# ── interactive widgets (vanilla JS hitting same-origin /api/cappe/public) ──
# The rendered page is standalone HTML; these blocks ship a tiny runtime that
# fetches/posts to the site's public API (set on window.__CAPPE__). All dynamic
# values are escaped via RT.esc before insertion. In the editor preview iframe
# (sandbox allow-scripts, no network) the fetches no-op and the shell shows.

_field = "rounded-theme border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-brand"


def _widget_runtime() -> str:
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
        "return {api:C.api,slug:C.slug,esc:esc,url:url,money:money,get:get,post:post};})();</script>"
    )


_STORE_JS = r"""(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
function field(f){var req=f.required?' required':'';var l='<label class="mb-1 block text-xs font-medium text-muted">'+RT.esc(f.label||f.key)+'</label>';
if(f.type==='textarea')return '<div class="mb-2">'+l+'<textarea data-k="'+RT.esc(f.key)+'"'+req+' class="w-full __F__"></textarea></div>';
if(f.type==='select'){var o=(f.options||[]).map(function(x){return '<option>'+RT.esc(x)+'</option>';}).join('');return '<div class="mb-2">'+l+'<select data-k="'+RT.esc(f.key)+'"'+req+' class="w-full __F__">'+o+'</select></div>';}
var ty=(['email','number','tel','date'].indexOf(f.type)>=0)?f.type:'text';return '<div class="mb-2">'+l+'<input type="'+ty+'" data-k="'+RT.esc(f.key)+'"'+req+' class="w-full __F__" /></div>';}
function form(p,host,btn){if(!host.hasAttribute('hidden')){host.setAttribute('hidden','');return;}host.removeAttribute('hidden');
var intake=(p.intake_fields||[]).map(field).join('');
var when=p.fulfillment==='booking'?'<div class="mb-2"><label class="mb-1 block text-xs font-medium text-muted">Preferred time</label><input type="datetime-local" data-when class="w-full __F__" /></div>':'';
host.innerHTML='<input type="email" data-email placeholder="Your email" class="mb-2 w-full __F__" />'+
'<input type="text" data-name placeholder="Your name" class="mb-2 w-full __F__" />'+when+intake+
'<button class="w-full rounded-theme bg-brand px-4 py-2 text-sm font-semibold text-brand-fg">Place order</button><p class="msg mt-2 text-sm"></p>';
var sb=host.querySelector('button'),msg=host.querySelector('.msg');
sb.addEventListener('click',function(){var email=host.querySelector('[data-email]').value.trim();
if(!email){msg.textContent='Email required';msg.className='msg mt-2 text-sm text-red-500';return;}
var ans={};(p.intake_fields||[]).forEach(function(f){var el=host.querySelector('[data-k="'+f.key+'"]');if(el)ans[f.key]=el.value;});
var item={product_id:p.id,quantity:1,intake_answers:ans};
if(p.fulfillment==='booking'){var w=host.querySelector('[data-when]').value;if(!w){msg.textContent='Pick a time';msg.className='msg mt-2 text-sm text-red-500';return;}item.starts_at=w;}
sb.disabled=true;msg.textContent='Placing order...';msg.className='msg mt-2 text-sm text-muted';
RT.post('/orders',{customer_email:email,customer_name:host.querySelector('[data-name]').value.trim(),items:[item]}).then(function(){
host.innerHTML='<p class="text-sm text-ink">Order placed. We will email you'+(p.fulfillment==='digital'?' your download once confirmed':'')+'.</p>';
}).catch(function(e){sb.disabled=false;msg.textContent=e.message;msg.className='msg mt-2 text-sm text-red-500';});});}
RT.get('/products').then(function(items){if(!items.length){box.innerHTML='<p class="text-muted">No products yet.</p>';return;}box.innerHTML='';
items.forEach(function(p){var c=document.createElement('div');c.className='flex flex-col rounded-theme border border-line bg-surface p-5';
var iu=RT.url(p.image_url);var img=iu?'<img src="'+RT.esc(iu)+'" alt="" class="mb-3 aspect-video w-full rounded-theme object-cover" />':'';
var price=p.price_cents?RT.money(p.price_cents,p.currency):'Free';var lbl=p.fulfillment==='booking'?'Book':'Buy';
c.innerHTML=img+'<h3 class="font-heading text-lg font-semibold text-ink">'+RT.esc(p.name)+'</h3>'+
'<p class="mt-1 flex-1 text-sm text-muted">'+RT.esc(p.description||'')+'</p>'+
'<div class="mt-3 flex items-center justify-between"><span class="font-semibold text-ink">'+price+'</span>'+
'<button class="rounded-theme bg-brand px-4 py-2 text-sm font-semibold text-brand-fg">'+lbl+'</button></div>'+
'<div class="host mt-3" hidden></div>';
c.querySelector('button').addEventListener('click',function(){form(p,c.querySelector('.host'),this);});box.appendChild(c);});
}).catch(function(){box.innerHTML='<p class="text-muted">Unable to load products.</p>';});})();""".replace("__F__", _field)


_BOOKING_JS = r"""(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
Promise.all([RT.get('/booking-types'),RT.get('/availability')]).then(function(r){var types=r[0],av=r[1];
if(!types.length){box.innerHTML='<p class="text-muted">No appointments available.</p>';return;}
var tz=av.timezone||'UTC';
box.innerHTML='<select data-bt class="mb-2 w-full __F__">'+types.map(function(t){return '<option value="'+RT.esc(t.id)+'">'+RT.esc(t.name)+' ('+t.duration_minutes+' min)</option>';}).join('')+'</select>'+
'<input type="datetime-local" data-when class="mb-1 w-full __F__" /><p class="mb-2 text-xs text-muted">Times in '+RT.esc(tz)+'</p>'+
'<input type="email" data-email placeholder="Your email" class="mb-2 w-full __F__" /><input type="text" data-name placeholder="Your name" class="mb-2 w-full __F__" />'+
'<button class="w-full rounded-theme bg-brand px-4 py-2 text-sm font-semibold text-brand-fg">Request booking</button><p class="msg mt-2 text-sm"></p>';
var sb=box.querySelector('button'),msg=box.querySelector('.msg');
sb.addEventListener('click',function(){var email=box.querySelector('[data-email]').value.trim(),w=box.querySelector('[data-when]').value;
if(!email||!w){msg.textContent='Email and time required';msg.className='msg mt-2 text-sm text-red-500';return;}
sb.disabled=true;msg.textContent='Requesting...';msg.className='msg mt-2 text-sm text-muted';
RT.post('/bookings',{booking_type_id:box.querySelector('[data-bt]').value,starts_at:w,customer_email:email,customer_name:box.querySelector('[data-name]').value.trim()}).then(function(res){
box.innerHTML='<p class="text-sm text-ink">Requested for '+RT.esc(new Date(res.starts_at).toLocaleString())+'. We will confirm by email.</p>';
}).catch(function(e){sb.disabled=false;msg.textContent=e.message;msg.className='msg mt-2 text-sm text-red-500';});});
}).catch(function(){box.innerHTML='<p class="text-muted">Unable to load.</p>';});})();""".replace("__F__", _field)


_NEWSLETTER_JS = r"""(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
box.innerHTML='<div class="flex gap-2"><input type="email" data-email placeholder="you@example.com" class="flex-1 __F__" /><button class="rounded-theme bg-brand px-5 py-2 text-sm font-semibold text-brand-fg">Subscribe</button></div><p class="msg mt-2 text-sm"></p>';
var sb=box.querySelector('button'),msg=box.querySelector('.msg');
sb.addEventListener('click',function(){var email=box.querySelector('[data-email]').value.trim();
if(!email){msg.textContent='Email required';msg.className='msg mt-2 text-sm text-red-500';return;}
sb.disabled=true;RT.post('/subscribe',{email:email}).then(function(){box.innerHTML='<p class="text-sm text-ink">You are subscribed.</p>';
}).catch(function(e){sb.disabled=false;msg.textContent=e.message;msg.className='msg mt-2 text-sm text-red-500';});});})();""".replace("__F__", _field)


_CONTACT_JS = r"""(function(){
var box=document.getElementById('__ID__'),RT=window.__CAPPE_RT__;if(!box||!RT)return;
var slug=box.getAttribute('data-form')||'';var sb=box.querySelector('button'),msg=box.querySelector('.msg');
sb.addEventListener('click',function(){if(!slug){msg.textContent='Form not configured yet';msg.className='msg text-sm text-red-500';return;}
var data={};box.querySelectorAll('[data-k]').forEach(function(el){data[el.getAttribute('data-k')]=el.value;});
sb.disabled=true;msg.textContent='Sending...';msg.className='msg text-sm text-muted';
RT.post('/forms/'+encodeURIComponent(slug),{data:data,submitter_email:data.email||null}).then(function(){
box.innerHTML='<p class="text-center text-sm text-ink">Thanks - your message was sent.</p>';
}).catch(function(e){sb.disabled=false;msg.textContent=e.message;msg.className='msg text-sm text-red-500';});});})();"""


def _store(b: dict, t: dict) -> str:
    wid = "st" + str(_uid())
    return (
        f'<section class="mx-auto max-w-6xl px-6 py-16">{_section_head(b)}'
        f'<div id="{wid}" class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">'
        f'<p class="text-muted">Loading products...</p></div></section>'
        f'<script>{_STORE_JS.replace("__ID__", wid)}</script>'
    )


def _booking(b: dict, t: dict) -> str:
    wid = "bk" + str(_uid())
    return (
        f'<section class="mx-auto max-w-md px-6 py-16">{_section_head(b)}'
        f'<div id="{wid}"><p class="text-muted">Loading...</p></div></section>'
        f'<script>{_BOOKING_JS.replace("__ID__", wid)}</script>'
    )


def _newsletter(b: dict, t: dict) -> str:
    wid = "nl" + str(_uid())
    return (
        f'<section class="mx-auto max-w-xl px-6 py-16 text-center">{_section_head(b)}'
        f'<div id="{wid}" class="mx-auto max-w-md text-left"></div></section>'
        f'<script>{_NEWSLETTER_JS.replace("__ID__", wid)}</script>'
    )


def _contact(b: dict, t: dict) -> str:
    wid = "cf" + str(_uid())
    fields = b.get("fields") or ["name", "email", "message"]
    form_slug = b.get("formSlug") or b.get("form_slug") or ""
    sub = b.get("subheading")
    sub_html = f'<p class="mt-2 text-muted">{_esc(sub)}</p>' if sub else ""
    inputs = "".join(
        (f'<textarea data-k="{_esc(f)}" rows="4" placeholder="{_esc(f.capitalize())}" class="{_field}"></textarea>'
         if f == "message" else
         f'<input data-k="{_esc(f)}" placeholder="{_esc(f.capitalize())}" class="{_field}" />')
        for f in fields if isinstance(f, str)
    )
    return (
        f'<section class="mx-auto max-w-xl px-6 py-20">'
        f'<div class="mb-8 text-center"><h2 class="font-heading text-3xl font-bold text-ink">'
        f'{_esc(b.get("heading") or "Get in touch")}</h2>{sub_html}</div>'
        f'<div id="{wid}" data-form="{_esc(form_slug)}" class="flex flex-col gap-3">{inputs}'
        f'<button type="button" class="rounded-theme bg-brand py-3 font-semibold text-brand-fg transition hover:opacity-90">Send</button>'
        f'<p class="msg text-sm"></p></div></section>'
        f'<script>{_CONTACT_JS.replace("__ID__", wid)}</script>'
    )


_RENDERERS = {
    "hero": _hero, "features": _features, "gallery": _gallery, "pricing": _pricing,
    "testimonial": _testimonial, "cta": _cta, "menu": _menu, "posts": _posts,
    "text": _text, "contact": _contact, "store": _store, "booking": _booking,
    "newsletter": _newsletter,
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

    slug = site.get("slug") or ""
    cappe_ctx = _js_obj({"slug": slug, "api": f"/api/cappe/public/sites/{slug}"})

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

    # Built as data + JSON-encoded so owner-controlled colors/fonts can't break
    # out of the inline <script> (e.g. a token containing </script>).
    config = "tailwind.config=" + _js_obj({
        "theme": {"extend": {
            "colors": {
                "canvas": c["bg"], "surface": c["surface"], "ink": c["text"],
                "muted": c["muted"], "line": c["border"], "brand": c["brand"],
                "brand-fg": c["brandText"], "accent": c["accent"],
            },
            "fontFamily": {"heading": [_font_stack(t["heading"])], "body": [_font_stack(t["body"])]},
            "borderRadius": {"theme": t["radius"]},
        }},
    })

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(site.get('name'))} — {_esc(page.get('title'))}</title>
  {_gfonts_link(t['heading'], t['body'])}
  <script src="https://cdn.tailwindcss.com"></script>
  <script>{config}</script>
  <script>window.__CAPPE__={cappe_ctx};</script>
  {_widget_runtime()}
  <style>
    :root {{ --brand: {_clean_css(c['brand'])}; }}
    body {{ font-family: {_clean_css(_font_stack(t['body']))}; }}
    .font-heading {{ font-family: {_clean_css(_font_stack(t['heading']))}; }}
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
