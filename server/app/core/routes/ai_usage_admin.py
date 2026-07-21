"""Admin endpoints for the AI usage ledger (/admin/ai-usage).

Reads `ai_usage_log`, written by every Gemini call via the
`get_genai_client()` -> `ai_usage.wrap_client()` instrumentation
(app/core/services/ai_usage.py). Read-only over that table — nothing here
writes a row; the wrapper is the only writer.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_admin
from ...database import get_connection

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
    -- NULL cost has two causes, both meaning "the true total is undercounted":
    -- an unpriced model (see ai_usage.PRICING), or a timed-out/errored call
    -- that carries no token counts at all (compute_cost returns None rather
    -- than 0 for exactly that reason — see ai_usage.py).
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
            ORDER BY SUM(cost_usd) DESC NULLS LAST, COUNT(*) DESC
            """,
            str(since_hours),
        )
        by_model_rows = await conn.fetch(
            f"""
            SELECT provider, model, {_ROLLUP_COLUMNS}
            FROM ai_usage_log
            WHERE created_at > NOW() - ($1 || ' hours')::interval
            GROUP BY provider, model
            ORDER BY SUM(cost_usd) DESC NULLS LAST, COUNT(*) DESC
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
                   thinking_tokens, cached_tokens, cost_usd, latency_ms, status, error, created_at
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
                "cost_usd": float(r["cost_usd"]) if r["cost_usd"] is not None else None,
                "latency_ms": r["latency_ms"],
                "status": r["status"],
                "error": r["error"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }
