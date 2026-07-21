"""Admin-composable product definitions — the /admin/products builder.

A product row is a sellable package: a set of feature flags, one paid gate
flag, a pricing model, and an optional nav ordering. Tenants who sign up
through /p/<slug>/signup get `signup_source = 'product:<slug>'`.

Grants are MATERIALIZED (written into companies.enabled_features) rather than
overlaid at read time — `merge_company_features` is pure + sync and runs in
the pool-free Celery workers, so a DB-consulting overlay would need a cache on
the hot path of every request. Product edits therefore don't retro-grant;
POST /admin/products/{id}/sync-tenants re-materializes deliberately.

`features` is validated against ALLOWED_PRODUCT_FEATURES on every write: it is
the authorization whitelist for which enabled_features keys the signup +
billing paths may touch (same defense-in-depth rule as services/lite_addons.py
— never a metadata-supplied flag name).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from ..feature_flags import DEFAULT_COMPANY_FEATURES

SIGNUP_SOURCE_PREFIX = "product:"

# mw_subscriptions.pack_id for a custom-product sub: prefix + slug.
PRODUCT_PACK_PREFIX = "product:"

PRICING_MODELS = ("per_seat", "block", "flat", "free", "contact_sales")

# Models that require a Stripe checkout before the gate flag flips.
PAID_PRICING_MODELS = ("per_seat", "block", "flat")

STATUSES = ("draft", "published", "archived")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")

# signup_source values already in use by the hardcoded products — a custom
# product may not claim one even though the 'product:' prefix would keep them
# apart, because the slug also shows up in URLs and admin copy.
RESERVED_SLUGS = frozenset(
    {
        "matcha_lite",
        "matcha_lite_essentials",
        "matcha_x",
        "matcha_compliance",
        "resources_free",
        "ir_only_self_serve",
        "bespoke",
        "invite",
        "broker",
    }
)

# `incidents` and `employees` are not in DEFAULT_COMPANY_FEATURES (they're
# flipped on by tier-specific flows), but they are the two most sellable flags
# in the catalog — admit them explicitly.
ALLOWED_PRODUCT_FEATURES: frozenset[str] = frozenset(DEFAULT_COMPANY_FEATURES) | {
    "incidents",
    "employees",
}


class ProductDefinitionError(ValueError):
    """Invalid product definition — surfaced as a 400 by the routes."""


@dataclass
class ProductDefinition:
    id: str
    slug: str
    name: str
    description: str
    features: dict[str, bool]
    gate_feature: Optional[str]
    pricing_model: str
    price_cents: Optional[int]
    block_size: Optional[int]
    min_headcount: int
    max_headcount: int
    nav: Optional[list[dict[str, Any]]]
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None

    @property
    def signup_source(self) -> str:
        return SIGNUP_SOURCE_PREFIX + self.slug

    @property
    def pack_id(self) -> str:
        return PRODUCT_PACK_PREFIX + self.slug

    @property
    def is_paid(self) -> bool:
        return self.pricing_model in PAID_PRICING_MODELS

    @property
    def activates_on_signup(self) -> bool:
        """Only a genuinely free product hands out its features at signup.

        `contact_sales` is NOT free — it is a sales-led product with no
        self-serve payment path, so it stays pending until an admin runs
        POST /admin/products/{id}/activate-tenant.
        """
        return self.pricing_model == "free"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "features": self.features,
            "gate_feature": self.gate_feature,
            "pricing_model": self.pricing_model,
            "price_cents": self.price_cents,
            "block_size": self.block_size,
            "min_headcount": self.min_headcount,
            "max_headcount": self.max_headcount,
            "nav": self.nav,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }

    def public_dict(self) -> dict[str, Any]:
        """Shape served to the (unauthenticated) signup page."""
        return {
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "features": [k for k, v in self.features.items() if v],
            "gate_feature": self.gate_feature,
            "pricing_model": self.pricing_model,
            "price_cents": self.price_cents,
            "block_size": self.block_size,
            "min_headcount": self.min_headcount,
            "max_headcount": self.max_headcount,
            "nav": self.nav,
        }


def _coerce_json(value: Any, fallback):
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def _iso(row, key: str) -> Optional[str]:
    if key not in row.keys() or row[key] is None:
        return None
    return row[key].isoformat()


def row_to_product(row) -> ProductDefinition:
    features = _coerce_json(row["features"], {})
    nav = _coerce_json(row["nav"], None)
    return ProductDefinition(
        id=str(row["id"]),
        slug=row["slug"],
        name=row["name"],
        description=row["description"] or "",
        features={k: bool(v) for k, v in (features or {}).items()},
        gate_feature=row["gate_feature"],
        pricing_model=row["pricing_model"],
        price_cents=row["price_cents"],
        block_size=row["block_size"],
        min_headcount=row["min_headcount"],
        max_headcount=row["max_headcount"],
        nav=nav if isinstance(nav, list) else None,
        status=row["status"],
        created_at=_iso(row, "created_at"),
        updated_at=_iso(row, "updated_at"),
        updated_by=row["updated_by"] if "updated_by" in row.keys() else None,
    )


SELECT_COLUMNS = """
    id, slug, name, description, features, gate_feature, pricing_model,
    price_cents, block_size, min_headcount, max_headcount, nav, status,
    created_at, updated_at, updated_by
"""


async def get_product_by_slug(
    conn, slug: str, published_only: bool = True
) -> Optional[ProductDefinition]:
    query = f"SELECT {SELECT_COLUMNS} FROM product_definitions WHERE slug = $1"
    if published_only:
        query += " AND status = 'published'"
    row = await conn.fetchrow(query, slug)
    return row_to_product(row) if row else None


async def get_product_by_signup_source(
    conn, signup_source: Optional[str], published_only: bool = True
) -> Optional[ProductDefinition]:
    """Resolve a company's signup_source back to its product, if it has one."""
    if not signup_source or not signup_source.startswith(SIGNUP_SOURCE_PREFIX):
        return None
    return await get_product_by_slug(
        conn, signup_source[len(SIGNUP_SOURCE_PREFIX):], published_only=published_only
    )


# ── validation ──────────────────────────────────────────────────────────────


def validate_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise ProductDefinitionError(
            "Slug must be 3-40 chars, lowercase letters/numbers/hyphens, starting with a letter or number"
        )
    if slug in RESERVED_SLUGS:
        raise ProductDefinitionError(f"'{slug}' is reserved by an existing product")
    return slug


def validate_features(features: Any) -> dict[str, bool]:
    if not isinstance(features, dict) or not features:
        raise ProductDefinitionError("Select at least one feature")
    unknown = sorted(set(features) - ALLOWED_PRODUCT_FEATURES)
    if unknown:
        raise ProductDefinitionError(f"Unknown feature flag(s): {', '.join(unknown)}")
    cleaned = {k: bool(v) for k, v in features.items()}
    if not any(cleaned.values()):
        raise ProductDefinitionError("Select at least one enabled feature")
    return cleaned


def validate_pricing(
    pricing_model: str,
    price_cents: Optional[int],
    block_size: Optional[int],
    min_headcount: int,
    max_headcount: int,
) -> None:
    if pricing_model not in PRICING_MODELS:
        raise ProductDefinitionError(
            f"Unknown pricing_model — must be one of {', '.join(PRICING_MODELS)}"
        )
    if pricing_model in PAID_PRICING_MODELS:
        if not price_cents or price_cents <= 0:
            raise ProductDefinitionError("Priced products need a price above zero")
    if pricing_model == "block" and (not block_size or block_size <= 0):
        raise ProductDefinitionError("Block pricing needs a block size above zero")
    if min_headcount < 1:
        raise ProductDefinitionError("Minimum headcount must be at least 1")
    if max_headcount < min_headcount:
        raise ProductDefinitionError("Maximum headcount must be at least the minimum")


def validate_gate_feature(
    gate_feature: Optional[str], features: dict[str, bool], pricing_model: str
) -> Optional[str]:
    """A paid product needs exactly one gate flag, and it must be one it grants.

    The gate is what the pending sidebar checks and what the Stripe webhook
    flips — a gate outside the product's own grants would leave a paid tenant
    permanently pending.
    """
    if pricing_model not in PAID_PRICING_MODELS:
        return None
    if not gate_feature:
        raise ProductDefinitionError("Priced products need a gate feature")
    if not features.get(gate_feature):
        raise ProductDefinitionError(
            "The gate feature must be one of the features this product enables"
        )
    return gate_feature


def validate_nav(nav: Any, features: dict[str, bool]) -> Optional[list[dict[str, Any]]]:
    """Nav is an ordering over the product's own enabled features."""
    if nav is None:
        return None
    if not isinstance(nav, list):
        raise ProductDefinitionError("Nav must be a list")
    cleaned: list[dict[str, Any]] = []
    for entry in nav:
        if not isinstance(entry, dict):
            raise ProductDefinitionError("Each nav entry must be an object")
        feature = entry.get("feature")
        if not feature or not features.get(feature):
            raise ProductDefinitionError(
                f"Nav entry '{feature}' is not an enabled feature of this product"
            )
        item: dict[str, Any] = {"feature": feature}
        label = (entry.get("label") or "").strip()
        if label:
            item["label"] = label[:60]
        cleaned.append(item)
    return cleaned


# ── pricing + materialization ───────────────────────────────────────────────


def compute_product_price_cents(
    product: ProductDefinition, headcount: int
) -> Optional[int]:
    """Monthly price in cents, or None when the product isn't Stripe-billed.

    Raises ProductDefinitionError when headcount is outside the configured
    range so the caller can surface a "contact us" message (mirrors
    matcha_lite_pricing.compute_matcha_lite_price_cents returning None, but
    typed so an out-of-range headcount can't be confused with a free product).
    """
    if product.pricing_model not in PAID_PRICING_MODELS:
        return None
    if headcount < product.min_headcount:
        raise ProductDefinitionError(
            f"Headcount under {product.min_headcount} — please contact us for pricing"
        )
    if headcount > product.max_headcount:
        raise ProductDefinitionError(
            f"Headcount over {product.max_headcount} — please contact us for pricing"
        )

    price = int(product.price_cents or 0)
    if product.pricing_model == "flat":
        return price
    if product.pricing_model == "per_seat":
        return price * headcount
    # block
    block_size = int(product.block_size or 1)
    return math.ceil(headcount / block_size) * price


def materialize_features(product: ProductDefinition) -> dict[str, bool]:
    """The company's full enabled_features shape for an ACTIVE tenant.

    Every default flag is written explicitly False and then the product's own
    grants overlay it — same full-stomp convention as
    admin/_shared.py:_TIER_FEATURE_PRESETS, so nothing hydrates back on via
    DEFAULT_COMPANY_FEATURES in merge_company_features.
    """
    features = {k: False for k in DEFAULT_COMPANY_FEATURES}
    features["incidents"] = False
    features["employees"] = False
    for key, value in product.features.items():
        features[key] = bool(value)
    return features


def pending_features(product: ProductDefinition) -> dict[str, bool]:
    """Feature shape for a tenant that has registered but not paid.

    Everything off — including the grants — so a company can't use the product
    before the gate flips. Free/contact-sales products never sit here.
    """
    features = {k: False for k in DEFAULT_COMPANY_FEATURES}
    features["incidents"] = False
    features["employees"] = False
    return features


def is_tenant_activated(product: ProductDefinition, stored_features: Any) -> bool:
    """Whether a company on this product has been activated (vs pending).

    Priced products have a gate flag, so that decides. `contact_sales` has no
    gate (validate_gate_feature clears it for non-paid models) — there the
    tell is whether the admin's activate-tenant materialization has run, i.e.
    whether ANY granted feature is on (pending_features writes all-off).
    `free` products activate at signup, so a signup IS an activation.

    This is the single pending/active predicate — sync-tenants and the admin
    tenant counts both use it. Getting it wrong in sync-tenants is a free
    activation: a pending contact_sales tenant that isn't skipped gets the
    full feature set without the admin ever approving it.
    """
    stored = stored_features
    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except json.JSONDecodeError:
            stored = {}
    stored = stored if isinstance(stored, dict) else {}

    if product.gate_feature:
        return bool(stored.get(product.gate_feature))
    if product.pricing_model == "contact_sales":
        return any(stored.get(key) for key, value in product.features.items() if value)
    return True


def product_for_pack_id(pack_id: str) -> Optional[str]:
    """Resolve an mw_subscriptions.pack_id back to a product slug, if any."""
    if not pack_id or not pack_id.startswith(PRODUCT_PACK_PREFIX):
        return None
    return pack_id[len(PRODUCT_PACK_PREFIX):] or None
