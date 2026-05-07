from app.core.feature_flags import merge_company_features


def test_merge_company_features_defaults_include_handbooks():
    features = merge_company_features(None)
    assert features["handbooks"] is True
    assert features["accommodations"] is True
    assert features["matcha_work"] is False


def test_merge_company_features_allows_explicit_override():
    features = merge_company_features({"handbooks": False, "policies": True})
    assert features["handbooks"] is False
    # Extra keys not in defaults pass through.
    assert features["policies"] is True


def test_merge_company_features_handles_json_string():
    features = merge_company_features('{"handbooks": false}')
    assert features["handbooks"] is False
    assert features["accommodations"] is True


def test_matcha_lite_tier_forces_handbooks_on():
    # Existing stored flag is False (pre-handbooks-bundle accounts) — tier overlay flips it back on.
    features = merge_company_features({"handbooks": False}, "matcha_lite")
    assert features["handbooks"] is True


def test_matcha_lite_tier_forces_training_on():
    # Same overlay applies to training (added with SB 1343 module).
    features = merge_company_features({"training": False}, "matcha_lite")
    assert features["training"] is True


def test_ir_only_self_serve_forces_handbooks_and_training_on():
    # Legacy matcha-lite signups; same overlay applies.
    features = merge_company_features(
        {"handbooks": False, "training": False}, "ir_only_self_serve"
    )
    assert features["handbooks"] is True
    assert features["training"] is True


def test_bespoke_tier_respects_explicit_disable():
    features = merge_company_features({"handbooks": False}, "bespoke")
    assert features["handbooks"] is False
