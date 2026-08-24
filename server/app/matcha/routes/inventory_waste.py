"""Waste, lots, and predictive-par controls — all company scoped."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client, require_feature
from app.matcha.services.inventory import movements
from app.matcha.services.inventory.waste import lots, reasons, rollup
from app.matcha.services.inventory.waste import par_store
from app.matcha.services.inventory.waste import agent as waste_agent

router = APIRouter()

class WasteLine(BaseModel):
    item_id: UUID
    quantity: Decimal = Field(gt=0)
    reason: str = "unknown"
    note: Optional[str] = Field(default=None, max_length=200)

class ParEnroll(BaseModel):
    item_ids: list[UUID] = Field(min_length=1, max_length=200)
    enrolled: bool

class WasteAsk(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    start: Optional[date] = None
    end: Optional[date] = None
    location_id: Optional[UUID] = None

@router.post("")
async def record_waste(body: WasteLine, company_id: UUID = Depends(get_client_company_id), user=Depends(require_admin_or_client)):
    reason = body.reason if body.reason in reasons.WASTE_REASONS else "unknown"
    async with get_connection() as conn:
        owned = await conn.fetchval("SELECT 1 FROM inventory_items WHERE id=$1 AND company_id=$2", body.item_id, company_id)
        if not owned: raise HTTPException(404, "Inventory item not found.")
        rows = await movements.record_movements(conn, company_id=company_id, channel_id=None, source_message_id=None, recorded_by=user.id, kind="waste", narrative="Waste recorded", note=body.note, lines=[{"item_id": body.item_id, "quantity": body.quantity, "estimated": False, "waste_reason": reason}])
    return rows[0] if rows else {"recorded": False}

@router.get("/rollup")
async def waste_rollup(start: date, end: date, location_id: Optional[UUID] = None, group_by: Literal['reason','category','item'] = 'reason', company_id: UUID = Depends(get_client_company_id), _=Depends(require_admin_or_client)):
    if end < start: raise HTTPException(400, "end must be on or after start")
    async with get_connection() as conn:
        return await rollup.waste_rollup(conn, company_id=company_id, location_id=location_id, start=start, end=end, group_by=group_by)

@router.get("/lots")
async def list_lots(item_id: Optional[UUID] = None, expiring_within_days: int = Query(7, ge=0, le=365), location_id: Optional[UUID] = None, company_id: UUID = Depends(get_client_company_id), _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        rows = await lots.expiring_lots(conn, company_id=company_id, location_id=location_id, within_days=expiring_within_days)
    return {"lots": [row for row in rows if item_id is None or row['item_id'] == item_id]}

@router.get('/variance')
async def usage_variance(start: date, end: date, location_id: Optional[UUID] = None, company_id: UUID = Depends(get_client_company_id), _=Depends(require_admin_or_client), _sales=Depends(require_feature('sales_intake'))):
    async with get_connection() as conn:
        rows = await conn.fetch("""SELECT al.*, i.name, i.unit FROM inventory_audit_lines al
            JOIN inventory_audit_runs ar ON ar.id=al.run_id JOIN inventory_items i ON i.id=al.item_id
            WHERE ar.company_id=$1 AND al.created_at::date BETWEEN $2 AND $3
            AND ($4::uuid IS NULL OR i.location_id IS NULL OR i.location_id=$4)
            ORDER BY al.created_at DESC""", company_id, start, end, location_id)
    return {'lines': [dict(row) for row in rows]}

@router.post("/lots/{lot_id}/discard")
async def discard_lot(lot_id: UUID, company_id: UUID = Depends(get_client_company_id), user=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        async with conn.transaction():
            lot = await conn.fetchrow("SELECT * FROM inventory_lots WHERE id=$1 AND company_id=$2 AND status='open' FOR UPDATE", lot_id, company_id)
            if lot is None: raise HTTPException(404, "Open lot not found.")
            quantity = lot['quantity_remaining']
            rows = await movements.record_movements(conn, company_id=company_id, channel_id=None, source_message_id=None, recorded_by=user.id, kind='waste', narrative='Expired lot discarded', note=f"Lot {lot['lot_code'] or str(lot_id)}", lines=[{'item_id': lot['item_id'], 'quantity': quantity, 'estimated': False, 'waste_reason': 'expired', 'consume_lots': False}])
            await conn.execute("UPDATE inventory_lots SET quantity_remaining=0,status='discarded',updated_at=NOW() WHERE id=$1", lot_id)
    return {"lot_id": lot_id, "movement": rows[0] if rows else None}

@router.get("/par/history")
async def get_par_history(item_id: UUID, limit: int = Query(50, ge=1, le=200), company_id: UUID = Depends(get_client_company_id), _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        return {"history": await par_store.par_history(conn, company_id=company_id, item_id=item_id, limit=limit)}

@router.post("/par/enroll")
async def enroll_par(body: ParEnroll, company_id: UUID = Depends(get_client_company_id), _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        return {"updated": await par_store.enroll_items_in_auto_par(conn, company_id=company_id, item_ids=body.item_ids, enrolled=body.enrolled)}

@router.post('/ask')
async def ask_waste_analyst(body: WasteAsk, company_id: UUID = Depends(get_client_company_id), user=Depends(require_admin_or_client)):
    from app.core.services.redis_cache import check_rate_limit
    await check_rate_limit(f'user:{user.id}', 'inventory_waste_ask', 30, 3600)
    end = body.end or date.today(); start = body.start or end - timedelta(days=6)
    async with get_connection() as conn:
        return await waste_agent.answer_question(conn, company_id=company_id, location_id=body.location_id, start=start, end=end, question=body.question)
