"""Golden-number tests for the Deal Flow pricing engine.

Values verified against deals/la-nonprofit/LA_NonProfit_Pricing_OnePager_v2.1.html.
"""

from app.core.services.deal_pricing import (
    DealInputs,
    TierOverride,
    compute_all,
    compute_quote,
    lite_pepm,
)


def test_lite_volume_pepm():
    assert lite_pepm(50) == 5
    assert lite_pepm(100) == 5  # "over 100" → 101+
    assert lite_pepm(101) == 4
    assert lite_pepm(500) == 4  # "over 500" → 501+
    assert lite_pepm(501) == 3
    assert lite_pepm(2000) == 3


def test_lite_volume_applied_in_quote():
    # 600 employees → Lite PEPM drops to $3 unless overridden.
    q = compute_quote("lite", 600)
    assert q.pepm == 3
    assert q.subscription_yr == 3 * 600 * 12
    # Override still wins.
    q2 = compute_quote("lite", 600, pepm=5)
    assert q2.pepm == 5


def test_lite_80_broker_partner():
    # ≤100 employees → base $5 PEPM.
    q = compute_quote("lite", 80, broker=True, partner=True)
    assert q.pepm == 5
    assert q.subscription_yr == 4_800
    assert q.onboarding == 0
    assert q.subtotal == 4_800
    assert q.your_price_yr == 4_800 - 480 - 240


def test_lite_500_broker_partner_volume():
    # 500 employees → over 100 → $4 PEPM (not over 500, so not $3).
    q = compute_quote("lite", 500, broker=True, partner=True)
    assert q.pepm == 4
    assert q.subscription_yr == 24_000
    assert q.subtotal == 24_000
    assert q.broker_disc == 2_400
    assert q.partner_disc == 1_200
    assert q.your_price_yr == 20_400
    assert q.you_save_yr == 3_600


def test_mid_500_broker_partner():
    q = compute_quote("mid", 500, broker=True, partner=True)
    assert q.subscription_yr == 60_000
    assert q.onboarding == 4_000
    assert q.subtotal == 64_000
    assert q.broker_disc == 6_400
    assert q.partner_disc == 3_200
    assert q.your_price_yr == 54_400
    assert q.you_save_yr == 9_600
    assert q.discount_pct == 15


def test_max_500_broker_partner():
    q = compute_quote("max", 500, broker=True, partner=True)
    assert q.subscription_yr == 78_000
    assert q.onboarding == 10_000
    assert q.subtotal == 88_000
    assert q.your_price_yr == 74_800
    assert q.you_save_yr == 13_200


def test_no_discount_mid_500():
    q = compute_quote("mid", 500)
    assert q.subtotal == 64_000
    assert q.broker_disc == 0
    assert q.partner_disc == 0
    assert q.your_price_yr == 64_000
    assert q.you_save_yr == 0
    assert q.discount_pct == 0


def test_broker_only():
    q = compute_quote("max", 500, broker=True, partner=False)
    assert q.broker_disc == 8_800
    assert q.partner_disc == 0
    assert q.your_price_yr == 88_000 - 8_800
    assert q.discount_pct == 10


def test_compute_all_uses_same_inputs():
    inp = DealInputs(company_name="Acme Test", headcount=200, tier="max", broker=True, partner=True)
    quotes = compute_all(inp)
    assert set(quotes) == {"lite", "mid", "max"}
    # Lite 200ee: over 100 → $4 PEPM → 4*200*12=9600 + 0 = 9600 subtotal
    assert quotes["lite"].pepm == 4
    assert quotes["lite"].subtotal == 9_600
    # Mid 200ee: 10*200*12=24000 + 4000 = 28000 subtotal
    assert quotes["mid"].subtotal == 28_000
    # Max 200ee: 13*200*12=31200 + 10000 = 41200 subtotal
    assert quotes["max"].subtotal == 41_200
    assert quotes["max"].your_price_yr == 41_200 - 4_120 - 2_060  # -10% -5%


def test_per_tier_overrides():
    inp = DealInputs(
        company_name="Custom Co",
        headcount=500,
        tier="mid",
        broker=False,
        partner=False,
        overrides={
            "mid": TierOverride(pepm=20, onboarding=5_000),
            "max": TierOverride(pepm=15, onboarding=12_000),
        },
    )
    quotes = compute_all(inp)
    # Mid override: 20*500*12=120000 + 5000 = 125000
    assert quotes["mid"].pepm == 20
    assert quotes["mid"].subtotal == 125_000
    # Max override
    assert quotes["max"].subtotal == 15 * 500 * 12 + 12_000
    # Lite untouched → volume default at 500ee ($4 / $0)
    assert quotes["lite"].pepm == 4
    assert quotes["lite"].subtotal == 24_000


def test_override_single_tier_quote():
    q = compute_quote("max", 500, pepm=20, onboarding=0)
    assert q.subscription_yr == 120_000
    assert q.onboarding == 0
    assert q.subtotal == 120_000
