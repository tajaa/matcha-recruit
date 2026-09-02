"""Forecast setup and deterministic replenishment recommendations."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.core.services.redis_cache import check_rate_limit
from app.matcha.dependencies import (
    get_client_company_id,
    require_admin_or_client,
    require_all_features,
)
from app.matcha.models.inventory import (
    ForecastPreviewRequest,
    ForecastAIDraftRequest,
    ForecastRuleUpsert,
    ForecastRunCreate,
    ForecastParApply,
    ForecastParAIDraft,
    ForecastNetworkPlanOut,
    ForecastSettingsUpsert,
)
from app.matcha.services.inventory import forecast_store, insight, network
from app.matcha.services.inventory import forecast_ai
from app.matcha.services.inventory.waste import par_store
from app.matcha.services.inventory.waste import par_ai


router = APIRouter()
_forecast_gate = Depends(require_all_features("inventory", "sales_intake", "inventory_forecasting"))
_par_gate = Depends(require_all_features("inventory", "sales_intake", "inventory_forecasting", "inventory_waste"))


def _overrides(body) -> list[dict]:
    return [override.model_dump() for override in body.overrides]


async def _forecast_start(conn, company_id: UUID, location_id: Optional[UUID], requested: Optional[date]) -> date:
    if requested is not None:
        return requested
    settings = await forecast_store.get_settings(conn, company_id, location_id)
    try:
        timezone = ZoneInfo(settings["timezone"])
    except Exception:
        timezone = ZoneInfo("UTC")
    return datetime.now(timezone).date()


@router.get("/settings")
async def get_forecast_settings(
    location_id: Optional[UUID] = Query(None),
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    async with get_connection() as conn:
        return await forecast_store.get_settings(conn, company_id, location_id)


@router.put("/settings")
async def put_forecast_settings(
    body: ForecastSettingsUpsert,
    company_id: UUID = Depends(get_client_company_id),
    user=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    async with get_connection() as conn:
        try:
            return await forecast_store.upsert_settings(
                conn,
                company_id=company_id,
                user_id=user.id,
                values=body.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(404, "Location not found.") from exc


@router.get("/replenishment-rules")
async def get_replenishment_rules(
    location_id: Optional[UUID] = Query(None),
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    async with get_connection() as conn:
        return {"rules": await forecast_store.list_rules(conn, company_id=company_id, location_id=location_id)}


@router.put("/replenishment-rules/{item_id}")
async def put_replenishment_rule(
    item_id: UUID,
    body: ForecastRuleUpsert,
    company_id: UUID = Depends(get_client_company_id),
    user=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    async with get_connection() as conn:
        try:
            values = body.model_dump()
            values["updated_by"] = user.id
            return await forecast_store.upsert_rule(
                conn, company_id=company_id, item_id=item_id, values=values,
            )
        except ValueError as exc:
            raise HTTPException(404, "Inventory item not found.") from exc


@router.post("/preview")
async def preview_forecast(
    body: ForecastPreviewRequest,
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    async with get_connection() as conn:
        start = await _forecast_start(conn, company_id, body.location_id, body.forecast_start)
        return await forecast_store.build_preview(
            conn,
            company_id=company_id,
            location_id=body.location_id,
            forecast_start=start,
            overrides=_overrides(body),
        )


@router.post("/runs")
async def create_forecast_run(
    body: ForecastRunCreate,
    company_id: UUID = Depends(get_client_company_id),
    user=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    async with get_connection() as conn:
        start = await _forecast_start(conn, company_id, body.location_id, body.forecast_start)
        return await forecast_store.create_run(
            conn,
            company_id=company_id,
            user_id=user.id,
            location_id=body.location_id,
            forecast_start=start,
            overrides=_overrides(body),
        )


@router.post("/ai-draft")
async def draft_forecast_adjustments(
    body: ForecastAIDraftRequest,
    company_id: UUID = Depends(get_client_company_id),
    user=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    await check_rate_limit(f"user:{user.id}", "inventory_forecast_ai_burst", 5, 60)
    await check_rate_limit(f"user:{user.id}", "inventory_forecast_ai", 40, 3600)
    await check_rate_limit(str(company_id), "inventory_forecast_ai_company", 120, 3600)
    async with get_connection() as conn:
        start = await _forecast_start(conn, company_id, body.location_id, body.horizon_start)
        preview = await forecast_store.build_preview(
            conn,
            company_id=company_id,
            location_id=body.location_id,
            forecast_start=start,
            overrides=[],
        )
    summary = {
        "items": [
            {
                "item_id": str(line["item_id"]),
                "name": line["name"],
                "history_nonzero_days": line["history_nonzero_days"],
                "average_daily_demand": str(line["average_daily_demand"]),
                "status": line["status"],
            }
            for line in preview["lines"]
        ]
    }
    return await forecast_ai.propose_forecast_adjustments(
        company_id=company_id,
        location_id=body.location_id,
        horizon_start=start,
        horizon_days=preview["settings"]["horizon_days"],
        manager_context=body.manager_context,
        historical_summary=summary,
    )


@router.get("/runs/latest")
async def get_latest_forecast_run(
    location_id: Optional[UUID] = Query(None),
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    async with get_connection() as conn:
        return await forecast_store.get_latest_run(
            conn, company_id=company_id, location_id=location_id,
        )


@router.get("/network", response_model=ForecastNetworkPlanOut)
async def get_inventory_network_plan(
    run_id: UUID = Query(...),
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    """Read-only transfer opportunities across the tenant's active stores."""
    async with get_connection() as conn:
        plan = await network.build_network_preview(
            conn,
            company_id=company_id,
            run_id=run_id,
        )
    if plan is None:
        raise HTTPException(404, "Forecast run not found.")
    return plan


@router.post("/runs/{run_id}/apply-par")
async def apply_forecast_par(
    run_id: UUID, body: ForecastParApply,
    company_id: UUID = Depends(get_client_company_id), user=Depends(require_admin_or_client),
    _gate=_par_gate,
):
    # Explicit manager application can override a pinned/drifted par only for
    # named items. A body without item ids keeps the normal deterministic gate.
    async with get_connection() as conn:
        return await par_store.apply_par_recommendations(
            conn, company_id=company_id, run_id=run_id, user_id=user.id,
            mode=body.mode, item_ids=body.item_ids,
        )


@router.post("/runs/{run_id}/par-preview")
async def preview_forecast_par(
    run_id: UUID, body: ForecastParApply,
    company_id: UUID = Depends(get_client_company_id), _=Depends(require_admin_or_client),
    _gate=_par_gate,
):
    async with get_connection() as conn:
        return await par_store.plan_par_recommendations(
            conn, company_id=company_id, run_id=run_id, mode=body.mode, item_ids=body.item_ids,
        )


@router.post("/insight")
async def forecast_insight(run_id: UUID, company_id: UUID = Depends(get_client_company_id), user=Depends(require_admin_or_client), _gate=_forecast_gate):
    await check_rate_limit(f"user:{user.id}", "inventory_forecast_insight", 30, 3600)
    async with get_connection() as conn:
        run = await forecast_store.get_run(conn, company_id=company_id, run_id=run_id)
    if run is None: raise HTTPException(404, "Forecast run not found.")
    plan = run["plan"]
    overdue = plan["buckets"]["overdue"]
    diagnosis = "restock_overdue" if overdue else "restock_upcoming" if plan["lines"] else "on_track"
    tokens = {"items": str(len(plan["lines"])), "order_value": f"${plan['total_order_value']:,.2f}" if plan["total_order_value"] is not None else "uncosted items", "overdue": str(overdue)}
    return await insight.interpret(surface="forecast", diagnosis=diagnosis, tokens=tokens)


@router.post('/par-ai')
async def draft_par_exceptions(body: ForecastParAIDraft, company_id: UUID = Depends(get_client_company_id), user=Depends(require_admin_or_client), _gate=_par_gate):
    await check_rate_limit(f'user:{user.id}', 'inventory_par_ai_burst', 5, 60)
    await check_rate_limit(f'user:{user.id}', 'inventory_par_ai', 40, 3600)
    await check_rate_limit(str(company_id), 'inventory_par_ai_company', 120, 3600)
    async with get_connection() as conn:
        rows = await conn.fetch("""SELECT fl.item_id, i.name, fl.status, fl.recommended_par,
            COALESCE((SELECT COUNT(*) FROM inventory_movements m WHERE m.item_id=fl.item_id AND m.kind='stockout' AND m.created_at > NOW()-INTERVAL '30 days'),0) AS stockouts,
            COALESCE((SELECT SUM(ABS(m.quantity_delta)) FROM inventory_movements m WHERE m.item_id=fl.item_id AND m.kind='waste' AND m.created_at > NOW()-INTERVAL '30 days'),0) AS waste_units
            FROM inventory_forecast_lines fl JOIN inventory_forecast_runs fr ON fr.id=fl.run_id JOIN inventory_items i ON i.id=fl.item_id
            WHERE fl.run_id=$1 AND fr.company_id=$2 AND fl.status <> 'ready'""", body.run_id, company_id)
    return await par_ai.propose_par_exceptions(suppressed_items=[dict(row) for row in rows])


@router.get("/runs/{run_id}")
async def get_forecast_run(
    run_id: UUID,
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_forecast_gate,
):
    async with get_connection() as conn:
        run = await forecast_store.get_run(conn, company_id=company_id, run_id=run_id)
    if run is None:
        raise HTTPException(404, "Forecast run not found.")
    return run
