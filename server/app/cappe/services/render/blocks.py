"""Block renderers + their interactive-widget JS, the freeform canvas block,
and `_render_block` (the per-block dispatch + `_apply_design` wrapper)."""
import re
from urllib.parse import quote

from .design import _apply_design, _font_stack
from .sanitize import _clampi, _clean_css, _cv_safe_id, _esc, _hexonly, _num, _safe_href, _safe_image, _uid


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
.cz-editable [data-cz-block].cz-drop-target{outline:3px dashed #10b981;outline-offset:-3px;background:rgba(16,185,129,.08)}
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
// Drag an external image (an asset-library thumbnail, a chat-generated image)
// onto a section to set it as that section's background — a native HTML5
// drag, NOT the pointer-based drag-reorder above (that's for reordering
// sections, entirely within this frame; this drag originates in the PARENT
// document, so only the standard dragover/drop events fire in here at all).
var dropTargetEl=null;
function clearDropTarget(){if(dropTargetEl){dropTargetEl.classList.remove('cz-drop-target');dropTargetEl=null;}}
document.addEventListener('dragover',function(e){
  // Not gated on restrictMode (Form mode) — setting a section's background is
  // orthogonal to the canvas-only affordances that flag suppresses (freeform
  // element drag/resize, inline text edit), and works from either mode.
  if(themeMode)return;
  var b=e.target.closest&&e.target.closest('[data-cz-block]');
  if(!b){clearDropTarget();return;}
  e.preventDefault();
  if(b!==dropTargetEl){clearDropTarget();dropTargetEl=b;b.classList.add('cz-drop-target');}
});
document.addEventListener('dragleave',function(e){
  // Only clear when the pointer actually left the highlighted block (not a
  // bubbled leave from a child element re-entering a sibling).
  if(dropTargetEl&&(!e.relatedTarget||!dropTargetEl.contains(e.relatedTarget)))clearDropTarget();
});
document.addEventListener('drop',function(e){
  if(themeMode)return;
  var b=e.target.closest&&e.target.closest('[data-cz-block]');
  clearDropTarget();
  if(!b||!e.dataTransfer)return;
  e.preventDefault();
  var url=e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('text/plain');
  if(!url)return;
  post({type:'cz-drop-image',block:idxOf(b),url:url});
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


def _render_block(block, t, index=None, editable=False, anchors=False):
    if not isinstance(block, dict):
        return ""
    btype = block.get("type")
    # Canvas needs the block index (for per-block CSS scoping) + editable, so it's
    # dispatched here rather than through _RENDERERS' (block, t[, editable]) shape.
    if btype == "canvas":
        raw = _canvas(block, t, editable, index if index is not None else 0)
        return _apply_design(
            raw, block.get("_design"), block_index=index, editable=editable, anchors=anchors,
        ) if raw else raw
    fn = _RENDERERS.get(btype)
    if fn:
        raw = fn(block, t, editable) if btype in _EDITABLE_AWARE else fn(block, t)
    else:
        body = block.get("body") or block.get("heading")
        raw = _text({"body": body}, t) if body else ""
    if not raw:
        return raw
    return _apply_design(raw, block.get("_design"), block_index=index, editable=editable, anchors=anchors)
