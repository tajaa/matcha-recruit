"""Turn one fetched HTML page into the compact facts the agent can use.

Retail and review pages usually publish their product facts as schema.org
JSON-LD (`Product` with `offers` and `aggregateRating`) — far more reliable
than scraping visible text. The extractor prefers that, falls back to Open
Graph tags, and adds a bounded slice of visible text for everything else.
Output is DATA for the model, never instructions.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

MAX_TEXT_CHARS = 8_000
MAX_PRODUCTS = 3
MAX_REVIEWS = 5


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _types(node: dict) -> set[str]:
    return {str(t) for t in _as_list(node.get("@type"))}


def _walk_ld(node: Any):
    """Every dict in a JSON-LD blob, including @graph members and nesting."""
    if isinstance(node, list):
        for item in node:
            yield from _walk_ld(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement", "item"):
            if key in node:
                yield from _walk_ld(node[key])


def _image_urls(value: Any, base: str) -> list[str]:
    urls = []
    for item in _as_list(value):
        if isinstance(item, dict):
            item = item.get("url") or item.get("contentUrl")
        if isinstance(item, str) and item.strip():
            urls.append(urljoin(base, item.strip()))
    return urls[:4]


def _offers(value: Any, base: str) -> list[dict]:
    out = []
    for offer in _as_list(value):
        if not isinstance(offer, dict):
            continue
        # AggregateOffer carries its own nested offers list.
        if "offers" in offer and "AggregateOffer" in _types(offer):
            out.extend(_offers(offer["offers"], base))
            if offer.get("lowPrice") is not None:
                out.append({
                    "price": offer.get("lowPrice"),
                    "currency": offer.get("priceCurrency"),
                    "availability": None,
                    "url": urljoin(base, offer["url"]) if isinstance(offer.get("url"), str) else None,
                    "seller": None,
                })
            continue
        seller = offer.get("seller")
        out.append({
            "price": offer.get("price") or offer.get("lowPrice"),
            "currency": offer.get("priceCurrency"),
            "availability": str(offer.get("availability") or "").rsplit("/", 1)[-1] or None,
            "url": urljoin(base, offer["url"]) if isinstance(offer.get("url"), str) else None,
            "seller": seller.get("name") if isinstance(seller, dict) else None,
        })
    return out[:6]


def _product(node: dict, base: str) -> dict:
    rating = node.get("aggregateRating") if isinstance(node.get("aggregateRating"), dict) else {}
    brand = node.get("brand")
    reviews = []
    for review in _as_list(node.get("review"))[:MAX_REVIEWS]:
        if not isinstance(review, dict):
            continue
        body = str(review.get("reviewBody") or review.get("description") or "").strip()
        if not body:
            continue
        rr = review.get("reviewRating") if isinstance(review.get("reviewRating"), dict) else {}
        author = review.get("author")
        reviews.append({
            "body": body[:400],
            "rating": rr.get("ratingValue"),
            "author": author.get("name") if isinstance(author, dict) else (author if isinstance(author, str) else None),
        })
    return {
        "name": str(node.get("name") or "").strip()[:200],
        "brand": brand.get("name") if isinstance(brand, dict) else (brand if isinstance(brand, str) else None),
        "description": str(node.get("description") or "").strip()[:600],
        "images": _image_urls(node.get("image"), base),
        "rating": {
            "value": rating.get("ratingValue"),
            "count": rating.get("reviewCount") or rating.get("ratingCount"),
            "best": rating.get("bestRating") or 5,
        } if rating.get("ratingValue") is not None else None,
        "offers": _offers(node.get("offers"), base),
        "reviews": reviews,
    }


def extract_page(html: bytes, final_url: str) -> dict:
    """Compact, bounded page facts for the model."""
    soup = BeautifulSoup(html, "lxml")
    products: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            blob = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for node in _walk_ld(blob):
            if "Product" in _types(node) and len(products) < MAX_PRODUCTS:
                products.append(_product(node, final_url))

    def meta(*names: str) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return None

    og_image = meta("og:image", "og:image:url", "twitter:image")
    title = meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"]):
        tag.decompose()
    text = " ".join((soup.body or soup).get_text(" ", strip=True).split())

    return {
        "url": final_url,
        "title": (title or "")[:200],
        "description": (meta("og:description", "description") or "")[:500],
        "og_image": urljoin(final_url, og_image) if og_image else None,
        "products": products,
        "text": text[:MAX_TEXT_CHARS],
        "text_truncated": len(text) > MAX_TEXT_CHARS,
    }


def page_urls(page: dict) -> set[str]:
    """URLs a fetched page vouches for: itself plus its JSON-LD offer URLs."""
    urls = {page["url"]} if page.get("url") else set()
    for product in page.get("products") or []:
        for offer in product.get("offers") or []:
            if offer.get("url"):
                urls.add(offer["url"])
    return urls
