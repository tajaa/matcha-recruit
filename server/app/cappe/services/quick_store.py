"""An online store in one step (`POST /sites/quick-store`).

The onboarding wizard's "Online only" path: a name, a line about the store and
the first product, and the owner lands on a store that can go live in one tap.
Everything else (logo, shipping rates, payments, pages) comes later, from the
dashboard.

So the home page is built here rather than cloned from a template: a template
is full of "Replace this with…" copy, and this store may be published a minute
after it is made. It says only what the owner told us: their name, their line,
and their products.
"""
from typing import Any

from .policies import REQUIRED_FOR_PHYSICAL, starter

# Where an online store is listed in Discover until the owner says otherwise.
DIRECTORY_CATEGORY = "retail"


def home_blocks(name: str, tagline: str | None) -> list[dict[str, Any]]:
    """The store's home page: its name (with the owner's line) over its products."""
    hero: dict[str, Any] = {
        "type": "hero", "style": "centered", "heading": name,
        "cta": "Shop now", "ctaHref": "#shop",
    }
    if tagline and tagline.strip():
        hero["subheading"] = tagline.strip()
    return [hero, {"type": "store", "heading": "Shop"}]


def starter_policies() -> list[tuple[str, str]]:
    """`(kind, body)` for the policies a store selling parcels must publish,
    from our starter text. The owner is told to review them; they are a prompt
    to edit, not legal advice (services/policies.py)."""
    return [(kind, starter(kind)) for kind in REQUIRED_FOR_PHYSICAL]
