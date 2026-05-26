"""Golden-number tests for the Deal Flow pricing engine.

Values verified against deals/la-nonprofit/LA_NonProfit_Pricing_OnePager_v2.1.html.
"""

from app.core.services.deal_pricing import DealInputs, compute_both, compute_quote


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


def test_compute_both_uses_same_inputs():
    inp = DealInputs(company_name="Acme Test", headcount=200, tier="max", broker=True, partner=True)
    quotes = compute_both(inp)
    # Mid 200ee: 10*200*12=24000 + 4000 = 28000 subtotal
    assert quotes["mid"].subtotal == 28_000
    # Max 200ee: 13*200*12=31200 + 10000 = 41200 subtotal
    assert quotes["max"].subtotal == 41_200
    assert quotes["max"].your_price_yr == 41_200 - 4_120 - 2_060  # -10% -5%
