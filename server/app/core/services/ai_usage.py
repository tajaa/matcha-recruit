"""Provider-general AI call usage ledger.

Wraps the `genai.Client` returned by `genai_client.get_genai_client()` so every
`generate_content` / `generate_content_stream` / `embed_content` call — sync or
async — logs its model, caller ("feature"), token counts, cost, latency, and
outcome to `ai_usage_log`, with zero changes at any of the ~100 call sites.

This is the LEDGER (what did we use, where, and what cost can be attributed
locally). `rate_limiter.py` / `api_rate_limits` is the separate, pre-existing
GUARD (are we about to spend too much) — untouched by this module, and not
reused for storage: the guard only ever needed a call count, this needs the full
row.

Known gaps (see admin UI / API docs for how these surface):
  - Live-API sessions (voice interviews) are not wrapped — `client.aio.live` is
    a distinct surface this module doesn't touch. Two call sites total today.
  - No per-company attribution — feature-level only. A nullable company_id
    column can be added later without reshaping this module.

The stack-derived label above is per MODULE, not per code path within it — too
coarse when one module has more than one real cost center (a multi-call agent
loop vs. its one-off image-generation tool, say). `feature_scope(label)` is the
escape hatch: it overrides the label for every wrapped call issued inside the
`with` block, no matter how deep the call chain — including through
`asyncio.to_thread`, since `contextvars.Context` is copied into the thread.
Use sparingly (each distinct label is a permanent row in "by feature"); the
default stack-derived label is right for the other ~100 call sites.

Paid APIs that bill per request rather than per token (Brave, through
`matcha_work/search_apis.answer`; SearchAPI, SerpApi and Google Places until
2026-10-18, whose rows and prices stay for the history) log here too,
one row per request: `record_api_call`, priced from `API_PRICING`. Claude's
hosted web search bills per search on top of the tokens, so each one Anthropic
reports is its own `anthropic / web_search` row. Quota a provider reports on its
responses (Brave's monthly window) is kept as the latest snapshot in
`platform_settings` (`save_api_quota`, key `api_quota.<provider>`), which
/admin/ai-usage reads back.

Set AI_USAGE_LOGGING=0 to disable (read once at import; the client is then
returned unwrapped).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

LOGGING_ENABLED = os.getenv("AI_USAGE_LOGGING", "1") != "0"

# --- Pricing --------------------------------------------------------------
# USD per 1M tokens, (input_price, output_price). Gemini rates were verified
# against ai.google.dev/gemini-api/docs/pricing; OpenAI Luna rates against
# developers.openai.com/api/docs/models/gpt-5.6-luna as of 2026-09-01. A model
# absent here
# logs cost_usd=NULL rather than a guessed number — the admin UI surfaces
# "unpriced" calls so a real row gets added instead of a fabricated price.
PRICING: dict[tuple[str, str], tuple[float, float]] = {
    # Responses output_tokens already includes reasoning tokens. The provider
    # payload also splits cached reads and cache writes out of input_tokens;
    # compute_cost applies their $0.02/M and 1.25x write rates respectively.
    ("openai", "gpt-5.6-luna"): (0.20, 1.20),
    # Anthropic output_tokens already includes thinking. Haiku 5.5 bills a
    # prompt above 100K input at 5x (see compute_cost). Schedule-assistant
    # model picker only (services/huume/claude_client.py).
    ("anthropic", "claude-haiku-5-5"): (0.10, 0.50),
    ("anthropic", "claude-sonnet-5-5"): (2.00, 10.00),
    ("gemini", "gemini-3.7-flash"): (1.50, 7.50),  # fleet quality tier (rate mirrors 3.6-flash pending 3.7 GA)
    ("gemini", "gemini-3.6-flash"): (1.50, 7.50),  # kept for already-logged rows
    ("gemini", "gemini-3.5-flash"): (1.50, 9.00),
    ("gemini", "gemini-3.7-flash-lite"): (0.30, 2.50),  # kept for already-logged rows
    ("gemini", "gemini-3.5-flash-lite"): (0.30, 2.50),  # active fleet cheap tier
    ("gemini", "gemini-3-flash-preview"): (0.50, 3.00),
    ("gemini", "gemini-3.1-flash-lite"): (0.25, 1.50),
    # Image output bills at the image rate (~$30/1M ≈ $0.039/1290-token image).
    # Same figure already used for dollar-based billing in
    # matcha/services/model_pricing.py — ported here so image-gen calls (the
    # editor's Generate button, Merlin's agent-loop generate_image tool) stop
    # logging cost_usd=NULL and showing as "unpriced" in the admin dashboard.
    # GA name is what every caller sends now (image_gen.IMAGE_MODEL etc. moved
    # off "-preview" 2026-07-22 — Google shut that model down 2026-06-25).
    # "-preview" stays priced too: existing ai_usage_log rows still carry it,
    # and a stale client binary in flight during the deploy would otherwise
    # start logging unpriced calls.
    ("gemini", "gemini-3.1-flash-image"): (0.30, 30.00),
    ("gemini", "gemini-3.1-flash-image-preview"): (0.30, 30.00),
}

_CACHED_INPUT_PRICING: dict[tuple[str, str], float] = {
    ("openai", "gpt-5.6-luna"): 0.02,
    ("anthropic", "claude-haiku-5-5"): 0.01,
    ("anthropic", "claude-sonnet-5-5"): 0.20,
}

# Anthropic models whose whole request reprices above an input threshold:
# (threshold, input multiplier, output multiplier).
_ANTHROPIC_LONG_CONTEXT: dict[str, tuple[int, float, float]] = {
    "claude-haiku-5-5": (100_000, 5.0, 5.0),
}

# USD per successful request, for APIs that bill by the request. Keyed
# (provider, model) like PRICING; "model" is the endpoint or SKU. A request
# that failed is not billed and logs 0. A provider absent here logs NULL:
# SearchAPI and SerpApi sell monthly plans, not a per-request price, so the
# admin page shows their plan and searches left from their account APIs
# instead of a made-up rate.
API_PRICING: dict[tuple[str, str], float] = {
    # Brave Search API: $5 per 1,000 at list price. Brave's price is the
    # account's plan (the Free plan's 2,000 a month cost nothing), so
    # BRAVE_SEARCH_USD_PER_1000 overrides it; see `api_price`.
    ("brave", "web_search"): 0.005,
    # Google Places API (New) Text Search, first volume tier, for the rows
    # research tasks logged until 2026-10-18 (nothing calls Places now). The
    # SKU was the dearest field the request's mask asked for: a search's
    # (website, phone, rating, hours) Enterprise, an anchor's (name and
    # location) Pro. Google's free monthly calls per SKU (1,000 Enterprise,
    # 5,000 Pro) are not netted out, so this overstates a quiet month.
    ("google_places", "text_search_enterprise"): 0.035,
    ("google_places", "text_search_pro"): 0.032,
    # Claude's hosted web search: $10 per 1,000 searches, on top of tokens.
    ("anthropic", "web_search"): 0.01,
}

# Modules that only carry a call to a provider. The feature label is the
# first frame past them, so a search shows the code that asked for it.
_TRANSPORT_MODULES = frozenset({
    __name__,
    "app.matcha.services.matcha_work.search_apis",
    "app.matcha.services.matcha_work.brave_search",
})

QUOTA_KEY_PREFIX = "api_quota."

# Overrides `_feature_label()`'s stack-derived label for every wrapped call
# made inside a `feature_scope(...)` block — see that function and the module
# docstring. `to_thread` copies the current Context into the worker thread, so
# a scope entered before an `asyncio.to_thread(...)` call is still visible to
# the wrapped SDK call running inside it.
_feature_override: "ContextVar[Optional[str]]" = ContextVar("ai_usage_feature_override", default=None)


@contextmanager
def feature_scope(label: str) -> Iterator[None]:
    """Attribute every wrapped Gemini call made inside this block to `label`,
    overriding the default stack-derived one. See the module docstring."""
    token = _feature_override.set(label)
    try:
        yield
    finally:
        _feature_override.reset(token)

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

# services/ split into domain subpackages 2026-07-25 (matcha_work_ai.py ->
# services/matcha_work/matcha_work_ai.py, etc). The domain segment is purely
# organizational nesting like "services"/"routes" above and must strip the
# same way, so a moved module's label is byte-identical to its pre-move label
# and old ai_usage_log rows keep rolling up under it. Deliberately NOT folded
# into _LABEL_STOPWORDS: several domain names (insurance/pilots/
# onboarding) collide with routes/ grouping-folder names, and stripping those
# generically would risk exactly the cross-branch collision the comment above
# warns about. Matched positionally instead — only the segment right after
# "app.matcha.services." is a candidate, never a same-named segment elsewhere.
_SERVICES_DOMAINS = {
    "ir", "er", "discipline", "leave", "scheduling", "training", "onboarding",
    "hris", "benefits", "workforce", "risk_analytics", "matcha_work", "billing",
    "pilots", "insurance", "property", "interviews",
}

# A domain service occasionally splits further into its own subpackage
# (services/pilots/legal_defense.py -> services/pilots/legal_defense/{chat,law,...}.py,
# core-reorg 2026-07-25). The leaf module name is internal organization, not a
# distinct feature, so it must collapse back out the same way the domain
# folder does above — otherwise "matcha.legal_defense.chat" and
# "matcha.legal_defense.law" fragment what used to roll up as one
# "matcha.legal_defense" label.
#
# THIS LIST GOING STALE IS A SILENT DATA BUG, not a crash: the admin AI-cost
# console GROUPs BY `ai_usage_log.feature`, so an unlisted split package makes
# its historical label stop accruing while N new per-leaf-module labels appear
# that don't roll up with it. It shipped exactly that way once — the round-2
# refactor split 6 more packages and only `legal_defense` was listed, silently
# fragmenting 8 live Gemini callsites. `tests/core/test_ai_usage.py::
# test_split_service_packages_covers_every_real_split_package` now derives the
# truth from the services tree and fails if this set drifts again; keep it a
# literal (no filesystem walk on the hot path of every AI call).
_SPLIT_SERVICE_PACKAGES = {
    "analysis_packs",
    "autopilot",
    "handbook_pilot",
    "hr_pilot_corpus",
    "job_search",
    "legal_defense",
    "matcha_work_ai",
    "matcha_work_document",
    "project_agent",
    "agent_card",
    "agent_runtime",
    "agent_tasks",
    "browser",
    "recaps",
    "project_service",
    "risk_assessment_service",
}


def _feature_label() -> str:
    """Best-effort caller attribution via stack inspection.

    Walks frames outward from the wrapper looking for the first frame whose
    module lives under `app.` and isn't this module or another transport
    (`_TRANSPORT_MODULES`) — that's the service/route/task that actually
    issued the call. Must run at CALL time, not when the
    client was built: several callers cache one client in a module-level
    singleton and reuse it across requests for different features.

    "app.cappe.services.merlin" -> "cappe.merlin"
    "app.workers.tasks.compliance_checks" -> "workers.tasks.compliance_checks"
    "app.core.services.gemini_compliance" -> "core.gemini_compliance"

    `feature_scope(...)` wins when set — checked first, before the (more
    expensive) frame walk.
    """
    override = _feature_override.get()
    if override is not None:
        return override[:100]

    frame = sys._getframe(1)
    depth = 0
    try:
        while frame is not None and depth < 30:
            name = frame.f_globals.get("__name__", "")
            if name.startswith("app.") and name not in _TRANSPORT_MODULES:
                segs = name.split(".")
                if (len(segs) > 3 and segs[1] == "matcha" and segs[2] == "services"
                        and segs[3] in _SERVICES_DOMAINS):
                    del segs[3]
                if (len(segs) > 4 and segs[1] == "matcha" and segs[2] == "services"
                        and segs[3] in _SPLIT_SERVICE_PACKAGES):
                    del segs[4]
                parts = [p for p in segs if p not in _LABEL_STOPWORDS]
                label = ".".join(parts) if parts else name
                return label[:100]
            frame = frame.f_back
            depth += 1
    finally:
        del frame
    return "unknown"


def _strip_model_prefix(model: str) -> str:
    return model[len("models/"):] if model.startswith("models/") else model


def _pricing_key(provider: str, model: str) -> tuple[str, str]:
    """Map provider snapshots onto their published pricing alias."""
    normalized = _strip_model_prefix(model)
    if provider == "openai" and normalized.startswith("gpt-5.6-luna-"):
        normalized = "gpt-5.6-luna"
    return provider, normalized


def compute_cost(provider: str, model: str, input_tokens: Optional[int],
                  output_tokens: Optional[int], thinking_tokens: Optional[int],
                  cached_tokens: Optional[int] = None,
                  cache_write_tokens: Optional[int] = None,
                  cache_write_1h_tokens: Optional[int] = None) -> Optional[float]:
    """Return the token-derived USD cost for one provider response.

    Gemini reports thinking separately from candidates, so both are billed as
    output. OpenAI Responses includes reasoning in output_tokens already. Its
    input total includes cached reads and cache writes, which have distinct
    Luna rates. Cache writes cost 1.25x input; the part of them written with
    the 1-hour TTL (`cache_write_1h_tokens`, Anthropic's
    `usage.cache_creation.ephemeral_1h_input_tokens`) costs 2x. Returns None
    when the model is unpriced or no usage metadata survived an
    errored/timed-out call.
    """
    if all(value is None for value in (
        input_tokens, output_tokens, thinking_tokens, cached_tokens, cache_write_tokens,
    )):
        return None
    key = _pricing_key(provider, model)
    prices = PRICING.get(key)
    if prices is None:
        return None
    in_price, out_price = prices
    input_total = max(input_tokens or 0, 0)
    cached_total = min(max(cached_tokens or 0, 0), input_total)
    write_total = min(max(cache_write_tokens or 0, 0), input_total - cached_total)
    uncached_total = input_total - cached_total - write_total
    write_1h_total = min(max(cache_write_1h_tokens or 0, 0), write_total)
    cached_price = _CACHED_INPUT_PRICING.get(key, in_price)
    input_cost = (
        uncached_total * in_price
        + cached_total * cached_price
        + (write_total - write_1h_total) * in_price * 1.25
        + write_1h_total * in_price * 2.0
    )
    output_total = max(output_tokens or 0, 0)
    # Responses and Messages both count reasoning inside output_tokens.
    if provider not in ("openai", "anthropic"):
        output_total += max(thinking_tokens or 0, 0)

    # GPT-5.6 applies long-context rates to the full request above 272K input.
    input_multiplier = 2.0 if provider == "openai" and input_total > 272_000 else 1.0
    output_multiplier = 1.5 if provider == "openai" and input_total > 272_000 else 1.0
    if provider == "anthropic" and key[1] in _ANTHROPIC_LONG_CONTEXT:
        threshold, in_mult, out_mult = _ANTHROPIC_LONG_CONTEXT[key[1]]
        if input_total > threshold:
            input_multiplier, output_multiplier = in_mult, out_mult
    return (
        input_cost * input_multiplier
        + output_total * out_price * output_multiplier
    ) / 1_000_000


def _extract_usage(resp: Any) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]]:
    """(input, output, thinking, cached, cache-write) tokens from usage metadata.
    Every field access is null-safe — embed_content responses, and some stream
    chunks, carry no usage_metadata at all."""
    um = getattr(resp, "usage_metadata", None)
    if um is None:
        return None, None, None, None, None
    return (
        getattr(um, "prompt_token_count", None),
        getattr(um, "candidates_token_count", None),
        getattr(um, "thoughts_token_count", None),
        getattr(um, "cached_content_token_count", None),
        getattr(um, "cache_write_token_count", None),
    )


async def _insert_row(row: dict[str, Any], *, direct: bool = False) -> None:
    """`direct` forces a raw (non-pooled) connection — set it when this runs on
    an event loop that is NOT the one the app's pool was created on. See
    `_record`'s no-running-loop branch."""
    try:
        from ...database import connection_or_direct
        async with connection_or_direct(force_direct=direct) as conn:
            await conn.execute(
                """
                INSERT INTO ai_usage_log
                    (provider, model, feature, method, input_tokens, output_tokens,
                     thinking_tokens, cached_tokens, cache_write_tokens, cost_usd,
                     latency_ms, status, error, provider_response_id, provider_status,
                     service_tier)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, $16)
                """,
                row["provider"], row["model"], row["feature"], row["method"],
                row["input_tokens"], row["output_tokens"], row["thinking_tokens"],
                row["cached_tokens"], row["cache_write_tokens"], row["cost_usd"],
                row["latency_ms"], row["status"], row["error"],
                row["provider_response_id"], row["provider_status"], row["service_tier"],
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
            # direct=True is load-bearing: `asyncio.run` creates a BRAND NEW
            # loop, and in the API process the app's asyncpg pool belongs to
            # the main loop. Acquiring from it here raises "got Future
            # attached to a different loop" and the row is lost — which is
            # exactly how image generation (the one path that reaches this
            # branch, via image_gen's `asyncio.to_thread(_generate_sync)`)
            # silently recorded nothing while every async caller recorded
            # fine. A raw per-call connection is correct for a foreign loop.
            asyncio.run(_insert_row(row, direct=True))
        except Exception:  # noqa: BLE001
            logger.warning("ai_usage: failed to record call (sync path)", exc_info=True)
        return
    # A sync SDK method called from a thread that DOES have a running loop
    # is already a caller-side anti-pattern (a blocking network call on the
    # event loop thread) — fall back to fire-and-forget rather than deadlock.
    loop.create_task(_insert_row(row))


def _build_row(*, provider: str, model: str, method: str, feature: str,
                latency_ms: Optional[int], status: str, error: Optional[str] = None,
                usage: tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]] = (None, None, None, None, None),
                provider_response_id: Optional[str] = None,
                provider_status: Optional[str] = None,
                service_tier: Optional[str] = None,
                cache_write_1h_tokens: Optional[int] = None) -> dict[str, Any]:
    input_tokens, output_tokens, thinking_tokens, cached_tokens, cache_write_tokens = usage
    return {
        "provider": provider,
        "model": _strip_model_prefix(model),
        "feature": feature,
        "method": method,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "cached_tokens": cached_tokens,
        "cache_write_tokens": cache_write_tokens,
        "cost_usd": compute_cost(
            provider, model, input_tokens, output_tokens, thinking_tokens,
            cached_tokens, cache_write_tokens, cache_write_1h_tokens,
        ),
        "latency_ms": latency_ms,
        "status": status,
        "error": error[:500] if error else None,
        "provider_response_id": provider_response_id[:200] if provider_response_id else None,
        "provider_status": provider_status[:50] if provider_status else None,
        "service_tier": service_tier[:50] if service_tier else None,
    }


async def record_openai_response(
    *, model: str, latency_ms: int, response: Optional[dict[str, Any]] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None, thinking_tokens: Optional[int] = None,
    cached_tokens: Optional[int] = None, cache_write_tokens: Optional[int] = None,
    error: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    """Record exact usage from one direct Responses API call.

    Most existing callers are Gemini SDK proxies. Huume uses a small httpx
    adapter for Responses calls. Successful callers pass the provider payload
    so this function owns the Responses schema mapping; explicit token fields
    remain as a compatibility fallback for callers without a retained payload.

    Dollar cost is derived from exact response token counters and the published
    Luna rates. OpenAI's organization Costs API remains invoice-authoritative,
    but cannot group billed dollars by Matcha's per-call feature labels.
    """
    if not LOGGING_ENABLED:
        return
    payload = response if isinstance(response, dict) else {}
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    input_details = usage.get("input_tokens_details")
    input_details = input_details if isinstance(input_details, dict) else {}
    output_details = usage.get("output_tokens_details")
    output_details = output_details if isinstance(output_details, dict) else {}

    actual_model = payload.get("model")
    actual_model = actual_model if isinstance(actual_model, str) and actual_model else model
    provider_response_id = payload.get("id")
    provider_response_id = provider_response_id if isinstance(provider_response_id, str) else None
    provider_status = payload.get("status")
    provider_status = provider_status if isinstance(provider_status, str) else None
    service_tier = payload.get("service_tier")
    service_tier = service_tier if isinstance(service_tier, str) else None

    row = _build_row(
        provider="openai", model=actual_model, method="responses.create",
        feature=_feature_label(), latency_ms=latency_ms,
        status=status if status in {"ok", "error", "timeout"} else ("error" if error else "ok"),
        error=error,
        usage=(
            usage.get("input_tokens", input_tokens),
            usage.get("output_tokens", output_tokens),
            output_details.get("reasoning_tokens", thinking_tokens),
            input_details.get("cached_tokens", cached_tokens),
            input_details.get("cache_write_tokens", cache_write_tokens),
        ),
        provider_response_id=provider_response_id,
        provider_status=provider_status,
        service_tier=service_tier,
    )
    await _record_async(row)


async def record_anthropic_response(
    *, model: str, latency_ms: int, message: Optional[dict[str, Any]] = None,
    error: Optional[str] = None, status: Optional[str] = None,
) -> None:
    """Record exact usage from one Anthropic Messages call.

    Messages reports `input_tokens` EXCLUDING cache reads and cache writes;
    the ledger's `input_tokens` is the whole prompt (as Responses reports it),
    so the three are summed here and the cached/write split kept alongside.
    """
    if not LOGGING_ENABLED:
        return
    payload = message if isinstance(message, dict) else {}
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    uncached = usage.get("input_tokens")
    cache_read = usage.get("cache_read_input_tokens") or 0
    cache_write = usage.get("cache_creation_input_tokens") or 0
    by_ttl = usage.get("cache_creation")
    cache_write_1h = (by_ttl.get("ephemeral_1h_input_tokens") or 0) if isinstance(by_ttl, dict) else 0
    input_total = None if uncached is None else uncached + cache_read + cache_write
    actual_model = payload.get("model")
    actual_model = actual_model if isinstance(actual_model, str) and actual_model else model
    response_id = payload.get("id")
    stop_reason = payload.get("stop_reason")
    feature = _feature_label()
    row = _build_row(
        provider="anthropic", model=actual_model, method="messages.create",
        feature=feature, latency_ms=latency_ms,
        status=status if status in {"ok", "error", "timeout"} else ("error" if error else "ok"),
        error=error,
        usage=(
            input_total, usage.get("output_tokens"), None,
            cache_read if input_total is not None else None,
            cache_write if input_total is not None else None,
        ),
        provider_response_id=response_id if isinstance(response_id, str) else None,
        provider_status=stop_reason if isinstance(stop_reason, str) else None,
        service_tier=usage.get("service_tier") if isinstance(usage.get("service_tier"), str) else None,
        cache_write_1h_tokens=cache_write_1h,
    )
    await _record_async(row)
    # Hosted searches bill per search whatever became of the message, so a
    # timed-out stream that searched still logs them.
    server_tools = usage.get("server_tool_use")
    searches = server_tools.get("web_search_requests") if isinstance(server_tools, dict) else None
    if isinstance(searches, int) and searches > 0:
        for _ in range(min(searches, 50)):
            await _record_async(_api_row(
                provider="anthropic", model="web_search", method="server_tool_use",
                feature=feature, latency_ms=None, status="ok",
            ))


# --- Request-priced APIs ----------------------------------------------------

# The env var that sets Brave's price for this account's plan, in USD per
# 1,000 searches (0 on Brave's Free plan).
BRAVE_PRICE_ENV = "BRAVE_SEARCH_USD_PER_1000"


def api_price(provider: str, model: str) -> Optional[float]:
    """USD per request, or None for a provider with no per-request price.
    Brave's comes from BRAVE_SEARCH_USD_PER_1000 when that is set to a
    number, read per call so the worker needs no restart to pick it up."""
    price = API_PRICING.get((provider, model))
    if price is not None and provider == "brave":
        given = os.getenv(BRAVE_PRICE_ENV, "").strip()
        try:
            override = float(given) if given else None
        except ValueError:
            override = None
        if override is not None and override >= 0:
            return override / 1000
    return price


def api_cost(provider: str, model: str, status: str) -> Optional[float]:
    """USD for one request: its price (`api_price`) when it succeeded, 0 when
    it failed (not billed), None for a provider with no per-request price."""
    price = api_price(provider, model)
    if price is None:
        return None
    return price if status == "ok" else 0.0


def _api_row(*, provider: str, model: str, method: str, feature: str,
             latency_ms: Optional[int], status: str, error: Optional[str] = None) -> dict[str, Any]:
    row = _build_row(provider=provider, model=model, method=method, feature=feature,
                     latency_ms=latency_ms, status=status, error=error)
    row["cost_usd"] = api_cost(provider, model, status)
    return row


async def record_api_call(*, provider: str, model: str, method: str, latency_ms: int,
                          status: str, error: Optional[str] = None) -> None:
    """Record one request to an API that bills by the request (see
    `API_PRICING`). Never raises."""
    if not LOGGING_ENABLED:
        return
    await _record_async(_api_row(
        provider=provider, model=model, method=method, feature=_feature_label(),
        latency_ms=latency_ms, status=status if status in {"ok", "error", "timeout"} else "error",
        error=error,
    ))


async def _save_quota(key: str, value: dict[str, Any]) -> None:
    try:
        from ...database import connection_or_direct
        async with connection_or_direct() as conn:
            await conn.execute(
                """
                INSERT INTO platform_settings (key, value, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """,
                key, json.dumps(value),
            )
    except Exception:  # noqa: BLE001 — telemetry must never break a search
        logger.warning("ai_usage: failed to save %s", key, exc_info=True)


async def save_api_quota(provider: str, *, limit: Optional[int], remaining: Optional[int],
                         reset_seconds: Optional[float], window_seconds: Optional[int] = None) -> None:
    """Keep the quota a provider reported on its latest response, for
    /admin/ai-usage. Only the latest matters, so it is one row per provider.
    Never raises."""
    if not LOGGING_ENABLED:
        return
    now = datetime.now(timezone.utc)
    resets_at = now + timedelta(seconds=reset_seconds) if reset_seconds is not None else None
    await _save_quota(f"{QUOTA_KEY_PREFIX}{provider}", {
        "limit": limit,
        "remaining": remaining,
        "window_seconds": window_seconds,
        "resets_at": resets_at.isoformat() if resets_at else None,
        "observed_at": now.isoformat(),
    })


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
                usage = (None, None, None, None, None)
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
            usage = (None, None, None, None, None)
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
