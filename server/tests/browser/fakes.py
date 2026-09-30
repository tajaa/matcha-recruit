"""A page and a model that exist only in memory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from google.genai import types


class _Recorder:
    def __init__(self, log, name):
        self._log, self._name = log, name

    def __getattr__(self, method):
        async def call(*args, **kwargs):
            self._log.append((f"{self._name}.{method}", args))

        return call


class FakePage:
    def __init__(self, *, url="https://www.tables.example/r/nopa", text="Pick a time", element=None,
                 frames=()):
        self.url = url
        self.text = text
        self.element = element or {}
        self.frames = [SimpleNamespace(url=f) for f in frames]
        self.log = []
        self.mouse = _Recorder(self.log, "mouse")
        self.keyboard = _Recorder(self.log, "keyboard")
        self.main_frame = object()

    async def screenshot(self, **_kw):
        return b"\x89PNG"

    async def goto(self, url, **_kw):
        self.log.append(("goto", (url,)))
        self.url = url

    async def go_back(self, **_kw):
        self.log.append(("go_back", ()))

    async def go_forward(self, **_kw):
        self.log.append(("go_forward", ()))

    async def evaluate(self, script, arg=None):
        if "elementFromPoint" in script:
            return dict(self.element) if self.element is not None else None
        return self.text


def action(name, **args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def reply(*parts, tokens=10):
    parts = [types.Part(text=p) if isinstance(p, str) else p for p in parts]
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=types.Content(role="model", parts=parts))],
        usage_metadata=SimpleNamespace(total_token_count=tokens),
    )


class FakeModel:
    """Stands in for the genai client: `client.models.generate_content(...)`."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        out = self.replies.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def session_factory(page, seen=None):
    @asynccontextmanager
    async def open_session(policy):
        if seen is not None:
            seen.append(policy)
        yield SimpleNamespace(page=page, policy=policy, proxy=None, blocked_navigations=[])

    return open_session
