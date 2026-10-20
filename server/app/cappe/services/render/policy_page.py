"""A store's policy page — `/policies/<kind>` (services/policies.py).

The owner's plain text, escaped, in the site's theme: no blocks, no scripts of
the site's own. Linked from the footer, the sitemap, the bag and Stripe's
payment page.
"""
from __future__ import annotations

from html import escape

from ..policies import TITLES, body_html, policy_path
from .page import render_site_html


def render_policy_page(site: dict, nav: list[dict], kind: str, body: str, *, updated_at, origin: str) -> str:
    title = TITLES[kind]
    when = updated_at.strftime("%-d %B %Y") if hasattr(updated_at, "strftime") else ""
    html = (
        '<section class="cz-policy"><div class="cz-wrap cz-policy__wrap">'
        f"<h1>{escape(title)}</h1>"
        + (f'<p class="cz-policy__updated">Last updated {escape(when)}</p>' if when else "")
        + f'<div class="cz-policy__body">{body_html(body)}</div>'
        "</div></section>"
    )
    return render_site_html(
        site, {"title": title, "slug": f"__policy_{kind}", "content": {}}, nav, body_override=html,
        seo={"title": f"{title} — {site.get('name')}", "url": f"{origin}{policy_path(kind)}"},
    )
