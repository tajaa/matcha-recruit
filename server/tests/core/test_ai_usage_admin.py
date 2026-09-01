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
