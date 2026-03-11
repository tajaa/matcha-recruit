from datetime import datetime, timezone
from pathlib import Path
import sys
import types
from uuid import uuid4

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

google_module = types.ModuleType("google")
google_module.genai = types.SimpleNamespace()
sys.modules.setdefault("google", google_module)

import app.matcha.services.risk_assessment_service as risk_assessment_service_module
from app.matcha.services.risk_assessment_service import (
    compute_compliance_dimension,
    compute_er_dimension,
)


class _ComplianceConn:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, query, *args):
        if "FROM compliance_alerts" in query:
            return self.row
        raise AssertionError(f"Unexpected fetchrow query: {query}")


class _ERConn:
    def __init__(self, *, status_rows, analysis_rows=None, case_rows=None):
        self.status_rows = status_rows
        self.analysis_rows = analysis_rows or []
        self.case_rows = case_rows or []

    async def fetch(self, query, *args):
        if "FROM er_cases" in query and "GROUP BY status" in query:
            return self.status_rows
        if "FROM er_case_analysis" in query:
            return self.analysis_rows
        if "SELECT id, title, status, category, created_at" in query:
            return self.case_rows
        raise AssertionError(f"Unexpected fetch query: {query}")


@pytest.mark.asyncio
async def test_compliance_dimension_scores_minimum_wage_violations(monkeypatch: pytest.MonkeyPatch):
    async def _fake_collect_metrics(company_id, conn):
        return {
            "minimum_wage_violation_employee_count": 8,
            "hourly_minimum_wage_violation_count": 5,
            "salary_minimum_wage_violation_count": 3,
            "locations_with_minimum_wage_violations": 5,
            "top_minimum_wage_violation_locations": [],
            "employee_violations": [],
        }

    monkeypatch.setattr(
        risk_assessment_service_module,
        "_collect_minimum_wage_violation_metrics",
        _fake_collect_metrics,
    )

    result = await compute_compliance_dimension(
        uuid4(),
        _ComplianceConn(
            {
                "critical_unread": 0,
                "warning_unread": 0,
                "last_check": datetime.now(timezone.utc),
            }
        ),
    )

    assert result.score == 100
    assert result.band == "critical"
    assert any("below minimum wage" in factor and "(+80)" in factor for factor in result.factors)
    assert any("location" in factor and "(+20)" in factor for factor in result.factors)


@pytest.mark.asyncio
async def test_er_dimension_keeps_pending_cases_below_auto_100_and_counts_open_cases():
    now = datetime.now(timezone.utc)
    result = await compute_er_dimension(
        uuid4(),
        _ERConn(
            status_rows=[
                {"status": "pending_determination", "cnt": 4},
                {"status": "in_review", "cnt": 1},
                {"status": "open", "cnt": 8},
            ],
            case_rows=[
                {
                    "id": uuid4(),
                    "title": "Case A",
                    "status": "pending_determination",
                    "category": "discipline",
                    "created_at": now,
                }
            ],
        ),
    )

    assert result.score == 95
    assert result.band == "critical"
    assert any("pending determination (+60)" in factor for factor in result.factors)
    assert any("in review (+10)" in factor for factor in result.factors)
    assert any("open case" in factor and "(+25)" in factor for factor in result.factors)
