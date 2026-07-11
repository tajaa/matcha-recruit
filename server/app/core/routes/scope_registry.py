"""Scope-registry admin API — authority indexes, classification, resolution.

Mounted at ``/admin/scope-registry`` (see ``core/routes/__init__.py``), all
endpoints admin-gated. The service layer lives in
``app/core/services/scope_registry/``; this file is routing + shapes only.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import require_admin
from ..models.scope_registry import (
    AcknowledgeDriftRequest,
    ClassificationProposal,
    ConfirmClassificationsRequest,
    DispatchResponse,
    FetchQueueResearchRequest,
    ReconcileRequest,
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


@router.get("/drift", dependencies=[Depends(require_admin)])
async def list_authority_drift(
    slug: Optional[str] = None,
    change_type: Optional[Literal["new", "amended", "removed"]] = None,
    status: Optional[Literal["open", "acknowledged"]] = None,
    limit: int = 100,
):
    """Recorded authority drift — new/amended/removed citations detected on
    re-ingest. This is the "a federal law changed or was added" review queue.

    Filter by ``slug`` (one index), ``change_type``, and/or ``status``
    ('open' = awaiting review); newest first. ``open_count`` always reflects
    the whole queue regardless of filters, so the UI can badge it.
    """
    limit = max(1, min(limit, 500))
    where = ["1=1"]
    params: list = []
    if slug:
        params.append(slug)
        where.append(f"ai.slug = ${len(params)}")
    if change_type:
        params.append(change_type)
        where.append(f"d.change_type = ${len(params)}")
    if status:
        params.append(status)
        where.append(f"d.status = ${len(params)}")
    params.append(limit)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT d.id, d.authority_index_id, ai.slug AS index_slug,
                   ai.name AS index_name, d.change_type, d.citation, d.heading,
                   d.old_amendment_date, d.new_amendment_date, d.detected_at,
                   d.status, d.acknowledged_by, d.acknowledged_at,
                   COALESCE(aff.n, 0) AS affected_requirements
            FROM authority_index_drift d
            JOIN authority_indexes ai ON ai.id = d.authority_index_id
            LEFT JOIN LATERAL (
                SELECT COUNT(DISTINCT sc.jurisdiction_requirement_id) AS n
                FROM authority_index_items i
                JOIN authority_item_classifications c ON c.item_id = i.id
                JOIN scope_codifications sc ON sc.classification_id = c.id
                WHERE i.authority_index_id = d.authority_index_id
                  AND i.citation = d.citation
            ) aff ON TRUE
            WHERE {' AND '.join(where)}
            ORDER BY d.detected_at DESC, d.change_type
            LIMIT ${len(params)}
            """,
            *params,
        )
        open_count = await conn.fetchval(
            "SELECT COUNT(*) FROM authority_index_drift WHERE status = 'open'"
        )
    return {"drift": [dict(r) for r in rows], "open_count": int(open_count or 0)}


@router.post("/drift/acknowledge", dependencies=[Depends(require_admin)])
async def acknowledge_drift(
    payload: AcknowledgeDriftRequest,
    current_user=Depends(require_admin),
):
    """Mark drift rows reviewed. Rows are kept (audit trail; the ingest
    removed-dedupe reads latest change_type regardless of status) — they just
    leave the open queue. Idempotent: already-acknowledged ids are skipped.
    """
    async with get_connection() as conn:
        acknowledged = await conn.fetchval(
            """
            WITH updated AS (
                UPDATE authority_index_drift
                SET status = 'acknowledged',
                    acknowledged_by = $2,
                    acknowledged_at = NOW()
                WHERE id = ANY($1::uuid[]) AND status = 'open'
                RETURNING 1
            )
            SELECT COUNT(*) FROM updated
            """,
            payload.ids,
            current_user.id,
        )
        open_count = await conn.fetchval(
            "SELECT COUNT(*) FROM authority_index_drift WHERE status = 'open'"
        )
    return {
        "acknowledged": int(acknowledged or 0),
        "skipped": len(payload.ids) - int(acknowledged or 0),
        "open_count": int(open_count or 0),
    }


@router.post("/authority/{slug}/fetch-bodies", dependencies=[Depends(require_admin)])
async def trigger_fetch_bodies(slug: str, current_user=Depends(require_admin)) -> DispatchResponse:
    """Fetch full statute/regulation text for one index's items (Celery)."""
    from app.core.services.scope_registry.authority_sources import all_index_slugs
    if slug not in all_index_slugs():
        raise HTTPException(status_code=404, detail=f"Unknown authority index: {slug}")
    from app.workers.tasks.scope_registry import fetch_authority_bodies
    fetch_authority_bodies.delay(index_slug=slug, triggered_by=str(current_user.id))
    return DispatchResponse(status="running", dispatched_to="celery", slug=slug)


@router.get("/items/{item_id}/body", dependencies=[Depends(require_admin)])
async def get_item_body(item_id: UUID):
    """The full statute/regulation text for one authority item (statute reader)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT i.id, i.citation, i.heading, i.source_url,
                   i.body_text, i.body_source_url, i.body_fetched_at,
                   ai.name AS index_name, ai.slug AS index_slug
            FROM authority_index_items i
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            WHERE i.id = $1
            """,
            item_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown authority item")
    return dict(row)


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


@router.post("/reconcile", dependencies=[Depends(require_admin)])
async def reconcile_endpoint(payload: Optional[ReconcileRequest] = None):
    """Persist the scope↔store codify linkage (scope_codifications) by matching
    confirmed keyed classifications against keyed catalog rows. No state =
    registry-wide backfill; a state narrows to that jurisdiction chain."""
    from app.core.services.scope_registry.codify import reconcile_codifications
    payload = payload or ReconcileRequest()
    async with get_connection() as conn:
        return await reconcile_codifications(
            conn, state=payload.state, city=payload.city,
            source="backfill" if not payload.state else "reconcile",
        )


@router.post("/fetch-queue/research", dependencies=[Depends(require_admin)])
async def fetch_queue_research(payload: FetchQueueResearchRequest):
    """Drive the chain's fetch queue into research, then reconcile — the wire that
    closes scope→fetch→store. SSE, emitting the same event types Scope Studio's
    research loop parses (status/researching/jurisdiction_complete/completed/error)."""
    import json as _json
    from fastapi.responses import StreamingResponse

    from app.core.services.scope_registry.codify import (
        chain_uncodified, group_research_units, reconcile_codifications,
    )
    from app.core.services.scope_registry.body_fetch import fetch_bodies_for_index
    from app.core.services.scope_registry.grounded import build_grounded_corpus
    from app.core.services.compliance_service import research_specialization_for_jurisdiction

    state, city = payload.state, payload.city

    def _sse(event: dict) -> str:
        return f"data: {_json.dumps(event)}\n\n"

    async def _corpus_for_unit(conn, unit) -> tuple:
        """Fetch the unit items' statute bodies and render the grounded corpus."""
        item_ids = [it["item_id"] for it in unit["items"] if it.get("item_id")]
        if not item_ids:
            return "", {}
        rows = await conn.fetch(
            "SELECT id AS item_id, citation, heading, body_text "
            "FROM authority_index_items WHERE id = ANY($1::uuid[])",
            item_ids,
        )
        return build_grounded_corpus([dict(r) for r in rows])

    async def stream():
      try:
        async with get_connection() as conn:
            work = await chain_uncodified(conn, state=state, city=city)
            units = group_research_units(
                work["keyed"],
                federal_id=work["chain"]["federal_id"],
                state_id=work["chain"]["state_id"],
                city_id=work["chain"]["city_id"],
            )

            # Grounding pre-flight: fetch official statute text for any worklist
            # index whose items don't have bodies yet, so research can extract
            # values from the source instead of model recall. Best-effort — a
            # fetch failure just falls back to ungrounded research for that unit.
            bodyless_slugs = sorted({
                it["index_slug"] for u in units for it in u["items"]
                if it.get("index_slug") and not it.get("has_body")
            })
            fetched = 0
            for slug in bodyless_slugs:
                try:
                    res = await fetch_bodies_for_index(conn, slug)
                    fetched += (res or {}).get("fetched", 0) if isinstance(res, dict) else 0
                except Exception as exc:
                    logger.warning("body prefetch failed for %s: %s", slug, exc)
            if bodyless_slugs:
                yield _sse({"type": "status",
                            "message": f"Fetched statute text for {fetched} item(s) "
                                       f"across {len(bodyless_slugs)} index(es)",
                            "bodies_fetched": fetched})

            yield _sse({"type": "status",
                        "message": f"{len(units)} research unit(s) · "
                                   f"{len(work['keyed'])} keyed · {len(work['unkeyed'])} unkeyed",
                        "units": len(units), "unkeyed": len(work["unkeyed"])})

            if not units:
                yield _sse({"type": "completed",
                            "summary": {"total_requirements": 0},
                            "unkeyed": len(work["unkeyed"]),
                            "message": "Nothing researchable — unkeyed items need a "
                                       "regulation key (mint in RKD, then set the classification)."})
                return

            total_new = 0
            for idx, unit in enumerate(units, start=1):
                label = await conn.fetchval(
                    "SELECT COALESCE(display_name, CONCAT_WS(', ', city, state)) "
                    "FROM jurisdictions WHERE id = $1", unit["jurisdiction_id"],
                ) or "jurisdiction"
                yield _sse({"type": "researching", "jurisdiction": label,
                            "progress": idx, "total": len(units)})
                try:
                    corpus, citation_index = await _corpus_for_unit(conn, unit)
                    res = await research_specialization_for_jurisdiction(
                        conn, unit["jurisdiction_id"], unit["categories"],
                        industry_tag="", industry_context=unit["context"],
                        skip_existing=False,
                        grounded_corpus=corpus, citation_index=citation_index,
                    )
                    total_new += res.get("new", 0)
                    yield _sse({"type": "jurisdiction_complete", "jurisdiction": label,
                                "new": res.get("new", 0), "failed": res.get("failed", []),
                                "grounded": bool(corpus)})
                except Exception as exc:  # a unit failing must not kill the stream
                    logger.warning("fetch-queue research failed for %s: %s", label, exc)
                    yield _sse({"type": "jurisdiction_complete", "jurisdiction": label,
                                "new": 0, "error": str(exc)})

            recon = await reconcile_codifications(
                conn, state=state, city=city, source="research_run",
                run_info={"endpoint": "fetch-queue/research",
                          "units": len(units), "new_requirements": total_new},
            )
            after = await chain_uncodified(conn, state=state, city=city)
            yield _sse({"type": "completed",
                        "summary": {"total_requirements": total_new},
                        "linked": recon["inserted"] + recon["updated"],
                        "still_uncodified": len(after["keyed"]),
                        "unkeyed": len(after["unkeyed"])})
      except Exception as exc:  # never leave the stream hanging with no terminal event
        logger.warning("fetch-queue research stream failed: %s", exc)
        yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(stream(), media_type="text/event-stream")


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
