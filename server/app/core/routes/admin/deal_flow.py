"""Admin deal flow routes (J5 split)."""
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


@router.post("/deal-flow/quote", dependencies=[Depends(require_admin)])
async def deal_flow_quote(inp: DealInputs):
    """Compute Lite + Mid + Max quotes from one set of inputs (headcount + discounts + overrides).

    Stateless — nothing persisted. Single source of pricing truth so the UI and
    the generated PDF never drift.
    """
    from app.core.services.deal_pricing import compute_all

    return compute_all(inp)


@router.post("/deal-flow/proposal", dependencies=[Depends(require_admin)])
async def deal_flow_proposal(inp: DealInputs):
    """Render a single-page pricing proposal (Lite + Mid + Max) to PDF via WeasyPrint."""
    from app.core.services.deal_pricing import compute_all
    from app.core.services.deal_proposal_template import render_proposal_html, render_lite_proposal_html

    quotes = compute_all(inp)
    if inp.template == "lite_edition":
        html_str = render_lite_proposal_html(inp, quotes["lite"])
    else:
        html_str = render_proposal_html(inp, quotes)

    try:
        from app.core.services.pdf import render_pdf
    except ImportError as ie:
        logger.error("weasyprint import failed: %s", ie)
        raise HTTPException(
            status_code=501,
            detail="PDF generation not available — install weasyprint on the server (`pip install weasyprint`).",
        )
    try:
        pdf_bytes = await asyncio.wait_for(
            asyncio.to_thread(lambda: render_pdf(html_str)),
            timeout=60,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="PDF render timed out.")

    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", inp.company_name).strip("_") or "Matcha"
    filename = f"{safe_name}_Matcha_Proposal.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/deal-flow/broker-defaults", dependencies=[Depends(require_admin)])
async def deal_flow_broker_defaults():
    """Default editable blocks + margin tiers for the broker packet."""
    from app.core.services.deal_broker import DEFAULT_BROKER_BLOCKS, DEFAULT_MARGIN_TIERS

    return {"blocks": DEFAULT_BROKER_BLOCKS, "margin_tiers": DEFAULT_MARGIN_TIERS}


@router.post("/deal-flow/broker-proposal/preview", dependencies=[Depends(require_admin)])
async def deal_flow_broker_preview(inp: BrokerInputs):
    """Styled HTML preview of the broker packet (for in-app iframe)."""
    from app.core.services.deal_broker import compute_broker_quote
    from app.core.services.deal_broker_template import render_broker_proposal_html

    return {"html": render_broker_proposal_html(inp, compute_broker_quote(inp))}


@router.post("/deal-flow/broker-proposal", dependencies=[Depends(require_admin)])
async def deal_flow_broker_proposal(inp: BrokerInputs):
    """Render the broker partner-program packet to PDF."""
    from app.core.services.deal_broker import compute_broker_quote
    from app.core.services.deal_broker_template import render_broker_proposal_html

    html_str = render_broker_proposal_html(inp, compute_broker_quote(inp))
    try:
        from app.core.services.pdf import render_pdf
    except ImportError as ie:
        logger.error("weasyprint import failed: %s", ie)
        raise HTTPException(status_code=501, detail="PDF generation not available — install weasyprint on the server.")
    try:
        pdf_bytes = await asyncio.wait_for(
            asyncio.to_thread(lambda: render_pdf(html_str)), timeout=60,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="PDF render timed out.")

    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", inp.broker_name).strip("_") or "Broker"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_Matcha_Partner_Program.pdf"'},
    )


@router.get("/deal-flow/book-defaults", dependencies=[Depends(require_admin)])
async def deal_flow_book_defaults():
    """Default editable blocks + volume-discount tiers for the broker book one-pager."""
    from app.core.services.deal_book import DEFAULT_BOOK_BLOCKS, DEFAULT_DISCOUNT_TIERS

    return {"blocks": DEFAULT_BOOK_BLOCKS, "discount_tiers": DEFAULT_DISCOUNT_TIERS}


@router.post("/deal-flow/book-proposal/preview", dependencies=[Depends(require_admin)])
async def deal_flow_book_preview(inp: BookInputs):
    """Styled HTML preview of the broker book one-pager (for in-app iframe)."""
    from app.core.services.deal_book import compute_book_quote
    from app.core.services.deal_book_template import render_book_proposal_html

    return {"html": render_book_proposal_html(inp, compute_book_quote(inp))}


@router.post("/deal-flow/book-proposal", dependencies=[Depends(require_admin)])
async def deal_flow_book_proposal(inp: BookInputs):
    """Render the broker Matcha-Lite book one-pager (pooled-volume pricing) to PDF."""
    from app.core.services.deal_book import compute_book_quote
    from app.core.services.deal_book_template import render_book_proposal_html

    html_str = render_book_proposal_html(inp, compute_book_quote(inp))
    try:
        from app.core.services.pdf import render_pdf
    except ImportError as ie:
        logger.error("weasyprint import failed: %s", ie)
        raise HTTPException(status_code=501, detail="PDF generation not available — install weasyprint on the server.")
    try:
        pdf_bytes = await asyncio.wait_for(
            asyncio.to_thread(lambda: render_pdf(html_str)), timeout=60,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="PDF render timed out.")

    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", inp.broker_name).strip("_") or "Broker"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_Matcha_Lite_Book_Pricing.pdf"'},
    )


@router.get("/deal-flow/lite-defaults", dependencies=[Depends(require_admin)])
async def deal_flow_lite_defaults():
    """Default editable blocks for the Lite Edition one-pager (UI pre-fills from this)."""
    from app.core.services.deal_proposal_template import DEFAULT_LITE_BLOCKS

    return {"blocks": DEFAULT_LITE_BLOCKS}


@router.get("/deal-flow/full-defaults", dependencies=[Depends(require_admin)])
async def deal_flow_full_defaults():
    """Default editable document blocks for the full proposal (UI pre-fills from this)."""
    from app.core.services.deal_full import DEFAULT_FULL_BLOCKS

    return {"blocks": DEFAULT_FULL_BLOCKS}


@router.post("/deal-flow/proposal/preview", dependencies=[Depends(require_admin)])
async def deal_flow_proposal_preview(inp: DealInputs):
    """Styled HTML preview of the one-pager (for in-app iframe, no PDF render)."""
    from app.core.services.deal_pricing import compute_all
    from app.core.services.deal_proposal_template import render_proposal_html, render_lite_proposal_html

    quotes = compute_all(inp)
    if inp.template == "lite_edition":
        html_str = render_lite_proposal_html(inp, quotes["lite"])
    else:
        html_str = render_proposal_html(inp, quotes)
    return {"html": html_str}


@router.post("/deal-flow/full-proposal/preview", dependencies=[Depends(require_admin)])
async def deal_flow_full_proposal_preview(inp: FullDealInputs):
    """Styled HTML preview of the full proposal (for in-app iframe, no PDF render)."""
    from app.core.services.deal_full import compute_full_pricing
    from app.core.services.deal_full_template import render_full_proposal_html

    q = compute_full_pricing(inp)
    return {"html": render_full_proposal_html(inp, q)}


@router.post("/deal-flow/full-proposal", dependencies=[Depends(require_admin)])
async def deal_flow_full_proposal(inp: FullDealInputs):
    """Render the full multi-page service proposal (rack-rate model) to PDF."""
    from app.core.services.deal_full import compute_full_pricing
    from app.core.services.deal_full_template import render_full_proposal_html

    q = compute_full_pricing(inp)
    html_str = render_full_proposal_html(inp, q)

    try:
        from app.core.services.pdf import render_pdf
    except ImportError as ie:
        logger.error("weasyprint import failed: %s", ie)
        raise HTTPException(
            status_code=501,
            detail="PDF generation not available — install weasyprint on the server (`pip install weasyprint`).",
        )
    try:
        pdf_bytes = await asyncio.wait_for(
            asyncio.to_thread(lambda: render_pdf(html_str)),
            timeout=90,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="PDF render timed out.")

    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", inp.company_name).strip("_") or "Matcha"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_Matcha_Full_Proposal.pdf"'},
    )


@router.get("/deal-flow/templates/{key}", dependencies=[Depends(require_admin)])
async def deal_flow_get_template(key: str):
    """Return the saved template payload for a Deal Flow tab, or null if unset."""
    if key not in _DEAL_TEMPLATE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown template key")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT payload, updated_at, updated_by FROM deal_flow_templates WHERE template_key = $1",
            key,
        )
    return _deal_template_row(key, row)


@router.put("/deal-flow/templates/{key}")
async def deal_flow_save_template(
    key: str,
    payload: dict = Body(..., embed=True),
    admin=Depends(require_admin),
):
    """Upsert the saved template payload for a Deal Flow tab (admin-global, shared)."""
    if key not in _DEAL_TEMPLATE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown template key")
    updated_by = getattr(admin, "email", None) or getattr(admin, "id", None)
    updated_by = str(updated_by) if updated_by is not None else None
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO deal_flow_templates (template_key, payload, updated_at, updated_by)
            VALUES ($1, $2::jsonb, now(), $3)
            ON CONFLICT (template_key) DO UPDATE
              SET payload = EXCLUDED.payload, updated_at = now(), updated_by = EXCLUDED.updated_by
            RETURNING payload, updated_at, updated_by
            """,
            key, json.dumps(payload), updated_by,
        )
    return _deal_template_row(key, row)
