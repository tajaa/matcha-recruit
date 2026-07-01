"""Pure-function tests for the admin-configurable Matcha Lite pricing engine."""

from app.core.services.matcha_lite_pricing import (
    PRODUCT_CODES,
    MatchaLitePricing,
    _FALLBACK_DEFAULTS,
    compute_matcha_lite_price_cents,
)


def _pricing(**overrides):
    defaults = dict(
        price_per_block_cents=5000,
        block_size=10,
        sale_price_per_block_cents=None,
        sale_active=False,
        min_headcount=1,
        max_headcount=300,
        updated_at=None,
        updated_by=None,
    )
    defaults.update(overrides)
    return MatchaLitePricing(**defaults)


def test_default_launch_price_is_five_dollars_per_head():
    pricing = _pricing()
    assert compute_matcha_lite_price_cents(pricing, 1) == 5000  # 1 employee still buys a full block
    assert compute_matcha_lite_price_cents(pricing, 10) == 5000
    assert compute_matcha_lite_price_cents(pricing, 11) == 10000
    assert compute_matcha_lite_price_cents(pricing, 300) == 150000


def test_out_of_range_headcount_returns_none():
    pricing = _pricing()
    assert compute_matcha_lite_price_cents(pricing, 0) is None
    assert compute_matcha_lite_price_cents(pricing, 301) is None


def test_admin_can_retune_base_price_and_block_size():
    pricing = _pricing(price_per_block_cents=2000, block_size=5)
    assert compute_matcha_lite_price_cents(pricing, 5) == 2000
    assert compute_matcha_lite_price_cents(pricing, 6) == 4000


def test_sale_price_used_only_when_active():
    pricing = _pricing(sale_price_per_block_cents=2500, sale_active=False)
    assert compute_matcha_lite_price_cents(pricing, 10) == 5000

    pricing_on_sale = _pricing(sale_price_per_block_cents=2500, sale_active=True)
    assert compute_matcha_lite_price_cents(pricing_on_sale, 10) == 2500
    assert compute_matcha_lite_price_cents(pricing_on_sale, 11) == 5000


def test_admin_configured_headcount_bounds_are_respected():
    pricing = _pricing(min_headcount=5, max_headcount=50)
    assert compute_matcha_lite_price_cents(pricing, 4) is None
    assert compute_matcha_lite_price_cents(pricing, 51) is None
    assert compute_matcha_lite_price_cents(pricing, 5) == 5000


def test_product_codes_has_standard_and_essentials():
    assert PRODUCT_CODES == ("matcha_lite", "matcha_lite_essentials")


def test_essentials_fallback_default_is_four_dollars_per_head():
    pricing = _pricing(**_FALLBACK_DEFAULTS["matcha_lite_essentials"])
    assert compute_matcha_lite_price_cents(pricing, 1) == 4000
    assert compute_matcha_lite_price_cents(pricing, 10) == 4000
    assert compute_matcha_lite_price_cents(pricing, 11) == 8000


def test_standard_fallback_default_matches_launch_price():
    pricing = _pricing(**_FALLBACK_DEFAULTS["matcha_lite"])
    assert compute_matcha_lite_price_cents(pricing, 10) == 5000
