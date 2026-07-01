"""Matcha Lite add-on registry.

Single server-side source of truth for the add-ons a Lite-family company can
self-serve purchase. Each add-on is its own Stripe subscription (the repo's
only multi-purchase precedent — no multi-item subscription machinery exists);
the `checkout.session.completed` / `customer.subscription.deleted` webhook
branches resolve the purchased add-on through this registry and flip exactly
`LiteAddon.feature` — NEVER a metadata-supplied flag name. That makes this
dict the authorization whitelist for which `enabled_features` keys billing is
allowed to touch (defense-in-depth on top of Stripe signature verification).

Pricing lives in `matcha_lite_pricing` rows keyed by `product_code`
(block_size=1 ⇒ straight per-employee-per-month), admin-editable at
/admin/matcha-lite-pricing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LiteAddon:
    key: str
    # matcha_lite_pricing.product_code carrying this add-on's PEPM price.
    product_code: str
    # The enabled_features flag the webhook flips on purchase / off on cancel.
    feature: str
    name: str
    description: str
    # signup_sources that may buy this add-on.
    allowed_sources: tuple[str, ...]
    # Merged feature flags the company must already have (tier fit) — e.g.
    # HRIS sync is useless without an employee roster.
    requires_features: tuple[str, ...] = ()


LITE_FAMILY_SOURCES: tuple[str, ...] = ("matcha_lite", "matcha_lite_essentials")

LITE_ADDONS: dict[str, LiteAddon] = {
    "voice_intake": LiteAddon(
        key="voice_intake",
        product_code="addon_voice_intake",
        feature="ir_voice_intake",
        name="Voice Incident Intake",
        description=(
            "Dictate incident reports — a spoken account is transcribed and "
            "prefills the incident form for review before submitting."
        ),
        allowed_sources=LITE_FAMILY_SOURCES,
    ),
    "hris_sync": LiteAddon(
        key="hris_sync",
        product_code="addon_hris_sync",
        # hris_finch = the unified Finch API (Rippling, BambooHR, ADP, …) — one
        # flag lights up every supported provider. hris_gusto (single-provider
        # direct OAuth) and hris_deductions (write-back) are NOT granted.
        feature="hris_finch",
        name="HRIS Sync",
        description=(
            "Keep your employee roster in sync automatically from your HRIS "
            "(Rippling, BambooHR, ADP, QuickBooks and more via Finch)."
        ),
        allowed_sources=("matcha_lite",),
        requires_features=("employees",),
    ),
    "handbook_watch": LiteAddon(
        key="handbook_watch",
        product_code="addon_handbook_watch",
        feature="handbook_watch",
        name="Handbook Watch",
        description=(
            "We continuously re-check your handbook against current law and "
            "alert you with proposed updates when requirements change."
        ),
        allowed_sources=LITE_FAMILY_SOURCES,
        requires_features=("handbooks",),
    ),
}

# mw_subscriptions.pack_id prefix for add-on subs: pack_id = prefix + addon key.
ADDON_PACK_PREFIX = "matcha_lite_addon_"


def addon_pack_id(key: str) -> str:
    return ADDON_PACK_PREFIX + key


def addon_for_pack_id(pack_id: str) -> Optional[LiteAddon]:
    """Resolve an mw_subscriptions.pack_id back to its add-on, if any."""
    if not pack_id.startswith(ADDON_PACK_PREFIX):
        return None
    return LITE_ADDONS.get(pack_id[len(ADDON_PACK_PREFIX):])
