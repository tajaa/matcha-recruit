"""Shared builders for the schedule projection suites (no real DB)."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.matcha.services.scheduling import schedule_cost_projection as projection
from app.matcha.services.scheduling.schedule_review import compact_review


def full_week_review():
    crew = [str(uuid4()) for _ in range(28)]
    return {
        "proposal_id": str(uuid4()), "kind": "week_draft", "compliance_status": "verified",
        "assignments": [
            {"shift_id": f"autopilot:{i}", "employee_id": crew[i],
             "employee_name": f"Crew {i}", "role": "Barista", "verdict": "ok",
             "starts_at": "2026-10-11T07:00:00Z", "ends_at": "2026-10-11T13:30:00Z"}
            for i in range(28)
        ],
        "unfilled": [], "rejected": [], "advisories": [], "findings": [],
        "employees": [
            {"employee_id": crew[i], "name": f"Crew {i}", "warnings": ["Sixth day"] if i == 0 else [],
             "before": {"minutes": 0, "shifts": 0, "days": 0},
             "after": {"minutes": 390, "shifts": 1, "days": 1}}
            for i in range(2)
        ],
        "jurisdiction": {},
        "cost": {
            "before": 0, "after": 900, "delta": 900, "ot_premium_before": 0, "ot_premium_after": 40,
            "by_employee": {crew[0]: {"before": 0, "after": 900}},
            "unpriced_employee_ids": [crew[1]], "unpriced_employee_count": 1,
        },
    }


def compact_week_state(review):
    return {"huume_action": {
        "type": "schedule_week_draft", "status": "proposed", "origin": "manual",
        "confirm_id": "same-confirmation", "generation_run_id": str(uuid4()),
        "review": compact_review(review),
        "demand_model": {"forecast_sales_week": 14000, "days": [], "labor": {"labor_pct": 20}},
    }}


def connection(frozen_review):
    """A connection whose scoped read returns the frozen review JSON."""
    conn = AsyncMock()
    conn.transaction = MagicMock(side_effect=lambda: AsyncMock())
    conn.fetchval.return_value = frozen_review
    return conn


def patch_preview_connection(monkeypatch, conn):
    @asynccontextmanager
    async def get_connection():
        yield conn

    monkeypatch.setattr(projection, "get_connection", get_connection)
    return conn
