"""Roster -> jurisdiction derivation, shared by the admin white-glove
enrichment flow (``core/routes/admin_onboarding.py``) and the Matcha-X
self-serve onboarding build (``matcha/routes/matcha_x_onboarding.py``), plus
post-onboarding jurisdiction drift detection.

Implements Phase D3 (lift the roster-scan logic out of admin_onboarding.py so
both flows share one implementation) and Phase D4 (alert-only drift
detection after roster mutations) of COMPLIANCE_REMEDIATION_PLAN.md.

Service-only module: import database + other services only, never route
modules — admin_onboarding.py, matcha_x_onboarding.py, and the employees
routes all import this file, so an import back to any of them would cycle.
"""
import logging
from typing import AsyncGenerator, Callable, Optional
from uuid import UUID

from app.database import get_connection
from app.core.feature_flags import merge_company_features

logger = logging.getLogger(__name__)


async def collect_roster_jurisdictions(
    conn, company_id: UUID
) -> tuple[list[str], dict, set, int]:
    """Distinct active-employee work locations + roles for a company.

    Returns (roles, emp_locs, existing_location_keys, skipped_no_work_state)
    where emp_locs is keyed by (lower_city, upper_state) -> (display_city,
    upper_state), existing_location_keys are the same keys already tracked as
    business_locations (so callers know which jurisdictions are NEW), and
    skipped_no_work_state is the count of active employees (rows, not
    distinct locations) dropped from the roster scan because they have no
    `work_state` on file (so callers can surface that the scope may be
    incomplete, rather than silently missing those employees' jurisdictions).
    """
    emp_rows = await conn.fetch(
        """
        SELECT work_city, work_state, job_title
        FROM employees
        WHERE org_id = $1 AND termination_date IS NULL
        """,
        company_id,
    )
    skipped_no_work_state = 0
    role_set: set[str] = set()
    emp_locs: dict[tuple[str, str], tuple[str, str]] = {}
    for r in emp_rows:
        state = (r["work_state"] or "").upper().strip()
        if not state:
            skipped_no_work_state += 1
            continue
        if r["job_title"] and r["job_title"].strip():
            role_set.add(r["job_title"].strip())
        city = (r["work_city"] or "").strip()
        emp_locs.setdefault((city.lower(), state), (city, state))
    roles = sorted(role_set)

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
    return roles, emp_locs, existing_keys, skipped_no_work_state


async def sync_and_check_roster_jurisdictions(
    conn_factory: Callable[[], "object"],
    company_id: UUID,
    *,
    allow_live_research: bool,
    categories: Optional[list[str]] = None,
) -> AsyncGenerator[dict, None]:
    """D3.2 — union roster-derived jurisdictions into a live build.

    For every distinct roster (city, state) not already tracked as a
    business_location, creates the location (``ensure_location_for_employee``
    — same helper the admin enrich flow uses) and runs it through
    ``run_compliance_check_stream`` with the SAME ``allow_live_research`` /
    ``categories`` the caller uses for its typed locations, so roster-derived
    jurisdictions get identical treatment. Yields SSE-shaped progress dicts
    tagged ``source: "roster"``; a per-location ``location_built`` event
    carries ``jurisdiction_id``/``covered``/``codified_new`` so the caller can
    fold roster locations into its own running totals exactly like typed ones.

    ``conn_factory`` is an async-context-manager factory (pass ``get_connection``)
    — each step opens its own short-lived connection so a slow Gemini research
    call never holds a pooled connection, matching the pattern used by the
    admin enrich stream and the Matcha-X build stream.
    """
    # Lazy import: compliance_service is the big module route files import
    # from; importing it at module load time here would risk a cycle given
    # how many places import this file.
    from app.core.services.compliance_service import (
        ensure_location_for_employee,
        run_compliance_check_stream,
    )

    async with conn_factory() as conn:
        roles, emp_locs, existing_keys, skipped_no_work_state = (
            await collect_roster_jurisdictions(conn, company_id)
        )

    new_keys = [k for k in emp_locs if k not in existing_keys]
    skipped_note = (
        f" {skipped_no_work_state} employee(s) skipped (no work state on file)."
        if skipped_no_work_state
        else ""
    )
    yield {
        "type": "roster_scanned",
        "source": "roster",
        "locations_total": len(emp_locs),
        "locations_new": len(new_keys),
        "roles": roles,
        "skipped_no_work_state": skipped_no_work_state,
        "message": (
            f"Checked your roster — {len(new_keys)} work location(s) not yet in your build."
            f"{skipped_note}"
        ),
    }

    for key in new_keys:
        city, state = emp_locs[key]
        label = f"{city + ', ' if city else ''}{state}"
        yield {
            "type": "jurisdiction_new",
            "source": "roster",
            "city": city or None,
            "state": state,
            "message": f"Roster implies a work location in {label} — adding it to your build.",
        }

        try:
            async with conn_factory() as conn:
                location_id = await ensure_location_for_employee(
                    conn, company_id, city or None, state,
                )
        except Exception:
            logger.exception("roster build: ensure_location failed for %s", label)
            yield {
                "type": "warning", "source": "roster",
                "message": f"Could not add roster location {label}.",
            }
            continue
        if not location_id:
            continue

        async with conn_factory() as conn:
            jid_before = await conn.fetchval(
                "SELECT jurisdiction_id FROM business_locations WHERE id = $1",
                location_id,
            )
            before_count = 0
            if jid_before:
                before_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                    jid_before,
                ) or 0

        researched_live = False
        try:
            async for ev in run_compliance_check_stream(
                location_id, company_id,
                allow_live_research=allow_live_research,
                categories=categories,
            ):
                etype = ev.get("type")
                if etype == "heartbeat":
                    yield {"type": "heartbeat"}
                    continue
                if etype == "error":
                    yield {
                        "type": "warning", "source": "roster",
                        "message": ev.get("message") or f"Research issue for {label}",
                        "location_id": str(location_id), "label": label,
                    }
                    continue
                if etype in (
                    "researching", "repository_refresh",
                    "discovering_sources", "trigger_research",
                ):
                    researched_live = True
                yield {**ev, "source": "roster", "location_id": str(location_id), "label": label}
        except Exception as exc:
            logger.exception("roster build: research failed for %s", label)
            yield {
                "type": "warning", "source": "roster",
                "message": f"Build incomplete for {label}: {exc}",
                "location_id": str(location_id), "label": label,
            }

        async with conn_factory() as conn:
            jid = await conn.fetchval(
                "SELECT jurisdiction_id FROM business_locations WHERE id = $1",
                location_id,
            )
            after_count = before_count
            if jid:
                after_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                    jid,
                ) or 0
            covered = await conn.fetchval(
                "SELECT COUNT(*) FROM compliance_requirements WHERE location_id = $1",
                location_id,
            ) or 0
        codified_new = max(0, after_count - before_count)

        yield {
            "type": "location_built",
            "source": "roster",
            "location_id": str(location_id),
            "jurisdiction_id": str(jid) if jid else None,
            "label": label,
            "city": city or None,
            "state": state,
            "covered": covered,
            "codified_new": codified_new,
            "researched_live": researched_live,
            "message": (
                f"{label} (from roster): {covered} requirement(s) mapped"
                + (f", {codified_new} newly codified" if codified_new else "")
            ),
        }


# ── D4: post-onboarding drift detection (alert-only, never triggers research) ──


_DRIFT_CATEGORY = "jurisdiction_drift"


async def detect_jurisdiction_drift(conn, company_id: UUID) -> Optional[dict]:
    """Compare the roster's implied work-state footprint against the
    company's tracked (jurisdiction-linked) locations and the signup-declared
    jurisdiction count; alert on drift. Alert-only — NEVER schedules research.

    Self-contained: swallows and logs its own errors so callers can fire it
    as a bare background task without their own try/except. Returns a summary
    dict (or None on internal failure / when gated off for this company).
    """
    try:
        company = await conn.fetchrow(
            "SELECT enabled_features, signup_source FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            return None

        loc_rows = await conn.fetch(
            """
            SELECT DISTINCT UPPER(state) AS state
            FROM business_locations
            WHERE company_id = $1 AND is_active = TRUE
              AND jurisdiction_id IS NOT NULL AND state IS NOT NULL
            """,
            company_id,
        )
        covered_states = {r["state"] for r in loc_rows if r["state"]}

        features = merge_company_features(company["enabled_features"], company["signup_source"])
        has_compliance = bool(features.get("compliance") or features.get("compliance_lite"))
        if not has_compliance and not covered_states:
            # Not a Compliance tenant and no jurisdiction-linked location to
            # anchor an alert to anyway — avoid alert spam for non-compliance
            # companies (D4 gating requirement).
            return None

        roster_rows = await conn.fetch(
            """
            SELECT DISTINCT UPPER(work_state) AS state
            FROM employees
            WHERE org_id = $1 AND termination_date IS NULL AND work_state IS NOT NULL
            """,
            company_id,
        )
        roster_states = {r["state"] for r in roster_rows if r["state"]}
        drift_states = sorted(roster_states - covered_states)

        # Need a location row to anchor compliance_alerts.location_id (NOT NULL).
        anchor_location_id = await conn.fetchval(
            """
            SELECT id FROM business_locations
            WHERE company_id = $1 AND is_active = TRUE
            ORDER BY created_at ASC LIMIT 1
            """,
            company_id,
        )

        alerts_created: list[str] = []
        if anchor_location_id:
            for state in drift_states:
                title = f"Roster implies compliance jurisdiction not in your build: {state}"
                existing = await conn.fetchval(
                    """
                    SELECT id FROM compliance_alerts
                    WHERE company_id = $1 AND title = $2 AND status != 'dismissed'
                    """,
                    company_id, title,
                )
                if existing:
                    continue
                await conn.execute(
                    """
                    INSERT INTO compliance_alerts (
                        location_id, company_id, title, message, severity, status,
                        category, alert_type
                    )
                    VALUES ($1, $2, $3, $4, 'warning', 'unread', $5, 'review_recommended')
                    """,
                    anchor_location_id, company_id, title,
                    (
                        f"Your employee roster includes staff working in {state}, but no "
                        f"tracked location covers {state} compliance requirements yet. Add "
                        f"a location there or review your build."
                    ),
                    _DRIFT_CATEGORY,
                )
                alerts_created.append(state)

            # Reconciliation: signup-declared jurisdiction count vs. computed.
            declared = await conn.fetchval(
                "SELECT compliance_jurisdiction_count FROM company_handbook_profiles WHERE company_id = $1",
                company_id,
            )
            computed = len(covered_states | roster_states)
            if declared is not None and declared < computed:
                recon_title = "Your declared jurisdiction count is behind your actual footprint"
                existing = await conn.fetchval(
                    """
                    SELECT id FROM compliance_alerts
                    WHERE company_id = $1 AND title = $2 AND status != 'dismissed'
                    """,
                    company_id, recon_title,
                )
                if not existing:
                    await conn.execute(
                        """
                        INSERT INTO compliance_alerts (
                            location_id, company_id, title, message, severity, status,
                            category, alert_type
                        )
                        VALUES ($1, $2, $3, $4, 'info', 'unread', $5, 'review_recommended')
                        """,
                        anchor_location_id, company_id, recon_title,
                        (
                            f"You declared {declared} jurisdiction(s) at signup; your roster "
                            f"and locations now imply {computed}."
                        ),
                        _DRIFT_CATEGORY,
                    )
                    alerts_created.append("reconciliation")

        return {"drift_states": drift_states, "alerts_created": alerts_created}
    except Exception:
        logger.exception("detect_jurisdiction_drift failed for company %s", company_id)
        return None


async def run_jurisdiction_drift_check(company_id: UUID) -> None:
    """Background-task entry point (mirrors `_refresh_risk_assessment`'s
    shape in `employees/_shared.py`): opens its own connection so it's safe
    to pass directly to `BackgroundTasks.add_task` or `await` inline from a
    non-route service (e.g. `hris_sync_orchestrator.start_hris_sync`)."""
    async with get_connection() as conn:
        await detect_jurisdiction_drift(conn, company_id)
