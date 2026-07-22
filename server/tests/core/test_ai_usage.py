"""ai_usage.py: feature-label derivation, cost math, and the client proxy.

No DB — `_insert_row` is monkeypatched everywhere so these stay pure/unit,
matching tests/cappe/test_merlin_turn.py's style for this kind of module.

Run from server/:  ./venv/bin/python -m pytest tests/core/test_ai_usage.py -q
"""
import asyncio
import os
import sys
import types as pytypes

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-ai-usage")

from app.core.services import ai_usage  # noqa: E402


# --- feature label -----------------------------------------------------------

def _call_feature_label_from(module_name: str) -> str:
    """Simulate `_feature_label()` being invoked from a frame in `module_name`
    by building a tiny fake module and running a function whose __module__ is
    that name.

    The parametrized names below (app.cappe.services.merlin,
    app.matcha.services.matcha_work_ai, ...) are REAL, already-imported
    production modules elsewhere in the suite — this MUST save whatever was
    already in sys.modules and put it back, never unconditionally `del`. An
    earlier version deleted the entry unconditionally, which — when some
    other test file had already imported the real module first — evicted the
    real cached module from sys.modules entirely. A later test importing the
    same dotted path then re-executed that module's top-level code from
    scratch and got a fresh set of classes/objects, distinct from (and
    failing isinstance/equality checks against) whatever earlier code had
    already cached a reference to. Reproduced: with the old unconditional
    `del`, running the full suite (not this file in isolation) failed
    tests/matcha_work/test_matcha_work_image_generation.py::
    test_non_image_requests_normal_flow — a test in a different file
    entirely, whose only connection to this one is import order."""
    mod = pytypes.ModuleType(module_name)
    mod.__dict__["ai_usage"] = ai_usage
    code = "def call():\n    return ai_usage._feature_label()\n"
    exec(compile(code, module_name, "exec"), mod.__dict__)
    original = sys.modules.get(module_name)
    sys.modules[module_name] = mod
    try:
        return mod.call()
    finally:
        if original is not None:
            sys.modules[module_name] = original
        else:
            del sys.modules[module_name]


@pytest.mark.parametrize("module_name,expected", [
    ("app.cappe.services.merlin", "cappe.merlin"),
    ("app.matcha.services.matcha_work_ai", "matcha.matcha_work_ai"),
    # "core"/"workers"/"tasks" are deliberately KEPT (not stripped): they're
    # top-level branches that hold same-named modules for different reasons —
    # app.core.services.legislation_watch (inline research call) vs.
    # app.workers.tasks.legislation_watch (the scheduled Celery sweep) is a
    # REAL pair in this codebase. Stripping both used to collapse them to the
    # identical label "legislation_watch".
    ("app.workers.tasks.compliance_checks", "workers.tasks.compliance_checks"),
    ("app.core.services.gemini_compliance", "core.gemini_compliance"),
])
def test_feature_label_transforms(module_name, expected):
    assert _call_feature_label_from(module_name) == expected


def test_feature_label_does_not_collide_core_and_workers_same_leaf_name():
    # The exact real-world pair: both call Gemini today (grep confirms
    # app/core/services/legislation_watch.py and app/workers/tasks/
    # legislation_watch.py both call generate_content).
    core_label = _call_feature_label_from("app.core.services.legislation_watch")
    worker_label = _call_feature_label_from("app.workers.tasks.legislation_watch")
    assert core_label != worker_label


def test_feature_label_fallback_outside_app():
    assert _call_feature_label_from("some_other_package.thing") == "unknown"


# --- feature_scope override --------------------------------------------------

def test_feature_scope_overrides_stack_label(recorded):
    """The escape hatch for a module with more than one real cost center
    (e.g. cappe.merlin_agent's loop vs. its generate_image tool) — the
    override must win over whatever the stack walk would have derived."""
    real = _FakeModels(is_async=False)
    fake_client = _FakeClient(models_sync=real, models_async=_FakeModels(is_async=True))
    wrapped = ai_usage.wrap_client(fake_client)

    with ai_usage.feature_scope("cappe.merlin_agent.image"):
        wrapped.models.generate_content(model="gemini-3.1-flash-image-preview", contents="hi")

    assert recorded[0]["feature"] == "cappe.merlin_agent.image"


def test_feature_scope_resets_after_block(recorded):
    real = _FakeModels(is_async=False)
    fake_client = _FakeClient(models_sync=real, models_async=_FakeModels(is_async=True))
    wrapped = ai_usage.wrap_client(fake_client)

    with ai_usage.feature_scope("scoped.label"):
        wrapped.models.generate_content(model="gemini-3.5-flash-lite", contents="hi")
    wrapped.models.generate_content(model="gemini-3.5-flash-lite", contents="hi")

    assert recorded[0]["feature"] == "scoped.label"
    assert recorded[1]["feature"] != "scoped.label"


def test_feature_scope_resets_on_exception(recorded):
    """A call that raises inside the `with` block must not leak the override
    into whatever runs after — `finally` in feature_scope is load-bearing."""
    real = _FakeModels(is_async=False)
    fake_client = _FakeClient(models_sync=real, models_async=_FakeModels(is_async=True))
    wrapped = ai_usage.wrap_client(fake_client)

    with pytest.raises(RuntimeError):
        with ai_usage.feature_scope("scoped.label"):
            raise RuntimeError("boom")

    wrapped.models.generate_content(model="gemini-3.5-flash-lite", contents="hi")
    assert recorded[0]["feature"] != "scoped.label"


@pytest.mark.asyncio
async def test_feature_scope_propagates_through_to_thread():
    """`image_gen.generate_image` runs the SDK call via
    `asyncio.to_thread(_generate_sync, ...)` — a scope entered on the calling
    coroutine must still be visible inside that thread, or Merlin's agent-loop
    image-gen override would silently no-op."""
    with ai_usage.feature_scope("thread.check"):
        seen = await asyncio.to_thread(ai_usage._feature_override.get)
    assert seen == "thread.check"
    assert ai_usage._feature_override.get() is None


# --- cost math -----------------------------------------------------------

def test_compute_cost_known_model():
    cost = ai_usage.compute_cost("gemini", "gemini-3.5-flash-lite", 1_000_000, 1_000_000, 0)
    assert cost == pytest.approx(0.30 + 2.50)


def test_compute_cost_thinking_bills_as_output():
    with_thinking = ai_usage.compute_cost("gemini", "gemini-3.6-flash", 0, 0, 1_000_000)
    as_output = ai_usage.compute_cost("gemini", "gemini-3.6-flash", 0, 1_000_000, 0)
    assert with_thinking == pytest.approx(as_output)


def test_compute_cost_unknown_model_is_none():
    assert ai_usage.compute_cost("gemini", "gemini-9-nonexistent", 100, 100, 0) is None


def test_compute_cost_strips_models_prefix():
    a = ai_usage.compute_cost("gemini", "models/gemini-3.5-flash-lite", 100, 100, 0)
    b = ai_usage.compute_cost("gemini", "gemini-3.5-flash-lite", 100, 100, 0)
    assert a == b is not None


def test_compute_cost_all_none_tokens_is_unknown_not_zero():
    # A timed-out/errored call carries no usage_metadata at all. That's
    # UNKNOWN cost (Google may still have billed partial generation), not
    # zero cost — recording 0.0 here said the opposite.
    assert ai_usage.compute_cost("gemini", "gemini-3.5-flash-lite", None, None, None) is None


def test_compute_cost_partial_tokens_still_computed():
    # Only all-three-None means "no usage data". A real response with e.g.
    # thinking_tokens=0 (an explicit int) still prices normally.
    cost = ai_usage.compute_cost("gemini", "gemini-3.5-flash-lite", 100, 100, 0)
    assert cost is not None and cost > 0


def test_compute_cost_prices_image_model():
    # image_gen.IMAGE_MODEL — every real call (the editor's Generate button,
    # Merlin's agent-loop generate_image tool) uses this exact string. Was
    # absent from PRICING entirely at one point, logging cost_usd=NULL and
    # showing as "unpriced" in the admin dashboard.
    cost = ai_usage.compute_cost("gemini", "gemini-3.1-flash-image", 1_000_000, 1_000_000, 0)
    assert cost == pytest.approx(0.30 + 30.00)


def test_compute_cost_prices_retired_preview_image_model():
    # "-preview" was the name this model shipped under before GA (shut down
    # 2026-06-25) — still priced so pre-migration ai_usage_log rows don't
    # retroactively show as unpriced.
    cost = ai_usage.compute_cost("gemini", "gemini-3.1-flash-image-preview", 1_000_000, 1_000_000, 0)
    assert cost == pytest.approx(0.30 + 30.00)


# --- proxy: fake client -----------------------------------------------------

class _FakeUsage:
    def __init__(self, prompt=10, candidates=20, thoughts=0, cached=0):
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates
        self.thoughts_token_count = thoughts
        self.cached_content_token_count = cached


class _FakeResponse:
    def __init__(self, usage_metadata=_FakeUsage()):
        self.usage_metadata = usage_metadata
        self.text = "ok"


class _FakeModels:
    """Stands in for genai.Client().models / .aio.models."""
    def __init__(self, is_async, fail=False):
        self._is_async = is_async
        self._fail = fail
        self.calls = 0

    def list(self):
        return ["passthrough-marker"]

    def generate_content(self, *, model, contents, config=None):
        self.calls += 1
        if self._fail:
            raise ValueError("boom")
        resp = _FakeResponse()
        if self._is_async:
            async def _aret():
                return resp
            return _aret()
        return resp


class _FakeAio:
    def __init__(self, models):
        self._models = models

    @property
    def models(self):
        return self._models


class _FakeClient:
    def __init__(self, models_sync, models_async):
        self.models = models_sync
        self.aio = _FakeAio(models_async)


@pytest.fixture
def recorded(monkeypatch):
    rows = []

    async def fake_insert(row):
        rows.append(row)

    monkeypatch.setattr(ai_usage, "_insert_row", fake_insert)
    return rows


def test_sync_generate_content_records_success_and_passes_through(recorded):
    real = _FakeModels(is_async=False)
    fake_client = _FakeClient(models_sync=real, models_async=_FakeModels(is_async=True))
    wrapped = ai_usage.wrap_client(fake_client)

    resp = wrapped.models.generate_content(model="gemini-3.5-flash-lite", contents="hi")

    assert resp.text == "ok"
    assert real.calls == 1
    assert len(recorded) == 1
    row = recorded[0]
    assert row["status"] == "ok"
    assert row["model"] == "gemini-3.5-flash-lite"
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 20
    assert row["cost_usd"] is not None


def test_sync_generate_content_passthrough_attr(recorded):
    real = _FakeModels(is_async=False)
    fake_client = _FakeClient(models_sync=real, models_async=_FakeModels(is_async=True))
    wrapped = ai_usage.wrap_client(fake_client)
    assert wrapped.models.list() == ["passthrough-marker"]


def test_sync_generate_content_error_recorded_and_reraised(recorded):
    real = _FakeModels(is_async=False, fail=True)
    fake_client = _FakeClient(models_sync=real, models_async=_FakeModels(is_async=True))
    wrapped = ai_usage.wrap_client(fake_client)

    with pytest.raises(ValueError):
        wrapped.models.generate_content(model="gemini-3.5-flash-lite", contents="hi")

    assert len(recorded) == 1
    assert recorded[0]["status"] == "error"
    assert "boom" in recorded[0]["error"]


@pytest.mark.asyncio
async def test_async_generate_content_records_success(recorded):
    # No asyncio.sleep(0) needed: _acall AWAITS the insert directly (see
    # test_celery_asyncio_run_shape_still_records below for why fire-and-forget
    # was wrong) — the row exists the instant this call returns.
    real_async = _FakeModels(is_async=True)
    fake_client = _FakeClient(models_sync=_FakeModels(is_async=False), models_async=real_async)
    wrapped = ai_usage.wrap_client(fake_client)

    resp = await wrapped.aio.models.generate_content(model="gemini-3.6-flash", contents="hi")

    assert resp.text == "ok"
    assert len(recorded) == 1
    assert recorded[0]["status"] == "ok"
    assert recorded[0]["model"] == "gemini-3.6-flash"


@pytest.mark.asyncio
async def test_async_generate_content_error_recorded_and_reraised(recorded):
    real_async = _FakeModels(is_async=True, fail=True)
    fake_client = _FakeClient(models_sync=_FakeModels(is_async=False), models_async=real_async)
    wrapped = ai_usage.wrap_client(fake_client)

    with pytest.raises(ValueError):
        await wrapped.aio.models.generate_content(model="gemini-3.6-flash", contents="hi")

    assert len(recorded) == 1
    assert recorded[0]["status"] == "error"


def test_celery_asyncio_run_shape_still_records(monkeypatch):
    """Regression for the data-loss bug: every Celery task body is
    `asyncio.run(_run())` (app/workers/tasks/*.py — the worker never calls
    init_pool(), see celery_app.py). `asyncio.run()` cancels any still-pending
    task the instant its own coroutine returns, so a fire-and-forget
    `loop.create_task(_insert_row(...))` recorded ZERO rows in this exact
    shape. Uses a slow_insert (a real INSERT isn't instant) so a regression
    back to fire-and-forget would flake/fail here, not pass by accident."""
    rows = []

    async def slow_insert(row):
        await asyncio.sleep(0.02)
        rows.append(row)

    monkeypatch.setattr(ai_usage, "_insert_row", slow_insert)

    real_async = _FakeModels(is_async=True)
    fake_client = _FakeClient(models_sync=_FakeModels(is_async=False), models_async=real_async)
    wrapped = ai_usage.wrap_client(fake_client)

    async def celery_task_body():
        await wrapped.aio.models.generate_content(model="gemini-3.6-flash", contents="research")
        return "task done"

    result = asyncio.run(celery_task_body())

    assert result == "task done"
    assert len(rows) == 1, "row lost when the enclosing asyncio.run() returned before the insert completed"


def test_insert_failure_never_raises(monkeypatch):
    async def failing_insert(row):
        raise RuntimeError("db is down")
    monkeypatch.setattr(ai_usage, "_insert_row", failing_insert)

    real = _FakeModels(is_async=False)
    fake_client = _FakeClient(models_sync=real, models_async=_FakeModels(is_async=True))
    wrapped = ai_usage.wrap_client(fake_client)

    # Must not raise even though the recorder's insert blows up.
    resp = wrapped.models.generate_content(model="gemini-3.5-flash-lite", contents="hi")
    assert resp.text == "ok"


def test_wrap_client_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(ai_usage, "LOGGING_ENABLED", False)
    sentinel = object()
    assert ai_usage.wrap_client(sentinel) is sentinel


@pytest.mark.parametrize("cls", [
    ai_usage._WrappedClient, ai_usage._WrappedAio, ai_usage._WrappedModels,
])
def test_getattr_missing_real_raises_attributeerror_not_recursionerror(cls):
    # A path that skips __init__ (copy.copy, unpickling) leaves `_real` unset.
    # Without the `name == "_real"` guard, looking it up re-enters
    # __getattr__('_real') and recurses until RecursionError — a confusing
    # failure compared to a plain AttributeError.
    instance = object.__new__(cls)
    with pytest.raises(AttributeError):
        instance.anything
