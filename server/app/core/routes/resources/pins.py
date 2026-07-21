"""pins routes (L9 split)."""
import html as _html
import json as _json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.models.auth import CurrentUser
from app.core.dependencies import get_optional_user
from app.matcha.dependencies import require_client, get_client_company_id
from app.core.services.redis_cache import check_rate_limit, client_ip

from app.core.routes.resources._shared import *  # noqa: F401,F403  (router objects + shared models/consts)
logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/assets")
async def list_assets(current_user: Optional[CurrentUser] = Depends(get_optional_user)):
    """List downloadable assets. Anonymous visitors see metadata for all
    templates but only get the download `path` for free-tier ones — the rest
    show a "Sign up to download" CTA on the frontend. Signed-in business
    accounts get every path."""
    assets: list[dict] = []
    for slug, meta in ASSETS.items():
        entry = {"slug": slug, **meta}
        if current_user is None and not meta.get("is_free", False):
            entry["path"] = None
        assets.append(entry)
    return {"assets": assets}




@router.get("/pins")
async def list_resource_pins(
    current_user: CurrentUser = Depends(require_client),
):
    from app.core.services import resource_pins_service
    pins = await resource_pins_service.list_pins(current_user.id)
    return {"pins": pins}




@router.post("/pins", status_code=204)
async def add_resource_pin(
    body: ResourcePinBody,
    current_user: CurrentUser = Depends(require_client),
):
    from app.core.services import resource_pins_service
    try:
        await resource_pins_service.add_pin(current_user.id, body.kind, body.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))




@router.delete("/pins/{kind}/{resource_id}", status_code=204)
async def remove_resource_pin(
    kind: str,
    resource_id: str,
    current_user: CurrentUser = Depends(require_client),
):
    from app.core.services import resource_pins_service
    try:
        await resource_pins_service.remove_pin(current_user.id, kind, resource_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
