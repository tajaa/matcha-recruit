"""OpenAI costs remain visible throughout the admin usage API."""

import inspect

from app.core.routes.admin_tools import ai_usage_admin


def test_rollups_include_openai_costs():
    assert "SUM(cost_usd) AS cost_usd" in ai_usage_admin._ROLLUP_COLUMNS
    assert "provider <> 'openai'" not in ai_usage_admin._ROLLUP_COLUMNS
    assert "provider = 'openai'" not in ai_usage_admin._ROLLUP_COLUMNS


def test_call_log_does_not_mask_openai_costs():
    source = inspect.getsource(ai_usage_admin.ai_usage_calls)
    assert "CASE WHEN provider = 'openai'" not in source
    assert "cache_write_tokens, cost_usd" in source


# --- provider rollup, Espresso runs and tools, quotas -------------------------

from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402

from tests.agent_runtime.helpers import FakeConn, connection  # noqa: E402


def _metrics(**over):
    base = {"calls": 0, "cost_usd": None, "input_tokens": None, "output_tokens": None, "thinking_tokens": None,
            "cached_tokens": None, "errors": 0, "unknown_cost_calls": 0, "avg_latency_ms": None,
            "p95_latency_ms": None}
    return {**base, **over}


@pytest.mark.asyncio
async def test_summary_rolls_up_by_provider(monkeypatch):
    # `on` puts the newest first, so the catch-all goes in first.
    conn = FakeConn()
    conn.on("SELECT", _metrics(calls=4))
    conn.on("GROUP BY feature", [_metrics(feature="matcha.espresso.assistant", calls=4)])
    conn.on("GROUP BY provider, model", [_metrics(provider="brave", model="web_search", calls=4)])
    conn.on("GROUP BY provider\n", [_metrics(provider="brave", calls=4, cost_usd=0.02)])
    monkeypatch.setattr(ai_usage_admin, "get_connection", connection(conn))
    out = await ai_usage_admin.ai_usage_summary(since_hours=24)
    assert out["by_provider"] == [{"provider": "brave", **ai_usage_admin._row_to_metrics(
        _metrics(calls=4, cost_usd=0.02))}]
    assert out["by_model"][0]["model"] == "web_search"


@pytest.mark.asyncio
async def test_espresso_rolls_up_runs_and_tools(monkeypatch):
    conn = FakeConn()
    conn.on("FROM ai_usage_log", [
        _metrics(provider="anthropic", model="claude-haiku-5-5", calls=10, cost_usd=0.2),
        _metrics(provider="brave", model="web_search", calls=6, cost_usd=0.03),
        _metrics(provider="serpapi", model="google_jobs", calls=2),
    ])
    conn.on("FROM mw_project_agent_steps", [
        {"tool": "web_search", "kind": "search", "calls": 9, "ok": 7, "errors": 1, "skipped": 1, "held": 0,
         "unknown": 0, "runs": 4, "run_kinds": ["assistant", "agent_task", None],
         "last_used_at": datetime(2026, 10, 16, tzinfo=timezone.utc)},
        {"tool": "send_email", "kind": "commit", "calls": 2, "ok": 0, "errors": 0, "skipped": 0, "held": 2,
         "unknown": None, "runs": 2, "run_kinds": None, "last_used_at": None},
    ])
    conn.on("SELECT COUNT(DISTINCT requested_by)", 3)
    conn.on("GROUP BY kind", [
        {"kind": "assistant", "runs": 5, "done": 4, "failed": 1, "live": 0, "people": 2, "model_calls": 9,
         "search_calls": 3, "avg_seconds": 12.5},
        {"kind": "job_search", "runs": 2, "done": 2, "failed": None, "live": 0, "people": 1, "model_calls": None,
         "search_calls": 0, "avg_seconds": None},
    ])
    monkeypatch.setattr(ai_usage_admin, "get_connection", connection(conn))
    out = await ai_usage_admin.ai_usage_espresso(since_hours=9999)
    assert out["since_hours"] == 24  # clamped
    assert out["totals"] == {"cost_usd": pytest.approx(0.23), "runs": 7, "failed": 1, "people": 3,
                             "model_calls": 9, "search_calls": 3, "tool_calls": 11}
    assert [(r["provider"], r["calls"]) for r in out["spend"]] == [("anthropic", 10), ("brave", 6), ("serpapi", 2)]
    assert out["runs"][1] == {"kind": "job_search", "runs": 2, "done": 2, "failed": 0, "live": 0, "people": 1,
                              "model_calls": 0, "search_calls": 0, "avg_seconds": None}
    web, email = out["tools"]
    assert web["run_kinds"] == ["agent_task", "assistant"] and web["last_used_at"].startswith("2026-10-16")
    assert email["held"] == 2 and email["unknown"] == 0 and email["run_kinds"] == []
    # Every window is a bound parameter, never text in the query.
    spend_call, *others = conn.calls
    assert spend_call[2] == ("24", "matcha.espresso.")
    assert all(args == ("24",) for _m, _q, args in others)


@pytest.mark.asyncio
async def test_espresso_with_no_spend_has_no_cost(monkeypatch):
    monkeypatch.setattr(ai_usage_admin, "get_connection", connection(FakeConn()))
    out = await ai_usage_admin.ai_usage_espresso(since_hours=24)
    assert out["totals"]["cost_usd"] is None and out["spend"] == [] and out["tools"] == []


@pytest.mark.asyncio
async def test_quotas_read_brave_then_ask_the_rest(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(ai_usage_admin, "get_connection", connection(conn))
    seen = {}

    async def brave(c):
        seen["conn"] = c
        return {"provider": "brave"}

    async def all_quotas(card):
        return [card, {"provider": "serpapi"}]

    monkeypatch.setattr(ai_usage_admin.api_quotas, "brave", brave)
    monkeypatch.setattr(ai_usage_admin.api_quotas, "all_quotas", all_quotas)
    out = await ai_usage_admin.ai_usage_quotas()
    assert seen["conn"] is conn
    assert out == {"providers": [{"provider": "brave"}, {"provider": "serpapi"}]}


@pytest.mark.asyncio
async def test_the_call_log_filters_by_provider(monkeypatch):
    conn = FakeConn()
    conn.on("SELECT COUNT(*) FROM ai_usage_log", 0)
    monkeypatch.setattr(ai_usage_admin, "get_connection", connection(conn))
    out = await ai_usage_admin.ai_usage_calls(since_hours=24, provider="brave", model="web_search")
    assert out == {"total": 0, "items": []}
    count, rows = conn.calls
    assert "model = $2 AND provider = $3" in count[1] and count[2] == ("24", "web_search", "brave")
    assert rows[2] == ("24", "web_search", "brave", 100, 0)
