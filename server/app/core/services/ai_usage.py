"""Provider-general AI call usage ledger.

Wraps the `genai.Client` returned by `genai_client.get_genai_client()` so every
`generate_content` / `generate_content_stream` / `embed_content` call — sync or
async — logs its model, caller ("feature"), token counts, cost, latency, and
outcome to `ai_usage_log`, with zero changes at any of the ~100 call sites.

This is the LEDGER (what did we spend, and where). `rate_limiter.py` /
`api_rate_limits` is the separate, pre-existing GUARD (are we about to spend too
much) — untouched by this module, and not reused for storage: the guard only
ever needed a call count, this needs the full row.

v1 known gaps (see admin UI / API docs for how these surface):
  - Live-API sessions (voice interviews) are not wrapped — `client.aio.live` is
    a distinct surface this module doesn't touch. Two call sites total today.
  - Cached-token discount is ignored in cost math (slight overestimate).
  - No per-company attribution — feature-level only. A nullable company_id
    column can be added later without reshaping this module.

Set AI_USAGE_LOGGING=0 to disable (read once at import; the client is then
returned unwrapped).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

LOGGING_ENABLED = os.getenv("AI_USAGE_LOGGING", "1") != "0"

# --- Pricing --------------------------------------------------------------
# USD per 1M tokens, (input_price, output_price). Verified against
# ai.google.dev/gemini-api/docs/pricing as of 2026-07-21. A model absent here
# logs cost_usd=NULL rather than a guessed number — the admin UI surfaces
# "unpriced" calls so a real row gets added instead of a fabricated price.
PRICING: dict[tuple[str, str], tuple[float, float]] = {
    ("gemini", "gemini-3.6-flash"): (1.50, 7.50),
    ("gemini", "gemini-3.5-flash"): (1.50, 9.00),
    ("gemini", "gemini-3.5-flash-lite"): (0.30, 2.50),
    ("gemini", "gemini-3-flash-preview"): (0.50, 3.00),
    ("gemini", "gemini-3.1-flash-lite"): (0.25, 1.50),
}

# Modules dropped from the feature label — purely organizational nesting
# that's redundant on every path ("app", the src root; "services"/"routes",
# the layer-within-a-package). "app.cappe.services.merlin" -> "cappe.merlin".
#
# Deliberately NOT stripping "core"/"workers"/"tasks": those are top-level
# branches that hold same-named modules calling Gemini for different reasons —
# e.g. app.core.services.legislation_watch (an inline research call) vs.
# app.workers.tasks.legislation_watch (the scheduled Celery sweep, see
# server/CLAUDE.md's periodic-task list). Stripping both collapsed them to the
# identical label "legislation_watch", merging an ad-hoc call's cost into a
# scheduled job's rollup — the exact split an admin needs to see, since the
# worker sweep is the one that runs unattended and repeatedly.
_LABEL_STOPWORDS = {"app", "services", "routes"}


def _feature_label() -> str:
    """Best-effort caller attribution via stack inspection.

    Walks frames outward from the wrapper looking for the first frame whose
    module lives under `app.` and isn't this module — that's the service/route/
    task that actually issued the call. Must run at CALL time, not when the
    client was built: several callers cache one client in a module-level
    singleton and reuse it across requests for different features.

    "app.cappe.services.merlin" -> "cappe.merlin"
    "app.workers.tasks.compliance_checks" -> "workers.tasks.compliance_checks"
    "app.core.services.gemini_compliance" -> "core.gemini_compliance"
    """
    frame = sys._getframe(1)
    depth = 0
    try:
        while frame is not None and depth < 30:
            name = frame.f_globals.get("__name__", "")
            if name.startswith("app.") and name != __name__:
                parts = [p for p in name.split(".") if p not in _LABEL_STOPWORDS]
                label = ".".join(parts) if parts else name
                return label[:100]
            frame = frame.f_back
            depth += 1
    finally:
        del frame
    return "unknown"


def _strip_model_prefix(model: str) -> str:
    return model[len("models/"):] if model.startswith("models/") else model


def compute_cost(provider: str, model: str, input_tokens: Optional[int],
                  output_tokens: Optional[int], thinking_tokens: Optional[int]) -> Optional[float]:
    """Thinking tokens bill as output tokens (Gemini pricing treats them as
    generated output). Returns None for an unpriced model, or when there is no
    usage metadata at all (a timed-out/errored call carries no token counts —
    that's UNKNOWN cost, not zero cost. Google still bills a call that timed
    out mid-generation; recording 0 here would say the opposite)."""
    if input_tokens is None and output_tokens is None and thinking_tokens is None:
        return None
    prices = PRICING.get((provider, _strip_model_prefix(model)))
    if prices is None:
        return None
    in_price, out_price = prices
    out_total = (output_tokens or 0) + (thinking_tokens or 0)
    return (input_tokens or 0) * in_price / 1_000_000 + out_total * out_price / 1_000_000


def _extract_usage(resp: Any) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """(input, output, thinking, cached) tokens from a response's usage_metadata.
    Every field access is null-safe — embed_content responses, and some stream
    chunks, carry no usage_metadata at all."""
    um = getattr(resp, "usage_metadata", None)
    if um is None:
        return None, None, None, None
    return (
        getattr(um, "prompt_token_count", None),
        getattr(um, "candidates_token_count", None),
        getattr(um, "thoughts_token_count", None),
        getattr(um, "cached_content_token_count", None),
    )


async def _insert_row(row: dict[str, Any]) -> None:
    try:
        from ...database import connection_or_direct
        async with connection_or_direct() as conn:
            await conn.execute(
                """
                INSERT INTO ai_usage_log
                    (provider, model, feature, method, input_tokens, output_tokens,
                     thinking_tokens, cached_tokens, cost_usd, latency_ms, status, error)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                row["provider"], row["model"], row["feature"], row["method"],
                row["input_tokens"], row["output_tokens"], row["thinking_tokens"],
                row["cached_tokens"], row["cost_usd"], row["latency_ms"], row["status"],
                row["error"],
            )
    except Exception:  # noqa: BLE001 — telemetry must never break a model call
        logger.warning("ai_usage: failed to record call", exc_info=True)


async def _record_async(row: dict[str, Any]) -> None:
    """Await the insert directly. `_insert_row` never raises, so this never
    raises either — safe to await unconditionally from any async call site.

    NOT fire-and-forget: an earlier version did `loop.create_task(...)` here
    to avoid adding insert latency to the calling coroutine, but every Celery
    task body is `asyncio.run(_run())` (see app/workers/tasks/*.py — the
    worker is deliberately pool-free, celery_app.py never calls init_pool()),
    and asyncio.run() cancels any still-pending task the instant its own
    coroutine returns. A scheduled Gemini call — compliance research,
    legislation watch, the exact traffic this dashboard exists to show —
    recorded ZERO rows every time, silently. Reproduced directly: a coroutine
    shaped like a Celery task recorded 0/1 expected rows under the old
    fire-and-forget path. One INSERT is a few ms; `rate_limiter.record_call`
    already awaits inline on this same call path with no measurable effect on
    Gemini latency (typically 100s of ms to several seconds)."""
    await _insert_row(row)


def _record(row: dict[str, Any]) -> None:
    """Sync-only dispatch, for the plain (non-async) `_scall` path. Real SDK
    sync calls in this codebase all run via `asyncio.to_thread(...)` (grep
    `to_thread` in matcha_work_ai.py/recruiting.py/dashboard.py etc.), i.e. off
    the event-loop thread entirely, so `asyncio.get_running_loop()` reliably
    raises RuntimeError here and the blocking `asyncio.run()` below only ever
    blocks that worker thread, never the loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        try:
            asyncio.run(_insert_row(row))
        except Exception:  # noqa: BLE001
            logger.warning("ai_usage: failed to record call (sync path)", exc_info=True)
        return
    # A sync SDK method called from a thread that DOES have a running loop
    # is already a caller-side anti-pattern (a blocking network call on the
    # event loop thread) — fall back to fire-and-forget rather than deadlock.
    loop.create_task(_insert_row(row))


def _build_row(*, provider: str, model: str, method: str, feature: str,
                latency_ms: int, status: str, error: Optional[str] = None,
                usage: tuple[Optional[int], Optional[int], Optional[int], Optional[int]] = (None, None, None, None)) -> dict[str, Any]:
    input_tokens, output_tokens, thinking_tokens, cached_tokens = usage
    return {
        "provider": provider,
        "model": _strip_model_prefix(model),
        "feature": feature,
        "method": method,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "cached_tokens": cached_tokens,
        "cost_usd": compute_cost(provider, model, input_tokens, output_tokens, thinking_tokens),
        "latency_ms": latency_ms,
        "status": status,
        "error": error[:500] if error else None,
    }


# --- Client proxy -----------------------------------------------------------
# `client.models` / `client.aio` are READ-ONLY properties on genai.Client (no
# setattr) — attribute patching doesn't work, so this wraps with delegating
# proxy objects instead. Nothing in the codebase isinstance-checks genai.Client
# (only type annotations), so returning a proxy here is safe.

_WRAPPED_METHODS = ("generate_content", "generate_content_stream", "embed_content")


class _WrappedModels:
    def __init__(self, real: Any, *, is_async: bool, provider: str = "gemini"):
        self._real = real
        self._is_async = is_async
        self._provider = provider

    def __getattr__(self, name: str) -> Any:
        # `_real` is set in __init__, so this branch is normally dead — it's a
        # guard against a path that skips __init__ (copy.copy, unpickling):
        # without it, looking up a MISSING `_real` re-enters __getattr__('_real')
        # and recurses until RecursionError, which is a confusing failure to
        # debug compared to a plain AttributeError.
        if name == "_real":
            raise AttributeError(name)
        return getattr(self._real, name)

    def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        if self._is_async:
            return self._acall("generate_content", self._real.generate_content, args, kwargs)
        return self._scall("generate_content", self._real.generate_content, args, kwargs)

    def embed_content(self, *args: Any, **kwargs: Any) -> Any:
        if self._is_async:
            return self._acall("embed_content", self._real.embed_content, args, kwargs)
        return self._scall("embed_content", self._real.embed_content, args, kwargs)

    def generate_content_stream(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "")
        feature = _feature_label()
        provider = self._provider
        real_fn = self._real.generate_content_stream
        if self._is_async:
            async def _agen() -> Any:
                t0 = time.perf_counter()
                usage = (None, None, None, None)
                status, error = "ok", None
                try:
                    async for chunk in real_fn(*args, **kwargs):
                        u = _extract_usage(chunk)
                        if any(v is not None for v in u):
                            usage = u
                        yield chunk
                except asyncio.CancelledError:
                    status = "timeout"
                    raise
                except Exception as exc:  # noqa: BLE001
                    status, error = "error", str(exc)
                    raise
                finally:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    await _record_async(_build_row(provider=provider, model=model, method="generate_content_stream",
                                                    feature=feature, latency_ms=latency_ms, status=status,
                                                    error=error, usage=usage))
            return _agen()

        def _gen() -> Any:
            t0 = time.perf_counter()
            usage = (None, None, None, None)
            status, error = "ok", None
            try:
                for chunk in real_fn(*args, **kwargs):
                    u = _extract_usage(chunk)
                    if any(v is not None for v in u):
                        usage = u
                    yield chunk
            except Exception as exc:  # noqa: BLE001
                status, error = "error", str(exc)
                raise
            finally:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                _record(_build_row(provider=provider, model=model, method="generate_content_stream",
                                    feature=feature, latency_ms=latency_ms, status=status,
                                    error=error, usage=usage))
        return _gen()

    async def _acall(self, method: str, real_fn: Any, args: tuple, kwargs: dict) -> Any:
        model = kwargs.get("model", "")
        feature = _feature_label()
        t0 = time.perf_counter()
        try:
            resp = await real_fn(*args, **kwargs)
        except asyncio.CancelledError:
            await _record_async(_build_row(provider=self._provider, model=model, method=method, feature=feature,
                                            latency_ms=int((time.perf_counter() - t0) * 1000), status="timeout"))
            raise
        except Exception as exc:  # noqa: BLE001
            await _record_async(_build_row(provider=self._provider, model=model, method=method, feature=feature,
                                            latency_ms=int((time.perf_counter() - t0) * 1000), status="error",
                                            error=str(exc)))
            raise
        await _record_async(_build_row(provider=self._provider, model=model, method=method, feature=feature,
                                        latency_ms=int((time.perf_counter() - t0) * 1000), status="ok",
                                        usage=_extract_usage(resp)))
        return resp

    def _scall(self, method: str, real_fn: Any, args: tuple, kwargs: dict) -> Any:
        model = kwargs.get("model", "")
        feature = _feature_label()
        t0 = time.perf_counter()
        try:
            resp = real_fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            _record(_build_row(provider=self._provider, model=model, method=method, feature=feature,
                                latency_ms=int((time.perf_counter() - t0) * 1000), status="error",
                                error=str(exc)))
            raise
        _record(_build_row(provider=self._provider, model=model, method=method, feature=feature,
                            latency_ms=int((time.perf_counter() - t0) * 1000), status="ok",
                            usage=_extract_usage(resp)))
        return resp


class _WrappedAio:
    def __init__(self, real: Any):
        self._real = real

    def __getattr__(self, name: str) -> Any:
        # `_real` is set in __init__, so this branch is normally dead — it's a
        # guard against a path that skips __init__ (copy.copy, unpickling):
        # without it, looking up a MISSING `_real` re-enters __getattr__('_real')
        # and recurses until RecursionError, which is a confusing failure to
        # debug compared to a plain AttributeError.
        if name == "_real":
            raise AttributeError(name)
        return getattr(self._real, name)

    @property
    def models(self) -> _WrappedModels:
        return _WrappedModels(self._real.models, is_async=True)


class _WrappedClient:
    def __init__(self, real: Any):
        self._real = real

    def __getattr__(self, name: str) -> Any:
        # `_real` is set in __init__, so this branch is normally dead — it's a
        # guard against a path that skips __init__ (copy.copy, unpickling):
        # without it, looking up a MISSING `_real` re-enters __getattr__('_real')
        # and recurses until RecursionError, which is a confusing failure to
        # debug compared to a plain AttributeError.
        if name == "_real":
            raise AttributeError(name)
        return getattr(self._real, name)

    @property
    def models(self) -> _WrappedModels:
        return _WrappedModels(self._real.models, is_async=False)

    @property
    def aio(self) -> _WrappedAio:
        return _WrappedAio(self._real.aio)


def wrap_client(client: Any) -> Any:
    """Wrap a genai.Client so every generate_content/embed_content call (sync,
    async, and streaming) is logged to ai_usage_log. No-op when
    AI_USAGE_LOGGING=0."""
    if not LOGGING_ENABLED:
        return client
    return _WrappedClient(client)
