"""Admin endpoints for the AI usage ledger (/admin/ai-usage).

Reads `ai_usage_log`, written by the Gemini client wrapper, the direct
OpenAI Responses / Anthropic Messages recorders and the paid search APIs
(`record_api_call`) in app/core/services/ai_usage.py. Read-only over that
table — nothing here writes a row.

`/espresso` reads Espresso's own run records (`mw_project_agent_runs` and
their tool steps), and `/quotas` what each search API has left this period
(`core/services/api_quotas.py`).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import require_admin
from app.core.services import api_quotas
from app.database import get_connection

router = APIRouter()

_VALID_STATUSES = {"ok", "error", "timeout"}


def _clamp_since_hours(since_hours: int) -> int:
    return since_hours if 1 <= since_hours <= 720 else 24


def _bucket_for(since_hours: int) -> str:
    return "hour" if since_hours <= 72 else "day"


_ROLLUP_COLUMNS = """
    COUNT(*) AS calls,
    SUM(cost_usd) AS cost_usd,
    SUM(input_tokens) AS input_tokens,
    SUM(output_tokens) AS output_tokens,
    SUM(thinking_tokens) AS thinking_tokens,
    SUM(cached_tokens) AS cached_tokens,
    COUNT(*) FILTER (WHERE status <> 'ok') AS errors,
    -- NULL remains meaningful for unpriced models and calls that failed before
    -- returning token usage. OpenAI Luna responses are locally priced from
    -- their exact provider token counters, like Gemini responses.
    COUNT(*) FILTER (WHERE cost_usd IS NULL) AS unknown_cost_calls,
    AVG(latency_ms) AS avg_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms
"""


def _row_to_metrics(r: Any) -> dict[str, Any]:
    calls = int(r["calls"] or 0)
    errors = int(r["errors"] or 0)
    return {
        "calls": calls,
        "cost_usd": float(r["cost_usd"]) if r["cost_usd"] is not None else None,
        "input_tokens": int(r["input_tokens"] or 0),
        "output_tokens": int(r["output_tokens"] or 0),
        "thinking_tokens": int(r["thinking_tokens"] or 0),
        "cached_tokens": int(r["cached_tokens"] or 0),
        "errors": errors,
        "error_rate": (errors / calls) if calls else 0.0,
        "unknown_cost_calls": int(r["unknown_cost_calls"] or 0),
        "avg_latency_ms": float(r["avg_latency_ms"]) if r["avg_latency_ms"] is not None else None,
        "p95_latency_ms": float(r["p95_latency_ms"]) if r["p95_latency_ms"] is not None else None,
    }


@router.get("/admin/ai-usage/summary", dependencies=[Depends(require_admin)])
async def ai_usage_summary(since_hours: int = 24):
    since_hours = _clamp_since_hours(since_hours)

    async with get_connection() as conn:
        totals_row = await conn.fetchrow(
            f"""
            SELECT {_ROLLUP_COLUMNS}
            FROM ai_usage_log
            WHERE created_at > NOW() - ($1 || ' hours')::interval
            """,
            str(since_hours),
        )
        by_feature_rows = await conn.fetch(
            f"""
            SELECT feature, {_ROLLUP_COLUMNS}
            FROM ai_usage_log
            WHERE created_at > NOW() - ($1 || ' hours')::interval
            GROUP BY feature
            ORDER BY SUM(cost_usd) DESC NULLS LAST,
                     COUNT(*) DESC
            """,
            str(since_hours),
        )
        by_model_rows = await conn.fetch(
            f"""
            SELECT provider, model, {_ROLLUP_COLUMNS}
            FROM ai_usage_log
            WHERE created_at > NOW() - ($1 || ' hours')::interval
            GROUP BY provider, model
            ORDER BY SUM(cost_usd) DESC NULLS LAST,
                     COUNT(*) DESC
            """,
            str(since_hours),
        )
        by_provider_rows = await conn.fetch(
            f"""
            SELECT provider, {_ROLLUP_COLUMNS}
            FROM ai_usage_log
            WHERE created_at > NOW() - ($1 || ' hours')::interval
            GROUP BY provider
            ORDER BY SUM(cost_usd) DESC NULLS LAST,
                     COUNT(*) DESC
            """,
            str(since_hours),
        )

    return {
        "since_hours": since_hours,
        # _ROLLUP_COLUMNS is a bare aggregate with no GROUP BY, so fetchrow
        # always gets exactly one row (COUNT 0, sums NULL) even over an empty
        # table — totals_row is never None. No empty-table fallback needed.
        "totals": _row_to_metrics(totals_row),
        "by_feature": [
            {"feature": r["feature"], **_row_to_metrics(r)} for r in by_feature_rows
        ],
        "by_model": [
            {"provider": r["provider"], "model": r["model"], **_row_to_metrics(r)}
            for r in by_model_rows
        ],
        "by_provider": [
            {"provider": r["provider"], **_row_to_metrics(r)} for r in by_provider_rows
        ],
    }


@router.get("/admin/ai-usage/timeseries", dependencies=[Depends(require_admin)])
async def ai_usage_timeseries(since_hours: int = 24):
    since_hours = _clamp_since_hours(since_hours)
    bucket = _bucket_for(since_hours)

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT date_trunc('{bucket}', created_at) AS bucket_at,
                   COUNT(*) AS calls,
                   SUM(cost_usd) AS cost_usd,
                   COUNT(*) FILTER (WHERE status <> 'ok') AS errors
            FROM ai_usage_log
            WHERE created_at > NOW() - ($1 || ' hours')::interval
            GROUP BY bucket_at
            ORDER BY bucket_at ASC
            """,
            str(since_hours),
        )

    return {
        "bucket": bucket,
        "points": [
            {
                "at": r["bucket_at"].isoformat(),
                "calls": int(r["calls"] or 0),
                "cost_usd": float(r["cost_usd"]) if r["cost_usd"] is not None else None,
                "errors": int(r["errors"] or 0),
            }
            for r in rows
        ],
    }


@router.get("/admin/ai-usage/calls", dependencies=[Depends(require_admin)])
async def ai_usage_calls(
    since_hours: int = 24,
    feature: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    since_hours = _clamp_since_hours(since_hours)
    if limit < 1 or limit > 500:
        limit = 100
    if offset < 0:
        offset = 0
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    filters = ["created_at > NOW() - ($1 || ' hours')::interval"]
    args: list[Any] = [str(since_hours)]
    if feature:
        args.append(feature)
        filters.append(f"feature = ${len(args)}")
    if model:
        args.append(model)
        filters.append(f"model = ${len(args)}")
    if status:
        args.append(status)
        filters.append(f"status = ${len(args)}")
    if provider:
        args.append(provider)
        filters.append(f"provider = ${len(args)}")

    args.append(limit)
    args.append(offset)

    async with get_connection() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM ai_usage_log WHERE {' AND '.join(filters)}",
            *args[:-2],
        )
        rows = await conn.fetch(
            f"""
            SELECT id, provider, model, feature, method, input_tokens, output_tokens,
                   thinking_tokens, cached_tokens, cache_write_tokens, cost_usd,
                   latency_ms, status, error,
                   provider_response_id, provider_status, service_tier, created_at
            FROM ai_usage_log
            WHERE {' AND '.join(filters)}
            ORDER BY id DESC
            LIMIT ${len(args) - 1} OFFSET ${len(args)}
            """,
            *args,
        )

    return {
        "total": int(total or 0),
        "items": [
            {
                "id": r["id"],
                "provider": r["provider"],
                "model": r["model"],
                "feature": r["feature"],
                "method": r["method"],
                "input_tokens": r["input_tokens"],
                "output_tokens": r["output_tokens"],
                "thinking_tokens": r["thinking_tokens"],
                "cached_tokens": r["cached_tokens"],
                "cache_write_tokens": r["cache_write_tokens"],
                "cost_usd": float(r["cost_usd"]) if r["cost_usd"] is not None else None,
                "latency_ms": r["latency_ms"],
                "status": r["status"],
                "error": r["error"],
                "provider_response_id": r["provider_response_id"],
                "provider_status": r["provider_status"],
                "service_tier": r["service_tier"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }


# Every Espresso surface logs under this prefix (assistant, tasks.<playbook>,
# job_search, agent_card, repo_question, task_draft).
ESPRESSO_FEATURE_PREFIX = "matcha.espresso."


@router.get("/admin/ai-usage/espresso", dependencies=[Depends(require_admin)])
async def ai_usage_espresso(since_hours: int = 24):
    """Espresso's spend by provider and model (the ledger's `matcha.espresso.*`
    rows: models, Brave and the other search APIs, Claude's hosted searches),
    its agent runs by kind, and the tools those runs used (the run records)."""
    since_hours = _clamp_since_hours(since_hours)

    async with get_connection() as conn:
        spend_rows = await conn.fetch(
            f"""
            SELECT provider, model, {_ROLLUP_COLUMNS}
            FROM ai_usage_log
            WHERE created_at > NOW() - ($1 || ' hours')::interval
              AND starts_with(feature, $2)
            GROUP BY provider, model
            ORDER BY SUM(cost_usd) DESC NULLS LAST,
                     COUNT(*) DESC
            """,
            str(since_hours), ESPRESSO_FEATURE_PREFIX,
        )
        run_rows = await conn.fetch(
            """
            SELECT kind,
                   COUNT(*) AS runs,
                   COUNT(*) FILTER (WHERE status = 'done') AS done,
                   COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                   COUNT(*) FILTER (WHERE status IN ('queued', 'running')) AS live,
                   COUNT(DISTINCT requested_by) AS people,
                   SUM(model_calls) AS model_calls,
                   SUM(search_calls) AS search_calls,
                   AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))
                       FILTER (WHERE completed_at IS NOT NULL AND started_at IS NOT NULL) AS avg_seconds
            FROM mw_project_agent_runs
            WHERE created_at > NOW() - ($1 || ' hours')::interval
            GROUP BY kind
            ORDER BY COUNT(*) DESC
            """,
            str(since_hours),
        )
        people = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT requested_by) FROM mw_project_agent_runs
            WHERE created_at > NOW() - ($1 || ' hours')::interval
            """,
            str(since_hours),
        )
        tool_rows = await conn.fetch(
            """
            SELECT s.tool, s.kind,
                   COUNT(*) AS calls,
                   COUNT(*) FILTER (WHERE s.status = 'ok') AS ok,
                   COUNT(*) FILTER (WHERE s.status = 'error') AS errors,
                   COUNT(*) FILTER (WHERE s.status = 'skipped') AS skipped,
                   COUNT(*) FILTER (WHERE s.status IN ('held', 'denied')) AS held,
                   COUNT(*) FILTER (WHERE s.status IN ('claimed', 'unknown')) AS unknown,
                   COUNT(DISTINCT s.run_id) AS runs,
                   ARRAY_AGG(DISTINCT r.kind) AS run_kinds,
                   MAX(s.created_at) AS last_used_at
            FROM mw_project_agent_steps s
            JOIN mw_project_agent_runs r ON r.id = s.run_id
            WHERE s.created_at > NOW() - ($1 || ' hours')::interval
            GROUP BY s.tool, s.kind
            ORDER BY COUNT(*) DESC
            LIMIT 200
            """,
            str(since_hours),
        )

    def _int(value: Any) -> int:
        return int(value or 0)

    runs = [
        {
            "kind": r["kind"],
            "runs": _int(r["runs"]),
            "done": _int(r["done"]),
            "failed": _int(r["failed"]),
            "live": _int(r["live"]),
            "people": _int(r["people"]),
            "model_calls": _int(r["model_calls"]),
            "search_calls": _int(r["search_calls"]),
            "avg_seconds": float(r["avg_seconds"]) if r["avg_seconds"] is not None else None,
        }
        for r in run_rows
    ]
    tools = [
        {
            "tool": r["tool"],
            "kind": r["kind"],
            "calls": _int(r["calls"]),
            "ok": _int(r["ok"]),
            "errors": _int(r["errors"]),
            "skipped": _int(r["skipped"]),
            "held": _int(r["held"]),
            "unknown": _int(r["unknown"]),
            "runs": _int(r["runs"]),
            "run_kinds": sorted(k for k in (r["run_kinds"] or []) if k),
            "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
        }
        for r in tool_rows
    ]
    spend = [
        {"provider": r["provider"], "model": r["model"], **_row_to_metrics(r)} for r in spend_rows
    ]
    return {
        "since_hours": since_hours,
        "spend": spend,
        "totals": {
            "cost_usd": sum(r["cost_usd"] for r in spend if r["cost_usd"] is not None)
            if any(r["cost_usd"] is not None for r in spend) else None,
            "runs": sum(r["runs"] for r in runs),
            "failed": sum(r["failed"] for r in runs),
            "people": _int(people),
            "model_calls": sum(r["model_calls"] for r in runs),
            "search_calls": sum(r["search_calls"] for r in runs),
            "tool_calls": sum(t["calls"] for t in tools),
        },
        "runs": runs,
        "tools": tools,
    }


@router.get("/admin/ai-usage/quotas", dependencies=[Depends(require_admin)])
async def ai_usage_quotas():
    """What each paid search API has left this period. Brave's is the latest
    its responses reported; SerpApi's and SearchAPI's are asked live from their
    free account endpoints."""
    async with get_connection() as conn:
        brave = await api_quotas.brave(conn)
    return {"providers": await api_quotas.all_quotas(brave)}
