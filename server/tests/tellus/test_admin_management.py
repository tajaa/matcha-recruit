"""Pure-function tests for the Tell-Us internal admin management system
(points adjustment math, audit serialization, admin filter builders, admin
model validation). No DB, no HTTP — see TELLUS_ADMIN_MGMT_PLAN.md Part 6/2c/3f.
"""
import pytest

from app.tellus.services.admin_audit import serialize_detail
from app.tellus.services.points_service import (
    AdjustError,
    compute_adjustment,
    level_for_points,
)


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
