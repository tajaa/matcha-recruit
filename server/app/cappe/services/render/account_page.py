"""The shopper's account page — `/account` on the store's own host.

Sign in with an emailed code, then: orders (each linking to its order page),
subscriptions (cancel, resume, update the card through Stripe's portal) and
saved addresses. A "Subscribe" button in the product panel lands here with
the product in the query string; once signed in, the page opens the
subscription checkout.

The page is a shell; everything personal is fetched by `account.js` with an
access token it holds in memory (see routes/public/shopper_web.py for the
cookie that keeps the session). Only our markup and our script run here —
none of the site's own blocks.
"""
from __future__ import annotations

from pathlib import Path

from .page import render_site_html

_ACCOUNT_JS = (Path(__file__).parent / "assets" / "account.js").read_text(encoding="utf-8")


def render_account_page(site: dict, nav: list[dict]) -> str:
    body = (
        '<section class="cz-order"><div class="cz-wrap cz-order__wrap cz-account" data-czaccount>'
        '<p class="cz-eyebrow">Your account</p>'
        '<h1 class="cz-order__title" data-title>Sign in</h1>'
        '<div data-body><p class="cz-order__lead">Loading…</p></div>'
        "</div></section>"
    )
    return render_site_html(
        site, {"title": "Your account", "slug": "__account", "content": {}}, nav,
        body_override=body,
        extra_head='<meta name="robots" content="noindex,nofollow" /><meta name="referrer" content="no-referrer" />',
        extra_body_end=f"<script>{_ACCOUNT_JS}</script>",
    )
