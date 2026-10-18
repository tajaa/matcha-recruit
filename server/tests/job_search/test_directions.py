"""Roles beyond the person's own title: suggested from their résumé, checked
against it word for word, searched, and marked on the jobs found."""
import json
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work.job_search import contracts, model_phases, normalize, prompts, service
from tests.agent_runtime.helpers import FakeConn, call, connection, response

from ._fixtures import SEARCH, USER, lead_row, search_row

RESUME = """Haley Rivera. Full stack engineer, 7 years at startups.
Joined 20+ enterprise customer calls as the technical lead: scoped integrations, wrote solution designs.
Led a 4-engineer platform group; set the architecture review process and mentored two engineers to senior."""

SOLUTIONS = {"title": "Solutions Architect", "why": "You've been the technical lead on 20+ enterprise calls.",
             "evidence": "Joined 20+ enterprise customer calls as the technical lead"}
MANAGER = {"title": "Engineering Manager", "why": "You already lead a platform group.",
           "evidence": "Led a 4-engineer platform   group"}
INVENTED = {"title": "Product Manager", "why": "You've shipped roadmaps.", "evidence": "Owned the product roadmap"}


def test_a_direction_needs_its_evidence_in_the_resume_and_a_new_title():
    kept = contracts.check_directions([SOLUTIONS, MANAGER, INVENTED], RESUME, ["Full Stack Engineer"])
    assert [d["title"] for d in kept] == ["Solutions Architect", "Engineering Manager"]
    # Their own titles aren't suggestions, however they're spelled.
    same = {**SOLUTIONS, "title": "full stack engineer"}
    assert contracts.check_directions([same], RESUME, ["Full Stack Engineer"]) == []
    # No résumé, no suggestions: there is nothing to support them.
    assert contracts.check_directions([SOLUTIONS], None, []) == []
    # Twice is once.
    assert len(contracts.check_directions([SOLUTIONS, SOLUTIONS], RESUME, [])) == 1


def test_the_plan_contract_shapes_directions():
    plan, _ = contracts.normalize_plan({"result": {
        "queries": [{"q": "Full stack engineer SF", "location": None}], "titles": ["Full stack engineer"],
        "deal_breakers": [], "profile_summary": "x", "weights": None,
        "directions": [SOLUTIONS, {"title": " ", "why": "x", "evidence": "y"}, "junk",
                       {**MANAGER, "why": "w" * 400}, INVENTED, {**SOLUTIONS, "title": "Fourth"}],
    }})
    assert [d["title"] for d in plan["directions"]] == ["Solutions Architect", "Engineering Manager", "Product Manager"]
    assert len(plan["directions"][1]["why"]) == 300
    plain, _ = contracts.normalize_plan({"result": {"queries": [{"q": "COO", "location": None}], "titles": [],
                                                    "deal_breakers": [], "profile_summary": "", "weights": None}})
    assert "directions" not in plain


def test_a_job_is_a_direction_only_when_it_is_squarely_that_title():
    directions = [SOLUTIONS, MANAGER]
    own = ["Full Stack Engineer", "Software Engineer"]
    assert contracts.direction_of("Senior Solutions Architect, AI", directions, own) == "Solutions Architect"
    assert contracts.direction_of("Engineering Manager, Platform", directions, own) == "Engineering Manager"
    # One shared word isn't enough, and the same job as one they asked for is theirs.
    assert contracts.direction_of("Solutions Engineer", directions, own) is None
    assert contracts.direction_of("Senior Software Engineer", directions, own) is None
    assert contracts.direction_of("Solutions Architect", [SOLUTIONS], ["Solutions Architect"]) is None
    assert normalize.title_covers("Staff Solutions Architect", "Solutions Architect")
    assert not normalize.title_covers("Architect", "Solutions Architect")
    assert not normalize.title_covers("Senior Engineer", "Engineering Manager")
    assert not normalize.title_covers("Anything", "")


def test_later_phases_are_told_the_directions():
    block = prompts.person_block("roles in CA", {"titles": ["Full stack engineer"]}, RESUME, "An engineer", [SOLUTIONS])
    assert "Also open to (suggested from their résumé):\n- Solutions Architect: You've been" in block
    assert "Also open to" not in prompts.person_block("x", {}, None)
    assert "directions suggested from" in prompts.SCREEN and "Directions (only when a résumé is given" in prompts.PLAN


@pytest.fixture
def conn(monkeypatch):
    # The wiring of test_model_phases' fixture, plus service (the tagging test).
    from uuid import uuid4

    from app.matcha.services.matcha_work.agent_runtime import chain, phase_run
    from app.matcha.services.matcha_work.job_search import agent_phase, phases
    from tests.agent_runtime.helpers import wire_store

    fake = FakeConn()
    for module in (model_phases, agent_phase, phases, phase_run, chain, service):
        monkeypatch.setattr(module, "connection_or_direct", connection(fake))
    wire_store(monkeypatch)
    monkeypatch.setattr(phase_run.store, "mark_run", AsyncMock())
    from app.matcha.services.billing import token_budget_service

    monkeypatch.setattr(token_budget_service, "deduct_tokens", AsyncMock())
    fake.on("INSERT INTO mw_project_agent_runs", uuid4())
    return fake


def _plan_finish(directions):
    from tests.agent_runtime.helpers import FakeClient
    from app.matcha.services.matcha_work.job_search import phases

    result = {"queries": [{"q": f"Full stack engineer SF {i}", "location": None} for i in range(8)],
              "titles": ["Full stack engineer", "Software Engineer", "Platform Engineer"], "deal_breakers": [],
              "profile_summary": "An engineer", "weights": None, "directions": directions}
    client = FakeClient([response(call("finish", {"result": result}))])
    return phases.Deps(client=lambda _model: client, fetch_page=AsyncMock())


@pytest.mark.asyncio
async def test_the_plan_searches_the_directions_its_resume_supports(conn, monkeypatch):
    from app.matcha.services.matcha_work.job_search import phases

    monkeypatch.setattr(model_phases, "load_resume_for_model", AsyncMock(return_value=RESUME))
    search = search_row(status="planning", use_resume=True,
                        criteria=json.dumps({"titles": ["Full stack engineer"], "locations": ["San Francisco, CA"]}))
    await model_phases.plan(search, _plan_finish([SOLUTIONS, INVENTED, MANAGER]), phases.Guard(SEARCH, search["dispatch_token"]))
    plan = json.loads(conn.ran("SET plan = $3::jsonb")[0][2][2])
    assert [d["title"] for d in plan["directions"]] == ["Solutions Architect", "Engineering Manager"]
    queries = [q["q"] for q in plan["queries"]]
    assert len(queries) == 8 and queries[-2:] == ["Solutions Architect San Francisco, CA",
                                                  "Engineering Manager San Francisco, CA"]
    # Among the first titles, which the board and web searches take.
    assert plan["titles"][:4] == ["Full stack engineer", "Software Engineer", "Solutions Architect", "Engineering Manager"]


@pytest.mark.asyncio
async def test_a_direction_the_plan_already_searches_gets_no_second_query(conn, monkeypatch):
    from tests.agent_runtime.helpers import FakeClient
    from app.matcha.services.matcha_work.job_search import phases

    monkeypatch.setattr(model_phases, "load_resume_for_model", AsyncMock(return_value=RESUME))
    result = {"queries": [{"q": "Full stack engineer San Francisco CA", "location": None},
                          {"q": "Solutions Architect San Francisco CA", "location": None}],
              "titles": ["Full stack engineer"], "deal_breakers": [], "profile_summary": "x", "weights": None,
              "directions": [SOLUTIONS, MANAGER]}
    client = FakeClient([response(call("finish", {"result": result}))])
    search = search_row(status="planning", use_resume=True,
                        criteria=json.dumps({"titles": ["Full stack engineer"], "locations": ["San Francisco, CA"]}))
    await model_phases.plan(search, phases.Deps(client=lambda _m: client, fetch_page=AsyncMock()),
                            phases.Guard(SEARCH, search["dispatch_token"]))
    queries = [q["q"] for q in json.loads(conn.ran("SET plan = $3::jsonb")[0][2][2])["queries"]]
    # Solutions Architect was planned already; only the manager gets a query of its own.
    assert queries == ["Full stack engineer San Francisco CA", "Solutions Architect San Francisco CA",
                       "Full stack engineer San Francisco, CA", "Engineering Manager San Francisco, CA"]


@pytest.mark.asyncio
async def test_without_the_resume_there_are_no_directions(conn, monkeypatch):
    from app.matcha.services.matcha_work.job_search import phases

    loader = AsyncMock(return_value=RESUME)
    monkeypatch.setattr(model_phases, "load_resume_for_model", loader)
    search = search_row(status="planning", use_resume=False, criteria=json.dumps({"titles": ["Full stack engineer"]}))
    await model_phases.plan(search, _plan_finish([SOLUTIONS]), phases.Guard(SEARCH, search["dispatch_token"]))
    plan = json.loads(conn.ran("SET plan = $3::jsonb")[0][2][2])
    assert "directions" not in plan and "Solutions Architect" not in plan["titles"]
    assert not loader.await_count


@pytest.mark.asyncio
async def test_found_jobs_are_marked_with_their_direction(conn):
    plan = {"titles": ["Full stack engineer", "Software Engineer", "Solutions Architect"], "directions": [SOLUTIONS]}
    conn.on("FROM mw_job_searches s", search_row(plan=json.dumps(plan)))
    conn.on("FROM mw_job_leads WHERE search_id", [
        lead_row(title="Solutions Architect, AI Platform"), lead_row(title="Senior Software Engineer")])
    out = await service.get_search(SEARCH, USER)
    assert [lead["direction"] for lead in out["leads"]] == ["Solutions Architect", None]
    assert out["plan"]["directions"][0]["why"].startswith("You've been")
    conn.on("FROM mw_job_searches s", search_row())
    assert (await service.get_search(SEARCH, USER))["leads"][0]["direction"] is None
