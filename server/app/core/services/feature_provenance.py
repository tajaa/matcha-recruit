"""Company feature provenance — audit logging + classification.

Two independent halves:

- `record_feature_changes` — call this at a write site right after diffing an
  old/new `enabled_features` dict, so `company_feature_audit_log` fills in
  going forward. Never let a failed insert fail the write it's observing —
  every call site wraps it in try/except-log.
- `feature_provenance` — given a company's current state, classify each
  currently-ENABLED effective feature into where it came from. See the
  ordered rules below; first match wins, and rule order encodes that an
  entitlement (tier/add-on/product) outranks mutation history (audit log) —
  a webhook may have written a flag a tier also grants, and "you own this"
  is the more useful answer than "someone flipped it".

Plus two small DISPLAY helpers so an admin page can show "what plan is this
company on, and what add-ons on top of it" instead of forcing that answer to
be reverse-engineered from a flat toggle grid: `resolve_plan` (builtin tier /
custom product / unknown, from signup_source) and `resolve_addons` (active
LiteAddon purchases). Both are pure and read-only over already-fetched data —
neither one grants or gates anything; `merge_company_features` +
`TIER_REQUIRED_FEATURES` remain the only source of truth for what's actually
enabled.

Plus `load_grants`/`set_grant`/`clear_grant` — a SEPARATE question from
provenance. Provenance answers WHERE a flag came from; a grant answers WHY an
admin gave it (comped / invoiced / trial / internal), for the features
provenance classifies as `admin_grant` or `audit` (source=admin_toggle).

All DB-touching helpers here are plain async functions over an already-open
connection — no pool assumptions, callable from request handlers and (if ever
needed) Celery.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from app.core.feature_flags import (
    ALL_FEATURES,
    TIER_REQUIRED_FEATURES,
    TIER_SIGNUP_PRESETS,
    merge_company_features,
)
from app.core.services.lite_addons import ADDON_PACK_PREFIX, addon_for_pack_id
from app.core.services.product_definitions import (
    PRODUCT_PACK_PREFIX,
    SIGNUP_SOURCE_PREFIX,
    product_for_pack_id,
)

logger = logging.getLogger(__name__)

VALID_SOURCES = frozenset({"admin_toggle", "tier_change", "product_sync", "stripe_webhook"})


async def record_feature_changes(
    conn,
    company_id: UUID,
    old_features: dict[str, Any],
    new_features: dict[str, Any],
    source: str,
    actor_user_id: Optional[UUID] = None,
) -> None:
    """Insert one audit row per key whose boolean value actually changed.

    Best-effort: logs and swallows its own errors rather than raising, so a
    broken audit insert can never fail the enabled_features write it's
    observing. Callers should still call this INSIDE the same transaction as
    the write when one is already open, so a rolled-back write doesn't leave
    an orphaned audit row.
    """
    if source not in VALID_SOURCES:
        logger.error("record_feature_changes: unknown source %r, skipping audit", source)
        return
    try:
        changed = [
            (key, bool(old_features.get(key, False)), bool(new_features.get(key, False)))
            for key in set(old_features) | set(new_features)
            if bool(old_features.get(key, False)) != bool(new_features.get(key, False))
        ]
        if not changed:
            return
        await conn.executemany(
            """
            INSERT INTO company_feature_audit_log
                (company_id, feature, old_value, new_value, source, actor_user_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [(company_id, key, old, new, source, actor_user_id) for key, old, new in changed],
        )
    except Exception:
        logger.exception(
            "record_feature_changes failed for company=%s source=%s (write itself is unaffected)",
            company_id, source,
        )


def _active_pack_ids(subscription_rows: list) -> list[str]:
    return [r["pack_id"] for r in subscription_rows if r["status"] == "active" and r["pack_id"]]


async def load_active_packs(conn, company_id: UUID) -> list[str]:
    """The company's currently-active mw_subscriptions pack_ids. Fetched once
    by the route and handed to feature_provenance/resolve_addons so a single
    page load doesn't query mw_subscriptions twice.
    """
    sub_rows = await conn.fetch(
        "SELECT pack_id, status FROM mw_subscriptions WHERE company_id = $1",
        company_id,
    )
    return _active_pack_ids(sub_rows)


def resolve_plan(signup_source: Optional[str], products_by_slug: dict[str, Any]) -> dict[str, Any]:
    """What plan/tier a company is on, for display — NOT for gating (that's
    still merge_company_features + TIER_REQUIRED_FEATURES). `kind` is one of
    builtin / custom_product / unknown (a company with no recognizable
    signup_source — legacy row or one the tier constants don't name).
    """
    from app.core.feature_flags import BUILTIN_TIER_META

    if signup_source and signup_source.startswith(SIGNUP_SOURCE_PREFIX):
        slug = signup_source[len(SIGNUP_SOURCE_PREFIX):]
        product = products_by_slug.get(slug)
        return {
            "kind": "custom_product",
            "slug": slug,
            "label": product.name if product else slug,
        }
    meta = BUILTIN_TIER_META.get(signup_source or "")
    if meta:
        return {"kind": "builtin", "slug": signup_source, "label": meta["label"]}
    return {"kind": "unknown", "slug": signup_source, "label": signup_source or "Unknown"}


def resolve_addons(active_packs: list[str]) -> list[dict[str, str]]:
    """Purchased add-ons currently active for a company, for display."""
    out: list[dict[str, str]] = []
    for pack_id in active_packs:
        if pack_id.startswith(ADDON_PACK_PREFIX):
            addon = addon_for_pack_id(pack_id)
            if addon:
                out.append({"key": addon.key, "name": addon.name, "feature": addon.feature})
    return out


async def feature_provenance(
    conn,
    company_row: Any,
    products_by_slug: dict[str, Any],
    active_packs: list[str],
) -> dict[str, dict[str, Any]]:
    """Classify every currently-enabled effective feature for one company.

    `company_row` needs `id`, `enabled_features`, `signup_source`.
    `products_by_slug` is a pre-fetched `{slug: ProductDefinition}` map (the
    caller already has the full product list loaded for /admin/products-style
    pages; fetching it per company here would be N+1). `active_packs` comes
    from `load_active_packs` — fetched once by the caller and shared with
    `resolve_addons` so a page load queries mw_subscriptions only once.

    Returns `{feature_key: {"bucket": ..., "detail": ...}}` for every feature
    that reads as enabled via `merge_company_features`. Buckets, in match
    order: tier_forced, addon, custom_product, paid_gate, tier_preset, audit,
    admin_grant. `admin_grant` is the fallback — nothing else explains the
    flag, and the only way that happens in this codebase is an admin (or
    broker, at company creation) turning it on directly: comped, invoiced
    separately, or a pre-audit-log toggle. It is NOT "unknown" in the sense of
    unexplainable — it just predates `company_feature_audit_log` or a write
    path this function doesn't (yet) resolve, so the specific actor/timestamp
    is unrecorded. See `load_grants`/`set_grant` for recording WHY (comped vs
    invoiced vs trial vs internal) once an admin classifies it.
    """
    signup_source = company_row["signup_source"]
    effective = merge_company_features(company_row["enabled_features"], signup_source)
    enabled_keys = [k for k in ALL_FEATURES if effective.get(k)]

    active_addon_flags: set[str] = set()
    for pack_id in active_packs:
        if pack_id.startswith(ADDON_PACK_PREFIX):
            addon = addon_for_pack_id(pack_id)
            if addon:
                active_addon_flags.add(addon.feature)

    active_product_features: set[str] = set()
    for pack_id in active_packs:
        if pack_id.startswith(PRODUCT_PACK_PREFIX):
            slug = product_for_pack_id(pack_id)
            product = products_by_slug.get(slug)
            if product:
                active_product_features |= {k for k, v in product.features.items() if v}

    overlay = TIER_REQUIRED_FEATURES.get(signup_source, {})
    preset = TIER_SIGNUP_PRESETS.get(signup_source, {})
    gate_flag = _stripe_gate_flag_for(signup_source)

    audit_rows = await conn.fetch(
        """
        SELECT DISTINCT ON (feature) feature, source, actor_user_id, created_at
        FROM company_feature_audit_log
        WHERE company_id = $1 AND new_value = true
        ORDER BY feature, created_at DESC
        """,
        company_row["id"],
    )
    latest_audit = {r["feature"]: r for r in audit_rows}

    result: dict[str, dict[str, Any]] = {}
    for key in enabled_keys:
        if overlay.get(key) is True:
            result[key] = {"bucket": "tier_forced", "detail": signup_source}
        elif key in active_addon_flags:
            result[key] = {"bucket": "addon", "detail": None}
        elif key in active_product_features:
            result[key] = {"bucket": "custom_product", "detail": None}
        elif gate_flag and key == gate_flag:
            result[key] = {"bucket": "paid_gate", "detail": signup_source}
        elif preset.get(key) is True:
            result[key] = {"bucket": "tier_preset", "detail": signup_source}
        elif key in latest_audit:
            row = latest_audit[key]
            result[key] = {
                "bucket": "audit",
                "detail": {
                    "source": row["source"],
                    "actor_user_id": str(row["actor_user_id"]) if row["actor_user_id"] else None,
                    "created_at": row["created_at"].isoformat(),
                },
            }
        else:
            result[key] = {"bucket": "admin_grant", "detail": None}
    return result


def _stripe_gate_flag_for(signup_source: Optional[str]) -> Optional[str]:
    from app.core.feature_flags import BUILTIN_TIER_META
    return BUILTIN_TIER_META.get(signup_source or "", {}).get("stripe_gate_flag")


# ── Grant classification — WHY an admin-granted feature was given ───────────
#
# Distinct question from provenance's WHERE-did-this-come-from: an
# `admin_grant` (or even an `audit`-sourced admin_toggle) bucket tells you an
# admin turned it on, not whether the company was billed for it. This table
# is deliberately per (company, feature), not a free-text log — one current
# classification, overwritten on re-classify, not a history of every note.

GRANT_TYPES = frozenset({"comped", "invoiced", "trial", "internal"})


async def load_grants(conn, company_id: UUID) -> dict[str, dict[str, Any]]:
    """`{feature: {"grant_type": ..., "note": ..., "updated_at": ...}}` for
    every feature an admin has classified for this company."""
    rows = await conn.fetch(
        "SELECT feature, grant_type, note, updated_at FROM company_feature_grants WHERE company_id = $1",
        company_id,
    )
    return {
        r["feature"]: {
            "grant_type": r["grant_type"],
            "note": r["note"],
            "updated_at": r["updated_at"].isoformat(),
        }
        for r in rows
    }


async def set_grant(
    conn, company_id: UUID, feature: str, grant_type: str,
    note: Optional[str] = None, actor_user_id: Optional[UUID] = None,
) -> None:
    if feature not in ALL_FEATURES:
        raise ValueError(f"Unknown feature: {feature}")
    if grant_type not in GRANT_TYPES:
        raise ValueError(f"Unknown grant_type: {grant_type}. Valid: {', '.join(sorted(GRANT_TYPES))}")
    await conn.execute(
        """
        INSERT INTO company_feature_grants (company_id, feature, grant_type, note, updated_by, updated_at)
        VALUES ($1, $2, $3, $4, $5, now())
        ON CONFLICT (company_id, feature) DO UPDATE
            SET grant_type = EXCLUDED.grant_type,
                note = EXCLUDED.note,
                updated_by = EXCLUDED.updated_by,
                updated_at = now()
        """,
        company_id, feature, grant_type, note, actor_user_id,
    )


async def clear_grant(conn, company_id: UUID, feature: str) -> None:
    await conn.execute(
        "DELETE FROM company_feature_grants WHERE company_id = $1 AND feature = $2",
        company_id, feature,
    )
