"""Ranking: posted pay first, never compared across currencies, unposted pay never $0."""
import pytest

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


def test_a_fit_floor_puts_weaker_matches_after_every_strong_one():
    leads = [
        lead("weak-high-pay", {"base": base(400_000, 450_000)}, fit=3),
        lead("strong-unposted", {}, fit=4),
        lead("strong", {"base": base(200_000, 220_000)}, fit=5),
        lead("unscreened", {}, fit=None),
        lead("out", {"base": base(500_000, 600_000)}, fit=4, screen_status="irrelevant"),
    ]
    # No floor (a search from before floors): pay posted outranks fit.
    assert order(leads)[0] == "weak-high-pay"
    ranked = ranking.rank(leads, None, fit_floor=ranking.FIT_FLOOR)
    assert [r.lead_id for r in ranked] == ["strong", "strong-unposted", "unscreened", "weak-high-pay", "out"]
    assert [r.band for r in ranked] == [0, 2, 2, ranking.BELOW_FLOOR_BAND, 9]
    # Widened to 3/5, the 3/5 job ranks with the rest again.
    assert order(leads, fit_floor=ranking.WIDER_FIT_FLOOR)[0] == "weak-high-pay"


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


@pytest.mark.parametrize(("title", "remote"), [
    ("Senior Product Designer (Remote)", True), ("Remote - Product Designer", True),
    ("Product Designer | US Remote", True), ("Product Designer - Remote US", True),
    ("Product Designer, Remote-first", True), ("Support Specialist - Work From Home", True),
    ("Product Designer (Hybrid)", False), ("Product Designer - Hybrid - 3 days in office", False),
    ("Product Designer (Remote or Hybrid)", True),
    # Inside the role, the word is not a tag.
    ("Remote Sensing Analyst", None), ("Hybrid Cloud Engineer", None),
    ("Nurse - Remote Patient Monitoring", None), ("Product Designer", None),
    ("Product Designer (Non-Remote)", None),
])
def test_remote_or_hybrid_in_a_title_counts_only_as_a_tag(title, remote):
    assert normalize.is_remote("Austin, TX", title=title) is remote, title


def test_hybrid_is_not_remote_whatever_the_flag():
    assert normalize.is_remote("New York, NY (Hybrid)", flag=True) is False
    assert normalize.is_remote("New York, NY (Hybrid)") is False
    assert normalize.is_remote("Hybrid or Remote - US", flag=None) is True
    assert normalize.is_remote("Austin, TX", flag=True, title="Designer (Hybrid)") is False
    assert normalize.is_remote("Remote", title="Designer (Hybrid)") is True
    assert normalize.is_remote("Austin, TX (not remote)") is None


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


def test_a_bonus_is_worth_the_base_it_is_paid_on():
    # Seen on dev: with a high bonus weight, $200-275K + 25-35% outranked $500K.
    weights = {"base": 0.9, "bonus": 0.8, "equity": 0.8, "fit": 0.3}
    leads = [
        lead("smaller", {"base": base(200_000, 275_000),
                         "bonus": {"status": "posted", "kind": "annual", "pct_min": 25, "pct_max": 35},
                         "equity": {"status": "mentioned"}}, fit=5),
        lead("larger", {"base": base(500_000, 500_000), "bonus": {"status": "mentioned"}}, fit=4),
    ]
    ranked = ranking.rank(leads, weights)
    assert [r.lead_id for r in ranked] == ["larger", "smaller"]
    smaller = ranked[1].explain["components"]
    assert smaller["bonus"] == round(0.6 * smaller["base"], 4)  # 30% of 50%, scaled by base share


def test_duplicate_postings_under_two_employer_names():
    from app.matcha.services.matcha_work.job_search import normalize

    title = "Senior Vice President and Chief Operating Officer"
    assert normalize.same_posting(title, "Beth Israel Lahey Health", title, "Lahey Clinic Hospital, Inc.")
    assert not normalize.same_posting(title, "Beth Israel Lahey Health", "Chief Operating Officer",
                                      "Lahey Clinic Hospital, Inc.")
    # Sharing only a generic word ("Health", "Group") is not the same employer.
    assert not normalize.same_posting("COO", "Brightline Health", "COO", "Northwind Health")
    assert not normalize.same_posting("COO", "Acme Group", "COO", "Beta Group")
    assert normalize.name_words("Truenorth Executive Search") == {"truenorth"}


def test_same_title_spells_out_abbreviations_and_allows_a_little_more():
    from app.matcha.services.matcha_work.job_search import normalize

    assert normalize.same_title("COO", "Chief Operating Officer")
    assert normalize.same_title("VP of Ops", "Vice President, Operations")
    assert normalize.same_title("Chief Operating Officer - Austin", "Chief Operating Officer")
    assert normalize.same_title("Chief Operating Officer (Remote)", "COO")
    # Real mix-ups from Google Jobs' apply links (2026-10-15 audit).
    assert not normalize.same_title("Founding COO / Head of Operations [Full-Time]",
                                    "Operations Associate / Head of Operations")
    assert not normalize.same_title("Chief of Staff (Executive Office) and VP of Strategy",
                                    "Director, Chief of Staff – R&D")
    assert not normalize.same_title("COO, Chief Operating Officer / President of Operations",
                                    "Divisional President / Chief Credit Officer")
    assert not normalize.same_title("", "COO") and not normalize.same_title("of the", "COO")


def test_same_employer():
    from app.matcha.services.matcha_work.job_search import normalize

    assert normalize.same_employer("Backpack Healthcare", "hellobackpack") is True
    assert normalize.same_employer("Nametag", "Nametag") is True
    assert normalize.same_employer("Flex", "headway") is False
    assert normalize.same_employer("Go Fractional", "lucidcomputing") is False
    # A name with nothing distinctive on its own is compared whole.
    assert normalize.same_employer("BMW Group", "bmwgroup") is True
    assert normalize.same_employer("BMW", "Mini Cooper") is False
    # Nothing to compare: the listing hides the employer, or the source names nobody.
    assert normalize.same_employer("Confidential", "acme") is None
    assert normalize.same_employer("Nametag", "") is None
    assert normalize.named_employer("Confidential Company") == ""
