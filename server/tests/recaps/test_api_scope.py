from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.matcha_work.recaps import Event, Manifest, Preferences, Scene
from app.matcha.services.matcha_work.recaps import adapters, observe, scope, service, settings, storage, supervisor
from .test_lifecycle import COMPANY, NOW, RECAP, RUN, USER, Conn, row, source, wire


@pytest.mark.asyncio
async def test_preferences_opt_out_cancels_only_unfinished_media(monkeypatch):
    conn=Conn();wire(monkeypatch,service,conn)
    monkeypatch.setattr(settings,"enabled",lambda:True);monkeypatch.setattr(settings,"available",lambda _:True)
    conn.fetchrow.return_value={"enabled":False,"email_enabled":True}
    result=await service.set_preferences(USER,COMPANY,Preferences(enabled=False,email_enabled=True))
    assert result=={"enabled":False,"email_enabled":True,"available":True}
    assert "render_token=NULL" in conn.execute.await_args.args[0]
    assert "'ready'" not in conn.execute.await_args.args[0]
    monkeypatch.setattr(settings,"available",lambda _:False)
    with pytest.raises(HTTPException) as exc:await service.set_preferences(USER,COMPANY,Preferences(enabled=True,email_enabled=True))
    assert exc.value.status_code==503


@pytest.mark.asyncio
async def test_list_detail_playback_and_delete_keep_keys_private(monkeypatch):
    conn=Conn();wire(monkeypatch,service,conn)
    monkeypatch.setattr(settings,"enabled",lambda:True)
    manifest=Manifest(scenes=[Scene(event=Event(title="Safe result",kind="result",occurred_at=NOW),seconds=4)])
    from .test_worker_storage import key
    asset={"key":key(),"bytes":4,"mime":"video/mp4","sha256":"a"*64}
    poster={**asset,"key":key("poster.png"),"mime":"image/png"}
    ready=row(state="ready",manifest=manifest.model_dump(mode="json"),output_manifest={"video":asset,"poster":poster,"duration_ms":4000,"chapters":[]},expires_at=NOW+timedelta(days=30))
    conn.fetch.return_value=[ready]
    page=await service.listing(USER,COMPANY,limit=1)
    assert page["next_cursor"] and "espresso-recaps/" not in str(page)
    await service.listing(USER,COMPANY,limit=1,before=page["next_cursor"])
    assert conn.fetch.await_args.args[-1]==RECAP
    monkeypatch.setattr(service,"owned",AsyncMock(return_value=ready))
    conn.fetch.return_value=[{"kind":"run","run_id":RUN,"task_id":None,"job_search_id":None}]
    detail=await service.detail(USER,COMPANY,RECAP)
    assert detail["sources"]==[{"kind":"run","id":RUN}]
    assert "espresso-recaps/" not in str(detail)
    monkeypatch.setattr(storage,"signed",lambda asset:"https://private.example.com/signed")
    assert (await service.playback(USER,COMPANY,RECAP))["expires_in"]==300
    conn.fetchrow.return_value={"state":"deleted"}
    assert await service.delete(USER,COMPANY,RECAP)=={"deleted":True}
    monkeypatch.setattr(service,"owned",AsyncMock(return_value=row(state="failed")))
    with pytest.raises(HTTPException) as exc:await service.playback(USER,COMPANY,RECAP)
    assert exc.value.status_code==409


@pytest.mark.asyncio
async def test_successful_retry_uses_frozen_manifest_and_one_grant(monkeypatch):
    conn=Conn();wire(monkeypatch,service,conn);conn.fetchval.return_value=True
    monkeypatch.setattr(settings,"available",lambda _:True)
    manifest=Manifest(scenes=[Scene(event=Event(title="Existing result",kind="result",occurred_at=NOW),seconds=4)])
    failed=row(state="failed",manifest=manifest.model_dump(mode="json"))
    monkeypatch.setattr(service,"owned",AsyncMock(return_value=failed))
    conn.fetchrow.return_value={**failed,"state":"queued","manual_retry_request_id":uuid4()}
    await service.retry(USER,COMPANY,RECAP,uuid4())
    assert "manual_retry_request_id=$2" in conn.fetchrow.await_args.args[0]
    assert "manifest=" not in conn.fetchrow.await_args.args[0]


@pytest.mark.asyncio
async def test_phase_runs_bind_only_the_accepted_generation_and_token(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:True)
    conn=Conn();conn.fetchrow.return_value=source()
    token=uuid4()
    owner=SimpleNamespace(kind="job_search",owner_id=uuid4(),recap_generation=2,dispatch_token=token)
    await scope.phase_run(conn,RUN,owner)
    assert conn.fetchrow.await_args.args[1:]==(owner.owner_id,2,token)
    assert "execution_token" in conn.execute.await_args.args[0]
    owner.kind="agent_task";owner.recap_round=3
    await scope.phase_run(conn,RUN,owner)
    assert conn.fetchrow.await_args.args[1:]==(owner.owner_id,3,token)
    conn.fetchval.return_value=None
    assert not await scope.capture_current(conn,source(role="phase"))
    assert await scope.capture_current(conn,source(role="root"))


@pytest.mark.asyncio
async def test_child_registration_inherits_root_and_optional_context_resets(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:True);monkeypatch.setattr(settings,"available",lambda _:True)
    conn=Conn();monkeypatch.setattr(scope,"source_for_run",AsyncMock(return_value=source()))
    conn.fetchrow.return_value={"enabled":True,"email_enabled":True};conn.fetchval.side_effect=[True,"waiting"]
    assert await scope.register(conn,kind="run",source_id=uuid4(),user_id=USER,company_id=COMPANY,title="Continuation",parent_run_id=RUN)==RECAP
    assert any(call.args[5]=="continuation" for call in conn.execute.await_args_list if "INSERT INTO mw_agent_recap_sources" in call.args[0])
    @scope.observe_run
    async def run(ctx):
        assert scope.current_run.get()==RUN
        return "ok"
    assert await run(SimpleNamespace(run_id=RUN))=="ok"
    assert scope.current_run.get() is None


@pytest.mark.asyncio
async def test_job_and_research_registration_use_domain_identity(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:True)
    conn=Conn();conn.fetchval.return_value=2
    register=AsyncMock(return_value=RECAP);monkeypatch.setattr(scope,"register",register)
    search={"id":uuid4(),"user_id":USER,"company_id":COMPANY,"title":"Jobs"}
    await scope.register_job(conn,search)
    assert register.await_args.kwargs["generation"]==2
    await scope.register_task(conn,{**search,"current_round":3})
    assert register.await_args.kwargs["source_id"]==2


@pytest.mark.asyncio
async def test_accepted_outcome_snapshots_are_optional_and_terminal_aware(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:True)
    conn=Conn();conn.fetchrow.return_value=source(kind="jobs")
    snapshot=Event(title="Job result",kind="result",occurred_at=NOW)
    monkeypatch.setattr(adapters,"search_event",AsyncMock(return_value=snapshot))
    record=AsyncMock();monkeypatch.setattr(scope,"event",record)
    await observe.accepted(conn,"mw_job_searches",uuid4(),uuid4(),phase="done",terminal=True)
    assert record.await_args.kwargs["reserve_final"] is True
    assert "semantic_state='terminal'" in conn.execute.await_args.args[0]
    record.reset_mock()
    await observe.accepted(conn,"mw_agent_tasks",uuid4(),uuid4(),phase="discover",terminal=False,retry=True)
    record.assert_not_awaited()
    conn.fetchrow.side_effect=RuntimeError("optional snapshot failed")
    await observe.accepted(conn,"mw_agent_tasks",uuid4(),uuid4(),phase="discover",terminal=False)


@pytest.mark.asyncio
async def test_research_and_jobs_snapshots_preserve_evidence_and_disclosure(monkeypatch):
    conn=Conn()
    from app.matcha.services.matcha_work.agent_tasks.research.contracts import clean_constraint
    constraints = [clean_constraint(raw, today=NOW.date()) for raw in (
        {"field":"price", "op":"lte", "value":3000, "unit":"month", "currency":"USD"},
        {"field":"beds", "op":"gte", "value":2},
    )]
    assert all(constraints) and all("label" not in item for item in constraints)
    conn.fetchrow.return_value={"id":uuid4(),"title":"Apartments","status":"done","recap_status":"done","plan":{"constraints":constraints},"progress":{},"completed_at":NOW}
    conn.fetch.return_value=[{"title":"Building A","subtitle":"Mission","fields":{"rent":{"display":"$2,900/mo","status":"verified"},"pets":{"display":"Allowed","status":"unknown"}},"fit_score":4,"fit_reasons":["Fits budget"]}]
    event=await adapters.search_event(conn,source(kind="research",task_round_id=uuid4()),terminal=True)
    text=event.model_dump_json()
    assert "verified" in text and "unconfirmed" in text and "$2,900/mo" in text
    assert "Price at most $3,000/mo" in text and "Beds at least 2" in text
    conn.fetchrow.return_value={"id":uuid4(),"title":"Jobs","status":"done","criteria":{"titles":["Engineer"],"locations":["SF"],"currency":"USD","base_floor":120000},"progress":{},"completed_at":NOW}
    conn.fetch.return_value=[{"title":"Engineer","company":"Example Labs","comp":{},"comp_status":"not_disclosed","fit_score":4,"fit_reasons":[],"approach_status":"done"}]
    event=await adapters.search_event(conn,source(kind="jobs",job_search_id=uuid4()),terminal=True)
    text=event.model_dump_json()
    assert "Pay not disclosed" in text and "Approach: done" in text and "120000 USD" in text


def test_supervisor_reaps_only_its_owned_descendants(monkeypatch):
    descendants={100:[101],101:[102],102:[]};sent=[]
    monkeypatch.setattr(supervisor,"children",lambda pid:descendants.get(pid,[]))
    monkeypatch.setattr(supervisor.os,"pidfd_open",lambda pid:pid,raising=False)
    monkeypatch.setattr(supervisor.signal,"pidfd_send_signal",lambda fd,_sig:sent.append(fd),raising=False)
    monkeypatch.setattr(supervisor.os,"close",lambda fd:None)
    monkeypatch.setattr(supervisor.os,"waitpid",lambda *args:(0,0))
    monkeypatch.setattr(supervisor.time,"sleep",lambda _:descendants.clear())
    supervisor.stop_owned_children(100)
    assert set(sent)=={101,102} and 100 not in sent
