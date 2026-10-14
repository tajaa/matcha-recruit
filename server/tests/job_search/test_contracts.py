"""What the model phases may hand back: ids from the batch, vouched contacts and
emails, answers only to the posting's open questions, links from this run."""
import pytest

from app.matcha.services.matcha_work.job_search import contracts

BATCH = {"J1": "lead-1", "J2": "lead-2"}


def test_plan():
    plan, _ = contracts.normalize_plan({"result": {
        "queries": [{"q": " Chief  Operating Officer ", "location": "United States"},
                    {"q": "chief operating officer", "location": "United States"},
                    {"q": "COO Denver", "location": "Denver, Colorado"}, {"q": "x"}, "junk"],
        "titles": ["COO", "", "Chief Operating Officer"], "deal_breakers": ["no relocation"],
        "profile_summary": "Operator.\x07", "weights": {"base": 0.9, "bonus": "high", "equity": 0.7},
    }})
    assert plan["queries"] == [{"q": "Chief Operating Officer", "location": "United States"},
                               {"q": "COO Denver", "location": None}]
    assert plan["titles"] == ["COO", "Chief Operating Officer"] and plan["profile_summary"] == "Operator."
    assert plan["weights"] == {"base": 0.9, "equity": 0.7} and plan["source"] == "model"
    for bad in ({}, {"result": "x"}, {"result": {"queries": []}}):
        with pytest.raises(ValueError):
            contracts.normalize_plan(bad)
    assert "weights" not in contracts.normalize_plan({"result": {"queries": [{"q": "COO"}], "weights": None}})[0]


def test_screen():
    verdicts, warnings = contracts.normalize_screen({"result": {"verdicts": [
        {"id": "j1", "relevant": True, "fit": 7, "reasons": ["Right level", "", "SaaS"], "deal_breaker": None},
        {"id": "J2", "relevant": True, "fit": 3, "reasons": ["Ok"], "deal_breaker": "Requires relocation"},
        {"id": "J9", "relevant": True, "fit": 5, "reasons": [], "deal_breaker": None},
        "junk",
    ]}}, BATCH)
    assert verdicts["lead-1"] == {"relevant": True, "fit": 5, "reasons": ["Right level", "SaaS"], "reason": ""}
    # A deal-breaker makes it irrelevant whatever the model said.
    assert verdicts["lead-2"]["relevant"] is False and verdicts["lead-2"]["reason"] == "Requires relocation"
    assert warnings and "J9" in warnings[0]
    with pytest.raises(ValueError, match="2 of 2 are missing"):
        contracts.normalize_screen({"result": {"verdicts": []}}, BATCH)
    one, _ = contracts.normalize_screen({"result": {"verdicts": [
        {"id": "J1", "relevant": False, "fit": True, "reasons": ["Wrong function"], "deal_breaker": None}]}},
        {"J1": "lead-1"})
    assert one["lead-1"] == {"relevant": False, "fit": None, "reasons": ["Wrong function"], "reason": "Wrong function"}


PAGE = "https://acme.test/about/leadership"
QUESTIONS = {"lead-1": [
    {"key": "first_name", "label": "First Name", "kind": "profile"},
    {"key": "resume", "label": "Resume/CV", "kind": "file"},
    {"key": "q_why", "label": "Why do you want to join?", "kind": "open"},
    {"key": "q_auth", "label": "Are you authorized to work in the US?", "kind": "authorization"},
]}


def approach(**over):
    base = {
        "id": "J1", "summary": "Go through the CEO.", "channel": "hiring_manager",
        "steps": ["Apply", "Email the CEO"], "talking_points": ["Scaled ops"], "negotiation": ["Ask for the range"],
        "contacts": [{"name": "Dana Ruiz", "role": "CEO", "source_url": PAGE},
                     {"name": "Made Up", "role": "VP", "source_url": PAGE},
                     {"name": "Sam Lee", "role": "CFO", "source_url": "https://other.test/never-loaded"}],
        "outreach": {"to_email": "Dana@Acme.test", "subject": "COO role", "body": "Hi Dana"},
        "answers": [
            {"question_key": "q_why", "question": "Why?", "answer": "Because."},
            {"question_key": "q_auth", "question": "Authorized?", "answer": "Yes"},
            {"question_key": "first_name", "question": "First", "answer": "Ana"},
            {"question_key": "nope", "question": "?", "answer": "x"},
            {"question_key": None, "question": "Salary expectations?", "answer": "Open."},
        ],
        "cover_letter": "Dear Acme", "sources": [PAGE, "https://made.up/x", PAGE],
    }
    base.update(over)
    return base


def run(*items, emails=frozenset({"dana@acme.test"}), questions=QUESTIONS, user_text=""):
    return contracts.normalize_approaches(
        {"result": {"approaches": list(items)}}, batch=BATCH, questions=questions,
        citable={PAGE}, pages={PAGE: "Our leadership: Dana Ruiz, Chief Executive Officer."},
        observed_emails=set(emails), user_text=user_text,
    )


def test_approach_keeps_only_what_the_run_can_vouch_for():
    out, warnings = run(approach())
    drafted = out["lead-1"]
    assert drafted["contacts"] == [{"name": "Dana Ruiz", "role": "CEO", "source_url": PAGE}]
    assert drafted["outreach"]["to_email"] == "dana@acme.test"
    assert [a["question_key"] for a in drafted["answers"]] == ["q_why"]  # open questions only
    assert {u["question_key"] for u in drafted["unanswered"]} == {"resume", "q_auth"}
    assert drafted["sources"] == [PAGE]
    assert len([w for w in warnings if "contact" in w]) == 2


def test_approach_email_and_likely_answers():
    out, warnings = run(approach(), emails=frozenset())
    assert out["lead-1"]["outreach"]["to_email"] is None and any("address" in w for w in warnings)
    typed, _ = run(approach(), emails=frozenset(), user_text="write to dana@acme.test please")
    assert typed["lead-1"]["outreach"]["to_email"] == "dana@acme.test"
    # No known questions: up to four likely ones, never authorization or demographics.
    likely, _ = run(approach(id="J2", channel="smoke signals", answers=[
        {"question_key": None, "question": f"Q{i}?", "answer": "A"} for i in range(6)
    ] + [{"question_key": None, "question": "Do you require visa sponsorship?", "answer": "No"},
         {"question_key": None, "question": "Gender", "answer": "x"}]))
    drafted = likely["lead-2"]
    assert len(drafted["answers"]) == 4 and all(a["likely"] for a in drafted["answers"])
    assert drafted["channel"] == "apply_portal"
    with pytest.raises(ValueError):
        run(approach(id="J7"))
    with pytest.raises(ValueError):
        contracts.normalize_approaches({"result": {}}, batch=BATCH, questions={}, citable=set(), pages={},
                                       observed_emails=set(), user_text="")
