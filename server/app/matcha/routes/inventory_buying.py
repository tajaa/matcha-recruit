"""Level-1 inventory buying guidance: advisory only, no vendor transmission."""

import csv
import io
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client, require_all_features
from app.matcha.models.inventory import BuyingPlanOut, BuyingRunCreate, SupplierCreate, SupplierItemUpsert
from app.matcha.services.inventory import buying_store, orders as orders_service


router = APIRouter()
_gate = Depends(require_all_features("inventory", "sales_intake", "inventory_forecasting"))


@router.get("/suppliers")
async def suppliers(company_id: UUID = Depends(get_client_company_id), _=Depends(require_admin_or_client), _g=_gate):
    async with get_connection() as conn:
        return {"suppliers": await buying_store.list_suppliers(conn, company_id=company_id)}


@router.post("/suppliers", status_code=201)
async def create_supplier(body: SupplierCreate, company_id: UUID = Depends(get_client_company_id),
                          user=Depends(require_admin_or_client), _g=_gate):
    async with get_connection() as conn:
        return await buying_store.upsert_supplier(conn, company_id=company_id, user_id=user.id, values=body.model_dump())


@router.put("/supplier-items/{item_id}")
async def put_supplier_item(item_id: UUID, body: SupplierItemUpsert,
                            company_id: UUID = Depends(get_client_company_id),
                            user=Depends(require_admin_or_client), _g=_gate):
    async with get_connection() as conn:
        try:
            return await buying_store.upsert_supplier_item(
                conn, company_id=company_id, item_id=item_id, user_id=user.id,
                values=body.model_dump(exclude_unset=True),
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc


@router.post("/runs", response_model=BuyingPlanOut, status_code=201)
async def create_buying_run(body: BuyingRunCreate, company_id: UUID = Depends(get_client_company_id),
                            user=Depends(require_admin_or_client), _g=_gate):
    async with get_connection() as conn:
        plan = await buying_store.create_run(
            conn, company_id=company_id, user_id=user.id, forecast_run_id=body.forecast_run_id,
            location_id=body.location_id, today=date.today(),
        )
    if plan is None:
        raise HTTPException(404, "Forecast run or location not found.")
    return plan


@router.get("/preview", response_model=BuyingPlanOut)
async def preview_buying_plan(forecast_run_id: UUID = Query(...), location_id: Optional[UUID] = Query(None),
                              company_id: UUID = Depends(get_client_company_id),
                              _=Depends(require_admin_or_client), _g=_gate):
    async with get_connection() as conn:
        plan = await buying_store.build_plan(conn, company_id=company_id, forecast_run_id=forecast_run_id,
                                             location_id=location_id, today=date.today())
    if plan is None:
        raise HTTPException(404, "Forecast run or location not found.")
    return plan


@router.post("/lines/{line_id}/stage")
async def stage_recommendation(line_id: UUID, company_id: UUID = Depends(get_client_company_id),
                               user=Depends(require_admin_or_client), _g=_gate):
    """Revalidate the snapshot, then stage an internal queue item only."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT bl.*,br.forecast_run_id,br.location_id AS run_location_id,br.input_fingerprint,
                      s.name AS supplier_name,si.unit_price AS configured_unit_price,si.freight_flat AS configured_freight
               FROM inventory_buying_lines bl JOIN inventory_buying_runs br ON br.id=bl.run_id
               LEFT JOIN inventory_suppliers s ON s.id=bl.supplier_id
               LEFT JOIN inventory_supplier_items si ON si.id=bl.supplier_item_id
               WHERE bl.id=$1 AND bl.company_id=$2""", line_id, company_id,
        )
        if row is None or row["action"] not in ("buy", "expedite"):
            raise HTTPException(404, "Actionable buying recommendation not found.")
        current = await buying_store.build_plan(conn, company_id=company_id, forecast_run_id=row["forecast_run_id"],
                                                location_id=row["run_location_id"], today=date.today())
        if current is None or current["input_fingerprint"] != row["input_fingerprint"]:
            raise HTTPException(409, detail={"code": "stale_recommendation", "message": "Inventory, transfers, or supplier terms changed. Refresh the buying plan."})
        suggestion = {"suggested_quantity": float(row["purchase_quantity"]), "source": "buying_advisory",
                      "buying_line_id": str(line_id), "supplier_name": row["supplier_name"]}
        order = await orders_service.stage_order(conn, company_id=company_id, item_id=row["item_id"], channel_id=None,
                                                 source_message_id=None, created_by=user.id, suggestion=suggestion)
        await conn.execute(
            """UPDATE inventory_orders SET supplier_id=$2,supplier_item_id=$3,expected_delivery=$4,
                 unit_price_snapshot=$5,freight_snapshot=$6,buying_line_id=$7,updated_at=NOW() WHERE id=$1""",
            order["id"], row["supplier_id"], row["supplier_item_id"], row["expected_arrival"],
            row["configured_unit_price"], row["configured_freight"], line_id,
        )
    return {"order_id": order["id"], "status": "queued"}


@router.get("/export.csv")
async def export_buying_plan(forecast_run_id: UUID = Query(...), location_id: Optional[UUID] = Query(None),
                             company_id: UUID = Depends(get_client_company_id),
                             _=Depends(require_admin_or_client), _g=_gate):
    async with get_connection() as conn:
        plan = await buying_store.build_plan(conn, company_id=company_id, forecast_run_id=forecast_run_id,
                                             location_id=location_id, today=date.today())
    if plan is None:
        raise HTTPException(404, "Forecast run or location not found.")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["location", "item", "action", "needed_quantity", "transfer_quantity", "purchase_quantity",
                     "supplier", "order_by", "expected_arrival", "landed_cost", "price_confirmation_required", "rationale"])
    for line in plan["lines"]:
        writer.writerow([line.get("location_name"), line["item_name"], line["action"], line.get("needed_quantity"),
                         line.get("transfer_quantity"), line.get("purchase_quantity"), line.get("supplier_name"),
                         line.get("order_by_date"), line.get("expected_arrival"), line.get("landed_cost"),
                         line["price_confirmation_required"], line["rationale"]])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="inventory-buying-plan.csv"'})
