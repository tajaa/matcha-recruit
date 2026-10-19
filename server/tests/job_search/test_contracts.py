"""What the model phases may hand back: ids from the batch, vouched contacts and
emails, answers only to the posting's open questions, links from this run."""
import json

import pytest

from app.matcha.services.matcha_work.job_search import contracts

BATCH = {"J1": "lead-1", "J2": "lead-2"}


def test_plan():
    plan, _ = contracts.normalize_plan({"result": {
        "titles": ["COO", "", " Chief  Operating Officer ", "coo", "x", 7],
        "deal_breakers": ["no relocation"],
        "profile_summary": "Operator.\x07", "weights": {"base": 0.9, "bonus": "high", "equity": 0.7},
        # A plan from before 2026-10-18 had Google Jobs queries: ignored.
        "queries": [{"q": "COO Denver", "location": None}],
    }})
    assert plan["titles"] == ["COO", "Chief Operating Officer"] and plan["profile_summary"] == "Operator."
    assert plan["weights"] == {"base": 0.9, "equity": 0.7} and plan["source"] == "model"
    assert "queries" not in plan and "queries" not in contracts.PLAN_SCHEMA["properties"]
    for bad in ({}, {"result": "x"}, {"result": {"titles": []}}, {"titles": ["x", ""]}):
        with pytest.raises(ValueError):
            contracts.normalize_plan(bad)
    assert "weights" not in contracts.normalize_plan({"result": {"titles": ["COO"], "weights": None}})[0]


def test_discover_keeps_links_the_run_saw():
    seen = {"https://jobs.lever.co/a/1", "https://boards.greenhouse.io/b/jobs/2", "ftp://files.test/x"}
    out, warnings = contracts.normalize_postings({"result": {"postings": [
        {"url": "https://jobs.lever.co/a/1", "title": " Chief People\x07 Officer ", "company": "A", "location": "SD"},
        {"url": "https://jobs.lever.co/a/1", "title": "Again", "company": "A", "location": "SD"},
        {"url": "https://invented.test/job", "title": "CPO", "company": "X", "location": ""},
        {"url": "ftp://files.test/x", "title": "CPO", "company": "X", "location": ""},
        {"url": "https://boards.greenhouse.io/b/jobs/2", "title": "", "company": "B", "location": ""},
        "junk",
    ]}}, citable=seen)
    assert out == {"postings": [{"url": "https://jobs.lever.co/a/1", "title": "Chief People Officer",
                                 "company": "A", "location": "SD"}]}
    assert len(warnings) == 2 and "invented.test" in warnings[0]
    # Nothing current is a fine answer; only untraceable links get a repair.
    assert contracts.normalize_postings({"result": {"postings": []}}, citable=seen) == ({"postings": []}, [])
    with pytest.raises(ValueError, match="exactly as a search"):
        contracts.normalize_postings({"result": {"postings": [{"url": "https://x.test/1", "title": "T"}]}},
                                     citable=seen)
    many = {f"https://jobs.lever.co/a/{i}" for i in range(50)}
    out, _ = contracts.normalize_postings({"result": {"postings": [
        {"url": url, "title": "T", "company": "", "location": ""} for url in sorted(many)]}}, citable=many)
    assert len(out["postings"]) == contracts.MAX_POSTINGS


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


def test_the_answer_comes_flat_wrapped_or_as_json_text():
    """Claude Haiku sent the wrapped `result` as JSON text, and the run failed
    (prod, 2026-10-15..18): every shape a model may send is the same answer."""
    plan = {"titles": ["COO", "Chief Operating Officer"], "deal_breakers": [],
            "profile_summary": "Operator.", "weights": None}
    expected = contracts.normalize_plan({"result": plan})
    assert contracts.normalize_plan(plan) == expected
    assert contracts.normalize_plan({"result": json.dumps(plan)}) == expected
    # A list the model quoted inside the object, read as the list it is.
    assert contracts.normalize_plan({**plan, "titles": json.dumps(plan["titles"])}) == expected
    # The finish tool asks for the fields themselves, not a wrapper.
    assert "titles" in contracts.PLAN_FINISH.parameters["properties"]
    assert "result" not in contracts.APPROACH_FINISH.parameters["properties"]
    with pytest.raises(ValueError, match="not valid JSON"):
        contracts.normalize_plan({"result": "{queries: [COO]"})
    for bad in (["COO"], {"result": ["COO"]}, {"result": "[1, 2]"}):
        with pytest.raises(ValueError, match="must be an object"):
            contracts.normalize_plan(bad)
    # Text that only looks like JSON stays the text it is.
    assert contracts._unquoted("[not json") == "[not json"
    assert contracts._unquoted('"quoted"') == '"quoted"'
    assert contracts._unquoted("[1]") == [1] and contracts._unquoted("7") == "7"
