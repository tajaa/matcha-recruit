"""Unit coverage for Matcha Work company token budgets."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.matcha.services.billing import token_budget_service


def _budget_row(free_token_limit: int, free_tokens_used: int = 0) -> dict:
    return {
        "free_token_limit": free_token_limit,
        "free_tokens_used": free_tokens_used,
        "subscription_token_limit": 0,
        "subscription_tokens_used": 0,
        "subscription_period_start": None,
        "updated_at": datetime.now(timezone.utc),
    }


class BudgetConnection:
    def __init__(self, row: dict, *, lose_upgrade_race: bool = False):
        self.row = row
        self.lose_upgrade_race = lose_upgrade_race
        self.fetchrow_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query: str, *args):
        self.fetchrow_calls.append((query, args))
        if query.lstrip().startswith("UPDATE"):
            if self.lose_upgrade_race:
                self.row["free_token_limit"] = token_budget_service.FREE_TOKEN_GRANT
                return None
            self.row["free_token_limit"] += args[1]
        return dict(self.row)


def test_get_token_budget_upgrades_legacy_grant_and_preserves_admin_tokens():
    company_id = uuid4()
    conn = BudgetConnection(_budget_row(1_500_000, free_tokens_used=1_000_000))

    budget = asyncio.run(token_budget_service.get_token_budget(company_id, conn=conn))

    assert budget["free_token_limit"] == 3_500_000
    assert budget["free_tokens_remaining"] == 2_500_000
    update_query, update_args = conn.fetchrow_calls[1]
    assert "free_token_limit = free_token_limit + $2" in update_query
    assert update_args == (company_id, 2_000_000, 1_000_000, 3_000_000)


def test_get_token_budget_leaves_current_grant_unchanged():
    company_id = uuid4()
    conn = BudgetConnection(_budget_row(token_budget_service.FREE_TOKEN_GRANT))

    budget = asyncio.run(token_budget_service.get_token_budget(company_id, conn=conn))

    assert budget["free_token_limit"] == token_budget_service.FREE_TOKEN_GRANT
    assert len(conn.fetchrow_calls) == 1


def test_get_token_budget_reloads_after_concurrent_upgrade():
    company_id = uuid4()
    conn = BudgetConnection(_budget_row(1_000_000), lose_upgrade_race=True)

    budget = asyncio.run(token_budget_service.get_token_budget(company_id, conn=conn))

    assert budget["free_token_limit"] == token_budget_service.FREE_TOKEN_GRANT
    assert len(conn.fetchrow_calls) == 3
