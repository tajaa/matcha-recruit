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
import json
import os
from typing import Any

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.merlin import agent as merlin_agent  # noqa: E402
from app.cappe.services.merlin.agent import run_merlin_agent  # noqa: E402

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

        shot_calls: list[dict[str, Any]] = []

        async def _shot(html, viewport="desktop", *, focus_block=None):
            shot_calls.append({"viewport": viewport, "focus_block": focus_block})
            if screenshot_error is not None:
                raise bp.ScreenshotUnavailable(screenshot_error)
            return screenshot, []

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
        fake.aio.models.shot_calls = shot_calls
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
    # JPEG, not PNG — a screenshot is judged at tile resolution, and the bytes
    # difference is real money across a multi-shot turn (browser_pool.SHOT_MIME).
    assert image_parts[0].inline_data.mime_type == merlin_agent.SHOT_MIME


def test_only_the_most_recent_screenshot_still_carries_pixels(patched):
    """Every screenshot rides in `contents` and is re-sent whole on EVERY later
    model call — an unpruned turn's 3rd shot means the 4th call still pays for
    shots 1 and 2 as image tokens even though only the newest one matters to
    what's being judged right now. Only the latest should still be an image;
    earlier ones degrade to a text placeholder, and — because the API requires
    one function_response per call — every call's function_response must
    still be there regardless."""
    frames, models = patched([
        [("render_screenshot", {})],
        [("render_screenshot", {})],
        [("render_screenshot", {})],
        [("finish", {"message": "Done."})],
    ], model_tier="max")
    _result(frames)

    all_parts = [p for content in models.received[-1] for p in (content.parts or [])]
    image_parts = [p for p in all_parts if getattr(p, "inline_data", None) is not None]
    function_responses = [p for p in all_parts if getattr(p, "function_response", None) is not None]
    stale_notes = [p for p in all_parts if getattr(p, "text", None) == merlin_agent._STALE_SHOT_NOTE]

    assert len(image_parts) == 1, "only the newest screenshot should still carry pixels"
    assert len(function_responses) == 3, "every screenshot call must still be answered"
    assert len(stale_notes) == 2, "pruned screenshots become a placeholder, not a silent gap"


_MANY_BLOCKS = [
    {"id": "b1", "type": "hero", "heading": "Old"},
    {"id": "b2", "type": "features"},
    {"id": "b3", "type": "faq"},
]


def test_render_screenshot_resolves_block_id_to_its_render_index(patched):
    """block_id must map to the position render_html enumerates blocks in —
    that's what browser_pool.screenshot_html's focus_block indexes into
    (data-cz-block="<index>", from render_site_html(..., block_anchors=True))
    to scroll the shot to the section actually being judged, not always the
    top fold."""
    frames, models = patched(
        [
            [("render_screenshot", {"block_id": "b3"})],
            [("finish", {"message": "Done."})],
        ],
        blocks=_MANY_BLOCKS,
    )
    _result(frames)

    assert models.shot_calls[0]["focus_block"] == 2


def test_render_screenshot_without_block_id_shoots_the_fold(patched):
    """Omitting block_id (judging the whole page, e.g. after a theme swap)
    must not resolve to some accidental index."""
    frames, models = patched([
        [("render_screenshot", {})],
        [("finish", {"message": "Done."})],
    ], blocks=_MANY_BLOCKS)
    _result(frames)

    assert models.shot_calls[0]["focus_block"] is None


def test_render_screenshot_unknown_block_id_degrades_to_the_fold(patched):
    """A stale or hallucinated id must not fail the shot — the turn still
    gets a screenshot, just of whatever the fold shows."""
    frames, models = patched([
        [("render_screenshot", {"block_id": "does-not-exist"})],
        [("finish", {"message": "Done."})],
    ], blocks=_MANY_BLOCKS)
    data = _result(frames)

    assert models.shot_calls[0]["focus_block"] is None
    assert any(s["kind"] == "screenshot" and "Rendered" in s["label"] for s in data["steps"])


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


def test_repeated_rejected_ops_stop_the_loop(patched):
    """One corrected edit batch may follow a rejection. Repeating an
    all-rejected batch must not consume the tier's remaining model calls."""
    invalid_ops = [("apply_ops", {"ops": '[{"op":"set_field","block":"ghost","path":"heading","value":"x"}]'})]
    frames, models = patched([invalid_ops, invalid_ops, [("finish", {"message": "ignored"})]])
    data = _result(frames)

    assert models.calls == merlin_agent._MAX_REJECTED_APPLY_ATTEMPTS
    assert data["ops"] == []
    assert "block id not found" in data["message"]


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


def _set_field_ops(n: int, offset: int = 0) -> str:
    """`n` independently-valid set_field ops against b1 — a cheap way to fill
    an apply_ops call without needing n distinct blocks."""
    return json.dumps([
        {"op": "set_field", "block": "b1", "path": "heading", "value": f"v{offset + i}"}
        for i in range(n)
    ])


def test_turn_op_budget_is_enforced_across_calls(patched):
    """MAX_OPS_PER_TURN (merlin_ops.py) caps one apply_ops CALL. This is the
    separate per-TURN cap — op_log accumulates across every call the loop
    makes this turn, which a single call's own cap can't see. Three calls of
    the per-call max (20 each) exactly spend the 60-op turn budget; a fourth
    call must be refused outright, not partially applied.

    A budget-exhausted call returns only an error payload (no step frame —
    there's nothing to report having applied), so the assertion is on the
    accumulated op log rather than the steps list; the model still gets the
    error back as that call's function_response and the loop keeps running,
    which is why a 5th (finish) call still completes normally."""
    assert merlin_agent._MAX_TURN_OPS == 60
    frames, models = patched([
        [("apply_ops", {"ops": _set_field_ops(20, offset=0)})],
        [("apply_ops", {"ops": _set_field_ops(20, offset=20)})],
        [("apply_ops", {"ops": _set_field_ops(20, offset=40)})],
        [("apply_ops", {"ops": _set_field_ops(1, offset=60)})],
        [("finish", {"message": "Done."})],
    ], model_tier="max")
    data = _result(frames)

    assert len(data["ops"]) == 60, "the turn must not exceed its own op budget"
    assert models.calls == 5, "the refused 4th call doesn't stop the loop"


def test_turn_op_budget_truncates_a_call_that_straddles_the_limit(patched):
    """A call that starts under budget but asks for more than remains gets the
    overflow rejected with a reason, not silently dropped — same "truncate and
    report" behavior validate_ops itself uses for MAX_OPS_PER_TURN. Every call
    stays at or under the per-call cap (MAX_OPS_PER_TURN=20 in merlin_ops.py)
    so this actually isolates the per-TURN budget logic — a call over 20 would
    get truncated by validate_ops's own cap before the turn budget ever sees
    it exceed what remains."""
    frames, _ = patched([
        [("apply_ops", {"ops": _set_field_ops(20, offset=0)})],
        [("apply_ops", {"ops": _set_field_ops(20, offset=20)})],
        [("apply_ops", {"ops": _set_field_ops(10, offset=40)})],  # 50 applied, 10 left in budget
        [("apply_ops", {"ops": _set_field_ops(15, offset=50)})],  # asks for 15, only 10 remain
        [("finish", {"message": "Done."})],
    ], model_tier="max")
    data = _result(frames)

    assert len(data["ops"]) == 60
    reasons = " ".join(r["reason"] for r in data["rejected"])
    assert "60" in reasons or "budget" in reasons, data["rejected"]


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
    # Deterministic honesty guard (2026-08-01): ops applied + every screenshot
    # attempt this turn was blind ⇒ the finish message must say so, regardless
    # of what the model itself claimed.
    assert "couldn't render a preview" in data["message"]


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


def test_render_exception_with_applied_ops_also_gets_the_caveat(patched):
    """Same blind-turn guard, via the OTHER degrade path (a render exception,
    not a missing browser) — both must count as 'never verified'."""

    def _boom(_blocks, _theme):
        raise ValueError("template exploded")

    frames, _ = patched(
        [
            [("apply_ops", {"ops": '[{"op":"set_field","block":"b1","path":"heading","value":"New"}]'})],
            [("render_screenshot", {})],
            [("finish", {"message": "Updated the heading."})],
        ],
        render_html=_boom,
    )
    data = _result(frames)
    assert data["ops"]
    assert "couldn't render a preview" in data["message"]


def test_no_caveat_when_a_screenshot_actually_succeeded(patched):
    frames, _ = patched([
        [("apply_ops", {"ops": '[{"op":"set_field","block":"b1","path":"heading","value":"New"}]'})],
        [("render_screenshot", {})],
        [("finish", {"message": "Done."})],
    ])
    data = _result(frames)
    assert "couldn't render a preview" not in data["message"]


def test_no_caveat_when_nothing_was_applied(patched):
    """A blind screenshot with no ops applied has nothing to caveat — the
    default 'nothing was changed' message already tells the truth."""
    frames, _ = patched(
        [[("render_screenshot", {})], [("finish", {"message": "Nothing to change."})]],
        screenshot_error="Executable doesn't exist",
    )
    data = _result(frames)
    assert data["ops"] == []
    assert "couldn't render a preview" not in data["message"]


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


# --- generate_image background targeting (2026-08-01 fix) --------------------
#
# Regression coverage for the incident: Merlin generated a paper-texture image
# for a `text` block (no image field), folded it as a bare set_field into a
# dead 'image' key, told the user "updated its background", and nothing on
# the page changed. do_generate_image must now (a) validate the target BEFORE
# spending quota/$ on generation, and (b) fold a background placement as the
# TWO set_design ops the renderer actually reads (bg.type + bg.image —
# services/render/design.py only paints bg.image when bg.type == "image").

_TEXT_BLOCKS = [{"id": "t1", "type": "text", "heading": "About Lumière", "body": "Sub"}]


def test_generate_image_explicit_bad_field_errors_before_generating(patched, monkeypatch):
    """An EXPLICIT field the block doesn't have must be rejected without ever
    calling generate_image — the old code generated first and only discovered
    the target was wrong (or, worse, silently accepted it) after paying for
    the image."""
    calls = _patch_generate_image(monkeypatch)
    frames, _ = patched([
        [("generate_image", {"block_id": "t1", "prompt": "paper", "field": "portrait"})],
        [("finish", {"message": "Could not do that."})],
    ], blocks=_TEXT_BLOCKS)
    data = _result(frames)
    assert calls == [], "no image should have been generated"
    assert data["ops"] == []
    image_steps = [s for s in data["steps"] if s["kind"] == "image"]
    assert image_steps and "invalid" in image_steps[0]["label"].lower()


def test_generate_image_defaulted_field_on_fieldless_block_auto_routes_to_background(patched, monkeypatch):
    """The flagship case: the model asked for the DEFAULT ('image') field on a
    block type that has none at all. Auto-route to the section background
    instead of failing — this is the exact request from the incident
    ("make this text section's background look like handcrafted paper")."""
    calls = _patch_generate_image(monkeypatch)
    frames, _ = patched([
        [("generate_image", {"block_id": "t1", "prompt": "handcrafted paper texture"})],
        [("finish", {"message": "Gave the section a paper-texture background."})],
    ], blocks=_TEXT_BLOCKS)
    data = _result(frames)

    assert len(calls) == 1, "exactly one generation — the field/background check runs before the API call"
    assert data["ops"] == [
        {"op": "set_design", "block": "t1", "group": "bg", "key": "type", "value": "image"},
        {"op": "set_design", "block": "t1", "group": "bg", "key": "image",
         "value": "https://cdn.example.test/g.png"},
    ]
    image_steps = [s for s in data["steps"] if s["kind"] == "image"]
    assert image_steps and image_steps[0]["label"].endswith("→ background")
    assert image_steps[0]["image_url"] == "https://cdn.example.test/g.png"


def test_generate_image_background_true_wins_even_on_a_block_with_an_image_field(patched, monkeypatch):
    """`background: true` is an explicit request, not a fallback — it must
    take the bg.type/bg.image path even on a block (hero) that HAS a content
    image field, not silently fall back to set_field."""
    _patch_generate_image(monkeypatch)
    frames, _ = patched([
        [("generate_image", {"block_id": "b1", "prompt": "sunset", "background": True})],
        [("finish", {"message": "Done."})],
    ])
    data = _result(frames)
    assert [o["op"] for o in data["ops"]] == ["set_design", "set_design"]
    assert [o["key"] for o in data["ops"]] == ["type", "image"]
