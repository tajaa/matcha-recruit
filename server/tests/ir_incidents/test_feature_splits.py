"""Tests for the 2026-07-30 OSHA/magic-links/copilot flag split that made
osha_export, osha_auto_report, ir_magic_links, and ir_copilot independently
composable in /admin/products.

Pure-helper unit tests over feature_flags.py + the public-intake gate — no
app boot, no DB.
"""
from app.core.feature_flags import (
    DEFAULT_COMPANY_FEATURES,
    FEATURE_REQUIRES,
    TIER_REQUIRED_FEATURES,
    merge_company_features,
)
from app.core.services.product_definitions import ProductDefinition, materialize_features
from app.matcha.routes.intake.inbound_email import _public_intake_allowed

NEW_FLAGS = ("osha_export", "osha_auto_report", "ir_magic_links", "ir_copilot")


# ── defaults ─────────────────────────────────────────────────────────────

def test_new_flags_present_and_default_true():
    for flag in NEW_FLAGS:
        assert flag in DEFAULT_COMPANY_FEATURES
        assert DEFAULT_COMPANY_FEATURES[flag] is True


def test_merge_missing_keys_default_true():
    # "bespoke" is not a TIER_REQUIRED_FEATURES key, so the overlay is a
    # no-op here — this is purely the raw-defaults merge path.
    merged = merge_company_features({}, "bespoke")
    for flag in NEW_FLAGS:
        assert merged[flag] is True


# ── essentials overlay forces OSHA sub-parts off ────────────────────────

def test_essentials_overlay_forces_osha_export_and_auto_report_off():
    # Stored True on everything (mirrors a tenant that somehow has them all
    # set) — the matcha_lite_essentials overlay must still stomp both to
    # False, matching the pre-existing osha_logs behavior.
    stored = {flag: True for flag in NEW_FLAGS}
    merged = merge_company_features(stored, "matcha_lite_essentials")
    assert merged["osha_logs"] is False
    assert merged["osha_export"] is False
    assert merged["osha_auto_report"] is False
    # ir_magic_links / ir_copilot are untouched by the essentials overlay —
    # essentials still gets them via `incidents`.
    assert merged["ir_magic_links"] is True
    assert merged["ir_copilot"] is True


def test_standard_lite_overlay_does_not_touch_new_flags():
    merged = merge_company_features({}, "matcha_lite")
    for flag in NEW_FLAGS:
        assert merged[flag] is True


# ── materialize_features withholds cleanly for a composed product ──────

def _product(features: dict) -> ProductDefinition:
    return ProductDefinition(
        id="test-id",
        slug="lite-test",
        name="Lite Test",
        description="",
        features=features,
        gate_feature="incidents",
        pricing_model="flat",
        price_cents=5000,
        block_size=None,
        min_headcount=1,
        max_headcount=300,
        nav=None,
        status="draft",
    )


def test_materialized_bare_bones_product_withholds_ungranted_flags():
    # incidents + osha_export only — the "Matcha Lite" composed product from
    # the plan. Everything else in NEW_FLAGS must land False.
    product = _product({"incidents": True, "osha_export": True})
    materialized = materialize_features(product)
    assert materialized["incidents"] is True
    assert materialized["osha_export"] is True
    assert materialized["osha_logs"] is False
    assert materialized["osha_auto_report"] is False
    assert materialized["ir_magic_links"] is False
    assert materialized["ir_copilot"] is False


def test_materialized_full_product_grants_all_new_flags():
    # "Matcha Daily" from the plan.
    features = {"incidents": True, **{f: True for f in NEW_FLAGS}}
    product = _product(features)
    materialized = materialize_features(product)
    for flag in NEW_FLAGS:
        assert materialized[flag] is True


# ── FEATURE_REQUIRES ─────────────────────────────────────────────────────

def test_new_flags_require_incidents():
    for flag in NEW_FLAGS:
        assert FEATURE_REQUIRES[flag] == ("incidents",)


# ── _public_intake_allowed: missing-key-defaults-true is the load-bearing
#    behavior — existing tenants predate the ir_magic_links column and must
#    not lose their public report/intake links. ───────────────────────────

def test_public_intake_allowed_missing_key_defaults_true():
    assert _public_intake_allowed({"incidents": True}) is True


def test_public_intake_allowed_explicit_false_blocks():
    assert _public_intake_allowed({"incidents": True, "ir_magic_links": False}) is False


def test_public_intake_allowed_requires_incidents_too():
    assert _public_intake_allowed({"incidents": False}) is False
    assert _public_intake_allowed({"incidents": False, "ir_magic_links": True}) is False


def test_public_intake_allowed_empty_dict_blocked():
    # No incidents key at all — must not be treated as "incidents on".
    assert _public_intake_allowed({}) is False
