"""Golden tests for the full-proposal rack-rate pricing engine.

Verified against deals/la-nonprofit/LA_NonProfit_Proposal_v1.html.
"""

from app.core.services.deal_full import FullDealInputs, compute_full_pricing


def test_la_golden():
    inp = FullDealInputs(
        company_name="LA Non-Profit",
        headcount=500,
        rack_pepm=15.0,
        platform_fee=5000,
        implementation=8000,
        partner=True,
    )
    q = compute_full_pricing(inp)
    assert q.volume_applied is True
    assert q.subtotal_pepm == 13.50
    assert q.your_pepm == 12.83
    assert q.partner_rate_pct == 5
    assert q.partner_pepm_cut == 0.67
    assert q.annual_employee_your == 76_980
    assert q.platform_fee_your == 4_750
    assert q.annual_recurring_your == 81_730
    assert q.implementation_your == 7_600
    assert q.year1_your == 89_330
    assert q.year2_your == 81_730
    # ROI defaults: 223k hard + 60k risk = 283k total value.
    assert q.roi_total_value == 283_000
    assert q.roi_net_year1 == 193_670
    assert q.roi_net_year2 == 201_270
    assert q.roi_net_3yr == 596_210
    assert q.roi_multiple == 3.2
    assert q.roi_payback_month == 4


def test_no_discounts_no_volume():
    inp = FullDealInputs(company_name="Small Co", headcount=120, rack_pepm=15.0)
    q = compute_full_pricing(inp)
    assert q.volume_applied is False  # under 500
    assert q.your_pepm == 15.0
    assert q.annual_employee_your == 15 * 120 * 12
    assert q.platform_fee_your == 5_000  # no partner discount
    assert q.juris_tier == "Growth"
    assert q.juris_fee == 3_200


def test_extra_jurisdictions():
    inp = FullDealInputs(
        company_name="Multi", headcount=600, jurisdictions_extra=3, partner=True
    )
    q = compute_full_pricing(inp)
    assert q.juris_tier == "Business"
    assert q.juris_fee == 7_500
    assert q.extra_jurisdiction_cost == 22_500  # 3 × 7,500
    assert q.annual_recurring_your == q.annual_employee_your + q.platform_fee_your + 22_500


def test_volume_toggle_override():
    # Force volume off even at 500+.
    inp = FullDealInputs(company_name="X", headcount=500, rack_pepm=15.0, volume_discount=False)
    q = compute_full_pricing(inp)
    assert q.volume_applied is False
    assert q.subtotal_pepm == 15.0


def test_the_full_deal_has_no_broker_discount_or_default_note():
    from app.core.services.deal_full import DEFAULT_FULL_BLOCKS

    assert not any("broker" in name for name in FullDealInputs.model_fields)
    assert not any("broker" in str(block).lower() for block in DEFAULT_FULL_BLOCKS)


def test_partner_row_label_in_the_rendered_proposal():
    from app.core.services.deal_full_template import render_full_proposal_html

    inp = FullDealInputs(company_name="LA Non-Profit", headcount=500, partner=True)
    html = render_full_proposal_html(inp, compute_full_pricing(inp))
    assert "Less 5% Partner discount" in html
    assert "Broker" not in html
