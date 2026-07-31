"""Unit tests for `_build_usage_meter` (GET /matcha-work/usage/meter) — no
DB/Gemini/redis. Collaborators are monkeypatched on the modules that DEFINE
them (entitlements_service, token_budget_service, doc_svc, redis_cache),
not a re-exporting facade — see server/CLAUDE.md's patch-target gotcha.

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_usage_meter.py -q
"""

import asyncio
from uuid import uuid4

from app.matcha.routes.matcha_work import workspace
from app.matcha.services.billing import entitlements_service, token_budget_service
from app.matcha.services.matcha_work import matcha_work_document as doc_svc

USER_ID = uuid4()
COMPANY_ID = uuid4()


def _run(coro):
    return asyncio.run(coro)


QUOTA_OK = {
    "used": 1000, "limit": 25000, "remaining": 24000,
    "window_hours": 12, "resets_at": "2026-08-01T00:00:00Z",
}

BUDGET_OK = {
    "free_tokens_remaining": 500_000, "subscription_tokens_remaining": 0,
    "total_tokens_remaining": 500_000, "free_token_limit": 1_000_000,
    "subscription_token_limit": 0, "has_active_subscription": False,
}

RATE_STATE_OK = {"used": 7, "limit": 120, "remaining": 113, "resets_in_seconds": 1800}


def _patch_happy_path(monkeypatch):
    async def fake_resolve_plan(user_id):
        return "free"
    async def fake_check_quota(user_id, company_id):
        return dict(QUOTA_OK)
    async def fake_get_budget(company_id):
        return dict(BUDGET_OK)
    async def fake_rate_state(key, action, limit, window):
        return dict(RATE_STATE_OK)

    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", fake_resolve_plan)
    monkeypatch.setattr(doc_svc, "check_token_quota", fake_check_quota)
    monkeypatch.setattr(token_budget_service, "get_token_budget", fake_get_budget)
    from app.core.services import redis_cache
    monkeypatch.setattr(redis_cache, "get_rate_limit_state", fake_rate_state)


class TestBuildUsageMeter:
    def test_company_user_full_shape(self, monkeypatch):
        _patch_happy_path(monkeypatch)
        result = _run(workspace._build_usage_meter(USER_ID, COMPANY_ID, "client"))
        assert result["user_quota"] == {
            "plan": "free", "used": 1000, "limit": 25000, "remaining": 24000,
            "window_hours": 12, "resets_at": "2026-08-01T00:00:00Z",
        }
        assert result["company_budget"] == BUDGET_OK
        assert result["huume_turns"] == RATE_STATE_OK

    def test_personal_user_has_null_company_blocks(self, monkeypatch):
        _patch_happy_path(monkeypatch)
        result = _run(workspace._build_usage_meter(USER_ID, None, "client"))
        assert result["user_quota"] is not None
        assert result["company_budget"] is None
        assert result["huume_turns"] is None

    def test_quota_read_failure_degrades_to_null(self, monkeypatch):
        _patch_happy_path(monkeypatch)

        async def raising(user_id, company_id):
            raise RuntimeError("db down")
        monkeypatch.setattr(doc_svc, "check_token_quota", raising)

        result = _run(workspace._build_usage_meter(USER_ID, COMPANY_ID, "client"))
        assert result["user_quota"] is None
        assert result["company_budget"] == BUDGET_OK
        assert result["huume_turns"] == RATE_STATE_OK

    def test_plan_resolve_failure_degrades_quota_to_null(self, monkeypatch):
        # resolve_plan_for_user lives inside the same try as check_token_quota
        # now — a transient failure there must not 500 the whole meter.
        _patch_happy_path(monkeypatch)

        async def raising(user_id):
            raise RuntimeError("db down")
        monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", raising)

        result = _run(workspace._build_usage_meter(USER_ID, COMPANY_ID, "client"))
        assert result["user_quota"] is None
        assert result["company_budget"] == BUDGET_OK
        assert result["huume_turns"] == RATE_STATE_OK

    def test_budget_read_failure_degrades_to_null(self, monkeypatch):
        _patch_happy_path(monkeypatch)

        async def raising(company_id):
            raise RuntimeError("db down")
        monkeypatch.setattr(token_budget_service, "get_token_budget", raising)

        result = _run(workspace._build_usage_meter(USER_ID, COMPANY_ID, "client"))
        assert result["user_quota"] is not None
        assert result["company_budget"] is None
        # huume_turns is independent of the budget read — still present.
        assert result["huume_turns"] == RATE_STATE_OK

    def test_redis_down_leaves_huume_turns_null_without_affecting_others(self, monkeypatch):
        _patch_happy_path(monkeypatch)
        from app.core.services import redis_cache

        async def none_state(key, action, limit, window):
            return None
        monkeypatch.setattr(redis_cache, "get_rate_limit_state", none_state)

        result = _run(workspace._build_usage_meter(USER_ID, COMPANY_ID, "client"))
        assert result["huume_turns"] is None
        assert result["user_quota"] is not None
        assert result["company_budget"] is not None

    def test_huume_limit_constants_shared_with_turn_pipeline(self, monkeypatch):
        # The meter must read whatever turn_pipeline actually gates on, not
        # a second hardcoded copy — patch the shared constant and assert the
        # meter's redis read used it.
        _patch_happy_path(monkeypatch)
        from app.core.services import redis_cache
        from app.matcha.services.matcha_work import turn_pipeline

        calls = []
        async def capturing_rate_state(key, action, limit, window):
            calls.append((action, limit, window))
            return dict(RATE_STATE_OK)
        monkeypatch.setattr(redis_cache, "get_rate_limit_state", capturing_rate_state)
        monkeypatch.setattr(turn_pipeline, "HUUME_TURN_LIMIT", 55)
        monkeypatch.setattr(turn_pipeline, "HUUME_TURN_WINDOW_SECONDS", 900)

        _run(workspace._build_usage_meter(USER_ID, COMPANY_ID, "client"))
        assert calls == [("huume_turn", 55, 900)]

    def test_admin_skips_company_budget_and_huume_turns(self, monkeypatch):
        # get_client_company_id hands an admin an arbitrary tenant's
        # company_id (resolve_accessible_company_scope's first match) — the
        # admin must never see that tenant's budget or an Upgrade button
        # pointed at it. Per-user quota still applies to admins (only the
        # 402 budget wall + deduction are role-skipped, not the 429 quota).
        _patch_happy_path(monkeypatch)
        result = _run(workspace._build_usage_meter(USER_ID, COMPANY_ID, "admin"))
        assert result["user_quota"] is not None
        assert result["company_budget"] is None
        assert result["huume_turns"] is None
