"""Tests for Monte Carlo risk simulation service."""

import pytest
from app.matcha.services.monte_carlo_service import (
    run_monte_carlo,
    extract_cost_of_risk_items,
    _lognormal_params,
    _poisson,
    _compute_percentiles,
    MonteCarloResult,
)
import random
import math


# ─── Sample line items (matching real cost-of-risk output) ────────────────────

SAMPLE_LINE_ITEMS = [
    {
        "key": "hourly_wage_shortfall",
        "label": "Hourly Wage Shortfall",
        "low": 45000,
        "high": 127000,
        "affected_count": 5,
        "basis": "FLSA § 216(b), 2–3yr lookback + liquidated damages",
    },
    {
        "key": "exempt_misclassification",
        "label": "Exempt Misclassification",
        "low": 80000,
        "high": 240000,
        "affected_count": 3,
        "basis": "FLSA § 207, overtime liability",
    },
    {
        "key": "hipaa_breach_exposure",
        "label": "HIPAA Breach Exposure",
        "low": 14500,
        "high": 145200,
        "affected_count": 100,
        "basis": "HIPAA penalty tiers",
    },
    {
        "key": "pending_determination",
        "label": "Pending Determination Cases",
        "low": 12750,
        "high": 34000,
        "affected_count": 1,
        "basis": "EEOC median resolution × 17% merit probability",
    },
    {
        "key": "critical_incidents",
        "label": "Critical Incidents",
        "low": 16550,
        "high": 165514,
        "affected_count": 1,
        "basis": "OSHA willful/repeat violation penalty range",
    },
]


class TestLognormalParams:
    def test_basic_range(self):
        mu, sigma = _lognormal_params(1000, 10000)
        assert mu > 0
        assert sigma > 0
        # mu should be between ln(1000) and ln(10000)
        assert math.log(1000) < mu < math.log(10000)

    def test_degenerate_range(self):
        mu, sigma = _lognormal_params(5000, 5000)
        assert sigma == 0.1  # minimal spread

    def test_zero_values(self):
        mu, sigma = _lognormal_params(0, 100)
        assert mu == 0.0
        assert sigma == 0.0


class TestPoisson:
    def test_zero_lambda(self):
        rng = random.Random(42)
        assert _poisson(0, rng) == 0

    def test_small_lambda(self):
        rng = random.Random(42)
        values = [_poisson(2.0, rng) for _ in range(1000)]
        mean = sum(values) / len(values)
        # Mean should be close to lambda
        assert 1.5 < mean < 2.5

    def test_large_lambda_normal_approx(self):
        rng = random.Random(42)
        values = [_poisson(50.0, rng) for _ in range(1000)]
        mean = sum(values) / len(values)
        assert 45 < mean < 55


class TestComputePercentiles:
    def test_basic(self):
        values = list(range(100))
        pcts = _compute_percentiles(values)
        assert pcts["p50"] == pytest.approx(49.5, abs=1)
        assert pcts["p5"] < pcts["p50"] < pcts["p95"]

    def test_empty(self):
        pcts = _compute_percentiles([])
        assert all(v == 0.0 for v in pcts.values())

    def test_single_value(self):
        pcts = _compute_percentiles([100.0])
        assert pcts["p50"] == 100.0


class TestRunMonteCarlo:
    def test_basic_execution(self):
        result = run_monte_carlo(SAMPLE_LINE_ITEMS, iterations=1000, seed=42)
        assert isinstance(result, MonteCarloResult)
        assert result.iterations == 1000
        assert len(result.categories) == len(SAMPLE_LINE_ITEMS)

    def test_deterministic_categories_have_zero_pct_zero(self):
        """Deterministic categories (wage shortfall, etc.) should never have $0 loss."""
        result = run_monte_carlo(SAMPLE_LINE_ITEMS, iterations=1000, seed=42)
        wage = result.categories["hourly_wage_shortfall"]
        assert wage.frequency_type == "deterministic"
        assert wage.zero_loss_pct == 0.0

    def test_stochastic_categories_can_have_zero_loss(self):
        """HIPAA breach is stochastic — some iterations should have $0."""
        result = run_monte_carlo(SAMPLE_LINE_ITEMS, iterations=1000, seed=42)
        hipaa = result.categories["hipaa_breach_exposure"]
        assert hipaa.frequency_type == "stochastic"
        assert hipaa.zero_loss_pct > 0.0  # Some iterations with no breach

    def test_percentile_ordering(self):
        """P5 < P50 < P95 for categories with variance."""
        result = run_monte_carlo(SAMPLE_LINE_ITEMS, iterations=5000, seed=42)
        for key, cat in result.categories.items():
            if cat.expected_loss > 0:
                assert cat.percentiles["p5"] <= cat.percentiles["p50"]
                assert cat.percentiles["p50"] <= cat.percentiles["p95"]

    def test_aggregate_var_exceeds_expected(self):
        """VaR at 95% should be >= expected annual loss."""
        result = run_monte_carlo(SAMPLE_LINE_ITEMS, iterations=5000, seed=42)
        assert result.aggregate.var_95 >= result.aggregate.expected_annual_loss

    def test_aggregate_cvar_exceeds_var(self):
        """CVaR (expected shortfall) should be >= VaR."""
        result = run_monte_carlo(SAMPLE_LINE_ITEMS, iterations=5000, seed=42)
        assert result.aggregate.cvar_95 >= result.aggregate.var_95

    def test_reproducibility_with_seed(self):
        """Same seed should produce identical results."""
        r1 = run_monte_carlo(SAMPLE_LINE_ITEMS, iterations=1000, seed=123)
        r2 = run_monte_carlo(SAMPLE_LINE_ITEMS, iterations=1000, seed=123)
        assert r1.aggregate.expected_annual_loss == r2.aggregate.expected_annual_loss
        assert r1.aggregate.var_95 == r2.aggregate.var_95

    def test_empty_items(self):
        """Empty input should not crash."""
        result = run_monte_carlo([], iterations=100, seed=42)
        assert result.aggregate.expected_annual_loss == 0.0
        assert len(result.categories) == 0

    def test_to_dict_serialization(self):
        """Result should serialize to dict without errors."""
        result = run_monte_carlo(SAMPLE_LINE_ITEMS, iterations=100, seed=42)
        d = result.to_dict()
        assert "iterations" in d
        assert "categories" in d
        assert "aggregate" in d
        assert "computed_at" in d
        assert isinstance(d["aggregate"]["var_95"], float)


class TestExtractCostOfRiskItems:
    def test_extract_from_dimensions(self):
        dimensions = {
            "compliance": {
                "score": 45,
                "band": "moderate",
                "factors": [],
                "raw_data": {
                    "cost_of_risk": {
                        "line_items": [
                            {"key": "hourly_wage_shortfall", "low": 10000, "high": 30000, "affected_count": 2},
                        ],
                        "total_low": 10000,
                        "total_high": 30000,
                    }
                },
            },
            "incidents": {
                "score": 25,
                "band": "low",
                "factors": [],
                "raw_data": {
                    "cost_of_risk": {
                        "line_items": [
                            {"key": "critical_incidents", "low": 16550, "high": 165514, "affected_count": 1},
                        ],
                        "total_low": 16550,
                        "total_high": 165514,
                    }
                },
            },
            "workforce": {
                "score": 10,
                "band": "low",
                "factors": [],
                "raw_data": {
                    "total_employees": 50,
                },
            },
        }
        items = extract_cost_of_risk_items(dimensions)
        assert len(items) == 2
        keys = {item["key"] for item in items}
        assert "hourly_wage_shortfall" in keys
        assert "critical_incidents" in keys

    def test_empty_dimensions(self):
        items = extract_cost_of_risk_items({})
        assert items == []

    def test_no_cost_of_risk(self):
        dimensions = {
            "workforce": {
                "score": 10,
                "raw_data": {"total_employees": 50},
            }
        }
        items = extract_cost_of_risk_items(dimensions)
        assert items == []
