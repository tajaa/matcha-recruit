"""Golden tests for the broker partner-program margin engine."""

from app.core.services.deal_broker import BrokerInputs, MarginTier, compute_broker_quote


def test_gold_tier_book_margin():
    inp = BrokerInputs(broker_name="Alliant", book_employees=2_000, representative_tier="mid")
    q = compute_broker_quote(inp)
    assert q.tier_label == "Gold"
    assert q.margin_pct == 20
    mid = next(w for w in q.wholesale if w.tier == "mid")
    assert mid.list_pepm == 10.0
    assert mid.cost_pepm == 8.0
    assert mid.spread_pepm == 2.0
    # 2.0 * 2000 * 12
    assert q.book_annual_margin == 48_000


def test_tier_boundaries():
    def tier(n):
        return compute_broker_quote(BrokerInputs(broker_name="B", book_employees=n)).tier_label
    assert tier(499) == "Bronze"
    assert tier(500) == "Silver"
    assert tier(1_999) == "Silver"
    assert tier(2_000) == "Gold"
    assert tier(4_999) == "Gold"
    assert tier(5_000) == "Platinum"


def test_sample_client_margin():
    inp = BrokerInputs(broker_name="B", book_employees=2_000, sample_client_headcount=300, sample_client_tier="mid")
    q = compute_broker_quote(inp)
    assert q.sample_client_list_pepm == 10.0
    assert q.sample_client_annual == 10 * 300 * 12       # client pays list
    assert q.sample_client_margin == 2 * 300 * 12        # 20% of $10 = $2 spread


def test_override_tier_wins():
    inp = BrokerInputs(broker_name="B", book_employees=100, margin_tier_override="Platinum")
    q = compute_broker_quote(inp)
    assert q.tier_label == "Platinum"
    assert q.margin_pct == 25


def test_editable_margin_tiers():
    inp = BrokerInputs(
        broker_name="B", book_employees=600,
        margin_tiers=[MarginTier(label="Flat", min_employees=0, max_employees=10_000_000, margin_pct=30)],
    )
    q = compute_broker_quote(inp)
    assert q.tier_label == "Flat"
    assert q.margin_pct == 30
    mid = next(w for w in q.wholesale if w.tier == "mid")
    assert mid.cost_pepm == 7.0  # 10 * 0.7


def test_defaults_resolve():
    inp = BrokerInputs(broker_name="B", book_employees=300)
    assert inp.blocks is None
    assert len(inp.resolved_blocks()) > 0
