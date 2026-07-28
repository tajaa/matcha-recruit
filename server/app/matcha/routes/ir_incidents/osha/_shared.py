"""Helpers shared by two or more of the OSHA sub-surfaces.

Only what genuinely crosses a group boundary lives here: the export
attestation gate (logs + 300A + ITA) and the 300A aggregation and headcount
resolution (300A + ITA).
"""
import logging

from fastapi import HTTPException

from app.matcha.routes.ir_incidents._shared import log_audit

logger = logging.getLogger(__name__)


# Unified onto the one shared implementation (refactor round 2, stage 4-5 audit).
# This module used to carry its own copy, justified as a permanent exception on
# "different default semantics" — the local one returned `default` (None) where
# the shared one returns `{}`. That difference is UNREACHABLE: all 8 call sites in
# this package pass an explicit `{}`, so the None branch was never taken. The only
# input the two disagree on given `{}` is a bare int, and these values come from
# JSONB columns with no asyncpg type codec registered, which decode to `str` (or
# None for NULL) — never an int. Verified case-by-case before merging them.
from app.matcha.services._shared.jsonio import safe_json_loads as _safe_json_loads  # noqa: F401


# Non-privacy incidents with no structured injury data still must NOT show the
# raw reporter narrative (it can name patients / third parties). Show a neutral
# pointer instead — the full narrative lives only on the internal incident record.


# Reviewer attestation gate for the OSHA file exports. Recordability,
# description cleansing, and Privacy Case masking are AI-assisted, so the human
# filing the record must confirm they reviewed it before anything leaves the
# system. That acknowledgement (audited per export) is what places accuracy +
# submission responsibility on the employer rather than the tool.
EXPORT_DISCLAIMER = (
    "This OSHA log was prepared with AI-assisted recordability classification, "
    "injury-description cleansing, and Privacy Case name masking. These are aids, "
    "not a substitute for your review. Before filing with OSHA or any agency you "
    "are responsible for verifying every entry — recordability, day counts, "
    "Privacy Case masking, and descriptions. Matcha does not guarantee the "
    "accuracy or completeness of generated entries. By exporting you confirm you "
    "have reviewed this data and accept responsibility for its accuracy and filing."
)


async def _attest_export(conn, current_user, *, form: str, year: int, attested: bool, location_id=None):
    """Gate an OSHA file export behind a reviewer attestation + record it.

    The export endpoints emit the artifact that actually gets filed with OSHA, so
    each download requires the user to confirm they reviewed the data (``attested``).
    Missing → 403 carrying the disclaimer (the UI renders it in a confirm modal).
    Present → an ``osha_export_attested`` audit row (who / when / which form +
    year + establishment) is written before the file streams — the record that a
    human, not the AI, signed off on this export.
    """
    if not attested:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "attestation_required",
                "disclaimer": EXPORT_DISCLAIMER,
                "form": form,
                "year": year,
            },
        )
    await log_audit(
        conn, None, str(current_user.id), "osha_export_attested",
        entity_type="osha_export",
        entity_id=str(location_id) if location_id else None,
        details={
            "form": form,
            "year": year,
            "location_id": str(location_id) if location_id else None,
        },
    )


async def _aggregate_300a(conn, company_id, location_id, year) -> dict:
    """Aggregate recordable-CASE totals for one establishment in one year.

    Counts one OSHA case per injured employee from ``ir_osha_case_details`` (each
    case's own classification / days / M-column injury type), UNION the
    incident-level values for any recordable incident that has no case rows yet
    (legacy / not-yet-captured) so nothing is undercounted. Single source of the
    300A column math — shared by the summary endpoint, the PDF, and the ITA
    export so the three can never drift. NULL injury type → Standard Injury.
    """
    return await conn.fetchrow(
        """
        WITH cases AS (
            SELECT cd.classification, cd.days_away, cd.days_restricted, cd.injury_type
            FROM ir_osha_case_details cd
            JOIN ir_incidents i ON i.id = cd.incident_id
            WHERE i.company_id = $1
              AND i.location_id = $2
              AND i.osha_recordable = true
              AND EXTRACT(YEAR FROM i.occurred_at) = $3
            UNION ALL
            SELECT i.osha_classification, COALESCE(i.days_away_from_work, 0),
                   COALESCE(i.days_restricted_duty, 0), i.osha_form_301_data->>'injury_type'
            FROM ir_incidents i
            WHERE i.company_id = $1
              AND i.location_id = $2
              AND i.osha_recordable = true
              AND EXTRACT(YEAR FROM i.occurred_at) = $3
              AND NOT EXISTS (SELECT 1 FROM ir_osha_case_details cd WHERE cd.incident_id = i.id)
        )
        SELECT
            COUNT(*) AS total_cases,
            COALESCE(SUM(CASE WHEN classification = 'death' THEN 1 ELSE 0 END), 0) AS total_deaths,
            COALESCE(SUM(CASE WHEN classification = 'days_away' THEN 1 ELSE 0 END), 0) AS total_days_away_cases,
            COALESCE(SUM(CASE WHEN classification = 'restricted_duty' THEN 1 ELSE 0 END), 0) AS total_restricted_cases,
            -- Columns G/H/I/J must partition total_cases. A recordable case with a
            -- NULL/unrecognized classification is neither death/days_away/restricted,
            -- and `NULL NOT IN (...)` is NULL (falls to ELSE 0) — so without the
            -- COALESCE it would be dropped from every column while still counted in
            -- total_cases, breaking the OSHA footing G+H+I+J = total_cases.
            COALESCE(SUM(CASE WHEN COALESCE(classification, 'other') NOT IN ('death','days_away','restricted_duty') THEN 1 ELSE 0 END), 0) AS total_other_recordable,
            -- Per 29 CFR 1904.7(b)(3)(vii) the day count for a single case is capped
            -- at 180 for each of columns K and L. Cap per case BEFORE summing.
            COALESCE(SUM(LEAST(COALESCE(days_away, 0), 180)), 0) AS total_days_away,
            COALESCE(SUM(LEAST(COALESCE(days_restricted, 0), 180)), 0) AS total_days_restricted,
            -- M1..M6 must also partition total_cases: NULL and any unrecognized
            -- injury_type fall through to "all other illnesses" (M6) rather than
            -- vanishing. M1 (injuries) is the explicit-injury/NULL bucket.
            COALESCE(SUM(CASE WHEN COALESCE(injury_type, 'injury') = 'injury' THEN 1 ELSE 0 END), 0) AS total_injuries,
            COALESCE(SUM(CASE WHEN injury_type = 'skin_disorder' THEN 1 ELSE 0 END), 0) AS total_skin_disorders,
            COALESCE(SUM(CASE WHEN injury_type = 'respiratory' THEN 1 ELSE 0 END), 0) AS total_respiratory,
            COALESCE(SUM(CASE WHEN injury_type = 'poisoning' THEN 1 ELSE 0 END), 0) AS total_poisonings,
            COALESCE(SUM(CASE WHEN injury_type = 'hearing_loss' THEN 1 ELSE 0 END), 0) AS total_hearing_loss,
            COALESCE(SUM(CASE WHEN injury_type IS NOT NULL
                               AND injury_type NOT IN ('injury','skin_disorder','respiratory','poisoning','hearing_loss')
                          THEN 1 ELSE 0 END), 0) AS total_other_illnesses
        FROM cases
        """,
        company_id, location_id, year,
    )


async def _active_headcount(conn, company_id, location_id, *, city=None, state=None, sole_location=False) -> int:
    """Active-employee count for an establishment — the OSHA 300A avg-employees default.

    HRIS/Finch sync populates work_city/work_state but never the work_location_id
    FK (and Finch sandbox cities are random), so an FK-only count returns ~0 for an
    imported roster. Resolution order:
      1. sole_location → every active employee in the org belongs to it. This is the
         common single-site matcha-lite case and what lets Finch-synced headcount
         actually flow into the 300A.
      2. else FK match OR a work_city/work_state heuristic, mirroring
         compliance_service.get_employee_impact_for_location (the FK is set on only a
         minority of rows; the heuristic catches the rest).
    'active' = termination_date IS NULL, matching the rest of the location-headcount
    code (delete_location guard, compliance dashboard) so counts stay consistent.
    Always overridable via the saved average_employees.
    """
    if sole_location:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
            company_id,
        ) or 0
    return await conn.fetchval(
        """
        SELECT COUNT(*) FROM employees
        WHERE org_id = $1
          AND termination_date IS NULL
          AND (
            work_location_id = $2
            OR (
              work_location_id IS NULL
              AND $3::text IS NOT NULL
              AND LOWER(work_city) = LOWER($3)
              AND UPPER(work_state) = UPPER($4)
            )
          )
        """,
        company_id, location_id, city, state,
    ) or 0
