import pytest

from app.core.feature_flags import (
    DEFAULT_COMPANY_FEATURES,
    FEATURE_REQUIRES,
    feature_dependency_violations,
)
from app.core.services.product_definitions import ProductDefinitionError, validate_features


def test_inventory_voice_is_an_admin_toggleable_default_off_feature():
    assert DEFAULT_COMPANY_FEATURES["inventory_voice"] is False


def test_inventory_voice_requires_inventory():
    assert FEATURE_REQUIRES["inventory_voice"] == ("inventory",)

    features = dict(DEFAULT_COMPANY_FEATURES)
    features["inventory_voice"] = True
    features["inventory"] = False

    assert feature_dependency_violations(features) == {
        "inventory_voice": ("inventory",),
    }


def test_inventory_voice_is_valid_with_inventory_enabled():
    features = dict(DEFAULT_COMPANY_FEATURES)
    features["matcha_ops"] = True
    features["inventory"] = True
    features["inventory_voice"] = True

    assert feature_dependency_violations(features) == {}


def test_custom_product_rejects_voice_audit_without_its_dependencies():
    with pytest.raises(ProductDefinitionError, match="inventory_voice.*inventory"):
        validate_features({"inventory_voice": True}, beta_features=frozenset())


def test_custom_product_rejects_inventory_chain_without_matcha_ops():
    with pytest.raises(ProductDefinitionError, match="inventory.*matcha_ops"):
        validate_features(
            {"inventory": True, "inventory_voice": True},
            beta_features=frozenset(),
        )


def test_custom_product_accepts_the_complete_voice_audit_chain():
    features = validate_features(
        {"matcha_ops": True, "inventory": True, "inventory_voice": True},
        beta_features=frozenset(),
    )

    assert features == {
        "matcha_ops": True,
        "inventory": True,
        "inventory_voice": True,
    }


def test_sales_intake_is_off_and_requires_inventory():
    assert DEFAULT_COMPANY_FEATURES["sales_intake"] is False
    assert FEATURE_REQUIRES["sales_intake"] == ("inventory",)
    features = dict(DEFAULT_COMPANY_FEATURES)
    features["sales_intake"] = True
    assert feature_dependency_violations(features) == {"sales_intake": ("inventory",)}
