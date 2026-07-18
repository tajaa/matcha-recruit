"""Matcha-X self-serve onboarding wizard companion endpoints.

A stripped-down, *performative* counterpart to the admin white-glove
``/admin/gap-analysis`` flow. Matcha-X tenants onboard themselves: add
locations, drop in their handbook, add employees — then watch Matcha build
their compliance baseline live (``POST /build/stream``): per-location
jurisdiction resolution → fetch from the directory → codify brand-new
jurisdictions on screen → overlay their handbook's coverage.

Mounted under ``require_feature("handbook_audit")`` — the exact Matcha-X /
Pro entitlement (``matcha_x`` is a ``signup_source``, not a boolean flag;
``handbook_audit`` is on for X via the tier overlay and stored for Pro, off
for Free/Lite and personal Werk).

No new table: wizard step is inferred from data presence (mirrors
``ir_onboarding.get_onboarding_status``); "skip / done" is a client-side
localStorage flag.
"""

import asyncio
import json
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.services.compliance_service import (
    run_compliance_check_stream,
    MATCHA_X_LITE_CATEGORIES,
    _get_industry_profile,
    _heartbeat_while,
)
from ....core.services.roster_jurisdictions import (
    collect_roster_jurisdictions,
    sync_and_check_roster_jurisdictions,
)
from ....core.services.handbook_audit_service import (
    _extract_sections_from_pdf,
    _grade_state_coverage,
)
from ....core.services.storage import get_storage
from ....core.services import vertical_coverage

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Status (data-presence step inference; no completion column) ───────────


@router.get("/status")
async def get_matcha_x_onboarding_status(
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM business_locations
                   WHERE company_id = $1 AND is_active = true) AS locations_count,
                (SELECT COUNT(*) FROM employees WHERE org_id = $1) AS employees_count,
                EXISTS(SELECT 1 FROM handbooks WHERE company_id = $1) AS handbook_present,
                EXISTS(
                    SELECT 1 FROM compliance_requirements cr
                    JOIN business_locations bl ON bl.id = cr.location_id
                    WHERE bl.company_id = $1
                ) AS built
            """,
            company_id,
        )

    locations_count = int(row["locations_count"] or 0)
    employees_count = int(row["employees_count"] or 0)
    built = bool(row["built"])

    if locations_count == 0:
        step = "locations"
    elif employees_count == 0:
        step = "people"
    elif not built:
        step = "build"
    else:
        step = "done"

    return {
        "step": step,
        "locations_count": locations_count,
        "employees_count": employees_count,
        "handbook_present": bool(row["handbook_present"]),
        "built": built,
    }


@router.post("/complete")
async def complete_matcha_x_onboarding(
    current_user=Depends(require_admin_or_client),
):
    """Best-effort marker. Completion is tracked client-side (localStorage);
    this exists for symmetry and future server-side persistence."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    return {"completed": True}


# ── Locations (decoupled from the incidents paywall) ──────────────────────
# Mirrors /ir-onboarding/locations but lives on the handbook_audit-gated router
# so the wizard works for EVERY Matcha-X tenant — including business-pays
# tenants whose `incidents` flag hasn't been flipped by the Stripe webhook yet
# (the /ir-onboarding/* router is incidents-gated and would 403 in that window).
# Same business_locations table, so any later upgrade carries the data over.


class MatchaXLocationCreate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: str
    state: str
    zipcode: str


def _serialize_location(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "address": row["address"],
        "city": row["city"],
        "state": row["state"],
        "zipcode": row["zipcode"],
        "is_active": bool(row["is_active"]),
    }


@router.get("/locations")
async def list_matcha_x_locations(
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, address, city, state, zipcode, is_active
            FROM business_locations
            WHERE company_id = $1 AND is_active = true
            ORDER BY name NULLS LAST, city
            """,
            company_id,
        )
    return [_serialize_location(r) for r in rows]


@router.post("/locations")
async def create_matcha_x_location(
    data: MatchaXLocationCreate,
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO business_locations (
                company_id, name, address, city, state, zipcode, is_active
            )
            VALUES ($1, $2, $3, $4, $5, $6, true)
            RETURNING id, name, address, city, state, zipcode, is_active
            """,
            company_id,
            data.name,
            data.address,
            data.city.strip(),
            data.state.strip().upper(),
            data.zipcode.strip(),
        )
    return _serialize_location(row)


@router.delete("/locations/{location_id}")
async def deactivate_matcha_x_location(
    location_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE business_locations
               SET is_active = false, updated_at = NOW()
             WHERE id = $1 AND company_id = $2
            RETURNING id
            """,
            location_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
    return {"deactivated": True}


# ── Handbook upload (per-company key namespace → ownership-checkable) ──────


@router.post("/handbook-upload")
async def upload_x_handbook(
    file: UploadFile = File(...),
    current_user=Depends(require_admin_or_client),
):
    """Handbook upload for the onboarding coverage overlay. Stores the file
    under a per-company key prefix (``handbooks/{company_id}/…``) so the build
    can verify the file belongs to the caller before downloading it — closing
    the IDOR / arbitrary-read a raw client-supplied storage URL would open."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    url = await get_storage().upload_file(
        file_bytes=data,
        filename=file.filename or "handbook.pdf",
        prefix=f"handbooks/{company_id}",
        content_type=file.content_type,
    )
    return {"url": url, "filename": file.filename or "handbook.pdf"}


def _is_owned_handbook_url(url: str, company_id) -> bool:
    """Allow only a storage reference THIS company uploaded via
    /handbook-upload: our own CloudFront URL whose key sits under
    ``handbooks/{company_id}/``, or (local dev backend) an ``/uploads/`` path
    that storage._resolve_local_upload_path confines to the uploads dir.
    Rejects ``s3://`` (arbitrary-bucket read), foreign hosts (SSRF), path
    traversal, and another tenant's handbook key."""
    if not url or ".." in url:
        return False
    storage = get_storage()
    domain = getattr(storage, "cloudfront_domain", None)
    if domain and url.startswith(f"https://{domain}/"):
        key = url[len(f"https://{domain}/"):].split("?", 1)[0]
        return key.startswith(f"handbooks/{company_id}/")
    # Local dev backend ignores the prefix (returns /uploads/resources/…) and
    # confines reads to the uploads dir — acceptable for dev-only data.
    if url.startswith("/uploads/") or url.startswith("uploads/"):
        return True
    return False


# ── The performative live build (SSE) ─────────────────────────────────────


async def _queue_jurisdiction_research(
    conn,
    jurisdiction_id,
    company_id,
    location_id,
    missing_categories: List[str],
    industry: Optional[str],
) -> None:
    """Queue a jurisdiction's catalog gap for OUR research team, no Gemini.

    The tenant build is projection-only; anything the shared catalog is missing
    becomes a pending ``jurisdiction_coverage_requests`` row an admin runs from
    /admin (Jurisdictions → Coverage Requests / research-queue). Mirrors the
    unknown-jurisdiction upsert in ``compliance_service.ensure_location_for_employee``.
    Best-effort — a queueing failure must never break the build.
    """
    try:
        if not jurisdiction_id:
            return
        jid = jurisdiction_id if isinstance(jurisdiction_id, UUID) else UUID(str(jurisdiction_id))
        jur = await conn.fetchrow(
            "SELECT city, state, county FROM jurisdictions WHERE id = $1",
            jid,
        )
        if not jur or not jur["city"]:
            return
        loc_uuid = None
        if location_id:
            loc_uuid = location_id if isinstance(location_id, UUID) else UUID(str(location_id))
        # Resolve category KEYS → human labels so the admin queue reads
        # "Anti-Discrimination, Final Pay, I-9 & E-Verify…" not raw slugs. This
        # is the exhaustive set of required categories the shared catalog is
        # missing for this jurisdiction — everything an admin needs to research.
        labels = []
        if missing_categories:
            name_rows = await conn.fetch(
                "SELECT slug, name FROM compliance_categories WHERE slug = ANY($1::text[])",
                missing_categories,
            )
            name_by_slug = {r["slug"]: r["name"] for r in name_rows}
            labels = [name_by_slug.get(k, k) for k in missing_categories]
        cats = ", ".join(labels) if labels else ""
        note = f"Needs research: {cats}" + (f" — {industry}" if industry else "")
        await conn.execute(
            """
            INSERT INTO jurisdiction_coverage_requests
                (city, state, county, requested_by_company_id, location_id, status, admin_notes)
            VALUES ($1, $2, $3, $4, $5, 'pending', $6)
            ON CONFLICT (city, state) DO UPDATE
                SET requested_by_company_id = EXCLUDED.requested_by_company_id,
                    location_id = EXCLUDED.location_id,
                    admin_notes = EXCLUDED.admin_notes,
                    -- bump recency so the queue surfaces the LATEST business to
                    -- hit this gap first (created_at doubles as "last requested"
                    -- — the table has no updated_at). We don't keep per-business
                    -- history; the newest trigger is what an admin follows up on.
                    created_at = NOW(),
                    status = CASE
                        WHEN jurisdiction_coverage_requests.status = 'dismissed'
                        THEN jurisdiction_coverage_requests.status
                        ELSE 'pending'
                    END
            """,
            jur["city"], jur["state"], jur["county"], company_id, loc_uuid, note,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("matcha-x: failed to queue jurisdiction research: %s", exc)


class MatchaXBuildRequest(BaseModel):
    # The exact string returned by POST /matcha-x-onboarding/handbook-upload.
    # Optional — absent / non-PDF / not-owned ⇒ the coverage overlay is skipped.
    handbook_url: Optional[str] = None


@router.post("/build/stream")
async def build_compliance_baseline_stream(
    data: MatchaXBuildRequest,
    current_user=Depends(require_admin_or_client),
):
    """Loop the company's locations through the live compliance engine
    (``run_compliance_check_stream`` with the lite category set + live
    research), pass each child event through tagged per-location, then overlay
    the uploaded handbook's coverage per state. SSE envelope mirrors the admin
    enrich stream (``data: {json}\\n\\n``, ``: heartbeat``, terminal
    ``data: [DONE]``).
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")

    handbook_url = (data.handbook_url or "").strip() or None

    async def events():
        # `handbook_url` is reassigned below (→ None on reject/non-PDF); declare it
        # nonlocal so those writes don't shadow the outer binding and turn the
        # earlier reads into an UnboundLocalError that crashes every build.
        nonlocal handbook_url
        # 1. Load active locations + company context (short-lived connection).
        async with get_connection() as conn:
            company = await conn.fetchrow(
                "SELECT name FROM companies WHERE id = $1", company_id
            )
            if not company:
                yield {"type": "error", "message": "Company not found"}
                return
            locs = await conn.fetch(
                """
                SELECT id, name, city, state
                FROM business_locations
                WHERE company_id = $1 AND is_active = true
                ORDER BY name NULLS LAST, city
                """,
                company_id,
            )
            industry_profile = await _get_industry_profile(conn, company_id)
            # D3.2: roster-derived work locations feed the build too — check
            # before deciding whether there's anything to build (a CSV-only
            # company with no typed location must still build from roster).
            _roles, _emp_locs, _existing_keys, skipped_no_work_state = (
                await collect_roster_jurisdictions(conn, company_id)
            )
        industry = (industry_profile or {}).get("canonical_industry")
        company_name = company["name"] or "your company"
        roster_new_keys = [k for k in _emp_locs if k not in _existing_keys]

        def _label(row) -> str:
            return row["name"] or f"{row['city']}, {row['state']}"

        if not locs and not roster_new_keys:
            yield {
                "type": "complete",
                "locations": 0,
                "jurisdictions": 0,
                "requirements": 0,
                "codified_new": 0,
                "handbook_states_graded": 0,
                "handbook_coverage_pct": None,
                "roster_locations_added": 0,
                "skipped_no_work_state": skipped_no_work_state,
                "message": "Add a location or an employee with a work state to build your compliance baseline.",
            }
            return

        yield {
            "type": "started",
            "message": f"Building {company_name}'s compliance baseline…",
        }
        yield {
            "type": "locations_scanned",
            "count": len(locs),
            "labels": [_label(l) for l in locs],
            "message": (
                f"{len(locs)} location(s) — each gets its own local compliance."
                if locs
                else "No locations added yet — building from your employee roster."
            ),
        }

        # 2. Kick off handbook section extraction in parallel so it overlaps the
        #    location loop (it's a slow Gemini call). PDF-only in v1.
        #    Reject any handbook_url not issued to THIS company (IDOR / arbitrary
        #    file read guard) before it ever reaches storage.download_file.
        section_task = None
        if handbook_url and not _is_owned_handbook_url(handbook_url, company_id):
            yield {
                "type": "handbook_skipped",
                "reason": "invalid",
                "message": "Handbook reference not recognized — skipping coverage overlay.",
            }
            handbook_url = None
        if handbook_url and handbook_url.lower().split("?")[0].endswith(".pdf"):
            yield {"type": "handbook_detected", "message": "Reading your handbook…"}

            async def _extract():
                try:
                    pdf_bytes = await get_storage().download_file(handbook_url)
                except Exception:
                    return None
                if not pdf_bytes:
                    return None
                return await _extract_sections_from_pdf(pdf_bytes)

            section_task = asyncio.create_task(_extract())
        elif handbook_url:
            yield {
                "type": "handbook_skipped",
                "reason": "non_pdf",
                "message": "Handbook coverage overlay supports PDF uploads only.",
            }

        # 3. Build each location live.
        total_covered = 0
        total_codified = 0
        jurisdictions_seen: set = set()

        for loc in locs:
            loc_id = loc["id"]
            label = _label(loc)
            yield {
                "type": "location_start",
                "location_id": str(loc_id),
                "label": label,
                "city": loc["city"],
                "state": loc["state"],
                "message": f"Resolving jurisdiction for {label}…",
            }

            # Count directory rows before, to surface "codified live" delta.
            async with get_connection() as conn:
                jid_before = await conn.fetchval(
                    "SELECT jurisdiction_id FROM business_locations WHERE id = $1",
                    loc_id,
                )
                before_count = 0
                if jid_before:
                    before_count = (
                        await conn.fetchval(
                            "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                            jid_before,
                        )
                        or 0
                    )

            researched_live = False
            try:
                # Projection-only: NO Gemini on a tenant build. Catalog gaps get
                # queued for our research team (repository_only → enqueue below),
                # never researched live on the tenant's dime.
                async for ev in run_compliance_check_stream(
                    loc_id,
                    company_id,
                    allow_live_research=False,
                    allow_repository_refresh=False,
                    categories=MATCHA_X_LITE_CATEGORIES,
                ):
                    etype = ev.get("type")
                    if etype == "heartbeat":
                        yield {"type": "heartbeat"}
                        continue
                    if etype == "error":
                        # Recoverable per-location hiccup → warning, keep going.
                        yield {
                            "type": "warning",
                            "message": ev.get("message") or f"Research issue for {label}",
                            "location_id": str(loc_id),
                            "label": label,
                        }
                        continue
                    if etype == "repository_only":
                        # Catalog gap → queue for our side, tell the tenant it's handled.
                        async with get_connection() as qconn:
                            await _queue_jurisdiction_research(
                                qconn, ev.get("jurisdiction_id"), company_id, loc_id,
                                ev.get("missing_categories") or [], industry,
                            )
                        yield {
                            "type": "queued_for_research",
                            "location_id": str(loc_id),
                            "label": label,
                            "message": (
                                f"{label}: new requirement areas queued for our "
                                "research team — they appear automatically once published."
                            ),
                        }
                        continue
                    yield {**ev, "location_id": str(loc_id), "label": label}
            except Exception as exc:
                yield {
                    "type": "warning",
                    "message": f"Build incomplete for {label}: {exc}",
                    "location_id": str(loc_id),
                    "label": label,
                }

            # Post-build counts.
            async with get_connection() as conn:
                jid = await conn.fetchval(
                    "SELECT jurisdiction_id FROM business_locations WHERE id = $1",
                    loc_id,
                )
                after_count = before_count
                if jid:
                    after_count = (
                        await conn.fetchval(
                            "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                            jid,
                        )
                        or 0
                    )
                covered = (
                    await conn.fetchval(
                        "SELECT COUNT(*) FROM compliance_requirements WHERE location_id = $1",
                        loc_id,
                    )
                    or 0
                )
            codified_new = max(0, after_count - before_count)
            total_covered += covered
            total_codified += codified_new
            if jid:
                jurisdictions_seen.add(str(jid))

            yield {
                "type": "location_built",
                "location_id": str(loc_id),
                "label": label,
                "covered": covered,
                "codified_new": codified_new,
                "researched_live": researched_live,
                "message": (
                    f"{label}: {covered} requirement(s) mapped"
                    + (f", {codified_new} newly codified" if codified_new else "")
                ),
            }

        # 3b. Union roster-derived jurisdictions (D3.2) — work states the roster
        # reports that aren't covered by a typed location yet. Projection-only,
        # same as the typed-location loop above: catalog gaps get queued for our
        # research team, never researched live on the tenant's build.
        roster_locations_added = 0
        async for ev in sync_and_check_roster_jurisdictions(
            get_connection,
            company_id,
            allow_live_research=False,
            allow_repository_refresh=False,
            categories=MATCHA_X_LITE_CATEGORIES,
        ):
            etype = ev.get("type")
            if etype == "heartbeat":
                yield {"type": "heartbeat"}
                continue
            if etype == "repository_only":
                async with get_connection() as qconn:
                    await _queue_jurisdiction_research(
                        qconn, ev.get("jurisdiction_id"), company_id,
                        ev.get("location_id"), ev.get("missing_categories") or [], industry,
                    )
                yield {
                    "type": "queued_for_research",
                    "location_id": ev.get("location_id"),
                    "label": ev.get("label"),
                    "message": (
                        f"{ev.get('label') or 'A roster location'}: new requirement "
                        "areas queued for our research team — they appear "
                        "automatically once published."
                    ),
                }
                continue
            if etype == "location_built":
                roster_locations_added += 1
                total_covered += ev.get("covered", 0)
                total_codified += ev.get("codified_new", 0)
                jid = ev.get("jurisdiction_id")
                if jid:
                    jurisdictions_seen.add(jid)
            yield ev

        # 3c. Vertical (industry sub-specialty) coverage — projection-only.
        # A tenant build NEVER researches. We detect the specialty gaps (all
        # pure SQL: resolve → ledger reconcile → plan) and QUEUE them; our side
        # runs the actual Gemini fill via the vertical_coverage_sweep worker
        # (admin: Schedulers → Run now), which then reprojects tenant tabs. So
        # dental-specific rows appear automatically once we've researched them —
        # without spending on the customer's onboarding click.
        vertical_label = None
        vertical_queued = 0
        vertical_minted = False
        try:
            async with get_connection() as vconn:
                resolved = await vertical_coverage.resolve_vertical(vconn, company_id)

            if resolved:
                v_parent, v_slug, v_label, v_tag, vertical_minted = resolved
                vertical_label = v_label

                # Cached categories ONLY — never ensure_specialty(), which triggers
                # Gemini discovery for a brand-new vertical. An undiscovered
                # specialty is itself a gap to queue for the sweep.
                async with get_connection() as vconn:
                    cat_rows = await vconn.fetch(
                        "SELECT slug FROM compliance_categories WHERE industry_tag = $1",
                        v_tag,
                    )
                v_categories = [r["slug"] for r in cat_rows]

                plan = []
                if v_categories and jurisdictions_seen:
                    async with get_connection() as vconn:
                        leaf_chains = await vertical_coverage.chains_for_leaves(
                            vconn, [UUID(j) for j in jurisdictions_seen]
                        )
                        all_nodes = sorted(
                            {jid for chain in leaf_chains.values() for jid, _ in chain}
                        )
                        # Reconcile the ledger with what the catalog already holds
                        # so a seeded vertical isn't re-flagged as a gap.
                        await vertical_coverage.backfill_ledger(
                            vconn, all_nodes, v_tag, v_categories
                        )
                        plan, _deferred = await vertical_coverage.plan_fill(
                            vconn, leaf_chains, v_tag, v_categories
                        )

                # Undiscovered specialty OR unresolved cells → queue for our team.
                if not v_categories or plan:
                    vertical_queued = len(plan) if plan else 1
                    yield {
                        "type": "vertical_queued",
                        "vertical": v_label,
                        "cells": vertical_queued,
                        "message": (
                            f"{v_label}: specialty requirement areas queued for our "
                            "research team — they appear automatically once published."
                        ),
                    }

                # Reproject ONLY when resolve_vertical just minted the specialty
                # tag onto the company (SQL-only, Gemini-free): every projection
                # made before that write filtered the vertical's existing rows
                # out, so the tenant needs a re-read to see catalog rows we
                # already hold. New research is NOT done here — the sweep does it.
                if vertical_minted:
                    async with get_connection() as vconn:
                        all_locs = await vconn.fetch(
                            "SELECT id FROM business_locations "
                            "WHERE company_id = $1 AND is_active = true",
                            company_id,
                        )
                        for row in all_locs:
                            await vertical_coverage.reproject_location(
                                vconn, company_id, row["id"]
                            )
        except Exception as exc:
            # Vertical scoping is additive — never fail a build over it.
            yield {
                "type": "warning",
                "message": f"Vertical scoping incomplete: {exc}",
            }

        # 4. Handbook coverage overlay (per state present across locations).
        handbook_states_graded = 0
        hb_covered = 0
        hb_total = 0
        if section_task is not None:
            async for evt in _heartbeat_while(section_task):
                yield evt
            try:
                sections = section_task.result()
            except Exception:
                sections = None

            if not sections:
                yield {
                    "type": "handbook_skipped",
                    "reason": "unreadable",
                    "message": "Couldn't read the handbook — skipping coverage overlay.",
                }
            else:
                async with get_connection() as conn:
                    req_rows = await conn.fetch(
                        """
                        SELECT bl.state AS state, cr.category, cr.title,
                               cr.description, cr.source_url
                        FROM compliance_requirements cr
                        JOIN business_locations bl ON bl.id = cr.location_id
                        WHERE bl.company_id = $1 AND bl.is_active = true
                        """,
                        company_id,
                    )
                by_state: dict = {}
                for r in req_rows:
                    st = (r["state"] or "").upper()
                    if not st:
                        continue
                    by_state.setdefault(st, []).append(
                        {
                            "category": r["category"],
                            "title": r["title"],
                            "description": r["description"],
                            "source_url": r["source_url"],
                        }
                    )

                for st, reqs in by_state.items():
                    if not reqs:
                        continue
                    yield {
                        "type": "handbook_grading",
                        "state": st,
                        "message": f"Matching your handbook against {st} law…",
                    }
                    grade_task = asyncio.create_task(
                        _grade_state_coverage(
                            state=st,
                            industry=industry,
                            requirements=reqs,
                            sections=sections,
                        )
                    )
                    async for evt in _heartbeat_while(grade_task):
                        yield evt
                    try:
                        results = grade_task.result()
                    except Exception:
                        results = None
                    if not results:
                        continue
                    covered_items = [r for r in results if r.get("covered")]
                    gaps = [r for r in results if not r.get("covered")]
                    handbook_states_graded += 1
                    hb_covered += len(covered_items)
                    hb_total += len(results)
                    yield {
                        "type": "handbook_coverage",
                        "state": st,
                        "covered": covered_items,
                        "gaps": gaps,
                        "covered_count": len(covered_items),
                        "gap_count": len(gaps),
                        "message": (
                            f"{st}: {len(covered_items)} covered, {len(gaps)} gap(s)"
                        ),
                    }

        # Shadow the scope registry against this self-serve build (fire-and-forget,
        # fully guarded — mirrors the admin onboarding wizard's finalize hook,
        # COMPLIANCE_SYSTEM_GAP_REVIEW.md §2's "self-serve unshadowed" gap).
        # Self-serve has no onboarding_sessions row and never calls map_to_bank,
        # so existing_items is built from what this run actually projected
        # (compliance_requirements.jurisdiction_requirement_id) rather than a
        # bank-resolution result — record_shadow only reads requirement_id off
        # each item, so that's all this needs to supply.
        async with get_connection() as shadow_conn:
            shadow_rows = await shadow_conn.fetch(
                """
                SELECT DISTINCT jurisdiction_requirement_id
                FROM compliance_requirements cr
                JOIN business_locations bl ON bl.id = cr.location_id
                WHERE bl.company_id = $1 AND cr.jurisdiction_requirement_id IS NOT NULL
                """,
                company_id,
            )
        if shadow_rows:
            from app.core.services.scope_registry.shadow import record_shadow
            shadow_existing = [{"requirement_id": r["jurisdiction_requirement_id"]} for r in shadow_rows]
            # Awaited, not create_task'd: a task spawned from inside an SSE
            # generator gets cancelled when the response closes. record_shadow
            # is fully guarded (never raises) and this stream is already long,
            # so paying its cost inline before the terminal event is fine.
            await record_shadow(
                session_id=None, company_id=company_id, industry=industry,
                existing_items=shadow_existing,
            )

        coverage_pct = round(100 * hb_covered / hb_total) if hb_total else None

        # Recount rather than reuse `total_covered`: that was summed per-location in
        # step 3, before the vertical fill (3c) added rows and reprojected. The
        # headline number on the finished screen was understating what the tenant
        # actually has every time a vertical contributed.
        # No `or total_covered` fallback: COUNT(*) never returns NULL, and the
        # one case a falsy fallback would fire — a genuine zero — is exactly the
        # case it must not paper over with the stale pre-fill sum.
        async with get_connection() as conn:
            final_covered = await conn.fetchval(
                """
                SELECT COUNT(*) FROM compliance_requirements cr
                JOIN business_locations bl ON bl.id = cr.location_id
                WHERE bl.company_id = $1 AND bl.is_active = true
                """,
                company_id,
            )

        yield {
            "type": "complete",
            "locations": len(locs) + roster_locations_added,
            "jurisdictions": len(jurisdictions_seen),
            "requirements": final_covered,
            "codified_new": total_codified,
            "handbook_states_graded": handbook_states_graded,
            "handbook_coverage_pct": coverage_pct,
            "roster_locations_added": roster_locations_added,
            "skipped_no_work_state": skipped_no_work_state,
            "vertical": vertical_label,
            "vertical_queued": vertical_queued,
            "message": "Your compliance baseline is live.",
        }

    async def sse():
        try:
            async for ev in events():
                if ev.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as exc:  # last-resort guard so the stream always closes
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )
