"""Cappe adapter for matcha IR incidents — /api/cappe/ir/*.

Thin wrappers over the matcha `ir_incidents` package handlers. Auth is the
cappe-native `require_matcha_feature("incidents")` gate (scope=cappe token +
`cappe_accounts.matcha_features.incidents`); each wrapper then calls the
existing matcha handler as a plain async function, passing the server-minted
bridged `CurrentUser` (role='client', backing tenant — see
`services/matcha_bridge.py`). `get_client_company_id` inside the handlers
resolves the backing company via the real `clients` membership and sets the
RLS tenant, so the 12k-line IR package runs unmodified.

Scope mirrors the `matcha_lite_essentials` shape (no employee roster): incident
CRUD, corrective actions (CAPA), documents, and the no-roster `ir_people`
index. NO OSHA logs, NO roster/employee flows, NO copilot (phase 2).

Plus one cappe-owned surface: /ir/locations. Matcha requires client-created
incidents to reference a `business_locations` row, so cappe accounts manage a
minimal location list for their backing company here (auto_check_enabled=false
so matcha's compliance workers never scan them).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query,
    Request, UploadFile,
)
from pydantic import BaseModel, Field

from ...database import get_connection
from app.matcha.models.ir_incident import IRIncidentCreate, IRIncidentUpdate
from app.matcha.models.ir_incident import (
    CorrectiveActionCreate,
    CorrectiveActionUpdate,
)
from app.matcha.routes.ir_incidents import capa as _capa
from app.matcha.routes.ir_incidents import crud as _crud
from app.matcha.routes.ir_incidents import documents as _documents
from app.matcha.routes.ir_incidents import people as _people

from ..services.matcha_bridge import CappeBridgeContext, require_matcha_feature

router = APIRouter(prefix="/ir", tags=["cappe-ir"])

_gate = require_matcha_feature("incidents")


# ---------------------------------------------------------------------------
# Locations (cappe-owned helper surface, not a matcha wrapper)
# ---------------------------------------------------------------------------

class CappeIrLocationCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=2)
    zipcode: str = Field(min_length=5, max_length=10)


@router.get("/locations")
async def list_locations(ctx: CappeBridgeContext = Depends(_gate)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, address, city, state, zipcode, is_active, created_at
            FROM business_locations
            WHERE company_id = $1 AND is_active = true
            ORDER BY created_at
            """,
            ctx.company_id,
        )
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "address": r["address"],
            "city": r["city"],
            "state": r["state"],
            "zipcode": r["zipcode"],
        }
        for r in rows
    ]


@router.post("/locations", status_code=201)
async def create_location(
    body: CappeIrLocationCreate,
    ctx: CappeBridgeContext = Depends(_gate),
):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO business_locations
                (company_id, name, address, city, state, zipcode,
                 is_active, auto_check_enabled)
            VALUES ($1, $2, $3, $4, upper($5), $6, true, false)
            RETURNING id, name, address, city, state, zipcode
            """,
            ctx.company_id,
            body.name,
            body.address,
            body.city,
            body.state,
            body.zipcode,
        )
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "address": row["address"],
        "city": row["city"],
        "state": row["state"],
        "zipcode": row["zipcode"],
    }


@router.delete("/locations/{location_id}", status_code=204)
async def deactivate_location(
    location_id: UUID,
    ctx: CappeBridgeContext = Depends(_gate),
):
    async with get_connection() as conn:
        updated = await conn.execute(
            "UPDATE business_locations SET is_active = false "
            "WHERE id = $1 AND company_id = $2",
            location_id,
            ctx.company_id,
        )
    if updated == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Location not found")


# ---------------------------------------------------------------------------
# Incident CRUD (wraps ir_incidents/crud.py)
# ---------------------------------------------------------------------------

@router.post("/incidents")
async def create_incident(
    incident: IRIncidentCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _crud.create_incident(
        incident, request, background_tasks, current_user=ctx.matcha_user
    )


@router.get("/incidents")
async def list_incidents(
    status: Optional[str] = None,
    incident_type: Optional[str] = None,
    severity: Optional[str] = None,
    location: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _crud.list_incidents(
        status=status,
        incident_type=incident_type,
        severity=severity,
        location=location,
        from_date=from_date,
        to_date=to_date,
        search=search,
        limit=limit,
        offset=offset,
        current_user=ctx.matcha_user,
    )


# NOTE: multi-segment static paths must register before /incidents/{incident_id}
# so FastAPI's registration-order matching can't shadow them. (Same trap as the
# matcha package — see ir_incidents/CLAUDE.md "Route ordering".)

@router.get("/incidents/corrective-actions/open")
async def list_open_corrective_actions(ctx: CappeBridgeContext = Depends(_gate)):
    return await _capa.list_open_corrective_actions(current_user=ctx.matcha_user)


@router.get("/incidents/people/search")
async def search_ir_people(
    q: str = Query("", max_length=120),
    limit: int = Query(20, ge=1, le=50),
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _people.search_ir_people(q=q, limit=limit, current_user=ctx.matcha_user)


@router.get("/incidents/people/{person_id}/incidents")
async def get_ir_person_incidents(
    person_id: UUID,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _people.get_ir_person_incidents(person_id, current_user=ctx.matcha_user)


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: UUID,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _crud.get_incident(incident_id, current_user=ctx.matcha_user)


@router.put("/incidents/{incident_id}")
async def update_incident(
    incident_id: UUID,
    incident: IRIncidentUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _crud.update_incident(
        incident_id, incident, request, background_tasks, current_user=ctx.matcha_user
    )


@router.delete("/incidents/{incident_id}")
async def delete_incident(
    incident_id: UUID,
    request: Request,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _crud.delete_incident(incident_id, request, current_user=ctx.matcha_user)


# ---------------------------------------------------------------------------
# Corrective actions / CAPA (wraps ir_incidents/capa.py)
# ---------------------------------------------------------------------------

@router.get("/incidents/{incident_id}/corrective-actions")
async def list_corrective_actions(
    incident_id: UUID,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _capa.list_corrective_actions(incident_id, current_user=ctx.matcha_user)


@router.post("/incidents/{incident_id}/corrective-actions", status_code=201)
async def create_corrective_action(
    incident_id: UUID,
    payload: CorrectiveActionCreate,
    request: Request,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _capa.create_corrective_action(
        incident_id, payload, request, current_user=ctx.matcha_user
    )


@router.put("/incidents/corrective-actions/{action_id}")
async def update_corrective_action(
    action_id: UUID,
    payload: CorrectiveActionUpdate,
    request: Request,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _capa.update_corrective_action(
        action_id, payload, request, current_user=ctx.matcha_user
    )


@router.delete("/incidents/corrective-actions/{action_id}", status_code=204)
async def delete_corrective_action(
    action_id: UUID,
    request: Request,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _capa.delete_corrective_action(action_id, request, current_user=ctx.matcha_user)


# ---------------------------------------------------------------------------
# Documents (wraps ir_incidents/documents.py)
# ---------------------------------------------------------------------------

@router.post("/incidents/{incident_id}/documents")
async def upload_document(
    incident_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _documents.upload_document(
        incident_id, request, file=file, document_type=document_type,
        current_user=ctx.matcha_user,
    )


@router.get("/incidents/{incident_id}/documents")
async def list_documents(
    incident_id: UUID,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _documents.list_documents(incident_id, current_user=ctx.matcha_user)


@router.delete("/incidents/{incident_id}/documents/{document_id}")
async def delete_document(
    incident_id: UUID,
    document_id: UUID,
    request: Request,
    ctx: CappeBridgeContext = Depends(_gate),
):
    return await _documents.delete_document(
        incident_id, document_id, request, current_user=ctx.matcha_user
    )
