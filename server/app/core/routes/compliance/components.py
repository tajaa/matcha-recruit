"""Per-clause statute audit — the component checklist for a decomposed requirement.

Read on `shared_router` (Lite sees it read-only, same split as the rest of the
Requirements tab); write on `router` (full `compliance` only). See reqcomp01
and compliance_status.py for the underlying model.
"""
import json
from uuid import UUID

from fastapi import Depends, HTTPException

from app.database import get_connection
from app.core.models.auth import CurrentUser
from app.core.models.compliance import (
    AttestComponentRequest,
    RequirementComponent,
    RequirementComponentChecklist,
    RequirementStatusSummary,
)
from app.core.services.compliance_service import get_location_requirements, verify_location_ownership
from app.core.services.compliance_status import (
    attest_component_status,
    get_component_checklist,
)
from app.matcha.dependencies import require_admin_or_client

from ._shared import router, shared_router, resolve_company_id


async def _load_requirement_header(conn, catalog_id: UUID):
    row = await conn.fetchrow(
        "SELECT id, title, statute_citation FROM jurisdiction_requirements WHERE id = $1",
        catalog_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return row


async def _exposure_for(conn, catalog_id: UUID, company_id: UUID) -> dict | None:
    """Directional exposure figure — reuses the exact penalty join already at
    compliance_risk.py:495 (catalog metadata + bound authority row) x active
    locations. Not a dollar model of its own; labelled directional."""
    row = await conn.fetchrow(
        """
        SELECT cat.metadata -> 'penalties' AS penalties, pai.citation AS penalty_citation,
               (SELECT count(*) FROM business_locations
                WHERE company_id = $2 AND COALESCE(is_active, true) = true) AS location_count
        FROM jurisdiction_requirements cat
        LEFT JOIN authority_index_items pai ON pai.id = cat.penalty_item_id
        WHERE cat.id = $1
        """,
        catalog_id, company_id,
    )
    if row is None or row["penalties"] is None:
        return None
    return {
        "penalties": row["penalties"],
        "penalty_citation": row["penalty_citation"],
        "location_count": row["location_count"],
        "directional": True,
    }


@shared_router.get(
    "/locations/{location_id}/requirements/{catalog_id}/components",
    response_model=RequirementComponentChecklist,
)
async def get_requirement_components_endpoint(
    location_id: str,
    catalog_id: str,
    company_id_override: str | None = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id_override)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid, cat_uuid = UUID(location_id), UUID(catalog_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id")

    async with get_connection() as conn:
        if not await verify_location_ownership(conn, loc_uuid, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

    # The component checklist must never be reachable for a requirement the
    # tenant's own Requirements tab hides — get_location_requirements already
    # runs the full visibility pipeline (industry applicability, preemption,
    # codified gate, local-ordinance filtering); a bare fetch by catalog id
    # would leak jurisdictional content this tenant isn't deemed subject to,
    # and would let attest write a status for a requirement never shown to
    # them anywhere in the product.
    visible = await get_location_requirements(loc_uuid, company_id)
    if not any(r.jurisdiction_requirement_id == str(cat_uuid) and r.has_components for r in visible):
        raise HTTPException(status_code=404, detail="Requirement not found")

    async with get_connection() as conn:
        header = await _load_requirement_header(conn, cat_uuid)
        checklist = await get_component_checklist(
            conn, company_id=company_id, location_id=loc_uuid, catalog_id=cat_uuid,
        )
        exposure = await _exposure_for(conn, cat_uuid, company_id)

    return RequirementComponentChecklist(
        jurisdiction_requirement_id=str(cat_uuid),
        location_id=str(loc_uuid),
        title=header["title"],
        statute_citation=header["statute_citation"],
        components=[RequirementComponent(**c) for c in checklist["components"]],
        summary=RequirementStatusSummary(**checklist["summary"]),
        exposure=exposure,
    )


@router.post(
    "/locations/{location_id}/requirements/{catalog_id}/components/{component_key}/attest",
    response_model=RequirementComponent,
)
async def attest_requirement_component_endpoint(
    location_id: str,
    catalog_id: str,
    component_key: str,
    payload: AttestComponentRequest,
    company_id_override: str | None = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id_override)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid, cat_uuid = UUID(location_id), UUID(catalog_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id")

    async with get_connection() as conn:
        if not await verify_location_ownership(conn, loc_uuid, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

    # Same visibility guard as the read endpoint — see its comment. Without
    # this a client could attest a status for a requirement never shown to
    # them on the Requirements tab (a different industry's obligation, a
    # preempted duplicate, an uncodified row).
    visible = await get_location_requirements(loc_uuid, company_id)
    if not any(r.jurisdiction_requirement_id == str(cat_uuid) and r.has_components for r in visible):
        raise HTTPException(status_code=404, detail="Requirement not found")

    async with get_connection() as conn:
        try:
            await attest_component_status(
                conn,
                company_id=company_id, location_id=loc_uuid, catalog_id=cat_uuid,
                component_key=component_key, status=payload.status, note=payload.note,
                actor_user_id=current_user.id,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        component = await conn.fetchrow(
            """
            SELECT rc.component_key, rc.label, rc.question, rc.statute_citation,
                   rc.suggested_fix, rc.severity, rc.sort_order, rc.derivation_key,
                   rcs.status, rcs.basis, rcs.evidence, rcs.attested_note, rcs.attested_at,
                   rcs.derived_at
            FROM requirement_components rc
            LEFT JOIN requirement_compliance_status rcs
              ON rcs.location_id = $2 AND rcs.jurisdiction_requirement_id = $1
             AND rcs.component_key = rc.component_key
            WHERE rc.jurisdiction_requirement_id = $1 AND rc.component_key = $3
            """,
            cat_uuid, loc_uuid, component_key,
        )

    evidence = component["evidence"]
    if isinstance(evidence, str):
        evidence = json.loads(evidence)

    return RequirementComponent(
        component_key=component["component_key"],
        label=component["label"],
        question=component["question"],
        statute_citation=component["statute_citation"],
        suggested_fix=component["suggested_fix"],
        severity=component["severity"],
        sort_order=component["sort_order"],
        derivable=component["derivation_key"] is not None,
        status=component["status"] or "unknown",
        basis=component["basis"],
        evidence=evidence or {},
        attested_note=component["attested_note"],
        attested_at=component["attested_at"].isoformat() if component["attested_at"] else None,
        derived_at=component["derived_at"].isoformat() if component["derived_at"] else None,
    )
