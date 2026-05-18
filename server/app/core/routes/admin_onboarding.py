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

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.models.auth import CurrentUser
from app.core.models.admin_onboarding import (
    AIScope,
    CreateCompanyResponse,
    CreateSessionRequest,
    DispatchResearchRequest,
    DispatchResearchResponse,
    ExpandScopeResponse,
    FinalizeResponse,
    GapCheckResponse,
    GapCheckResult,
    OnboardingSessionDetail,
    OnboardingSessionSummary,
    PatchSessionRequest,
    ResolveScopeResponse,
    ResolvedScope,
)
from app.core.services.onboarding_scope_ai import (
    INDUSTRY_SPECIALTIES,
    build_missing_id,
    expand_scope as ai_expand_scope,
    gap_check as ai_gap_check,
    map_to_bank,
)

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

    Idempotent — re-running just re-writes the same rows (UNIQUE
    constraints on company_compliance_scope, company_certifications,
    company_licenses no-op on duplicate).
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
        # Cache the company-wide sentinel id once.
        sentinel = await conn.fetchrow(
            "SELECT id FROM business_locations WHERE company_id = $1 AND is_company_wide = TRUE LIMIT 1",
            company_id,
        )
        sentinel_id = sentinel["id"] if sentinel else None

        # For state/county/city scope, pick the FIRST matching real location.
        # Federal scope → sentinel. Multi-location attach is Phase 2.
        real_locs = await conn.fetch(
            """
            SELECT id, state, county, city FROM business_locations
            WHERE company_id = $1 AND is_company_wide = FALSE AND is_active = TRUE
            """,
            company_id,
        )

        scope_rows_written = 0
        for item in existing:
            scope_level = (item.get("scope_level") or "federal").lower()
            target_location_id = sentinel_id
            if scope_level != "federal" and real_locs:
                # Match by state when present, else first real location.
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
                continue
            try:
                await conn.execute(
                    """
                    INSERT INTO company_compliance_scope (
                        company_id, requirement_id, location_id, scope_level,
                        source, status, admin_reviewed_by
                    )
                    VALUES ($1, $2, $3, $4, 'onboarding_wizard', 'active', $5)
                    ON CONFLICT (company_id, requirement_id, location_id) DO NOTHING
                    """,
                    company_id, item["requirement_id"], target_location_id,
                    scope_level, current_user.id,
                )
                scope_rows_written += 1
            except Exception as exc:
                logger.warning("scope insert failed for %s: %s", item.get("requirement_id"), exc)

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

        await conn.execute(
            """
            UPDATE onboarding_sessions
            SET status = 'finalized', step = 'done',
                invite_token = $1, updated_at = NOW()
            WHERE id = $2
            """,
            invite_token, session_id,
        )

    return FinalizeResponse(
        session_id=session_id,
        company_id=company_id,
        invite_token=invite_token,
        scope_rows_written=scope_rows_written,
        certifications_written=certifications_written,
        licenses_written=licenses_written,
    )


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
