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
MAX_JOBS = 2
# In the general page view (the model's fetch_page output) a job description
# stays short; `job_postings` gives the job search the whole thing.
MAX_JOB_DESCRIPTION = 3_000
MAX_FULL_JOB_DESCRIPTION = 20_000


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _types(node: dict) -> set[str]:
    return {str(t) for t in _as_list(node.get("@type"))}


_MAX_LD_NODES = 2000
_MAX_LD_DEPTH = 40


def _walk_ld(node: Any):
    """Every dict in a JSON-LD blob, including @graph members and nesting.

    Iterative with a depth and node cap: JSON-LD is attacker-controlled, and a
    recursive walk over absurd nesting raises RecursionError.
    """
    stack: list[tuple[Any, int]] = [(node, 0)]
    seen = 0
    while stack and seen < _MAX_LD_NODES:
        current, depth = stack.pop()
        if depth > _MAX_LD_DEPTH:
            continue
        if isinstance(current, list):
            stack.extend((item, depth + 1) for item in reversed(current))
        elif isinstance(current, dict):
            seen += 1
            yield current
            for key in ("item", "itemListElement", "mainEntity", "@graph"):
                if key in current:
                    stack.append((current[key], depth + 1))


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


def plain_text(value: Any, limit: int) -> str:
    """Text from a field that may hold HTML, one line per block, at most `limit`."""
    raw = str(value or "")
    if "<" in raw:
        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        raw = soup.get_text("\n", strip=True)
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    return "\n".join(line for line in lines if line)[:limit]


def _scalar(value: Any, limit: int = 24) -> str | int | float | None:
    """A number, or a short string; anything else (a nested object a page made
    up to smuggle text into the model's input) is dropped."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and value.strip():
        return value.strip()[:limit]
    return None


def _salary(raw: Any) -> dict | None:
    """schema.org `baseSalary`, reduced to the fields pay is read from."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {"currency": _scalar(raw.get("currency"), 8)}
    value = raw.get("value")
    if isinstance(value, dict):
        out["value"] = {key: _scalar(value.get(key)) for key in ("minValue", "maxValue", "value", "unitText")
                        if _scalar(value.get(key)) is not None}
    elif _scalar(value) is not None:
        out["value"] = _scalar(value)
        out["unitText"] = _scalar(raw.get("unitText"))
    else:
        return None
    return out


def _address(value: Any) -> str:
    parts = []
    for place in _as_list(value)[:3]:
        if not isinstance(place, dict):
            continue
        address = place.get("address") if isinstance(place.get("address"), dict) else place
        bits = [str(address.get(k) or "").strip() for k in
                ("addressLocality", "addressRegion", "addressCountry")]
        country = address.get("addressCountry")
        if isinstance(country, dict):
            bits[2] = str(country.get("name") or "").strip()
        text = ", ".join(b for b in bits if b)
        if text:
            parts.append(text)
    return "; ".join(parts)[:200]


def _job_posting(node: dict, base: str, description_limit: int = MAX_JOB_DESCRIPTION) -> dict:
    """schema.org JobPosting: the facts a job search needs, pay included."""
    org = node.get("hiringOrganization")
    salary = _salary(node.get("baseSalary"))
    location_type = " ".join(str(t) for t in _as_list(node.get("jobLocationType")))
    url = node.get("url")
    return {
        "title": str(node.get("title") or "").strip()[:200],
        "company": (org.get("name") if isinstance(org, dict) else org if isinstance(org, str) else "") or "",
        "location": _address(node.get("jobLocation")),
        "remote": "TELECOMMUTE" in location_type.upper(),
        "base_salary": salary,
        "date_posted": str(node.get("datePosted") or "")[:40] or None,
        "valid_through": str(node.get("validThrough") or "")[:40] or None,
        "employment_type": " ".join(str(t) for t in _as_list(node.get("employmentType")))[:80] or None,
        "url": urljoin(base, url) if isinstance(url, str) else None,
        "description": plain_text(node.get("description"), description_limit),
    }


def _ld_nodes(soup: BeautifulSoup):
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            blob = json.loads(raw)
        except (ValueError, TypeError, RecursionError):
            continue
        yield from _walk_ld(blob)


def job_postings(html: bytes, final_url: str) -> list[dict]:
    """Every schema.org JobPosting on the page (up to MAX_JOBS), full description."""
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for node in _ld_nodes(soup):
        if "JobPosting" in _types(node):
            jobs.append(_job_posting(node, final_url, MAX_FULL_JOB_DESCRIPTION))
            if len(jobs) >= MAX_JOBS:
                break
    return jobs


def extract_page(html: bytes, final_url: str) -> dict:
    """Compact, bounded page facts for the model."""
    soup = BeautifulSoup(html, "lxml")
    products: list[dict] = []
    jobs: list[dict] = []
    for node in _ld_nodes(soup):
        if "Product" in _types(node) and len(products) < MAX_PRODUCTS:
            products.append(_product(node, final_url))
        elif "JobPosting" in _types(node) and len(jobs) < MAX_JOBS:
            jobs.append(_job_posting(node, final_url))

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

    page = {
        "url": final_url,
        "title": (title or "")[:200],
        "description": (meta("og:description", "description") or "")[:500],
        "og_image": urljoin(final_url, og_image) if og_image else None,
        "products": products,
        "text": text[:MAX_TEXT_CHARS],
        "text_truncated": len(text) > MAX_TEXT_CHARS,
    }
    # Only when the page has one, so product pages keep their exact shape.
    if jobs:
        page["jobs"] = jobs
    return page


def page_urls(page: dict) -> set[str]:
    """URLs a fetched page vouches for: itself plus its JSON-LD offer URLs."""
    urls = {page["url"]} if page.get("url") else set()
    for product in page.get("products") or []:
        for offer in product.get("offers") or []:
            if offer.get("url"):
                urls.add(offer["url"])
    return urls
