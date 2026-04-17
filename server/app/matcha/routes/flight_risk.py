"""Flight-Risk endpoints — companion to dashboard wage-gap (§3.3).

Surfaces the composite score from `flight_risk_service` to the operator
dashboard widget and the per-employee drawer. No mutations from this
router; snapshots are written by a Celery task or manual ops trigger
(see flight_risk_service.snapshot_company).
"""

import logging
from dataclasses import asdict
from typing import List, Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.models.auth import CurrentUser
from ..dependencies import get_client_company_id, require_admin_or_client
from ..services.flight_risk_service import (
    compute_company_summary,
    compute_for_company,
    get_employee_history,
    snapshot_company,
)


logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic response models
# ─────────────────────────────────────────────────────────────────────────────


class ManagerHotspot(BaseModel):
    manager_id: str
    manager_name: str
    flagged_count: int


class FlightRiskSummary(BaseModel):
    employees_evaluated: int
    critical_count: int
    high_count: int
    elevated_count: int
    low_count: int
    expected_loss_at_replacement: int
    top_driver: Optional[str] = None
    top_driver_count: int = 0
    early_tenure_count: int = 0
    manager_hotspots: List[ManagerHotspot] = []


class FlightRiskFactor(BaseModel):
    name: str
    contribution: int
    color: str
    narrative: str
    value: Optional[float] = None


class EmployeeFlightRisk(BaseModel):
    employee_id: str
    name: str
    score: int
    tier: str
    top_factor: str
    factors: List[FlightRiskFactor]
    expected_replacement_cost: int


class EmployeeFlightRiskList(BaseModel):
    employees: List[EmployeeFlightRisk]


class FlightRiskHistoryEntry(BaseModel):
    score: int
    tier: str
    top_factor: Optional[str] = None
    computed_at: str


class FlightRiskHistoryResponse(BaseModel):
    employee_id: str
    history: List[FlightRiskHistoryEntry]


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/summary", response_model=FlightRiskSummary)
async def get_summary(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Dashboard widget aggregate. Mirrors `WageGapSummary` shape."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return FlightRiskSummary(
            employees_evaluated=0,
            critical_count=0, high_count=0, elevated_count=0, low_count=0,
            expected_loss_at_replacement=0,
        )
    try:
        summary = await compute_company_summary(company_id)
    except asyncpg.UndefinedTableError:
        return FlightRiskSummary(
            employees_evaluated=0,
            critical_count=0, high_count=0, elevated_count=0, low_count=0,
            expected_loss_at_replacement=0,
        )
    return FlightRiskSummary(**asdict(summary))


@router.get("/employees", response_model=EmployeeFlightRiskList)
async def list_employee_scores(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Per-employee score list — drives the drill-down drawer."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return EmployeeFlightRiskList(employees=[])
    try:
        results = await compute_for_company(company_id)
    except asyncpg.UndefinedTableError:
        return EmployeeFlightRiskList(employees=[])
    return EmployeeFlightRiskList(
        employees=[
            EmployeeFlightRisk(
                employee_id=r.employee_id,
                name=r.name,
                score=r.score,
                tier=r.tier,
                top_factor=r.top_factor,
                factors=[FlightRiskFactor(**asdict(f)) for f in r.factors],
                expected_replacement_cost=r.expected_replacement_cost,
            )
            for r in results
        ]
    )


@router.get("/employees/{employee_id}", response_model=EmployeeFlightRisk)
async def get_employee_score(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Per-employee detail — for the profile drawer badge expansion."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    results = await compute_for_company(company_id)
    target = next((r for r in results if r.employee_id == str(employee_id)), None)
    if not target:
        raise HTTPException(status_code=404, detail="Employee not found in active roster")
    return EmployeeFlightRisk(
        employee_id=target.employee_id,
        name=target.name,
        score=target.score,
        tier=target.tier,
        top_factor=target.top_factor,
        factors=[FlightRiskFactor(**asdict(f)) for f in target.factors],
        expected_replacement_cost=target.expected_replacement_cost,
    )


@router.get("/employees/{employee_id}/history", response_model=FlightRiskHistoryResponse)
async def get_employee_history_endpoint(
    employee_id: UUID,
    limit: int = 30,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Trend view from snapshot table."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return FlightRiskHistoryResponse(employee_id=str(employee_id), history=[])
    try:
        history = await get_employee_history(company_id, employee_id, limit=limit)
    except asyncpg.UndefinedTableError:
        history = []
    return FlightRiskHistoryResponse(
        employee_id=str(employee_id),
        history=[FlightRiskHistoryEntry(**h) for h in history],
    )


@router.post("/snapshot", status_code=201)
async def trigger_snapshot(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Compute + persist current scores for the whole roster.

    Manual trigger for now. Wire to a daily Celery beat task later.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {"snapshotted": 0}
    try:
        count = await snapshot_company(company_id)
    except asyncpg.UndefinedTableError:
        count = 0
    return {"snapshotted": count}
