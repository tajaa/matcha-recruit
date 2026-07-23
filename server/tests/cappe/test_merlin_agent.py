"""The Merlin agent loop, driven by a scripted fake Gemini.

The loop is the whole point of the feature — Merlin applying an edit, rendering
it, LOOKING at the result, and revising — so what's asserted here is the
loop's contract rather than any model behavior:

  - ops accumulate across tool calls, and later calls validate against the
    working copy (not the original snapshot), so an op can target a block an
    earlier call created;
  - a screenshot goes back to the model as an image part it can actually see;
  - bounds (model calls / screenshots / wall clock) force a finish rather than
    running away, and the ops earned so far survive;
  - a missing Chromium degrades to editing blind, never to a failed turn;
  - exactly one `result` frame is emitted, always, last.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_agent.py -q
"""
import os
from typing import Any

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services import merlin_agent  # noqa: E402
from app.cappe.services.merlin_agent import run_merlin_agent  # noqa: E402

_BLOCKS = [{"id": "b1", "type": "hero", "heading": "Old", "subheading": "Sub"}]


# --- fakes -------------------------------------------------------------------

class _FakeCall:
    def __init__(self, name: str, args: dict[str, Any]):
        self.name = name
        self.args = args


class _FakePart:
    def __init__(self, call: _FakeCall):
        self.function_call = call


class _FakeContent:
    def __init__(self, parts):
        self.parts = parts


class _FakeCandidate:
    def __init__(self, calls):
        self.content = _FakeContent([_FakePart(c) for c in calls])


class _FakeResponse:
    def __init__(self, calls, text=""):
        self.candidates = [_FakeCandidate(calls)]
        self.text = text


class _FakeModels:
    """Replays a scripted list of tool-call turns, one per generate_content."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.received: list[Any] = []

    async def generate_content(self, **kwargs):
        self.received.append(kwargs.get("contents"))
        self.calls += 1
        if not self.script:
            return _FakeResponse([], text="ran out of script")
        turn = self.script.pop(0)
        if isinstance(turn, str):  # a prose (no tool call) turn
            return _FakeResponse([], text=turn)
        return _FakeResponse([_FakeCall(name, args) for name, args in turn])


class _FakeClient:
    def __init__(self, script):
        self.aio = type("aio", (), {"models": _FakeModels(script)})()


class _NoopLimiter:
    async def check_limit(self, *_a, **_k):
        return None

    async def record_call(self, *_a, **_k):
        return None


@pytest.fixture
def patched(monkeypatch):
    """Install a scripted client + a no-op rate limiter, and return a helper
    that runs a whole turn and collects its frames."""

    def _run(script, *, screenshot=b"PNG", screenshot_error=None, **overrides):
        fake = _FakeClient(script)
        monkeypatch.setattr(merlin_agent, "get_genai_client", lambda *a, **k: fake)
        monkeypatch.setattr(merlin_agent, "GeminiRateLimiter", lambda: _NoopLimiter())

        import app.cappe.services.browser_pool as bp

        async def _shot(html, viewport="desktop"):
            if screenshot_error is not None:
                raise bp.ScreenshotUnavailable(screenshot_error)
            return screenshot

        monkeypatch.setattr(bp, "screenshot_html", _shot)

        kwargs = {
            "message": "make the hero darker",
            "history": [],
            "blocks": _BLOCKS,
            "theme": {"mode": "light"},
            "render_html": lambda b, t: "<html><body>page</body></html>",
            "business_name": "Demo",
            "model_tier": "max",
            "plan": "pro",
            "account_id": "acct-1",
            "selected_block": "b1",
        }
        kwargs.update(overrides)

        async def _collect():
            return [f async for f in run_merlin_agent(**kwargs)]

        import asyncio

        frames = asyncio.run(_collect())
        return frames, fake.aio.models

    return _run


def _result(frames):
    results = [f for f in frames if f["type"] == "result"]
    assert len(results) == 1, "exactly one result frame, always"
    assert frames[-1]["type"] == "result", "the result frame is last"
    return results[0]["data"]


# --- tests -------------------------------------------------------------------

def test_apply_then_screenshot_then_finish(patched):
    """The flagship path: edit, look at it, decide it's fine, stop."""
    frames, models = patched([
        [("apply_ops", {"ops": '[{"op":"set_field","block":"b1","path":"heading","value":"New"}]'})],
        [("render_screenshot", {"viewport": "desktop"})],
        [("finish", {"message": "Darkened the hero."})],
    ])
    data = _result(frames)

    assert data["message"] == "Darkened the hero."
    assert [o["op"] for o in data["ops"]] == ["set_field"]
    assert [s["kind"] for s in data["steps"]] == ["ops", "screenshot"]
    assert models.calls == 3


def test_finish_in_the_same_batch_does_not_discard_sibling_calls(patched):
    """Gemini's parallel function calling makes no ordering promise within one
    batch — `[finish(...), apply_ops(...)]` is a real shape. `finish` must not
    short-circuit the batch and drop the ops after it, or the turn reports a
    change it never actually applied."""
    frames, _ = patched([
        [
            ("finish", {"message": "Darkened the hero."}),
            ("apply_ops", {"ops": '[{"op":"set_field","block":"b1","path":"heading","value":"New"}]'}),
        ],
    ])
    data = _result(frames)

    assert data["message"] == "Darkened the hero."
    assert [o["op"] for o in data["ops"]] == ["set_field"], (
        "the sibling apply_ops call must still execute even though finish "
        "came first in the batch"
    )


def test_screenshot_is_handed_back_to_the_model_as_an_image(patched):
    """A screenshot the model can't see is a wasted round trip — the PNG must
    ride back on the next request's contents, not just into the step frame."""
    frames, models = patched([
        [("render_screenshot", {})],
        [("finish", {"message": "Looks right."})],
    ])
    _result(frames)

    # The contents of the LAST request carry the function response + the image.
    last = models.received[-1]
    image_parts = [
        p for content in last for p in (content.parts or [])
        if getattr(p, "inline_data", None) is not None
    ]
    assert image_parts, "the screenshot must be attached as an image part"


def test_ops_accumulate_and_later_calls_see_earlier_ones(patched):
    """Each apply_ops validates against the WORKING COPY. A section added in
    one tool call must be targetable by the next — the single-shot path can't
    do this (it validates one batch against the original snapshot)."""
    frames, _ = patched([
        [("apply_ops", {"ops": '[{"op":"add_block","type":"faq","at":1,"id":"new-1"}]'})],
        [("apply_ops", {"ops": '[{"op":"set_field","block":"new-1","path":"heading","value":"FAQ"}]'})],
        [("finish", {"message": "Added an FAQ."})],
    ])
    data = _result(frames)

    assert [o["op"] for o in data["ops"]] == ["add_block", "set_field"]
    ops_steps = [s for s in data["steps"] if s["kind"] == "ops"]
    assert all(r["ok"] for s in ops_steps for r in s["results"]), s_fail(ops_steps)


def s_fail(steps):
    return f"expected every op to apply; got {[s['results'] for s in steps]}"


def test_invalid_ops_are_reported_back_not_applied(patched):
    """Rejections go back to the model as a reason it can act on, and the op
    never reaches the returned log."""
    frames, _ = patched([
        [("apply_ops", {"ops": '[{"op":"set_field","block":"ghost","path":"heading","value":"x"}]'})],
        [("finish", {"message": "Couldn't find that section."})],
    ])
    data = _result(frames)

    assert data["ops"] == []
    assert data["rejected"], "the bad op must be reported, not silently dropped"


def test_malformed_ops_json_does_not_kill_the_turn(patched):
    frames, _ = patched([
        [("apply_ops", {"ops": "not json"})],
        [("finish", {"message": "Nothing changed."})],
    ])
    data = _result(frames)
    assert data["ops"] == []


def test_model_call_bound_forces_a_finish_and_keeps_the_ops(patched):
    """A model that never calls finish must still terminate, and the work it
    did before the bound is kept — a partial improvement beats an error."""
    apply_turn = [("apply_ops", {"ops": '[{"op":"set_field","block":"b1","path":"heading","value":"New"}]'})]
    frames, models = patched([apply_turn] * 30, model_tier="regular")
    data = _result(frames)

    assert models.calls == merlin_agent._BOUNDS["regular"].model_calls
    assert data["ops"], "ops earned before the bound survive"
    assert data["message"]


def test_screenshot_budget_is_enforced_within_the_turn(patched):
    """Screenshots are the expensive half. Past the budget the tool reports
    that rather than rendering, and the loop carries on."""
    shot = [("render_screenshot", {})]
    frames, _ = patched([*([shot] * 4), [("finish", {"message": "Done."})]], model_tier="regular")
    data = _result(frames)

    rendered = [s for s in data["steps"] if s["kind"] == "screenshot" and "Rendered" in s["label"]]
    assert len(rendered) == merlin_agent._BOUNDS["regular"].screenshots


def test_missing_chromium_degrades_to_editing_blind(patched):
    """No browser in the image is a deployment state, not a user-facing error:
    the turn proceeds without vision, exactly as Merlin behaved before."""
    frames, _ = patched(
        [
            [("render_screenshot", {})],
            [("apply_ops", {"ops": '[{"op":"set_field","block":"b1","path":"heading","value":"New"}]'})],
            [("finish", {"message": "Darkened the hero."})],
        ],
        screenshot_error="Executable doesn't exist",
    )
    data = _result(frames)

    assert data["ops"], "the edit still lands without a screenshot"
    assert any(s["label"] == "Preview unavailable" for s in data["steps"])
    assert not any(f["type"] == "error" for f in frames)


def test_a_render_failure_is_also_survivable(patched):
    """A render that raises (bad block payload, template bug) must not take the
    turn down — the model is told and continues."""

    def _boom(_blocks, _theme):
        raise ValueError("template exploded")

    frames, _ = patched(
        [[("render_screenshot", {})], [("finish", {"message": "Done."})]],
        render_html=_boom,
    )
    data = _result(frames)
    assert any(s["label"] == "Render failed" for s in data["steps"])


def test_a_prose_turn_ends_the_loop_as_the_message(patched):
    """A model that answers in prose instead of calling finish shouldn't spin."""
    frames, models = patched(["I can't do that — no such section."])
    data = _result(frames)

    assert data["message"] == "I can't do that — no such section."
    assert models.calls == 1


def test_unknown_tool_is_reported_rather_than_crashing(patched):
    frames, _ = patched([
        [("teleport", {"to": "mars"})],
        [("finish", {"message": "Done."})],
    ])
    data = _result(frames)
    assert data["message"] == "Done."


def test_a_model_error_still_yields_a_result_frame(patched, monkeypatch):
    """The never-raises contract: a broken Gemini degrades to an error frame
    plus a result, so the client always has something to apply and the stream
    always terminates."""

    class _Boom:
        async def generate_content(self, **_kw):
            raise RuntimeError("gemini is down")

    class _BoomClient:
        def __init__(self):
            self.aio = type("aio", (), {"models": _Boom()})()

    monkeypatch.setattr(merlin_agent, "get_genai_client", lambda *a, **k: _BoomClient())
    monkeypatch.setattr(merlin_agent, "GeminiRateLimiter", lambda: _NoopLimiter())

    import asyncio

    async def _collect():
        return [
            f
            async for f in run_merlin_agent(
                message="make the hero darker",
                history=[],
                blocks=_BLOCKS,
                theme={},
                render_html=lambda b, t: "<html></html>",
                model_tier="max",
                plan="pro",
            )
        ]

    frames = asyncio.run(_collect())
    assert any(f["type"] == "error" for f in frames)
    data = _result(frames)
    assert data["ops"] == []


def test_rate_limit_propagates_for_the_route_to_429(patched, monkeypatch):
    """RateLimitExceeded is the ONE exception that escapes — the route turns it
    into a 429 (or an in-band error frame once the stream has started)."""
    from app.core.services.rate_limiter import RateLimitExceeded

    class _Limited:
        async def check_limit(self, *_a, **_k):
            raise RateLimitExceeded("cap reached", "daily", 100, 100)

        async def record_call(self, *_a, **_k):
            return None

    monkeypatch.setattr(merlin_agent, "get_genai_client", lambda *a, **k: _FakeClient([]))
    monkeypatch.setattr(merlin_agent, "GeminiRateLimiter", lambda: _Limited())

    import asyncio

    async def _collect():
        return [
            f
            async for f in run_merlin_agent(
                message="hi", history=[], blocks=_BLOCKS, theme={},
                render_html=lambda b, t: "", model_tier="max", plan="pro",
            )
        ]

    with pytest.raises(RateLimitExceeded):
        asyncio.run(_collect())


def test_lite_is_not_an_agent_tier():
    """The loop is several model calls plus screenshots — not a free taste. The
    route uses this to route Lite to the single-shot path."""
    assert "lite" not in merlin_agent.AGENT_TIERS
    assert merlin_agent.AGENT_TIERS == {"regular", "max"}


# --- generate_image tool (Phase 4) -------------------------------------------

def _patch_generate_image(monkeypatch, *, url="https://cdn.example.test/g.png", png=b"GEN", error=None):
    import app.core.services.image_gen as image_gen_mod

    calls = []

    async def _fake_generate_image(prompt, *, prefix, aspect_ratio="16:9",
                                    reference_images=None, return_bytes=False, image_size=None):
        calls.append({"prompt": prompt, "reference_images": reference_images, "image_size": image_size})
        if error is not None:
            raise image_gen_mod.ImageGenError(error)
        return (url, png) if return_bytes else url

    async def _noop_quota(*_a, **_k):
        return None

    # generate_image is imported LAZILY inside do_generate_image, so patch the
    # source module it resolves from at call time.
    monkeypatch.setattr(image_gen_mod, "generate_image", _fake_generate_image)
    monkeypatch.setattr(merlin_agent.image_quota, "check_and_record", _noop_quota)
    return calls


def test_generate_image_tool_places_the_result_and_logs_a_set_field(patched, monkeypatch):
    calls = _patch_generate_image(monkeypatch)
    frames, _ = patched([
        [("generate_image", {"block_id": "b1", "prompt": "a warm sunset", "field": "image"})],
        [("finish", {"message": "Added an image."})],
    ])
    data = _result(frames)

    assert data["ops"] == [
        {"op": "set_field", "block": "b1", "path": "image", "value": "https://cdn.example.test/g.png"}
    ]
    assert calls[0]["reference_images"] is None
    # Default resolution when the model omits the arg — 2K, not the SDK's own
    # 1K default, because section backgrounds render full-bleed (render.py).
    assert calls[0]["image_size"] == "2K"
    image_steps = [s for s in data["steps"] if s["kind"] == "image"]
    assert image_steps
    # The panel's "Apply to…" menu (and its chat thumbnail) both read this —
    # without it the model's placement is the ONLY way to see or re-target
    # what got generated.
    assert image_steps[0]["image_url"] == "https://cdn.example.test/g.png"
    # Rides along on the step so the route can catalog the generation into
    # cappe_assets without re-deriving it from the raw tool-call args.
    assert image_steps[0]["prompt"] == "a warm sunset"
    assert image_steps[0]["image_size"] == "2K"


def test_generate_image_tool_honors_an_explicit_image_size(patched, monkeypatch):
    calls = _patch_generate_image(monkeypatch)
    frames, _ = patched([
        [("generate_image", {"block_id": "b1", "prompt": "a warm sunset", "image_size": "4K"})],
        [("finish", {"message": "Added an image."})],
    ])
    data = _result(frames)
    assert calls[0]["image_size"] == "4K"
    image_steps = [s for s in data["steps"] if s["kind"] == "image"]
    assert image_steps[0]["image_size"] == "4K"


def test_generate_image_tool_ignores_an_invalid_image_size(patched, monkeypatch):
    calls = _patch_generate_image(monkeypatch)
    patched([
        [("generate_image", {"block_id": "b1", "prompt": "a warm sunset", "image_size": "8K"})],
        [("finish", {"message": "Added an image."})],
    ])
    assert calls[0]["image_size"] == "2K"


def test_generate_image_conditions_on_a_numbered_attachment(patched, monkeypatch):
    calls = _patch_generate_image(monkeypatch)
    frames, _ = patched(
        [
            [("generate_image", {
                "block_id": "b1", "prompt": "a lighter background", "attachment_index": 1,
            })],
            [("finish", {"message": "Done."})],
        ],
        attachments=[{"url": "https://cdn.example.test/photo.jpg", "mime": "image/jpeg", "data": b"PHOTO"}],
    )
    data = _result(frames)

    assert data["ops"], "the placement must still apply"
    assert calls[0]["reference_images"] == [(b"PHOTO", "image/jpeg")]


def test_generate_image_generated_bytes_go_back_to_the_model(patched, monkeypatch):
    """Same principle as the screenshot tool: a generation the model can't see
    is a wasted round trip — it can't judge or retry a bad result."""
    _patch_generate_image(monkeypatch, png=b"GENERATED-PNG")
    frames, models = patched([
        [("generate_image", {"block_id": "b1", "prompt": "x"})],
        [("finish", {"message": "Done."})],
    ])
    _result(frames)

    last = models.received[-1]
    image_parts = [
        p for content in last for p in (content.parts or [])
        if getattr(p, "inline_data", None) is not None
    ]
    assert image_parts


def test_generate_image_missing_block_is_reported_not_raised(patched, monkeypatch):
    _patch_generate_image(monkeypatch)
    frames, _ = patched([
        [("generate_image", {"block_id": "ghost", "prompt": "x"})],
        [("finish", {"message": "Couldn't find that section."})],
    ])
    data = _result(frames)
    assert data["ops"] == []


def test_generate_image_failure_is_reported_not_raised(patched, monkeypatch):
    _patch_generate_image(monkeypatch, error="model returned no image")
    frames, _ = patched([
        [("generate_image", {"block_id": "b1", "prompt": "x"})],
        [("finish", {"message": "Couldn't generate that."})],
    ])
    data = _result(frames)
    assert data["ops"] == []
    assert any("failed" in s["label"].lower() for s in data["steps"])


def test_generate_image_quota_exhausted_degrades_the_tool_not_the_turn(patched, monkeypatch):
    """`image_quota.check_and_record` raises `HTTPException(429)`, not
    `RateLimitExceeded` (that type belongs to a different budget,
    `GeminiRateLimiter`). A prior regression caught the wrong exception here,
    so quota exhaustion escaped to the loop's outer handler and killed the
    WHOLE turn — including ops already applied earlier in it — instead of
    just failing this one tool call."""
    from fastapi import HTTPException

    async def _quota_exhausted(*_a, **_k):
        raise HTTPException(status_code=429, detail="quota reached")

    monkeypatch.setattr(merlin_agent.image_quota, "check_and_record", _quota_exhausted)

    frames, _ = patched([
        [("apply_ops", {"ops": '[{"op":"set_field","block":"b1","path":"heading","value":"New"}]'})],
        [("generate_image", {"block_id": "b1", "prompt": "x"})],
        [("finish", {"message": "Updated the heading; couldn't generate the image."})],
    ])

    assert not any(f["type"] == "error" for f in frames), (
        "quota exhaustion must not surface as a turn-level error frame"
    )
    data = _result(frames)
    assert [o["op"] for o in data["ops"]] == ["set_field"], (
        "the earlier apply_ops must survive a later tool's quota rejection"
    )
    assert any(s["kind"] == "image" and "quota" in s["label"].lower() for s in data["steps"])
