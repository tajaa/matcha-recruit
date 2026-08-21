"""Square connection, location binding, and manual POS sync endpoints."""

import json
import os
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.services.secret_crypto import encrypt_secret
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client, require_all_features
from app.matcha.models.inventory import POSLocationBindingUpsert, POSMappingUpsert, POSSalesSyncRequest
from app.matcha.services.inventory import pos
from app.matcha.services.inventory.pos.square import SquareProvider
from app.matcha.services.inventory.pos.sync import _credentials, sync_pos_connection


router = APIRouter()
_sales_gate = Depends(require_all_features("matcha_ops", "inventory", "sales_intake"))


def _square_redirect_uri() -> str:
    return os.getenv("SQUARE_OAUTH_REDIRECT_URI", "")


def _require_square_config() -> None:
    missing = [
        name for name, value in (
            ("SQUARE_CLIENT_ID", SquareProvider._CLIENT_ID),
            ("SQUARE_CLIENT_SECRET", SquareProvider._CLIENT_SECRET),
            ("SQUARE_OAUTH_REDIRECT_URI", _square_redirect_uri()),
        ) if not value
    ]
    if missing:
        raise HTTPException(503, f"Square is not configured (missing {', '.join(missing)})")


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _connection_payload(row) -> dict:
    config = _json_object(row["config"])
    return {
        "id": row["id"],
        "provider": row["provider"],
        "status": row["status"],
        "environment": config.get("environment"),
        "last_sync_at": row["last_sync_at"],
        "last_error": row["last_error"],
        "updated_at": row["updated_at"],
        "has_credentials": bool(row["secrets"]),
    }


@router.get("/authorize")
async def authorize_square(
    current_user=Depends(require_admin_or_client),
    _gate=_sales_gate,
):
    _require_square_config()
    company_id = await get_client_company_id(current_user)
    state = secrets.token_urlsafe(32)
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO oauth_states (state, company_id, created_at) VALUES ($1, $2, NOW())",
            state,
            company_id,
        )
    provider = SquareProvider()
    return {"oauth_url": provider.authorize_url(state=state, redirect_uri=_square_redirect_uri())}


@router.get("/callback")
async def square_callback(code: str = Query(...), state: str = Query(...)):
    _require_square_config()
    async with get_connection() as conn:
        oauth_state = await conn.fetchrow(
            """SELECT company_id FROM oauth_states
               WHERE state=$1 AND created_at > NOW() - INTERVAL '10 minutes'""",
            state,
        )
        if oauth_state is None:
            raise HTTPException(400, "Invalid or expired state")
        try:
            token_data = await SquareProvider().exchange_code(
                code=code, redirect_uri=_square_redirect_uri(),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(400, "Square token response did not include an access token")
        config = {
            "environment": os.getenv("SQUARE_ENVIRONMENT", "production").lower(),
            "merchant_id": token_data.get("merchant_id"),
        }
        secrets_payload = {
            "access_token": encrypt_secret(access_token),
            "refresh_token": encrypt_secret(token_data.get("refresh_token")),
            "expires_at": token_data.get("expires_at") if isinstance(token_data.get("expires_at"), str) else None,
        }
        await conn.execute(
            """
            INSERT INTO inventory_pos_connections
                (company_id, provider, status, config, secrets, created_by, updated_by)
            VALUES ($1, 'square', 'connected', $2::jsonb, $3::jsonb, NULL, NULL)
            ON CONFLICT (company_id, provider) DO UPDATE SET
                status='connected', config=EXCLUDED.config, secrets=EXCLUDED.secrets,
                last_error=NULL, updated_at=NOW()
            """,
            oauth_state["company_id"], json.dumps(config), json.dumps(secrets_payload),
        )
        await conn.execute("DELETE FROM oauth_states WHERE state=$1", state)
    return RedirectResponse(url="/ops/inventory?pos=connected")


@router.get("")
async def list_pos_connections(
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_sales_gate,
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM inventory_pos_connections WHERE company_id=$1 ORDER BY provider",
            company_id,
        )
    return {"connections": [_connection_payload(row) for row in rows]}


@router.get("/{connection_id}/locations")
async def list_pos_locations(
    connection_id: UUID,
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_sales_gate,
):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM inventory_pos_connections WHERE id=$1 AND company_id=$2",
            connection_id, company_id,
        )
    if row is None:
        raise HTTPException(404, "POS connection not found")
    try:
        locations = await pos.provider_for(row["provider"]).list_locations(
            credentials=_credentials(_json_object(row["secrets"])),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    async with get_connection() as conn:
        bindings = await conn.fetch(
            """SELECT external_location_id, location_id
               FROM inventory_pos_location_bindings
               WHERE connection_id=$1 AND company_id=$2""",
            connection_id, company_id,
        )
    bound_by_external_id = {row["external_location_id"]: row["location_id"] for row in bindings}
    return {"locations": [
        {**location, "location_id": bound_by_external_id.get(location["external_location_id"])}
        for location in locations
    ]}


@router.get("/{connection_id}/catalog")
async def list_pos_catalog(
    connection_id: UUID,
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_sales_gate,
):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM inventory_pos_connections WHERE id=$1 AND company_id=$2",
            connection_id, company_id,
        )
    if row is None:
        raise HTTPException(404, "POS connection not found")
    try:
        catalog = await pos.provider_for(row["provider"]).list_catalog_items(
            credentials=_credentials(_json_object(row["secrets"])),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"items": catalog}


@router.put("/{connection_id}/locations")
async def bind_pos_location(
    connection_id: UUID,
    body: POSLocationBindingUpsert,
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_sales_gate,
):
    async with get_connection() as conn:
        connection = await conn.fetchval(
            "SELECT 1 FROM inventory_pos_connections WHERE id=$1 AND company_id=$2",
            connection_id, company_id,
        )
        location = await conn.fetchval(
            """SELECT 1 FROM business_locations
               WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE
                 AND is_company_wide=FALSE""",
            body.location_id, company_id,
        )
        if not connection:
            raise HTTPException(404, "POS connection not found")
        if not location:
            raise HTTPException(404, "Location not found")
        row = await conn.fetchrow(
            """
            INSERT INTO inventory_pos_location_bindings
                (connection_id, company_id, location_id, external_location_id, name, timezone)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (connection_id, external_location_id) DO UPDATE SET
                location_id=EXCLUDED.location_id, name=EXCLUDED.name,
                timezone=EXCLUDED.timezone, updated_at=NOW()
            RETURNING *
            """,
            connection_id, company_id, body.location_id, body.external_location_id,
            body.name, body.timezone,
        )
    return dict(row)


@router.put("/{connection_id}/mappings")
async def map_pos_item(
    connection_id: UUID,
    body: POSMappingUpsert,
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_sales_gate,
):
    async with get_connection() as conn:
        owned = await conn.fetchval(
            "SELECT 1 FROM inventory_pos_connections WHERE id=$1 AND company_id=$2",
            connection_id, company_id,
        )
        mapping = await conn.fetchval(
            "SELECT 1 FROM inventory_sales_mappings WHERE id=$1 AND company_id=$2",
            body.mapping_id, company_id,
        )
        if not owned or not mapping:
            raise HTTPException(404, "POS connection or sales mapping not found")
        row = await conn.fetchrow(
            """
            INSERT INTO inventory_pos_mapping_keys
                (connection_id, company_id, external_item_id, mapping_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (connection_id, external_item_id) DO UPDATE SET
                mapping_id=EXCLUDED.mapping_id, updated_at=NOW()
            RETURNING *
            """,
            connection_id, company_id, body.external_item_id, body.mapping_id,
        )
    return dict(row)


@router.get("/{connection_id}/mappings")
async def list_pos_mappings(
    connection_id: UUID,
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_sales_gate,
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT k.external_item_id, k.mapping_id, m.sold_name
               FROM inventory_pos_mapping_keys k
               JOIN inventory_sales_mappings m ON m.id=k.mapping_id
               WHERE k.connection_id=$1 AND k.company_id=$2
               ORDER BY k.external_item_id""",
            connection_id, company_id,
        )
    return {"mappings": [dict(row) for row in rows]}


@router.post("/{connection_id}/sync")
async def sync_pos(
    connection_id: UUID,
    body: POSSalesSyncRequest,
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
    _gate=_sales_gate,
):
    async with get_connection() as conn:
        try:
            return await sync_pos_connection(
                conn,
                connection_id=connection_id,
                company_id=company_id,
                start_date=body.start_date,
                end_date=body.end_date,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
