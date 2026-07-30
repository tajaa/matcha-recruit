"""Tests for the 2026-07-30 OSHA/magic-links/copilot flag split that made
osha_export, osha_auto_report, ir_magic_links, and ir_copilot independently
composable in /admin/products.

Two different default policies are load-bearing here and the tests are split
accordingly:

- osha_export / osha_auto_report are ADDITIVE (default False). Their routes
  gate on require_any_feature("osha_logs", <flag>), so a legacy osha_logs
  tenant needs nothing stored to keep full OSHA capability, and a tenant with
  osha_logs deliberately off doesn't silently regain it.
- ir_magic_links / ir_copilot are SUBTRACTIVE (default True, parent is
  `incidents` itself — an any()-with-incidents gate would be a no-op since
  the router mount already requires incidents). Every full-stomp preset that
  grants `incidents` must re-assert both, or a stored explicit False
  overrides the default and silently denies them (an xhigh review on PR #103
  caught this happening in real Lite/X/IR signups).

A prior version of this file also asserted FEATURE_REQUIRES ties all four
flags to `incidents` — that was removed after the same review found it
broke PATCH /admin/company-features (disabling incidents on any company with
a default-True dependent) and PATCH .../tier for tier="bespoke" (whose preset
carries the pair True with no `incidents` key at all). The route-level gates
already make the sub-flags inert without their parent; FEATURE_REQUIRES had
nothing left to protect.

Pure-helper unit tests over feature_flags.py + the public-intake gate — no
app boot, no DB.
"""
from app.core.feature_flags import (
    DEFAULT_COMPANY_FEATURES,
    FEATURE_REQUIRES,
    TIER_SIGNUP_PRESETS,
    feature_dependency_violations,
    merge_company_features,
)
from app.core.services.product_definitions import ProductDefinition, materialize_features
from app.matcha.routes.intake.inbound_email import _public_intake_allowed

ADDITIVE_OSHA_FLAGS = ("osha_export", "osha_auto_report")
SUBTRACTIVE_IR_FLAGS = ("ir_magic_links", "ir_copilot")
NEW_FLAGS = ADDITIVE_OSHA_FLAGS + SUBTRACTIVE_IR_FLAGS

# Every TIER_SIGNUP_PRESETS entry that grants `incidents` True — each one
# must also carry the subtractive IR pair True, or the full-stomp shape
# denies them by omission (see the module docstring).
INCIDENTS_BEARING_PRESETS = ("matcha_lite", "matcha_lite_essentials", "matcha_x", "ir_only_self_serve")


# ── defaults ─────────────────────────────────────────────────────────────

def test_additive_osha_flags_default_false():
    for flag in ADDITIVE_OSHA_FLAGS:
        assert flag in DEFAULT_COMPANY_FEATURES
        assert DEFAULT_COMPANY_FEATURES[flag] is False


def test_subtractive_ir_flags_default_true():
    for flag in SUBTRACTIVE_IR_FLAGS:
        assert flag in DEFAULT_COMPANY_FEATURES
        assert DEFAULT_COMPANY_FEATURES[flag] is True


def test_merge_missing_keys_use_their_own_default():
    # "bespoke" is not a TIER_REQUIRED_FEATURES key, so the read-time overlay
    # is a no-op here — this is purely the raw-defaults merge path.
    merged = merge_company_features({}, "bespoke")
    for flag in ADDITIVE_OSHA_FLAGS:
        assert merged[flag] is False
    for flag in SUBTRACTIVE_IR_FLAGS:
        assert merged[flag] is True


# ── essentials overlay: osha_logs=False is sufficient, no overlay entries
#    needed for the additive OSHA pair (require_any_feature covers it) ────

def test_essentials_overlay_forces_osha_logs_off_and_additive_flags_stay_default():
    merged = merge_company_features({}, "matcha_lite_essentials")
    assert merged["osha_logs"] is False
    # Additive flags weren't touched by the overlay at all — they're at
    # their own default (False), same as any other tenant with no stored key.
    assert merged["osha_export"] is False
    assert merged["osha_auto_report"] is False
    # ir_magic_links / ir_copilot are untouched by the essentials overlay —
    # essentials still gets them via `incidents`.
    assert merged["ir_magic_links"] is True
    assert merged["ir_copilot"] is True


def test_standard_lite_overlay_leaves_new_flags_at_default():
    merged = merge_company_features({}, "matcha_lite")
    for flag in ADDITIVE_OSHA_FLAGS:
        assert merged[flag] is False
    for flag in SUBTRACTIVE_IR_FLAGS:
        assert merged[flag] is True


# ── the regression PR #103's review caught: full-stomp presets must
#    re-assert the subtractive IR pair, or they silently deny it ─────────

def test_incidents_bearing_presets_reassert_subtractive_ir_pair():
    for slug in INCIDENTS_BEARING_PRESETS:
        preset = TIER_SIGNUP_PRESETS[slug]
        assert preset.get("incidents") is True, f"{slug} preset should grant incidents"
        for flag in SUBTRACTIVE_IR_FLAGS:
            assert preset.get(flag) is True, (
                f"{slug} preset stomps enabled_features to False then grants "
                f"incidents — it must also explicitly grant {flag!r} or a real "
                f"signup through this preset loses it (stored False beats the "
                f"default True in merge_company_features)"
            )


def test_incidents_bearing_preset_merge_result_has_ir_pair_on():
    # End-to-end version of the above: merge each real preset dict the way
    # merge_company_features actually would for a fresh signup.
    for slug in INCIDENTS_BEARING_PRESETS:
        merged = merge_company_features(TIER_SIGNUP_PRESETS[slug], slug)
        assert merged["ir_magic_links"] is True, slug
        assert merged["ir_copilot"] is True, slug


# ── FEATURE_REQUIRES: the four split flags must NOT be enforced there ────

def test_new_flags_not_in_feature_requires():
    # See module docstring — enforcing this broke incidents-disable and the
    # bespoke tier-change path. Route-level gates already make these flags
    # inert without their parent; don't re-add the dependency here.
    for flag in NEW_FLAGS:
        assert flag not in FEATURE_REQUIRES


def test_disabling_incidents_introduces_no_violations():
    features = dict(DEFAULT_COMPANY_FEATURES)
    features["incidents"] = True
    assert feature_dependency_violations(features) == {}
    features["incidents"] = False
    assert feature_dependency_violations(features) == {}


def test_bespoke_preset_has_no_violations():
    merged = merge_company_features(TIER_SIGNUP_PRESETS["bespoke"], "bespoke")
    assert feature_dependency_violations(merged) == {}


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
