from app.core.feature_flags import merge_company_features


def test_merge_company_features_defaults_include_handbooks():
    features = merge_company_features(None)
    assert features["offer_letters"] is True
    assert features["offer_letters_plus"] is False
    assert features["handbooks"] is True


def test_merge_company_features_allows_explicit_override():
    features = merge_company_features({"handbooks": False, "policies": True})
    assert features["handbooks"] is False
    assert features["policies"] is True


def test_merge_company_features_handles_json_string():
    features = merge_company_features('{"offer_letters": false}')
    assert features["offer_letters"] is False
    assert features["offer_letters_plus"] is False
    assert features["handbooks"] is True
