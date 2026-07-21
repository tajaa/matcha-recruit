"""Admin-composed products — pure-function tests (no DB, no Stripe).

The invariants that must not regress: a product can only ever grant flags on
the whitelist (it is the authorization boundary for the signup + webhook
paths), a paid product can't ship without a working gate, and the price a
customer is quoted matches every pricing model exactly.
"""

import pytest

from app.core.feature_flags import DEFAULT_COMPANY_FEATURES
from app.core.services.product_definitions import (
    ProductDefinition,
    ProductDefinitionError,
    compute_product_price_cents,
    is_tenant_activated,
    materialize_features,
    pending_features,
    product_for_pack_id,
    validate_features,
    validate_gate_feature,
    validate_nav,
    validate_pricing,
    validate_slug,
)


def make_product(**overrides) -> ProductDefinition:
    base = dict(
        id="00000000-0000-0000-0000-000000000001",
        slug="safety-pro",
        name="Safety Pro",
        description="",
        features={"incidents": True, "handbooks": True},
        gate_feature="incidents",
        pricing_model="per_seat",
        price_cents=300,
        block_size=None,
        min_headcount=1,
        max_headcount=300,
        nav=None,
        status="published",
    )
    base.update(overrides)
    return ProductDefinition(**base)


# --------------------------------------------------------------------------- #
# Pricing — what the customer is actually charged.
# --------------------------------------------------------------------------- #

def test_per_seat_price_scales_with_headcount():
    product = make_product(pricing_model="per_seat", price_cents=300)
    assert compute_product_price_cents(product, 25) == 7500


def test_block_price_rounds_up_to_the_next_block():
    product = make_product(pricing_model="block", price_cents=5000, block_size=10)
    assert compute_product_price_cents(product, 11) == 10000
    assert compute_product_price_cents(product, 10) == 5000


def test_flat_price_ignores_headcount():
    product = make_product(pricing_model="flat", price_cents=19900)
    assert compute_product_price_cents(product, 1) == 19900
    assert compute_product_price_cents(product, 250) == 19900


@pytest.mark.parametrize("model", ["free", "contact_sales"])
def test_unbilled_models_have_no_price(model):
    product = make_product(pricing_model=model, price_cents=None, gate_feature=None)
    assert compute_product_price_cents(product, 25) is None


def test_headcount_outside_range_raises_rather_than_quoting_zero():
    product = make_product(min_headcount=5, max_headcount=100)
    with pytest.raises(ProductDefinitionError):
        compute_product_price_cents(product, 4)
    with pytest.raises(ProductDefinitionError):
        compute_product_price_cents(product, 101)


# --------------------------------------------------------------------------- #
# The feature whitelist — the authorization boundary for signup + billing.
# --------------------------------------------------------------------------- #

def test_unknown_flag_is_rejected():
    with pytest.raises(ProductDefinitionError):
        validate_features({"totally_made_up": True})


def test_incidents_and_employees_are_sellable_despite_not_being_defaults():
    # Neither is in DEFAULT_COMPANY_FEATURES (they're flipped on by tier flows),
    # but they're the two headline sellable flags.
    assert "incidents" not in DEFAULT_COMPANY_FEATURES
    assert "employees" not in DEFAULT_COMPANY_FEATURES
    assert validate_features({"incidents": True, "employees": True}) == {
        "incidents": True, "employees": True,
    }


def test_a_product_with_nothing_enabled_is_rejected():
    with pytest.raises(ProductDefinitionError):
        validate_features({"incidents": False})


# --------------------------------------------------------------------------- #
# Materialization — the exact shape written to companies.enabled_features.
# --------------------------------------------------------------------------- #

def test_materialize_stomps_every_default_off_then_grants():
    product = make_product(features={"incidents": True, "handbooks": True})
    features = materialize_features(product)
    assert features["incidents"] is True
    assert features["handbooks"] is True
    # A default-True flag the product doesn't sell must NOT hydrate back on.
    assert DEFAULT_COMPANY_FEATURES["accommodations"] is True
    assert features["accommodations"] is False


def test_pending_shape_grants_nothing():
    product = make_product()
    assert not any(pending_features(product).values())


# --------------------------------------------------------------------------- #
# is_tenant_activated — the pending/active predicate sync-tenants gates on.
# Getting it wrong is a free activation.
# --------------------------------------------------------------------------- #

def test_priced_product_activation_follows_the_gate_flag():
    product = make_product()  # per_seat, gate=incidents
    assert is_tenant_activated(product, pending_features(product)) is False
    assert is_tenant_activated(product, materialize_features(product)) is True


def test_contact_sales_is_pending_until_a_granted_flag_is_on():
    # No gate flag exists for a sales-led product, so "has the admin run
    # activate-tenant yet?" is the only signal. Treating no-gate as active
    # would let sync-tenants hand the product to a company sales never approved.
    product = make_product(pricing_model="contact_sales", gate_feature=None, price_cents=None)
    assert is_tenant_activated(product, pending_features(product)) is False
    assert is_tenant_activated(product, materialize_features(product)) is True


def test_contact_sales_ignores_flags_the_product_does_not_grant():
    product = make_product(
        pricing_model="contact_sales", gate_feature=None, price_cents=None,
        features={"incidents": True},
    )
    # `handbooks` isn't part of this product — an unrelated admin toggle must
    # not read as activation.
    assert is_tenant_activated(product, {"handbooks": True}) is False


def test_free_products_are_active_from_signup():
    product = make_product(pricing_model="free", gate_feature=None, price_cents=None)
    assert is_tenant_activated(product, pending_features(product)) is True


def test_activation_check_accepts_a_json_string_column():
    # companies.enabled_features comes back as a dict from asyncpg's jsonb
    # codec, but a str on connections without it registered.
    product = make_product()
    assert is_tenant_activated(product, '{"incidents": true}') is True
    assert is_tenant_activated(product, '{"incidents": false}') is False
    assert is_tenant_activated(product, "not json") is False
    assert is_tenant_activated(product, None) is False


# --------------------------------------------------------------------------- #
# Gate + slug + nav guards.
# --------------------------------------------------------------------------- #

def test_paid_product_gate_must_be_a_feature_it_grants():
    # Otherwise the webhook flips a flag the tenant never gets and the pending
    # sidebar never clears.
    with pytest.raises(ProductDefinitionError):
        validate_gate_feature("employees", {"incidents": True}, "per_seat")
    assert validate_gate_feature("incidents", {"incidents": True}, "per_seat") == "incidents"


def test_unbilled_products_have_no_gate():
    assert validate_gate_feature("incidents", {"incidents": True}, "free") is None


def test_reserved_and_malformed_slugs_are_rejected():
    for bad in ("matcha_lite", "AB", "Has Spaces", "-leading", "x" * 41):
        with pytest.raises(ProductDefinitionError):
            validate_slug(bad)
    assert validate_slug("  Safety-Pro  ") == "safety-pro"


def test_block_pricing_needs_a_block_size():
    with pytest.raises(ProductDefinitionError):
        validate_pricing("block", 5000, None, 1, 300)
    validate_pricing("block", 5000, 10, 1, 300)


def test_nav_can_only_order_features_the_product_grants():
    with pytest.raises(ProductDefinitionError):
        validate_nav([{"feature": "training"}], {"incidents": True})
    assert validate_nav([{"feature": "incidents", "label": "Reports"}], {"incidents": True}) == [
        {"feature": "incidents", "label": "Reports"}
    ]


def test_pack_id_round_trip_ignores_other_products_subscriptions():
    product = make_product()
    assert product.pack_id == "product:safety-pro"
    assert product_for_pack_id(product.pack_id) == "safety-pro"
    assert product_for_pack_id("matcha_lite") is None
    assert product_for_pack_id("matcha_lite_addon_voice_intake") is None


def test_contact_sales_never_activates_itself_at_signup():
    # A sales-led product must wait for the admin, or it's free to anyone with
    # the signup link.
    assert make_product(pricing_model="contact_sales", gate_feature=None).activates_on_signup is False
    assert make_product(pricing_model="free", gate_feature=None).activates_on_signup is True
    assert make_product(pricing_model="per_seat").activates_on_signup is False
