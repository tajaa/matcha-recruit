"""Cappe product pages — a product's web address, its pictures, and the facts
search engines and shopping feeds read about it.

A product lives at `/shop/<slug>` on its store (routes/render.py). The slug is
made from the name once and kept when the product is renamed, so a shared link
keeps working; the owner can change it on purpose. Pictures are an ordered
list whose first is the cover, which `cappe_products.image_url` mirrors for
everything that reads that one column (both apps, receipts, the directory).

`product_slug`, `gtin_valid`, `product_ld` and the price/availability helpers are
pure; the rest run in the caller's transaction, after the product row is
written or locked.
"""
from __future__ import annotations

import json
import re
import secrets
import unicodedata
from typing import Any, Iterable, Optional
from uuid import UUID

from fastapi import HTTPException

from .common import _SLUG_RE

MAX_IMAGES = 20
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_SLUG_MAX = 72  # leaves room for a "-<n>" suffix inside the 80-character column


def product_slug(text: Optional[str]) -> str:
    """"Café Crème — 250 g" → "cafe-creme-250-g". Never empty. Unlike
    `common.slugify` (sites, pages) it folds accents and fits the column's
    check, since it is a URL people share."""
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    slug = _SLUG_RE.sub("-", ascii_text.lower()).strip("-")[:_SLUG_MAX].strip("-")
    return slug or "product"


def product_path(slug: Optional[str]) -> Optional[str]:
    return f"/shop/{slug}" if slug else None


def gtin_valid(value: str) -> bool:
    """An 8-, 12-, 13- or 14-digit GTIN (EAN-8, UPC-A, EAN-13, GTIN-14) whose
    last digit is its check digit — the one a typo almost always breaks."""
    if not re.fullmatch(r"\d{8}|\d{12,14}", value or ""):
        return False
    digits = [int(c) for c in value]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


async def assign_slug(conn, site_id: UUID, product_id: UUID, name: str, wanted: Optional[str] = None) -> str:
    """Give a product its address. `wanted` is the owner's own choice: taken by
    another product is a 409, never a quiet "-2". Without one, the name's slug,
    with the first free "-2", "-3"… after it."""
    base = product_slug(wanted if wanted is not None else name)
    taken = {
        r["slug"] for r in await conn.fetch(
            "SELECT slug FROM cappe_products WHERE site_id = $1 AND id <> $2 "
            "AND (slug = $3 OR slug LIKE $3 || '-%')",
            site_id, product_id, base,
        )
    }
    if wanted is not None:
        if base in taken:
            raise HTTPException(status_code=409, detail=f'Another product already uses the address "{base}".')
        slug = base
    else:
        slug = next((c for c in (base, *(f"{base}-{n}" for n in range(2, 100))) if c not in taken),
                    f"{base}-{secrets.token_hex(3)}")
    await conn.execute(
        "UPDATE cappe_products SET slug = $1, updated_at = NOW() WHERE id = $2 AND site_id = $3",
        slug, product_id, site_id,
    )
    return slug


async def fetch_images(conn, product_ids: Iterable) -> dict:
    """{product_id: [{id, url, alt, sort_order}]} in order. Read-only."""
    ids = list(product_ids)
    if not ids:
        return {}
    rows = await conn.fetch(
        "SELECT id, product_id, url, alt, sort_order FROM cappe_product_images "
        "WHERE product_id = ANY($1::uuid[]) ORDER BY sort_order, created_at, id",
        ids,
    )
    out: dict = {}
    for r in rows:
        out.setdefault(r["product_id"], []).append(
            {"id": r["id"], "url": r["url"], "alt": r["alt"], "sort_order": r["sort_order"]}
        )
    return out


async def replace_images(conn, site_id: UUID, product_id: UUID, images) -> None:
    """A product's pictures become `images`, in that order (None = leave them),
    and the cover column follows the first."""
    if images is None:
        return
    if len(images) > MAX_IMAGES:
        raise HTTPException(status_code=422, detail=f"A product can have at most {MAX_IMAGES} pictures.")
    await conn.execute(
        "DELETE FROM cappe_product_images WHERE product_id = $1 AND site_id = $2", product_id, site_id,
    )
    for pos, img in enumerate(images):
        await conn.execute(
            "INSERT INTO cappe_product_images (site_id, product_id, url, alt, sort_order) "
            "VALUES ($1, $2, $3, $4, $5)",
            site_id, product_id, img.url, img.alt, pos,
        )
    await conn.execute(
        "UPDATE cappe_products SET image_url = $1, updated_at = NOW() WHERE id = $2 AND site_id = $3",
        images[0].url if images else None, product_id, site_id,
    )


async def set_cover(conn, site_id: UUID, product_id: UUID, image_url: Optional[str]) -> None:
    """A client that only knows the one cover column (the apps, Merlin) set it:
    the first picture becomes that one, the rest stay."""
    first = await conn.fetchrow(
        "SELECT id FROM cappe_product_images WHERE product_id = $1 AND site_id = $2 "
        "ORDER BY sort_order, created_at, id LIMIT 1",
        product_id, site_id,
    )
    if not image_url:
        if first:
            await conn.execute("DELETE FROM cappe_product_images WHERE id = $1", first["id"])
        return
    if first:
        await conn.execute("UPDATE cappe_product_images SET url = $1 WHERE id = $2", image_url, first["id"])
    else:
        await conn.execute(
            "INSERT INTO cappe_product_images (site_id, product_id, url, sort_order) VALUES ($1, $2, $3, 0)",
            site_id, product_id, image_url,
        )


# ── what the page says about a product ───────────────────────────────────────

def is_sold_out(product: dict, variants: list) -> bool:
    """The storefront's own rule (store.js `soldOut`): out itself, or every
    combination it sells is out."""
    if product.get("fulfillment") != "physical":
        return False
    inv = product.get("inventory")
    if inv is not None and inv <= 0:
        return True
    live = [v for v in variants or [] if v.get("status") == "active"]
    return bool(live) and all(v.get("inventory") is not None and v["inventory"] <= 0 for v in live)


def price_range(product: dict, variants: list, price_cents: int) -> tuple[int, int]:
    """(low, high) over the product's price and every live variant's own price."""
    prices = [price_cents] + [v["price_cents"] for v in variants or []
                              if v.get("status") == "active" and v.get("price_cents") is not None]
    return min(prices), max(prices)


def absolute(url: Optional[str], origin: str) -> Optional[str]:
    if not url:
        return None
    return url if url.lower().startswith(("http://", "https://")) else f"{origin}{url if url.startswith('/') else '/' + url}"


def product_ld(product: dict, *, images: list, variants: list, origin: str, url: str,
               price_cents: int, rating: Optional[dict] = None) -> str:
    """schema.org Product JSON-LD: what Google Shopping and rich results read.
    Absolute URLs only; one Offer, or an AggregateOffer when variants are
    priced differently."""
    cur = product.get("currency") or "USD"
    available = "https://schema.org/OutOfStock" if is_sold_out(product, variants) else "https://schema.org/InStock"
    low, high = price_range(product, variants, price_cents)
    if low == high:
        offers: dict[str, Any] = {"@type": "Offer", "price": f"{low / 100:.2f}", "priceCurrency": cur,
                                  "availability": available, "url": url}
    else:
        offers = {"@type": "AggregateOffer", "lowPrice": f"{low / 100:.2f}", "highPrice": f"{high / 100:.2f}",
                  "priceCurrency": cur, "offerCount": len([v for v in variants if v.get("status") == "active"]),
                  "availability": available, "url": url}
    if product.get("fulfillment") == "physical":
        offers["itemCondition"] = "https://schema.org/NewCondition"
    data: dict[str, Any] = {"@context": "https://schema.org", "@type": "Product", "name": product.get("name") or "",
                            "url": url, "offers": offers}
    pics = [a for a in (absolute(i.get("url"), origin) for i in images) if a]
    if pics:
        data["image"] = pics
    if product.get("description"):
        data["description"] = str(product["description"])[:5000]
    if product.get("sku"):
        data["sku"] = product["sku"]
    if product.get("gtin"):
        data["gtin"] = product["gtin"]
    if product.get("brand"):
        data["brand"] = {"@type": "Brand", "name": product["brand"]}
    if product.get("category"):
        data["category"] = product["category"]
    if rating and rating.get("count"):
        data["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": rating["avg"],
                                   "reviewCount": rating["count"]}
    # No raw "<", ">" or "&" from an owner's text inside the script element:
    # "</script>" would end it, and "<!--" + "<script" would keep the real end
    # tag from ending it. The escapes are still the same JSON.
    payload = (json.dumps(data, ensure_ascii=False)
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    return f'<script type="application/ld+json">{payload}</script>'
