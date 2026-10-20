"""A product's own page — `/shop/<slug>` — and the store's catalog, `/shop`.

The product page is server-rendered so a link shared on Instagram or found on
Google has something to show before any script runs: name, price, pictures,
description, Open Graph tags for the link preview, and Product structured data
(services/product_pages.py). The store widget (store.js) then takes over the
same panel in place — options, variants, the bag, reviews — exactly as the
overlay on a shop page does.

Everything the owner typed is escaped. Only our markup and our scripts run
here: none of the site's own blocks.
"""
from __future__ import annotations

from html import escape
from typing import Optional

from ..email import fmt_money
from ..product_pages import absolute, is_sold_out, product_ld, product_path
from .blocks import _STORE_JS
from .page import render_site_html

_WIDGET_ID = "czproduct"


def _media_html(name: str, images: list) -> str:
    if not images:
        return '<div class="cz-pd__shot"><div class="cz-pd__noimg"></div></div>'
    first = images[0]
    shot = (f'<div class="cz-pd__shot"><img src="{escape(first["url"], quote=True)}" '
            f'alt="{escape(first.get("alt") or name, quote=True)}" /></div>')
    if len(images) < 2:
        return shot
    thumbs = "".join(
        f'<button type="button" class="cz-pd__thumb{" is-on" if i == 0 else ""}" data-img="{i}">'
        f'<img src="{escape(img["url"], quote=True)}" alt="{escape(img.get("alt") or "", quote=True)}" /></button>'
        for i, img in enumerate(images)
    )
    return f'{shot}<div class="cz-pd__thumbs">{thumbs}</div>'


def _price_html(price_cents: int, base_cents: int, discount_percent: int, currency: str) -> str:
    if discount_percent and price_cents != base_cents:
        return (f'<span class="cz-pd__was">{escape(fmt_money(base_cents, currency))}</span>'
                f'{escape(fmt_money(price_cents, currency))}<span class="cz-pd__off">{int(discount_percent)}% off</span>')
    return escape(fmt_money(price_cents, currency)) if price_cents else "Free"


def render_product_page(site: dict, nav: list[dict], product: dict, *, images: list, variants: list,
                        price_cents: int, discount_percent: int, origin: str, rating: Optional[dict],
                        back_href: str, back_label: str) -> str:
    name = product.get("name") or ""
    cur = product.get("currency") or "USD"
    url = f"{origin}{product_path(product['slug'])}"
    sold_out = is_sold_out(product, variants)
    desc = (product.get("description") or "").strip()
    info = (
        (f'<div class="cz-eyebrow">{escape(product["category"])}</div>' if product.get("category") else "")
        + f'<h1 class="cz-pd__name">{escape(name)}</h1>'
        + f'<div class="cz-pd__price">{_price_html(price_cents, product["price_cents"], discount_percent, cur)}</div>'
        + (f'<p class="cz-pd__desc">{escape(desc)}</p>' if desc else "")
        + ('<p class="cz-pd__stock">Sold out</p>' if sold_out else "")
    )
    body = (
        '<section class="cz-store cz-product-page"><div class="cz-wrap">'
        f'<nav class="cz-crumbs" aria-label="Breadcrumb"><a href="{escape(back_href, quote=True)}">← {escape(back_label)}</a></nav>'
        f'<div id="{_WIDGET_ID}" class="cz-pd-inline" data-product="{escape(product["slug"], quote=True)}">'
        '<div class="cz-pd__panel cz-pd__panel--inline"><div class="cz-pd__grid">'
        f'<div class="cz-pd__media" data-media>{_media_html(name, images)}</div>'
        f'<div class="cz-pd__info" data-info>{info}</div>'
        '</div><div class="cz-pd__reviews" data-reviews></div></div>'
        "</div></div></section>"
        f"<script>{_STORE_JS.replace('__ID__', _WIDGET_ID)}</script>"
    )
    first_image = absolute(images[0]["url"], origin) if images else None
    extra_head = (
        f'<meta property="product:price:amount" content="{price_cents / 100:.2f}" />'
        f'<meta property="product:price:currency" content="{escape(cur, quote=True)}" />'
        f'<meta property="product:availability" content="{"out of stock" if sold_out else "in stock"}" />'
        + product_ld(product, images=images, variants=variants, origin=origin, url=url,
                     price_cents=price_cents, rating=rating)
    )
    return render_site_html(
        site, {"title": name, "slug": "__product", "content": {}}, nav,
        body_override=body, extra_head=extra_head,
        seo={"title": f"{name} — {site.get('name')}", "description": desc[:300], "image": first_image,
             "type": "product", "url": url},
    )


def render_catalog_page(site: dict, nav: list[dict], products: list[dict], *, origin: str) -> str:
    """Every product, linked: the page a crawler reads to find them all. The
    store widget replaces the list with the usual grid."""
    items = "".join(
        f'<li><a href="{escape(product_path(p["slug"]), quote=True)}">{escape(p["name"] or "")}</a></li>'
        for p in products if p.get("slug")
    )
    body = (
        '<section id="shop" class="cz-store"><div class="cz-wrap">'
        f'<div class="cz-head"><h1>Shop</h1></div>'
        f'<div id="czcatalog" class="cz-store-box"><ul class="cz-catalog">{items}</ul></div>'
        "</div></section>"
        f"<script>{_STORE_JS.replace('__ID__', 'czcatalog')}</script>"
    )
    return render_site_html(
        site, {"title": "Shop", "slug": "__shop", "content": {}}, nav, body_override=body,
        seo={"title": f"Shop — {site.get('name')}", "url": f"{origin}/shop"},
    )
