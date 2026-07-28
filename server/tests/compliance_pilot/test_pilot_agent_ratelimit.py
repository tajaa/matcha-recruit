"""The agentic Pilot's rate-limit contract, driven through the real loop.

    cd server && ./venv/bin/python -m pytest tests/compliance_pilot -q

No DB, no Gemini: `get_connection`, `core.load_actions`, `GeminiRateLimiter` and
`get_genai_client` are all substituted on the `agent` module (the module that
DEFINES the caller — patching a facade that re-exports them is a silent no-op,
see server/CLAUDE.md).

What's being pinned: WHERE a Gemini rate limit lands decides whether the turn is
recoverable.

- Hit BEFORE any tool ran, nothing happened, so the loop re-raises and the route
  renders its own message rather than persisting an empty assistant turn.
- Hit AFTER a tool ran, the turn has already changed the database — the stage_*
  tools INSERT real `compliance_pilot_actions` rows — so re-raising would skip
  the route's shielded persist and strand those proposals in the session with no
  message explaining them. It degrades into a normal terminal `agent_result`
  frame carrying `error` instead.

The asymmetry is the whole point, so both directions are asserted here.
"""

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import types

from app.core.services.compliance_pilot import agent as agent_mod
from app.core.services.rate_limiter import RateLimitExceeded

SESSION = "8f14e45f-ceea-467a-9575-1234567890ab"


# --------------------------------------------------------------------------- #
# Substitutes
# --------------------------------------------------------------------------- #

class _FakeConn:
    """Every tool this test exercises reads through `core.load_actions`, which is
    itself substituted — so the connection only has to be an object."""


class _FakeConnCtx:
    async def __aenter__(self):
        return _FakeConn()

    async def __aexit__(self, *exc):
        return False


class _Limiter:
    """Raises on the Nth `check_limit` (1-based), passes before that."""

    def __init__(self, raise_on_call: int) -> None:
        self.raise_on_call = raise_on_call
        self.checks = 0
        self.records = 0

    async def check_limit(self, service_name, endpoint=None):
        self.checks += 1
        if self.checks >= self.raise_on_call:
            raise RateLimitExceeded("daily Gemini budget exhausted", "daily", 1000, 1000)

    async def record_call(self, service_name, endpoint=None):
        self.records += 1


def _tool_call_response(name: str, args: dict | None = None):
    """A Gemini response whose single candidate part is a function call. Built
    from REAL `types` objects because the loop appends the parts straight back
    into a `types.Content`, which validates them."""
    part = types.Part(function_call=types.FunctionCall(name=name, args=args or {}))
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
        usage_metadata=None,
        text=None,
    )


def _client_returning(responses: list):
    """A genai client stand-in that hands back `responses` in order."""
    calls = {"n": 0}

    async def generate_content(*, model, contents, config):
        i = calls["n"]
        calls["n"] += 1
        return responses[min(i, len(responses) - 1)]

    return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(
        generate_content=generate_content)))


def _install(monkeypatch, *, limiter, responses):
    monkeypatch.setattr(agent_mod, "get_connection", lambda: _FakeConnCtx())
    monkeypatch.setattr(agent_mod, "GeminiRateLimiter", lambda: limiter)
    monkeypatch.setattr(agent_mod, "get_genai_client", lambda: _client_returning(responses))

    async def _load_actions(conn, session_id):
        return []

    monkeypatch.setattr(agent_mod.core_mod, "load_actions", _load_actions)


async def _drain(history=None):
    frames = []
    async for ev in agent_mod.run_pilot_turn(
        session_id=SESSION, actor_id=None,
        history=history or [{"role": "user", "content": "what's staged?"}],
    ):
        frames.append(ev)
    return frames


# --------------------------------------------------------------------------- #
# Before any tool ran — nothing to save, so the raise stands
# --------------------------------------------------------------------------- #

def test_rate_limit_before_any_tool_ran_still_raises(monkeypatch):
    limiter = _Limiter(raise_on_call=1)
    _install(monkeypatch, limiter=limiter, responses=[_tool_call_response("list_actions")])

    with pytest.raises(RateLimitExceeded):
        asyncio.run(_drain())

    # The model was never reached, so there is genuinely no turn to persist.
    assert limiter.records == 0


# --------------------------------------------------------------------------- #
# After a tool ran — the turn changed the DB, so it must come back as a result
# --------------------------------------------------------------------------- #

def test_rate_limit_after_a_tool_ran_finishes_the_turn_instead_of_raising(monkeypatch):
    limiter = _Limiter(raise_on_call=2)
    _install(monkeypatch, limiter=limiter, responses=[_tool_call_response("list_actions")])

    frames = asyncio.run(_drain())

    results = [f for f in frames if f["type"] == "agent_result"]
    assert len(results) == 1, "the route only persists when a terminal frame arrives"
    data = results[0]["data"]

    # The tool that ran before the limit is preserved, and so is its narrative.
    assert [s["tool"] for s in data["steps"]] == ["list_actions"]
    assert "rate limit" in data["error"].lower()
    assert data["message"] == data["error"], (
        "the persisted assistant message must SAY the turn was cut short — the "
        "generic 'Done for now' would read as a clean finish"
    )


def test_a_cut_short_turn_emits_no_duplicate_error_frame(monkeypatch):
    """The console appends an `error` frame as a live '⚠' bubble that can never
    reconcile against the transcript (the persisted content lacks the marker), so
    emitting one alongside an `agent_result` that says the same thing leaves the
    sentence on screen twice, forever. The terminal frame is the error report."""
    _install(monkeypatch, limiter=_Limiter(raise_on_call=2),
             responses=[_tool_call_response("list_actions")])

    frames = asyncio.run(_drain())

    assert [f["type"] for f in frames].count("error") == 0
    assert frames[-1]["type"] == "agent_result"


def test_staged_proposals_survive_a_cut_short_turn(monkeypatch):
    """`proposal_action_ids` is how the client links the turn to the rows the
    stage_* tools inserted. Losing the frame loses that link — the rows would
    still be in the session with nothing pointing at them."""
    _install(monkeypatch, limiter=_Limiter(raise_on_call=2),
             responses=[_tool_call_response("list_actions")])

    frames = asyncio.run(_drain())
    data = [f for f in frames if f["type"] == "agent_result"][0]["data"]

    assert "proposal_action_ids" in data
    assert "citations" in data
    assert data["model_calls"] == 1
