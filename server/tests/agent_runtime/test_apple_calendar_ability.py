from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work import apple_calendar_service as apple
from app.matcha.services.matcha_work.agent_runtime import runner, result, catalog
from app.matcha.services.matcha_work.agent_runtime.abilities import calendar, apple_calendar
from app.matcha.services.matcha_work.agent_runtime.context import RunState
from app.matcha.services.matcha_work.agent_runtime.registry import offered_tools
from .helpers import context, wire_store, FakeClient, response, call

EVENT = {"id": "apple-e1", "calendar_id": "home", "title": "Private focus", "start": "2026-10-05",
         "end": "2026-10-05", "all_day": True, "notes": None, "location": None, "modified": "v1", "editable": True}


def state():
    return RunState(started=0, sessions={"calendar": calendar.CalendarSession(calendar=None,
        apple_connection=str(uuid4()), apple_events={EVENT["id"]: EVENT})})


def test_apple_tools_need_a_connection_and_do_not_request_fake_google_scopes():
    ability = calendar.build()
    without = offered_tools([ability], last_call=False, hosted_left=0)
    assert not any("apple" in tool.name for tool in without)
    with_apple = offered_tools([ability], last_call=False, hosted_left=0, granted_scopes=frozenset({apple.SCOPE}))
    assert {t.name for t in with_apple if "apple" in t.name} == {"list_apple_events", "create_apple_event", "update_apple_event", "delete_apple_event"}
    situation = catalog.Situation(private=True, grants={"calendar": {}}, granted_scopes=frozenset({apple.SCOPE}))
    available = catalog.availability(ability, situation)
    assert apple.SCOPE not in available.missing_scopes
    assert not catalog.abilities_for([ability], catalog.Situation(private=False, grants={"calendar": {}}))
    assert "through their Mac" in calendar.prompt_block(context(granted_scopes=frozenset({apple.SCOPE})))
    assert "Settings > Calendars" in calendar.prompt_block(context())


def test_writes_freeze_connection_original_event_and_validated_times():
    s = state()
    made = apple_calendar._resolve("create", {"title": "Focus", "start": "2026-10-05", "end": "2026-10-06"}, s)
    assert made["payload"]["fields"]["all_day"] and made["payload"]["fields"]["end"] == "2026-10-06"
    moved = apple_calendar._resolve("update", {"event_id": EVENT["id"], "title": "New title"}, s)
    assert moved["payload"]["event"] == EVENT and moved["payload"]["fields"]["title"] == "New title"
    deleted = apple_calendar._resolve("delete", {"event_id": EVENT["id"]}, s)
    assert deleted["payload"]["fields"] == {}
    assert "Delete Apple Calendar" in apple_calendar._preview(deleted, s)["title"]
    with pytest.raises(ValueError):
        apple_calendar._resolve("create", {"title": "x", "start": "friday"}, s)
    with pytest.raises(ValueError, match="editable"):
        apple_calendar._resolve("update", {"event_id": "unseen"}, s)
    s.sessions["calendar"].apple_events[EVENT["id"]] = {**EVENT, "editable": False}
    with pytest.raises(ValueError, match="invitations"):
        apple_calendar._resolve("delete", {"event_id": EVENT["id"]}, s)
    s.sessions["calendar"].apple_connection = None
    with pytest.raises(ValueError, match="List Apple Calendar"):
        apple_calendar._resolve("create", {}, s)


@pytest.mark.asyncio
async def test_listing_remembers_only_provider_events_and_result_gate_rebuilds_them(monkeypatch):
    now = datetime.now(timezone.utc)
    row = {"connection_id": uuid4(), "calendars": [{"id": "home"}], "snapshot": [EVENT], "synced_at": now,
           "window_start": now-timedelta(days=365), "window_end": now+timedelta(days=365), "complete": True}
    monkeypatch.setattr(apple, "connection", AsyncMock(return_value=row))
    s = state()
    out = await apple_calendar._list(context(), s, {"time_min": "2026-10-01T00:00:00Z", "time_max": "2026-10-10T00:00:00Z"}, 10)
    assert out.payload["events"] == [EVENT]
    block, warnings = calendar.gate_block("events", {"event_ids": [EVENT["id"], "fake"], "title": "Invented"}, s)
    assert block["items"][0]["title"] == EVENT["title"] and block["items"][0]["calendar"] == "apple"
    assert warnings
    monkeypatch.setattr(apple, "connection", AsyncMock(return_value=None))
    assert (await apple_calendar._list(context(), s, {"time_min": "2026-10-01T00:00:00Z", "time_max": "2026-10-10T00:00:00Z"}, 10)).payload["status"] == "not_connected"


@pytest.mark.asyncio
async def test_queue_failure_is_not_reported_as_a_success(monkeypatch):
    monkeypatch.setattr(apple, "enqueue", AsyncMock(side_effect=ValueError("changed")))
    out = await apple_calendar._write(context(), state(), {"connection_id": str(uuid4()), "operation": "delete", "payload": {}}, 10)
    assert out.payload == {"error": "changed"} and out.receipt is None


@pytest.mark.asyncio
async def test_default_preview_context_can_make_calendar_changes_live_and_receipt_stays_queued(monkeypatch):
    _, claim, _ = wire_store(monkeypatch)
    enqueue = AsyncMock(return_value="action-1")
    monkeypatch.setattr(apple, "enqueue", enqueue)
    monkeypatch.setattr(apple_calendar, "_list", AsyncMock())
    ability = calendar.build()
    # The frozen action came from a previous listing, so no provider call is
    # needed to execute it. Only the frozen arguments reach the queue.
    from app.matcha.services.matcha_work.agent_runtime.context import FrozenAction
    from app.matcha.services.matcha_work.agent_runtime.policy import PolicyContext, Grounding
    args = apple_calendar._resolve("create", {"title": "Focus", "start": "2026-10-05", "end": "2026-10-05"}, state())
    frozen = FrozenAction(tool="create_apple_event", args=args, targets=(), preview=apple_calendar._preview(args, state()))
    ctx = context(commit_mode="dry_run", commit_modes={"calendar": "live"}, granted_scopes=frozenset({apple.SCOPE}),
                  policy=PolicyContext(surface="assistant", private_conversation=True, grounding=Grounding()), resume=frozen)
    client = FakeClient([response(call("finish", {"headline": "Queued", "summary": "Waiting for your Mac", "blocks": []}))])
    out = await runner.run_agent(ctx, client=client, abilities=[ability], instructions="sys", first_input=[],
        contract=runner.ResultContract(finish=result.finish_tool([ability]), normalize=lambda raw, state: result.normalize(raw, state, [ability])))
    assert enqueue.await_count == 1 and out.receipts[0]["status"] == "handoff"
    assert claim.await_args.args[6]["mode"] == "live"
