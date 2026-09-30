from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.project_agent import store

from .helpers import FakeConn, connection


@pytest.mark.asyncio
async def test_a_claim_is_written_as_claimed_and_resolved_only_once(monkeypatch):
    step_id = uuid4()
    conn = FakeConn([("INSERT INTO mw_project_agent_steps", step_id)])
    monkeypatch.setattr(store, "connection_or_direct", connection(conn))
    run = uuid4()
    assert await store.claim_step(run, 3, "send_email", "commit", "Send an email",
                                  {"to": ["a@example.com"]}, {"mode": "live"}) == step_id
    insert = conn.ran("INSERT INTO mw_project_agent_steps")[0]
    assert "'claimed'" in insert[1] and "RETURNING id" in insert[1]
    assert insert[2][:5] == (run, 3, "send_email", "commit", "Send an email")
    assert insert[2][5] == '{"to": ["a@example.com"]}'

    await store.resolve_step(step_id, status="unknown", result={"error": "no answer"})
    update = conn.ran("UPDATE mw_project_agent_steps")[0]
    # Only a claim still open is resolved: a second resolve changes nothing.
    assert "status = 'claimed'" in update[1] and "resolved_at = NOW()" in update[1]
    assert update[2] == (step_id, "unknown", '{"error": "no answer"}')
    await store.resolve_step(step_id, status="ok", result=None)
    assert conn.ran("UPDATE mw_project_agent_steps")[1][2][2] == "{}"


@pytest.mark.asyncio
async def test_history_shows_where_each_assistant_run_got_to(monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime import chat_progress
    from app.werk.routes import channels

    run, channel = uuid4(), uuid4()
    conn = FakeConn([
        ("FROM mw_project_agent_runs", [{"id": run, "status": "done", "error": None}]),
        ("FROM mw_project_agent_steps", []),
    ])
    messages = [{"id": 1, "metadata": {"kind": "agent_progress", "run_id": str(run)}}]
    out = await channels._resolve_assistant_run_states(conn, messages, channel_id=channel)
    assert out[0]["metadata"]["progress"]["status"] == "done"

    async def broken(*_a, **_k):
        raise RuntimeError("overlay down")

    monkeypatch.setattr(chat_progress, "overlay_run_progress", broken)
    # Best effort: history still loads without the overlay.
    assert await channels._resolve_assistant_run_states(conn, messages, channel_id=channel) == messages
