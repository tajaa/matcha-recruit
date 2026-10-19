"""What the model phases may hand back: ids from the batch, vouched contacts and
emails, answers only to the posting's open questions, links from this run."""
import json

import pytest

from app.matcha.services.matcha_work.agent_runtime import finish
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
    # A posting with no title is still read (the ATS has the title); the invented
    # and the ftp links go, the repeat is kept once.
    assert out == {"postings": [{"url": "https://jobs.lever.co/a/1", "title": "Chief People Officer",
                                 "company": "A", "location": "SD"},
                                {"url": "https://boards.greenhouse.io/b/jobs/2", "title": "", "company": "B",
                                 "location": ""}]}
    assert len(warnings) == 2 and "invented.test" in warnings[0]
    # One traceable posting among untraceable ones is an answer, not a repair.
    out, _ = contracts.normalize_postings({"result": {"postings": [
        {"url": "https://x.test/1", "title": "T"}, {"url": "https://jobs.lever.co/a/1", "title": "T"}]}}, citable=seen)
    assert len(out["postings"]) == 1
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
    # "None" and "N/A" as text are no deal-breaker.
    for word in ("None", "none", "N/A", "null", "No."):
        kept, _ = contracts.normalize_screen({"result": {"verdicts": [
            {"id": "J1", "relevant": True, "fit": 4, "reasons": [], "deal_breaker": word}]}}, {"J1": "lead-1"})
        assert kept["lead-1"]["relevant"] is True and kept["lead-1"]["reason"] == "", word


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


def test_a_contact_is_named_on_the_page_as_a_name():
    page = "Our team: Johnathan Doe (CEO) and Sarah Smithers (CFO). Reach Dana Ruiz, COO."
    out, warnings = contracts.normalize_approaches(
        {"result": {"approaches": [approach(contacts=[
            {"name": "John Smith", "role": "CEO", "source_url": PAGE},  # fragments of two names
            {"name": "Dana Ruiz", "role": "COO", "source_url": PAGE},
            {"name": "Ruiz, Dana", "role": "COO", "source_url": PAGE},  # the words, whole, out of order
        ])]}}, batch=BATCH, questions=QUESTIONS, citable={PAGE}, pages={PAGE: page},
        observed_emails=set(), user_text="")
    assert [c["name"] for c in out["lead-1"]["contacts"]] == ["Dana Ruiz", "Ruiz, Dana"]
    assert any("John Smith" in w for w in warnings)


def test_nested_fields_sent_as_json_text_are_read_or_refused():
    text_fields = approach(
        contacts='[{"name": "Dana Ruiz", "role": "CEO", "source_url": "%s"}]' % PAGE,
        outreach='{"to_email": null, "subject": "COO", "body": "Hi Dana"}',
        answers='[{"question_key": "q_why", "question": "Why?", "answer": "Because."}]',
        steps='["Apply", "Email"]', sources='["%s"]' % PAGE,
    )
    out, _ = run(text_fields)
    drafted = out["lead-1"]
    assert drafted["contacts"][0]["name"] == "Dana Ruiz" and drafted["outreach"]["body"] == "Hi Dana"
    assert [a["question_key"] for a in drafted["answers"]] == ["q_why"] and drafted["steps"] == ["Apply", "Email"]
    assert drafted["sources"] == [PAGE]
    # Text that isn't JSON is refused by field, for the one repair: iterated as
    # characters it used to store an approach with nothing in it.
    with pytest.raises(ValueError, match="`outreach` of J1 came as text"):
        run(approach(outreach="Dear Dana, ..."))
    with pytest.raises(ValueError, match="`contacts` of J1 came as text"):
        run(approach(contacts="Dana Ruiz (CEO)"))


def test_approach_email_and_likely_answers():
    out, warnings = run(approach(), emails=frozenset())
    assert out["lead-1"]["outreach"]["to_email"] is None and any("address" in w for w in warnings)
    typed, _ = run(approach(), emails=frozenset(), user_text="write to dana@acme.test please")
    assert typed["lead-1"]["outreach"]["to_email"] == "dana@acme.test"
    # A typed address is itself: a suffix of one isn't printed anywhere.
    suffix, _ = run(approach(outreach={"to_email": "doe@acme.test", "subject": "s", "body": "b"}), emails=frozenset(),
                    user_text="write to jane.doe@acme.test please")
    assert suffix["lead-1"]["outreach"]["to_email"] is None
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


def test_a_list_sent_as_text_is_refused_by_name():
    """A list sent as JSON that isn't valid (a cover letter's quotes left
    unescaped) was read letter by letter, and the model was told to fix its
    ids: now the repair names the field and says it came as text."""
    broken = '[{"id": "J1", "cover_letter": "I "love" this role"}]'
    with pytest.raises(ValueError, match="`approaches` came as text"):
        contracts.normalize_approaches({"approaches": broken}, batch=BATCH, questions={}, citable=set(),
                                       pages={}, observed_emails=set(), user_text="")
    with pytest.raises(ValueError, match="`verdicts` came as text"):
        contracts.normalize_screen({"verdicts": "[{bad"}, BATCH)
    with pytest.raises(ValueError, match="`postings` came as text"):
        contracts.normalize_postings({"postings": "[{bad"}, citable=set())
    with pytest.raises(ValueError, match="`verdicts` must be a list"):
        contracts.normalize_screen({"verdicts": {"id": "J1"}}, BATCH)
    # Each job sent as its own JSON text is read as the job it is.
    out, _ = run(json.dumps(approach()))
    assert out["lead-1"]["contacts"][0]["name"] == "Dana Ruiz"
    # No postings at all is still a fine answer.
    assert contracts.normalize_postings({}, citable=set()) == ({"postings": []}, [])
    # Ids that aren't the batch's: the repair names the ones to use.
    with pytest.raises(ValueError, match="by its short id: J1, J2"):
        run(approach(id="J7"))
    assert finish.items({}, "approaches") == []

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
    assert finish.unquoted("[not json") == "[not json"
    assert finish.unquoted('"quoted"') == '"quoted"'
    assert finish.unquoted("[1]") == [1] and finish.unquoted("7") == "7"
    # Titles are cleaned the way a typed one is (`titles_in`): one letter isn't one.
    out, _ = contracts.normalize_plan({**plan, "titles": ["C", " COO ", "coo", "Chief\x00 of Staff"]})
    assert out["titles"] == ["COO", "Chief of Staff"]
