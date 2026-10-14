"""Pay parsing: what counts as pay, what never does, and the evidence it keeps."""
import pytest

from app.matcha.services.matcha_work.job_search import comp


def bases(text, **kw):
    return [(f["min"], f["max"], f["period"]) for f in comp.scan_base(text, origin="page", **kw)]


@pytest.mark.parametrize("text, expected", [
    ("150K–200K a year", [(150_000, 200_000, "year")]),
    ("$85–$95 an hour", [(85, 95, "hour")]),
    ("Pay range $180k to $220k", [(180_000, 220_000, "year")]),
    ("Salary up to $200,000 annually", [(200_000, 200_000, "year")]),
    ("Base salary: $275,000.", [(275_000, 275_000, "year")]),
    ("The salary is 150-200K per year", [(150_000, 200_000, "year")]),
    ("$12,500 per month", [(12_500, 12_500, "month")]),
])
def test_base_pay_is_read(text, expected):
    assert bases(text) == expected


@pytest.mark.parametrize("text", [
    "We are a $40M Series B company with $5M ARR. Competitive salary, 401(k) match.",
    "You will manage a $20M budget and a P&L of $500M.",
    "Competitive salary. Budget of $300,000 for tooling.",
    "EBITDA of $150-200M",
    "Grow revenue 25% year over year with a team of 200.",
    "Founded in 2012, we have 450 employees.",
    "USD 210,000–240,000",  # no pay word and no period: not assumed to be pay
    "$85 gift card on your first day",
    "Shifts are 12 hour days.",
    "Competitive salary, 24 hour on-call rotation.",
    "Competitive salary and 401k with match.",
    "Salary competitive; 403(b) and 457(b) plans.",
    "Base pay plus a 401K match.",
])
def test_company_figures_are_never_pay(text):
    assert bases(text) == []


def test_a_known_pay_field_needs_no_pay_word():
    assert bases("USD 210,000–240,000", known_pay=True) == [(210_000, 240_000, "year")]
    # Google's salary field may leave out the currency; free text may not.
    assert bases("85–95 an hour", known_pay=True) == [(85, 95, "hour")]
    assert bases("Pay is 85–95 an hour") == []


@pytest.mark.parametrize("text, expected", [
    ("Competitive salary, plus a bonus of up to 20%.", ("posted", 20, 20)),
    ("Bonus: 20–30% of base", ("posted", 20, 30)),
    ("a bonus of 15% to 25%", ("posted", 15, 25)),
    ("401(k) match of 4% and an annual bonus.", ("mentioned", None, None)),
    ("We offer 15% off at the store and a performance bonus.", ("mentioned", None, None)),
])
def test_a_percentage_is_a_bonus_only_in_its_clause(text, expected):
    [bonus] = comp.scan_bonus(text, origin="page")
    assert (bonus["status"], bonus.get("pct_min"), bonus.get("pct_max")) == expected


def test_budget_right_next_to_an_amount_wins_over_salary_elsewhere():
    text = "Base salary $250,000; you will manage a $900,000 budget."
    assert bases(text) == [(250_000, 250_000, "year")]


def test_evidence_is_a_slice_of_the_text():
    text = "About us. The base salary range is $250,000 - $300,000 per year. Apply now."
    [finding] = comp.scan_base(text, origin="page", url="https://example.test/job")
    quote = finding["evidence"]["quote"]
    assert quote in text and "$250,000" in quote
    assert finding["evidence"] == {"quote": quote, "origin": "page", "url": "https://example.test/job"}
    assert finding["annual_min"] == 250_000 and finding["currency"] == "USD"


def test_bonus_and_equity_percentages_and_mentions():
    text = "Base salary: $275,000. Annual bonus target of 40% of base. Equity: 0.5%-1.0%."
    found = {f["component"]: f for f in comp.scan_text(text, origin="page")}
    assert (found["bonus"]["pct_min"], found["bonus"]["kind"]) == (40, "annual")
    assert (found["equity"]["pct_min"], found["equity"]["pct_max"]) == (0.5, 1.0)
    mentioned = {f["component"]: f["status"] for f in
                 comp.scan_text("Compensation: salary + bonus + equity", origin="page")}
    assert mentioned == {"bonus": "mentioned", "equity": "mentioned"}
    assert comp.scan_text("stock options and RSUs", origin="page")[0]["status"] == "mentioned"
    signing = comp.scan_bonus("Sign-on bonus of 10% available.", origin="page")
    assert signing[0]["kind"] == "signing"


@pytest.mark.parametrize("text", [
    "Our private equity-backed portfolio company seeks a COO.",
    "Diversity, equity and inclusion are core values.",
    "Experience with SaaS is a bonus.",
    "Bonus points for Spanish.",
    "Reports to the CEO; 15% travel.",
    "Pay equity analysis experience required.",
])
def test_things_that_only_look_like_bonus_or_equity(text):
    assert comp.scan_bonus(text, origin="page") == []
    assert comp.scan_equity(text, origin="page") == []


def test_structured_sources():
    [jsonld] = comp.from_jsonld(
        {"@type": "MonetaryAmount", "currency": "USD",
         "value": {"@type": "QuantitativeValue", "minValue": 200000, "maxValue": 260000, "unitText": "YEAR"}},
        url="https://example.test/j",
    )
    assert (jsonld["annual_min"], jsonld["annual_max"], jsonld["evidence"]["origin"]) == (200_000, 260_000, "jsonld")
    assert comp.from_jsonld({"currency": "USD", "value": 55, "unitText": "HOUR"}, url=None)[0]["annual_min"] == 114_400
    assert comp.from_jsonld("not a dict", url=None) == []

    lever = comp.from_lever(
        {"salaryRange": {"min": 180000, "max": 220000, "currency": "USD", "interval": "per-year-salary"},
         "salaryDescriptionPlain": "Plus a 20% annual bonus and stock options."},
        url="https://jobs.lever.co/acme/x",
    )
    kinds = {f["component"]: f for f in lever}
    assert kinds["base"]["evidence"]["origin"] == "ats_api" and kinds["base"]["max"] == 220_000
    assert kinds["bonus"]["pct_min"] == 20 and kinds["equity"]["status"] == "mentioned"

    [gh] = comp.from_greenhouse(
        [{"min_cents": 25000000, "max_cents": 30000000, "currency_type": "USD", "title": "US Base"}],
        url="https://boards.greenhouse.io/acme/jobs/1",
    )
    assert (gh["min"], gh["max"], gh["period"]) == (250_000, 300_000, "year")
    assert comp.from_greenhouse([{"title": "nothing"}, "junk"], url=None) == []

    ashby = comp.from_ashby({"compensationTiers": [{"components": [
        {"compensationType": "Salary", "interval": "1 YEAR", "currencyCode": "USD", "minValue": 240000, "maxValue": 280000},
        {"compensationType": "EquityPercentage", "interval": "NONE", "minValue": 0.5, "maxValue": 1.25},
        {"compensationType": "Bonus", "interval": "1 YEAR", "currencyCode": "USD", "minValue": 50000, "maxValue": 70000},
        {"compensationType": "EquityCashValue", "interval": "4 YEAR", "currencyCode": "USD", "minValue": 400000},
    ]}]}, url="https://jobs.ashbyhq.com/acme/x")
    best = comp.combine(ashby)
    assert best["base"]["annual_max"] == 280_000
    assert best["equity"]["pct_max"] == 1.25  # percent first, the cash value is a fallback
    assert comp.bonus_pct(best) == pytest.approx(23.1, abs=0.1)  # 60K of a 260K midpoint
    assert comp.from_ashby({"compensationTierSummary": "$150K – $180K"}, url=None) == []
    assert comp.from_ashby(None, url=None) == []


def test_combine_prefers_posted_then_the_better_source():
    google = {"component": "base", "status": "posted", "min": 1e5, "max": 1.2e5, "annual_min": 1e5,
              "annual_max": 1.2e5, "currency": "USD", "evidence": {"origin": "google_jobs"}}
    ats_api = dict(google, annual_max=1.3e5, evidence={"origin": "ats_api"})
    mention = {"component": "base", "status": "mentioned", "evidence": {"origin": "ats_api"}}
    assert comp.combine([mention, google])["base"]["evidence"]["origin"] == "google_jobs"
    assert comp.combine([google, ats_api])["base"]["annual_max"] == 1.3e5
    kept = comp.combine([mention], existing={"base": {k: v for k, v in google.items() if k != "component"}})
    assert kept["base"]["status"] == "posted"
    assert comp.comp_status({}) == "not_disclosed"
    assert comp.comp_status({"bonus": {"status": "mentioned"}}) == "mentioned"
    assert comp.comp_status(comp.combine([google])) == "posted"
    assert comp.annual_range({"base": {"status": "mentioned"}}) == (None, None, None)
    signing = {"bonus": {"status": "posted", "kind": "signing", "pct_min": 10}}
    assert comp.bonus_pct(signing) is None


def test_checking_a_claim_against_its_source():
    source = "Compensation\n  The base   salary is $180,000 to $220K per year."
    assert comp.verify_quote("the base salary is $180,000 to $220K", source)
    assert not comp.verify_quote("the base salary is $190,000", source)
    assert not comp.verify_quote("short", source)
    assert comp.numbers_supported([180000, 220000], "$180,000 to $220K")
    assert not comp.numbers_supported([180000, 250000], "$180,000 to $220K")
    assert comp.numbers_supported([None], "anything")


def test_quotes_stop_at_flattened_bullets():
    # Real Google Jobs text (dev, 2026-10-14): a posting's bullet list arrives as one line.
    text = ("Compensation * Competitive Base Salary * Executive Performance Bonus 25%-35% (Based on hitting "
            "performance targets) * Company Equity Participation (for long-term performance) * Full Benefits "
            "Package * On-site leadership role with impact $200,000 - $275,000 a year Actual compensation will "
            "be determined based on job-related factors including experience, education, certifications, "
            "security clearance requirements.")
    found = {f["component"]: f["evidence"]["quote"] for f in comp.scan_text(text, origin="google_jobs")}
    assert found["bonus"] == "Executive Performance Bonus 25%-35% (Based on hitting performance targets)"
    assert found["equity"] == "Company Equity Participation (for long-term performance)"
    assert found["base"].startswith("On-site leadership role with impact $200,000 - $275,000 a year")
    assert len(found["base"]) <= 160 and all(q in text for q in found.values())
