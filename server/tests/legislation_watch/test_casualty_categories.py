"""Casualty-legislation relevance scoring (tort reform / WC presumption / auto, #3/#24)."""

from app.core.services.rss_parser import score_relevance, RELEVANCE_KEYWORDS


def test_casualty_categories_registered():
    for c in ("tort_reform", "wc_presumption", "auto_liability"):
        assert c in RELEVANCE_KEYWORDS


def test_tort_reform_detected():
    score, cat = score_relevance(
        "Legislature votes to repeal noneconomic damages cap",
        "The bill removes the state's damage cap on noneconomic damages in liability suits.",
    )
    assert cat == "tort_reform" and score >= 0.3


def test_wc_presumption_detected():
    score, cat = score_relevance(
        "Firefighter cancer presumption signed into law",
        "New occupational disease presumption of compensability for first responders.",
    )
    assert cat == "wc_presumption" and score >= 0.3


def test_auto_liability_detected():
    score, cat = score_relevance(
        "Bill raises minimum commercial auto liability limits",
        "Motor carrier liability minimums increase; financial responsibility law updated.",
    )
    assert cat == "auto_liability" and score >= 0.3


def test_labor_categories_still_work():
    _, cat = score_relevance("State minimum wage increase announced", "wage floor rises")
    assert cat == "minimum_wage"


def test_irrelevant_scores_zero():
    score, cat = score_relevance("Governor visits the state fair", "A nice day out.")
    assert score == 0.0 and cat is None
