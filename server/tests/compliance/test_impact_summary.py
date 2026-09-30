from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.services import impact_summary


class _EmployeeCountConn:
    def __init__(self, employee_count: int):
        self.employee_count = employee_count
        self.query = None
        self.args = None

    async def fetchval(self, query, *args):
        self.query = query
        self.args = args
        return self.employee_count


@pytest.mark.asyncio
async def test_generate_impact_summary_uses_employee_schema_contract(monkeypatch):
    location_id = uuid4()
    conn = _EmployeeCountConn(employee_count=7)
    captured = {}

    def _capture_prompt(change_info, location, company_context, employee_count):
        captured["employee_count"] = employee_count
        return "prompt"

    monkeypatch.setattr(impact_summary, "_build_prompt", _capture_prompt)
    monkeypatch.setattr(impact_summary.os, "getenv", lambda _name: None)
    monkeypatch.setattr(
        impact_summary,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key=None),
    )

    await impact_summary.generate_impact_summary(
        {"req": {}},
        {"id": location_id, "name": "Downtown"},
        {"industry": "hospitality"},
        conn,
    )

    normalized_query = " ".join(conn.query.split())
    assert "org_id = (SELECT company_id FROM business_locations WHERE id = $1)" in normalized_query
    assert "termination_date IS NULL" in normalized_query
    assert "employees.company_id" not in normalized_query
    assert "status = 'active'" not in normalized_query
    assert conn.args == (location_id,)
    assert captured["employee_count"] == 7
