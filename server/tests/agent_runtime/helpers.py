"""Shared fakes for the agent-runtime tests. Nothing here opens a connection."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from app.core.services import ai_usage
from app.matcha.services.huume.luna_client import LunaResponse
from app.matcha.services.matcha_work.agent_runtime import runner
from app.matcha.services.matcha_work.agent_runtime.context import NoProgress, RunContext, RunLimits
from app.matcha.services.matcha_work.agent_runtime.registry import Ability, AgentTool, Target, ToolOutput

_counter = {"n": 0}


def call(name, args=None):
    _counter["n"] += 1
    return {"call_id": f"call_{_counter['n']}", "name": name, "arguments": args or {}}


def response(*calls, output=(), text=""):
    return LunaResponse(
        response_id="resp",
        text=text,
        function_calls=list(calls),
        usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        output_items=list(output),
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create_response(self, **kwargs):
        self.calls.append({**kwargs, "feature": ai_usage._feature_override.get()})
        return self.responses.pop(0)


class Progress(NoProgress):
    def __init__(self):
        self.notes = []
        self.steps = []

    async def note(self, text, *, force=False):
        self.notes.append(text)

    async def step(self, seq, kind, label, status):
        self.steps.append((seq, kind, label, status))


FINISH = AgentTool(
    name="finish", effect="finish", description="Finish.",
    parameters={"type": "object", "properties": {"answer": {"type": "string"}}},
    step_kind="finish",
)
ASK = AgentTool(
    name="ask_user", effect="ask", description="Ask the person one question.",
    parameters={"type": "object", "properties": {"question": {"type": "string"}}},
    step_kind="ask",
)


def contract():
    def normalize(args, state):
        if not args.get("answer"):
            raise ValueError("answer is required")
        return {"answer": args["answer"]}, []

    return runner.ResultContract(finish=FINISH, normalize=normalize)


def context(**over):
    base = dict(
        run_id=uuid4(), user_id=uuid4(), company_id=uuid4(), role="client",
        surface="assistant", ask="do the thing", storage_prefix="x",
        progress=Progress(), limits=RunLimits(), usage_feature="matcha.test", model="luna",
    )
    base.update(over)
    return RunContext(**base)


def read_tool(name="lookup", handler=None, **over):
    async def default(ctx, state, args, left):
        return ToolOutput(payload={"value": args.get("q", "")})

    return AgentTool(
        name=name, effect="read", description="Look something up.",
        parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        step_kind="read", handler=handler or default, **over,
    )


def commit_tool(name="send_email", handler=None, **over):
    async def default(ctx, state, args, left):
        return ToolOutput(payload={"ok": True, "id": "m1"}, receipt={"lines": [{"label": "Id", "value": "m1"}]})

    base = dict(
        targets=lambda args, state: tuple(Target("email", a) for a in args.get("to", [])),
        preview=lambda args, state: {"title": f"Email to {', '.join(args.get('to', []))}"},
    )
    base.update(over)
    return AgentTool(
        name=name, effect="commit", description="Send an email.",
        parameters={"type": "object", "properties": {"to": {"type": "array", "items": {"type": "string"}}}},
        step_kind="commit", handler=handler or default, **base,
    )


def ability(*tools, key="test", **over):
    return Ability(key=key, label=key, tools=tuple(tools), prompt_block=lambda ctx: "", **over)


def wire_store(monkeypatch):
    """Replace the three audit writes; returns (record_step, claim_step, resolve_step)."""
    record, claim, resolve = AsyncMock(), AsyncMock(return_value=uuid4()), AsyncMock()
    monkeypatch.setattr(runner.store, "record_step", record)
    monkeypatch.setattr(runner.store, "claim_step", claim)
    monkeypatch.setattr(runner.store, "resolve_step", resolve)
    return record, claim, resolve


# ── a scripted connection ────────────────────────────────────────────────────
from contextlib import asynccontextmanager  # noqa: E402


class FakeConn:
    """Answers queries by the first scripted substring they contain, and keeps
    what was run. An unscripted read returns nothing; nothing here is a database."""

    def __init__(self, script=None):
        self.script = list(script or [])  # [(substring, value | callable(args))]
        self.calls = []  # (method, query, args)
        self.in_transaction = 0

    def on(self, substring, value):
        self.script.insert(0, (substring, value))
        return self

    @asynccontextmanager
    async def transaction(self):
        self.in_transaction += 1
        try:
            yield
        finally:
            self.in_transaction -= 1

    def _answer(self, method, query, args, default):
        self.calls.append((method, " ".join(query.split()), args))
        for substring, value in self.script:
            if substring in query:
                out = value(*args) if callable(value) else value
                if isinstance(out, Exception):
                    raise out
                return out
        return default

    async def execute(self, query, *args):
        return self._answer("execute", query, args, "OK")

    async def fetch(self, query, *args):
        return self._answer("fetch", query, args, [])

    async def fetchrow(self, query, *args):
        return self._answer("fetchrow", query, args, None)

    async def fetchval(self, query, *args):
        return self._answer("fetchval", query, args, None)

    def ran(self, substring):
        return [call for call in self.calls if substring in call[1]]


def connection(conn):
    @asynccontextmanager
    async def factory(*_a, **_k):
        yield conn

    return factory
