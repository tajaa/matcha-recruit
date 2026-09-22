"""Failure-injection tests for the two Merlin SSE persistence wrappers."""
import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.merlin import agent_stream, setup_agent  # noqa: E402


def _json_frames(frames: list[str]) -> list[dict]:
    return [
        json.loads(frame.removeprefix("data: ").strip())
        for frame in frames
        if frame.startswith("data: {")
    ]


@pytest.mark.asyncio
async def test_page_stream_retries_transient_assistant_persist_before_delivery(monkeypatch):
    conversation_id, message_id = uuid4(), uuid4()
    attempts = 0

    @asynccontextmanager
    async def _connection():
        yield object()

    async def _turn(**_kwargs):
        return {"message": "Done.", "ops": [], "tier": "lite"}

    async def _add_message(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient database error")
        return {"id": message_id}

    monkeypatch.setattr(agent_stream, "get_connection", _connection)
    monkeypatch.setattr(agent_stream, "run_merlin_turn", _turn)
    monkeypatch.setattr(agent_stream.merlin_store, "add_message", _add_message)

    body = SimpleNamespace(
        message="fix it", blocks=[], theme={}, selected_block=None,
        selection=None, attachments=[],
    )
    account = SimpleNamespace(id=uuid4(), plan="free")
    prep = SimpleNamespace(
        agentic=False, history=[], site={"name": "Demo"}, tier="lite",
        attachments=[], routed=False, conversation={"id": conversation_id},
    )
    frames = [
        frame async for frame in agent_stream.stream_agent_turn(
            site_id=uuid4(), body=body, account=account, prep=prep,
            render_html=lambda *_args: "",
        )
    ]

    [result] = [frame for frame in _json_frames(frames) if frame["type"] == "result"]
    assert attempts == 2
    assert result["data"]["conversation_id"] == str(conversation_id)
    assert result["data"]["message_id"] == str(message_id)


@pytest.mark.asyncio
async def test_setup_stream_retries_transient_assistant_persist_before_delivery(monkeypatch):
    conversation_id, message_id = uuid4(), uuid4()
    attempts = 0

    @asynccontextmanager
    async def _connection():
        yield object()

    async def _run_setup_agent(**_kwargs):
        yield {"type": "result", "data": {
            "message": "Done.", "steps": [], "results": [], "tier": "regular",
        }}

    async def _add_message(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient database error")
        return {"id": message_id}

    monkeypatch.setattr(setup_agent, "get_connection", _connection)
    monkeypatch.setattr(setup_agent, "run_setup_agent", _run_setup_agent)
    monkeypatch.setattr(setup_agent.merlin_store, "add_message", _add_message)

    frames = [
        frame async for frame in setup_agent.stream_setup_turn(
            conversation_id=conversation_id, message="set me up", history=[],
            context={}, site={"id": uuid4()}, account=SimpleNamespace(id=uuid4()),
        )
    ]

    [result] = [frame for frame in _json_frames(frames) if frame["type"] == "result"]
    assert attempts == 2
    assert result["data"]["conversation_id"] == str(conversation_id)
    assert result["data"]["message_id"] == str(message_id)
