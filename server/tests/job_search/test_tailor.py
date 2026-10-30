"""A résumé tailored to one job: the checks that keep it true, the ask, the run."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_runtime import phase_run, runner
from app.matcha.services.matcha_work.job_search import contracts, service, tailor
from app.matcha.services.matcha_work.job_search.service import JobSearchError
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import COMPANY, LEAD, SEARCH, USER, lead_row, search_row

RESUME = """Jane Doe
Operations Director, Acme Logistics, 2019 - 2024
- Ran a 40-person warehouse team across 3 sites.
- Cut shipping costs by 18% by renegotiating carrier contracts.
- Rolled out a new inventory system to every site.
Operations Manager, Beta Freight, 2015 - 2019
- Managed vendor relationships and quarterly business reviews.
Skills: Lean, SAP, vendor negotiation, Excel
Education
- MBA, State University, 2014
"""

POSTING = "We need a COO who has run multi-site operations and negotiated with carriers. " * 4


def _good(**over):
    answer = {
        "summary": {"text": "Operations leader who has run multi-site warehouse teams.",
                    "sources": ["Ran a 40-person warehouse team across 3 sites."]},
        "experience": [
            {"role": "Operations Director", "organization": "Acme Logistics", "dates": "2019 - 2024", "bullets": [
                {"text": "Cut carrier costs 18% by renegotiating contracts.",
                 "sources": ["Cut shipping costs by 18% by renegotiating carrier contracts."]},
                {"text": "Led a 40-person team across 3 warehouse sites.",
                 "sources": ["Ran a 40-person warehouse team across 3 sites."]},
            ]},
        ],
        "skills": ["vendor negotiation", "SAP"],
        "sections": [{"heading": "Education", "lines": [
            {"text": "MBA, State University, 2014", "sources": ["MBA, State University, 2014"]},
        ]}],
        "changes": ["Put the carrier negotiation first: the posting asks for it."],
        "gaps": ["The posting asks for P&L ownership; your résumé doesn't mention it."],
    }
    answer.update(over)
    return answer


# ── the checks ───────────────────────────────────────────────────────────────

def test_a_number_must_match_exactly_not_nearly():
    # The pay check's 0.5% leeway would pass 2009 for 2015 and 1,000 for 995.
    for text in ("Ran a 40-person warehouse team since 2009.", "Ran a 41-person warehouse team across 3 sites.",
                 "Ran a forty-five person warehouse team across 3 sites.",
                 "Ran a 40-person warehouse team across three sites, doubled.",
                 "Ran a 40-person warehouse team across five sites."):
        line, why = contracts._line({"text": text, "sources": ["Ran a 40-person warehouse team across 3 sites."]}, RESUME)
        assert line is None and "number" in why, text
    line, _ = contracts._line({"text": "Ran a 40-person warehouse team across three sites.",
                               "sources": ["Ran a 40-person warehouse team across 3 sites."]}, RESUME)
    assert line is not None


def test_a_line_must_be_made_of_its_sources():
    source = ["Ran a 40-person warehouse team across 3 sites."]
    for text, why in (
        ("Led the Snowflake migration across 3 sites.", "Snowflake"),
        ("Owned the AWS warehouse team across 3 sites.", "AWS"),
        ("Architected distributed streaming platforms company-wide.", "words"),
    ):
        line, said = contracts._line({"text": text, "sources": source}, RESUME)
        assert line is None and why in said, text
    # A few words found anywhere in the résumé are no source.
    line, said = contracts._line({"text": "Led the team.", "sources": ["warehouse team"]}, RESUME)
    assert line is None and "word for word" in said


def test_a_summary_needs_sources():
    result, warnings = contracts.normalize_tailored(_good(summary={
        "text": "Award-winning operations executive.", "sources": [],
    }), resume=RESUME)
    assert result["summary"] == {"text": "", "sources": []} and result["dropped"] == 1
    assert "names no résumé line" in warnings[0]


def test_skills_and_titles_match_whole_words():
    resume = RESUME + "Known for excellent, scalable work under state laws.\n"
    result, _ = contracts.normalize_tailored(_good(skills=["Excel", "Scala", "AWS", "SAP"]), resume=resume)
    assert result["skills"] == ["Excel", "SAP"]  # Excel from its Skills line, not "excellent"
    result, _ = contracts.normalize_tailored(_good(skills=["Scala", "AWS"]), resume=resume.replace("Excel", ""))
    assert result["skills"] == []


def test_a_role_is_read_where_the_resume_writes_it():
    # A title from one job put with another employer keeps only what is written together.
    result, warnings = contracts.normalize_tailored(_good(experience=[
        {"role": "Operations Director", "organization": "Beta Freight", "dates": "2015 - 2019", "bullets": [
            {"text": "Managed vendor relationships and business reviews.",
             "sources": ["Managed vendor relationships and quarterly business reviews."]}]},
    ]), resume=RESUME)
    [role] = result["experience"]
    assert (role["role"], role["organization"], role["dates"]) == ("", "Beta Freight", "2015 - 2019")
    assert any("Operations Director" in w for w in warnings)


def test_a_line_cannot_move_under_another_job():
    result, warnings = contracts.normalize_tailored(_good(experience=[
        {"role": "Operations Director", "organization": "Acme Logistics", "dates": "", "bullets": [
            {"text": "Led a 40-person team across 3 warehouse sites.",
             "sources": ["Ran a 40-person warehouse team across 3 sites."]}]},
        {"role": "Operations Manager", "organization": "Beta Freight", "dates": "", "bullets": [
            {"text": "Cut carrier costs 18% by renegotiating contracts.",
             "sources": ["Cut shipping costs by 18% by renegotiating carrier contracts."]},
            {"text": "Managed vendor relationships and business reviews.",
             "sources": ["Managed vendor relationships and quarterly business reviews."]}]},
    ]), resume=RESUME)
    assert [b["text"] for b in result["experience"][1]["bullets"]] == ["Managed vendor relationships and business reviews."]
    assert result["dropped"] == 1


def test_a_true_rewrite_is_kept_whole():
    result, warnings = contracts.normalize_tailored(_good(), resume=RESUME)
    assert warnings == [] and result["dropped"] == 0
    [role] = result["experience"]
    assert role["role"] == "Operations Director" and len(role["bullets"]) == 2
    assert result["skills"] == ["vendor negotiation", "SAP"]
    assert result["sections"][0]["lines"][0]["text"] == "MBA, State University, 2014"
    assert result["gaps"] and result["changes"] and result["summary"]["text"]


def test_a_line_with_a_number_its_sources_lack_is_dropped():
    bullets = [
        {"text": "Cut carrier costs 25% by renegotiating contracts.",
         "sources": ["Cut shipping costs by 18% by renegotiating carrier contracts."]},
        {"text": "Led a 40-person team.", "sources": ["Ran a 40-person warehouse team across 3 sites."]},
    ]
    result, warnings = contracts.normalize_tailored(_good(experience=[
        {"role": "Operations Director", "organization": "Acme Logistics", "dates": "", "bullets": bullets},
    ]), resume=RESUME)
    assert [b["text"] for b in result["experience"][0]["bullets"]] == ["Led a 40-person team."]
    assert result["dropped"] == 1 and "number" in warnings[0]


def test_a_line_whose_source_is_not_in_the_resume_is_dropped():
    bullets = [
        {"text": "Owned a $5M P&L.", "sources": ["Owned the P&L for the region."]},
        {"text": "Rolled out new inventory software everywhere.",
         "sources": ["Rolled out a new inventory system to every site."]},
    ]
    result, warnings = contracts.normalize_tailored(_good(experience=[
        {"role": "Operations Director", "organization": "Acme Logistics", "dates": "2019 - 2024", "bullets": bullets},
    ]), resume=RESUME)
    assert [b["text"] for b in result["experience"][0]["bullets"]] == ["Rolled out new inventory software everywhere."]
    assert "word for word" in warnings[0]


def test_a_role_employer_or_skill_not_written_in_the_resume_is_left_out():
    experience = [
        {"role": "Chief Operating Officer", "organization": "Acme Logistics", "dates": "2018 - 2024", "bullets": [
            {"text": "Led a 40-person team.", "sources": ["Ran a 40-person warehouse team across 3 sites."]}]},
        {"role": "VP", "organization": "Gamma Corp", "dates": "", "bullets": [
            {"text": "Managed vendors.", "sources": ["Managed vendor relationships and quarterly business reviews."]}]},
    ]
    result, warnings = contracts.normalize_tailored(
        _good(experience=experience, skills=["SAP", "Kubernetes"]), resume=RESUME,
    )
    # The made-up title and dates are blanked; the role at an employer it never named goes.
    assert result["experience"] == [{"role": "", "organization": "Acme Logistics", "dates": "", "bullets": [
        {"text": "Led a 40-person team.", "sources": ["Ran a 40-person warehouse team across 3 sites."]}]}]
    assert result["dropped"] == 1
    assert result["skills"] == ["SAP"]
    assert any("Kubernetes" in w for w in warnings)


def test_a_summary_it_cannot_trace_is_dropped_not_the_resume():
    result, _ = contracts.normalize_tailored(_good(summary={
        "text": "Operator with 15 years of experience.", "sources": ["Ran a 40-person warehouse team across 3 sites."],
    }), resume=RESUME)
    assert result["summary"] == {"text": "", "sources": []} and result["dropped"] == 1
    assert result["experience"]


def test_nothing_traceable_gets_the_model_one_repair():
    with pytest.raises(ValueError, match="sources"):
        contracts.normalize_tailored(_good(experience=[
            {"role": "Operations Director", "organization": "Acme Logistics", "dates": "", "bullets": [
                {"text": "Did great things.", "sources": ["Did great things at work."]}]},
        ]), resume=RESUME)


def test_lists_sent_as_json_text_are_read():
    args = _good()
    args["experience"] = json.dumps(args["experience"])
    result, _ = contracts.normalize_tailored(args, resume=RESUME)
    assert len(result["experience"][0]["bullets"]) == 2


# ── the views ────────────────────────────────────────────────────────────────

def test_plain_text_follows_the_page():
    result, _ = contracts.normalize_tailored(_good(), resume=RESUME)
    text = tailor.as_text(result)
    assert text.startswith("SUMMARY\nOperations leader")
    assert "EXPERIENCE\nOperations Director — Acme Logistics (2019 - 2024)\n• Cut carrier costs 18%" in text
    assert "SKILLS\nvendor negotiation, SAP" in text and "EDUCATION\n• MBA" in text


def test_a_run_that_died_reads_failed():
    now = datetime.now(timezone.utc)
    assert tailor.status_of({"resume_status": "drafting", "resume_requested_at": now}) == "drafting"
    old = now - timedelta(minutes=tailor.STALE_MINUTES + 1)
    assert tailor.status_of({"resume_status": "drafting", "resume_requested_at": old}) == "failed"
    # Waiting behind other work in the queue isn't dying.
    assert tailor.status_of({"resume_status": "queued", "resume_requested_at": old}) == "queued"
    older = now - timedelta(minutes=tailor.QUEUED_STALE_MINUTES + 1)
    assert tailor.status_of({"resume_status": "queued", "resume_requested_at": older}) == "failed"
    assert tailor.status_of({"resume_status": "queued", "resume_requested_at": None}) == "failed"
    assert tailor.status_of({"resume_status": "done", "resume_requested_at": old}) == "done"
    assert tailor.status_of({}) == "none"


def test_the_job_keeps_its_last_tailored_resume():
    result, _ = contracts.normalize_tailored(_good(), resume=RESUME)
    done = lead_row(resume_status="done", resume_tailored=json.dumps(result))
    detail = service.lead_detail(done)
    assert detail["resume_status"] == "done"
    assert detail["tailored_resume"]["experience"] and detail["tailored_resume"]["text"].startswith("SUMMARY")
    assert service.lead_detail(lead_row())["tailored_resume"] is None
    assert service.lead_summary(lead_row())["resume_status"] == "none"
    # A failed "Tailor again" leaves the last good one to read.
    failed = service.lead_detail(lead_row(resume_status="failed", resume_tailored=json.dumps(result)))
    assert failed["resume_status"] == "failed" and failed["tailored_resume"]["experience"]


# ── asking for one ───────────────────────────────────────────────────────────

CLIENT = SimpleNamespace(id=USER, role="client")
ADMIN = SimpleNamespace(id=USER, role="admin")


@pytest.fixture
def gates(monkeypatch):
    from app.core.services import redis_cache
    from app.matcha.services.billing import entitlements_service, token_budget_service

    seen = SimpleNamespace(plan=AsyncMock(return_value="pro"), rate=AsyncMock(), budget=AsyncMock(),
                           dispatch=Mock())
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", seen.plan)
    monkeypatch.setattr(redis_cache, "check_rate_limit", seen.rate)
    monkeypatch.setattr(token_budget_service, "check_token_budget", seen.budget)
    from app.workers.tasks import job_search as task_module

    monkeypatch.setattr(task_module.tailor_job_resume, "apply_async", seen.dispatch)
    monkeypatch.setattr(tailor, "has_resume", AsyncMock(return_value=True))
    seen.allowed = AsyncMock(return_value=True)
    monkeypatch.setattr(tailor, "_allowed", seen.allowed)
    return seen


def _conn(monkeypatch, lead, updated=None):
    conn = (FakeConn()
            .on("JOIN mw_job_searches s", {**lead, "search_company_id": COMPANY} if lead else None)
            .on("FOR UPDATE", lead)
            .on("SET resume_status = 'queued'", lambda lead_id, token: {**lead, "resume_status": "queued",
                                                                         "resume_token": token,
                                                                         "resume_requested_at": datetime.now(timezone.utc)})
            .on("resume_token = NULL", updated))
    monkeypatch.setattr(tailor, "connection_or_direct", connection(conn))
    return conn


@pytest.mark.asyncio
async def test_asking_queues_the_job_and_dispatches_its_run(monkeypatch, gates):
    conn = _conn(monkeypatch, lead_row(description=POSTING))
    out = await tailor.request(CLIENT, SEARCH, LEAD)
    assert out["resume_status"] == "queued"
    [(_m, _q, (lead_id, token))] = conn.ran("SET resume_status = 'queued'")
    assert lead_id == LEAD
    gates.dispatch.assert_called_once()
    assert gates.dispatch.call_args.kwargs["args"] == [str(LEAD), str(token)]
    gates.rate.assert_awaited_once()
    assert gates.rate.await_args.args[1:] == ("espresso_job_resume_tailor", tailor.HOURLY_LIMIT, 3600)
    gates.budget.assert_awaited_once()
    assert gates.budget.await_args.args == (COMPANY,)
    gates.allowed.assert_awaited_once_with(USER, COMPANY)


@pytest.mark.asyncio
async def test_without_consent_nothing_is_sent(monkeypatch, gates):
    gates.allowed.return_value = False
    conn = _conn(monkeypatch, lead_row(description=POSTING))
    with pytest.raises(JobSearchError) as err:
        await tailor.request(ADMIN, SEARCH, LEAD)
    assert err.value.code == 403 and err.value.detail["code"] == "job_search_off"
    assert not conn.ran("SET resume_status = 'queued'")
    gates.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_asking_again_while_it_runs_spends_nothing(monkeypatch, gates):
    running = lead_row(description=POSTING, resume_status="drafting", resume_requested_at=datetime.now(timezone.utc))
    conn = _conn(monkeypatch, running)
    out = await tailor.request(CLIENT, SEARCH, LEAD)
    assert out["resume_status"] == "drafting"
    assert not conn.ran("SET resume_status = 'queued'")
    gates.rate.assert_not_awaited()
    gates.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_a_run_that_died_can_be_asked_again(monkeypatch, gates):
    stale = lead_row(description=POSTING, resume_status="drafting",
                     resume_requested_at=datetime.now(timezone.utc) - timedelta(hours=1))
    _conn(monkeypatch, stale)
    assert (await tailor.request(CLIENT, SEARCH, LEAD))["resume_status"] == "queued"
    gates.dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_refusals_spend_nothing(monkeypatch, gates):
    _conn(monkeypatch, lead_row(description="Short."))
    with pytest.raises(JobSearchError) as err:
        await tailor.request(CLIENT, SEARCH, LEAD)
    assert err.value.code == 409 and err.value.detail["code"] == "posting_unread"

    _conn(monkeypatch, lead_row(description=POSTING))
    monkeypatch.setattr(tailor, "has_resume", AsyncMock(return_value=False))
    with pytest.raises(JobSearchError) as err:
        await tailor.request(CLIENT, SEARCH, LEAD)
    assert err.value.code == 422 and err.value.detail["code"] == "resume_required"

    _conn(monkeypatch, None)
    with pytest.raises(JobSearchError) as err:
        await tailor.request(CLIENT, SEARCH, LEAD)
    assert err.value.code == 404
    gates.rate.assert_not_awaited()
    gates.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_it_needs_pro_but_an_admin_passes_every_gate(monkeypatch, gates):
    from fastapi import HTTPException

    gates.plan.return_value = "lite"
    _conn(monkeypatch, lead_row(description=POSTING))
    with pytest.raises(HTTPException) as err:
        await tailor.request(CLIENT, SEARCH, LEAD)
    assert err.value.status_code == 403 and err.value.detail["feature"] == "job_search"
    assert (await tailor.request(ADMIN, SEARCH, LEAD))["resume_status"] == "queued"
    gates.rate.assert_not_awaited()
    gates.budget.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_broker_that_is_down_fails_it_and_says_so(monkeypatch, gates):
    conn = _conn(monkeypatch, lead_row(description=POSTING))
    gates.dispatch.side_effect = RuntimeError("broker down")
    with pytest.raises(JobSearchError) as err:
        await tailor.request(CLIENT, SEARCH, LEAD)
    assert err.value.code == 503
    [(_m, _q, args)] = conn.ran("resume_token = NULL")
    assert args[2] == "failed"


# ── the run ──────────────────────────────────────────────────────────────────

def _owner():
    return phase_run.RunOwner(
        kind="job_search", fk_column="job_search_id", owner_id=SEARCH, user_id=USER, company_id=uuid4(),
        model="claude-haiku-5-5", usage_feature="x", storage_prefix="x", surface="job_search",
        account=AsyncMock(), dispatch_token=uuid4(), recap_generation=3,
    )


def _run_conn(monkeypatch, claimed=True, search=True):
    claim = {"id": LEAD, "search_id": SEARCH, "user_id": USER, "title": "COO", "company": "Acme",
             "location": "Austin, TX", "description": POSTING, "highlights": "[]"} if claimed else None
    conn = (FakeConn()
            .on("SET resume_status = 'drafting'", claim)
            .on("FROM mw_job_searches WHERE id = $1", search_row() if search else None)
            .on("resume_token = NULL", LEAD))
    monkeypatch.setattr(tailor, "connection_or_direct", connection(conn))
    monkeypatch.setattr(tailor, "run_owner", AsyncMock(return_value=_owner()))
    monkeypatch.setattr(tailor, "load_resume", AsyncMock(return_value=(RESUME, datetime(2026, 10, 1, tzinfo=timezone.utc))))
    monkeypatch.setattr(tailor, "_allowed", AsyncMock(return_value=True))
    return conn


@pytest.mark.asyncio
async def test_the_run_keeps_what_checks_out_and_never_touches_the_recap(monkeypatch):
    conn = _run_conn(monkeypatch)
    seen = {}

    async def fake_run(owner, **kwargs):
        seen["owner"], seen["kwargs"] = owner, kwargs
        result, _ = kwargs["contract"].normalize(_good(), None)
        return runner.RunOutcome(kind="result", result=result)

    monkeypatch.setattr(tailor.phase_run, "run_model_phase", fake_run)
    token = uuid4()
    await tailor.run(LEAD, token)
    assert seen["owner"].dispatch_token is None and seen["owner"].recap_generation is None
    assert seen["kwargs"]["abilities"] == () and seen["kwargs"]["phase"] == "tailor_resume"
    assert "<resume>" in seen["kwargs"]["user_text"] and "multi-site operations" in seen["kwargs"]["user_text"]
    [(_m, claim, _a)] = conn.ran("SET resume_status = 'drafting'")
    assert "resume_requested_at = NOW()" in claim  # the stale clock starts when the worker does
    [(_m, _q, (lead_id, written_token, status, tailored))] = conn.ran("resume_token = NULL")
    assert (lead_id, written_token, status) == (LEAD, token, "done")
    stored = json.loads(tailored)
    assert stored["experience"][0]["bullets"] and stored["resume_saved_at"].startswith("2026-10-01")


@pytest.mark.asyncio
async def test_a_run_with_nothing_traceable_is_failed(monkeypatch):
    conn = _run_conn(monkeypatch)
    monkeypatch.setattr(tailor.phase_run, "run_model_phase", AsyncMock(side_effect=runner.AgentRunError("no")))
    await tailor.run(LEAD, uuid4())
    [(_m, _q, args)] = conn.ran("resume_token = NULL")
    assert args[2] == "failed" and args[3] is None


@pytest.mark.asyncio
async def test_any_other_failure_is_failed_too(monkeypatch):
    conn = _run_conn(monkeypatch)
    monkeypatch.setattr(tailor.phase_run, "run_model_phase", AsyncMock(side_effect=RuntimeError("boom")))
    await tailor.run(LEAD, uuid4())
    assert conn.ran("resume_token = NULL")[0][2][2] == "failed"


@pytest.mark.asyncio
async def test_a_duplicate_or_replaced_run_does_nothing(monkeypatch):
    conn = _run_conn(monkeypatch, claimed=False)
    model = AsyncMock()
    monkeypatch.setattr(tailor.phase_run, "run_model_phase", model)
    await tailor.run(LEAD, uuid4())
    model.assert_not_awaited()
    assert not conn.ran("resume_token = NULL")


@pytest.mark.asyncio
async def test_a_resume_removed_since_fails_it(monkeypatch):
    conn = _run_conn(monkeypatch)
    monkeypatch.setattr(tailor, "load_resume", AsyncMock(return_value=None))
    model = AsyncMock()
    monkeypatch.setattr(tailor.phase_run, "run_model_phase", model)
    await tailor.run(LEAD, uuid4())
    model.assert_not_awaited()
    assert conn.ran("resume_token = NULL")[0][2][2] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("why", ["search deleted", "consent withdrawn"])
async def test_a_run_that_may_no_longer_go_ahead_is_failed(monkeypatch, why):
    conn = _run_conn(monkeypatch, search=why != "search deleted")
    if why == "consent withdrawn":
        monkeypatch.setattr(tailor, "_allowed", AsyncMock(return_value=False))
    model = AsyncMock()
    monkeypatch.setattr(tailor.phase_run, "run_model_phase", model)
    await tailor.run(LEAD, uuid4())
    model.assert_not_awaited()
    assert conn.ran("resume_token = NULL")[0][2][2] == "failed"


@pytest.mark.asyncio
async def test_allowed_needs_the_workspace_and_the_consent(monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime import enqueue as runtime_enqueue
    from app.matcha.services.matcha_work.job_search import enqueue

    monkeypatch.setattr(runtime_enqueue, "workspace_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(enqueue, "consent_granted", AsyncMock(return_value=True))
    assert await tailor._allowed(USER, COMPANY)
    monkeypatch.setattr(enqueue, "consent_granted", AsyncMock(return_value=False))
    assert not await tailor._allowed(USER, COMPANY)
    monkeypatch.setattr(runtime_enqueue, "workspace_enabled", AsyncMock(return_value=False))
    assert not await tailor._allowed(USER, COMPANY)


@pytest.mark.asyncio
async def test_has_resume_asks_only_whether_there_is_text(monkeypatch):
    conn = FakeConn().on("FROM user_resumes", True)
    monkeypatch.setattr(tailor, "connection_or_direct", connection(conn))
    assert await tailor.has_resume(USER) is True
    [(method, query, _a)] = conn.ran("FROM user_resumes")
    assert method == "fetchval" and "raw_text, updated_at" not in query


@pytest.mark.asyncio
async def test_load_resume_reads_the_whole_text(monkeypatch):
    saved = datetime(2026, 10, 1, tzinfo=timezone.utc)
    conn = FakeConn().on("FROM user_resumes", {"raw_text": "  x" * 9000, "updated_at": saved})
    monkeypatch.setattr(tailor, "connection_or_direct", connection(conn))
    text, when = await tailor.load_resume(USER)
    assert len(text) == tailor.RESUME_CHARS and when == saved
    monkeypatch.setattr(tailor, "connection_or_direct", connection(FakeConn().on("FROM user_resumes", {"raw_text": " ", "updated_at": saved})))
    assert await tailor.load_resume(USER) is None
    monkeypatch.setattr(tailor, "connection_or_direct", connection(FakeConn()))
    assert await tailor.load_resume(USER) is None
