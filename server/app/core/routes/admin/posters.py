"""Admin posters routes (J5 split)."""
import asyncio
import difflib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncGenerator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Depends, Query, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.services.credential_crypto import decrypt_credential_fields
from app.core.services.scope_registry.codify import codified_sql
from app.core.feature_flags import merge_company_features
from app.core.services.email import get_email_service
from app.core.models.compliance import AutoCheckSettings, LocationCreate
from app.core.models.compliance_evals import EvalRunRequest, FindingResolveRequest
from app.core.compliance_registry import (
    TRIGGER_PROFILES,
    LABOR_CATEGORIES, HEALTHCARE_CATEGORIES, ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES, SUPPLEMENTARY_CATEGORIES,
)
from app.core.services.compliance_service import (
    _resolve_industry,
    update_auto_check_settings,
    _jurisdiction_row_to_dict,
    run_compliance_check_background,
    run_compliance_check_stream,
    research_jurisdiction_repo_only,
    get_locations,
    get_location_requirements,
    create_location,
    admin_add_requirement_to_location,
)
from app.core.services.redis_cache import (
    get_redis_cache, cache_get, cache_set, cache_delete, cache_delete_pattern,
    admin_jurisdictions_list_key, admin_jurisdiction_detail_key,
    admin_jurisdiction_data_overview_key, admin_jurisdiction_policy_overview_key,
    admin_bookmarked_requirements_key,
)
from app.core.services.rate_limiter import get_rate_limiter
from app.core.services.auth import hash_password
from app.core.services.platform_settings import (
    get_visible_features, prime_visible_features_cache,
    get_matcha_work_model_mode, prime_matcha_work_model_mode_cache,
    get_jurisdiction_research_model_mode, prime_jurisdiction_research_model_mode_cache,
    get_er_similarity_weights, prime_er_similarity_weights_cache,
    get_tenant_codified_only, prime_tenant_codified_only_cache,
    DEFAULT_ER_SIMILARITY_WEIGHTS, EXPECTED_WEIGHT_KEYS,
)
from app.matcha.services import billing_service as mw_billing_service
from app.config import get_settings
from app.core.services.stripe_service import StripeService, StripeServiceError
from app.core.feature_flags import DEFAULT_COMPANY_FEATURES
from app.core.services.deal_pricing import DealInputs
from app.core.services.deal_full import FullDealInputs
from app.core.services.deal_broker import BrokerInputs
from app.core.services.deal_book import BookInputs


from app.core.services.scope_registry.jurisdiction_chain import (  # noqa: E402
    resolve_jurisdiction_chain as _resolve_jurisdiction_chain,
)

from app.core.models.admin import *  # noqa: F401,F403
from app.core.routes.admin._shared import *  # noqa: F401,F403

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/posters/templates", dependencies=[Depends(require_admin)])
async def list_poster_templates():
    """List all poster templates with jurisdiction info."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT pt.*, j.city, j.state, j.county
            FROM poster_templates pt
            JOIN jurisdictions j ON pt.jurisdiction_id = j.id
            ORDER BY j.state, j.city
            """
        )
        templates = []
        for r in rows:
            j_name = f"{r['city']}, {r['state']}"
            if r["county"]:
                j_name = f"{r['city']}, {r['county']} County, {r['state']}"
            templates.append({
                "id": str(r["id"]),
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "title": r["title"],
                "description": r["description"],
                "version": r["version"],
                "pdf_url": r["pdf_url"],
                "pdf_generated_at": _fmt_dt(r["pdf_generated_at"]),
                "categories_included": r["categories_included"],
                "requirement_count": r["requirement_count"],
                "status": r["status"],
                "jurisdiction_name": j_name,
                "state": r["state"],
                "created_at": _fmt_dt(r["created_at"]),
                "updated_at": _fmt_dt(r["updated_at"]),
            })
        return {"templates": templates, "total": len(templates)}


@router.post("/posters/templates/{jurisdiction_id}", dependencies=[Depends(require_admin)])
async def generate_poster_template(jurisdiction_id: UUID):
    """Generate or regenerate a compliance poster PDF for a jurisdiction."""
    from app.core.services.poster_service import generate_poster_pdf

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

        result = await generate_poster_pdf(conn, jurisdiction_id)
        return result


@router.post("/posters/generate-all", dependencies=[Depends(require_admin)])
async def generate_all_missing_posters():
    """Generate poster templates for all jurisdictions that have poster-worthy
    requirement data but no template yet."""
    from app.core.services.poster_service import generate_all_missing_posters as _generate_all

    async with get_connection() as conn:
        result = await _generate_all(conn)
        return result


@router.get("/posters/orders", dependencies=[Depends(require_admin)])
async def list_poster_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List all poster orders with optional status filter."""
    async with get_connection() as conn:
        query = """
            SELECT po.*,
                   comp.name AS company_name,
                   bl.name AS location_name, bl.city AS location_city, bl.state AS location_state,
                   u.email AS requested_by_email
            FROM poster_orders po
            JOIN companies comp ON po.company_id = comp.id
            JOIN business_locations bl ON po.location_id = bl.id
            LEFT JOIN users u ON po.requested_by = u.id
        """
        params = []
        if status_filter:
            query += " WHERE po.status = $1"
            params.append(status_filter)
        query += " ORDER BY po.created_at DESC"

        rows = await conn.fetch(query, *params)

        orders = []
        for r in rows:
            # Fetch items for this order
            items = await conn.fetch(
                """
                SELECT poi.*, pt.title AS template_title,
                       j.city || ', ' || j.state AS jurisdiction_name
                FROM poster_order_items poi
                JOIN poster_templates pt ON poi.template_id = pt.id
                JOIN jurisdictions j ON pt.jurisdiction_id = j.id
                WHERE poi.order_id = $1
                """,
                r["id"],
            )
            orders.append({
                "id": str(r["id"]),
                "company_id": str(r["company_id"]),
                "location_id": str(r["location_id"]),
                "status": r["status"],
                "requested_by": str(r["requested_by"]) if r["requested_by"] else None,
                "admin_notes": r["admin_notes"],
                "quote_amount": float(r["quote_amount"]) if r["quote_amount"] else None,
                "shipping_address": r["shipping_address"],
                "tracking_number": r["tracking_number"],
                "shipped_at": _fmt_dt(r["shipped_at"]),
                "delivered_at": _fmt_dt(r["delivered_at"]),
                "metadata": r["metadata"],
                "created_at": _fmt_dt(r["created_at"]),
                "updated_at": _fmt_dt(r["updated_at"]),
                "company_name": r["company_name"],
                "location_name": r["location_name"],
                "location_city": r["location_city"],
                "location_state": r["location_state"],
                "requested_by_email": r["requested_by_email"],
                "items": [
                    {
                        "id": str(i["id"]),
                        "template_id": str(i["template_id"]),
                        "quantity": i["quantity"],
                        "template_title": i["template_title"],
                        "jurisdiction_name": i["jurisdiction_name"],
                    }
                    for i in items
                ],
            })
        return {"orders": orders, "total": len(orders)}


@router.get("/posters/orders/{order_id}", dependencies=[Depends(require_admin)])
async def get_poster_order(order_id: UUID):
    """Get poster order detail."""
    async with get_connection() as conn:
        r = await conn.fetchrow(
            """
            SELECT po.*,
                   comp.name AS company_name,
                   bl.name AS location_name, bl.city AS location_city, bl.state AS location_state,
                   u.email AS requested_by_email
            FROM poster_orders po
            JOIN companies comp ON po.company_id = comp.id
            JOIN business_locations bl ON po.location_id = bl.id
            LEFT JOIN users u ON po.requested_by = u.id
            WHERE po.id = $1
            """,
            order_id,
        )
        if not r:
            raise HTTPException(status_code=404, detail="Order not found")

        items = await conn.fetch(
            """
            SELECT poi.*, pt.title AS template_title,
                   j.city || ', ' || j.state AS jurisdiction_name
            FROM poster_order_items poi
            JOIN poster_templates pt ON poi.template_id = pt.id
            JOIN jurisdictions j ON pt.jurisdiction_id = j.id
            WHERE poi.order_id = $1
            """,
            order_id,
        )
        return {
            "id": str(r["id"]),
            "company_id": str(r["company_id"]),
            "location_id": str(r["location_id"]),
            "status": r["status"],
            "requested_by": str(r["requested_by"]) if r["requested_by"] else None,
            "admin_notes": r["admin_notes"],
            "quote_amount": float(r["quote_amount"]) if r["quote_amount"] else None,
            "shipping_address": r["shipping_address"],
            "tracking_number": r["tracking_number"],
            "shipped_at": _fmt_dt(r["shipped_at"]),
            "delivered_at": _fmt_dt(r["delivered_at"]),
            "metadata": r["metadata"],
            "created_at": _fmt_dt(r["created_at"]),
            "updated_at": _fmt_dt(r["updated_at"]),
            "company_name": r["company_name"],
            "location_name": r["location_name"],
            "location_city": r["location_city"],
            "location_state": r["location_state"],
            "requested_by_email": r["requested_by_email"],
            "items": [
                {
                    "id": str(i["id"]),
                    "template_id": str(i["template_id"]),
                    "quantity": i["quantity"],
                    "template_title": i["template_title"],
                    "jurisdiction_name": i["jurisdiction_name"],
                }
                for i in items
            ],
        }


@router.patch("/posters/orders/{order_id}", dependencies=[Depends(require_admin)])
async def update_poster_order(order_id: UUID, request: PosterOrderUpdateRequest):
    """Update a poster order (status, notes, quote, tracking)."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id, status FROM poster_orders WHERE id = $1", order_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Order not found")

        updates = []
        params = []
        idx = 1

        if request.status is not None:
            if request.status not in VALID_ORDER_STATUSES:
                raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")
            updates.append(f"status = ${idx}")
            params.append(request.status)
            idx += 1

            # Auto-set timestamps
            if request.status == "shipped":
                updates.append(f"shipped_at = NOW()")
            elif request.status == "delivered":
                updates.append(f"delivered_at = NOW()")

        if request.admin_notes is not None:
            updates.append(f"admin_notes = ${idx}")
            params.append(request.admin_notes)
            idx += 1

        if request.quote_amount is not None:
            updates.append(f"quote_amount = ${idx}")
            params.append(request.quote_amount)
            idx += 1

        if request.tracking_number is not None:
            updates.append(f"tracking_number = ${idx}")
            params.append(request.tracking_number)
            idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at = NOW()")
        params.append(order_id)

        await conn.execute(
            f"UPDATE poster_orders SET {', '.join(updates)} WHERE id = ${idx}",
            *params,
        )

        return {"status": "updated", "order_id": str(order_id)}
