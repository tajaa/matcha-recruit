"""Ranking: posted pay first, never compared across currencies, unposted pay never $0."""
from app.matcha.services.matcha_work.job_search import normalize, ranking


def base(lo, hi, currency="USD"):
    return {"status": "posted", "annual_min": lo, "annual_max": hi, "currency": currency}


def lead(id, comp=None, fit=None, **over):
    return {"id": id, "comp": comp or {}, "fit_score": fit, "screen_status": "pending",
            "user_state": "new", **over}


def order(leads, weights=None, **kw):
    return [r.lead_id for r in ranking.rank(leads, weights, **kw)]


def test_higher_posted_pay_ranks_first_and_unposted_pay_after():
    leads = [
        lead("low", {"base": base(150_000, 170_000)}, fit=5),
        lead("high", {"base": base(300_000, 350_000)}, fit=3),
        lead("none", {}, fit=5),
        lead("mid", {"base": base(220_000, 240_000)}, fit=3),
    ]
    ranked = ranking.rank(leads, None)
    assert [r.lead_id for r in ranked] == ["high", "mid", "low", "none"]
    assert [r.band for r in ranked] == [0, 0, 0, 2]
    assert [r.rank for r in ranked] == [1, 2, 3, 4]
    # The unposted job's score has no base term at all, not a zero one.
    none = ranked[-1]
    assert "base" not in none.explain["components"] and "base" not in none.explain["weights"]
    assert abs(sum(none.explain["weights"].values()) - 1) < 1e-3


def test_bonus_and_equity_move_a_job_up_with_the_persons_weights():
    leads = [
        lead("cash", {"base": base(260_000, 280_000)}),
        lead("upside", {"base": base(250_000, 270_000),
                        "bonus": {"status": "posted", "kind": "annual", "pct_min": 40},
                        "equity": {"status": "posted", "pct_min": 1.0, "pct_max": 1.5}}),
    ]
    assert order(leads, {"base": 1, "bonus": 0, "equity": 0, "fit": 0}) == ["cash", "upside"]
    assert order(leads) == ["upside", "cash"]


def test_other_currencies_are_their_own_band_and_floor_flags():
    leads = [
        lead("gbp", {"base": base(400_000, 450_000, "GBP")}),
        lead("usd_low", {"base": base(120_000, 140_000)}),
        lead("usd", {"base": base(200_000, 210_000)}),
    ]
    ranked = {r.lead_id: r for r in ranking.rank(leads, None, floor=150_000)}
    assert ranked["gbp"].band == 1 and ranked["usd"].band == 0
    assert ranked["usd"].rank < ranked["usd_low"].rank < ranked["gbp"].rank
    assert ranked["usd_low"].explain["flags"] == ["below_floor"]
    assert ranked["usd_low"].explain["components"]["base"] == 0


def test_dismissed_and_irrelevant_go_last_and_ties_are_stable():
    leads = [
        lead("b", {}, fit=3, posted_order=-48),
        lead("gone", {"base": base(400_000, 500_000)}, user_state="dismissed"),
        lead("a", {}, fit=3, posted_order=-2),
        lead("off", {"base": base(400_000, 500_000)}, screen_status="irrelevant"),
        lead("c", {}, fit=4),
    ]
    assert order(leads) == ["c", "a", "b", "gone", "off"]
    assert order(leads) == order(list(reversed(leads)))


def test_weights_are_cleaned():
    assert ranking.clean_weights(None) == ranking.DEFAULT_WEIGHTS
    assert ranking.clean_weights({"base": 0, "bonus": 0, "equity": 0, "fit": 0}) == ranking.DEFAULT_WEIGHTS
    assert ranking.clean_weights({"base": 7, "bonus": "x", "equity": -1})["base"] == 1.0
    assert ranking.clean_weights({"base": 7, "bonus": "x", "equity": -1})["equity"] == 0.0


def test_comp_line():
    assert ranking.comp_line({}) == "Pay not posted"
    assert ranking.comp_line({"base": base(250_000, 300_000),
                              "bonus": {"status": "posted", "kind": "annual", "pct_min": 30},
                              "equity": {"status": "mentioned"}}) == "$250K–$300K · 30% bonus · equity"
    assert ranking.comp_line({"base": base(1_200_000, 1_200_000, "EUR")}) == "EUR 1.2M"
    assert ranking.comp_line({"bonus": {"status": "mentioned"},
                              "equity": {"status": "posted", "pct_min": 0.5}}) == "bonus · 0.5% equity"


def test_normalize_helpers():
    assert normalize.dedupe_key("Acme, Inc.", "Chief Operating Officer", "Austin, TX") == \
        normalize.dedupe_key("ACME", "Chief  Operating Officer", "Austin, Texas, United States")
    assert normalize.state_of("Austin, TX") == "TX"
    assert normalize.state_of("Denver, Colorado") == "CO"
    assert normalize.state_of("Boston, MA 02110") == "MA"
    assert normalize.state_of("New York, NY (+2 others)") == "NY"
    assert normalize.state_of("United States") is None and normalize.state_of("") is None
    assert normalize.is_remote("Anywhere") is True
    assert normalize.is_remote("Austin, TX", flag=None) is None
    assert normalize.is_remote(None, flag=True) is True
    assert normalize.http_url("https://example.test/a") == "https://example.test/a"
    for bad in ("javascript:alert(1)", "https://u:p@example.test", "ftp://example.test", 7, "x" * 3000):
        assert normalize.http_url(bad) is None
    assert normalize.host_of("https://WWW.Example.test/x") == "www.example.test"
    assert normalize.posted_age_hours("3 days ago") == 72
    assert normalize.posted_age_hours("30+ days ago") == 720
    assert normalize.posted_age_hours("Just posted") == 0
    assert normalize.posted_age_hours("whenever") is None and normalize.posted_age_hours(None) is None
