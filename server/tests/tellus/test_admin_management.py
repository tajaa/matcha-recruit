"""Pure-function tests for the Tell-Us internal admin management system
(points adjustment math, audit serialization, admin filter builders, admin
model validation). No DB, no HTTP — see TELLUS_ADMIN_MGMT_PLAN.md Part 6/2c/3f.
"""
from uuid import uuid4

import pytest

from app.tellus.models.admin import (
    ACCOUNT_STATUSES,
    TellusAdminEarningRuleUpdate,
    TellusAdminPlanAction,
    TellusAdminPointsAdjust,
    TellusPasswordResetConfirm,
)
from app.tellus.routes.admin._shared import account_filter_sql, report_filter_sql
from app.tellus.services.admin_audit import serialize_detail
from app.tellus.services.points_service import (
    AdjustError,
    adjust_points,
    compute_adjustment,
    level_for_points,
)


class _NullTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeConn:
    """Minimal asyncpg stand-in for adjust_points: dispatches on SQL
    substring, records every call so a test can assert what did (and didn't)
    run. `dup` simulates a ledger row already existing for the idempotency
    key — the pre-check path adjust_points must take instead of relying on a
    caught UniqueViolationError under a nested SAVEPOINT."""

    def __init__(self, *, dup: bool, balance: int, lifetime: int, level: int, insert_id="ledger-1"):
        self.calls: list[tuple] = []
        self._dup = dup
        self._balance = balance
        self._lifetime = lifetime
        self._level = level
        self._insert_id = insert_id

    def transaction(self):
        return _NullTxn()

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "OK"

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "SELECT 1 FROM tellus_points_ledger" in query:
            return 1 if self._dup else None
        if "INSERT INTO tellus_points_ledger" in query:
            return None if self._dup else self._insert_id
        raise AssertionError(f"unexpected fetchval: {query}")

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "tellus_points_balances" in query:
            return {"points_balance": self._balance, "lifetime_points": self._lifetime, "level": self._level}
        raise AssertionError(f"unexpected fetchrow: {query}")


class TestComputeAdjustment:
    def test_credit_raises_balance_and_lifetime(self):
        plan = compute_adjustment(0, 99, 1)
        assert plan == {
            "applied_delta": 1, "new_balance": 1, "new_lifetime": 100, "new_level": 2,
        }

    def test_debit_within_balance_can_drop_level(self):
        # lifetime=300 -> level 3; clawback 201 -> lifetime 99 -> level 1.
        assert level_for_points(300) == 3
        plan = compute_adjustment(300, 300, -201)
        assert plan["applied_delta"] == -201
        assert plan["new_balance"] == 99
        assert plan["new_lifetime"] == 99
        assert plan["new_level"] == 1

    def test_lifetime_floors_at_zero(self):
        plan = compute_adjustment(50, 10, -20)
        assert plan["new_balance"] == 30
        assert plan["new_lifetime"] == 0

    def test_overdraw_without_clamp_raises(self):
        with pytest.raises(AdjustError) as exc:
            compute_adjustment(10, 10, -20)
        assert "10" in str(exc.value)
        assert "20" in str(exc.value)

    def test_overdraw_with_clamp_zeroes_out(self):
        plan = compute_adjustment(10, 10, -20, clamp=True)
        assert plan["applied_delta"] == -10
        assert plan["new_balance"] == 0
        assert plan["new_lifetime"] == 0

    def test_clamp_at_zero_balance_raises(self):
        with pytest.raises(AdjustError):
            compute_adjustment(0, 0, -5, clamp=True)

    def test_zero_delta_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_adjustment(10, 10, 0)

    def test_invariant_sweep(self):
        for balance in (0, 5, 100, 999):
            for lifetime in (0, 5, 100, 999, 5000):
                for delta in (-500, -50, -1, 1, 50, 500):
                    if delta < 0 and balance + delta < 0:
                        continue  # would raise without clamp — not this sweep's concern
                    plan = compute_adjustment(balance, lifetime, delta)
                    assert plan["new_balance"] == balance + plan["applied_delta"] >= 0
                    assert plan["new_level"] == level_for_points(plan["new_lifetime"])


class TestAdjustPointsIdempotency:
    """adjust_points' insert is routinely called inside an already-open
    transaction (routes/admin/accounts.py opens one before calling it), which
    makes it a SAVEPOINT — a caught UniqueViolationError there leaves the
    savepoint aborted and the request 500s. The fix is a pre-check + ON
    CONFLICT DO NOTHING, verified here without touching a real DB."""

    @pytest.mark.asyncio
    async def test_first_call_inserts_and_credits(self):
        conn = _FakeConn(dup=False, balance=0, lifetime=99, level=1)
        result = await adjust_points(conn, uuid4(), 1, description="test adj", reference_id="adm:key1")
        assert result == {"adjusted": True, "applied_delta": 1, "balance": 1, "lifetime": 100, "level": 2}
        insert_calls = [c for c in conn.calls if c[0] == "fetchval" and "INSERT INTO tellus_points_ledger" in c[1]]
        assert len(insert_calls) == 1

    @pytest.mark.asyncio
    async def test_replay_short_circuits_before_insert(self):
        conn = _FakeConn(dup=True, balance=1, lifetime=100, level=2)
        result = await adjust_points(conn, uuid4(), 1, description="test adj", reference_id="adm:key1")
        assert result == {"adjusted": False, "applied_delta": 0, "balance": 1, "lifetime": 100, "level": 2}
        insert_calls = [c for c in conn.calls if c[0] == "fetchval" and "INSERT INTO tellus_points_ledger" in c[1]]
        assert len(insert_calls) == 0
        # The pre-check dup lookup ran, but the FOR UPDATE balance lock never did.
        lock_calls = [c for c in conn.calls if c[0] == "fetchrow" and "FOR UPDATE" in c[1]]
        assert len(lock_calls) == 0

    @pytest.mark.asyncio
    async def test_no_reference_id_never_hits_the_precheck(self):
        conn = _FakeConn(dup=False, balance=0, lifetime=0, level=1)
        result = await adjust_points(conn, uuid4(), 5, description="test adj")
        assert result["adjusted"] is True
        dup_calls = [c for c in conn.calls if c[0] == "fetchval" and "SELECT 1 FROM tellus_points_ledger" in c[1]]
        assert len(dup_calls) == 0


class TestSerializeDetail:
    def test_none_passes_through(self):
        assert serialize_detail(None) is None

    def test_uuid_and_datetime_round_trip_as_strings(self):
        import json
        from datetime import datetime
        from uuid import uuid4

        u = uuid4()
        d = datetime(2026, 8, 6, 12, 0, 0)
        raw = serialize_detail({"id": u, "when": d, "n": 3})
        decoded = json.loads(raw)
        assert decoded == {"id": str(u), "when": str(d), "n": 3}


class TestReportFilterSql:
    def test_published_fragment(self):
        where, params = report_filter_sql(review_state="published")
        assert "publish_at <= NOW()" in where
        assert params == []

    def test_held_fragment(self):
        where, _ = report_filter_sql(review_state="held")
        assert "IS NULL OR r.publish_at > NOW()" in where

    def test_withdrawn_fragment(self):
        where, _ = report_filter_sql(review_state="withdrawn")
        assert "r.review_state = 'withdrawn'" in where

    def test_placeholders_sequential_from_start_idx(self):
        where, params = report_filter_sql(moderation_status="visible", brand_id="b1", start_idx=3)
        assert "$3" in where and "$4" in where
        assert params == ["visible", "b1"]

    def test_q_escapes_like_wildcards_in_param(self):
        _, params = report_filter_sql(q="50%_off")
        assert params[0] == "%50\\%\\_off%"

    def test_no_filters_returns_empty(self):
        assert report_filter_sql() == ("", [])


class TestAccountFilterSql:
    def test_no_filters_returns_empty(self):
        assert account_filter_sql() == ("", [])

    def test_verified_true_and_false_differ(self):
        where_true, _ = account_filter_sql(verified=True)
        where_false, _ = account_filter_sql(verified=False)
        assert "IS NOT NULL" in where_true
        assert "IS NULL" in where_false


class TestAdminModels:
    def test_points_adjust_rejects_zero_delta(self):
        with pytest.raises(Exception):
            TellusAdminPointsAdjust(delta=0, description="test adj")

    def test_points_adjust_rejects_out_of_range(self):
        with pytest.raises(Exception):
            TellusAdminPointsAdjust(delta=100_001, description="test adj")

    def test_points_adjust_rejects_short_description(self):
        with pytest.raises(Exception):
            TellusAdminPointsAdjust(delta=10, description="ab")

    def test_points_adjust_accepts_valid_clawback(self):
        m = TellusAdminPointsAdjust(delta=-50, description="fraud clawback", clamp=True)
        assert m.delta == -50 and m.clamp is True

    def test_plan_action_rejects_unknown_literal(self):
        with pytest.raises(Exception):
            TellusAdminPlanAction(action="pending")

    def test_password_reset_confirm_rejects_short_password(self):
        with pytest.raises(Exception):
            TellusPasswordResetConfirm(token="a" * 20, new_password="short12")

    def test_password_reset_confirm_rejects_short_token(self):
        with pytest.raises(Exception):
            TellusPasswordResetConfirm(token="short", new_password="longenoughpw")

    def test_earning_rule_update_distinguishes_absent_vs_null(self):
        absent = TellusAdminEarningRuleUpdate(points=10)
        explicit_null = TellusAdminEarningRuleUpdate(points=10, daily_cap=None)
        assert "daily_cap" not in absent.model_dump(exclude_unset=True)
        assert "daily_cap" in explicit_null.model_dump(exclude_unset=True)
        assert explicit_null.model_dump(exclude_unset=True)["daily_cap"] is None

    def test_account_statuses_tripwire(self):
        assert ACCOUNT_STATUSES == ("active", "suspended")


class TestAdminGateSweep:
    def test_every_admin_route_is_gated(self):
        from app.tellus.dependencies import require_tellus_admin
        from app.tellus.routes.admin import router

        assert len(router.routes) > 0
        for route in router.routes:
            deps = [d.call for d in route.dependant.dependencies]
            assert require_tellus_admin in deps, f"{route.path} is not admin-gated"
