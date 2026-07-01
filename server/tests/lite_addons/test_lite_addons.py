"""Pure-logic tests for the Lite add-on registry (no DB)."""

from app.core.feature_flags import DEFAULT_COMPANY_FEATURES, TIER_REQUIRED_FEATURES
from app.core.services.lite_addons import (
    ADDON_PACK_PREFIX,
    LITE_ADDONS,
    LITE_FAMILY_SOURCES,
    addon_for_pack_id,
    addon_pack_id,
)
from app.core.services.matcha_lite_pricing import PRODUCT_CODES


# Paid/tier gates deliberately absent from DEFAULT_COMPANY_FEATURES (flipped
# by webhooks or tier overlays) but valid in eligibility checks.
_PAID_GATE_FLAGS = {"incidents", "employees"}


def test_registry_features_exist_in_default_flags():
    # The webhook flips LiteAddon.feature on enabled_features — every entry
    # must be a real flag, or purchases would write orphan keys.
    for addon in LITE_ADDONS.values():
        assert addon.feature in DEFAULT_COMPANY_FEATURES, addon.key
        for required in addon.requires_features:
            assert required in DEFAULT_COMPANY_FEATURES or required in _PAID_GATE_FLAGS, (
                addon.key, required,
            )


def test_registry_features_not_forced_by_lite_overlays():
    # Overlay values override stored flags at read time — an add-on whose
    # feature is force-asserted in a Lite-family overlay could never actually
    # activate (or deactivate) for that tier.
    for source in LITE_FAMILY_SOURCES:
        overlay = TIER_REQUIRED_FEATURES.get(source, {})
        for addon in LITE_ADDONS.values():
            if source in addon.allowed_sources:
                assert addon.feature not in overlay, (addon.key, source)


def test_registry_product_codes_are_priced():
    for addon in LITE_ADDONS.values():
        assert addon.product_code in PRODUCT_CODES, addon.key


def test_registry_keys_are_consistent():
    for key, addon in LITE_ADDONS.items():
        assert addon.key == key
        assert addon.allowed_sources  # never empty
        assert set(addon.allowed_sources) <= set(LITE_FAMILY_SOURCES)


def test_pack_id_round_trip():
    for key in LITE_ADDONS:
        pack = addon_pack_id(key)
        assert pack.startswith(ADDON_PACK_PREFIX)
        resolved = addon_for_pack_id(pack)
        assert resolved is not None and resolved.key == key
    assert addon_for_pack_id("matcha_lite") is None
    assert addon_for_pack_id(ADDON_PACK_PREFIX + "nope") is None


def test_hris_addon_is_lite_only_and_needs_roster():
    hris = LITE_ADDONS["hris_sync"]
    assert hris.allowed_sources == ("matcha_lite",)
    assert "employees" in hris.requires_features
    # Unified Finch flag only — never the write-back deductions flag.
    assert hris.feature == "hris_finch"
