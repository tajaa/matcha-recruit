"""Plan → entitlement resolution for Cappe.

Cappe's analogue of matcha's `require_feature`. Before this, plan enforcement
was ad-hoc and inline (a `PREMIUM_PLANS` set in `design_gate`, a `_PLAN_SITE_LIMIT`
dict in `routes/sites.py`, a bare `plan != "pro"` in `routes/rider.py`), and the
storefront take rate was a single global env constant.

**`cappe_accounts.plan` stays the denormalized effective tier.** It is written
only by the subscription webhook and the admin override, so entitlement lookup
on the hot path is a dict read against a cached catalog — no extra query, and
every existing reader of `account.plan` keeps working untouched. The
subscription tables are the billing record, not the read path.

**Only the catalog is cached** (a handful of global rows, 60s TTL). Per-account
state is deliberately NOT cached: there is nothing to save, and an upgrade that
takes a minute to visibly apply generates support tickets.

**Failure is open, to today's behaviour.** If the catalog is unreadable — most
likely because the migration has not been applied yet — every account resolves
to `_LEGACY_FALLBACK`, which reproduces the pre-catalog world exactly: selling
allowed at `settings.cappe_platform_fee_bps`, all fulfillment types, the old
one-site free limit. A billing-config outage must not stop a merchant taking
money.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import HTTPException, status

from app.config import get_settings
from app.database import connection_or_direct

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _conn_ctx(conn=None):
    """Yield the caller's connection when it has one, else open a managed one.

    `connection_or_direct` takes no connection argument — it only chooses
    between the pool and a raw connection — so callers that already hold one
    need this passthrough to avoid opening a second.
    """
    if conn is not None:
        yield conn
    else:
        async with connection_or_direct() as active:
            yield active

CATALOG_CACHE_TTL_SECONDS = 60

ALL_FULFILLMENT = frozenset({"physical", "digital", "service", "booking"})

# Subscription statuses that still carry full entitlement. `trialing` is in the
# list because the $1/30-day intro IS a Stripe trial — the customer has paid and
# must not be gated. `past_due` is in the list because Stripe retries a failed
# card for days; dropping a merchant's storefront on the first retry failure
# would break a live business over a card that renews on Thursday. Access ends
# when Stripe moves the subscription to `unpaid`/`canceled`.
ENTITLED_SUBSCRIPTION_STATUSES = frozenset({"trialing", "active", "past_due"})

_catalog_cache: Optional[dict[str, dict]] = None
_catalog_cached_at: float = 0.0


@dataclass(frozen=True)
class Entitlements:
    """What an account may do. Resolved from its plan's catalog row."""

    plan_code: str
    plan_name: str
    can_sell: bool
    platform_fee_bps: int
    allowed_fulfillment: frozenset[str]
    site_limit: Optional[int]  # None = unlimited
    mailbox_quota_included: int
    premium_design: bool
    features: dict[str, Any] = field(default_factory=dict)

    def has(self, feature: str) -> bool:
        return bool(self.features.get(feature))


DEFAULT_PLATFORM_FEE_BPS = 200  # mirrors config.py's own default


def _fallback_fee_bps() -> int:
    """The global take rate, or the compiled-in default if settings are not
    loaded.

    This is the degraded path, so it must not be able to raise: `get_settings()`
    throws when `load_settings()` hasn't run, and a fallback that itself blows
    up would turn an unreadable billing catalog into a failed checkout — the
    exact outcome the fallback exists to prevent.
    """
    try:
        return get_settings().cappe_platform_fee_bps
    except Exception:  # noqa: BLE001
        return DEFAULT_PLATFORM_FEE_BPS


def _legacy_fallback(plan_code: str) -> Entitlements:
    """Pre-catalog behaviour, used when the catalog can't be read or the plan
    has no row. Permissive on purpose — see the module docstring."""
    return Entitlements(
        plan_code=plan_code or "free",
        plan_name=plan_code or "free",
        can_sell=True,
        platform_fee_bps=_fallback_fee_bps(),
        allowed_fulfillment=ALL_FULFILLMENT,
        site_limit=1 if plan_code == "free" else None,
        mailbox_quota_included=0,
        # Mirrors design_gate.PREMIUM_PLANS so a fallback can't silently revoke
        # premium design from an account that has it today.
        premium_design=str(plan_code or "").lower() in {"pro", "business", "creator"},
        features={"rider": str(plan_code or "").lower() in {"pro", "creator"}},
    )


def invalidate_catalog_cache() -> None:
    """Drop the cached catalog. Every admin write to plans/prices calls this so
    an edit is visible immediately rather than up to a TTL later."""
    global _catalog_cache, _catalog_cached_at
    _catalog_cache = None
    _catalog_cached_at = 0.0


async def get_catalog(*, conn=None, force: bool = False) -> dict[str, dict]:
    """The billing catalog keyed by product code, TTL-cached.

    Uses `connection_or_direct` (not `get_connection`) so this is safe to read
    from the pool-free Celery workers as well as from a request.
    """
    global _catalog_cache, _catalog_cached_at

    now = time.monotonic()
    if (
        not force
        and _catalog_cache is not None
        and (now - _catalog_cached_at) < CATALOG_CACHE_TTL_SECONDS
    ):
        return _catalog_cache

    try:
        async with _conn_ctx(conn) as active:
            rows = await active.fetch(
                """
                SELECT code, kind, name, status, can_sell, platform_fee_bps,
                       allowed_fulfillment, site_limit, mailbox_quota_included,
                       premium_design, features, unit_label, max_quantity,
                       sort_order, stripe_product_id
                  FROM cappe_billing_products
                """
            )
    except Exception as exc:  # noqa: BLE001
        # Most likely the migration has not been applied. Cache nothing so the
        # next call retries, and let callers fall back to legacy behaviour.
        logger.warning("cappe billing catalog unavailable, falling back: %s", exc)
        return {}

    catalog = {row["code"]: dict(row) for row in rows}
    _catalog_cache = catalog
    _catalog_cached_at = now
    return catalog


def _entitlements_from_row(row: dict) -> Entitlements:
    features = row.get("features") or {}
    if isinstance(features, str):  # asyncpg returns JSONB as str without a codec
        import json

        try:
            features = json.loads(features)
        except ValueError:
            features = {}
    return Entitlements(
        plan_code=row["code"],
        plan_name=row.get("name") or row["code"],
        can_sell=bool(row.get("can_sell")),
        platform_fee_bps=int(row.get("platform_fee_bps") or 0),
        allowed_fulfillment=frozenset(row.get("allowed_fulfillment") or ()),
        site_limit=row.get("site_limit"),
        mailbox_quota_included=int(row.get("mailbox_quota_included") or 0),
        premium_design=bool(row.get("premium_design")),
        features=features if isinstance(features, dict) else {},
    )


async def resolve_entitlements(plan_code: Optional[str], *, conn=None) -> Entitlements:
    """Entitlements for a plan code (i.e. `account.plan`)."""
    code = plan_code or "free"
    catalog = await get_catalog(conn=conn)
    row = catalog.get(code)
    if row is None or row.get("kind") != "plan":
        if catalog:
            # The catalog loaded but has no row for this plan. The FK on
            # cappe_accounts.plan should make this impossible; log loudly if it
            # ever happens rather than silently handing out a default.
            logger.warning("cappe plan %r missing from billing catalog", code)
        return _legacy_fallback(code)
    return _entitlements_from_row(row)


async def resolve_for_account(account, *, conn=None) -> Entitlements:
    """Convenience wrapper for a CappeAccount-shaped object."""
    return await resolve_entitlements(getattr(account, "plan", None), conn=conn)


# ── Take rate ─────────────────────────────────────────────────────────────

def fee_cents(amount_cents: int, bps: int) -> int:
    """The platform's cut of a sale, in cents (floored).

    Same arithmetic as the global `stripe_connect.platform_fee_cents` it
    replaces; the rate now comes from the plan rather than a env constant.
    """
    return max(0, (int(amount_cents) * int(bps)) // 10_000)


# ── Gates ─────────────────────────────────────────────────────────────────

def require_can_sell(ent: Entitlements) -> None:
    """402 unless this plan may take payments."""
    if not ent.can_sell:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Taking payments requires a paid plan.",
        )


def require_fulfillment(ent: Entitlements, fulfillment: Optional[str]) -> None:
    """403 unless this plan may sell that kind of thing.

    `fulfillment` is the existing `cappe_products.fulfillment` vocabulary, so
    the gate is data-driven off `allowed_fulfillment` rather than hardcoding a
    Creator-vs-Business branch.
    """
    value = (fulfillment or "physical").lower()
    if value not in ent.allowed_fulfillment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Your {ent.plan_name} plan can't sell {value} items. "
                "Upgrade to sell physical and digital products."
            ),
        )


async def mailbox_quota(account_id, *, conn=None) -> int:
    """Mailboxes this account may provision: the plan's included allowance plus
    any purchased add-on quantity.

    Read from `cappe_subscription_items`, which is rebuilt from Stripe's
    `items.data` on every subscription event — so the quantity here cannot drift
    from what the customer is actually being billed for.
    """
    catalog = await get_catalog(conn=conn)
    try:
        async with _conn_ctx(conn) as active:
            row = await active.fetchrow(
                """
                SELECT a.plan AS plan_code,
                       COALESCE(SUM(i.quantity) FILTER (
                           WHERE p.kind = 'addon' AND p.unit_label = 'mailbox'
                       ), 0) AS purchased
                  FROM cappe_accounts a
                  LEFT JOIN cappe_subscriptions s
                         ON s.account_id = a.id
                        AND s.status = ANY($2::text[])
                  LEFT JOIN cappe_subscription_items i ON i.subscription_id = s.id
                  LEFT JOIN cappe_billing_products p ON p.code = i.product_code
                 WHERE a.id = $1
                 GROUP BY a.plan
                """,
                account_id,
                list(ENTITLED_SUBSCRIPTION_STATUSES),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("mailbox quota lookup failed for %s: %s", account_id, exc)
        return 0

    if row is None:
        return 0
    plan_row = catalog.get(row["plan_code"]) or {}
    included = int(plan_row.get("mailbox_quota_included") or 0)
    return included + int(row["purchased"] or 0)
