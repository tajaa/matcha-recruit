"""Minimal Cappe public-site renderer.

Turns a published site's theme + a page's content blocks into a standalone HTML
document. This is the first slice of the (otherwise deferred) public renderer —
enough to view a site served at its subdomain. Block shapes match the seed
templates: hero / text / features / contact (unknown types degrade gracefully).
All user content is HTML-escaped.
"""
import html
from typing import Any


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _render_block(block: dict, primary: str) -> str:
    if not isinstance(block, dict):
        return ""
    btype = block.get("type")
    if btype == "hero":
        cta = block.get("cta")
        return f"""
        <section class="hero">
          <h1>{_esc(block.get('heading'))}</h1>
          <p class="lead">{_esc(block.get('subheading'))}</p>
          {f'<a class="cta" href="#">{_esc(cta)}</a>' if cta else ''}
        </section>"""
    if btype == "text":
        return f'<section class="text"><p>{_esc(block.get("body"))}</p></section>'
    if btype == "features":
        items = block.get("items") or []
        cards = "".join(
            f'<div class="card"><h3>{_esc(i.get("title"))}</h3><p>{_esc(i.get("body"))}</p></div>'
            for i in items if isinstance(i, dict)
        )
        return f'<section class="features">{cards}</section>'
    if btype == "contact":
        fields = block.get("fields") or ["name", "email", "message"]
        inputs = "".join(
            (f'<textarea placeholder="{_esc(f)}"></textarea>' if f == "message"
             else f'<input placeholder="{_esc(f)}" />')
            for f in fields
        )
        return f"""
        <section class="contact">
          <h2>{_esc(block.get('heading') or 'Contact')}</h2>
          <form onsubmit="return false">{inputs}<button>Send</button></form>
        </section>"""
    # Unknown block → render any 'body'/'heading' it has, or skip.
    body = block.get("body") or block.get("heading")
    return f'<section class="text"><p>{_esc(body)}</p></section>' if body else ""


def render_site_html(site: dict, page: dict, nav_pages: list[dict]) -> str:
    """Full HTML document for one page of a site."""
    theme = site.get("theme_config") or {}
    primary = _esc(theme.get("primaryColor") or "#10b981")
    font = _esc(theme.get("font") or "Inter")

    content = page.get("content") or {}
    blocks = content.get("blocks") if isinstance(content, dict) else None
    blocks = blocks if isinstance(blocks, list) else []
    body_html = "".join(_render_block(b, primary) for b in blocks)
    if not body_html:
        body_html = f'<section class="text"><p>{_esc(page.get("title"))}</p></section>'

    nav = "".join(
        f'<a href="{"/" if p["slug"] in ("home", nav_pages[0]["slug"]) else "/p/" + _esc(p["slug"])}">{_esc(p["title"])}</a>'
        for p in nav_pages
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(site.get('name'))} — {_esc(page.get('title'))}</title>
  <style>
    :root {{ --primary: {primary}; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: '{font}', -apple-system, system-ui, sans-serif; color: #18181b; }}
    header {{ display: flex; gap: 1.25rem; align-items: center; padding: 1rem 2rem; border-bottom: 1px solid #e4e4e7; position: sticky; top: 0; background: #fff; }}
    header .brand {{ font-weight: 700; font-size: 1.1rem; }}
    header nav a {{ margin-left: 1rem; color: #52525b; text-decoration: none; font-size: .9rem; }}
    header nav a:hover {{ color: var(--primary); }}
    .hero {{ padding: 5rem 2rem; text-align: center; background: linear-gradient(180deg,#fafafa,#fff); }}
    .hero h1 {{ font-size: 2.75rem; margin: 0 0 .5rem; }}
    .hero .lead {{ color: #71717a; font-size: 1.15rem; max-width: 40rem; margin: 0 auto 1.5rem; }}
    .cta {{ display: inline-block; background: var(--primary); color: #fff; padding: .7rem 1.4rem; border-radius: .6rem; text-decoration: none; font-weight: 600; }}
    .text {{ max-width: 44rem; margin: 0 auto; padding: 2rem; line-height: 1.7; color: #3f3f46; }}
    .features {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 1.25rem; max-width: 60rem; margin: 0 auto; padding: 2rem; }}
    .card {{ border: 1px solid #e4e4e7; border-radius: .9rem; padding: 1.5rem; }}
    .card h3 {{ margin: 0 0 .35rem; }}
    .card p {{ margin: 0; color: #71717a; }}
    .contact {{ max-width: 30rem; margin: 0 auto; padding: 2rem 2rem 4rem; }}
    .contact form {{ display: flex; flex-direction: column; gap: .6rem; }}
    .contact input, .contact textarea {{ padding: .6rem .8rem; border: 1px solid #d4d4d8; border-radius: .5rem; font: inherit; }}
    .contact button {{ background: var(--primary); color: #fff; border: 0; padding: .7rem; border-radius: .5rem; font-weight: 600; cursor: pointer; }}
    footer {{ text-align: center; color: #a1a1aa; font-size: .8rem; padding: 2rem; border-top: 1px solid #f4f4f5; }}
  </style>
</head>
<body>
  <header>
    <span class="brand">{_esc(site.get('name'))}</span>
    <nav>{nav}</nav>
  </header>
  <main>{body_html}</main>
  <footer>Built with Cappe</footer>
</body>
</html>"""
