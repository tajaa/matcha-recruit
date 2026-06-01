"""Golden tests for the broker Book-Pricing engine (pooled %-off-list volume model)."""

from app.core.services.deal_book import (
    BookClient,
    BookInputs,
    DiscountTier,
    compute_book_quote,
)


def _q(seats_list, **kw):
    clients = [BookClient(name=f"C{i}", seats=s) for i, s in enumerate(seats_list)]
    return compute_book_quote(BookInputs(broker_name="Alliant", clients=clients, **kw))


def test_tier_boundaries():
    def disc(n):
        return _q([n]).discount_pct
    assert disc(99) == 0
    assert disc(100) == 5
    assert disc(499) == 5
    assert disc(500) == 10
    assert disc(999) == 10
    assert disc(1_000) == 15
    assert disc(5_000) == 15


def test_net_pepm_math():
    q = _q([500])  # 500 seats → 10% off $5
    assert q.discount_pct == 10
    assert q.list_pepm == 5.0
    assert q.net_pepm == 4.5
    assert q.applied_tier_min == 500


def test_pooling_unlocks_volume():
    # Three small clients, none individually over 100, but pooled = 640 → 10% tier.
    q = _q([80, 210, 350])
    assert q.total_seats == 640
    assert q.discount_pct == 10
    assert q.net_pepm == 4.5
    # Per-client lines at the pooled rate.
    by_seats = {ln.seats: ln.annual for ln in q.lines}
    assert by_seats[80] == round(4.5 * 80 * 12)    # 4,320
    assert by_seats[210] == round(4.5 * 210 * 12)  # 11,340
    assert by_seats[350] == round(4.5 * 350 * 12)  # 18,900


def test_roster_foots_to_book_total():
    q = _q([80, 210, 350])
    assert q.book_annual == sum(ln.annual for ln in q.lines)
    assert q.book_annual == 34_560
    assert q.list_annual == sum(ln.list_annual for ln in q.lines)
    assert q.list_annual == 5 * 640 * 12  # 38,400
    assert q.book_savings == q.list_annual - q.book_annual  # 3,840


def test_empty_roster():
    q = compute_book_quote(BookInputs(broker_name="B", clients=[]))
    assert q.total_seats == 0
    assert q.discount_pct == 0           # 0 >= min_seats 0 → first tier (0%)
    assert q.net_pepm == 5.0
    assert q.book_annual == 0
    assert q.book_savings == 0


def test_editable_list_pepm_and_tiers():
    # Custom list rate + custom discount tiers (both threshold and % editable).
    inp = BookInputs(
        broker_name="B",
        list_pepm=4.0,
        discount_tiers=[DiscountTier(min_seats=0, discount_pct=0), DiscountTier(min_seats=250, discount_pct=20)],
        clients=[BookClient(name="X", seats=300)],
    )
    q = compute_book_quote(inp)
    assert q.discount_pct == 20
    assert q.net_pepm == round(4.0 * 0.8, 2)  # 3.2
    assert q.applied_tier_min == 250


def test_defaults_when_none():
    # No blocks / no discount_tiers / no clients → engine + doc still resolve.
    inp = BookInputs(broker_name="B")
    q = compute_book_quote(inp)
    assert q.total_seats == 300          # default sample client
    assert q.discount_pct == 5           # 300 → 100-tier
    assert len(inp.resolved_blocks()) > 0
    assert inp.resolved_tiers()[0].min_seats == 0


def test_template_renders():
    from app.core.services.deal_book_template import render_book_proposal_html

    # Two clients so the book-wide aggregate differs from every per-company figure.
    inp = BookInputs(
        broker_name="Alliant",
        clients=[BookClient(name="Acme", seats=200), BookClient(name="Beacon", seats=450)],
    )
    q = compute_book_quote(inp)
    html = render_book_proposal_html(inp, q)
    assert "Book Pricing" in html
    assert "Acme" in html
    assert "your book" in html  # active schedule row marker

    # Roster: per-company Monthly + Annual columns, no book-wide total row.
    assert "<th>Monthly</th>" in html
    assert "<th>Annual</th>" in html
    assert "Book total" not in html
    acme = next(ln for ln in q.lines if ln.name == "Acme")
    assert f"${round(acme.annual / 12):,}" in html  # Acme's per-company monthly
    assert f"${acme.annual:,}" in html              # Acme's per-company annual

    # Book Economics: pooled PEPM rate, NO scary book-wide aggregate dollar totals.
    assert "PEPM" in html
    assert f"${round(q.book_annual / 12):,}" not in html  # aggregate monthly gone
    assert f"${q.book_annual:,}" not in html              # aggregate yearly gone
