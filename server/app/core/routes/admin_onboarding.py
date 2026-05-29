"""Master-admin onboarding wizard endpoints.

Mounted at ``/admin/onboarding`` (see ``core/routes/__init__.py``).
Gated by ``require_master_admin`` (= ``require_admin`` until the column
lands — see TODO below).

The wizard's lifecycle is encoded in ``onboarding_sessions.step``:
basics → size → locations → scope → gaps → review → done. Session rows
are resumable: a refresh hits ``GET /sessions/{id}`` and the UI
re-renders at the persisted ``step``.

Wire of routes to plan deliverables:

* ``POST   /admin/onboarding/sessions``                    — create / idempotent claim
* ``GET    /admin/onboarding/sessions``                    — list (compact rows)
* ``GET    /admin/onboarding/sessions/{id}``               — full detail
* ``PATCH  /admin/onboarding/sessions/{id}``               — save Step 1-3 data
* ``POST   /admin/onboarding/sessions/{id}/create-company`` — provisions companies + locations at end of Step 3
* ``POST   /admin/onboarding/sessions/{id}/expand``        — Gemini scope expansion
* ``POST   /admin/onboarding/sessions/{id}/resolve``       — bank reconciliation
* ``POST   /admin/onboarding/sessions/{id}/dispatch-research`` — gated by admin checkboxes
* ``POST   /admin/onboarding/sessions/{id}/finalize``      — issue invite + write scope rows
* ``POST   /admin/onboarding/sessions/{id}/abandon``       — soft close
"""

import asyncio
import json
import logging
import secrets
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.models.auth import CurrentUser
from app.core.models.admin_onboarding import (
    AIScope,
    CreateCompanyResponse,
    CreateSessionRequest,
    DispatchResearchRequest,
    DispatchResearchResponse,
    EnrichRosterResponse,
    ExpandScopeResponse,
    ResearchGapsRequest,
    FinalizeResponse,
    GapAnalysisDossier,
    GapCheckResponse,
    GapCheckResult,
    OnboardingSessionDetail,
    OnboardingSessionSummary,
    PatchSessionRequest,
    ResolveScopeResponse,
    ResolvedScope,
)
from app.core.services.onboarding_dossier import (
    build_gap_analysis_dossier,
    _dossier_to_html,
    _dossier_to_markdown,
)
from app.core.services.onboarding_scope_ai import (
    INDUSTRY_SPECIALTIES,
    build_missing_id,
    expand_scope as ai_expand_scope,
    gap_check as ai_gap_check,
    map_to_bank,
)
from app.core.services.compliance_service import (
    ensure_location_for_employee,
    run_compliance_check_stream,
    admin_add_requirements_to_location_batch,
    _refresh_repository_missing_categories,
    _get_or_create_jurisdiction,
    _lookup_has_local_ordinance,
    _load_jurisdiction_requirements,
    _jurisdiction_row_to_dict,
    _heartbeat_while,
)
from app.core.services.gemini_compliance import get_gemini_compliance_service

logger = logging.getLogger(__name__)

router = APIRouter()


# TODO: replace with a real ``is_master_admin`` check once that column
# exists on the users table. The wizard is admin-only by design — the
# regular admin role is fine for now, but the plan calls for tighter
# gating (e.g. a "master_admin" boolean) before we open this surface
# more widely.
require_master_admin = require_admin


# ── Helpers ─────────────────────────────────────────────────────────────


def _safe_jsonb(value: Any, default: Any) -> Any:
    """asyncpg returns JSONB as raw str when no codec is registered.

    Centralizes the str-vs-dict guard so handlers can treat session.basics
    et al. as plain Python structures.
    """
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _row_to_summary(row) -> OnboardingSessionSummary:
    basics = _safe_jsonb(row["basics"], {})
    return OnboardingSessionSummary(
        id=row["id"],
        schema_version=row["schema_version"],
        step=row["step"],
        status=row["status"],
        business_name=basics.get("business_name"),
        industry=basics.get("industry"),
        company_id=row["company_id"],
        owner_email=row["owner_email"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_detail(row) -> OnboardingSessionDetail:
    return OnboardingSessionDetail(
        id=row["id"],
        schema_version=row["schema_version"],
        step=row["step"],
        status=row["status"],
        created_by=row["created_by"],
        company_id=row["company_id"],
        owner_email=row["owner_email"],
        owner_user_id=row["owner_user_id"],
        invite_token=row["invite_token"],
        idempotency_key=row["idempotency_key"],
        basics=_safe_jsonb(row["basics"], {}),
        size=_safe_jsonb(row["size"], {}),
        locations=_safe_jsonb(row["locations"], []),
        ai_scope=_safe_jsonb(row["ai_scope"], None) if row["ai_scope"] else None,
        resolved_scope=_safe_jsonb(row["resolved_scope"], None) if row["resolved_scope"] else None,
        # row.get tolerates a pre-migration DB (column absent) — degrades to None.
        gap_analysis=_safe_jsonb(row.get("gap_analysis"), None) if row.get("gap_analysis") else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _load_session_or_404(conn, session_id: UUID):
    row = await conn.fetchrow(
        "SELECT * FROM onboarding_sessions WHERE id = $1",
        session_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    return row


def _dossier_from_row(row) -> dict:
    """Assemble the gap-analysis dossier for a session row.

    Returns the frozen ``gap_analysis`` snapshot if finalize wrote one;
    otherwise assembles live from the current JSONB columns so an
    in-progress session is still reviewable. JSONB is parsed via
    ``_safe_jsonb`` first — the assembler takes pre-parsed dicts.
    """
    snapshot = _safe_jsonb(row.get("gap_analysis"), None) if row.get("gap_analysis") else None
    if snapshot:
        return snapshot
    return build_gap_analysis_dossier({
        "id": row["id"],
        "status": row["status"],
        "basics": _safe_jsonb(row["basics"], {}),
        "size": _safe_jsonb(row["size"], {}),
        "locations": _safe_jsonb(row["locations"], []),
        "ai_scope": _safe_jsonb(row["ai_scope"], {}),
        "resolved_scope": _safe_jsonb(row["resolved_scope"], {}),
    })


async def _ensure_company_wide_location(conn, company_id: UUID) -> UUID:
    """Return the company-wide sentinel location id, creating it if missing.

    Federal-scope requirements attach here. The sentinel is normally created at
    create-company; older companies (or roster-enriched ones) may predate it, so
    we create on demand rather than silently dropping federal scope.
    """
    sentinel = await conn.fetchrow(
        "SELECT id FROM business_locations WHERE company_id = $1 AND is_company_wide = TRUE LIMIT 1",
        company_id,
    )
    if sentinel:
        return sentinel["id"]
    return await conn.fetchval(
        """
        INSERT INTO business_locations (
            company_id, name, address, city, state, county, zipcode, is_active, is_company_wide
        )
        VALUES ($1, 'Company-wide', NULL, NULL, NULL, NULL, NULL, TRUE, TRUE)
        RETURNING id
        """,
        company_id,
    )


async def _write_compliance_scope_rows(
    conn,
    *,
    company_id: UUID,
    existing_items: list[dict],
    admin_user_id: UUID,
    source: str,
) -> int:
    """Project resolved 'existing' bank requirements into the live per-company
    store (``compliance_requirements``) — the single source of truth every
    compliance surface reads (customer /app/compliance, /admin/compliance-mgmt,
    dashboard, brokers).

    Federal scope → the company-wide sentinel; state/county/city → first matching
    real location (multi-location attach is Phase 2). Idempotent via the
    ``(location_id, jurisdiction_requirement_id)`` partial unique index — re-runs
    skip rows already linked. Shared by ``finalize`` (source='onboarding_wizard')
    and the employee-sync enrichment (source='employee_sync'); ``source`` becomes
    the row's ``governance_source``. ``admin_user_id`` is accepted for call-site
    symmetry (compliance_requirements has no reviewer column). Returns rows newly
    written.
    """
    if not existing_items:
        return 0

    needs_federal = any(
        (item.get("scope_level") or "federal").lower() == "federal"
        for item in existing_items
    )
    if needs_federal:
        sentinel_id = await _ensure_company_wide_location(conn, company_id)
    else:
        sentinel = await conn.fetchrow(
            "SELECT id FROM business_locations WHERE company_id = $1 AND is_company_wide = TRUE LIMIT 1",
            company_id,
        )
        sentinel_id = sentinel["id"] if sentinel else None

    real_locs = await conn.fetch(
        """
        SELECT id, state, county, city FROM business_locations
        WHERE company_id = $1 AND is_company_wide = FALSE AND is_active = TRUE
        """,
        company_id,
    )

    # Resolve each scope item to a target location, grouping catalog requirement
    # ids so the batch projector runs once per location.
    by_location: dict = {}
    for item in existing_items:
        req_id = item.get("requirement_id")
        if not req_id:
            continue
        scope_level = (item.get("scope_level") or "federal").lower()
        target_location_id = sentinel_id
        if scope_level != "federal" and real_locs:
            want_state = (item.get("state") or "").upper()
            want_county = (item.get("county") or "").lower()
            want_city = (item.get("city") or "").lower()
            best = None
            for loc in real_locs:
                if want_state and (loc["state"] or "").upper() != want_state:
                    continue
                if want_county and (loc["county"] or "").lower() != want_county:
                    continue
                if want_city and (loc["city"] or "").lower() != want_city:
                    continue
                best = loc
                break
            target_location_id = best["id"] if best else (real_locs[0]["id"] if real_locs else sentinel_id)
        if target_location_id is None:
            logger.warning(
                "no location to attach scope item %s (company %s)", req_id, company_id
            )
            continue
        by_location.setdefault(target_location_id, []).append(req_id)

    written = 0
    for location_id, jr_ids in by_location.items():
        try:
            res = await admin_add_requirements_to_location_batch(
                conn, location_id, company_id, jr_ids, governance_source=source,
            )
            written += res["written"]
        except Exception as exc:
            logger.warning(
                "scope projection failed for location %s: %s", location_id, exc
            )
    return written


# ── Catalog endpoint ────────────────────────────────────────────────────


@router.get("/onboarding/specialties")
async def get_industry_specialties(
    _user: CurrentUser = Depends(require_master_admin),
):
    """Industry → specialty dropdown feed for Step 1 typeahead."""
    return INDUSTRY_SPECIALTIES


# ── Session CRUD ────────────────────────────────────────────────────────


@router.post("/onboarding/sessions", response_model=OnboardingSessionDetail)
async def create_session(
    body: CreateSessionRequest,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Create or idempotently re-claim an onboarding session.

    A unique ``idempotency_key`` is required so a double-click on "New
    Onboarding" returns the same row instead of spawning duplicates.
    """
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM onboarding_sessions WHERE idempotency_key = $1",
            body.idempotency_key,
        )
        if existing:
            return _row_to_detail(existing)

        row = await conn.fetchrow(
            """
            INSERT INTO onboarding_sessions (
                created_by, idempotency_key, step, status,
                basics, size, locations
            )
            VALUES ($1, $2, 'basics', 'in_progress',
                    '{}'::jsonb, '{}'::jsonb, '[]'::jsonb)
            RETURNING *
            """,
            current_user.id, body.idempotency_key,
        )
    return _row_to_detail(row)


@router.get("/onboarding/sessions", response_model=list[OnboardingSessionSummary])
async def list_sessions(
    current_user: CurrentUser = Depends(require_master_admin),
    status_filter: Optional[str] = None,
    limit: int = 50,
):
    """List onboarding sessions visible to the current admin.

    Admins see only sessions they created. status_filter narrows the list.
    """
    limit = max(1, min(limit, 200))
    async with get_connection() as conn:
        if status_filter:
            rows = await conn.fetch(
                """
                SELECT * FROM onboarding_sessions
                WHERE created_by = $1 AND status = $2
                ORDER BY updated_at DESC
                LIMIT $3
                """,
                current_user.id, status_filter, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM onboarding_sessions
                WHERE created_by = $1
                ORDER BY updated_at DESC
                LIMIT $2
                """,
                current_user.id, limit,
            )
    return [_row_to_summary(r) for r in rows]


@router.get("/onboarding/sessions/{session_id}", response_model=OnboardingSessionDetail)
async def get_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    async with get_connection() as conn:
        row = await _load_session_or_404(conn, session_id)
        if row["created_by"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not your onboarding session")
    return _row_to_detail(row)


@router.patch("/onboarding/sessions/{session_id}", response_model=OnboardingSessionDetail)
async def patch_session(
    session_id: UUID,
    body: PatchSessionRequest,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Save Step 1-3 data into the session row.

    Each step's payload lives in its own JSONB column. ``step`` advances
    the wizard cursor; omit to save without moving (e.g. autosave).
    """
    async with get_connection() as conn:
        row = await _load_session_or_404(conn, session_id)
        if row["created_by"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not your onboarding session")
        if row["status"] != "in_progress":
            raise HTTPException(
                status_code=400,
                detail=f"Session is {row['status']} — cannot edit.",
            )

        sets: list[str] = ["updated_at = NOW()"]
        params: list[Any] = []
        idx = 1

        if body.basics is not None:
            sets.append(f"basics = ${idx}::jsonb")
            params.append(json.dumps(body.basics.model_dump()))
            idx += 1
            # owner_email is also persisted to the column for fast lookup.
            sets.append(f"owner_email = ${idx}")
            params.append(body.basics.owner_email)
            idx += 1
        if body.size is not None:
            sets.append(f"size = ${idx}::jsonb")
            params.append(json.dumps(body.size.model_dump()))
            idx += 1
        if body.locations is not None:
            sets.append(f"locations = ${idx}::jsonb")
            params.append(json.dumps([loc.model_dump() for loc in body.locations.locations]))
            idx += 1
        if body.step is not None:
            sets.append(f"step = ${idx}")
            params.append(body.step)
            idx += 1

        if len(sets) == 1:
            # No-op save.
            return _row_to_detail(row)

        params.append(session_id)
        await conn.execute(
            f"UPDATE onboarding_sessions SET {', '.join(sets)} WHERE id = ${idx}",
            *params,
        )
        row = await _load_session_or_404(conn, session_id)
    return _row_to_detail(row)


# ── Company provisioning (end of Step 3) ────────────────────────────────


@router.post(
    "/onboarding/sessions/{session_id}/create-company",
    response_model=CreateCompanyResponse,
)
async def create_company(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Provision the companies + business_locations rows at end of Step 3.

    Firing here (rather than at finalize) means the gap-research workers
    in Step 5 can pass a real company_id + location_id. Resolves the v1
    "dispatch-research has no company_id" race.
    """
    async with get_connection() as conn:
        row = await _load_session_or_404(conn, session_id)
        if row["created_by"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not your onboarding session")

        basics = _safe_jsonb(row["basics"], {})
        if not basics.get("business_name"):
            raise HTTPException(status_code=400, detail="Step 1 must be saved before creating the company.")

        locations = _safe_jsonb(row["locations"], [])
        # Locations can be empty (federal-only business). The company-wide
        # sentinel still gets created.

        # If the session already has a company_id, this call is idempotent.
        if row["company_id"]:
            sentinel = await conn.fetchrow(
                """
                SELECT id FROM business_locations
                WHERE company_id = $1 AND is_company_wide = TRUE
                LIMIT 1
                """,
                row["company_id"],
            )
            if sentinel is None:
                raise HTTPException(
                    status_code=500,
                    detail="Session has company_id but no company-wide sentinel location",
                )
            return CreateCompanyResponse(
                session_id=session_id,
                company_id=row["company_id"],
                company_wide_location_id=sentinel["id"],
            )

        # Provision new company. companies table has only created_at —
        # no updated_at column (verified in app/database.py:764).
        company_row = await conn.fetchrow(
            """
            INSERT INTO companies (name, signup_source, status, approved_at, approved_by, created_at)
            VALUES ($1, 'admin_onboarding_wizard', 'approved', NOW(), $2, NOW())
            RETURNING id
            """,
            basics["business_name"], current_user.id,
        )
        company_id = company_row["id"]

        # Company-wide sentinel location for federal-only requirements.
        sentinel_row = await conn.fetchrow(
            """
            INSERT INTO business_locations (
                company_id, name, address, city, state, county, zipcode, is_active, is_company_wide
            )
            VALUES ($1, 'Company-wide', NULL, NULL, NULL, NULL, NULL, TRUE, TRUE)
            RETURNING id
            """,
            company_id,
        )
        sentinel_id = sentinel_row["id"]

        # One business_locations row per location supplied in Step 3.
        for loc in locations:
            await conn.execute(
                """
                INSERT INTO business_locations (
                    company_id, name, address, city, state, county, zipcode,
                    is_active, is_company_wide
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE, FALSE)
                """,
                company_id,
                loc.get("name"),
                loc.get("address"),
                loc.get("city"),
                (loc.get("state") or "").upper() or None,
                loc.get("county"),
                loc.get("zipcode"),
            )

        await conn.execute(
            """
            UPDATE onboarding_sessions
            SET company_id = $1, updated_at = NOW()
            WHERE id = $2
            """,
            company_id, session_id,
        )
    return CreateCompanyResponse(
        session_id=session_id,
        company_id=company_id,
        company_wide_location_id=sentinel_id,
    )


# ── Employee-sync enrichment (existing company) ─────────────────────────


async def _collect_roster(conn, company_id: UUID) -> tuple[list[str], dict, set]:
    """Distinct active-employee work locations + roles for a company.

    Returns (roles, emp_locs, existing_location_keys) where emp_locs is keyed
    by (lower_city, upper_state) → (display_city, upper_state), and
    existing_location_keys are the same keys already tracked as
    business_locations (so callers know which jurisdictions are NEW).
    """
    emp_rows = await conn.fetch(
        """
        SELECT DISTINCT work_city, work_state, job_title
        FROM employees
        WHERE org_id = $1 AND termination_date IS NULL AND work_state IS NOT NULL
        """,
        company_id,
    )
    roles = sorted({
        r["job_title"].strip()
        for r in emp_rows
        if r["job_title"] and r["job_title"].strip()
    })
    emp_locs: dict[tuple[str, str], tuple[str, str]] = {}
    for r in emp_rows:
        state = (r["work_state"] or "").upper().strip()
        if not state:
            continue
        city = (r["work_city"] or "").strip()
        emp_locs.setdefault((city.lower(), state), (city, state))

    existing_loc_rows = await conn.fetch(
        """
        SELECT city, state FROM business_locations
        WHERE company_id = $1 AND is_active = TRUE AND is_company_wide = FALSE
        """,
        company_id,
    )
    existing_keys = {
        ((r["city"] or "").lower(), (r["state"] or "").upper())
        for r in existing_loc_rows
    }
    return roles, emp_locs, existing_keys


# Company columns the enrichment loads to ground the scope analysis.
_COMPANY_PROFILE_COLS = (
    "id, name, industry, healthcare_specialties, size, company_values, "
    "benefits_summary, pto_policy_summary, compensation_notes, ir_guidance_blurb, "
    "ai_guidance_notes, work_arrangement, default_employment_type, "
    "headquarters_city, headquarters_state"
)


def _build_enrichment_basics(company) -> dict:
    """Assemble the scope-engine `basics` from the full company profile.

    `companies` has no dedicated `description` column, so synthesize one from the
    profile fields that exist — this is the richest grounding signal `expand_scope`
    has (it reads `description` + `specialty`). All specialties are folded into the
    description so the single `specialty` field isn't lossy.
    """
    specialties = [s for s in (company["healthcare_specialties"] or []) if s]
    parts: list[str] = []
    if specialties:
        parts.append(f"Specialties: {', '.join(specialties)}.")
    if company["work_arrangement"]:
        parts.append(f"Work arrangement: {company['work_arrangement']}.")
    if company["default_employment_type"]:
        parts.append(f"Default employment type: {company['default_employment_type']}.")
    hq = ", ".join(x for x in [company["headquarters_city"], company["headquarters_state"]] if x)
    if hq:
        parts.append(f"Headquarters: {hq}.")
    for label, key in (
        ("Company values", "company_values"),
        ("Benefits", "benefits_summary"),
        ("PTO policy", "pto_policy_summary"),
        ("Compensation", "compensation_notes"),
        ("IR guidance", "ir_guidance_blurb"),
        ("Notes", "ai_guidance_notes"),
    ):
        val = (company[key] or "").strip()
        if val:
            parts.append(f"{label}: {val}")
    return {
        "business_name": company["name"],
        "industry": company["industry"] or "general",
        "specialty": specialties[0] if specialties else None,
        "description": " ".join(parts).strip() or None,
    }


async def _enrich_scope_and_persist(
    conn, *, company, roles: list[str], admin_user_id: UUID,
) -> dict:
    """Role-aware scope expansion → bank reconciliation → project resolved
    'existing' scope into compliance_requirements (the live store) → upsert the
    per-company enrichment session.

    Assumes any new locations have already been filled into business_locations.
    Returns {session_id, resolved (ResolvedScope), ai_scope (AIScope),
    scope_written (int)}. Raises HTTPException(502) if expansion fails.
    """
    company_id = company["id"]
    basics = _build_enrichment_basics(company)
    all_loc_rows = await conn.fetch(
        """
        SELECT name, address, city, state, county, zipcode, facility_attributes
        FROM business_locations
        WHERE company_id = $1 AND is_active = TRUE AND is_company_wide = FALSE
        """,
        company_id,
    )
    locations = [
        {
            "name": r["name"], "address": r["address"], "city": r["city"],
            "state": r["state"], "county": r["county"], "zipcode": r["zipcode"],
            # Real facility attributes (entity_type, payer_contracts) sharpen
            # expand_scope + trigger-based category expansion.
            "facility_attributes": _safe_jsonb(r["facility_attributes"], {}),
        }
        for r in all_loc_rows
    ]

    try:
        ai_scope_raw = await ai_expand_scope(
            basics=basics, locations=locations, conn=conn, employee_roles=roles,
        )
    except Exception as exc:
        logger.exception("enrich: expand_scope failed for company %s", company_id)
        raise HTTPException(status_code=502, detail=f"Scope expansion failed: {exc}")
    try:
        ai_scope = AIScope.model_validate(ai_scope_raw)
    except Exception:
        ai_scope = AIScope()
    resolved_raw = await map_to_bank(ai_scope.model_dump(), conn)
    try:
        resolved = ResolvedScope.model_validate(resolved_raw)
    except Exception:
        resolved = ResolvedScope()

    # Final safety-net gap check (role-aware) → surfaced as fill prompts. Persisted
    # under resolved_scope.gap_check (same slot the wizard's Step-6 uses).
    gap_check_dict: dict = {}
    try:
        gap_raw = await ai_gap_check(
            basics=basics, locations=locations, ai_scope=ai_scope.model_dump(),
            resolved_scope=resolved.model_dump(mode="json"), conn=conn,
            employee_roles=roles,
        )
        gap_check_dict = GapCheckResult.model_validate(gap_raw).model_dump()
    except Exception:
        logger.exception("enrich: gap_check failed for company %s", company_id)

    scope_written = await _write_compliance_scope_rows(
        conn,
        company_id=company_id,
        existing_items=resolved.model_dump(mode="json").get("existing") or [],
        admin_user_id=admin_user_id,
        source="employee_sync",
    )

    # Per-company enrichment session (idempotent) so the gap-analysis UI can
    # show the result + dispatch research on the remaining missing items.
    idem = f"enrich-{company_id}"
    basics_blob = json.dumps({**basics, "enrichment_run": True})
    locations_blob = json.dumps(locations)
    ai_blob = json.dumps(ai_scope.model_dump())
    # Persist gap_check alongside resolved_scope so the UI surfaces fill prompts.
    resolved_persist = resolved.model_dump(mode="json")
    if gap_check_dict:
        resolved_persist["gap_check"] = gap_check_dict
    resolved_blob = json.dumps(resolved_persist)
    existing_session = await conn.fetchrow(
        "SELECT id FROM onboarding_sessions WHERE idempotency_key = $1", idem,
    )
    if existing_session:
        session_id = existing_session["id"]
        await conn.execute(
            """
            UPDATE onboarding_sessions
            SET created_by = $1, company_id = $2, basics = $3::jsonb,
                locations = $4::jsonb, ai_scope = $5::jsonb,
                resolved_scope = $6::jsonb, step = 'gaps',
                status = 'in_progress', updated_at = NOW()
            WHERE id = $7
            """,
            admin_user_id, company_id, basics_blob, locations_blob,
            ai_blob, resolved_blob, session_id,
        )
    else:
        session_id = await conn.fetchval(
            """
            INSERT INTO onboarding_sessions (
                created_by, company_id, idempotency_key, step, status,
                basics, size, locations, ai_scope, resolved_scope
            )
            VALUES ($1, $2, $3, 'gaps', 'in_progress',
                    $4::jsonb, '{}'::jsonb, $5::jsonb, $6::jsonb, $7::jsonb)
            RETURNING id
            """,
            admin_user_id, company_id, idem,
            basics_blob, locations_blob, ai_blob, resolved_blob,
        )

    # Existing coverage (for display) — live per-company requirements this
    # company already tracks (the single source of truth all surfaces read).
    covered_existing = await conn.fetchval(
        """
        SELECT COUNT(*) FROM compliance_requirements cr
        JOIN business_locations bl ON cr.location_id = bl.id
        WHERE bl.company_id = $1
        """,
        company_id,
    )

    return {
        "session_id": session_id,
        "resolved": resolved,
        "ai_scope": ai_scope,
        "scope_written": scope_written,
        "gap_check": gap_check_dict,
        "existing_scope_count": covered_existing or 0,
    }


@router.post("/onboarding/enrich/{company_id}", response_model=EnrichRosterResponse)
async def enrich_company_from_roster(
    company_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Employee-sync gap analysis for an EXISTING company (non-streaming).

    Reads the live roster, FILLS new work jurisdictions into business_locations
    (→ weekly cadence) via ``ensure_location_for_employee``, then re-runs the
    role-aware scope engine to BOLSTER/FILL the company's compliance scope.
    Idempotent + additive. The streaming variant (``/enrich/{id}/stream``)
    drives the performative demo; this one returns the summary in one shot.
    """
    async with get_connection() as conn:
        company = await conn.fetchrow(
            f"SELECT {_COMPANY_PROFILE_COLS} FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        roles, emp_locs, existing_keys = await _collect_roster(conn, company_id)

        new_jurisdictions: list[dict] = []
        for key, (city, state) in emp_locs.items():
            if key in existing_keys:
                continue
            try:
                await ensure_location_for_employee(conn, company_id, city or None, state)
                new_jurisdictions.append({"city": city or None, "state": state})
            except Exception:
                logger.exception("enrich: ensure_location failed for %s, %s", city, state)

        result = await _enrich_scope_and_persist(
            conn, company=company, roles=roles, admin_user_id=current_user.id,
        )
        resolved = result["resolved"]

    return EnrichRosterResponse(
        session_id=result["session_id"],
        company_id=company_id,
        employee_roles=roles,
        new_jurisdictions=new_jurisdictions,
        locations_filled=len(new_jurisdictions),
        scope_rows_written=result["scope_written"],
        covered_count=len(resolved.existing),
        missing_count=len(resolved.missing),
        resolved_scope=resolved,
    )


@router.post("/onboarding/enrich/{company_id}/stream")
async def enrich_company_stream(
    company_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Performative employee-sync gap analysis (SSE).

    Same outcome as ``/enrich/{id}`` but streamed as staged events so the UI
    can show it "scoping out" live: roster scan → each NEW jurisdiction is
    filled + researched live (delegating to ``run_compliance_check_stream``,
    which pulls source-of-truth requirements for jurisdictions not yet in the
    bank) → role-aware scope → done. Mirrors the SSE shape used by the
    compliance check stream (``data: {json}\\n\\n``, ``: heartbeat``, terminal
    ``data: [DONE]``).
    """

    async def events():
        # 1. Roster scan (short-lived connection).
        async with get_connection() as conn:
            company = await conn.fetchrow(
                f"SELECT {_COMPANY_PROFILE_COLS} FROM companies WHERE id = $1",
                company_id,
            )
            if not company:
                yield {"type": "error", "message": "Company not found"}
                return
            roles, emp_locs, existing_keys = await _collect_roster(conn, company_id)

        new_keys = [k for k in emp_locs if k not in existing_keys]
        yield {
            "type": "roster_scanned",
            "locations_total": len(emp_locs),
            "locations_new": len(new_keys),
            "roles": roles,
            "message": (
                f"Scanned roster — {len(emp_locs)} work location(s), "
                f"{len(new_keys)} not yet tracked, {len(roles)} role(s)."
            ),
        }
        if roles:
            yield {"type": "roles_detected", "roles": roles,
                   "message": f"Roles on staff: {', '.join(roles)}"}

        # 2. Fill each NEW jurisdiction (FAST — repo sync only, no Gemini sweep).
        #    Unknown jurisdictions surface as gaps to fill selectively afterward.
        new_jurisdictions: list[dict] = []
        for key in new_keys:
            city, state = emp_locs[key]
            label = f"{city + ', ' if city else ''}{state}"
            yield {"type": "jurisdiction_new", "city": city or None, "state": state,
                   "message": f"New work jurisdiction: {label} — not in the compliance engine yet."}
            location_id = None
            try:
                async with get_connection() as conn:
                    # background_tasks=None → creates + links jurisdiction (and
                    # clones repo data for known jurisdictions) WITHOUT firing an
                    # inline check.
                    location_id = await ensure_location_for_employee(
                        conn, company_id, city or None, state,
                    )
            except Exception:
                logger.exception("enrich-stream: ensure_location failed for %s", label)
                yield {"type": "warning", "message": f"Could not create location for {label}."}
            if not location_id:
                continue
            new_jurisdictions.append({"city": city or None, "state": state})
            yield {"type": "jurisdiction_tracking", "city": city or None, "state": state,
                   "message": f"{label} is now tracked weekly."}
            yield {"type": "researching", "jurisdiction": label,
                   "message": f"Checking known requirements for {label}…"}
            # Repo-sync only (allow_live_research=False) so the analyze pass stays
            # fast; anything missing becomes a gap the admin fills selectively.
            try:
                async for ev in run_compliance_check_stream(
                    location_id, company_id, allow_live_research=False,
                ):
                    etype = ev.get("type")
                    if etype == "heartbeat":
                        yield {"type": "heartbeat"}
                    elif etype == "error":
                        # A recoverable per-jurisdiction research hiccup — NOT a
                        # run failure. Downgrade to a warning so it doesn't trip
                        # the client's fatal-error handling; the run continues.
                        yield {"type": "warning",
                               "message": ev.get("message") or f"Research issue for {label}",
                               "jurisdiction": label}
                    else:
                        yield {**ev, "jurisdiction": label}
            except Exception as exc:
                logger.exception("enrich-stream: research failed for %s", label)
                yield {"type": "warning", "message": f"Research incomplete for {label}: {exc}",
                       "jurisdiction": label}

        # 3. Role-aware scope + persist.
        yield {"type": "scoping", "roles": roles,
               "message": "Scoping role-specific compliance from the roster…"}
        try:
            async with get_connection() as conn:
                company = await conn.fetchrow(
                    f"SELECT {_COMPANY_PROFILE_COLS} FROM companies WHERE id = $1",
                    company_id,
                )
                if not company:
                    yield {"type": "error", "message": "Company no longer exists."}
                    return
                # expand_scope + gap_check are two sequential Gemini calls; keep the
                # SSE alive with heartbeats so a proxy/client doesn't time out the
                # silent gap.
                scope_task = asyncio.create_task(_enrich_scope_and_persist(
                    conn, company=company, roles=roles, admin_user_id=current_user.id,
                ))
                async for evt in _heartbeat_while(scope_task):
                    yield evt
                result = scope_task.result()
        except HTTPException as exc:
            yield {"type": "error", "message": str(exc.detail)}
            return
        except Exception as exc:
            logger.exception("enrich-stream: scope/persist failed for %s", company_id)
            yield {"type": "error", "message": f"Scope step failed: {exc}"}
            return

        resolved = result["resolved"]
        ai_scope = result["ai_scope"]
        credentials = [
            {"name": c.name, "applies_to_role": c.applies_to_role}
            for c in ai_scope.required_credentials
        ]
        yield {
            "type": "scoped",
            "covered": len(resolved.existing),
            "missing": len(resolved.missing),
            "scope_rows_written": result["scope_written"],
            "credentials": credentials,
            "message": (
                f"Scoped {len(resolved.existing)} in-bank requirement(s); "
                f"{len(resolved.missing)} gap(s) flagged for research."
            ),
        }
        gc = result.get("gap_check") or {}
        suggestions = (
            len(gc.get("suggested_compliance_categories") or [])
            + len(gc.get("suggested_certifications") or [])
            + len(gc.get("suggested_licenses") or [])
            + len(gc.get("suggested_jurisdictions") or [])
        )
        yield {
            "type": "complete",
            "session_id": str(result["session_id"]),
            "company_id": str(company_id),
            "new_jurisdictions": new_jurisdictions,
            "roles": roles,
            "covered": len(resolved.existing),
            "missing": len(resolved.missing),
            "existing_scope_count": result.get("existing_scope_count", 0),
            "suggestions": suggestions,
            "message": "Gap analysis complete.",
        }

    async def sse():
        try:
            async for ev in events():
                if ev.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield f"data: {json.dumps(ev)}\n\n"
        except Exception as exc:  # last-resort guard so the stream always closes
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


# ── Selective gap fill (research only the chosen gaps) ──────────────────


@router.post("/onboarding/research-gaps/{company_id}/stream")
async def research_gaps_stream(
    company_id: UUID,
    body: ResearchGapsRequest,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Research the admin-SELECTED gaps only (SSE) — never a full sweep, so
    Gemini runs stay short. Groups the chosen (jurisdiction, category) items by
    jurisdiction, researches just those categories (`_refresh_repository_missing_categories`,
    which discovers sources for brand-new jurisdictions), upserts the bank, writes
    the manifest rows to the company's matching location, and re-syncs that
    location's tracked requirements. Streams progress like the enrich stream.
    """
    # Group selected gaps by jurisdiction.
    groups: dict[tuple, list[str]] = {}
    for it in body.items:
        state = (it.state or "").upper().strip()
        if not state or not it.category_slug:
            continue
        county = (it.county or "").strip() or None
        city = (it.city or "").strip() or None
        cats = groups.setdefault((state, county, city), [])
        if it.category_slug not in cats:
            cats.append(it.category_slug)

    async def events():
        if not groups:
            yield {"type": "error", "message": "No gaps selected to research."}
            return
        async with get_connection() as conn:
            comp = await conn.fetchrow("SELECT industry FROM companies WHERE id = $1", company_id)
        if not comp:
            yield {"type": "error", "message": "Company not found."}
            return
        industry_context = comp["industry"] or ""
        service = get_gemini_compliance_service()
        total_cats = sum(len(v) for v in groups.values())
        yield {"type": "started", "jurisdictions": len(groups), "categories": total_cats,
               "message": f"Researching {total_cats} selected gap(s) across {len(groups)} jurisdiction(s)…"}

        filled = 0
        for (state, county, city), cats in groups.items():
            label = f"{city + ', ' if city else ''}{state}"
            yield {"type": "researching", "jurisdiction": label, "categories": cats,
                   "message": f"Researching {', '.join(cats)} for {label}…"}
            loc = None
            try:
                async with get_connection() as conn:
                    jid = await _get_or_create_jurisdiction(conn, city or state, state, county)
                    has_local = await _lookup_has_local_ordinance(conn, city, state) if city else None
                    cur = [_jurisdiction_row_to_dict(jr)
                           for jr in await _load_jurisdiction_requirements(conn, jid)]

                    rq: asyncio.Queue = asyncio.Queue()

                    def _on_retry(attempt, err, _q=rq, _l=label):
                        _q.put_nowait({"type": "retrying", "jurisdiction": _l,
                                       "message": f"Retrying research for {_l} (attempt {attempt + 1})…"})

                    task = asyncio.create_task(_refresh_repository_missing_categories(
                        conn, service, jurisdiction_id=jid, city=city or "", state=state,
                        county=county, has_local_ordinance=has_local,
                        current_requirements=cur, missing_categories=cats,
                        on_retry=_on_retry, industry_context=industry_context,
                    ))
                    # Heartbeat + drain retry messages while research runs.
                    async for evt in _heartbeat_while(task, queue=rq):
                        yield evt
                    task.result()  # propagate research exceptions

                    loc = await conn.fetchrow(
                        "SELECT id FROM business_locations WHERE company_id = $1 AND jurisdiction_id = $2 "
                        "AND is_active = TRUE ORDER BY is_company_wide ASC LIMIT 1",
                        company_id, jid,
                    )
                # The re-sync below (run_compliance_check_stream) writes the freshly
                # researched requirements straight into compliance_requirements — the
                # live single source of truth. No separate scope-pointer table to keep.
                filled += 1
                # Re-sync the location's tracked requirements from the updated repo.
                if loc:
                    async for ev in run_compliance_check_stream(
                        loc["id"], company_id, allow_live_research=False,
                    ):
                        etype = ev.get("type")
                        if etype == "heartbeat":
                            yield {"type": "heartbeat"}
                        elif etype == "error":
                            yield {"type": "warning",
                                   "message": ev.get("message") or f"Sync issue for {label}",
                                   "jurisdiction": label}
                        else:
                            yield {**ev, "jurisdiction": label}
                yield {"type": "jurisdiction_done", "jurisdiction": label,
                       "message": f"Filled {label} ({len(cats)} categor{'y' if len(cats) == 1 else 'ies'})."}
            except Exception as exc:
                logger.exception("research-gaps: failed for %s", label)
                yield {"type": "warning", "jurisdiction": label,
                       "message": f"Research failed for {label}: {exc}"}

        yield {"type": "complete", "company_id": str(company_id),
               "jurisdictions_filled": filled,
               "message": f"Done — filled {filled} of {len(groups)} jurisdiction(s)."}

    async def sse():
        try:
            async for ev in events():
                if ev.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield f"data: {json.dumps(ev)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


# ── AI scope expansion ──────────────────────────────────────────────────


@router.post(
    "/onboarding/sessions/{session_id}/expand",
    response_model=ExpandScopeResponse,
)
async def expand_session_scope(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Run Gemini to expand basics+locations into a scope manifest.

    Persists the result into ``onboarding_sessions.ai_scope``.
    """
    async with get_connection() as conn:
        row = await _load_session_or_404(conn, session_id)
        if row["created_by"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not your onboarding session")

        basics = _safe_jsonb(row["basics"], {})
        if not basics.get("industry"):
            raise HTTPException(
                status_code=400,
                detail="Industry is required to expand scope. Save Step 1 first.",
            )
        locations = _safe_jsonb(row["locations"], [])

        try:
            ai_scope_raw = await ai_expand_scope(
                basics=basics, locations=locations, conn=conn,
            )
        except asyncio.TimeoutError:
            # Surface the actionable retry message rather than the generic
            # 5xx fallback in the API client. 504 over 502 because we DID
            # reach Gemini — the upstream just took too long to respond.
            logger.warning("expand_scope timed out for session %s", session_id)
            raise HTTPException(
                status_code=504,
                detail=(
                    "AI scope expansion is taking longer than expected. "
                    "Click 'Run AI scope expansion' again to retry."
                ),
            )
        except Exception as exc:
            logger.exception("expand_scope failed for session %s", session_id)
            raise HTTPException(
                status_code=502,
                detail=f"Gemini scope expansion failed: {exc}",
            )

        # Validate via Pydantic to catch shape drift before persisting.
        try:
            ai_scope = AIScope.model_validate(ai_scope_raw)
        except Exception as exc:
            logger.warning("AI scope failed Pydantic validation: %s", exc)
            ai_scope = AIScope()  # surface empty scope; admin retries

        # Flag fully-empty scopes for observability. Frontend surfaces a
        # "re-run" banner in this case; the log helps us see how often
        # Gemini whiffs on a given industry/locations shape.
        if (
            not ai_scope.compliance_categories
            and not ai_scope.required_certifications
            and not ai_scope.required_licenses
            and not ai_scope.applicable_jurisdictions
        ):
            logger.warning(
                "expand_scope produced fully empty scope for session %s "
                "(industry=%r locations=%d) — check Gemini output",
                session_id, basics.get("industry"), len(locations),
            )

        # Re-expand invalidates any prior bank reconciliation: clearing
        # resolved_scope here prevents the gaps UI from showing stale
        # existing/missing lists keyed to a previous AI run.
        await conn.execute(
            """
            UPDATE onboarding_sessions
            SET ai_scope = $1::jsonb,
                resolved_scope = NULL,
                step = 'scope',
                updated_at = NOW()
            WHERE id = $2
            """,
            json.dumps(ai_scope.model_dump()), session_id,
        )
    return ExpandScopeResponse(session_id=session_id, ai_scope=ai_scope)


# ── Bank reconciliation ─────────────────────────────────────────────────


@router.post(
    "/onboarding/sessions/{session_id}/resolve",
    response_model=ResolveScopeResponse,
)
async def resolve_session_scope(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Map the persisted ``ai_scope`` against the shared bank.

    Pure SQL — no Gemini. Persists ``resolved_scope`` and bumps step to
    ``gaps``.
    """
    async with get_connection() as conn:
        row = await _load_session_or_404(conn, session_id)
        if row["created_by"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not your onboarding session")
        ai_scope = _safe_jsonb(row["ai_scope"], None)
        if not ai_scope:
            raise HTTPException(
                status_code=400,
                detail="No AI scope on file. Run /expand first.",
            )
        resolved_raw = await map_to_bank(ai_scope, conn)
        try:
            resolved = ResolvedScope.model_validate(resolved_raw)
        except Exception as exc:
            logger.warning("Resolved scope failed Pydantic validation: %s", exc)
            resolved = ResolvedScope()

        await conn.execute(
            """
            UPDATE onboarding_sessions
            SET resolved_scope = $1::jsonb, step = 'gaps', updated_at = NOW()
            WHERE id = $2
            """,
            json.dumps(resolved.model_dump(mode="json")), session_id,
        )
    return ResolveScopeResponse(session_id=session_id, resolved_scope=resolved)


# ── Gap-fill research dispatch ──────────────────────────────────────────


@router.post(
    "/onboarding/sessions/{session_id}/dispatch-research",
    response_model=DispatchResearchResponse,
)
async def dispatch_research(
    session_id: UUID,
    body: DispatchResearchRequest,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Dispatch background research workers for admin-approved missing items.

    Each ``approved_missing_ids`` entry is the stable id from
    ``build_missing_id``. Items not in that list are skipped so AI
    hallucinations don't pollute the bank.

    Phase 1: the worker dispatch itself is a soft-stub — we log the
    requested category/jurisdiction tuples and return them in the
    ``dispatched`` list, but actual Celery enqueue is wired through
    existing ``run_compliance_check_task`` / ``run_medical_compliance_research``
    workers in a follow-up commit. The admin checkbox gate is the part
    that needs to land first.
    """
    async with get_connection() as conn:
        row = await _load_session_or_404(conn, session_id)
        if row["created_by"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not your onboarding session")
        resolved = _safe_jsonb(row["resolved_scope"], None) or {}
        missing = resolved.get("missing") or []

    approved = set(body.approved_missing_ids or [])
    dispatched: list[str] = []
    skipped: list[str] = []
    for item in missing:
        item_id = build_missing_id(item)
        if item_id in approved:
            dispatched.append(item_id)
            # TODO: enqueue run_compliance_check_task or
            # run_medical_compliance_research keyed off
            # item['category_slug'] + item['state']/county/city. Existing
            # workers want (category, jurisdiction) keys — wire-up lives
            # in a follow-up commit so this endpoint can ship with the
            # admin checkbox gate intact.
            logger.info(
                "TODO: dispatch research worker for session=%s item=%s",
                session_id, item_id,
            )
        else:
            skipped.append(item_id)
    return DispatchResearchResponse(
        session_id=session_id,
        dispatched=dispatched,
        skipped=skipped,
    )


# ── Gap check (end-of-wizard safety net) ────────────────────────────────


@router.post(
    "/onboarding/sessions/{session_id}/gap-check",
    response_model=GapCheckResponse,
)
async def gap_check_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Re-read the full captured state and surface anything the wizard missed.

    Read-only: returns suggestions, does not mutate ``ai_scope``. Result
    is persisted under ``resolved_scope.gap_check`` so it survives a
    page refresh.
    """
    async with get_connection() as conn:
        row = await _load_session_or_404(conn, session_id)
        if row["created_by"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not your onboarding session")

        basics = _safe_jsonb(row["basics"], {})
        locations = _safe_jsonb(row["locations"], [])
        ai_scope = _safe_jsonb(row["ai_scope"], None) or {}
        resolved_scope_raw = _safe_jsonb(row["resolved_scope"], None) or {}

        try:
            gap_raw = await ai_gap_check(
                basics=basics,
                locations=locations,
                ai_scope=ai_scope,
                resolved_scope=resolved_scope_raw,
                conn=conn,
            )
        except Exception as exc:
            logger.exception("gap_check failed for session %s", session_id)
            raise HTTPException(
                status_code=502,
                detail=f"Gemini gap check failed: {exc}",
            )

        try:
            gap_result = GapCheckResult.model_validate(gap_raw)
        except Exception as exc:
            logger.warning("Gap check failed Pydantic validation: %s", exc)
            gap_result = GapCheckResult(summary="Gap check returned an unrecognized shape.")

        # Stash on the session row so refresh + resume both see it.
        next_resolved = dict(resolved_scope_raw)
        next_resolved["gap_check"] = gap_result.model_dump()
        await conn.execute(
            """
            UPDATE onboarding_sessions
            SET resolved_scope = $1::jsonb, updated_at = NOW()
            WHERE id = $2
            """,
            json.dumps(next_resolved), session_id,
        )

    return GapCheckResponse(session_id=session_id, gap_check=gap_result)


# ── Finalize ────────────────────────────────────────────────────────────


@router.post(
    "/onboarding/sessions/{session_id}/finalize",
    response_model=FinalizeResponse,
)
async def finalize_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Write the durable manifest + invite the owner.

    Projects resolved 'existing' scope into compliance_requirements (the single
    per-company source of truth) and upserts the cert/license catalogs +
    company_certifications/company_licenses. Idempotent — re-running re-writes the
    same rows (the (location_id, jurisdiction_requirement_id) partial unique index
    and the cert/license UNIQUE constraints no-op on duplicate).
    """
    async with get_connection() as conn:
        row = await _load_session_or_404(conn, session_id)
        if row["created_by"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not your onboarding session")
        if not row["company_id"]:
            raise HTTPException(
                status_code=400,
                detail="Run /create-company before finalizing.",
            )

        ai_scope = _safe_jsonb(row["ai_scope"], None) or {}
        resolved = _safe_jsonb(row["resolved_scope"], None) or {}
        existing = resolved.get("existing") or []
        certifications = ai_scope.get("required_certifications") or []
        licenses = ai_scope.get("required_licenses") or []

        company_id = row["company_id"]
        scope_rows_written = await _write_compliance_scope_rows(
            conn,
            company_id=company_id,
            existing_items=existing,
            admin_user_id=current_user.id,
            source="onboarding_wizard",
        )

        # Upsert catalogs + per-company manifests for certs/licenses.
        certifications_written = 0
        for cert in certifications:
            try:
                cert_row = await conn.fetchrow(
                    """
                    INSERT INTO certifications_catalog (
                        slug, name, issuing_authority, scope_level, industry_tag, renewal_months
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    cert.get("slug"), cert.get("name"),
                    cert.get("issuing_authority"),
                    cert.get("scope_level") or "federal",
                    _safe_jsonb(row["basics"], {}).get("industry"),
                    cert.get("renewal_period_months"),
                )
                await conn.execute(
                    """
                    INSERT INTO company_certifications (
                        company_id, certification_id, location_id
                    )
                    VALUES ($1, $2, NULL)
                    ON CONFLICT (company_id, certification_id, location_id) DO NOTHING
                    """,
                    company_id, cert_row["id"],
                )
                certifications_written += 1
            except Exception as exc:
                logger.warning("cert insert failed: %s", exc)

        licenses_written = 0
        for lic in licenses:
            try:
                lic_row = await conn.fetchrow(
                    """
                    INSERT INTO licenses_catalog (
                        slug, name, issuing_authority, scope_level, industry_tag, renewal_months
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    lic.get("slug"), lic.get("name"),
                    lic.get("issuing_authority"),
                    lic.get("scope_level") or "state",
                    _safe_jsonb(row["basics"], {}).get("industry"),
                    lic.get("renewal_period_months"),
                )
                await conn.execute(
                    """
                    INSERT INTO company_licenses (
                        company_id, license_id, location_id
                    )
                    VALUES ($1, $2, NULL)
                    ON CONFLICT (company_id, license_id, location_id) DO NOTHING
                    """,
                    company_id, lic_row["id"],
                )
                licenses_written += 1
            except Exception as exc:
                logger.warning("license insert failed: %s", exc)

        # Issue an invite token. The user accepts via existing
        # /invitations machinery; we just stamp the token here. Token
        # generation kept inline to avoid pulling in the email service
        # at this layer — the index page surfaces the link to the admin
        # so they can hand it off manually for now.
        invite_token = row["invite_token"] or secrets.token_urlsafe(32)

        # Freeze the full gap-analysis dossier as-finalized. resolved/ai_scope
        # are already parsed above; basics/size/locations come off the row.
        dossier = build_gap_analysis_dossier({
            "id": session_id,
            "status": "finalized",
            "basics": _safe_jsonb(row["basics"], {}),
            "size": _safe_jsonb(row["size"], {}),
            "locations": _safe_jsonb(row["locations"], []),
            "ai_scope": ai_scope,
            "resolved_scope": resolved,
        })

        await conn.execute(
            """
            UPDATE onboarding_sessions
            SET status = 'finalized', step = 'done',
                invite_token = $1, gap_analysis = $2::jsonb, updated_at = NOW()
            WHERE id = $3
            """,
            invite_token, json.dumps(dossier), session_id,
        )

    return FinalizeResponse(
        session_id=session_id,
        company_id=company_id,
        invite_token=invite_token,
        scope_rows_written=scope_rows_written,
        certifications_written=certifications_written,
        licenses_written=licenses_written,
    )


# ── Gap-analysis report (view + export) ─────────────────────────────────


async def _load_owned_session(conn, session_id: UUID, current_user):
    """Load a session + enforce the per-creator 403 guard used elsewhere."""
    row = await _load_session_or_404(conn, session_id)
    if row["created_by"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not your onboarding session")
    return row


def _dossier_filename(dossier: dict, ext: str) -> str:
    name = ((dossier.get("company") or {}).get("name") or "onboarding").strip()
    slug = "".join(c if c.isalnum() else "-" for c in name).strip("-").lower() or "onboarding"
    return f"gap-analysis-{slug}.{ext}"


@router.get(
    "/onboarding/sessions/{session_id}/report",
    response_model=GapAnalysisDossier,
)
async def get_session_report(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """The assembled gap-analysis dossier. Returns the frozen snapshot if
    finalized, else assembles live so in-progress sessions are reviewable."""
    async with get_connection() as conn:
        row = await _load_owned_session(conn, session_id, current_user)
        return _dossier_from_row(row)


@router.get("/onboarding/sessions/{session_id}/report.md")
async def get_session_report_markdown(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Markdown export of the dossier."""
    async with get_connection() as conn:
        row = await _load_owned_session(conn, session_id, current_user)
        dossier = _dossier_from_row(row)
    md = _dossier_to_markdown(dossier)
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{_dossier_filename(dossier, "md")}"'},
    )


@router.get("/onboarding/sessions/{session_id}/report.pdf")
async def get_session_report_pdf(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """PDF export of the dossier (WeasyPrint, rendered inline)."""
    async with get_connection() as conn:
        row = await _load_owned_session(conn, session_id, current_user)
        dossier = _dossier_from_row(row)

    full_html = _dossier_to_html(dossier)
    try:
        from weasyprint import HTML
    except ImportError as ie:
        logger.error("weasyprint import failed: %s", ie)
        raise HTTPException(
            status_code=501,
            detail="PDF generation not available — install weasyprint on the server (`pip install weasyprint`).",
        )
    try:
        pdf_bytes = await asyncio.wait_for(
            asyncio.to_thread(lambda: HTML(string=full_html).write_pdf()),
            timeout=60,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="PDF render timed out.")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_dossier_filename(dossier, "pdf")}"'},
    )


# ── Persistent per-company gap dashboard ────────────────────────────────


async def _load_company_gap_session(conn, company_id: UUID):
    """The durable gap-analysis session for a company.

    Prefers the idempotent enrichment session (``enrich-{company_id}``); falls
    back to the most-recent non-abandoned session for the company (e.g. a
    wizard-onboarded company that never ran roster enrichment).
    """
    row = await conn.fetchrow(
        "SELECT * FROM onboarding_sessions WHERE idempotency_key = $1",
        f"enrich-{company_id}",
    )
    if row:
        return row
    return await conn.fetchrow(
        """
        SELECT * FROM onboarding_sessions
        WHERE company_id = $1 AND status != 'abandoned'
        ORDER BY updated_at DESC LIMIT 1
        """,
        company_id,
    )


@router.get("/onboarding/companies/{company_id}/gap-dashboard")
async def get_company_gap_dashboard(
    company_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Live, persistent gap-analysis dossier for a company.

    Cheap by design: re-resolves the company's persisted ``ai_scope`` against
    the CURRENT compliance bank via ``map_to_bank`` (pure SQL) so gaps filled
    since the last run show as covered — without any Gemini call. A full
    (Gemini) recompute is the separate ``/enrich`` stream; selective fills are
    ``/research-gaps``. Returns ``status='never_run'`` when no analysis exists.
    """
    async with get_connection() as conn:
        company = await conn.fetchrow(
            "SELECT id, name FROM companies WHERE id = $1", company_id,
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        session = await _load_company_gap_session(conn, company_id)
        if not session:
            return {
                "status": "never_run",
                "company": {"id": str(company_id), "name": company["name"]},
                "dossier": None,
                "drift": None,
            }

        ai_scope = _safe_jsonb(session["ai_scope"], {}) or {}
        persisted_resolved = _safe_jsonb(session["resolved_scope"], {}) or {}
        gap_check = persisted_resolved.get("gap_check") or {}

        # Cheap live refresh: re-resolve persisted scope against the current
        # bank (SQL only). Preserve the persisted (Gemini) safety-net suggestions.
        resolved = persisted_resolved
        if ai_scope:
            try:
                fresh = await map_to_bank(ai_scope, conn)
                resolved = {**fresh, "gap_check": gap_check}
                # Persist the cheap live refresh back so the companies overview's
                # counts stay fresh (e.g. a gap filled here drops out of `missing`).
                # Do NOT bump updated_at — that tracks the last full (Gemini) analysis.
                await conn.execute(
                    "UPDATE onboarding_sessions SET resolved_scope = $1::jsonb WHERE id = $2",
                    json.dumps(resolved), session["id"],
                )
            except Exception:
                logger.exception(
                    "gap-dashboard: map_to_bank refresh failed for company %s", company_id,
                )

        dossier = build_gap_analysis_dossier({
            "id": session["id"],
            "status": session["status"],
            "basics": _safe_jsonb(session["basics"], {}),
            "size": _safe_jsonb(session["size"], {}),
            "locations": _safe_jsonb(session["locations"], []),
            "ai_scope": ai_scope,
            "resolved_scope": resolved,
        })
        counts = dossier["counts"]
        denom = counts["covered"] + counts["gaps"]
        counts["coverage_pct"] = round(100 * counts["covered"] / denom) if denom else 100

        # Drift (cheap): roster jurisdictions not yet tracked + locations added
        # since the last analysis. Signals when a full Re-run is worthwhile.
        drift = {
            "last_analyzed_at": session["updated_at"].isoformat() if session["updated_at"] else None,
            "new_locations": 0,
            "new_jurisdictions": 0,
        }
        try:
            _roles, emp_locs, existing_keys = await _collect_roster(conn, company_id)
            drift["new_jurisdictions"] = sum(1 for k in emp_locs if k not in existing_keys)
            tracked = await conn.fetchval(
                """
                SELECT COUNT(*) FROM business_locations
                WHERE company_id = $1 AND is_active = TRUE AND is_company_wide = FALSE
                """,
                company_id,
            )
            analyzed = len(_safe_jsonb(session["locations"], []))
            drift["new_locations"] = max(0, (tracked or 0) - analyzed)
        except Exception:
            logger.exception("gap-dashboard: drift calc failed for company %s", company_id)

        return {
            "status": "ok",
            "company": {"id": str(company_id), "name": company["name"]},
            "session_id": str(session["id"]),
            "dossier": dossier,
            "drift": drift,
        }


@router.get("/onboarding/gap-overview")
async def get_gap_overview(
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Companies overview for the gap-analysis landing dashboard.

    One row per analyzed company (its canonical gap session) with persisted
    counts + a cheap location-drift signal. Counts are as-of the last dashboard
    view / analysis (the per-company dashboard writes its live refresh back), so
    this is fast (2 queries total, no per-company Gemini or map_to_bank).
    """
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (s.company_id)
                   s.company_id, c.name AS company_name,
                   COALESCE(c.status, 'approved') AS company_status,
                   s.status AS session_status, s.updated_at,
                   s.resolved_scope, s.locations
            FROM onboarding_sessions s
            JOIN companies c ON c.id = s.company_id
            WHERE s.company_id IS NOT NULL AND s.status != 'abandoned'
            ORDER BY s.company_id,
                     (s.idempotency_key = 'enrich-' || s.company_id::text) DESC NULLS LAST,
                     s.updated_at DESC
            """
        )
        loc_rows = await conn.fetch(
            """
            SELECT company_id, COUNT(*) AS n FROM business_locations
            WHERE is_active = TRUE AND is_company_wide = FALSE
            GROUP BY company_id
            """
        )
    loc_counts = {r["company_id"]: r["n"] for r in loc_rows}

    out = []
    for r in rows:
        resolved = _safe_jsonb(r["resolved_scope"], {}) or {}
        covered = len(resolved.get("existing") or [])
        gaps = len(resolved.get("missing") or [])
        ambiguous = len(resolved.get("ambiguous") or [])
        denom = covered + gaps
        analyzed_locs = len(_safe_jsonb(r["locations"], []) or [])
        tracked = loc_counts.get(r["company_id"], 0)
        out.append({
            "company_id": str(r["company_id"]),
            "company_name": r["company_name"],
            "company_status": r["company_status"],
            "session_status": r["session_status"],
            "covered": covered,
            "gaps": gaps,
            "ambiguous": ambiguous,
            "coverage_pct": round(100 * covered / denom) if denom else 100,
            "last_analyzed_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            "new_locations": max(0, tracked - analyzed_locs),
        })
    # Needs-attention first: open gaps, then drift, then lowest coverage.
    out.sort(key=lambda x: (-x["gaps"], -x["new_locations"], x["coverage_pct"]))
    return out


@router.get("/onboarding/companies/{company_id}/requirements/{requirement_id}")
async def get_company_requirement_detail(
    company_id: UUID,
    requirement_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Rich detail for a covered requirement (drill-in from the dashboard).

    Covered items carry the shared-bank ``requirement_id`` → resolve it to the
    full ``jurisdiction_requirements`` row. The bank is shared reference data,
    so this is admin-readable regardless of company.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, category, jurisdiction_level, jurisdiction_name, title,
                   description, current_value, rate_type, source_url, source_name,
                   effective_date, expiration_date, requires_written_policy,
                   implementation_steps
            FROM jurisdiction_requirements WHERE id = $1
            """,
            requirement_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Requirement not found")
        return {
            "id": str(row["id"]),
            "category": row["category"],
            "jurisdiction_level": row["jurisdiction_level"],
            "jurisdiction_name": row["jurisdiction_name"],
            "title": row["title"],
            "description": row["description"],
            "current_value": row["current_value"],
            "rate_type": row["rate_type"],
            "source_url": row["source_url"],
            "source_name": row["source_name"],
            "effective_date": row["effective_date"].isoformat() if row["effective_date"] else None,
            "expiration_date": row["expiration_date"].isoformat() if row["expiration_date"] else None,
            "requires_written_policy": row["requires_written_policy"],
            "implementation_steps": _safe_jsonb(row["implementation_steps"], None),
        }


# ── Abandon ─────────────────────────────────────────────────────────────


@router.post("/onboarding/sessions/{session_id}/abandon", status_code=status.HTTP_204_NO_CONTENT)
async def abandon_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_master_admin),
):
    """Soft-close an in-progress session.

    A reaper job (added in a follow-up commit) will eventually delete
    the orphaned company + locations if no scope rows were written.
    For now this just flips the status so the index page hides it.
    """
    async with get_connection() as conn:
        row = await _load_session_or_404(conn, session_id)
        if row["created_by"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not your onboarding session")
        if row["status"] != "in_progress":
            return
        await conn.execute(
            "UPDATE onboarding_sessions SET status = 'abandoned', updated_at = NOW() WHERE id = $1",
            session_id,
        )
    return
