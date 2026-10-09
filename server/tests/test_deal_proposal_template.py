"""One-pager + Lite Edition proposal renderers — partner discount only (no broker lines)."""

from app.core.services.deal_pricing import DealInputs, compute_all
from app.core.services.deal_proposal_template import render_lite_proposal_html, render_proposal_html


def _render(partner: bool, **extra):
    inp = DealInputs(company_name="Acme Test", headcount=500, tier="max", partner=partner, **extra)
    return inp, compute_all(inp)


def test_standard_one_pager_shows_the_partner_discount_in_the_banner_and_every_card():
    inp, quotes = _render(partner=True)
    html = render_proposal_html(inp, quotes)
    assert "Your pricing" in html and "5% below list" in html
    assert html.count("&minus;5% partner") == 3  # one build-up per tier card
    assert "Subtotal" in html
    assert "Broker discount" not in html and "% Broker" not in html


def test_standard_one_pager_without_a_discount_has_no_banner_or_subtotal_rows():
    inp, quotes = _render(partner=False)
    html = render_proposal_html(inp, quotes)
    assert "below list" not in html
    assert "&minus;5% partner" not in html


def test_lite_edition_shows_the_partner_line_and_the_saving():
    inp, quotes = _render(partner=True, template="lite_edition")
    html = render_lite_proposal_html(inp, quotes["lite"])
    assert "&minus;5% partner" in html
    assert "YOU SAVE" in html and "5% OFF" in html
    assert "% Broker" not in html


def test_lite_edition_without_a_discount_has_no_saving_line():
    inp, quotes = _render(partner=False, template="lite_edition")
    html = render_lite_proposal_html(inp, quotes["lite"])
    assert "YOU SAVE" not in html


def test_the_deal_flow_template_keys_no_longer_include_the_removed_tabs():
    from app.core.routes.admin._shared import _DEAL_TEMPLATE_KEYS

    assert _DEAL_TEMPLATE_KEYS == {"full", "one_pager", "lite"}
