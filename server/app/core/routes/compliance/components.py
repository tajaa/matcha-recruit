"""Per-clause statute audit — the component checklist for a decomposed requirement.

Read on `shared_router` (Lite sees it read-only, same split as the rest of the
Requirements tab); write on `router` (full `compliance` only). See reqcomp01
and compliance_status.py for the underlying model.
"""
import json
from uuid import UUID

from fastapi import Depends, HTTPException, Query

from app.database import get_connection
from app.core.models.auth import CurrentUser
from app.core.models.compliance import (
    AttestComponentRequest,
    ComplianceAuditLocationRow,
    ComplianceAuditOverview,
    ComplianceAuditStatute,
    RequirementComponent,
    RequirementComponentChecklist,
    RequirementExposure,
    RequirementStatusSummary,
)
from app.core.services.compliance_risk import (
    PENALTY_JOIN_SQL,
    PENALTY_SELECT_SQL,
    _parse_penalties,
    _risk_penalty,
)
from app.core.services.compliance_service import get_location_requirements
from app.core.services.compliance_status import (
    attest_component_status,
    component_derivation,
    get_company_audit_overview,
    get_component_checklist,
)
from app.matcha.dependencies import require_admin_or_client

from ._shared import router, shared_router, resolve_company_id


async def _assert_component_requirement_visible(
    conn, *, location_id: UUID, catalog_id: UUID, company_id: UUID
):
    """404 unless this requirement is on the tenant's own Requirements tab AND
    decomposed into components. Returns the matched `RequirementResponse`.

    Returning it rather than discarding it is what lets the checklist read skip
    a second SELECT for title/statute_citation: this pipeline already fetched
    them, and the header then provably describes the same row the visibility
    pass approved.

    Runs the real `get_location_requirements` pipeline rather than a bare
    fetch-by-id: industry applicability, preemption and city-level promotion
    (`_filter_with_preemption` / `_filter_city_level_requirements`) are
    SET-RELATIVE — they decide by comparing sibling requirement rows in the
    same category group, so a query narrowed to just this one row cannot
    reproduce the same visibility answer. Skipping this check would leak
    jurisdictional content this tenant isn't deemed subject to, and would let
    attest write a status for a requirement never shown to them anywhere in
    the product.

    Also stands in for the location-ownership check: `get_location_requirements`
    already filters on `l.company_id = $2` and returns `[]` for a foreign or
    nonexistent location, so a mismatched location 404s here rather than
    getting a separate 403 (no existence disclosure either way).
    """
    visible = await get_location_requirements(location_id, company_id, conn=conn)
    match = next(
        (r for r in visible
         if r.jurisdiction_requirement_id == str(catalog_id) and r.has_components),
        None,
    )
    if match is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return match


async def _exposures_for(conn, catalog_ids: list[UUID]) -> dict[UUID, RequirementExposure]:
    """Directional exposure figures for a SET of decomposed requirements.

    Batched deliberately: the whole point of `requirement_components` is that
    the number of decomposed statutes grows, and a per-statute `await` in the
    caller's loop turns the Audit tab into K sequential round-trips on top of
    the per-location pipeline runs it already pays.

    Composes the same PENALTY_SELECT_SQL/PENALTY_JOIN_SQL fragments and the
    same pure `_risk_penalty` builder compliance_risk.py's own issue penalties
    use, so provenance rules (source_url/citation only from the bound
    authority row, `grounded` = the FK's existence) apply identically here —
    no hand-copied join to drift out of sync with that file. Penalties parse
    through `_parse_penalties` (not a bare `json.loads`) because the blob is
    model-authored by the research path: a malformed string or a non-dict
    JSON value (array/scalar/null) must degrade to "no exposure figure" for
    that one row, not 500 the whole Audit tab.
    """
    if not catalog_ids:
        return {}
    rows = await conn.fetch(
        f"""
        SELECT cat.id, {PENALTY_SELECT_SQL}
        FROM jurisdiction_requirements cat
        {PENALTY_JOIN_SQL}
        WHERE cat.id = ANY($1::uuid[])
        """,
        catalog_ids,
    )
    out: dict[UUID, RequirementExposure] = {}
    for row in rows:
        penalties = _parse_penalties(row["penalties"])
        if penalties is None:
            continue
        out[row["id"]] = RequirementExposure(
            penalty=_risk_penalty(
                penalties,
                authority_url=row["penalty_source_url"],
                authority_citation=row["penalty_citation"],
                effective_date=row["penalty_effective_date"],
            ),
            directional=True,
        )
    return out


async def _exposure_for(conn, catalog_id: UUID) -> RequirementExposure | None:
    """Single-requirement convenience wrapper over `_exposures_for`."""
    return (await _exposures_for(conn, [catalog_id])).get(catalog_id)


@shared_router.get("/audit", response_model=ComplianceAuditOverview)
async def get_compliance_audit_endpoint(
    company_id_override: str | None = Query(None, alias="company_id"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Company-wide Audit tab: every statute with a clause decomposition,
    grouped by statute then location. `shared_router` — Lite sees it
    read-only, same split as the checklist read below."""
    company_id = await resolve_company_id(current_user, company_id_override)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    async with get_connection() as conn:
        overview = await get_company_audit_overview(conn, company_id)
        exposures = await _exposures_for(
            conn, [UUID(s["jurisdiction_requirement_id"]) for s in overview["statutes"]]
        )

    return ComplianceAuditOverview(
        statutes=[
            ComplianceAuditStatute(
                jurisdiction_requirement_id=s["jurisdiction_requirement_id"],
                title=s["title"],
                statute_citation=s["statute_citation"],
                category=s["category"],
                authority_level=s["authority_level"],
                authority_name=s["authority_name"],
                component_count=s["component_count"],
                locations=[ComplianceAuditLocationRow(**loc) for loc in s["locations"]],
                summary=RequirementStatusSummary(**s["summary"]),
                exposure=exposures.get(UUID(s["jurisdiction_requirement_id"])),
            )
            for s in overview["statutes"]
        ],
        summary=RequirementStatusSummary(**overview["summary"]),
        location_count=overview["location_count"],
    )


@shared_router.get(
    "/locations/{location_id}/requirements/{catalog_id}/components",
    response_model=RequirementComponentChecklist,
)
async def get_requirement_components_endpoint(
    location_id: str,
    catalog_id: str,
    company_id_override: str | None = Query(None, alias="company_id"),
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
        header = await _assert_component_requirement_visible(
            conn, location_id=loc_uuid, catalog_id=cat_uuid, company_id=company_id,
        )
        checklist = await get_component_checklist(
            conn, company_id=company_id, location_id=loc_uuid, catalog_id=cat_uuid,
        )
        exposure = await _exposure_for(conn, cat_uuid)

    return RequirementComponentChecklist(
        jurisdiction_requirement_id=str(cat_uuid),
        location_id=str(loc_uuid),
        title=header.title,
        statute_citation=header.statute_citation,
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
    company_id_override: str | None = Query(None, alias="company_id"),
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
        # Same visibility guard as the read endpoint — see its docstring.
        # Without this a client could attest a status for a requirement never
        # shown to them on the Requirements tab (a different industry's
        # obligation, a preempted duplicate, an uncodified row).
        await _assert_component_requirement_visible(
            conn, location_id=loc_uuid, catalog_id=cat_uuid, company_id=company_id,
        )
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
        try:
            evidence = json.loads(evidence)
        except ValueError:
            evidence = None

    # Registry-resolved, not a bare `derivation_key is not None` — must agree
    # with attest_component_status's own refusal check (compliance_status.py)
    # and with get_component_checklist's read-path builder, or the attest
    # button and the server's 409 disagree the moment the catalog carries a
    # stale/dropped derivation_key.
    d = component_derivation(component["derivation_key"])

    return RequirementComponent(
        component_key=component["component_key"],
        label=component["label"],
        question=component["question"],
        statute_citation=component["statute_citation"],
        suggested_fix=component["suggested_fix"],
        severity=component["severity"],
        sort_order=component["sort_order"],
        derivable=d is not None,
        derivation_source=d.source_label if d is not None else None,
        status=component["status"] or "unknown",
        basis=component["basis"],
        evidence=evidence or {},
        attested_note=component["attested_note"],
        attested_at=component["attested_at"].isoformat() if component["attested_at"] else None,
        derived_at=component["derived_at"].isoformat() if component["derived_at"] else None,
    )
