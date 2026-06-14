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
from typing import Any
from urllib.parse import quote

_uid_counter = itertools.count(1)


def _uid() -> int:
    return next(_uid_counter)


# ── tokens ──────────────────────────────────────────────────────────────────

_SERIF = {
    "playfair display", "lora", "fraunces", "source serif pro", "source serif 4",
    "merriweather", "georgia", "pt serif", "cormorant garamond", "libre baskerville",
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


def _font_stack(name: str) -> str:
    generic = "serif" if (name or "").strip().lower() in _SERIF else "sans-serif"
    fallback = "ui-serif, Georgia," if generic == "serif" else "ui-sans-serif, system-ui, -apple-system,"
    return f"'{_clean_css(name)}', {fallback} {generic}"


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
  line-height:1.6;-webkit-font-smoothing:antialiased;font-size:17px}
img{max-width:100%;display:block}
a{color:inherit}
h1,h2,h3{font-family:var(--font-h);font-weight:700;line-height:1.05;letter-spacing:-0.02em;margin:0}
p{margin:0}
.cz-wrap{max-width:72rem;margin:0 auto;padding:0 1.5rem}
.cz-narrow{max-width:44rem;margin:0 auto;padding:0 1.5rem}

/* header */
.cz-header{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--bg) 82%,transparent);
  backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.cz-header .cz-bar{display:flex;align-items:center;gap:1.5rem;padding:1.05rem 0}
.cz-header.center .cz-bar{justify-content:center}
.cz-header:not(.center) .cz-bar{justify-content:space-between}
.cz-brand{font-family:var(--font-h);font-weight:700;font-size:1.2rem;text-decoration:none;color:var(--ink)}
.cz-brand img{height:30px;width:auto}
.cz-nav{display:flex;gap:1.5rem;flex-wrap:wrap}
.cz-nav a{color:var(--muted);text-decoration:none;font-size:.95rem;font-weight:500;transition:color .2s}
.cz-nav a:hover{color:var(--brand)}

/* buttons */
.cz-btn{display:inline-flex;align-items:center;justify-content:center;gap:.5rem;
  padding:.8rem 1.5rem;border-radius:var(--radius);font-weight:600;font-size:.95rem;
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
.cz-head h2{font-size:clamp(1.8rem,4vw,2.6rem)}
.cz-head p{margin-top:.75rem;color:var(--muted)}
.cz-eyebrow{font-size:.72rem;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:var(--brand)}

/* hero */
.cz-hero{padding:clamp(3.5rem,9vw,7rem) 0}
.cz-hero--centered{text-align:center;background:linear-gradient(180deg,var(--surface),var(--bg))}
.cz-hero__title{font-size:clamp(2.4rem,6vw,4.4rem)}
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
.cz-hero--image .cz-wrap{position:relative;z-index:1}
.cz-hero--image .cz-hero__title{margin:0 auto;max-width:20ch;text-shadow:0 2px 24px rgba(0,0,0,.35)}
.cz-hero--image .cz-hero__lead{color:rgba(255,255,255,.88);margin:1.25rem auto 0}
.cz-hero--image .cz-eyebrow{color:rgba(255,255,255,.85)}
.cz-hero--left{text-align:left}
.cz-hero--left .cz-hero__title,.cz-hero--left .cz-hero__lead{margin-left:0;margin-right:0}
.cz-hero--left .cz-cta-row{justify-content:flex-start}

/* features */
.cz-features{padding:clamp(3rem,7vw,5rem) 0}
.cz-cards{display:grid;gap:1.25rem;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.cz-card{border:1px solid var(--line);background:var(--surface);border-radius:var(--radius);padding:1.6rem}
.cz-feat__icon{width:44px;height:44px;display:flex;align-items:center;justify-content:center;
  border-radius:var(--radius);background:color-mix(in srgb,var(--brand) 14%,transparent);
  color:var(--brand);font-weight:700;font-size:1.15rem;margin-bottom:1rem}
.cz-card h3{font-size:1.15rem;margin-bottom:.4rem}
.cz-card p{color:var(--muted);font-size:.95rem}

/* gallery */
.cz-gallery{padding:clamp(3rem,7vw,5rem) 0}
.cz-grid-img{display:grid;gap:.85rem;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.cz-tile{position:relative;border-radius:var(--radius);overflow:hidden}
.cz-tile img{aspect-ratio:1;width:100%;object-fit:cover;transition:transform .5s}
.cz-tile:hover img{transform:scale(1.05)}
.cz-tile figcaption{position:absolute;inset:auto 0 0 0;padding:.7rem .9rem;color:#fff;font-size:.85rem;
  background:linear-gradient(transparent,rgba(0,0,0,.6))}

/* pricing */
.cz-pricing{padding:clamp(3rem,7vw,5rem) 0}
.cz-plans{display:grid;gap:1.25rem;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));max-width:60rem;margin:0 auto}
.cz-plan{position:relative;border:1px solid var(--line);background:var(--surface);border-radius:var(--radius);
  padding:2rem;display:flex;flex-direction:column}
.cz-plan--hot{outline:2px solid var(--brand);outline-offset:-1px;box-shadow:0 20px 40px -24px rgba(0,0,0,.4)}
.cz-plan__badge{position:absolute;top:-.7rem;left:50%;transform:translateX(-50%);background:var(--brand);
  color:var(--brand-fg);font-size:.7rem;font-weight:700;padding:.25rem .7rem;border-radius:999px}
.cz-plan__price{font-size:2.4rem;font-weight:700;font-family:var(--font-h);margin:.5rem 0}
.cz-plan__price span{font-size:.9rem;color:var(--muted);font-weight:400}
.cz-plan ul{list-style:none;padding:0;margin:0 0 1.5rem;display:flex;flex-direction:column;gap:.6rem;flex:1}
.cz-plan li{color:var(--muted);font-size:.93rem;display:flex;gap:.5rem}
.cz-plan li::before{content:"✓";color:var(--brand);font-weight:700}

/* testimonial */
.cz-quotes{padding:clamp(3rem,7vw,5rem) 0}
.cz-quote-grid{display:grid;gap:1.25rem;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));max-width:60rem;margin:0 auto}
.cz-quote{border:1px solid var(--line);background:var(--surface);border-radius:var(--radius);padding:2rem}
.cz-quote blockquote{font-family:var(--font-h);font-size:1.15rem;line-height:1.5;margin:0}
.cz-quote figcaption{margin-top:1.25rem;font-size:.9rem}
.cz-quote figcaption b{color:var(--ink)}
.cz-quote figcaption span{color:var(--muted)}

/* cta band */
.cz-band{background:var(--brand);color:var(--brand-fg);text-align:center;padding:clamp(3rem,7vw,5rem) 0}
.cz-band h2{font-size:clamp(1.8rem,4vw,2.6rem)}
.cz-band p{margin:.75rem auto 0;max-width:34rem;opacity:.9}
.cz-band .cz-btn{margin-top:1.75rem;background:rgba(255,255,255,.16);color:#fff}
.cz-band .cz-btn:hover{background:rgba(255,255,255,.26)}

/* menu */
.cz-menu{padding:clamp(3rem,7vw,5rem) 0}
.cz-menu-grid{display:grid;gap:2.5rem;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));max-width:54rem;margin:0 auto}
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
.cz-text h2{font-size:clamp(1.6rem,3.5vw,2.2rem);margin-bottom:1rem}
.cz-text p{font-size:1.12rem;color:var(--muted);line-height:1.75}

/* forms / widgets */
.cz-form-sec{padding:clamp(3rem,7vw,5rem) 0}
.cz-field{width:100%;padding:.7rem .9rem;border:1px solid var(--line);background:var(--bg);color:var(--ink);
  border-radius:var(--radius);font:inherit;font-size:.95rem;outline:none;transition:border-color .2s}
.cz-field:focus{border-color:var(--brand)}
.cz-form{display:flex;flex-direction:column;gap:.7rem;max-width:32rem;margin:0 auto}
.cz-label{font-size:.78rem;font-weight:600;color:var(--muted);display:block;margin-bottom:.3rem}
.cz-msg{font-size:.9rem}
.cz-msg.err{color:#ef4444}.cz-msg.ok{color:var(--brand)}
.cz-inline{display:flex;gap:.6rem}.cz-inline .cz-field{flex:1}

/* store */
.cz-store{padding:clamp(3rem,7vw,5rem) 0}
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
.cz-pd__name{font-size:clamp(1.6rem,3.4vw,2.2rem);line-height:1.05;margin:.1rem 0 0}
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
  font-size:.85rem;padding:2.5rem 0}
.cz-footer .small{font-size:.75rem;opacity:.7;margin-top:.35rem}
.cz-foot-social{display:flex;flex-wrap:wrap;justify-content:center;gap:1.1rem;margin-bottom:1rem}
.cz-foot-social a{color:var(--ink);text-decoration:none;font-size:.82rem;font-weight:600;letter-spacing:.02em}
.cz-foot-social a:hover{color:var(--brand)}
.cz-foot-contact{display:flex;flex-wrap:wrap;justify-content:center;gap:.4rem 1.2rem;margin-bottom:1rem}
.cz-foot-contact a,.cz-foot-contact span{color:var(--muted);text-decoration:none;font-size:.9rem}
.cz-foot-contact a:hover{color:var(--brand)}

/* stats band */
.cz-stats{padding:clamp(3rem,7vw,5rem) 0}
.cz-stats-grid{display:grid;gap:1.5rem;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));max-width:62rem;margin:0 auto;text-align:center}
.cz-stat{padding:1rem .5rem;position:relative}
.cz-stat+.cz-stat::before{content:"";position:absolute;left:0;top:18%;bottom:18%;width:1px;background:var(--line)}
.cz-stat__num{font-family:var(--font-h);font-weight:700;font-size:clamp(2.4rem,5vw,3.4rem);line-height:1;
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
.cz-faq{padding:clamp(3rem,7vw,5rem) 0}
.cz-faq__list{max-width:46rem;margin:0 auto;border-top:1px solid var(--line)}
.cz-faq__item{border-bottom:1px solid var(--line)}
.cz-faq__item summary{display:flex;justify-content:space-between;align-items:center;gap:1rem;cursor:pointer;
  padding:1.3rem .25rem;font-family:var(--font-h);font-weight:600;font-size:1.12rem;color:var(--ink);list-style:none}
.cz-faq__item summary::-webkit-details-marker{display:none}
.cz-faq__item summary::after{content:"+";color:var(--brand);font-size:1.5rem;font-weight:300;line-height:1;transition:transform .25s}
.cz-faq__item[open] summary::after{transform:rotate(45deg)}
.cz-faq__item p{color:var(--muted);font-size:1.02rem;line-height:1.75;margin:0;padding:0 .25rem 1.4rem;max-width:42rem}

/* bento grid */
.cz-bento{padding:clamp(3rem,7vw,5rem) 0}
.cz-bento-grid{display:grid;gap:1.1rem;grid-template-columns:repeat(2,1fr)}
.cz-bento-cell{border:1px solid var(--line);background:var(--surface);border-radius:var(--radius);padding:1.7rem;
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
.cz-split{padding:clamp(3rem,7vw,5rem) 0}
.cz-split__grid{display:grid;gap:2.5rem;align-items:center}
.cz-split__art{aspect-ratio:4/3;border-radius:var(--radius);overflow:hidden;background:linear-gradient(135deg,var(--brand),var(--accent))}
.cz-split__art img{width:100%;height:100%;object-fit:cover}
.cz-split__body h2{font-size:clamp(1.6rem,3.5vw,2.4rem);margin-bottom:1rem}
.cz-split__body>.cz-eyebrow{margin-bottom:.9rem}
.cz-split__body p{color:var(--muted);font-size:1.08rem;line-height:1.7}
.cz-split__bullets{list-style:none;padding:0;margin:1.25rem 0 0;display:flex;flex-direction:column;gap:.7rem}
.cz-split__bullets li{display:flex;gap:.6rem;color:var(--ink);font-size:1rem}
.cz-split__bullets li::before{content:"✓";color:var(--brand);font-weight:700}
.cz-split .cz-btn{margin-top:1.6rem}

/* credentials / qualifications */
.cz-creds{padding:clamp(3rem,7vw,5rem) 0}
.cz-creds-grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));max-width:62rem;margin:0 auto}
.cz-cred{display:flex;gap:.95rem;align-items:flex-start;border:1px solid var(--line);background:var(--surface);
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
.cz-reviews{padding:clamp(3rem,7vw,5rem) 0}
.cz-reviews-grid{display:grid;gap:1.25rem;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));max-width:60rem;margin:0 auto}
.cz-review{border:1px solid var(--line);background:var(--surface);border-radius:var(--radius);padding:1.6rem}
.cz-review__stars{color:#f5b301;letter-spacing:2px;margin-bottom:.55rem}
.cz-review blockquote{margin:0;font-size:1.02rem;line-height:1.6;color:var(--ink)}
.cz-review figcaption{margin-top:.9rem;font-weight:600;color:var(--muted);font-size:.9rem}
.cz-rv-form{max-width:34rem;margin:2rem auto 0;display:flex;flex-direction:column;gap:.6rem;
  border-top:1px solid var(--line);padding-top:1.6rem}
.cz-rv-form__t{font-weight:700;font-family:var(--font-h);text-align:center}

/* map + hours */
.cz-map{padding:clamp(3rem,7vw,5rem) 0}
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

/* scroll-reveal — only active once JS adds .cz-js (no-JS shows everything) */
.cz-premium.cz-js main>section{opacity:0;transform:translateY(26px);
  transition:opacity .9s cubic-bezier(.2,.7,.2,1),transform .9s cubic-bezier(.2,.7,.2,1)}
.cz-premium.cz-js main>section.cz-in{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){
  .cz-premium.cz-js main>section{opacity:1;transform:none;transition:none}
  .cz-premium::after{animation:none}}
"""


# ── blocks ──────────────────────────────────────────────────────────────────

def _btn(label, href, *, solid=True):
    if not label:
        return ""
    cls = "cz-btn--solid" if solid else "cz-btn--ghost"
    return f'<a class="cz-btn {cls}" href="{_esc(_safe_href(href))}">{_esc(label)}</a>'


def _head(b):
    h = f'<h2>{_esc(b.get("heading"))}</h2>' if b.get("heading") else ""
    s = f'<p>{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    return f'<div class="cz-head">{h}{s}</div>' if (h or s) else ""


def _hero(b, t):
    style = (b.get("style") or t["heroStyle"]).lower()
    eyebrow = f'<p class="cz-eyebrow cz-hero__eyebrow">{_esc(b.get("eyebrow"))}</p>' if b.get("eyebrow") else ""
    title = f'<h1 class="cz-hero__title">{_esc(b.get("heading"))}</h1>'
    lead = f'<p class="cz-hero__lead">{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    cta = (f'<div class="cz-cta-row">{_btn(b.get("cta"), b.get("ctaHref"))}'
           f'{_btn(b.get("cta2"), b.get("cta2Href"), solid=False)}</div>') if (b.get("cta") or b.get("cta2")) else ""
    img = _safe_image(b.get("image"))

    # A centered hero that has a photo becomes a photo-overlay hero — the
    # intuitive result of "add a hero image". split/minimal stay explicit.
    if img and style == "centered":
        style = "image"

    if style == "image":
        overlay = (b.get("overlay") or "medium").lower()
        overlay = overlay if overlay in ("light", "medium", "dark") else "medium"
        cls = f"cz-hero--image cz-ov-{overlay}"
        if (b.get("align") or "center").lower() == "left":
            cls += " cz-hero--left"
        if (b.get("height") or "tall").lower() == "full":
            cls += " cz-hero--full"
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


def _features(b, t):
    cards = "".join(
        f'<div class="cz-card"><div class="cz-feat__icon">{_esc(i.get("icon") or (i.get("title") or "•")[:1])}</div>'
        f'<h3>{_esc(i.get("title"))}</h3><p>{_esc(i.get("body"))}</p></div>'
        for i in (b.get("items") or []) if isinstance(i, dict))
    return f'<section class="cz-features"><div class="cz-wrap">{_head(b)}<div class="cz-cards">{cards}</div></div></section>'


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


def _cta(b, t):
    sub = f'<p>{_esc(b.get("subheading"))}</p>' if b.get("subheading") else ""
    return (f'<section class="cz-band"><div class="cz-wrap"><h2>{_esc(b.get("heading"))}</h2>{sub}'
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


def _split(b, t):
    img = _safe_image(b.get("image"))
    art = f'<img src="{_esc(img)}" alt="" />' if img else ""
    eyebrow = f'<p class="cz-eyebrow">{_esc(b.get("eyebrow"))}</p>' if b.get("eyebrow") else ""
    head = f'<h2>{_esc(b.get("heading"))}</h2>' if b.get("heading") else ""
    body = f'<p>{_esc(b.get("body"))}</p>' if b.get("body") else ""
    bl = [x for x in (b.get("bullets") or []) if x]
    bullets = ('<ul class="cz-split__bullets">' + "".join(f'<li>{_esc(x)}</li>' for x in bl) + "</ul>") if bl else ""
    cta = _btn(b.get("cta"), b.get("ctaHref")) if b.get("cta") else ""
    mod = " cz-split--reverse" if b.get("reverse") else ""
    return (f'<section class="cz-split{mod}"><div class="cz-wrap"><div class="cz-split__grid">'
            f'<div class="cz-split__art">{art}</div>'
            f'<div class="cz-split__body">{eyebrow}{head}{body}{bullets}{cta}</div>'
            f'</div></div></section>')


def _text(b, t):
    body = b.get("body")
    paras = body if isinstance(body, list) else [body]
    inner = "".join(f"<p>{_esc(p)}</p>" for p in paras if p)
    head = f'<h2>{_esc(b.get("heading"))}</h2>' if b.get("heading") else ""
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


# Scroll-reveal for premium sites. Adds `cz-js` (so the hide-state CSS only
# applies when JS is available — no-JS shows everything), then reveals each
# <section> as it scrolls in. No-op if IntersectionObserver is unsupported.
_PREMIUM_JS = (
    "<script>(function(){var b=document.body;"
    "if(!b||b.className.indexOf('cz-premium')<0||!('IntersectionObserver' in window))return;"
    "b.classList.add('cz-js');"
    "var io=new IntersectionObserver(function(es){es.forEach(function(e){"
    "if(e.isIntersecting){e.target.classList.add('cz-in');io.unobserve(e.target);}});},{threshold:.12});"
    "document.querySelectorAll('main>section').forEach(function(s){io.observe(s);});})();</script>"
)


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
RT.post('/orders',{customer_email:email,customer_name:info.querySelector('[data-name]').value.trim(),items:[item]}).then(function(){info.querySelector('.cz-pd__buy').innerHTML='<p class="cz-msg ok">Order placed. We will email you'+(p.fulfillment==='digital'?' your download once confirmed':'')+'.</p>';
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
Promise.all([RT.get('/booking-types'),RT.get('/rider').catch(function(){return {items:[]};}),RT.get('/staff').catch(function(){return [];})]).then(function(r){
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
RT.get('/booking-types/'+encodeURIComponent(t.id)+'/slots'+(selStaff?('?staff_id='+encodeURIComponent(selStaff)):'')).then(function(d){var slots=(d&&d.slots)||[];
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
sb.disabled=true;msg.textContent='Requesting…';msg.className='cz-msg';
RT.post('/bookings',body).then(function(res){var price=res.quoted_price_cents?(' — '+RT.money(res.quoted_price_cents,'USD')):'';
var note=res.requires_approval?'Request sent for '+RT.esc(new Date(res.starts_at).toLocaleString())+price+'. The host will review and confirm by email.':'Booked for '+RT.esc(new Date(res.starts_at).toLocaleString())+price+'. A confirmation is on its way.';
box.innerHTML='<p class="cz-msg ok">'+note+'</p>';
}).catch(function(e){sb.disabled=false;sb.textContent='Request booking';msg.textContent=e.message;msg.className='cz-msg err';});});
}).catch(function(){box.innerHTML='<p style="color:var(--muted)">Unable to load.</p>';});})();"""


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


def _map(b, t):
    """A "find us" block: address + directions deep links (no API key), plus an
    OpenStreetMap embed when the owner supplied lat/lng."""
    meta = t.get("meta") or {}
    geo = meta.get("geo") if isinstance(meta.get("geo"), dict) else {}
    addr = (b.get("address") or meta.get("contact_address") or "").strip()
    lat = _num(b.get("lat") if b.get("lat") not in (None, "") else geo.get("lat"))
    lng = _num(b.get("lng") if b.get("lng") not in (None, "") else geo.get("lng"))
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
    meta = t.get("meta") or {}
    hours = meta.get("hours") if isinstance(meta.get("hours"), list) else []
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


_RENDERERS = {
    "hero": _hero, "features": _features, "gallery": _gallery, "pricing": _pricing,
    "testimonial": _testimonial, "cta": _cta, "menu": _menu, "posts": _posts,
    "stats": _stats, "logos": _logos, "faq": _faq, "bento": _bento, "split": _split,
    "credentials": _credentials, "reviews": _reviews, "map": _map, "hours": _hours,
    "text": _text, "contact": _contact, "store": _store, "booking": _booking, "newsletter": _newsletter,
}


def _render_block(block, t):
    if not isinstance(block, dict):
        return ""
    fn = _RENDERERS.get(block.get("type"))
    if fn:
        return fn(block, t)
    body = block.get("body") or block.get("heading")
    return _text({"body": body}, t) if body else ""


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

def render_site_html(site: dict, page: dict, nav_pages: list[dict], preview: bool = False) -> str:
    t = _tokens(site.get("theme_config"))
    c = t["colors"]
    slug = site.get("slug") or ""
    home_slug = nav_pages[0]["slug"] if nav_pages else "home"
    # `preview` flags the editor's sandboxed iframe (no same-origin = no live API
    # fetch). Widgets read it to show a static placeholder instead of failing.
    _meta_ctx = site.get("meta_config") if isinstance(site.get("meta_config"), dict) else {}
    cappe_ctx = _js_obj({
        "slug": slug, "api": f"/api/cappe/public/sites/{slug}", "preview": bool(preview),
        "tz": site.get("timezone") or "UTC",
        "hours": _meta_ctx.get("hours") if isinstance(_meta_ctx.get("hours"), list) else [],
    })

    meta = site.get("meta_config") or {}
    logo = _safe_image(meta.get("logo_url")) if isinstance(meta, dict) else None
    brand_inner = f'<img src="{_esc(logo)}" alt="{_esc(site.get("name"))}" />' if logo else _esc(site.get("name"))

    # Give block renderers access to site context (used by map/hours blocks).
    t["meta"] = meta if isinstance(meta, dict) else {}
    t["site_name"] = site.get("name") or ""

    content = page.get("content") or {}
    blocks = content.get("blocks") if isinstance(content, dict) else None
    blocks = blocks if isinstance(blocks, list) else []
    body_html = "".join(_render_block(b, t) for b in blocks) or _text({"body": page.get("title")}, t)

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

    meta_dict = meta if isinstance(meta, dict) else {}
    head_title, head_seo = _head_seo(site, page, meta_dict)
    body_cls = "cz-premium" if t["premium"] else ""
    premium_js = _PREMIUM_JS if t["premium"] else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{head_title}</title>
  {head_seo}
  {_gfonts_link(t['heading'], t['body'])}
  <style>{theme_vars}{_BASE_CSS}</style>
  <script>window.__CAPPE__={cappe_ctx};</script>
  {_widget_runtime()}
</head>
<body class="{body_cls}">
  <header class="{header_cls}"><div class="cz-wrap cz-bar">
    <a class="cz-brand" href="/">{brand_inner}</a>
    <nav class="cz-nav">{nav_links}</nav>
  </div></header>
  <main>{body_html}</main>
  {_footer(site, meta_dict)}
  {premium_js}
</body>
</html>"""
