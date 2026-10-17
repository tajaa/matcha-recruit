import base64
import importlib.util
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.matcha_work.recaps import Cursor, Event, Manifest
from app.matcha.services.matcha_work.recaps import adapters, capture, delivery, observe, reconcile, scope, service, settings, transport
from .test_lifecycle import COMPANY, NOW, RECAP, RUN, USER, Conn, row, source, wire


def test_migration_has_individually_executable_ddl(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/recap01_espresso_task_recaps.py"
    spec = importlib.util.spec_from_file_location("recap_migration", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    statements = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=statements.append))
    migration.upgrade()
    assert len(statements) > 15
    assert all(sql.count("CREATE TABLE") <= 1 for sql in statements)
    assert all(";" not in sql for sql in statements)
    assert any("parent_source_id" in sql and "execution_token" in sql for sql in statements)
    migration.downgrade()
    assert any("DROP COLUMN recap_generation" in sql for sql in statements)


@pytest.mark.asyncio
async def test_flag_off_honors_existing_delivery_ownership(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:False)
    conn=Conn();conn.fetchval.return_value="mw_agent_recaps"
    conn.fetchrow.return_value={"id":uuid4(),"completion_mail_owner":"recap"}
    assert await delivery.own_mail(conn,kind="jobs",source_id=uuid4(),message={"text":"existing result"})
    assert "mail_payload" in conn.execute.await_args.args[0]


@pytest.mark.asyncio
async def test_empty_chat_has_no_completion_email(monkeypatch):
    conn=Conn();wire(monkeypatch,delivery,conn)
    conn.fetchrow.side_effect=[{"recap_id":RECAP,"attempts":1},row(state="skipped",last_error_code="no_useful_evidence",email="owner@example.com",email_enabled=True)]
    conn.fetch.return_value=[]
    send=AsyncMock();monkeypatch.setattr(transport,"send",send)
    await delivery.deliver(uuid4())
    send.assert_not_awaited()
    assert "suppressed" in conn.execute.await_args.args[0]


@pytest.mark.asyncio
async def test_allowlist_removal_never_starts_capture(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:True)
    monkeypatch.setattr(settings,"available",lambda _:False)
    monkeypatch.setattr(capture,"get_settings",lambda:SimpleNamespace(espresso_recaps_capture_enabled=True))
    conn=Conn();wire(monkeypatch,capture,conn)
    monkeypatch.setattr(scope,"source_for_run",AsyncMock(return_value=source()))
    page=SimpleNamespace(context=SimpleNamespace(new_cdp_session=AsyncMock()))
    token=scope.current_run.set(RUN)
    try:
        async with capture.window(page) as window: window.accepted=True
    finally: scope.current_run.reset(token)
    page.context.new_cdp_session.assert_not_awaited()
    conn.fetchval.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiting_round_snapshot_is_closed_before_followup(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:True)
    conn=Conn();conn.fetchrow.return_value=source(kind="research",task_round_id=uuid4())
    snapshot=Event(kind="result",title="Old results",occurred_at=NOW)
    monkeypatch.setattr(adapters,"search_event",AsyncMock(return_value=snapshot))
    record=AsyncMock();monkeypatch.setattr(scope,"event",record)
    await scope.supersede_round(conn,{"id":uuid4(),"current_round":1})
    assert record.await_args.args[3].outcome=="partial"
    assert "semantic_state='terminal'" in conn.execute.await_args.args[0]


@pytest.mark.asyncio
async def test_unknown_action_survives_full_decorative_budget(monkeypatch):
    conn=Conn();conn.fetchrow.return_value={"state":"collecting","event_count":120};conn.fetchval.return_value=uuid4()
    snap=Event(kind="action_resolved",title="Sent email",outcome="unknown",occurred_at=NOW)
    assert await scope.event(conn,source(),"new-unknown",snap)


@pytest.mark.asyncio
async def test_final_manifest_recovers_unknown_actions_beyond_event_budget(monkeypatch):
    conn=Conn();monkeypatch.setattr(observe,"refresh_source",AsyncMock(return_value="terminal"))
    monkeypatch.setattr(settings,"available",lambda _:True)
    phases=[{"snapshot":Event(title=f"Phase {n}",kind="phase_completed",occurred_at=NOW).model_dump(mode="json"),"asset":None} for n in range(120)]
    groups=[{"tool":"send_email","kind":"commit","status":"unknown","mode":"live","queued":None,"count":1,"created_at":NOW}]
    conn.fetch.side_effect=[[source()],phases,groups]
    await reconcile.collect(conn,row(source_completed_at=NOW,finalize_after=NOW-timedelta(seconds=1)))
    freeze=next(c for c in conn.execute.await_args_list if "manifest=$2" in c.args[0])
    manifest=Manifest.model_validate_json(freeze.args[2])
    assert any(event.outcome=="unknown" and event.title=="Sent email" for event in manifest.transcript)
    assert any(scene.event.outcome=="unknown" for scene in manifest.scenes)


def test_storyboard_keeps_every_child_result_and_safe_unknown_action():
    from app.matcha.services.matcha_work.recaps.storyboard import build
    phases=[{"snapshot":Event(title=f"Phase {n}",kind="phase_completed",occurred_at=NOW).model_dump(mode="json")} for n in range(20)]
    results=[{"snapshot":Event(title=title,kind="result",occurred_at=NOW).model_dump(mode="json")} for title in ("Apartments found","Jobs found")]
    unknown={"snapshot":Event(title="Sent email",kind="action_resolved",outcome="unknown",occurred_at=NOW).model_dump(mode="json")}
    manifest=build([*phases,*results,unknown])
    titles={scene.event.title for scene in manifest.scenes}
    assert {"Apartments found","Jobs found","Sent email"} <= titles


@pytest.mark.asyncio
async def test_retry_does_not_spend_grant_while_opted_out(monkeypatch):
    conn=Conn();wire(monkeypatch,service,conn);conn.fetchval.return_value=False
    monkeypatch.setattr(settings,"available",lambda _:True)
    monkeypatch.setattr(service,"owned",AsyncMock(return_value=row(state="failed")))
    with pytest.raises(HTTPException) as exc: await service.retry(USER,COMPANY,RECAP,uuid4())
    assert exc.value.status_code==409
    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw",["2026-10-17T00:00:00","bad!!!","e30",base64.urlsafe_b64encode(json.dumps({"at":"2026-10-17T00:00:00","id":str(uuid4())}).encode()).decode().rstrip("=")])
async def test_invalid_or_naive_cursors_are_422_before_db(raw):
    with pytest.raises(HTTPException) as exc: await service.listing(USER,COMPANY,before=raw)
    assert exc.value.status_code==422


def test_cursor_contains_timestamp_and_tie_breaker():
    cursor=Cursor(at=NOW,id=uuid4())
    assert Cursor.model_validate_json(cursor.model_dump_json())==cursor


def test_saved_calendar_actions_and_apple_handoff_are_truthful():
    step={"tool":"delete_espresso_event","kind":"draft","status":"ok","result":{},"created_at":NOW}
    assert adapters.step_event(step).outcome=="confirmed"
    assert adapters.step_event({**step,"tool":"create_apple_event","kind":"commit","result":{"mode":"live","queued":True}}).outcome=="handoff"
    preview={"lines":[{"label":"Event","value":"Selected meeting"},{"label":"When","value":"2026-11-01T01:30:00-07:00 to 2026-11-01T01:30:00-08:00"},{"label":"Notifies","value":"private@example.com"}]}
    event=adapters.step_event({**step,"tool":"update_event","kind":"commit","result":{"mode":"live","preview":preview}})
    assert "Selected meeting" in event.model_dump_json() and "-07:00" in event.model_dump_json() and "-08:00" in event.model_dump_json()
    assert "private@example.com" not in event.model_dump_json()


def test_media_settings_need_no_provider_or_auth_secrets(monkeypatch):
    import app.config as config
    with monkeypatch.context() as env:
        for key in ("LIVE_API","OPENAI_API_KEY","ANTHROPIC_API_KEY","JWT_SECRET_KEY","CHAT_JWT_SECRET_KEY"):
            env.delenv(key,raising=False)
        env.setenv("DATABASE_URL","postgresql://test:test@localhost/test")
        env.setenv("S3_PRIVATE_BUCKET","private")
        env.setenv("ESPRESSO_RECAPS_WORKER","1")
        previous=config._settings
        try:
            value=config.load_settings()
            assert value.gemini_api_key is None and value.openai_api_key is None and value.anthropic_api_key is None
            assert value.s3_private_bucket=="private"
        finally: config._settings=previous
