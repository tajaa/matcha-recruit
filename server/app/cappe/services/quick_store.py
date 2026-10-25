"""Draft online stores: choose a look now, review the details before launch."""
from typing import Any

from .site_templates import clone_structure, get_template

DIRECTORY_CATEGORY = "retail"
DEFAULT_TEMPLATE = "online-studio"


def is_store_template(slug: Any) -> bool:
    template = get_template(slug)
    return template is not None and "online-store" in template.tags


def store_structure(name: str, tagline: str | None, slug: str, plan: str):
    template = get_template(slug)
    if not is_store_template(slug):
        raise ValueError("Choose an online-store starter template.")
    theme, pages = clone_structure(template, business_name=name, plan=plan)
    hero = pages[0]["content"]["blocks"][0]
    if tagline and tagline.strip():
        hero["subheading"] = tagline.strip()
    return theme, pages


def home_blocks(name: str, tagline: str | None) -> list[dict[str, Any]]:
    """The default starter's blocks; retained for callers using this helper."""
    return store_structure(name, tagline, DEFAULT_TEMPLATE, "free")[1][0]["content"]["blocks"]


def sample_products() -> list[dict]:
    """Illustrative cards only. Never inserted as products or exposed to shoppers."""
    return [{"name": name, "price_cents": price, "currency": "USD", "image_url": None}
            for name, price in (("Your first product", 2400), ("Your next product", 3800), ("A new favourite", 1800))]
