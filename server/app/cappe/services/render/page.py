"""Document assembly: page `<head>`/SEO, footer, site-wide promos, and
`render_site_html` — the one function every in-app caller uses."""
import json
import re
from typing import Any

from .blocks import _CANVAS_CSS, _CANVAS_JS, _MOTION_JS, _render_block, _text, _widget_runtime
from .design import _BASE_CSS, _block_has_motion, _design_gradient, _font_stack, _gfonts_link, _style_vars, _tokens
from .sanitize import _clampi, _clean_css, _esc, _hexonly, _js_obj, _num, _safe_href, _safe_image


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
                     locations: list[dict] | None = None, block_anchors: bool = False) -> str:
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
    # `block_anchors` is the Merlin agent loop's screenshot target, NOT the
    # canvas editor (`editable`) — it wants `data-cz-block` so a shot can
    # scroll to the section being edited, without the editor runtime/
    # data-cz-field tags `editable` also carries. See _apply_design.
    body_html = "".join(
        _render_block(b, t, i, editable, block_anchors) for i, b in enumerate(blocks)
    ) or _text({"body": page.get("title")}, t)

    nav_links = "".join(
        f'<a href="{"/" if p["slug"] in ("home", home_slug) else "/p/" + _esc(p["slug"])}">{_esc(p["title"])}</a>'
        for p in nav_pages)
    header_cls = "cz-header center" if t["navStyle"] == "centered" else "cz-header"

    theme_vars = (
        f":root{{--bg:{_clean_css(c['bg'])};--surface:{_clean_css(c['surface'])};"
        f"--ink:{_clean_css(c['text'])};--muted:{_clean_css(c['muted'])};--line:{_clean_css(c['border'])};"
        f"--brand:{_clean_css(c['brand'])};--brand-fg:{_clean_css(c['brandText'])};--accent:{_clean_css(c['accent'])};"
        f"--radius:{_clean_css(t['radius'])};--font-h:{_font_stack(t['heading'])};--font-b:{_font_stack(t['body'])};"
        # `--t-*`: stable, cycle-proof aliases for design_registry.DESIGN_COLOR_TOKENS.
        # A `_design` color token must NEVER resolve through --bg/--surface/--brand/etc
        # directly — a section that also sets colors.accent remaps --brand to
        # --cz-brand (the `.cz-acc` class, below), and --cz-brand's own value is
        # `var(--brand)`. If a token had resolved to `var(--brand)`, that section's
        # gradient/icon colors would read `--brand -> --cz-brand -> --brand`, a
        # reference cycle the CSS spec makes INVALID (not "falls back to the
        # cycled value" — the whole custom property computes to nothing), which is
        # exactly what killed the icons and gradient in the 2026-07-21 "brand-glow
        # + accent" incident. --t-* are declared ONCE here with concrete values and
        # no section-scoped class ever reassigns them, so no cycle is constructible.
        f"--t-bg:{_clean_css(c['bg'])};--t-surface:{_clean_css(c['surface'])};--t-ink:{_clean_css(c['text'])};"
        f"--t-line:{_clean_css(c['border'])};--t-brand:{_clean_css(c['brand'])};--t-muted:{_clean_css(c['muted'])}}}"
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
