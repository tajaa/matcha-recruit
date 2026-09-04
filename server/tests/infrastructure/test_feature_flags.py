import pytest

from app.core.feature_flags import (
    ALL_FEATURES,
    BETA_FEATURES,
    BUILTIN_TIER_META,
    BUILTIN_TIER_SLUGS,
    DEFAULT_COMPANY_FEATURES,
    TIER_REQUIRED_FEATURES,
    TIER_SIGNUP_PRESETS,
    assert_feature_allowed,
    builtin_tier_composition,
    company_may_use_beta,
    merge_company_features,
)


def test_merge_company_features_defaults_include_handbooks():
    features = merge_company_features(None)
    assert features["handbooks"] is True
    assert "accommodations" not in features
    assert "discipline" not in features
    assert "resident_care" not in features
    assert "driver_risk" not in features
    assert features["matcha_work"] is False
    assert features["matcha_ops"] is False


def test_merge_company_features_allows_explicit_override():
    features = merge_company_features({"handbooks": False, "policies": True})
    assert features["handbooks"] is False
    # Extra keys not in defaults pass through.
    assert features["policies"] is True


def test_ops_features_are_independent_from_matcha_work():
    features = merge_company_features({"matcha_ops": True})
    assert features["matcha_ops"] is True
    assert features["matcha_work"] is False


def test_ops_children_require_ops_parent():
    from app.core.feature_flags import feature_dependency_violations

    assert feature_dependency_violations({"inventory": True})["inventory"] == ("matcha_ops",)


def test_merge_company_features_handles_json_string():
    features = merge_company_features('{"handbooks": false}')
    assert features["handbooks"] is False
    assert "accommodations" not in features


def test_merge_company_features_ignores_retired_stored_grants():
    features = merge_company_features({
        "accommodations": True,
        "discipline": True,
        "resident_care": True,
        "driver_risk": True,
    })
    assert not ({"accommodations", "discipline", "resident_care", "driver_risk"} & features.keys())


def test_matcha_lite_tier_forces_handbooks_on():
    # Existing stored flag is False (pre-handbooks-bundle accounts) — tier overlay flips it back on.
    features = merge_company_features({"handbooks": False}, "matcha_lite")
    assert features["handbooks"] is True


def test_matcha_lite_tier_forces_training_on():
    # Same overlay applies to training (added with SB 1343 module).
    features = merge_company_features({"training": False}, "matcha_lite")
    assert features["training"] is True


def test_ir_only_self_serve_forces_full_ir_bundle_on():
    # Legacy free beta — remaining bundle features are auto-enabled regardless
    # of stored value; retired feature grants are ignored.
    features = merge_company_features(
        {
            "handbooks": False,
            "training": False,
            "employees": False,
            "discipline": True,
            "incidents": False,
        },
        "ir_only_self_serve",
    )
    assert features["handbooks"] is True
    assert features["training"] is True
    assert features["employees"] is True
    assert "discipline" not in features
    assert features["incidents"] is True


def test_matcha_lite_keeps_employees_payment_gated():
    # Stored false stays false — Stripe webhook flips it after payment.
    features = merge_company_features({"employees": False, "discipline": False}, "matcha_lite")
    assert features["employees"] is False
    assert "discipline" not in features


def test_bespoke_tier_respects_explicit_disable():
    features = merge_company_features({"handbooks": False}, "bespoke")
    assert features["handbooks"] is False


# ── Beta gating ──────────────────────────────────────────────────────────────


def test_beta_features_is_subset_of_all_features():
    # Catches a typo'd or since-renamed key in BETA_FEATURES at CI time,
    # rather than it silently no-op'ing at runtime.
    assert BETA_FEATURES <= ALL_FEATURES


def test_no_default_true_feature_is_marked_beta():
    # A flag that ships ON for every company by default is GA by definition —
    # marking it beta would show a locked "beta" toggle on a feature the
    # customer already has.
    always_on = {k for k, v in DEFAULT_COMPANY_FEATURES.items() if v is True}
    assert not (always_on & BETA_FEATURES)


def test_company_may_use_beta_requires_is_test_true():
    assert company_may_use_beta({"is_test": True}) is True
    assert company_may_use_beta({"is_test": False}) is False
    assert company_may_use_beta({}) is False
    assert company_may_use_beta(None) is False


@pytest.mark.parametrize(
    "enabled,is_test,should_raise",
    [
        (True, False, True),
        (True, True, False),
        (False, False, False),
        (False, True, False),
    ],
)
def test_assert_feature_allowed_beta_matrix(enabled, is_test, should_raise):
    # Exercise the matrix against a synthetic beta set passed explicitly —
    # beta_features is a required kwarg, not a read of the module constant,
    # so coverage doesn't depend on BETA_FEATURES being non-empty and doesn't
    # need monkeypatching.
    beta_features = frozenset({"schedule_intelligence"})
    row = {"is_test": is_test}
    if should_raise:
        with pytest.raises(ValueError):
            assert_feature_allowed("schedule_intelligence", enabled, beta_features=beta_features, company_row=row)
    else:
        assert assert_feature_allowed("schedule_intelligence", enabled, beta_features=beta_features, company_row=row) is None


def test_assert_feature_allowed_noop_for_non_beta_feature():
    beta_features = frozenset({"schedule_intelligence"})
    assert assert_feature_allowed("handbooks", True, beta_features=beta_features, company_row={"is_test": False}) is None


def test_assert_feature_allowed_requires_beta_features_kwarg():
    # No silent fallback to the module constant — see is_beta's docstring for
    # why (it would make an admin's beta->ready DB override a no-op).
    with pytest.raises(TypeError):
        assert_feature_allowed("handbooks", True, company_row={"is_test": False})


# ── Built-in tier composition ────────────────────────────────────────────────


def test_builtin_tier_slugs_covers_both_overlay_and_preset():
    assert set(BUILTIN_TIER_SLUGS) == set(TIER_REQUIRED_FEATURES) | set(TIER_SIGNUP_PRESETS)


def test_every_builtin_tier_has_meta():
    for slug in BUILTIN_TIER_SLUGS:
        assert slug in BUILTIN_TIER_META, f"{slug} missing from BUILTIN_TIER_META"


@pytest.mark.parametrize("slug", list(BUILTIN_TIER_SLUGS))
def test_builtin_tier_composition_buckets_are_disjoint(slug):
    buckets = builtin_tier_composition(slug)
    seen: dict[str, str] = {}
    for bucket_name, keys in buckets.items():
        for key in keys:
            assert key not in seen, (
                f"{slug}: '{key}' appears in both '{seen.get(key)}' and '{bucket_name}'"
            )
            seen[key] = bucket_name


def test_matcha_lite_forced_off_bucket_has_training():
    # Training moved up to Matcha-X — the overlay forces it off
    # regardless of any stored True, and that must render as "blocked", not
    # merely absent from "forced_on".
    buckets = builtin_tier_composition("matcha_lite")
    assert set(buckets["forced_off"]) == {"training"}


def test_matcha_lite_paid_gate_is_incidents():
    assert builtin_tier_composition("matcha_lite")["paid_gate"] == ["incidents"]


def test_matcha_lite_essentials_preset_exists():
    # This preset was missing before this change — admin_change_tier didn't
    # recognize the tier as a valid PATCH target.
    assert "matcha_lite_essentials" in TIER_SIGNUP_PRESETS
    assert TIER_SIGNUP_PRESETS["matcha_lite_essentials"]["incidents"] is True


def test_resources_free_and_bespoke_have_no_paid_gate():
    # Presets exist but no Stripe checkout backs either — LifecycleActions
    # needs their labels without treating them as gated tiers.
    assert builtin_tier_composition("resources_free")["paid_gate"] == []
    assert builtin_tier_composition("bespoke")["paid_gate"] == []
