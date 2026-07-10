"""Scope-registry admin API — authority indexes, classification, resolution.

Mounted at ``/admin/scope-registry`` (see ``core/routes/__init__.py``), all
endpoints admin-gated. The service layer lives in
``app/core/services/scope_registry/``; this file is routing + shapes only.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import require_admin
from ..models.scope_registry import (
    ClassificationProposal,
    ConfirmClassificationsRequest,
    DispatchResponse,
)
from ...database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter()


_JSONB_FIELDS = ("entity_condition", "unmodeled_coordinates")


def _row_out(row) -> dict:
    """dict(row) with JSONB fields normalized — asyncpg returns JSONB as a str
    on this pool, and the API must not leak strings where objects belong."""
    from app.core.services.scope_registry.resolve import parse_jsonb

    out = dict(row)
    for field in _JSONB_FIELDS:
        if field in out:
            out[field] = parse_jsonb(out[field])
    return out


@router.get("/authority", dependencies=[Depends(require_admin)])
async def list_authority_indexes():
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT slug, name, level, jurisdiction_id, source_type,
                   domain_categories, domain_excludes, enumerable,
                   item_count, unclassified_count, last_ingested_at
            FROM authority_indexes ORDER BY level, slug
            """
        )
    return {"indexes": [dict(r) for r in rows]}


@router.post("/authority/{slug}/ingest", dependencies=[Depends(require_admin)])
async def trigger_ingest(slug: str, current_user=Depends(require_admin)) -> DispatchResponse:
    from app.core.services.scope_registry.authority_sources import all_index_slugs
    if slug not in all_index_slugs():
        raise HTTPException(status_code=404, detail=f"Unknown authority index: {slug}")

    from app.workers.tasks.scope_registry import ingest_authority_index
    ingest_authority_index.delay(index_slug=slug, trigger_source="manual")
    return DispatchResponse(status="running", dispatched_to="celery", slug=slug)


@router.get("/authority/{slug}/items", dependencies=[Depends(require_admin)])
async def list_authority_items(
    slug: str,
    classified: Optional[bool] = None,
    disposition: Optional[str] = None,
):
    """The item list — ``classified=false`` is the definitive remaining-work view."""
    async with get_connection() as conn:
        index_id = await conn.fetchval(
            "SELECT id FROM authority_indexes WHERE slug = $1", slug
        )
        if index_id is None:
            raise HTTPException(status_code=404, detail=f"Unknown authority index: {slug}")

        where = ["i.authority_index_id = $1"]
        params = [index_id]
        if classified is True:
            where.append("c.id IS NOT NULL")
        elif classified is False:
            where.append("c.id IS NULL")
        if disposition:
            params.append(disposition)
            where.append(f"c.disposition = ${len(params)}")

        rows = await conn.fetch(
            f"""
            SELECT i.id, i.citation, i.heading, i.parent_item_id, i.source_url,
                   c.disposition, c.applies_to_categories, c.excludes_categories,
                   c.entity_condition, c.regulation_key, c.status,
                   c.proposed_by, c.inherits_from_item_id
            FROM authority_index_items i
            LEFT JOIN authority_item_classifications c ON c.item_id = i.id
            WHERE {' AND '.join(where)}
            ORDER BY i.citation
            """,
            *params,
        )
    return {"slug": slug, "items": [_row_out(r) for r in rows]}


@router.post("/authority/{slug}/classify", dependencies=[Depends(require_admin)])
async def trigger_classify(slug: str, current_user=Depends(require_admin)) -> DispatchResponse:
    from app.core.services.scope_registry.authority_sources import all_index_slugs
    if slug not in all_index_slugs():
        raise HTTPException(status_code=404, detail=f"Unknown authority index: {slug}")

    from app.workers.tasks.scope_registry import classify_authority_index
    classify_authority_index.delay(index_slug=slug, triggered_by=str(current_user.id))
    return DispatchResponse(status="running", dispatched_to="celery", slug=slug)


@router.post("/seed", dependencies=[Depends(require_admin)])
async def apply_seed_classifications():
    """Apply the citation-anchored Phase-1 seed (provisional, no network)."""
    from app.core.services.scope_registry.seed import apply_seed
    async with get_connection() as conn:
        return await apply_seed(conn)


@router.post("/classifications/confirm", dependencies=[Depends(require_admin)])
async def confirm_classifications_endpoint(
    payload: ConfirmClassificationsRequest,
    current_user=Depends(require_admin),
):
    from app.core.services.scope_registry.classify import confirm_classifications
    async with get_connection() as conn:
        return await confirm_classifications(conn, payload.item_ids, current_user.id)


@router.put("/items/{item_id}/classification", dependencies=[Depends(require_admin)])
async def override_classification_endpoint(
    item_id: UUID,
    payload: ClassificationProposal,
    current_user=Depends(require_admin),
):
    from app.core.services.scope_registry.classify import override_classification
    async with get_connection() as conn:
        try:
            return await override_classification(
                conn, item_id, payload.model_dump(), current_user.id
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.get("/strata", dependencies=[Depends(require_admin)])
async def list_strata():
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.level, s.jurisdiction_id, j.display_name AS jurisdiction_label,
                   s.category_slug, s.entity_condition, s.label, s.status,
                   s.item_count, s.key_count, s.refreshed_at
            FROM scope_strata s
            LEFT JOIN jurisdictions j ON j.id = s.jurisdiction_id
            ORDER BY s.level, s.category_slug NULLS FIRST
            """
        )
    return {"strata": [_row_out(r) for r in rows]}


@router.get("/resolve", dependencies=[Depends(require_admin)])
async def resolve_preview(
    state: str,
    category: Optional[str] = None,
    naics: Optional[str] = None,
    city: Optional[str] = None,
    headcount: Optional[int] = None,
):
    """Live resolution preview: category + location (+ headcount) → scope."""
    from app.core.services.scope_registry.resolve import resolve_scope
    if not category and not naics:
        raise HTTPException(status_code=422, detail="category or naics is required")

    facility_attributes = {"employee_count": headcount} if headcount is not None else {}
    async with get_connection() as conn:
        return await resolve_scope(
            conn,
            category=category,
            naics=naics,
            state=state,
            city=city,
            facility_attributes=facility_attributes,
        )


@router.get("/fetch-queue", dependencies=[Depends(require_admin)])
async def fetch_queue_endpoint(
    category: Optional[str] = None,
    state: Optional[str] = None,
):
    """Applicable-classified items with no codified value — the research worklist."""
    from app.core.services.scope_registry.resolve import fetch_queue
    async with get_connection() as conn:
        items = await fetch_queue(conn, category=category, state=state)
    return {"items": items, "count": len(items)}


@router.get("/labor-scope", dependencies=[Depends(require_admin)])
async def labor_scope_endpoint(state: Optional[str] = None, city: Optional[str] = None):
    """Per-jurisdiction labor scope for a generic employer — federal/state/city
    codified-vs-fetch split + the core-labor checklist + honest exhaustiveness.

    Industry-agnostic (no coordinate): the authoritative "what labor must we
    fetch for this jurisdiction, and what's already codified" view.
    """
    from app.core.services.scope_registry.labor_scope import labor_scope
    async with get_connection() as conn:
        return await labor_scope(conn, state=state, city=city)


@router.get("/shadow-log", dependencies=[Depends(require_admin)])
async def list_shadow_log(limit: int = 50):
    """resolve_scope vs expand_scope diffs recorded on onboarding finalize.

    The confidence surface before the registry takes over the runtime path:
    only_in_expand is usually the category-grab's conditional over-inclusion,
    only_in_resolve is precision the registry adds.
    """
    limit = max(1, min(limit, 200))
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.session_id, s.company_id, c.name AS company_name,
                   s.resolve_keys, s.expand_keys, s.only_in_resolve,
                   s.only_in_expand, s.unmodeled_coordinates, s.created_at
            FROM scope_shadow_log s
            LEFT JOIN companies c ON c.id = s.company_id
            ORDER BY s.created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return {"entries": [_row_out(r) for r in rows]}
